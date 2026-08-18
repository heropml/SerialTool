# -*- coding: utf-8 -*-
"""网络连接层：TCP Server / TCP Client / UDP，统一接口供主窗口调用。

基于 QtNetwork（事件驱动，无需轮询线程）。对外语义对齐原来的串口连接：
    open() -> bool   建立连接/监听（同步失败返回 False，异步连接返回 True 后由信号通知）
    close()          断开/停止
    send(data, target=None) -> int   返回写出的字节数；<0 = 软错误（无可发送目标）
    is_open          能否发送

信号：
    data_received(bytes)   收到数据（统一入口，等价原 SerialReader.data_received）
    data_received_from(bytes, key)  TCP Server 专用，收到数据及其来源客户端
    error_occurred(str)    socket 错误（致命，主窗口会断开并提示）
    state_changed(bool)    True=已连接/监听中；False=对端断开/停止
    clients_changed(list)  TCP Server 专用，已连接客户端 [(key, label)]
"""
import logging
import socket as _socket

from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtNetwork import (
    QTcpServer, QTcpSocket, QUdpSocket, QHostAddress, QAbstractSocket,
    QNetworkInterface,
)

from automation.safe_step import safe_step

PROTO_TCP_SERVER = "TCP Server"
PROTO_TCP_CLIENT = "TCP Client"
PROTO_UDP = "UDP"
PROTO_UDP_MULTICAST = "UDP Multicast"
PROTOCOLS = [PROTO_UDP, PROTO_UDP_MULTICAST, PROTO_TCP_SERVER, PROTO_TCP_CLIENT]

SEND_NO_TARGET = -1   # send() 软错误：没有可发送的目标（UDP 无对端 / TCP Server 无客户端）

# TCP Client 连接超时的错误哨兵：emit 它而非硬编码中文，由主窗口按 i18n 翻译成当前语言
ERR_CONN_TIMEOUT = "__conn_timeout__"
# 普通发送因写缓冲积压丢弃：非致命，主窗口/桥接面板不得因此断开连接
ERR_SEND_BACKPRESSURE = "__send_backpressure__"

# TCP Client 连接超时(毫秒)：异步 connectToHost 对不可达地址默认要等 OS ~20s 才报
# errorOccurred，这里主动设上限，超时即 abort 并提示，避免界面长时间无反馈卡在「连接中」。
_TCP_CONNECT_TIMEOUT_MS = 10000
_MAX_PENDING_BYTES = 4 * 1024 * 1024
_BRIDGE_MAX_PENDING_BYTES = _MAX_PENDING_BYTES
_UDP_MAX_PAYLOAD = 65507

_log = logging.getLogger(__name__)


def _safe(func, *args):
    """执行一步清理动作。失败只记日志不抛，保证同一段清理里后面的步骤不被跳过。"""
    return safe_step(func, *args, log=_log, kind="net_io cleanup step")


def _pending_overflow(sock, data, limit=_MAX_PENDING_BYTES):
    """True if writing data would push Qt's bytesToWrite() past the cap."""
    try:
        pending = int(sock.bytesToWrite())
    except (RuntimeError, TypeError, ValueError, AttributeError):
        return False
    return pending + len(data) > limit


def local_ipv4_list():
    """枚举本机 IPv4 地址，供「本地IP」下拉用。首项 0.0.0.0 = 监听所有网卡。"""
    ips = ["0.0.0.0"]
    try:
        for addr in QNetworkInterface.allAddresses():
            if addr.protocol() == QAbstractSocket.IPv4Protocol:
                s = addr.toString()
                if s and s not in ips:
                    ips.append(s)
    except (RuntimeError, TypeError, ValueError, OSError):
        _log.debug("枚举本机 IPv4 地址失败，回退到默认地址表", exc_info=True)
    if "127.0.0.1" not in ips:
        ips.append("127.0.0.1")
    return ips


def _any_or(ip):
    """空 / 0.0.0.0 → 监听所有网卡；否则解析为指定地址。"""
    if not ip or ip == "0.0.0.0":
        return QHostAddress(QHostAddress.AnyIPv4)
    return QHostAddress(ip)


