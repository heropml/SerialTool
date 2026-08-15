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
from PyQt5.QtCore import QCoreApplication, QEvent, QSettings

_APP = QApplication.instance() or QApplication([])
_TEST_WINDOWS = []


@pytest.fixture(autouse=True)
def _dispose_test_windows():
    """Fully shut down each native window before deferred deletion."""
    yield
    for window in reversed(_TEST_WINDOWS):
        window._shutdown()
        _APP.processEvents()
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
    _TEST_WINDOWS.append(w)
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


def test_close_session_asks_confirm_even_when_closed(monkeypatch, tmp_path):
    """Tab X always confirms, including for disconnected sessions."""
    w = _window(monkeypatch, tmp_path, "close-confirm-idle")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    assert not s2.is_open()
    asks = []

    def _confirm(title, body, **kwargs):
        asks.append((title, body, kwargs.get("danger")))
        return False

    monkeypatch.setattr(w, "_confirm_dlg", _confirm)
    assert w.close_session(s2.id) is False
    assert len(w.sessions()) == 2
    assert asks and asks[0][2] is True
    assert s2.tab_label() in asks[0][1]

    monkeypatch.setattr(w, "_confirm_dlg", lambda *a, **k: True)
    assert w.close_session(s2.id) is True
    assert len(w.sessions()) == 1
    assert w.active_session() is s1
    w._close_all_sessions()


def test_close_session_confirm_open_mentions_disconnect(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "close-confirm-open")
    _open_virtual(w)
    w.add_session(activate=True)
    _open_virtual(w)
    s2 = w.active_session()
    bodies = []
    expected = w._t("session_close_confirm_open", name=s2.tab_label())

    def _confirm(title, body, **kwargs):
        bodies.append(body)
        return True

    monkeypatch.setattr(w, "_confirm_dlg", _confirm)
    assert w.close_session(s2.id) is True
    assert bodies == [expected]
    w._close_all_sessions()


def test_close_session_confirm_connecting_mentions_disconnect(monkeypatch, tmp_path):
    """A TCP Client connect attempt is still cancelled by closing the tab."""
    w = _window(monkeypatch, tmp_path, "close-confirm-connecting")
    s2 = w.add_session(activate=True)

    class _ConnectingConn:
        is_open = False

    s2.conn = _ConnectingConn()
    bodies = []
    expected = w._t("session_close_confirm_open", name=s2.tab_label())

    def _cancel(_title, body, **_kwargs):
        bodies.append(body)
        return False

    monkeypatch.setattr(w, "_confirm_dlg", _cancel)
    assert w.close_session(s2.id) is False
    assert bodies == [expected]
    assert s2 in w.sessions()
    assert s2.conn is not None
    s2.conn = None
    w._close_all_sessions()


def test_close_session_confirm_pauses_and_cancel_restores_timers(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "close-confirm-pause-timers")
    _open_virtual(w)
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    s2.period_on = True
    s2._period_timer.start(60000)
    s2._reconnect_timer.start(60000)

    def _cancel(*_args, **_kwargs):
        assert s2._user_closing is True
        assert not s2._reconnect_timer.isActive()
        assert not s2._period_timer.isActive()
        return False

    monkeypatch.setattr(w, "_confirm_dlg", _cancel)
    assert w.close_session(s2.id) is False
    assert s2._user_closing is False
    assert s2._reconnect_timer.isActive()
    assert s2._period_timer.isActive()
    assert s2.period_on is True
    assert s2.is_open()
    w._close_all_sessions()


def test_close_session_cancel_clamps_elapsed_reconnect_timer(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "close-confirm-reconnect-clamp")
    s2 = w.add_session(activate=True)

    class _ElapsedTimer:
        def __init__(self):
            self.starts = []

        def isActive(self):
            return True

        def remainingTime(self):
            return 0

        def stop(self):
            return None

        def start(self, delay):
            self.starts.append(delay)

    real_timer = s2._reconnect_timer
    fake_timer = _ElapsedTimer()
    s2._reconnect_timer = fake_timer
    monkeypatch.setattr(w, "_confirm_dlg", lambda *_a, **_k: False)
    try:
        assert w.close_session(s2.id) is False
        assert fake_timer.starts == [500]
    finally:
        s2._reconnect_timer = real_timer
    w._close_all_sessions()


def test_close_session_cancel_reschedules_drop_during_confirm(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "close-confirm-drop")
    s2 = w.add_session(activate=True)

    class _OpenConn:
        is_open = True

    s2.conn = _OpenConn()
    scheduled = []

    def _cancel(*_args, **_kwargs):
        assert s2._user_closing is True
        s2.conn = None
        return False

    monkeypatch.setattr(w, "_confirm_dlg", _cancel)
    monkeypatch.setattr(
        w, "_schedule_reconnect",
        lambda: scheduled.append(w._session_ctx().id))
    assert w.close_session(s2.id) is False
    assert s2._user_closing is False
    assert scheduled == [s2.id]
    assert s2 in w.sessions()
    w._close_all_sessions()


def test_close_middle_active_session_rebinds_receive_ui(monkeypatch, tmp_path):
    """Closing B from [A,B,C] selects C and clears deleted-view fallback."""
    from PyQt5 import sip
    from PyQt5.QtCore import QEvent

    w = _window(monkeypatch, tmp_path, "close-middle-active")
    w.active_session()
    middle = w.add_session(activate=True)
    right = w.add_session(activate=False)
    overlays = (w._search_bar, w.btn_to_bottom)
    assert all(widget.parentWidget() is middle.txt_recv for widget in overlays)
    w._txt_recv_fallback = middle.txt_recv

    assert w.close_session(middle.id)
    _APP.sendPostedEvents(None, QEvent.DeferredDelete)

    assert w.active_session() is right
    assert w.recv_stack.currentWidget() is right.txt_recv
    assert w._txt_recv_fallback is right.txt_recv
    assert all(not sip.isdeleted(widget) for widget in overlays)
    assert all(widget.parentWidget() is right.txt_recv for widget in overlays)
    w._open_search()
    w._close_all_sessions()


def test_receive_scroll_has_one_session_route(monkeypatch, tmp_path):
    """Only the active tab's receive scrollbar drives the shared UI.

    Qt owns QTextEdit's vertical scrollbar, so QObject.receivers() is a
    protected API for that object on some PyQt/macOS builds.  Exercise the
    public signal path instead of introspecting Qt's private connection list.
    """
    w = _window(monkeypatch, tmp_path, "single-scroll-route")
    first = w.active_session()
    second = w.add_session(activate=False)
    first_sb = first.txt_recv.verticalScrollBar()
    second_sb = second.txt_recv.verticalScrollBar()
    calls = []
    monkeypatch.setattr(w, "_on_recv_scroll", lambda value: calls.append(value))

    first_sb.setRange(0, 100)
    second_sb.setRange(0, 100)
    calls.clear()
    first_sb.setValue(10)
    second_sb.setValue(20)
    assert calls == [10]

    assert w.switch_session(second.id)
    calls.clear()
    first_sb.setValue(30)
    second_sb.setValue(40)
    assert calls == [40]
    w._close_all_sessions()


def test_busy_soft_leave_allows_tab_switch(monkeypatch, tmp_path):
    """Pinned exclusive engines no longer hard-block tab switch."""
    w = _window(monkeypatch, tmp_path, "busy")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    w._replay_on = True
    w._io_bind_owner("replay", s1)
    assert w.switch_session(s2.id) is True
    assert w.active_session().id == s2.id
    assert w.close_session(s1.id, confirm=False) is False
    s1._replay_on = False
    w._io_clear_owner("replay")
    w._close_all_sessions()



def test_busy_toast_names_occupying_tasks(monkeypatch, tmp_path):
    """Exclusive-busy and session-busy toasts list concrete task names."""
    w = _window(monkeypatch, tmp_path, "busy-named")
    toasts = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: toasts.append((msg, error)))
    w._replay_on = True
    w.toast_io_exclusive_busy()
    assert toasts and toasts[-1][1] is True
    assert w._t("io_task_replay") in toasts[-1][0]
    toasts.clear()
    w.toast_session_busy()
    assert toasts and w._t("io_task_replay") in toasts[-1][0]
    # exclude hides the named task from the message
    toasts.clear()
    w.toast_io_exclusive_busy(exclude=("replay",))
    assert toasts and w._t("io_task_unknown") in toasts[-1][0]
    w._replay_on = False
    w._close_all_sessions()


