# -*- coding: utf-8 -*-
"""B6-3: connect/send/live-log failures stay user-visible and leave a traceback."""
from __future__ import print_function

import logging
import os
import sys
from pathlib import Path

import pytest
from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_APP = QApplication.instance() or QApplication([])
_TEST_WINDOWS = []


@pytest.fixture(autouse=True)
def _dispose_test_windows():
    yield
    for window in reversed(_TEST_WINDOWS):
        window._close_all_sessions()
        window.deleteLater()
    _TEST_WINDOWS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _window(monkeypatch, tmp_path, profile="b6-io"):
    from main_window import CommTool, PortScannerThread
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "_confirm_dlg", lambda *a, **k: True)
    ini = tmp_path / ("%s.ini" % profile)
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool(profile)
    _TEST_WINDOWS.append(w)
    return w


class _BoomConn(object):
    is_open = True

    def send(self, data, target=None):
        raise OSError("broken pipe")

    def blockSignals(self, _on):
        return None

    def close(self):
        return None

    def deleteLater(self):
        return None


def test_send_oserror_toasts_and_logs_traceback(monkeypatch, tmp_path, caplog):
    w = _window(monkeypatch, tmp_path, "b6-send")
    toasts = []
    monkeypatch.setattr(w, "toast", lambda *a, **k: toasts.append((a, k)))
    w.conn = _BoomConn()
    with caplog.at_level(logging.DEBUG, logger="main_window"):
        ok = w._send_text("hi", hex_mode=False, newline=0, checksum=0)
    assert ok is False
    assert toasts
    assert any(kw.get("error") for _a, kw in toasts)
    assert any(
        rec.exc_info and rec.getMessage() == "send failed"
        for rec in caplog.records)


def test_open_log_on_directory_toasts_and_logs_traceback(
        monkeypatch, tmp_path, caplog):
    w = _window(monkeypatch, tmp_path, "b6-log")
    toasts = []
    monkeypatch.setattr(w, "toast", lambda *a, **k: toasts.append((a, k)))
    with caplog.at_level(logging.DEBUG, logger="main_window"):
        ok = w._open_log_segment(str(tmp_path))
    assert ok is False
    assert toasts
    assert any(kw.get("error") for _a, kw in toasts)
    assert any(
        rec.exc_info and "open log segment failed" in rec.getMessage()
        for rec in caplog.records)


def test_log_write_oserror_toasts_and_logs_traceback(
        monkeypatch, tmp_path, caplog):
    w = _window(monkeypatch, tmp_path, "b6-logw")
    if hasattr(w, "sw_show_timestamp"):
        w.sw_show_timestamp.setChecked(False)
    monkeypatch.setattr(w, "_maybe_rotate_log", lambda now=None, session=None: None)
    toasts = []
    monkeypatch.setattr(w, "toast", lambda *a, **k: toasts.append((a, k)))

    class _BoomFile(object):
        def write(self, _s):
            raise OSError("disk full")

        def flush(self):
            return None

        def close(self):
            return None

    session = w.active_session()
    session._log_file = _BoomFile()
    session._log_ends_with_nl = True
    session.log_wanted = True
    with caplog.at_level(logging.DEBUG, logger="main_window"):
        w._write_log_block("X\n", "rx", True)
    assert session._log_file is None
    assert session.log_wanted is False
    assert toasts
    assert any(
        rec.exc_info and "live log write failed" in rec.getMessage()
        for rec in caplog.records)
