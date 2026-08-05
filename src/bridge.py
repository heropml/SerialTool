# -*- coding: utf-8 -*-
"""串口↔网络双向透传引擎。

BridgeEngine — 纯信号驱动，无独立线程，不依赖 Qt Widget。
持有两个连接对象（Side A / Side B），连接双方的 data_received
信号实现双向转发，监听 state_changed / error_occurred 自动停止。
"""
import time
from collections import deque

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

try:
    from modbus_gateway import ModbusGatewayEngine
except ImportError:  # pragma: no cover
    ModbusGatewayEngine = None


class BridgeEngine(QObject):
    """双向透传引擎。

    生命周期：
    1. 由 BridgeDialog 创建
    2. dialog 调 set_connection(0, conn_a) / set_connection(1, conn_b)
    3. start() → 连接信号 → 双向转发
    4. stop(reason) 或任一侧断开 → 停止转发、断开信号（不关连接）
    """

    started = pyqtSignal()
    stopped = pyqtSignal(str)  # reason
    # Python int 避免长时间桥接累计超过 Qt 32-bit int（约 2 GiB）后溢出。
    stats_updated = pyqtSignal(object, object, object, object, object, object)
    # a_rx, a_tx, b_rx, b_tx, a_rate, b_rate
    side_state = pyqtSignal(int, bool)  # side(0=A, 1=B), opened
    error_occurred = pyqtSignal(int, str)  # side, msg
    forwarded = pyqtSignal(int, bytes)  # direction: 0=A→B, 1=B→A；仅发送成功后触发

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn_a = None
        self._conn_b = None
        self._active = False
        self._gateway = None  # optional ModbusGatewayEngine (A=TCP, B=RTU)

        # 字节计数器
        self._a_rx = 0
        self._a_tx = 0
        self._b_rx = 0
        self._b_tx = 0

        # 转发发送是否正常：边沿触发失败上报（正常→失败时报一次，防每字节刷屏）
        self._send_ok_a = True
        self._send_ok_b = True

        # 速率统计（1 秒滑动窗口）
        self._a_hist = deque()  # [(timestamp, bytes), ...]
        self._b_hist = deque()
        self._rate_timer = QTimer(self)
        self._rate_timer.timeout.connect(self._tick_rate)
        self._rate_timer.setInterval(1000)
        # The rate tick is too coarse to expire gateway requests on time.
        self._gw_timer = QTimer(self)
        self._gw_timer.timeout.connect(self._tick_gateway)
        self._gw_timer.setInterval(100)

    # ── 公开 API ─────────────────────────────────────────────

    def set_modbus_gateway(self, enabled, unit_map=None, timeout_s=1.0):
        """When enabled, A->B is MBAP->RTU and B->A is RTU->MBAP."""
        if not enabled or ModbusGatewayEngine is None:
            self._gateway = None
            self._gw_timer.stop()
            return
        self._gateway = ModbusGatewayEngine(unit_map=unit_map, timeout_s=timeout_s)
        if self._active:
            self._gw_timer.start()

    def set_connection(self, side: int, conn) -> None:
        """设置一侧的连接对象。

        Args:
            side: 0=Side A, 1=Side B
            conn: SerialConn 或 NetConn 子类实例（已 open）
        """
        if side == 0:
            self._conn_a = conn
        else:
            self._conn_b = conn

    def start(self) -> bool:
        """启动桥接。双方必须已通过 set_connection 设置且 is_open。"""
        if self._active:
            return False
        if not (self._conn_a and self._conn_b
                and self._conn_a.is_open and self._conn_b.is_open):
            return False
        if not all(getattr(c, "bridge_ready", True)
                   for c in (self._conn_a, self._conn_b)):
            return False
        self._reset_stats()
        if self._gateway is not None:
            self._gateway.reset()
            self._gw_timer.start()
        self._connect_signals()
        self._active = True
        self._rate_timer.start()
        self._emit_stats(0, 0)
        self.started.emit()
        return True

    def stop(self, reason: str = "") -> None:
        """停止桥接。断开信号连线，不关闭连接（由调用方决定是否关闭）。"""
        if not self._active:
            return
        self._active = False
        self._emit_stats(0, 0)  # 保留累计量，但停止态实时速率必须归零
        self._rate_timer.stop()
        self._gw_timer.stop()
        self._disconnect_signals()
        self.stopped.emit(reason)

    def is_active(self) -> bool:
        return self._active

    def reset_counters(self) -> None:
        self._a_rx = self._a_tx = self._b_rx = self._b_tx = 0
        self._a_hist.clear()
        self._b_hist.clear()
        self._emit_stats(0, 0)

    # ── 信号连接 ─────────────────────────────────────────────

    def _connect_signals(self):
        ca, cb = self._conn_a, self._conn_b
        self._a_keyed = False
        ca.data_received.connect(self._on_data_a)
        cb.data_received.connect(self._on_data_b)
        # TCP Server 侧还带一个标了来源客户端的信号。网关模式下必须用它：多个客户端
        # 的分片混进同一个重组缓冲会被切成错帧，响应也会广播给不相干的客户端。
        sig_from = getattr(ca, "data_received_from", None)
        if sig_from is not None:
            sig_from.connect(self._on_data_a_from)
            self._a_keyed = True
        sig_clients = getattr(ca, "clients_changed", None)
        if sig_clients is not None:
            sig_clients.connect(self._on_clients_a)
        ca.state_changed.connect(self._on_state_a)
        cb.state_changed.connect(self._on_state_b)
        ca.error_occurred.connect(self._on_error_a)
        cb.error_occurred.connect(self._on_error_b)

    def _disconnect_signals(self):
        # 只断本引擎自己连的槽（用具体 slot），不用 disconnect() 一锅端——同一连接上还挂着
        # BridgeDialog 面板的 _on_conn_state/_on_conn_error 和日志槽，全断会误伤它们、连接仍存活。
        for c, on_data, on_state, on_err in (
            (self._conn_a, self._on_data_a, self._on_state_a, self._on_error_a),
            (self._conn_b, self._on_data_b, self._on_state_b, self._on_error_b),
        ):
            if c is None:
                continue
            for sig, slot in ((c.data_received, on_data),
                              (c.state_changed, on_state),
                              (c.error_occurred, on_err)):
                try:
                    sig.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        for name, slot in (("data_received_from", self._on_data_a_from),
                           ("clients_changed", self._on_clients_a)):
            sig = getattr(self._conn_a, name, None)
            if sig is None:
                continue
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._a_keyed = False

    # ── 转发槽 ────────────────────────────────────────────────

    def _gw_send(self, direction, frames):
        """Forward gateway output. direction: 0 = to side B, 1 = to side A.

        Mirrors the plain-forward bookkeeping (tx counter, rate sample,
        forwarded signal) and keeps the one-shot error latch per side so a
        broken link does not emit one error per frame.
        """
        to_a = (direction == 1)
        conn = self._conn_a if to_a else self._conn_b
        if not frames or conn is None:
            return
        ok_attr = "_send_ok_a" if to_a else "_send_ok_b"
        err_side = 0 if to_a else 1
        try:
            for item in frames:
                # TCP 回包是 TcpReply(client, frame)，RTU 侧仍是裸 bytes
                target = getattr(item, "client", None)
                fr = getattr(item, "frame", item)
                sent = self._send_bridge(conn, fr, target)
                if sent != len(fr):
                    raise IOError("sent %s of %s bytes" % (sent, len(fr)))
                if to_a:
                    self._a_tx += len(fr)
                else:
                    self._b_tx += len(fr)
                self._record_rate(direction, len(fr))
                self.forwarded.emit(direction, fr)
            setattr(self, ok_attr, True)
        except Exception as e:
            if getattr(self, ok_attr):
                setattr(self, ok_attr, False)
                self.error_occurred.emit(err_side, "send failed: %s" % e)

    def _gw_dispatch(self, out):
        rtu_out, tcp_out = out
        self._gw_send(0, rtu_out)
        self._gw_send(1, tcp_out)

    def _tick_gateway(self):
        if not self._active or self._gateway is None:
            return
        try:
            self._gw_dispatch(self._gateway.tick())
        except Exception:
            pass

    def _on_data_a(self, data: bytes):
        self._a_rx += len(data)
        if self._gateway is not None and getattr(self, "_a_keyed", False):
            return        # 同一批字节由 _on_data_a_from 按客户端喂给网关，避免喂两遍
        if self._active and self._conn_b:
            try:
                payload = bytes(data)
                if self._gateway is not None:
                    self._gw_dispatch(self._gateway.feed_tcp(payload))
                    return
                sent = self._send_bridge(self._conn_b, payload)
                if sent != len(data):
                    raise IOError("sent %s of %s bytes" % (sent, len(data)))
                self._b_tx += len(data)
                self._record_rate(0, len(data))
                self._send_ok_b = True
                self.forwarded.emit(0, payload)
            except Exception as e:
                # 别静默丢数据：正常→失败时上报一次（进日志），持续失败静默直到恢复，防每字节刷屏
                if self._send_ok_b:
                    self._send_ok_b = False
                    self.error_occurred.emit(1, "send failed: %s" % e)

    def _on_data_a_from(self, data: bytes, key: str):
        """TCP Server 侧带来源的收包：网关按客户端隔离重组，回包定向送回。"""
        if not self._active or self._gateway is None or self._conn_b is None:
            return
        try:
            self._gw_dispatch(self._gateway.feed_tcp(bytes(data), client=key))
        except Exception as e:
            if self._send_ok_b:
                self._send_ok_b = False
                self.error_occurred.emit(1, "gateway failed: %s" % e)

    def _on_clients_a(self, clients):
        """客户端断开后清掉网关里它的重组缓冲和排队请求。

        不清的话 key 会一直堆积，且它那条在途请求的响应会落到广播路径上。
        """
        if self._gateway is None:
            return
        alive = {k for k, _label in clients}
        for key in self._gateway.clients:
            if key is not None and key not in alive:
                self._gateway.forget_client(key)

    def _on_data_b(self, data: bytes):
        self._b_rx += len(data)
        if self._active and self._conn_a:
            try:
                payload = bytes(data)
                if self._gateway is not None:
                    self._gw_dispatch(self._gateway.feed_rtu(payload))
                    return
                sent = self._send_bridge(self._conn_a, payload)
                if sent != len(data):
                    raise IOError("sent %s of %s bytes" % (sent, len(data)))
                self._a_tx += len(data)
                self._record_rate(1, len(data))
                self._send_ok_a = True
                self.forwarded.emit(1, payload)
            except Exception as e:
                # 别静默丢数据：正常→失败时上报一次（进日志），持续失败静默直到恢复，防每字节刷屏
                if self._send_ok_a:
                    self._send_ok_a = False
                    self.error_occurred.emit(0, "send failed: %s" % e)

    @staticmethod
    def _send_bridge(conn, data: bytes, target=None) -> int:
        """桥接可使用连接层更严格的发送语义，不改变主窗口普通 send 行为。

        target 非空时定向发给该客户端（网关回包用）；为空时行为与原来完全一致。
        """
        sender = getattr(conn, "send_bridge", None)
        if sender is None:
            return conn.send(data) if target is None else conn.send(data, target)
        return sender(data) if target is None else sender(data, target)

    # ── 状态监听 ──────────────────────────────────────────────

    def _on_state_a(self, opened: bool):
        self.side_state.emit(0, opened)
        if not opened and self._active:
            self.stop("Side A disconnected")

    def _on_state_b(self, opened: bool):
        self.side_state.emit(1, opened)
        if not opened and self._active:
            self.stop("Side B disconnected")

    def _on_error_a(self, msg: str):
        self.error_occurred.emit(0, msg)
        if self._active:
            self.stop("Side A error: %s" % msg)

    def _on_error_b(self, msg: str):
        self.error_occurred.emit(1, msg)
        if self._active:
            self.stop("Side B error: %s" % msg)

    # ── 速率统计 ──────────────────────────────────────────────

    def _reset_stats(self):
        self._a_rx = self._a_tx = self._b_rx = self._b_tx = 0
        self._a_hist.clear()
        self._b_hist.clear()
        self._send_ok_a = self._send_ok_b = True

    def _record_rate(self, side: int, n: int):
        t = time.monotonic()
        (self._a_hist if side == 0 else self._b_hist).append((t, n))

    def _tick_rate(self):
        """滑动窗口重算双向速率（B/s）并上报 stats_updated。"""
        cutoff = time.monotonic() - 1.0
        for hist in (self._a_hist, self._b_hist):
            while hist and hist[0][0] < cutoff:
                hist.popleft()
        rate_a = sum(n for _, n in self._a_hist)
        rate_b = sum(n for _, n in self._b_hist)
        self._emit_stats(rate_a, rate_b)

    def _emit_stats(self, rate_a: int, rate_b: int):
        self.stats_updated.emit(
            self._a_rx, self._a_tx, self._b_rx, self._b_tx, rate_a, rate_b
        )
