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
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtNetwork import (
    QTcpServer, QTcpSocket, QUdpSocket, QHostAddress, QAbstractSocket,
    QNetworkInterface,
)

PROTO_TCP_SERVER = "TCP Server"
PROTO_TCP_CLIENT = "TCP Client"
PROTO_UDP = "UDP"
PROTO_UDP_MULTICAST = "UDP Multicast"
PROTOCOLS = [PROTO_UDP, PROTO_UDP_MULTICAST, PROTO_TCP_SERVER, PROTO_TCP_CLIENT]

SEND_NO_TARGET = -1   # send() 软错误：没有可发送的目标（UDP 无对端 / TCP Server 无客户端）

# TCP Client 连接超时的错误哨兵：emit 它而非硬编码中文，由主窗口按 i18n 翻译成当前语言
ERR_CONN_TIMEOUT = "__conn_timeout__"

# TCP Client 连接超时(毫秒)：异步 connectToHost 对不可达地址默认要等 OS ~20s 才报
# errorOccurred，这里主动设上限，超时即 abort 并提示，避免界面长时间无反馈卡在「连接中」。
_TCP_CONNECT_TIMEOUT_MS = 10000


def local_ipv4_list():
    """枚举本机 IPv4 地址，供「本地IP」下拉用。首项 0.0.0.0 = 监听所有网卡。"""
    ips = ["0.0.0.0"]
    try:
        for addr in QNetworkInterface.allAddresses():
            if addr.protocol() == QAbstractSocket.IPv4Protocol:
                s = addr.toString()
                if s and s not in ips:
                    ips.append(s)
    except Exception:
        pass
    if "127.0.0.1" not in ips:
        ips.append("127.0.0.1")
    return ips


def _any_or(ip):
    """空 / 0.0.0.0 → 监听所有网卡；否则解析为指定地址。"""
    if not ip or ip == "0.0.0.0":
        return QHostAddress(QHostAddress.AnyIPv4)
    return QHostAddress(ip)


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


def _find_interface(ip):
    """按 IP 找对应网卡 QNetworkInterface（指定组播网卡用）；空/0.0.0.0 → None=默认路由。"""
    if not ip or ip == "0.0.0.0":
        return None
    try:
        for nif in QNetworkInterface.allInterfaces():
            for entry in nif.addressEntries():
                if entry.ip().toString() == ip:
                    return nif
    except Exception:
        pass
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


# ============== TCP Server ==============
class TcpServerConn(NetConn):
    data_received_from = pyqtSignal(bytes, str)

    def __init__(self, local_ip, port, parent=None):
        super().__init__(parent)
        self._ip = local_ip
        self._port = port
        self._server = None
        self._clients = []   # [QTcpSocket]

    def open(self):
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_new)
        if not self._server.listen(_any_or(self._ip), self._port):
            self.error_occurred.emit(self._server.errorString())
            self._server = None
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

    def send(self, data, target=None):
        if not self._clients:
            return SEND_NO_TARGET
        if target in (None, "", "__all__"):
            targets = self._clients
        else:
            targets = [s for s in self._clients if self._key(s) == target]
            if not targets:
                return SEND_NO_TARGET
        ok = False
        for s in targets:
            if s.write(data) != -1:   # QTcpSocket.write 失败返回 -1
                ok = True
        return len(data) if ok else 0   # 全部客户端写入失败 → 0（调用方按发送失败处理）

    def close(self):
        for s in list(self._clients):
            try:
                s.close()
                s.deleteLater()
            except Exception:
                pass
        self._clients = []
        if self._server:
            self._server.close()
            self._server = None
        self.state_changed.emit(False)

    @property
    def is_open(self):
        return self._server is not None and self._server.isListening()


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
        try:
            sock.abort()
            sock.deleteLater()
        except Exception:
            pass
        self.error_occurred.emit(ERR_CONN_TIMEOUT)

    def send(self, data, target=None):
        if self._sock and self._sock.state() == QAbstractSocket.ConnectedState:
            return len(data) if self._sock.write(data) != -1 else 0
        return 0

    def close(self):
        # 先置 _connected=False + 解绑 _sock，再 abort()：abort 可能触发 errorOccurred，
        # 此时 _on_error 的 `self._sock` 已为 None，杜绝虚假错误通知（不再仅依赖外层 blockSignals）
        self._conn_timer.stop()
        self._connected = False
        sock = self._sock
        self._sock = None
        if sock:
            try:
                sock.abort()
                sock.deleteLater()
            except Exception:
                pass
        self.state_changed.emit(False)

    @property
    def is_open(self):
        return self._sock is not None and self._sock.state() == QAbstractSocket.ConnectedState


