# -*- coding: utf-8 -*-
"""Qt-free unit tests for modbus_scheduler (S-2)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modbus import modbus_scheduler as ms


def test_pick_next_due_skips_disabled_and_honors_guard():
    rules = [
        {"enabled": False},
        {"enabled": True},
        {"enabled": True},
    ]
    due = {1: 10.0, 2: 5.0}
    idx, wait = ms.pick_next_due(rules, due, now=4.0, guard_until=0.0)
    assert idx == 2
    assert abs(wait - 1.0) < 1e-9

    idx, wait = ms.pick_next_due(rules, due, now=4.0, guard_until=7.0)
    assert idx == 2
    assert abs(wait - 3.0) < 1e-9  # max(due=5, guard=7) - now


def test_pick_next_due_ready_when_past():
    rules = [{"enabled": True}]
    idx, wait = ms.pick_next_due(rules, {0: 1.0}, now=2.0, guard_until=0.0)
    assert idx == 0
    assert wait <= 0


def test_pick_next_due_empty():
    assert ms.pick_next_due([], {}, 0.0) == (None, None)
    assert ms.pick_next_due([{"enabled": False}], {}, 0.0) == (None, None)


def test_schedule_delay_ms_clamps():
    assert ms.schedule_delay_ms(0) == 0
    assert ms.schedule_delay_ms(-1) == 0
    assert ms.schedule_delay_ms(0.001) == 2  # int(1)+1
    assert ms.schedule_delay_ms(1.0) == 1001
    assert ms.schedule_delay_ms(1e9, qtimer_max_ms=100) == 100


def test_next_due_after():
    assert ms.next_due_after(10.0, 500) == 10.5
    assert ms.next_due_after(10.0, -5) == 10.0