def test_session_tab_reconnect_marker_and_tooltip(monkeypatch, tmp_path):
    """Yellow reconnect dot + tooltip covers conn / period / log state."""
    from PyQt5.QtGui import QColor
    import main_window as main_window_module

    w = _window(monkeypatch, tmp_path, "tab-reconnect-tip")
    s = w.active_session()
    s.period_on = True
    s.log_wanted = True
    monkeypatch.setattr(
        main_window_module._reconnect_policy,
        "plan_schedule",
        lambda **_kwargs: {
            "action": "schedule", "delay_ms": 60000,
            "bump_attempts": False,
        },
    )
    with w._with_session(s):
        w._schedule_reconnect()
    assert s._reconnect_timer.isActive()
    bar = w._session_tab_bar
    image = bar.tabIcon(0).pixmap(12, 12).toImage()
    color = image.pixelColor(image.width() // 2, image.height() // 2)
    assert color == QColor("#FF9F0A")
    tip = bar.tabToolTip(0)
    assert w._t("session_tip_reconnecting") in tip
    assert w._t("session_tip_period_on") in tip
    assert w._t("session_tip_log_wanted") in tip
    with w._with_session(s):
        w._cancel_reconnect()
    assert not s._reconnect_timer.isActive()
    assert w._t("session_tip_closed") in bar.tabToolTip(0)
    w._close_all_sessions()


def test_session_tab_style_tolerates_missing_reconnect_timer(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "tab-no-reconnect-timer")
    session = w.active_session()
    timer = session._reconnect_timer
    session._reconnect_timer = None
    try:
        w._refresh_session_tab_styles()
        assert w._t("session_tip_closed") in w._session_tab_bar.tabToolTip(0)
    finally:
        session._reconnect_timer = timer
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


def test_background_rx_feeds_pinned_script_engine(monkeypatch, tmp_path):
    """Background RX feeds script only when pinned to that session."""
    w = _window(monkeypatch, tmp_path, "bg-rx")
    _open_virtual(w)
    s1 = w.active_session()
    w.add_session(activate=True)
    _open_virtual(w)
    fed = {"script": 0}

    class _Worker:
        def feed(self, data):
            fed["script"] += 1

    s1._script_worker = _Worker()
    w._io_bind_owner("script", s1)
    monkeypatch.setattr(w, "_script_running", lambda: True)
    monkeypatch.setattr(w, "_seq_running", lambda: False)

    s1.conn.inject(b"YES-SCRIPT")
    _pump()
    assert fed["script"] == 1
    assert s1.rx_bytes >= 10

    fed["script"] = 0
    w._io_clear_owner("script")
    s1._script_worker = None
    s1.conn.inject(b"NO-SCRIPT")
    _pump()
    assert fed["script"] == 0
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


def test_restore_rewrites_id_all_session_timers_still_route(
        monkeypatch, tmp_path):
    """Every per-session timer must resolve ``Session.id`` when it fires."""
    w = _window(monkeypatch, tmp_path, "restore-id-all-timers")
    session = w.active_session()
    old_id = session.id
    session.id = "restored-all"
    w._active_session_id = session.id
    hits = []

    for method_name, tag in (
            ("_ar_flush_for", "ar"),
            ("_pulse_reset_release_for", "reset"),
            ("_period_send_for", "period"),
            ("_ms_cycle_step_for", "multi"),
            ("_seq_on_timeout_for", "sequence")):
        monkeypatch.setattr(
            w, method_name,
            lambda sid, _tag=tag: hits.append((_tag, sid)))

    for timer in (
            session._ar_gap_timer, session._reset_timer,
            session._period_timer, session._ms_cycle_timer,
            session._seq_timer):
        timer.start(1)
    _pump(20, 0.01)

    expected = {
        ("ar", session.id), ("reset", session.id),
        ("period", session.id), ("multi", session.id),
        ("sequence", session.id),
    }
    # The period timer is intentionally repeating, so it may fire more than
    # once while events are pumped; routing identity is the invariant here.
    assert set(hits) == expected
    assert all(sid != old_id for _tag, sid in hits)
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


def test_restore_sessions_rebinds_persisted_modbus_owner(monkeypatch, tmp_path):
    """Restoring tab IDs must not leave enabled Modbus pinned to a dead tab."""
    w = _window(monkeypatch, tmp_path, "restore-mbm-owner")
    payload = w.active_session().to_persist()
    payload["id"] = "restored-mbm-owner"
    w.settings.setValue("sessions_v1", json.dumps([payload]))
    w._mbm_on = True
    w._io_bind_owner("modbus")
    old_owner_id = w._io_owner_sid["modbus"]

    w._restore_sessions_settings()

    assert old_owner_id != w.active_session().id
    assert w._io_owner_session("modbus") is w.active_session()
    w._mbm_on = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_owner_reconcile_clears_all_stale_nonpersistent_pins(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "restore-stale-owners")
    stale_id = "deleted-session"
    for key in w._io_owner_sid:
        w._io_owner_sid[key] = stale_id

    w._io_reconcile_session_owners()

    assert all(owner is None for owner in w._io_owner_sid.values())
    w._close_all_sessions()


def test_auto_reply_sequence_counter_is_session_owned(monkeypatch, tmp_path):
    """Concurrent auto-reply sessions must not consume each other's {seq}."""
    w = _window(monkeypatch, tmp_path, "autoreply-seq-owner")
    s1 = w.active_session()
    w._ar_seq = 7
    s2 = w.add_session(activate=True)

    assert w._ar_seq == 0
    w._ar_seq = 21
    with w._with_session(s1):
        assert w._ar_seq == 7
        w._ar_seq = 8
    assert w.active_session() is s2
    assert w._ar_seq == 21
    assert s1._ar_seq == 8
    w._close_all_sessions()


def test_auto_reply_cooldown_is_session_owned(monkeypatch, tmp_path):
    """A hit on one link must not rate-limit the same shared rule on another."""
    w = _window(monkeypatch, tmp_path, "autoreply-cooldown-owner")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    rule = {
        "on": True,
        "match": "AA",
        "match_hex": True,
        "mode": 1,
        "reply": "06",
        "reply_hex": True,
        "cooldown": 60_000,
    }
    w._ar_rules = [rule]
    w._ar_on = True
    s1._ar_enabled = True
    s2._ar_enabled = True
    w._ar_modbus = {"on": False}
    w._ar_frame = {"on": False}
    w._ar_gap = 0
    monkeypatch.setattr(w, "_is_open", lambda: True)
    scheduled = []
    monkeypatch.setattr(
        w, "_ar_schedule_send",
        lambda *_a, **_k: scheduled.append(w._session_ctx().id))

    with w._with_session(s1):
        w._auto_reply(b"\xAA")
    with w._with_session(s2):
        w._auto_reply(b"\xAA")
    with w._with_session(s1):
        w._auto_reply(b"\xAA")

    assert scheduled == [s1.id, s2.id]
    assert rule["_hits"] == 3
    assert set(rule["_last_by_session"]) == {s1.id, s2.id}
    assert w.close_session(s1.id, confirm=False)
    assert s1.id not in rule["_last_by_session"]
    w._close_all_sessions()


def test_restore_first_session_uses_complete_persisted_state(monkeypatch, tmp_path):
    """The reused first tab must restore the same fields as later tabs."""
    w = _window(monkeypatch, tmp_path, "restore-first-complete")
    first = w.active_session().to_persist()
    first.update({
        "id": "persisted-first",
        "title": "stale-default-label",
        "title_index": 7,
        "send_count": 259,
        "send_target": "client-a",
    })
    w.settings.setValue("sessions_v1", json.dumps([first]))

    w._restore_sessions_settings()

    restored = w.active_session()
    assert restored.id == "persisted-first"
    assert restored.title_index == 7
    assert restored.tab_label() == "%s-7" % w._t("session_default")
    assert restored._send_count == 3
    assert restored.send_target == "client-a"
    assert restored.txt_recv.property("session_id") == restored.id
    w._close_all_sessions()


def test_restore_repairs_duplicate_ids_and_malformed_fields(monkeypatch, tmp_path):
    """One damaged entry must not break startup or session-id routing."""
    w = _window(monkeypatch, tmp_path, "restore-repair")
    base = w.active_session().to_persist()
    first = dict(base, id="duplicate", title_index="bad",
                 conn_fields={"net_proto": ["bad"], "net_use_remote": "false"},
                 send_draft=["bad"], period_on="false", log_wanted="false",
                 log_base_path=["bad"], display_opts={"line_nl": "bad"})
    second = dict(base, id="duplicate", title="Second", title_index=None)
    w.settings.setValue(
        "sessions_v1", json.dumps([first, "bad-entry", second]))

    w._restore_sessions_settings()

    sessions = w.sessions()
    assert len(sessions) == 2
    assert len({s.id for s in sessions}) == 2
    assert sessions[0].conn_fields == {"net_use_remote": False}
    assert sessions[0].send_draft == ""
    assert sessions[0].log_base_path == ""
    assert sessions[0].period_on is False
    assert sessions[0].log_wanted is False
    assert w.cb_line_nl.currentIndex() == 0
    assert w.close_session(sessions[0].id) is True
    assert len(w.sessions()) == 1
    w._close_all_sessions()


def test_default_title_index_continues_after_restore_per_window(
        monkeypatch, tmp_path):
    w1 = _window(monkeypatch, tmp_path, "title-restore-window-1")
    base = w1.active_session().to_persist()
    payload = [dict(base, id="s%d" % n, title_index=i)
               for n, i in enumerate((1, 2, 2), 1)]
    w1.settings.setValue("sessions_v1", json.dumps(payload))
    w1._restore_sessions_settings()
    assert [s.title_index for s in w1.sessions()] == [1, 2, 3]
    added1 = w1.add_session(activate=False)
    assert added1.title_index == 4

    w2 = _window(monkeypatch, tmp_path, "title-restore-window-2")
    added2 = w2.add_session(activate=False)
    assert added2.title_index == 2
    w1._close_all_sessions()
    w2._close_all_sessions()


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


def test_multi_send_cycle_keeps_running_after_session_switch(
        monkeypatch, tmp_path):
    """Per-session multi-send cycle survives tab switch (like period TX)."""
    w = _window(monkeypatch, tmp_path, "multi-switch")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    toasts = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: toasts.append((msg, error)))
    s1._ms_cycle_seq = [("AA", False, 0, 0, 1000)]
    s1._ms_cycle_timer.start(60000)
    try:
        assert w.switch_session(s2.id) is True
        assert w.active_session().id == s2.id
        assert s1._ms_cycle_timer.isActive()
        assert not any(w._t("io_task_multi") in (t[0] or "") for t in toasts)
        assert not w._session_ms_cycle_active()  # active tab has no cycle
    finally:
        s1._ms_cycle_timer.stop()
        w._close_all_sessions()


def test_hard_busy_soft_leave_keeps_multi_send(monkeypatch, tmp_path):
    """Hard engines pin to owner: soft leave OK; multi-send keeps running."""
    w = _window(monkeypatch, tmp_path, "multi-hard-busy")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    s1._ms_cycle_seq = [("AA", False, 0, 0, 1000)]
    s1._ms_cycle_timer.start(60000)
    w._replay_on = True
    w._io_bind_owner("replay", s1)
    try:
        assert w.switch_session(s2.id) is True
        assert w.active_session().id == s2.id
        assert s1._ms_cycle_timer.isActive()
        assert w.close_session(s1.id, confirm=False) is False
    finally:
        s1._replay_on = False
        w._io_clear_owner("replay")
        s1._ms_cycle_timer.stop()
        w._close_all_sessions()


def test_concurrent_multi_send_cycle_keeps_running_in_background(
        monkeypatch, tmp_path):
    """Two sessions can cycle concurrently; leaving a tab must not stop others."""
    w = _window(monkeypatch, tmp_path, "dual-ms-cycle")
    _open_virtual(w)
    s1 = w.active_session()
    s1._ms_cycle_seq = [("A", False, 0, 0, 40)]
    s1._ms_cycle_idx = 0
    s1._ms_cycle_timer.start(40)
    # Drive via public step so TX actually happens.
    w._ms_cycle_step_for(s1.id)
    assert s1._ms_cycle_timer.isActive()

    s2 = w.add_session(activate=True)
    _open_virtual(w)
    s2._ms_cycle_seq = [("B", False, 0, 0, 40)]
    s2._ms_cycle_idx = 0
    w._ms_cycle_step_for(s2.id)

    before_s1_tx = s1.tx_bytes
    before_s2_tx = s2.tx_bytes
    _pump(25, 0.02)
    assert s1.tx_bytes > before_s1_tx
    assert s2.tx_bytes > before_s2_tx
    assert s1._ms_cycle_timer.isActive()
    w._close_all_sessions()
    assert not s1._ms_cycle_timer.isActive()
    assert not s2._ms_cycle_timer.isActive()


def test_ms_groups_changed_refreshes_background_cycle_seq(monkeypatch, tmp_path):
    """Editing shared multi-send groups refreshes every running cycle, not only active."""
    w = _window(monkeypatch, tmp_path, "ms-groups-refresh")
    _open_virtual(w)
    s1 = w.active_session()
    w._ms_groups = [{
        "name": "G",
        "items": [
            {"name": "old", "data": "OLD", "checked": True,
             "hex": False, "nl": 0, "cs": 0, "delay": 1000},
            {"name": "new", "data": "NEW", "checked": True,
             "hex": False, "nl": 0, "cs": 0, "delay": 500},
        ],
    }]
    w._ms_group_idx = 0
    s1._ms_cycle_seq = [("OLD", False, 0, 0, 1000)]
    s1._ms_cycle_timer.start(60000)

    s2 = w.add_session(activate=True)
    # Background s1 still cycling; edit unchecks OLD (active is s2).
    w._ms_groups[0]["items"][0]["checked"] = False
    w._ms_groups_changed()

    assert s1._ms_cycle_timer.isActive()
    assert s1._ms_cycle_seq == [("NEW", False, 0, 0, 500)]
    w._close_all_sessions()


def test_ms_groups_changed_stops_background_when_seq_empty(monkeypatch, tmp_path):
    """Empty rebuilt cycle seq stops every running session, including background."""
    w = _window(monkeypatch, tmp_path, "ms-groups-empty")
    _open_virtual(w)
    s1 = w.active_session()
    w._ms_groups = [{
        "name": "G",
        "items": [
            {"name": "a", "data": "AA", "checked": True,
             "hex": False, "nl": 0, "cs": 0, "delay": 1000},
        ],
    }]
    w._ms_group_idx = 0
    s1._ms_cycle_seq = [("AA", False, 0, 0, 1000)]
    s1._ms_cycle_timer.start(60000)
    w.add_session(activate=True)

    w._ms_groups[0]["items"][0]["checked"] = False
    w._ms_groups_changed()

    assert not s1._ms_cycle_timer.isActive()
    assert s1._ms_cycle_seq == []
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


def test_background_engine_feed_keeps_owner_display_context(
        monkeypatch, tmp_path):
    """Immediate engine replies must not inherit the visible tab's options."""
    w = _window(monkeypatch, tmp_path, "bg-engine-format")
    owner = w.active_session()
    w.add_session(activate=True)
    w.cb_encoding.setCurrentText("UTF-8")
    w.sw_rx_hex.setChecked(True)
    owner.display_opts = {"encoding": "gbk", "rx_hex": False}
    outer = {"sentinel": True}
    w._display_context = outer
    seen = []
    monkeypatch.setattr(
        w, "_on_data_received_impl", lambda _data, source=None: None)
    monkeypatch.setattr(
        w, "_feed_session_engines",
        lambda _data, reply_target=None, **_k: seen.append(
            dict(w._display_context)))

    with w._with_session(owner):
        w._on_background_session_data(b"reply")

    assert seen and seen[0]["encoding"] == "gbk"
    assert seen[0]["rx_hex"] is False
    assert w._display_context is outer
    w._display_context = None
    w._close_all_sessions()


def test_background_engines_do_not_mix_window_structured_recording(
        monkeypatch, tmp_path):
    """Structured rows have no session ID, so only the visible tab may add them."""
    import device_resources

    w = _window(monkeypatch, tmp_path, "bg-structured-owner")
    background = w.active_session()
    active = w.add_session(activate=True)
    added = []
    w._structured_recorder.start(clear=False)
    monkeypatch.setattr(w, "_structured_add", lambda rows: added.extend(rows))
    monkeypatch.setattr(
        device_resources, "decode_modbus_samples",
        lambda *_a, **_k: [{
            "timestamp": 1.0, "source": "modbus", "tag": "value",
            "value": 1, "unit": "", "raw": "00 01",
        }])
    info = {"func": 3, "unit": 1, "addr": 0}
    result = {"regs": [1]}

    with w._with_session(background):
        w._structured_feed_modbus(info, result)
    assert added == []

    with w._with_session(active):
        w._structured_feed_modbus(info, result)
    assert len(added) == 1
    w._structured_recorder.stop()
    w._close_all_sessions()


def test_background_rx_missing_options_never_fall_back_to_active_view(
        monkeypatch, tmp_path):
    """Old/incomplete snapshots use stable defaults, not the visible tab UI."""
    w = _window(monkeypatch, tmp_path, "bg-format-defaults")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    _open_virtual(w)

    s1.display_opts = {}
    w.sw_hexdump.setChecked(True)
    s1.conn.inject(b"AB")
    _pump()
    assert "AB" in s1.txt_recv.toPlainText()
    assert "00000000" not in s1.txt_recv.toPlainText()

    s1.txt_recv.clear()
    w.sw_hexdump.setChecked(False)
    s1.display_opts = {"hexdump_on": True, "hexdump_width": "8"}
    s1.conn.inject(b"CD")
    _pump()
    assert "00000000" in s1.txt_recv.toPlainText()
    assert w.active_session() is s2
    w._close_all_sessions()


def test_background_decoder_init_does_not_reset_window_triggers(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "bg-codec-trigger-isolation")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    other_key = (s2.id, "rx", None)
    w._trg_dec_buf[other_key] = b"keep"
    s1.display_opts = {"encoding": "utf-8"}
    s1._inc_decoder = None

    s1.conn.inject("中".encode("utf-8"))
    _pump()

    assert "中" in s1.txt_recv.toPlainText()
    assert w._trg_dec_buf.get(other_key) == b"keep"
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


