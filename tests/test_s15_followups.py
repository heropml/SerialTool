# -*- coding: utf-8 -*-
"""Tests for custom tab titles, keyword match modes, and draft autosave."""
from __future__ import print_function

import json
import os
import sys
from pathlib import Path

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_APP = QApplication.instance() or QApplication([])


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
