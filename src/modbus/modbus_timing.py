# -*- coding: utf-8 -*-
"""Modbus master timing helpers (Qt-free).

S-2 slice: baud/char-time math and address-span checks live here so tests
do not need CommTool. UI/config resolution stays on the main window.
"""
from modbus import modbus_master


def serial_char_bits(databits, parity, stopbits):
    """Bits per serial character = start + data + optional parity + stop."""
    try:
        databits = int(databits)
        stopbits = float(stopbits)
        parity = str(parity)
    except (ValueError, TypeError):
        return 11.0
    return 1.0 + databits + (0.0 if parity == "None" else 1.0) + stopbits


def rtu_silent_ms(baud, char_bits=11.0):
    """Modbus RTU inter-frame silence (>= 3.5 chars; fixed 1.75ms above 19200)."""
    try:
        baud = max(int(baud), 300)
        char_bits = float(char_bits)
    except (ValueError, TypeError):
        return 2
    return 2 if baud > 19200 else max(2, int(3.5 * char_bits * 1000.0 / baud + 0.999))


def rtu_tx_guard_ms(frame_len, baud, char_bits=11.0):
    """Wait for full TX time + t3.5 after a no-response (broadcast) frame."""
    try:
        frame_len = int(frame_len)
        baud = max(int(baud), 300)
        char_bits = float(char_bits)
    except (ValueError, TypeError):
        return rtu_silent_ms(9600, 11.0)
    tx_ms = int(frame_len * char_bits * 1000.0 / baud + 0.999)
    return tx_ms + rtu_silent_ms(baud, char_bits)


def response_len_budget(func, qty, variant="rtu"):
    """Expected response size used for serial timeout budgeting."""
    resp_rtu = modbus_master.rtu_normal_len(func, qty)
    if resp_rtu is None:
        resp_rtu = 256 if func == 0x11 else 8
    if str(variant).lower() == "ascii":
        return 2 * resp_rtu + 1
    return resp_rtu


def timeout_ms(base, frame_len, resp_len, baud, char_bits=11.0):
    """Response timeout = processing base + request/response wire time."""
    try:
        base = int(base)
        frame_len = int(frame_len)
        resp_len = int(resp_len)
        baud = max(int(baud), 300)
        char_bits = float(char_bits)
    except (ValueError, TypeError):
        # base may already be int if a later arg failed conversion.
        return base if isinstance(base, int) else 1000
    tx_ms = (frame_len + resp_len) * char_bits * 1000.0 / baud
    return int(base + tx_ms)


def _span_over(start, count):
    return bool(start is not None and count and start + int(count) - 1 > 0xFFFF)


def span_bad(rule):
    """True when a continuous read/write range crosses 0xFFFF."""
    r = rule or {}
    func = r.get("func")
    if func in modbus_master.READ_FUNCS:
        return _span_over(r.get("addr"), r.get("qty"))
    if func in modbus_master.WRITE_MULTI:
        return _span_over(r.get("addr"), len(r.get("wvals") or []))
    if func == 0x17:
        rw = r.get("rw") or {}
        return bool(
            _span_over(r.get("addr"), r.get("qty"))
            or _span_over(r.get("write_addr"), len(rw.get("write_vals") or []))
        )
    if func == 0x16:
        return _span_over(r.get("addr"), 1)
    return False
