# -*- coding: utf-8 -*-
"""Tests for custom tab titles, keyword match modes, and draft autosave."""
from __future__ import print_function

import json
import os
import sys
import csv
from pathlib import Path

import pytest
from PyQt5.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor, QKeyEvent, QTextCharFormat, QTextCursor

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_APP = QApplication.instance() or QApplication([])
_TEST_WINDOWS = []


@pytest.fixture(autouse=True)
def _dispose_test_windows():
    """Destroy each test window before its Qt event loop can leak onward."""
    yield
    for window in reversed(_TEST_WINDOWS):
        window._close_all_sessions()
        window.deleteLater()
    _TEST_WINDOWS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _quiet(monkeypatch):
    from main_window import CommTool, PortScannerThread
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "toast", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "_confirm_dlg", lambda *a, **k: True)


def _window(monkeypatch, tmp_path, profile="feat"):
    _quiet(monkeypatch)
    from main_window import CommTool
    ini = tmp_path / ("%s.ini" % profile)
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool(profile)
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    _TEST_WINDOWS.append(w)
    return w


def test_custom_title_prefers_name_over_connection(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "rename")
    s = w.active_session()
    s._conn_proto = "Serial"
    s._conn_cfg = ("Serial", "COM9", "115200")
    assert "COM9" in s.connection_label().upper()
    s.set_custom_title("Line-A")
    assert s.tab_label() == "Line-A"
    assert s.has_custom_title()
    tip_conn = s.connection_label()
    assert tip_conn != "Line-A"
    data = s.to_persist()
    assert data.get("custom_title") == "Line-A"
    assert data.get("title_index") is None
    s.set_custom_title("   ")
    assert not s.has_custom_title()
    assert s.title_index == 1
    w._close_all_sessions()


def test_custom_title_restore_and_conflict_allowed(monkeypatch, tmp_path):
    from session import Session
    w = _window(monkeypatch, tmp_path, "rename-restore")
    a = Session.from_persist(w, {"id": "a", "custom_title": "Same", "title_index": None})
    b = Session.from_persist(w, {"id": "b", "title": "Same", "title_index": None})
    c = Session.from_persist(
        w, {"id": "c", "custom_title": "Session-7", "title_index": None})
    assert a.tab_label() == "Same"
    assert b.tab_label() == "Same"
    assert c.tab_label() == "Session-7"
    assert c.has_custom_title()
    w._close_all_sessions()


def test_keyword_rule_regex_and_hex_helpers():
    from keyword_groups import rule_matches, rule_spans, normalize_match
    assert normalize_match(None) == "plain"
    assert normalize_match("REGEX") == "regex"
    assert rule_matches("err ERROR ok", {"pattern": r"ERR\w+", "match": "regex"})
    assert not rule_matches("err ERROR ok", {"pattern": r"ERR\w+", "match": "plain"})
    assert rule_matches("AA BB CC", {"pattern": "BBCC", "match": "hex"})
    spans = rule_spans("AA BB CC", {"pattern": "BBCC", "match": "hex"})
    assert spans and spans[0][1] > spans[0][0]
    # catastrophic regex rejected -> no match
    assert not rule_matches("a" * 30, {"pattern": r"(a+)+$", "match": "regex"})
    # Zero-width regexes cannot paint a highlight or keep filtered rows.
    assert not rule_matches("abc", {"pattern": r"^", "match": "regex"})
    # A leading empty alternative must not hide a later paintable match.
    assert rule_matches("abc", {"pattern": r"^|b", "match": "regex"})


def test_keyword_match_limit_caps_work():
    from search_helper import find_spans
    from keyword_groups import rule_spans

    assert len(find_spans("x" * 1000, "x", limit=7)) == 7
    assert len(rule_spans(
        "x" * 1000, {"pattern": "x", "match": "regex"}, limit=9)) == 9


