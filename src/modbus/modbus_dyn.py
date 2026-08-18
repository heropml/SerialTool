# -*- coding: utf-8 -*-
"""Dynamic register models + Modbus exception injection (Qt-free).

Used by ModbusSlave for P1-2: values can grow/oscillate, and exception
PDUs can be injected by function/address policy.
"""
from __future__ import print_function

import math
import random
import time

MODES = ("static", "inc", "dec", "random", "sine", "ramp")
EXC_MODES = ("always", "once", "n")


def _safe_period_ms(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = 1000
    return max(1, n or 1000)


def _safe_phase(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _clamp_u16(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    # Clamp, never wrap: a hand-written min:-5 must not come back as 65531.
    return max(0, min(0xFFFF, n))


def normalize_dynamic(rec):
    """Normalize one dynamic-value rule dict."""
    rec = rec or {}
    mode = str(rec.get("mode") or "static").lower()
    if mode not in MODES:
        mode = "static"
    space = str(rec.get("space") or "holding").lower()
    if space not in ("holding", "input", "coils", "discrete"):
        space = "holding"
    try:
        addr = int(rec.get("addr", 0))
    except (TypeError, ValueError):
        addr = 0
    addr = max(0, min(0xFFFF, addr))
    out = {
        "space": space,
        "addr": addr,
        "mode": mode,
        "step": _clamp_u16(rec.get("step", 1)) or 1,
        "min": _clamp_u16(rec.get("min", 0)),
        "max": _clamp_u16(rec.get("max", 0xFFFF)),
        "period_ms": _safe_period_ms(rec.get("period_ms", 1000)),
        "phase": _safe_phase(rec.get("phase", 0)),
        "seed": rec.get("seed"),
        # Fixed value for static mode; None = do not override the static table.
        "value": None if rec.get("value") in (None, "") else _clamp_u16(rec.get("value")),
    }
    if out["min"] > out["max"]:
        out["min"], out["max"] = out["max"], out["min"]
    return out


def normalize_dynamics(items):
    out = []
    for it in (items or []):
        if isinstance(it, dict):
            out.append(normalize_dynamic(it))
    return out[:256]


def normalize_exception_policy(rec):
    """Normalize exception-injection policy."""
    rec = rec or {}
    try:
        code = int(rec.get("code", 0x04))
    except (TypeError, ValueError):
        code = 0x04
    code = max(1, min(255, code))
    mode = str(rec.get("mode") or "always").lower()
    if mode not in EXC_MODES:
        mode = "always"
    try:
        n = int(rec.get("n", 1))
    except (TypeError, ValueError):
        n = 1
    funcs = []
    for f in (rec.get("funcs") or []):
        try:
            funcs.append(int(f) & 0xFF)
        except (TypeError, ValueError):
            pass
    addrs = []
    for a in (rec.get("addrs") or []):
        try:
            addrs.append(max(0, min(0xFFFF, int(a))))
        except (TypeError, ValueError):
            pass
    return {
        "enabled": bool(rec.get("enabled", False)),
        "code": code,
        "mode": mode,
        "n": max(1, min(10000, n)),
        "funcs": funcs,   # empty = any function
        "addrs": addrs,   # empty = any address (checked against PDU start)
        "_hits": 0,
    }


class DynamicEngine(object):
    """Compute live values for (space, addr) keys."""

    def __init__(self, rules=None, now=None):
        self.rules = {}  # (space, addr) -> rule
        self._state = {}  # (space, addr) -> current int/bool
        self._overrides = {}  # sticky write overrides until reset()
        self._t0 = float(now if now is not None else time.monotonic())
        self._rng = {}
        for r in normalize_dynamics(rules):
            key = (r["space"], r["addr"])
            self.rules[key] = r
            self._state[key] = r["min"]
            seed = r.get("seed")
            if seed is not None:
                self._rng[key] = random.Random(seed)

    def reset(self, now=None):
        self._t0 = float(now if now is not None else time.monotonic())
        self._overrides.clear()
        self._state.clear()          # 同时清掉 random 模式的 ("__b", key) 周期标记
        for key, r in self.rules.items():
            self._state[key] = r["min"]
            seed = r.get("seed")
            if seed is not None:
                # seed 的意义就是可复现：reset 后必须回到序列开头，否则续用旧状态
                self._rng[key] = random.Random(seed)

    def value(self, space, addr, fallback=0, now=None):
        key = (space, int(addr))
        if key in self._overrides:
            v = self._overrides[key]
            if space in ("coils", "discrete"):
                return bool(int(v) & 1)
            return int(v) & 0xFFFF
        rule = self.rules.get(key)
        if rule is None:
            return fallback
        if rule["mode"] == "static":
            # No value configured -> stay out of the way (original behaviour).
            v = rule.get("value")
            if v is None:
                return fallback
            if space in ("coils", "discrete"):
                return bool(int(v) & 1)
            return int(v) & 0xFFFF
        now = float(now if now is not None else time.monotonic())
        elapsed = max(0.0, now - self._t0)
        lo, hi = rule["min"], rule["max"]
        if hi <= lo:
            v = lo
            if space in ("coils", "discrete"):
                return bool(int(v) & 1)
            return int(v) & 0xFFFF
        span = hi - lo
        mode = rule["mode"]
        if mode == "inc":
            steps = int(elapsed * 1000.0 / rule["period_ms"])
            v = lo + (steps * rule["step"]) % (span + 1)
        elif mode == "dec":
            steps = int(elapsed * 1000.0 / rule["period_ms"])
            v = hi - (steps * rule["step"]) % (span + 1)
        elif mode == "random":
            rng = self._rng.get(key) or random
            # re-roll each period boundary
            bucket = int(elapsed * 1000.0 / rule["period_ms"])
            if self._state.get(("__b", key)) != bucket:
                self._state[("__b", key)] = bucket
                self._state[key] = rng.randint(lo, hi)
            v = self._state.get(key, lo)
        elif mode == "sine":
            # map sin to [lo, hi]
            period_s = rule["period_ms"] / 1000.0
            ang = 2.0 * math.pi * (elapsed / period_s) + rule["phase"]
            frac = 0.5 * (1.0 + math.sin(ang))
            v = lo + int(round(frac * span))
        elif mode == "ramp":
            period_s = rule["period_ms"] / 1000.0
            phase = (elapsed / period_s) % 1.0
            v = lo + int(round(phase * span))
        else:
            v = fallback
        if space in ("coils", "discrete"):
            return bool(int(v) & 1)
        return int(v) & 0xFFFF

    def note_write(self, space, addr, value):
        """Sticky override after master write; cleared by reset()."""
        key = (space, int(addr))
        if key in self.rules:
            self._state[key] = value
            self._overrides[key] = value


class ExceptionInjector(object):
    def __init__(self, policy=None):
        self.policy = normalize_exception_policy(policy)

    def reset(self):
        self.policy["_hits"] = 0

    def should_raise(self, func, start_addr=None):
        p = self.policy
        if not p.get("enabled"):
            return None
        if p["funcs"] and (int(func) & 0xFF) not in p["funcs"]:
            return None
        if p["addrs"]:
            if start_addr is None:
                return None
            # start_addr 可以是多个候选地址（如 FC23 的读段/写段），任一命中即算命中；
            # 不能分多次调用本方法来试，once/n 模式的计数会被重复消耗。
            cands = start_addr if isinstance(start_addr, (tuple, list, set)) else (start_addr,)
            if not any(int(a) in p["addrs"] for a in cands if a is not None):
                return None
        mode = p["mode"]
        hits = int(p.get("_hits", 0))
        if mode == "once" and hits >= 1:
            return None
        if mode == "n" and hits >= int(p.get("n", 1)):
            return None
        # Only count for once/n so switching from always later still works.
        if mode in ("once", "n"):
            p["_hits"] = hits + 1
        return int(p["code"])
