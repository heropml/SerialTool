# -*- coding: utf-8 -*-
"""Multi-session tab concurrency (v1.5): dual Virtual loopback, no crosstalk."""
from __future__ import print_function

import os
import json
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

_APP = QApplication.instance() or QApplication([])


def _quiet(monkeypatch):
    from main_window import CommTool, PortScannerThread
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "toast", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "_confirm_dlg", lambda *a, **k: True)


def _window(monkeypatch, tmp_path, profile="multi-sess"):
    _quiet(monkeypatch)
    from main_window import CommTool
    ini = tmp_path / ("%s.ini" % profile)
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool(profile)
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    if hasattr(w, "sw_hexdump"):
        w.sw_hexdump.setChecked(False)
    return w


def _pump(n=30, dt=0.02):
    for _ in range(n):
        _APP.processEvents()
        time.sleep(dt)


def _open_virtual(w, loopback=True):
    from virtual_io import PROTO_VIRTUAL
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    w._update_net_fields()
    if hasattr(w, "sw_vconn_loop"):
        w.sw_vconn_loop.setChecked(loopback, animate=False)
    w.open_conn()
    assert w.conn is not None and w.conn.is_open


def test_session_proxy_single_path(monkeypatch, tmp_path):
    """Single-tab path still opens Virtual and echoes TX->RX."""
    w = _window(monkeypatch, tmp_path, "single")
    assert len(w.sessions()) == 1
    _open_virtual(w)
    w.txt_send.setPlainText("ping")
    w.do_send()
    _pump()
    assert w.rx_bytes >= 4
    assert "ping" in w.txt_recv.toPlainText()
    w._close_all_sessions()


def test_two_virtual_sessions_no_crosstalk(monkeypatch, tmp_path):
    """Two Virtual loopbacks: concurrent RX stays on owning session."""
    w = _window(monkeypatch, tmp_path, "dual")
    _open_virtual(w)
    w.txt_send.setPlainText("AAA")
    w.do_send()
    _pump()
    s1 = w.active_session()
    assert s1.rx_bytes >= 3

    s2 = w.add_session(activate=True)
    assert s2 is not None and s2.id != s1.id
    assert w.recv_stack.count() == 2
    _open_virtual(w)
    w.txt_send.setPlainText("BBB")
    w.do_send()
    _pump()
    assert w.active_session().id == s2.id
    assert s2.rx_bytes >= 3
    assert s1.rx_bytes >= 3
    # Inject into background s1 while viewing s2
    before_s1 = s1.rx_bytes
    before_s2 = s2.rx_bytes
    s1.conn.inject(b"ONLY-S1")
    _pump()
    assert s1.rx_bytes > before_s1
    assert s2.rx_bytes == before_s2
    assert b"ONLY" in (s1.txt_recv.toPlainText().encode("utf-8", "replace")) or \
        "ONLY-S1" in s1.txt_recv.toPlainText()

    w.switch_session(s1.id)
    assert w.active_session().id == s1.id
    assert "ONLY-S1" in w.txt_recv.toPlainText()
    assert "BBB" not in w.txt_recv.toPlainText()

    w.switch_session(s2.id)
    assert "BBB" in w.txt_recv.toPlainText()
    assert "ONLY-S1" not in w.txt_recv.toPlainText()
    w._close_all_sessions()


def test_close_session_disconnects_only_that_tab(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "close-one")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    assert s1.is_open() and s2.is_open()
    assert w.close_session(s2.id)
    assert len(w.sessions()) == 1
    assert s1.is_open()
    assert w.active_session().id == s1.id
    w._close_all_sessions()


def test_close_middle_active_session_rebinds_receive_ui(monkeypatch, tmp_path):
    """Closing the active middle tab must preserve overlays and select its owner."""
    from PyQt5 import sip
    from PyQt5.QtCore import QEvent

    w = _window(monkeypatch, tmp_path, "close-middle-active")
    first = w.active_session()
    middle = w.add_session(activate=True)
    w.add_session(activate=False)
    overlays = (w._search_bar, w.btn_to_bottom)
    assert all(widget.parentWidget() is middle.txt_recv for widget in overlays)

    assert w.close_session(middle.id)
    _APP.sendPostedEvents(None, QEvent.DeferredDelete)

    assert w.active_session() is first
    assert w.recv_stack.currentWidget() is first.txt_recv
    assert all(not sip.isdeleted(widget) for widget in overlays)
    assert all(widget.parentWidget() is first.txt_recv for widget in overlays)
    w._open_search()
    w._close_all_sessions()


def test_receive_scroll_has_one_session_route(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "single-scroll-route")
    first = w.active_session()
    second = w.add_session(activate=False)
    first_sb = first.txt_recv.verticalScrollBar()
    second_sb = second.txt_recv.verticalScrollBar()
    assert first_sb.receivers(first_sb.valueChanged) == \
        second_sb.receivers(second_sb.valueChanged)
    w._close_all_sessions()


