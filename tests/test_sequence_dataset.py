# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sequence_dataset as sd
import seq_context as sc


def test_load_and_seed(tmp_path):
    p = tmp_path / "devs.csv"
    p.write_text("device_id,payload\nA01,PING\n , \nB02,PONG\n", encoding="utf-8-sig")
    ds = sd.load_dataset(str(p))
    assert ds["headers"] == ["device_id", "payload"]
    assert len(ds["rows"]) == 2
    assert ds["skipped_empty"] == 1
    assert ds["rows"][0]["number"] == 2
    assert ds["rows"][0]["seeds"]["device_id"] == "A01"
    assert ds["rows"][0]["label"] == "A01"
    assert ds["rows"][1]["number"] == 4
    ctx = sc.RoundContext(ds["rows"][0]["seeds"])
    assert sc.expand("ID=${device_id} ${payload}", ctx.as_dict()) == "ID=A01 PING"


def test_bad_header_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("device-id,x\n1,2\n", encoding="utf-8-sig")
    try:
        sd.load_dataset(str(p))
        assert False
    except sd.DatasetError as e:
        assert e.code == "seq_csv_bad_header"


def test_no_rows(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("device_id,payload\n\n\n", encoding="utf-8-sig")
    try:
        sd.load_dataset(str(p))
        assert False
    except sd.DatasetError as e:
        assert e.code == "seq_csv_no_rows"


def test_csv_driven_sequence_rounds(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PROTO_VIRTUAL, PortScannerThread

    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "csvseq.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    csv_path = tmp_path / "batch.csv"
    csv_path.write_text("device_id,cmd\nD1,AA\nD2,BB\n", encoding="utf-8-sig")
    ds = sd.load_dataset(str(csv_path))

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "csvseq.ini"), QSettings.IniFormat)
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    w.sw_vconn_loop.setChecked(True, animate=False)
    w.open_conn()
    assert w._is_open()

    steps = [{
        "on": True, "name": "ping", "send": "HELLO ${device_id}:${cmd}", "send_hex": False, "cs": 0,
        "expect": "", "expect_hex": False, "mode": 0, "timeout": 200,
        "on_timeout": "stop", "delay": 0, "retry": 0,
    }]
    sent = []

    def capture(text, **kwargs):
        sent.append(text)
        return True

    monkeypatch.setattr(w, "_send_text", capture)
    w._seq_start(steps, loops=1, stop_on_fail=False, dataset=ds)
    for _ in range(80):
        app.processEvents()
        if not w._seq_on:
            break
    assert sent == ["HELLO D1:AA", "HELLO D2:BB"]
    assert w._seq_summary and w._seq_summary.get("csv_rows") == 2
    assert len(w._seq_rounds) == 2
    assert w._seq_rounds[0].get("csv_label") == "D1"
    assert w._seq_rounds[1].get("csv_row") == 3

    w.close_conn()
    try:
        for _attr in ("send_timer", "_reconnect_timer", "_ms_cycle_timer",
                      "_seq_timer", "_kw_timer", "_ctrl_poll_timer", "_reset_timer"):
            _t = getattr(w, _attr, None)
            if _t is not None:
                _t.stop()
        if getattr(w, "port_scanner", None) is not None:
            w.port_scanner.stop()
    except Exception:
        pass
    w.deleteLater()
    for _ in range(3):
        app.processEvents()


