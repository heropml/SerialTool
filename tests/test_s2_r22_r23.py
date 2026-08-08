# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R22/R23 (config_io + send_history FIFO)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config_io as cio
import send_history as hist


def test_trigger_gate_helpers_identity_and_strip():
    assert cio.parse_json_list("") is None
    rules = [
        {"name": "a", "run_cmd": "calc.exe", "run_cmd_on": True},
        {"name": "b", "webhook_url": "http://h", "webhook": True},
        {"name": "c", "beep": True},
    ]
    assert cio.trigger_external_count(rules) == 2
    stripped = cio.strip_trigger_externals(rules)
    assert rules[0]["run_cmd"] == "calc.exe"  # input not mutated
    assert all("run_cmd" not in r and "webhook_url" not in r for r in stripped)
    assert stripped[0].get("run_cmd_on") is None
    assert stripped[2]["beep"] is True


def test_script_gates_and_coerce_export():
    items = [{"name": "x", "code": "log(1)"}, {"name": "y", "code": "  "}]
    assert cio.script_lib_code_count(items) == 1
    data = {"script_lib": "x", "script_active": 1, "theme": "dark"}
    dropped = cio.drop_script_lib(data)
    assert "script_lib" not in dropped and dropped["theme"] == "dark"
    assert data["script_lib"] == "x"

    rules = [{"match": "AA", "script": "return b''"}, {"match": "BB"}]
    assert cio.ar_script_count(rules) == 1
    assert all(not r.get("script") for r in cio.strip_ar_scripts(rules))

    settings = cio.collect_export_settings(
        lambda k: {"a": False, "b": 0, "c": "", "d": None}[k],
        keys=("a", "b", "c", "d"),
    )
    assert settings == {"a": False, "b": 0, "c": ""}
    payload = cio.build_export_payload(settings, app="CommTool", version="1.4.0")
    assert payload["_app"] == "CommTool" and payload["settings"]["a"] is False

    assert cio.coerce_setting_value({"x": 1}) == json.dumps({"x": 1}, ensure_ascii=False)
    assert cio.coerce_imported_settings(
        {"theme": "dark", "bogus": 1, "snippets": [{"a": 1}]},
        keys=("theme", "snippets"),
    ) == {"theme": "dark", "snippets": json.dumps([{"a": 1}], ensure_ascii=False)}


def test_send_history_fifo():
    assert hist.load_list("") is None
    assert hist.load_list("{") is None
    assert hist.load_list('["a","b"]') == ["a", "b"]
    h, ch = hist.push([], "hi\r\n")
    assert h == ["hi"] and ch
    h2, ch2 = hist.push(h, "hi")
    assert h2 == ["hi"] and not ch2
    big = list(range(hist.HIST_CAP + 5))
    assert len(hist.sanitize_list(big)) == hist.HIST_CAP
    assert hist.dumps(["a"]) == '["a"]'


def test_send_history_remove_at_and_nav():
    h, ok = hist.remove_at(["a", "b", "c"], 1)
    assert ok and h == ["a", "c"]
    assert hist.remove_at(["a"], 9)[1] is False
    assert hist.remove_at(["a"], "x")[1] is False
    assert hist.nav_idx_after_remove(-1, 0) == -1
    assert hist.nav_idx_after_remove(2, 0) == 1
    assert hist.nav_idx_after_remove(0, 0) == -1
    assert hist.nav_idx_after_remove(1, 2) == 1
