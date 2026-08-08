# -*- coding: utf-8 -*-
"""Auto-reconnect policy (Qt-free).

CommTool keeps QTimer / toast / open_conn as the shell; delay, attempt
budget and device-gate decisions live here so CLI/API can reuse them.
"""
from __future__ import annotations

SERIAL_RECONNECT_LIMIT = 10
SERIAL_DELAY_CAP_MS = 5000
SERIAL_DELAY_STEP_MS = 500
NET_DELAY_CAP_MS = 30000
NET_DELAY_BASE_MS = 1000


def serial_delay_ms(attempts):
    """Linear backoff: 0.5s, 1.0s, ... capped at 5s (attempts is pre-bump)."""
    n = max(0, int(attempts or 0))
    return min(SERIAL_DELAY_CAP_MS, SERIAL_DELAY_STEP_MS * (n + 1))


def net_delay_ms(attempts):
    """Exponential backoff: 1s, 2s, 4s, ... capped at 30s."""
    n = max(0, int(attempts or 0))
    # Guard absurd exponents; delay is capped anyway.
    if n > 20:
        return NET_DELAY_CAP_MS
    return min(NET_DELAY_CAP_MS, NET_DELAY_BASE_MS * (2 ** n))


def plan_schedule(
    *,
    user_closing,
    auto_reconnect,
    timer_active,
    serial_retry,
    attempts,
    serial_limit=SERIAL_RECONNECT_LIMIT,
):
    """Decide whether to arm the reconnect timer.

    Returns a dict:
      action: "skip" | "exhausted" | "arm"
      delay_ms: int (only for "arm")
      bump_attempts: bool (True for network path; serial bumps on try)
      clear_serial_target: bool (only for "exhausted")
      reset_attempts: bool (only for "exhausted")
    """
    if user_closing or not auto_reconnect or timer_active:
        return {"action": "skip"}
    n = max(0, int(attempts or 0))
    limit = int(serial_limit or SERIAL_RECONNECT_LIMIT)
    if serial_retry and n >= limit:
        return {
            "action": "exhausted",
            "clear_serial_target": True,
            "reset_attempts": True,
        }
    if serial_retry:
        return {
            "action": "arm",
            "delay_ms": serial_delay_ms(n),
            "bump_attempts": False,
        }
    return {
        "action": "arm",
        "delay_ms": net_delay_ms(n),
        "bump_attempts": True,
    }


def plan_try(
    *,
    conn_open,
    user_closing,
    auto_reconnect,
    serial_cfg,
    device_available,
):
    """Decide what a reconnect timer tick should do.

    Returns:
      action: "noop" | "wait_device" | "open"
      bump_attempts: bool (serial path bumps once per tick)
      toast_try: bool (network path shows attempt toast)
    """
    if conn_open or user_closing or not auto_reconnect:
        return {"action": "noop", "bump_attempts": False, "toast_try": False}
    if serial_cfg:
        device = serial_cfg[1] if len(serial_cfg) > 1 else None
        available = device_available or set()
        if device not in available:
            return {
                "action": "wait_device",
                "bump_attempts": True,
                "toast_try": False,
            }
        return {
            "action": "open",
            "bump_attempts": True,
            "toast_try": False,
        }
    return {
        "action": "open",
        "bump_attempts": False,
        "toast_try": True,
    }


def should_reschedule_after_open_fail(*, serial_cfg, serial_target_still_set):
    """After open_conn left conn=None, whether to queue another attempt.

    Serial attempt #limit clears the target inside schedule; do not fall
    through to a network-style reconnect that reads the UI port.
    """
    if serial_cfg is None:
        return True
    return bool(serial_target_still_set)
