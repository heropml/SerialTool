# -*- coding: utf-8 -*-
"""Qt-free tests for binproto frame_rules helpers (S-2 R11)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import binproto as bp


def test_parse_frame_rules():
    raw = (
        "\n"
        "# comment\n"
        "AA 55 | cmd=2:u8x, len=3:u8\n"
        "| only=0:u8\n"
        "bad | nope\n"
        "BB | seq=1:u16le\n"
    )
    rules = bp.parse_frame_rules(raw)
    assert len(rules) == 3
    assert rules[0]["header"] == bytes.fromhex("AA55")
    assert rules[0]["header_str"] == "AA 55"
    assert rules[0]["fields"][0][0] == "cmd"
    assert rules[1]["header"] == b""
    assert rules[1]["header_str"] == "*"
    assert rules[2]["header"] == bytes.fromhex("BB")


def test_first_matching_rule():
    rules = bp.parse_frame_rules("AA | a=0:u8\nBB | b=0:u8")
    assert bp.first_matching_rule(rules, b"\xaa\x01")["header"] == b"\xaa"
    assert bp.first_matching_rule(rules, b"\xbb\x02")["header"] == b"\xbb"
    assert bp.first_matching_rule(rules, b"\xcc") is None
    any_rules = bp.parse_frame_rules("| x=0:u8")
    assert bp.first_matching_rule(any_rules, b"\xff") is not None


def test_field_disp():
    assert bp.field_disp("u8x", 0x1A) == "0x1A"
    assert bp.field_disp("u8x", -3) == "-0x3"
    assert bp.field_disp("u8", 26) == "26"
    assert bp.field_disp("f32le", 1.5).startswith("1.5")
    assert bp.field_disp("str4", "AB") == "AB"
    assert bp.field_disp("u8", None) == ""