def test_stale_csv_path_cleared_on_dialog_init(tmp_path, monkeypatch):
    """Missing persisted CSV keeps path, enables Clear, and Clear unbinds."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PortScannerThread
    from dialogs import SequenceDialog

    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "stale.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    ini = tmp_path / "stale.ini"
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    missing = str(tmp_path / "gone.csv")
    w.settings.setValue("sequence_csv_path", missing)
    w.settings.sync()

    dlg = SequenceDialog(w)
    assert dlg._csv_path == missing
    assert dlg._csv_dataset is None
    assert (w.settings.value("sequence_csv_path", "") or "") == missing
    assert dlg.btn_csv_clear.isEnabled() is True
    dlg._on_clear_csv()
    assert dlg._csv_path == ""
    assert (w.settings.value("sequence_csv_path", "") or "") == ""
    assert dlg.btn_csv_clear.isEnabled() is False

    dlg.close()
    dlg.deleteLater()
    try:
        for _attr in ("send_timer", "_reconnect_timer", "_ms_cycle_timer",
                      "_seq_timer", "_kw_timer", "_ctrl_poll_timer", "_reset_timer"):
            _t = getattr(w, _attr, None)
            if _t is not None:
                _t.stop()
        if getattr(w, "port_scanner", None) is not None:
            w.port_scanner.stop()
    except Exception:
        pass
    w.deleteLater()
    for _ in range(3):
        app.processEvents()


def test_single_row_csv_report_includes_row_meta(tmp_path, monkeypatch):
    """1-row CSV must still expose csv_row/label in exported report table."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PROTO_VIRTUAL, PortScannerThread
    from dialogs import SequenceDialog

    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "one.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    csv_path = tmp_path / "one.csv"
    csv_path.write_text("device_id,cmd\nONLY1,ZZ\n", encoding="utf-8-sig")
    ds = sd.load_dataset(str(csv_path))
    assert len(ds["rows"]) == 1

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "one.ini"), QSettings.IniFormat)
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    w.sw_vconn_loop.setChecked(True, animate=False)
    w.open_conn()

    steps = [{
        "on": True, "name": "ping", "send": "${cmd}", "send_hex": False, "cs": 0,
        "expect": "", "expect_hex": False, "mode": 0, "timeout": 200,
        "on_timeout": "stop", "delay": 0, "retry": 0,
    }]
    monkeypatch.setattr(w, "_send_text", lambda text, **kw: True)
    w._seq_start(steps, loops=1, stop_on_fail=False, dataset=ds)
    for _ in range(40):
        app.processEvents()
        if not w._seq_on:
            break
    assert w._seq_summary and w._seq_summary.get("csv_path")
    assert w._seq_summary.get("loops") == 1

    dlg = SequenceDialog(w)
    assert dlg._report_is_csv() is True
    assert dlg._report_is_loop() is True
    header, body = dlg._report_table([])
    assert any("CSV" in str(h) or "Device" in str(h) or "row" in str(h).lower() or "ID" in str(h)
               for h in header)
    assert body and str(body[0]["cells"][1]) == "2"  # file row number
    assert body[0]["cells"][2] == "ONLY1"

    dlg.close(); dlg.deleteLater()
    w.close_conn()
    try:
        for _attr in ("send_timer", "_reconnect_timer", "_ms_cycle_timer",
                      "_seq_timer", "_kw_timer", "_ctrl_poll_timer", "_reset_timer"):
            _t = getattr(w, _attr, None)
            if _t is not None:
                _t.stop()
        if getattr(w, "port_scanner", None) is not None:
            w.port_scanner.stop()
    except Exception:
        pass
    w.deleteLater()
    for _ in range(3):
        app.processEvents()


