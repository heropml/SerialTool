# -*- coding: utf-8 -*-
"""Protocol stream assembler: sticky/split packets, resync, session isolation."""
from __future__ import print_function

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import binproto
import frame_stream
from parse_diag import ParseDiagnostics

# AA BB | len(1) | data | sum(1)  → total = L + 4
_HDR = b"\xAA\xBB"
_OFF, _W, _EXTRA = 2, 1, 4


def _frame(payload):
    payload = bytes(payload)
    return _HDR + bytes([len(payload)]) + payload + b"\x7E"


def test_scan_matches_iter_length_frames():
    cases = [
        b"",
        _frame(b"\x11\x22\x33"),
        b"\x00\x01" + _frame(b"\x01") + _frame(b"\x02\x03"),
        _frame(b"\x11\x22\x33")[:4],
        _HDR,  # header only
        b"\xAA",  # partial header
    ]
    for buf in cases:
        a, ra = binproto.iter_length_frames(buf, _HDR, _OFF, _W, _EXTRA)
        b, rb, _st = binproto.scan_length_frames(buf, _HDR, _OFF, _W, _EXTRA)
        assert a == b, buf
        assert ra == rb, buf


def test_empty_header_passthrough():
    buf = b"\x01\x02\x03"
    frames, rest = binproto.iter_length_frames(buf, b"", 0, 1, 0)
    assert frames == []
    assert rest == buf


def test_assembler_sticky_two_frames():
    a = frame_stream.FrameStreamAssembler(_HDR, _OFF, _W, _EXTRA)
    f1, f2 = _frame(b"\x01"), _frame(b"\x02\x03")
    out = a.feed(f1 + f2)
    assert out == [f1, f2]
    assert a.last_stats["waiting"] == 0


def test_assembler_split_across_chunks():
    a = frame_stream.FrameStreamAssembler(_HDR, _OFF, _W, _EXTRA)
    full = _frame(b"\x11\x22\x33")
    assert a.feed(full[:3]) == []
    assert a.last_stats["waiting"] == 3
    assert a.feed(full[3:]) == [full]
    assert a.last_stats["waiting"] == 0


def test_assembler_header_spans_chunks():
    a = frame_stream.FrameStreamAssembler(_HDR, _OFF, _W, _EXTRA)
    full = _frame(b"\xAA")
    assert a.feed(b"\xAA") == []          # half header
    assert a.feed(full[1:]) == [full]


def test_assembler_bad_length_resync():
    # header AA, length at offset 1 (1 byte), extra 0 → total = L; need = 2.
    hdr = b"\xAA"
    good = b"\xAA\x03\x11"        # L=3, extra=0 → 3-byte frame
    junk = b"\xAA\x00"           # L=0, total=0 < need=2 → skip header byte
    a = frame_stream.FrameStreamAssembler(hdr, 1, 1, 0, max_frame=64)
    out = a.feed(junk + good)
    assert good in out
    assert a.last_stats["bad_length"] >= 1


def test_assembler_oversize_resync():
    a = frame_stream.FrameStreamAssembler(_HDR, _OFF, _W, _EXTRA, max_frame=8)
    good = _frame(b"\x01")  # 2+1+1+1 = 5 bytes
    huge = _HDR + b"\x7F" + b"\x00" * 4  # L=127, total=131 > 8
    out = a.feed(huge + good)
    assert good in out
    assert a.last_stats["oversize"] >= 1


def test_assembler_big_endian_length():
    # header AA, len u16be at offset 1, extra 3 (hdr+len)
    hdr = b"\xAA"
    payload = b"\x11\x22"
    frame = hdr + b"\x00\x02" + payload   # L=2, total=5
    a = frame_stream.FrameStreamAssembler(hdr, 1, 2, 3, len_be=True)
    assert a.feed(frame) == [frame]
    le = frame_stream.FrameStreamAssembler(hdr, 1, 2, 3, len_be=False)
    assert le.feed(frame) == []   # would read L=0x0200


def test_assembler_map_isolates_sources():
    cfg = binproto.norm_stream_frame({
        "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
        "len_extra": 4,
    })
    m = frame_stream.FrameAssemblerMap()
    full = _frame(b"\x01")
    a_units, _ = m.feed(full[:4], "peer-a", cfg)
    b_units, _ = m.feed(full, "peer-b", cfg)
    assert a_units == []
    assert b_units == [full]
    rest, _ = m.feed(full[4:], "peer-a", cfg)
    assert rest == [full]


