# -*- coding: utf-8 -*-
"""Offscreen BLE settings: type visibility, swap, scan dialog, preset round-trip."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QCoreApplication, QEvent, QSettings
from PyQt5.QtWidgets import QApplication

from conn_ui import PROTO_BLE

_APP = QApplication.instance() or QApplication([])
_WINDOWS = []


def _make_window(tmp_path, monkeypatch):
    from main_window import CommTool, PortScannerThread

    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(tmp_path / "ble.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "ble.ini"), QSettings.IniFormat)
    _WINDOWS.append(w)
    return w


def teardown_function(_fn=None):
    for window in reversed(_WINDOWS):
        window._shutdown()
        _APP.processEvents()
        window.deleteLater()
    _WINDOWS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_ble_type_shows_rows_and_swap(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_BLE)
    w._update_net_fields()
    assert w.row_ble_scan.isHidden() is False
    assert w.row_port.isHidden() is True
    assert w.ed_ble_write.text().upper().endswith("FFF2") or w.ed_ble_write.text().upper() == "FFF2"
    wr, ntf = w.ed_ble_write.text(), w.ed_ble_notify.text()
    w._on_ble_swap_clicked()
    assert w.ed_ble_write.text() == ntf
    assert w.ed_ble_notify.text() == wr


def test_ble_scan_dialog_select_and_preset_roundtrip(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_BLE)
    w._update_net_fields()
    assert not hasattr(w, "tbl_ble")
    dlg = w._ble_scan_dialog()
    dlg.upsert("69:1E:38:38:39:0D", "GEE7016691F98FE", -51)
    dlg.upsert("69:1E:38:38:39:0D", "GEE7016691F98FE", -40)
    assert dlg.table.rowCount() == 1
    assert dlg.table.item(0, 2).text() == "-40"
    dlg.table.selectRow(0)
    dlg._use_selected()
    assert w.ed_ble_address.text() == "69:1E:38:38:39:0D"
    assert "GEE701" in w.ed_ble_name.text()
    fields = w._capture_connection_fields()
    assert fields["net_proto"] == PROTO_BLE
    assert fields["ble_address"] == "69:1E:38:38:39:0D"
    w.ed_ble_address.setText("")
    w.ed_ble_name.setText("")
    w._apply_connection_fields(fields)
    assert w.ed_ble_address.text() == "69:1E:38:38:39:0D"
    assert w.cb_proto.currentText() == PROTO_BLE
    key = w._session_resource_key_from_open(PROTO_BLE, {
        "address": "69:1E:38:38:39:0D"})
    assert key == ("ble", "69:1E:38:38:39:0D")
