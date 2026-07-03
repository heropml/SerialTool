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
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool
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
        try:
            w.cb_proto.setCurrentText("Serial")
            w.cb_baud.setCurrentText("9600")
            w._conn_proto = "Serial"
            w._conn_cfg = w._conn_config_signature("Serial")
            w._mbm_on = True
            w._mbm_rules = [{"enabled": True}]
            w._is_open = lambda: True
            self.assertTrue(w._mbm_active())
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
            w._conn_cfg, w._conn_proto, w._mbm_on = old_cfg, old_proto, old_on
            w._mbm_rules, w._is_open = old_rules, old_open

    def test_coil_response_byte_count_must_match_request(self):
        fake = type("Fake", (), {"_t": lambda self, key: key})()
        self.assertIsNone(CommTool._mbm_validate(fake, {"qty": 1}, {"bits": [False] * 8}))
        self.assertEqual(CommTool._mbm_validate(
            fake, {"qty": 1}, {"bits": [False] * 16}), "mbm_st_badresp")

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
            w._update_mbm_btn()
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
        had_lock = hasattr(app, "_profile_lock")
        o_app_lock = getattr(app, "_profile_lock", None)
        o_send = w.txt_send.toPlainText()
        d = tempfile.mkdtemp()
        orig = CommTool._settings_file
        CommTool._settings_file = staticmethod(
            lambda p="": _os.path.join(d, "settings.ini" if not p else "settings-%s.ini" % p))
        try:
            w.txt_send.setPlainText("LEAK-ME")           # P2：制造"上一配置"的残留值
            w._reconnect_timer.start(99999)              # P1：模拟排队中的自动重连
            w._switch_profile("3")
            self.assertEqual(w._profile, "3")
            self.assertEqual(w._title_suffix, " (3)")
            self.assertTrue(w.windowTitle().endswith("(3)"))
            self.assertTrue(w.settings.fileName().endswith("settings-3.ini"))
            self.assertEqual(w.txt_send.toPlainText(), w._field_defaults.get("txt_send", ""))  # P2：复位、不残留
            self.assertFalse(w._reconnect_timer.isActive())                                     # P1：已取消重连
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
            w.txt_send.setPlainText(o_send)
            w._reconnect_timer.stop()
            w.setWindowTitle(w._t("app_title") + w._title_suffix)
            shutil.rmtree(d, ignore_errors=True)

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
            self._seq_pump(150)
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
        old = w._terminal_on
        try:
            w._set_terminal_enabled(True)
            for name in ("sw_rx_hex", "sw_show_timestamp", "sw_line_split",
                         "sw_tx_hex", "sw_append_newline", "cb_checksum"):
                self.assertFalse(getattr(w, name).isEnabled(), name + " 应不可配置")
            self.assertTrue(w.cb_encoding.isEnabled())   # 编码仍可用
            self.assertTrue(w.sw_wrap.isEnabled())       # 自动换行仍可用
            w._set_terminal_enabled(False)
            for name in ("sw_rx_hex", "sw_tx_hex", "cb_checksum"):
                self.assertTrue(getattr(w, name).isEnabled(), name + " 应恢复可配置")
        finally:
            w._set_terminal_enabled(old)

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
            self.assertFalse(w.sw_rx_hex.isEnabled())   # 终端开 → 其它设置不可配置
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

    def test_serial_runtime_error_no_autoreconnect(self):
        """串口运行时掉线(拔出)不自动重连；网络掉线仍重连。"""
        w = _win()
        n = {"reconnect": 0}
        old = (w._schedule_reconnect, w.conn, w._conn_engaged, w._reconnect_attempts,
               w.close_conn, w.toast, w._refresh_stat_labels, w._conn_proto)
        try:
            w._schedule_reconnect = lambda: n.__setitem__("reconnect", n["reconnect"] + 1)
            w.close_conn = lambda: None
            w.toast = lambda *a, **k: None
            w._refresh_stat_labels = lambda *a, **k: None
            w.conn = None
            w._conn_engaged = True            # 曾连上 → 运行时掉线
            w._reconnect_attempts = 0
            # 串口掉线 → 不重连（_on_conn_error 以 _conn_proto 为准，不看下拉框）
            w._conn_proto = "Serial"
            w._on_conn_error("device disconnected")
            self.assertEqual(n["reconnect"], 0)
            # 网络(TCP Client)掉线 → 仍重连
            w._conn_engaged = True
            w._reconnect_attempts = 0
            w._conn_proto = "TCP Client"
            w._on_conn_error("connection reset")
            self.assertEqual(n["reconnect"], 1)
        finally:
            (w._schedule_reconnect, w.conn, w._conn_engaged, w._reconnect_attempts,
             w.close_conn, w.toast, w._refresh_stat_labels, w._conn_proto) = old

    def test_serial_removal_disconnects_after_debounce(self):
        """已连接的串口在后台扫描里连续 N 次检测不到 → 断开；单次抖动不误断。"""
        w = _win()
        calls = {"close": 0, "toast": 0}
        old = (w.conn, w._conn_proto, w._serial_device, w._serial_missing_count,
               w.close_conn, w.toast)
        try:
            w.close_conn = lambda: calls.__setitem__("close", calls["close"] + 1)
            w.toast = lambda *a, **k: calls.__setitem__("toast", calls["toast"] + 1)
            w.conn = object()                      # 假装已连接
            w._conn_proto = "Serial"               # PROTO_SERIAL
            w._serial_device = "COM1"
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
            # 单次抖动后口回来 → 计数清零，不会断
            w._serial_missing_count = 0
            w._on_port_scan_complete([("COM2", "COM2")])    # 缺 1 次
            w._on_port_scan_complete([("COM1", "COM1")])    # 回来 → 清零
            self.assertEqual(w._serial_missing_count, 0)
            self.assertEqual(calls["close"], 1)             # 没有再断
        finally:
            (w.conn, w._conn_proto, w._serial_device, w._serial_missing_count,
             w.close_conn, w.toast) = old

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