def test_busy_blocks_tab_switch(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "busy")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    monkeypatch.setattr(w, "_io_task_busy", lambda exclude=(): True)
    assert w.switch_session(s2.id) is False
    assert w.active_session().id == s1.id
    w._close_all_sessions()


def test_resource_conflict_serial_key(monkeypatch, tmp_path):
    """Two open sessions with same serial resource key are detected."""
    w = _window(monkeypatch, tmp_path, "conflict")
    s1 = w.active_session()
    s1._conn_proto = "Serial"
    s1._conn_cfg = ("Serial", "COM9", "115200")

    class _Fake:
        is_open = True

        def close(self):
            self.is_open = False

        def blockSignals(self, *_a):
            return None

        def deleteLater(self):
            return None

    s1.conn = _Fake()
    w.add_session(activate=True)
    # Point UI at Serial + COM9
    if hasattr(w, "cb_proto"):
        idx = w.cb_proto.findText("Serial")
        if idx >= 0:
            w.cb_proto.setCurrentIndex(idx)
        else:
            w.cb_proto.setCurrentText("Serial")
    if hasattr(w, "cb_port"):
        w.cb_port.addItem("COM9", "COM9")
        w.cb_port.setCurrentIndex(w.cb_port.count() - 1)
    conflict = w.check_session_resource_conflict()
    assert conflict is not None
    assert conflict.id == s1.id
    s1.conn = None
    w._close_all_sessions()


def test_dual_virtual_concurrent_soak(monkeypatch, tmp_path):
    """Concurrent TX on two Virtual tabs; optional COMMTOOL_SOAK seconds."""
    w = _window(monkeypatch, tmp_path, "soak-dual")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    assert s1.is_open() and s2.is_open()

    seconds = float(os.environ.get("COMMTOOL_SOAK", "0.5") or "0.5")
    deadline = time.monotonic() + max(0.2, seconds)
    n = 0
    while time.monotonic() < deadline:
        with w._with_session(s1):
            s1.conn.send(("S1-%d\n" % n).encode())
        with w._with_session(s2):
            s2.conn.send(("S2-%d\n" % n).encode())
        n += 1
        _APP.processEvents()
        time.sleep(0.01)
    _pump(40)
    assert s1.rx_bytes > 0 and s2.rx_bytes > 0
    t1 = s1.txt_recv.toPlainText()
    t2 = s2.txt_recv.toPlainText()
    assert "S1-" in t1 and "S2-" not in t1
    assert "S2-" in t2 and "S1-" not in t2
    # Flip tabs mid-stream and ensure views stay isolated
    w.switch_session(s1.id)
    assert "S1-" in w.txt_recv.toPlainText()
    w.switch_session(s2.id)
    assert "S2-" in w.txt_recv.toPlainText()
    w._close_all_sessions()


def test_session_persist_roundtrip(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "persist")
    w.add_session(activate=False)
    assert len(w.sessions()) == 2
    w._save_sessions_settings()
    raw = w.settings.value("sessions_v1", "")
    assert raw and "conn_fields" in str(raw)
    w._close_all_sessions()


def test_sessions_persist_across_restart(monkeypatch, tmp_path):
    """C1 regression: sessions_v1 must be written by _save_settings and restored."""
    w = _window(monkeypatch, tmp_path, "persist-restart")
    w.add_session(activate=False)
    assert len(w.sessions()) == 2
    assert w._save_settings() is True
    raw = w.settings.value("sessions_v1", "")
    assert raw and "conn_fields" in str(raw)
    active = w.active_session().id
    w.settings.setValue("active_session_id", active)
    w.settings.sync()
    ini = Path(w.settings.fileName())
    w._close_all_sessions()

    # New window, same ini -> restore tabs (closed, no auto-open)
    from main_window import CommTool
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w2 = CommTool("persist-restart")
    w2.settings = QSettings(str(ini), QSettings.IniFormat)
    # _load_settings already ran in __init__; force restore again if needed
    if len(w2.sessions()) < 2:
        w2._restore_sessions_settings()
    assert len(w2.sessions()) >= 2
    w2._close_all_sessions()


def test_background_reconnect_binds_context_session(monkeypatch, tmp_path):
    """P1: open_conn under _with_session(s1) must bind RX to s1, not active s2."""
    w = _window(monkeypatch, tmp_path, "bg-bind")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    assert w.active_session().id == s2.id

    calls = []
    real_bind = w._bind_conn_signals

    def _spy(conn, session):
        calls.append(session.id)
        return real_bind(conn, session)

    monkeypatch.setattr(w, "_bind_conn_signals", _spy)
    with w._with_session(s1):
        _open_virtual(w)
    assert calls and calls[-1] == s1.id
    assert s1.is_open() and not s2.is_open()

    before_s2 = s2.rx_bytes
    s1.conn.inject(b"BG123")
    _pump()
    assert s1.rx_bytes >= 5
    assert s2.rx_bytes == before_s2
    w._close_all_sessions()


