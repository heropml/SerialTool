# -*- coding: utf-8 -*-
"""Qt-free unit tests for modbus_timing (S-2)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modbus import modbus_timing as mt


def test_serial_char_bits():
    assert mt.serial_char_bits(8, "None", 1) == 10.0
    assert mt.serial_char_bits(8, "Even", 1) == 11.0
    assert mt.serial_char_bits(8, "None", 2) == 11.0
    assert mt.serial_char_bits("bad", "None", 1) == 11.0


def test_rtu_silent_ms_high_and_low_baud():
    assert mt.rtu_silent_ms(38400, 11.0) == 2
    # 9600, 11 bits: 3.5 * 11 * 1000 / 9600 + 0.999 -> int == 5
    assert mt.rtu_silent_ms(9600, 11.0) == 5
    assert mt.rtu_silent_ms(1200, 11.0) >= 2


def test_rtu_tx_guard_includes_silent():
    guard = mt.rtu_tx_guard_ms(8, 9600, 11.0)
    assert guard > mt.rtu_silent_ms(9600, 11.0)


def test_timeout_ms_grows_with_frame():
    short = mt.timeout_ms(1000, 8, 7, 9600, 11.0)
    long = mt.timeout_ms(1000, 8, 255, 1200, 11.0)
    assert long > short
    assert short >= 1000


def test_response_len_budget_ascii_vs_rtu():
    rtu = mt.response_len_budget(0x03, 10, "rtu")
    ascii_n = mt.response_len_budget(0x03, 10, "ascii")
    assert ascii_n == 2 * rtu + 1


def test_span_bad():
    assert mt.span_bad({"func": 0x03, "addr": 0xFFFE, "qty": 3}) is True
    assert mt.span_bad({"func": 0x03, "addr": 0x10, "qty": 2}) is False
    assert mt.span_bad({"func": 0x10, "addr": 0xFFFE, "wvals": [1, 2, 3]}) is True
    assert mt.span_bad({"func": 0x16, "addr": 0xFFFF}) is False
    assert mt.span_bad({"func": 0x16, "addr": 0x10000}) is True
