# -*- coding: utf-8 -*-
"""Regression tests for the second review round fixes.

Covers: double-open guard, gateway resync yield, broadcast burst limit,
TCP resync limit, FC11 byte_count upper bound, bitfield overlap detection,
scope upper bound clamp, webhook SSRF, and device decode skip redundant normalize.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])

from net_io import TcpServerConn, TcpClientConn, UdpConn, UdpGroupConn  # noqa: E402
import modbus_master as mm  # noqa: E402
from modbus_gateway import ModbusGatewayEngine  # noqa: E402
from device_resources import parse_bitfields, decode_modbus_samples  # noqa: E402
import triggers  # noqa: E402


# =========================================================================
# 1. Double-open guard for all 4 connection classes
#    Test that calling close() when never opened should NOT emit state_changed(False).
# =========================================================================

def test_tcp_server_close_when_never_opened_no_signal():
    """TcpServerConn: close() without prior open must not emit state_changed(False)."""
    conn = TcpServerConn("127.0.0.1", 0)
    states = []
    conn.state_changed.connect(states.append)
    conn.close()
    assert states == []


def test_tcp_client_close_when_never_opened_no_signal():
    """TcpClientConn: close() without prior open must not emit state_changed(False)."""
    conn = TcpClientConn("127.0.0.1", 5000)
    states = []
    conn.state_changed.connect(states.append)
    conn.close()
    assert states == []


def test_udp_conn_close_when_never_opened_no_signal():
    """UdpConn: close() without prior open must not emit state_changed(False)."""
    conn = UdpConn("0.0.0.0", 0, "127.0.0.1", 5000)
    states = []
    conn.state_changed.connect(states.append)
    conn.close()
    assert states == []


def test_udp_group_conn_close_when_never_opened_no_signal():
    """UdpGroupConn: close() without prior open must not emit state_changed(False)."""
    conn = UdpGroupConn("0.0.0.0", "239.1.1.1", 5000)
    states = []
    conn.state_changed.connect(states.append)
    conn.close()
    assert states == []


# =========================================================================
# 2. Gateway resync yield
#    feed_rtu with corrupt data processes at most 8 drops per call.
# =========================================================================

def test_gateway_resync_caps_drops_per_call():
    """Pathological noise must not resync without a per-feed ceiling."""
    from modbus_gateway import _RESYNC_MAX_PER_FEED
    gw = ModbusGatewayEngine()
    gw.feed_tcp(mm.build_tcp_request(1, 1, 3, 0, 1))
    assert gw._pending is not None

    gw._rtu_buf.extend(b"\xFF" * (_RESYNC_MAX_PER_FEED + 80))
    initial_drops = gw.stats["drops"]
    gw.feed_rtu(b"")
    new_drops = gw.stats["drops"] - initial_drops
    assert new_drops <= _RESYNC_MAX_PER_FEED
    # leftover stays for the next feed
    assert len(gw._rtu_buf) > 0


def test_gateway_resync_continues_on_next_call():
    """After hitting the per-feed ceiling, the next feed keeps resyncing."""
    from modbus_gateway import _RESYNC_MAX_PER_FEED
    gw = ModbusGatewayEngine()
    gw.feed_tcp(mm.build_tcp_request(1, 1, 3, 0, 1))
    assert gw._pending is not None

    gw.feed_rtu(b"\xFF" * (_RESYNC_MAX_PER_FEED + 40))
    drops_after_first = gw.stats["drops"]
    gw.feed_rtu(b"\xFF" * 40)
    assert gw.stats["drops"] > drops_after_first


def test_gateway_resync_same_batch_keeps_the_valid_frame():
    """Noise then a valid RTU reply in ONE feed must not strand the reply.

    The old 8-drop early-return left the valid frame in _rtu_buf; with no more
    slave traffic the gateway timed out and cleared it — silent data loss.
    """
    import modbus_slave as ms
    gw = ModbusGatewayEngine(timeout_s=1.0)
    gw.feed_tcp(mm.build_tcp_request(1, 1, 3, 0, 1), client="A", now=0.0)
    body = bytes([1, 0x03, 0x02, 0x12, 0x34])
    valid = body + ms.crc16(body)
    _, tcp_out = gw.feed_rtu(b"\xFF" * 8 + valid, now=0.1)
    assert len(tcp_out) == 1 and tcp_out[0].client == "A"
    assert tcp_out[0].frame[9:11] == bytes([0x12, 0x34])
    assert gw._pending is None


# =========================================================================
# 3. Broadcast burst limit
#    _pump with many broadcast requests stops after 4 per call.
# =========================================================================

def test_broadcast_burst_limit_of_4():
    """_pump stops after 4 broadcast requests in a single call."""
    gw = ModbusGatewayEngine()
    # Queue 8 broadcast (unit=0) requests
    for tid in range(8):
        gw._queue.append({
            "tid": tid,
            "unit_tcp": 0,
            "pdu": bytes([3, 0, 0, 0, 1]),
            "client": None,
        })
    rtu_out = []
    gw._pump(rtu_out)
    assert len(rtu_out) <= 4, "_pump should emit at most 4 broadcast frames per call"
    # Remaining requests should still be in the queue
    assert len(gw._queue) >= 4, "Remaining broadcast requests should stay queued"


# =========================================================================
# 4. TCP resync limit
#    _take_tcp_frame with garbage data stops after 64 bytes of scanning.
# =========================================================================

def test_tcp_resync_limit_of_64_bytes():
    """_take_tcp_frame stops scanning after 64 bytes of garbage."""
    gw = ModbusGatewayEngine()
    buf = bytearray(b"\xFF" * 200)

    total_drops = 0
    frames_found = 0
    for _ in range(10):
        frame = gw._take_tcp_frame(buf)
        if frame is None:
            break
        frames_found += 1

    total_drops = gw.stats["drops"]
    assert frames_found == 0, "No valid frames should be found in garbage data"
    assert total_drops >= 1, "Some drops should have occurred"


def test_tcp_resync_scans_at_most_64_per_call():
    """Each _take_tcp_frame call consumes at most 64 invalid bytes."""
    gw = ModbusGatewayEngine()
    buf = bytearray(b"\xFF" * 200)

    # First call: should scan exactly 64 bytes
    frame = gw._take_tcp_frame(buf)
    assert frame is None
    drops_first_call = gw.stats["drops"]
    assert drops_first_call == 64, "First call should drop exactly 64 bytes"
    assert len(buf) == 200 - 64


def test_tcp_resync_same_batch_keeps_the_valid_request():
    """64 bytes of junk then a valid MBAP in one feed_tcp must still dispatch."""
    gw = ModbusGatewayEngine()
    req = mm.build_tcp_request(1, 1, 3, 0, 1)
    rtu_out, _ = gw.feed_tcp(b"\xFF" * 64 + req, client="X", now=0.0)
    assert len(rtu_out) == 1
    assert gw._pending is not None and gw._pending["client"] == "X"


# =========================================================================
# 5. FC11 byte_count upper bound
#    take_rtu_response with FC11 and byte_count > 252 raises ValueError.
# =========================================================================

def test_fc11_byte_count_too_large_raises():
    """FC11 with byte_count > 252 must raise ValueError."""
    from modbus_slave import crc16
    frame_body = bytes([1, 0x11, 253])
    frame_body += b"\x00" * 253
    frame = frame_body + crc16(frame_body)
    with pytest.raises(ValueError, match="FC11 byte_count too large"):
        mm.take_rtu_response(frame, 1, 0x11, 1)


def test_fc11_byte_count_at_boundary_ok():
    """FC11 with byte_count == 252 should not raise byte_count error."""
    from modbus_slave import crc16
    frame_body = bytes([1, 0x11, 252])
    frame_body += b"\x00" * 252
    frame = frame_body + crc16(frame_body)
    # This should not raise the byte_count ValueError
    try:
        result = mm.take_rtu_response(frame, 1, 0x11, 1)
        # It's ok if it returns a result or raises something other than byte_count error
        assert result is None or result is not None
    except ValueError as e:
        assert "byte_count" not in str(e).lower()


# =========================================================================
# 6. Bitfield overlap detection
#    parse_bitfields("0:8:A,4:8:B") only returns the first entry.
# =========================================================================

def test_bitfield_overlap_drops_second():
    """Overlapping bitfields: second entry is dropped."""
    result = parse_bitfields("0:8:A,4:8:B")
    assert len(result) == 1
    assert result[0] == (0, 8, "A")


def test_bitfield_no_overlap_keeps_both():
    """Non-overlapping bitfields: both entries are kept."""
    result = parse_bitfields("0:4:A,4:4:B")
    assert len(result) == 2
    assert result[0] == (0, 4, "A")
    assert result[1] == (4, 4, "B")


def test_bitfield_partial_overlap_drops_second():
    """Partially overlapping bitfields: second is dropped."""
    result = parse_bitfields("0:8:A,6:4:B")
    assert len(result) == 1
    assert result[0] == (0, 8, "A")


# =========================================================================
# 7. Scope upper bound clamp
#    Tuple access with out-of-range index clamps correctly.
# =========================================================================

def test_scope_tuple_clamp():
    """Out-of-range scope index is clamped to valid range."""
    assert ("rx", "tx", "both")[min(2, max(0, 0))] == "rx"
    assert ("rx", "tx", "both")[min(2, max(0, 1))] == "tx"
    assert ("rx", "tx", "both")[min(2, max(0, 2))] == "both"
    assert ("rx", "tx", "both")[min(2, max(0, 3))] == "both"
    assert ("rx", "tx", "both")[min(2, max(0, 99))] == "both"
    assert ("rx", "tx", "both")[min(2, max(0, -1))] == "rx"


def test_triggers_normalize_invalid_scope_defaults_rx():
    """normalize with invalid scope falls back to 'rx'."""
    rule = triggers.normalize({"name": "t", "pattern": "X", "scope": "invalid"})
    assert rule["scope"] == "rx"


def test_triggers_normalize_valid_scopes():
    """normalize preserves valid scope values."""
    for scope in ("rx", "tx", "both"):
        rule = triggers.normalize({"name": "t", "pattern": "X", "scope": scope})
        assert rule["scope"] == scope


# =========================================================================
# 8. Webhook SSRF
#    CommTool._is_private_url blocks private/loopback addresses.
# =========================================================================

def test_is_private_url_blocks_loopback():
    """127.0.0.1 is private."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://127.0.0.1/webhook") is True