def route_local_ipv4(remote_ip, remote_port):
    """Resolve the concrete source IPv4 selected by the OS route table.

    UDP connect does not send a datagram; it only selects a route/source.
    """
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    try:
        sock.connect((str(remote_ip), int(remote_port)))
        ip = str(sock.getsockname()[0] or "")
        return ip if ip and ip != "0.0.0.0" else None
    except (OSError, TypeError, ValueError):
        return None
    finally:
        sock.close()


# Back-compat alias for older call sites / tests.
_route_local_ipv4 = route_local_ipv4


def resolve_export_local_ipv4(configured, remote_ip=None, remote_port=None):
    """Pick a concrete host IPv4 for PCAP (never 0.0.0.0 / ::).

    Order: non-wildcard configured → route toward remote/group → first
    non-loopback local address → 127.0.0.1. Returns None if nothing usable.
    """
    text = str(configured or "").strip()
    if text and text not in ("0.0.0.0", "::", "::0"):
        return text
    if remote_ip and remote_port not in (None, ""):
        routed = route_local_ipv4(remote_ip, remote_port)
        if routed:
            return routed
    fallback = None
    for ip in local_ipv4_list():
        if ip in ("0.0.0.0", "::", "::0"):
            continue
        if ip == "127.0.0.1":
            fallback = fallback or ip
            continue
        return ip
    return fallback


def is_multicast_ipv4(ip):
    """组播地址须在 224.0.0.0 ~ 239.255.255.255（D 类）。"""
    try:
        parts = [int(x) for x in str(ip).split(".")]
    except (ValueError, AttributeError):
        return False
    return (len(parts) == 4 and 224 <= parts[0] <= 239
            and all(0 <= p <= 255 for p in parts))


def is_valid_ip(ip):
    """ip 是否为合法 IP 字面量（QHostAddress 能解析）。空 / None / 主机名 → False。"""
    return bool(ip) and not QHostAddress(str(ip).strip()).isNull()


def is_local_ipv4(ip):
    """是否可作为本地绑定地址；0.0.0.0 表示所有网卡。"""
    value = str(ip or "").strip()
    return value == "0.0.0.0" or value in local_ipv4_list()


def _find_interface(ip):
    """按 IP 找对应网卡 QNetworkInterface（指定组播网卡用）；空/0.0.0.0 → None=默认路由。"""
    if not ip or ip == "0.0.0.0":
        return None
    try:
        for nif in QNetworkInterface.allInterfaces():
            for entry in nif.addressEntries():
                if entry.ip().toString() == ip:
                    return nif
    except (RuntimeError, TypeError, ValueError, OSError):
        _log.debug("按 IP %s 查找网卡失败，回退到默认路由", ip, exc_info=True)
    return None


class NetConn(QObject):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    state_changed = pyqtSignal(bool)
    clients_changed = pyqtSignal(list)
    peer_changed = pyqtSignal(str, int)   # UDP 收到新对端(ip, port)，供界面显示「当前对端」

    def open(self):
        raise NotImplementedError

    def close(self):
        pass

    def send(self, data, target=None):
        return 0

    @property
    def is_open(self):
        return False

    @property
    def bridge_ready(self):
        """双向桥接是否已有可发送目标；普通连接状态与发送目标状态分开。"""
        return self.is_open


