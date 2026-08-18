# -*- coding: utf-8 -*-
"""Tests for S-1 serial_io._safe and S-5 conn tips / send-history filter."""
import logging
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from transport.serial_io import SerialConn, _safe  # noqa: E402
from transport import conn_error_tips  # noqa: E402
from automation import send_history  # noqa: E402


def test_safe_logs_and_continues():
    calls = []

    def boom():
        calls.append("boom")
        raise RuntimeError("x")

    def ok():
        calls.append("ok")

    with mock.patch("transport.serial_io._log") as log:
        assert _safe(boom) is False
        assert _safe(ok) is True
        assert calls == ["boom", "ok"]
        assert log.debug.called


def test_serial_close_uses_safe_when_close_raises():
    conn = SerialConn("COM9", 115200, 8, "N", 1)
    ser = mock.Mock()
    ser.is_open = True
    ser.close.side_effect = RuntimeError("close failed")
    conn._ser = ser
    conn._reader = None
    with mock.patch("transport.serial_io._log") as log:
        conn.close()
    assert conn._ser is None
    assert log.debug.called
    ser.close.assert_called_once()


def test_classify_conn_error_patterns():
    cases = [
        ("PermissionError(13, 'Access is denied', None, 5)", "err_hint_permission"),
        ("could not open port 'COM3': PermissionError(...)", "err_hint_permission"),
        ("could not open port 'COM99': FileNotFoundError(2, '...')", "err_hint_port_missing"),
        ("The system cannot find the file specified", "err_hint_port_missing"),
        ("Address already in use", "err_hint_addr_in_use"),
        ("Connection refused", "err_hint_refused"),
        ("No route to host", "err_hint_unreachable"),
        ("getaddrinfo failed", "err_hint_host"),
        ("something totally unknown xyz", None),
        ("", None),
    ]
    for msg, expect in cases:
        got = conn_error_tips.classify_conn_error(msg)
        assert got == expect, (msg, got, expect)


def test_format_conn_error_detail_prefers_tip():
    tips = {"err_hint_refused": "TIP: refused"}
    out = conn_error_tips.format_conn_error_detail(
        "Connection refused", lambda k: tips.get(k, k))
    assert out.startswith("TIP: refused")
    assert "Connection refused" in out


def test_format_conn_error_detail_passthrough():
    out = conn_error_tips.format_conn_error_detail(
        "weird failure 42", lambda k: k)
    assert out == "weird failure 42"


def test_filter_hist_case_insensitive_and_indices():
    items = ["AT", "PING 1", "at+ver", "hello"]
    assert send_history.filter_hist(items, "") == list(enumerate(items))
    assert send_history.filter_hist(items, "at") == [(0, "AT"), (2, "at+ver")]
    assert send_history.filter_hist(items, "zzz") == []


def test_preview_hist_truncates():
    s = "a" * 100
    p = send_history.preview_hist(s, max_len=20)
    assert len(p) == 20
    assert p.endswith("\u2026")


def test_classify_disconnected_patterns():
    assert conn_error_tips.classify_conn_error(
        "ClearCommError failed (PermissionError(13, ...))"
    ) == "err_hint_disconnected"
    assert conn_error_tips.classify_conn_error(
        "device disconnected"
    ) == "err_hint_disconnected"
    assert conn_error_tips.classify_conn_error(
        "Connection reset by peer"
    ) == "err_hint_disconnected"
    assert conn_error_tips.classify_conn_error(
        "OSError: [Errno 104] Connection reset by peer"
    ) == "err_hint_disconnected"
    assert conn_error_tips.classify_conn_error(
        "errno 104"
    ) == "err_hint_disconnected"
    assert conn_error_tips.classify_conn_error(
        "[errno 111] Connection refused"
    ) == "err_hint_refused"


def test_rx_side_logs_without_raising():
    from main_window import CommTool  # noqa: WPS433

    calls = []

    def boom():
        calls.append("boom")
        raise RuntimeError("side failed")

    with mock.patch("main_window._log") as log:
        CommTool._rx_side(None, "plot.feed", boom)
    assert calls == ["boom"]
    assert log.warning.called


def test_rx_side_toast_uses_user_facing_label():
    from main_window import CommTool  # noqa: WPS433

    shown = []

    class _Host(object):
        def _t(self, key, **kw):
            table = {
                "ar_title": "自动应答",
                "trg_title": "触发告警",
                "err_rx_side": "接收侧处理失败: {name}",
            }
            text = table[key]
            return text.format(**kw) if kw else text

        def _rx_side_display_name(self, name):
            return CommTool._rx_side_display_name(self, name)

        def toast(self, msg, error=False):
            shown.append((msg, error))

    host = _Host()
    CommTool._toast_rx_side_throttled(host, "automation.triggers.feed")
    assert shown == [("接收侧处理失败: 触发告警", True)]
    CommTool._toast_rx_side_throttled(host, "auto_reply")
    assert shown[-1] == ("接收侧处理失败: 自动应答", True)
    assert all("automation.triggers" not in msg for msg, _err in shown)


def test_seq_waiting_mbm_feed_uses_mbm_channel():
    import inspect
    from main_window import CommTool  # noqa: WPS433

    src = inspect.getsource(CommTool._feed_session_engines)
    assert 'route == "seq_mbm"' in src
    assert 'self._rx_side("mbm.feed", lambda: self._mbm_feed(data))' in src
    assert 'self._rx_side("seq.feed", lambda: self._mbm_feed(data))' not in src
    assert 'self._rx_side("seq.feed", lambda: self._seq_feed(data))' in src
    host = type("H", (), {"_t": lambda self, key, **kw: key})()
    assert CommTool._rx_side_display_name(host, "mbm.feed") == "mbm_title"
    assert CommTool._rx_side_display_name(host, "seq.feed") == "seq_title"


def test_ar_kill_worker_continues_after_conn_close_fails():
    from main_window import CommTool  # noqa: WPS433

    conn = mock.Mock()
    conn.close.side_effect = RuntimeError("pipe closed")
    proc = mock.Mock()
    proc.is_alive.return_value = False
    proc.pid = 4242
    with mock.patch("main_window._log"):
        CommTool._ar_kill_worker(proc, conn, group_ready=False)
    conn.close.assert_called_once()
    proc.join.assert_called()
    proc.close.assert_called_once()
