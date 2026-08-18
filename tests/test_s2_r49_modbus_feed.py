# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R49 modbus_feed."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modbus import modbus_feed as mf


def test_idle_guard_rtu_extends_ascii_does_not():
    rtu = mf.idle_guard_plan(
        has_inflight=False, now=10.0, guard_until=10.5,
        variant_eff="rtu", rtu_silent_s=0.4)
    assert rtu["action"] == "idle_return"
    assert rtu["guard_until"] == 10.5  # max(10.5, 10.4)

    rtu2 = mf.idle_guard_plan(
        has_inflight=False, now=10.0, guard_until=10.1,
        variant_eff="rtu", rtu_silent_s=0.5)
    assert rtu2["guard_until"] == 10.5

    ascii_p = mf.idle_guard_plan(
        has_inflight=False, now=10.0, guard_until=10.1,
        variant_eff="ascii", rtu_silent_s=0.5)
    assert ascii_p["action"] == "idle_return"
    assert ascii_p["guard_until"] == 10.1

    cont = mf.idle_guard_plan(
        has_inflight=True, now=10.0, guard_until=10.1,
        variant_eff="rtu", rtu_silent_s=0.5)
    assert cont["action"] == "continue"


def test_buf_echo_resync():
    assert len(mf.clamp_rx_buf(b"x" * 5000)) == mf.BUF_CAP
    assert mf.clamp_rx_buf(None) == b""
    assert mf.clamp_rx_buf(b"abc", cap=0) == b"abc"  # cap<=0: no trim
    assert mf.feed_variant({"variant": "tcp"}) == "tcp"
    assert mf.echo_needed({"echo": b"a", "echo_done": False}, echo_enabled=True)
    assert not mf.echo_needed({"echo": b"a", "echo_done": True}, echo_enabled=True)
    assert mf.after_echo_strip(False) == "wait"
    assert mf.ascii_resync_on_value_error(b"bad\nmore") == b"more"
    assert mf.rtu_resync_on_value_error(b"abc") == b"bc"