def test_background_open_state_restarts_its_modbus_master(monkeypatch, tmp_path):
    """A background Modbus-owner reconnect must resume its own poll schedule."""
    w = _window(monkeypatch, tmp_path, "bg-open-modbus")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    w._mbm_on = True
    s1._mbm_enabled = True
    w._io_bind_owner("modbus", s1)
    restarted = []
    monkeypatch.setattr(
        w, "_mbm_restart", lambda: restarted.append(w._session_ctx().id))

    w._route_session_state(s1.id, True)

    assert restarted == [s1.id]
    assert w.active_session() is s2
    w._mbm_on = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_drive_tx_replay_only_suppresses_its_owner_modbus_slave(monkeypatch, tmp_path):
    """Replay in tab A must not block Modbus-slave replies from tab B."""
    w = _window(monkeypatch, tmp_path, "replay-modbus-owner")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    sent = []
    old_ar_on, old_drive = w._ar_on, s1._replay_drive_tx
    try:
        w._ar_on = True
        s1._ar_enabled = True
        s2._ar_enabled = True
        s1._replay_on = True
        s1._replay_drive_tx = True
        w._io_bind_owner("replay", s1)
        monkeypatch.setattr(w, "_is_open", lambda: True)
        monkeypatch.setattr(
            w, "_send_text",
            lambda payload, **kwargs: sent.append((payload, kwargs)) or True)

        w._modbus_send(b"\x01")
        assert [payload for payload, _kwargs in sent] == ["01"]

        with w._with_session(s1):
            w._modbus_send(b"\x02")
        assert [payload for payload, _kwargs in sent] == ["01"]
        assert w.active_session() is s2
    finally:
        w._ar_on = old_ar_on
        s1._replay_on = False
        s1._replay_drive_tx = old_drive
        s1._ar_enabled = False
        s2._ar_enabled = False
        w._io_clear_owner("replay")
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
    assert not w._session_tab_bar.tabText(0).startswith(("\u25cb ", "\u25cf "))
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
    w._ar_state = "active-state"
    w._mbm_guard_until = 123.5
    background._ar_buf = b"background-partial"
    background._modbus_buffers = {"background-client": b"partial"}
    background._ar_state = "background-state"
    background._ar_sm_pending = object()
    background._ar_sm_queue.append(b"queued")

    with w._with_session(background):
        w.close_conn(update_ui=False)

    assert background.conn is None
    assert background._ar_buf == b""
    assert background._modbus_buffers == {}
    assert background._ar_state == w._ar_sm.get("init", "")
    assert background._ar_sm_pending is None
    assert list(background._ar_sm_queue) == []
    assert active.is_open()
    assert stopped == []
    assert w._ar_gap_timer.isActive()
    assert w._modbus_buffers == {"active-client": b"partial"}
    assert w._ar_state == "active-state"
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
    timers = (closing._reconnect_timer, closing._ar_gap_timer,
              closing._period_timer, closing._reset_timer)
    assert w.close_session(closing.id)
    _APP.sendPostedEvents(None, QEvent.DeferredDelete)
    assert all(sip.isdeleted(timer) for timer in timers)
    w._close_all_sessions()


def test_max_lines_applies_to_existing_and_new_sessions(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "max-lines-all-sessions")
    first = w.active_session()
    second = w.add_session(activate=False)

    w.ed_max_lines.setText("321")
    w._on_max_lines_changed()
    assert first.txt_recv.document().maximumBlockCount() == 321
    assert second.txt_recv.document().maximumBlockCount() == 321

    third = w.add_session(activate=False)
    assert third.txt_recv.document().maximumBlockCount() == 321
    w._close_all_sessions()


def test_wrap_mode_applies_to_existing_and_new_sessions(monkeypatch, tmp_path):
    from PyQt5.QtWidgets import QTextEdit

    w = _window(monkeypatch, tmp_path, "wrap-all-sessions")
    first = w.active_session()
    second = w.add_session(activate=False)

    w.sw_wrap.setChecked(False, animate=False)
    w.on_wrap_toggled(False)
    assert first.txt_recv.lineWrapMode() == QTextEdit.NoWrap
    assert second.txt_recv.lineWrapMode() == QTextEdit.NoWrap

    third = w.add_session(activate=False)
    assert third.txt_recv.lineWrapMode() == QTextEdit.NoWrap
    w._close_all_sessions()


def test_missing_display_options_do_not_inherit_previous_tab(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "display-default-isolation")
    w.sw_tx_hex.setChecked(True, animate=False)
    w.sw_append_newline.setChecked(True, animate=False)
    w.sw_rx_hex.setChecked(True, animate=False)
    w.sw_line_split.setChecked(True, animate=False)
    first = w.active_session()
    second = w.add_session(activate=False)
    second.display_opts = {}

    assert w.switch_session(second.id)
    assert w.sw_tx_hex.isChecked() is False
    assert w.sw_append_newline.isChecked() is False
    assert w.sw_rx_hex.isChecked() is False
    assert w.sw_line_split.isChecked() is False
    assert first.display_opts["tx_hex"] is True
    assert first.display_opts["append_nl_on"] is True
    assert first.display_opts["rx_hex"] is True
    assert first.display_opts["line_split"] is True
    w._close_all_sessions()


def test_relative_timestamp_anchor_is_session_owned(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "timestamp-anchor-isolation")
    first = w.active_session()
    second = w.add_session(activate=False)

    with w._with_session(first):
        w._ts_anchor = 101.5
    with w._with_session(second):
        assert w._ts_anchor is None
        w._ts_anchor = 202.5
    assert first._ts_anchor == 101.5
    assert second._ts_anchor == 202.5
    w._close_all_sessions()


def test_protocol_field_cursor_cache_is_session_owned(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "protocol-field-cache-isolation")
    first = w.active_session()
    first._proto_fields.append({"label": "first"})
    second = w.add_session(activate=True)

    assert list(w._proto_fields) == []
    w._proto_fields.append({"label": "second"})
    assert w.switch_session(first.id)
    assert [item["label"] for item in w._proto_fields] == ["first"]
    assert [item["label"] for item in second._proto_fields] == ["second"]
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
    original_prepare = w._prepare_project_switch
    suppress_depths = []

    def _prepare():
        suppress_depths.append(w._autosave_suppress)
        return original_prepare()

    monkeypatch.setattr(w, "_prepare_project_switch", _prepare)

    w.import_config()

    assert suppress_depths and suppress_depths[0] > 0
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
    w._commit_project_switch_sessions()
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
    original_prepare = w._prepare_project_switch
    suppress_depths = []

    def _prepare():
        suppress_depths.append(w._autosave_suppress)
        return original_prepare()

    monkeypatch.setattr(w, "_prepare_project_switch", _prepare)
    index = w.cb_workspace_template.findData("modbus_rtu")
    w.cb_workspace_template.setCurrentIndex(index)

    w._apply_workspace_protocol_template()

    assert suppress_depths and suppress_depths[0] > 0
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
    w._commit_project_switch_sessions()
    w._close_all_sessions()


def test_project_switch_refuses_pinned_background_worker(monkeypatch, tmp_path):
    """Replacing sessions must not orphan an asynchronous window worker."""
    w = _window(monkeypatch, tmp_path, "project-bg-worker")
    owner = w.active_session()
    w.add_session(activate=True)

    class _Worker:
        @staticmethod
        def isRunning():
            return True

    owner._script_worker = _Worker()
    w._io_bind_owner("script", owner)
    notices = []
    monkeypatch.setattr(w, "toast_session_busy", lambda: notices.append(True))

    assert w._prepare_project_switch() is False
    assert owner in w.sessions()
    assert owner._script_worker is not None
    assert notices == [True]

    owner._script_worker = None
    w._io_clear_owner("script")
    w._close_all_sessions()


def test_profile_switch_refuses_pinned_background_worker(monkeypatch, tmp_path):
    """Profile replacement uses the same orphan-worker guard as project load."""
    w = _window(monkeypatch, tmp_path, "profile-bg-worker")
    owner = w.active_session()
    w.add_session(activate=True)

    class _Worker:
        @staticmethod
        def isRunning():
            return True

    owner._script_worker = _Worker()
    w._io_bind_owner("script", owner)
    notices = []
    confirms = []
    monkeypatch.setattr(w, "toast_session_busy", lambda: notices.append(True))
    monkeypatch.setattr(
        w, "_confirm_project_switch", lambda: confirms.append(True) or True)
    profile = w._profile

    w._switch_profile("8" if profile != "8" else "7")

    assert w._profile == profile
    assert owner in w.sessions()
    assert owner._script_worker is not None
    assert notices == [True]
    assert confirms == []
    owner._script_worker = None
    w._io_clear_owner("script")
    w._close_all_sessions()


def test_finished_transfer_remains_busy_until_done_callback(
        monkeypatch, tmp_path):
    """Queued transfer completion must keep its captured session alive."""
    w = _window(monkeypatch, tmp_path, "xfer-done-gap")
    owner = w.active_session()

    class _Worker:
        @staticmethod
        def isRunning():
            return False

    w._xfer_worker = _Worker()
    w._io_bind_owner("transfer", owner)
    assert w._xfer_active() is True
    assert w._hard_busy_owned_by(owner) is True

    w._xfer_worker = None
    w._io_clear_owner("transfer")
    w._close_all_sessions()


def test_xfer_start_blocked_on_other_tab_while_transfer_runs(
        monkeypatch, tmp_path):
    """A live transfer on another tab must not block Start on this idle tab."""
    w = _window(monkeypatch, tmp_path, "xfer-start-other-tab")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    _open_virtual(w)

    class _Worker:
        @staticmethod
        def isRunning():
            return True

    s1._xfer_worker = _Worker()
    w._io_bind_owner("transfer", s1)
    assert w.active_session() is s2
    assert w._xfer_start_blocked() is False
    assert w._xfer_active(s1) is True
    assert w._hard_busy_owned_by(s1) is True
    assert w._hard_busy_owned_by(s2) is False

    s1._xfer_worker = None
    w._io_clear_owner("transfer")
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


def test_cold_restore_is_the_only_ui_load_path_that_restores_log_intent(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "cold-log-restore")
    payload = [{
        "id": "cold-log", "title_index": 1,
        "log_wanted": True, "log_base_path": str(tmp_path / "cold.log"),
    }]
    w.settings.setValue("sessions_v1", json.dumps(payload))
    restored = []
    monkeypatch.setattr(
        w, "_restore_session_log_intent",
        lambda session: restored.append(session.id) or True)

    w._restore_sessions_settings()

    assert restored == ["cold-log"]
    w._close_all_sessions()


def test_reconnect_policy_and_control_defaults_do_not_cross_sessions(
        monkeypatch, tmp_path):
    import main_window as main_window_module

    w = _window(monkeypatch, tmp_path, "session-reconnect-policy")
    w.settings.setValue("auto_reconnect", True)
    w.settings.setValue("serial_dtr", True)
    w.settings.setValue("serial_rts", True)
    first = w.active_session()
    first.conn_fields = {
        "auto_reconnect": False, "serial_dtr": False, "serial_rts": False,
    }
    w._load_session_into_ui(first)
    assert w.settings.value("auto_reconnect", True, type=bool) is True
    assert w.settings.value("serial_dtr", True, type=bool) is True
    assert w.settings.value("serial_rts", True, type=bool) is True
    assert w._capture_connection_fields()["auto_reconnect"] is False
    assert w._capture_connection_fields()["serial_dtr"] is False

    second = w.add_session(activate=False)
    second.conn_fields = {"auto_reconnect": True}
    autos = []
    monkeypatch.setattr(
        main_window_module._reconnect_policy, "plan_schedule",
        lambda **kwargs: autos.append(kwargs["auto_reconnect"])
        or {"action": "skip"})
    with w._with_session(first):
        w._schedule_reconnect()
    with w._with_session(second):
        w._schedule_reconnect()
    assert autos == [False, True]
    w._close_all_sessions()


def test_partial_session_connection_fields_use_global_control_defaults(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "partial-session-control-defaults")
    w.settings.setValue("auto_reconnect", False)
    w.settings.setValue("serial_dtr", False)
    w.settings.setValue("serial_rts", False)
    session = w.active_session()
    session.conn_fields = {"net_proto": "Serial"}

    w._load_session_into_ui(session)
    captured = w._capture_connection_fields()

    assert captured["auto_reconnect"] is False
    assert captured["serial_dtr"] is False
    assert captured["serial_rts"] is False
    assert w._session_auto_reconnect_enabled(w, session) is False
    w._save_ui_into_session(session)
    assert session.conn_fields["auto_reconnect"] is False
    assert session.conn_fields["serial_dtr"] is False
    assert session.conn_fields["serial_rts"] is False
    w._close_all_sessions()


def test_empty_session_does_not_inherit_previous_connection_controls(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "empty-session-control-defaults")
    w.settings.setValue("auto_reconnect", False)
    w.settings.setValue("serial_dtr", False)
    w.settings.setValue("serial_rts", False)
    first = w.active_session()
    first.conn_fields = {
        "auto_reconnect": True, "serial_dtr": True, "serial_rts": True,
    }
    w._load_session_into_ui(first)
    assert w._capture_connection_fields()["auto_reconnect"] is True

    second = w.add_session(activate=True)
    captured = w._capture_connection_fields()

    assert second.conn_fields == {}
    assert captured["auto_reconnect"] is False
    assert captured["serial_dtr"] is False
    assert captured["serial_rts"] is False
    w._save_ui_into_session(second)
    assert second.conn_fields["auto_reconnect"] is False
    assert second.conn_fields["serial_dtr"] is False
    assert second.conn_fields["serial_rts"] is False
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


