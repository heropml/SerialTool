# -*- coding: utf-8 -*-
"""Tests for custom tab titles, keyword match modes, and draft autosave."""
from __future__ import print_function

import json
import os
import sys
import csv
from pathlib import Path

import pytest
from PyQt5.QtCore import QCoreApplication, QEvent, QSettings
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor

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
