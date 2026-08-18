# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R48 TX helpers in auto_reply_core."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import auto_reply_core as core


def test_parse_tx_hex_ok_and_errors():
    ok = core.parse_tx_hex("AA /*c*/ BB //x\n")
    assert ok["ok"] and ok["data"] == b"\xaa\xbb"
    assert core.parse_tx_hex("")["error"] == "empty"
    assert core.parse_tx_hex("ZZ")["error"] == "bad_chars"
    assert core.parse_tx_hex("ABC")["error"] == "odd_length"
    assert core.reply_hex_bytes("AA BB") == b"\xaa\xbb"
    assert core.reply_hex_bytes("ZZ") is None


def test_newline_preflight_classify_display():
    assert core.append_tx_newline(b"x", newline=None, global_on=True, global_idx=0) == b"x\r\n"
    assert core.append_tx_newline(b"x", newline=2, global_on=False) == b"x\n"
    assert core.append_tx_newline(b"x", newline=0) == b"x"
    assert core.send_preflight(exclusive_blocked=True, is_open=True, raw_empty=False) == "exclusive"
    assert core.send_preflight(exclusive_blocked=False, is_open=False, raw_empty=False) == "not_open"
    assert core.send_preflight(exclusive_blocked=False, is_open=True, raw_empty=True) == "empty"
    assert core.send_preflight(exclusive_blocked=False, is_open=True, raw_empty=False) is None
    assert core.classify_send_result(
        sent=-1, payload_len=4, no_target_sentinel=-1, strict_full_write=True) == "no_target"
    assert core.classify_send_result(
        sent=2, payload_len=4, no_target_sentinel=-1, strict_full_write=True) == "fail_partial"
    assert core.classify_send_result(
        sent=4, payload_len=4, no_target_sentinel=-1, strict_full_write=True) == "ok"
    # strict + sent>len (or otherwise unequal and not partial) -> fail_mismatch
    assert core.classify_send_result(
        sent=5, payload_len=4, no_target_sentinel=-1, strict_full_write=True) == "fail_mismatch"
    # non-strict: partial write still ok (UDP etc.)
    assert core.classify_send_result(
        sent=2, payload_len=4, no_target_sentinel=-1, strict_full_write=False) == "ok"
    assert core.classify_send_result(
        sent=0, payload_len=4, no_target_sentinel=-1, strict_full_write=False) == "fail_empty"
    assert core.tx_display_mode(
        hexdump_on=False, numview_on=False, rx_hex=True) == "hex"