def test_session_switch_keeps_per_session_trigger_stream_state(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "trigger-switch-keep")
    first = w.active_session()
    second = w.add_session(activate=False)
    key = (first.id, "rx", None)
    w._trg_dec_buf = {key: b"partial"}
    w._trg_dec = {key: object()}
    w._trg_ansi_pending = {key: "escape"}
    w._trg_tail_bytes = {key: b"tail"}
    w._trg_tail_text = {key: "tail"}
    assert w.switch_session(second.id)
    assert w._trg_dec_buf.get(key) == b"partial"
    assert key in w._trg_dec
    assert w._trg_ansi_pending.get(key) == "escape"
    assert w._trg_tail_bytes.get(key) == b"tail"
    assert w._trg_tail_text.get(key) == "tail"
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


def test_concurrent_session_logs_keep_writing_in_background(monkeypatch, tmp_path):
    """Each session owns a log handle; switching tabs must not close others."""
    w = _window(monkeypatch, tmp_path, "dual-log")
    _open_virtual(w)
    s1 = w.active_session()
    log1 = tmp_path / "s1.log"
    s1.log_base_path = str(log1)
    s1.log_seg = 0
    assert w._open_log_segment(str(log1), session=s1)
    s1.display_opts = dict(s1.display_opts or {}, show_timestamp=False)

    s2 = w.add_session(activate=True)
    _open_virtual(w)
    log2 = tmp_path / "s2.log"
    s2.log_base_path = str(log2)
    s2.log_seg = 0
    assert w._open_log_segment(str(log2), session=s2)
    w.sw_show_timestamp.setChecked(True)
    w._save_ui_into_session(s2)
    assert s1._log_file is not None
    assert s2._log_file is not None

    before1 = log1.read_text(encoding="utf-8")
    s1.conn.inject(b"BG-LOG-1")
    _pump()
    after1 = log1.read_text(encoding="utf-8")
    assert "BG-LOG-1" in after1
    assert after1 != before1
    bg_line = next(line for line in after1.splitlines() if "BG-LOG-1" in line)
    assert not bg_line.startswith("[")
    assert "BG-LOG-1" not in log2.read_text(encoding="utf-8")

    w.txt_send.setPlainText("FG-LOG-2")
    w.do_send()
    _pump()
    assert "FG-LOG-2" in log2.read_text(encoding="utf-8")

    w.switch_session(s1.id)
    assert s1._log_file is not None
    assert s2._log_file is not None
    w._close_all_sessions()
    assert s1._log_file is None
    assert s2._log_file is None


def test_background_period_log_uses_own_timestamp(monkeypatch, tmp_path):
    """Background period TX logging must not inherit the active tab timestamp."""
    w = _window(monkeypatch, tmp_path, "bg-period-log-ts")
    _open_virtual(w)
    s1 = w.active_session()
    path = tmp_path / "period.log"
    s1.log_base_path = str(path)
    assert w._open_log_segment(str(path), session=s1)
    # Become background first - switch_session would overwrite draft/opts/period.
    w.add_session(activate=True)
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(True)
    s1.send_draft = "PLOG"
    s1.display_opts = dict(
        s1.display_opts or {},
        show_timestamp=False, append_nl_on=False, tx_hex=False, checksum=0)
    s1.period_on = True

    w._period_send_for(s1.id)
    text = path.read_text(encoding="utf-8")
    assert "PLOG" in text
    line = next(part for part in text.splitlines() if "PLOG" in part)
    assert not line.startswith("[")
    w._close_all_sessions()


def test_switch_away_while_disconnected_keeps_reconnect_intent(
        monkeypatch, tmp_path):
    """Saving UI on a down tab must not clear preserved AA reconnect intent."""
    w = _window(monkeypatch, tmp_path, "switch-keep-intent")
    _open_virtual(w)
    s1 = w.active_session()
    s1.period_on = True
    s1._period_timer.start(60000)
    path = tmp_path / "keep-intent.log"
    s1.log_base_path = str(path)
    assert w._open_log_segment(str(path), session=s1)
    snapshot = dict(s1._reconnect_snapshot)

    s2 = w.add_session(activate=True)
    w._route_session_state(s1.id, False)
    assert s1.period_on is True
    assert s1.log_wanted is True

    # Visiting a disconnected session must not reopen its log. Only a real
    # reconnect or process-start cold restore may consume the preserved intent.
    w.switch_session(s1.id)
    assert not s1.is_open()
    assert s1._log_file is None
    assert w.sw_log_file.isChecked() is False
    if hasattr(w, "sw_period"):
        assert w.sw_period.isChecked() is False
    w.switch_session(s2.id)
    assert s1.period_on is True
    assert s1.log_wanted is True
    assert s1._log_file is None

    s1._reconnect_timer.stop()
    with w._with_session(s1):
        w.open_conn(reconnect_snapshot=snapshot)
    assert s1._period_timer.isActive()
    assert s1._log_file is not None
    w._close_all_sessions()


def test_user_disables_log_clears_reconnect_intent(monkeypatch, tmp_path):
    """Explicitly turning logging off must not reopen after auto-reconnect."""
    w = _window(monkeypatch, tmp_path, "log-off-intent")
    _open_virtual(w)
    s1 = w.active_session()
    path = tmp_path / "log-off.log"
    s1.log_base_path = str(path)
    assert w._open_log_segment(str(path), session=s1)
    assert s1.log_wanted is True
    # _open_log_segment does not flip the switch; simulate a user toggle off.
    w.sw_log_file.blockSignals(True)
    w.sw_log_file.setChecked(True)
    w.sw_log_file.blockSignals(False)
    w.sw_log_file.setChecked(False)
    assert s1.log_wanted is False
    assert s1._log_file is None
    snapshot = dict(s1._reconnect_snapshot)

    w.add_session(activate=True)
    w._route_session_state(s1.id, False)
    assert s1.log_wanted is False
    s1._reconnect_timer.stop()
    with w._with_session(s1):
        w.open_conn(reconnect_snapshot=snapshot)
    assert s1.log_wanted is False
    assert s1._log_file is None
    w._close_all_sessions()


def test_background_reconnect_restores_period_and_log_intent(
        monkeypatch, tmp_path):
    """An automatic reconnect resumes only the owning session's AA runtime."""
    w = _window(monkeypatch, tmp_path, "reconnect-aa-intent")
    _open_virtual(w)
    s1 = w.active_session()
    s1.send_draft = "KEEP-RUNNING"
    s1.period_ms = "60000"
    s1.period_on = True
    s1._period_timer.start(60000)
    path = tmp_path / "reconnect.log"
    s1.log_base_path = str(path)
    assert w._open_log_segment(str(path), session=s1)
    snapshot = dict(s1._reconnect_snapshot)

    s2 = w.add_session(activate=True)
    w._route_session_state(s1.id, False)
    assert s1.conn is None
    assert s1.period_on is True
    assert not s1._period_timer.isActive()
    assert s1.log_wanted is True
    assert s1._log_file is None
    assert s1._reconnect_timer.isActive()

    s1._reconnect_timer.stop()
    with w._with_session(s1):
        w.open_conn(reconnect_snapshot=snapshot)
    assert s1.is_open()
    assert s1._period_timer.isActive()
    assert s1.log_wanted is True
    assert s1._log_file is not None
    assert w.active_session() is s2
    w._close_all_sessions()


def test_manual_close_clears_period_and_log_intent(monkeypatch, tmp_path):
    """Only automatic reconnect preserves AA runtime; user close is final."""
    w = _window(monkeypatch, tmp_path, "manual-close-intent")
    _open_virtual(w)
    session = w.active_session()
    session.period_on = True
    session._period_timer.start(60000)
    path = tmp_path / "manual-close.log"
    session.log_base_path = str(path)
    assert w._open_log_segment(str(path), session=session)

    w.close_conn()
    assert session.period_on is False
    assert not session._period_timer.isActive()
    assert session.log_wanted is False
    assert session._log_file is None
    w._close_all_sessions()


def test_concurrent_period_send_keeps_running_in_background(monkeypatch, tmp_path):
    """Period timers are per-session; leaving a tab must not stop others."""
    w = _window(monkeypatch, tmp_path, "dual-period")
    _open_virtual(w)
    s1 = w.active_session()
    w.txt_send.setPlainText("TICK-A")
    s1.send_draft = "TICK-A"
    s1.period_ms = "40"
    s1.period_on = True
    s1.display_opts = {"tx_hex": False}
    w.ed_period_ms.setText("40")
    w.sw_period.blockSignals(True)
    w.sw_period.setChecked(True)
    w.sw_period.blockSignals(False)
    w._sync_session_period_timer(s1)
    assert s1._period_timer.isActive()

    s2 = w.add_session(activate=True)
    _open_virtual(w)
    w.txt_send.setPlainText("TICK-B")
    s2.send_draft = "TICK-B"
    s2.period_ms = "40"
    s2.period_on = True
    s2.display_opts = {"tx_hex": False}
    w.ed_period_ms.setText("40")
    w.sw_period.blockSignals(True)
    w.sw_period.setChecked(True)
    w.sw_period.blockSignals(False)
    w._sync_session_period_timer(s2)

    assert s1._period_timer.isActive()
    assert s2._period_timer.isActive()
    before_s1_tx = s1.tx_bytes
    before_s2_tx = s2.tx_bytes
    _pump(25, 0.02)
    assert s1.tx_bytes > before_s1_tx
    assert s2.tx_bytes > before_s2_tx
    assert s1._period_timer.isActive()
    w._close_all_sessions()
    assert not s1._period_timer.isActive()
    assert not s2._period_timer.isActive()


def test_invalid_persisted_period_is_disabled_not_silently_clamped(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "invalid-period")
    _open_virtual(w)
    session = w.active_session()
    session.period_ms = "0"
    session.period_on = True
    notices = []
    monkeypatch.setattr(
        w, "toast", lambda msg, error=False: notices.append((msg, error)))

    w._sync_session_period_timer(session)

    assert session.period_ms == "0"
    assert session.period_on is False
    assert not session._period_timer.isActive()
    assert notices and notices[-1][1] is True
    w._close_all_sessions()


def test_log_path_conflict_rejects_second_session(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "log-conflict")
    s1 = w.active_session()
    path = str(tmp_path / "shared.log")
    s1.log_base_path = path
    assert w._open_log_segment(path, session=s1)
    s2 = w.add_session(activate=True)
    s2.log_base_path = path
    assert w._open_log_segment(path, session=s2) is False
    assert s2._log_file is None
    assert s1._log_file is not None
    w._close_all_sessions()


def test_default_session_title_follows_language(monkeypatch, tmp_path):
    """Default tab titles use session_default and refresh on language change."""
    w = _window(monkeypatch, tmp_path, "session-title-i18n")
    s1 = w.active_session()
    assert s1.title_index == 1
    w._lang = "zh"
    w._L = __import__("i18n", fromlist=["TR"]).TR["zh"]
    assert s1.tab_label() == w._t("session_default")
    s2 = w.add_session(activate=False)
    assert s2.title_index >= 2
    assert s2.tab_label() == "%s-%d" % (w._t("session_default"), s2.title_index)
    w._lang = "en"
    w._L = __import__("i18n", fromlist=["TR"]).TR["en"]
    w._apply_language()
    assert s1.tab_label() == "Session"
    assert s2.tab_label().startswith("Session-")
    w._close_all_sessions()


def test_active_period_tick_does_not_snapshot_entire_ui(monkeypatch, tmp_path):
    """The minimum-interval hot path reads TX controls without full UI capture."""
    w = _window(monkeypatch, tmp_path, "active-period-hot-path")
    _open_virtual(w)
    session = w.active_session()
    w.txt_send.setPlainText("PING")
    session.display_opts = {"append_nl_on": False, "append_nl": 0}
    w.sw_append_newline.setChecked(True)
    w.cb_append_nl.setCurrentIndex(1)  # LF; differs from the stale snapshot.
    session.period_on = True
    captures = []
    monkeypatch.setattr(
        w, "_save_ui_into_session", lambda *_a, **_k: captures.append(True))

    w._period_send_for(session.id)

    assert captures == []
    assert session.send_draft == "PING"
    assert session.conn.tx_log[-1] == b"PING\n"
    w._close_all_sessions()


def test_background_period_skips_window_recording_and_triggers(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "bg-period-window-engines")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    s1.send_draft = "BACKGROUND"
    s1.display_opts = {"tx_hex": False}
    s1.period_on = True
    fed = []
    monkeypatch.setattr(
        w, "_record_stream_tx",
        lambda data, source=None: fed.append((bytes(data), source)))

    w._period_send_for(s1.id)

    assert s1.conn.tx_log[-1] == b"BACKGROUND"
    assert len(fed) == 1
    assert fed[0][0] == b"BACKGROUND"
    assert w.active_session() is s2
    w._close_all_sessions()


def test_background_non_server_never_reads_active_target(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "bg-period-no-target-leak")
    _open_virtual(w)
    s1 = w.active_session()
    w.add_session(activate=True)
    w.cb_proto.setCurrentText("TCP Server")
    w._update_net_fields()
    w.cb_target.clear()
    w.cb_target.addItem("client B", "client-b")
    s1.send_draft = "BACKGROUND"
    s1.send_target = "keep-me"
    s1.display_opts = {"tx_hex": False}
    s1.period_on = True

    w._period_send_for(s1.id)

    assert s1.conn.tx_log[-1] == b"BACKGROUND"
    assert s1.send_target == "keep-me"
    w._close_all_sessions()