def test_keyword_highlight_uses_match_mode(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "kw-match")
    w._keyword_groups = [{"name": "t", "rules": [
        {"pattern": r"OK\d+", "match": "regex", "mode": "bg",
         "color": "#FFD60A", "enabled": True, "scope": "both"},
    ]}]
    w._keyword_active = 0
    te = w.txt_recv
    te.clear()
    te.setPlainText("cmd OK12 done")
    # Tag whole body as RX so keyword matcher considers it.
    from main_window import ROLE_PROP, ROLE_RX
    cur = QTextCursor(te.document())
    cur.select(QTextCursor.Document)
    fmt = cur.charFormat()
    fmt.setProperty(ROLE_PROP, ROLE_RX)
    cur.setCharFormat(fmt)
    w._refresh_extra_selections(rebuild_search=False)
    sels = te.extraSelections()
    assert sels, "expected regex keyword highlight selections"
    w._close_all_sessions()


def test_keyword_highlight_matches_across_same_role_fragments(monkeypatch, tmp_path):
    """Formatting fragments must not split one logical RX/TX keyword stream."""
    from main_window import ROLE_PROP, ROLE_RX

    w = _window(monkeypatch, tmp_path, "kw-fragment")
    te = w.txt_recv
    cases = (
        ("ER", "ROR", "ERROR", "plain"),
        ("OK", "12", r"OK\d+", "regex"),
        ("AA ", "BB", "AABB", "hex"),
    )
    for left, right, pattern, match_mode in cases:
        te.clear()
        cur = QTextCursor(te.document())
        first_fmt = QTextCharFormat()
        first_fmt.setProperty(ROLE_PROP, ROLE_RX)
        first_fmt.setForeground(QColor("#FF0000"))
        second_fmt = QTextCharFormat()
        second_fmt.setProperty(ROLE_PROP, ROLE_RX)
        second_fmt.setForeground(QColor("#0000FF"))
        cur.insertText(left, first_fmt)
        cur.insertText(right, second_fmt)
        w._keyword_groups = [{"name": "t", "rules": [{
            "pattern": pattern, "match": match_mode, "mode": "bg",
            "color": "#FFD60A", "enabled": True, "scope": "rx",
        }]}]
        w._keyword_active = 0

        w._refresh_extra_selections(rebuild_search=False)

        selected = [sel.cursor.selectedText() for sel in te.extraSelections()]
        assert left + right in selected
        assert w._block_has_keyword_match(te.document().firstBlock())
    w._close_all_sessions()


def test_workspace_autosave_debounces_user_edit(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "autosave")
    saves = []
    monkeypatch.setattr(w, "_save_settings", lambda strict=False: saves.append(1) or True)
    assert w._autosave_ready is True
    w.txt_send.setPlainText("draft-1")
    assert saves == []
    assert w._autosave_timer.isActive()
    w._autosave_timer.stop()
    w._flush_workspace_autosave()
    assert saves == [1]
    # paused path must not flush
    saves.clear()
    with w._workspace_autosave_paused():
        w.txt_send.setPlainText("draft-2")
        assert not w._autosave_timer.isActive()
        w._flush_workspace_autosave()
    assert saves == []
    w._close_all_sessions()


def test_session_add_and_close_schedule_workspace_autosave(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "autosave-tabs")
    scheduled = []
    monkeypatch.setattr(
        w, "_schedule_workspace_autosave",
        lambda *_args: scheduled.append(len(w._sessions)),
    )
    added = w.add_session(activate=False)
    assert added is not None
    assert scheduled == [2]
    scheduled.clear()
    assert w.switch_session(added.id)
    assert scheduled == [2]
    scheduled.clear()
    assert w.close_session(added.id, confirm=False)
    assert scheduled == [1]
    w._close_all_sessions()


def test_session_switch_pauses_pending_workspace_autosave(monkeypatch, tmp_path):
    """Autosave cannot snapshot the shared UI while a tab is half-loaded."""
    w = _window(monkeypatch, tmp_path, "autosave-switch-pause")
    target = w.add_session(activate=False)
    w._autosave_timer.start(5000)
    saves = []
    observed = []
    real_load = w._load_session_into_ui
    monkeypatch.setattr(
        w, "_save_settings", lambda strict=False: saves.append(True) or True)

    def _load(session):
        observed.append((w._autosave_suppress, w._autosave_timer.isActive()))
        w._flush_workspace_autosave()
        return real_load(session)

    monkeypatch.setattr(w, "_load_session_into_ui", _load)

    assert w.switch_session(target.id)
    assert observed == [(1, False)]
    assert saves == []
    assert w._autosave_timer.isActive()
    w._autosave_timer.stop()
    w._close_all_sessions()


