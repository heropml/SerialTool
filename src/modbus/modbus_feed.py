# -*- coding: utf-8 -*-
"""Modbus master RX feed decisions (Qt-free).

Parsers stay in modbus_master; guard/echo/resync/buffer policy lives here.
"""
from __future__ import annotations

BUF_CAP = 4096


def idle_guard_plan(
    *,
    has_inflight,
    now,
    guard_until,
    variant_eff,
    rtu_silent_s,
):
    """When no inflight request: optionally extend RTU silent guard, then return.

    Returns dict:
      action: "continue" | "idle_return"
      guard_until: float (updated when RTU late bytes arrive in guard window)
    """
    if has_inflight:
        return {"action": "continue", "guard_until": float(guard_until)}
    veff = str(variant_eff or "")
    now = float(now)
    guard_until = float(guard_until)
    if now < guard_until and veff in ("rtu", "ascii"):
        if veff == "rtu":
            guard_until = max(guard_until, now + float(rtu_silent_s))
    return {"action": "idle_return", "guard_until": guard_until}


def clamp_rx_buf(buf, cap=BUF_CAP):
    """Bound reassembly buffer to last ``cap`` bytes."""
    raw = bytes(buf or b"")
    cap = max(0, int(cap))
    if cap > 0 and len(raw) > cap:
        return raw[-cap:]
    return raw


def feed_variant(info):
    """Normalize inflight variant to tcp|ascii|rtu."""
    v = str((info or {}).get("variant") or "")
    if v == "tcp":
        return "tcp"
    if v == "ascii":
        return "ascii"
    return "rtu"


def echo_needed(info, *, echo_enabled):
    """True when local echo must be stripped before parse."""
    if not echo_enabled:
        return False
    info = info or {}
    return bool(info.get("echo")) and not bool(info.get("echo_done"))


def after_echo_strip(found):
    """'wait' until full echo seen; 'echo_done' when stripped."""
    return "echo_done" if found else "wait"


def ascii_resync_on_value_error(buf):
    """Drop through first newline (inclusive), or clear if none."""
    raw = bytes(buf or b"")
    nl = raw.find(b"\n")
    return raw[nl + 1:] if nl >= 0 else b""


def rtu_resync_on_value_error(buf):
    """Drop exactly one leading byte."""
    raw = bytes(buf or b"")
    return raw[1:] if raw else b""

