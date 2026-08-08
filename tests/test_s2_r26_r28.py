# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R26-R28 (restore scalars / JSON dict / field defaults)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config_io as cio


def test_normalize_and_combo_helpers():
    assert cio.normalize_ts_format("relative") == "relative"
    assert cio.normalize_ts_format("nope") == "absolute"
    assert cio.normalize_ts_format(None) == "absolute"
    assert cio.normalize_encoding("") == "auto"
    assert cio.normalize_encoding("gbk") == "gbk"
    assert cio.clamp_combo_index("1", 3, default=0) == 1
    assert cio.clamp_combo_index("9", 3, default=2) == 2
    assert cio.try_combo_index("9", 3) is None
    assert cio.try_combo_index("1", 3) == 1
    assert cio.resolve_view_mutex(True, True) == (True, False)
    assert cio.resolve_view_mutex(False, True) == (False, True)
    assert cio.resolve_combo_text(None, ["a"]) is None
    assert cio.resolve_combo_text("a", ["a", "b"]) == ("index", 0)
    assert cio.resolve_combo_text("z", ["a"], editable=True) == ("edit", "z")
    assert cio.resolve_combo_text("z", ["a"], editable=False) is None


def test_parse_json_dict_and_object_list():
    assert cio.parse_json_dict("") is None
    assert cio.parse_json_dict('{"a": 1}') == {"a": 1}
    assert cio.parse_json_dict([1, 2]) is None
    assert cio.parse_json_dict({"a": 1}) == {"a": 1}
    assert cio.parse_json_object_list('[{"a":1},"x",{"b":2}]') == [{"a": 1}, {"b": 2}]
    assert cio.parse_json_object_list("") is None


def test_capture_field_defaults():
    assert "ed_period_ms" in cio.RESET_LINE_EDITS
    assert "cb_baud" in cio.RESET_COMBOS
    values = {
        "txt_send": "hi",
        "ed_period_ms": "1000",
        "cb_baud": "115200",
        "extra": "ignore",
    }
    got = cio.capture_field_defaults(values)
    assert got == {"txt_send": "hi", "ed_period_ms": "1000", "cb_baud": "115200"}
