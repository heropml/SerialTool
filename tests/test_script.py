# -*- coding: utf-8 -*-
"""B5 脚本化应答 —— ctx 校验工具 / 脚本执行 / 导入门禁 测试。

覆盖 CommTool._ar_crc（通用可定制 CRC）/ _ar_make_ctx / _ar_script_eval / _ar_gate_imported_scripts。
匹配引擎依赖 GUI 模块(PyQt5/pyserial)；缺则整类跳过（真实代码错误仍抛出）。完整运行：
    .venv/bin/python -m unittest discover -s tests
注意：测试只读不写真实 QSettings（不调 _commit；构造后把 .settings 重定向到临时文件兜底）。
"""
import os
import sys
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from PyQt5.QtWidgets import QApplication, QLabel
    from PyQt5.QtCore import QSettings
    from main_window import CommTool
    from i18n import CHECKSUM_KEYS
    _IMPORT_ERR = None
except ModuleNotFoundError as e:
    if (e.name or "").split(".")[0] in {"serial", "PyQt5"}:
        CommTool = None
        _IMPORT_ERR = e
    else:
        raise

_APP = None
_WIN = None


def _win():
    """共享一个 CommTool 实例；把它的 settings 重定向到临时文件，确保测试不写真实配置。"""
    global _APP, _WIN
    _APP = QApplication.instance() or QApplication([])
    if _WIN is None:
        _WIN = CommTool()
        import tempfile
        _WIN.settings = QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat)
    return _WIN


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class CrcTests(unittest.TestCase):
    C = staticmethod(CommTool._ar_crc) if CommTool else None

    def test_standard_check_values(self):
        d = b"123456789"
        self.assertEqual(self.C(d, 16, 0x8005, 0xFFFF, refin=True, refout=True, byteorder="big"), b"\x4b\x37")  # MODBUS
        self.assertEqual(self.C(d, 16, 0x1021, 0x0000), b"\x31\xc3")                                            # XMODEM
        self.assertEqual(self.C(d, 16, 0x1021, 0xFFFF), b"\x29\xb1")                                            # CCITT-FALSE
        self.assertEqual(self.C(d, 8, 0x07, 0x00), b"\xf4")                                                     # CRC-8/SMBus
        self.assertEqual(self.C(d, 32, 0x04C11DB7, 0xFFFFFFFF, refin=True, refout=True,
                                xorout=0xFFFFFFFF, byteorder="big"), b"\xcb\xf4\x39\x26")                       # CRC-32

    def test_byteorder_and_width(self):
        be = self.C(b"\x01\x03", 16, 0x8005, 0xFFFF, refin=True, refout=True, byteorder="big")
        le = self.C(b"\x01\x03", 16, 0x8005, 0xFFFF, refin=True, refout=True, byteorder="little")
        self.assertEqual(le, be[::-1])
        self.assertEqual(len(self.C(b"x", 8, 0x07)), 1)
        self.assertEqual(len(self.C(b"x", 32, 0x04C11DB7)), 4)


class _XInbox:
    """线程安全字节缓冲：put 追加、read(n,timeout) 攒够 n 才回、超时 None、剩余留存。供 xfer loopback 用。"""
    def __init__(self):
        import threading
        self._buf = bytearray()
        self._cv = threading.Condition()

    def put(self, data):
        with self._cv:
            self._buf.extend(data)
            self._cv.notify_all()

    def read(self, n, timeout):
        deadline = time.monotonic() + timeout
        with self._cv:
            while len(self._buf) < n:
                remain = deadline - time.monotonic()
                if remain <= 0:
                    return None
                self._cv.wait(remain)
            out = bytes(self._buf[:n])
            del self._buf[:n]
            return out


class XferTests(unittest.TestCase):
    """XMODEM/XMODEM-1K/YMODEM 协议（纯逻辑，无 Qt）：CRC 标准值 + 全模式 loopback + 有损重传/去重。"""

    def _run(self, mode, data, drop_send=(), drop_recv=(), corrupt_send=()):
        import threading
        import xfer
        a2b, b2a = _XInbox(), _XInbox()      # a=发→收, b=收→发
        sc, rc, res = {"n": 0}, {"n": 0}, {}

        def send_putc(d):
            sc["n"] += 1
            if sc["n"] in drop_send:
                return
            if sc["n"] in corrupt_send and len(d) > 5:
                d = bytearray(d); d[4] ^= 0xFF; d = bytes(d)
            a2b.put(d)

        def recv_putc(d):
            rc["n"] += 1
            if rc["n"] not in drop_recv:
                b2a.put(d)

        def do_send():
            try:
                xfer.send_file(b2a.read, send_putc, data, mode=mode, name="fw.bin"); res["s"] = "ok"
            except Exception as e:
                res["s"] = repr(e)

        def do_recv():
            try:
                res["r"] = xfer.recv_file(a2b.read, recv_putc, mode=mode)
            except Exception as e:
                res["r"] = repr(e)

        ts, tr = threading.Thread(target=do_send), threading.Thread(target=do_recv)
        tr.start(); time.sleep(0.02); ts.start()
        ts.join(30); tr.join(30)
        return res

    def test_crc16_standard(self):
        import xfer
        self.assertEqual(xfer._crc16(b"123456789"), 0x31C3)   # XMODEM CRC-16 标准校验值

    def test_loopback_all_modes(self):
        import xfer
        for mode in xfer.MODES:
            for sz in (0, 1, 128, 1024, 3000):
                data = bytes((i * 7 + 3) & 0xFF for i in range(sz))
                res = self._run(mode, data)
                self.assertIsInstance(res.get("r"), tuple, "%s sz=%d recv err: %r" % (mode, sz, res.get("r")))
                got, meta = res["r"]
                self.assertEqual(res.get("s"), "ok", "%s sz=%d send err" % (mode, sz))
                if mode == xfer.MODE_YMODEM:
                    self.assertEqual(got, data)
                    self.assertEqual(meta.get("size"), sz)
                    if sz:
                        self.assertEqual(meta.get("name"), "fw.bin")
                else:
                    self.assertEqual(got.rstrip(bytes([xfer.SUB])), data.rstrip(bytes([xfer.SUB])))
                    self.assertGreaterEqual(len(got), sz)

    def test_lossy_retransmit_and_dedup(self):
        import xfer
        saved = (xfer.START_TIMEOUT, xfer.ACK_TIMEOUT, xfer.BLOCK_TIMEOUT)
        xfer.START_TIMEOUT = xfer.ACK_TIMEOUT = xfer.BLOCK_TIMEOUT = 0.3   # 调小超时跑快
        try:
            data = bytes((i * 13 + 1) & 0xFF for i in range(4100))        # ymodem: 头块 + 4×1K + 尾
            for label, kw in (
                ("drop data frame", dict(drop_send=(3,))),                # 丢帧 → 超时 → NAK 重发
                ("drop ACK → dup block", dict(drop_recv=(4,))),           # 丢 ACK → 重发 → 重复块去重
                ("corrupt frame", dict(corrupt_send=(4,))),               # 坏 CRC → NAK 重发
                ("multi fault", dict(drop_send=(3,), drop_recv=(6,), corrupt_send=(5,))),
            ):
                res = self._run(xfer.MODE_YMODEM, data, **kw)
                self.assertIsInstance(res.get("r"), tuple, "%s: recv err %r" % (label, res.get("r")))
                got, meta = res["r"]
                self.assertEqual(got, data, "%s: data mismatch" % label)
                self.assertEqual(meta.get("size"), len(data), "%s: size" % label)
        finally:
            xfer.START_TIMEOUT, xfer.ACK_TIMEOUT, xfer.BLOCK_TIMEOUT = saved

    def test_ymodem_send_tolerates_missing_end_handshake(self):
        """YMODEM 发送端：数据 + EOT 已确认交付后，接收方不发批次结束块的 C，也不应把「已成功交付」判为失败。"""
        import xfer
        q = [xfer.C]                     # 接收方回发队列（单字节）；预置起传 C
        blocks = []

        def getc(n, timeout):            # 单线程反应式 stub：有则取、空则超时 None
            if len(q) >= n:
                out = bytes(q[:n]); del q[:n]; return out
            return None

        def putc(frame):
            b0 = frame[0]
            if b0 in (xfer.SOH, xfer.STX):
                seq = frame[1]; blocks.append(seq)
                q.append(xfer.ACK)
                if seq == 0:             # 头块 → ACK 后补一个 C 起数据阶段
                    q.append(xfer.C)
            elif b0 == xfer.EOT:
                q.append(xfer.ACK)       # EOT ACK（数据已交付）；此后不再发 C（模拟对端已收尾）

        data = b"hello ymodem end handshake"
        n = xfer.send_file(getc, putc, data, mode=xfer.MODE_YMODEM, name="fw.bin")
        self.assertEqual(n, len(data))   # 缺末尾握手仍返回成功、不抛异常
        self.assertIn(0, blocks)         # 头块确已发出

    def test_loopback_block_number_wrap(self):
        """块号回绕：>256 块的传输要走过 seq 255→0 边界，数据仍完整（mod 256、send/recv 两端一致）。
        loopback 常规用例尺寸 ≤3000B 绕不到，这里用 XMODEM-CRC 128B/块 × ~313 块专门覆盖回绕。"""
        import xfer
        data = bytes((i * 7 + 3) & 0xFF for i in range(40000))
        res = self._run(xfer.MODE_XMODEM_CRC, data)
        self.assertIsInstance(res.get("r"), tuple, "recv err: %r" % (res.get("r"),))
        got, _ = res["r"]
        self.assertGreaterEqual(len(got) // 128, 257)     # 确实 >256 块（越过 255→0 回绕）
        self.assertEqual(got[:len(data)], data)           # 回绕两侧数据完整无错位

    def test_send_block_number_is_mod256(self):
        """发送端线上块号回绕为 mod 256：255 之后是 0（标准 XMODEM/YMODEM），不是 255→1。
        loopback 两端一致时 255→1 也会自洽通过，故这里直接断言线上块号值、把标准钉死。"""
        import xfer
        seqs, q = [], [xfer.C]            # 反应式 stub：预置起传 C；逐块 / EOT 回 ACK
        def getc(n, timeout):
            if len(q) >= n:
                out = bytes(q[:n]); del q[:n]; return out
            return None
        def putc(frame):
            b0 = frame[0]
            if b0 in (xfer.SOH, xfer.STX):
                seqs.append(frame[1]); q.append(xfer.ACK)
            elif b0 == xfer.EOT:
                q.append(xfer.ACK)
        xfer.send_file(getc, putc, bytes(300 * 128), mode=xfer.MODE_XMODEM_CRC)   # 300 块，越过 255
        self.assertEqual(seqs[254], 255)  # 第 255 块
        self.assertEqual(seqs[255], 0)    # 回绕 → 0（mod 256），不是 1
        self.assertEqual(seqs[256], 1)


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class ModbusMasterIntegrationTests(unittest.TestCase):
    def test_config_whitelist_contains_all_master_settings(self):
        self.assertTrue({"modbus_master", "modbus_master_on", "modbus_master_variant",
                         "modbus_master_echo"}.issubset(CommTool._CFG_KEYS))

    def test_partial_frame_send_is_failure_and_not_counted(self):
        w = _win()
        frame = bytes.fromhex("0110000000020400010002")

        class PartialConn:
            @staticmethod
            def send(data, target):
                return len(data) - 1

        old_conn, old_is_open, old_target = w.conn, w._is_open, w._send_target
        old_proto, old_close, old_reconnect = w._conn_proto, w.close_conn, w._schedule_reconnect
        old_bytes, old_packets = w.tx_bytes, w.tx_packets
        closed, reconnects = [], []
        try:
            w.conn = PartialConn()
            w._is_open = lambda: True
            w._send_target = lambda: None
            w._conn_proto = "TCP Client"
            w.close_conn = lambda: closed.append(True)
            w._schedule_reconnect = lambda: reconnects.append(True)
            self.assertFalse(w._mbm_send_raw(frame))
            self.assertEqual((w.tx_bytes, w.tx_packets), (old_bytes, old_packets))
            self.assertEqual(closed, [True])
            self.assertEqual(reconnects, [True])
        finally:
            w.conn = old_conn
            w._is_open = old_is_open
            w._send_target = old_target
            w._conn_proto, w.close_conn = old_proto, old_close
            w._schedule_reconnect = old_reconnect
            w.tx_bytes, w.tx_packets = old_bytes, old_packets

    def test_normal_send_rejects_and_counts_actual_partial_write(self):
        w = _win()

        class PartialConn:
            @staticmethod
            def send(_data, _target):
                return 1

        old_conn, old_open, old_proto = w.conn, w._is_open, w._conn_proto
        old_bytes, old_packets, old_errors = w.tx_bytes, w.tx_packets, w.tx_errors
        try:
            w.conn = PartialConn()
            w._is_open = lambda: True
            w._conn_proto = "Serial"
            self.assertFalse(w._send_text("AA BB", hex_mode=True, newline=0, checksum=0))
            self.assertEqual(w.tx_bytes, old_bytes + 1)
            self.assertEqual(w.tx_packets, old_packets)
            self.assertEqual(w.tx_errors, old_errors + 1)
        finally:
            w.conn, w._is_open, w._conn_proto = old_conn, old_open, old_proto
            w.tx_bytes, w.tx_packets, w.tx_errors = old_bytes, old_packets, old_errors

    def test_tcp_connection_reports_actual_short_write(self):
        from PyQt5.QtNetwork import QAbstractSocket
        from net_io import TcpClientConn

        class ShortSocket:
            @staticmethod
            def state():
                return QAbstractSocket.ConnectedState

            @staticmethod
            def write(_data):
                return 3

        conn = TcpClientConn("127.0.0.1", 1)
        conn._sock = ShortSocket()
        self.assertEqual(conn.send(b"1234567890"), 3)

    def test_tcp_server_rejects_and_drops_partial_client_stream(self):
        from net_io import TcpServerConn

        class ShortClient:
            aborted = False
            deleted = False

            def write(self, _data):
                return 3

            def abort(self):
                self.aborted = True

            def deleteLater(self):
                self.deleted = True

        client = ShortClient()
        conn = TcpServerConn("127.0.0.1", 1)
        conn._clients = [client]
        conn._emit_clients = lambda: None
        self.assertEqual(conn.send(b"1234567890"), 0)
        self.assertTrue(client.aborted)
        self.assertTrue(client.deleted)
        self.assertEqual(conn._clients, [])

    def test_protocol_change_pauses_existing_connection(self):
        class Combo:
            @staticmethod
            def currentText():
                return "TCP Client"

        fake = type("Fake", (), {"cb_proto": Combo(), "_conn_proto": "Serial",
                                  "_mbm_on": True, "_mbm_rules": [{"enabled": True}],
                                  "_mbm_connection_ready": lambda self: CommTool._mbm_connection_ready(self),
                                  "_is_open": lambda self: True})()
        self.assertFalse(CommTool._mbm_active(fake))

    def test_imported_master_is_paused_while_connected(self):
        opened = type("Fake", (), {"_is_open": lambda self: True})()
        closed = type("Fake", (), {"_is_open": lambda self: False})()
        self.assertFalse(CommTool._mbm_import_enabled(opened, True))
        self.assertTrue(CommTool._mbm_import_enabled(closed, True))

    def test_changed_serial_settings_pause_existing_connection(self):
        from modbus_master_dialog import ModbusMasterDialog
        w = _win()
        old_cfg, old_proto, old_on = w._conn_cfg, w._conn_proto, w._mbm_on
        old_rules, old_open = w._mbm_rules, w._is_open
        old_ui_proto, old_baud = w.cb_proto.currentText(), w.cb_baud.currentText()
        old_flow = w.cb_flow.currentText()
        try:
            w.cb_proto.setCurrentText("Serial")
            w.cb_baud.setCurrentText("9600")
            w.cb_flow.setCurrentText("None")
            w._conn_proto = "Serial"
            w._conn_cfg = w._conn_config_signature("Serial")
            w._mbm_on = True
            w._mbm_rules = [{"enabled": True}]
            w._is_open = lambda: True
            self.assertTrue(w._mbm_active())
            w.cb_flow.setCurrentText("RTS/CTS")
            self.assertFalse(w._mbm_active())
            w.cb_flow.setCurrentText("None")
            w.cb_baud.setCurrentText("19200")
            self.assertFalse(w._mbm_active())
            w._mbm_on = False
            dlg = ModbusMasterDialog(w)
            dlg.cb_enable.setChecked(True)
            self.assertFalse(dlg.cb_enable.isChecked())
            self.assertFalse(w._mbm_on)
            dlg.close()
        finally:
            w.cb_proto.setCurrentText(old_ui_proto)
            w.cb_baud.setCurrentText(old_baud)
            w.cb_flow.setCurrentText(old_flow)
            w._conn_cfg, w._conn_proto, w._mbm_on = old_cfg, old_proto, old_on
            w._mbm_rules, w._is_open = old_rules, old_open

    def test_coil_response_byte_count_must_match_request(self):
        fake = type("Fake", (), {"_t": lambda self, key: key})()
        self.assertIsNone(CommTool._mbm_validate(fake, {"qty": 1}, {"bits": [False] * 8}))
        self.assertEqual(CommTool._mbm_validate(
            fake, {"qty": 1}, {"bits": [False] * 16}), "mbm_st_badresp")

    def test_register_response_quantity_must_match_request(self):
        # ASCII 取帧层 qty 不参与切帧（响应自带长度），但应用层 _mbm_validate 必须拦截
        # 数量不符的读响应——请求 1 个寄存器、从机回 2 个不能当成功接受。
        fake = type("Fake", (), {"_t": lambda self, key: key})()
        self.assertIsNone(CommTool._mbm_validate(fake, {"qty": 1}, {"regs": [7]}))
        self.assertEqual(CommTool._mbm_validate(
            fake, {"qty": 1}, {"regs": [1, 2]}), "mbm_st_badresp")

    def test_qtimer_delay_is_clamped_after_rounding(self):
        class Timer:
            value = None

            def start(self, value):
                self.value = value

        fake = type("Fake", (), {})()
        fake._mbm_inflight = None
        fake._mbm_active = lambda: True
        fake._mbm_rules = [{"enabled": True}]
        fake._mbm_due = {0: time.monotonic() + 0x7FFFFFFF}
        fake._mbm_guard_until = 0.0
        fake._mbm_sched = Timer()
        fake._mbm_poll = lambda _i: self.fail("future poll must not run immediately")
        fake._MBM_QTIMER_MAX_MS = CommTool._MBM_QTIMER_MAX_MS
        CommTool._mbm_tick(fake)
        self.assertEqual(fake._mbm_sched.value, 0x7FFFFFFF)

    def test_rtu_timeout_uses_full_timeout_window_as_guard(self):
        fake = type("Fake", (), {})()
        fake._mbm_inflight = {"i": 0, "variant": "rtu", "timeout_ms": 2300}
        fake._mbm_buf = b"late"
        fake._MBM_MIN_GUARD_MS = CommTool._MBM_MIN_GUARD_MS
        fake._MBM_TIMEOUT_MS = CommTool._MBM_TIMEOUT_MS
        fake._mbm_set_result = lambda *_args: None
        fake._t = lambda key: key
        fake._mbm_tick = lambda: None
        fake._stat_note_timeout = lambda *_args: None
        before = time.monotonic()
        CommTool._mbm_on_timeout(fake)
        self.assertIsNone(fake._mbm_inflight)
        self.assertEqual(fake._mbm_buf, b"")
        self.assertGreaterEqual(fake._mbm_guard_until, before + 2.3)

    def test_late_byte_never_shortens_timeout_guard(self):
        fake = type("Fake", (), {})()
        fake._mbm_inflight = None
        fake._mbm_guard_until = time.monotonic() + 2.0
        fake._mbm_variant_eff = lambda: "rtu"
        fake._mbm_rtu_silent_ms = lambda: 5
        original = fake._mbm_guard_until
        CommTool._mbm_feed(fake, b"late")
        self.assertGreaterEqual(fake._mbm_guard_until, original)

    def test_successful_rtu_response_observes_interframe_silence(self):
        class Timer:
            stopped = False

            def stop(self):
                self.stopped = True

        fake = type("Fake", (), {})()
        fake._mbm_to = Timer()
        fake._mbm_inflight = {"variant": "rtu"}
        fake._mbm_buf = b"response"
        fake._mbm_rtu_silent_ms = lambda: 5
        fake._mbm_tick = lambda: None
        before = time.monotonic()
        CommTool._mbm_finish_inflight(fake)
        self.assertTrue(fake._mbm_to.stopped)
        self.assertGreaterEqual(fake._mbm_guard_until, before + 0.005)

    def test_successful_ascii_response_observes_interframe_silence(self):
        # 低速串口下 ASCII 响应（含 CRLF 帧界）需整帧传输时间量级的 guard，
        # 确保尾字节完全离线上前不发下一帧（ASCII 无事务 ID，迟到尾字节会串到下一请求）。
        class Timer:
            stopped = False

            def stop(self):
                self.stopped = True

        fake = type("Fake", (), {})()
        fake._mbm_to = Timer()
        fake._mbm_inflight = {"variant": "ascii", "resp_len": 19}
        fake._mbm_buf = b":0103...\r\n"
        fake._mbm_rtu_silent_ms = lambda: 5
        fake._mbm_tick = lambda: None
        fake._conn_proto = "Serial"
        # 1200baud 慢速串口，8N1：确保整帧传输时间 guard 远大于 t3.5 兜底
        fake._conn_cfg = ("Serial", "COM1", 1200, "8", "None", "1")
        fake.cb_baud = type("Combo", (), {"currentText": lambda self: "115200"})()
        fake.cb_databits = type("Combo", (), {"currentText": lambda self: "8"})()
        fake.cb_parity = type("Combo", (), {"currentText": lambda self: "None"})()
        fake.cb_stopbits = type("Combo", (), {"currentText": lambda self: "1"})()
        fake._mbm_serial_baud = lambda: CommTool._mbm_serial_baud(fake)
        fake._mbm_serial_char_bits = lambda: CommTool._mbm_serial_char_bits(fake)
        fake._mbm_rtu_tx_guard_ms = lambda n: CommTool._mbm_rtu_tx_guard_ms(fake, n)
        before = time.monotonic()
        CommTool._mbm_finish_inflight(fake)
        self.assertTrue(fake._mbm_to.stopped)
        self.assertIsNone(fake._mbm_inflight)
        self.assertEqual(fake._mbm_buf, b"")
        # 低速 1200baud 下 19 字符响应帧：传输时间(≈19*11/1200≈174ms) + t3.5，远大于 t3.5 兜底
        self.assertGreaterEqual(fake._mbm_guard_until, before + 0.05)
        self.assertGreater(fake._mbm_guard_until, before + 0.005)

    def test_successful_ascii_response_non_serial_uses_short_fallback(self):
        # 非串口连接（如 TCP/RTU-over-TCP）无波特率概念，用 t3.5 量级兜底即可
        # （ASCII 有 CRLF 帧界，帧界本身已提供切帧依据，无需整帧传输时间）。
        class Timer:
            stopped = False

            def stop(self):
                self.stopped = True

        fake = type("Fake", (), {})()
        fake._mbm_to = Timer()
        fake._mbm_inflight = {"variant": "ascii", "resp_len": 19}
        fake._mbm_buf = b":0103...\r\n"
        fake._mbm_rtu_silent_ms = lambda: 5
        fake._mbm_tick = lambda: None
        fake._conn_proto = "TCP"      # 非串口
        before = time.monotonic()
        CommTool._mbm_finish_inflight(fake)
        self.assertTrue(fake._mbm_to.stopped)
        self.assertIsNone(fake._mbm_inflight)
        self.assertGreaterEqual(fake._mbm_guard_until, before + 0.005)

    def test_sequence_release_observes_ascii_guard(self):
        """ASCII 与 RTU 一样无事务 ID，序列不能绕过正常响应后的隔离期。"""
        from unittest.mock import patch
        fake = type("Fake", (), {})()
        fake._seq_on = True
        fake._seq_gen = 7
        fake._seq_waiting_mbm = True
        fake._seq_wait_mbm_variant = "ascii"
        fake._mbm_inflight = None
        fake._seq_wait_mbm_until = 0.0
        fake._mbm_guard_until = time.monotonic() + 1.0
        fake._MBM_QTIMER_MAX_MS = CommTool._MBM_QTIMER_MAX_MS
        fake._seq_run_from = lambda _index: setattr(fake, "started", True)
        fake.started = False
        with patch("main_window.QTimer.singleShot") as single_shot:
            CommTool._seq_mbm_release_check(fake)
        self.assertTrue(fake._seq_waiting_mbm)
        self.assertFalse(fake.started)
        single_shot.assert_called_once()

    def test_broadcast_guard_includes_transmit_time(self):
        fake = type("Fake", (), {})()
        fake._conn_cfg = ("Serial", "COM1", 1200, "8", "None", "1")
        fake.cb_baud = type("Combo", (), {"currentText": lambda self: "115200"})()
        fake._mbm_serial_baud = lambda: CommTool._mbm_serial_baud(fake)
        fake._mbm_serial_char_bits = lambda: CommTool._mbm_serial_char_bits(fake)
        fake._mbm_rtu_silent_ms = lambda: CommTool._mbm_rtu_silent_ms(fake)
        guard = CommTool._mbm_rtu_tx_guard_ms(fake, 20)
        self.assertGreater(guard, CommTool._mbm_rtu_silent_ms(fake))

    def test_rtu_timing_uses_actual_serial_character_width(self):
        fake = type("Fake", (), {})()
        fake._conn_cfg = ("Serial", "COM1", 9600, "8", "Even", "2")
        fake.cb_baud = type("Combo", (), {"currentText": lambda self: "9600"})()
        fake._mbm_serial_baud = lambda: CommTool._mbm_serial_baud(fake)
        fake._mbm_serial_char_bits = lambda: CommTool._mbm_serial_char_bits(fake)
        self.assertEqual(CommTool._mbm_serial_char_bits(fake), 12.0)
        self.assertEqual(CommTool._mbm_rtu_silent_ms(fake), 5)

    def test_master_and_autoreply_switches_are_mutually_exclusive(self):
        w = _win()
        old_ar, old_mbm = w._ar_on, w._mbm_on
        try:
            w._ar_on, w._mbm_on = True, False
            w._set_mbm_enabled(True)
            self.assertTrue(w._mbm_on)
            self.assertFalse(w._ar_on)
            w._set_autoreply_enabled(True)
            self.assertTrue(w._ar_on)
            self.assertFalse(w._mbm_on)
        finally:
            w._ar_on, w._mbm_on = old_ar, old_mbm
            w.settings.setValue("autoreply_on", old_ar)
            w.settings.setValue("modbus_master_on", old_mbm)
            w._update_autoreply_btn()
            w._mbm_restart()

    def test_physical_close_clears_old_guard(self):
        w = _win()
        old_guard = w._mbm_guard_until
        try:
            w._mbm_guard_until = time.monotonic() + 10.0
            w.close_conn()
            self.assertEqual(w._mbm_guard_until, 0.0)
        finally:
            w._mbm_guard_until = old_guard

    def test_dirty_dialog_blocks_runtime_changes_using_old_rules(self):
        from modbus_master_dialog import ModbusMasterDialog
        w = _win()
        old_rules, old_on = w._mbm_rules, w._mbm_on
        old_variant, old_echo = w._mbm_variant, w._mbm_echo
        try:
            w._mbm_on = False
            w._mbm_variant = ""
            w._mbm_echo = False
            w._mbm_rules = [{"enabled": True, "name": "old", "unit": 1, "func": 6,
                             "addr": 10, "qty": 1, "period": 1000,
                             "wval": 0x1111, "wvals": []}]
            dlg = ModbusMasterDialog(w)
            dlg._rows[0]["qty"].setText("8738")  # 0x2222，仍是草稿
            self.assertTrue(dlg._dirty)
            dlg._on_enable(True)
            self.assertFalse(w._mbm_on)
            self.assertFalse(dlg.cb_enable.isChecked())
            self.assertEqual(w._mbm_rules[0]["wval"], 0x1111)
            dlg.cb_variant.setCurrentIndex(dlg.cb_variant.findData("tcp"))
            self.assertEqual(w._mbm_variant, "")
            self.assertEqual(dlg.cb_variant.currentData(), "")
            dlg.cb_echo.setChecked(True)
            self.assertFalse(w._mbm_echo)
            self.assertFalse(dlg.cb_echo.isChecked())
            dlg.close()
        finally:
            w._mbm_rules, w._mbm_on = old_rules, old_on
            w._mbm_variant, w._mbm_echo = old_variant, old_echo

    def test_header_stays_aligned_when_vertical_scrollbar_appears(self):
        from PyQt5.QtWidgets import QApplication
        from modbus_master_dialog import ModbusMasterDialog
        w = _win()
        old_rules = w._mbm_rules
        try:
            w._mbm_rules = [
                {"enabled": True, "name": "row%d" % i, "unit": 1, "func": 3,
                 "addr": i, "qty": 1, "period": 1000, "wval": 0, "wvals": []}
                for i in range(30)
            ]
            dlg = ModbusMasterDialog(w)
            dlg.resize(1040, 460)
            dlg.show()
            QApplication.instance().processEvents()
            QApplication.instance().processEvents()
            row_split = dlg._rows[0]["split"]
            self.assertTrue(dlg.scroll.verticalScrollBar().isVisible())
            self.assertEqual(dlg._hdr_split.width(), row_split.width())
            self.assertEqual(dlg._hdr_split.sizes(), row_split.sizes())
            dlg.close()
        finally:
            w._mbm_rules = old_rules

    def test_tcp_server_broadcast_succeeds_if_any_client_gets_full_frame(self):
        from net_io import TcpServerConn

        class DeadClient:        # write 返回 -1：对端 RST / 缓冲满
            @staticmethod
            def write(_data):
                return -1

        class GoodClient:
            @staticmethod
            def write(data):
                return len(data)

        dead, good = DeadClient(), GoodClient()
        conn = TcpServerConn("127.0.0.1", 1)
        conn._clients = [dead, good]
        conn._emit_clients = lambda: None
        # 一个客户端 -1 失败、另一个整帧成功 → 整体成功(返回 len)，不因掉线客户端误判失败；
        # -1 客户端不剔除(交 Qt disconnected 清理)。
        self.assertEqual(conn.send(b"1234567890"), 10)
        self.assertEqual(conn._clients, [dead, good])

    def test_disable_autoreply_syncs_open_dialog_checkbox(self):
        from auto_reply_dialog import AutoReplyDialog
        w = _win()
        old_ar, old_dlg = w._ar_on, getattr(w, "_ar_dlg", None)
        try:
            w._ar_on = True
            dlg = AutoReplyDialog(w)
            w._ar_dlg = dlg
            dlg.cb_enable.setChecked(True)
            w._set_autoreply_enabled(False)
            self.assertFalse(w._ar_on)
            self.assertFalse(dlg.cb_enable.isChecked())   # 打开着的对话框 checkbox 同步关闭
            dlg.close()
        finally:
            w._ar_on, w._ar_dlg = old_ar, old_dlg

    def test_port_combo_keeps_selection_when_device_vanishes(self):
        """选中口在某次扫描里没枚举到时，选择必须保留（占位），绝不静默漂移到别的口。
        复现并钉死「选了串口1、后台扫描 COM1 短暂消失 → 打开成了串口2」的根因。"""
        w = _win()
        # 选 COM1
        w._populate_port_combo([("COM1", "COM1"), ("COM2", "COM2")], keep_device="COM1")
        self.assertEqual(w.cb_port.currentData(), "COM1")
        # COM1 本次扫描消失（只剩 COM2）→ 选择必须仍是 COM1，不能跳到 COM2
        w._populate_port_combo([("COM2", "COM2")], keep_device="COM1")
        self.assertEqual(w.cb_port.currentData(), "COM1")        # 占位保留，未漂移到 COM2
        self.assertIn("COM1", w.cb_port.currentText())           # 显示为占位（含设备名）
        # COM1 回来 → 选回真实 COM1（不再是占位项）
        w._populate_port_combo([("COM1", "COM1"), ("COM2", "COM2")], keep_device="COM1")
        self.assertEqual(w.cb_port.currentData(), "COM1")
        self.assertEqual(w.cb_port.currentText(), "COM1")        # 真实项标签，非「未检测到」

    def test_multi_send_column_width_persists(self):
        """拖动名称/数据列宽 → 写盘；重开对话框恢复（不再回默认）。"""
        from dialogs import MultiSendDialog

        class _FakeSplit:                       # 绕开离屏下 splitter 无几何的问题
            def sizes(self):
                return [150, 400]
            def setSizes(self, s):
                pass
        w = _win()
        old = w._ms_groups
        try:
            w._ms_groups = [{"name": "T", "items": [{"name": "A", "data": "a"}]}]
            w.settings.remove("multi_send_split")
            dlg = MultiSendDialog(w)
            self.assertIsNone(dlg._name_split_sizes)            # 没存过 → 默认
            dlg._sync_splits(_FakeSplit())                      # 模拟拖动到 150/400
            self.assertEqual(w.settings.value("multi_send_split", ""), "150,400")
            dlg.close()
            # 重开 → 读回保存的列宽，不再回默认
            dlg2 = MultiSendDialog(w)
            self.assertEqual(dlg2._name_split_sizes, [150, 400])
            dlg2.close()
        finally:
            w._ms_groups = old
            w.settings.remove("multi_send_split")

    def test_modbus_master_column_width_persists(self):
        """Modbus 主机轮询：拖动列宽 → 写盘；重开对话框恢复。"""
        from modbus_master_dialog import ModbusMasterDialog, _DEFAULT_SPLIT

        class _FakeSplit:
            def __init__(self, sizes):
                self._s = sizes
            def sizes(self):
                return self._s
            def setSizes(self, s):
                pass
        w = _win()
        try:
            w.settings.remove("modbus_master_split")
            dlg = ModbusMasterDialog(w)
            self.assertIsNone(dlg._split_sizes)
            new_sizes = [s + 7 for s in _DEFAULT_SPLIT]
            dlg._sync_splits(_FakeSplit(new_sizes))
            self.assertEqual(w.settings.value("modbus_master_split", ""),
                             ",".join(str(s) for s in new_sizes))
            dlg.close()
            dlg2 = ModbusMasterDialog(w)
            self.assertEqual(dlg2._split_sizes, new_sizes)
            dlg2.close()
        finally:
            w.settings.remove("modbus_master_split")

    def test_autoreply_column_width_persists(self):
        """自动应答：拖动收到/回复列宽 → 写盘；重开对话框恢复。"""
        from auto_reply_dialog import AutoReplyDialog

        class _FakeSplit:
            def sizes(self):
                return [220, 520]
            def setSizes(self, s):
                pass
        w = _win()
        try:
            w.settings.remove("autoreply_split")
            dlg = AutoReplyDialog(w)
            self.assertIsNone(dlg._split_sizes)
            dlg._sync_splitters(_FakeSplit())
            self.assertEqual(w.settings.value("autoreply_split", ""), "220,520")
            dlg.close()
            dlg2 = AutoReplyDialog(w)
            self.assertEqual(dlg2._split_sizes, [220, 520])
            dlg2.close()
        finally:
            w.settings.remove("autoreply_split")

    def test_port_placeholder_dropped_after_grace(self):
        """未连接：选中口短暂消失保留占位(防漂移)；长期不在时——即便端口列表此后稳定不变——
        占位也要在宽限后被删、回落真实口（钉死「列表稳定后计数停更、占位删不掉」的回归）。"""
        w = _win()
        old = (w.conn, w._pending_restore_port, w._last_port_list, w._sel_missing_count)
        try:
            w.conn = None
            w._pending_restore_port = None
            w._sel_missing_count = 0
            w._last_port_list = None
            # 选中 COM1
            w._populate_port_combo([("COM1", "COM1"), ("COM2", "COM2")], "COM1")
            self.assertEqual(w.cb_port.currentData(), "COM1")
            # 之后端口列表【稳定】为只有 COM2（COM1 一直不在）——不手动重置 _last_port_list，
            # 验证列表稳定时计数仍推进、占位最终被删。
            for _ in range(w._serial_missing_limit):
                w._on_port_scan_complete([("COM2", "COM2")])
                self.assertEqual(w.cb_port.currentData(), "COM1")   # 宽限内保留 COM1 占位
            # 超宽限的那次：列表依旧没变，也要删占位、回落第一个真实口 COM2
            w._on_port_scan_complete([("COM2", "COM2")])
            self.assertEqual(w.cb_port.currentData(), "COM2")
            datas = [w.cb_port.itemData(i) for i in range(w.cb_port.count())]
            self.assertNotIn("COM1", datas)                   # 占位已删，不再常驻
        finally:
            (w.conn, w._pending_restore_port, w._last_port_list,
             w._sel_missing_count) = old

    def test_port_pending_restored_when_scan_precedes_config(self):
        """启动扫描早于配置恢复：pending 在「端口列表已与上次相同」之后才设上，仍要选回上次的串口
        （钉死「列表没变就 return、pending 永远跳过」的时序回归）。"""
        w = _win()
        old = (w.conn, w._pending_restore_port, w._last_port_list, w._sel_missing_count)
        try:
            w.conn = None
            w._sel_missing_count = 0
            w._pending_restore_port = None
            w._last_port_list = None
            # 第一次扫描已处理(此时还没 pending)，_last_port_list 已等于当前列表，cb_port 落在 COM1
            w._populate_port_combo([("COM1", "COM1"), ("COM87", "COM87")], None)
            w._on_port_scan_complete([("COM1", "COM1"), ("COM87", "COM87")])
            self.assertEqual(w.cb_port.currentData(), "COM1")
            # 配置恢复此刻才设上 pending=COM87；下一次扫描端口列表【不变】
            w._pending_restore_port = "COM87"
            w._on_port_scan_complete([("COM1", "COM1"), ("COM87", "COM87")])
            self.assertEqual(w.cb_port.currentData(), "COM87")   # 列表没变也选回了 COM87
            self.assertIsNone(w._pending_restore_port)
        finally:
            (w.conn, w._pending_restore_port, w._last_port_list,
             w._sel_missing_count) = old

    def test_port_pending_reselected_when_device_returns(self):
        """启动恢复：上次端口先占位、超宽限回落到别的口，插上后仍自动选回（pending 不被占位误清）。"""
        w = _win()
        old = (w.conn, w._pending_restore_port, w._last_port_list, w._sel_missing_count)
        try:
            w.conn = None
            w._sel_missing_count = 0
            w._last_port_list = None
            w._pending_restore_port = "COM1"
            # 起点：COM1 占位选中（pending 恢复但没插）
            w._populate_port_combo([("COM2", "COM2"), ("COM3", "COM3")], "COM1")
            self.assertEqual(w.cb_port.currentData(), "COM1")
            # 列表【稳定】 [COM2,COM3]、COM1 一直不在 → 超宽限后删占位、回落，但 pending 仍 COM1
            for _ in range(w._serial_missing_limit + 2):
                w._on_port_scan_complete([("COM2", "COM2"), ("COM3", "COM3")])
            self.assertNotEqual(w.cb_port.currentData(), "COM1")  # 已回落
            self.assertEqual(w._pending_restore_port, "COM1")     # pending 未被占位误清
            # COM1 插上（列表变化）→ 自动选回 + 清 pending
            w._on_port_scan_complete([("COM1", "COM1"), ("COM2", "COM2"), ("COM3", "COM3")])
            self.assertEqual(w.cb_port.currentData(), "COM1")
            self.assertIsNone(w._pending_restore_port)
        finally:
            (w.conn, w._pending_restore_port, w._last_port_list,
             w._sel_missing_count) = old

    def test_terminal_key_mapping(self):
        """终端模式按键 → 字节映射：回车(CR/LF/CRLF)、Backspace、Tab、方向键、Ctrl+C、普通字符。"""
        from PyQt5.QtCore import Qt
        w = _win()
        old = w._terminal_enter
        try:
            w._terminal_enter = 0   # CR
            self.assertEqual(w._term_key_to_bytes(Qt.Key_Return, Qt.NoModifier, "\r"), (b"\r", "\n"))
            w._terminal_enter = 1   # LF
            self.assertEqual(w._term_key_to_bytes(Qt.Key_Return, Qt.NoModifier, ""), (b"\n", "\n"))
            w._terminal_enter = 2   # CRLF
            self.assertEqual(w._term_key_to_bytes(Qt.Key_Enter, Qt.NoModifier, ""), (b"\r\n", "\n"))
            self.assertEqual(w._term_key_to_bytes(Qt.Key_Backspace, Qt.NoModifier, "")[0], b"\x7f")
            self.assertEqual(w._term_key_to_bytes(Qt.Key_Tab, Qt.NoModifier, "\t"), (b"\t", "\t"))
            self.assertEqual(w._term_key_to_bytes(Qt.Key_Up, Qt.NoModifier, "")[0], b"\x1b[A")
            self.assertEqual(w._term_key_to_bytes(Qt.Key_Left, Qt.NoModifier, "")[0], b"\x1b[D")
            self.assertEqual(w._term_key_to_bytes(Qt.Key_C, Qt.ControlModifier, "\x03")[0], b"\x03")
            self.assertEqual(w._term_key_to_bytes(Qt.Key_A, Qt.NoModifier, "a"), (b"a", "a"))
            self.assertEqual(w._term_key_to_bytes(Qt.Key_unknown, Qt.NoModifier, ""), (None, None))
        finally:
            w._terminal_enter = old

    def test_terminal_append_stream(self):
        r"""终端轻量 VT 渲染：\n 换行、\r 回行首、\b 光标左移 + 覆盖式打印。"""
        w = _win()
        old_esc, old_discard, old_pos = w._term_esc, w._term_discard_csi, w._term_pos
        try:
            w._term_esc = ""
            w._term_pos = None
            w.txt_recv.clear()
            w._terminal_append("line1\nline2")
            self.assertEqual(w.txt_recv.toPlainText(), "line1\nline2")
            # \r 回行首 + 覆盖：abc\rXY → XYc（X 覆盖 a、Y 覆盖 b、c 留存，真终端行为）
            w.txt_recv.clear()
            w._terminal_append("abc\rXY")
            self.assertEqual(w.txt_recv.toPlainText(), "XYc")
            w.txt_recv.clear()
            w._terminal_append("a\r\nb")
            self.assertEqual(w.txt_recv.toPlainText(), "a\nb")
            # \b 光标左移（非破坏）+ 覆盖：abc\b\bX → aXc
            w.txt_recv.clear()
            w._terminal_append("abc\b\bX")
            self.assertEqual(w.txt_recv.toPlainText(), "aXc")
            # 'BS 空格 BS' 擦除序列：ab\b \bX → aX
            w.txt_recv.clear()
            w._terminal_append("ab\b \bX")
            self.assertEqual(w.txt_recv.toPlainText(), "aX")
            # 用户设备的退格回显：BS + ESC[J（擦光标到末尾）+ 杂散 0xFF(U+FFFD) → 删末字符
            w.txt_recv.clear()
            w._terminal_append("ls")
            w._terminal_append("\b\x1b[J�")
            self.assertEqual(w.txt_recv.toPlainText(), "l")
            # 颜色码 ESC[..m 被忽略（不再显示成 ^[[31m 乱码）
            w.txt_recv.clear()
            w._terminal_append("a\x1b[31mb\x1b[0mc")
            self.assertEqual(w.txt_recv.toPlainText(), "abc")
            # ESC[K 擦到行尾
            w.txt_recv.clear()
            w._terminal_append("abcde\r\x1b[K")
            self.assertEqual(w.txt_recv.toPlainText(), "")
            # 超大 CSI 光标计数：到边界即停、不空转冻结（ab + ESC[大数D → 回行首，X 覆盖 a → Xb）
            w.txt_recv.clear()
            w._terminal_append("ab\x1b[999999999DX")
            self.assertEqual(w.txt_recv.toPlainText(), "Xb")
            # 未处理控制符（BEL/NUL）丢弃
            w.txt_recv.clear()
            w._terminal_append("a\x07\x00b")
            self.assertEqual(w.txt_recv.toPlainText(), "ab")
            # 跨块拼接的转义序列：ESC[ 在前一块、J 在后一块
            w.txt_recv.clear()
            w._terminal_append("xy")
            w._terminal_append("\b\x1b[")
            w._terminal_append("J")
            self.assertEqual(w.txt_recv.toPlainText(), "x")
            # 未完成的超长 CSI 跨块输入会被丢弃，不无限增长；之后普通文本仍可继续渲染
            w.txt_recv.clear()
            w._terminal_append("\x1b[" + "9" * 100)
            self.assertEqual(w._term_esc, "")
            self.assertTrue(w._term_discard_csi)
            w._terminal_append("mok")   # m 终止并被丢弃，后面的普通文本继续渲染
            self.assertEqual(w.txt_recv.toPlainText(), "ok")
        finally:
            w._term_esc, w._term_discard_csi, w._term_pos = old_esc, old_discard, old_pos

    def test_terminal_mode_receive_bypasses_decoration(self):
        """终端模式收数据：纯流显示，绕过时间戳/方向/HEX/分包装饰。"""
        w = _win()
        old = w._terminal_on
        try:
            w._terminal_on = True
            w.txt_recv.clear()
            w._on_data_received_impl(b"hello\n")
            self.assertEqual(w.txt_recv.toPlainText(), "hello\n")
        finally:
            w._terminal_on = old

    def test_profile_lock_acquire_and_reclaim(self):
        """配置槽位锁：临时目录隔离（不受外部已开窗口影响），依次分配 ''/2/3，释放中间槽后复用。"""
        import main as _main
        import tempfile
        import shutil
        import os as _os
        d = tempfile.mkdtemp()
        path_fn = lambda p: _os.path.join(d, "settings.ini" if not p else "settings-%s.ini" % p)
        p1, l1 = _main._acquire_profile(path_fn)
        p2, l2 = _main._acquire_profile(path_fn)
        p3, l3 = _main._acquire_profile(path_fn)
        try:
            self.assertEqual((p1, p2, p3), ("", "2", "3"))   # 干净环境 → 确定性槽位
            l2.unlock()                                       # 释放中间槽位 2
            p4, l4 = _main._acquire_profile(path_fn)
            self.assertEqual(p4, "2")                         # 复用刚释放的槽位
            l4.unlock()
        finally:
            l1.unlock()
            l3.unlock()
            shutil.rmtree(d, ignore_errors=True)

    def test_acquire_profile_prefers_requested_slot(self):
        """「打开指定配置」：preferred 指定的空闲槽位被优先占用；被占则回落到第一个空闲槽位。"""
        import main as _main
        import tempfile
        import shutil
        import os as _os
        d = tempfile.mkdtemp()
        path_fn = lambda p: _os.path.join(d, "settings.ini" if not p else "settings-%s.ini" % p)
        p, lock = _main._acquire_profile(path_fn, preferred="3")
        try:
            self.assertEqual(p, "3")                              # 指定的空闲槽位被优先拿到
            p2, lock2 = _main._acquire_profile(path_fn, preferred="3")
            try:
                self.assertEqual(p2, "")                          # "3" 已占 → 回落到第一个空闲("")
            finally:
                lock2.unlock()
        finally:
            lock.unlock()
            shutil.rmtree(d, ignore_errors=True)

    def test_acquire_profile_returns_none_when_full(self):
        """8 个槽位全占（开满 8 窗口）时返回 (None, None) → 调用方提示已达上限、不再开第 9 个。"""
        import main as _main
        import tempfile
        import shutil
        import os as _os
        d = tempfile.mkdtemp()
        path_fn = lambda p: _os.path.join(d, "settings.ini" if not p else "settings-%s.ini" % p)
        locks = []
        try:
            for _ in range(8):                                  # 占满 "" + 2..8 共 8 个
                p, lk = _main._acquire_profile(path_fn)
                self.assertIsNotNone(lk)
                locks.append(lk)
            p9, lk9 = _main._acquire_profile(path_fn)            # 第 9 个：无空闲槽位
            self.assertIsNone(p9)
            self.assertIsNone(lk9)
        finally:
            for lk in locks:
                lk.unlock()
            shutil.rmtree(d, ignore_errors=True)

    def test_parse_profile_arg(self):
        """命令行 --profile=<值> 解析：合法值取回 / 空值=主配置 / 无该参数 / 越界·乱填 → None。"""
        import main as _main
        self.assertEqual(_main._parse_profile_arg(["x", "--profile=3", "y"]), "3")
        self.assertEqual(_main._parse_profile_arg(["--profile="]), "")   # 空 = 主配置
        self.assertIsNone(_main._parse_profile_arg(["x", "y"]))
        self.assertIsNone(_main._parse_profile_arg(["--profile=9"]))     # 越界(>8) → None，防孤儿配置
        self.assertIsNone(_main._parse_profile_arg(["--profile=abc"]))   # 乱填 → None

    def test_acquire_profile_ignores_out_of_range_preferred(self):
        """越界 preferred（如 "9"）被忽略、走正常扫描回落到第一个空闲，不建出菜单选不到的孤儿槽位。"""
        import main as _main
        import tempfile
        import shutil
        import os as _os
        d = tempfile.mkdtemp()
        path_fn = lambda p: _os.path.join(d, "settings.ini" if not p else "settings-%s.ini" % p)
        p, lock = _main._acquire_profile(path_fn, preferred="9")
        try:
            self.assertEqual(p, "")   # "9" 非法 → 忽略 → 拿第一个空闲槽位
        finally:
            lock.unlock()
            shutil.rmtree(d, ignore_errors=True)

    def test_profile_in_use_smoke(self):
        """_profile_in_use（子菜单标注「使用中」用）探测不抛异常、返回 bool。"""
        w = _win()
        self.assertIn(w._profile_in_use("7"), (True, False))

    def test_switch_profile_in_place(self):
        """就地切换配置（不新开窗口）：_profile/_title_suffix/settings/标题切到目标；
        P1 切换取消排队的自动重连；P2 目标缺键的字段复位到默认、不残留上一配置。
        用共享 _win() + 存/还原身份——不新建实例（新建后 _shutdown 会与 port_scanner 线程在
        进程退出时竞态、触发 Qt C++ 层崩溃 0xC0000409；其它测试也都复用 _win() 不销毁）。"""
        from PyQt5.QtWidgets import QApplication
        import tempfile
        import shutil
        import os as _os
        w = _win()
        app = QApplication.instance()
        o_profile, o_suffix, o_settings = w._profile, w._title_suffix, w.settings
        o_project = (w._project_path, dict(w._project_meta),
                     w._project_name, w._project_baseline)
        o_confirm_switch = w._confirm_project_switch
        had_lock = hasattr(app, "_profile_lock")
        o_app_lock = getattr(app, "_profile_lock", None)
        o_send = w.txt_send.toPlainText()
        d = tempfile.mkdtemp()
        orig = CommTool._settings_file
        CommTool._settings_file = staticmethod(
            lambda p="": _os.path.join(d, "settings.ini" if not p else "settings-%s.ini" % p))
        try:
            w._confirm_project_switch = lambda: True
            w._project_path = _os.path.join(d, "old.ctproj")
            w._project_name = "Old project"
            w._project_meta = {"connection_type": "Serial"}
            w._project_baseline = "old-baseline"
            w.txt_send.setPlainText("LEAK-ME")           # P2：制造"上一配置"的残留值
            w._reconnect_timer.start(99999)              # P1：模拟排队中的自动重连
            w._switch_profile("3")
            self.assertEqual(w._profile, "3")
            self.assertEqual(w._title_suffix, " (3)")
            self.assertTrue(w.windowTitle().endswith("(3)"))
            self.assertTrue(w.settings.fileName().endswith("settings-3.ini"))
            self.assertEqual(w.txt_send.toPlainText(), w._field_defaults.get("txt_send", ""))  # P2：复位、不残留
            self.assertFalse(w._reconnect_timer.isActive())                                     # P1：已取消重连
            self.assertIsNone(w._project_path)                                                    # 旧工程不得绑到新 profile
            self.assertEqual(w._project_name, "")
            self.assertEqual(w._project_meta, {})
            self.assertIsNone(w._project_baseline)
        finally:
            CommTool._settings_file = staticmethod(orig)
            cur = getattr(app, "_profile_lock", None)   # 释放 switch 抢的锁、还原 app 锁
            if cur is not None and cur is not o_app_lock:
                try:
                    cur.unlock()
                except Exception:
                    pass
            if had_lock:
                app._profile_lock = o_app_lock
            elif hasattr(app, "_profile_lock"):
                try:
                    delattr(app, "_profile_lock")
                except Exception:
                    pass
            # 还原共享 _WIN 身份/settings/发送框/标题，避免污染后续测试
            w._profile, w._title_suffix, w.settings = o_profile, o_suffix, o_settings
            (w._project_path, w._project_meta,
             w._project_name, w._project_baseline) = o_project
            w._confirm_project_switch = o_confirm_switch
            w.txt_send.setPlainText(o_send)
            w._reconnect_timer.stop()
            w.setWindowTitle(w._t("app_title") + w._title_suffix)
            shutil.rmtree(d, ignore_errors=True)

    def test_switch_profile_cancel_keeps_current_project_and_profile(self):
        w = _win()
        old_confirm = w._confirm_project_switch
        old_path, old_name = w._project_path, w._project_name
        try:
            w._project_path = "current.ctproj"
            w._project_name = "Current"
            w._confirm_project_switch = lambda: False
            profile = w._profile
            settings = w.settings
            w._switch_profile("3" if profile != "3" else "4")
            self.assertEqual(w._profile, profile)
            self.assertIs(w.settings, settings)
            self.assertEqual(w._project_path, "current.ctproj")
            self.assertEqual(w._project_name, "Current")
        finally:
            w._confirm_project_switch = old_confirm
            w._project_path, w._project_name = old_path, old_name

    def test_project_collect_propagates_pending_editor_failure(self):
        w = _win()
        old_dialog = getattr(w, "_multi_send_dlg", None)

        class BrokenEditor:
            @staticmethod
            def flush_pending():
                raise OSError("pending edit failed")

        try:
            w._multi_send_dlg = BrokenEditor()
            with self.assertRaisesRegex(OSError, "pending edit failed"):
                w._collect_project_settings()
        finally:
            w._multi_send_dlg = old_dialog

    def test_project_apply_rejects_qsettings_sync_error(self):
        from PyQt5.QtCore import QSettings
        w = _win()
        old_settings = w.settings

        class FailingSettings:
            def __init__(self):
                self.values = {}
            def value(self, key, default=None):
                return self.values.get(key, default)
            def setValue(self, key, value):
                self.values[key] = value
            def remove(self, key):
                self.values.pop(key, None)
            @staticmethod
            def sync():
                pass
            @staticmethod
            def status():
                return QSettings.AccessError

        try:
            w.settings = FailingSettings()
            with self.assertRaisesRegex(OSError, "QSettings sync failed"):
                w._apply_project_settings({"rx_hex": True}, gate_scripts=False)
        finally:
            w.settings = old_settings

    def test_switch_profile_save_failure_keeps_identity_and_releases_target_lock(self):
        from PyQt5.QtCore import QLockFile
        import os as _os
        import shutil
        import tempfile

        w = _win()
        old_confirm = w._confirm_project_switch
        old_info = w._info_dlg
        old_dialog = getattr(w, "_multi_send_dlg", None)
        original_settings_file = CommTool._settings_file
        folder = tempfile.mkdtemp()
        target = "3" if w._profile != "3" else "4"

        class BrokenEditor:
            @staticmethod
            def flush_pending():
                raise OSError("cannot flush")

        try:
            CommTool._settings_file = staticmethod(
                lambda p="": _os.path.join(
                    folder, "settings.ini" if not p else "settings-%s.ini" % p))
            w._confirm_project_switch = lambda: True
            w._info_dlg = lambda *args, **kwargs: None
            w._multi_send_dlg = BrokenEditor()
            profile, settings = w._profile, w.settings

            w._switch_profile(target)

            self.assertEqual(w._profile, profile)
            self.assertIs(w.settings, settings)
            probe = QLockFile(CommTool._settings_file(target) + ".mwlock")
            self.assertTrue(probe.tryLock(0), "failed switch leaked the target profile lock")
            probe.unlock()
        finally:
            CommTool._settings_file = staticmethod(original_settings_file)
            w._confirm_project_switch = old_confirm
            w._info_dlg = old_info
            w._multi_send_dlg = old_dialog
            shutil.rmtree(folder, ignore_errors=True)

    def test_delete_profile(self):
        """删除配置：确认→删掉 settings-<N>.ini；取消→保留；主配置("")即使确认也拒删（前置 guard）。
        用共享 _win()（_delete_profile 只删文件、不改 UI）+ monkeypatch _settings_file + stub 确认框。"""
        import tempfile
        import shutil
        import os as _os
        w = _win()
        d = tempfile.mkdtemp()
        orig = CommTool._settings_file
        CommTool._settings_file = staticmethod(
            lambda p="": _os.path.join(d, "settings.ini" if not p else "settings-%s.ini" % p))
        try:
            target = CommTool._settings_file("4")
            open(target, "w").close()                       # 造一个待删配置
            main_ini = CommTool._settings_file("")
            open(main_ini, "w").close()
            w._confirm_dlg = lambda *a, **k: False           # 取消 → 不删
            w._delete_profile("4")
            self.assertTrue(_os.path.exists(target))
            w._confirm_dlg = lambda *a, **k: True            # 确认 → 删
            w._delete_profile("4")
            self.assertFalse(_os.path.exists(target))
            w._delete_profile("")                            # 主配置：前置 guard 直接返回，不删
            self.assertTrue(_os.path.exists(main_ini))
            w._delete_profile("9")                           # 越界(非 2..8)：前置 guard 拒绝
            # 被占：目标配置的 .mwlock 被别处持有（模拟另一窗口在用）→ 拒绝删除、文件保留
            from PyQt5.QtCore import QLockFile
            t5 = CommTool._settings_file("5")
            open(t5, "w").close()
            held = QLockFile(t5 + ".mwlock")
            self.assertTrue(held.tryLock(0))
            try:
                w._delete_profile("5")                       # confirm 仍为 True，但锁被占
                self.assertTrue(_os.path.exists(t5))         # 被占 → 未删
            finally:
                held.unlock()
        finally:
            w.__dict__.pop("_confirm_dlg", None)             # 移除 stub，恢复类方法
            CommTool._settings_file = staticmethod(orig)
            shutil.rmtree(d, ignore_errors=True)

    def test_statusbar_background_opaque(self):
        """状态栏背景须不透明（窗口色）——若为 transparent，toast(showMessage) 时 Qt 隐藏 RX/TX
        统计标签但透明底不擦底、旧像素残留会与提示文字重叠（用户实测到的 bug）。"""
        w = _win()
        ss = w.status_bar.styleSheet()
        self.assertNotIn("transparent", ss)   # 不透明底才能擦净隐藏标签的残留

    def test_workspace_pages_cover_former_func_entries(self):
        """工作区页面保留原标题栏中的全部功能入口。"""
        w = _win()
        self.assertTrue(hasattr(w, "_workbench_buttons"))
        self.assertEqual(
            set(w._workbench_buttons),
            {"terminal", "protocol", "simulation", "automation", "data", "bridge"})

        def title_keys(key):
            page = w.workspace_stack.widget(w._workspace_page_indexes[key])
            return {
                label.property("tr_text")
                for label in page.findChildren(QLabel, "WorkspaceToolTitle")
            }

        for key in ("fb_title", "frame_open", "tb_title", "mbm_open"):
            self.assertIn(key, title_keys("protocol"))
        for key in ("plot_open", "dash_open", "rd_title"):
            self.assertIn(key, title_keys("data"))
        for key in ("seq_title", "sc_title", "trg_title"):
            self.assertIn(key, title_keys("automation"))
        for key in ("ar_title", "rr_title"):
            self.assertIn(key, title_keys("simulation"))
        self.assertIn("bg_title", title_keys("bridge"))
        self.assertEqual(w.btn_xfer.text(), w._t("xfer_title"))
        self.assertEqual(w.btn_snippets.text(), w._t("snip_title"))
    def test_transient_menu_is_always_released(self):
        """一次性标题栏菜单 exec 返回或抛错后都必须 deleteLater，不能挂在主窗下累积。"""
        class FakeMenu:
            def __init__(self, fail=False):
                self.fail = fail
                self.deleted = False
            def exec_(self, _pos):
                if self.fail:
                    raise ValueError("boom")
                return 7
            def deleteLater(self):
                self.deleted = True

        ok = FakeMenu()
        self.assertEqual(CommTool._exec_transient_menu(ok, None), 7)
        self.assertTrue(ok.deleted)
        bad = FakeMenu(fail=True)
        with self.assertRaises(ValueError):
            CommTool._exec_transient_menu(bad, None)
        self.assertTrue(bad.deleted)

    @staticmethod
    def _seq_pump(ms):
        from PyQt5.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec_()

    def test_sequence_run_pass(self):
        """自动化序列：发送→等回包(匹配)→纯发送 全过 → PASS 汇总；发送内容被真发出。"""
        w = _win()
        sends = []
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]   # 记录发送、恒成功
        w._is_open = lambda: True
        try:
            w._seq_summary = None
            w._seq_start([
                {"on": True, "send": "AT", "expect": "OK", "mode": 0, "timeout": 500, "on_timeout": "stop", "delay": 0},
                {"on": True, "send": "GO", "expect": "", "delay": 0},
            ])
            self.assertTrue(w._seq_running())
            self.assertEqual(w._seq_results[0]["status"], "waiting")
            self.assertIn("AT", sends)
            w.on_data_received(b"junk OK junk")   # 走真实收数据入口 → 序列运行时接管、匹配 step0
            self.assertEqual(w._seq_results[0]["status"], "pass")
            self._seq_pump(120)                    # 让延时/单次定时器推进 step1 + 完成
            self.assertFalse(w._seq_running())
            self.assertIsNotNone(w._seq_summary)
            self.assertTrue(w._seq_summary["pass"])
            self.assertIn("GO", sends)             # 第二步也发出去了
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_timeout_fail(self):
        """期望回包超时（收到不匹配数据）→ 该步失败、on_timeout=stop → 整体 FAIL。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: True
        w._is_open = lambda: True
        try:
            w._seq_summary = None
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "mode": 0,
                           "timeout": 60, "on_timeout": "stop", "delay": 0}])
            w._seq_feed(b"GARBAGE")                # 不含 OK → 不匹配、继续等
            self.assertEqual(w._seq_results[0]["status"], "waiting")
            self._seq_pump(180)                    # 超过 60ms 超时
            self.assertFalse(w._seq_running())
            self.assertFalse(w._seq_summary["pass"])
            self.assertEqual(w._seq_results[0]["status"], "fail")
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_timeout_continue_still_finishes_fail(self):
        """超时选择继续只推进后续步骤；只要有失败步骤，最终汇总仍必须是 FAIL。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: True
        w._is_open = lambda: True
        try:
            w._seq_start([
                {"on": True, "send": "AT", "expect": "OK", "timeout": 30,
                 "on_timeout": "continue", "delay": 0},
                {"on": True, "send": "GO", "expect": "", "delay": 0},
            ])
            self._seq_pump(400)
            self.assertFalse(w._seq_running())
            self.assertEqual(w._seq_results[0]["status"], "fail")
            self.assertEqual(w._seq_results[1]["status"], "sent")
            self.assertFalse(w._seq_summary["pass"])
            self.assertEqual(w._seq_summary["ok"], 1)
            self.assertEqual(w._seq_summary["total"], 2)
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_pauses_modbus_and_cancels_delayed_autoreply(self):
        """序列运行时 Modbus 不再活跃，且开始前排程的延迟自动应答不会穿插发送。"""
        w = _win()
        sends = []
        o_send, o_open, o_ar_on = w._send_text, w._is_open, w._ar_on
        o_mbm_on, o_mbm_rules = w._mbm_on, w._mbm_rules
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]
        w._is_open = lambda: True
        w._ar_on = True
        w._mbm_on = True
        w._mbm_rules = [{"enabled": True}]
        try:
            w._ar_schedule_send(["OLD"], False, 0, [], (50, 50))
            w._seq_start([{"on": True, "send": "AT", "expect": "NEVER", "timeout": 500}])
            self.assertFalse(w._mbm_active())
            self._seq_pump(120)
            self.assertIn("AT", sends)
            self.assertNotIn("OLD", sends)
        finally:
            w._seq_stop()
            w._send_text, w._is_open, w._ar_on = o_send, o_open, o_ar_on
            w._mbm_on, w._mbm_rules = o_mbm_on, o_mbm_rules

    def test_sequence_loop_runs_all_rounds(self):
        """循环 N 轮：整条序列跑 N 遍，聚合汇总 loops/rounds/rounds_pass/累计步 正确，报告出按轮次表。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        sends = []
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]
        w._is_open = lambda: True
        try:
            w._seq_start([{"on": True, "send": "GO", "expect": "", "delay": 0}], loops=3)
            self._seq_pump(200)
            self.assertFalse(w._seq_running())
            s = w._seq_summary
            self.assertEqual((s["loops"], s["rounds"], s["rounds_pass"]), (3, 3, 3))
            self.assertEqual((s["ok"], s["total"]), (3, 3))    # 1 纯发送步 × 3 轮
            self.assertTrue(s["pass"])
            self.assertEqual(sends.count("GO"), 3)             # 每轮发一次
            self.assertEqual(len(s["round_list"]), 3)
            # 报告：循环时出按轮次表
            from dialogs import SequenceDialog
            dlg = SequenceDialog(w)
            try:
                self.assertTrue(dlg._report_is_loop())
                html = dlg._build_report_html(dlg._report_rows(w._seq_steps, w._seq_results))
                self.assertIn(w._t("seq_report_round"), html)
                self.assertEqual(html.count("<tr"), 1 + 3)     # 表头 + 3 轮
            finally:
                dlg._save_timer.stop()
                dlg.deleteLater()
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_loop_stops_on_fail(self):
        """失败即停：某轮失败 → 不再跑后续循环，只记录已跑的轮。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: True
        w._is_open = lambda: True
        try:
            w._seq_start([{"on": True, "send": "AT", "expect": "NEVER", "mode": 0,
                           "timeout": 30, "on_timeout": "stop", "delay": 0}],
                         loops=5, stop_on_fail=True)
            self._seq_pump(250)
            self.assertFalse(w._seq_running())
            s = w._seq_summary
            self.assertEqual(s["loops"], 5)
            self.assertEqual(s["rounds"], 1)          # 第一轮就失败 → 停，只跑了 1 轮
            self.assertEqual(s["rounds_pass"], 0)
            self.assertFalse(s["pass"])
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_loop_input_validation(self):
        """循环次数非法(0/空)→ 纠正为 1 并 toast 提示，不静默；合法值不动也不提示。"""
        from dialogs import SequenceDialog
        w = _win()
        o_rules, o_toast = w._seq_rules, w.toast
        toasts = []
        w.toast = lambda msg, **k: toasts.append(msg)
        dlg = None
        try:
            w._seq_rules = []
            dlg = SequenceDialog(w)
            dlg.reload_rows()
            dlg.ed_loops.setText("0")
            dlg._save_loop_cfg()
            self.assertEqual(dlg.ed_loops.text(), "1")     # 非法 → 纠正为 1
            self.assertTrue(toasts)                        # 且有提示
            toasts.clear()
            dlg.ed_loops.setText("5")
            dlg._save_loop_cfg()
            self.assertEqual(dlg.ed_loops.text(), "5")     # 合法值不动
            self.assertFalse(toasts)                       # 合法不提示
            # _on_run 也回写实际生效值：清空后点运行，框应显示 1（不留空白与真实 loops 不符）
            dlg.ed_loops.setText("")
            dlg._on_run()                                  # 空步骤/未连接会被 _seq_start 拒，但回写已先发生
            self.assertEqual(dlg.ed_loops.text(), "1")
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w.toast, w._seq_rules = o_toast, o_rules

    def test_sequence_loop_abort_builds_exportable_summary(self):
        """回归(P1)：循环运行中停止/断连，已完成轮次要生成汇总(stopped=True)，让老化结果可导出。"""
        w = _win()
        o_summary, o_rounds = getattr(w, "_seq_summary", None), getattr(w, "_seq_rounds", [])
        try:
            w._seq_on = True
            w._seq_steps = [{"on": True, "send": "GO", "expect": ""}]
            w._seq_loops = 5
            w._seq_t0 = 0.0
            w._seq_idx = 0
            w._seq_results = [{"status": "sent", "ms": 0, "detail": ""}]
            w._seq_rounds = [{"round": 1, "ok": 1, "total": 1, "ms": 5, "pass": True},
                             {"round": 2, "ok": 1, "total": 1, "ms": 5, "pass": True}]
            w._seq_summary = None
            w._seq_abort("seq_stopped")
            s = w._seq_summary
            self.assertIsNotNone(s)                        # 有汇总 → 导出按钮不被禁用
            self.assertEqual((s["loops"], s["rounds"], s["rounds_pass"]), (5, 2, 2))
            self.assertTrue(s["stopped"])
            self.assertFalse(s["pass"])                    # 中止一律非 PASS
        finally:
            w._seq_on = False
            w._seq_summary, w._seq_rounds = o_summary, o_rounds

    def test_sequence_abort_after_round_snapshot_does_not_duplicate_round(self):
        w = _win()
        old_summary, old_rounds = getattr(w, "_seq_summary", None), getattr(w, "_seq_rounds", [])
        try:
            w._seq_on = True
            w._seq_steps = [{"on": True, "send": "GO", "expect": ""}]
            w._seq_loops = 3
            w._seq_loop_i = 1
            w._seq_t0 = 0.0
            w._seq_results = [{"status": "sent", "ms": 5, "detail": ""}]
            w._seq_rounds = [{"round": 1, "ok": 1, "total": 1, "ms": 5, "pass": True}]
            w._seq_round_snapshot_taken = True
            w._seq_summary = None
            w._seq_abort("seq_stopped")
            assert len(w._seq_summary["round_list"]) == 1
        finally:
            w._seq_on = False
            w._seq_summary, w._seq_rounds = old_summary, old_rounds

    def test_sequence_loop_summary_shows_planned_when_partial(self):
        """回归(P2)：提前停止(失败即停/中途停)时汇总标出计划总轮数，避免"0/1"被误读；跑满不标。"""
        from dialogs import SequenceDialog
        w = _win()
        dlg = None
        try:
            dlg = SequenceDialog(w)
            partial = {"loops": 5, "rounds": 1, "rounds_pass": 0, "ok": 0, "total": 1, "ms": 20}
            txt = dlg._loop_summary_text(partial, w._t("seq_fail"))
            self.assertIn(w._t("seq_rounds_partial", rp=0, rt=1, loops=5), txt)
            full = {"loops": 3, "rounds": 3, "rounds_pass": 3, "ok": 6, "total": 6, "ms": 30}
            txt2 = dlg._loop_summary_text(full, w._t("seq_pass"))
            self.assertIn(w._t("seq_rounds_frac", rp=3, rt=3), txt2)
            self.assertNotIn(w._t("seq_rounds_partial", rp=3, rt=3, loops=3), txt2)
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()

    def test_sequence_loop_count_capped(self):
        """回归(P2)：循环次数钳到上限 _SEQ_MAX_LOOPS，防无界内存/巨表。"""
        import main_window
        w = _win()
        o_open, o_send = w._is_open, w._send_text
        w._is_open = lambda: True
        w._send_text = lambda raw, **k: True
        try:
            w._seq_start([{"on": True, "send": "GO", "expect": ""}], loops=99999999)
            self.assertEqual(w._seq_loops, main_window._SEQ_MAX_LOOPS)
        finally:
            w._seq_stop()
            w._is_open, w._send_text = o_open, o_send

    def test_sequence_loop_config_keys_in_cfg(self):
        """回归(P2)：循环参数键加入 _CFG_KEYS，会话配置导出/导入不丢。"""
        from main_window import CommTool
        self.assertIn("sequence_loops", CommTool._CFG_KEYS)
        self.assertIn("sequence_stop_on_fail", CommTool._CFG_KEYS)

    def test_sequence_step_retry_passes_on_second(self):
        """步骤级重试：首次超时→重试，第2次收到匹配→通过，标记 attempt=2。
        用手动触发超时(而非等真实计时器)避免墙钟竞态导致多触发一次。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: True
        w._is_open = lambda: True
        try:
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "mode": 0,
                           "timeout": 5000, "retry": 2, "delay": 40}])  # 重试间隔用于校验总耗时
            self.assertEqual(w._seq_results[0]["status"], "waiting")
            w._seq_on_timeout()                   # 手动触发首次超时 → 进入重试
            self._seq_pump(70)                    # 等 40ms 间隔后进入第2次尝试
            self.assertEqual(w._seq_results[0]["status"], "waiting")
            self.assertEqual(w._seq_attempt, 2)
            w.on_data_received(b"OK")             # 第2次收到匹配 → 通过
            self._seq_pump(70)                    # 成功后仍有本步 delay，等待整体收尾
            r = w._seq_results[0]
            self.assertEqual(r["status"], "pass")
            self.assertEqual(r.get("attempt"), 2)
            self.assertGreaterEqual(r["ms"], 50)  # 含重试间隔；若只算第2次尝试会明显小于此值
            self.assertTrue(w._seq_summary["pass"])
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_step_retry_exhausted_fails(self):
        """重试用尽仍不匹配 → 该步失败(按超时动作走)，attempt 记为总尝试次数。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: True
        w._is_open = lambda: True
        try:
            w._seq_start([{"on": True, "send": "AT", "expect": "NEVER", "mode": 0,
                           "timeout": 25, "retry": 1, "on_timeout": "stop", "delay": 0}])
            self._seq_pump(220)                   # 首次+1重试都超时 → 失败
            self.assertFalse(w._seq_running())
            self.assertEqual(w._seq_results[0]["status"], "fail")
            self.assertEqual(w._seq_results[0].get("attempt"), 2)   # 共尝试 2 次
            self.assertFalse(w._seq_summary["pass"])
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_retry_quarantines_late_response(self):
        """首次超时后的迟到响应不得命中第2次尝试；安静窗后才真正重发。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        sends = []
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]
        w._is_open = lambda: True
        try:
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "timeout": 5000,
                           "retry": 1, "delay": 0}])
            w._seq_on_timeout()
            self.assertEqual(w._seq_results[0]["status"], "retry")
            w._seq_feed(b"OK")                    # 旧尝试迟到响应：只延长隔离窗
            w._seq_retry(w._seq_gen, w._seq_idx, w._seq_attempt)  # 强制早到回调也不得重发
            self.assertEqual(w._seq_results[0]["status"], "retry")
            self._seq_pump(100)
            self.assertEqual(w._seq_results[0]["status"], "waiting")
            self.assertEqual(len(sends), 2)
            w._seq_feed(b"OK")                    # 真正重发后的响应才能命中
            self._seq_pump(20)
            self.assertEqual(w._seq_results[0]["status"], "pass")
            self.assertEqual(w._seq_results[0].get("attempt"), 2)
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_retry_quiet_wait_is_bounded(self):
        """回归：重试静默窗有上限——对端持续 <50ms 刷数据也不会让该步永远卡在「↻ 重试」；
        超过 _SEQ_RETRY_MAX_QUIET_MS 后照常重发。"""
        import time as _t
        import main_window
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        o_cap = main_window._SEQ_RETRY_MAX_QUIET_MS
        sends = []
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]
        w._is_open = lambda: True
        main_window._SEQ_RETRY_MAX_QUIET_MS = 60      # 缩短上限便于测试
        try:
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "timeout": 5000,
                           "retry": 1, "delay": 0}])
            w._seq_on_timeout()                       # 首次超时 → 进入重试
            self.assertEqual(w._seq_results[0]["status"], "retry")
            # 持续刷迟到字节(每 <50ms 一次)本应无限延后静默窗；但有上限，最终仍重发
            deadline = _t.monotonic() + 1.5
            while w._seq_results[0]["status"] == "retry" and _t.monotonic() < deadline:
                w._seq_feed(b"x")                     # 迟到字节：延长静默窗
                self._seq_pump(15)
            self.assertEqual(w._seq_results[0]["status"], "waiting")   # 上限到了 → 已重发
            self.assertEqual(len(sends), 2)           # 首发 + 重发
            self.assertEqual(w._seq_attempt, 2)
        finally:
            main_window._SEQ_RETRY_MAX_QUIET_MS = o_cap
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_abort_during_retry_marks_stopped(self):
        """回归：重试延迟窗口(status=retry)被停止/断连 → 标记 stopped 且保留 attempt，
        不会卡在「↻ 第N次…」。"""
        w = _win()
        o_summary, o_rounds = getattr(w, "_seq_summary", None), getattr(w, "_seq_rounds", [])
        try:
            w._seq_on = True
            w._seq_steps = [{"on": True, "send": "AT", "expect": "OK"}]
            w._seq_idx = 0
            w._seq_step_total_t0 = 0.0
            w._seq_rounds = []
            w._seq_summary = None
            w._seq_results = [{"status": "retry", "ms": 0, "detail": "",
                               "detail_key": "seq_st_fail", "attempt": 2}]
            w._seq_abort("seq_stopped")
            r = w._seq_results[0]
            self.assertEqual(r["status"], "stopped")   # 重试中被停 → 已停止
            self.assertEqual(r.get("attempt"), 2)       # 保留尝试次数
        finally:
            w._seq_on = False
            w._seq_summary, w._seq_rounds = o_summary, o_rounds

    def test_sequence_steps_json_roundtrip(self):
        """步骤导入/导出：真实 JSON 文件 → 文件选择/确认 → 应用，并清掉旧结果。"""
        import json, tempfile
        from unittest.mock import patch
        from dialogs import SequenceDialog
        w = _win()
        o_rules = w._seq_rules
        o_results = getattr(w, "_seq_results", [])
        o_summary = getattr(w, "_seq_summary", None)
        o_confirm = w._confirm_dlg
        dlg = None
        path = ""
        try:
            w._seq_rules = [{"on": True, "name": "握手", "send": "AT", "expect": "OK", "retry": 2,
                             "mode": 0, "timeout": 500},
                            {"on": True, "name": "读", "send": "01 03", "expect": "01 03",
                             "send_hex": True, "expect_hex": True}]
            dlg = SequenceDialog(w)
            dlg.reload_rows()
            data = json.loads(json.dumps(dlg._all_steps(), ensure_ascii=False))  # 导出再读回
            with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8",
                                             delete=False) as f:
                json.dump(data, f, ensure_ascii=False)
                path = f.name
            w._seq_results = [{"status": "pass", "ms": 1, "detail": ""}]
            w._seq_summary = {"ok": 1, "total": 1, "ms": 1, "pass": True}
            w._confirm_dlg = lambda *a, **k: True
            with patch("dialogs.QFileDialog.getOpenFileName", return_value=(path, "JSON (*.json)")):
                dlg._import_steps()
            got = dlg._all_steps()
            self.assertEqual([s["name"] for s in got], ["握手", "读"])
            self.assertEqual(got[0]["retry"], 2)
            self.assertTrue(got[1]["send_hex"])
            self.assertEqual(w._seq_results, [])
            self.assertIsNone(w._seq_summary)
            self.assertIsNone(dlg._validate_import_steps([]))
            self.assertIsNone(dlg._validate_import_steps([{"retry": 1000}]))
            self.assertIsNone(dlg._validate_import_steps([{}] * 501))
            self.assertIsNone(dlg._validate_import_steps([{"on": "false"}]))
            self.assertIsNone(dlg._validate_import_steps([{"send_hex": "false"}]))
            self.assertIsNone(dlg._validate_import_steps([{"mode": 99}]))
            dlg._rows[0]["to"].setText(str(2 ** 40))
            dlg._rows[0]["dl"].setText(str(2 ** 40))
            clamped = dlg._row_to_step(dlg._rows[0])
            self.assertLessEqual(clamped["timeout"], dlg._MAX_TIMER_MS)
            self.assertLessEqual(clamped["delay"], dlg._MAX_TIMER_MS)
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._seq_rules = o_rules
            w._seq_results, w._seq_summary = o_results, o_summary
            w._confirm_dlg = o_confirm
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            w.settings.setValue("sequence_rules", json.dumps(o_rules, ensure_ascii=False))

    def test_sequence_needs_connection(self):
        """未连接时运行序列被拒（不进入运行态）。"""
        w = _win()
        o_open = w._is_open
        w._is_open = lambda: False
        try:
            w._seq_on = False
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "timeout": 100}])
            self.assertFalse(w._seq_running())
        finally:
            w._is_open = o_open

    def test_sequence_dialog_smoke(self):
        """序列对话框：构造 + 加行 + 读回步骤 + 重译/主题/结果刷新，均不抛异常。"""
        from dialogs import SequenceDialog
        w = _win()
        o_rules = w._seq_rules
        dlg = None
        try:
            dlg = SequenceDialog(w)
            dlg.reload_rows()
            dlg._add_row({"on": True, "send": "AT", "expect": "OK", "mode": 0,
                          "timeout": 300, "on_timeout": "continue", "delay": 10})
            steps = dlg._all_steps()
            self.assertTrue(any(s["send"] == "AT" and s["expect"] == "OK" for s in steps))
            got = next(s for s in steps if s["send"] == "AT")
            self.assertEqual(got["on_timeout"], "continue")
            self.assertEqual(got["timeout"], 300)
            dlg.retranslate()
            dlg.refresh_theme()
            dlg.update_results()
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._seq_rules = o_rules   # 还原（对话框 _add_row 未落盘，但保险）

    def test_sequence_dialog_columns_draggable_and_persist(self):
        """只有发送/期望两数据框可拖：表头与每行都是 2 面板(左组/右组) splitter，拖动同步且列宽持久化。"""
        from dialogs import SequenceDialog
        w = _win()
        o_rules = w._seq_rules
        dlg = None
        try:
            dlg = SequenceDialog(w)
            dlg.reload_rows()
            dlg._add_row({"on": True, "send": "AT", "expect": "OK"})
            self.assertEqual(dlg._hdr_split.count(), 2)      # 左组 / 右组两面板
            row = dlg._rows[-1]
            self.assertIn("split", row)
            self.assertEqual(row["split"].count(), 2)
            # 模拟拖动表头分隔条 → 同步到行 + 持久化
            sizes = [s + 12 for s in dlg._hdr_split.sizes()]
            dlg._hdr_split.setSizes(sizes)
            dlg._sync_splits(dlg._hdr_split)
            self.assertEqual(row["split"].sizes(), dlg._hdr_split.sizes())
            self.assertTrue(w.settings.value("sequence_split"))
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._seq_rules = o_rules

    def test_sequence_dialog_delete_then_pump_no_crash(self):
        """回归（崩溃根因）：对话框 deleteLater 后，构造期/滚动条 rangeChanged 排的 singleShot
        仍会触发；若回调对已析构的 splitter 调 sizes()/setSizes() 会因 PyQt 槽内异常 abort 硬崩溃。
        删除后泵事件循环，不得崩溃。"""
        from dialogs import SequenceDialog
        from PyQt5.QtWidgets import QApplication
        w = _win()
        o_rules = w._seq_rules
        try:
            dlg = SequenceDialog(w)
            dlg.reload_rows()
            dlg._add_row({"on": True, "send": "AT", "expect": "OK"})
            dlg._save_timer.stop()
            dlg.deleteLater()
            del dlg
            for _ in range(4):        # 触发所有挂起的 singleShot(0)（含 _update_header_scroll_margin 链）
                QApplication.instance().processEvents()
            self.assertTrue(True)     # 走到这里=没崩
        finally:
            w._seq_rules = o_rules

    def test_sequence_stop_keeps_results(self):
        """回归：运行中点「停止」不能清空已跑结果；当前等回包的步应标记为 stopped 而非一直 waiting。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: True
        w._is_open = lambda: True
        try:
            w._seq_start([
                {"on": True, "send": "AT", "expect": "OK", "mode": 0, "timeout": 5000, "delay": 0},
                {"on": True, "send": "GO", "expect": "OK2", "timeout": 5000, "delay": 0},
            ])
            w.on_data_received(b"OK")              # step0 通过
            self.assertEqual(w._seq_results[0]["status"], "pass")
            self._seq_pump(60)                     # 单次定时器推进到 step1 → 等回包
            self.assertEqual(w._seq_results[1]["status"], "waiting")
            w._seq_stop()
            self.assertFalse(w._seq_running())
            self.assertEqual(w._seq_results[0]["status"], "pass")     # 已跑结果保留
            self.assertEqual(w._seq_results[1]["status"], "stopped")  # 等回包步标记已停止
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_disconnect_aborts_and_keeps_results(self):
        """回归：运行中连接断开 → 序列中止但保留已跑结果，当前等回包步标记 stopped。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: True
        w._is_open = lambda: True
        try:
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "timeout": 5000, "delay": 0}])
            self.assertEqual(w._seq_results[0]["status"], "waiting")
            w._is_open = lambda: False
            w.close_conn()                          # 断开 → 触发 _seq_abort
            self.assertFalse(w._seq_running())
            self.assertEqual(w._seq_results[0]["status"], "stopped")
        finally:
            w._seq_on = False
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_skips_empty_enabled_step(self):
        """回归：启用但发送与期望都为空的步骤应被跳过（skip），不误判「已发送」也不发数据。"""
        w = _win()
        sends = []
        o_send, o_open = w._send_text, w._is_open
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]
        w._is_open = lambda: True
        try:
            w._seq_start([
                {"on": True, "send": "", "expect": "", "delay": 0},        # 空步骤 → 跳过
                {"on": True, "send": "GO", "expect": "", "delay": 0},
            ])
            self._seq_pump(120)
            self.assertFalse(w._seq_running())
            self.assertEqual(w._seq_results[0]["status"], "skip")
            self.assertEqual(w._seq_results[1]["status"], "sent")
            self.assertNotIn("", sends)             # 空步骤没发出空串
            self.assertIn("GO", sends)
            # 关键回归：启用的空步骤=skip 不算失败(整体仍 PASS)，也不被计入「通过 X/Y」
            self.assertTrue(w._seq_summary["pass"])
            self.assertEqual(w._seq_summary["ok"], 1)      # 只有真正执行的 sent 步计入
            self.assertEqual(w._seq_summary["total"], 1)   # skip 步不计入 total
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_isolates_inflight_modbus_response(self):
        """启动时有在途 Modbus-TCP 请求：先由 Modbus 收完，随后才发送序列第 0 步。"""
        w = _win()
        o_send, o_open, o_inflight = w._send_text, w._is_open, w._mbm_inflight
        o_guard = w._mbm_guard_until
        sends = []
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]
        w._is_open = lambda: True
        try:
            w._mbm_inflight = {"i": 0, "variant": "tcp", "tid": 1, "unit": 1,
                               "func": 0x03, "qty": 1, "addr": 0, "exp_write": None,
                               "timeout_ms": 1000}
            w._mbm_to.start(1000)
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "mode": 0,
                           "timeout": 5000, "delay": 0}])
            self.assertTrue(w._seq_running())
            self.assertTrue(w._seq_waiting_mbm)
            self.assertNotIn("AT", sends)        # 在途请求未完成前不发送序列
            w.on_data_received(bytes.fromhex("0001000000050103021234"))
            self.assertFalse(w._seq_waiting_mbm) # Modbus 响应完成 → 立即启动 step0
            self.assertIn("AT", sends)
            self.assertEqual(w._seq_results[0]["status"], "waiting")
            w.on_data_received(b"OK")           # 真正的回包 → 通过
            self.assertEqual(w._seq_results[0]["status"], "pass")
        finally:
            w._seq_stop()
            w._mbm_to.stop()
            w._mbm_inflight = o_inflight
            w._mbm_guard_until = o_guard
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_waits_through_modbus_rtu_late_guard(self):
        """在途 RTU 请求超时后，序列须等完整迟到响应隔离期结束，不能在名义超时点立即启动。"""
        w = _win()
        o_send, o_open, o_inflight = w._send_text, w._is_open, w._mbm_inflight
        o_guard = w._mbm_guard_until
        sends = []
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]
        w._is_open = lambda: True
        try:
            w._mbm_inflight = {"i": 0, "variant": "rtu", "timeout_ms": 80}
            w._mbm_to.start(30)
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "timeout": 5000}])
            w._mbm_on_timeout()                  # 名义超时 → 再进入至少 80ms 迟到隔离
            self.assertTrue(w._seq_waiting_mbm)
            self.assertNotIn("AT", sends)
            w.on_data_received(b"late")         # 隔离期字节只用于延长排空，不喂给序列
            self.assertNotIn("AT", sends)
            self._seq_pump(140)
            self.assertFalse(w._seq_waiting_mbm)
            self.assertIn("AT", sends)
            self.assertEqual(w._seq_results[0]["status"], "waiting")
        finally:
            w._seq_stop()
            w._mbm_to.stop()
            w._mbm_inflight = o_inflight
            w._mbm_guard_until = o_guard
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_waits_through_modbus_tcp_late_guard(self):
        """TCP 虽可用 TID 防轮询误配，但序列无 TID；在途请求超时后也须隔离迟到响应。"""
        w = _win()
        o_send, o_open, o_inflight = w._send_text, w._is_open, w._mbm_inflight
        sends = []
        w._send_text = lambda raw, **k: (sends.append(raw), True)[1]
        w._is_open = lambda: True
        try:
            w._mbm_inflight = {"i": 0, "variant": "tcp", "timeout_ms": 80}
            w._mbm_to.start(30)
            w._seq_start([{"on": True, "send": "AT", "expect": "OK", "timeout": 5000}])
            w._mbm_on_timeout()
            self.assertTrue(w._seq_waiting_mbm)
            self.assertNotIn("AT", sends)
            w.on_data_received(b"late tcp response")
            self.assertNotIn("AT", sends)
            self._seq_pump(120)
            self.assertFalse(w._seq_waiting_mbm)
            self.assertIn("AT", sends)
        finally:
            w._seq_stop()
            w._mbm_to.stop()
            w._mbm_inflight = o_inflight
            w._send_text, w._is_open = o_send, o_open

    def test_sequence_dialog_clears_stale_results_on_edit(self):
        """非运行态编辑步骤 → 清掉上次运行的结果/汇总，避免旧「通过/失败」赖在改过的步骤上或删行后错位。"""
        from dialogs import SequenceDialog
        w = _win()
        o_rules = w._seq_rules
        o_results = getattr(w, "_seq_results", [])
        o_summary = getattr(w, "_seq_summary", None)
        dlg = None
        try:
            w._seq_rules = []
            dlg = SequenceDialog(w)
            dlg.reload_rows()                 # 空规则 → 1 行空模板
            w._seq_results = [{"status": "pass", "ms": 5, "detail": ""}]   # 伪造上次运行结果
            w._seq_summary = {"ok": 1, "total": 1, "ms": 5, "pass": True}
            dlg.update_results()
            self.assertIn("✓", dlg._rows[0]["res"].text())
            dlg._rows[0]["send"].setText("ATZ")   # 非运行态编辑 → textChanged → _schedule → 清结果
            self.assertEqual(w._seq_results, [])
            self.assertIsNone(w._seq_summary)
            self.assertEqual(dlg._rows[0]["res"].text(), w._t("seq_st_pending"))
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._seq_rules, w._seq_results, w._seq_summary = o_rules, o_results, o_summary

    def test_sequence_dialog_export_report(self):
        """导出测试报告：跑完(有结果)才可导出；HTML 含标题/步骤/结果/HEX 标记/失败底色，CSV 含表头与各步。"""
        from dialogs import SequenceDialog
        w = _win()
        o_rules = w._seq_rules
        o_steps = getattr(w, "_seq_steps", [])
        o_results = getattr(w, "_seq_results", [])
        o_summary = getattr(w, "_seq_summary", None)
        o_started_at = getattr(w, "_seq_started_at", "")
        dlg = None
        try:
            w._seq_rules = []
            dlg = SequenceDialog(w)
            dlg.reload_rows()
            w._seq_results = []
            dlg.update_results()
            self.assertFalse(dlg.btn_export.isEnabled())     # 无结果 → 不可导出
            # 伪造一次运行快照 + 结果 + 汇总
            w._seq_steps = [{"on": True, "name": "握手", "send": "AT", "expect": "OK", "mode": 0,
                             "cs": 5, "timeout": 1000},
                            {"on": True, "name": "读值", "send": "01 03", "expect": "01 03",
                             "mode": 2, "send_hex": True, "expect_hex": True, "timeout": 500}]
            w._seq_results = [{"status": "pass", "ms": 12, "detail": ""},
                              {"status": "fail", "ms": 500, "detail": "超时",
                               "detail_key": "seq_st_fail"}]
            w._seq_summary = None
            dlg.update_results()
            self.assertFalse(dlg.btn_export.isEnabled())      # 停止/断连的部分结果无汇总 → 不可导出
            w._seq_summary = {"ok": 1, "total": 2, "ms": 520, "pass": False}
            w._seq_started_at = "2026-07-04 21:15:30"
            dlg.update_results()
            self.assertTrue(dlg.btn_export.isEnabled())       # 有结果 → 可导出
            rows = dlg._report_rows(w._seq_steps, w._seq_results)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["status"], w._t("seq_report_fail"))
            self.assertEqual(rows[1]["detail"], w._t("seq_st_fail"))
            html = dlg._build_report_html(rows)
            self.assertIn(w._t("seq_report_title"), html)
            self.assertIn("握手", html)
            self.assertIn("(HEX)", html)                      # HEX 步骤标注
            self.assertIn('tr class="fail"', html)            # 失败步骤底色
            self.assertIn("2026-07-04 21:15:30", html)        # 测试时间
            csv = dlg._build_report_csv(rows)
            self.assertIn(w._t("seq_report_time"), csv)
            self.assertIn("握手", csv)
            self.assertIn(w._t("seq_col_result"), csv)        # 表头
            self.assertEqual(dlg._csv_safe("=2+2"), "'=2+2")
            self.assertEqual(dlg._csv_safe("  @cmd"), "'  @cmd")
            self.assertEqual(dlg._csv_safe("\tcmd"), "'\tcmd")
            self.assertEqual(dlg._csv_safe("normal"), "normal")
            # 格式判定：扩展名优先；无扩展名时按选中过滤器补扩展名（跨平台防错）
            self.assertEqual(dlg._report_fmt("a.csv", "HTML (*.html)"), ("csv", "a.csv"))
            self.assertEqual(dlg._report_fmt("a.html", "CSV (*.csv)"), ("html", "a.html"))
            self.assertEqual(dlg._report_fmt("rep", "CSV (*.csv)"), ("csv", "rep.csv"))
            self.assertEqual(dlg._report_fmt("rep", "HTML (*.html)"), ("html", "rep.html"))
            self.assertEqual(dlg._report_fmt("a.xml", "HTML (*.html)"), ("junit", "a.xml"))
            self.assertEqual(dlg._report_fmt("rep", "JUnit XML (*.xml)"), ("junit", "rep.xml"))
            w._seq_finished_at = "2026-07-04 21:15:31"
            w._seq_summary = {"ok": 1, "total": 2, "ms": 520, "pass": False,
                              "loops": 1, "step_count": 2, "version": "1.3.6",
                              "started_at": "2026-07-04 21:15:30",
                              "finished_at": "2026-07-04 21:15:31"}
            junit = dlg._build_report_junit([])
            self.assertIn("testsuite", junit)
            self.assertIn("failure", junit)
            self.assertIn("1.3.6", junit)
            html = dlg._build_report_html(rows)
            self.assertIn("1.3.6", html)
            self.assertIn("2026-07-04 21:15:31", html)
            # 无汇总数据不当作通过（独立安全默认）
            w._seq_summary = None
            self.assertEqual(dlg._report_summary_line(), ("", False))
            self.assertNotIn("class='verdict'", dlg._build_report_html(rows))
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._seq_rules, w._seq_steps = o_rules, o_steps
            w._seq_results, w._seq_summary = o_results, o_summary
            w._seq_started_at = o_started_at

    def test_sequence_dialog_locks_editing_while_running(self):
        """回归(P2)：运行中只锁「结构性改动」(增行/删行)防结果按索引错位；步骤字段/勾选框不锁
        (改字段不影响在跑快照，且禁用勾选框会丢选中蓝色像被取消)。运行按钮变绿、结束后恢复。"""
        from dialogs import SequenceDialog
        w = _win()
        o_rules, o_running = w._seq_rules, w._seq_running
        dlg = None
        try:
            dlg = SequenceDialog(w)
            dlg.reload_rows()
            dlg._add_row({"on": True, "send": "AT", "expect": "OK"})
            row = dlg._rows[-1]
            w._seq_running = lambda: True       # 模拟运行态
            dlg.update_results()
            self.assertFalse(dlg.btn_add.isEnabled())      # 结构性改动锁住
            self.assertFalse(row["del"].isEnabled())
            self.assertTrue(row["send"].isEnabled())       # 字段/勾选框不锁、不变灰
            self.assertTrue(row["on"].isEnabled())
            self.assertFalse(dlg.btn_run.isEnabled())      # 运行中：运行按钮禁用
            self.assertIn("background-color", dlg.btn_run.styleSheet())  # 且点亮成绿色作运行指示
            w._seq_running = lambda: False      # 结束 → 恢复
            dlg.update_results()
            self.assertTrue(dlg.btn_add.isEnabled())
            self.assertTrue(row["del"].isEnabled())
            self.assertEqual(dlg.btn_run.styleSheet(), "")  # 空闲：回落普通灰(无内联样式)
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._seq_running = o_running
            w._seq_rules = o_rules

    def test_sequence_send_exception_is_fail_not_hang(self):
        """回归：_send_text 抛异常时该步判失败并按 on_timeout 走，不能卡在等回包。"""
        w = _win()
        o_send, o_open = w._send_text, w._is_open
        def _boom(raw, **k):
            raise RuntimeError("send blew up")
        w._send_text = _boom
        w._is_open = lambda: True
        try:
            w._seq_start([{"on": True, "send": "AT", "expect": "OK",
                           "timeout": 5000, "on_timeout": "stop", "delay": 0}])
            self.assertFalse(w._seq_running())      # 异常即失败 → stop → 立即结束，不进等回包
            self.assertEqual(w._seq_results[0]["status"], "fail")
            self.assertFalse(w._seq_summary["pass"])
        finally:
            w._seq_stop()
            w._send_text, w._is_open = o_send, o_open

    def test_recv_scroll_pinned_when_selected_and_scrolled_up(self):
        """回归：数据区有选区且往上翻看时，来新数据不得把视图拽到选区/底部——恢复选区的 setTextCursor
        会滚到选区，必须显式钉回原滚动位置；贴底时仍应跟随最新。"""
        from PyQt5.QtCore import QEventLoop, QTimer
        from PyQt5.QtGui import QTextCursor
        w = _win()
        te = w.txt_recv
        o_groups, o_active = w._keyword_groups, w._keyword_active

        def pump(ms):
            loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec_()
        try:
            w.resize(900, 600); w.show(); pump(10)
            w._keyword_groups = [{"name": "t", "rules": [
                {"pattern": "ERR", "color": "#FFD60A", "mode": "bg", "scope": "both", "enabled": True}]}]
            w._keyword_active = 0
            te.clear()
            for i in range(300):
                w._append_block_data("line %d ERR\n" % i, "rx", True)
            pump(200)
            sb = te.verticalScrollBar()
            if sb.maximum() <= 100:
                self.skipTest("offscreen Qt does not compute QTextDocument scroll extent")
            self.assertGreater(sb.maximum(), 100)     # 确有可滚空间
            c = QTextCursor(te.document())
            c.setPosition(400); c.setPosition(460, QTextCursor.KeepAnchor)
            te.setTextCursor(c)                       # 选中中间一段
            sb.setValue(0)                            # 用户滚到顶
            pump(10)
            w._append_block_data("NEW ERR\n", "rx", True)   # 来新数据
            pump(220)                                 # 含 150ms 高亮重扫
            self.assertEqual(sb.value(), 0)           # 视图仍钉在顶（修前会跳到选区/底）
            sb.setValue(sb.maximum())                 # 贴底则应跟随
            pump(10)
            w._append_block_data("BOTTOM ERR\n", "rx", True)
            self.assertEqual(sb.value(), sb.maximum())
        finally:
            w._kw_timer.stop()
            w._keyword_groups, w._keyword_active = o_groups, o_active
            te.clear()
            w.hide()

    def test_binproto_pack_field(self):
        """帧构造器打包：数值大小端 / 有符号 / ascii / hex / float / 溢出与坏 hex 报错。"""
        import binproto
        self.assertEqual(binproto.pack_field("0x03", "u8"), b"\x03")
        self.assertEqual(binproto.pack_field("258", "u16be"), b"\x01\x02")
        self.assertEqual(binproto.pack_field("258", "u16le"), b"\x02\x01")  # 大小端相反
        self.assertEqual(binproto.pack_field("-1", "i8"), b"\xff")
        self.assertEqual(binproto.pack_field("AT", "ascii"), b"AT")
        self.assertEqual(binproto.pack_field("01 03", "hex"), b"\x01\x03")
        self.assertEqual(binproto.pack_field("1.0", "f32le"), b"\x00\x00\x80\x3f")
        with self.assertRaises(ValueError):
            binproto.pack_field("999", "u8")        # u8 溢出
        with self.assertRaises(ValueError):
            binproto.pack_field("1e39", "f32le")    # f32 有限值溢出也统一成 ValueError
        with self.assertRaises(ValueError):
            binproto.pack_field("zz", "hex")        # 坏 hex

    def test_binproto_build_frame(self):
        """帧构造器拼帧：Modbus 读帧交叉核对 build_rtu_request；length 字段=其后字节数。"""
        import binproto, modbus_master
        from main_window import CommTool
        modbus = [("num", "u8", 1), ("num", "u8", 3), ("num", "u16be", 0),
                  ("num", "u16be", 1), ("checksum", 5, "")]
        self.assertEqual(binproto.build_frame(modbus, CommTool.compute_checksum),
                         modbus_master.build_rtu_request(1, 3, 0, 1))   # CRC 交叉核对
        lenf = [("num", "u8", "0xAA"), ("length", "u8", ""), ("hex", "hex", "11 22 33")]
        self.assertEqual(binproto.build_frame(lenf, CommTool.compute_checksum),
                         b"\xAA\x03\x11\x22\x33")     # 长度字节=后续 3 字节
        with self.assertRaisesRegex(ValueError, "preceding data"):
            binproto.build_frame([("checksum", 5, "")], CommTool.compute_checksum)
        with self.assertRaisesRegex(ValueError, "checksum algorithm"):   # typ=0(无校验) → 显式报错，不静默 0 字节
            binproto.build_frame([("num", "u8", 1), ("checksum", 0, "")], CommTool.compute_checksum)
        # kind/typ 必须配套，防导入的坏配置静默改变发送语义；长度仅支持 UI 暴露的两种编码。
        for bad in ([('ascii', 'u8', '65')], [('num', 'ascii', '65')],
                    [('hex', 'u8', 'AA')], [('length', 'f32le', '')]):
            with self.subTest(fields=bad), self.assertRaises(ValueError):
                binproto.build_frame(bad, CommTool.compute_checksum)

    def test_convert_byte_sequences(self):
        """工具箱：字节序列 HEX / 文本 / 十进制 / 二进制 互转 + 非法输入报错。"""
        import convert as C
        self.assertEqual(C.hex_to_bytes("01 41 FF"), b"\x01\x41\xff")
        self.assertEqual(C.hex_to_bytes("0141ff"), b"\x01\x41\xff")
        self.assertEqual(C.bytes_to_hex(b"\x01\x41\xff"), "01 41 FF")
        self.assertEqual(C.text_to_bytes("AB"), b"AB")
        self.assertEqual(C.bytes_to_text(b"AB"), "AB")
        self.assertEqual(C.bytes_to_text(b"\xff"), "\\xff")          # 不可解码字节 → 转义
        self.assertEqual(C.dec_to_bytes("1 65 255"), b"\x01\x41\xff")
        self.assertEqual(C.bytes_to_dec(b"\x01\x41\xff"), "1 65 255")
        self.assertEqual(C.bin_to_bytes("00000001 01000001"), b"\x01\x41")
        self.assertEqual(C.bytes_to_bin(b"\x01\x41"), "00000001 01000001")
        self.assertEqual(C.interpret_bytes(b"\x01\x02AB", "be")["u16"], "258")
        self.assertEqual(C.interpret_bytes(b"\x01\x02AB", "le")["u16"], "513")
        self.assertEqual(C.interpret_bytes(b"\x01\x02AB", "be")["ascii"], "..AB")
        self.assertEqual(C.custom_crc(C.hex_to_bytes("01 03 00 00 00 01"), 16, 0x8005,
                                      0xFFFF, True, True, 0, "little").hex(" ").upper(), "84 0A")
        for fn, bad in [(C.hex_to_bytes, "XY"), (C.hex_to_bytes, "012"),
                        (C.dec_to_bytes, "256"), (C.dec_to_bytes, "-1"),
                        (C.bin_to_bytes, "012"), (C.bin_to_bytes, "111111111")]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                fn(bad)

    def test_convert_single_value(self):
        """工具箱：单值多进制转换（位宽 + 有无符号；负数按补码落进位宽）。"""
        import convert as C
        self.assertEqual(C.parse_value("255", "dec", 8), 255)
        self.assertEqual(C.parse_value("FF", "hex", 8), 255)
        self.assertEqual(C.parse_value("11111111", "bin", 8), 255)
        self.assertEqual(C.parse_value("-1", "dec", 8), 255)         # 补码落进 8 位
        self.assertEqual(C.parse_value("-1", "dec", 16), 0xFFFF)
        self.assertEqual(C.format_value(255, 8, False),
                         {"dec": "255", "hex": "FF", "bin": "11111111", "oct": "377"})
        self.assertEqual(C.format_value(255, 8, True)["dec"], "-1")  # 有符号解读
        self.assertEqual(C.format_value(0x1234, 16, False),
                         {"dec": "4660", "hex": "1234", "bin": "0001001000110100", "oct": "11064"})
        self.assertEqual(C.parse_bits("0, 3 7", 8), 0x89)
        self.assertEqual(C.bits_from_value(0x89, 8), "0, 3, 7")
        for base, s in [("hex", "GG"), ("dec", ""), ("bin", "2"),
                        ("dec", "256"), ("hex", "100"), ("bin", "100000000")]:
            with self.subTest(s=s), self.assertRaises(ValueError):
                C.parse_value(s, base, 8)
        with self.assertRaises(ValueError):
            C.parse_bits("8", 8)

    def test_convert_custom_crc(self):
        """通用 CRC（Rocksoft 参数）拿多个已知标准值核对 + 交叉核对主程序 compute_checksum。"""
        import convert as C
        from main_window import CommTool
        d = b"123456789"
        self.assertEqual(C.custom_crc(d, 16, 0x8005, 0xFFFF, True, True, 0, "big").hex().upper(), "4B37")   # CRC-16/MODBUS
        self.assertEqual(C.custom_crc(d, 16, 0x1021, 0xFFFF, False, False, 0, "big").hex().upper(), "29B1") # CCITT-FALSE
        self.assertEqual(C.custom_crc(d, 16, 0x1021, 0x0000, False, False, 0, "big").hex().upper(), "31C3") # XMODEM
        self.assertEqual(C.custom_crc(d, 8, 0x07, 0x00, False, False, 0, "big").hex().upper(), "F4")        # CRC-8/SMBus
        # MODBUS（小端字节序）== 主程序 compute_checksum 的 ModbusCRC16
        self.assertEqual(C.custom_crc(d, 16, 0x8005, 0xFFFF, True, True, 0, "little").hex(" ").upper(),
                         CommTool.compute_checksum(d, 5).hex(" ").upper())

    def test_toolbox_dialog(self):
        """工具箱对话框：字节序列互转同步、单值进制(位宽/符号)、校验计算(ModbusCRC16 交叉核对)、菜单入口。"""
        from toolbox_dialog import ToolboxDialog
        from PyQt5.QtWidgets import QMenu
        w = _win()
        dlg = None
        try:
            dlg = ToolboxDialog(w)
            # 字节序列：编辑 HEX → 其余实时同步
            dlg._seq["hex"][1].setText("41 42 FF")
            dlg._on_seq_edit("hex")
            self.assertEqual(dlg._seq["dec"][1].text(), "65 66 255")
            self.assertEqual(dlg._seq["text"][1].text(), "AB\\xff")          # 不可解码字节转义
            self.assertEqual(dlg._seq["bin"][1].text(), "01000001 01000010 11111111")
            self.assertEqual(dlg._interp["ascii"][1].text(), "AB.")
            self.assertEqual(dlg._interp["u16"][1].text(), str(0x4142))
            # 单值进制（8 位）：编辑 HEX FF → dec 255；勾有符号 → -1
            dlg.cb_width.setCurrentText("8")
            dlg._val["hex"][1].setText("FF")
            dlg._on_val_edit("hex")
            self.assertEqual(dlg._val["dec"][1].text(), "255")
            self.assertEqual(dlg._val["bin"][1].text(), "11111111")
            self.assertEqual(dlg.ed_bits.text(), "0, 1, 2, 3, 4, 5, 6, 7")
            dlg.chk_signed.setChecked(True)
            self.assertEqual(dlg._val["dec"][1].text(), "-1")
            dlg.ed_bits.setText("0, 3, 7")
            dlg._on_bits_edit()
            self.assertEqual(dlg._val["hex"][1].text(), "89")
            # 校验：ModbusCRC16(01 03 00 00 00 01) == 84 0A（同 Modbus 读帧尾 CRC）
            dlg.ed_ck_in.setText("01 03 00 00 00 01")
            crc = [res.text() for idx, _n, res in dlg._ck_rows if idx == 5]
            self.assertEqual(crc, ["84 0A"])
            self.assertEqual(dlg.ed_crc_result.text(), "84 0A")
            # 协议工作区页面含「工具箱」入口
            self.assertIn("tb_title", {item[0] for item in w._workspace_specs("protocol")})
        finally:
            if dlg is not None:
                dlg.deleteLater()

    def test_serial_control_lines(self):
        """串口控制线：DTR/RTS 开关调 conn.set_dtr/set_rts + 持久化；轮询按 read_lines 刷状态灯；复位先拉低 DTR；仅串口+已连接时显示。"""
        from main_window import PROTO_SERIAL
        w = _win()
        rec = {"dtr": [], "rts": []}
        class _Mock:
            def set_dtr(s, on): rec["dtr"].append(on)
            def set_rts(s, on): rec["rts"].append(on)
            def read_lines(s): return {"cts": True, "dsr": False, "dcd": True, "ri": True}
        o_conn, o_proto, o_idx = w.conn, w._conn_proto, w.cb_proto.currentIndex()
        try:
            w.conn = _Mock(); w._conn_proto = PROTO_SERIAL
            # 开关 → 调 conn.set_dtr/set_rts + 落到设置
            w._on_dtr_toggled(False)
            self.assertEqual(rec["dtr"], [False])
            self.assertEqual(str(w.settings.value("serial_dtr")).lower(), "false")
            w._on_rts_toggled(True)
            self.assertEqual(rec["rts"], [True])
            # 轮询 → 状态灯颜色随 read_lines：有效(True)→绿、无效(False)→非绿
            # dcd 特别校验：读的是 pyserial 的 cd 属性、灯键是 dcd，两侧键名须对齐（否则永不亮）
            w._poll_ctrl_lines()
            self.assertIn("2ecc71", w._ctrl_dots["cts"].styleSheet().lower())
            self.assertIn("2ecc71", w._ctrl_dots["dcd"].styleSheet().lower())
            self.assertNotIn("2ecc71", w._ctrl_dots["dsr"].styleSheet().lower())
            # 复位脉冲：立即拉低 DTR（随后定时器恢复，此处只验证起始沿）
            rec["dtr"].clear()
            w.sw_dtr.blockSignals(True); w.sw_dtr.setChecked(True); w.sw_dtr.blockSignals(False)
            w._pulse_reset()
            self.assertEqual(rec["dtr"], [False])
            # 释放恢复到「开关当前状态」而非硬置高：脉冲期间用户把 DTR 关掉 → 释放应恢复为 False（尊重用户、不覆盖）
            rec["dtr"].clear()
            w.sw_dtr.blockSignals(True); w.sw_dtr.setChecked(False); w.sw_dtr.blockSignals(False)
            w._pulse_reset_release()
            self.assertEqual(rec["dtr"], [False])
            # 开关为高时释放恢复为高（正常空闲态）
            rec["dtr"].clear()
            w.sw_dtr.blockSignals(True); w.sw_dtr.setChecked(True); w.sw_dtr.blockSignals(False)
            w._pulse_reset_release()
            self.assertEqual(rec["dtr"], [True])
            # 显隐：串口 + 已连接 → 显示；断开 → 隐藏
            self.assertIn(PROTO_SERIAL, [w.cb_proto.itemText(i) for i in range(w.cb_proto.count())])
            w.conn = _Mock(); w.cb_proto.setCurrentText(PROTO_SERIAL)
            w._update_net_fields()
            self.assertFalse(w.box_ctrl.isHidden())
            w.conn = None
            w._update_net_fields()
            self.assertTrue(w.box_ctrl.isHidden())
        finally:
            w.conn, w._conn_proto = o_conn, o_proto
            w.cb_proto.setCurrentIndex(o_idx)
            if hasattr(w, "_ctrl_poll_timer"): w._ctrl_poll_timer.stop()
            if getattr(w, "_reset_timer", None): w._reset_timer.stop()

    def test_serial_break_and_flow(self):
        """Break 走 conn.send_break；流控下拉 RTS/CTS 禁用手动 RTS；SerialConn 存 flow 参数。"""
        from main_window import PROTO_SERIAL
        import serial_io
        w = _win()
        rec = {"break": 0}
        class _Mock:
            def send_break(s, d=0.25): rec["break"] += 1
        o_conn, o_proto = w.conn, w._conn_proto
        try:
            w.conn = _Mock(); w._conn_proto = PROTO_SERIAL
            w._send_break()
            self.assertEqual(rec["break"], 1)                     # Break 走 conn.send_break
            w.cb_flow.setCurrentText("RTS/CTS")
            self.assertFalse(w.sw_rts.isEnabled())                # 硬件流控 → 禁用手动 RTS
            w.cb_flow.setCurrentText("None")
            self.assertTrue(w.sw_rts.isEnabled())
        finally:
            w.conn, w._conn_proto = o_conn, o_proto
            w.cb_flow.setCurrentText("None")
        sc = serial_io.SerialConn("COMx", 9600, 8, "N", 1, flow="rtscts")
        self.assertEqual(sc._flow, "rtscts")                      # 流控参数落到 SerialConn

    def test_port_label_format(self):
        """端口标签 = '设备名  系统描述  [芯片型号]'；型号已在描述内不重复，认不出芯片/无描述时降级。"""
        import serial_io
        # _chip_ident：精确型号 / 厂商退路 / 认不出 / 虚拟口
        self.assertEqual(serial_io._chip_ident(0x0403, 0x6001), "FT232R")   # 精确
        self.assertEqual(serial_io._chip_ident(0x1A86, 0x9999), "WCH")      # 未收录 pid→厂商
        self.assertEqual(serial_io._chip_ident(0xFFFF, 0x0000), "")         # 全未知
        self.assertEqual(serial_io._chip_ident(None, None), "")             # 虚拟/蓝牙口

        class _P:
            def __init__(s, dev, desc, vid=None, pid=None):
                s.device, s.description, s.vid, s.pid = dev, desc, vid, pid
        import serial.tools.list_ports as _LP
        orig = _LP.comports
        _LP.comports = lambda: [
            _P("COM29", "USB Serial Port", 0x0403, 0x6001),        # 泛化描述→补型号 FT232R
            _P("COM3", "USB-SERIAL CH340 (COM3)", 0x1A86, 0x7523),  # 描述已含 CH340→不重复
            _P("COM2", "JLink CDC UART Port (COM2)", 0x1366, 0x0105),  # 未收录→只留描述
            _P("COM1", "通信端口 (COM1)"),                          # 无 vid→只留描述
            _P("COM9", ""),                                         # 无描述、无 vid→只显示设备名
        ]
        try:
            labels = dict(serial_io._scan_ports())
        finally:
            _LP.comports = orig
        self.assertEqual(labels["COM29"], "COM29  USB Serial Port  FT232R")  # 补型号
        self.assertEqual(labels["COM3"], "COM3  USB-SERIAL CH340")           # 型号不重复
        self.assertEqual(labels["COM2"], "COM2  JLink CDC UART Port")        # 认不出→只描述
        self.assertEqual(labels["COM1"], "COM1  通信端口")
        self.assertEqual(labels["COM9"], "COM9")                             # 只设备名

    def test_xfer_worker_loopback(self):
        """两个真实 XferWorker(QThread) 经 sig_send↔feed 直连对拼：验证线程 + 信号桥端到端收发一致。"""
        import xfer
        from xfer_dialog import XferWorker
        from PyQt5.QtCore import Qt
        _win()   # 确保 QApplication 存在
        for mode in (xfer.MODE_XMODEM_CRC, xfer.MODE_YMODEM):
            payload = bytes((i * 5 + 1) & 0xFF for i in range(2500))
            snd = XferWorker("send", mode, payload=payload, name="fw.bin")
            rcv = XferWorker("recv", mode)
            snd.sig_send.connect(rcv.feed, Qt.DirectConnection)   # 直连：跨线程即时投递（feed 仅线程安全 put）
            rcv.sig_send.connect(snd.feed, Qt.DirectConnection)
            box = {}
            rcv.sig_done.connect(lambda ok, msg, res: box.update(ok=ok, res=res), Qt.DirectConnection)
            rcv.start(); snd.start()
            snd.wait(15000); rcv.wait(15000)
            self.assertTrue(box.get("ok"), "%s: recv not ok" % mode)
            data, meta = box["res"]
            if mode == xfer.MODE_YMODEM:
                self.assertEqual(data, payload)
                self.assertEqual(meta.get("size"), len(payload))
                self.assertEqual(meta.get("name"), "fw.bin")
            else:
                self.assertEqual(data.rstrip(bytes([xfer.SUB])), payload.rstrip(bytes([xfer.SUB])))

    def test_xfer_raw_send(self):
        """原始字节流：XferWorker raw 模式按 chunk 分块 sig_send、逐字节拼回等于原文、末块为余数；takes_input=False。"""
        from xfer_dialog import XferWorker, MODE_RAW
        from PyQt5.QtCore import Qt
        _win()   # 确保 QApplication 存在
        payload = bytes((i * 3 + 1) & 0xFF for i in range(5000))
        sent, chunks, box = bytearray(), [], {}
        wk = XferWorker("send", MODE_RAW, payload=payload, chunk=1024, delay=0)
        self.assertFalse(wk.takes_input)                          # raw 只发不收、不接管收流
        wk.sig_send.connect(lambda b: (sent.extend(b), chunks.append(len(b))), Qt.DirectConnection)
        wk.sig_done.connect(lambda ok, msg, r: box.update(ok=ok), Qt.DirectConnection)
        wk.start(); wk.wait(5000)
        self.assertTrue(box.get("ok"))
        self.assertEqual(bytes(sent), payload)                    # 全部字节按序发出
        self.assertEqual(chunks, [1024, 1024, 1024, 1024, 904])   # 5000 = 4×1024 + 904

    def test_xfer_raw_keeps_recv_disabled_after_busy(self):
        """原始字节流只支持发送：忙碌状态恢复后也不能把接收单选框重新启用。"""
        from xfer_dialog import XferDialog, MODE_RAW
        w = _win()
        dlg = XferDialog(w)
        try:
            for i in range(dlg.cb_proto.count()):
                if dlg.cb_proto.itemData(i) == MODE_RAW:
                    dlg.cb_proto.setCurrentIndex(i)
                    break
            self.assertTrue(dlg.rb_send.isChecked())
            self.assertFalse(dlg.rb_recv.isEnabled())
            dlg._set_busy(True)
            self.assertFalse(dlg.rb_recv.isEnabled())
            dlg._set_busy(False)
            self.assertTrue(dlg.rb_send.isChecked())
            self.assertFalse(dlg.rb_recv.isEnabled())
        finally:
            dlg.close()

    def test_xfer_proto_change_preserves_send_path(self):
        """发送方向切换协议不应清空已选文件；只有切到 raw 导致方向变化时才清路径。"""
        import xfer
        from xfer_dialog import XferDialog, MODE_RAW
        w = _win()
        dlg = XferDialog(w)
        try:
            dlg.rb_send.setChecked(True)
            dlg._path = r"C:\tmp\fw.bin"
            dlg.ed_path.setText(dlg._path)
            for i in range(dlg.cb_proto.count()):
                if dlg.cb_proto.itemData(i) == xfer.MODE_YMODEM:
                    dlg.cb_proto.setCurrentIndex(i)
                    break
            self.assertEqual(dlg._path, r"C:\tmp\fw.bin")
            self.assertEqual(dlg.ed_path.text(), r"C:\tmp\fw.bin")

            dlg.rb_recv.setChecked(True)
            dlg._path = r"C:\tmp\recv.bin"
            dlg.ed_path.setText(dlg._path)
            for i in range(dlg.cb_proto.count()):
                if dlg.cb_proto.itemData(i) == MODE_RAW:
                    dlg.cb_proto.setCurrentIndex(i)
                    break
            self.assertTrue(dlg.rb_send.isChecked())
            self.assertEqual(dlg._path, "")
            self.assertEqual(dlg.ed_path.text(), "")
        finally:
            dlg.close()

    def test_xfer_refuses_periodic_or_modbus_traffic(self):
        """文件传输接管原始收流前，必须排除定时发送及 Modbus 主机/在途响应。"""
        from xfer_dialog import XferDialog
        w = _win()
        dlg = XferDialog(w)
        old = (w._is_open, w.toast, w._mbm_active, w._mbm_inflight)
        notices = []
        try:
            w._is_open = lambda: True
            w.toast = lambda msg, **kwargs: notices.append(msg)
            w.send_timer.start(60000)
            dlg._start()
            self.assertIsNone(dlg._worker)
            w.send_timer.stop()
            w._mbm_active = lambda: True
            dlg._start()
            self.assertIsNone(dlg._worker)
            self.assertGreaterEqual(len(notices), 2)
        finally:
            w.send_timer.stop()
            w._is_open, w.toast, w._mbm_active, w._mbm_inflight = old
            dlg.close()

    def test_xfer_bridge_takeover(self):
        """主窗桥接：传输中 on_data_received 把收流喂 worker、不进正常显示；worker 发字节经 sig_send→conn.send；detach 后复原。"""
        from PyQt5.QtCore import QObject, pyqtSignal
        w = _win()

        class _FakeWorker(QObject):
            sig_send = pyqtSignal(bytes)
            def __init__(s): super().__init__(); s.fed = bytearray(); s._run = True; s.takes_input = True
            def isRunning(s): return s._run
            def feed(s, d): s.fed.extend(d)

        class _MockConn:
            def __init__(s): s.sent = []
            def send(s, data, target=None): s.sent.append((bytes(data), target)); return len(data)

        fake, mock = _FakeWorker(), _MockConn()
        o_conn, o_worker = w.conn, w._xfer_worker
        o_rx, o_pkt = w.rx_bytes, w.rx_packets
        try:
            w.conn = mock
            w._xfer_attach(fake)
            self.assertIs(w._xfer_worker, fake)
            # 传输中：收到的数据喂 worker，且不计入正常接收统计（未走显示路径）
            w.on_data_received(b"\x01\x02\x03")
            self.assertEqual(bytes(fake.fed), b"\x01\x02\x03")
            self.assertEqual(w.rx_bytes, o_rx)
            # worker 要发的字节经桥回到 conn.send
            fake.sig_send.emit(b"ACK")
            self.assertEqual(mock.sent[-1][0], b"ACK")
            # raw worker（takes_input=False）：收流不喂给它，但仍被吞掉、不进正常显示
            fake.takes_input = False
            fed_before = bytes(fake.fed)
            w.on_data_received(b"\x09\x09")
            self.assertEqual(bytes(fake.fed), fed_before)     # raw 不喂
            self.assertEqual(w.rx_bytes, o_rx)                # 仍吞掉、不计入正常接收
            fake.takes_input = True
            # attach 第二个 worker 应先断开第一个的发送桥：旧 worker 再 emit 不应再到 conn（防两个 worker 同发）
            fake2 = _FakeWorker()
            w._xfer_attach(fake2)
            self.assertIs(w._xfer_worker, fake2)
            before = len(mock.sent)
            fake.sig_send.emit(b"STALE")
            self.assertEqual(len(mock.sent), before)          # 旧桥已断，STALE 未发出
            fake2.sig_send.emit(b"NEW")
            self.assertEqual(mock.sent[-1][0], b"NEW")        # 新桥正常
            # detach 后恢复正常收流
            w._xfer_detach()
            self.assertIsNone(w._xfer_worker)
            w.on_data_received(b"hello")
            self.assertGreater(w.rx_bytes, o_rx)
        finally:
            w._xfer_detach()
            w.conn, w._xfer_worker = o_conn, o_worker
            w.rx_bytes, w.rx_packets = o_rx, o_pkt

    def test_hexdump_view(self):
        """HEX dump 视图：_format_hexdump 三列格式（偏移 / HEX 分两半 / ASCII、短行补齐对齐、多行偏移、空串）；RX 开启时渲染转储。"""
        w = _win()
        line = w._format_hexdump(b"Hello World\r\n\x01\x02\x03")     # 16 字节整行
        self.assertEqual(line, "00000000  48 65 6C 6C 6F 20 57 6F  72 6C 64 0D 0A 01 02 03 |Hello World.....|")
        short = w._format_hexdump(b"AB")                             # 短行补齐 → ASCII 列与整行同列对齐
        self.assertTrue(short.startswith("00000000  41 42"))
        self.assertTrue(short.endswith("|AB|"))
        self.assertEqual(short.index("|"), line.index("|"))
        two = w._format_hexdump(bytes(range(17)))                    # 17 字节 → 两行，次行偏移 00000010
        self.assertEqual(len(two.split("\n")), 2)
        self.assertTrue(two.split("\n")[1].startswith("00000010  10 "))
        self.assertEqual(w._format_hexdump(b""), "")
        # 每行字节数可变：per=8 → 每行 8 字节、中缝在第 4 字节后；per=32 → 32 字节一行
        rows8 = w._format_hexdump(bytes(range(20)), per=8).split("\n")
        self.assertEqual(len(rows8), 3)                             # 20 / 8 = 3 行
        self.assertTrue(rows8[1].startswith("00000008  08 09 0A 0B  0C 0D 0E 0F |"))
        self.assertEqual(len(w._format_hexdump(bytes(range(32)), per=32).split("\n")), 1)
        # 下拉驱动 _hexdump_block 的每行字节数
        o_w = w.cb_hexdump_width.currentText()
        try:
            w.cb_hexdump_width.setCurrentText("8")
            self.assertEqual(len(w._hexdump_block(bytes(range(16))).lstrip("\n").split("\n")), 2)  # 16/8=2
        finally:
            w.cb_hexdump_width.setCurrentText(o_w)
        o_hd = w._hexdump_on
        try:
            w._hexdump_on = True; w._reset_recv_state()              # RX 渲染：开 hexdump → 出现偏移 + ASCII 列
            w._on_data_received_impl(b"\x00\x01\x02ABC")
            txt = w.txt_recv.toPlainText()
            self.assertIn("00000000  00 01 02 41 42 43", txt)
            self.assertIn("|...ABC|", txt)
        finally:
            w._hexdump_on = o_hd
            w._reset_recv_state()

    def test_hexdump_toggle_disables_hex_display(self):
        """HEX dump 开启接管 HEX 显示 → 灰掉 HEX 显示开关（明确优先级）；关闭后恢复（非终端模式）。"""
        w = _win()
        o_hd, o_term = w.sw_hexdump.isChecked(), w._terminal_on
        try:
            if o_term:
                w._set_terminal_enabled(False)
            # 合并成「显示方式」下拉后：开转储不是把 HEX 显示灰掉，而是真的切走那个模式，
            # 且下拉显示要跟着状态走（三个开关退居幕后当状态源）。
            w.sw_hexdump.setChecked(False)
            w._refresh_hex_toggle_state()
            self.assertNotEqual(w.cb_view_mode.currentData(), "dump")
            w.sw_hexdump.setChecked(True)
            self.assertEqual(w.cb_view_mode.currentData(), "dump")
            w.sw_hexdump.setChecked(False)
            self.assertNotEqual(w.cb_view_mode.currentData(), "dump")
        finally:
            w.sw_hexdump.setChecked(o_hd)
            if o_term:
                w._set_terminal_enabled(True)

    def test_hexdump_filter_multiblock(self):
        """多行 hexdump 块 + 只显高亮行：每一行立即按关键字定可见性（不只最后一行）；
        时间戳开启时纯装饰 prefix 行不受过滤影响（不会被误隐藏）。"""
        w = _win()
        o_hd, o_rules, o_flt = w._hexdump_on, w._active_rules, w.btn_filter_hl.isChecked()
        o_ts = w.sw_show_timestamp.isChecked()
        try:
            # ---- 场景 A：时间戳关，测多行 hexdump 逐行过滤 ----
            w._hexdump_on = True
            w.sw_show_timestamp.setChecked(False)
            w.btn_filter_hl.setChecked(True)
            w._active_rules = lambda: [{"pattern": "ABC", "enabled": True, "scope": "both"}]
            w.txt_recv.clear(); w._reset_recv_state()
            # 32 字节 → 两行：首行(0x00..0x0F)无 "ABC"、次行含 "ABC"
            w._on_data_received_impl(bytes(range(16)) + b"ABC" + bytes(13))
            doc = w.txt_recv.document(); vis = {}
            blk = doc.begin()
            while blk.isValid():
                t = blk.text()
                if t.startswith("00000000"): vis["row1"] = blk.isVisible()
                if t.startswith("00000010"): vis["row2"] = blk.isVisible()
                blk = blk.next()
            self.assertEqual(vis.get("row1"), False, "A-首行无关键字应立即隐藏")
            self.assertEqual(vis.get("row2"), True, "A-次行含关键字应可见")

            # ---- 场景 B：时间戳开，纯装饰 prefix 行不受过滤影响 ----
            w.sw_show_timestamp.setChecked(True)
            w.txt_recv.clear(); w._reset_recv_state()
            # 同一数据；timestamp ON 时 _hexdump_block 在 dump 前插 \n → prefix 独占一个 block
            w._on_data_received_impl(bytes(range(16)) + b"ABC" + bytes(13))
            doc = w.txt_recv.document(); vis.clear()
            blk = doc.begin()
            while blk.isValid():
                t = blk.text()
                if "ABC" in t and t.startswith("00000010"):
                    vis["row2_abc"] = blk.isVisible()          # 含关键字 → 可见
                if t.startswith("00000000"):
                    vis["row1"] = blk.isVisible()              # 无关键字 → 隐藏
                if t.startswith("[") and "←" in t:
                    vis["ts"] = blk.isVisible()                # 纯装饰 prefix → 不受过滤
                blk = blk.next()
            self.assertEqual(vis.get("row1"), False, "B-首行无关键字应隐藏")
            self.assertEqual(vis.get("row2_abc"), True, "B-次行含关键字应可见")
            self.assertTrue(vis.get("ts"), "B-时间戳 prefix 应始终可见（不被过滤误隐藏）")
            # 触发异步重扫（150ms 的同款逻辑）：装饰行须仍可见——否则时间戳先闪后消失（即时修了、重扫又隐藏）
            w._refresh_extra_selections(rebuild_search=True)
            def _vis(pred):
                b = doc.begin()
                while b.isValid():
                    if pred(b.text()):
                        return b.isVisible()
                    b = b.next()
                return None
            self.assertTrue(_vis(lambda t: t.startswith("[") and "←" in t), "B-重扫后时间戳行仍应可见")
            self.assertTrue(_vis(lambda t: t.startswith("00000010") and "ABC" in t), "B-重扫后命中行仍可见")
            self.assertEqual(_vis(lambda t: t.startswith("00000000")), False, "B-重扫后无关键字行仍隐藏")
        finally:
            w._hexdump_on = o_hd
            w._active_rules = o_rules
            w.btn_filter_hl.setChecked(o_flt)
            w.sw_show_timestamp.setChecked(o_ts)
            w.txt_recv.clear(); w._reset_recv_state()

    def test_frame_builder_dialog(self):
        """帧构造器对话框：默认模板出正确 HEX、填入发送框置 HEX 态、发送走 _send_text、坏字段禁用按钮。"""
        from frame_builder_dialog import FrameBuilderDialog
        w = _win()
        o_send, o_toast, o_hex = w._send_text, w.toast, w.sw_tx_hex.isChecked()
        o_nl, o_cs = w.sw_append_newline.isChecked(), w.cb_checksum.currentIndex()
        o_txt = w.txt_send.toPlainText()
        o_fields = w.settings.value("frame_builder_fields", "")
        sent = []
        w._send_text = lambda raw, **k: (sent.append((raw, k)), True)[1]
        dlg = None
        try:
            w.settings.remove("frame_builder_fields")
            dlg = FrameBuilderDialog(w)
            dlg.reload_rows()                    # 空 → 默认 Modbus 读模板
            hexs, err = dlg._built_hex()
            self.assertIsNone(err)
            self.assertEqual(hexs, "01 03 00 00 00 01 84 0A")
            w.sw_append_newline.setChecked(True)
            w.cb_checksum.setCurrentIndex(3)
            dlg._on_fill()
            self.assertEqual(w.txt_send.toPlainText(), "01 03 00 00 00 01 84 0A")
            self.assertTrue(w.sw_tx_hex.isChecked())   # 填入自动开 HEX 发送
            self.assertTrue(w.sw_append_newline.isChecked())    # 不得篡改用户的全局发送设置
            self.assertEqual(w.cb_checksum.currentIndex(), 3)
            dlg._on_send()
            self.assertEqual(sent, [("01 03 00 00 00 01 84 0A",
                                     {"hex_mode": True, "newline": 0, "checksum": 0})])
            notices = []
            w._send_text = lambda *_a, **_k: False
            w.toast = lambda *a, **k: notices.append((a, k))
            dlg._on_send()
            self.assertEqual(notices, [])             # _send_text 已报告具体失败原因，不再覆盖成通用提示
            dlg._rows[0]["val"].setText("999")   # u8 溢出 → 有错误、发送/填入禁用
            dlg._rebuild()
            _h, e = dlg._built_hex()
            self.assertIsNotNone(e)
            self.assertFalse(dlg.btn_send.isEnabled())
            self.assertIn("border", dlg._rows[0]["val"].styleSheet())
            self.assertEqual(dlg._rows[1]["val"].styleSheet(), "")
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._send_text = o_send
            w.toast = o_toast
            w.sw_tx_hex.setChecked(o_hex)
            w.sw_append_newline.setChecked(o_nl)
            w.cb_checksum.setCurrentIndex(o_cs)
            w.txt_send.setPlainText(o_txt)
            w.settings.setValue("frame_builder_fields", o_fields)

    def test_frame_builder_reopen_keeps_saved_fields(self):
        """回归：单实例对话框关闭/重开时，不得用构造时的旧快照覆盖刚保存的字段。"""
        import json
        from frame_builder_dialog import FrameBuilderDialog
        w = _win()
        o_fields = w.settings.value("frame_builder_fields", "")
        dlg = None
        try:
            w.settings.remove("frame_builder_fields")
            dlg = FrameBuilderDialog(w)
            dlg._rows[0]["val"].setText("7")
            dlg.reload_rows()                         # 模拟主窗再次打开单实例对话框
            self.assertEqual(dlg._rows[0]["val"].text(), "7")
            saved = json.loads(w.settings.value("frame_builder_fields", "[]"))
            self.assertEqual(saved[0][2], "7")
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w.settings.setValue("frame_builder_fields", o_fields)

    def test_frame_builder_external_config_discards_old_pending_edit(self):
        """回归：导入/切换配置后，旧槽位的防抖草稿不得覆盖新配置。"""
        import json
        from frame_builder_dialog import FrameBuilderDialog
        w = _win()
        o_fields = w.settings.value("frame_builder_fields", "")
        o_dlg = w._frame_builder_dlg
        dlg = None
        try:
            old_cfg = [["num", "u8", "1", "old"]]
            new_cfg = [["num", "u8", "9", "new"]]
            w.settings.setValue("frame_builder_fields", json.dumps(old_cfg))
            dlg = FrameBuilderDialog(w)
            w._frame_builder_dlg = dlg
            dlg._rows[0]["val"].setText("7")
            self.assertTrue(dlg._save_timer.isActive())
            w._save_settings()                        # 切槽前提交到旧 settings
            self.assertFalse(dlg._save_timer.isActive())
            self.assertEqual(json.loads(w.settings.value("frame_builder_fields"))[0][2], "7")

            dlg._rows[0]["val"].setText("8")
            w.settings.setValue("frame_builder_fields", json.dumps(new_cfg))
            w._apply_loaded_settings()                # 导入/切槽后丢弃旧草稿、载入新配置
            self.assertFalse(dlg._save_timer.isActive())
            self.assertEqual(dlg._rows[0]["val"].text(), "9")
            self.assertEqual(json.loads(w.settings.value("frame_builder_fields"))[0][2], "9")
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._frame_builder_dlg = o_dlg
            w.settings.setValue("frame_builder_fields", o_fields)

    def test_frame_builder_load_numeric_zero_and_unknown_type(self):
        """回归：①存成数值 0 的字段值要还原成 "0"（不能被 `x or ""` 吞成空串）；
        ②未知/不支持的类型不得静默降级成 u8——原样保留、拼帧时报错标红（绝不改变发送字节）。"""
        import json
        from frame_builder_dialog import FrameBuilderDialog
        w = _win()
        o_fields = w.settings.value("frame_builder_fields", "")
        dlg = None
        try:
            cfg = [["num", "u8", 0, "z"],          # 数值 0（JSON 数字，非字符串）
                   ["num", "u64le", "1", "bad"]]   # u64le 不在类型表里
            w.settings.setValue("frame_builder_fields", json.dumps(cfg))
            dlg = FrameBuilderDialog(w)
            dlg.reload_rows()
            self.assertEqual(dlg._rows[0]["val"].text(), "0")              # 0 → "0"，非空
            self.assertEqual(dlg._rows[1]["type"].currentData(), ("num", "u64le"))  # 未降级成 u8
            _h, e = dlg._built_hex()
            self.assertIsNotNone(e)                                        # 非静默：拼帧报错
            self.assertEqual(dlg._error_row, 1)
            self.assertFalse(dlg.btn_send.isEnabled())
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w.settings.setValue("frame_builder_fields", o_fields)

    def test_frame_builder_template_apply_confirms(self):
        """回归：套用协议模板会覆盖当前字段 → 先弹确认；取消则字段不动、下拉回到自定义。"""
        from frame_builder_dialog import FrameBuilderDialog, _TEMPLATE_ORDER
        w = _win()
        o_fields = w.settings.value("frame_builder_fields", "")
        o_confirm = w._confirm_dlg
        dlg = None
        try:
            w.settings.remove("frame_builder_fields")
            dlg = FrameBuilderDialog(w)                 # 默认 Modbus 读模板（5 字段）
            before = dlg._all_fields()
            idx_at = _TEMPLATE_ORDER.index("at")
            w._confirm_dlg = lambda *a, **k: False      # 取消
            dlg.cb_tmpl.setCurrentIndex(idx_at)
            dlg._on_template(idx_at)
            self.assertEqual(dlg._all_fields(), before)  # 字段不动
            self.assertEqual(dlg.cb_tmpl.currentIndex(), 0)  # 下拉回自定义
            w._confirm_dlg = lambda *a, **k: True        # 确认 → 套用 AT（2 字段）
            dlg.cb_tmpl.setCurrentIndex(idx_at)
            dlg._on_template(idx_at)
            self.assertEqual([f[:2] for f in dlg._all_fields()],
                             [("ascii", "ascii"), ("hex", "hex")])
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w._confirm_dlg = o_confirm
            w.settings.setValue("frame_builder_fields", o_fields)

    def test_frame_builder_drag_reorder(self):
        """字段行拖拽排序：拖第 0 行落到末尾 → _rows / HEX 顺序随之改变并落盘。"""
        import json
        from frame_builder_dialog import FrameBuilderDialog
        w = _win()
        o_fields = w.settings.value("frame_builder_fields", "")
        dlg = None
        try:
            cfg = [["num", "u8", "0xAA", "a"], ["num", "u8", "0xBB", "b"],
                   ["num", "u8", "0xCC", "c"]]
            w.settings.setValue("frame_builder_fields", json.dumps(cfg))
            dlg = FrameBuilderDialog(w)
            self.assertEqual(dlg._built_hex()[0], "AA BB CC")
            dlg._drag_frame = dlg._rows[0]["frame"]   # 模拟拖第 0 行
            dlg._on_row_drop(10 ** 6)                  # 落点给超大 y → 插到末尾（不依赖控件几何）
            self.assertEqual([r["val"].text() for r in dlg._rows], ["0xBB", "0xCC", "0xAA"])
            self.assertEqual(dlg._built_hex()[0], "BB CC AA")
            dlg._commit()
            self.assertEqual(json.loads(w.settings.value("frame_builder_fields"))[2][2], "0xAA")
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w.settings.setValue("frame_builder_fields", o_fields)

    def test_frame_builder_columns_draggable_and_persist(self):
        """列宽拖拽：表头 + 每行都是 3 面板(名称/类型/值) splitter，拖动同步且列宽持久化。"""
        import json
        from frame_builder_dialog import FrameBuilderDialog
        w = _win()
        o_fields = w.settings.value("frame_builder_fields", "")
        o_split = w.settings.value("frame_builder_split", "")
        o_lang = w._lang
        dlg = None
        try:
            w.settings.remove("frame_builder_fields")
            dlg = FrameBuilderDialog(w)                   # 默认模板 → 有行
            self.assertEqual(dlg._hdr_split.count(), 3)   # 名称 / 类型 / 值 三面板
            row = dlg._rows[-1]
            self.assertIn("split", row)
            self.assertEqual(row["split"].count(), 3)
            sizes = [s + 15 for s in dlg._hdr_split.sizes()]   # 模拟拖表头分隔条
            dlg._hdr_split.setSizes(sizes)
            dlg._sync_splits(dlg._hdr_split)
            self.assertEqual(row["split"].sizes(), dlg._hdr_split.sizes())  # 同步到行
            self.assertTrue(w.settings.value("frame_builder_split"))         # 已落盘
            self.assertIn("frame_builder_split", w._CFG_KEYS)                # 随配置导入/导出

            w.settings.setValue("frame_builder_split", "210,220,230")
            dlg.reload_rows(discard_pending=True)                            # 模拟配置切换
            self.assertEqual(dlg._split_sizes, [210, 220, 230])
            QApplication.instance().processEvents()
            QApplication.instance().processEvents()
            self.assertEqual(dlg._rows[0]["split"].sizes(), dlg._hdr_split.sizes())

            w._lang = "en"
            dlg.retranslate()
            self.assertEqual(dlg._rows[0]["grip"].toolTip(), "Drag to reorder")

            w.settings.setValue("frame_builder_split", "999999999999999999999,1,1")
            self.assertIsNone(dlg._load_split_sizes())                       # 不得传给 Qt C++ int 崩溃

            oversized = [["num", "u8", "1", "x"]] * (dlg._MAX_FIELDS + 1)
            w.settings.setValue("frame_builder_fields", json.dumps(oversized))
            self.assertEqual(len(dlg._load_fields()), dlg._MAX_FIELDS)       # 海量行安全截断
        finally:
            if dlg is not None:
                dlg._save_timer.stop()
                dlg.deleteLater()
            w.settings.setValue("frame_builder_fields", o_fields)
            w.settings.setValue("frame_builder_split", o_split)
            w._lang = o_lang

    def test_frame_builder_delete_then_pump_no_crash(self):
        """回归：对话框 deleteLater 后，构造期/滚动条 rangeChanged 排的 singleShot 仍会触发；
        回调对已析构的 splitter 调 sizes()/setSizes() 须被 RuntimeError 守卫接住，不得崩溃。"""
        from frame_builder_dialog import FrameBuilderDialog
        from PyQt5.QtWidgets import QApplication
        w = _win()
        o_fields = w.settings.value("frame_builder_fields", "")
        try:
            dlg = FrameBuilderDialog(w)
            dlg._save_timer.stop()
            dlg.deleteLater()
            del dlg
            for _ in range(4):        # 触发所有挂起的 singleShot(0)（含 _update_header_scroll_margin 链）
                QApplication.instance().processEvents()
            self.assertTrue(True)     # 走到这里=没崩
        finally:
            w.settings.setValue("frame_builder_fields", o_fields)

    def test_data_tools_moved_to_workspace_pages(self):
        """Plot / frame parse / Modbus master live in workspace pages, not the data toolbar."""
        w = _win()
        self.assertFalse(any(hasattr(w, b) for b in ("btn_plot", "btn_frame", "btn_mbm")))
        data_keys = {item[0] for item in w._workspace_specs("data")}
        protocol_keys = {item[0] for item in w._workspace_specs("protocol")}
        self.assertIn("plot_open", data_keys)
        self.assertIn("frame_open", protocol_keys)
        self.assertIn("mbm_open", protocol_keys)

    def test_profile_lock_does_not_deadlock_qsettings_sync(self):
        """回归（多窗口卡死根因）：配置槽位锁的文件名不能与 QSettings 内部写锁 <ini>.lock 撞名，
        否则同进程 settings.sync() 会与自己已持有的锁死锁——新配置窗口构造时(首次落盘迁移)
        或关窗保存时永久阻塞，表现为『进程在、界面没有』/『关第一个窗口卡死』。
        用带超时的线程跑 sync：撞名→线程永久阻塞→join 超时→done 为空→断言失败。"""
        import main as _main
        import tempfile
        import shutil
        import os as _os
        import threading
        from PyQt5.QtCore import QSettings
        d = tempfile.mkdtemp()
        path_fn = lambda p: _os.path.join(d, "settings.ini" if not p else "settings-%s.ini" % p)
        prof, lock = _main._acquire_profile(path_fn)   # 持有槽位锁（撞名点就在这个 .lock）
        done = []

        def worker():
            s = QSettings(path_fn(prof), QSettings.IniFormat)
            s.setValue("probe", 1)
            s.sync()                 # 撞名时这里会永久阻塞在 QLockFile 上
            done.append(True)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(5.0)
        try:
            self.assertTrue(done, "settings.sync() 卡死——配置槽位锁与 QSettings 的 <ini>.lock 撞名了")
        finally:
            if lock:
                lock.unlock()
            shutil.rmtree(d, ignore_errors=True)

    @staticmethod
    def _titlebar_grabbable(w):
        """标题栏顶部是否有连续 ≥120px 宽、8px 高的一段落在某屏工作区内（= 抓得住、拖得动）。"""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QRect
        fg = w.frameGeometry()
        strip = QRect(fg.left(), fg.top(), fg.width(), 8)
        for s in QApplication.screens():
            it = s.availableGeometry().intersected(strip)
            if it.width() >= 120 and it.height() >= 8:
                return True
        return False

    def test_ensure_on_screen_pulls_offscreen_window_back(self):
        """窗口完全挪到屏幕外时，_ensure_on_screen 把它搬回、标题栏可抓（防'进程在窗口看不见'）。"""
        w = _win()
        old = w.geometry()
        try:
            w.move(-10000, -10000)   # 挪到任何屏幕都够不到的位置
            w._ensure_on_screen()
            self.assertTrue(self._titlebar_grabbable(w))   # 已被搬回且标题栏抓得住
        finally:
            w.setGeometry(old)

    def test_ensure_on_screen_rescues_barely_intersecting_window(self):
        """回归：窗口只剩一条边/一个角相交（intersects()=True 但标题栏已被推出屏）时，
        旧逻辑会误判'可见'而不搬；新逻辑要求标题栏真的露出一段，故应把它搬回抓得住的位置。"""
        from PyQt5.QtWidgets import QApplication
        w = _win()
        old = w.geometry()
        try:
            avail = QApplication.primaryScreen().availableGeometry()
            # 顶到主屏右下角：只有左上极小一块在屏内，标题栏顶部条几乎全被推出右侧
            w.move(avail.right() - 5, avail.bottom() - 5)
            fg = w.frameGeometry()
            # 前提校验：此位置下 intersects() 仍为 True（正是旧逻辑漏判的场景），但标题栏抓不住
            self.assertTrue(any(s.availableGeometry().intersects(fg) for s in QApplication.screens()))
            self.assertFalse(self._titlebar_grabbable(w))
            w._ensure_on_screen()
            self.assertTrue(self._titlebar_grabbable(w))   # 修复后标题栏可抓
        finally:
            w.setGeometry(old)

    def test_settings_file_profile_isolation(self):
        """多窗口配置隔离：主 profile=settings.ini，其余=settings-<N>.ini，同目录不同文件。"""
        import os as _os
        main = CommTool._settings_file("")
        p2 = CommTool._settings_file("2")
        p3 = CommTool._settings_file("3")
        self.assertTrue(main.endswith("settings.ini"))
        self.assertTrue(p2.endswith("settings-2.ini"))
        self.assertTrue(p3.endswith("settings-3.ini"))
        self.assertEqual(len({main, p2, p3}), 3)                       # 三个路径各不相同
        self.assertEqual(_os.path.dirname(main), _os.path.dirname(p2))  # 隔离只体现在文件名、同目录

    def test_terminal_toggle_persists(self):
        """终端模式开关写盘 + 纳入配置导出键。"""
        w = _win()
        old = w._terminal_on
        try:
            w._set_terminal_enabled(True)
            self.assertTrue(w._terminal_on)
            self.assertTrue(w.settings.value("terminal_mode", type=bool))
            self.assertEqual(w.txt_send.property("tr_placeholder"), "term_send_ph")   # 占位同步
            w._set_terminal_enabled(False)
            self.assertFalse(w._terminal_on)
            self.assertFalse(w.settings.value("terminal_mode", type=bool))
            self.assertEqual(w.txt_send.property("tr_placeholder"), "send_placeholder")
            self.assertIn("terminal_mode", w._CFG_KEYS)
        finally:
            w._set_terminal_enabled(old)

    def test_terminal_disables_irrelevant_settings(self):
        """终端模式开启时不生效的显示/发送格式设置变不可配置，关闭后恢复；编码/自动换行不受影响。"""
        w = _win()
        old, old_hd = w._terminal_on, w.sw_hexdump.isChecked()
        try:
            w.sw_hexdump.setChecked(False)   # 控制变量：hexdump 关，专测终端对 HEX 显示等的禁用/恢复
            w._set_terminal_enabled(True)
            # 显示方式合并成下拉后，禁用的是 cb_view_mode（三个开关退居幕后当状态源，
            # 不再出现在界面上，其 isEnabled 已无意义）
            for name in ("cb_view_mode", "cb_hexdump_width", "sw_show_timestamp",
                         "sw_line_split", "sw_tx_hex", "sw_append_newline", "cb_checksum"):
                self.assertFalse(getattr(w, name).isEnabled(), name + " 应不可配置")
            self.assertTrue(w.cb_encoding.isEnabled())   # 编码仍可用
            self.assertTrue(w.sw_wrap.isEnabled())       # 自动换行仍可用
            w._set_terminal_enabled(False)
            for name in ("sw_rx_hex", "sw_hexdump", "sw_tx_hex", "cb_checksum"):
                self.assertTrue(getattr(w, name).isEnabled(), name + " 应恢复可配置")
        finally:
            w._set_terminal_enabled(old)
            w.sw_hexdump.setChecked(old_hd)

    def test_import_reloads_terminal_settings(self):
        """配置导入后终端三项即时生效（不必重启）：状态 + UI 开关 + 禁用态都同步。"""
        w = _win()
        old = (w._terminal_on, w._terminal_echo, w._terminal_enter)
        try:
            w._set_terminal_enabled(False)
            w.settings.setValue("terminal_mode", True)
            w.settings.setValue("terminal_echo", True)
            w.settings.setValue("terminal_enter", 2)    # CRLF
            w._reload_terminal_from_settings()
            self.assertTrue(w._terminal_on)
            self.assertTrue(w._terminal_echo)
            self.assertEqual(w._terminal_enter, 2)
            self.assertTrue(w.sw_terminal.isChecked())
            self.assertTrue(w.sw_term_echo.isChecked())
            self.assertEqual(w.cb_term_enter.currentIndex(), 2)
            self.assertFalse(w.cb_view_mode.isEnabled())   # 终端开 → 其它设置不可配置
        finally:
            for k in ("terminal_mode", "terminal_echo", "terminal_enter"):
                w.settings.remove(k)
            w._set_terminal_enabled(old[0])
            w._terminal_echo, w._terminal_enter = old[1], old[2]

    def test_safe_enter_idx(self):
        """回车映射索引安全解析：损坏/越界值回退 0，不让启动崩溃、不让下拉越界。"""
        f = CommTool._safe_enter_idx
        self.assertEqual(f(0), 0)
        self.assertEqual(f(2), 2)
        self.assertEqual(f("1"), 1)
        self.assertEqual(f("abc"), 0)   # 损坏的 ini 值
        self.assertEqual(f(None), 0)
        self.assertEqual(f(99), 0)      # 越界
        self.assertEqual(f(-1), 0)

    def test_terminal_mode_stops_period_send(self):
        """开终端模式时停掉定时发送，避免后台继续按周期发空内容。"""
        w = _win()
        old = (w._terminal_on, w.sw_period.isChecked())
        try:
            w._set_terminal_enabled(False)
            # 模拟「定时发送」已开 + 定时器在跑（blockSignals 避免触发未连接的提前关闭）
            w.sw_period.blockSignals(True)
            w.sw_period.setChecked(True)
            w.sw_period.blockSignals(False)
            w.send_timer.start(1000)
            self.assertTrue(w.send_timer.isActive())
            w._set_terminal_enabled(True)
            self.assertFalse(w.sw_period.isChecked())   # 定时发送被关
            self.assertFalse(w.send_timer.isActive())   # 定时器停了
        finally:
            w.send_timer.stop()
            w.sw_period.blockSignals(True)
            w.sw_period.setChecked(old[1])
            w.sw_period.blockSignals(False)
            w._set_terminal_enabled(old[0])

    def test_terminal_mode_clears_freeze_view(self):
        """进入连续流终端模式时，已冻结的视图状态必须同步解除。"""
        w = _win()
        old = (w._terminal_on, getattr(w, "_freeze_view", False),
               w.sw_freeze_view.isChecked())
        try:
            w._set_terminal_enabled(False)
            w.sw_freeze_view.setChecked(True)
            self.assertTrue(w._freeze_view)
            w._set_terminal_enabled(True)
            self.assertFalse(w.sw_freeze_view.isChecked())
            self.assertFalse(w._freeze_view)
        finally:
            w._set_terminal_enabled(old[0])
            w.sw_freeze_view.blockSignals(True)
            w.sw_freeze_view.setChecked(old[2])
            w.sw_freeze_view.blockSignals(False)
            w._freeze_view = old[1]

    def test_serial_runtime_error_autoreconnects_original_config(self):
        """串口运行时掉线会排队重连，并保存实际连接签名而不是稍后读取 UI。"""
        w = _win()
        n = {"reconnect": 0}
        old = (w._schedule_reconnect, w.conn, w._conn_engaged, w._reconnect_attempts,
               w.close_conn, w.toast, w._refresh_stat_labels, w._conn_proto,
               w._conn_cfg, w._serial_reconnect_cfg)
        try:
            w._schedule_reconnect = lambda: n.__setitem__("reconnect", n["reconnect"] + 1)
            w.close_conn = lambda: None
            w.toast = lambda *a, **k: None
            w._refresh_stat_labels = lambda *a, **k: None
            w.conn = None
            w._conn_engaged = True            # 曾连上 → 运行时掉线
            w._reconnect_attempts = 0
            serial_cfg = ("Serial", "COM1", 115200, "8", "None", "1", "None")
            w._conn_proto = "Serial"
            w._conn_cfg = serial_cfg
            w._on_conn_error("device disconnected")
            self.assertEqual(n["reconnect"], 1)
            self.assertEqual(w._serial_reconnect_cfg, serial_cfg)
            # 网络(TCP Client)掉线 → 仍重连
            w._conn_engaged = True
            w._reconnect_attempts = 0
            w._conn_proto = "TCP Client"
            w._conn_cfg = ("TCP Client", "127.0.0.1", 502)
            w._on_conn_error("connection reset")
            self.assertEqual(n["reconnect"], 2)
        finally:
            (w._schedule_reconnect, w.conn, w._conn_engaged, w._reconnect_attempts,
             w.close_conn, w.toast, w._refresh_stat_labels, w._conn_proto,
             w._conn_cfg, w._serial_reconnect_cfg) = old

    def test_serial_removal_disconnects_after_debounce(self):
        """已连接的串口在后台扫描里连续 N 次检测不到 → 断开；单次抖动不误断。"""
        w = _win()
        calls = {"close": 0, "toast": 0, "reconnect": 0}
        old = (w.conn, w._conn_proto, w._serial_device, w._serial_missing_count,
               w.close_conn, w.toast, w._schedule_reconnect, w._conn_cfg,
               w._serial_reconnect_cfg, w._available_serial_devices)
        try:
            w.close_conn = lambda: calls.__setitem__("close", calls["close"] + 1)
            w.toast = lambda *a, **k: calls.__setitem__("toast", calls["toast"] + 1)
            w._schedule_reconnect = lambda: calls.__setitem__("reconnect", calls["reconnect"] + 1)
            w.conn = object()                      # 假装已连接
            w._conn_proto = "Serial"               # PROTO_SERIAL
            w._serial_device = "COM1"
            w._conn_cfg = ("Serial", "COM1", 9600, "8", "None", "1", "None")
            w._serial_missing_count = 0
            # 口在 → 计数清零，不断开
            w._on_port_scan_complete([("COM1", "COM1"), ("COM2", "COM2")])
            self.assertEqual(calls["close"], 0)
            self.assertEqual(w._serial_missing_count, 0)
            # 连续缺失：达阈值前不断
            for _ in range(w._serial_missing_limit - 1):
                w._on_port_scan_complete([("COM2", "COM2")])
            self.assertEqual(calls["close"], 0)
            # 再缺一次 → 达阈值 → 断开 + 提示各一次
            w._on_port_scan_complete([("COM2", "COM2")])
            self.assertEqual(calls["close"], 1)
            self.assertEqual(calls["toast"], 1)
            self.assertEqual(calls["reconnect"], 1)
            self.assertEqual(w._serial_reconnect_cfg, w._conn_cfg)
            # 单次抖动后口回来 → 计数清零，不会断
            w._serial_missing_count = 0
            w._on_port_scan_complete([("COM2", "COM2")])    # 缺 1 次
            w._on_port_scan_complete([("COM1", "COM1")])    # 回来 → 清零
            self.assertEqual(w._serial_missing_count, 0)
            self.assertEqual(calls["close"], 1)             # 没有再断
        finally:
            (w.conn, w._conn_proto, w._serial_device, w._serial_missing_count,
             w.close_conn, w.toast, w._schedule_reconnect, w._conn_cfg,
             w._serial_reconnect_cfg, w._available_serial_devices) = old

    def test_serial_reconnect_waits_for_exact_original_port(self):
        """原口未出现时只继续等待；即使 UI/扫描里有其他口，也不能误连。"""
        w = _win()
        cfg = ("Serial", "COM1", 115200, "8", "None", "1", "None")
        calls = {"schedule": 0, "opened": []}
        old = (w.conn, w._user_closing, w._serial_reconnect_cfg,
               w._available_serial_devices, w._reconnect_attempts,
               w._schedule_reconnect, w.open_conn, w.toast)
        try:
            w.conn = None
            w._user_closing = False
            w._serial_reconnect_cfg = cfg
            w._reconnect_attempts = 0
            w._available_serial_devices = {"COM2"}
            w._schedule_reconnect = lambda: calls.__setitem__("schedule", calls["schedule"] + 1)
            w.open_conn = lambda reconnect_cfg=None: calls["opened"].append(reconnect_cfg)
            w.toast = lambda *a, **k: None

            w._try_reconnect()
            self.assertEqual(calls["schedule"], 1)
            self.assertEqual(calls["opened"], [])
            self.assertEqual(w._reconnect_attempts, 1)

            w._available_serial_devices = {"COM1", "COM2"}
            w.open_conn = lambda reconnect_cfg=None: (
                calls["opened"].append(reconnect_cfg), setattr(w, "conn", object()))
            w._try_reconnect()
            self.assertEqual(calls["opened"], [cfg])
            self.assertEqual(w._reconnect_attempts, 2)
        finally:
            (w.conn, w._user_closing, w._serial_reconnect_cfg,
             w._available_serial_devices, w._reconnect_attempts,
             w._schedule_reconnect, w.open_conn, w.toast) = old

    def test_serial_reconnect_keeps_combo_on_actual_port(self):
        """等待和成功重连时下拉始终显示 COM87，不能回落/残留为列表第一个 COM1。"""
        class WakeTimer:
            def __init__(self):
                self.starts = []
            def isActive(self):
                return True
            def start(self, ms):
                self.starts.append(ms)

        w = _win()
        cfg = ("Serial", "COM87", 9600, "8", "None", "1", "None")
        combo_items = [(w.cb_port.itemData(i), w.cb_port.itemText(i))
                       for i in range(w.cb_port.count())]
        combo_current = w.cb_port.currentData()
        old = (w.conn, w._serial_reconnect_cfg, w._pending_restore_port,
               w._last_port_list, w._sel_missing_count, w._reconnect_timer,
               w._reconnect_attempts)
        try:
            w.conn = None
            w._serial_reconnect_cfg = cfg
            w._pending_restore_port = None
            w._last_port_list = None
            w._sel_missing_count = 0
            w._reconnect_attempts = 3
            wake_timer = WakeTimer()
            w._reconnect_timer = wake_timer
            w._populate_port_combo([("COM87", "COM87")], "COM87")

            for _ in range(w._serial_missing_limit + 2):
                w._on_port_scan_complete([("COM1", "COM1 通信端口")])
            self.assertEqual(w.cb_port.currentData(), "COM87")

            w._on_port_scan_complete([("COM1", "COM1 通信端口"),
                                      ("COM87", "COM87 USB Serial")])
            self.assertEqual(w.cb_port.currentData(), "COM87")
            self.assertIn("COM87", w.cb_port.currentText())
            self.assertEqual(wake_timer.starts, [0])
            self.assertEqual(w._reconnect_attempts, 3)  # 立即唤醒不重置全局重连步数

            w.cb_port.setCurrentIndex(w.cb_port.findData("COM1"))
            w._select_serial_device("COM87")
            self.assertEqual(w.cb_port.currentData(), "COM87")
        finally:
            (w.conn, w._serial_reconnect_cfg, w._pending_restore_port,
             w._last_port_list, w._sel_missing_count, w._reconnect_timer,
             w._reconnect_attempts) = old
            w._populate_port_combo([(data, label) for data, label in combo_items], combo_current)

    def test_selecting_other_port_cancels_reconnect_and_removes_placeholder(self):
        """用户从 COM87 缺失占位改选 COM29 后，旧占位和旧重连必须立即清掉。"""
        class Timer:
            def __init__(self):
                self.stops = 0
            def isActive(self):
                return True
            def stop(self):
                self.stops += 1

        w = _win()
        cfg = ("Serial", "COM87", 9600, "8", "None", "1", "None")
        combo_items = [(w.cb_port.itemData(i), w.cb_port.itemText(i))
                       for i in range(w.cb_port.count())]
        combo_current = w.cb_port.currentData()
        old = (w._serial_reconnect_cfg, w._available_serial_devices,
               w._reconnect_attempts, w._sel_missing_count,
               w._pending_restore_port, w._last_port_list, w._reconnect_timer)
        try:
            timer = Timer()
            w._reconnect_timer = timer
            w._serial_reconnect_cfg = cfg
            w._available_serial_devices = {"COM1", "COM29"}
            w._reconnect_attempts = 4
            w._sel_missing_count = 8
            w._pending_restore_port = "COM87"
            w._populate_port_combo([("COM1", "COM1 通信端口"),
                                    ("COM29", "COM29 USB Serial Port")],
                                   "COM87", allow_placeholder=True)

            idx = w.cb_port.findData("COM29")
            w.cb_port.setCurrentIndex(idx)
            w._on_serial_port_selected(idx)

            self.assertIsNone(w._serial_reconnect_cfg)
            self.assertEqual(w._reconnect_attempts, 0)
            self.assertEqual(timer.stops, 1)
            self.assertEqual(w.cb_port.currentData(), "COM29")
            self.assertNotIn("COM87", [w.cb_port.itemData(i)
                                       for i in range(w.cb_port.count())])
            self.assertIsNone(w._pending_restore_port)
        finally:
            (w._serial_reconnect_cfg, w._available_serial_devices,
             w._reconnect_attempts, w._sel_missing_count,
             w._pending_restore_port, w._last_port_list, w._reconnect_timer) = old
            w._populate_port_combo([(data, label) for data, label in combo_items], combo_current)

    def test_serial_reconnect_is_silent_and_stops_at_five_seconds(self):
        """串口从 0.5s 线性退避到 5s；第 10 次失败后保持断开。"""
        class Timer:
            def __init__(self):
                self.starts = []
            def isActive(self):
                return False
            def start(self, ms):
                self.starts.append(ms)

        fake = type("Fake", (), {})()
        fake._user_closing = False
        fake._serial_reconnect_cfg = ("Serial", "COM1", 9600, "8", "None", "1", "None")
        fake._serial_reconnect_limit = 10
        fake._reconnect_attempts = 0
        fake._reconnect_timer = Timer()
        fake.settings = type("Settings", (), {"value": lambda self, *a, **k: True})()
        fake.toast = lambda *a, **k: self.fail("串口静默重连不应弹提示")
        fake._t = lambda *a, **k: ""

        for attempt in range(10):
            fake._reconnect_attempts = attempt
            CommTool._schedule_reconnect(fake)
        fake._reconnect_attempts = 10
        CommTool._schedule_reconnect(fake)

        self.assertEqual(fake._reconnect_timer.starts,
                         [500, 1000, 1500, 2000, 2500,
                          3000, 3500, 4000, 4500, 5000])
        self.assertIsNone(fake._serial_reconnect_cfg)
        self.assertEqual(fake._reconnect_attempts, 0)

    def test_serial_reconnect_uses_one_global_ten_slot_window(self):
        """缺口等待和实际打开共用 10 个时隙；末次失败后不能退化成 UI/网络重连。"""
        class Timer:
            def __init__(self):
                self.starts = []
            def isActive(self):
                return False
            def start(self, ms):
                self.starts.append(ms)

        fake = type("Fake", (), {})()
        cfg = ("Serial", "COM87", 9600, "8", "None", "1", "None")
        fake.conn = None
        fake._user_closing = False
        fake._serial_reconnect_cfg = cfg
        fake._serial_reconnect_limit = 10
        fake._reconnect_attempts = 0
        fake._available_serial_devices = set()
        fake._reconnect_timer = Timer()
        fake.settings = type("Settings", (), {"value": lambda self, *a, **k: True})()
        fake.toast = lambda *a, **k: self.fail("串口重连应静默")
        def fail_final_open(reconnect_cfg=None):
            # 模拟同步 error_occurred 已在内部达到上限并清除目标；_try_reconnect 尾部不得再排队。
            fake._serial_reconnect_cfg = None
            fake._reconnect_attempts = 0
        fake.open_conn = fail_final_open
        fake._schedule_reconnect = lambda: CommTool._schedule_reconnect(fake)

        CommTool._schedule_reconnect(fake)       # 第 1 个时隙：0.5s
        for _ in range(9):                       # 前 9 次端口仍缺失
            CommTool._try_reconnect(fake)
        fake._available_serial_devices = {"COM87"}
        CommTool._try_reconnect(fake)             # 第 10 次真实 open 失败

        self.assertEqual(fake._reconnect_timer.starts,
                         [500, 1000, 1500, 2000, 2500,
                          3000, 3500, 4000, 4500, 5000])
        self.assertIsNone(fake._serial_reconnect_cfg)
        self.assertEqual(fake._reconnect_attempts, 0)

    def test_serial_disconnect_prompts_once_then_retries_silently(self):
        """首次掉线无论计数状态都提示；进入重连会话后的打开失败不重复提示。"""
        w = _win()
        cfg = ("Serial", "COM1", 9600, "8", "None", "1", "None")
        calls = {"toast": 0, "schedule": 0}
        old = (w.conn, w._conn_proto, w._conn_cfg, w._conn_engaged,
               w._reconnect_attempts, w._serial_reconnect_cfg, w.close_conn,
               w.toast, w._schedule_reconnect, w._refresh_stat_labels)
        try:
            w.conn = None
            w._conn_proto = "Serial"
            w._conn_cfg = cfg
            w._conn_engaged = True
            w._reconnect_attempts = 3  # 即使计数异常残留，首次掉线仍必须提示
            w._serial_reconnect_cfg = None
            w.close_conn = lambda: None
            w.toast = lambda *a, **k: calls.__setitem__("toast", calls["toast"] + 1)
            w._schedule_reconnect = lambda: calls.__setitem__("schedule", calls["schedule"] + 1)
            w._refresh_stat_labels = lambda *a, **k: None

            w._on_conn_error("device disconnected")
            self.assertEqual(calls, {"toast": 1, "schedule": 1})
            self.assertEqual(w._serial_reconnect_cfg, cfg)

            w._conn_engaged = False
            w._reconnect_attempts = 1
            w._on_conn_error("open failed")
            self.assertEqual(calls, {"toast": 1, "schedule": 2})
        finally:
            (w.conn, w._conn_proto, w._conn_cfg, w._conn_engaged,
             w._reconnect_attempts, w._serial_reconnect_cfg, w.close_conn,
             w.toast, w._schedule_reconnect, w._refresh_stat_labels) = old

    def test_exact_int_accepts_leading_zero_decimal(self):
        from modbus_master import _exact_int
        self.assertEqual(_exact_int("08"), 8)
        self.assertEqual(_exact_int("010"), 10)      # 十进制 10，不是八进制
        self.assertEqual(_exact_int("0x1F"), 31)     # 十六进制前缀仍支持
        self.assertEqual(_exact_int("247"), 247)
        self.assertEqual(_exact_int(5), 5)
        with self.assertRaises(ValueError):
            _exact_int("zz")
        with self.assertRaises(ValueError):
            _exact_int(1.9)                           # 非整数浮点仍拒


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class ScriptEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = _win()

    def ev(self, script, frame=b"\xAA\x11\x22\x33"):
        return self.w._ar_script_eval({"script": script}, frame)

    def test_return_bytes(self):
        self.assertEqual(self.ev("def reply(f,c):\n return bytes([6])+f[1:3]"), (["06 11 22"], None))

    def test_return_str_utf8(self):
        self.assertEqual(self.ev("def reply(f,c):\n return 'AB'"), (["41 42"], None))

    def test_return_list_multiframe(self):
        self.assertEqual(self.ev("def reply(f,c):\n return [b'\\x06', b'\\x15']"), (["06", "15"], None))

    def test_return_none(self):
        self.assertEqual(self.ev("def reply(f,c):\n return None"), (None, None))

    def test_empty_bytes_means_no_reply(self):
        self.assertEqual(self.ev("def reply(f,c):\n return b''"), (None, None))

    def test_ctx_crc_builds_modbus_response(self):
        parts, err = self.ev("def reply(f,c):\n d=b'\\x01\\x03\\x02\\x00\\x0A'\n return d + c.crc16(d)")
        self.assertIsNone(err)
        self.assertEqual(parts, ["01 03 02 00 0A 38 43"])   # crc16(Modbus,小端) of 01 03 02 00 0A

    def test_runtime_error_caught(self):
        parts, err = self.ev("def reply(f,c):\n return 1/0")
        self.assertIsNone(parts)
        self.assertIn("ZeroDivisionError", err)

    def test_syntax_error_caught(self):
        parts, err = self.ev("def reply(f,c)\n return b''")
        self.assertIsNone(parts)
        self.assertIn("SyntaxError", err)

    def test_missing_reply_func(self):
        parts, err = self.ev("x = 1")
        self.assertIsNone(parts)
        self.assertIn("reply", err)

    def test_bad_return_type(self):
        parts, err = self.ev("def reply(f,c):\n return 123")
        self.assertIsNone(parts)
        self.assertTrue(err)

    def test_script_on_flag_gates_engine(self):
        # script_on=True → 走脚本；False → 跳过脚本回退静态（此处静态空 → 不回）
        self.w._ar_rules = [{"match": "AA", "match_hex": True, "mode": 2, "on": True, "reply": "",
                             "script": "def reply(f,c):\n return b'\\x06'", "script_on": True}]
        self.assertEqual(self.w._ar_preview(b"\xAA").get("replies"), ["06"])
        self.w._ar_rules[0]["script_on"] = False
        self.assertEqual(self.w._ar_preview(b"\xAA").get("replies"), [])

    def test_seq_advances_each_call(self):
        # 评审#3：ctx.seq 每次调用自增（之前一直拿到同一值）
        self.w._ar_seq = 0
        a = self.w._ar_script_eval({"script": "def reply(f,c):\n return bytes([c.seq])"}, b"\x00")[0]
        b = self.w._ar_script_eval({"script": "def reply(f,c):\n return bytes([c.seq])"}, b"\x00")[0]
        self.assertEqual((a, b), (["01"], ["02"]))

    def test_preview_hits_matches_live(self):
        # 评审#3：预览 hits 比 live 少一次 → 现在 preview 下 +1 对齐
        self.assertEqual(self.w._ar_make_ctx({"_hits": 3}, preview=False).hits, 3)
        self.assertEqual(self.w._ar_make_ctx({"_hits": 3}, preview=True).hits, 4)

    def test_fresh_namespace_no_state_leak(self):
        # 评审#2：每次全新命名空间 → 模块级状态不跨调用累积（预览/测试不污染实发）
        sc = "g=[0]\ndef reply(f,c):\n g[0]+=1\n return bytes([g[0]])"
        a = self.w._ar_script_eval({"script": sc}, b"\x00")[0]
        b = self.w._ar_script_eval({"script": sc}, b"\x00")[0]
        self.assertEqual((a, b), (["01"], ["01"]))

    def test_timeout_kills_infinite_loop(self):
        # 评审#1：超时必须真正终止子进程，不能只是主调用返回。
        old = self.w._AR_SCRIPT_TIMEOUT
        self.w._AR_SCRIPT_TIMEOUT = 0.2
        try:
            parts, err = self.w._ar_script_eval({"script": "def reply(f,c):\n while True: pass"}, b"\x00")
        finally:
            self.w._AR_SCRIPT_TIMEOUT = old
        self.assertIsNone(parts)
        self.assertTrue(err)
        self.assertIsNone(self.w._ar_script_proc)
        self.assertIsNone(self.w._ar_script_conn)
        # 超时工作进程被杀后，下一帧应自动重建并恢复正常执行。
        parts, err = self.w._ar_script_eval({"script": "def reply(f,c): return b'\\x06'"}, b"\x00")
        self.assertEqual((parts, err), (["06"], None))
        self.assertTrue(self.w._ar_script_proc.is_alive())

    def test_preview_does_not_consume_seq(self):
        self.w._ar_seq = 10
        parts, err = self.w._ar_script_eval(
            {"script": "def reply(f,c):\n return bytes([c.seq])"}, b"\x00", preview=True)
        self.assertEqual((parts, err), (["0B"], None))
        self.assertEqual(self.w._ar_seq, 10)

    def test_non_string_script_no_crash(self):
        # 评审#3：script 字段非字符串 → str() 容错，不抛 AttributeError
        parts, err = self.w._ar_script_eval({"script": 123}, b"\x00")
        self.assertIsNone(parts)
        self.assertTrue(err)
        self.w._ar_rules = [{"match": "AA", "match_hex": True, "mode": 2, "on": True, "script": 123}]
        self.assertIsInstance(self.w._ar_preview(b"\xAA"), dict)   # 实时/预览路径也不崩

    def test_preview_worker_isolated_from_live(self):
        # 评审#2：预览与实发各用独立进程 → 预览不污染实发的 random/已导入模块等共享态
        self.w._ar_script_eval({"script": "def reply(f,c): return b'\\x01'"}, b"\x00", preview=False)
        self.w._ar_script_eval({"script": "def reply(f,c): return b'\\x01'"}, b"\x00", preview=True)
        self.assertNotEqual(self.w._ar_script_proc.pid, self.w._ar_preview_proc.pid)

    @unittest.skipIf(sys.platform == "win32", "POSIX setsid/pgid handshake")
    def test_worker_ready_means_private_process_group(self):
        self.w._ar_script_eval({"script": "def reply(f,c): return b'\\x01'"}, b"\x00")
        pid = self.w._ar_script_proc.pid
        self.assertEqual(os.getpgid(pid), pid)
        self.assertNotEqual(os.getpgid(pid), os.getpgrp())

    @unittest.skipIf(sys.platform == "win32", "posix killpg path; Windows 走 taskkill /T")
    def test_timeout_kills_spawned_subprocess(self):
        # 评审#1：超时杀整个进程组 → 脚本起的 subprocess 孙子进程也被回收，不 orphan
        import tempfile, time
        marker = tempfile.mktemp()
        sc = ("import subprocess, sys\n"
              "def reply(f, c):\n"
              "    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
              "    with open(%r, 'w') as fh: fh.write(str(p.pid))\n"
              "    while True: pass\n" % marker)
        old = self.w._AR_SCRIPT_TIMEOUT
        self.w._AR_SCRIPT_TIMEOUT = 0.3
        try:
            try:
                self.w._ar_script_eval({"script": sc}, b"\x00")
            finally:
                self.w._AR_SCRIPT_TIMEOUT = old
            time.sleep(0.5)
            with open(marker, encoding="utf-8") as f:
                cpid = int(f.read())
            try:
                os.kill(cpid, 0)
                alive = True
            except OSError:
                alive = False
            self.assertFalse(alive)
        finally:
            try:
                os.unlink(marker)
            except FileNotFoundError:
                pass

    @unittest.skipIf(sys.platform == "win32", "posix killpg path; Windows 走 taskkill /T")
    def test_crashed_worker_still_kills_spawned_subprocess(self):
        # worker 先退出后 is_alive() 已为 False，仍必须按 ready 握手记录的 PGID 回收孙进程。
        import signal, tempfile, time
        marker = tempfile.mktemp()
        child_pid = None
        sc = ("import os, subprocess, sys\n"
              "def reply(f, c):\n"
              "    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
              "    with open(%r, 'w') as fh: fh.write(str(p.pid))\n"
              "    os._exit(7)\n" % marker)
        try:
            parts, err = self.w._ar_script_eval({"script": sc}, b"\x00")
            self.assertIsNone(parts)
            self.assertTrue(err)
            with open(marker, encoding="utf-8") as f:
                child_pid = int(f.read())
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    os.kill(child_pid, 0)
                except OSError:
                    break
                time.sleep(0.05)
            else:
                self.fail("worker 崩溃后子进程未被回收")
        finally:
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except OSError:
                    pass
            try:
                os.unlink(marker)
            except FileNotFoundError:
                pass

    @classmethod
    def tearDownClass(cls):
        cls.w._ar_stop_script_worker()

    def test_ctx_helpers(self):
        ctx = self.w._ar_make_ctx({"_hits": 5})
        self.assertEqual(ctx.crc8(b"123456789"), b"\xf4")
        self.assertEqual(ctx.sum8(bytes([0x10, 0x20, 0x30])), bytes([0x60]))
        self.assertEqual(ctx.xor8(bytes([0x0F, 0xF0])), bytes([0xFF]))
        self.assertEqual(ctx.hexbytes("AA BB,0xCC"), b"\xaa\xbb\xcc")
        self.assertEqual(ctx.tohex(b"\xaa\xbb"), "AA BB")
        self.assertEqual(ctx.hits, 5)


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class ImportGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = _win()

    @staticmethod
    def _cfg():
        import json
        return {"autoreply_rules": json.dumps(
            [{"match": "AA", "script": "def reply(f,c):\n return b'\\x99'"},
             {"match": "BB"}], ensure_ascii=False)}

    def test_trust_keeps_scripts(self):
        self.w._ar_confirm = lambda *a: True
        out = self.w._ar_gate_imported_scripts(self._cfg())
        self.assertIn("reply", out["autoreply_rules"])

    def test_decline_strips_scripts_but_keeps_rules(self):
        import json
        self.w._ar_confirm = lambda *a: False
        out = self.w._ar_gate_imported_scripts(self._cfg())
        rules = json.loads(out["autoreply_rules"])
        self.assertEqual(len(rules), 2)
        self.assertTrue(all(not (r.get("script") or "") for r in rules))

    def test_no_script_no_prompt(self):
        import json
        called = {"n": 0}
        self.w._ar_confirm = lambda *a: called.__setitem__("n", 1) or True
        self.w._ar_gate_imported_scripts({"autoreply_rules": json.dumps([{"match": "AA"}])})
        self.assertEqual(called["n"], 0)


class NumericStreamParserTests(unittest.TestCase):
    """数值流解析器（仪表盘/波形图共用语义）：三模式 + 跨包缓冲 + 通道命名。仅依赖 binproto，无需 Qt。"""

    def _p(self, mode=0):
        from stream_parse import NumericStreamParser
        p = NumericStreamParser()
        p.mode = mode
        return p

    def test_delim_columns(self):
        p = self._p(0)
        self.assertEqual(p.feed(b"36.5,72,3.30\n"),
                         [("CH1", 36.5), ("CH2", 72.0), ("CH3", 3.30)])

    def test_delim_nonnumeric_keeps_column_index(self):
        # 非数值列跳过，但通道号仍按 token 位置（"abc"=CH1 跳过，"5"=CH2）
        p = self._p(0)
        self.assertEqual(p.feed(b"abc,5\n"), [("CH2", 5.0)])

    def test_delim_auto_sep(self):
        p = self._p(0)
        p.sep_index = 4                       # [,\s;]+
        self.assertEqual(p.feed(b"1 2\t3;4\n"),
                         [("CH1", 1.0), ("CH2", 2.0), ("CH3", 3.0), ("CH4", 4.0)])

    def test_regex_groups(self):
        p = self._p(1)
        self.assertTrue(p.set_regex(r"t=(\d+).*h=(\d+)"))
        self.assertEqual(p.feed(b"t=25 h=60\n"), [("CH1", 25.0), ("CH2", 60.0)])

    def test_regex_bad_pattern(self):
        p = self._p(1)
        self.assertFalse(p.set_regex(r"("))   # 非法正则
        self.assertEqual(p.feed(b"anything\n"), [])

    def test_hex_fields(self):
        p = self._p(2)
        self.assertTrue(p.set_header("AA"))
        self.assertTrue(p.set_fields("temp=1:i16be, volt=3:u16be"))
        # AA + 0x00FA(=250) + 0x0CE4(=3300)
        self.assertEqual(p.feed(bytes([0xAA, 0x00, 0xFA, 0x0C, 0xE4])),
                         [("temp", 250.0), ("volt", 3300.0)])

    def test_hex_header_mismatch(self):
        p = self._p(2)
        p.set_header("AA")
        p.set_fields("x=1:u8")
        self.assertEqual(p.feed(bytes([0xBB, 0x01])), [])   # 帧头不符 → 空

    def test_cross_packet_buffering(self):
        p = self._p(0)
        self.assertEqual(p.feed(b"1.2,3."), [])             # 未成行 → 缓冲
        self.assertEqual(p.feed(b"4\n"), [("CH1", 1.2), ("CH2", 3.4)])

    def test_multibyte_regex_across_packets(self):
        """UTF-8 多字节标签跨收包时仍应完整解码并匹配。"""
        p = self._p(1)
        self.assertTrue(p.set_regex(r"温度=(\d+)"))
        raw = "温度=25\n".encode("utf-8")
        self.assertEqual(p.feed(raw[:2], "utf-8"), [])      # 截在“温”的 UTF-8 中间
        self.assertEqual(p.feed(raw[2:], "utf-8"), [("CH1", 25.0)])

    def test_codec_change_drops_old_partial_line(self):
        p = self._p(0)
        self.assertEqual(p.feed(b"1,", "utf-8"), [])
        self.assertEqual(p.feed(b"2\n", "gbk"), [("CH1", 2.0)])

    def test_reset_clears_buffer(self):
        p = self._p(0)
        p.feed(b"9.9,")                                     # 残段进缓冲
        p.reset()
        self.assertEqual(p.feed(b"1,2\n"), [("CH1", 1.0), ("CH2", 2.0)])


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class DashboardTests(unittest.TestCase):
    """数值仪表盘：feed → 建卡片 + 最新值 + 阈值告警着色。"""

    def _dlg(self, thresh=""):
        from dashboard_dialog import DashboardDialog
        w = _win()
        for k in ("dash_mode", "dash_sep", "dash_regex", "dash_fields", "dash_header"):
            w.settings.setValue(k, "")
        w.settings.setValue("dash_mode", 0)
        w.settings.setValue("dash_thresholds", thresh)
        dlg = DashboardDialog(w)
        return w, dlg

    def test_feed_creates_tiles_and_values(self):
        w, dlg = self._dlg()
        try:
            dlg.feed(b"36.5,72\n")
            self.assertEqual(dlg._order, ["CH1", "CH2"])
            self.assertEqual(dlg._values["CH1"], 36.5)
            dlg._refresh_tiles()
            self.assertEqual(dlg._tiles["CH1"]["lbl_val"].text(), "36.5")
            self.assertEqual(dlg._tiles["CH2"]["lbl_val"].text(), "72")   # 整数去小数点
        finally:
            dlg.deleteLater()

    def test_threshold_alert(self):
        w, dlg = self._dlg(thresh="CH1:0~30:℃")
        try:
            dlg.feed(b"36.5,20\n")            # CH1=36.5 > 30 → 告警；CH2 无阈值
            dlg._refresh_tiles()
            self.assertTrue(dlg._tiles["CH1"]["alert"])
            self.assertFalse(dlg._tiles["CH2"]["alert"])
            self.assertEqual(dlg._tiles["CH1"]["lbl_unit"].text(), "℃")
            # 回到范围内 → 解除告警
            dlg.feed(b"25,20\n")
            dlg._refresh_tiles()
            self.assertFalse(dlg._tiles["CH1"]["alert"])
        finally:
            dlg.deleteLater()

    def test_threshold_one_sided(self):
        w, dlg = self._dlg(thresh="CH1:10~:V")   # 只管下限
        try:
            dlg.feed(b"5\n")                       # < 10 → 告警
            dlg._refresh_tiles()
            self.assertTrue(dlg._tiles["CH1"]["alert"])
            dlg.feed(b"9999\n")                    # 上限留空 → 不告警
            dlg._refresh_tiles()
            self.assertFalse(dlg._tiles["CH1"]["alert"])
        finally:
            dlg.deleteLater()

    def test_pause_stops_updates(self):
        w, dlg = self._dlg()
        try:
            dlg.feed(b"1,")                                # 留一个未完成残段
            dlg._toggle_pause()
            dlg.feed(b"999\n")                            # 暂停中不解析
            dlg._toggle_pause()
            dlg.feed(b"2\n")                              # 不得与暂停前的 "1," 拼接
            self.assertEqual(dlg._order, ["CH1"])
            self.assertEqual(dlg._values["CH1"], 2.0)
        finally:
            dlg.deleteLater()

    def test_reset_stream_drops_partial_line_but_keeps_tiles(self):
        w, dlg = self._dlg()
        try:
            dlg.feed(b"7\n")
            dlg.feed(b"1,")
            dlg.reset_stream()                              # 模拟隐藏/重连
            dlg.feed(b"2\n")
            self.assertEqual(dlg._values["CH1"], 2.0)
            self.assertNotIn("CH2", dlg._values)
            self.assertIn("CH1", dlg._tiles)               # 最近值卡片无需销毁重建
        finally:
            dlg.deleteLater()

    def test_tile_cap(self):
        from dashboard_dialog import _MAX_TILES
        w, dlg = self._dlg()
        try:
            line = ",".join(str(i) for i in range(_MAX_TILES + 30)) + "\n"
            dlg.feed(line.encode())                         # 畸形长行 → 只建到上限、不卡死
            self.assertEqual(len(dlg._tiles), _MAX_TILES)
            self.assertLessEqual(len(dlg._values), _MAX_TILES)
        finally:
            dlg.deleteLater()


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class ProtoHighlightTests(unittest.TestCase):
    """协议高亮：HEX 模式下按 frame_rules 把收到帧各字段映射成数据区字符区间 + 悬浮标签。"""

    # Modbus 读响应帧 01 03 + 地址 006B + 数量 0001 + CRC D5 D9
    FRAME = bytes([0x01, 0x03, 0x00, 0x6B, 0x00, 0x01, 0xD5, 0xD9])
    RULE = "01 03 | slave=0:u8x, func=1:u8x, addr=2:u16be, crc=6:hex2"

    def _setup(self, rule=None):
        w = _win()
        w.settings.setValue("frame_rules", rule if rule is not None else self.RULE)
        w._proto_rules_raw = None            # 强制重解析（清缓存）
        w._proto_fields.clear()
        # 数值视图 / HEX 转储在渲染路径里都排在 HEX 之前且直接 return —— 前面的用例若把任一个
        # 留在开启态，本类的协议高亮就永远跑不到（表现为 _proto_fields 空、KeyError）。
        # 用开关而非私有标志，顺带走它们各自的复位（清余数 / 清字段）。
        w.sw_numview.setChecked(False, animate=False)
        w.sw_hexdump.setChecked(False, animate=False)
        w.sw_rx_hex.setChecked(True)
        w._hexdump_on = False
        w.sw_line_split.setChecked(False)
        # 开关已挪到「帧解析」对话框；这里用主窗 API 置位（与对话框勾选框驱动的是同一路径）
        w.set_proto_highlight(True)
        w._proto_fields.clear()
        w.txt_recv.clear()
        w._reset_recv_state()
        return w

    def test_rules_parsed_and_cached(self):
        w = self._setup()
        r1 = w._proto_rules()
        self.assertEqual(len(r1), 1)
        self.assertEqual(r1[0]["header"], b"\x01\x03")
        self.assertEqual([f[0] for f in r1[0]["fields"]], ["slave", "func", "addr", "crc"])
        self.assertIs(w._proto_rules(), r1)   # raw 未变 → 命中缓存返回同对象

    def test_field_char_ranges(self):
        """每字段 cursor 选中的正是该字段字节对应的 hex 子串。"""
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        got = {f["label"].split("·")[1].split("=")[0].strip():
               f["cursor"].selectedText() for f in w._proto_fields}
        self.assertEqual(got["slave"], "01")
        self.assertEqual(got["func"], "03")
        self.assertEqual(got["addr"], "00 6B")
        self.assertEqual(got["crc"], "D5 D9")

    def test_field_labels(self):
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        labels = [f["label"] for f in w._proto_fields]
        self.assertIn("01 03 · slave=0x1", labels)     # u8x → 十六进制
        self.assertIn("01 03 · func=0x3", labels)
        self.assertIn("01 03 · addr=107", labels)      # u16be 0x006B=107，无 x → 十进制
        self.assertIn("01 03 · crc=D5 D9", labels)     # hex2 → 原样 HEX 串

    def test_hover_field_at(self):
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        cur = next(f["cursor"] for f in w._proto_fields if "addr=" in f["label"])
        mid = (cur.selectionStart() + cur.selectionEnd()) // 2
        self.assertIn("addr=107", w._proto_field_at(mid))
        self.assertIsNone(w._proto_field_at(w.txt_recv.document().characterCount() + 50))

    def test_extra_selections_emitted(self):
        w = self._setup()
        orig = w._active_rules
        w._active_rules = lambda: []          # 无关键字规则，隔离出字段选区
        try:
            w._on_data_received_impl(self.FRAME)
            w._refresh_extra_selections()
            palette = {c.upper() for c in w._PROTO_PALETTE}
            field_sels = [s for s in w.txt_recv.extraSelections()
                          if s.format.background().color().name().upper() in palette]
            self.assertEqual(len(field_sels), 4)
        finally:
            w._active_rules = orig

    def test_text_mode_hides_highlight(self):
        """切到文本模式立即撤掉协议高亮（区间按 HEX 渲染算得，文本模式无意义）；切回 HEX 恢复。"""
        w = self._setup()
        orig = w._active_rules
        w._active_rules = lambda: []
        try:
            palette = {c.upper() for c in w._PROTO_PALETTE}
            fc = lambda: sum(1 for s in w.txt_recv.extraSelections()
                             if s.format.background().color().name().upper() in palette)
            w._on_data_received_impl(self.FRAME)
            w._refresh_extra_selections()
            self.assertEqual(fc(), 4, "HEX 模式应画 4 字段")
            w.sw_rx_hex.setChecked(False)     # → _on_hex_display_changed 立即重画
            self.assertEqual(fc(), 0, "文本模式不应残留协议高亮")
            w.sw_rx_hex.setChecked(True)       # 切回 HEX
            self.assertEqual(fc(), 4, "切回 HEX 高亮应恢复")
        finally:
            w._active_rules = orig
            w.sw_rx_hex.setChecked(True)

    def test_hexdump_mode_hides_highlight(self):
        """开启 HEX 转储 → 立即清掉普通 HEX 的协议色块（转储是另一种排版，不适用），不残留到下一包。"""
        w = self._setup()
        orig = w._active_rules
        w._active_rules = lambda: []
        try:
            palette = {c.upper() for c in w._PROTO_PALETTE}
            fc = lambda: sum(1 for s in w.txt_recv.extraSelections()
                             if s.format.background().color().name().upper() in palette)
            w._on_data_received_impl(self.FRAME)
            w._refresh_extra_selections()
            self.assertEqual(fc(), 4, "普通 HEX 应画 4 字段")
            w._on_hexdump_toggled(True)         # 开转储 → 立即清 + 重画
            self.assertEqual(fc(), 0, "转储模式不应残留协议色块")
            self.assertEqual(len(w._proto_fields), 0)
        finally:
            w._on_hexdump_toggled(False)         # 复原到普通 HEX
            w._active_rules = orig

    def test_header_mismatch_no_fields(self):
        w = self._setup()
        w._on_data_received_impl(bytes([0x02, 0x03, 0x00, 0x6B]))   # 帧头非 01 03
        self.assertEqual(len(w._proto_fields), 0)

    def test_off_clears_and_no_emit(self):
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self.assertTrue(w._proto_fields)
        w.set_proto_highlight(False)          # 关闭 → 清空已存字段
        self.assertEqual(len(w._proto_fields), 0)
        self.assertFalse(w._proto_hl_on)

    def test_frame_dialog_checkbox_drives(self):
        """「帧解析」对话框的勾选框 ↔ 主窗 _proto_hl_on 双向同步。"""
        from frame_dialog import FrameParseDialog
        w = self._setup()                 # _proto_hl_on = True
        old = getattr(w, "_frame_dlg", None)
        dlg = FrameParseDialog(w)
        w._frame_dlg = dlg
        try:
            dlg.sync_highlight()
            self.assertTrue(dlg.chk_highlight.isChecked())    # 跟随主窗 True
            dlg.chk_highlight.setChecked(False)               # 勾选框驱动 → set_proto_highlight(False)
            self.assertFalse(w._proto_hl_on)
            dlg.chk_highlight.setChecked(True)
            self.assertTrue(w._proto_hl_on)
            w.set_proto_highlight(False)                      # 主窗端改动 → 反映回勾选框
            self.assertFalse(dlg.chk_highlight.isChecked())
        finally:
            w._frame_dlg = old
            dlg.deleteLater()

    def test_out_of_range_field_skipped(self):
        """字段偏移超出帧长 → 跳过不崩（截断帧）。"""
        w = self._setup()
        w._on_data_received_impl(self.FRAME[:3])   # 只有 3 字节，addr/crc 越界
        got = {f["label"].split("·")[1].split("=")[0].strip() for f in w._proto_fields}
        self.assertEqual(got, {"slave", "func"})   # 仅前两个在范围内


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class ScriptConsoleTests(unittest.TestCase):
    """脚本控制台执行核心：API 语义 / 跨块匹配 / 超时 / 停止 / 断言计数 / 端到端跑一段脚本。
    多数用例直接调 _api_*（不起线程），避免线程竞态、跑得快。"""

    def _w(self, code=""):
        _win()                                  # 确保 QApplication 存在
        from script_console import ScriptWorker
        return ScriptWorker(code)

    def test_parse_hex(self):
        from script_console import parse_hex
        self.assertEqual(parse_hex("AA BB"), b"\xaa\xbb")
        self.assertEqual(parse_hex("0xAA,0xBB"), b"\xaa\xbb")
        self.assertEqual(parse_hex(""), b"")
        with self.assertRaises(ValueError):
            parse_hex("ABC")                    # 奇数长度

    def test_send_encodes(self):
        w = self._w()
        got = []
        def sent(_worker, payload, done, result):
            got.append(payload)
            result["ok"] = True
            done.set()
        w.send_requested.connect(sent)
        w._api_send("AB")                       # 文本 → UTF-8
        w._api_send("01 02", hex=True)          # HEX 串
        w._api_send(b"\xff")                    # bytes 原样
        self.assertEqual(got, [b"AB", b"\x01\x02", b"\xff"])

    def test_expect_matches_across_chunks(self):
        """跨多个收包拼接后匹配；返回含匹配的那段，尾部留给下次。"""
        w = self._w()
        w.feed(b"AT")
        w.feed(b"+OK\r\n")
        self.assertEqual(w._api_expect("OK", timeout=300), b"AT+OK")
        self.assertEqual(w._api_recv(0), b"\r\n")      # 未消费尾部还在

    def test_expect_hex_pattern(self):
        w = self._w()
        w.feed(bytes([0x01, 0x03, 0x02, 0x00]))
        self.assertEqual(w._api_expect("01 03", timeout=300, hex=True),
                         bytes([0x01, 0x03]))

    def test_expect_timeout_returns_none(self):
        w = self._w()
        w.feed(b"junk")
        self.assertIsNone(w._api_expect("OK", timeout=60))

    def test_expect_empty_pattern_rejected(self):
        w = self._w()
        with self.assertRaises(ValueError):
            w._api_expect("", timeout=10)

    def test_recv_timeout_returns_empty(self):
        w = self._w()
        self.assertEqual(w._api_recv(30), b"")

    def test_check_counts_and_returns(self):
        w = self._w()
        self.assertTrue(w._api_check(1 == 1, "ok"))
        self.assertFalse(w._api_check(False, "bad"))
        self.assertEqual((w.checks_passed, w.checks_failed), (1, 1))

    def test_stop_interrupts_sleep_and_expect(self):
        from script_console import ScriptStopped
        w = self._w()
        w.stop()
        with self.assertRaises(ScriptStopped):
            w._api_sleep(5000)
        with self.assertRaises(ScriptStopped):
            w._api_expect("X", timeout=5000)

    @staticmethod
    def _run_and_wait(w, done, timeout=8000):
        """起线程并跑主线程事件循环直到脚本结束。
        ScriptWorker 对象归属主线程，run() 里 emit 的信号是**队列连接**，必须有事件循环
        才能投递（真实程序里就是主事件循环）——所以不能只 w.wait()。"""
        from PyQt5.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        w.run_finished.connect(lambda ok, s: (done.append((ok, s)), loop.quit()))
        QTimer.singleShot(timeout, loop.quit)      # 兜底：卡住也不挂死测试
        w.start()
        loop.exec_()
        w.wait(2000)

    def test_run_end_to_end(self):
        """真起线程跑一段脚本：send 触发对端回包 → expect 命中 → check 通过 → 汇总 ok。"""
        code = ("log('go')\n"
                "send('PING')\n"
                "r = expect('PONG', timeout=3000)\n"
                "check(r is not None, 'got pong')\n")
        w = self._w(code)
        sent, done, logs = [], [], []
        def send_and_reply(_worker, payload, ack, result):
            sent.append(payload)
            result["ok"] = True
            w.feed(b"PONG")
            ack.set()
        w.send_requested.connect(send_and_reply)
        w.log_line.connect(logs.append)
        self._run_and_wait(w, done)
        self.assertEqual(sent, [b"PING"])
        self.assertEqual(done, [(True, "")])
        self.assertEqual((w.checks_passed, w.checks_failed), (1, 0))
        self.assertIn("go", logs)

    def test_run_reports_syntax_error(self):
        w = self._w("def (:\n")
        done = []
        self._run_and_wait(w, done)
        self.assertEqual(done, [(False, "syntax")])

    def test_run_failed_check_marks_not_ok(self):
        w = self._w("check(False, 'boom')\n")
        done = []
        self._run_and_wait(w, done)
        self.assertEqual(done, [(False, "checks")])

    def test_negative_timeout_rejected(self):
        """负数超时是调用方笔误：原先被 max(0,..) 静默钳成 0（=不等待），现在直接报错。"""
        w = self._w()
        with self.assertRaises(ValueError):
            w._api_expect("X", timeout=-1)
        with self.assertRaises(ValueError):
            w._api_recv(-5)
        with self.assertRaises(ValueError):
            w._api_sleep(-1)
        self.assertEqual(w._api_recv(0), b"")          # 0 仍合法 = 非阻塞查一次

    def test_buffer_truncation_warns_once(self):
        """缓冲超限截断会告警（否则模式跨越截断点后永远匹配不到、现象难懂），且只告警一次。"""
        w = self._w()
        logs = []
        w.log_line.connect(logs.append)
        big = b"x" * (w._MAX_BUF + 4096)
        w.feed(big)
        w.feed(big)
        self.assertIsNone(w._api_expect("NOPE", timeout=50))
        warns = [ln for ln in logs if "截断" in ln]
        self.assertEqual(len(warns), 1, warns)

    def test_pending_rx_is_bounded_before_worker_consumes(self):
        """脚本 sleep/计算期间 feed 也必须限流，不能把数据留在无界队列里。"""
        w = self._w()
        w.feed(b"a" * (w._MAX_BUF // 2 + 1))
        w.feed(b"b" * (w._MAX_BUF // 2 + 1))
        self.assertLessEqual(w._rx_bytes, w._MAX_BUF)
        self.assertEqual(w._api_recv(0)[:1], b"b")       # 最旧块被丢，保留最新数据

    def test_stale_worker_send_is_rejected(self):
        """关窗/换轮后才送达 GUI 的旧 worker 发送不能落到当前连接。"""
        import threading
        from script_console import ScriptWorker
        app = _win()
        old, new = ScriptWorker(""), ScriptWorker("")
        old_reg, old_send = app._script_worker, app._send_text
        calls, done, result = [], threading.Event(), {"ok": False}
        try:
            app._script_worker = new
            app._send_text = lambda *a, **k: calls.append((a, k)) or True
            app._script_send(old, b"STALE", done, result)
            self.assertTrue(done.is_set())
            self.assertFalse(result["ok"])
            self.assertEqual(calls, [])
        finally:
            app._script_worker, app._send_text = old_reg, old_send

    def test_main_send_bridge_acknowledges_current_worker(self):
        """真实队列信号经主窗口发送并回 ACK，worker 才能继续且不会死锁。"""
        app = _win()
        worker = self._w("check(send('PING') == 4, 'sent')\n")
        old = (app._script_worker, app._script_quiet_until, app._send_text)
        sent, done = [], []
        try:
            app._script_worker = worker
            app._script_quiet_until = 0.0
            app._send_text = lambda raw, **kwargs: sent.append((raw, kwargs)) or True
            worker.send_requested.connect(app._script_send)
            self._run_and_wait(worker, done)
            self.assertEqual(done, [(True, "")])
            self.assertEqual(sent[0][0], "50 49 4E 47")
            self.assertFalse(sent[0][1]["record_macro"])
        finally:
            app._script_worker, app._script_quiet_until, app._send_text = old

    def test_default_template_modbus_frame_has_crc(self):
        """默认模板里的 Modbus 帧必须是带 CRC 的完整帧（与帮助文档示例一致）。"""
        import modbus_master as mm
        from script_console_dialog import _DEFAULT_CODE
        want = mm.build_rtu_request(1, 3, 0, 1).hex(" ").upper()   # 01 03 00 00 00 01 84 0A
        self.assertIn(want, _DEFAULT_CODE)
        self.assertNotIn("hex=False", _DEFAULT_CODE)   # hexs() 已返回 bytes，该参数多余且误导

    def test_stale_finish_does_not_orphan_new_worker(self):
        """竞态回归：上一轮 worker 的迟到 run_finished 不能把新一轮 worker 架空。
        （run_finished 是队列信号，旧信号可能在新一轮已 start 之后才送达）"""
        from script_console_dialog import ScriptConsoleDialog
        from script_console import ScriptWorker
        w = _win()
        d = ScriptConsoleDialog(w)
        old_reg = getattr(w, "_script_worker", None)
        try:
            old, new = ScriptWorker(""), ScriptWorker("")
            d._worker = new
            w._script_worker = new                 # 新一轮已接管收流
            d._on_finished(old, True, "")          # 旧 worker 的迟到完成信号
            self.assertIs(d._worker, new, "新 worker 被旧信号清掉了")
            self.assertIs(w._script_worker, new, "收流被旧信号误释放")
            # 当前 worker 自己的完成信号才真正收尾
            d._on_finished(new, True, "")
            self.assertIsNone(d._worker)
            self.assertIsNone(w._script_worker)
        finally:
            d._worker = None
            w._script_worker = old_reg
            d.deleteLater()

    def test_finish_counts_come_from_signaling_worker(self):
        """通过/失败计数取自发信的 worker，关窗把 self._worker 置空也不会显示成 0/0。"""
        from script_console_dialog import ScriptConsoleDialog
        from script_console import ScriptWorker
        w = _win()
        d = ScriptConsoleDialog(w)
        old_reg = getattr(w, "_script_worker", None)
        try:
            cur = ScriptWorker("")
            cur.checks_passed, cur.checks_failed = 3, 1
            d._worker = cur
            d.txt_out.clear()
            d._on_finished(cur, False, "checks")
            out = d.txt_out.toPlainText()
            self.assertIn("3", out)
            self.assertIn("1", out)
        finally:
            d._worker = None
            w._script_worker = old_reg
            d.deleteLater()

    def test_disconnect_stops_running_script(self):
        """断连要停掉脚本（同自动化序列）：否则脚本对着断掉的连接空跑，每个 expect 等满超时。
        钩子放在 close_conn —— 出错断线 / 用户手动断 / 设备移除 三条路径都经过它。"""
        w = _win()
        from script_console import ScriptWorker
        sw = ScriptWorker("")
        old = (w.conn, w._script_worker, w.toast)
        try:
            w.toast = lambda *a, **k: None
            w.conn = None                        # 已无连接：close_conn 走干净收尾路径
            w._script_worker = sw
            sw.isRunning = lambda: True          # 假装脚本线程在跑
            self.assertFalse(sw.stopping())
            w.close_conn()
            self.assertTrue(sw.stopping(), "断连没有停掉运行中的脚本")
        finally:
            (w.conn, w._script_worker, w.toast) = old

    def test_worker_has_no_qt_parent(self):
        """worker 不能以对话框为 parent：对话框销毁会连带析构仍在运行的 QThread，
        Qt 会 std::terminate() 让进程 abort。靠 Python 引用保命，不靠 Qt 父子链。"""
        from script_console import ScriptWorker
        _win()
        self.assertIsNone(ScriptWorker("").parent())

    def test_unstoppable_worker_is_kept_alive_on_close(self):
        """关窗时停不下来的 worker 要转移到主窗常驻列表续命，避免被析构导致进程 abort。"""
        from script_console_dialog import ScriptConsoleDialog
        from script_console import ScriptWorker
        w = _win()
        d = ScriptConsoleDialog(w)
        n0 = len(w._script_orphans)
        old_reg = getattr(w, "_script_worker", None)
        try:
            stuck = ScriptWorker("")
            stuck.isRunning = lambda: True       # 永远停不下来
            stuck.wait = lambda ms=0: False
            d._worker = stuck
            d.close()
            self.assertEqual(len(w._script_orphans), n0 + 1, "停不下来的 worker 没被续命")
            self.assertIs(w._script_orphans[-1], stuck)
        finally:
            del w._script_orphans[n0:]
            d._worker = None
            w._script_worker = old_reg
            d.deleteLater()

    def test_lib_parse_filters_bad_entries(self):
        from script_console_dialog import ScriptConsoleDialog as D
        good = D.parse_lib('[{"name":"a","code":"x"},{"name":"","code":"y"},'
                           '"junk",{"code":"no name"}]')
        self.assertEqual(good, [{"name": "a", "code": "x"}])
        self.assertEqual(D.parse_lib("not json"), [])
        self.assertEqual(D.parse_lib('{"name":"a"}'), [])      # 非数组

    def test_modbus_master_is_inactive_while_script_registered(self):
        """含 start 前短窗口在内，只要脚本已接管就不能恢复 Modbus 轮询。"""
        w = _win()
        from script_console import ScriptWorker
        old = w._script_worker
        try:
            w._script_worker = ScriptWorker("")
            self.assertFalse(w._mbm_active())
        finally:
            w._script_worker = old

    def test_sequence_refuses_to_start_while_script_registered(self):
        w = _win()
        from script_console import ScriptWorker
        old = (w._script_worker, w._seq_on, w.toast)
        notices = []
        try:
            w._script_worker = ScriptWorker("")
            w._seq_on = False
            w.toast = lambda msg, **kwargs: notices.append(msg)
            w._seq_start([{"on": True, "send": "AT", "expect": ""}])
            self.assertFalse(w._seq_on)
            self.assertTrue(notices)
        finally:
            w._script_worker, w._seq_on, w.toast = old

    def test_sequence_refuses_periodic_and_multi_send(self):
        """序列独占收发流；定时发送或多条循环已运行时不得启动。"""
        w = _win()
        old = (w._seq_on, w.toast)
        notices = []
        try:
            w._seq_on = False
            w.toast = lambda msg, **kwargs: notices.append(msg)
            w.send_timer.start(60000)
            w._seq_start([{"on": True, "send": "", "expect": "OK"}])
            self.assertFalse(w._seq_on)
            w.send_timer.stop()
            w._ms_cycle_timer.start(60000)
            w._seq_start([{"on": True, "send": "", "expect": "OK"}])
            self.assertFalse(w._seq_on)
            self.assertGreaterEqual(len(notices), 2)
        finally:
            w.send_timer.stop()
            w._ms_cycle_timer.stop()
            w._seq_on, w.toast = old

    def test_periodic_and_multi_send_refuse_sequence(self):
        """反向入口同样受统一互斥表约束，不能在序列运行中开启后台发送。"""
        w = _win()
        old = (w._seq_on, w.toast)
        try:
            w._seq_on = True
            w.toast = lambda *args, **kwargs: None
            w.send_timer.stop()
            w._ms_cycle_timer.stop()
            w.on_period_toggled(True)
            self.assertFalse(w.send_timer.isActive())
            w._ms_toggle_cycle()
            self.assertFalse(w._ms_cycle_timer.isActive())
        finally:
            w.send_timer.stop()
            w._ms_cycle_timer.stop()
            w._seq_on, w.toast = old

    def test_periodic_send_and_modbus_master_are_mutually_exclusive(self):
        """定时/循环发送与 Modbus 主机都主动占线，两个方向的开启入口都必须拒绝并发。"""
        w = _win()
        old = (w._mbm_on, w._mbm_inflight, w._mbm_active, w.toast)
        try:
            w.toast = lambda *args, **kwargs: None
            w._mbm_active = lambda: True
            w.send_timer.stop()
            w.on_period_toggled(True)
            self.assertFalse(w.send_timer.isActive())

            w._mbm_active = old[2]
            w._mbm_on = False
            w._mbm_inflight = None
            w.send_timer.start(60000)
            w._set_mbm_enabled(True)
            self.assertFalse(w._mbm_on)
        finally:
            w.send_timer.stop()
            w._mbm_on, w._mbm_inflight, w._mbm_active, w.toast = old

    def test_manual_and_terminal_send_refuse_exclusive_task(self):
        """序列/脚本/传输接管回包期间，主发送框和终端按键均不得插入线路。"""
        w = _win()
        old = (w._seq_on, w.toast, w._is_open, w.conn)
        sent = []
        fake = type("Conn", (), {"send": lambda _self, data, target=None:
                                  sent.append(bytes(data)) or len(data)})()
        try:
            w._seq_on = True
            w.toast = lambda *args, **kwargs: None
            w._is_open = lambda: True
            w.conn = fake
            self.assertFalse(w._send_text("AA", hex_mode=True))
            w._terminal_send(b"A", echo="A")
            self.assertEqual(sent, [])
        finally:
            w._seq_on, w.toast, w._is_open, w.conn = old

    def test_script_combo_overrides_native_on_background(self):
        """Windows 下拉框打开/收起后的 :on 状态不能透出系统青绿色底色。"""
        from script_console_dialog import ScriptConsoleDialog
        d = ScriptConsoleDialog(_win())
        try:
            qss = d.styleSheet()
            self.assertIn("QComboBox#ScScript:on", qss)
            self.assertIn("selection-background-color", qss)
        finally:
            d.deleteLater()

    def test_script_run_button_matches_main_primary_style(self):
        """脚本运行/停止按钮沿用主界面主操作按钮的尺寸和交互状态。"""
        from script_console_dialog import ScriptConsoleDialog
        d = ScriptConsoleDialog(_win())
        try:
            self.assertGreaterEqual(d.btn_run.minimumHeight(), 34)
            self.assertEqual(d.btn_run.minimumSize(), d.btn_stop.minimumSize())
            qss = d.styleSheet()
            self.assertIn("QPushButton#PlotPrimaryBtn:pressed", qss)
            self.assertIn("border-radius: 9px", qss)
            self.assertIn("font-weight: 600", qss)
        finally:
            d.deleteLater()

    def test_script_delete_uses_themed_danger_confirmation(self):
        """删除脚本使用统一主题确认框，并将删除动作标成危险按钮。"""
        from script_console_dialog import ScriptConsoleDialog
        w = _win()
        d = ScriptConsoleDialog(w)
        old_confirm = w._confirm_dlg
        seen = {}
        try:
            d._scripts = [{"name": "A", "code": "a"}, {"name": "B", "code": "b"}]
            d._active = 1
            w._confirm_dlg = lambda *args, **kwargs: seen.update(kwargs) or False
            d._on_delete()
            self.assertTrue(seen.get("danger"))
            self.assertEqual(seen.get("ok_text"), w._t("sc_delete"))
            self.assertEqual(len(d._scripts), 2)
        finally:
            w._confirm_dlg = old_confirm
            d.deleteLater()

    def test_script_run_rejection_shows_themed_popup_and_local_error(self):
        """未连接时弹主题错误框，同时在控制台输出区和底栏留下原因。"""
        from script_console_dialog import ScriptConsoleDialog
        w = _win()
        d = ScriptConsoleDialog(w)
        old = (w._script_start_blocked, w._is_open, w.toast, w._info_dlg)
        notices, popups = [], []
        try:
            w._script_start_blocked = lambda: False
            w._is_open = lambda: False
            w.toast = lambda msg, **kwargs: notices.append((msg, kwargs))
            w._info_dlg = lambda *args, **kwargs: popups.append((args, kwargs))
            d.txt_out.clear()
            d._on_run()
            msg = w._t("net_not_open")
            self.assertIn(msg, d.txt_out.toPlainText())
            self.assertEqual(d.lbl_status.text(), msg)
            self.assertIn("color", d.lbl_status.styleSheet())
            self.assertTrue(notices)
            self.assertEqual(len(popups), 1)
            self.assertTrue(popups[0][1].get("is_error"))
            self.assertIsNone(d._worker)
        finally:
            w._script_start_blocked, w._is_open, w.toast, w._info_dlg = old
            d.deleteLater()

    def test_shared_dialog_combo_popup_uses_neutral_palette(self):
        """波形图/仪表盘/桥接/Modbus 共用样式应同时覆盖 :on 和独立弹出容器。"""
        from PyQt5.QtWidgets import QDialog, QComboBox, QVBoxLayout
        from dialogs import _dialog_list_qss, _style_combo_popups
        from theme import chrome_for
        root = QDialog()
        combo = QComboBox(root)
        combo.addItems(["A", "B"])
        QVBoxLayout(root).addWidget(combo)
        c = chrome_for(_win()._theme_id())
        try:
            qss = _dialog_list_qss(c)
            self.assertIn("QComboBox:on", qss)
            self.assertIn("selection-background-color", qss)
            _style_combo_popups(root, c)
            self.assertIn(c["combo_dropdown_bg"], combo.view().window().styleSheet())
        finally:
            root.deleteLater()


class MacroRecorderTests(unittest.TestCase):
    """宏录制：事件采集 + 翻译成脚本代码。纯逻辑，无需 Qt。"""

    def _r(self):
        from macro_recorder import MacroRecorder
        r = MacroRecorder()
        r.start()
        return r

    def test_not_recording_drops_events(self):
        from macro_recorder import MacroRecorder
        r = MacroRecorder()
        r.on_tx(b"AT")                      # 未 start → 不采集
        self.assertEqual(len(r), 0)

    def test_tx_rx_pair_becomes_send_expect_check(self):
        r = self._r()
        r.on_tx(b"AT\r\n", t=10.0)
        r.on_rx(b"OK\r\n", t=10.05)
        r.stop()
        code = r.to_script()
        self.assertIn('send("AT\\r\\n")', code)
        self.assertIn("r = expect(", code)
        self.assertIn('"OK\\r\\n"', code)
        self.assertIn("check(r is not None", code)

    def test_binary_uses_hexs(self):
        r = self._r()
        r.on_tx(bytes([0x01, 0x03, 0x00, 0xFF]), t=1.0)
        r.stop()
        self.assertIn('send(hexs("01 03 00 FF"))', r.to_script())

    def test_gap_becomes_sleep(self):
        r = self._r()
        r.on_tx(b"A", t=1.0)
        r.on_tx(b"B", t=1.5)                # 间隔 500ms → 补 sleep
        r.stop()
        code = r.to_script()
        self.assertIn("sleep(500)", code)

    def test_small_gap_no_sleep(self):
        r = self._r()
        r.on_tx(b"A", t=1.0)
        r.on_tx(b"B", t=1.01)               # 10ms < gap_ms(50) → 不补
        r.stop()
        self.assertNotIn("sleep(", r.to_script())

    def test_timeout_scales_with_latency(self):
        r = self._r()
        r.on_tx(b"A", t=1.0)
        r.on_rx(b"R", t=1.5)                # 500ms 延迟 → 超时留余量且 >500
        r.stop()
        import re as _re
        m = _re.search(r"timeout=(\d+)", r.to_script())
        self.assertIsNotNone(m)
        self.assertGreater(int(m.group(1)), 500)

    def test_multiple_rx_merged_into_one_expect(self):
        r = self._r()
        r.on_tx(b"A", t=1.0)
        r.on_rx(b"12", t=1.01)
        r.on_rx(b"34", t=1.02)              # 同一次发送后的多包合并
        r.stop()
        code = r.to_script()
        self.assertEqual(code.count("expect("), 1)
        self.assertIn('"1234"', code)

    def test_unsolicited_rx_becomes_comment(self):
        r = self._r()
        r.on_rx(b"BOOT", t=1.0)             # 没有对应发送 → 只记注释
        r.stop()
        code = r.to_script()
        self.assertIn("# 收到(无对应发送)", code)
        self.assertNotIn("expect(", code)

    def test_empty_recording(self):
        r = self._r()
        r.stop()
        self.assertIn("未录到任何收发", r.to_script())

    def test_event_cap_marks_truncated(self):
        from macro_recorder import MacroRecorder
        r = MacroRecorder(max_events=3)
        r.start()
        for i in range(10):
            r.on_tx(b"X", t=float(i))
        r.stop()
        self.assertEqual(len(r), 3)
        self.assertTrue(r.truncated)
        self.assertIn("超过上限", r.to_script())

    def test_generated_script_is_valid_python(self):
        """生成的代码必须能编译（否则录完直接跑就报语法错）。"""
        r = self._r()
        r.on_tx(b'say "hi"\\\r\n', t=1.0)   # 含引号/反斜杠/CR LF，考验转义
        r.on_rx(bytes([0x00, 0xFF]), t=1.2)
        r.on_tx(b"AT", t=2.0)
        r.stop()
        compile(r.to_script(), "<gen>", "exec")

    def test_generated_script_respects_library_limit(self):
        r = self._r()
        for i in range(20):
            r.on_tx(bytes([i]) * 4096, t=float(i))
        r.stop()
        code = r.to_script(max_chars=2000)
        self.assertLessEqual(len(code), 2000)
        self.assertIn("超过脚本库上限", code)
        compile(code, "<limited-gen>", "exec")

    def test_counts(self):
        r = self._r()
        r.on_tx(b"A", t=1.0)
        r.on_rx(b"B", t=1.1)
        r.on_rx(b"C", t=1.2)
        self.assertEqual((r.tx_count, r.rx_count), (1, 2))


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class MacroRecorderIntegrationTests(unittest.TestCase):
    """录制与主窗的接线：手动发送/收包被录，脚本自身的发送不被录。"""

    def test_rx_recorded_only_while_recording(self):
        w = _win()
        rec = w._macro
        old = (rec.recording, w._script_worker)
        try:
            rec.clear()
            rec.recording = False
            w.on_data_received(b"junk")
            self.assertEqual(len(rec), 0)
            rec.start()
            w.on_data_received(b"HELLO")
            self.assertEqual(rec.rx_count, 1)
        finally:
            rec.stop(); rec.clear()
            (rec.recording, w._script_worker) = old

    def _dlg(self):
        """建对话框，并记下 settings 里的脚本库以便测试后还原
        （对话框的 _save_cfg 会写 settings，不还原会污染后续用例）。"""
        from script_console_dialog import ScriptConsoleDialog
        w = _win()
        self._saved_lib = (w.settings.value("script_lib", ""),
                           w.settings.value("script_active", ""))
        return ScriptConsoleDialog(w)

    def _restore_lib(self):
        w = _win()
        lib, active = getattr(self, "_saved_lib", ("", ""))
        w.settings.setValue("script_lib", lib)
        w.settings.setValue("script_active", active)

    def test_full_library_keeps_recording_for_retry(self):
        """库满时不能先 clear 再报错 —— 录到的东西要留着，腾出空位后能重试保存。"""
        from script_console_dialog import _MAX_SCRIPTS
        w = _win()
        rec = w._macro
        d = self._dlg()
        try:
            d._scripts = [{"name": "s%d" % i, "code": "log(1)"} for i in range(_MAX_SCRIPTS)]
            rec.clear(); rec.start()
            rec.on_tx(b"AT\r\n", t=1.0); rec.on_rx(b"OK", t=1.05)
            d._on_record()                       # 停止 → 库满，应保留数据
            self.assertFalse(rec.recording)
            self.assertGreater(len(rec), 0, "库满时录制数据被清掉了")
            n_before = len(d._scripts)
            # 腾出空位后再点一次 → 当作「重试保存」，而不是开新一轮把数据清掉
            d._scripts.pop()
            d._on_record()
            self.assertEqual(len(d._scripts), n_before)   # 删1加1
            self.assertEqual(len(rec), 0, "重试保存后应已消费掉录制数据")
            self.assertIn("send(", d.ed_code.toPlainText())
        finally:
            rec.stop(); rec.clear()
            self._restore_lib()
            d.deleteLater()

    def test_full_library_refuses_to_start(self):
        """库满时直接拒绝开始录制，别让用户白录一场。"""
        from script_console_dialog import _MAX_SCRIPTS
        w = _win()
        rec = w._macro
        d = self._dlg()
        try:
            rec.clear()
            d._scripts = [{"name": "s%d" % i, "code": "log(1)"} for i in range(_MAX_SCRIPTS)]
            d._on_record()
            self.assertFalse(rec.recording, "库满仍然开始了录制")
        finally:
            rec.stop(); rec.clear()
            self._restore_lib()
            d.deleteLater()

    def test_retranslate_keeps_recording_ui(self):
        """录制中切语言/配置：按钮样式(红)、运行禁用、状态栏文案都要保持录制态。"""
        w = _win()
        rec = w._macro
        d = self._dlg()
        try:
            rec.clear()
            d._on_record()                       # 开始录制
            self.assertTrue(rec.recording)
            d.retranslate()                      # 模拟切语言
            self.assertEqual(d.btn_rec.objectName(), "PlotDangerBtn")
            self.assertFalse(d.btn_run.isEnabled())
            self.assertEqual(d.lbl_status.text(), w._t("sc_rec_running"))
        finally:
            rec.stop(); rec.clear()
            self._restore_lib()
            d.deleteLater()

    def test_status_priority(self):
        """状态文案优先级：录制中 > 运行中 > 普通。"""
        w = _win()
        rec = w._macro
        d = self._dlg()
        try:
            rec.clear()
            self.assertEqual(d._status_key(), "sc_hint")
            self.assertEqual(d._status_key(running=True), "sc_running")
            rec.start()
            self.assertEqual(d._status_key(running=True), "sc_rec_running")
        finally:
            rec.stop(); rec.clear()
            self._restore_lib()
            d.deleteLater()

    def test_autoreply_sends_not_recorded(self):
        """自动应答/Modbus 从机的回复也走 _send_text，但不是用户手动发 —— 必须被 _ar_in_flight
        排除，否则录制期间开着自动应答，设备每次回包触发的自动回复都会被录成多余的 send()。
        直接调生产入口 _macro_record_tx（不复制钩子条件，条件变了测试自动跟着变）。"""
        w = _win()
        rec = w._macro
        old = (rec.recording, w._ar_in_flight)
        try:
            rec.clear(); rec.start()
            w._ar_in_flight = False
            w._macro_record_tx(b"MANUAL")                # 手动发 → 应录
            self.assertEqual(rec.tx_count, 1)
            w._ar_in_flight = True
            w._macro_record_tx(b"AUTO-REPLY")            # 自动应答/Modbus 发 → 不应录
            self.assertEqual(rec.tx_count, 1, "自动应答的回复被错误录进宏脚本")
        finally:
            rec.stop(); rec.clear()
            (rec.recording, w._ar_in_flight) = old

    def test_sequence_sends_not_recorded(self):
        """自动化序列调用通用发送入口时不能被当成用户手动 TX。"""
        w = _win()
        rec = w._macro
        old = w._seq_on
        try:
            rec.clear(); rec.start()
            w._seq_on = True
            w._macro_record_tx(b"AUTO-SEQUENCE")
            self.assertEqual(rec.tx_count, 0)
        finally:
            w._seq_on = old
            rec.stop(); rec.clear()

    def test_modbus_send_sets_in_flight(self):
        """Modbus 从机响应经 _modbus_send → _send_text，是另一条独立发送路径，
        必须同样置 _ar_in_flight，否则从机响应被录进宏脚本。"""
        w = _win()
        old = (w._ar_on, w._is_open, w._send_text, w._ar_in_flight)
        seen = {}
        try:
            w._ar_on = True
            w._is_open = lambda: True
            # 在 _send_text 内部快照 _ar_in_flight —— 发送那一刻标记必须是 True
            w._send_text = lambda *a, **k: seen.__setitem__("flag", w._ar_in_flight) or True
            w._modbus_send(bytes([0x01, 0x03, 0x02, 0x00, 0x64]))
            self.assertTrue(seen.get("flag"), "Modbus 响应发送时 _ar_in_flight 不是 True")
            self.assertFalse(w._ar_in_flight, "_modbus_send 后 _ar_in_flight 没复位")
        finally:
            (w._ar_on, w._is_open, w._send_text, w._ar_in_flight) = old

    def test_ar_in_flight_reset_after_send(self):
        """标记必须在 finally 里复位，否则一次自动应答后所有手动发送都不再被录。"""
        w = _win()
        old = (w._ar_in_flight, w.conn, w.toast)
        try:
            w.toast = lambda *a, **k: None
            w._ar_in_flight = False
            w.conn = None                       # 无连接 → _ar_schedule_send 内部走异常/早退
            try:
                w._ar_schedule_send(["AA"], False, None, 0, None)
            except Exception:
                pass
            self.assertFalse(w._ar_in_flight, "_ar_in_flight 没有复位")
        finally:
            (w._ar_in_flight, w.conn, w.toast) = old

    def test_script_sends_not_recorded(self):
        """脚本运行期间的收发不录 —— 否则录到的是脚本自己发的，自指。"""
        w = _win()
        rec = w._macro
        old = w._script_worker
        try:
            rec.clear(); rec.start()
            class FakeW:
                def isRunning(self): return True
                def feed(self, d): pass
            w._script_worker = FakeW()
            w.on_data_received(b"FROM-SCRIPT")
            self.assertEqual(len(rec), 0)
        finally:
            w._script_worker = old
            rec.stop(); rec.clear()


class SendDslTests(unittest.TestCase):
    """命令 DSL 编译：指令解析 / 重复展开 / 边界与错误。纯逻辑，无需 Qt。"""

    def _c(self, text, **kw):
        import send_dsl
        return send_dsl.compile_dsl(text, **kw)

    def test_has_dsl(self):
        import send_dsl
        self.assertTrue(send_dsl.has_dsl(r"AT\!(Delay100)"))
        self.assertFalse(send_dsl.has_dsl("AT+VER"))
        self.assertFalse(send_dsl.has_dsl(""))

    def test_delay_between_segments(self):
        import send_dsl
        ops = self._c(r"AT\!(Delay500)BT")
        self.assertEqual([o for o, _a in ops],
                         [send_dsl.OP_SEND, send_dsl.OP_DELAY, send_dsl.OP_SEND])
        self.assertEqual(ops[1][1], 500)

    def test_wait_is_delay_alias(self):
        import send_dsl
        ops = self._c(r"A\!(Wait50)B")
        self.assertEqual(ops[1], (send_dsl.OP_DELAY, 50))

    def test_case_and_space_tolerant(self):
        import send_dsl
        ops = self._c(r"A\!( delay 250 )B")
        self.assertEqual(ops[1], (send_dsl.OP_DELAY, 250))

    def test_repeat_expands_following_ops(self):
        import send_dsl
        ops = self._c(r"\!(Repeat3)PING\!(Delay200)")
        self.assertEqual(len(ops), 6)
        self.assertEqual(sum(1 for o, _a in ops if o == send_dsl.OP_SEND), 3)

    def test_repeat_only_repeats_what_follows(self):
        """Repeat 之前的内容只发一次。"""
        import send_dsl
        ops = self._c(r"HEAD\!(Repeat2)X")
        sends = [a[0] for o, a in ops if o == send_dsl.OP_SEND]
        self.assertEqual(sends, ["HEAD", "X", "X"])

    def test_hex_text_switch(self):
        ops = self._c(r"\!(Hex)01 02\!(Text)hi")
        payloads = [a for o, a in ops if o == "send"]
        self.assertEqual(payloads[0][1], True)     # hex 段
        self.assertEqual(payloads[1][1], False)    # text 段

    def test_hex_text_reject_numeric_suffix(self):
        import send_dsl
        for bad in (r"\!(Hex1)01", r"\!(Text99)hello"):
            with self.assertRaises(send_dsl.DslError, msg=bad):
                self._c(bad)

    def test_default_hex_mode_is_none(self):
        """不写 Hex/Text 时留 None，由主界面开关决定，不在编译期定死。"""
        ops = self._c(r"A\!(Delay10)B")
        self.assertIsNone(ops[0][1][1])

    def test_errors(self):
        import send_dsl
        for bad in (r"\!(Delay)X", r"\!(Repeat)X", r"\!(Repeat0)X",
                    r"\!(Nope)X", r"\!(Delay100)", r"\!(Repeat2)",
                    r"HEAD\!(Repeat1)", r"A\!(Delay-1)B", r"A\!(Delay500"):
            with self.assertRaises(send_dsl.DslError, msg=bad):
                self._c(bad)

    def test_malformed_marker_is_detected_before_send(self):
        import send_dsl
        self.assertTrue(send_dsl.has_dsl(r"A\!(Delay-1)B"))
        with self.assertRaises(send_dsl.DslError):
            self._c(r"A\!(Delay-1)B\!(Delay1)C")

    def test_repeat_twice_rejected(self):
        import send_dsl
        with self.assertRaises(send_dsl.DslError):
            self._c(r"\!(Repeat2)A\!(Repeat3)B")

    def test_limits(self):
        import send_dsl
        with self.assertRaises(send_dsl.DslError):
            self._c(r"\!(Repeat999999)X")          # 次数上限
        with self.assertRaises(send_dsl.DslError):
            self._c(r"A\!(Delay999999999)B")       # 延时上限
        from unittest.mock import patch
        with patch.object(send_dsl, "_MAX_OPS", 3):
            with self.assertRaises(send_dsl.DslError):
                self._c(r"A\!(Delay0)B\!(Delay0)C")

    def test_describe(self):
        import send_dsl
        ops = self._c(r"A\!(Delay100)B\!(Delay50)C")
        self.assertEqual(send_dsl.describe(ops), (3, 150))

    def test_send_box_tip_documents_dsl(self):
        """发送框悬浮提示必须介绍 DSL —— 用户在那里查动态字段，不该不知道还能写时序指令。"""
        import i18n
        for lang in ("zh", "en", "zh_tw"):
            tip = i18n.TR[lang]["send_box_tip"]
            self.assertIn("DSL", tip, lang)
            for tok in (r"\!(Delay", r"\!(Repeat", r"\!(Hex)", r"\!(Text)"):
                self.assertIn(tok, tip, "%s 缺 %s" % (lang, tok))

    def test_tip_examples_actually_compile(self):
        """提示里给的示例必须真能跑 —— 否则改了语法忘改文档，用户照抄就报错。"""
        import re, i18n, send_dsl
        for lang in ("zh", "en", "zh_tw"):
            tip = i18n.TR[lang]["send_box_tip"]
            # 取 DSL 小节里出现指令的示例行（行首缩进或「示例/範例/Example:」引出）
            examples = [ln.strip().split("：", 1)[-1].split(": ", 1)[-1].strip()
                        for ln in tip.splitlines()
                        if r"\!(" in ln and not ln.strip().startswith(r"\!(Delay500)  ")]
            examples = [e for e in examples if re.match(r"^[^ ]", e) and "  " not in e]
            self.assertTrue(examples, "%s 未找到可校验的示例" % lang)
            for ex in examples:
                self.assertNotIn(r"\r", ex, "%s 示例不应暗示文本模式会解析 C 转义" % lang)
                self.assertNotIn(r"\n", ex, "%s 示例不应暗示文本模式会解析 C 转义" % lang)
                try:
                    send_dsl.compile_dsl(ex)
                except send_dsl.DslError as err:
                    self.fail("%s 提示里的示例编译失败: %r (%s)" % (lang, ex, err))

    def test_escaped_backslash_not_an_instruction(self):
        r"""\\!(...) 是转义，当成字面量 \!(...) 发送，不当作指令。"""
        import send_dsl
        ops = self._c(r"AT\\!(Delay100)BT")
        sends = [a[0] for o, a in ops if o == send_dsl.OP_SEND]
        self.assertEqual(sends, [r"AT\!(Delay100)BT"])
        self.assertEqual(len([o for o, _a in ops if o == send_dsl.OP_DELAY]), 0)

    def test_escaped_backslash_before_real_instruction(self):
        r"""\\ 后跟 \!(...) 指令：\\→字面量 \，指令照常生效。"""
        import send_dsl
        ops = self._c(r"\\\!(Delay200)X")
        sends = [a[0] for o, a in ops if o == send_dsl.OP_SEND]
        delays = [a for o, a in ops if o == send_dsl.OP_DELAY]
        self.assertEqual(sends, ["\\", "X"])
        self.assertEqual(delays, [200])

    def test_escaped_has_dsl_still_true(self):
        """含 \\!(...) 的文本 has_dsl 仍返回 True，走 DSL 路径由 compile_dsl 妥善处理。"""
        import send_dsl
        self.assertTrue(send_dsl.has_dsl(r"\\!(Delay100)"))


class RecReplayTests(unittest.TestCase):
    """数据录制/回放引擎：采集 / 存盘载入往返 / 回放时序。纯逻辑，无需 Qt。"""

    def _rec(self):
        import rec_replay
        r = rec_replay.StreamRecorder()
        r.start()
        return r

    def test_records_relative_time(self):
        r = self._rec()
        r.on_rx(b"A", t=100.0)
        r.on_tx(b"B", t=100.5)
        r.stop()
        self.assertEqual([(round(t, 2), d, b) for t, d, b in r.events],
                         [(0.0, "rx", b"A"), (0.5, "tx", b"B")])
        self.assertEqual((r.rx_count, r.tx_count), (1, 1))

    def test_not_recording_drops(self):
        import rec_replay
        r = rec_replay.StreamRecorder()
        r.on_rx(b"A")
        self.assertEqual(len(r), 0)

    def test_event_cap(self):
        import rec_replay
        r = rec_replay.StreamRecorder(max_events=3)
        r.start()
        for i in range(10):
            r.on_rx(b"X", t=float(i))
        self.assertEqual(len(r), 3)
        self.assertTrue(r.truncated)

    def test_large_chunk_is_split_without_losing_bytes(self):
        import rec_replay
        from unittest.mock import patch
        r = rec_replay.StreamRecorder()
        r.start()
        with patch.object(rec_replay, "_MAX_CHUNK", 2):
            r.on_rx(b"ABCDE", t=1.0)
        self.assertEqual([b for _t, _d, b in r.events], [b"AB", b"CD", b"E"])
        self.assertEqual(b"".join(b for _t, _d, b in r.events), b"ABCDE")
        self.assertEqual({t for t, _d, _b in r.events}, {0.0})
        self.assertFalse(r.truncated)

    def test_save_load_roundtrip(self):
        import rec_replay, tempfile, os
        r = self._rec()
        r.on_rx(b"\x01\x02", t=1.0)
        r.on_tx(b"OK", t=1.25)
        r.stop()
        p = os.path.join(tempfile.mkdtemp(), "t.ctrec")
        r.save(p, note="unit")
        events, header = rec_replay.load(p)
        self.assertEqual(header.get("note"), "unit")
        self.assertEqual(events, [(0.0, "rx", b"\x01\x02"), (0.25, "tx", b"OK")])
        os.remove(p)

    def test_load_rejects_non_ctrec(self):
        import rec_replay, tempfile, os
        p = os.path.join(tempfile.mkdtemp(), "x.ctrec")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"hello": 1}\n')
        with self.assertRaises(rec_replay.RecordError):
            rec_replay.load(p)
        os.remove(p)

    def test_load_skips_bad_lines(self):
        """录制文件常被手改，坏行跳过而不是整体失败。"""
        import rec_replay, tempfile, os
        p = os.path.join(tempfile.mkdtemp(), "x.ctrec")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"_": "ctrec", "v": 1}\n')
            f.write('{"t": 0, "d": "rx", "b": "41"}\n')
            f.write('not json\n')
            f.write('{"t": 1, "d": "rx", "b": "ZZ"}\n')     # 非法 hex
            f.write('{"t": "NaN", "d": "rx", "b": "43"}\n')
            f.write('{"t": 1, "d": "bad", "b": "43"}\n')
            f.write('{"t": 1, "d": "rx", "b": ""}\n')
            f.write('{"t": 2, "d": "rx", "b": "42"}\n')
        events, header = rec_replay.load(p)
        self.assertEqual([b for _t, _d, b in events], [b"A", b"B"])
        self.assertEqual(header["bad_lines"], 5)
        os.remove(p)

    def test_load_rejects_unknown_version_and_event_overflow(self):
        import rec_replay, tempfile, os
        from unittest.mock import patch
        p = os.path.join(tempfile.mkdtemp(), "x.ctrec")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"_": "ctrec", "v": 2}\n')
        with self.assertRaises(rec_replay.RecordError):
            rec_replay.load(p)
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"_": "ctrec", "v": 1}\n')
            f.write('{"t": 0, "d": "rx", "b": "41"}\n')
            f.write('{"t": 1, "d": "rx", "b": "42"}\n')
        with patch.object(rec_replay, "_MAX_EVENTS", 1):
            with self.assertRaises(rec_replay.RecordError):
                rec_replay.load(p)
        os.remove(p)

    def test_load_skips_oversized_event(self):
        import rec_replay, tempfile, os
        from unittest.mock import patch
        p = os.path.join(tempfile.mkdtemp(), "x.ctrec")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"_": "ctrec", "v": 1}\n')
            f.write('{"t": 0, "d": "rx", "b": "41 42 43"}\n')
            f.write('{"t": 1, "d": "rx", "b": "44"}\n')
        with patch.object(rec_replay, "_MAX_CHUNK", 2):
            events, header = rec_replay.load(p)
        self.assertEqual(events, [(1.0, "rx", b"D")])
        self.assertEqual(header["bad_lines"], 1)
        os.remove(p)

    def test_load_handles_leading_blank_lines(self):
        """.ctrec 文件头前有空行不该导致整份文件被拒。"""
        import rec_replay, tempfile, os
        p = os.path.join(tempfile.mkdtemp(), "x.ctrec")
        with open(p, "w", encoding="utf-8") as f:
            f.write('\n')                            # 手改时常在文件头前留空行
            f.write('\n')
            f.write('{"_": "ctrec", "v": 1}\n')
            f.write('{"t": 0, "d": "rx", "b": "41"}\n')
        events, header = rec_replay.load(p)
        self.assertEqual(header.get("v"), 1)
        self.assertEqual([b for _t, _d, b in events], [b"A"])
        os.remove(p)

    def test_player_respects_timing(self):
        import rec_replay
        got = []
        p = rec_replay.Player([(0.0, "rx", b"A"), (1.0, "rx", b"B")], got.append)
        p.start(now=0.0)
        p.tick(0.0)
        self.assertEqual(got, [b"A"])          # 只派发已到期的
        p.tick(0.5)
        self.assertEqual(got, [b"A"])          # 还没到 1.0s
        p.tick(1.0)
        self.assertEqual(got, [b"A", b"B"])
        self.assertTrue(p.finished)

    def test_player_speed(self):
        import rec_replay
        got = []
        p = rec_replay.Player([(0.0, "rx", b"A"), (1.0, "rx", b"B")], got.append, speed=2.0)
        p.start(now=0.0)
        p.tick(0.5)                            # 2 倍速 → 0.5s 已相当于 1.0s
        self.assertEqual(got, [b"A", b"B"])

    def test_player_caps_each_tick_to_avoid_ui_event_storm(self):
        import rec_replay
        from unittest.mock import patch
        got = []
        events = [(0.0, "rx", bytes([i])) for i in range(4)]
        p = rec_replay.Player(events, got.append)
        p.start(now=0.0)
        with patch.object(rec_replay, "_MAX_TICK_EVENTS", 2):
            self.assertEqual(p.tick(0.0), 2)
            self.assertFalse(p.finished)
            self.assertEqual(p.tick(0.0), 2)
        self.assertTrue(p.finished)
        self.assertEqual(got, [b"\x00", b"\x01", b"\x02", b"\x03"])

    def test_player_skips_tx_by_default(self):
        """默认只回放 RX：回放我方发的会造成自问自答。"""
        import rec_replay
        events = [(0.0, "rx", b"A"), (0.1, "tx", b"B")]
        self.assertEqual(len(rec_replay.Player(events, lambda b: None)), 1)
        self.assertEqual(len(rec_replay.Player(events, lambda b: None, include_tx=True)), 2)

    def test_player_loop(self):
        import rec_replay
        got = []
        p = rec_replay.Player([(0.0, "rx", b"A")], got.append, loop=True)
        p.start(now=0.0)
        p.tick(0.0)
        p.tick(0.1)
        self.assertFalse(p.finished)
        self.assertGreaterEqual(len(got), 2)

    def test_player_inject_failure_does_not_break(self):
        """注入失败（连接已关）不该打断回放收尾。"""
        import rec_replay

        def boom(_b):
            raise RuntimeError("closed")

        p = rec_replay.Player([(0.0, "rx", b"A")], boom)
        p.start(now=0.0)
        p.tick(0.0)
        self.assertTrue(p.finished)


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class VirtualConnTests(unittest.TestCase):
    """虚拟连接（离线模式）：接口契约 / 回环 / 注入。"""

    def _conn(self, loopback=False):
        from virtual_io import VirtualConn
        _win()
        return VirtualConn(loopback=loopback)

    def test_open_close_state(self):
        c = self._conn()
        states = []
        c.state_changed.connect(states.append)
        self.assertTrue(c.open())
        self.assertTrue(c.is_open)
        c.close()
        self.assertFalse(c.is_open)
        self.assertEqual(states, [True, False])

    def test_send_when_closed_is_noop(self):
        c = self._conn()
        self.assertEqual(c.send(b"X"), 0)

    def test_send_counts_and_logs(self):
        c = self._conn()
        c.open()
        self.assertEqual(c.send(b"ABC"), 3)
        self.assertEqual(c.tx_log, [b"ABC"])

    def test_loopback_is_async(self):
        """回环必须延到下一轮事件循环：同步 emit 会在 _send_text 中途重入收包路径。"""
        from PyQt5.QtCore import QTimer, QEventLoop
        c = self._conn(loopback=True)
        c.open()
        got = []
        c.data_received.connect(got.append)
        c.send(b"HI")
        self.assertEqual(got, [], "回环同步回灌了")
        loop = QEventLoop(); QTimer.singleShot(60, loop.quit); loop.exec_()
        self.assertEqual(got, [b"HI"])

    def test_no_loopback_no_echo(self):
        from PyQt5.QtCore import QTimer, QEventLoop
        c = self._conn(loopback=False)
        c.open()
        got = []
        c.data_received.connect(got.append)
        c.send(b"HI")
        loop = QEventLoop(); QTimer.singleShot(60, loop.quit); loop.exec_()
        self.assertEqual(got, [])

    def test_inject_delivers_as_rx(self):
        from PyQt5.QtCore import QTimer, QEventLoop
        c = self._conn()
        c.open()
        got = []
        c.data_received.connect(got.append)
        c.inject(b"FROM-DEVICE")
        loop = QEventLoop(); QTimer.singleShot(60, loop.quit); loop.exec_()
        self.assertEqual(got, [b"FROM-DEVICE"])

    def test_inject_after_close_dropped(self):
        from PyQt5.QtCore import QTimer, QEventLoop
        c = self._conn()
        c.open()
        got = []
        c.data_received.connect(got.append)
        c.inject(b"X")
        c.close()                       # 派发前就关掉 → 应丢弃
        loop = QEventLoop(); QTimer.singleShot(60, loop.quit); loop.exec_()
        self.assertEqual(got, [])

    def test_registered_as_conn_type(self):
        from virtual_io import PROTO_VIRTUAL
        from main_window import CONN_TYPES
        self.assertIn(PROTO_VIRTUAL, CONN_TYPES)


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class OfflineIntegrationTests(unittest.TestCase):
    """虚拟连接 + 录制/回放 + DSL 在主窗里的接线。"""

    def _virtual(self, loopback=False):
        from virtual_io import PROTO_VIRTUAL
        w = _win()
        w.cb_proto.setCurrentText(PROTO_VIRTUAL)
        w._update_net_fields()
        w.sw_vconn_loop.setChecked(loopback, animate=False)
        w.open_conn()
        return w

    @staticmethod
    def _pump(ms=60):
        from PyQt5.QtCore import QTimer, QEventLoop
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec_()

    def test_virtual_open_close(self):
        w = self._virtual()
        try:
            from virtual_io import VirtualConn
            self.assertIsInstance(w.conn, VirtualConn)
            self.assertTrue(w.conn.is_open)
        finally:
            w.close_conn()
        self.assertIsNone(w.conn)

    def test_replay_target_only_virtual(self):
        """回放只能注入虚拟连接；真实连接/未连接一律返回 None 让调用方拒绝。"""
        w = _win()
        old = w.conn
        try:
            w.conn = None
            self.assertIsNone(w._replay_inject_target())
            w2 = self._virtual()
            self.assertIsNotNone(w2._replay_inject_target())
            w2.close_conn()
        finally:
            w.conn = old

    def test_record_captures_rx_and_tx(self):
        w = self._virtual()
        r = w._recorder
        try:
            r.clear(); r.start()
            w.conn.inject(b"DEV"); self._pump()
            w._send_text("41", hex_mode=True, newline=0, checksum=0)
            self._pump()
            r.stop()
            self.assertEqual(r.rx_count, 1)
            self.assertEqual(r.tx_count, 1)
        finally:
            r.stop(); r.clear(); w.close_conn()

    def test_recording_counts_as_io_task(self):
        w = self._virtual()
        r = w._recorder
        try:
            r.clear(); r.start()
            self.assertTrue(w._io_task_busy())
            r.stop()
            self.assertFalse(w._io_task_busy(exclude=("modbus",)))
        finally:
            r.stop(); r.clear(); w.close_conn()

    def test_closing_record_dialog_keeps_capture_for_save(self):
        """关闭录制窗口等同于停止按钮：本次数据仍要留在对话框里，重开后可保存。"""
        from rec_replay_dialog import RecReplayDialog
        w = self._virtual()
        r = w._recorder
        dlg = RecReplayDialog(w)
        try:
            r.clear(); r.start()
            r.on_rx(b"CAPTURE", t=1.0)
            dlg.close()
            self.assertFalse(r.recording)
            self.assertEqual(dlg._events, r.events)
            self.assertEqual(dlg._src_name, w._t("rr_src_live"))
        finally:
            r.stop(); r.clear(); dlg.deleteLater(); w.close_conn()

    def test_disconnect_stops_replay_and_releases_busy_state(self):
        """回放绑定旧虚拟连接；断连必须停定时器并释放 replay 占用态。"""
        from rec_replay_dialog import RecReplayDialog
        w = self._virtual()
        old_dlg = w._rr_dlg
        dlg = RecReplayDialog(w)
        w._rr_dlg = dlg
        try:
            dlg._events = [(0.0, "rx", b"A"), (60.0, "rx", b"B")]
            dlg.chk_loop.setChecked(True)
            dlg._on_play()
            self.assertTrue(dlg.is_playing())
            self.assertTrue(w._replay_on)
            self.assertTrue(dlg._timer.isActive())
            w.close_conn()
            self.assertFalse(dlg.is_playing())
            self.assertFalse(w._replay_on)
            self.assertFalse(dlg._timer.isActive())
        finally:
            w._rr_dlg = old_dlg
            dlg.close(); dlg.deleteLater(); w.close_conn()

    def test_disconnect_stops_recording_and_keeps_capture(self):
        """录制跨断连继续会混入下一会话；断连时应停止并保留当前现场。"""
        from rec_replay_dialog import RecReplayDialog
        w = self._virtual()
        old_dlg = w._rr_dlg
        dlg = RecReplayDialog(w)
        w._rr_dlg = dlg
        r = w._recorder
        try:
            r.clear(); r.start(); r.on_rx(b"A", t=1.0)
            w.close_conn()
            self.assertFalse(r.recording)
            self.assertEqual(dlg._events, [(0.0, "rx", b"A")])
        finally:
            r.stop(); r.clear(); w._rr_dlg = old_dlg
            dlg.close(); dlg.deleteLater(); w.close_conn()

    def test_recording_count_refreshes_on_main_rate_tick(self):
        """录制中的事件数应随主窗 1Hz 定时器刷新，不能一直显示启动时的 0。"""
        from rec_replay_dialog import RecReplayDialog
        w = self._virtual()
        old_dlg = w._rr_dlg
        dlg = RecReplayDialog(w)
        w._rr_dlg = dlg
        r = w._recorder
        try:
            dlg.show(); self._pump(10)
            r.clear(); r.start(); dlg._refresh_stat()
            r.on_rx(b"A", t=1.0)
            w._tick_rate()
            self.assertEqual(dlg.lbl_rec_stat.text(), w._t("rr_recording", n=1))
        finally:
            r.stop(); r.clear(); w._rr_dlg = old_dlg
            dlg.close(); dlg.deleteLater(); w.close_conn()

    def test_record_and_replay_refuse_active_modbus_master(self):
        """录制/回放不会暂停 Modbus 主机，因此从这一侧启动时也必须遵守互斥。"""
        from rec_replay_dialog import RecReplayDialog
        from unittest.mock import patch
        w = self._virtual()
        dlg = RecReplayDialog(w)
        dlg._events = [(0.0, "rx", b"A")]
        try:
            with patch.object(w, "_mbm_active", return_value=True):
                dlg._on_rec()
                self.assertFalse(w._recorder.recording)
                dlg._on_play()
                self.assertIsNone(dlg._player)
                self.assertFalse(w._replay_on)
        finally:
            w._recorder.stop(); dlg.close(); dlg.deleteLater(); w.close_conn()

    def test_recording_locks_file_and_replay_controls(self):
        from rec_replay_dialog import RecReplayDialog
        w = self._virtual()
        dlg = RecReplayDialog(w)
        try:
            dlg._on_rec()
            self.assertTrue(w._recorder.recording)
            self.assertTrue(dlg.btn_rec.isEnabled())
            for control in (dlg.btn_load, dlg.btn_save, dlg.btn_play,
                            dlg.cb_speed, dlg.chk_loop, dlg.chk_tx):
                self.assertFalse(control.isEnabled(), control.objectName())
            dlg._on_rec()
            self.assertFalse(w._recorder.recording)
            self.assertTrue(dlg.btn_load.isEnabled())
        finally:
            w._recorder.stop(); dlg.close(); dlg.deleteLater(); w.close_conn()

    def test_plain_send_cannot_mix_into_replay(self):
        """回放期间手动发送会污染复现场景；自动应答等内部发送仍有专用绕过通道。"""
        from rec_replay_dialog import RecReplayDialog
        w = self._virtual()
        old_dlg = w._rr_dlg
        dlg = RecReplayDialog(w)
        w._rr_dlg = dlg
        try:
            dlg._events = [(0.0, "rx", b"A"), (60.0, "rx", b"B")]
            dlg._on_play()
            w.conn.tx_log.clear()
            w.sw_tx_hex.setChecked(False)
            w.txt_send.setPlainText("MANUAL")
            w.do_send()
            self.assertEqual(w.conn.tx_log, [])
        finally:
            dlg.stop_replay(); w._rr_dlg = old_dlg
            dlg.close(); dlg.deleteLater(); w.close_conn()

    def test_dsl_sends_segments_in_order(self):
        w = self._virtual()
        try:
            w.sw_tx_hex.setChecked(False)
            w.conn.tx_log.clear()
            w.txt_send.setPlainText(r"A\!(Delay50)B")
            w.do_send()
            for _ in range(40):
                self._pump(30)
                if not w._dsl_running():
                    break
            self.assertEqual(w.conn.tx_log, [b"A", b"B"])
            self.assertFalse(w._dsl_running())
        finally:
            w._dsl_abort(); w.close_conn()

    def test_dsl_counts_as_io_task_while_running(self):
        w = self._virtual()
        try:
            w.sw_tx_hex.setChecked(False)
            w.txt_send.setPlainText(r"A\!(Delay300)B")
            w.do_send()
            self.assertTrue(w._dsl_running())
            self.assertTrue(w._io_task_busy())
        finally:
            w._dsl_abort(); w.close_conn()

    def test_dsl_aborted_on_disconnect(self):
        """断连要中止 DSL，否则剩余步骤对着断掉的连接空发、每段刷一次错误。"""
        w = self._virtual()
        try:
            w.sw_tx_hex.setChecked(False)
            w.txt_send.setPlainText(r"A\!(Delay500)B")
            w.do_send()
            self.assertTrue(w._dsl_running())
            w.close_conn()
            self.assertFalse(w._dsl_running())
        finally:
            w._dsl_abort()

    def test_plain_send_cannot_interleave_running_dsl(self):
        """DSL 延时窗口内的普通发送不能插队破坏命令顺序。"""
        w = self._virtual()
        try:
            w.sw_tx_hex.setChecked(False)
            w.conn.tx_log.clear()
            w.txt_send.setPlainText(r"A\!(Delay500)B")
            w.do_send()
            self.assertTrue(w._dsl_running())
            self.assertEqual(w.conn.tx_log, [b"A"])
            w.txt_send.setPlainText("MANUAL")
            w.do_send()
            self.assertEqual(w.conn.tx_log, [b"A"])
            self.assertTrue(w._dsl_running())
        finally:
            w._dsl_abort(); w.close_conn()

    def test_dsl_refuses_active_modbus_master(self):
        """DSL 的内部发送只能绕过自身占用，不能绕过 Modbus 主机的线路占用。"""
        from unittest.mock import patch
        w = self._virtual()
        try:
            w.sw_tx_hex.setChecked(False)
            w.conn.tx_log.clear()
            with patch.object(w, "_mbm_active", return_value=True):
                w.txt_send.setPlainText(r"A\!(Delay10)B")
                w.do_send()
            self.assertFalse(w._dsl_running())
            self.assertEqual(w.conn.tx_log, [])
        finally:
            w._dsl_abort(); w.close_conn()

    def test_bad_periodic_dsl_stops_period_timer(self):
        """确定性 DSL 错误若不停定时器，会按周期无限重复同一错误提示。"""
        w = self._virtual()
        try:
            w.txt_send.setPlainText(r"A\!(Delay-1)B")
            w.ed_period_ms.setText("10000")
            w.sw_period.setChecked(True)
            self.assertTrue(w.send_timer.isActive())
            w.do_send()
            self.assertFalse(w.sw_period.isChecked())
            self.assertFalse(w.send_timer.isActive())
        finally:
            w.sw_period.setChecked(False); w._dsl_abort(); w.close_conn()

    def test_period_tick_does_not_spam_busy_while_dsl_runs(self):
        from unittest.mock import patch
        w = self._virtual()
        try:
            w.sw_tx_hex.setChecked(False)
            self.assertTrue(w._dsl_start(r"A\!(Delay500)B", record_macro=False))
            with patch.object(w, "toast") as toast:
                self.assertFalse(w._dsl_start(r"A\!(Delay500)B", record_macro=False))
                toast.assert_not_called()
        finally:
            w._dsl_abort(); w.close_conn()

    def test_virtual_tooltip_retranslates(self):
        w = _win()
        old_lang = w._lang
        try:
            w._set_language("en")
            self.assertEqual(w.sw_vconn_loop.toolTip(), w._t("vconn_tip"))
            w._set_language("zh_tw")
            self.assertEqual(w.sw_vconn_loop.toolTip(), w._t("vconn_tip"))
        finally:
            w._set_language(old_lang)

    def test_plain_send_unaffected(self):
        """不含 DSL 指令时完全走原路径。"""
        w = self._virtual()
        try:
            w.sw_tx_hex.setChecked(False)
            w.conn.tx_log.clear()
            w.txt_send.setPlainText("PLAIN")
            w.do_send()
            self._pump(30)
            self.assertEqual(w.conn.tx_log, [b"PLAIN"])
            self.assertFalse(w._dsl_running())
        finally:
            w.close_conn()



class HexLineSelectionTests(unittest.TestCase):
    """整行 HEX 选区 → 字节（Qt-free）：结合布局剔除装饰，残缺 token 宁可丢也不能猜。"""

    def setUp(self):
        import convert
        self.convert = convert

    def test_plain_hex(self):
        line = "01 03 FF"
        self.assertEqual(
            self.convert.hex_line_selection_to_bytes(line, 0, len(line)),
            b"\x01\x03\xff")

    def test_context_parser_rejects_partial_hexdump_ascii_column(self):
        """选区从 ASCII 列内部开始时没有左侧 |，必须靠整行上下文识别，不能把 AB 当 0xAB。"""
        line = "00000000  41 42 43 44  45 46 47 48 |ABCDEFGH|"
        start = line.index("AB")
        self.assertEqual(
            self.convert.hex_line_selection_to_bytes(
                line, start, start + 2, hexdump=True),
            b"")
        self.assertEqual(
            self.convert.hex_line_selection_to_bytes(
                line, 0, len(line), hexdump=True),
            b"ABCDEFGH")

    def test_context_parser_rejects_partial_timestamp(self):
        """时间戳被局部截成恰好两位 HEX 字符时，也不能伪装成数据。"""
        line = "[2026/07/23 10:00:00 123] \u2190 01 03"
        start = line.index("26")
        self.assertEqual(
            self.convert.hex_line_selection_to_bytes(line, start, start + 2),
            b"")
        data_start = line.index("01")
        self.assertEqual(
            self.convert.hex_line_selection_to_bytes(line, data_start, len(line)),
            b"\x01\x03")

    def test_context_parser_requires_whole_hex_token_selected(self):
        line = "\u2190 AA BB"
        start = line.index("AA")
        self.assertEqual(
            self.convert.hex_line_selection_to_bytes(line, start + 1, len(line)),
            b"\xbb")

class FormatNumericTests(unittest.TestCase):
    """字节流 → 数值序列（Qt-free）：余数必须原样返回，否则跨包流会永久错位。"""

    def setUp(self):
        import convert
        self.convert = convert

    def test_u16_le_be(self):
        t, rest = self.convert.format_numeric(b"\x34\x12", "u16", "le")
        self.assertEqual(t.strip(), "4660")
        self.assertEqual(rest, b"")
        t, _ = self.convert.format_numeric(b"\x34\x12", "u16", "be")
        self.assertEqual(t.strip(), "13330")

    def test_signed(self):
        t, _ = self.convert.format_numeric(b"\xff\xff", "i16", "le")
        self.assertEqual(t.strip(), "-1")
        t, _ = self.convert.format_numeric(b"\xff", "i8")
        self.assertEqual(t.strip(), "-1")

    def test_f32(self):
        t, _ = self.convert.format_numeric(b"\x00\x00\x80\x3f", "f32", "le")
        self.assertEqual(t.strip(), "1")

    def test_remainder_returned_not_dropped(self):
        t, rest = self.convert.format_numeric(b"\x34\x12\x99", "u16", "le")
        self.assertEqual(t.strip(), "4660")
        self.assertEqual(rest, b"\x99")

    def test_too_short_returns_all_as_remainder(self):
        t, rest = self.convert.format_numeric(b"\x99", "u16")
        self.assertEqual(t, "")
        self.assertEqual(rest, b"\x99")

    def test_unknown_type_falls_back_u16(self):
        t, _ = self.convert.format_numeric(b"\x34\x12", "nope", "le")
        self.assertEqual(t.strip(), "4660")

    def test_line_wrap_and_alignment(self):
        """每行 per_line 个，各值右对齐到本块最宽值宽度（纵向成列）。"""
        t, _ = self.convert.format_numeric(bytes([1, 200, 3]), "u8", per_line=2)
        self.assertEqual(t, "  1 200\n  3")

    def test_fixed_width_aligns_across_blocks(self):
        """列宽按类型写死，不按本块最大值现算 —— 每个收包各自成块，现算的话量级一变
        纵向就参差（1 2 3 / 4660 65535 / 7 8 对不齐），整条流没法竖着扫。"""
        a, _ = self.convert.format_numeric(bytes([1, 0, 2, 0]), "u16", "le")
        b, _ = self.convert.format_numeric(bytes([0x34, 0x12, 0xFF, 0xFF]), "u16", "le")
        cols = lambda t: [len(x) for x in t.split(" ") if x != ""]
        self.assertEqual(len(a), len(b), "同类型同个数的两块，行宽必须一致:%r vs %r" % (a, b))
        for line in (a, b):
            for field in line.split(" "):
                if field:
                    self.assertLessEqual(len(field), 5)      # u16 列宽
        self.assertTrue(a.startswith("    1"), repr(a))      # 右对齐到 5 列

    def test_fixed_width_holds_for_type_extremes(self):
        """各类型极值必须撑得下写死的列宽，否则那一行会凸出来破坏对齐。"""
        import struct
        for typ, (size, code, _per, w) in self.convert.NUM_TYPES.items():
            if code == "f":
                raw = b"".join(struct.pack("<f", v)
                               for v in (-1.23456789e38, 1.5, float("nan"), float("-inf")))
            else:
                top = 2 ** (8 * size - 1)
                raw = b"".join(struct.pack("<" + code, v) for v in (
                    -1 if code.islower() else 2 ** (8 * size) - 1,   # 最小/最大
                    0,
                    -top if code.islower() else top,
                    (top - 1) if code.islower() else (2 ** (8 * size) - 2),
                ))
            text, _ = self.convert.format_numeric(raw, typ, "le", per_line=99)
            widest = max(len(x) for x in text.split())
            with self.subTest(typ=typ):
                self.assertLessEqual(widest, w, "%s 极值 %d 列 > 列宽 %d" % (typ, widest, w))

    def test_default_per_line_by_width(self):
        """窄类型每行 16 个、宽类型 8 个。"""
        t, _ = self.convert.format_numeric(bytes(34), "u8")
        self.assertEqual(len(t.splitlines()), 3)          # 16 + 16 + 2
        t, _ = self.convert.format_numeric(bytes(36), "u32")
        self.assertEqual(len(t.splitlines()), 2)          # 8 + 1


class NumericViewTests(unittest.TestCase):
    """数值视图在主窗里的接线：接管显示、与转储互斥、跨包不错位。"""

    def tearDown(self):
        """本类会把共享主窗留在「数值视图」态。数值视图在渲染路径里排在 HEX 之前且直接
        return，留着会让后面所有依赖 HEX/文本渲染的用例莫名失败（协议高亮那一组就是这么
        被带崩的，且只在特定执行顺序下复现，很难查）。谁开的谁关。"""
        w = _win()
        w.sw_numview.setChecked(False, animate=False)
        w.sw_hexdump.setChecked(False, animate=False)
        w._reset_recv_state()

    def _setup(self, idx=2):
        w = _win()
        w.sw_hexdump.setChecked(False, animate=False)
        w.sw_show_timestamp.setChecked(False, animate=False)
        w.cb_numview_type.setCurrentIndex(idx)
        w.sw_numview.setChecked(True, animate=False)
        w.txt_recv.clear()
        w._reset_recv_state()
        return w

    def test_renders_numbers(self):
        w = self._setup()                       # u16 LE
        w._on_data_received_impl(bytes([0x34, 0x12, 0xFF, 0xFF]))
        txt = w.txt_recv.toPlainText()
        self.assertIn("4660", txt)
        self.assertIn("65535", txt)

    def test_carry_across_packets(self):
        """一个 u16 被拆到两个收包里 —— 按包截断会让整条流从此错位，故必须带余数。"""
        w = self._setup()
        w._on_data_received_impl(bytes([0x34]))
        self.assertEqual(w.txt_recv.toPlainText().strip(), "")   # 半个数不输出
        self.assertEqual(w._numview_carries, {None: b"\x34"})
        w._on_data_received_impl(bytes([0x12]))
        self.assertIn("4660", w.txt_recv.toPlainText())
        self.assertEqual(w._numview_carries, {})

    def test_independent_block_shows_incomplete_tail_bytes(self):
        w = self._setup()                       # u16 LE
        only_tail = w._numview_block(b"\x34", carry=False)
        self.assertIn("34", only_tail)
        self.assertIn(w._t("numview_tail", data="34"), only_tail)
        value_and_tail = w._numview_block(b"\x34\x12\x99", carry=False)
        self.assertIn("4660", value_and_tail)
        self.assertIn(w._t("numview_tail", data="99"), value_and_tail)

    def test_udp_datagrams_do_not_share_numeric_remainder(self):
        from main_window import PROTO_UDP
        w = self._setup()
        old_proto = w._conn_proto
        try:
            w._conn_proto = PROTO_UDP
            w._on_data_received_impl(b"\x34")
            self.assertIn(w._t("numview_tail", data="34"), w.txt_recv.toPlainText())
            self.assertEqual(w._numview_carries, {})
            w._on_data_received_impl(b"\x12")
            text = w.txt_recv.toPlainText()
            self.assertIn(w._t("numview_tail", data="12"), text)
            self.assertNotIn("4660", text)
            self.assertEqual(w._numview_carries, {})
        finally:
            w._conn_proto = old_proto

    def test_carry_isolated_per_tcp_client(self):
        """TCP Server 多客户端的半包不能交叉拼成一个数。"""
        w = self._setup()
        w._on_data_received_impl(b"\x34", source="client-A")
        w._on_data_received_impl(b"\x12", source="client-B")
        self.assertEqual(w.txt_recv.toPlainText().strip(), "")
        self.assertEqual(w._numview_carries,
                         {"client-A": b"\x34", "client-B": b"\x12"})
        w._on_data_received_impl(b"\x12", source="client-A")
        self.assertIn("4660", w.txt_recv.toPlainText())
        self.assertEqual(w._numview_carries, {"client-B": b"\x12"})

    def test_disconnected_tcp_client_carry_is_pruned(self):
        w = self._setup()
        w.txt_recv.clear()
        w._numview_carries = {"client-A": b"\x34", "client-B": b"\x12"}
        w._on_clients_changed([("client-B", "client-B")])
        self.assertEqual(w._numview_carries, {"client-B": b"\x12"})
        self.assertIn(w._t("numview_tail", data="34"), w.txt_recv.toPlainText())

    def test_carry_cleared_on_reset(self):
        """清屏/断连是数据流断点，旧的半个数已无意义。"""
        w = self._setup()
        w._on_data_received_impl(bytes([0x34]))
        self.assertEqual(w._numview_carries, {None: b"\x34"})
        w._reset_recv_state()
        self.assertEqual(w._numview_carries, {})

    def test_type_change_resets_carry(self):
        w = self._setup()
        w._on_data_received_impl(bytes([0x34]))
        self.assertEqual(w._numview_carries, {None: b"\x34"})
        w.cb_numview_type.setCurrentIndex(6)      # u32 LE
        self.assertEqual(w._numview_carries, {})
        self.assertIn(w._t("numview_tail", data="34"), w.txt_recv.toPlainText())

    def test_turning_numeric_view_off_flushes_pending_tail(self):
        w = self._setup()
        w._on_data_received_impl(b"\x34")
        w.sw_numview.setChecked(False, animate=False)
        self.assertEqual(w._numview_carries, {})
        self.assertIn(w._t("numview_tail", data="34"), w.txt_recv.toPlainText())

    def test_mutually_exclusive_with_hexdump(self):
        """四种渲染方式合成一个下拉后，互斥由类型天然保证：选中一个，其余真的被关掉
        （旧设计是三个开关互相「灰掉」，只是不让点、状态仍可能同时为真）。
        附属参数页也跟着模式换：数值→类型页，转储→每行字节数页。"""
        w = self._setup()
        self.assertEqual(w.cb_view_mode.currentData(), "num")
        self.assertEqual(w._view_extra.currentIndex(), 3)      # 数值类型页
        w.cb_view_mode.setCurrentIndex(w.cb_view_mode.findData("dump"))
        self.assertTrue(w._hexdump_on)
        self.assertFalse(w._numview_on)                        # 换模式=旧模式真的关掉
        self.assertFalse(w.sw_rx_hex.isChecked())
        self.assertEqual(w._view_extra.currentIndex(), 2)      # 每行字节数页
        w.cb_view_mode.setCurrentIndex(w.cb_view_mode.findData("text"))
        self.assertFalse(w._hexdump_on or w._numview_on or w.sw_rx_hex.isChecked())
        self.assertEqual(w._view_extra.currentIndex(), 0)      # 文本页＝ANSI 着色开关
        self.assertEqual(w._view_extra.currentIndex(), 0)    # 只在文本模式露面
        w.cb_view_mode.setCurrentIndex(w.cb_view_mode.findData("hex"))
        self.assertEqual(w._view_extra.currentIndex(), 1)      # HEX 页无附属参数
        self.assertNotEqual(w._view_extra.currentIndex(), 0)  # HEX 不解释转义序列 → 藏起来

    def test_hexdump_wins_when_both_set_programmatically(self):
        """坏配置让两个模式同时为真时：渲染按转储优先，下拉也必须显示转储 ——
        显示与实际渲染不一致会让人以为看错了。"""
        w = self._setup()
        w.sw_hexdump.blockSignals(True)
        w.sw_hexdump.setChecked(True, animate=False)
        w.sw_hexdump.blockSignals(False)
        w._hexdump_on = True
        w._refresh_hex_toggle_state()
        self.assertEqual(w.cb_view_mode.currentData(), "dump")
        w.txt_recv.clear(); w._reset_recv_state()
        w._on_data_received_impl(bytes([0x34, 0x12]))
        self.assertIn("00000000", w.txt_recv.toPlainText())   # 走了转储而非数值
        w.sw_hexdump.setChecked(False, animate=False)

    def test_conflicting_saved_modes_are_normalized_on_load(self):
        w = self._setup()
        try:
            w.settings.setValue("hexdump_view", True)
            w.settings.setValue("numview", True)
            w._load_settings()
            self.assertTrue(w.sw_hexdump.isChecked())
            self.assertFalse(w.sw_numview.isChecked())
            self.assertFalse(w.settings.value("numview", True, type=bool))
            self.assertTrue(w.sw_hexdump.isEnabled())  # 获胜模式仍可关闭
        finally:
            w.settings.setValue("hexdump_view", False)
            w.settings.setValue("numview", False)
            w._load_settings()

    def test_proto_highlight_suppressed(self):
        """协议高亮只在普通 HEX 模式有意义；数值视图下不该再上色。"""
        w = self._setup()
        w.settings.setValue("frame_rules", ProtoHighlightTests.RULE)
        w._proto_rules_raw = None
        w.set_proto_highlight(True)
        w._proto_fields.clear()
        w.txt_recv.clear(); w._reset_recv_state()
        w._on_data_received_impl(ProtoHighlightTests.FRAME)
        self.assertEqual(len(w._proto_fields), 0)
        w.set_proto_highlight(False)

    def test_type_index_persisted_and_restored(self):
        w = self._setup(idx=11)                   # f32 BE
        self.assertEqual(w._numview_spec(), ("f32", "be"))
        self.assertEqual(int(w.settings.value("numview_type")), 11)

    def test_all_12_types_render(self):
        """12 个下拉项都要能出数值，别有哪个组合是坏的。"""
        w = self._setup()
        for i in range(w.cb_numview_type.count()):
            w.cb_numview_type.setCurrentIndex(i)
            w.txt_recv.clear(); w._reset_recv_state()
            w._on_data_received_impl(bytes(range(16)))
            with self.subTest(item=w.cb_numview_type.itemText(i)):
                self.assertTrue(w.txt_recv.toPlainText().strip(),
                                "%s 没渲染出内容" % w.cb_numview_type.itemText(i))

    def test_terminal_mode_dims_numeric_view_label(self):
        w = self._setup()
        try:
            w._apply_terminal_ui(True)
            # 数值视图并入「显示方式」下拉后，淡化的是那一行的标签
            labels = w._setting_labels.get("view_mode", ())
            self.assertTrue(labels)
            self.assertTrue(all(label.graphicsEffect() is not None for label in labels))
        finally:
            w._apply_terminal_ui(False)


class SelectionChecksumTests(unittest.TestCase):
    """选中即算校验和：状态栏就地出结果，超限只报字节数不给错值。"""

    FRAME = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x02])   # Modbus CRC = C4 0B

    def _setup(self, hexmode=True):
        w = _win()
        w.sw_hexdump.setChecked(False, animate=False)
        w.sw_numview.setChecked(False, animate=False)
        w.sw_show_timestamp.setChecked(False, animate=False)
        w.sw_rx_hex.setChecked(hexmode, animate=False)
        w.txt_recv.clear()
        w._reset_recv_state()
        return w

    @staticmethod
    def _select_all(w):
        from PyQt5.QtGui import QTextCursor
        cur = w.txt_recv.textCursor()
        cur.select(QTextCursor.Document)
        w.txt_recv.setTextCursor(cur)
        w._update_sel_checksum()          # 直接调，跳过 120ms 节流

    def test_brief_and_tooltip(self):
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self._select_all(w)
        self.assertFalse(w.lbl_sel_chk.isHidden())
        self.assertIn("C4 0B", w.lbl_sel_chk.text())      # Modbus CRC16
        title, meta, rows = w._sel_chk_popup_payload
        self.assertEqual(w.lbl_sel_chk.toolTip(), title)  # 仅作 Qt 悬停触发器，不再塞 HTML
        self.assertIn(w.fmt_bytes(len(self.FRAME)), meta)
        values = dict(rows)
        for idx in range(1, len(CHECKSUM_KEYS)):          # 9 种全在 tooltip 里
            self.assertEqual(
                values[w._t(CHECKSUM_KEYS[idx])],
                w.compute_checksum(self.FRAME, idx).hex(" ").upper())

    def test_matches_compute_checksum(self):
        """状态栏那三种必须和主程序算法逐字节一致，不能是另一套实现。"""
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self._select_all(w)
        txt = w.lbl_sel_chk.text()
        for idx, name in w._SEL_CHK_BRIEF:
            self.assertIn("%s %s" % (name, w.compute_checksum(self.FRAME, idx).hex(" ").upper()),
                          txt)

    def test_hidden_without_selection(self):
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self._select_all(w)
        self.assertFalse(w.lbl_sel_chk.isHidden())
        cur = w.txt_recv.textCursor()
        cur.clearSelection()
        w.txt_recv.setTextCursor(cur)
        w._update_sel_checksum()
        self.assertTrue(w.lbl_sel_chk.isHidden())
        self.assertTrue(w._sel_chk_sep.isHidden())

    def test_hidden_when_selection_has_no_bytes(self):
        """选中的全是装饰(时间戳/箭头)、一个字节也解析不出 → 不显示空结果。"""
        w = self._setup()
        w.txt_recv.setPlainText("\u2190 hello world")
        self._select_all(w)
        self.assertTrue(w.lbl_sel_chk.isHidden())

    def test_hexdump_ascii_column_partial_selection_is_rejected(self):
        """从 |ASCII| 内部只选 AB 时，不能把它静默算成 0xAB。"""
        from PyQt5.QtGui import QTextCursor
        w = self._setup()
        w.sw_hexdump.setChecked(True, animate=False)
        w.txt_recv.clear(); w._reset_recv_state()
        w._on_data_received_impl(b"ABCDEFGH")
        text = w.txt_recv.toPlainText()
        start = text.index("|AB") + 1
        cur = w.txt_recv.textCursor()
        cur.setPosition(start)
        cur.setPosition(start + 2, QTextCursor.KeepAnchor)
        w.txt_recv.setTextCursor(cur)
        w._update_sel_checksum()
        self.assertTrue(w.lbl_sel_chk.isHidden())
        w.sw_hexdump.setChecked(False, animate=False)

    def test_oversize_refuses_without_claiming_a_size(self):
        """超限只说明未算：既不截断去算（会给出"看着像真的"的错值），也不报字节数
        （提取够数就提前收工了，len 只是超限的证据、不是选区实际大小，报出来是假精确）。"""
        w = self._setup()
        w.txt_recv.clear(); w._reset_recv_state()
        w._on_data_received_impl(bytes(w._SEL_CHK_MAX + 1024))
        self._select_all(w)
        self.assertEqual(w.lbl_sel_chk.toolTip(), "")
        self.assertEqual(w.lbl_sel_chk.text(),
                         w._t("sel_chk_too_big", n=w._SEL_CHK_MAX // 1024))
        self.assertNotIn(w._t("sel_chk"), w.lbl_sel_chk.text())   # 不带"选中 N KB"前缀

    def test_extraction_is_bounded_not_document_sized(self):
        """提取跑在 GUI 线程上（120ms 节流后），而「最大行数」可配到 100 万。
        取够上限就必须收工，否则 Ctrl+A 全选会按文档大小线性卡死界面。"""
        w = self._setup()
        w.txt_recv.clear(); w._reset_recv_state()
        w._on_data_received_impl(bytes(4 * w._SEL_CHK_MAX))       # 远超上限
        from PyQt5.QtGui import QTextCursor
        cur = w.txt_recv.textCursor()
        cur.select(QTextCursor.Document)
        capped = w._selected_hex_bytes(cur, limit=w._SEL_CHK_MAX)
        full = w._selected_hex_bytes(cur)
        self.assertGreater(len(capped), w._SEL_CHK_MAX)           # 足以判定超限
        self.assertLess(len(capped), len(full))                   # 但确实提前停了
        self.assertGreater(len(full), 3 * w._SEL_CHK_MAX)         # 不设限时会全扫

    def test_history_hex_keeps_checksum_after_switching_to_text_view(self):
        """历史块按写入时的元数据解析，不应被当前开关重新解释。"""
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self._select_all(w)
        before = w.lbl_sel_chk.text()
        w.sw_rx_hex.setChecked(False, animate=False)
        w._update_sel_checksum()
        self.assertEqual(w.lbl_sel_chk.text(), before)

    def test_terminal_mode_does_not_offer_checksum(self):
        """终端正文有独立元数据，即使 sw_rx_hex 留着勾选也不能被当作 HEX。"""
        w = self._setup()
        try:
            w._terminal_on = True
            w._apply_terminal_ui(True)
            w.txt_recv.clear(); w._reset_recv_state()
            w._on_data_received_impl(b"OK AB CD READY\r\n")
            self._select_all(w)
            self.assertTrue(w.lbl_sel_chk.isHidden(),
                            "终端模式仍显示校验和: %r" % w.lbl_sel_chk.text())
        finally:
            w._terminal_on = False
            w._apply_terminal_ui(False)

    def test_old_hexdump_ascii_is_rejected_after_switching_view(self):
        """切回普通 HEX 后，历史转储仍须知道自己的 ASCII 列边界。"""
        from PyQt5.QtGui import QTextCursor
        w = self._setup()
        w.sw_hexdump.setChecked(True, animate=False)
        w.txt_recv.clear(); w._reset_recv_state()
        w._on_data_received_impl(b"ABCDEFGH")
        text = w.txt_recv.toPlainText()
        start = text.index("|AB") + 1
        w.sw_hexdump.setChecked(False, animate=False)
        cur = w.txt_recv.textCursor()
        cur.setPosition(start)
        cur.setPosition(start + 2, QTextCursor.KeepAnchor)
        w.txt_recv.setTextCursor(cur)
        w._update_sel_checksum()
        self.assertTrue(w.lbl_sel_chk.isHidden())

    def test_text_mode_does_not_offer_lossy_checksum(self):
        """解码后的文本无法无损反推原始字节；宁可隐藏，也不能对重编码文本给出伪校验值。"""
        w = self._setup(hexmode=False)
        w.txt_recv.setPlainText("AT")
        self._select_all(w)
        self.assertTrue(w.lbl_sel_chk.isHidden())

    def test_numeric_mode_does_not_checksum_decimal_text(self):
        """原始 34 12 显示为 4660 后，绝不能转而校验 ASCII '4660'。"""
        w = self._setup()
        w.sw_numview.setChecked(True, animate=False)
        w.txt_recv.clear(); w._reset_recv_state()
        w._on_data_received_impl(b"\x34\x12")
        self._select_all(w)
        self.assertTrue(w.lbl_sel_chk.isHidden())
        w.sw_numview.setChecked(False, animate=False)

    def test_tooltip_is_app_card_with_real_grid_layout(self):
        """结果使用真实控件网格排版，避免原生富文本 tooltip 的字体、间距和主题差异。"""
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self._select_all(w)
        w._show_sel_checksum_popup()
        popup = w._sel_chk_popup
        self.assertIsNotNone(popup)
        self.assertEqual(popup.grid.rowCount(), len(CHECKSUM_KEYS) - 1)
        self.assertEqual(len(popup._rows), len(CHECKSUM_KEYS) - 1)
        plain = " ".join(lbl.text() for pair in popup._rows for lbl in pair)
        for idx in range(1, len(CHECKSUM_KEYS)):
            with self.subTest(algo=w._t(CHECKSUM_KEYS[idx])):
                self.assertIn(w._t(CHECKSUM_KEYS[idx]), plain)
                self.assertIn(w.compute_checksum(self.FRAME, idx).hex(" ").upper(), plain)
        popup.hide()

    def test_popup_rows_are_reused_not_rebuilt(self):
        """行控件复用：重建的话 deleteLater 要等事件循环空闲才真删，连续悬停时旧 QLabel
        会成百上千地短暂堆积（实测连刷 10 次不给事件循环，子控件 20 → 200）。"""
        from PyQt5.QtWidgets import QLabel
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self._select_all(w)
        w._show_sel_checksum_popup()
        popup = w._sel_chk_popup
        first = popup.findChildren(QLabel)
        for _ in range(10):                    # 期间不给事件循环，堆积会立刻现形
            w._show_sel_checksum_popup()
        self.assertEqual(len(popup.findChildren(QLabel)), len(first))
        self.assertEqual(len(popup._rows), len(CHECKSUM_KEYS) - 1)
        popup.hide()

    def test_tooltip_uses_ui_names_and_monospace_values(self):
        """名称与应用 UI 一致，校验值统一用等宽字体，字节列能精确对齐。"""
        from fonts import ui_font, mono_font
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self._select_all(w)
        w._show_sel_checksum_popup()
        for name_label, value_label in w._sel_chk_popup._rows:
            self.assertEqual(name_label.font().family(), ui_font(9).family())
            self.assertEqual(value_label.font().family(), mono_font(9).family())
            self.assertEqual(value_label.objectName(), "ChecksumValue")
        w._sel_chk_popup.hide()

    def test_relabels_on_language_switch(self):
        """状态栏文案是算出来的，tr_text 机制刷不到 —— 切语言必须重算，否则残留旧语言。"""
        w = self._setup()
        w._on_data_received_impl(self.FRAME)
        self._select_all(w)
        old_lang = w._lang
        try:
            w._set_language("en")
            self.assertTrue(w.lbl_sel_chk.text().startswith(w._t("sel_chk")))
            w._set_language("zh")
            self.assertTrue(w.lbl_sel_chk.text().startswith(w._t("sel_chk")))
        finally:
            w._set_language(old_lang)

    def test_ts_format_and_search_mode_combos_relabel_on_language_switch(self):
        """cb_ts_format/cb_search_mode 的下拉项文案在创建时填充一次，
        _apply_language 必须重建，否则切语言后残留旧语言。"""
        w = self._setup()
        old_lang = w._lang
        try:
            ts_before = [w.cb_ts_format.itemText(i) for i in range(w.cb_ts_format.count())]
            sm_before = [w.cb_search_mode.itemText(i) for i in range(w.cb_search_mode.count())]
            w._set_language("en")
            self.assertEqual(w.cb_ts_format.itemText(0), w._t("ts_fmt_absolute"))
            self.assertEqual(w.cb_search_mode.itemText(0), w._t("search_mode_plain"))
            # 切回 zh 与重建前一致（itemData 保留当前选中）
            w._set_language("zh")
            self.assertEqual([w.cb_ts_format.itemText(i) for i in range(w.cb_ts_format.count())],
                             ts_before)
            self.assertEqual([w.cb_search_mode.itemText(i) for i in range(w.cb_search_mode.count())],
                             sm_before)
        finally:
            w._set_language(old_lang)

    def test_data_area_tooltip_advertises_feature(self):
        """状态栏标签没选区时是隐藏的，提示必须挂在数据区上，否则功能没人发现得了。"""
        w = self._setup()
        self.assertEqual(w.txt_recv.toolTip(), w._t("sel_chk_hint"))
        self.assertEqual(w.txt_recv.property("tr_tooltip"), "sel_chk_hint")

    def test_i18n_keys_present(self):
        from i18n import TR
        for lang in TR:
            for k in ("numview", "numview_tip", "numview_type_tip", "numview_tail",
                      "sel_chk", "sel_chk_too_big", "sel_chk_tip", "sel_chk_hint"):
                with self.subTest(lang=lang, key=k):
                    self.assertIn(k, TR[lang])



class _FakeSerial:
    """够用的 pyserial 替身：记录属性赋值，模拟已打开端口的 reconfigure 语义。"""

    _LIVE = ("baudrate", "bytesize", "parity", "stopbits", "rtscts", "xonxoff")

    def __init__(self, **kw):
        self.is_open = True
        self.fail_on = None
        self.applied = []
        # LIVE 属性给初值：真 pyserial 打开后这些属性都有值，apply_params 会先读快照
        # （失败回滚用），替身不给初值的话读快照就 AttributeError，掩盖真实行为。
        import serial as _s
        self.__dict__.update(dict(baudrate=9600, bytesize=_s.EIGHTBITS,
                                  parity=_s.PARITY_NONE, stopbits=_s.STOPBITS_ONE,
                                  rtscts=False, xonxoff=False))
        self.__dict__.update(kw)

    def __setattr__(self, k, v):
        if k in self._LIVE:
            if getattr(self, "fail_on", None) == k:
                import serial as _s
                raise _s.SerialException("simulated failure on %s" % k)
            self.__dict__.setdefault("applied", []).append((k, v))
        object.__setattr__(self, k, v)

    def write(self, d):
        return len(d)

    def close(self):
        self.is_open = False

    @property
    def in_waiting(self):
        return 0

    def read(self, n):
        return b""


class SerialLiveParamsTests(unittest.TestCase):
    """不断开连接改串口参数：pyserial 对已打开端口的属性赋值即时生效。"""

    def _conn(self):
        import serial
        from serial_io import SerialConn
        c = SerialConn("COM_FAKE", 9600, serial.EIGHTBITS,
                       serial.PARITY_NONE, serial.STOPBITS_ONE)
        c._ser = _FakeSerial()
        return c

    def test_applies_and_syncs_internal_state(self):
        """内部记录必须同步 —— 掉线自动重连读的是它，不同步会用旧参数重连。"""
        import serial
        c = self._conn()
        self.assertTrue(c.apply_params(baud=115200, parity=serial.PARITY_EVEN))
        self.assertEqual(c._ser.baudrate, 115200)
        self.assertEqual(c._ser.parity, serial.PARITY_EVEN)
        self.assertEqual(c._baud, 115200)
        self.assertEqual(c._parity, serial.PARITY_EVEN)

    def test_none_leaves_field_untouched(self):
        import serial
        c = self._conn()
        c.apply_params(baud=115200)
        c.apply_params(baud=None, stopbits=serial.STOPBITS_TWO)
        self.assertEqual(c._ser.baudrate, 115200)
        self.assertEqual(c._ser.stopbits, serial.STOPBITS_TWO)

    def test_flow_modes_are_exclusive(self):
        c = self._conn()
        c.apply_params(flow="rtscts")
        self.assertTrue(c._ser.rtscts)
        self.assertFalse(c._ser.xonxoff)
        c.apply_params(flow="xonxoff")
        self.assertFalse(c._ser.rtscts)
        self.assertTrue(c._ser.xonxoff)
        c.apply_params(flow="none")
        self.assertFalse(c._ser.rtscts)
        self.assertFalse(c._ser.xonxoff)

    def test_failure_reports_and_returns_false(self):
        """赋值失败多半是端口已异常（拔线）——要发信号让上层掉线路径接管，不能静默。"""
        c = self._conn()
        errs = []
        c.error_occurred.connect(errs.append)
        c._ser.fail_on = "baudrate"
        self.assertFalse(c.apply_params(baud=57600))
        self.assertTrue(errs)

    def test_partial_failure_rolls_back_atomically(self):
        """中途失败必须整体回滚：baud 改成功、parity 改失败时，硬件与内部记录都要退回
        调用前的旧值，不能留「硬件跑混合参数、函数却返回 False」的半应用状态。"""
        import serial
        c = self._conn()
        c._ser.fail_on = "parity"
        ok = c.apply_params(baud=115200, parity=serial.PARITY_EVEN)
        self.assertFalse(ok)
        self.assertEqual(c._ser.baudrate, 9600, "baud 硬件未回滚")
        self.assertEqual(c._ser.parity, serial.PARITY_NONE)
        self.assertEqual(c._baud, 9600, "内部记录 _baud 未回滚，重连会用错参数")
        self.assertEqual(c._parity, serial.PARITY_NONE)

    def test_flow_partial_failure_rolls_back(self):
        """flow 是两个属性（rtscts+xonxoff）：后者失败时前者也要回滚。"""
        c = self._conn()
        c._ser.fail_on = "xonxoff"
        self.assertFalse(c.apply_params(flow="rtscts"))
        self.assertFalse(c._ser.rtscts, "rtscts 未回滚")
        self.assertEqual(c._flow, "none", "内部 _flow 记录不该变")

    def test_success_is_all_or_nothing(self):
        """全成功时硬件与记录一次性到位；这是回滚路径的正常对照。"""
        import serial
        c = self._conn()
        self.assertTrue(c.apply_params(baud=57600, parity=serial.PARITY_ODD,
                                       stopbits=serial.STOPBITS_TWO))
        self.assertEqual((c._ser.baudrate, c._ser.parity, c._ser.stopbits),
                         (57600, serial.PARITY_ODD, serial.STOPBITS_TWO))
        self.assertEqual((c._baud, c._parity, c._stopbits),
                         (57600, serial.PARITY_ODD, serial.STOPBITS_TWO))

    def test_rejects_when_not_open(self):
        c = self._conn()
        c._ser = None
        self.assertFalse(c.apply_params(baud=9600))


class SerialLiveParamsUiTests(unittest.TestCase):
    """主窗接线：连接期间参数可改、改动即应用、连接签名同步。"""

    def _setup(self):
        import serial
        from serial_io import SerialConn
        from main_window import PROTO_SERIAL
        w = _win()
        c = SerialConn("COM_FAKE", 9600, serial.EIGHTBITS,
                       serial.PARITY_NONE, serial.STOPBITS_ONE)
        c._ser = _FakeSerial()
        w.conn = c
        w._conn_proto = PROTO_SERIAL
        w.cb_proto.setCurrentText(PROTO_SERIAL)
        w.cb_port.clear()
        w.cb_port.addItem("COM_FAKE", "COM_FAKE")
        w.cb_baud.setCurrentText("9600")
        w.cb_databits.setCurrentText("8")
        w.cb_parity.setCurrentText("None")
        w.cb_stopbits.setCurrentText("1")
        w.cb_flow.setCurrentText("None")
        w._conn_cfg = w._conn_config_signature(PROTO_SERIAL)
        return w, c

    def tearDown(self):
        w = _win()
        w.conn = None
        w._conn_proto = None
        w._conn_cfg = None

    def test_params_stay_editable_while_connected(self):
        """端口/协议换了必须重开连接，仍锁；波特率等可即时改，不锁。"""
        w, _c = self._setup()
        w.set_settings_enabled(False)
        for name in ("cb_baud", "cb_databits", "cb_parity", "cb_stopbits", "cb_flow"):
            with self.subTest(widget=name):
                self.assertTrue(getattr(w, name).isEnabled())
        self.assertFalse(w.cb_port.isEnabled())
        self.assertFalse(w.cb_proto.isEnabled())
        w.set_settings_enabled(True)

    def test_applies_to_live_port_and_syncs_signature(self):
        """_conn_cfg 是连接签名真源：Modbus 就绪门禁 / RTU t3.5 / 掉线重连都读它。"""
        w, c = self._setup()
        w.cb_baud.setCurrentText("115200")
        w._apply_serial_params_live()
        self.assertEqual(c._ser.baudrate, 115200)
        self.assertEqual(w._conn_cfg[2], 115200)
        self.assertIn("115200", w.lbl_state.text())

    def test_modbus_master_stays_ready_after_change(self):
        """签名不同步的话主机会因「UI 与实际连接不一致」立刻暂停轮询。"""
        w, c = self._setup()
        w.cb_baud.setCurrentText("115200")
        w._apply_serial_params_live()
        self.assertTrue(w._mbm_connection_ready())
        self.assertEqual(w._mbm_serial_baud(), 115200)

    def test_no_reapply_when_unchanged(self):
        """editingFinished 失焦也会来一次；值没变不该重复应用、不该重复提示。"""
        w, c = self._setup()
        w.cb_baud.setCurrentText("115200")
        w._apply_serial_params_live()
        n = len(c._ser.applied)
        w._apply_serial_params_live()
        self.assertEqual(len(c._ser.applied), n)

    def test_invalid_baud_rejected(self):
        w, c = self._setup()
        w.cb_baud.setCurrentText("115200")
        w._apply_serial_params_live()
        w.cb_baud.setCurrentText("abc")
        w._apply_serial_params_live()
        self.assertEqual(c._ser.baudrate, 115200)
        w.cb_baud.setCurrentText("115200")

    def test_ignored_for_non_serial_connection(self):
        from main_window import PROTO_TCP_CLIENT
        w, c = self._setup()
        w.cb_baud.setCurrentText("115200")
        w._apply_serial_params_live()
        w._conn_proto = PROTO_TCP_CLIENT
        w.cb_baud.setCurrentText("9600")
        w._apply_serial_params_live()
        self.assertEqual(c._ser.baudrate, 115200)

    def test_safe_when_disconnected(self):
        w = _win()
        w.conn = None
        w._conn_proto = None
        w._apply_serial_params_live()      # 不该抛

    def test_maps_shared_with_open_conn(self):
        """建连接与动态改参数必须共用同一份映射，两处解释不允许分叉。"""
        import main_window as MW
        import serial
        self.assertEqual(MW._PARITY_MAP["Even"], serial.PARITY_EVEN)
        self.assertEqual(MW._DATABITS_MAP["8"], serial.EIGHTBITS)
        self.assertEqual(MW._STOPBITS_MAP["1.5"], serial.STOPBITS_ONE_POINT_FIVE)
        self.assertEqual(MW._FLOW_MAP["RTS/CTS"], "rtscts")

    def test_live_flow_change_toggles_rts_switch(self):
        """改流控后手动 RTS 开关的启用态要跟着变——RTS/CTS 下硬件接管、禁用手动开关。
        直接调 _apply_serial_params_live（不经 UI 信号）也必须联动，不靠巧合同帧触发。"""
        w, c = self._setup()
        w.sw_rts.setEnabled(True)
        w.cb_flow.setCurrentText("RTS/CTS")
        w._apply_serial_params_live()
        self.assertTrue(c._ser.rtscts)
        self.assertFalse(w.sw_rts.isEnabled(), "RTS/CTS 下应禁用手动 RTS 开关")
        w.cb_flow.setCurrentText("None")
        w._apply_serial_params_live()
        self.assertFalse(c._ser.rtscts)
        self.assertTrue(w.sw_rts.isEnabled(), "无流控时应恢复手动 RTS 开关")

    def test_i18n_key_present(self):
        from i18n import TR
        for lang in TR:
            with self.subTest(lang=lang):
                self.assertIn("live_params_applied", TR[lang])



class LogNamingTests(unittest.TestCase):
    """文件名变量展开与跨日判定（Qt-free）。"""

    WHEN = None      # setUp 里填，避免模块导入期算时间

    def setUp(self):
        import log_naming
        from datetime import datetime
        self.L = log_naming
        self.WHEN = datetime(2026, 7, 23, 14, 30, 5)

    def test_date_time_port(self):
        self.assertEqual(self.L.expand("%date", self.WHEN), "20260723")
        self.assertEqual(self.L.expand("%time", self.WHEN), "143005")
        self.assertEqual(self.L.expand("%port", self.WHEN, port="COM3"), "COM3")

    def test_datetime_wins_over_date_prefix(self):
        """%datetime 必须整体匹配 —— 按 %date 先吃会剩个字面 time。"""
        self.assertEqual(self.L.expand("%datetime", self.WHEN), "20260723_143005")

    def test_case_insensitive(self):
        self.assertEqual(self.L.expand("%DATE", self.WHEN), "20260723")
        self.assertEqual(self.L.expand("%Port", self.WHEN, port="COM7"), "COM7")

    def test_unknown_percent_kept(self):
        """用户文件名里真有百分号时不能被吃掉。"""
        self.assertEqual(self.L.expand("100%done", self.WHEN), "100%done")

    def test_port_sanitized(self):
        """IP:端口 的冒号在 Windows 上非法，必须清掉才能进文件名。"""
        out = self.L.expand("%port", self.WHEN, port="192.168.1.10:8080")
        self.assertEqual(out, "192.168.1.10_8080")
        for ch in ':/\\<>"|?*':
            with self.subTest(ch=ch):
                self.assertNotIn(ch, self.L.sanitize_token("a%sb" % ch))

    def test_port_empty_falls_back(self):
        self.assertEqual(self.L.sanitize_token("", "conn"), "conn")
        self.assertEqual(self.L.sanitize_token(None, "conn"), "conn")

    def test_segment_appends_index_without_n_var(self):
        """不含 %n 时序号追加在扩展名前，与旧版 xxx_001.log 观感一致。"""
        self.assertEqual(self.L.segment_path("a.log", self.WHEN, seg=0), "a.log")
        self.assertEqual(self.L.segment_path("a.log", self.WHEN, seg=2), "a_002.log")

    def test_segment_respects_explicit_n(self):
        out = self.L.segment_path("a_%n.log", self.WHEN, seg=2)
        self.assertEqual(out, "a_002.log")
        self.assertNotIn("__", out)      # 没有被二次追加

    def test_should_roll_date(self):
        from datetime import datetime
        nxt = datetime(2026, 7, 24, 0, 0, 1)
        same = datetime(2026, 7, 23, 23, 59, 59)
        self.assertTrue(self.L.should_roll_date(self.WHEN, nxt, "%date.log"))
        self.assertFalse(self.L.should_roll_date(self.WHEN, same, "%date.log"))

    def test_no_roll_without_date_var(self):
        """没有日期变量时换日期也是同一个文件名，白白切断文件。"""
        from datetime import datetime
        nxt = datetime(2026, 7, 24, 0, 0, 1)
        self.assertFalse(self.L.should_roll_date(self.WHEN, nxt, "plain.log"))

    def test_should_roll_handles_none(self):
        self.assertFalse(self.L.should_roll_date(None, self.WHEN, "%date.log"))


class LogRotationTests(unittest.TestCase):
    """主窗接线：真开文件、真轮转。"""

    def setUp(self):
        import tempfile
        from datetime import datetime
        self.tmp = tempfile.mkdtemp(prefix="ctlog_")
        self.d1 = datetime(2026, 7, 23, 23, 59, 50)
        self.d2 = datetime(2026, 7, 24, 0, 0, 5)
        self.w = _win()
        self.w._close_log_file()
        self.w._log_seg = 0
        self.w._log_limit = 0

    def tearDown(self):
        import shutil
        self.w._close_log_file()
        self.w._log_base_path = ""
        self.w._log_seg = 0
        self.w._log_limit = 0
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _start(self, name, when=None):
        import os
        self.w._log_base_path = os.path.join(self.tmp, name)
        self.w._log_seg = 0
        when = when or self.d1
        path = self.w._log_segment_path(when)
        self.assertTrue(self.w._open_log_segment(path, when=when))
        return path

    def test_conn_token_from_connection(self):
        from main_window import PROTO_SERIAL
        old_proto, old_cfg = self.w._conn_proto, self.w._conn_cfg
        try:
            self.w._conn_proto = PROTO_SERIAL
            self.w._conn_cfg = (PROTO_SERIAL, "COM7", 115200, "8", "None", "1", "None")
            self.assertEqual(self.w._log_conn_token(), "COM7")
        finally:
            self.w._conn_proto, self.w._conn_cfg = old_proto, old_cfg

    def test_rolls_over_midnight_and_resets_index(self):
        """序号必须归零 —— 文件名已带新日期，再从 _003 数会像是这天从第 4 段开始。"""
        import os
        first = self._start("log_%date.txt")
        self.w._log_file.write("day1\n")
        self.w._log_file.flush()
        self.w._maybe_rotate_log(now=self.d2)
        second = self.w._log_file_path
        self.assertNotEqual(second, first)
        self.assertIn("20260724", os.path.basename(second))
        self.assertEqual(self.w._log_seg, 0)

    def test_no_roll_same_day(self):
        from datetime import datetime
        self._start("log_%date.txt")
        path = self.w._log_file_path
        self.w._maybe_rotate_log(now=datetime(2026, 7, 23, 23, 59, 59))
        self.assertEqual(self.w._log_file_path, path)

    def test_no_roll_without_date_var(self):
        self._start("plain.log")
        path = self.w._log_file_path
        self.w._maybe_rotate_log(now=self.d2)
        self.assertEqual(self.w._log_file_path, path)

    def test_old_segment_gets_footer_new_gets_header(self):
        first = self._start("log_%date.txt")
        self.w._log_file.write("day1\n")
        self.w._maybe_rotate_log(now=self.d2)
        with open(first, encoding="utf-8") as f:
            self.assertIn(self.w._t("log_footer", time="").strip()[:6], f.read())
        with open(self.w._log_file_path, encoding="utf-8") as f:
            self.assertIn(self.w._t("log_header", time="").strip()[:6], f.read())

    def test_size_split_still_works(self):
        self._start("size_%date.log")
        first = self.w._log_file_path
        self.w._log_limit = 200
        self.w._log_file.write("x" * 300)
        self.w._log_file.flush()
        self.w._maybe_rotate_log(now=self.d1)
        self.assertNotEqual(self.w._log_file_path, first)
        self.assertEqual(self.w._log_seg, 1)

    def test_date_roll_wins_over_size_index(self):
        self._start("size_%date.log")
        self.w._log_limit = 200
        self.w._log_file.write("x" * 300)
        self.w._log_file.flush()
        self.w._maybe_rotate_log(now=self.d1)
        self.assertEqual(self.w._log_seg, 1)
        self.w._maybe_rotate_log(now=self.d2)
        self.assertEqual(self.w._log_seg, 0)
        self.assertIn("20260724", self.w._log_file_path)

    def test_creates_subdirectory_from_variable(self):
        """%date 可以出现在目录段上，目录得自动建出来。"""
        import os
        path = self._start(os.path.join("%date", "run.log"))
        self.assertTrue(os.path.exists(path))
        self.assertIn("20260723", path)

    def test_i18n_keys_present(self):
        from i18n import TR
        for lang in TR:
            with self.subTest(lang=lang):
                self.assertIn("log_vars_tip", TR[lang])
                for tok in ("%date", "%port", "%n"):
                    self.assertIn(tok, TR[lang]["log_vars_tip"])



class RecDiffTests(unittest.TestCase):
    """会话比较对齐算法（Qt-free）。"""

    def setUp(self):
        import rec_diff
        self.D = rec_diff

    @staticmethod
    def _ev(t, d, hexs):
        return (t, d, bytes.fromhex(hexs))

    def test_identical(self):
        a = [self._ev(0, "tx", "01 03"), self._ev(0.1, "rx", "01 03 AA")]
        r = self.D.compare(a, list(a))
        self.assertTrue(r["stats"]["identical"])
        self.assertEqual(r["stats"]["same"], 2)
        self.assertEqual([x["kind"] for x in r["rows"]], ["same", "same"])

    def test_changed_payload_reported_as_one_row(self):
        """同一条帧内容变了，报「改了」比报「删一条又加一条」更贴近用户心里的模型。"""
        a = [self._ev(0.1, "rx", "01 03 AA")]
        b = [self._ev(0.1, "rx", "01 03 BB")]
        r = self.D.compare(a, b)
        self.assertEqual([x["kind"] for x in r["rows"]], ["diff"])
        self.assertEqual(r["rows"][0]["first_diff"], 2)

    def test_missing_frame_does_not_cascade(self):
        """核心价值：B 少答一帧时只报这一处，后续继续对齐。
        按下标并排比会让之后每一条都错位报差异，噪声淹没真正的那一处。"""
        a = [self._ev(0, "tx", "AA"), self._ev(0.1, "rx", "01"),
             self._ev(0.2, "rx", "02"), self._ev(0.3, "rx", "03")]
        b = [self._ev(0, "tx", "AA"), self._ev(0.1, "rx", "01"),
             self._ev(0.25, "rx", "03")]
        r = self.D.compare(a, b)
        self.assertEqual([x["kind"] for x in r["rows"]],
                         ["same", "same", "only_a", "same"])
        self.assertEqual(r["stats"]["only_a"], 1)
        self.assertEqual(r["stats"]["same"], 3)

    def test_extra_frame(self):
        a = [self._ev(0, "rx", "01"), self._ev(0.2, "rx", "03")]
        b = [self._ev(0, "rx", "01"), self._ev(0.1, "rx", "02"),
             self._ev(0.2, "rx", "03")]
        r = self.D.compare(a, b)
        self.assertEqual([x["kind"] for x in r["rows"]], ["same", "only_b", "same"])

    def test_direction_change_is_not_a_payload_change(self):
        """RX 变 TX 是两件事，不是同一条帧的内容变化，不该合并成 diff。"""
        a = [self._ev(0, "rx", "AA")]
        b = [self._ev(0, "tx", "AA")]
        r = self.D.compare(a, b)
        self.assertEqual(sorted(x["kind"] for x in r["rows"]), ["only_a", "only_b"])

    def test_timing_not_part_of_equality(self):
        """同一条帧早 30ms 到达仍是同一条帧；把时序算进相等性会让所有条目都不相等。"""
        a = [self._ev(0.0, "rx", "AA"), self._ev(1.0, "rx", "BB")]
        b = [self._ev(0.0, "rx", "AA"), self._ev(1.5, "rx", "BB")]
        r = self.D.compare(a, b)
        self.assertTrue(r["stats"]["identical"])
        self.assertEqual([x["dt"] for x in r["rows"]], [0.0, 0.5])
        self.assertEqual(r["stats"]["max_dt"], 0.5)

    def test_max_dt_keeps_sign(self):
        """变快也要看得见，所以记的是带符号的最大偏移而不是绝对值。"""
        a = [self._ev(0.0, "rx", "AA"), self._ev(2.0, "rx", "BB")]
        b = [self._ev(0.0, "rx", "AA"), self._ev(1.0, "rx", "BB")]
        r = self.D.compare(a, b)
        self.assertEqual(r["stats"]["max_dt"], -1.0)

    def test_empty_inputs(self):
        r = self.D.compare([], [])
        self.assertEqual(r["rows"], [])
        self.assertTrue(r["stats"]["identical"])
        a = [self._ev(0, "rx", "AA")]
        r = self.D.compare(a, [])
        self.assertEqual([x["kind"] for x in r["rows"]], ["only_a"])
        r = self.D.compare([], a)
        self.assertEqual([x["kind"] for x in r["rows"]], ["only_b"])

    def test_lcs_matches_naive_on_random_cases(self):
        """线性空间 Hirschberg 的 LCS 长度必须与朴素 DP 完全一致（交叉验证正确性）。"""
        import random

        def naive(ka, kb):
            n, m = len(ka), len(kb)
            dp = [[0] * (m + 1) for _ in range(n + 1)]
            for i in range(n):
                for j in range(m):
                    dp[i + 1][j + 1] = (dp[i][j] + 1 if ka[i] == kb[j]
                                        else max(dp[i][j + 1], dp[i + 1][j]))
            return dp[n][m]

        rnd = random.Random(20260724)
        for _ in range(200):
            A = [self._ev(0, "rx", "%02X" % rnd.randint(0, 4))
                 for _ in range(rnd.randint(0, 25))]
            B = [self._ev(0, "rx", "%02X" % rnd.randint(0, 4))
                 for _ in range(rnd.randint(0, 25))]
            ops = self.D._lcs_ops(A, B)
            lcs_len = sum(1 for o in ops if o[0] == "=")
            ka = [self.D._key(x) for x in A]
            kb = [self.D._key(x) for x in B]
            self.assertEqual(lcs_len, naive(ka, kb))

    def test_lcs_ops_cover_every_index_monotonically(self):
        """对齐结果必须覆盖两侧每个下标恰一次、下标严格递增，且每个 '=' 两侧键相等。"""
        import random
        rnd = random.Random(7)
        for _ in range(100):
            A = [self._ev(0, "rx", "%02X" % rnd.randint(0, 3))
                 for _ in range(rnd.randint(0, 30))]
            B = [self._ev(0, "rx", "%02X" % rnd.randint(0, 3))
                 for _ in range(rnd.randint(0, 30))]
            ops = self.D._lcs_ops(A, B)
            li = lj = -1
            for tag, i, j in ops:
                if i is not None:
                    self.assertGreater(i, li); li = i
                if j is not None:
                    self.assertGreater(j, lj); lj = j
                if tag == "=":
                    self.assertEqual(self.D._key(A[i]), self.D._key(B[j]))
            self.assertEqual(sorted(i for _, i, _ in ops if i is not None),
                             list(range(len(A))))
            self.assertEqual(sorted(j for _, _, j in ops if j is not None),
                             list(range(len(B))))

    def test_consecutive_changes_all_merge_to_diff(self):
        """连续多帧内容都变了（同方向），要逐条合并成 diff，而不是只并第一对、其余
        散成 only_a+only_b。归一化 + 块内逐条配对共同保证这点。"""
        a = [self._ev(i * 0.1, "rx", "AA %02X" % i) for i in range(6)]
        b = [self._ev(i * 0.1, "rx", "BB %02X" % i) for i in range(6)]
        r = self.D.compare(a, b)
        self.assertEqual([x["kind"] for x in r["rows"]], ["diff"] * 6)

    def test_change_plus_delete_mixed_block(self):
        """一处改+一处删混在一起：改的合并成 diff、删的保留 only_a，不互相污染。"""
        a = [self._ev(0, "rx", "01"), self._ev(1, "rx", "02"), self._ev(2, "rx", "03")]
        b = [self._ev(0, "rx", "F1"), self._ev(2, "rx", "03")]   # 01→F1, 删 02
        r = self.D.compare(a, b)
        self.assertEqual([x["kind"] for x in r["rows"]], ["diff", "only_a", "same"])

    def test_alignment_invariants_hold_on_random_cases(self):
        """随机用例上的对齐不变量：每侧下标恰覆盖一次；same 两侧全等；diff 同向异字节；
        stats 计数与 rows 一致。这是 _pair_ops 块状配对的总校验。"""
        import random
        from collections import Counter
        rnd = random.Random(99)
        for _ in range(400):
            n1, n2 = rnd.randint(0, 15), rnd.randint(0, 15)
            a = [self._ev(i * 0.1, rnd.choice(("rx", "tx")),
                          "%02X" % rnd.randint(0, 3)) for i in range(n1)]
            b = [self._ev(i * 0.1, rnd.choice(("rx", "tx")),
                          "%02X" % rnd.randint(0, 3)) for i in range(n2)]
            rows = self.D.compare(a, b)["rows"]
            self.assertEqual(sorted(x["ia"] for x in rows if x["ia"] is not None),
                             list(range(n1)))
            self.assertEqual(sorted(x["ib"] for x in rows if x["ib"] is not None),
                             list(range(n2)))
            for x in rows:
                if x["kind"] == "same":
                    self.assertEqual(self.D._key(a[x["ia"]]), self.D._key(b[x["ib"]]))
                elif x["kind"] == "diff":
                    self.assertEqual(x["dir_a"], x["dir_b"])
                    self.assertNotEqual(a[x["ia"]][2], b[x["ib"]][2])
            c = Counter(x["kind"] for x in rows)
            st = self.D.compare(a, b)["stats"]
            for k in ("same", "diff", "only_a", "only_b"):
                self.assertEqual(c.get(k, 0), st[k])

    def test_degrades_gracefully_when_oversized(self):
        """LCS 是 O(n*m)：超规模退化成线性比较并标记，绝不悄悄截断数据。"""
        a = [self._ev(i * 0.01, "rx", "%02X" % (i % 256)) for i in range(20)]
        r = self.D.compare(a, list(a), max_align=10)
        self.assertTrue(r["degraded"])
        self.assertEqual(r["stats"]["same"], 20)
        self.assertEqual(len(r["rows"]), 20)

    def test_not_degraded_within_limit(self):
        a = [self._ev(i * 0.01, "rx", "%02X" % (i % 256)) for i in range(5)]
        r = self.D.compare(a, list(a), max_align=10)
        self.assertFalse(r["degraded"])

    def test_degrade_by_cell_count(self):
        """退化按格子数 n*m 而非条数：LCS 时间是 O(n*m)，用格子数才贴合真实开销。
        一边条数很多但另一边很少时格子数小、瞬时算完，不该因单边条数多就退化。"""
        a = [self._ev(i * 0.01, "rx", "%02X" % (i % 256)) for i in range(10)]
        # max_align=10 → 阈值 100 格。各 9 条 = 81 格：不退化
        self.assertFalse(self.D.compare(a[:9], a[:9], max_align=10)["degraded"])
        # 各 10 条 = 100 格：达阈值，退化
        self.assertTrue(self.D.compare(a, a, max_align=10)["degraded"])
        # 10 × 5 = 50 格：远小于窄边条数暗示的规模，不退化（格子数判定的价值所在）
        self.assertFalse(self.D.compare(a, a[:5], max_align=10)["degraded"])
        # 直接用 max_cells：50 格 ≥ 40 阈值 → 退化
        self.assertTrue(self.D.compare(a, a[:5], max_cells=40)["degraded"])

    def test_narrow_side_stays_full_lcs(self):
        """一边 3 条 × 另一边 5000 条 = 15000 格，远小于默认 50 万，走完整 LCS 不退化。"""
        a = [self._ev(i * 0.01, "rx", "AA") for i in range(3)]
        b = [self._ev(i * 0.01, "rx", "AA") for i in range(5000)]
        self.assertFalse(self.D.compare(a, b)["degraded"])

    def test_csv_export_escapes_formula_injection(self):
        """首列以 = + - @ 开头会被 Excel 当公式执行，同报告导出的既有做法加前导单引号。"""
        a = [self._ev(0, "rx", "01 03 AA")]
        b = [self._ev(0, "rx", "01 03 BB")]
        csv = self.D.rows_to_csv(self.D.compare(a, b)["rows"])
        lines = csv.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("kind,"))
        self.assertIn("01 03 AA", lines[1])
        self.assertIn("01 03 BB", lines[1])

    def test_csv_has_no_none(self):
        """缺席侧的字段应是空串而不是字面 None。"""
        a = [self._ev(0, "rx", "AA")]
        csv = self.D.rows_to_csv(self.D.compare(a, [])["rows"])
        self.assertNotIn("None", csv)


class RecDiffDialogTests(unittest.TestCase):
    """会话比较对话框接线。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="ctdiff_")
        self.w = _win()

    def tearDown(self):
        import shutil
        dlg = getattr(self.w, "_rd_dlg", None)
        if dlg is not None:
            dlg.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, rows):
        import os
        import rec_replay
        r = rec_replay.StreamRecorder()
        r.events = [(t, d, bytes.fromhex(h)) for t, d, h in rows]
        path = os.path.join(self.tmp, name)
        r.save(path)
        return path

    def _dlg_with(self, rows_a, rows_b):
        import rec_replay
        pa = self._write("a.ctrec", rows_a)
        pb = self._write("b.ctrec", rows_b)
        self.w.open_rec_diff()
        dlg = self.w._rd_dlg
        for side, path in (("a", pa), ("b", pb)):
            events, _h = rec_replay.load(path)
            setattr(dlg, "_path_%s" % side, path)
            setattr(dlg, "_events_%s" % side, events)
        dlg._sync_controls()
        return dlg

    def test_compare_button_requires_both_sides(self):
        self.w.open_rec_diff()
        dlg = self.w._rd_dlg
        dlg._path_a = ""
        dlg._path_b = ""
        dlg._events_a = []
        dlg._events_b = []
        dlg._result = None
        dlg._sync_controls()
        self.assertFalse(dlg.btn_cmp.isEnabled())
        self.assertFalse(dlg.btn_export.isEnabled())

    def test_empty_recording_is_comparable(self):
        """空录制（有效文件但 0 事件）是合法输入：「设备这次一条都没回」正是要比出的差异，
        就绪判定必须按是否选了文件、不能按事件数，否则空录制会把比较按钮锁死。"""
        dlg = self._dlg_with([], [(0.0, "rx", "AA")])
        self.assertTrue(dlg.btn_cmp.isEnabled(), "一侧空录制不该禁用比较")
        dlg._on_compare()
        self.assertEqual([x["kind"] for x in dlg._result["rows"]], ["only_b"])
        # 两侧都空：完全一致
        dlg2 = self._dlg_with([], [])
        self.assertTrue(dlg2.btn_cmp.isEnabled())
        dlg2._on_compare()
        self.assertTrue(dlg2._result["stats"]["identical"])

    def test_table_filters_to_differences(self):
        dlg = self._dlg_with(
            [(0.0, "tx", "AA"), (0.1, "rx", "01"), (0.2, "rx", "02")],
            [(0.0, "tx", "AA"), (0.1, "rx", "01")])
        dlg._on_compare()
        dlg.chk_only_diff.setChecked(True)
        self.assertEqual(dlg.table.rowCount(), 1)
        dlg.chk_only_diff.setChecked(False)
        self.assertEqual(dlg.table.rowCount(), 3)

    def test_export_enabled_after_compare(self):
        dlg = self._dlg_with([(0.0, "rx", "AA")], [(0.0, "rx", "BB")])
        self.assertFalse(dlg.btn_export.isEnabled())
        dlg._on_compare()
        self.assertTrue(dlg.btn_export.isEnabled())

    def test_help_uses_self_drawn_dialog_not_qmessagebox(self):
        """帮助必须走自绘主题窗（对齐录制/回放），不用系统 QMessageBox —— 后者跨平台
        样式和主题都对不上。模块级不再导入 QMessageBox 即证明整个对话框都不依赖它。"""
        import rec_diff_dialog
        self.assertFalse(hasattr(rec_diff_dialog, "QMessageBox"),
                         "rec_diff_dialog 仍导入 QMessageBox，帮助/错误提示应走自绘窗+toast")
        # 三语言帮助正文与标题齐全，且正文是富文本（有 <b> 标签，对齐 rr 观感）
        from i18n import TR
        for lang in TR:
            with self.subTest(lang=lang):
                self.assertIn("rd_help_title", TR[lang])
                self.assertIn("<b>", TR[lang]["rd_help"])
                self.assertNotIn("\n", TR[lang]["rd_help"])   # 富文本用 <br> 不用裸换行

    def test_identical_reported_in_status(self):
        rows = [(0.0, "tx", "AA"), (0.1, "rx", "01")]
        dlg = self._dlg_with(rows, rows)
        dlg._on_compare()
        self.assertIn(self.w._t("rd_identical"), dlg.lbl_stat.text())

    def test_hex_cell_shows_direction_and_truncates(self):
        from rec_diff_dialog import RecDiffDialog, _HEX_PREVIEW
        self.assertEqual(RecDiffDialog._hex_cell(b"", "rx"), "")
        self.assertTrue(RecDiffDialog._hex_cell(b"\x01", "rx").startswith("\u2190"))
        self.assertTrue(RecDiffDialog._hex_cell(b"\x01", "tx").startswith("\u2192"))
        long = RecDiffDialog._hex_cell(bytes(_HEX_PREVIEW + 10), "rx")
        self.assertIn("B)", long)          # 超长带 …(NB) 标注，完整值在 tooltip / CSV

    def test_dialog_is_single_instance(self):
        self.w.open_rec_diff()
        first = self.w._rd_dlg
        self.w.open_rec_diff()
        self.assertIs(self.w._rd_dlg, first)

    def test_workspace_has_entry(self):
        keys = {item[0] for item in self.w._workspace_specs("data")}
        self.assertIn("rd_title", keys)

    def test_language_switch(self):
        dlg = self._dlg_with([(0.0, "rx", "AA")], [(0.0, "rx", "BB")])
        dlg._on_compare()
        old = self.w._lang
        try:
            self.w._set_language("en")
            self.assertEqual(dlg.windowTitle(), self.w._t("rd_title"))
            self.assertEqual(dlg.table.horizontalHeaderItem(0).text(),
                             self.w._t("rd_col_kind"))
            # 已加载文件的描述是套翻译模板拼的，切语言必须重渲染，否则残留旧语言格式。
            # 英文模板是 "{f} ({n} events)"，中文是 "{f}（{n} 条）"——用 events 判英文态。
            self.assertIn("events", dlg.name_a.text(), dlg.name_a.text())
            self.assertIn("a.ctrec", dlg.name_a.text())
            self.w._set_language("zh")
            self.assertIn("条", dlg.name_a.text(), dlg.name_a.text())
        finally:
            self.w._set_language(old)

    def test_unloaded_side_shows_none_after_language_switch(self):
        """只选了一边时，另一边切语言也要跟着刷成新语言的「未选择」。"""
        self.w.open_rec_diff()
        dlg = self.w._rd_dlg
        dlg._path_a = ""
        dlg._events_a = []
        dlg._result = None
        old = self.w._lang
        try:
            dlg.retranslate()
            self.assertEqual(dlg.name_a.text(), self.w._t("rd_none"))
            self.w._set_language("en")
            self.assertEqual(dlg.name_a.text(), self.w._t("rd_none"))
        finally:
            self.w._set_language(old)

    def test_i18n_keys_present(self):
        from i18n import TR
        keys = [k for k in TR["zh"] if k.startswith("rd_")]
        self.assertGreater(len(keys), 20)
        for lang in TR:
            for k in keys:
                with self.subTest(lang=lang, key=k):
                    self.assertIn(k, TR[lang])



class SnippetsCoreTests(unittest.TestCase):
    """模板库纯数据逻辑（Qt-free）。"""

    def setUp(self):
        import snippets
        self.S = snippets

    def test_normalize_fills_and_truncates(self):
        self.assertEqual(self.S.normalize({"name": "x"}),
                         {"name": "x", "text": "", "hex": False})
        self.assertEqual(self.S.normalize("junk"),
                         {"name": "", "text": "", "hex": False})
        self.assertEqual(len(self.S.normalize({"name": "a" * 999})["name"]), self.S.MAX_NAME)
        self.assertEqual(len(self.S.normalize({"text": "b" * 99999})["text"]), self.S.MAX_TEXT)
        self.assertIs(self.S.normalize({"hex": 1})["hex"], True)

    def test_normalize_parses_string_booleans(self):
        """手写/第三方 JSON 常把布尔值写成字符串；'false' 不能变成 True。"""
        for value in ("false", "0", "no", "off", ""):
            self.assertFalse(self.S.normalize({"hex": value})["hex"], value)
        for value in ("true", "1", "yes", "on"):
            self.assertTrue(self.S.normalize({"hex": value})["hex"], value)

    def test_sanitize_drops_junk_and_caps(self):
        got = self.S.sanitize_list([{"name": "a"}, "junk", 42, {"text": "b", "hex": True}])
        self.assertEqual(len(got), 2)
        self.assertEqual(got[1], {"name": "", "text": "b", "hex": True})
        self.assertEqual(len(self.S.sanitize_list([{"name": str(i)} for i in range(999)])),
                         self.S.MAX_SNIPPETS)
        self.assertEqual(self.S.sanitize_list("nope"), [])

    def test_match_and_filter(self):
        lst = [{"name": "AT查版本", "text": "AT+VER", "hex": False},
               {"name": "复位", "text": "AA 55", "hex": True}]
        self.assertTrue(self.S.match(lst[0], "at"))         # 不分大小写
        self.assertTrue(self.S.match(lst[1], "55"))         # 命中内容
        self.assertTrue(self.S.match(lst[0], ""))           # 空 query 全过
        self.assertFalse(self.S.match(lst[0], "zzz"))
        # filter 保留原始下标
        self.assertEqual(self.S.filter_snippets(lst, "55"), [(1, lst[1])])
        self.assertEqual(len(self.S.filter_snippets(lst, "")), 2)

    def test_json_roundtrip(self):
        lst = [{"name": "a", "text": "01 02", "hex": True},
               {"name": "b", "text": "AT", "hex": False}]
        j = self.S.to_json(lst)
        self.assertIn("commtool-snippets", j)
        self.assertEqual(self.S.from_json(j), lst)

    def test_from_json_accepts_three_shapes(self):
        # 本程序格式 / 裸列表 / items 同构
        self.assertEqual(self.S.from_json('{"snippets":[{"name":"a"}]}'),
                         [{"name": "a", "text": "", "hex": False}])
        self.assertEqual(self.S.from_json('[{"name":"b","text":"t"}]'),
                         [{"name": "b", "text": "t", "hex": False}])
        self.assertEqual(self.S.from_json('{"items":[{"name":"c"}]}'),
                         [{"name": "c", "text": "", "hex": False}])

    def test_from_json_rejects_garbage(self):
        with self.assertRaises(ValueError):
            self.S.from_json("not json at all")
        with self.assertRaises(ValueError):
            self.S.from_json('{"foo": 1}')       # 无列表键

    def test_defaults_are_editable_samples(self):
        d = self.S.default_snippets()
        self.assertEqual(len(d), 3)
        for s in d:                               # 都是合法 normalize 结构
            self.assertEqual(self.S.normalize(s), s)


class SnippetsDialogTests(unittest.TestCase):
    """模板库对话框 + 主窗接线。"""

    def setUp(self):
        import tempfile
        self.w = _win()
        # 用干净的临时库，避免测试间互相污染
        import snippets
        self.w._snippets = snippets.default_snippets()
        self.w.open_snippets()
        self.dlg = self.w._snip_dlg
        self.dlg.ed_search.clear()
        self.dlg._reload_list()

    def tearDown(self):
        dlg = getattr(self.w, "_snip_dlg", None)
        if dlg is not None:
            dlg.close()

    def test_loads_defaults_first_time(self):
        import tempfile
        from PyQt5.QtCore import QSettings
        w = _win()
        w.settings = QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat)
        items, ok = w._load_snippets()
        self.assertFalse(ok)                      # 走了默认 → 调用方应落盘
        self.assertEqual(len(items), 3)

    def test_empty_library_stays_empty_after_reload(self):
        """用户删除全部模板后保存的 [] 是合法配置，重启不能重新塞回示例。"""
        import tempfile
        from PyQt5.QtCore import QSettings
        w = _win()
        old_settings = w.settings
        try:
            w.settings = QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat)
            w.settings.setValue("snippets", "[]")
            items, ok = w._load_snippets()
            self.assertTrue(ok)
            self.assertEqual(items, [])
        finally:
            w.settings = old_settings

    def test_add_edit_delete(self):
        n0 = len(self.w._snippets)
        self.dlg._add()
        self.assertEqual(len(self.w._snippets), n0 + 1)
        self.dlg.ed_name.setText("我的帧")
        self.dlg.ed_body.setPlainText("DE AD BE EF")
        self.dlg.chk_hex.setChecked(True)
        self.dlg._commit_edit()
        self.assertEqual(self.w._snippets[-1],
                         {"name": "我的帧", "text": "DE AD BE EF", "hex": True})
        self.dlg._cur = len(self.w._snippets) - 1
        self.dlg._delete()
        self.assertEqual(len(self.w._snippets), n0)

    def test_commit_does_not_recurse(self):
        """编辑落盘会重建列表、重建又会改选中行 —— 必须不触发无限递归（曾 hang）。"""
        self.dlg._add()
        self.dlg.ed_name.setText("x")
        self.dlg._commit_edit()                   # 不 hang 即通过
        self.assertEqual(self.w._snippets[-1]["name"], "x")

    def test_pending_edit_survives_search_and_add(self):
        """搜索/新增会重建列表，必须先提交仍在去抖窗口里的输入。"""
        self.w._snippets = [{"name": "old", "text": "A", "hex": False}]
        self.dlg._cur = -1
        self.dlg._reload_list()
        self.dlg.ed_name.setText("draft")
        self.assertTrue(self.dlg._save_timer.isActive())
        self.dlg.ed_search.setText("zzz")
        self.assertEqual(self.w._snippets[0]["name"], "draft")

        self.dlg.ed_search.clear()
        self.dlg.ed_name.setText("draft2")
        self.dlg._add()
        self.assertEqual(self.w._snippets[0]["name"], "draft2")
        self.assertEqual(len(self.w._snippets), 2)

    def test_pending_edit_then_change_row_keeps_selection_in_sync(self):
        """切行时提交旧条目后，高亮行和编辑区必须仍指向用户点击的新条目。"""
        self.w._snippets = [
            {"name": "first", "text": "A", "hex": False},
            {"name": "second", "text": "B", "hex": False},
        ]
        self.dlg._cur = -1
        self.dlg._reload_list()
        self.dlg.ed_name.setText("first edited")
        self.dlg.list.setCurrentRow(1)
        self.assertEqual(self.w._snippets[0]["name"], "first edited")
        self.assertEqual(self.dlg._cur, 1)
        self.assertEqual(self.dlg.list.currentRow(), 1)
        self.assertEqual(self.dlg.ed_name.text(), "second")

    def test_search_filters_list(self):
        self.w._snippets = [{"name": "读温度", "text": "01 03", "hex": True},
                            {"name": "查版本", "text": "AT+VER", "hex": False}]
        self.dlg._cur = -1
        self.dlg.ed_search.setText("温度")
        self.assertEqual(self.dlg.list.count(), 1)
        self.dlg.ed_search.setText("AT")          # 命中内容
        self.assertEqual(self.dlg.list.count(), 1)
        self.dlg.ed_search.clear()
        self.assertEqual(self.dlg.list.count(), 2)

    def test_fill_sets_send_box_and_hex(self):
        # 走正常路径：设数据 → reload 同步编辑区 → 选中 → 填入（同用户操作，_fill 的落盘取到正确内容）
        self.w._snippets = [{"name": "帧", "text": "DE AD", "hex": True}]
        self.dlg._cur = -1
        self.dlg._reload_list()               # 选中第 0 行，编辑区同步成 "帧"
        self.w.sw_tx_hex.setChecked(False)
        self.dlg._fill(send=False)
        self.assertEqual(self.w.txt_send.toPlainText(), "DE AD")
        self.assertTrue(self.w.sw_tx_hex.isChecked())
        # 文本模板反向：填入后 HEX 关
        self.w._snippets = [{"name": "at", "text": "AT+RST", "hex": False}]
        self.dlg._cur = -1
        self.dlg._reload_list()
        self.dlg._fill(send=False)
        self.assertEqual(self.w.txt_send.toPlainText(), "AT+RST")
        self.assertFalse(self.w.sw_tx_hex.isChecked())

    def test_persistence_roundtrip(self):
        import json, snippets
        self.w._snippets = [{"name": "a", "text": "01", "hex": True}]
        self.w._save_snippets()
        raw = self.w.settings.value("snippets", "")
        self.assertEqual(snippets.sanitize_list(json.loads(raw)), self.w._snippets)

    def test_snippets_in_terminal_workbench(self):
        """Snippet library is directly reachable in Terminal and Multi-Send."""
        self.assertEqual(self.w.btn_snippets.text(), self.w._t("snip_title"))
        opened = []
        original = self.w.open_snippets
        try:
            self.w.btn_snippets.clicked.disconnect()
            self.w.btn_snippets.clicked.connect(lambda: opened.append(True))
            self.w.btn_snippets.click()
            self.assertEqual(opened, [True])
        finally:
            self.w.btn_snippets.clicked.disconnect()
            self.w.btn_snippets.clicked.connect(original)

    def test_multi_send_dialog_opens_snippets(self):
        """多条发送对话框顶部的「模板库」按钮点击后打开模板库——两个发送辅助工具就近串联。"""
        from i18n import TR
        for lang in TR:                       # 按钮文案键三语言齐全
            self.assertIn("ms_snip_btn", TR[lang])
            self.assertIn("ms_snip_btn_tip", TR[lang])
        self.w.open_multi_send()
        ms = self.w._multi_send_dlg
        self.assertTrue(hasattr(ms, "btn_snippets"))
        self.assertEqual(ms.btn_snippets.text(), self.w._t("ms_snip_btn"))
        ms.btn_snippets.click()
        self.assertIsNotNone(self.w._snip_dlg)
        old = self.w._lang                    # 按钮文案随语言刷新
        try:
            self.w._set_language("en")
            self.assertEqual(ms.btn_snippets.text(), self.w._t("ms_snip_btn"))
        finally:
            self.w._set_language(old)
        ms.close()

    def test_single_instance(self):
        first = self.w._snip_dlg
        self.w.open_snippets()
        self.assertIs(self.w._snip_dlg, first)

    def test_language_switch(self):
        old = self.w._lang
        try:
            self.w._set_language("en")
            self.assertEqual(self.dlg.windowTitle(), self.w._t("snip_title"))
            self.assertEqual(self.dlg.btn_add.text(), self.w._t("snip_add"))
            self.w._set_language("zh")
            self.assertEqual(self.dlg.windowTitle(), self.w._t("snip_title"))
        finally:
            self.w._set_language(old)

    def test_i18n_keys_present(self):
        from i18n import TR
        keys = [k for k in TR["zh"] if k.startswith("snip_")]
        self.assertGreater(len(keys), 15)
        for lang in TR:
            for k in keys:
                with self.subTest(lang=lang, key=k):
                    self.assertIn(k, TR[lang])


if __name__ == "__main__":
    unittest.main(verbosity=2)
