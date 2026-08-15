# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ble_uuid as bu


def test_normalize_16_32_128():
    assert bu.normalize_uuid("FFF0") == "0000fff0-0000-1000-8000-00805f9b34fb"
    assert bu.normalize_uuid("0xFFF1") == "0000fff1-0000-1000-8000-00805f9b34fb"
    assert bu.normalize_uuid("0000FFF2-0000-1000-8000-00805F9B34FB") == (
        "0000fff2-0000-1000-8000-00805f9b34fb")
    assert bu.normalize_uuid(
        "6E400001B5A3F393E0A9E50E24DCCA9E") == bu.NUS_SERVICE
    assert bu.normalize_uuid("") == ""
    assert bu.normalize_uuid("nope") == ""
    assert bu.normalize_uuid("fff") == ""


def test_compare_and_short():
    assert bu.uuids_equal("fff1", "0000FFF1-0000-1000-8000-00805f9b34fb")
    assert not bu.uuids_equal("fff1", "fff2")
    assert bu.short_uuid("fff0") == "FFF0"
    assert bu.short_uuid(bu.NUS_SERVICE) == bu.NUS_SERVICE


def test_swap_and_presets():
    w, n = bu.swap_write_notify("fff2", "fff1")
    assert (w, n) == ("fff1", "fff2")
    fff0 = bu.apply_preset("fff0")
    assert fff0["profile"] == "fff0"
    assert bu.uuids_equal(fff0["service_uuid"], "fff0")
    assert bu.uuids_equal(fff0["write_uuid"], "fff2")
    assert bu.uuids_equal(fff0["notify_uuid"], "fff1")
    ffe0 = bu.apply_preset("ffe0")
    assert bu.uuids_equal(ffe0["write_uuid"], "ffe1")
    assert bu.uuids_equal(ffe0["notify_uuid"], "ffe1")
    nus = bu.apply_preset("Nordic UART")
    assert nus["profile"] == "nus"
    assert nus["write_uuid"] == bu.NUS_WRITE
    assert nus["notify_uuid"] == bu.NUS_NOTIFY
    custom = bu.apply_preset("custom", {
        "service_uuid": "fff0", "write_uuid": "fff1", "notify_uuid": "fff2"})
    assert custom["profile"] == "custom"
    assert bu.uuids_equal(custom["write_uuid"], "fff1")
    assert bu.match_profile("fff0", "fff2", "fff1") == "fff0"
    assert bu.match_profile("fff0", "fff1", "fff2") == "custom"


def test_address():
    assert bu.normalize_address("69-1e-38-38-39-0d") == "69:1E:38:38:39:0D"
    assert bu.is_valid_address("69:1E:38:38:39:0D")
    assert not bu.is_valid_address("COM3")
    assert not bu.is_valid_address("")
    assert not bu.is_valid_uuid("zz")
    assert bu.is_valid_uuid("FFF0")
    assert bu.is_valid_uuid("", allow_empty=True)
