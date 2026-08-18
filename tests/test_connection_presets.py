# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project import connection_presets as cp
from project.project_model import collect_project_resources, merge_project_resources


def _dispose_window(app, window):
    """Stop producers, drain queued callbacks while alive, then delete."""
    from PyQt5.QtCore import QCoreApplication, QEvent

    window._shutdown()
    app.processEvents()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_normalize_defaults_and_bool_parsing():
    p = cp.normalize({"name": "A", "auto_reconnect": "false", "serial_dtr": "0"})
    assert p["name"] == "A"
    assert p["auto_reconnect"] is False
    assert p["serial_dtr"] is False
    assert p["ser_baud"] == "115200"
    assert p["id"]


def test_sanitize_caps_and_drops_junk():
    items = [{"name": "a"}, "x", 1, {"name": "b", "net_proto": "TCP Client"}]
    got = cp.sanitize_list(items)
    assert len(got) == 2
    assert got[1]["net_proto"] == "TCP Client"
    assert len(cp.sanitize_list([{"name": str(i)} for i in range(999)])) == cp.MAX_PRESETS
    assert cp.sanitize_list("nope") == []


def test_upsert_duplicate_delete_touch():
    items = []
    p = cp.make_preset("DevA", {"net_proto": "Serial", "ser_port": "COM3", "ser_baud": "9600"})
    items, _ = cp.upsert(items, p)
    assert len(items) == 1
    items, clone = cp.duplicate(items, p["id"])
    assert clone is not None
    assert clone["id"] != p["id"]
    assert "copy" in clone["name"].lower() or "\u526f\u672c" in clone["name"] or clone["name"] != p["name"]
    items, touched = cp.touch_last_used(items, clone["id"], when=123.0)
    assert items[0]["id"] == clone["id"]
    assert items[0]["last_used"] == 123.0
    items, removed = cp.delete_by_id(items, clone["id"])
    assert removed["id"] == clone["id"]
    assert len(items) == 1


def test_summary_and_json_roundtrip():
    p = cp.make_preset("Board", {
        "net_proto": "TCP Client",
        "net_remote_ip": "192.168.1.10",
        "net_remote_port": "502",
    })
    assert "TCP Client" in cp.summary(p)
    assert "192.168.1.10" in cp.summary(p)
    j = cp.to_json([p])
    assert "commtool-connection-presets" in j
    back = cp.from_json(j)
    assert back[0]["name"] == "Board"
    ble = cp.make_preset("GEE", {
        "net_proto": "BLE",
        "ble_address": "69:1E:38:38:39:0D",
        "ble_name": "GEE701",
        "ble_profile": "fff0",
        "ble_write_uuid": "FFF2",
        "ble_notify_uuid": "FFF1",
    })
    assert "BLE" in cp.summary(ble)
    assert "GEE701" in cp.summary(ble)
    assert ble["ble_address"] == "69:1E:38:38:39:0D"
    assert ble["ble_write_mode"] == "auto"
    forced = cp.normalize({"ble_write_mode": "wwr"})
    assert forced["ble_write_mode"] == "wwr"
    assert cp.from_json('[{"name":"x"}]')[0]["name"] == "x"
    assert cp.from_json('{"items":[{"name":"y"}]}')[0]["name"] == "y"


def test_project_resources_include_connection_presets():
    presets = [cp.make_preset("Lab", {"net_proto": "UDP", "net_local_port": "9000"})]
    settings = {"connection_presets": json.dumps(presets)}
    resources = collect_project_resources(settings)
    assert resources["connection"]["presets"][0]["name"] == "Lab"
    restored = merge_project_resources({}, resources)
    loaded = json.loads(restored["connection_presets"])
    assert loaded[0]["net_local_port"] == "9000"


