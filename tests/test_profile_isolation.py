# -*- coding: utf-8 -*-
"""Two live profile windows must keep isolated QSettings and mwlocks."""
from __future__ import print_function

import os
import sys
import time
from pathlib import Path

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

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


def _window(monkeypatch, ini_path, profile):
    _quiet(monkeypatch)
    from main_window import CommTool

    def _path(p=""):
        # Keep both windows under the same temp dir with real profile naming.
        name = "settings.ini" if not p else ("settings-%s.ini" % p)
        return str(Path(ini_path).parent / name)

    monkeypatch.setattr(CommTool, "_settings_file", staticmethod(_path))
    w = CommTool(profile)
    w.settings = QSettings(_path(profile), QSettings.IniFormat)
    w._profile = profile
    return w


def _dispose(*windows):
    for window in windows:
        if window is None:
            continue
        window._shutdown()
        window.deleteLater()
    _APP.processEvents()


def test_two_profiles_keep_isolated_settings(monkeypatch, tmp_path):
    """Two simultaneously alive CommTool instances must not overwrite each other."""
    marker_a = "profile-A-%s" % time.time()
    marker_b = "profile-B-%s" % time.time()

    wa = wb = None
    try:
        wa = _window(monkeypatch, tmp_path / "settings.ini", "")
        wb = _window(monkeypatch, tmp_path / "settings-2.ini", "2")
        assert wa._settings_file("") != wb._settings_file("2")

        wa.txt_send.setPlainText(marker_a)
        wb.txt_send.setPlainText(marker_b)
        assert wa._save_settings()
        assert wb._save_settings()

        # Re-read from disk through fresh QSettings handles.
        sa = QSettings(wa._settings_file(""), QSettings.IniFormat)
        sb = QSettings(wb._settings_file("2"), QSettings.IniFormat)
        assert sa.value("send_text") == marker_a
        assert sb.value("send_text") == marker_b
        assert sa.value("send_text") != sb.value("send_text")

        # Live widgets stay isolated even before reload.
        assert wa.txt_send.toPlainText() == marker_a
        assert wb.txt_send.toPlainText() == marker_b
    finally:
        _dispose(wa, wb)


def test_two_profiles_keep_virtual_runtime_isolated(monkeypatch, tmp_path):
    """TX/RX and connection objects stay inside their owning live window."""
    from virtual_io import PROTO_VIRTUAL

    wa = wb = None
    try:
        wa = _window(monkeypatch, tmp_path / "settings.ini", "")
        wb = _window(monkeypatch, tmp_path / "settings-2.ini", "2")
        for window in (wa, wb):
            window.cb_proto.setCurrentText(PROTO_VIRTUAL)
            window._update_net_fields()
            window.sw_vconn_loop.setChecked(True, animate=False)
            window.open_conn()
            assert window.conn is not None and window.conn.is_open
        assert wa.conn is not wb.conn

        wa.txt_send.setPlainText("only-A")
        wa.do_send()
        for _ in range(10):
            _APP.processEvents()
        assert wa.tx_bytes > 0 and wa.rx_bytes > 0
        assert wb.tx_bytes == 0 and wb.rx_bytes == 0
        assert "only-A" in wa.txt_recv.toPlainText()
        assert "only-A" not in wb.txt_recv.toPlainText()
    finally:
        _dispose(wa, wb)


def test_profile_mwlock_blocks_second_holder(monkeypatch, tmp_path):
    """Same profile slot cannot be acquired twice while the first lock lives."""
    from main import _acquire_profile
    from main_window import CommTool

    def path_fn(p=""):
        name = "settings.ini" if not p else ("settings-%s.ini" % p)
        return str(tmp_path / name)

    monkeypatch.setattr(CommTool, "_settings_file", staticmethod(path_fn))
    p1, lock1 = _acquire_profile(path_fn, preferred="")
    assert p1 == "" and lock1 is not None
    p2, lock2 = _acquire_profile(path_fn, preferred="")
    assert p2 != ""  # falls through to next free slot
    assert lock2 is not None
    assert CommTool._profile_in_use("") is True
    lock1.unlock()
    lock2.unlock()
    assert CommTool._profile_in_use("") is False


def test_sessions_persist_stay_per_profile(monkeypatch, tmp_path):
    """sessions_v1 written by one profile must not appear in the other."""
    wa = wb = None
    try:
        wa = _window(monkeypatch, tmp_path / "settings.ini", "")
        wb = _window(monkeypatch, tmp_path / "settings-2.ini", "2")
        s2 = wa.add_session(activate=True)
        assert s2 is not None
        assert wa._save_settings()
        assert wb._save_settings()

        sa = QSettings(wa._settings_file(""), QSettings.IniFormat)
        sb = QSettings(wb._settings_file("2"), QSettings.IniFormat)
        raw_a = sa.value("sessions_v1", "")
        raw_b = sb.value("sessions_v1", "")
        assert isinstance(raw_a, str) and "title_index" in raw_a
        # Profile B keeps its own default payload, not A's second tab id.
        assert s2.id not in (raw_b or "")
    finally:
        _dispose(wa, wb)