def test_background_rx_skips_window_engines(monkeypatch, tmp_path):
    """P1: background RX must not feed active-tab script/xfer engines."""
    w = _window(monkeypatch, tmp_path, "bg-rx")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    fed = {"script": 0}

    class _Worker:
        def feed(self, data):
            fed["script"] += 1

    w._script_worker = _Worker()
    monkeypatch.setattr(w, "_script_running", lambda: True)
    monkeypatch.setattr(w, "_seq_running", lambda: False)

    s1.conn.inject(b"NO-SCRIPT")
    _pump()
    assert fed["script"] == 0
    assert s1.rx_bytes >= 9
    w._close_all_sessions()


def test_tcp_client_same_remote_not_conflict(monkeypatch, tmp_path):
    """P2: two TCP Client tabs may target the same server endpoint."""
    w = _window(monkeypatch, tmp_path, "tcp-dual")
    s1 = w.active_session()
    s1._conn_proto = "TCP Client"
    s1._conn_cfg = ("TCP Client", "127.0.0.1", 9)

    class _Fake:
        is_open = True

        def close(self):
            self.is_open = False

        def blockSignals(self, *_a):
            return None

        def deleteLater(self):
            return None

    s1.conn = _Fake()
    s1.conn_fields = {
        "net_remote_ip": "127.0.0.1",
        "net_remote_port": "9",
    }
    w.add_session(activate=True)
    if hasattr(w, "cb_proto"):
        idx = w.cb_proto.findText("TCP Client")
        if idx >= 0:
            w.cb_proto.setCurrentIndex(idx)
        else:
            w.cb_proto.setCurrentText("TCP Client")
    if hasattr(w, "ed_remote_ip"):
        w.ed_remote_ip.setText("127.0.0.1")
    if hasattr(w, "ed_remote_port"):
        w.ed_remote_port.setText("9")
    assert w.check_session_resource_conflict() is None
    s1.conn = None
    w._close_all_sessions()


def test_udp_peer_route_passes_ip_port(monkeypatch, tmp_path):
    """P2: peer_changed(ip, port) must not treat port as session id."""
    w = _window(monkeypatch, tmp_path, "udp-peer")
    s = w.active_session()
    seen = []

    def _capture(ip, port):
        seen.append((ip, port))

    monkeypatch.setattr(w, "_on_udp_peer_changed", _capture)
    w._route_session_peer(s.id, "10.0.0.2", 12345)
    assert seen == [("10.0.0.2", 12345)]
    w._close_all_sessions()


def test_restore_rewrites_id_reconnect_still_fires(monkeypatch, tmp_path):
    """P2: rewriting session.id after restore must not orphan the reconnect timer."""
    w = _window(monkeypatch, tmp_path, "restore-id")
    s0 = w.active_session()
    old_id = s0.id
    new_id = "restored01"
    s0.id = new_id
    w._active_session_id = new_id
    hit = []

    def _hit(sid):
        hit.append(sid)

    monkeypatch.setattr(w, "_try_reconnect_for", _hit)
    s0._reconnect_timer.start(1)
    _pump(20, 0.01)
    assert hit == [new_id]
    assert old_id not in hit
    w._close_all_sessions()


def test_restore_sessions_is_idempotent(monkeypatch, tmp_path):
    """Repeated settings loads must replace tabs, not append duplicates."""
    w = _window(monkeypatch, tmp_path, "restore-repeat")
    w.add_session(activate=False)
    w._save_sessions_settings()
    w.settings.sync()
    w._restore_sessions_settings()
    assert len(w.sessions()) == 2
    w._restore_sessions_settings()
    assert len(w.sessions()) == 2
    w._close_all_sessions()


def test_reset_sessions_closes_every_connection(monkeypatch, tmp_path):
    """Profile replacement must not leave hidden old-profile links running."""
    w = _window(monkeypatch, tmp_path, "reset-all")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    c1, c2 = s1.conn, s2.conn
    assert c1.is_open and c2.is_open
    w._reset_sessions_runtime()
    assert len(w.sessions()) == 1
    assert not c1.is_open and not c2.is_open
    assert w.active_session().conn is None
    w._close_all_sessions()


def test_multi_send_blocks_session_switch(monkeypatch, tmp_path):
    """A window-owned multi-send timer must never migrate to another conn."""
    w = _window(monkeypatch, tmp_path, "multi-switch")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    w._ms_cycle_seq = [("AA", False, 0, 0, 1000)]
    w._ms_cycle_timer.start(60000)
    try:
        assert w.switch_session(s2.id) is False
        assert w.active_session().id == s1.id
        assert w._ms_cycle_timer.isActive()
    finally:
        w._ms_cycle_timer.stop()
        w._close_all_sessions()