# ============== TCP Server ==============
class TcpServerConn(NetConn):
    data_received_from = pyqtSignal(bytes, str)

    def __init__(self, local_ip, port, parent=None):
        super().__init__(parent)
        self._ip = local_ip
        self._port = port
        self._server = None
        self._clients = []   # [QTcpSocket]
        self._last_send_client_keys = []

    def open(self):
        # 防御性守卫：重复 open() 先关闭旧的，避免泄漏 QTcpServer 和重复连接信号
        if self._server:
            self.close()
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_new)
        if not self._server.listen(_any_or(self._ip), self._port):
            self.error_occurred.emit(self._server.errorString())
            srv = self._server
            self._server = None
            _safe(srv.close)
            _safe(srv.deleteLater)
            return False
        self.state_changed.emit(True)
        return True

    def _on_new(self):
        while self._server and self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._clients.append(sock)
            sock.readyRead.connect(lambda s=sock: self._on_read(s))
            sock.disconnected.connect(lambda s=sock: self._on_disc(s))
            # socket 出错(RST/超时等)兜底清理：多数情况 Qt 随后也会发 disconnected，
            # 这里防"只发 error 不发 disconnected"的罕见路径残留死 socket
            if hasattr(sock, "errorOccurred"):
                sock.errorOccurred.connect(lambda _e, s=sock: self._on_disc(s))
        self._emit_clients()

    def _on_read(self, sock):
        if sock not in self._clients:   # 已断开但 deleteLater 未完成时的残留 readyRead，忽略
            return
        data = bytes(sock.readAll())
        if data:
            self.data_received.emit(data)  # 保留连接层原有公共信号，兼容其他订阅者
            self.data_received_from.emit(data, self._key(sock))

    def _on_disc(self, sock):
        if sock in self._clients:
            self._clients.remove(sock)
        sock.deleteLater()
        self._emit_clients()

    @staticmethod
    def _key(sock):
        return f"{sock.peerAddress().toString()}:{sock.peerPort()}"

    def _emit_clients(self):
        self.clients_changed.emit([(self._key(s), self._key(s)) for s in self._clients])

    def _drop_client(self, sock):
        """摘掉半帧污染/出错的客户端。先移出客户端表再释放：
        这样 abort() 失败也不会把它留在表里继续接收后续写入。"""
        if sock in self._clients:
            self._clients.remove(sock)
        _safe(sock.abort)
        _safe(sock.deleteLater)

    def _note_send_backpressure(self):
        """Drop this write; keep the socket. error_occurred is edge-triggered."""
        _log.warning("TCP send dropped: write buffer exceeds %s bytes",
                     _MAX_PENDING_BYTES)
        if not getattr(self, "_bp_emitted", False):
            self._bp_emitted = True
            self.error_occurred.emit(ERR_SEND_BACKPRESSURE)

    def send(self, data, target=None):
        self._last_send_client_keys = []
        if not self._clients:
            return SEND_NO_TARGET
        if target in (None, "", "__all__"):
            # Snapshot: _on_disc may remove clients while we iterate.
            targets = list(self._clients)
        else:
            targets = [s for s in self._clients if self._key(s) == target]
            if not targets:
                return SEND_NO_TARGET
        # 广播尽力而为：任一客户端整帧写成功即算成功。只有「半帧」(0<n<len) 会错位污染
        # 该客户端的字节流 → abort 剔除；纯写失败(-1，对端 RST/缓冲满)交 Qt 的 disconnected
        # 信号清理，不因某个掉线客户端把其它已收到完整帧的客户端也判成发送失败。
        any_ok = False
        poisoned = []
        overflow = False
        for s in targets:
            if _pending_overflow(s, data):
                overflow = True
                continue
            n = s.write(data)
            if n == len(data):
                any_ok = True
                self._last_send_client_keys.append(self._key(s))
            elif 0 < n < len(data):
                poisoned.append(s)  # 半帧已进入该客户端流，不能继续复用
        for s in poisoned:
            self._drop_client(s)
        if poisoned:
            self._emit_clients()
        if overflow:
            self._note_send_backpressure()
        elif getattr(self, "_bp_emitted", False):
            self._bp_emitted = False
        return len(data) if any_ok else 0

    def send_bridge(self, data, target=None):
        """桥接发送。target=None 广播给所有客户端，否则只发给指定客户端。

        网关模式必须定向：把某个客户端的 Modbus 响应广播给其他客户端会串数据。
        """
        if target in (None, "", "__all__"):
            targets = list(self._clients)
        else:
            targets = [s for s in self._clients if self._key(s) == target]
        if not targets:
            return SEND_NO_TARGET
        all_ok = True
        poisoned = []
        for sock in targets:
            if _pending_overflow(sock, data):
                all_ok = False
                continue
            n = sock.write(data)
            if n != len(data):
                all_ok = False
                if 0 < n < len(data):
                    poisoned.append(sock)
        for sock in poisoned:
            self._drop_client(sock)
        if poisoned:
            self._emit_clients()
        return len(data) if all_ok else 0

    def close(self):
        for s in list(self._clients):
            _safe(s.close)
            _safe(s.deleteLater)
        self._clients = []
        self._last_send_client_keys = []
        was_open = bool(self._server)
        if self._server:
            srv = self._server
            self._server = None
            _safe(srv.close)
            _safe(srv.deleteLater)
        if was_open:
            self.state_changed.emit(False)

    def client_keys(self):
        """Connected client keys ('ip:port'), same format as send() target."""
        return [self._key(s) for s in list(self._clients)]

    def last_send_client_keys(self):
        """Client keys that accepted the full payload in the latest send()."""
        return list(self._last_send_client_keys)

    @property
    def is_open(self):
        return self._server is not None and self._server.isListening()

    @property
    def bridge_ready(self):
        return self.is_open and bool(self._clients)

    @property
    def bound_port(self):
        # Actual listen port (useful when open() used port 0).
        if self._server is None:
            return 0
        try:
            return int(self._server.serverPort())
        except (RuntimeError, TypeError, ValueError):
            return 0


