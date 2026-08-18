# -*- coding: utf-8 -*-
"""Qt-free unit tests for view_format (S-2)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol import view_format as vf


def test_bytes_to_hex():
    assert vf.bytes_to_hex(b"\xaa\xbb") == "AA BB"
    assert vf.bytes_to_hex(b"") == ""


def test_format_hexdump_layout():
    line = vf.format_hexdump(b"AB")
    assert line.startswith("00000000  ")
    assert line.endswith("|AB|")
    assert "41 42" in line
    two = vf.format_hexdump(bytes(range(17))).split("\n")
    assert len(two) == 2
    assert two[1].startswith("00000010  ")
    assert vf.format_hexdump(b"") == ""
    assert len(vf.format_hexdump(bytes(range(20)), per=8).split("\n")) == 3
    assert len(vf.format_hexdump(bytes(range(32)), per=32).split("\n")) == 1
    # invalid per falls back to 16
    assert len(vf.format_hexdump(bytes(range(17)), per=7).split("\n")) == 2


def test_with_leading_newline():
    assert vf.with_leading_newline("abc", True) == "\nabc"
    assert vf.with_leading_newline("abc", False) == "abc"
    assert vf.with_leading_newline("", True) == ""
