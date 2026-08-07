# -*- coding: utf-8 -*-
"""Qt-free tests for auto_reply_core config normalizers (S-2 R10)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auto_reply_core as ar


def test_state_tokens():
    assert ar.state_tokens("") == []
    assert ar.state_tokens(None) == []
    assert ar.state_tokens("A, B ,WAIT ACK") == ["A", "B", "WAIT ACK"]


def test_norm_frame():
    cfg = ar.norm_frame({
        "on": 1, "header": "AA 55", "len_off": -3, "len_width": 9,
        "len_be": True, "len_extra": "2",
    })
    assert cfg["on"] is True
    assert cfg["header"] == "AA 55"
    assert cfg["len_off"] == 0
    assert cfg["len_width"] == 2  # invalid -> default
    assert cfg["len_be"] is True
    assert cfg["len_extra"] == 2
    assert cfg["_header"] == bytes.fromhex("AA55")
    bad = ar.norm_frame({"header": "ZZ"})
    assert bad["_header"] == b""


def test_norm_fault():
    cfg = ar.norm_fault({"on": True, "drop": 150, "badcrc": -1, "badlen": "40"})
    assert cfg == {"on": True, "drop": 100, "badcrc": 0, "badlen": 40}


def test_norm_sm():
    assert ar.norm_sm({"on": 1, "init": "  IDLE  "}) == {"on": True, "init": "IDLE"}
    assert ar.norm_sm({}) == {"on": False, "init": ""}


def test_norm_modbus_variant_and_slaves():
    cfg = ar.norm_modbus({
        "on": True,
        "addr": 300,
        "variant": "ASCII",
        "holding": {"1": 0x1234, "bad": 9},
        "slaves": [
            {"addr": 2, "variant": "ignored", "coils": {"0": 1},
             "server_id": "S2", "dynamics": "nope", "exception": []},
            "skip-me",
        ],
    })
    assert cfg["on"] is True
    assert cfg["addr"] == 247
    assert cfg["variant"] == "ascii"
    assert cfg["holding"] == {"1": 0x1234}
    assert len(cfg["slaves"]) == 1
    s0 = cfg["slaves"][0]
    assert s0["addr"] == 2
    assert s0["coils"] == {"0": True}
    assert s0["server_id"] == "S2"
    assert s0["dynamics"] == []
    assert s0["exception"] == {}
