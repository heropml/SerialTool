# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from transport import ble_uuid as bu


def test_normalize_16_32_128():
    dashed_fff0 = "0000fff0-0000-1000-8000-00805f9b34fb"
    assert bu.normalize_uuid("FFF0") == dashed_fff0
    assert bu.normalize_uuid("fff0") == dashed_fff0
    assert bu.normalize_uuid("0xFFF1") == "0000fff1-0000-1000-8000-00805f9b34fb"
    assert bu.normalize_uuid("0000FFF2-0000-1000-8000-00805F9B34FB") == (
        "0000fff2-0000-1000-8000-00805f9b34fb")
    # 16/32-bit aliases must match Bleak's hyphenated 128-bit advertisements.
    assert bu.normalize_uuid("FFF0") == bu.normalize_uuid(
        "0000FFF0-0000-1000-8000-00805F9B34FB")
    assert bu.normalize_uuid("12345678") == (
        "12345678-0000-1000-8000-00805f9b34fb")
    assert bu.uuids_equal("12345678", "12345678-0000-1000-8000-00805f9b34fb")
    assert "-" in bu.normalize_uuid("FFF0")
    assert bu.normalize_uuid(
        "6E400001B5A3F393E0A9E50E24DCCA9E") == bu.NUS_SERVICE
    assert bu.normalize_uuid("") == ""
    assert bu.normalize_uuid("nope") == ""
    assert bu.normalize_uuid("fff") == ""


def test_compare_and_short():
    assert bu.uuids_equal("fff1", "0000FFF1-0000-1000-8000-00805f9b34fb")
    assert not bu.uuids_equal("fff1", "fff2")
    assert bu.short_uuid("fff0") == "FFF0"
    assert bu.short_uuid("0000FFF0-0000-1000-8000-00805F9B34FB") == "FFF0"
    assert bu.short_uuid("12345678") == "12345678-0000-1000-8000-00805f9b34fb"
    assert bu.short_uuid(bu.NUS_SERVICE) == bu.NUS_SERVICE
    assert bu.format_adv_uuids(["fff0", "0000FFF0-0000-1000-8000-00805f9b34fb"]) == "FFF0"
    assert bu.format_adv_uuids([]) == "-"
    assert "fff0" in bu.format_adv_uuids_full(["FFF0"])
    class _Adv(object):
        service_uuids = ["180a"]
        service_data = {"fff0": b"\x01"}
    got = bu.adv_service_uuids(_Adv())
    assert bu.uuids_equal(got[0], "180a")
    assert bu.uuids_equal(got[1], "fff0")


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
    mc = bu.apply_preset("microchip")
    assert mc["profile"] == "microchip"
    assert bu.uuids_equal(mc["service_uuid"], bu.MICROCHIP_SERVICE)
    assert bu.uuids_equal(mc["write_uuid"], bu.MICROCHIP_WRITE)
    assert bu.match_profile(
        bu.MICROCHIP_SERVICE, bu.MICROCHIP_WRITE, bu.MICROCHIP_NOTIFY) == "microchip"
    assert bu.normalize_write_mode("Write NR") == bu.WRITE_MODE_WWR
    assert bu.normalize_write_mode("") == bu.WRITE_MODE_AUTO


def test_address():
    assert bu.normalize_address("69-1e-38-38-39-0d") == "69:1E:38:38:39:0D"
    assert bu.is_valid_address("69:1E:38:38:39:0D")
    assert not bu.is_valid_address("COM3")
    assert not bu.is_valid_address("")
    assert not bu.is_valid_uuid("zz")
    assert bu.is_valid_uuid("FFF0")
    assert bu.is_valid_uuid("", allow_empty=True)