def test_assembler_map_discard_does_not_glue_after_reconnect():
    cfg = binproto.norm_stream_frame({
        "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
        "len_extra": 4,
    })
    m = frame_stream.FrameAssemblerMap()
    full = _frame(b"\x01")
    peer = ("10.0.0.1", 40000)
    first, _ = m.feed(full[:4], peer, cfg)
    assert first == []
    m.discard(peer)
    tail, _ = m.feed(full[4:], peer, cfg)
    assert tail == []
    again, _ = m.feed(full, peer, cfg)
    assert again == [full]


def test_assembler_map_retain_sources_drops_gone_clients():
    cfg = binproto.norm_stream_frame({
        "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
        "len_extra": 4,
    })
    m = frame_stream.FrameAssemblerMap()
    full = _frame(b"\x01")
    gone = ("1.1.1.1", 1)
    stay = ("2.2.2.2", 2)
    m.feed(full[:4], gone, cfg)
    m.feed(full[:4], stay, cfg)
    m.retain_sources({stay})
    assert m.feed(full[4:], gone, cfg)[0] == []
    assert m.feed(full[4:], stay, cfg)[0] == [full]


def test_analysis_chunk_mode_default():
    cfg = binproto.norm_stream_frame({})
    m = frame_stream.FrameAssemblerMap()
    chunk = b"\x01\x02"
    units, stats = frame_stream.analysis_rx_units(cfg, "Serial", chunk, None, m)
    assert units == [chunk]
    assert stats is None


def test_analysis_udp_stays_datagram():
    cfg = binproto.norm_stream_frame({
        "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
        "len_extra": 4,
    })
    m = frame_stream.FrameAssemblerMap()
    half = _frame(b"\x01")[:4]
    units, stats = frame_stream.analysis_rx_units(
        cfg, "UDP", half, None, m)
    assert units == [half]
    assert stats is None


def test_analysis_udp_stream_opt_in():
    cfg = binproto.norm_stream_frame({
        "on": True, "udp_stream": True, "header": "AA BB",
        "len_off": 2, "len_width": 1, "len_extra": 4,
    })
    m = frame_stream.FrameAssemblerMap()
    full = _frame(b"\x01")
    u1, st1 = frame_stream.analysis_rx_units(cfg, "UDP", full[:3], None, m)
    u2, st2 = frame_stream.analysis_rx_units(cfg, "UDP", full[3:], None, m)
    assert u1 == []
    assert u2 == [full]
    assert st2 is not None


def test_analysis_tcp_server_per_client():
    cfg = binproto.norm_stream_frame({
        "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
        "len_extra": 4,
    })
    m = frame_stream.FrameAssemblerMap()
    full = _frame(b"\x01")
    u1, _ = frame_stream.analysis_rx_units(
        cfg, "TCP Server", full[:4], ("1.2.3.4", 9), m)
    u2, _ = frame_stream.analysis_rx_units(
        cfg, "TCP Server", full, ("5.6.7.8", 9), m)
    assert u1 == []
    assert u2 == [full]


def test_reset_drops_half_frame():
    cfg = binproto.norm_stream_frame({
        "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
        "len_extra": 4,
    })
    m = frame_stream.FrameAssemblerMap()
    full = _frame(b"\x01")
    frame_stream.analysis_rx_units(cfg, "Serial", full[:4], None, m)
    m.reset()
    units, _ = frame_stream.analysis_rx_units(cfg, "Serial", full[4:], None, m)
    assert units == []   # tail without header is discarded, not glued to old half


def test_parse_diag_counts():
    d = ParseDiagnostics()
    d.note_chunk()
    d.note_assemble(2, {"waiting": 3, "header_skip": 4, "bad_length": 1,
                        "oversize": 0, "last_reason": "bad_length",
                        "last_sample": "AA BB"})
    d.note_parse(matched=True, field_ok=3, field_oob=1)
    snap = d.snapshot()
    assert snap["chunks"] == 1
    assert snap["frames"] == 2
    assert snap["matched"] == 1
    assert snap["fields"] == 3
    assert snap["oob"] == 1
    assert snap["waiting"] == 3
    assert snap["last_reason"] == "bad_length"
    d.reset()
    assert d.snapshot()["frames"] == 0


def test_extract_rule_fields_oob():
    rule = {"fields": [("a", 0, "u8"), ("b", 10, "u16le")]}
    pairs, ok, oob = binproto.extract_rule_fields(rule, b"\x05")
    assert ok == 1 and oob == 1
    assert pairs[0][0] == "a" and pairs[0][3] == 5


def test_norm_stream_frame_missing_is_off():
    cfg = binproto.norm_stream_frame(None)
    assert cfg["on"] is False
    assert cfg["_header"] == b""
    assert frame_stream.should_assemble(cfg, "Serial") is False
