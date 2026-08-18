# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R45 sequence_engine feed/mbm/fail helpers."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import sequence_engine as se


def test_feed_action():
    assert se.feed_action("retry") == "extend_quiet"
    assert se.feed_action("waiting") == "accumulate"
    assert se.feed_action("pass") == "ignore"
    assert se.feed_action(None) == "ignore"


def test_mbm_release_plan_branches():
    assert se.mbm_release_plan(
        seq_on=False, gen_ok=True, waiting_mbm=True,
        inflight=None, deadline=0)["action"] == "noop"
    assert se.mbm_release_plan(
        seq_on=True, gen_ok=False, waiting_mbm=True,
        inflight=None, deadline=0)["action"] == "noop"
    assert se.mbm_release_plan(
        seq_on=True, gen_ok=True, waiting_mbm=False,
        inflight=None, deadline=0)["action"] == "noop"
    assert se.mbm_release_plan(
        seq_on=True, gen_ok=True, waiting_mbm=True,
        inflight=object(), deadline=0)["action"] == "still_inflight"

    now = 1000.0
    wait = se.mbm_release_plan(
        seq_on=True, gen_ok=True, waiting_mbm=True,
        inflight=None, deadline=now + 0.25, now=now, qtimer_max_ms=50)
    assert wait["action"] == "wait"
    assert wait["delay_ms"] == 50

    ready = se.mbm_release_plan(
        seq_on=True, gen_ok=True, waiting_mbm=True,
        inflight=None, deadline=now - 0.01, now=now)
    assert ready["action"] == "ready"


def test_fail_outcome():
    assert se.fail_outcome(1, 1) == "retry"
    assert se.fail_outcome(2, 1) == "fail"
    assert se.fail_outcome(1, 0) == "fail"
