# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R17 subst_reply + R18 config_keys."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auto_reply_core as ar
import config_keys as ck


def test_subst_rN_and_range_hex():
    data = bytes([0x10, 0x20, 0x30, 0x40])
    out, seq = ar.subst_reply("{r0} {r1-2}", data, True, seq=0, ts_ms=0)
    assert out == "10 20 30"
    assert seq == 0


def test_subst_arith_and_seq():
    data = b"\x05\x0A"
    out, seq = ar.subst_reply("{r0+1}|{r1^0x0F}|{seq}", data, True, seq=7, ts_ms=0)
    assert "06" in out and "05" in out  # 5+1=6, 0x0A^0x0F=5
    assert seq == 8
    assert "08" in out


def test_subst_ts_and_text_mode():
    data = b"AB"
    out, seq = ar.subst_reply("{r0}{ts}", data, False, seq=0, ts_ms=0x01020304)
    assert out.startswith("A")
    # ts bytes as chars in text mode
    assert len(out) == 1 + 4


def test_build_parts_advances_seq_per_segment():
    rule = {"reply": "{seq}|{seq}", "reply_hex": True}
    parts, seq = ar.build_parts(rule, b"", seq=0, ts_ms=0)
    assert parts == ["01", "02"]
    assert seq == 2


def test_cfg_keys_core_members():
    assert "net_proto" in ck.CFG_KEYS
    assert "autoreply_rules" in ck.CFG_KEYS
    assert "sequence_loops" in ck.CFG_KEYS
    assert "sequence_stop_on_fail" in ck.CFG_KEYS
    assert "sequence_split" in ck.CFG_KEYS
    assert "terminal_mode" in ck.CFG_KEYS
    assert "frame_builder_split" in ck.CFG_KEYS
    assert "modbus_master_echo" in ck.CFG_KEYS
    assert "send_history" not in ck.CFG_KEYS  # intentionally excluded
