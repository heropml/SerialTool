# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R14/R15/R16 extractions."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import auto_reply_core as ar
import connection_presets as cp
import io_stats as io
import log_naming as ln


class _FixedRng(object):
    def __init__(self, values):
        self._values = list(values)

    def random(self):
        return self._values.pop(0)


def test_fmt_bytes_and_rate():
    assert io.fmt_bytes(500) == "500 B"
    assert io.fmt_bytes(2048).endswith("KB")
    assert io.fmt_bytes(2 * 1024 * 1024).endswith("MB")
    assert io.fmt_rate(100).endswith("/s")
    assert io.fmt_bytes(None) == "0 B"


def test_format_stat_bar():
    line = io.format_stat_bar("RX", 100, 3, 50, 2, 0, "pkts", "pps")
    assert line.startswith("RX ")
    assert "100 B" in line and "3" in line and "pps" in line
    err = io.format_stat_bar("TX", 0, 0, 0, 0, 5, "pkts", "pps")
    assert "5" in err and "\u26a0" in err


def test_reply_hex_and_compose():
    assert ar.reply_hex_bytes("AA BB") == b"\xaa\xbb"
    assert ar.reply_hex_bytes("0xAA //c\nBB") == b"\xaa\xbb"
    assert ar.reply_hex_bytes("AA B") is None
    assert ar.reply_bytes("hi", False, lambda t: t.encode("ascii")) == b"hi"
    frame = ar.compose_frame(
        "01 02", True, [], 1,
        lambda t: t.encode("ascii"), ar.compute_checksum)
    assert frame.startswith(b"\x01\x02")
    assert len(frame) == 3  # + SUM8


def test_apply_cs_segs_and_fault():
    buf = ar.apply_cs_segs(bytearray(b"\x01\x02\x00"), [
        {"algo": 1, "start": 0, "end": 1, "at": 2},
    ], ar.compute_checksum)
    assert len(buf) == 3
    out, tags = ar.apply_fault(
        b"\x01\x02\x03", {"on": True, "drop": 100}, rng=_FixedRng([0.0]))
    assert out is None and tags == ["drop"]
    # random order: drop check, badlen, badcrc
    out, tags = ar.apply_fault(
        b"\x01\x02\x03",
        {"on": True, "drop": 0, "badlen": 100, "badcrc": 100},
        rng=_FixedRng([0.99, 0.0, 0.0]))
    assert tags == ["badlen", "badcrc"]
    assert out is not None and len(out) == 2


def test_conn_token_and_signatures():
    assert ln.conn_token("Serial", ("Serial", "COM7", 115200), "Serial", "TCP Client") == "COM7"
    assert ln.conn_token(
        "TCP Client", ("TCP Client", "1.2.3.4", 80), "Serial", "TCP Client") == "1.2.3.4_80"
    assert ln.conn_token("UDP", ("UDP",), "Serial", "TCP Client") == "UDP"
    assert ln.safe_enter_idx("2") == 2
    assert ln.safe_enter_idx("9") == 0
    assert cp.serial_signature("Serial", "COM1", 9600, "8", "None", "1", "None")[1] == "COM1"
    assert cp.tcp_client_signature("TCP Client", "a", 1) == ("TCP Client", "a", 1)
    assert cp.proto_only_signature("UDP") == ("UDP",)
