# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R46 auto_reply_gate."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import auto_reply_gate as gate


def test_ingress_mode_priority():
    assert gate.ingress_mode(
        ar_on=False, is_open=True, modbus_on=False, has_rules=True,
        frame_on=False, has_header=False, gap_ms=0) == "noop"
    assert gate.ingress_mode(
        ar_on=True, is_open=False, modbus_on=True, has_rules=True,
        frame_on=False, has_header=False, gap_ms=0) == "noop"
    assert gate.ingress_mode(
        ar_on=True, is_open=True, modbus_on=True, has_rules=False,
        frame_on=True, has_header=True, gap_ms=10) == "modbus"
    assert gate.ingress_mode(
        ar_on=True, is_open=True, modbus_on=False, has_rules=False,
        frame_on=True, has_header=True, gap_ms=10) == "no_rules"
    assert gate.ingress_mode(
        ar_on=True, is_open=True, modbus_on=False, has_rules=True,
        frame_on=True, has_header=True, gap_ms=10) == "length_frame"
    assert gate.ingress_mode(
        ar_on=True, is_open=True, modbus_on=False, has_rules=True,
        frame_on=True, has_header=False, gap_ms=10) == "gap"
    assert gate.ingress_mode(
        ar_on=True, is_open=True, modbus_on=False, has_rules=True,
        frame_on=False, has_header=False, gap_ms=0) == "immediate"


def test_trim_length_buf():
    buf, trimmed = gate.trim_length_buf(b"x" * 9000)
    assert trimmed is True
    assert len(buf) == gate.LENGTH_BUF_KEEP
    buf2, trimmed2 = gate.trim_length_buf(b"abc")
    assert trimmed2 is False
    assert buf2 == b"abc"


def test_sm_busy_and_enqueue():
    assert gate.sm_busy(sm_on=False, pending=object(), queue_len=1, draining=False) is False
    assert gate.sm_busy(sm_on=True, pending=object(), queue_len=0, draining=False) is True
    assert gate.sm_busy(sm_on=True, pending=None, queue_len=2, draining=False) is True
    assert gate.sm_busy(sm_on=True, pending=None, queue_len=2, draining=True) is False

    q = []
    assert gate.enqueue_sm_frame(q, b"\x01") is True
    assert q == [b"\x01"]
    q = [b"x"] * gate.SM_QUEUE_LIMIT
    assert gate.enqueue_sm_frame(q, b"y") is False
    assert len(q) == gate.SM_QUEUE_LIMIT


def test_len_filter_and_cooldown():
    assert gate.len_filter_ok(5, 0, 0) is True
    assert gate.len_filter_ok(5, 6, 0) is False
    assert gate.len_filter_ok(5, 0, 4) is False
    assert gate.len_filter_ok(5, 3, 8) is True

    assert gate.cooldown_blocks(10.0, 9.9, 0) is False
    assert gate.cooldown_blocks(10.0, 9.9, 200) is True
    assert gate.cooldown_blocks(10.0, 9.0, 200) is False
