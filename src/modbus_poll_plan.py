# -*- coding: utf-8 -*-
"""Modbus master poll precheck + response validate (Qt-free).

Returns i18n *keys* (not localized strings) so CommTool / CLI can translate.
"""
from __future__ import annotations

import modbus_master as mbm
from modbus_timing import span_bad as _span_bad


def poll_reject_reason(rule, variant):
    """Return error key if this poll must not be sent, else None."""
    r = rule if isinstance(rule, dict) else {}
    variant = str(variant or "")
    if (r.get("unit") is None or r.get("addr") is None or r.get("period") is None
            or (r.get("func") in mbm.READ_FUNCS + (0x17,) and r.get("qty") is None)
            or (r.get("func") == 0x17 and r.get("write_addr") is None)
            or (variant in ("rtu", "ascii")
                and r.get("unit") is not None and r["unit"] > 247)):
        return "mbm_st_badparam"
    if _span_bad(r):
        return "mbm_st_badparam"
    if r.get("func") == 0x08 and (
            r.get("diag_sub") is None or r.get("diag_data") is None):
        return "mbm_st_badparam"
    if r.get("func") == 0x16 and (
            r.get("and_mask") is None or r.get("or_mask") is None):
        return "mbm_st_badparam"
    if r.get("func") == 0x2B and (
            r.get("read_code") is None or r.get("object_id") is None):
        return "mbm_st_badparam"
    if ((r.get("func") in mbm.WRITE_SINGLE and r.get("wval") is None)
            or (r.get("func") in mbm.WRITE_MULTI and not r.get("wvals"))):
        return "mbm_st_noval"
    if variant in ("rtu", "ascii") and r.get("unit") == 0:
        if r.get("func") not in (mbm.WRITE_SINGLE + mbm.WRITE_MULTI + (0x16,)):
            return "mbm_st_broadcast_nowrite"
    return None


def build_poll_arg(rule):
    """Build request arg for a normalized poll rule.

    Returns (arg, reject_key). reject_key is set when FC23 has empty writes.
    """
    r = rule if isinstance(rule, dict) else {}
    func = r.get("func")
    if func in mbm.READ_FUNCS:
        return r.get("qty"), None
    if func in mbm.WRITE_MULTI:
        return r.get("wvals"), None
    if func == 0x08:
        return (int(r.get("diag_sub") or 0), int(r.get("diag_data"))), None
    if func == 0x16:
        return (int(r["and_mask"]), int(r["or_mask"])), None
    if func == 0x2B:
        return ({
            "mei": 0x0E,
            "read_code": int(r.get("read_code") or 1),
            "object_id": int(r.get("object_id") or 0),
        }, None)
    if func in (0x0B, 0x11):
        return 0, None
    if func == 0x17:
        arg = r.get("rw") or {
            "read_addr": r.get("addr"),
            "read_qty": r.get("qty"),
            "write_addr": r.get("write_addr", r.get("addr")),
            "write_vals": r.get("wvals") or [],
        }
        if not arg.get("write_vals"):
            return None, "mbm_st_noval"
        return arg, None
    return r.get("wval"), None


def validate_response(info, result):
    """Semantic check for a parsed response. Return error key or None."""
    info = info or {}
    result = result or {}
    if "regs" in result:
        if len(result["regs"]) != info.get("qty"):
            return "mbm_st_badresp"
    elif "bits" in result:
        qty = int(info.get("qty") or 0)
        expected = ((qty + 7) // 8) * 8
        if len(result["bits"]) != expected:
            return "mbm_st_badresp"
    elif "echo" in result:
        exp = info.get("exp_write")
        if exp is not None and tuple(result["echo"]) != tuple(exp):
            return "mbm_st_badresp"
    elif "diag" in result:
        exp = info.get("exp_diag")
        if exp is not None:
            sub, data = result["diag"]
            if sub != exp[0] or (exp[0] == 0 and data != exp[1]):
                return "mbm_st_badresp"
    return None
