# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R19/R20/R21."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auto_reply_core as ar
import multi_send as ms
import view_format as vf


def test_multi_send_load_and_cycle():
    raw = json.dumps([{"name": "G", "items": [
        {"data": "AA", "checked": True, "hex": True, "nl": 0, "cs": 0, "delay": 50},
        {"data": "", "checked": True},
        {"data": "BB", "checked": False},
    ]}])
    groups, ok = ms.load_groups(raw, "", "Default")
    assert ok and len(groups) == 1
    seq = ms.build_cycle_seq(ms.active_items(groups, 0))
    assert seq == [("AA", True, 0, 0, 50)]
    groups2, ok2 = ms.load_groups("", json.dumps([{"data": "X"}]), "Default")
    assert ok2 is False and groups2[0]["items"][0]["data"] == "X"


def test_state_ok_and_next_state():
    assert ar.state_ok(False, "A", "B") is True
    assert ar.state_ok(True, "", "ANY") is True
    assert ar.state_ok(True, "IDLE, WAIT", "WAIT") is True
    assert ar.state_ok(True, "IDLE", "WAIT") is False
    assert ar.next_state(True, {"goto": "DONE"}, "IDLE") == "DONE"
    assert ar.next_state(True, {"goto": ""}, "IDLE") == "IDLE"
    assert ar.next_state(False, {"goto": "DONE"}, "IDLE") == "IDLE"


def test_view_mode_helpers():
    assert vf.view_mode_of_state(True, True, True) == "dump"
    assert vf.view_mode_of_state(False, True, True) == "num"
    assert vf.view_mode_of_state(False, False, True) == "hex"
    assert vf.view_mode_of_state(False, False, False) == "text"
    assert vf.view_extra_index("num") == 3
    assert vf.view_extra_index("hex", terminal_on=True) == 0