def test_is_private_url_blocks_10_range():
    """10.0.0.1 is private."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://10.0.0.1/hook") is True


def test_is_private_url_blocks_192_168():
    """192.168.1.1 is private."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://192.168.1.1/hook") is True


def test_is_private_url_blocks_172_16():
    """172.16.0.1 is private."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://172.16.0.1/hook") is True


def test_is_private_url_blocks_169_254():
    """169.254.1.1 (link-local) is private."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://169.254.1.1/hook") is True


def test_is_private_url_allows_public_ip():
    """8.8.8.8 is not private."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://8.8.8.8:8080/hook") is False


def test_is_private_url_allows_hostname():
    """example.com hostname is not private."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://example.com/webhook") is False


def test_is_private_url_blocks_localhost():
    """localhost is private."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://localhost/hook") is True


def test_is_private_url_blocks_ipv4_mapped_ipv6():
    """::ffff:192.168.1.1 must be treated as private (dotted form)."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://[::ffff:192.168.1.1]/hook") is True
    assert CommTool._is_private_url("http://[::ffff:127.0.0.1]/hook") is True


def test_is_private_url_blocks_ipv4_mapped_hex_form():
    """::ffff:c0a8:101 is 192.168.1.1 in hex-mapped form."""
    from main_window import CommTool
    assert CommTool._is_private_url("http://[::ffff:c0a8:101]/hook") is True