def test_session_switch_autosave_persists_previous_draft(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "autosave-switch-draft")
    first = w.active_session()
    target = w.add_session(activate=False)
    w.txt_send.setPlainText("draft-a")

    assert w.switch_session(target.id)
    w._autosave_timer.stop()
    assert w._save_settings()

    disk = QSettings(w.settings.fileName(), QSettings.IniFormat)
    payload = json.loads(str(disk.value("sessions_v1", "[]")))
    by_id = {item["id"]: item for item in payload}
    assert by_id[first.id]["send_draft"] == "draft-a"
    assert str(disk.value("active_session_id", "")) == target.id
    w._close_all_sessions()


def test_dtr_rts_changes_schedule_workspace_autosave(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "autosave-control-lines")
    w._autosave_timer.stop()

    w.sw_dtr.setChecked(not w.sw_dtr.isChecked())
    assert w._autosave_timer.isActive()
    w._autosave_timer.stop()

    w.sw_rts.setChecked(not w.sw_rts.isChecked())
    assert w._autosave_timer.isActive()
    w._autosave_timer.stop()
    w._close_all_sessions()


def test_port_and_flow_changes_schedule_workspace_autosave(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "autosave-serial-fields")
    w.cb_port.addItem("COM_TEST", "COM_TEST")
    port_index = w.cb_port.count() - 1
    w.cb_port.setCurrentIndex(port_index)
    w._autosave_timer.stop()
    w.cb_port.activated.emit(port_index)
    assert w._autosave_timer.isActive()
    w._autosave_timer.stop()

    w.cb_flow.setCurrentIndex((w.cb_flow.currentIndex() + 1) % w.cb_flow.count())
    assert w._autosave_timer.isActive()
    w._autosave_timer.stop()
    w._close_all_sessions()


def test_workspace_autosave_pause_restores_preexisting_pending_timer(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "autosave-resume")
    w._autosave_timer.start(5000)
    with w._workspace_autosave_paused():
        assert not w._autosave_timer.isActive()
        with w._workspace_autosave_paused():
            assert not w._autosave_timer.isActive()
        assert not w._autosave_timer.isActive()
    assert w._autosave_timer.isActive()
    w._autosave_timer.stop()
    w._close_all_sessions()


def test_recv_search_passes_hard_cap_into_find_spans(monkeypatch, tmp_path):
    """Search rebuild must stop scanning inside find_spans, not after."""
    w = _window(monkeypatch, tmp_path, "search-limit")
    seen = {}

    def _fake_find_spans(text, term, mode="plain", case_sensitive=False,
                         hexdump=False, limit=None, start=0):
        seen["limit"] = limit
        seen["start"] = start
        n = 0 if limit is None else max(0, int(limit))
        base = int(start or 0)
        return [(base + i, base + i + 1) for i in range(n)]

    monkeypatch.setattr("search_helper.find_spans", _fake_find_spans)
    monkeypatch.setattr("search_helper.to_utf16_spans", lambda text, spans: spans)
    w._search_term = "00"
    w._search_mode = "hex"
    w.txt_recv.setPlainText("00 00 00")
    w._refresh_extra_selections(rebuild_search=True)
    assert seen.get("limit") == w._KW_MAX_SELECTIONS + 1
    assert len(w._search_matches) == w._KW_MAX_SELECTIONS
    assert w._search_match_capped is True
    w._close_all_sessions()


def test_active_timestamp_toggle_beats_stale_display_opts(monkeypatch, tmp_path):
    """Live UI on the active tab must not be masked by a prior snapshot."""
    w = _window(monkeypatch, tmp_path, "active-ts-ui")
    session = w.active_session()
    session.display_opts = dict(session.display_opts or {}, show_timestamp=False)
    w._display_context = None
    w.sw_show_timestamp.setChecked(True)
    assert w._session_display_flag("show_timestamp", True) is True
    assert w._timestamp_prefix("rx").startswith("[")
    assert "\u2190" in w._timestamp_prefix("rx")

    w.sw_show_timestamp.setChecked(False)
    assert w._session_display_flag("show_timestamp", False) is False
    assert w._timestamp_prefix("rx") == ""

    # Background snapshot still wins when an explicit display context is set.
    w._display_context = {"show_timestamp": False}
    w.sw_show_timestamp.setChecked(True)
    assert w._session_display_flag("show_timestamp", True) is False
    w._display_context = None
    w._close_all_sessions()