def test_background_period_failure_does_not_touch_active_ui(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "bg-period-silent-error")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    s1.send_draft = "ZZ"
    s1.display_opts = {"tx_hex": True}
    s1.period_on = True
    notices = []
    refreshes = []
    monkeypatch.setattr(
        w, "toast", lambda msg, error=False: notices.append((msg, error)))
    monkeypatch.setattr(
        w, "_refresh_stat_labels", lambda *a, **k: refreshes.append(True))
    errors_before = s1.tx_errors

    w._period_send_for(s1.id)

    assert s1.period_on is False
    assert s1.tx_errors == errors_before + 1
    assert notices == []
    assert refreshes == []
    assert w.active_session() is s2
    w._close_all_sessions()


def test_background_period_uses_own_tx_options(monkeypatch, tmp_path):
    """Background period TX must use owning session encoding/format/{count}."""
    w = _window(monkeypatch, tmp_path, "bg-period-opts")
    _open_virtual(w)
    s1 = w.active_session()
    # Snapshot via UI before leave — switch_session saves txt_send/opts into s1.
    w.txt_send.setPlainText("\u4e2d{count}")
    if hasattr(w, "sw_append_newline"):
        w.sw_append_newline.setChecked(True)
    if hasattr(w, "cb_append_nl"):
        w.cb_append_nl.setCurrentIndex(1)  # LF
    if hasattr(w, "cb_checksum"):
        w.cb_checksum.setCurrentIndex(1)
    if hasattr(w, "cb_encoding"):
        idx = w.cb_encoding.findData("gbk")
        assert idx >= 0
        w.cb_encoding.setCurrentIndex(idx)
    w._save_ui_into_session(s1)
    s1._send_count = 0

    s2 = w.add_session(activate=True)
    _open_virtual(w)
    # Active tab uses different encoding/append/checksum; none may leak into s1.
    if hasattr(w, "sw_append_newline"):
        w.sw_append_newline.setChecked(False)
    if hasattr(w, "cb_checksum"):
        w.cb_checksum.setCurrentIndex(0)
    if hasattr(w, "cb_encoding"):
        idx = w.cb_encoding.findData("utf-8")
        if idx >= 0:
            w.cb_encoding.setCurrentIndex(idx)
    s2._send_count = 40

    s1.period_on = True
    w._period_send_for(s1.id)
    base = "\u4e2d\x01".encode("gbk") + b"\n"
    expected = base + w.compute_checksum(base, 1)
    assert s1.conn.tx_log[-1] == expected
    assert s1._send_count == 1
    assert s2._send_count == 40  # not crossed
    w._close_all_sessions()


def test_background_period_uses_own_send_target(monkeypatch, tmp_path):
    """TCP Server period TX must address the owning session's send_target."""
    w = _window(monkeypatch, tmp_path, "bg-period-target")
    s1 = w.active_session()
    # Become background first — switch_session would overwrite draft/target from UI.
    s2 = w.add_session(activate=True)
    s1._conn_proto = "TCP Server"
    s1.send_target = "client-a"
    s1.send_draft = "PING"
    s1.display_opts = {"tx_hex": False, "append_nl_on": False, "checksum": 0}
    s1.period_on = True
    seen = []

    class _Conn:
        is_open = True

        def send(self, data, target=None):
            seen.append((bytes(data), target))
            return len(data)

        def deleteLater(self):
            pass

    s1.conn = _Conn()
    # Active UI would pick a different target if _send_target read the combo.
    if hasattr(w, "cb_target"):
        w.cb_target.blockSignals(True)
        w.cb_target.clear()
        w.cb_target.addItem("all", "__all__")
        w.cb_target.addItem("other", "client-b")
        w.cb_target.setCurrentIndex(1)
        w.cb_target.blockSignals(False)
    w._period_send_for(s1.id)
    assert seen == [(b"PING", "client-a")]
    s1.conn = None
    w._close_all_sessions()


def test_tcp_server_target_survives_tab_switch(monkeypatch, tmp_path):
    """Rebuilding the shared target combo must not overwrite the tab's choice."""
    w = _window(monkeypatch, tmp_path, "target-switch")
    s1 = w.active_session()
    s1._conn_proto = "TCP Server"
    s1.clients = [("client-a", "client A")]
    s1.send_target = "client-a"
    w._restore_session_network_ui(s1)
    assert w.cb_target.currentData() == "client-a"

    s2 = w.add_session(activate=True)
    s2._conn_proto = "TCP Server"
    s2.clients = [("client-b", "client B")]
    s2.send_target = "client-b"
    w._restore_session_network_ui(s2)

    assert w.switch_session(s1.id)
    assert s1.send_target == "client-a"
    assert w.cb_target.currentData() == "client-a"
    w._close_all_sessions()


def test_io_task_busy_periodic_is_context_session(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "busy-period-ctx")
    s1 = w.active_session()
    s1.period_on = True
    s1._period_timer.start(1000)
    s2 = w.add_session(activate=True)
    # Active s2 has no period; busy(periodic) must be False for s2 context.
    assert w._session_period_active(s2) is False
    assert w._io_task_busy() is False
    with w._with_session(s1):
        assert w._session_period_active() is True
        assert w._io_task_busy(exclude=("periodic",)) is False
    s1._period_timer.stop()
    w._close_all_sessions()


def test_terminal_mode_stops_all_session_period_timers(monkeypatch, tmp_path):
    """Entering terminal mode must halt every session period timer."""
    w = _window(monkeypatch, tmp_path, "term-stop-all-period")
    _open_virtual(w)
    s1 = w.active_session()
    s1.period_on = True
    s1._period_timer.start(60000)
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    s2.period_on = True
    s2._period_timer.start(60000)
    assert s1._period_timer.isActive()
    w._set_terminal_enabled(True)
    assert s1.period_on is False
    assert s2.period_on is False
    assert not s1._period_timer.isActive()
    assert not s2._period_timer.isActive()
    w._set_terminal_enabled(False)
    w._close_all_sessions()


def test_background_period_encoding_defaults_without_snapshot(
        monkeypatch, tmp_path):
    """Missing session encoding must not inherit the active tab combo."""
    w = _window(monkeypatch, tmp_path, "bg-period-enc-default")
    _open_virtual(w)
    s1 = w.active_session()
    w.add_session(activate=True)
    if hasattr(w, "cb_encoding"):
        idx = w.cb_encoding.findData("gbk")
        if idx >= 0:
            w.cb_encoding.setCurrentIndex(idx)
    s1.send_draft = "\u4e2d"
    s1.display_opts = {"tx_hex": False, "append_nl_on": False, "checksum": 0}
    s1.period_on = True
    seen = []

    class _Conn:
        is_open = True

        def send(self, data, target=None):
            seen.append(bytes(data))
            return len(data)

        def deleteLater(self):
            pass

    s1.conn = _Conn()
    w._period_send_for(s1.id)
    assert seen == ["\u4e2d".encode("utf-8")]
    s1.conn = None
    w._close_all_sessions()


def test_delayed_auto_reply_keeps_originating_session_after_switch(
        monkeypatch, tmp_path):
    """A delayed reply armed by A must never be transmitted through B."""
    w = _window(monkeypatch, tmp_path, "ar-delayed-owner")
    first = w.active_session()
    second = w.add_session(activate=False)
    sent_from = []
    w._ar_on = True
    first._ar_enabled = True
    monkeypatch.setattr(w, "_is_open", lambda: True)
    monkeypatch.setattr(
        w, "_send_text",
        lambda *_a, **_k: sent_from.append(w._session_ctx().id) or True)

    with w._with_session(first):
        w._ar_schedule_send(["AA"], False, 0, [], (20, 20))
    assert w.switch_session(second.id)
    # Opening/closing/resetting B must not invalidate A's delayed reply token.
    w._ar_reset_state()
    _pump(10, 0.01)

    assert sent_from == [first.id]
    w._close_all_sessions()


def test_window_autoreply_reset_clears_every_session_runtime(
        monkeypatch, tmp_path):
    """A window-level AR config/reset cannot leave stale state in hidden tabs."""
    w = _window(monkeypatch, tmp_path, "ar-global-reset")
    first = w.active_session()
    second = w.add_session(activate=False)
    w._ar_sm = {"on": True, "init": "fresh"}
    for session, suffix in ((first, b"a"), (second, b"b")):
        with w._with_session(session):
            w._ar_buf = b"partial-" + suffix
            w._modbus_buffers["peer"] = b"partial"
            w._ar_state = "stale"
            w._ar_sm_pending = object()
            w._ar_sm_queue.append(b"queued")

    w._ar_reset_all_buffers()
    w._ar_reset_all_states()

    for session in (first, second):
        assert session._ar_buf == b""
        assert session._modbus_buffers == {}
        assert session._ar_state == "fresh"
        assert session._ar_sm_pending is None
        assert list(session._ar_sm_queue) == []
    w._close_all_sessions()


def test_tcp_server_modbus_partial_buffers_are_session_owned(
        monkeypatch, tmp_path):
    """Identical client keys in two server tabs cannot share a half frame."""
    w = _window(monkeypatch, tmp_path, "modbus-buffer-owner")
    first = w.active_session()
    second = w.add_session(activate=False)
    key = "10.0.0.2:50000"
    first._conn_proto = "TCP Server"
    second._conn_proto = "TCP Server"
    first.clients = [(key, key)]
    second.clients = [(key, key)]

    with w._with_session(first):
        w._modbus_buffers[key] = b"partial-a"
    assert w.switch_session(second.id)

    with w._with_session(second):
        assert w._modbus_buffers == {}
    with w._with_session(first):
        assert w._modbus_buffers == {key: b"partial-a"}
    w._close_all_sessions()


def test_background_serial_reconnect_applies_session_control_lines(
        monkeypatch, tmp_path):
    """A hidden serial reconnect still writes that tab's DTR/RTS values."""
    w = _window(monkeypatch, tmp_path, "background-serial-lines")
    background = w.add_session(activate=False)
    background.conn_fields = {"serial_dtr": False, "serial_rts": True}
    calls = []

    class _SerialConn:
        def __init__(self, *_args, **_kwargs):
            self.is_open = False

        def open(self):
            self.is_open = True
            return True

        def set_dtr(self, value):
            calls.append(("dtr", bool(value)))

        def set_rts(self, value):
            calls.append(("rts", bool(value)))

        def deleteLater(self):
            return None

    monkeypatch.setattr("main_window.SerialConn", _SerialConn)
    monkeypatch.setattr(w, "_bind_conn_signals", lambda *_a, **_k: None)
    snapshot = {
        "proto": "Serial",
        "fields": {"port": "COM99", "baud": "9600"},
        "serial_extras": ("8", "None", "1", "None"),
        "conn_cfg": ("Serial", "COM99", 9600, "8", "None", "1", "None"),
    }

    with w._with_session(background):
        w.open_conn(reconnect_snapshot=snapshot)

    assert background.conn is not None and background.conn.is_open
    assert calls == [("dtr", False), ("rts", True)]
    background.conn = None
    w._close_all_sessions()


def test_switch_to_background_serial_starts_control_line_polling(
        monkeypatch, tmp_path):
    """A serial link opened while hidden must start CTS/DSR polling when selected."""
    w = _window(monkeypatch, tmp_path, "background-serial-poll")
    first = w.active_session()
    first._conn_proto = "Virtual"
    serial = w.add_session(activate=False)
    reads = []

    class _SerialConn:
        is_open = True

        def read_lines(self):
            reads.append(True)
            return {"cts": True, "dsr": False, "dcd": False, "ri": False}

    serial.conn = _SerialConn()
    serial._conn_proto = "Serial"
    assert not w._ctrl_poll_timer.isActive()

    assert w.switch_session(serial.id)
    assert reads == [True]
    assert w._ctrl_poll_timer.isActive()

    assert w.switch_session(first.id)
    assert not w._ctrl_poll_timer.isActive()
    serial.conn = None
    w._close_all_sessions()


def test_serial_reset_pulse_releases_originating_session_after_switch(
        monkeypatch, tmp_path):
    """The delayed DTR release must stay bound to the tab that started it."""
    w = _window(monkeypatch, tmp_path, "serial-reset-owner")
    first = w.active_session()
    second = w.add_session(activate=False)
    calls = {first.id: [], second.id: []}

    class _SerialConn:
        is_open = True

        def __init__(self, sid):
            self.sid = sid

        def set_dtr(self, value):
            calls[self.sid].append(bool(value))

        def read_lines(self):
            return {"cts": False, "dsr": False, "dcd": False, "ri": False}

    first.conn = _SerialConn(first.id)
    first._conn_proto = "Serial"
    first.conn_fields = {"serial_dtr": True, "serial_rts": False}
    second.conn = _SerialConn(second.id)
    second._conn_proto = "Serial"
    second.conn_fields = {"serial_dtr": False, "serial_rts": False}

    w._pulse_reset()
    assert w.switch_session(second.id)
    _pump(20, 0.01)

    assert calls[first.id] == [False, True]
    assert calls[second.id] == []
    first.conn = None
    second.conn = None
    w._close_all_sessions()