def test_sanitize_ble_name():
    assert bu.sanitize_ble_name("\x04BLGW") == "BLGW"
    assert bu.sanitize_ble_name("\ufffd") == ""
    assert bu.sanitize_ble_name("") == ""
    assert bu.sanitize_ble_name(None) == ""
    assert bu.sanitize_ble_name("GEE701") == "GEE701"
    assert bu.sanitize_ble_name("\x00foo\x7f") == "foo"
    assert bu.name_from_raw_sections([(0x09, b"BLGW".hex())]) == "BLGW"
    assert bu.name_from_raw_sections([
        (0x08, b"TV".hex()), (0x09, b"[TV] Samsung".hex()),
    ]) == "[TV] Samsung"
    class _AdvName(object):
        local_name = ""
        manufacturer_data = {}
        service_data = {}
        raw_sections = [(0x09, b"MG_D3_D879".hex())]
    snap = bu.snapshot_advertisement(_AdvName())
    assert bu.adv_local_name("", _AdvName(), snap) == "MG_D3_D879"


def test_snapshot_advertisement_and_merge():
    class _Adv(object):
        tx_power = 4
        connectable = True
        manufacturer_data = {0x004C: b"\x10\x06\x12"}
        service_data = {"fff0": b"\x01"}
        appearance = 0x40
        advertisement_type = "ADV_IND"

    snap = bu.snapshot_advertisement(_Adv())
    assert snap["tx_power"] == 4
    assert snap["connectable"] is True
    assert snap["manufacturer"] == [(0x004C, "100612")]
    assert snap["appearance"] == 0x40
    assert "ADV_IND" in snap["advertisement_type"]
    preview = bu.format_mfr_preview(snap)
    assert "004C" in preview
    assert "100612" in preview
    later = bu.snapshot_advertisement(None)
    later["manufacturer"] = [(0x02E5, "aabb")]
    later["connectable"] = False
    merged = bu.merge_adv_snapshots(snap, later)
    assert merged["connectable"] is True
    assert merged["tx_power"] == 4
    ids = [cid for cid, _hx in merged["manufacturer"]]
    assert ids == [0x004C, 0x02E5]
    blob = bu.search_blob_for_adv(merged)
    assert "004c" in blob and "02e5" in blob
    assert "adv_ind" in blob
    assert "apple" in blob
    a = bu.empty_adv_snapshot()
    b = bu.empty_adv_snapshot()
    a["manufacturer"].append((1, "aa"))
    assert b["manufacturer"] == []
    a["raw_sections"].append((1, "06"))
    assert b["raw_sections"] == []


def test_company_appearance_flags_rssi_raw():
    assert "Apple" in bu.company_name(0x004C)
    assert "Nordic" in bu.company_name(0x0059)
    assert "Generic Phone" in bu.appearance_label(0x40)
    assert "0x0040" in bu.appearance_label(0x40)
    assert bu.adv_flag_keys(0x06) == ["le_general", "bredr_not"]
    assert "█" in bu.rssi_bars(-40)
    cell = bu.format_rssi_cell(-51)
    assert "-51" in cell
    snap = {
        "flags": 0x06,
        "appearance": 0x40,
        "tx_power": 4,
        "manufacturer": [(0x004C, "100612")],
        "service_data": [],
        "raw_sections": [],
    }
    raw, rebuilt = bu.format_raw_hex(snap, ["fff0"])
    assert rebuilt is True
    assert raw
    snap["raw_sections"] = [(0x01, "06")]
    raw2, rebuilt2 = bu.format_raw_hex(snap)
    assert rebuilt2 is False
    assert "06" in raw2.replace(" ", "")


def test_format_raw_hex_splits_overlong_section():
    payload = bytes([0xAB]) * 300
    raw, rebuilt = bu.format_raw_hex({
        "raw_sections": [(0xFF, payload.hex())],
    })
    assert rebuilt is False
    blob = bytes.fromhex(raw.replace(" ", ""))
    assert blob[0] == 255
    assert blob[0] != ((300 + 1) & 0xFF)
    parts, i = [], 0
    while i < len(blob):
        ln = blob[i]
        assert 1 <= ln <= 255
        assert blob[i + 1] == 0xFF
        chunk = blob[i + 2:i + 1 + ln]
        assert len(chunk) == ln - 1
        parts.append(chunk)
        i += 1 + ln
    assert b"".join(parts) == payload
    assert len(parts) == 2
    assert len(parts[0]) == 254
    assert len(parts[1]) == 46