def test_open_io_graph_applies_rate_preset(monkeypatch, tmp_path):
    """I/O Graph is an isolated, reversible view that preserves plot samples."""
    pytest.importorskip("pyqtgraph")
    w = _window(monkeypatch, tmp_path, "io-graph-entry")
    w._rx_rate = 1200.0
    w._tx_rate = 340.0
    w.open_plot()
    dlg = w._plot_dlg
    dlg._append_vals([7.0], names=["rx_Bps"])
    generic = dlg._channels[0]
    assert list(generic["ys"]) == [7.0]
    assert list(generic["xs"]) == [0]

    # A named rate source may collide with a user field carrying the same label.
    dlg.feed_named_samples([{"tag": "rx_Bps", "value": 11.0}])
    same_named = dlg._channels[dlg._name_to_idx["rx_Bps"]]
    assert same_named is not generic
    assert same_named["name"] == generic["name"] == "rx_Bps"
    rate_before = list(same_named["ys"])
    assert rate_before == [11.0]
    saved_sample_idx = dlg._sample_idx

    w.open_io_graph()
    dlg = getattr(w, "_plot_dlg", None)
    assert dlg is not None
    assert dlg.isVisible()
    assert dlg._io_graph_mode is True
    assert dlg.cb_xaxis.currentIndex() == 1
    assert dlg._x_time is True
    assert list(generic["ys"]) == [7.0]
    assert not generic["cb"].isChecked()
    for tag in ("rx_Bps", "tx_Bps", "rx_pps", "tx_pps"):
        assert tag in dlg._name_to_idx
        ch = dlg._channels[dlg._name_to_idx[tag]]
        assert ch["cb"].isChecked()
        assert ch.get("jumpable") is False
    assert len(dlg._channels[dlg._name_to_idx["rx_Bps"]]["ys"]) >= 1
    # Temporary overlay replaced the old rate series (restored on leave).
    assert list(dlg._channels[dlg._name_to_idx["rx_Bps"]]["ys"]) != rate_before

    # Exporting the temporary view must not include the hidden generic curve,
    # even though it deliberately shares the display name "rx_Bps".
    csv_path = tmp_path / "io-graph.csv"
    monkeypatch.setattr(
        "plot_dialog.QFileDialog.getSaveFileName",
        lambda *_a, **_k: (str(csv_path), "CSV (*.csv)"))
    dlg._export_csv()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    assert len(header) == 8
    assert header.count("rx_Bps") == 1

    channel_count = len(dlg._channels)
    dlg.feed(b"9\n")
    dlg.feed_named_samples([{"tag": "temperature", "value": 25.0}])
    assert len(dlg._channels) == channel_count
    assert "temperature" not in dlg._name_to_idx
    assert list(generic["ys"]) == [7.0]

    # Reopening an active I/O Graph must not reset its accumulated history.
    dlg.feed_named_samples([{"tag": "rx_Bps", "value": 9999.0}])
    rate_live = dlg._channels[dlg._name_to_idx["rx_Bps"]]
    live_before = list(rate_live["ys"])
    w.open_io_graph()
    assert list(rate_live["ys"])[:len(live_before)] == live_before

    # Closing while in I/O Graph must restore, not keep the temporary mode.
    dlg.close()
    assert dlg._io_graph_mode is False
    assert dlg.cb_xaxis.currentIndex() == 0
    assert dlg._x_time is False
    assert dlg._sample_idx == saved_sample_idx
    assert generic["cb"].isChecked()
    assert list(generic["ys"]) == [7.0]
    assert list(generic["xs"]) == [0]
    assert list(same_named["ys"]) == [11.0]
    assert list(dlg._channels[dlg._name_to_idx["rx_Bps"]]["ys"]) == rate_before
    w._close_all_sessions()