def test_template_apply_failure_restores_previous_session_runtime(
        monkeypatch, tmp_path):
    """A failed settings apply must restore the old tabs and receive views."""
    w = _window(monkeypatch, tmp_path, "template-session-rollback")
    first = w.active_session()
    first.txt_recv.setPlainText("history-a")
    second = w.add_session(activate=True)
    second.txt_recv.setPlainText("history-b")
    old_sessions = list(w.sessions())
    old_active_id = w.active_session().id
    old_widgets = [session.txt_recv for session in old_sessions]
    real_apply = w._apply_loaded_settings
    calls = {"count": 0}

    def _fail_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("reload failed")
        return real_apply()

    monkeypatch.setattr(w, "_confirm_dlg", lambda *_a, **_k: True)
    monkeypatch.setattr(w, "_apply_loaded_settings", _fail_once)
    index = w.cb_workspace_template.findData("modbus_rtu")
    w.cb_workspace_template.setCurrentIndex(index)

    w._apply_workspace_protocol_template()

    assert w.sessions() == old_sessions
    assert w.active_session().id == old_active_id
    assert [session.txt_recv for session in w.sessions()] == old_widgets
    assert first.txt_recv.toPlainText() == "history-a"
    assert second.txt_recv.toPlainText() == "history-b"
    assert w.recv_stack.currentWidget() is second.txt_recv
    w._close_all_sessions()


def test_import_apply_failure_restores_previous_session_runtime(
        monkeypatch, tmp_path):
    """An import reload failure cannot discard the current tabs or histories."""
    import json
    from PyQt5.QtWidgets import QFileDialog

    w = _window(monkeypatch, tmp_path, "import-session-rollback")
    first = w.active_session()
    first.txt_recv.setPlainText("history-a")
    second = w.add_session(activate=True)
    second.txt_recv.setPlainText("history-b")
    old_sessions = list(w.sessions())
    imported = tmp_path / "broken-apply.json"
    imported.write_text(json.dumps({"settings": {"language": "en"}}), encoding="utf-8")
    real_apply = w._apply_loaded_settings
    calls = {"count": 0}
    messages = []

    def _fail_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("reload failed")
        return real_apply()

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *_a, **_k: (str(imported), "JSON (*.json)"))
    monkeypatch.setattr(w, "_apply_loaded_settings", _fail_once)
    monkeypatch.setattr(
        w, "_info_dlg", lambda title, body, **_k: messages.append((title, body)))

    w.import_config()

    assert w.sessions() == old_sessions
    assert w.active_session() is second
    assert first.txt_recv.toPlainText() == "history-a"
    assert second.txt_recv.toPlainText() == "history-b"
    assert len(messages) == 1
    assert "reload failed" in messages[0][1]
    w._close_all_sessions()


def test_open_project_apply_failure_restores_previous_session_runtime(
        monkeypatch, tmp_path):
    """A project apply exception rolls the temporary session replacement back."""
    import project_model

    w = _window(monkeypatch, tmp_path, "project-session-rollback")
    first = w.active_session()
    w.txt_send.setPlainText("draft-a")
    second = w.add_session(activate=True)
    w.txt_send.setPlainText("draft-b")
    old_sessions = list(w.sessions())
    monkeypatch.setattr(
        project_model, "load_project",
        lambda _path: {"settings": {}, "resources": {}, "name": "x"})
    monkeypatch.setattr(
        project_model, "merge_project_resources",
        lambda settings, resources: settings)
    monkeypatch.setattr(
        w, "_apply_project_settings",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("apply failed")))

    assert w._open_project_path(
        str(tmp_path / "fake.ctproj"), confirm=False,
        notify=False, notify_errors=False) is False

    assert w.sessions() == old_sessions
    assert w.active_session() is second
    assert first.send_draft == "draft-a"
    assert second.send_draft == "draft-b"
    w._close_all_sessions()


def test_display_options_matrix_background_vs_active(monkeypatch, tmp_path):
    """Background RX uses owning display_opts; active tab uses live UI.

    Covers timestamp, HEX/hexdump/numview, ANSI strip, line split, encoding,
    freeze (view locked, log still writes), without active-tab leakage.
    """
    w = _window(monkeypatch, tmp_path, "display-matrix")
    _open_virtual(w)
    s1 = w.active_session()
    log1 = tmp_path / "matrix-s1.log"
    s1.log_base_path = str(log1)
    s1.log_seg = 0
    assert w._open_log_segment(str(log1), session=s1)

    # Capture s1 options while it is active, then diverge the foreground.
    w.sw_show_timestamp.setChecked(False)
    w.sw_rx_hex.setChecked(False)
    if hasattr(w, "sw_hexdump"):
        w.sw_hexdump.setChecked(False)
    if hasattr(w, "sw_numview"):
        w.sw_numview.setChecked(False)
    if hasattr(w, "sw_line_split"):
        w.sw_line_split.setChecked(True)
    if hasattr(w, "sw_ansi"):
        w.sw_ansi.setChecked(True)
        w._ansi_on = True
    if hasattr(w, "cb_encoding"):
        idx = w.cb_encoding.findData("gbk")
        if idx >= 0:
            w.cb_encoding.setCurrentIndex(idx)
    w._freeze_view = False
    if hasattr(w, "sw_freeze_view"):
        w.sw_freeze_view.setChecked(False, animate=False)
    w._save_ui_into_session(s1)

    s2 = w.add_session(activate=True)
    _open_virtual(w)
    # Active tab: opposite formatting so leakage would be obvious.
    w.sw_show_timestamp.setChecked(True)
    w.sw_rx_hex.setChecked(True)
    if hasattr(w, "sw_hexdump"):
        w.sw_hexdump.setChecked(False)
    if hasattr(w, "sw_line_split"):
        w.sw_line_split.setChecked(False)
    if hasattr(w, "sw_ansi"):
        w.sw_ansi.setChecked(False)
        w._ansi_on = False
    if hasattr(w, "cb_encoding"):
        idx = w.cb_encoding.findData("utf-8")
        if idx >= 0:
            w.cb_encoding.setCurrentIndex(idx)
    w._save_ui_into_session(s2)

    # --- timestamp / encoding / ANSI / line_split on background ---
    s1.txt_recv.clear()
    # GBK for U+4E2D plus ANSI color; background must decode+strip, not HEX.
    s1.conn.inject(b"\x1b[31m\xd6\xd0\x1b[0m\nTAIL")
    _pump()
    bg = s1.txt_recv.toPlainText()
    assert "\u4e2d" in bg, bg
    assert "TAIL" in bg
    assert "\x1b" not in bg
    assert "31m" not in bg
    assert not bg.lstrip().startswith("["), bg  # no timestamp prefix
    assert "41" not in bg  # must not render as active HEX

    # Active tab still HEX+timestamp when it receives.
    s2.txt_recv.clear()
    s2.conn.inject(b"AB")
    _pump()
    fg = s2.txt_recv.toPlainText()
    assert "41" in fg and "42" in fg
    assert fg.lstrip().startswith("["), fg

    # --- hexdump only on background opts ---
    s1.txt_recv.clear()
    s1.display_opts = dict(
        s1.display_opts or {},
        hexdump_on=True, numview_on=False, rx_hex=False,
        ansi_on=False, show_timestamp=False, line_split=False,
        encoding="utf-8")
    s1.conn.inject(b"CD")
    _pump()
    dump = s1.txt_recv.toPlainText()
    assert "00000000" in dump
    assert "43" in dump and "44" in dump

    # --- freeze locks view but keeps log ---
    s1.txt_recv.clear()
    before_log = log1.read_text(encoding="utf-8")
    s1._freeze_view = True
    s1.display_opts = dict(s1.display_opts or {}, freeze_view=True,
                           hexdump_on=False, rx_hex=False, encoding="utf-8")
    s1.conn.inject(b"FROZEN-VIEW")
    _pump()
    assert "FROZEN-VIEW" not in s1.txt_recv.toPlainText()
    after_log = log1.read_text(encoding="utf-8")
    assert "FROZEN-VIEW" in after_log
    assert after_log != before_log

    # display_context freeze wins even if session proxy is stale False
    s1._freeze_view = False
    s1.display_opts = dict(s1.display_opts or {}, freeze_view=True)
    s1.txt_recv.clear()
    s1.conn.inject(b"CTX-FREEZE")
    _pump()
    assert "CTX-FREEZE" not in s1.txt_recv.toPlainText()
    assert "CTX-FREEZE" in log1.read_text(encoding="utf-8")

    w._close_all_sessions()


def test_display_options_matrix_numview_and_packet_split(monkeypatch, tmp_path):
    """Numview and packet_split stay on the owning background session."""
    w = _window(monkeypatch, tmp_path, "display-matrix-num-pkt")
    _open_virtual(w)
    s1 = w.active_session()
    w.sw_rx_hex.setChecked(False)
    if hasattr(w, "sw_hexdump"):
        w.sw_hexdump.setChecked(False)
    if hasattr(w, "sw_numview"):
        w.sw_numview.setChecked(True)
        w._numview_on = True
    if hasattr(w, "sw_packet_split"):
        w.sw_packet_split.setChecked(False)
    w._save_ui_into_session(s1)

    s2 = w.add_session(activate=True)
    _open_virtual(w)
    if hasattr(w, "sw_numview"):
        w.sw_numview.setChecked(False)
        w._numview_on = False
    w.sw_rx_hex.setChecked(True)
    w._save_ui_into_session(s2)

    s1.txt_recv.clear()
    s1.display_opts = dict(
        s1.display_opts or {},
        numview_on=True, hexdump_on=False, rx_hex=False,
        packet_split=True, packet_timeout="50",
        show_timestamp=False, encoding="utf-8")
    s1.conn.inject(b"\x01\x02")
    _pump(n=5, dt=0.01)
    s1.conn.inject(b"\x03\x04")
    _pump()
    text = s1.txt_recv.toPlainText()
    # Numview should not look like plain HEX dump offset or active HEX stream.
    assert "00000000" not in text
    assert text.strip() != "01 02 03 04"
    # Packet split forces separate appends; at least one numeric rendering present.
    assert any(ch.isdigit() for ch in text), text
    assert "01 02" not in s2.txt_recv.toPlainText()
    w._close_all_sessions()

def test_modbus_slave_bank_is_per_session(monkeypatch, tmp_path):
    """Writes to one tab's slave bank must not appear on another tab."""
    w = _window(monkeypatch, tmp_path, "mb-bank-per-sess")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    w._ar_modbus = w._norm_ar_modbus({
        "on": True, "addr": 1, "variant": "rtu",
        "holding": {"0": 0},
    })
    w._modbus_rebuild_all_sessions()
    assert s1._modbus is not s2._modbus
    s1._modbus.slaves[1].holding[0] = 0xABCD
    assert s2._modbus.slaves[1].holding.get(0, 0) != 0xABCD
    w._close_all_sessions()


def test_dual_sessions_can_run_sequence_concurrently(monkeypatch, tmp_path):
    """Two tabs may each start a sequence; busy gate is per-session."""
    w = _window(monkeypatch, tmp_path, "dual-seq")
    _open_virtual(w)
    s1 = w.active_session()
    steps = [{"on": True, "send": "AA", "hex": True, "expect": "", "timeout": 50}]
    w._seq_start(steps, loops=1)
    assert s1._seq_on is True
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    # Other tab's sequence must not block starting one here.
    assert w._io_task_busy(exclude=("sequence", "modbus")) is False
    w._seq_start(steps, loops=1)
    assert s2._seq_on is True
    assert s1._seq_on is True
    assert w.switch_session(s1.id) is True
    assert w._seq_on is True  # proxy → s1
    w._seq_abort("seq_stopped")
    assert s1._seq_on is False
    assert s2._seq_on is True
    assert w.switch_session(s2.id) is True
    w._seq_abort("seq_stopped")
    assert s2._seq_on is False
    w._close_all_sessions()


def test_script_send_keeps_bound_owner_after_switch(monkeypatch, tmp_path):
    """Queued script TX must use the session that started the worker."""
    import threading

    w = _window(monkeypatch, tmp_path, "script-owner-tx")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    seen = []

    class _Worker:
        @staticmethod
        def stopping():
            return False

    worker = _Worker()
    w._script_worker = worker
    w._script_quiet_until = 0.0
    w._io_bind_owner("script", s1)
    monkeypatch.setattr(
        w, "_send_text",
        lambda *_a, **_k: seen.append(w._session_ctx().id) or True)

    assert w.switch_session(s2.id)
    done = threading.Event()
    result = {"ok": False}
    w._script_send(worker, b"PING", done, result)

    assert done.is_set() and result["ok"] is True
    assert seen == [s1.id]
    w._script_worker = None
    w._io_clear_owner("script")
    w._close_all_sessions()


def test_transfer_and_replay_tx_keep_bound_owner_after_switch(
        monkeypatch, tmp_path):
    """Transfer/replay callbacks must not resolve ``self.conn`` from the new tab."""
    w = _window(monkeypatch, tmp_path, "xfer-replay-owner-tx")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)

    class _Conn:
        is_open = True

        def __init__(self):
            self.sent = []

        def send(self, data, target=None):
            self.sent.append((bytes(data), target))
            return len(data)

        def blockSignals(self, *_args):
            pass

        def close(self):
            self.is_open = False

        def deleteLater(self):
            pass

    c1, c2 = _Conn(), _Conn()
    s1.conn, s2.conn = c1, c2
    replay_send = w._replay_send_target()
    assert replay_send is not None
    monkeypatch.setattr(w, "_record_stream_tx", lambda *_a, **_k: None)
    assert w.switch_session(s2.id)

    w._io_bind_owner("transfer", s1)
    s1._xfer_target = None
    w._xfer_send(b"X")
    w._io_clear_owner("transfer")
    s1._replay_on = True
    w._io_bind_owner("replay", s1)
    assert replay_send(b"R") == 1

    assert c1.sent == [(b"X", None), (b"R", None)]
    assert c2.sent == []
    s1._replay_on = False
    w._io_clear_owner("replay")
    s1.conn = s2.conn = None
    w._close_all_sessions()


