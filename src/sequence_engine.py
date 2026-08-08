# -*- coding: utf-8 -*-
"""Sequence runner helpers (Qt-free).

S-2 slice: match / capture / summary / limits live here so tests and a future
headless runner do not need CommTool. Orchestration (QTimer, send, toast)
stays on the main window.
"""
import time

import seq_context
from auto_reply_core import to_int, hit_test

MAX_LOOPS = 100000
MAX_RETRIES = 999
QTIMER_MAX_MS = 0x7FFFFFFF
RETRY_GUARD_MS = 50
RETRY_MAX_QUIET_MS = 2000


def decode_buf(buf, codec="utf-8"):
    """Decode RX bytes for text expect / extractors."""
    enc = "utf-8" if (not codec or codec == "auto") else codec
    try:
        return bytes(buf or b"").decode(enc, errors="replace")
    except Exception:
        return ""


def step_match(step, buf, codec="utf-8"):
    """True when accumulated buf satisfies the step expect (AR hit-test rules)."""
    rule = {
        "match": step.get("expect", ""),
        "match_hex": bool(step.get("expect_hex", False)),
        "mode": to_int(step.get("mode", 0)),
    }
    text = ""
    if not rule["match_hex"]:
        text = decode_buf(buf, codec)
    return hit_test(rule, buf, text)


def capture_vars(step, buf, codec="utf-8"):
    """Run step extractors against buf; return {name: value} (does not touch ctx)."""
    specs = step.get("extract")
    if not specs:
        dsl = step.get("extract_dsl") or step.get("vars") or ""
        specs = seq_context.parse_extract_dsl(dsl)
    specs = seq_context.sanitize_extractors(specs if isinstance(specs, list) else [])
    if not specs:
        return {}
    text = decode_buf(buf, codec)
    return seq_context.extract(buf, specs, text=text, codec=codec)


def apply_capture(ctx, extracted):
    """Update RoundContext (or None) with extracted vars; return extracted."""
    if ctx is not None and extracted:
        ctx.update(extracted)
    return extracted


def clamp_loops(loops):
    return max(1, min(to_int(loops), MAX_LOOPS))


def clamp_retries(retry):
    return min(MAX_RETRIES, max(0, to_int(retry)))


def clamp_timer_ms(ms, minimum=0):
    return min(QTIMER_MAX_MS, max(minimum, to_int(ms)))


def round_snapshot(results, steps, loop_i, round_t0, now=None, dataset_row=None):
    """Build one round record (same shape as CommTool._seq_rounds entries)."""
    now = time.monotonic() if now is None else now
    enabled = [
        results[i]
        for i, s in enumerate(steps)
        if s.get("on", True) and i < len(results)
    ]
    total = sum(1 for r in enabled if r.get("status") != "skip")
    passed = sum(1 for r in enabled if r.get("status") in ("pass", "sent"))
    round_ms = int((now - round_t0) * 1000)
    rec = {
        "round": loop_i + 1,
        "ok": passed,
        "total": total,
        "ms": round_ms,
        "pass": (passed == total),
        "steps": [dict(r) for r in (results or [])],
        "step_defs": [dict(s) for s in (steps or [])],
    }
    if dataset_row:
        rec["csv_row"] = dataset_row.get("number")
        rec["csv_label"] = dataset_row.get("label") or ""
    return rec


def build_summary(
    rounds,
    *,
    loops,
    t0,
    now=None,
    stopped=False,
    started_at="",
    finished_at="",
    version="",
    stop_on_fail=False,
    step_count=0,
    dataset=None,
):
    """Aggregate finished rounds into the export/report summary dict."""
    now = time.monotonic() if now is None else now
    rounds = list(rounds or [])
    rounds_total = len(rounds)
    rounds_pass = sum(1 for r in rounds if r.get("pass"))
    steps_ok = sum(r.get("ok", 0) for r in rounds)
    steps_total = sum(r.get("total", 0) for r in rounds)
    ok = (not stopped) and rounds_total > 0 and rounds_pass == rounds_total
    out = {
        "ok": steps_ok,
        "total": steps_total,
        "ms": int((now - t0) * 1000),
        "pass": ok,
        "loops": loops,
        "rounds": rounds_total,
        "rounds_pass": rounds_pass,
        "round_list": rounds,
        "stopped": bool(stopped),
        "started_at": started_at or "",
        "finished_at": finished_at or "",
        "version": version or "",
        "stop_on_fail": bool(stop_on_fail),
        "step_count": int(step_count or 0),
    }
    if dataset:
        out["csv_path"] = dataset.get("path") or ""
        out["csv_rows"] = len(dataset.get("rows") or [])
    return out


def has_runnable_steps(steps):
    """True if any enabled step has non-empty send or expect."""
    for s in steps or []:
        if not s.get("on", True):
            continue
        if str(s.get("send", "") or "").strip() or str(s.get("expect", "") or "").strip():
            return True
    return False


def next_enabled_index(steps, start=0):
    """First enabled step index at or after start, or len(steps) if none."""
    steps = steps or []
    i = max(0, int(start or 0))
    n = len(steps)
    while i < n and not steps[i].get("on", True):
        i += 1
    return i