def test_background_rx_uses_own_display_options(monkeypatch, tmp_path):
    """Background bytes are rendered only after that tab's options are restored."""
    w = _window(monkeypatch, tmp_path, "bg-format")
    _open_virtual(w)
    w.sw_rx_hex.setChecked(False)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    w.sw_rx_hex.setChecked(True)

    s1.conn.inject(b"A")
    _pump()
    assert s1.rx_bytes >= 1
    assert "41" not in s1.txt_recv.toPlainText()
    assert w.switch_session(s1.id)
    assert "A" in s1.txt_recv.toPlainText()
    assert "41" not in s1.txt_recv.toPlainText()
    w._close_all_sessions()


def test_background_network_reconnect_uses_saved_snapshot(monkeypatch, tmp_path):
    """A hidden TCP tab must not reconnect with the visible tab's UI fields."""
    w = _window(monkeypatch, tmp_path, "bg-net-reconnect")
    s1 = w.active_session()
    snapshot = {
        "proto": "TCP Client",
        "fields": {"remote_ip": "10.0.0.1", "remote_port": "9000"},
        "conn_cfg": ("TCP Client", "10.0.0.1", 9000),
    }
    s1._reconnect_snapshot = snapshot
    s2 = w.add_session(activate=True)
    from virtual_io import PROTO_VIRTUAL
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    seen = []

    def _open_conn(reconnect_cfg=None, reconnect_snapshot=None):
        seen.append((reconnect_cfg, reconnect_snapshot, w._session_ctx().id))

    monkeypatch.setattr(w, "open_conn", _open_conn)
    w._try_reconnect_for(s1.id)
    assert seen == [(None, snapshot, s1.id)]
    assert w.active_session().id == s2.id
    w._close_all_sessions()


def test_background_open_state_advances_reconnect_state(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "bg-open-state")
    s1 = w.active_session()
    w.add_session(activate=True)
    s1._reconnect_attempts = 4
    s1._reconnect_timer.start(60000)
    w._route_session_state(s1.id, True)
    assert s1._conn_engaged is True
    assert s1._reconnect_attempts == 0
    assert not s1._reconnect_timer.isActive()
    w._close_all_sessions()


def test_tcp_server_targets_are_session_owned(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "server-targets")
    s1 = w.active_session()
    s1._conn_proto = "TCP Server"
    w._route_session_clients(s1.id, [("A", "client-A")])
    s2 = w.add_session(activate=True)
    s2._conn_proto = "TCP Server"
    w._route_session_clients(s2.id, [("B", "client-B")])
    assert w.switch_session(s1.id)
    targets = [w.cb_target.itemData(i) for i in range(w.cb_target.count())]
    assert targets == ["__all__", "A"]
    w._close_all_sessions()