def test_io_graph_starts_fresh_segment_on_session_switch(monkeypatch, tmp_path):
    """Rate samples from two tabs must never be joined in one I/O curve."""
    pytest.importorskip("pyqtgraph")
    w = _window(monkeypatch, tmp_path, "io-graph-session-switch")
    w.open_io_graph()
    dlg = w._plot_dlg
    dlg.feed_named_samples([{"tag": "rx_Bps", "value": 9999.0}])
    rate = dlg._channels[dlg._name_to_idx["rx_Bps"]]
    assert list(rate["ys"])

    target = w.add_session(activate=True)
    assert target is w.active_session()
    assert dlg._io_graph_mode is True
    assert list(rate["xs"]) == []
    assert list(rate["ys"]) == []
    assert dlg._io_graph_restore is not None

    dlg.feed_named_samples([{"tag": "rx_Bps", "value": 7.0}])
    assert list(rate["ys"]) == [7.0]
    dlg.close()
    w._close_all_sessions()


@pytest.mark.parametrize("change", ["mode", "separator", "regex", "fields", "header"])
def test_io_graph_parser_changes_restore_then_clear(monkeypatch, tmp_path, change):
    """Parser changes leave the temporary overlay before their intentional wipe."""
    pytest.importorskip("pyqtgraph")
    w = _window(monkeypatch, tmp_path, "io-graph-parser-" + change)
    w.open_plot()
    dlg = w._plot_dlg
    dlg._append_vals([7.0])
    w.open_io_graph()
    assert dlg._io_graph_mode is True
    assert dlg._io_graph_restore is not None

    if change == "mode":
        dlg.cb_mode.setCurrentIndex((dlg.cb_mode.currentIndex() + 1) % 3)
    elif change == "separator":
        dlg.cb_sep.setCurrentIndex((dlg.cb_sep.currentIndex() + 1) % 5)
    elif change == "regex":
        dlg.ed_regex.setText(r"(\\d+)")
        dlg._on_regex_changed()
    elif change == "fields":
        dlg.ed_fields.setText("value=0:u8")
        dlg._on_fields_changed()
    else:
        dlg.ed_header.setText("AA")
        dlg._on_header_changed()

    assert dlg._io_graph_mode is False
    assert dlg._io_graph_restore is None
    assert dlg._channels == []
    dlg.close()
    w._close_all_sessions()


def _kw_sel_ranges(w):
    return [(s.cursor.selectionStart(), s.cursor.selectionEnd(),
             s.format.background().color().name().upper())
            for s in w.txt_recv.extraSelections()]


def test_keyword_highlight_incremental_only_scans_dirty_blocks(
        monkeypatch, tmp_path):
    """Appending N blocks must not re-walk the whole document on the next tick."""
    w = _window(monkeypatch, tmp_path, "kw-incr")
    w._keyword_groups = [{"name": "t", "rules": [{
        "pattern": "KW", "match": "plain", "mode": "bg",
        "color": "#FFD60A", "enabled": True, "scope": "rx",
    }]}]
    w._keyword_active = 0
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(False)
    if hasattr(w, "sw_rx_hex"):
        w.sw_rx_hex.setChecked(False)
    w.clear_recv()
    warmup = 40
    extra = 8
    for i in range(warmup):
        w._append_block_data("noise-%d\n" % i, "rx", True)
    w._refresh_extra_selections(rebuild_search=False)
    assert w._kw_scan_mode == "full"
    assert w._kw_scan_blocks >= warmup

    for i in range(extra):
        w._append_block_data("KW-hit-%d\n" % i, "rx", True)
    w._refresh_extra_selections(rebuild_search=False)
    assert w._kw_scan_mode == "incr"
    assert w._kw_scan_blocks <= extra + 2
    incr_ranges = _kw_sel_ranges(w)
    assert any("KW" in w.txt_recv.document().toPlainText()[a:b]
               for a, b, _c in incr_ranges)

    w._refresh_extra_selections(rebuild_search=False)
    assert w._kw_scan_mode == "skip"
    assert w._kw_scan_blocks == 0

    w._kw_mark_full()
    w._refresh_extra_selections(rebuild_search=False)
    assert w._kw_scan_mode == "full"
    assert w._kw_scan_blocks >= warmup + extra
    assert _kw_sel_ranges(w) == incr_ranges
    w._close_all_sessions()


