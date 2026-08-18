# -*- coding: utf-8 -*-
"""Auto-reply ingress / SM queue / rule gate decisions (Qt-free).

CommTool keeps buffers, timers, and reply construction; mode selection,
length-buffer trim, SM busy/enqueue, length filter and cooldown live here.
"""
from __future__ import annotations

LENGTH_BUF_MAX = 8192
LENGTH_BUF_KEEP = 512
SM_QUEUE_LIMIT = 256


def ingress_mode(
    *,
    ar_on,
    is_open,
    modbus_on,
    has_rules,
    frame_on,
    has_header,
    gap_ms,
):
    """Choose how RX bytes enter the auto-reply engine.

    Returns:
      "noop" | "modbus" | "no_rules" | "length_frame" | "gap" | "immediate"
    """
    if not ar_on or not is_open:
        return "noop"
    if modbus_on:
        return "modbus"
    if not has_rules:
        return "no_rules"
    if frame_on and has_header:
        return "length_frame"
    if int(gap_ms or 0) > 0:
        return "gap"
    return "immediate"


def trim_length_buf(buf, max_len=LENGTH_BUF_MAX, keep=LENGTH_BUF_KEEP):
    """Bound length-frame reassembly buffer; return (buf, trimmed)."""
    raw = bytes(buf or b"")
    max_len = max(0, int(max_len))
    keep = max(0, int(keep))
    if max_len > 0 and len(raw) > max_len:
        if keep <= 0:
            return b"", True
        return raw[-keep:], True
    return raw, False


def sm_busy(*, sm_on, pending, queue_len, draining):
    """True when SM multi-segment reply owns the match path."""
    if not sm_on:
        return False
    if pending is not None:
        return True
    return int(queue_len or 0) > 0 and not bool(draining)


def enqueue_sm_frame(queue, data, limit=SM_QUEUE_LIMIT):
    """Append frame to SM FIFO when under limit. Returns True if enqueued."""
    q = queue
    lim = max(0, int(limit))
    if lim > 0 and len(q) >= lim:
        return False
    q.append(bytes(data))
    return True


def len_filter_ok(data_len, min_len, max_len):
    """True when frame length passes optional min/max (0 = unlimited)."""
    n = int(data_len)
    lo = int(min_len or 0)
    hi = int(max_len or 0)
    if lo > 0 and n < lo:
        return False
    if hi > 0 and n > hi:
        return False
    return True


def cooldown_blocks(now, last, cooldown_ms):
    """True when rule cooldown window still suppresses a hit."""
    cd = int(cooldown_ms or 0)
    if cd <= 0:
        return False
    return (float(now) - float(last or 0.0)) * 1000.0 < cd


def reply_path(rule):
    """Choose reply builder: "script" or "template"."""
    r = rule if isinstance(rule, dict) else {}
    script = str(r.get("script") or "").strip()
    if script and r.get("script_on", True):
        return "script"
    return "template"


def goto_armed(*, sm_on, goto):
    """True when SM is on and rule has a non-empty goto target."""
    return bool(sm_on) and bool(str(goto or "").strip())


def post_hit_plan(
    rule,
    *,
    sm_on,
    parts,
    from_script,
    script_err=None,
):
    """After a rule hits and cooldown passes: decide schedule vs abort.

    Returns dict:
      action: "abort" | "schedule"
      note_script_err: bool
      hexmode: bool
      cs: int
      cs_segs: list
      arm_goto: bool
    """
    r = rule if isinstance(rule, dict) else {}
    note = bool(from_script and script_err)
    if not parts:
        return {
            "action": "abort",
            "note_script_err": note,
            "hexmode": True,
            "cs": 0,
            "cs_segs": [],
            "arm_goto": False,
        }
    if from_script:
        hexmode, cs, cs_segs = True, 0, []
    else:
        hexmode = bool(r.get("reply_hex", True))
        try:
            cs = int(r.get("cs", 0) or 0)
        except (TypeError, ValueError):
            cs = 0
        cs_segs = list(r.get("cs_segs", []) or [])
    return {
        "action": "schedule",
        "note_script_err": note,
        "hexmode": hexmode,
        "cs": cs,
        "cs_segs": cs_segs,
        "arm_goto": goto_armed(sm_on=sm_on, goto=r.get("goto", "")),
    }


def clear_pending_on_schedule_error(*, pending, current_pending):
    """True when schedule failed and pending token still owns the latch."""
    return pending is not None and current_pending is pending