def test_flush_pending_preserves_manual_loops_when_csv_bound(tmp_path, monkeypatch):
    """Project flush must not overwrite sequence_loops with CSV row count."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PortScannerThread
    from dialogs import SequenceDialog

    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "flush.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    csv_path = tmp_path / "three.csv"
    csv_path.write_text("device_id\nA\nB\nC\n", encoding="utf-8-sig")

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "flush.ini"), QSettings.IniFormat)
    w.settings.setValue("sequence_loops", 7)
    w.settings.sync()

    dlg = SequenceDialog(w)
    assert dlg._loops_cfg == 7
    ds = sd.load_dataset(str(csv_path))
    dlg._csv_path = ds["path"]
    dlg._csv_dataset = ds
    dlg._refresh_csv_ui()
    assert dlg.ed_loops.text() == "3"
    dlg.flush_pending()
    assert int(w.settings.value("sequence_loops", 0)) == 7

    dlg.close(); dlg.deleteLater()
    try:
        for _attr in ("send_timer", "_reconnect_timer", "_ms_cycle_timer",
                      "_seq_timer", "_kw_timer", "_ctrl_poll_timer", "_reset_timer"):
            _t = getattr(w, _attr, None)
            if _t is not None:
                _t.stop()
        if getattr(w, "port_scanner", None) is not None:
            w.port_scanner.stop()
    except Exception:
        pass
    w.deleteLater()
    for _ in range(3):
        app.processEvents()


def test_run_reloads_csv_from_disk(tmp_path, monkeypatch):
    """Bound CSV edited on disk must be re-read on Run (not stale memory)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PROTO_VIRTUAL, PortScannerThread
    from dialogs import SequenceDialog

    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "reload.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    csv_path = tmp_path / "live.csv"
    csv_path.write_text("device_id,cmd\nA,OLD\n", encoding="utf-8-sig")

    steps = [{
        "on": True, "name": "ping", "send": "${cmd}", "send_hex": False, "cs": 0,
        "expect": "", "expect_hex": False, "mode": 0, "timeout": 200,
        "on_timeout": "stop", "delay": 0, "retry": 0,
    }]

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "reload.ini"), QSettings.IniFormat)
    w._seq_rules = steps
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    w.sw_vconn_loop.setChecked(True, animate=False)
    w.open_conn()

    dlg = SequenceDialog(w)
    ds0 = sd.load_dataset(str(csv_path))
    dlg._csv_path = ds0["path"]
    dlg._csv_dataset = ds0
    dlg._refresh_csv_ui()
    assert dlg._csv_dataset["rows"][0]["seeds"]["cmd"] == "OLD"

    # External edit after bind
    csv_path.write_text("device_id,cmd\nA,NEW\nB,ZZ\n", encoding="utf-8-sig")

    sent = []
    monkeypatch.setattr(w, "_send_text", lambda text, **kw: sent.append(text) or True)
    dlg._on_run()
    for _ in range(80):
        app.processEvents()
        if not w._seq_on:
            break
    assert sent == ["NEW", "ZZ"]
    assert len(dlg._csv_dataset["rows"]) == 2

    dlg.close(); dlg.deleteLater()
    w.close_conn()
    try:
        for _attr in ("send_timer", "_reconnect_timer", "_ms_cycle_timer",
                      "_seq_timer", "_kw_timer", "_ctrl_poll_timer", "_reset_timer"):
            _t = getattr(w, _attr, None)
            if _t is not None:
                _t.stop()
        if getattr(w, "port_scanner", None) is not None:
            w.port_scanner.stop()
    except Exception:
        pass
    w.deleteLater()
    for _ in range(3):
        app.processEvents()


def test_load_gbk_csv(tmp_path):
    """Excel-on-CN-Windows style GBK CSV must load via encoding fallback."""
    text = "device_id,name\nA01," + "\u8bbe\u5907" + "\n"
    p = tmp_path / "gbk.csv"
    p.write_bytes(text.encode("gbk"))
    ds = sd.load_dataset(str(p))
    assert ds["encoding"] == "gb18030"
    assert len(ds["rows"]) == 1
    assert ds["rows"][0]["seeds"]["name"] == "\u8bbe\u5907"
    assert ds["rows"][0]["label"] == "A01"


def test_load_utf8_still_preferred(tmp_path):
    p = tmp_path / "u8.csv"
    p.write_text("device_id,name\nA01," + "\u8bbe\u5907" + "\n", encoding="utf-8")
    ds = sd.load_dataset(str(p))
    assert ds["encoding"].startswith("utf-8")
    assert ds["rows"][0]["seeds"]["name"] == "\u8bbe\u5907"