def test_keyword_incremental_survives_max_block_truncation(monkeypatch, tmp_path):
    """maximumBlockCount 头部截断不能破坏尾部累积的增量脏区间（A1）。

    正文只追加到文末；头部截断会平移块号和绝对字符位置，但已追加内容永远留在文末。
    增量用累积的 st["tail"] 从末字符往回定位脏区间，再 findBlock 落到整块上扫。
    之前按块号锚定时，多块追加触发头部丢弃后会扫错区间、静默漏高亮。
    """
    w = _window(monkeypatch, tmp_path, "kw-trunc")
    w._keyword_groups = [{"name": "t", "rules": [{
        "pattern": "KW", "match": "plain", "mode": "bg",
        "color": "#FFD60A", "enabled": True, "scope": "rx",
    }]}]
    w._keyword_active = 0
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(False)
    if hasattr(w, "sw_rx_hex"):
        w.sw_rx_hex.setChecked(False)
    w.clear_recv()
    doc = w.txt_recv.document()
    doc.setMaximumBlockCount(6)      # 收窄上限，让头部截断在测试内发生
    for i in range(8):               # 填满并触发头部丢弃
        w._append_block_data("noise-%d\n" % i, "rx", True)
    w._refresh_extra_selections(rebuild_search=False)
    assert w._kw_scan_mode == "full"
    assert doc.blockCount() <= 6

    # 单次多块追加（跨 3 行 → 3 个 block）：插入后头部被截断，增量必须仍命中关键字
    w._append_block_data("pre\nKW-hit!\npost\n", "rx", True)
    w._refresh_extra_selections(rebuild_search=False)
    assert w._kw_scan_mode == "incr", "截断后应走增量路径"
    txt = w.txt_recv.document().toPlainText()
    kpos = txt.find("KW-hit!")
    assert kpos >= 0, "截断后关键字内容应仍存在: %r" % txt
    incr_ranges = _kw_sel_ranges(w)
    assert any(a == kpos and b == kpos + 2 for a, b, _c in incr_ranges), \
        "截断后增量应高亮 'KW' 于正确位置: ranges=%r txt=%r" % (incr_ranges, txt)

    # 与全量重扫结果等价（不因截断而多/漏）
    w._kw_mark_full()
    w._refresh_extra_selections(rebuild_search=False)
    assert w._kw_scan_mode == "full"
    assert _kw_sel_ranges(w) == incr_ranges
    w._close_all_sessions()


def test_keyword_full_rescan_on_terminal_toggle(monkeypatch, tmp_path):
    """进出终端模式必须触发全量重扫（A3）。

    终端模式改变正文的可匹配性（终端块无 ROLE_PROP）；_kw_rules_key 含
    terminal_on，开关即走全量，避免旧 RX 文本上的选区残留在切换后的画面上。
    """
    w = _window(monkeypatch, tmp_path, "kw-term")
    w._keyword_groups = [{"name": "t", "rules": [{
        "pattern": "KW", "match": "plain", "mode": "bg",
        "color": "#FFD60A", "enabled": True, "scope": "rx",
    }]}]
    w._keyword_active = 0
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(False)
    if hasattr(w, "sw_rx_hex"):
        w.sw_rx_hex.setChecked(False)
    w.clear_recv()
    w._append_block_data("KW-hello\n", "rx", True)
    w._refresh_extra_selections(rebuild_search=False)
    assert _kw_sel_ranges(w), "进入终端前应有高亮"

    w._set_terminal_enabled(True)
    assert w._kw_scan_mode == "full", "进终端必须全量重扫"
    w._set_terminal_enabled(False)
    assert w._kw_scan_mode == "full", "出终端必须全量重扫"
    assert _kw_sel_ranges(w), "退出终端后旧 RX 正文仍应按规则高亮"
    w._close_all_sessions()


