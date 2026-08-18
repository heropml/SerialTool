# -*- coding: utf-8 -*-
"""FC22 Mask Write + FC43/14 Device Identification."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modbus import modbus_master as mm
from modbus import modbus_slave as ms


def test_fc22_mask_write_formula():
    slave = ms.ModbusSlave(addr=1, holding={10: 0x1234})
    req = mm.build_rtu_request(1, 0x16, 10, (0x00F0, 0x0005))
    resp = slave.handle(req)
    out, n = mm.take_rtu_response(resp, 1, 0x16, 1)
    assert n == len(resp)
    assert out["mask"] == (10, 0x00F0, 0x0005)
    # (0x1234 & 0x00F0) | (0x0005 & ~0x00F0) = 0x0030 | 0x0005 = 0x0035
    assert slave.holding[10] == 0x0035


def test_fc22_broadcast_silent():
    slave = ms.ModbusSlave(addr=1, holding={0: 0xABCD})
    req = mm.build_rtu_request(0, 0x16, 0, (0xFF00, 0x0011))
    assert slave.handle(req) is None
    assert slave.holding[0] == ((0xABCD & 0xFF00) | (0x0011 & 0x00FF))


def test_fc43_basic_stream():
    slave = ms.ModbusSlave(addr=1)
    req = mm.build_rtu_request(1, 0x2B, 0, {"mei": 0x0E, "read_code": 1, "object_id": 0})
    resp = slave.handle(req)
    out, n = mm.take_rtu_response(resp, 1, 0x2B, 1)
    assert n == len(resp)
    did = out["device_id"]
    assert did["read_code"] == 1
    assert did["objects"][0] == b"CommTool"
    assert did["objects"][1] == b"Slave"
    assert did["objects"][2] == b"1.0"


def test_fc43_specific_object():
    slave = ms.ModbusSlave(addr=1, device_id_objects={1: b"XYZ"})
    req = mm.build_rtu_request(1, 0x2B, 0, (0x0E, 4, 1))
    resp = slave.handle(req)
    out, _ = mm.take_rtu_response(resp, 1, 0x2B, 1)
    assert out["device_id"]["objects"] == {1: b"XYZ"}


def test_fc43_bad_mei_illegal_function():
    slave = ms.ModbusSlave(addr=1)
    body = bytes([1, 0x2B, 0x0D, 1, 0])
    frame = body + ms.crc16(body)
    resp = slave.handle(frame)
    assert resp[1] == 0x2B | 0x80
    assert resp[2] == ms.EXC_ILLEGAL_FUNCTION


def test_normalize_fc22_and_fc43():
    a = mm.normalize_poll({"func": 0x16, "addr": 5, "wval": "0xFFF0:1", "unit": 1, "period": 100})
    assert a["and_mask"] == 0xFFF0 and a["or_mask"] == 1
    assert mm.normalize_poll(a) == a
    b = mm.normalize_poll({"func": 0x2B, "wval": "4:2", "unit": 1, "period": 100, "addr": 0})
    assert b["read_code"] == 4 and b["object_id"] == 2
    assert mm.normalize_poll(b) == b


def test_rtu_normal_len_fc22():
    assert mm.rtu_normal_len(0x16, 1) == 10
