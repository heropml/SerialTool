# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R43 reconnect_policy."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import reconnect_policy as rp


def test_serial_linear_backoff():
    assert rp.serial_delay_ms(0) == 500
    assert rp.serial_delay_ms(1) == 1000
    assert rp.serial_delay_ms(9) == 5000
    assert rp.serial_delay_ms(20) == 5000


def test_net_exponential_backoff():
    assert rp.net_delay_ms(0) == 1000
    assert rp.net_delay_ms(1) == 2000
    assert rp.net_delay_ms(2) == 4000
    assert rp.net_delay_ms(10) == 30000
    assert rp.net_delay_ms(99) == 30000


def test_plan_schedule_skip_and_arm():
    assert rp.plan_schedule(
        user_closing=True, auto_reconnect=True, timer_active=False,
        serial_retry=False, attempts=0)["action"] == "skip"
    assert rp.plan_schedule(
        user_closing=False, auto_reconnect=False, timer_active=False,
        serial_retry=False, attempts=0)["action"] == "skip"
    assert rp.plan_schedule(
        user_closing=False, auto_reconnect=True, timer_active=True,
        serial_retry=False, attempts=0)["action"] == "skip"

    serial = rp.plan_schedule(
        user_closing=False, auto_reconnect=True, timer_active=False,
        serial_retry=True, attempts=0)
    assert serial["action"] == "arm"
    assert serial["delay_ms"] == 500
    assert serial["bump_attempts"] is False

    net = rp.plan_schedule(
        user_closing=False, auto_reconnect=True, timer_active=False,
        serial_retry=False, attempts=0)
    assert net["action"] == "arm"
    assert net["delay_ms"] == 1000
    assert net["bump_attempts"] is True


def test_plan_schedule_serial_exhausted():
    out = rp.plan_schedule(
        user_closing=False, auto_reconnect=True, timer_active=False,
        serial_retry=True, attempts=rp.SERIAL_RECONNECT_LIMIT)
    assert out["action"] == "exhausted"
    assert out["clear_serial_target"] is True
    assert out["reset_attempts"] is True


def test_plan_schedule_ble_exhausted():
    armed = rp.plan_schedule(
        user_closing=False, auto_reconnect=True, timer_active=False,
        serial_retry=False, attempts=0,
        attempt_limit=rp.BLE_RECONNECT_LIMIT)
    assert armed["action"] == "arm"
    out = rp.plan_schedule(
        user_closing=False, auto_reconnect=True, timer_active=False,
        serial_retry=False, attempts=rp.BLE_RECONNECT_LIMIT,
        attempt_limit=rp.BLE_RECONNECT_LIMIT)
    assert out["action"] == "exhausted"
    assert out["clear_serial_target"] is False
    net = rp.plan_schedule(
        user_closing=False, auto_reconnect=True, timer_active=False,
        serial_retry=False, attempts=rp.BLE_RECONNECT_LIMIT)
    assert net["action"] == "arm"


def test_plan_try_device_gate_and_open():
    cfg = ("Serial", "COM9", 9600, "8", "None", "1", "None")
    wait = rp.plan_try(
        conn_open=False, user_closing=False, auto_reconnect=True,
        serial_cfg=cfg, device_available=set())
    assert wait["action"] == "wait_device"
    assert wait["bump_attempts"] is True

    open_s = rp.plan_try(
        conn_open=False, user_closing=False, auto_reconnect=True,
        serial_cfg=cfg, device_available={"COM9"})
    assert open_s["action"] == "open"
    assert open_s["bump_attempts"] is True
    assert open_s["toast_try"] is False

    open_n = rp.plan_try(
        conn_open=False, user_closing=False, auto_reconnect=True,
        serial_cfg=None, device_available=set())
    assert open_n["action"] == "open"
    assert open_n["toast_try"] is True

    assert rp.plan_try(
        conn_open=True, user_closing=False, auto_reconnect=True,
        serial_cfg=None, device_available=set())["action"] == "noop"


def test_should_reschedule_after_open_fail():
    assert rp.should_reschedule_after_open_fail(
        serial_cfg=None, serial_target_still_set=False) is True
    assert rp.should_reschedule_after_open_fail(
        serial_cfg=("Serial", "COM1"), serial_target_still_set=True) is True
    assert rp.should_reschedule_after_open_fail(
        serial_cfg=("Serial", "COM1"), serial_target_still_set=False) is False