def test_stale_transfer_callback_cannot_use_new_owner(
        monkeypatch, tmp_path):
    """A queued signal from the detached worker must not follow a new owner."""
    w = _window(monkeypatch, tmp_path, "xfer-stale-owner")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)

    class _Conn:
        is_open = True

        def __init__(self):
            self.sent = []

        def send(self, data, target=None):
            self.sent.append(bytes(data))
            return len(data)

    old_worker, new_worker = object(), object()
    s1.conn, s2.conn = _Conn(), _Conn()
    monkeypatch.setattr(w, "_record_stream_tx", lambda *_a, **_k: None)
    s1._xfer_worker = None
    s2._xfer_worker = new_worker
    s2._xfer_conn = s2.conn

    w._xfer_send_for(old_worker, s1.id, b"STALE")
    w._xfer_send_for(new_worker, s2.id, b"NEW")

    assert s1.conn.sent == []
    assert s2.conn.sent == [b"NEW"]
    s1._xfer_worker = None
    s2._xfer_worker = None
    s1.conn = s2.conn = None
    w._close_all_sessions()


def test_cancelled_transfer_cannot_cross_into_reconnected_link(
        monkeypatch, tmp_path):
    """Cancelled transfer cannot TX/RX or suppress engines on a new conn."""
    from PyQt5.QtCore import QObject, pyqtSignal

    w = _window(monkeypatch, tmp_path, "xfer-reconnect-race")

    class _Conn:
        is_open = True

        def __init__(self):
            self.sent = []

        def send(self, data, target=None):
            self.sent.append(bytes(data))
            return len(data)

        @staticmethod
        def blockSignals(_on):
            pass

        def close(self):
            self.is_open = False

        @staticmethod
        def deleteLater():
            pass

    class _Worker(QObject):
        sig_send = pyqtSignal(bytes)
        takes_input = True

        @staticmethod
        def isRunning():
            return True

        @staticmethod
        def cancel():
            pass

        def feed(self, _data):
            raise AssertionError("replacement-link RX reached stale transfer")

    old_conn, new_conn = _Conn(), _Conn()
    worker = _Worker()
    w.conn = old_conn
    w._xfer_attach(worker)
    w.conn = new_conn  # models reconnect before queued sig_done is delivered
    before_rx = w.rx_bytes

    worker.sig_send.emit(b"STALE-TX")
    w.on_data_received(b"NEW-RX")

    assert old_conn.sent == []
    assert new_conn.sent == []
    assert w.rx_bytes == before_rx + len(b"NEW-RX")
    monkeypatch.setattr(w, "_mbm_connection_ready", lambda: True)
    monkeypatch.setattr(w, "_is_open", lambda: True)
    w._mbm_on = True
    w.active_session()._mbm_enabled = True
    w._mbm_rules = [{"enabled": True}]
    w._io_bind_owner("modbus", w.active_session())
    assert w._mbm_active()
    w._mbm_on = False
    w.active_session()._mbm_enabled = False
    w._io_clear_owner("modbus")
    w._xfer_detach()
    w.conn = None
    w._close_all_sessions()


def test_stopping_script_cannot_consume_reconnected_link_rx(
        monkeypatch, tmp_path):
    """A still-unwinding script cannot own or suppress a replacement link."""
    w = _window(monkeypatch, tmp_path, "script-reconnect-race")
    session = w.active_session()
    fed = []

    class _Worker:
        @staticmethod
        def isRunning():
            return True

        def feed(self, data):
            fed.append(bytes(data))

    class _Conn:
        is_open = True

        @staticmethod
        def blockSignals(_on):
            pass

        def close(self):
            self.is_open = False

        @staticmethod
        def deleteLater():
            pass

    old_conn, new_conn = _Conn(), _Conn()
    worker = _Worker()
    w._script_worker = worker
    w._script_conn = old_conn
    w._io_bind_owner("script", session)
    w.conn = new_conn
    before_rx = w.rx_bytes

    w.on_data_received(b"NEW-RX")

    assert fed == []
    assert w.rx_bytes == before_rx + len(b"NEW-RX")
    monkeypatch.setattr(w, "_mbm_connection_ready", lambda: True)
    monkeypatch.setattr(w, "_is_open", lambda: True)
    w._mbm_on = True
    session._mbm_enabled = True
    w._mbm_rules = [{"enabled": True}]
    w._io_bind_owner("modbus", session)
    assert w._mbm_active()
    sent = []
    monkeypatch.setattr(w, "_ar_apply_fault", lambda frame: (frame, None))
    monkeypatch.setattr(
        w, "_send_text",
        lambda *args, **_kwargs: sent.append(args[0]) or True)
    w._ar_on = True
    session._ar_enabled = True
    w._ar_schedule_send(["06"], True, 0, [], (0, 0))
    assert sent == ["06"]
    w._mbm_on = False
    w._io_clear_owner("modbus")
    w._script_worker = None
    w._script_conn = None
    w._io_clear_owner("script")
    w.conn = None
    w._close_all_sessions()


def test_transfer_attach_cancels_only_owner_autoreply_and_keeps_other_slots(
        monkeypatch, tmp_path):
    """Transfer takeover invalidates owner AR without altering worker observers."""
    from PyQt5.QtCore import QObject, pyqtSignal

    w = _window(monkeypatch, tmp_path, "xfer-ar-takeover")
    owner = w.active_session()
    other = w.add_session(activate=False)

    class _Worker(QObject):
        sig_send = pyqtSignal(bytes)

        @staticmethod
        def isRunning():
            return True

    worker = _Worker()
    observed = []
    worker.sig_send.connect(lambda data: observed.append(bytes(data)))
    owner_gen = owner._ar_generation
    other_gen = other._ar_generation

    w._xfer_attach(worker)
    worker.sig_send.emit(b"PING")
    w._xfer_detach()
    worker.sig_send.emit(b"AFTER")

    assert owner._ar_generation == owner_gen + 1
    assert other._ar_generation == other_gen
    assert observed == [b"PING", b"AFTER"]
    assert w._xfer_send_bridge is None
    w._close_all_sessions()


def test_dsl_and_mbm_callbacks_keep_bound_owner_after_switch(
        monkeypatch, tmp_path):
    """Window timers for DSL/MBM must re-enter their pinned session."""
    import main_window

    w = _window(monkeypatch, tmp_path, "dsl-mbm-owner-tx")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    seen = []

    w._dsl_ops = None
    s1._dsl_ops = [("send", ("AA", True))]
    s1._dsl_idx = 0
    s1._dsl_gen = 7
    w._io_bind_owner("dsl", s1)
    monkeypatch.setattr(
        w, "_send_with_subst",
        lambda *_a, **_k: seen.append(("dsl", w._session_ctx().id)) or True)
    w._dsl_step(7, s1.id)
    s1._dsl_ops = None
    w._io_clear_owner("dsl")

    w._mbm_on = True
    s1._mbm_enabled = True
    s1._mbm_inflight = None
    w._mbm_rules = [{"enabled": True}]
    s1._mbm_due = {}
    w._io_bind_owner("modbus", s1)
    monkeypatch.setattr(w, "_mbm_active", lambda: True)
    monkeypatch.setattr(main_window, "_mbm_sched_pick_next", lambda *_a: (0, 0.0))
    monkeypatch.setattr(
        w, "_mbm_poll",
        lambda _i: seen.append(("mbm", w._session_ctx().id)))
    w._mbm_tick_for(s1.id)

    assert seen == [("dsl", s1.id), ("mbm", s1.id)]
    assert w.active_session() is s2
    w._mbm_on = False
    s1._mbm_enabled = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_background_owner_disconnect_stops_its_window_tasks(
        monkeypatch, tmp_path):
    """A hidden tab dropping must stop tasks pinned to that connection."""
    w = _window(monkeypatch, tmp_path, "background-owner-drop")
    s1 = w.active_session()
    w.add_session(activate=True)
    stopped = []

    class _Conn:
        is_open = True

        def blockSignals(self, *_args):
            pass

        def close(self):
            self.is_open = False

        def deleteLater(self):
            pass

    class _Worker:
        @staticmethod
        def isRunning():
            return True

        @staticmethod
        def stop():
            stopped.append("script")

    s1.conn = _Conn()
    s1._conn_proto = "Virtual"
    s1._conn_cfg = ("Virtual",)
    s1._conn_engaged = True
    s1._script_worker = _Worker()
    w._io_bind_owner("script", s1)
    s1._macro.start()
    w._io_bind_owner("macro", s1)
    s1._dsl_ops = [("delay", 1000)]
    w._io_bind_owner("dsl", s1)
    monkeypatch.setattr(w, "_schedule_reconnect", lambda: None)

    w._route_session_state(s1.id, False)

    assert stopped == ["script"]
    assert s1._macro.recording is False
    assert s1._dsl_ops is None
    w._script_worker = None
    s1._script_worker = None
    w._io_clear_owner("script")
    w._close_all_sessions()


def test_script_begin_does_not_cancel_other_session_ar_or_mbm(
        monkeypatch, tmp_path):
    """Starting a script on B must leave A's AR/MBM runtime untouched."""
    w = _window(monkeypatch, tmp_path, "script-peer-scope")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    s1._ar_generation = 11
    s2._ar_generation = 22
    info = {"timeout_ms": 500, "variant": "rtu"}
    s1._mbm_enabled = True
    s1._mbm_inflight = info
    w._io_bind_owner("modbus", s1)
    s1._mbm_sched.start(60000)
    s1._mbm_to.start(60000)
    worker = object()

    w._script_begin(worker)

    assert s1._ar_generation == 11
    assert s2._ar_generation == 23
    assert s1._mbm_inflight is info
    assert s1._mbm_sched.isActive()
    assert s1._mbm_to.isActive()
    s2._script_worker = None
    w._io_clear_owner("script")
    s1._mbm_sched.stop()
    s1._mbm_to.stop()
    s1._mbm_inflight = None
    s1._mbm_enabled = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_sequence_dialog_tracks_active_session_only(monkeypatch, tmp_path):
    """Background sequence updates must not lock or overwrite the active tab UI."""
    w = _window(monkeypatch, tmp_path, "seq-dialog-owner")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    s1._seq_on = True
    s1._seq_steps = [{"on": True, "send": "AA"}]
    s1._seq_results = [{"status": "waiting"}]
    w.open_sequence()
    assert w._seq_dlg.btn_run.isEnabled() is False

    assert w.switch_session(s2.id)
    assert w._seq_dlg.btn_run.isEnabled() is True
    assert s1.title in w._seq_dlg.lbl_summary.text()
    with w._with_session(s1):
        w._seq_notify()
    assert w._seq_dlg.btn_run.isEnabled() is True
    assert s1.title in w._seq_dlg.lbl_summary.text()

    s1._seq_on = False
    w._seq_dlg.close()
    w._close_all_sessions()


def test_background_rx_feeds_triggers(monkeypatch, tmp_path):
    """Inactive-tab RX still matches trigger rules (per-session decoder)."""
    import triggers

    w = _window(monkeypatch, tmp_path, "bg-trg")
    _open_virtual(w)
    s1 = w.active_session()
    w.add_session(activate=True)
    _open_virtual(w)
    fired = []
    w._triggers = [triggers.normalize({
        "on": True, "pattern": "ALARM", "mode": "contains",
        "scope": "rx", "beep": False, "notify": False,
    })]
    w._trigger_engine.set_rules(w._triggers)
    monkeypatch.setattr(w, "_fire_trigger", lambda *a, **k: fired.append(True))

    s1.conn.inject(b"ALARM")
    _pump()
    assert fired == [True]
    w._close_all_sessions()


def test_two_sessions_can_each_own_a_script(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "dual-script")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)

    class _Worker:
        pass

    s1._script_worker = _Worker()
    s2._script_worker = _Worker()
    w._io_bind_owner("script", s1)
    w._io_bind_owner("script", s2)
    assert w._script_active(s1) is True
    assert w._script_active(s2) is True
    assert w._io_session_owns("script", s1) is True
    assert w._io_session_owns("script", s2) is True
    assert w._hard_busy_owned_by(s1) is True
    assert w._hard_busy_owned_by(s2) is True
    s1._script_worker = None
    s2._script_worker = None
    w._io_clear_owner("script")
    w._close_all_sessions()


def test_script_end_does_not_clear_other_session_pin(monkeypatch, tmp_path):
    """A 标签脚本结束不能清掉 B 标签仍在跑的脚本 I/O 钉。"""
    from script_console_dialog import ScriptConsoleDialog
    from script_console import ScriptWorker

    w = _window(monkeypatch, tmp_path, "script-end-pin")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    old_a, old_b = ScriptWorker(""), ScriptWorker("")
    s1._script_worker = old_a
    s2._script_worker = old_b
    w._io_bind_owner("script", s1)
    w._io_bind_owner("script", s2)
    dlg = ScriptConsoleDialog(w)
    dlg._worker = old_b
    try:
        dlg._on_finished(old_a, True, "")
        assert s1._script_worker is None
        assert s2._script_worker is old_b
        assert dlg._worker is old_b
        assert w._io_owner_sid["script"] == s2.id
    finally:
        dlg._worker = None
        s1._script_worker = None
        s2._script_worker = None
        w._io_clear_owner("script")
        dlg.deleteLater()
        w._close_all_sessions()


