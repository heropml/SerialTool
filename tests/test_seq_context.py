# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import seq_context as sc


def _destroy_win(w, app):
    """Stop timers + deleteLater so a freshly-built CommTool does not
    destabilize later GUI tests sharing the QApplication singleton
    (Qt C++ access violation during processEvents -- see test_script._win
    note about not leaving extra CommTool instances alive)."""
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


def test_expand_basic_and_escape():
    assert sc.expand("AT+ID=${id}", {"id": "42"}) == "AT+ID=42"
    assert sc.expand("pre${missing}post", {}) == "prepost"
    assert sc.expand("price $${id}=${id}", {"id": "7"}) == "price ${id}=7"


def test_extract_text_hex_regex_modbus():
    buf = b"SN:ABC123\x00\x10"
    text = "SN:ABC123"
    got = sc.extract(buf, [
        {"as": "sn", "kind": "regex", "pattern": r"SN:(\w+)", "group": 1},
        {"as": "raw", "kind": "hex", "offset": 0, "length": 2},
        {"as": "hi", "kind": "text", "pattern": "SN"},
        {"as": "u", "kind": "modbus", "type": "u16be", "offset": len(b"SN:ABC123")},
    ], text=text)
    assert got["sn"] == "ABC123"
    assert got["raw"] == "534e"
    assert got["hi"] == "SN"
    assert got["u"] == "16"


def test_parse_dsl_and_round_isolation():
    specs = sc.parse_extract_dsl(r"sn=regex:SN:(\w+):1; raw=hex:0:2")
    assert specs[0]["kind"] == "regex"
    assert specs[1]["length"] == 2
    ctx = sc.RoundContext({"seed": "1"})
    ctx.update({"sn": "A"})
    assert ctx.as_dict()["seed"] == "1"
    assert ctx.as_dict()["sn"] == "A"
    ctx.reset({"seed": "2"})
    assert "sn" not in ctx.as_dict()
    assert ctx.as_dict()["seed"] == "2"