def test_terminal_clear_screen_clears_extra_selections(monkeypatch, tmp_path):
    """终端 ESC[2J 全清后必须清掉残留的关键字选区（A4）。"""
    w = _window(monkeypatch, tmp_path, "kw-termclr")
    w._keyword_groups = [{"name": "t", "rules": [{
        "pattern": "KW", "match": "plain", "mode": "bg",
        "color": "#FFD60A", "enabled": True, "scope": "rx",
    }]}]
    w._keyword_active = 0
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(False)
    if hasattr(w, "sw_rx_hex"):
        w.sw_rx_hex.setChecked(False)
    w.clear_recv()
    w._append_block_data("KW-hit\n", "rx", True)
    w._refresh_extra_selections(rebuild_search=False)
    assert _kw_sel_ranges(w), "清屏前应有高亮"

    w._term_handle_csi(QTextCursor(w.txt_recv.document().end()), "\x1b[2J")
    assert w.txt_recv.toPlainText() == ""
    assert w.txt_recv.extraSelections() == []
    assert w._bookmarks == []
    w._close_all_sessions()


def test_search_page_skips_rebuild_when_term_unchanged(monkeypatch, tmp_path):
    """搜索：词+文档都未变才跳过全扫；文档变了则重建当前页（B1）。

    关键字高亮已走增量；搜索页是全文档 toPlainText+find_spans 的唯一全扫点。
    词/模式/大小写/hexdump 与 revision 都未变 → 跳过。词未变但文档追加 → 重建
    当前页，新命中进入搜索高亮。换词仍从第一页重建。
    """
    w = _window(monkeypatch, tmp_path, "kw-search")
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(False)
    if hasattr(w, "sw_rx_hex"):
        w.sw_rx_hex.setChecked(False)
    w.clear_recv()
    w._append_block_data("alpha line\nbeta line\n", "rx", True)

    # 打字防抖：textChanged 不再直连 _do_search，而是重启 single-shot 定时器
    assert hasattr(w, "_search_debounce")
    assert w._search_debounce.isSingleShot()
    w.ed_search.setText("alpha")
    assert w._search_debounce.isActive(), "输入后防抖定时器应处于待触发状态"
    w._do_search()   # 同步建立搜索页（测试不走事件循环，定时器不触发）
    assert len(w._search_matches) >= 1
    key0 = w._search_page_key
    n0 = len(w._search_matches)
    assert key0 is not None

    loads = {"n": 0}
    orig = w._load_search_page

    def _spy(start=0):
        loads["n"] += 1
        return orig(start)

    w._load_search_page = _spy

    # 文档未变 + 词未变 → 跳过 toPlainText+find_spans
    w._refresh_extra_selections(rebuild_search=True)
    assert w._search_page_key == key0
    assert loads["n"] == 0, "文档未变不应重建搜索页"

    # 持续收数据：词未变但文档变了 → 重建当前页，新命中可见
    w._append_block_data("more alpha here\n", "rx", True)
    w._refresh_extra_selections(rebuild_search=True)
    assert w._search_page_key == key0, "词未变时 query key 不变"
    assert loads["n"] == 1, "文档变了应重建当前页"
    assert len(w._search_matches) > n0, "追加的命中应出现在当前搜索页"

    # 换词 → 强制从第一页重建
    w.ed_search.setText("beta")
    w._do_search()
    assert w._search_page_key != key0
    assert any(w.txt_recv.document().toPlainText()[a:b] == "beta"
               for a, b, _c in _kw_sel_ranges(w)) or w._search_matches
    w._close_all_sessions()


def test_ctrl_enter_sends_plain_enter_stays_newline(monkeypatch, tmp_path):
    """普通发送框：Ctrl+Enter 走 do_send；裸 Enter 不拦截（留给换行）。"""
    w = _window(monkeypatch, tmp_path, "ctrl-enter")
    sent = []
    w.do_send = lambda: sent.append("send")
    ctrl = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
    assert w.eventFilter(w.txt_send, ctrl) is True
    assert sent == ["send"]
    sent[:] = []
    enter = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    assert w.eventFilter(w.txt_send, enter) is not True
    assert sent == []
    keypad = QKeyEvent(QEvent.KeyPress, Qt.Key_Enter, Qt.ControlModifier)
    assert w.eventFilter(w.txt_send, keypad) is True
    assert sent == ["send"]
    sent[:] = []
    repeat = QKeyEvent(
        QEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier, "", True, 1)
    assert w.eventFilter(w.txt_send, repeat) is True
    assert sent == [], "长按 Ctrl+Enter 不应连发"
    override = QKeyEvent(QEvent.ShortcutOverride, Qt.Key_Return, Qt.ControlModifier)
    assert w.eventFilter(w.txt_send, override) is True
    assert sent == [], "ShortcutOverride 只认领快捷键，不发送"
    sent[:] = []
    w._set_terminal_enabled(True)
    term = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
    assert w.eventFilter(w.txt_send, term) is True
    assert sent == [], "终端模式 Ctrl+Enter 应走按键透传，不走 do_send"
    w._close_all_sessions()