def test_reconnect_attempts_and_serial_target_are_per_session(
        monkeypatch, tmp_path):
    """两个串口同时掉线时，重连次数与目标签名不能互相覆盖。"""
    w = _window(monkeypatch, tmp_path, "reconnect-budget")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    s1.conn_fields = {"auto_reconnect": True}
    s2.conn_fields = {"auto_reconnect": True}

    s1._serial_reconnect_cfg = ("Serial", "COM1", 115200)
    s1._reconnect_attempts = 10
    s2._serial_reconnect_cfg = ("Serial", "COM2", 115200)
    s2._reconnect_attempts = 0
    with w._with_session(s1):
        w._schedule_reconnect()
    assert s1._serial_reconnect_cfg is None
    assert s1._reconnect_attempts == 0
    assert s2._serial_reconnect_cfg == ("Serial", "COM2", 115200)
    assert s2._reconnect_attempts == 0

    s1._serial_reconnect_cfg = None
    s2._serial_reconnect_cfg = None
    s1._reconnect_attempts = 3
    s2._reconnect_attempts = 0
    with w._with_session(s1):
        w._schedule_reconnect()
    assert s1._reconnect_attempts == 4
    assert s2._reconnect_attempts == 0
    s1._reconnect_timer.stop()
    with w._with_session(s2):
        w._schedule_reconnect()
    assert s2._reconnect_attempts == 1
    assert s1._reconnect_attempts == 4
    s2._reconnect_timer.stop()
    w._close_all_sessions()


def test_two_sessions_can_enable_modbus_independently(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "dual-mbm")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    s1._mbm_enabled = True
    s2._mbm_enabled = True
    w._io_bind_owner("modbus", s1)
    w._io_bind_owner("modbus", s2)
    assert w._io_session_owns("modbus", s1) is True
    assert w._io_session_owns("modbus", s2) is True
    s1._mbm_enabled = False
    s2._mbm_enabled = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_script_console_close_ends_background_owner(monkeypatch, tmp_path):
    """Closing the console must _script_end even if the owner tab is not visible."""
    from script_console_dialog import ScriptConsoleDialog

    w = _window(monkeypatch, tmp_path, "sc-close-bg")
    owner = w.active_session()
    w.add_session(activate=True)

    class _Worker:
        @staticmethod
        def isRunning():
            return False

        @staticmethod
        def stop():
            return None

        @staticmethod
        def wait(_ms=0):
            return True

    worker = _Worker()
    owner._script_worker = worker
    w._io_bind_owner("script", owner)
    dlg = ScriptConsoleDialog(w)
    dlg._worker = worker
    dlg.close()
    assert owner._script_worker is None
    assert w._hard_busy_owned_by(owner) is False
    dlg.deleteLater()
    w._close_all_sessions()


def test_script_console_running_follows_visible_tab(monkeypatch, tmp_path):
    from script_console_dialog import ScriptConsoleDialog

    w = _window(monkeypatch, tmp_path, "sc-follow-tab")
    owner = w.active_session()
    dlg = ScriptConsoleDialog(w)

    class _Worker:
        @staticmethod
        def isRunning():
            return True

    worker = _Worker()
    owner._script_worker = worker
    dlg._worker = worker
    w.add_session(activate=True)
    assert dlg.is_running() is False
    assert w.switch_session(owner.id)
    assert dlg.is_running() is True
    owner._script_worker = None
    dlg._worker = None
    dlg.deleteLater()
    w._close_all_sessions()


def test_mbm_dialog_reloads_results_on_session_switch(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "mbm-dlg-switch")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    s1._mbm_enabled = True
    s1._mbm_results = {0: {"status": "ok", "text": "from-s1"}}
    s2._mbm_results = {0: {"status": "ok", "text": "from-s2"}}

    class _CB:
        def __init__(self):
            self.checked = None

        def blockSignals(self, *_a):
            return None

        def setChecked(self, value):
            self.checked = bool(value)

    class _Dlg:
        def __init__(self):
            self.cb_enable = _CB()
            self.reloads = []

        def reload_rows(self):
            self.reloads.append(dict(getattr(w, "_mbm_results", {}) or {}))

    dlg = _Dlg()
    w._mbm_dlg = dlg
    assert w.switch_session(s2.id)
    assert w._mbm_on is False
    assert dlg.cb_enable.checked is False
    assert dlg.reloads
    assert dlg.reloads[-1].get(0, {}).get("text") == "from-s2"
    w._mbm_dlg = None
    s1._mbm_enabled = False
    w._close_all_sessions()


def test_two_sessions_can_enable_modbus_via_set_enabled(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "mbm-two-masters")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    s1._mbm_enabled = True
    s1._mbm_wanted = True
    notices = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: notices.append(msg))
    w._set_mbm_enabled(True)
    assert s2._mbm_enabled is True
    assert s2._mbm_wanted is True
    assert s1._mbm_enabled is True
    assert notices == []
    s1._mbm_enabled = False
    s1._mbm_wanted = False
    s2._mbm_enabled = False
    s2._mbm_wanted = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_disconnect_clears_mbm_runtime_but_keeps_pin(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "mbm-disc-flag")
    _open_virtual(w)
    s = w.active_session()
    s._mbm_enabled = True
    w._io_bind_owner("modbus", s)
    w.close_conn()
    assert s._mbm_enabled is False
    assert w._hard_busy_owned_by(s) is False
    assert w._io_owner_session("modbus") is s
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_mbm_resume_syncs_on_flag_for_visible_owner(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "mbm-resume-on")
    s = w.active_session()
    s._mbm_enabled = False
    w._mbm_on = False
    w._io_bind_owner("modbus", s)
    w._mbm_resume_after_link_up()
    assert s._mbm_enabled is True
    assert w._mbm_on is True
    s._mbm_enabled = False
    w._mbm_on = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_mbm_resume_does_not_flip_on_flag_for_background_owner(
        monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "mbm-resume-bg")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    s1._mbm_enabled = False
    w._mbm_on = False
    w._io_bind_owner("modbus", s1)
    with w._with_session(s1):
        w._mbm_resume_after_link_up()
    assert s1._mbm_enabled is True
    assert w.active_session() is s2
    assert w._mbm_on is False
    s1._mbm_enabled = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_profile_rollback_restores_mbm_enabled(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "mbm-rollback")
    s = w.active_session()
    sid = s.id
    s._mbm_enabled = True
    snap = w._begin_sessions_runtime_reset()
    assert s._mbm_enabled is False
    w._rollback_sessions_runtime_reset(snap)
    restored = w.find_session(sid)
    assert restored is not None
    assert restored._mbm_enabled is True
    restored._mbm_enabled = False
    w._io_clear_owner("modbus")
    w._close_all_sessions()


def test_background_sequence_does_not_toast(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "seq-bg-toast")
    s1 = w.active_session()
    w.add_session(activate=True)
    toasts = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: toasts.append(msg))
    with w._with_session(s1):
        w._toast_if_active_session("bg-seq")
    w._toast_if_active_session("fg-seq")
    assert toasts == ["fg-seq"]
    w._close_all_sessions()


def test_two_sessions_can_each_own_a_transfer(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "dual-xfer")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)

    class _Worker:
        @staticmethod
        def isRunning():
            return True

    s1._xfer_worker = _Worker()
    s2._xfer_worker = _Worker()
    assert w._xfer_active(s1) is True
    assert w._xfer_active(s2) is True
    assert w._hard_busy_owned_by(s1) is True
    assert w._hard_busy_owned_by(s2) is True
    s1._xfer_worker = None
    s2._xfer_worker = None
    w._close_all_sessions()


def test_two_sessions_can_replay_independently(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "dual-replay")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    s1._replay_on = True
    s2._replay_on = True
    assert w._io_session_owns("replay", s1) is True
    assert w._io_session_owns("replay", s2) is True
    assert w._hard_busy_owned_by(s1) is True
    assert w._hard_busy_owned_by(s2) is True
    s1._replay_on = False
    s2._replay_on = False
    w._close_all_sessions()


def test_autoreply_switch_is_per_session(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "ar-per-tab")
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    w._set_autoreply_enabled(True)
    assert s1._ar_enabled is True
    assert s2._ar_enabled is False
    assert w._session_ar_on(s1) is True
    assert w._session_ar_on(s2) is False
    w._set_autoreply_enabled(False)
    w._close_all_sessions()


def test_two_sessions_can_scan_without_hijacking_mbm_rules(monkeypatch, tmp_path):
    w = _window(monkeypatch, tmp_path, "dual-scan")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    _open_virtual(w)
    old_rules = w._mbm_rules
    monkeypatch.setattr(w, "_mbm_connection_ready", lambda: True)
    monkeypatch.setattr(w, "_mbm_restart", lambda: None)
    rules_a = [{"enabled": True, "unit": 1, "func": 3, "addr": 0, "qty": 1,
                "period": 0x7FFFFFFF}]
    rules_b = [{"enabled": True, "unit": 2, "func": 3, "addr": 0, "qty": 1,
                "period": 0x7FFFFFFF}]
    with w._with_session(s1):
        assert w._start_device_scan(rules_a, 200, lambda *_a: None, lambda *_a: None)
    assert w._mbm_rules is old_rules
    with w._with_session(s2):
        assert w._start_device_scan(rules_b, 200, lambda *_a: None, lambda *_a: None)
    assert s1._device_scan_state is not None
    assert s2._device_scan_state is not None
    assert w._mbm_rules is old_rules
    with w._with_session(s1):
        w._stop_device_scan(cancelled=True)
    with w._with_session(s2):
        w._stop_device_scan(cancelled=True)
    w._close_all_sessions()


def test_device_scan_dialog_keeps_per_session_results(monkeypatch, tmp_path):
    """A 扫描中切到 B 再扫：A 的回调不能写进 B 的表格。"""
    from device_center_dialog import DeviceCenterDialog

    w = _window(monkeypatch, tmp_path, "scan-ui-iso")
    s1 = w.active_session()
    dlg = DeviceCenterDialog(w)
    w._device_center_dlg = dlg
    s1._scan_capture = {
        "rows": [{"name": "R1", "unit": 1, "func": 3, "addr": 1}],
        "ok": [],
        "completed": set(),
        "cells": [("waiting", "")],
        "mode": "register",
        "cancelled": False,
        "running": True,
    }
    s2 = w.add_session(activate=True)
    s2._scan_capture = {
        "rows": [{"name": "R9", "unit": 2, "func": 3, "addr": 9}],
        "ok": [],
        "completed": set(),
        "cells": [("waiting", "")],
        "mode": "register",
        "cancelled": False,
        "running": True,
    }
    dlg.sync_session()
    assert dlg._scan_rows[0]["addr"] == 9
    with w._with_session(s1):
        dlg._scan_update(0, "ok", "FROM-A")
    assert s1._scan_capture["cells"][0] == ("ok", "FROM-A")
    assert s1._scan_capture["ok"] == [0]
    assert dlg.scan_table.item(0, 3).text() != "FROM-A"
    assert dlg._scan_rows[0]["addr"] == 9
    w.switch_session(s1.id)
    assert dlg._scan_rows[0]["addr"] == 1
    assert dlg.scan_table.item(0, 3).text() == "FROM-A"
    w._device_center_dlg = None
    dlg.deleteLater()
    w._close_all_sessions()


def test_recording_capture_is_per_session(monkeypatch, tmp_path):
    """A、B 分别录制停止后，切回 A 仍保存/回放 A 的事件。"""
    from rec_replay_dialog import RecReplayDialog

    w = _window(monkeypatch, tmp_path, "rr-capture-iso")
    dlg = RecReplayDialog(w)
    w._rr_dlg = dlg
    s1 = w.active_session()
    s1._recorder.clear()
    s1._recorder.start()
    s1._recorder.on_rx(b"FROM-A", t=1.0)
    dlg.stop_recording()
    assert dlg._events and dlg._events[0][2] == b"FROM-A"

    s2 = w.add_session(activate=True)
    dlg.sync_session()
    assert dlg._events == []
    s2._recorder.clear()
    s2._recorder.start()
    s2._recorder.on_rx(b"FROM-B", t=1.0)
    dlg.stop_recording()
    assert dlg._events[0][2] == b"FROM-B"

    w.switch_session(s1.id)
    assert dlg._events[0][2] == b"FROM-A"
    w._rr_dlg = None
    dlg.deleteLater()
    w._close_all_sessions()


def test_script_console_logs_are_isolated_per_session(monkeypatch, tmp_path):
    from script_console_dialog import ScriptConsoleDialog

    w = _window(monkeypatch, tmp_path, "sc-log-iso")
    s1 = w.active_session()
    s2 = w.add_session(activate=True)
    dlg = ScriptConsoleDialog(w)
    dlg._append_out("from-s1", sid=s1.id)
    dlg._append_out("from-s2", sid=s2.id)
    assert "from-s1" in (s1._script_log or [])
    assert "from-s2" in (s2._script_log or [])
    assert "from-s1" not in (s2._script_log or [])
    dlg.show_session_log()
    text = dlg.txt_out.toPlainText()
    assert "from-s2" in text
    assert "from-s1" not in text
    dlg.deleteLater()
    w._close_all_sessions()
