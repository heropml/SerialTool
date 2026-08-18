# -*- coding: utf-8 -*-
"""Qt-free unit tests for sequence_engine (S-2)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import seq_context
from automation import sequence_engine as se


def test_clamp_loops_and_retries():
    assert se.clamp_loops(0) == 1
    assert se.clamp_loops(-3) == 1
    assert se.clamp_loops(se.MAX_LOOPS + 9) == se.MAX_LOOPS
    assert se.clamp_retries(-1) == 0
    assert se.clamp_retries(se.MAX_RETRIES + 1) == se.MAX_RETRIES
    assert se.clamp_timer_ms(-5) == 0
    assert se.clamp_timer_ms(se.QTIMER_MAX_MS + 1) == se.QTIMER_MAX_MS


def test_step_match_hex_and_text():
    assert se.step_match({"expect": "0103", "expect_hex": True, "mode": 0}, b"\x01\x03\xaa")
    assert not se.step_match({"expect": "0103", "expect_hex": True, "mode": 1}, b"\x01\x03\xaa")
    assert se.step_match({"expect": "OK", "expect_hex": False, "mode": 0}, b"xxOKyy")
    assert se.step_match({"expect": "OK", "expect_hex": False, "mode": 2}, b"OKrest")


def test_capture_vars_and_apply():
    step = {"extract_dsl": "raw=hex:0:1"}
    extracted = se.capture_vars(step, b"\x2a\x00")
    assert extracted.get("raw") == "2a"
    ctx = seq_context.RoundContext()
    se.apply_capture(ctx, extracted)
    assert ctx.get("raw") == "2a"


def test_round_snapshot_and_summary():
    steps = [{"on": True}, {"on": True}, {"on": False}]
    results = [
        {"status": "pass", "ms": 10},
        {"status": "fail", "ms": 20},
        {"status": "skip", "ms": 0},
    ]
    snap = se.round_snapshot(results, steps, loop_i=0, round_t0=100.0, now=100.5)
    assert snap["round"] == 1
    assert snap["ok"] == 1
    assert snap["total"] == 2
    assert snap["pass"] is False
    assert snap["ms"] == 500

    rounds = [
        {"ok": 2, "total": 2, "pass": True, "ms": 100},
        {"ok": 1, "total": 2, "pass": False, "ms": 200},
    ]
    summary = se.build_summary(
        rounds, loops=3, t0=1.0, now=2.0, stopped=False, version="t", step_count=2
    )
    assert summary["ok"] == 3
    assert summary["total"] == 4
    assert summary["rounds"] == 2
    assert summary["rounds_pass"] == 1
    assert summary["pass"] is False
    assert summary["ms"] == 1000
    assert summary["version"] == "t"

    stopped = se.build_summary(rounds[:1], loops=1, t0=0.0, now=0.1, stopped=True)
    assert stopped["pass"] is False
    assert stopped["stopped"] is True


def test_has_runnable_and_next_enabled():
    assert not se.has_runnable_steps([])
    assert not se.has_runnable_steps([{"on": True, "send": "", "expect": ""}])
    assert se.has_runnable_steps([{"on": True, "send": "A", "expect": ""}])
    steps = [{"on": False}, {"on": True}, {"on": False}, {"on": True}]
    assert se.next_enabled_index(steps, 0) == 1
    assert se.next_enabled_index(steps, 2) == 3
    assert se.next_enabled_index(steps, 4) == 4


def test_prepare_runtime_and_step_kind():
    runtime, missing = se.prepare_runtime(
        {"send": "HI ${name}", "expect": "OK"}, {"name": "X"}
    )
    assert missing == []
    assert runtime["send"] == "HI X"
    assert se.step_kind(runtime) == "wait"
    runtime, missing = se.prepare_runtime({"send": "${missing}", "expect": ""}, {})
    assert "missing" in missing
    assert se.step_kind({"send": "", "expect": ""}) == "skip"
    assert se.step_kind({"send": "A", "expect": ""}) == "send_only"


def test_retry_plan_and_more_rounds():
    assert se.should_retry(1, 0) is False
    assert se.should_retry(1, 1) is True
    plan = se.plan_retry({"delay": 100, "retry": 2}, attempt=1, now=10.0)
    assert plan["next_attempt"] == 2
    assert plan["delay_ms"] == 100
    assert plan["timer_ms"] == max(100, se.RETRY_GUARD_MS)
    assert plan["not_before"] == 10.1
    remain = se.retry_remain_s(10.2, 10.05, 12.0, now=10.0)
    assert abs(remain - 0.2) < 1e-9
    assert se.more_rounds(1, 3, False, False) is True
    assert se.more_rounds(1, 3, True, False) is False
    assert se.continue_after_fail({"on_timeout": "continue"}) is True
    assert se.continue_after_fail({}) is False
    assert se.clip_rx_hex(b"\x00" * 300).endswith("...")
    assert se.detail_from_extracted({"a": 1, "b": 2}) == "a=1,b=2"
    assert se.initial_results([{"on": True}, {"on": False}])[1]["status"] == "skip"