def test_ctrl_enter_commits_ime_before_send(monkeypatch, tmp_path):
    """Ctrl+Enter 发送前必须先提交 IME 组合，保证组词未上屏也发完整内容。"""
    w = _window(monkeypatch, tmp_path, "ctrl-enter-ime")
    order = []
    w._commit_ime_composition = lambda: order.append("commit")
    w.do_send = lambda: order.append("send")
    ctrl = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
    assert w.eventFilter(w.txt_send, ctrl) is True
    assert order == ["commit", "send"], "IME 提交必须先于发送"
    w._close_all_sessions()


def test_commit_ime_composition_safe_without_ime(monkeypatch, tmp_path):
    """无活动 IME 组合时提交为空操作，不抛异常、不阻塞后续发送。"""
    w = _window(monkeypatch, tmp_path, "ctrl-enter-ime-off")
    sent = []
    w.do_send = lambda: sent.append("send")
    # 真实 QGuiApplication.inputMethod()（offscreen 下存在但无组合）→ 空操作
    w._commit_ime_composition()
    ctrl = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.ControlModifier)
    assert w.eventFilter(w.txt_send, ctrl) is True
    assert sent == ["send"]
    w._close_all_sessions()


def test_log_flush_reaches_file_and_tolerates_stringio(monkeypatch, tmp_path):
    """实时日志 write 后 flush 可见；关闭时 fsync；StringIO 无 fileno 不炸。"""
    import io
    w = _window(monkeypatch, tmp_path, "log-flush")
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(False)
    monkeypatch.setattr(w, "_maybe_rotate_log", lambda now=None, session=None: None)
    path = tmp_path / "live.log"
    session = w.active_session()
    session._log_file = open(path, "a", encoding="utf-8")
    session._log_file_path = str(path)
    session._log_ends_with_nl = True
    w._write_log_block("HELLO-FLUSH\n", "rx", True)
    assert "HELLO-FLUSH" in path.read_text(encoding="utf-8")
    w._flush_log_file(session=session, to_disk=True)
    w._close_log_file(session=session, toast=False)
    assert "HELLO-FLUSH" in path.read_text(encoding="utf-8")

    buf = io.StringIO()
    session._log_file = buf
    session._log_ends_with_nl = True
    w._write_log_block("STRINGIO-OK\n", "rx", True)
    w._flush_log_file(session=session, to_disk=True)
    assert "STRINGIO-OK" in buf.getvalue()
    session._log_file = None
    w._close_all_sessions()


def test_idle_log_sync_isolates_fsync_errors(monkeypatch, tmp_path):
    """定时 fsync 槽必须吞掉 OSError，不能让未捕获异常冒出 Qt timer。"""
    w = _window(monkeypatch, tmp_path, "log-idle-sync")
    session = w.active_session()
    session._log_file = object()

    def boom(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(w, "_flush_log_file", boom)
    try:
        w._sync_open_log_files()
    finally:
        session._log_file = None
    w._close_all_sessions()


def test_log_flush_error_closes_live_log(monkeypatch, tmp_path):
    """flush 失败必须走原来的关日志路径，不能静默继续写。"""
    w = _window(monkeypatch, tmp_path, "log-flush-err")
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(False)
    monkeypatch.setattr(w, "_maybe_rotate_log", lambda now=None, session=None: None)
    session = w.active_session()

    class _BoomFile(object):
        def write(self, _s):
            return None

        def flush(self):
            raise OSError("disk full")

        def close(self):
            self.closed = True

        def fileno(self):
            raise OSError("no fd")

    boom = _BoomFile()
    session._log_file = boom
    session._log_ends_with_nl = True
    session.log_wanted = True
    w._write_log_block("X\n", "rx", True)
    assert session._log_file is None
    assert session.log_wanted is False
    w._close_all_sessions()