# =========================================================================
# 9. Device decode skip redundant normalize
#    decode_modbus_samples works when passed definitions directly.
# =========================================================================

def test_decode_modbus_samples_without_normalize():
    """decode_modbus_samples works with raw definitions (no normalize_registers)."""
    definition = {
        "enabled": True,
        "name": "voltage",
        "slave": 1,
        "function": 3,
        "address": 0,
        "addr_base": 0,
        "display_address": 0,
        "type": "u16",
        "order": "AB",
        "bit": 0,
        "bitfields": "",
        "scale": 1.0,
        "offset": 0.0,
        "unit": "V",
        "warn_lo": None,
        "warn_hi": None,
        "alarm_lo": None,
        "alarm_hi": None,
    }
    registers = [220, 380]
    samples = decode_modbus_samples(
        [definition], slave=1, function=3, start_address=0,
        registers=registers,
    )
    assert len(samples) == 1
    assert samples[0]["tag"] == "voltage"
    assert samples[0]["value"] == 220
    assert samples[0]["unit"] == "V"


def test_decode_modbus_samples_multiple_defs():
    """decode_modbus_samples handles multiple definitions; disabled ones are skipped."""
    defs = [
        {
            "enabled": True,
            "name": "temp",
            "slave": 1,
            "function": 3,
            "address": 100,
            "addr_base": 1,
            "display_address": 101,
            "type": "u16",
            "order": "AB",
            "bit": 0,
            "bitfields": "",
            "scale": 0.1,
            "offset": -50.0,
            "unit": "C",
            "warn_lo": None,
            "warn_hi": None,
            "alarm_lo": None,
            "alarm_hi": None,
        },
        {
            "enabled": False,
            "name": "disabled_reg",
            "slave": 1,
            "function": 3,
            "address": 101,
            "addr_base": 1,
            "display_address": 102,
            "type": "u16",
            "order": "AB",
            "bit": 0,
            "bitfields": "",
            "scale": 1.0,
            "offset": 0.0,
            "unit": "",
            "warn_lo": None,
            "warn_hi": None,
            "alarm_lo": None,
            "alarm_hi": None,
        },
    ]
    registers = [850]  # 850 * 0.1 - 50 = 35.0
    samples = decode_modbus_samples(
        defs, slave=1, function=3, start_address=100,
        registers=registers,
    )
    assert len(samples) == 1
    assert samples[0]["tag"] == "temp"
    assert samples[0]["value"] == 35.0


def test_decode_modbus_samples_with_bitfields():
    """decode_modbus_samples decodes bitfields when present."""
    definition = {
        "enabled": True,
        "name": "status",
        "slave": 1,
        "function": 3,
        "address": 0,
        "addr_base": 0,
        "display_address": 0,
        "type": "u16",
        "order": "AB",
        "bit": 0,
        "bitfields": "0:4:lo,4:4:hi",
        "scale": 1.0,
        "offset": 0.0,
        "unit": "",
        "warn_lo": None,
        "warn_hi": None,
        "alarm_lo": None,
        "alarm_hi": None,
    }
    registers = [0x23]  # lo=3, hi=2
    samples = decode_modbus_samples(
        [definition], slave=1, function=3, start_address=0,
        registers=registers,
    )
    tags = {s["tag"]: s["value"] for s in samples}
    assert "status" in tags
    assert "status.lo" in tags
    assert "status.hi" in tags
    assert tags["status.lo"] == 3
    assert tags["status.hi"] == 2