def test_gui_save_and_apply_preset(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication, QPushButton
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PortScannerThread
    from ui.theme import chrome_for
    # Mirror test_workspace._patch_window_runtime: strip side effects from
    # CommTool construction (tray icon, real settings file, port scanner
    # thread, modal info dialogs) so this window cannot destabilize the
    # later GUI tests that share the QApplication singleton.
    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "cpreset.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    ini = tmp_path / "cpreset.ini"
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    w._connection_presets = []
    name_dlg = w._build_connection_preset_name_dialog()
    assert name_dlg.windowTitle() == w._t("cpreset_save_title")
    assert name_dlg.textValue() == w._t("cpreset_new_name")
    assert name_dlg.findChild(QPushButton, "MsPrimaryBtn").text() == "确定"
    assert name_dlg.findChild(QPushButton, "MsGhostBtn").text() == "取消"
    assert chrome_for(w._theme_id())["accent"] in name_dlg.styleSheet()
    name_dlg.deleteLater()
    w.cb_proto.setCurrentText("TCP Client")
    w.ed_remote_ip.setText("10.0.0.8")
    w.ed_remote_port.setText("502")
    w.settings.setValue("auto_reconnect", False)

    saved = w.save_connection_preset_from_ui(prompt_name=False, name="PLC-A", note="lab")
    assert saved is not None
    assert saved["net_remote_ip"] == "10.0.0.8"
    assert saved["auto_reconnect"] is False
    assert len(w._connection_presets) == 1

    w.ed_remote_ip.setText("1.2.3.4")
    w.ed_remote_port.setText("1")
    session = w.active_session()
    session.conn_fields = {
        "net_proto": "TCP Client",
        "serial_dtr": True,
        "serial_rts": True,
        "auto_reconnect": True,
    }
    w._connection_presets[0].update({
        "serial_dtr": False,
        "serial_rts": False,
        "auto_reconnect": False,
    })
    assert w.apply_connection_preset(saved["id"]) is True
    assert w.ed_remote_ip.text() == "10.0.0.8"
    assert w.ed_remote_port.text() == "502"
    assert session.conn_fields["net_proto"] == "TCP Client"
    assert session.conn_fields["serial_dtr"] is False
    assert session.conn_fields["serial_rts"] is False
    assert session.conn_fields["auto_reconnect"] is False
    assert w._session_auto_reconnect_enabled(w, session) is False
    assert w.settings.value("auto_reconnect", True, type=bool) is False

    class _Fake:
        is_open = True
    w.conn = _Fake()
    assert w.apply_connection_preset(saved["id"]) is False
    w.conn = None
    _dispose_window(app, w)


def test_sanitize_truncates_over_max_and_reports_delta():
    """Import merge must expose actual added count after MAX_PRESETS cap."""
    existing = [cp.make_preset("E%d" % i, {"net_proto": "Serial"}) for i in range(cp.MAX_PRESETS - 2)]
    incoming = [cp.make_preset("N%d" % i, {"net_proto": "UDP"}) for i in range(5)]
    before = len(existing)
    merged = cp.sanitize_list(existing + incoming)
    added = len(merged) - before
    assert len(merged) == cp.MAX_PRESETS
    assert added == 2
    assert added < len(incoming)

def test_apply_empty_ser_port_clears_selection(tmp_path, monkeypatch):
    """Preset with empty ser_port must clear a previously selected COM."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PortScannerThread
    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "ep.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "ep.ini"), QSettings.IniFormat)
    w._last_port_list = [("COM3", "COM3"), ("COM4", "COM4")]
    w._populate_port_combo(w._last_port_list, keep_device="COM3")
    assert w.cb_port.currentData() == "COM3"

    empty = cp.make_preset("NoPort", {"net_proto": "Serial", "ser_port": "", "ser_baud": "9600"})
    w._connection_presets = [empty]
    assert w.apply_connection_preset(empty["id"]) is True
    assert (w.cb_port.currentData() or "") == ""
    w._on_port_scan_complete([("COM3", "COM3"), ("COM4", "COM4"), ("COM5", "COM5")])
    assert (w.cb_port.currentData() or "") == ""

    _dispose_window(app, w)


def test_dialog_keeps_selection_after_apply_mru(tmp_path, monkeypatch):
    """After apply/touch_last_used reorder, dialog _cur must still point at applied preset."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PortScannerThread
    from ui.connection_presets_dialog import ConnectionPresetsDialog
    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "mru.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "mru.ini"), QSettings.IniFormat)
    a = cp.make_preset("A", {"net_proto": "UDP", "net_local_port": "1"}, last_used=1.0)
    b = cp.make_preset("B", {"net_proto": "UDP", "net_local_port": "2"}, last_used=2.0)
    c = cp.make_preset("C", {"net_proto": "UDP", "net_local_port": "3"}, last_used=0.0)
    w._connection_presets = [a, b, c]
    w._cpreset_dlg = ConnectionPresetsDialog(w)
    dlg = w._cpreset_dlg
    dlg._cur = 1
    dlg._reload_list()
    assert dlg._items[dlg._cur]["id"] == b["id"]
    dlg._apply()
    assert w._connection_presets[0]["id"] == b["id"]
    assert dlg._items[dlg._cur]["id"] == b["id"]

    _dispose_window(app, w)


def test_export_default_filename_unprefixed():
    """Save-as default must stay connection_presets.json (not a package-prefixed name)."""
    import inspect
    from ui.connection_presets_dialog import ConnectionPresetsDialog
    src = inspect.getsource(ConnectionPresetsDialog._export)
    assert '"connection_presets.json"' in src
    assert "project.connection_presets.json" not in src
