# -*- coding: utf-8 -*-
"""Qt-free tests for view_format.timestamp_prefix + connection_presets.parse_port."""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project import connection_presets as cp
from protocol import view_format as vf


def test_parse_port():
    assert cp.parse_port("8080") == 8080
    assert cp.parse_port(" 1 ") == 1
    assert cp.parse_port("65535") == 65535
    assert cp.parse_port("0") is None
    assert cp.parse_port("65536") is None
    assert cp.parse_port("abc") is None
    assert cp.parse_port("") is None
    assert cp.parse_port(None) is None


def test_timestamp_absolute_and_arrows():
    now = datetime(2026, 8, 7, 15, 30, 45, 123000)
    tx, _ = vf.timestamp_prefix("absolute", "tx", now=now, wall_time=1.0, anchor=None)
    rx, _ = vf.timestamp_prefix("absolute", "rx", now=now, wall_time=1.0, anchor=None)
    assert tx == "[2026/08/07 15:30:45.123] " + vf.ARROW_TX
    assert rx == "[2026/08/07 15:30:45.123] " + vf.ARROW_RX
    assert tx.endswith("\u2192 ") or tx.endswith(vf.ARROW_TX)


def test_timestamp_time_epoch_relative():
    now = datetime(2026, 1, 2, 3, 4, 5, 6000)
    t, a = vf.timestamp_prefix("time", "rx", now=now, wall_time=10.0, anchor=None)
    assert t.startswith("[03:04:05.006] ")
    assert a is None
    e, a = vf.timestamp_prefix("epoch", "tx", now=now, wall_time=1700000000.25, anchor=None)
    assert e.startswith("[1700000000.250] ")
    r1, a1 = vf.timestamp_prefix("relative", "rx", now=now, wall_time=100.0, anchor=None)
    assert r1.startswith("[+0.000] ")
    assert a1 == 100.0
    r2, a2 = vf.timestamp_prefix("relative", "tx", now=now, wall_time=100.5, anchor=a1)
    assert r2.startswith("[+0.500] ")
    assert a2 == 100.0
