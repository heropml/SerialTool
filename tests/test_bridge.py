# -*- coding: utf-8 -*-
"""BridgeEngine 单测：双向转发 / 计数 / 自动停 / 按具体 slot 断 / 发送失败上报 / 守卫。

桥接引擎是纯信号驱动、无独立线程，用假连接对象即可完整覆盖行为。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication  # noqa: E402
from PyQt5.QtCore import QObject, pyqtSignal  # noqa: E402

_APP = QApplication.instance() or QApplication([])

from bridge import BridgeEngine  # noqa: E402
from bridge_dialog import BridgeDialog, _BridgeSidePanel  # noqa: E402
from net_io import TcpServerConn, UdpConn, _UDP_MAX_PAYLOAD  # noqa: E402


class FakeConn(QObject):
    """假连接：带 data_received / state_changed / error_occurred 信号 + send + is_open。"""
    data_received = pyqtSignal(bytes)
    state_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, fail=False, send_result=None):
        super().__init__()
        self.is_open = True
        self.sent = []
        self.fail = fail
        self.send_result = send_result
        self.closed = False

    def send(self, data):
        if self.fail:
            raise IOError("write fail")
        self.sent.append(bytes(data))
        return len(data) if self.send_result is None else self.send_result

    def close(self):
        self.closed = True
        self.is_open = False


def _engine(a=None, b=None):
    eng = BridgeEngine()
    a = a or FakeConn()
    b = b or FakeConn()
    eng.set_connection(0, a)
    eng.set_connection(1, b)
    return eng, a, b


class BridgeEngineTests(unittest.TestCase):
    def test_bidirectional_forward_and_counts(self):
        """A→B / B→A 原样透传，收发字节计数正确。"""
        eng, a, b = _engine()
        stats = {}
        eng.stats_updated.connect(lambda *v: stats.update(
            dict(zip("a_rx a_tx b_rx b_tx a_rate b_rate".split(), v))))
        self.assertTrue(eng.start())
        a.data_received.emit(b"hello")
        self.assertEqual(b.sent, [b"hello"])           # A 收 → 转发到 B
        b.data_received.emit(b"world!!")
        self.assertEqual(a.sent, [b"world!!"])         # B 收 → 转发到 A
        eng._tick_rate()
        self.assertEqual((stats["a_rx"], stats["b_tx"], stats["b_rx"], stats["a_tx"]),
                         (5, 5, 7, 7))
        eng.stop()

    def test_auto_stop_on_side_disconnect(self):
        """任一侧 state_changed(False) → 自动停，stopped 带原因。"""
        eng, a, b = _engine()
        reasons = []
        eng.stopped.connect(lambda r: reasons.append(r))
        eng.start()
        a.state_changed.emit(False)
        self.assertFalse(eng.is_active())
        self.assertTrue(reasons and "A" in reasons[0])

    def test_no_forward_after_stop(self):
        """停止后信号已摘，迟到数据不再转发。"""
        eng, a, b = _engine()
        eng.start()
        eng.stop()
        a.data_received.emit(b"late")
        self.assertEqual(b.sent, [])

    def test_stop_preserves_other_slots(self):
        """核心设计：停桥只断引擎自己连的槽，面板 co-挂在同一信号上的槽必须存活。"""
        eng, a, b = _engine()
        panel = []
        a.data_received.connect(lambda d: panel.append(d))   # 模拟面板日志槽
        eng.start()
        eng.stop("t")
        a.data_received.emit(b"X")
        self.assertEqual(panel, [b"X"])

    def test_send_failure_reported_not_silent(self):
        """回归：发送失败不再静默——正常→失败时 error_occurred 报一次、持续失败不刷屏、恢复后再失败会再报。"""
        eng, a, b = _engine(b=FakeConn(fail=True))
        errs = []
        eng.error_occurred.connect(lambda side, msg: errs.append((side, msg)))
        eng.start()
        a.data_received.emit(b"z")
        a.data_received.emit(b"z")                  # 连续失败：边沿触发，只报一次
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0][0], 1)             # side=B（转发到 B 失败）
        self.assertIn("send failed", errs[0][1])
        b.fail = False
        a.data_received.emit(b"ok")                 # 成功 → 复位 _send_ok_b
        b.fail = True
        a.data_received.emit(b"z")                  # 再失败 → 再报一次
        self.assertEqual(len(errs), 2)
        eng.stop()

    def test_send_failure_does_not_crash_or_stop(self):
        """发送失败不崩溃、不停桥（真正掉线交给 state_changed 处理）。"""
        eng, a, b = _engine(b=FakeConn(fail=True))
        eng.start()
        a.data_received.emit(b"zzz")
        self.assertTrue(eng.is_active())
        eng.stop()

    def test_send_zero_return_reported_and_not_counted(self):
        """真实连接以返回 0/-1 表示失败：必须上报且不能虚增 TX。"""
        eng, a, b = _engine(b=FakeConn(send_result=0))
        errs = []
        stats = []
        eng.error_occurred.connect(lambda side, msg: errs.append((side, msg)))
        eng.stats_updated.connect(lambda *values: stats.append(values))
        eng.start()
        a.data_received.emit(b"lost")
        eng._tick_rate()
        self.assertEqual(errs[0][0], 1)
        self.assertEqual(stats[-1][3], 0)  # b_tx
        self.assertEqual(stats[-1][4], 0)  # a_rate：只统计成功转发
        eng.stop()

    def test_connection_error_stops_active_bridge(self):
        """底层致命错误必须停止桥接，不能只记日志后继续假运行。"""
        eng, a, b = _engine()
        reasons = []
        errs = []
        eng.stopped.connect(reasons.append)
        eng.error_occurred.connect(lambda side, msg: errs.append((side, msg)))
        eng.start()
        a.error_occurred.emit("reader failed")
        self.assertFalse(eng.is_active())
        self.assertEqual(errs, [(0, "reader failed")])
        self.assertIn("Side A error", reasons[0])

    def test_large_counters_do_not_overflow_qt_signal(self):
        """累计超过 Qt 32-bit int 后仍能正常发射统计。"""
        eng, a, b = _engine()
        stats = []
        eng.stats_updated.connect(lambda *values: stats.append(values))
        eng.start()
        eng._a_rx = 3_000_000_000
        eng._tick_rate()
        self.assertEqual(stats[-1][0], 3_000_000_000)
        eng.stop()

    def test_stop_emits_final_counts(self):
        """不足一个定时周期就停止时，也不能漏掉最后累计值。"""
        eng, a, b = _engine()
        stats = []
        eng.stats_updated.connect(lambda *values: stats.append(values))
        eng.start()
        a.data_received.emit(b"end")
        eng.stop()
        self.assertEqual(stats[-1][3], 3)  # b_tx
        self.assertEqual(stats[-1][4:], (0, 0))

    def test_forwarded_signal_only_after_success(self):
        """转发日志的数据源只能是成功发送，失败数据不得冒充已转发。"""
        eng, a, b = _engine(b=FakeConn(send_result=0))
        forwarded = []
        eng.forwarded.connect(lambda side, data: forwarded.append((side, data)))
        eng.start()
        a.data_received.emit(b"lost")
        self.assertEqual(forwarded, [])
        b.send_result = None
        a.data_received.emit(b"ok")
        self.assertEqual(forwarded, [(0, b"ok")])
        eng.stop()

    def test_start_rejects_connection_without_bridge_target(self):
        """TCP Server 无客户端/UDP 无对端时不得进入会必丢首包的假桥接态。"""
        eng, a, b = _engine()
        b.bridge_ready = False
        self.assertFalse(eng.start())

    def test_guards(self):
        """未启动停 / 重复 start / 重复 stop 均安全。"""
        eng, a, b = _engine()
        eng.stop()
        self.assertFalse(eng.is_active())
        self.assertTrue(eng.start())
        self.assertFalse(eng.start())               # 重复 start → False
        eng.stop("x")
        eng.stop("y")
        self.assertFalse(eng.is_active())

    def test_start_requires_both_open(self):
        """一端未 open → start 返回 False。"""
        b = FakeConn()
        b.is_open = False
        eng, a, _ = _engine(b=b)
        self.assertFalse(eng.start())


class BridgeSidePanelTests(unittest.TestCase):
    class App:
        def _t(self, key, **kwargs):
            return key.format(**kwargs)

        def toast(self, _msg):
            pass

    def test_cancel_connecting_closes_underlying_connection(self):
        """TCP 尚在连接时 is_open=False，点击取消仍必须立即 close/abort。"""
        panel = _BridgeSidePanel(0, self.App())
        conn = FakeConn()
        conn.is_open = False
        panel._conn = conn
        panel._connecting = True
        panel.close_conn()
        self.assertTrue(conn.closed)
        self.assertIsNone(panel._conn)


class BridgeLogTests(unittest.TestCase):
    class Toggle:
        def __init__(self, checked):
            self.checked = checked

        def isChecked(self):
            return self.checked

    class View:
        def __init__(self):
            self.lines = []

        def appendPlainText(self, line):
            self.lines.append(line)

    class Harness:
        _MAX_LOG_BYTES_PER_ENTRY = BridgeDialog._MAX_LOG_BYTES_PER_ENTRY
        _reset_log_decoders = BridgeDialog._reset_log_decoders
        _append_log = BridgeDialog._append_log

        def __init__(self, hex_mode=False):
            self.sw_log = BridgeLogTests.Toggle(True)
            self.sw_log_hex = BridgeLogTests.Toggle(hex_mode)
            self.txt_log = BridgeLogTests.View()
            self._reset_log_decoders()

    def test_text_log_decodes_utf8_across_chunks(self):
        h = self.Harness()
        raw = "中".encode("utf-8")
        h._append_log(0, "A→B", raw[:2])
        h._append_log(0, "A→B", raw[2:])
        text = "\n".join(h.txt_log.lines)
        self.assertIn("中", text)
        self.assertNotIn("�", text)

    def test_log_entry_is_bounded(self):
        h = self.Harness(hex_mode=True)
        h._append_log(0, "A→B", b"x" * 10000)
        self.assertIn("+5904 bytes", h.txt_log.lines[0])
        self.assertLess(len(h.txt_log.lines[0]), 13000)


class BridgeConnectionSemanticsTests(unittest.TestCase):
    class Socket:
        def __init__(self, result, pending=0):
            self.result = result
            self.pending = pending
            self.writes = 0

        def bytesToWrite(self):
            return self.pending

        def write(self, data):
            self.writes += 1
            return len(data) if self.result is None else self.result

        def abort(self):
            pass

        def deleteLater(self):
            pass

    def test_tcp_server_bridge_requires_every_client(self):
        conn = TcpServerConn("127.0.0.1", 1)
        conn._clients = [self.Socket(None), self.Socket(0)]
        self.assertEqual(conn.send_bridge(b"frame"), 0)

    def test_tcp_server_bridge_caps_pending_buffer(self):
        conn = TcpServerConn("127.0.0.1", 1)
        sock = self.Socket(None, pending=4 * 1024 * 1024)
        conn._clients = [sock]
        self.assertEqual(conn.send_bridge(b"x"), 0)
        self.assertEqual(sock.writes, 0)

    def test_udp_bridge_splits_oversized_block(self):
        class RecordingUdp(UdpConn):
            def __init__(self):
                super().__init__("127.0.0.1", 1, "127.0.0.1", 2)
                self._sock = object()
                self.chunks = []

            def send(self, data, target=None):
                self.chunks.append(bytes(data))
                return len(data)

        conn = RecordingUdp()
        payload = b"x" * (_UDP_MAX_PAYLOAD + 10)
        self.assertEqual(conn.send_bridge(payload), len(payload))
        self.assertEqual(list(map(len, conn.chunks)), [_UDP_MAX_PAYLOAD, 10])
        conn._sock = None


class FakeTcpServerConn(QObject):
    """假 TCP Server：像真的一样同时发 data_received 和带来源的 data_received_from。"""
    data_received = pyqtSignal(bytes)
    data_received_from = pyqtSignal(bytes, str)
    clients_changed = pyqtSignal(list)
    state_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.is_open = True
        self.bridge_ready = True
        self.sent = []          # [(target, data)]

    def deliver(self, data, key):
        self.data_received.emit(data)
        self.data_received_from.emit(data, key)

    def send_bridge(self, data, target=None):
        self.sent.append((target, bytes(data)))
        return len(data)

    def send(self, data, target=None):
        return self.send_bridge(data, target)

    def close(self):
        self.is_open = False


class GatewayRoutingTests(unittest.TestCase):
    """网关回包必须只发给发起请求的客户端。"""

    def _setup(self):
        import modbus_master as mm
        import modbus_slave as ms
        eng = BridgeEngine()
        a, b = FakeTcpServerConn(), FakeConn()
        eng.set_connection(0, a)
        eng.set_connection(1, b)
        eng.set_modbus_gateway(True)
        eng.start()
        return eng, a, b, mm, ms

    def test_reply_targets_only_the_requesting_client(self):
        eng, a, b, mm, ms = self._setup()
        try:
            slave = ms.ModbusSlave(addr=1, holding={0: 0x1234})
            a.deliver(mm.build_tcp_request(0x77, 1, 3, 0, 1), "10.0.0.5:1111")
            self.assertEqual(len(b.sent), 1)              # 请求已转成 RTU
            b.data_received.emit(slave.handle(b.sent[0]))
            self.assertEqual(len(a.sent), 1)
            target, frame = a.sent[0]
            self.assertEqual(target, "10.0.0.5:1111")     # 定向，而非广播
            self.assertEqual(
                mm.take_tcp_response(frame, 0x77, 3, 1)[0]["regs"], [0x1234])
        finally:
            eng.stop()

    def test_two_clients_are_not_cross_fed(self):
        eng, a, b, mm, ms = self._setup()
        try:
            half = mm.build_tcp_request(0x11, 1, 3, 0, 1)[:5]
            a.deliver(half, "A:1")                         # A 只发了半帧
            self.assertEqual(b.sent, [])
            a.deliver(mm.build_tcp_request(0x22, 2, 3, 0, 1), "B:2")
            self.assertEqual(len(b.sent), 1)               # B 的整帧照常转出
            self.assertEqual(b.sent[0][0], 2)              # 而且是发给单元 2
            slave_b = ms.ModbusSlave(addr=2, holding={0: 0xBBBB})
            b.data_received.emit(slave_b.handle(b.sent[0]))
            self.assertEqual([t for t, _f in a.sent], ["B:2"])
        finally:
            eng.stop()

    def test_disconnected_client_reply_is_dropped(self):
        eng, a, b, mm, ms = self._setup()
        try:
            slave = ms.ModbusSlave(addr=1, holding={0: 0x1234})
            a.deliver(mm.build_tcp_request(0x33, 1, 3, 0, 1), "gone:9")
            self.assertEqual(len(b.sent), 1)
            a.clients_changed.emit([])                     # 该客户端断开
            b.data_received.emit(slave.handle(b.sent[0]))
            self.assertEqual(a.sent, [])                   # 回包丢弃，不广播
        finally:
            eng.stop()


if __name__ == "__main__":
    unittest.main()
