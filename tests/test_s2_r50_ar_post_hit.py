# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R50 auto_reply_gate post-hit plan."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auto_reply_gate as gate


def test_reply_path_and_post_hit():
    assert gate.reply_path({"script": "x=1", "script_on": True}) == "script"
    assert gate.reply_path({"script": "", "reply_hex": False}) == "template"

    abort = gate.post_hit_plan(
        {"goto": "A"}, sm_on=True, parts=[], from_script=True, script_err="boom")
    assert abort["action"] == "abort"
    assert abort["note_script_err"] is True

    sched = gate.post_hit_plan(
        {"goto": "A", "reply_hex": False, "cs": 1, "cs_segs": [{"a": 1}]},
        sm_on=True, parts=[b"hi"], from_script=False)
    assert sched["action"] == "schedule"
    assert sched["hexmode"] is False
    assert sched["cs"] == 1
    assert sched["arm_goto"] is True

    script_ok = gate.post_hit_plan(
        {"goto": ""}, sm_on=True, parts=[b"x"], from_script=True)
    assert script_ok["hexmode"] is True
    assert script_ok["cs"] == 0
    assert script_ok["arm_goto"] is False

    tok = object()
    assert gate.clear_pending_on_schedule_error(pending=tok, current_pending=tok)
    assert not gate.clear_pending_on_schedule_error(pending=tok, current_pending=object())