# ============== TCP Client ==============
class TcpClientConn(NetConn):
    def __init__(self, remote_ip, port, parent=None):
        super().__init__(parent)
        self._ip = remote_ip
        self._port = port
        self._sock = None
        self._connected = False
        self._conn_timer = QTimer(self)
        self._conn_timer.setSingleShot(True)
        self._conn_timer.timeout.connect(self._on_conn_timeout)

    def open(self):
        # 防御性守卫：重复 open() 先关闭旧的，避免泄漏 socket 和重复连接信号
        if self._sock:
            self.close()
        self._sock = QTcpSocket(self)
        self._sock.readyRead.connect(self._on_read)
        self._sock.connected.connect(self._on_connected)
        self._sock.disconnected.connect(self._on_disc)
        if hasattr(self._sock, "errorOccurred"):
            self._sock.errorOccurred.connect(lambda _e: self._on_error())
        self._sock.connectToHost(QHostAddress(self._ip), self._port)
        self._conn_timer.start(_TCP_CONNECT_TIMEOUT_MS)   # 超时保护：不可达地址不再干等 ~20s
        return True   # 异步连接，结果由 connected / error 信号通知

    def _on_connected(self):
        self._conn_timer.stop()
        self._connected = True
        self.state_changed.emit(True)

    def _on_read(self):
        data = bytes(self._sock.readAll())
        if data:
            self.data_received.emit(data)

    def _on_disc(self):
        was = self._connected
        self._connected = False
        if was:
            self.state_changed.emit(False)   # 连接后被对端断开

    def _on_error(self):
        self._conn_timer.stop()
        if not self._connected and self._sock:
            self.error_occurred.emit(self._sock.errorString())

    def _on_conn_timeout(self):
        # 连接超时(对端不可达/被防火墙丢包)：abort 底层连接并报错，让主窗口走
        # _on_conn_error →「连接失败」提示并断开，不再干等 OS 默认 ~20s。
        # 注意此处不 emit state_changed(False)，否则会被主窗口误读成「对端已断开」。
        if self._connected or not self._sock:
            return
        sock = self._sock
        self._sock = None
        _safe(sock.abort)
        _safe(sock.deleteLater)
        self.error_occurred.emit(ERR_CONN_TIMEOUT)

    def send(self, data, target=None):
        if self._sock and self._sock.state() == QAbstractSocket.ConnectedState:
            if _pending_overflow(self._sock, data):
                self._note_send_backpressure()
                return 0
            if getattr(self, "_bp_emitted", False):
                self._bp_emitted = False
            n = self._sock.write(data)
            return n if n > 0 else 0
        return 0

    def _note_send_backpressure(self):
        _log.warning("TCP send dropped: write buffer exceeds %s bytes",
                     _MAX_PENDING_BYTES)
        if not getattr(self, "_bp_emitted", False):
            self._bp_emitted = True
            self.error_occurred.emit(ERR_SEND_BACKPRESSURE)

    def send_bridge(self, data, target=None):
        if not self.bridge_ready:
            return SEND_NO_TARGET
        if _pending_overflow(self._sock, data):
            return 0
        return self.send(data)

    def close(self):
        # 先置 _connected=False + 解绑 _sock，再 abort()：abort 可能触发 errorOccurred，
        # 此时 _on_error 的 `self._sock` 已为 None，杜绝虚假错误通知（不再仅依赖外层 blockSignals）
        self._conn_timer.stop()
        was_connected = self._connected
        self._connected = False
        sock = self._sock
        self._sock = None
        if sock:
            _safe(sock.abort)
            _safe(sock.deleteLater)
        if was_connected:
            # 还在 connecting 就被关掉时，从未发过 state_changed(True)，再发一个
            # False 会被主窗口读成「对端已断开」——弹提示并触发自动重连。
            # 上面 _on_conn_timeout 避的是同一个坑。
            self.state_changed.emit(False)

    @property
    def is_open(self):
        return self._sock is not None and self._sock.state() == QAbstractSocket.ConnectedState

    def local_endpoint(self):
        """Return (ip_str, port) for the local side of an established TCP client."""
        if not self._sock or not self._connected:
            return None
        try:
            ip = self._sock.localAddress().toString()
            port = int(self._sock.localPort())
            if ip.startswith("::ffff:"):
                ip = ip[7:]
            if not ip or port <= 0:
                return None
            return (ip, port)
        except (RuntimeError, TypeError, ValueError, AttributeError):
            return None


