# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R44 modbus_poll_plan."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modbus import modbus_master as mbm
from modbus import modbus_poll_plan as plan


def _rule(**kw):
    base = {
        "unit": 1, "addr": 0, "period": 1000, "func": 0x03, "qty": 2,
    }
    base.update(kw)
    return mbm.normalize_poll(base)


def test_poll_reject_badparam_and_noval():
    assert plan.poll_reject_reason(_rule(unit=None), "rtu") == "mbm_st_badparam"
    assert plan.poll_reject_reason(_rule(qty=None), "rtu") == "mbm_st_badparam"
    assert plan.poll_reject_reason(
        _rule(func=0x06, wval=None), "rtu") == "mbm_st_noval"
    assert plan.poll_reject_reason(
        _rule(func=0x10, wvals=[]), "rtu") == "mbm_st_noval"


def test_poll_reject_broadcast_nowrite():
    r = _rule(unit=0, func=0x03, qty=1)
    assert plan.poll_reject_reason(r, "rtu") == "mbm_st_broadcast_nowrite"
    w = _rule(unit=0, func=0x06, wval=1)
    assert plan.poll_reject_reason(w, "rtu") is None


def test_poll_reject_diag_masks():
    bad = mbm.normalize_poll({
        "unit": 1, "addr": 0, "period": 1000, "func": 0x08, "diag_sub": "",
    })
    # present-but-empty diag_sub becomes None after normalize when invalid;
    # missing diag_sub defaults to 0. Force None on the normalized dict.
    bad["diag_sub"] = None
    assert plan.poll_reject_reason(bad, "rtu") == "mbm_st_badparam"
    bad16 = _rule(func=0x16, and_mask=None, or_mask=1)
    assert plan.poll_reject_reason(bad16, "rtu") == "mbm_st_badparam"
    ok = _rule(func=0x08, diag_sub=0, diag_data=0x1234)
    assert plan.poll_reject_reason(ok, "rtu") is None


def test_build_poll_arg_variants():
    arg, err = plan.build_poll_arg(_rule(func=0x03, qty=4))
    assert err is None and arg == 4
    arg, err = plan.build_poll_arg(_rule(func=0x08, diag_sub=0, diag_data=7))
    assert err is None and arg == (0, 7)
    arg, err = plan.build_poll_arg(
        _rule(func=0x17, qty=2, write_addr=10, wvals=[]))
    assert err == "mbm_st_noval"
    arg, err = plan.build_poll_arg(
        _rule(func=0x17, qty=2, write_addr=10, wvals=[1, 2]))
    assert err is None and arg["write_vals"] == [1, 2]


def test_validate_response_regs_bits_echo_diag():
    assert plan.validate_response({"qty": 2}, {"regs": [1, 2]}) is None
    assert plan.validate_response({"qty": 2}, {"regs": [1]}) == "mbm_st_badresp"
    assert plan.validate_response(
        {"qty": 8}, {"bits": [0] * 8}) is None
    assert plan.validate_response(
        {"qty": 8}, {"bits": [0] * 7}) == "mbm_st_badresp"
    assert plan.validate_response(
        {"exp_write": (1, 0xFF00)}, {"echo": (1, 0xFF00)}) is None
    assert plan.validate_response(
        {"exp_write": (1, 0xFF00)}, {"echo": (1, 0)}) == "mbm_st_badresp"
    assert plan.validate_response(
        {"exp_diag": (0, 9)}, {"diag": (0, 9)}) is None
    assert plan.validate_response(
        {"exp_diag": (0, 9)}, {"diag": (0, 1)}) == "mbm_st_badresp"
    assert plan.validate_response(
        {"exp_diag": (1, 9)}, {"diag": (1, 99)}) is None
