# -*- coding: utf-8 -*-
"""Modbus master poll scheduler helpers (Qt-free).

S-2 slice: pick the next due rule and compute QTimer delay without CommTool.
"""
QTIMER_MAX_MS = 0x7FFFFFFF


def pick_next_due(rules, due_map, now, guard_until=0.0):
    """Pick the soonest enabled rule.

    Returns (index, wait_s) or (None, None) when nothing is enabled.
    wait_s <= 0 means the rule is ready to poll immediately.
    """
    best_i, best_due = None, None
    for i, r in enumerate(rules or []):
        if not (r or {}).get("enabled"):
            continue
        due = float((due_map or {}).get(i, 0.0) or 0.0)
        if best_due is None or due < best_due:
            best_i, best_due = i, due
    if best_i is None:
        return None, None
    wait = max(float(best_due), float(guard_until or 0.0)) - float(now)
    return best_i, wait


def schedule_delay_ms(wait_s, qtimer_max_ms=QTIMER_MAX_MS):
    """Convert a positive wait (seconds) into a clamped single-shot delay."""
    try:
        wait_s = float(wait_s)
    except (TypeError, ValueError):
        return 1
    if wait_s <= 0:
        return 0
    return min(int(qtimer_max_ms), max(1, int(wait_s * 1000) + 1))


def next_due_after(now, period_ms):
    """Absolute monotonic due time after a successful/failed poll."""
    try:
        period_ms = max(0, int(period_ms))
    except (TypeError, ValueError):
        period_ms = 0
    return float(now) + period_ms / 1000.0
