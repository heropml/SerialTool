# -*- coding: utf-8 -*-
"""RX ownership / display-mode decisions (Qt-free).

CommTool keeps side-feed scheduling, decode, and QTextEdit writes;
routing and view-mode choice live here for CLI/API reuse.
"""
from __future__ import annotations

UDP_PROTOS = frozenset({"UDP", "UDP Multicast"})


def xfer_owns(*, xfer_running):
    """True when file transfer owns the RX stream (early return)."""
    return bool(xfer_running)


def engine_route(
    *,
    script_running,
    script_quiet_until,
    now,
    seq_running,
    seq_waiting_mbm,
):
    """Who consumes RX for match engines after display/side feeds.

    Returns: "script" | "seq_mbm" | "seq" | "normal"
    """
    if script_running:
        return "script"
    if seq_running:
        return "seq_mbm" if seq_waiting_mbm else "seq"
    return "normal"


def should_feed_script(*, route, now, quiet_until):
    """Script feed only after Modbus quiet window ends."""
    return route == "script" and float(now) >= float(quiet_until or 0.0)


def should_feed_auto_reply(*, route, mbm_active):
    """AR only on normal path when Modbus master poll is off."""
    return route == "normal" and not bool(mbm_active)


def should_feed_mbm(*, route):
    """Mbm feed on normal path and while sequence waits for late Modbus."""
    return route in ("normal", "seq_mbm")


def structured_feed_ok(*, mbm_inflight):
    """Skip generic structured parse while a Modbus request is in flight."""
    return not bool(mbm_inflight)


def rx_display_mode(*, terminal_on, hexdump_on, numview_on):
    """Priority: terminal > hexdump > numview > stream."""
    if terminal_on:
        return "terminal"
    if hexdump_on:
        return "hexdump"
    if numview_on:
        return "numview"
    return "stream"


def numview_carry(*, conn_proto, udp_protos=UDP_PROTOS):
    """UDP datagrams must not carry partial numbers across packets."""
    return str(conn_proto or "") not in udp_protos


def stream_flags(*, rx_hex, line_split):
    """(use_hex, use_line_split); line split disabled in hex mode."""
    use_hex = bool(rx_hex)
    return use_hex, bool(line_split) and not use_hex


def ansi_needs_parse(*, pending, text, state_is_default):
    """Whether ANSI parser must run (pending/escape/carried style)."""
    return bool(pending) or ("\x1b" in (text or "")) or (not bool(state_is_default))


def packet_timeout_ms(raw, default=20):
    """Parse packet-split timeout; invalid -> default, minimum 1."""
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return int(default)


def force_new_block_first(
    *,
    last_direction,
    pending_line_break,
    cross_chunk_crlf,
    packet_split,
    gap_ms,
    timeout_ms,
):
    """Whether the first stream segment starts a new display block."""
    if last_direction != "rx" or pending_line_break or cross_chunk_crlf:
        return True
    if packet_split and float(gap_ms) > float(timeout_ms):
        return True
    return False


def skip_empty_trailing_seg(*, is_last, seg, use_line_split, n_segments):
    """Drop the empty trailing piece produced by a trailing newline split."""
    return bool(is_last) and seg == "" and bool(use_line_split) and int(n_segments) > 1


def next_pending_line_break(*, use_line_split, segments):
    """Carry line-break intent when split ends with an empty segment."""
    if not use_line_split:
        return False
    segs = list(segments or [])
    return bool(segs) and segs[-1] == "" and len(segs) > 1
