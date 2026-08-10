# -*- coding: utf-8 -*-
"""ANSI 着色 / 触发告警 与主窗集成的回归测试（评审提出的 7 个问题各留一条守门）。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QSettings  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])

from main_window import (CommTool, ANSI_FG_PROP, ANSI_BG_PROP, ROLE_PROP, PROTO_SERIAL,
                         PROTO_TCP_SERVER, PROTO_UDP, SEND_NO_TARGET)  # noqa: E402
from theme import THEMES  # noqa: E402
import triggers  # noqa: E402
import ansi as ansi_mod  # noqa: E402
import json  # noqa: E402

_WIN = None


def _win():
    global _WIN
    if _WIN is None:
        _WIN = CommTool()
    return _WIN


def _fmt_at(w, sub, prop=ANSI_FG_PROP):
    """取 sub 首字符所在片段的某个格式属性（None=没设）。"""
    doc = w.txt_recv.document()
    cur = doc.find(sub)
    if cur.isNull():
        return "<未找到>"
    pos = cur.selectionStart()
    blk = doc.findBlock(pos)
    it = blk.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.position() <= pos < frag.position() + frag.length():
            return frag.charFormat().property(prop)
        it += 1
    return None


class AnsiRenderTests(unittest.TestCase):
    def setUp(self):
        self.w = _win()
        self.w._set_terminal_enabled(False)
        self.w.cb_view_mode.setCurrentIndex(self.w.cb_view_mode.findData("text"))
        self.w.sw_ansi.setChecked(True, animate=False)
        self.w.sw_line_split.setChecked(True, animate=False)
        self.w.cb_line_nl.setCurrentIndex(1)          # CRLF
        self.w.sw_show_timestamp.setChecked(False, animate=False)
        self.w.txt_recv.clear()
        self.w._reset_recv_state()

    def test_escapes_stripped_and_colored(self):
        """转义序列不进正文，颜色进格式；非 SGR 序列（擦除等）一并吃掉不留乱码。"""
        self.w._on_data_received_impl(b"\x1b[K\x1b[0;32mOK\x1b[0m\r\n")
        shown = self.w.txt_recv.toPlainText()
        self.assertNotIn("\x1b", shown)
        self.assertNotIn("[K", shown)
        self.assertIn("OK", shown)
        self.assertEqual(_fmt_at(self.w, "OK"), "i2")

    def test_cross_chunk_crlf_keeps_spans_aligned(self):
        """回归(P4)：跨包 CRLF 会增删 text 的首尾字符，颜色区间必须跟着平移 ——
        否则整行色块错位一位（行首字符没上色、行尾多上一格）。"""
        self.w._on_data_received_impl(b"x\r")
        self.w._on_data_received_impl(b"\n\x1b[31mRED\r\n")
        self.assertEqual(_fmt_at(self.w, "RED"), "i1")        # 三个字符整体红，不是从第二个才红
        self.w.txt_recv.clear(); self.w._reset_recv_state()
        self.w._on_data_received_impl(b"y\r")                 # 挂起的 \r 没等到 \n → 补回首字符
        self.w._on_data_received_impl(b"\x1b[32mGRN\r\n")
        self.assertEqual(_fmt_at(self.w, "GRN"), "i2")

    def test_carried_color_survives_escape_free_packet(self):
        """回归(快速通道)：为省逐字符解析，无转义符的包会走跳过路径 —— 但上一包
        留下的颜色未复位时不能跳，否则纯文本的后续包会掉色。三种续包各验一次。"""
        w = self.w
        w.sw_line_split.setChecked(False, animate=False)
        w._on_data_received_impl(b"\x1b[32mGREEN")
        w._on_data_received_impl(b"-PLAIN")               # 无转义：颜色必须延续
        self.assertEqual(_fmt_at(w, "-PLAIN"), "i2")
        w._on_data_received_impl(b"\x1b[0mDONE")           # 复位后……
        w._on_data_received_impl(b"AFTER")                # ……后续纯文本包走快速通道、无色
        self.assertIn(_fmt_at(w, "AFTER"), ("", None))
        # 半条转义收尾也不能被快速通道跳过
        w.txt_recv.clear(); w._reset_recv_state()
        w._on_data_received_impl(b"A\x1b[3")
        w._on_data_received_impl(b"1mRED")                # 本包无 ESC，但有残片 → 必须解析
        self.assertEqual(_fmt_at(w, "RED"), "i1")

    def test_theme_switch_recolors_fg_and_bg(self):
        """回归(P6)：调色板序号要按新主题明暗重解析 —— 前景和**背景**都得重算，
        否则深色底选的配色留到浅色底上会看不见 / 糊成一片。"""
        w = self.w
        w._on_data_received_impl(b"\x1b[44m\x1b[33mTXT\x1b[0m\r\n")   # 蓝底黄字

        def colors():
            doc = w.txt_recv.document()
            cur = doc.find("TXT")
            pos = cur.selectionStart()
            blk = doc.findBlock(pos)
            it = blk.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.position() <= pos < frag.position() + frag.length():
                    cf = frag.charFormat()
                    return cf.foreground().color().name(), cf.background().color().name()
                it += 1
            return None, None

        old_idx = w.cb_theme.currentIndex()
        try:
            mode0 = w._theme().get("mode")
            fg0, bg0 = colors()
            target = next(tid for tid, t in THEMES.items() if t.get("mode") != mode0)
            idx = w.cb_theme.findData(target)
            self.assertGreaterEqual(idx, 0)
            w.cb_theme.setCurrentIndex(idx)
            w._on_theme_changed()
            fg1, bg1 = colors()
            self.assertNotEqual(fg0, fg1, "前景没随主题重解析")
            self.assertNotEqual(bg0, bg1, "背景没随主题重解析")
        finally:
            w.cb_theme.setCurrentIndex(old_idx)
            w._on_theme_changed()

    def test_terminal_stops_coloring_when_ansi_off(self):
        """回归(P3)：终端的基础格式若沿用光标处旧格式，会把上一段的 ANSI 颜色带过来 ——
        关掉着色后新文字仍是红的。"""
        w = self.w
        w.txt_recv.clear()
        w._term_sgr = None
        w._term_pos = None
        w._term_esc = ""
        w._terminal_append("\x1b[31mRED")
        w.sw_ansi.setChecked(False, animate=False)
        w._terminal_append("PLAIN")
        self.assertIn(_fmt_at(w, "PLAIN"), ("", None))
        w.sw_ansi.setChecked(True, animate=False)

    def test_reentering_terminal_starts_uncolored(self):
        """回归：上一次终端会话结尾若停在红色，重进终端不该让新会话第一行凭空是红的。"""
        w = self.w
        w.sw_ansi.setChecked(True, animate=False)
        w.txt_recv.clear()
        w._term_sgr = None
        w._term_pos = None
        w._term_esc = ""
        w._terminal_append("\x1b[31mRED")
        w._set_terminal_enabled(False)
        w._set_terminal_enabled(True)
        try:
            w.txt_recv.clear()
            w._term_pos = None
            w._terminal_append("NEW")
            self.assertIn(_fmt_at(w, "NEW"), ("", None))
        finally:
            w._set_terminal_enabled(False)

    def test_reverse_video_follows_theme(self):
        """回归(反显)：SGR 7 缺省那一侧要用主题正文/底色，且必须存记号而非当场算好的颜色 ——
        存死了切主题就不会变，为深底选的颜色会留在浅底上。"""
        w = self.w
        w.txt_recv.clear()
        w._reset_recv_state()
        w._on_data_received_impl(b"\x1b[7mREV\x1b[0m\r\n")
        self.assertEqual(_fmt_at(w, "REV"), ansi_mod.SPEC_THEME_BG)   # 存的是记号

        def fg():
            doc = w.txt_recv.document()
            cur = doc.find("REV")
            pos = cur.selectionStart()
            blk = doc.findBlock(pos)
            it = blk.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.position() <= pos < frag.position() + frag.length():
                    return frag.charFormat().foreground().color().name()
                it += 1

        old_idx = w.cb_theme.currentIndex()
        try:
            f0 = fg()
            mode0 = w._theme().get("mode")
            target = next(tid for tid, t in THEMES.items() if t.get("mode") != mode0)
            w.cb_theme.setCurrentIndex(w.cb_theme.findData(target))
            w._on_theme_changed()
            self.assertNotEqual(f0, fg(), "反显颜色没跟随主题重解析")
        finally:
            w.cb_theme.setCurrentIndex(old_idx)
            w._on_theme_changed()

    def test_ansi_switch_only_shown_for_text_and_terminal(self):
        """着色开关并进「显示方式」那一行的附属参数格：只在文本模式露面（HEX/转储/数值不解释
        转义序列），终端模式下强制露面（终端里同样按 SGR 上色，要能关掉）。"""
        w = self.w
        for mode, page in (("text", 0), ("hex", 1), ("dump", 2), ("num", 3)):
            w.cb_view_mode.setCurrentIndex(w.cb_view_mode.findData(mode))
            self.assertEqual(w._view_extra.currentIndex(), page, mode)
            # The switch lives on the stacked text-only page; this does not
            # depend on whether the parent window is shown on offscreen Qt.
            self.assertEqual(w._view_extra.currentIndex() == 0, mode == "text", mode)
        w.cb_view_mode.setCurrentIndex(w.cb_view_mode.findData("hex"))
        w._set_terminal_enabled(True)
        try:
            self.assertEqual(w._view_extra.currentIndex(), 0)
        finally:
            w._set_terminal_enabled(False)
            w.cb_view_mode.setCurrentIndex(w.cb_view_mode.findData("text"))

    def test_tcp_clients_keep_decode_and_ansi_state_separate(self):
        """TCP Server 多客户端不能共享半个 UTF-8 字符或 ANSI 颜色状态。"""
        w = self.w
        old_proto = w._conn_proto
        try:
            w._conn_proto = PROTO_TCP_SERVER
            w.sw_line_split.setChecked(False, animate=False)
            w.txt_recv.clear(); w._reset_recv_state()
            w._on_data_received_impl(b"\x1b[31mA", source="client-A")
            w._on_data_received_impl(b"PLAIN", source="client-B")
            self.assertIn(_fmt_at(w, "PLAIN"), ("", None))

            # A 留下 UTF-8 前两字节，B 的末字节不能替 A 补成一个欧元符号。
            w.sw_ansi.setChecked(False, animate=False)
            w.txt_recv.clear(); w._reset_recv_state()
            w._on_data_received_impl(b"\xe2\x82", source="client-A")
            w._on_data_received_impl(b"\xac", source="client-B")
            self.assertNotIn("€", w.txt_recv.toPlainText())
            w._on_data_received_impl(b"\xac", source="client-A")
            self.assertIn("€", w.txt_recv.toPlainText())
        finally:
            w._conn_proto = old_proto
            w.sw_ansi.setChecked(True, animate=False)
            w._reset_recv_state()

    def test_tcp_clients_do_not_join_crlf_or_terminal_escapes(self):
        """多客户端的 CR/LF、终端 SGR 和半条 ESC 都不能跨来源拼接。"""
        w = self.w
        old_proto = w._conn_proto
        try:
            w._conn_proto = PROTO_TCP_SERVER
            w.txt_recv.clear(); w._reset_recv_state()
            w._on_data_received_impl(b"A\r", source="client-A")
            self.assertEqual(w._rx_pending_cr_source, "client-A")
            w._on_data_received_impl(b"\nB", source="client-B")
            self.assertFalse(w._pending_line_break,
                             "B 的 LF 被误当成 A 的 CR 后半段")

            w._set_terminal_enabled(True)
            w.txt_recv.clear()
            w._on_data_received_impl(b"\x1b[31mA", source="client-A")
            w._on_data_received_impl(b"PLAIN", source="client-B")
            self.assertIn(_fmt_at(w, "PLAIN"), ("", None))

            w.txt_recv.clear()
            w._set_terminal_enabled(False)
            w._set_terminal_enabled(True)
            w._on_data_received_impl(b"\x1b[", source="client-A")
            w._on_data_received_impl(b"31mTEXT", source="client-B")
            self.assertIn("31mTEXT", w.txt_recv.toPlainText())
        finally:
            w._set_terminal_enabled(False)
            w._conn_proto = old_proto
            w._reset_recv_state()

    def test_terminal_swallows_osc_and_charset_sequences(self):
        """终端里的 OSC 标题和 ESC(B 字符集序列要整条吞掉，不能把参数漏进正文。"""
        w = self.w
        w._set_terminal_enabled(True)
        try:
            w.txt_recv.clear()
            w._term_pos = None
            w._term_esc = ""
            w._term_discard_csi = False
            w._term_discard_osc = False
            w._term_osc_prev_esc = False
            # 同时覆盖 BEL / ST 两种 OSC 终止方式及跨块 ESC(B。
            w._terminal_append("\x1b]0;title")
            w._terminal_append("\x07OK\x1b]8;;https://example.invalid\x1b\\LINK")
            w._terminal_append("\x1b(")
            w._terminal_append("BZ")
            self.assertEqual(w.txt_recv.toPlainText(), "OKLINKZ")
        finally:
            w._set_terminal_enabled(False)


class SidebarStateTests(unittest.TestCase):
    def test_load_settings_restores_collapsible_sections(self):
        """切配置槽后折叠状态应读取新槽位，不能一直沿用窗口创建时的旧值。"""
        w = _win()
        old_settings = w.settings
        with tempfile.TemporaryDirectory() as td:
            try:
                w.settings = QSettings(str(Path(td) / "sections.ini"), QSettings.IniFormat)
                w.settings.setValue("sec_recv_more", True)
                w.settings.setValue("sec_send_term", False)
                w.settings.setValue("terminal_mode", False)
                w._load_settings()
                self.assertTrue(w.sec_recv_more.isExpanded())
                self.assertFalse(w.sec_send_term.isExpanded())

                w.settings.setValue("sec_recv_more", False)
                w.settings.setValue("sec_send_term", True)
                w._load_settings()
                self.assertFalse(w.sec_recv_more.isExpanded())
                self.assertTrue(w.sec_send_term.isExpanded())
            finally:
                w.settings = old_settings
                w._load_settings()


class TriggerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.w = _win()
        self.w._set_terminal_enabled(False)
        self.w.cb_view_mode.setCurrentIndex(self.w.cb_view_mode.findData("text"))
        self.w.cb_encoding.setCurrentIndex(0)         # Auto
        self.w._reset_trigger_decoders()

    def _rules(self, *rules):
        self.w._triggers = [triggers.normalize(r) for r in rules]
        self.w._save_triggers()

    def test_decoding_matches_display_path(self):
        """回归(P1-解码)：触发引擎要和数据区**同一套编码规则**（Auto 走 UTF-8 优先 /
        GBK 回退、半个字符跨包拼），否则带中文关键字的规则会漏报。"""
        w = self.w
        w._reset_recv_state(); w._reset_trigger_decoders()
        gbk = "温度告警".encode("gbk")
        self.assertEqual(w._decode_rx(gbk), "温度告警")
        w._reset_trigger_decoders()
        self.assertEqual(w._decode_for_triggers(gbk, "rx"), "温度告警")
        # 跨包切半的 UTF-8 多字节字符：两边都要拼回，而不是吐替换字符
        u = "告警".encode("utf-8")
        w._reset_trigger_decoders()
        got = w._decode_for_triggers(u[:4], "rx") + w._decode_for_triggers(u[4:], "rx")
        self.assertEqual(got, "告警")

    def test_rx_and_tx_decoders_are_independent(self):
        """收发共用一个解码器会让 RX 的半个字符和 TX 的字节拼在一起，两边都乱。"""
        w = self.w
        u = "告警".encode("utf-8")
        w._reset_trigger_decoders()
        a = w._decode_for_triggers(u[:4], "rx")
        self.assertEqual(w._decode_for_triggers(b"OK", "tx"), "OK")
        self.assertEqual(a + w._decode_for_triggers(u[4:], "rx"), "告警")

    def test_chinese_keyword_hits_in_both_encodings(self):
        w = self.w
        self._rules({"name": "cn", "pattern": "告警", "cooldown": 0,
                     "beep": False, "notify": False})
        for enc in ("gbk", "utf-8"):
            w._reset_trigger_decoders()
            w._triggers_feed("温度告警".encode(enc), "rx")
        self.assertEqual(w._trigger_engine.hits(0), 2)

    def test_prefix_matches_indented_log_line(self):
        """回归(P2-语义)：日志行的缩进与 \\r\\n 属于分帧，不该让前缀匹配失效。"""
        w = self.w
        self._rules({"name": "p", "pattern": "ERROR", "mode": triggers.MODE_PREFIX,
                     "cooldown": 0, "beep": False, "notify": False})
        w._reset_trigger_decoders()
        w._triggers_feed(b"  ERROR: boom\r\n", "rx")
        self.assertEqual(w._trigger_engine.hits(0), 1)

    def test_terminal_send_feeds_tx_rules(self):
        """回归(P5)：终端是绕过 _send_text 的直发路径，范围含「发送」的规则必须也盯它，
        否则在终端里敲的命令永远不命中。"""
        w = self.w
        self._rules({"name": "tx", "pattern": "PING", "scope": "tx", "cooldown": 0,
                     "beep": False, "notify": False})
        seen = []
        orig_feed = w._triggers_feed
        orig_open, orig_conn = w._is_open, getattr(w, "conn", None)

        class _FakeConn:
            def send(self, data, target=None):
                return len(data)

        w._triggers_feed = lambda d, dr, source=None: (
            seen.append((bytes(d), dr)), orig_feed(d, dr, source=source))[1]
        w._is_open = lambda: True
        w.conn = _FakeConn()
        try:
            w._terminal_send(b"PING")
            self.assertIn((b"PING", "tx"), seen)
            self.assertEqual(w._trigger_engine.hits(0), 1)
        finally:
            w._triggers_feed = orig_feed
            w._is_open = orig_open
            w.conn = orig_conn

    def test_keyword_split_across_serial_reads(self):
        """回归：串口按块回调，"ERROR" 可能被劈成 "ERR" + "OR" —— 只看单块必漏。"""
        w = self.w
        old_proto = w._conn_proto
        try:
            w._conn_proto = PROTO_SERIAL
            self._rules({"name": "s", "pattern": "ERROR", "cooldown": 0,
                         "beep": False, "notify": False})
            w._triggers_feed(b"ERR", "rx")
            w._triggers_feed(b"OR: boom", "rx")
            self.assertEqual(w._trigger_engine.hits(0), 1)
        finally:
            w._conn_proto = old_proto
            w._reset_trigger_decoders()

    def test_datagrams_and_tcp_clients_do_not_share_stream_tail(self):
        """UDP 报文有独立边界；TCP Server 每个客户端也是独立字节流，不能互相拼关键字。"""
        w = self.w
        old_proto = w._conn_proto
        rule = {"name": "s", "pattern": "ERROR", "cooldown": 0,
                "beep": False, "notify": False}
        try:
            w._conn_proto = PROTO_UDP
            self._rules(rule)
            w._triggers_feed(b"ER", "rx")
            w._triggers_feed(b"ROR", "rx")
            self.assertEqual(w._trigger_engine.hits(0), 0)

            w._conn_proto = PROTO_TCP_SERVER
            self._rules(rule)
            w._triggers_feed(b"ER", "rx", source="client-A")
            w._triggers_feed(b"ROR", "rx", source="client-B")
            self.assertEqual(w._trigger_engine.hits(0), 0)
            # 同一客户端的后续块仍应与自己的尾巴拼上。
            w._triggers_feed(b"ROR", "rx", source="client-A")
            self.assertEqual(w._trigger_engine.hits(0), 1)
        finally:
            w._conn_proto = old_proto
            w._reset_trigger_decoders()

    def test_split_ansi_escape_keeps_prefix_and_anchor_semantics(self):
        """ANSI 控制序列自身也会被底层劈开；残片必须留到同一流的下一块再剥除。"""
        w = self.w
        old_proto = w._conn_proto
        try:
            w._conn_proto = PROTO_SERIAL
            self._rules({"name": "p", "pattern": "ERROR", "mode": triggers.MODE_PREFIX,
                         "cooldown": 0, "beep": False, "notify": False},
                        {"name": "r", "pattern": r"^ERROR", "mode": triggers.MODE_REGEX,
                         "cooldown": 0, "beep": False, "notify": False})
            w._triggers_feed(b"\x1b[31", "rx")
            w._triggers_feed(b"mERROR", "rx")
            self.assertEqual(w._trigger_engine.hits(0), 1)
            self.assertEqual(w._trigger_engine.hits(1), 1)
        finally:
            w._conn_proto = old_proto
            w._reset_trigger_decoders()

    def test_anchored_regex_still_matches_later_chunk_start(self):
        """跨块回看不能改变 ^ 的本块锚定语义，否则规则只可能命中第一块。"""
        w = self.w
        old_proto = w._conn_proto
        try:
            w._conn_proto = PROTO_SERIAL
            self._rules({"name": "r", "pattern": r"^ERROR", "mode": triggers.MODE_REGEX,
                         "cooldown": 0, "beep": False, "notify": False})
            w._triggers_feed(b"OK", "rx")
            w._triggers_feed(b"ERROR", "rx")
            self.assertEqual(w._trigger_engine.hits(0), 1)
        finally:
            w._conn_proto = old_proto
            w._reset_trigger_decoders()

    def test_rule_edit_discards_old_stream_tail(self):
        """新规则从保存时刻开始观察，不能和旧规则时期留下的半个关键字拼接。"""
        w = self.w
        old_proto = w._conn_proto
        try:
            w._conn_proto = PROTO_SERIAL
            self._rules({"pattern": "COLOR", "cooldown": 0,
                         "beep": False, "notify": False})
            w._triggers_feed(b"CO", "rx")
            self._rules({"pattern": "CORAL", "cooldown": 0,
                         "beep": False, "notify": False})
            w._triggers_feed(b"RAL", "rx")
            self.assertEqual(w._trigger_engine.hits(0), 0)
        finally:
            w._conn_proto = old_proto
            w._reset_trigger_decoders()

    def test_ansi_escapes_do_not_block_prefix_and_anchored_regex(self):
        """回归：彩色日志一行真正的开头是 "I (123)"，前面那串转义是显示格式不是内容 ——
        不剥掉的话「前缀」和「^ 锚定正则」永远命中不了。"""
        w = self.w
        self._rules({"name": "p", "pattern": "I (", "mode": triggers.MODE_PREFIX,
                     "cooldown": 0, "beep": False, "notify": False},
                    {"name": "r", "pattern": r"^I \(", "mode": triggers.MODE_REGEX,
                     "cooldown": 0, "beep": False, "notify": False})
        w._triggers_feed(b"\x1b[0;32mI (123) app: ok\x1b[0m\r\n", "rx")
        self.assertEqual(w._trigger_engine.hits(0), 1)
        self.assertEqual(w._trigger_engine.hits(1), 1)

    def test_modbus_and_xfer_paths_feed_tx_rules(self):
        """回归：Modbus 主机与文件传输都绕过 _send_text，采集入口必须各自补上。"""
        import inspect
        for fn in ("_mbm_send_raw", "_xfer_send", "_terminal_send"):
            src = inspect.getsource(getattr(CommTool, fn))
            self.assertIn("_record_stream_tx", src, fn + " 未接入 TX 采集")

    def test_xfer_only_records_fully_sent_chunks(self):
        """文件传输断线、无目标、零写或短写时，未上线路的数据不能进入录制/TX 告警。"""
        w = self.w
        old = (w.conn, w._conn_proto, w._xfer_target)

        class _Conn:
            def __init__(self, result):
                self.result = result

            def send(self, data, target=None):
                if isinstance(self.result, Exception):
                    raise self.result
                return self.result

        rule = {"pattern": "PING", "scope": "tx", "cooldown": 0,
                "beep": False, "notify": False}
        try:
            w._conn_proto = PROTO_SERIAL
            w._xfer_target = None
            for result in (OSError("disconnected"), SEND_NO_TARGET, 0, 2):
                self._rules(rule)
                w.conn = _Conn(result)
                w._xfer_send(b"PING")
                self.assertEqual(w._trigger_engine.hits(0), 0, repr(result))
            self._rules(rule)
            w.conn = _Conn(4)
            w._xfer_send(b"PING")
            self.assertEqual(w._trigger_engine.hits(0), 1)
        finally:
            w.conn, w._conn_proto, w._xfer_target = old
            w._reset_trigger_decoders()

    def test_pending_edit_flushed_by_save(self):
        """回归：规则编辑有 400ms 去抖，保存 / 退出正好落在窗口内时不能把它丢了。"""
        w = self.w
        self._rules({"name": "old", "pattern": "A"})
        old_dlg = getattr(w, "_triggers_dlg", None)
        w.open_triggers()
        dlg = w._triggers_dlg
        try:
            dlg.ed_pat.setText("CHANGED")
            self.assertTrue(dlg._save_timer.isActive())
            w._save_settings()
            self.assertEqual(w._triggers[0]["pattern"], "CHANGED")
        finally:
            dlg._save_timer.stop()
            dlg._stat_timer.stop()
            dlg.close()
            w._triggers_dlg = old_dlg

    def test_alert_mark_is_decoration_not_rx_body(self):
        """回归：告警标记是我们自己插的说明行，不该被当成设备发来的 RX 正文
        （否则会参与关键字过滤、混进收发统计口径）。"""
        from theme import ROLE_TS, ROLE_RX
        w = self.w
        self._rules({"name": "m", "pattern": "Z", "cooldown": 0, "mark": True,
                     "beep": False, "notify": False})
        w.txt_recv.clear()
        w._reset_recv_state()
        w._triggers_feed(b"Z", "rx")
        doc = w.txt_recv.document()
        blk, role = doc.begin(), None
        while blk.isValid():
            if w._t("trg_mark_prefix") in blk.text():
                it = blk.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid():
                        role = frag.charFormat().property(ROLE_PROP)
                        break
                    it += 1
                break
            blk = blk.next()
        self.assertEqual(role, ROLE_TS)
        self.assertNotEqual(role, ROLE_RX)

    def test_alert_mark_does_not_corrupt_terminal_cursor(self):
        """终端告警标记应独占一行；下一包不能回到旧光标把标记覆盖掉。"""
        w = self.w
        self._rules({"name": "alarm", "pattern": "ERROR", "cooldown": 0,
                     "mark": True, "beep": False, "notify": False})
        w.txt_recv.clear()
        w._set_terminal_enabled(True)
        try:
            w.on_data_received(b"ERROR")
            w.on_data_received(b"NEXT")
            shown = w.txt_recv.toPlainText()
            self.assertIn("ERROR\n⚠ %s alarm\nNEXT" % w._t("trg_mark_prefix"), shown)
        finally:
            w._set_terminal_enabled(False)

    def test_config_switch_reloads_ansi_and_rules(self):
        """回归(P1)：切换 / 导入配置后必须换上新配置的 ANSI 开关与触发规则，
        不能继续用内存里的旧值。"""
        w = self.w
        w.sw_ansi.setChecked(False, animate=False)
        self._rules()
        w.settings.setValue("ansi_color", True)
        w.settings.setValue("triggers", json.dumps(
            [triggers.normalize({"name": "z", "pattern": "Z"})], ensure_ascii=False))
        try:
            w._load_settings()
            self.assertTrue(w._ansi_on and w.sw_ansi.isChecked())
            self.assertEqual(len(w._triggers), 1)
            self.assertTrue(w._trigger_engine.active())
        finally:
            w.settings.remove("triggers")
            w.settings.setValue("ansi_color", False)


class EventFilterLifetimeTests(unittest.TestCase):
    """app 级事件过滤器的存活期防御。"""

    def test_survives_window_destroy_and_recreate(self):
        """回归：eventFilter 装在 QApplication 上，窗口销毁后 Qt 仍会回调进来，
        那时 Python 侧属性已清 —— 不加守卫会 AttributeError 崩在半个对象上
        （同进程反复开关窗口时必现，写测试或多窗口场景会踩到）。"""
        for _ in range(3):
            w = CommTool()
            w.show()
            _APP.processEvents()
            # 跳过「最小化/退出」模态提示：offscreen 下 dlg.exec_() 无人点击会永久阻塞
            # （_closing_real=True 走真正退出分支，等同用户选「退出」）。
            w._closing_real = True
            w.close()
            w.deleteLater()
            _APP.processEvents()

    def test_guard_does_not_break_live_instance(self):
        """守卫不能误伤正常实例：属性还在时照常走原有分支。"""
        from PyQt5.QtCore import QEvent
        w = _win()
        self.assertTrue(hasattr(w, "_mac_tooltip"))
        self.assertFalse(w.eventFilter(w, QEvent(QEvent.None_)))

    def test_guard_handles_uninitialized_receive_view(self):
        """macOS 应用级过滤器可在接收视图创建前收到事件，不能让 Python
        AttributeError 穿透 PyQt 回调（Qt 会将其升级为 qFatal / SIGABRT）。"""
        from PyQt5.QtCore import QEvent
        w = _win()
        session = w.active_session()
        old_recv = session.txt_recv
        old_fallback = w._txt_recv_fallback
        try:
            session.txt_recv = None
            w._txt_recv_fallback = None
            self.assertFalse(w.eventFilter(w, QEvent(QEvent.None_)))
        finally:
            session.txt_recv = old_recv
            w._txt_recv_fallback = old_fallback


class TriggerDialogTests(unittest.TestCase):
    def test_existing_rule_is_editable_on_open(self):
        """回归(P2)：打开对话框时 _cur 必须落到第 0 条 —— 否则编辑区全灰，
        已有规则点不动（setCurrentRow 触发的信号被 _reloading 挡掉了）。"""
        from triggers_dialog import TriggersDialog
        w = _win()
        old = w._triggers
        try:
            w._triggers = [triggers.normalize({"name": "only", "pattern": "A"})]
            w._save_triggers()
            dlg = TriggersDialog(w)
            try:
                self.assertEqual(dlg._cur, 0)
                self.assertTrue(dlg.ed_pat.isEnabled())
                self.assertEqual(dlg.ed_pat.text(), "A")
            finally:
                dlg._stat_timer.stop()
                dlg._save_timer.stop()
                dlg.deleteLater()
        finally:
            w._triggers = old
            w._save_triggers()

    def test_sync_mode_items_safe_before_populate(self):
        """回归(P3-防御)：下拉未填充时不该崩。"""
        from triggers_dialog import TriggersDialog
        w = _win()
        dlg = TriggersDialog(w)
        try:
            dlg.cb_mode.clear()
            dlg._sync_mode_items()
        finally:
            dlg._stat_timer.stop()
            dlg._save_timer.stop()
            dlg.deleteLater()

    def test_pending_edit_survives_add_reset_and_language_reload(self):
        """会重建编辑区的操作都必须先提交去抖中的草稿。"""
        from triggers_dialog import TriggersDialog
        w = _win()
        old = w._triggers
        try:
            w._triggers = [triggers.normalize({"name": "only", "pattern": "OLD"})]
            w._save_triggers()
            dlg = TriggersDialog(w)
            try:
                dlg.ed_pat.setText("BEFORE-ADD")
                dlg._add()
                self.assertEqual(w._triggers[0]["pattern"], "BEFORE-ADD")

                dlg.list.setCurrentRow(0)
                dlg.ed_pat.setText("BEFORE-RESET")
                dlg._reset_stats()
                self.assertEqual(w._triggers[0]["pattern"], "BEFORE-RESET")

                dlg.ed_pat.setText("BEFORE-LANGUAGE")
                dlg.retranslate()
                self.assertEqual(w._triggers[0]["pattern"], "BEFORE-LANGUAGE")
                self.assertEqual(dlg.ed_pat.text(), "BEFORE-LANGUAGE")
            finally:
                dlg._stat_timer.stop()
                dlg._save_timer.stop()
                dlg.deleteLater()
        finally:
            w._triggers = old
            w._save_triggers()


if __name__ == "__main__":
    unittest.main()