def test_sequence_var_pass_through(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings, QTimer
    from main_window import CommTool, PROTO_VIRTUAL, PortScannerThread
    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "s.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    w.sw_vconn_loop.setChecked(True, animate=False)
    w.open_conn()
    assert w._is_open()

    steps = [
        {"on": True, "name": "read", "send": "PING", "send_hex": False, "cs": 0,
         "expect": "SN:", "expect_hex": False, "mode": 0, "timeout": 2000,
         "on_timeout": "stop", "delay": 0, "retry": 0,
         "extract_dsl": r"sn=regex:SN:(\w+):1"},
        {"on": True, "name": "use", "send": "USE ${sn}", "send_hex": False, "cs": 0,
         "expect": "", "expect_hex": False, "mode": 0, "timeout": 1000,
         "on_timeout": "stop", "delay": 0, "retry": 0},
    ]
    sent = []
    real_send = w._send_text

    def wrap_send(text, **kwargs):
        sent.append(text)
        ok = real_send(text, **kwargs)
        if text == "PING":
            QTimer.singleShot(0, lambda: w._seq_feed(b"SN:XYZ99\r\n"))
        return ok

    w._send_text = wrap_send
    w._seq_start(steps, loops=1, stop_on_fail=True)

    for _ in range(50):
        app.processEvents()
        if not w._seq_on:
            break
        QTimer.singleShot(10, lambda: None)
        app.processEvents()

    assert any(s.startswith("USE XYZ99") for s in sent), sent
    assert w._seq_summary is not None
    w.close_conn()
    _destroy_win(w, app)


def test_extracted_survives_set_result(tmp_path, monkeypatch):
    """Pass path must keep extracted on the result dict after _seq_set_result."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings, QTimer
    from main_window import CommTool, PROTO_VIRTUAL, PortScannerThread
    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "e.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "e.ini"), QSettings.IniFormat)
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    w.sw_vconn_loop.setChecked(True, animate=False)
    w.open_conn()
    assert w._is_open()

    steps = [{
        "on": True, "name": "cap", "send": "PING", "send_hex": False, "cs": 0,
        "expect": "SN:", "expect_hex": False, "mode": 0, "timeout": 2000,
        "on_timeout": "stop", "delay": 0, "retry": 0,
        "extract": [{"as": "sn", "kind": "regex", "pattern": r"SN:(\w+)", "group": 1}],
    }]
    real_send = w._send_text

    def wrap_send(text, **kwargs):
        ok = real_send(text, **kwargs)
        if text == "PING":
            QTimer.singleShot(0, lambda: w._seq_feed(b"SN:KEEP1\r\n"))
        return ok

    w._send_text = wrap_send
    w._seq_start(steps, loops=1, stop_on_fail=True)
    for _ in range(50):
        app.processEvents()
        if not w._seq_on:
            break
    assert w._seq_results and w._seq_results[0].get("status") == "pass"
    assert w._seq_results[0].get("extracted", {}).get("sn") == "KEEP1"
    w.close_conn()
    _destroy_win(w, app)


def test_missing_vars_and_escape():
    assert sc.referenced_vars("A=${a} B=${b} $${c}") == ["a", "b"]
    assert sc.missing_vars("X=${sn}", {}) == ["sn"]
    assert sc.missing_vars("X=${sn}", {"sn": "1"}) == []
    assert sc.missing_vars("$${sn}", {}) == []


def test_missing_expect_var_fails_not_silent_sent(tmp_path, monkeypatch):
    """expect with undefined ${var} must fail; must not downgrade to pure-send."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool, PROTO_VIRTUAL, PortScannerThread
    monkeypatch.setattr(CommTool, "_settings_file",
                        staticmethod(lambda profile="": str(tmp_path / "mv.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg",
                        lambda self, title, body, is_error=False: None)

    app = QApplication.instance() or QApplication([])
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "mv.ini"), QSettings.IniFormat)
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    w.sw_vconn_loop.setChecked(True, animate=False)
    w.open_conn()
    assert w._is_open()

    steps = [{
        "on": True, "name": "bad", "send": "PING", "send_hex": False, "cs": 0,
        "expect": "ID=${sn}", "expect_hex": False, "mode": 0, "timeout": 500,
        "on_timeout": "stop", "delay": 0, "retry": 0,
    }]
    w._seq_start(steps, loops=1, stop_on_fail=True)
    for _ in range(30):
        app.processEvents()
        if not w._seq_on:
            break
    assert w._seq_results
    assert w._seq_results[0].get("status") == "fail"
    assert w._seq_results[0].get("detail_key") == "seq_st_var_missing"
    w.close_conn()
    _destroy_win(w, app)

def test_regex_named_group_dsl_roundtrip():
    """Named capture groups must survive extractors_to_dsl <-> parse_extract_dsl."""
    pat = r"SN:(?P<id>\w+)"
    specs = sc.sanitize_extractors([
        {"as": "sn", "kind": "regex", "pattern": pat, "group": "id"},
    ])
    assert specs[0]["group"] == "id"
    dsl = sc.extractors_to_dsl(specs)
    back = sc.parse_extract_dsl(dsl)
    assert back[0]["group"] == "id"
    assert back[0]["pattern"] == pat
    parsed = sc.parse_extract_dsl("sn=regex:" + pat + ":group=id")
    assert parsed[0]["group"] == "id"
    assert parsed[0]["pattern"] == pat
    got = sc.extract(b"SN:ABC", parsed, text="SN:ABC")
    assert got.get("sn") == "ABC"


def test_regex_colon_identifier_stays_in_pattern():
    pat = r"^(foo):bar$"
    parsed = sc.parse_extract_dsl("value=regex:" + pat)
    assert parsed[0]["group"] == 1
    assert parsed[0]["pattern"] == pat
    assert sc.extract(b"foo:bar", parsed, text="foo:bar").get("value") == "foo"