# ============== UDP ==============
class UdpConn(NetConn):
    def __init__(self, local_ip, local_port, remote_ip, remote_port, parent=None):
        super().__init__(parent)
        self._local_ip = local_ip
        self._local_port = local_port
        self._remote_ip = remote_ip
        self._remote_port = remote_port
        self._sock = None
        self._last_peer = None       # (QHostAddress, port) 最近发来数据的对端(send 回复用)
        self._last_peer_key = None   # (ip_str, port) 仅用于「对端是否变化」判断

    def open(self):
        self._sock = QUdpSocket(self)
        if not self._sock.bind(_any_or(self._local_ip), self._local_port):
            self.error_occurred.emit(self._sock.errorString())
            self._sock.close()
            self._sock = None
            return False
        self._sock.readyRead.connect(self._on_read)
        self.state_changed.emit(True)
        return True

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

    def close(self):
        if self._sock:
            try:
                self._sock.close()
                self._sock.deleteLater()
            except Exception:
                pass
            self._sock = None
        # 清理对端缓存：否则复用本对象重开后，首次「回复最近对端」会发给上一会话的旧地址
        self._last_peer = None
        self._last_peer_key = None
        self.state_changed.emit(False)

    @property
    def is_open(self):
        return self._sock is not None


# ============== UDP 组播 (multicast) ==============
class UdpGroupConn(NetConn):
    """加入组播组收发：bind 端口(ShareAddress) → joinMulticastGroup(组地址)。
    发送直接发往组地址:端口。iface_ip 指定出网卡(空=默认路由)。"""

    def __init__(self, iface_ip, group_ip, port, parent=None):
        super().__init__(parent)
        self._iface_ip = iface_ip
        self._group = group_ip
        self._port = port
        self._sock = None

    def open(self):
        self._sock = QUdpSocket(self)
        # 绑到 AnyIPv4 + ShareAddress/ReuseAddressHint：允许多个监听者共用端口，组播才收得到
        if not self._sock.bind(QHostAddress(QHostAddress.AnyIPv4), self._port,
                               QUdpSocket.ShareAddress | QUdpSocket.ReuseAddressHint):
            self.error_occurred.emit(self._sock.errorString())
            self._sock.close()
            self._sock = None
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
            self._sock.close()
            self._sock = None
            return False
        # 组播 TTL：默认 1 仅限本子网，设大些以便跨网段/经路由器转发（按需可调）
        self._sock.setSocketOption(QAbstractSocket.MulticastTtlOption, 16)
        self._sock.readyRead.connect(self._on_read)
        self.state_changed.emit(True)
        return True

    def _on_read(self):
        while self._sock and self._sock.hasPendingDatagrams():
            size = self._sock.pendingDatagramSize()
            data, host, port = self._sock.readDatagram(size)
            if data:
                self.data_received.emit(bytes(data))

    def send(self, data, target=None):
        if not self._sock:
            return 0
        n = self._sock.writeDatagram(data, QHostAddress(self._group), self._port)
        return n if n != -1 else 0

    def close(self):
        if self._sock:
            try:
                self._sock.leaveMulticastGroup(QHostAddress(self._group))
                self._sock.close()
                self._sock.deleteLater()
            except Exception:
                pass
            self._sock = None
        self.state_changed.emit(False)

    @property
    def is_open(self):
        return self._sock is not None
