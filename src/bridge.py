# -*- coding: utf-8 -*-
"""串口↔网络双向透传引擎。

BridgeEngine — 纯信号驱动，无独立线程，不依赖 Qt Widget。
持有两个连接对象（Side A / Side B），连接双方的 data_received
信号实现双向转发，监听 state_changed / error_occurred 自动停止。
"""
import time
from collections import deque

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


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

    # ── 公开 API ─────────────────────────────────────────────

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
        ca.data_received.connect(self._on_data_a)
        cb.data_received.connect(self._on_data_b)
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

    # ── 转发槽 ────────────────────────────────────────────────

    def _on_data_a(self, data: bytes):
        self._a_rx += len(data)
        if self._active and self._conn_b:
            try:
                payload = bytes(data)
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

    def _on_data_b(self, data: bytes):
        self._b_rx += len(data)
        if self._active and self._conn_a:
            try:
                payload = bytes(data)
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
    def _send_bridge(conn, data: bytes) -> int:
        """桥接可使用连接层更严格的发送语义，不改变主窗口普通 send 行为。"""
        sender = getattr(conn, "send_bridge", None)
        return sender(data) if sender is not None else conn.send(data)

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
        """每秒触发：清理过期条目，计算实时速率，发射 stats_updated。"""
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
