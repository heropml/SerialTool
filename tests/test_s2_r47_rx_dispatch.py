# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R47 rx_dispatch."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import rx_dispatch as rx


def test_engine_route_priority():
    assert rx.engine_route(
        script_running=True, script_quiet_until=0, now=1,
        seq_running=True, seq_waiting_mbm=True) == "script"
    assert rx.engine_route(
        script_running=False, script_quiet_until=0, now=1,
        seq_running=True, seq_waiting_mbm=True) == "seq_mbm"
    assert rx.engine_route(
        script_running=False, script_quiet_until=0, now=1,
        seq_running=True, seq_waiting_mbm=False) == "seq"
    assert rx.engine_route(
        script_running=False, script_quiet_until=0, now=1,
        seq_running=False, seq_waiting_mbm=False) == "normal"


def test_feed_gates():
    assert rx.should_feed_script(route="script", now=10, quiet_until=9) is True
    assert rx.should_feed_script(route="script", now=8, quiet_until=9) is False
    assert rx.should_feed_auto_reply(route="normal", mbm_active=False) is True
    assert rx.should_feed_auto_reply(route="normal", mbm_active=True) is False
    assert rx.should_feed_mbm(route="normal") is True
    assert rx.should_feed_mbm(route="seq_mbm") is True
    assert rx.should_feed_mbm(route="seq") is False
    assert rx.structured_feed_ok(mbm_inflight=True) is False
    assert rx.xfer_owns(xfer_running=True) is True


def test_display_mode_and_stream():
    assert rx.rx_display_mode(
        terminal_on=True, hexdump_on=True, numview_on=True) == "terminal"
    assert rx.rx_display_mode(
        terminal_on=False, hexdump_on=True, numview_on=True) == "hexdump"
    assert rx.rx_display_mode(
        terminal_on=False, hexdump_on=False, numview_on=True) == "numview"
    assert rx.rx_display_mode(
        terminal_on=False, hexdump_on=False, numview_on=False) == "stream"
    assert rx.numview_carry(conn_proto="UDP") is False
    assert rx.numview_carry(conn_proto="Serial") is True
    assert rx.stream_flags(rx_hex=True, line_split=True) == (True, False)
    assert rx.packet_timeout_ms("abc") == 20
    assert rx.packet_timeout_ms("5") == 5
    assert rx.next_pending_line_break(
        use_line_split=True, segments=["a", ""]) is True


def test_ansi_and_force_new_block():
    assert rx.ansi_needs_parse(pending="", text="hi", state_is_default=True) is False
    assert rx.ansi_needs_parse(pending="x", text="hi", state_is_default=True) is True
    assert rx.ansi_needs_parse(pending="", text="a\x1bb", state_is_default=True) is True
    assert rx.ansi_needs_parse(pending="", text="hi", state_is_default=False) is True
    assert rx.force_new_block_first(
        last_direction="tx", pending_line_break=False, cross_chunk_crlf=False,
        packet_split=False, gap_ms=0, timeout_ms=20) is True
    assert rx.force_new_block_first(
        last_direction="rx", pending_line_break=False, cross_chunk_crlf=False,
        packet_split=True, gap_ms=50, timeout_ms=20) is True
    assert rx.force_new_block_first(
        last_direction="rx", pending_line_break=False, cross_chunk_crlf=False,
        packet_split=True, gap_ms=5, timeout_ms=20) is False


def test_skip_empty_trailing_seg_edges():
    # trailing empty from split: skip
    assert rx.skip_empty_trailing_seg(
        is_last=True, seg="", use_line_split=True, n_segments=2) is True
    # single empty segment: do not skip (n_segments==1)
    assert rx.skip_empty_trailing_seg(
        is_last=True, seg="", use_line_split=True, n_segments=1) is False
    assert rx.skip_empty_trailing_seg(
        is_last=True, seg="", use_line_split=False, n_segments=2) is False