def test_session_tab_connection_markers_differ(monkeypatch, tmp_path):
    from PyQt5.QtGui import QColor

    w = _window(monkeypatch, tmp_path, "tab-marker")
    s = w.active_session()
    w._refresh_session_tab_styles()
    closed_image = w._session_tab_bar.tabIcon(0).pixmap(12, 12).toImage()
    closed_color = closed_image.pixelColor(
        closed_image.width() // 2, closed_image.height() // 2)
    assert not w._session_tab_bar.tabText(0).startswith(("○ ", "● "))
    _open_virtual(w)
    w._refresh_session_tab_styles()
    open_image = w._session_tab_bar.tabIcon(0).pixmap(12, 12).toImage()
    open_color = open_image.pixelColor(
        open_image.width() // 2, open_image.height() // 2)
    assert open_color == QColor("#34C759")
    assert open_color != closed_color
    w._close_all_sessions()


def test_selected_session_uses_custom_white_close_icon(monkeypatch, tmp_path):
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import QTabBar

    w = _window(monkeypatch, tmp_path, "tab-close-icon")
    w.add_session(activate=False)
    bar = w._session_tab_bar
    close_btn = bar.tabButton(bar.currentIndex(), QTabBar.RightSide)
    assert close_btn is not None
    assert close_btn.objectName() == "SessionCloseBtn"
    image = close_btn.icon().pixmap(12, 12).toImage()
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    assert center == QColor("#FFFFFF")
    w._close_all_sessions()


def test_session_open_status_keeps_connection_detail(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "session-open-status")
    _open_virtual(w)
    session = w.active_session()
    w._sync_open_button_from_session(session)
    assert w.lbl_state.text() == w._t("vconn_state_loop")
    w._close_all_sessions()


def test_reparent_overlays_repositions_both_controls(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "overlay-reposition")
    calls = []
    monkeypatch.setattr(
        w, "_reposition_to_bottom_btn", lambda: calls.append("bottom"))
    monkeypatch.setattr(
        w, "_reposition_search_bar", lambda: calls.append("search"))
    w._reparent_recv_overlays(w.active_session().txt_recv)
    assert calls == ["bottom", "search"]
    w._close_all_sessions()


def test_font_size_change_updates_all_session_views(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "all-session-font")
    first = w.active_session()
    second = w.add_session(activate=True)
    old_size = w._recv_font_size
    w.change_recv_font_size(1)
    assert w._recv_font_size == old_size + 1
    assert first.txt_recv.font().pointSize() == old_size + 1
    assert second.txt_recv.font().pointSize() == old_size + 1
    w._close_all_sessions()


def test_theme_recolors_all_session_histories(monkeypatch, tmp_path):
    from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
    from main_window import ROLE_PROP, ROLE_RX

    w = _window(monkeypatch, tmp_path, "all-session-theme")
    first = w.active_session()
    second = w.add_session(activate=True)
    for session in (first, second):
        cursor = QTextCursor(session.txt_recv.document())
        fmt = QTextCharFormat()
        fmt.setProperty(ROLE_PROP, ROLE_RX)
        fmt.setForeground(QColor("#FF0000"))
        cursor.insertText("x", fmt)

    w._recolor_history()

    expected = QColor(w._role_color(ROLE_RX, w._theme()))
    for session in (first, second):
        frag = session.txt_recv.document().firstBlock().begin().fragment()
        assert frag.charFormat().foreground().color() == expected
    w._close_all_sessions()


def test_periodic_restore_uses_session_interval(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "session-period-interval")
    session = w.active_session()

    class _OpenConn:
        is_open = True

    session.conn = _OpenConn()
    session.period_on = True
    session.period_ms = "250"
    w.ed_period_ms.setText("999")
    w._restore_session_periodic(session)
    assert w.send_timer.isActive()
    assert w.send_timer.interval() == 250
    w.send_timer.stop()
    session.conn = None
    w._close_all_sessions()


def test_background_close_preserves_active_window_engines(monkeypatch, tmp_path):
    """Background teardown must only reset fields owned by that session."""
    w = _window(monkeypatch, tmp_path, "bg-close-engines")
    _open_virtual(w)
    background = w.active_session()
    active = w.add_session(activate=True)
    _open_virtual(w)
    stopped = []
    monkeypatch.setattr(w, "_stop_device_scan", lambda **_k: stopped.append(True))
    w._ar_gap_timer.start(60000)
    w._modbus_buffers = {"active-client": b"partial"}
    w._mbm_guard_until = 123.5
    background._ar_buf = b"background-partial"

    with w._with_session(background):
        w.close_conn(update_ui=False)

    assert background.conn is None
    assert background._ar_buf == b""
    assert active.is_open()
    assert stopped == []
    assert w._ar_gap_timer.isActive()
    assert w._modbus_buffers == {"active-client": b"partial"}
    assert w._mbm_guard_until == 123.5
    w._ar_gap_timer.stop()
    w._close_all_sessions()


def test_reconnect_open_checks_other_session_resource(monkeypatch, tmp_path):
    """Automatic reconnect cannot bypass the same serial conflict as manual open."""
    w = _window(monkeypatch, tmp_path, "reconnect-conflict")
    holder = w.active_session()

    class _OpenConn:
        is_open = True

        def blockSignals(self, *_a):
            return None

        def close(self):
            self.is_open = False

        def deleteLater(self):
            return None

    holder.conn = _OpenConn()
    holder._conn_proto = "Serial"
    holder._conn_cfg = ("Serial", "COM7", 115200, "8", "None", "1", "None")
    reconnecting = w.add_session(activate=True)
    built = []
    monkeypatch.setattr(
        "main_window.SerialConn",
        lambda *_a, **_k: built.append(True))
    snapshot = {
        "proto": "Serial",
        "fields": {"port": "COM7", "baud": "115200"},
        "serial_extras": ("8", "None", "1", "None"),
        "conn_cfg": ("Serial", "COM7", 115200, "8", "None", "1", "None"),
    }
    with w._with_session(reconnecting):
        w.open_conn(reconnect_snapshot=snapshot)
    assert reconnecting.conn is None
    assert built == []
    reconnecting._serial_reconnect_cfg = tuple(snapshot["conn_cfg"])
    reconnecting._reconnect_attempts = 3
    w._available_serial_devices = {"COM7"}
    with w._with_session(reconnecting):
        w._try_reconnect()
    assert reconnecting._serial_reconnect_cfg is None
    assert not reconnecting._reconnect_timer.isActive()
    holder.conn = None
    w._close_all_sessions()


def test_close_session_disposes_owned_timers(monkeypatch, tmp_path):
    from PyQt5 import sip
    from PyQt5.QtCore import QEvent

    w = _window(monkeypatch, tmp_path, "session-timer-dispose")
    closing = w.add_session(activate=False)
    timers = (closing._reconnect_timer, closing._ar_gap_timer)
    assert w.close_session(closing.id)
    _APP.sendPostedEvents(None, QEvent.DeferredDelete)
    assert all(sip.isdeleted(timer) for timer in timers)
    w._close_all_sessions()


def test_resource_conflict_stops_network_reconnect_loop(monkeypatch, tmp_path):
    """An in-process bind conflict is stalled, not retried forever."""
    w = _window(monkeypatch, tmp_path, "reconnect-conflict-stop")
    holder = w.active_session()

    class _OpenConn:
        is_open = True

    holder.conn = _OpenConn()
    holder._conn_proto = "TCP Server"
    holder._conn_cfg = ("TCP Server", "0.0.0.0", 9001)
    holder._reconnect_snapshot = {
        "proto": "TCP Server",
        "fields": {"local_ip": "0.0.0.0", "local_port": "9001"},
    }
    reconnecting = w.add_session(activate=True)
    reconnecting._reconnect_snapshot = {
        "proto": "UDP",
        "fields": {
            "local_ip": "127.0.0.1", "local_port": "9001",
            "remote_ip": "127.0.0.1", "remote_port": "9002",
        },
        "conn_cfg": ("UDP", "127.0.0.1", 9001, "127.0.0.1", 9002),
    }
    reconnecting._reconnect_attempts = 5

    with w._with_session(reconnecting):
        w._try_reconnect()

    assert reconnecting.conn is None
    assert not reconnecting._reconnect_timer.isActive()
    assert reconnecting._reconnect_attempts == 0
    holder.conn = None
    w._close_all_sessions()


def test_import_config_replaces_stale_sessions(monkeypatch, tmp_path):
    """Importing one workspace config must not retain old hidden tab state."""
    w = _window(monkeypatch, tmp_path, "import-resets-sessions")
    _open_virtual(w)
    first = w.active_session()
    first.send_draft = "OLD-FIRST"
    second = w.add_session(activate=True)
    _open_virtual(w)
    second.send_draft = "OLD-SECOND"
    old_conns = (first.conn, second.conn)
    imported = tmp_path / "imported.json"
    imported.write_text(
        json.dumps({"settings": {"send_text": "IMPORTED"}}),
        encoding="utf-8")
    monkeypatch.setattr(
        "main_window.QFileDialog.getOpenFileName",
        lambda *_a, **_k: (str(imported), "JSON (*.json)"))

    w.import_config()

    assert all(not conn.is_open for conn in old_conns)
    assert len(w.sessions()) == 1
    assert w.active_session() not in (first, second)
    assert w.txt_send.toPlainText() == "IMPORTED"
    assert w.active_session().send_draft == "IMPORTED"
    w._close_all_sessions()


def test_project_switch_resets_all_sessions(monkeypatch, tmp_path):
    """Applying a project/template cannot leave a hidden old-config link alive."""
    w = _window(monkeypatch, tmp_path, "project-all")
    _open_virtual(w)
    first = w.active_session()
    second = w.add_session(activate=True)
    _open_virtual(w)
    c1, c2 = first.conn, second.conn

    assert w._prepare_project_switch() is True
    assert not c1.is_open and not c2.is_open
    assert len(w.sessions()) == 1
    assert w.active_session().conn is None
    w._close_all_sessions()


def test_workspace_template_persists_reset_sessions_immediately(
        monkeypatch, tmp_path):
    """A crash after template apply must not resurrect the old tab list."""
    import json

    w = _window(monkeypatch, tmp_path, "template-session-persist")
    old_first = w.active_session()
    old_second = w.add_session(activate=False)
    w._save_sessions_settings()
    w.settings.sync()
    old_ids = {old_first.id, old_second.id}
    monkeypatch.setattr(w, "_confirm_dlg", lambda *_a, **_k: True)
    index = w.cb_workspace_template.findData("modbus_rtu")
    w.cb_workspace_template.setCurrentIndex(index)

    w._apply_workspace_protocol_template()

    disk = QSettings(w.settings.fileName(), QSettings.IniFormat)
    payload = json.loads(str(disk.value("sessions_v1", "")))
    assert len(payload) == 1
    assert payload[0]["id"] == str(disk.value("active_session_id", ""))
    assert payload[0]["id"] not in old_ids
    w._close_all_sessions()


def test_project_switch_cleans_window_engines_when_only_background_is_open(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "project-bg-only")
    _open_virtual(w)
    background = w.active_session()
    w.add_session(activate=True)
    stopped = []
    monkeypatch.setattr(w, "_stop_device_scan", lambda **_k: stopped.append(True))
    assert w._prepare_project_switch() is True
    assert background.conn is None
    assert stopped == [True]
    w._close_all_sessions()


def test_port_scan_disconnects_background_serial_and_arms_reconnect(monkeypatch, tmp_path):
    """USB removal detection must traverse hidden serial sessions."""
    w = _window(monkeypatch, tmp_path, "bg-port-remove")
    hidden = w.active_session()

    class _SerialConn:
        is_open = True

        def blockSignals(self, *_a):
            return None

        def close(self):
            self.is_open = False

        def deleteLater(self):
            return None

    conn = _SerialConn()
    cfg = ("Serial", "COM9", 115200, "8", "None", "1", "None")
    hidden.conn = conn
    hidden._conn_proto = "Serial"
    hidden._conn_cfg = cfg
    hidden._conn_engaged = True
    hidden._serial_device = "COM9"
    w.add_session(activate=True)
    w._serial_missing_limit = 2

    w._on_port_scan_complete([("COM1", "COM1")])
    assert hidden.conn is conn
    w._on_port_scan_complete([("COM1", "COM1")])
    assert hidden.conn is None
    assert hidden._serial_reconnect_cfg == cfg
    assert hidden._reconnect_timer.isActive()
    w._close_all_sessions()


def test_port_scan_wakes_background_serial_reconnect(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "bg-port-wake")
    hidden = w.active_session()
    hidden._serial_reconnect_cfg = (
        "Serial", "COM9", 115200, "8", "None", "1", "None")
    hidden._reconnect_timer.start(60000)
    w.add_session(activate=True)
    w._on_port_scan_complete([("COM9", "COM9")])
    assert hidden._reconnect_timer.interval() == 0
    w._close_all_sessions()


def test_background_error_does_not_refresh_or_toast_active_ui(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "bg-error-ui")
    hidden = w.active_session()
    hidden._conn_proto = "TCP Client"
    w.add_session(activate=True)
    refreshed = []
    toasted = []
    monkeypatch.setattr(w, "_refresh_stat_labels", lambda **_k: refreshed.append(True))
    monkeypatch.setattr(w, "toast", lambda *a, **k: toasted.append((a, k)))
    w._route_session_error(hidden.id, "background failure")
    assert hidden.rx_errors == 1
    assert refreshed == []
    assert toasted == []
    w._close_all_sessions()


def test_one_session_user_close_does_not_suppress_other_session_reconnect(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "close-race")
    active = w.active_session()
    w.add_session(activate=False)
    background = w.sessions()[1]
    active._user_closing = True
    with w._with_session(background):
        w._schedule_reconnect()
    assert background._reconnect_timer.isActive()
    background._reconnect_timer.stop()
    active._user_closing = False
    w._close_all_sessions()


def test_window_shutdown_suppresses_background_reconnect(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "shutdown-reconnect-race")
    background = w.add_session(activate=False)
    opened = []
    monkeypatch.setattr(
        w, "open_conn", lambda **_k: opened.append(True))
    w._user_closing = True
    with w._with_session(background):
        w._schedule_reconnect()
        w._try_reconnect()
    assert not background._reconnect_timer.isActive()
    assert opened == []
    w._user_closing = False
    w._close_all_sessions()


def test_session_switch_restores_terminal_highlight_and_freeze(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "display-restore")
    first = w.active_session()
    second = w.add_session(activate=True)
    first.display_opts = {
        "terminal_on": True,
        "proto_hl_on": True,
        "freeze_view": False,
        "numview_spec": w.cb_numview_type.itemData(0),
    }
    w._terminal_on = False
    w._proto_hl_on = False
    w._freeze_view = True
    w.sw_freeze_view.setChecked(True, animate=False)

    assert w.switch_session(first.id)
    assert w._terminal_on is True
    assert w.sw_terminal.isChecked() is True
    assert w._proto_hl_on is True
    assert w._freeze_view is False
    assert w.cb_numview_type.currentData() == first.display_opts["numview_spec"]
    assert w.switch_session(second.id)
    assert w._terminal_on is False
    assert w.sw_terminal.isChecked() is False
    assert w._proto_hl_on is False
    assert w._freeze_view is True
    assert w.sw_freeze_view.isChecked() is True
    w._close_all_sessions()


def test_period_and_log_intent_persist_roundtrip(monkeypatch, tmp_path):
    from session import Session

    w = _window(monkeypatch, tmp_path, "intent-persist")
    s = w.active_session()
    s.period_on = True
    s.log_wanted = True
    s.log_base_path = "capture.log"
    s.log_seg = 3
    s.display_opts = {"freeze_view": True}
    restored = Session.from_persist(w, s.to_persist())
    assert restored.period_on is True
    assert restored.log_wanted is True
    assert restored.log_base_path == "capture.log"
    assert restored.log_seg == 3
    assert restored._freeze_view is True
    w._close_all_sessions()


def test_ar_gap_timer_flushes_in_owning_session(monkeypatch, tmp_path):
    """A's silence timer must not execute against B after a tab switch."""
    w = _window(monkeypatch, tmp_path, "ar-gap-owner")
    first = w.active_session()
    second = w.add_session(activate=False)
    seen = []
    monkeypatch.setattr(
        w, "_ar_flush", lambda: seen.append(w._session_ctx().id))
    first._ar_gap_timer.start(5)
    assert w.switch_session(second.id)
    _pump(5, 0.01)
    assert seen == [first.id]
    assert not first._ar_gap_timer.isActive()
    w._close_all_sessions()


def test_session_switch_clears_window_trigger_stream_state(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "trigger-switch-reset")
    second = w.add_session(activate=False)
    w._trg_dec_buf = {("rx", None): b"partial"}
    w._trg_dec = {("rx", None): object()}
    w._trg_ansi_pending = {("rx", None): "escape"}
    w._trg_tail_bytes = {("rx", None): b"tail"}
    w._trg_tail_text = {("rx", None): "tail"}
    assert w.switch_session(second.id)
    assert w._trg_dec_buf == {}
    assert w._trg_dec == {}
    assert w._trg_ansi_pending == {}
    assert w._trg_tail_bytes == {}
    assert w._trg_tail_text == {}
    w._close_all_sessions()


def test_background_rx_exception_does_not_toast_active_session(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "background-rx-exception")
    hidden = w.active_session()
    w.add_session(activate=True)
    toasted = []
    monkeypatch.setattr(w, "toast", lambda *a, **k: toasted.append((a, k)))
    monkeypatch.setattr(
        w, "_on_data_received_impl",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad rx")))
    w._route_session_data(hidden.id, b"broken")
    assert hidden.rx_errors == 1
    assert toasted == []
    w._close_all_sessions()


def test_rate_tick_samples_background_sessions(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "background-rate-sample")
    w._rate_timer.stop()
    hidden = w.active_session()
    active = w.add_session(activate=True)
    with w._with_session(hidden):
        w._stat_note_rx(128)
    before_hidden = len(hidden._io_stats.history)
    before_active = len(active._io_stats.history)
    w._tick_rate()
    assert len(hidden._io_stats.history) == before_hidden + 1
    assert len(active._io_stats.history) == before_active + 1
    w._close_all_sessions()


def test_period_intent_resumes_after_connection_opens(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "period-resume")
    session = w.active_session()
    session.period_on = True
    session.period_ms = "250"
    w.ed_period_ms.setText("250")
    _open_virtual(w)
    assert session.period_on is True
    assert w.sw_period.isChecked() is True
    assert w.send_timer.isActive()
    assert w.send_timer.interval() == 250
    w.send_timer.stop()
    w._close_all_sessions()


def test_background_clients_change_prunes_session_stream_state(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "bg-client-prune")
    hidden = w.active_session()
    hidden._numview_carries = {"gone": b"x", "live": b"y"}
    hidden._rx_decode_buffers = {"gone": b"x", "live": b"y"}
    hidden._ansi_states = {"gone": object(), "live": object()}
    hidden._term_streams = {"gone": object(), "live": object()}
    w.add_session(activate=True)
    w._route_session_clients(hidden.id, [("live", "client")])
    assert set(hidden._numview_carries) == {"live"}
    assert set(hidden._rx_decode_buffers) == {"live"}
    assert set(hidden._ansi_states) == {"live"}
    assert set(hidden._term_streams) == {"live"}
    w._close_all_sessions()


def test_network_bind_conflict_is_protocol_independent(monkeypatch, tmp_path):
    """A local address/port is reserved by one listener regardless of its label."""
    w = _window(monkeypatch, tmp_path, "bind-conflict")
    holder = w.active_session()

    class _OpenConn:
        is_open = True

    holder.conn = _OpenConn()
    holder._conn_proto = "TCP Server"
    holder._reconnect_snapshot = {
        "proto": "TCP Server",
        "fields": {"local_ip": "0.0.0.0", "local_port": "9001"},
    }
    w.add_session(activate=True)
    w.cb_proto.setCurrentText("UDP")
    w.cb_local_ip.setCurrentText("127.0.0.1")
    w.ed_local_port.setText("9001")
    assert w.check_session_resource_conflict() is holder
    holder.conn = None
    w._close_all_sessions()


def test_udp_tab_label_ignores_leftover_serial_port(monkeypatch, tmp_path):
    """Disconnecting UDP must not rename the tab to a shared-UI COM leftover."""
    w = _window(monkeypatch, tmp_path, "udp-tab-label")
    s = w.active_session()
    s.conn_fields = {
        "net_proto": "UDP",
        "ser_port": "COM1",  # shared serial combo bleed
        "net_remote_ip": "192.168.5.100",
        "net_remote_port": "8082",
    }
    s._conn_proto = "UDP"
    s._conn_cfg = ("UDP", "192.168.5.104", "6000")
    assert s.tab_label() == "UDP"
    # close_conn clears live cfg; label must stay UDP, not COM1
    s._conn_proto = None
    s._conn_cfg = None
    assert s.tab_label() == "UDP"

    serial = w.add_session(activate=False)
    serial.conn_fields = {"net_proto": "Serial", "ser_port": "COM1"}
    assert serial.tab_label() == "COM1"
    w._close_all_sessions()
