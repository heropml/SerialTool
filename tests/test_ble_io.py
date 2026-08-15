# -*- coding: utf-8 -*-
"""BLE GATT helpers + mocked BleConn (no live adapter)."""
from __future__ import print_function

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication, QEvent

import ble_io
import ble_uuid as bu

_APP = QApplication.instance() or QApplication([])


def _wait_until(pred, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _APP.processEvents()
        if pred():
            return True
        time.sleep(0.02)
    return False


class _Char(object):
    def __init__(self, uuid, properties):
        self.uuid = uuid
        self.properties = list(properties)


class _Svc(object):
    def __init__(self, uuid, chars):
        self.uuid = uuid
        self.characteristics = list(chars)


def test_fragment_and_write_mode():
    assert ble_io.fragment_payload(b"abcdef", 2) == [b"ab", b"cd", b"ef"]
    assert ble_io.fragment_payload(b"", 20) == []
    assert ble_io.write_chunk_size(23) == 20
    assert ble_io.prefer_write_without_response(
        ["read", "write-without-response"]) is True
    assert ble_io.prefer_write_without_response(["write"]) is False
    assert ble_io.char_supports_notify(["notify", "read"])
    assert not ble_io.char_supports_notify(["indicate"])


def test_resolve_uart_same_uuid_and_service_filter():
    chars = [
        _Svc("fff0", [
            _Char("fff1", ["notify"]),
            _Char("fff2", ["write-without-response", "write"]),
        ]),
        _Svc("ffe0", [
            _Char("ffe1", ["notify", "write-without-response"]),
        ]),
    ]
    ok = ble_io.resolve_uart_chars(chars, "fff0", "fff2", "fff1")
    assert ok["ok"] and ok["write_without_response"] is True
    same = ble_io.resolve_uart_chars(chars, "ffe0", "ffe1", "ffe1")
    assert same["ok"]
    missing = ble_io.resolve_uart_chars(chars, "fff0", "ffe1", "fff1")
    assert not missing["ok"] and missing["error"] == ble_io.ERR_NO_WRITE
    bad_nt = ble_io.resolve_uart_chars(chars, "fff0", "fff2", "fff2")
    assert not bad_nt["ok"] and bad_nt["error"] == ble_io.ERR_NO_NOTIFY


class FakeClient(object):
    services = [
        _Svc("fff0", [
            _Char("fff1", ["notify"]),
            _Char("fff2", ["write-without-response"]),
        ]),
    ]
    mtu_size = 23
    fail_connect = None
    connect_sleep = 0.0

    def __init__(self, address, disconnected_callback=None):
        self.address = address
        self._disc = disconnected_callback
        self.connected = False
        self.writes = []
        self.notify_cb = None
        self.stopped = False

    async def connect(self, timeout=None):
        if self.connect_sleep:
            import asyncio
            await asyncio.sleep(self.connect_sleep)
        if self.fail_connect:
            raise RuntimeError(self.fail_connect)
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def start_notify(self, uuid, cb):
        self.notify_cb = cb

    async def stop_notify(self, uuid):
        self.notify_cb = None
        self.stopped = True

    async def write_gatt_char(self, uuid, data, response=False):
        self.writes.append((str(uuid), bytes(data), bool(response)))

    @property
    def is_connected(self):
        return self.connected

    def inject_rx(self, data):
        if self.notify_cb:
            self.notify_cb(None, data)

    def inject_drop(self):
        self.connected = False
        if self._disc:
            self._disc(self)


def _make_conn(factory=None):
    ble_io._allow_non_windows = True
    BleConn = ble_io.BleConn
    old = BleConn.client_factory
    BleConn.client_factory = factory or FakeClient
    conn = BleConn("69:1E:38:38:39:0D", "fff0", "fff2", "fff1")
    return conn, old


def _cleanup(conn, old_factory):
    try:
        conn.close()
        _APP.processEvents()
        time.sleep(0.05)
        _APP.processEvents()
        conn.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    finally:
        ble_io.BleConn.client_factory = old_factory
        ble_io.shutdown_loop()


def test_ble_conn_connect_notify_write_and_stale():
    created = []

    class Factory(FakeClient):
        def __init__(self, address, disconnected_callback=None):
            FakeClient.__init__(self, address, disconnected_callback)
            created.append(self)

    conn, old = _make_conn(Factory)
    rx = []
    errs = []
    states = []
    conn.data_received.connect(rx.append)
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: True in states and conn.is_open)
        client = created[-1]
        client.inject_rx(b"\x01\x02")
        assert _wait_until(lambda: rx == [b"\x01\x02"])
        n = conn.send(b"abcdefghij")  # 10 bytes, chunk 20 → one write
        assert n == 10
        assert _wait_until(lambda: len(client.writes) == 1)
        assert client.writes[0][1] == b"abcdefghij"
        assert client.writes[0][2] is False  # WWR
        # oversized fragments stay in order
        client.writes.clear()
        conn._chunk = 3
        assert conn.send(b"ABCDEF") == 6
        assert _wait_until(lambda: len(client.writes) == 2)
        assert [w[1] for w in client.writes] == [b"ABC", b"DEF"]
        # stale notify after close
        conn.close()
        assert _wait_until(lambda: not conn.is_open)
        client.inject_rx(b"late")
        _APP.processEvents()
        time.sleep(0.05)
        _APP.processEvents()
        assert b"late" not in rx
        assert client.stopped is True
    finally:
        _cleanup(conn, old)


def test_ble_conn_cancel_inflight_and_drop():
    created = []

    class Slow(FakeClient):
        connect_sleep = 0.4

        def __init__(self, address, disconnected_callback=None):
            FakeClient.__init__(self, address, disconnected_callback)
            created.append(self)

    conn, old = _make_conn(Slow)
    errs = []
    states = []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert conn.is_open is False
        conn.close()  # cancel connecting
        time.sleep(0.5)
        _APP.processEvents()
        assert conn.is_open is False
        assert True not in states
        # remote drop after a successful connect
        conn2, old2 = _make_conn(FakeClient)
        drop_errs = []
        conn2.error_occurred.connect(drop_errs.append)
        try:
            assert conn2.open() is True
            assert _wait_until(lambda: conn2.is_open)
            # grab client via drain of factory: reopen with capturing factory
        finally:
            _cleanup(conn2, old2)
    finally:
        _cleanup(conn, old)

    created = []

    class Cap(FakeClient):
        def __init__(self, address, disconnected_callback=None):
            FakeClient.__init__(self, address, disconnected_callback)
            created.append(self)

    conn, old = _make_conn(Cap)
    errs = []
    conn.error_occurred.connect(errs.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        created[-1].inject_drop()
        assert _wait_until(lambda: ble_io.ERR_GONE in errs)
        assert conn.is_open is False
    finally:
        _cleanup(conn, old)


def test_ble_conn_send_fails_when_closed():
    conn, old = _make_conn()
    try:
        assert conn.send(b"hi") == 0
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert conn.send(b"hi") == 2
        conn.close()
        _wait_until(lambda: not conn.is_open)
        assert conn.send(b"hi") == 0
    finally:
        _cleanup(conn, old)
