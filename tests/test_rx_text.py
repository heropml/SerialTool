# -*- coding: utf-8 -*-
"""Qt-free unit tests for rx_text (S-2)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol import ansi
from protocol import rx_text as rt


def test_decode_auto_utf8_and_partial():
    payload = "\u4f60\u597d".encode("utf-8")
    text, buf = rt.decode_auto_chunk(b"", payload)
    assert text == "\u4f60\u597d" and buf == b""
    partial = "\u4f60".encode("utf-8")
    text, buf = rt.decode_auto_chunk(b"", partial[:2])
    assert text == "" and buf == partial[:2]
    text, buf = rt.decode_auto_chunk(buf, partial[2:])
    assert text == "\u4f60" and buf == b""


def test_decode_auto_gbk_fallback():
    raw = "\u6d4b\u8bd5".encode("gbk")
    text, buf = rt.decode_auto_chunk(b"", raw)
    assert buf == b""
    assert text


def test_split_lines_modes():
    segs, offs = rt.split_lines_with_offsets("a\r\nb\nc\rd", 0)
    assert segs == ["a", "b", "c", "d"]
    assert offs == [0, 3, 5, 7]
    segs, offs = rt.split_lines_with_offsets("a\r\nb", 1)
    assert segs == ["a", "b"] and offs == [0, 3]
    segs, offs = rt.split_lines_with_offsets("a\nb", 2)
    assert segs == ["a", "b"] and offs == [0, 2]
    segs, offs = rt.split_lines_with_offsets("a\rb", 3)
    assert segs == ["a", "b"] and offs == [0, 2]


def test_ansi_flatten_shift_slice():
    runs, _st, _pend = ansi.parse("\x1b[31mRED\x1b[0m plain")
    text, spans = rt.ansi_flatten(runs)
    assert text == "RED plain"
    assert spans and spans[0][0] == 0 and spans[0][1] == 3
    shifted = rt.ansi_shift(spans, 2, len(text) + 2)
    assert shifted[0][0] == 2 and shifted[0][1] == 5
    sliced = rt.ansi_slice(spans, 1, 8)
    assert sliced[0][0] == 0 and sliced[0][1] == 2
    assert rt.ansi_shift([], 1, 10) == []
    assert rt.ansi_slice([], 0, 5) == []