def prepare_runtime(step, ctx_map=None):
    """Expand ${vars} in send/expect; return (runtime_step, missing_names)."""
    ctx_map = ctx_map or {}
    step = step or {}
    send_tmpl = step.get("send", "") or ""
    expect_tmpl = step.get("expect", "") or ""
    missing = []
    seen = set()
    for name in (seq_context.missing_vars(send_tmpl, ctx_map)
                 + seq_context.missing_vars(expect_tmpl, ctx_map)):
        if name not in seen:
            seen.add(name)
            missing.append(name)
    runtime = dict(step)
    runtime["send"] = seq_context.expand(send_tmpl, ctx_map)
    runtime["expect"] = seq_context.expand(expect_tmpl, ctx_map)
    return runtime, missing


def step_kind(runtime):
    """Classify prepared step: 'skip' | 'send_only' | 'wait'."""
    send = str((runtime or {}).get("send", "") or "")
    expect = str((runtime or {}).get("expect", "") or "").strip()
    if not send.strip() and not expect:
        return "skip"
    if not expect:
        return "send_only"
    return "wait"


def should_retry(attempt, retry_limit):
    """True when current 1-based attempt may still be retried (attempt <= limit)."""
    return int(attempt) <= clamp_retries(retry_limit)


def plan_retry(step, attempt, now=None, guard_ms=None, max_quiet_ms=None):
    """Build retry timing windows after a failed attempt.

    Returns dict: next_attempt, delay_ms, timer_ms, not_before, quiet_until,
    quiet_deadline (monotonic seconds).
    guard_ms / max_quiet_ms default to module constants; CommTool passes its
    re-exports so tests can patch main_window._SEQ_RETRY_* at runtime.
    """
    now = time.monotonic() if now is None else float(now)
    guard_ms = RETRY_GUARD_MS if guard_ms is None else max(0, int(guard_ms))
    max_quiet_ms = (
        RETRY_MAX_QUIET_MS if max_quiet_ms is None else max(0, int(max_quiet_ms))
    )
    delay_ms = clamp_timer_ms((step or {}).get("delay", 0), minimum=0)
    not_before = now + delay_ms / 1000.0
    quiet_until = now + guard_ms / 1000.0
    quiet_deadline = not_before + max_quiet_ms / 1000.0
    return {
        "next_attempt": int(attempt) + 1,
        "delay_ms": delay_ms,
        "timer_ms": max(delay_ms, guard_ms),
        "not_before": not_before,
        "quiet_until": quiet_until,
        "quiet_deadline": quiet_deadline,
    }


def retry_remain_s(not_before, quiet_until, quiet_deadline, now=None):
    """Seconds until retry is allowed (0 when ready)."""
    now = time.monotonic() if now is None else float(now)
    quiet = min(float(quiet_until), float(quiet_deadline))
    return max(float(not_before), quiet) - now


def more_rounds(loop_i, loops, stop_on_fail, round_ok):
    """After incrementing loop_i: whether another round should run."""
    return int(loop_i) < int(loops) and not (bool(stop_on_fail) and not bool(round_ok))


def continue_after_fail(step):
    """True when on_timeout=continue (keep running next step after fail)."""
    return str((step or {}).get("on_timeout", "stop")) == "continue"


def clip_rx_hex(buf, limit=512):
    """Hex preview of RX buffer, truncated with '...'."""
    rx_hex = bytes(buf or b"").hex()
    if len(rx_hex) > int(limit):
        return rx_hex[: int(limit)] + "..."
    return rx_hex


def detail_from_extracted(extracted, limit=4):
    """Short detail string from captured vars."""
    if not extracted:
        return ""
    keys = list(extracted)[: int(limit)]
    return ",".join("%s=%s" % (k, extracted[k]) for k in keys)


def initial_results(steps):
    """Per-step result stubs for a new round."""
    return [
        {"status": ("pending" if s.get("on", True) else "skip"), "ms": 0, "detail": ""}
        for s in (steps or [])
    ]


def feed_action(status):
    """Decide how RX bytes interact with the current sequence step.

    Returns:
      "extend_quiet" - late RX during retry isolation (bump quiet window)
      "accumulate"   - waiting for expect; append and try match
      "ignore"       - not waiting / not retry
    """
    if status == "retry":
        return "extend_quiet"
    if status == "waiting":
        return "accumulate"
    return "ignore"


def mbm_release_plan(
    *,
    seq_on,
    gen_ok,
    waiting_mbm,
    inflight,
    deadline,
    now=None,
    qtimer_max_ms=None,
):
    """After Modbus in-flight ends, decide wait vs start sequence step 0.

    Returns dict with action:
      "noop" | "still_inflight" | "wait" | "ready"
    and delay_ms when action is "wait".
    """
    if not seq_on or not gen_ok or not waiting_mbm:
        return {"action": "noop"}
    if inflight is not None:
        return {"action": "still_inflight"}
    now = time.monotonic() if now is None else float(now)
    remain = float(deadline) - now
    if remain > 0:
        cap = QTIMER_MAX_MS if qtimer_max_ms is None else int(qtimer_max_ms)
        delay = min(cap, max(1, int(remain * 1000) + 1))
        return {"action": "wait", "delay_ms": delay}
    return {"action": "ready"}


def fail_outcome(attempt, retry_limit):
    """After a step fail: "retry" if budget remains, else "fail"."""
    return "retry" if should_retry(attempt, retry_limit) else "fail"