# ============== UDP ==============
class _UdpBase(NetConn):
    """Shared datagram read/close; bind and send stay on the subclasses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sock = None
        self._last_peer = None
        self._last_peer_key = None

    def _on_read(self):
        while self._sock and self._sock.hasPendingDatagrams():
            size = self._sock.pendingDatagramSize()
            data, host, port = self._sock.readDatagram(size)
            self._last_peer = (host, port)
            key = (host.toString(), port)
            if key != self._last_peer_key:   # 对端变化才通知界面，避免每包刷
                self._last_peer_key = key
                self.peer_changed.emit(host.toString(), port)
            if data:
                self.data_received.emit(bytes(data))

    def _release_udp_extras(self):
        pass

    def close(self):
        was_open = bool(self._sock)
        if self._sock:
            self._release_udp_extras()
            _safe(self._sock.close)
            _safe(self._sock.deleteLater)
            self._sock = None
        # 清理对端缓存：否则复用本对象重开后，首次「回复最近对端」会发给上一会话的旧地址
        self._last_peer = None
        self._last_peer_key = None
        if was_open:
            self.state_changed.emit(False)

    @property
    def is_open(self):
        return self._sock is not None


class UdpConn(_UdpBase):
    def __init__(self, local_ip, local_port, remote_ip, remote_port, parent=None):
        super().__init__(parent)
        self._local_ip = local_ip
        self._local_port = local_port
        self._remote_ip = remote_ip
        self._remote_port = remote_port

    def open(self):
        # 防御性守卫：重复 open() 先关闭旧的
        if self._sock:
            self.close()
        self._sock = QUdpSocket(self)
        if not self._sock.bind(_any_or(self._local_ip), self._local_port):
            self.error_occurred.emit(self._sock.errorString())
            sock = self._sock
            self._sock = None
            _safe(sock.close)
            _safe(sock.deleteLater)
            return False
        self._sock.readyRead.connect(self._on_read)
        self.state_changed.emit(True)
        return True

    def send(self, data, target=None):
        if not self._sock:
            return 0
        if self._remote_ip and self._remote_port:
            n = self._sock.writeDatagram(data, QHostAddress(self._remote_ip), self._remote_port)
        elif self._last_peer:
            n = self._sock.writeDatagram(data, self._last_peer[0], self._last_peer[1])
        else:
            return SEND_NO_TARGET   # 没填远程地址，也还没收到过任何对端
        return n if n != -1 else 0   # writeDatagram 失败(网络不可达等)返回 -1

    def send_bridge(self, data, target=None):
        """超大流块拆成合法 UDP 数据报；返回成功写入的总字节数。"""
        if not self.bridge_ready:
            return SEND_NO_TARGET
        total = 0
        for offset in range(0, len(data), _UDP_MAX_PAYLOAD):
            chunk = data[offset:offset + _UDP_MAX_PAYLOAD]
            n = self.send(chunk)
            if n != len(chunk):
                return total if total else n
            total += n
        return total

    @property
    def bound_port(self):
        # OS-assigned local port after bind (port 0 friendly).
        if self._sock is None:
            return 0
        try:
            return int(self._sock.localPort())
        except (RuntimeError, TypeError, ValueError):
            return 0

    @property
    def bridge_ready(self):
        return self.is_open and bool(
            (self._remote_ip and self._remote_port) or self._last_peer)

    def peer_endpoint(self):
        """Return the source endpoint of the most recently emitted datagram."""
        if not self._last_peer:
            return None
        try:
            ip = self._last_peer[0].toString()
            if ip.startswith("::ffff:"):
                ip = ip[7:]
            port = int(self._last_peer[1])
            return (ip, port) if ip and port > 0 else None
        except (RuntimeError, TypeError, ValueError, AttributeError, IndexError):
            return None

    def local_endpoint(self):
        """Return (ip_str, port) for the bound UDP socket when available."""
        if self._sock is None:
            return None
        try:
            ip = self._sock.localAddress().toString()
            if ip.startswith("::ffff:"):
                ip = ip[7:]
            port = int(self._sock.localPort())
            if not ip or ip in ("0.0.0.0", "::"):
                configured = str(self._local_ip or "").strip()
                if configured and configured not in ("0.0.0.0", "::"):
                    ip = configured
                elif self._remote_ip and self._remote_port:
                    ip = route_local_ipv4(self._remote_ip, self._remote_port)
                else:
                    ip = None
            if not ip or port <= 0:
                return None
            return (ip, port)
        except (RuntimeError, TypeError, ValueError, AttributeError, OSError):
            return None


# ============== UDP 组播 (multicast) ==============
class UdpGroupConn(_UdpBase):
    """加入组播组收发：bind 端口(ShareAddress) → joinMulticastGroup(组地址)。
    发送直接发往组地址:端口。iface_ip 指定出网卡(空=默认路由)。"""

    def __init__(self, iface_ip, group_ip, port, parent=None):
        super().__init__(parent)
        self._iface_ip = iface_ip
        self._group = group_ip
        self._port = port

    def open(self):
        # 防御性守卫：重复 open() 先关闭旧的
        if self._sock:
            self.close()
        self._sock = QUdpSocket(self)
        # 绑到 AnyIPv4 + ShareAddress/ReuseAddressHint：允许多个监听者共用端口，组播才收得到
        if not self._sock.bind(QHostAddress(QHostAddress.AnyIPv4), self._port,
                               QUdpSocket.ShareAddress | QUdpSocket.ReuseAddressHint):
            self.error_occurred.emit(self._sock.errorString())
            sock = self._sock
            self._sock = None
            _safe(sock.close)
            _safe(sock.deleteLater)
            return False
        grp = QHostAddress(self._group)
        iface = _find_interface(self._iface_ip)
        if iface is not None:
            joined = self._sock.joinMulticastGroup(grp, iface)
            self._sock.setMulticastInterface(iface)
        else:
            joined = self._sock.joinMulticastGroup(grp)
        if not joined:
            self.error_occurred.emit(self._sock.errorString())
            sock = self._sock
            self._sock = None
            _safe(sock.close)
            _safe(sock.deleteLater)
            return False
        # 组播 TTL：默认 1 仅限本子网，设大些以便跨网段/经路由器转发（按需可调）
        self._sock.setSocketOption(QAbstractSocket.MulticastTtlOption, 16)
        self._sock.readyRead.connect(self._on_read)
        self.state_changed.emit(True)
        return True

    def _release_udp_extras(self):
        # 三步各自兜底：退组失败以前会连带跳过 close/deleteLater，socket 泄漏且没退组
        _safe(self._sock.leaveMulticastGroup, QHostAddress(self._group))

    def peer_endpoint(self):
        """Return the source endpoint of the most recently emitted datagram."""
        if not self._last_peer:
            return None
        try:
            ip = self._last_peer[0].toString()
            port = int(self._last_peer[1])
        except (TypeError, ValueError, AttributeError):
            return None
        return (ip, port)

    def send(self, data, target=None):
        if not self._sock:
            return 0
        n = self._sock.writeDatagram(data, QHostAddress(self._group), self._port)
        return n if n != -1 else 0
