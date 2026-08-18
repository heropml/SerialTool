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

from transport import ble_io
from transport import ble_uuid as bu
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
    def __init__(self, uuid, properties, max_write_without_response_size=None):
        self.uuid = uuid
        self.properties = list(properties)
        if max_write_without_response_size is not None:
            self.max_write_without_response_size = max_write_without_response_size


class _Svc(object):
    def __init__(self, uuid, chars):
        self.uuid = uuid
        self.characteristics = list(chars)


def test_fragment_and_write_mode():
    assert ble_io.fragment_payload(b"abcdef", 2) == [b"ab", b"cd", b"ef"]
    assert ble_io.fragment_payload(b"", 20) == []
    assert ble_io.write_chunk_size(23) == 20
    assert ble_io.wwr_chunk_size(None, 23) == 20
    small = _Char("fff2", ["write-without-response"], max_write_without_response_size=5)
    assert ble_io.wwr_chunk_size(small, 247) == 5
    assert ble_io.wwr_chunk_size(small, 23) == 5
    huge = _Char("fff2", ["write-without-response"], max_write_without_response_size=512)
    assert ble_io.wwr_chunk_size(huge, 23) == 20
    zero = _Char("fff2", ["write-without-response"], max_write_without_response_size=0)
    assert ble_io.wwr_chunk_size(zero, 23) == 20
    assert ble_io.prefer_write_without_response(
        ["read", "write-without-response"]) is True
    assert ble_io.prefer_write_without_response(["write"]) is False
    assert ble_io.apply_write_mode(
        ["write", "write-without-response"], True, "write") is False
    assert ble_io.apply_write_mode(
        ["write", "write-without-response"], False, "wwr") is True
    assert ble_io.apply_write_mode(["write-without-response"], True, "write") is True
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
    assert ok["write_char"] is chars[0].characteristics[1]
    assert ok["notify_char"] is chars[0].characteristics[0]
    same = ble_io.resolve_uart_chars(chars, "ffe0", "ffe1", "ffe1")
    assert same["ok"]
    assert same["write_char"] is chars[1].characteristics[0]
    assert same["notify_char"] is chars[1].characteristics[0]
    other_wr = _Char("fff2", ["write-without-response"])
    want_wr = _Char("fff2", ["write-without-response"])
    want_nt = _Char("fff1", ["notify"])
    dup = [
        _Svc("abcd", [other_wr]),
        _Svc("fff0", [want_nt, want_wr]),
    ]
    picked = ble_io.resolve_uart_chars(dup, "fff0", "fff2", "fff1")
    assert picked["ok"] and picked["write_char"] is want_wr
    assert picked["notify_char"] is want_nt
    # Bleak advertises 16-bit services as hyphenated 128-bit; UI may hold FFF0.
    bleak_svc = [
        _Svc("0000FFF0-0000-1000-8000-00805F9B34FB", [
            _Char("0000FFF1-0000-1000-8000-00805F9B34FB", ["notify"]),
            _Char("0000FFF2-0000-1000-8000-00805F9B34FB",
                  ["write-without-response"]),
        ]),
    ]
    from_ui = ble_io.resolve_uart_chars(bleak_svc, "FFF0", "FFF2", "FFF1")
    assert from_ui["ok"]
    wr_only = _Char("ffe1", ["write-without-response"])
    nt_only = _Char("ffe1", ["notify"])
    split = [_Svc("ffe0", [wr_only, nt_only])]
    split_ok = ble_io.resolve_uart_chars(split, "ffe0", "ffe1", "ffe1")
    assert split_ok["ok"]
    assert split_ok["write_char"] is wr_only
    assert split_ok["notify_char"] is nt_only
    split_rev = [_Svc("ffe0", [nt_only, wr_only])]
    split_ok2 = ble_io.resolve_uart_chars(split_rev, "ffe0", "ffe1", "ffe1")
    assert split_ok2["write_char"] is wr_only
    assert split_ok2["notify_char"] is nt_only
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
        self.disconnects = 0

    async def connect(self, timeout=None):
        if self.connect_sleep:
            import asyncio
            await asyncio.sleep(self.connect_sleep)
        if self.fail_connect:
            raise RuntimeError(self.fail_connect)
        self.connected = True

    async def disconnect(self):
        self.disconnects += 1
        self.connected = False

    async def start_notify(self, uuid, cb):
        self.notify_cb = cb

    async def stop_notify(self, uuid):
        self.notify_cb = None
        self.stopped = True

    async def write_gatt_char(self, uuid, data, response=False):
        key = getattr(uuid, "uuid", uuid)
        self.writes.append((str(key), bytes(data), bool(response)))

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
        # characteristic WWR cap (not MTU-3) drives fragments
        client.writes.clear()
        conn._write_char.max_write_without_response_size = 3
        assert conn.send(b"ABCDEF") == 6
        assert _wait_until(lambda: len(client.writes) == 2)
        assert [w[1] for w in client.writes] == [b"ABC", b"DEF"]
        del conn._write_char.max_write_without_response_size
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
    states = []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        created[-1].inject_drop()
        assert _wait_until(lambda: ble_io.ERR_GONE in errs)
        assert conn.is_open is False
        assert False in states
        n_false = states.count(False)
        conn.close()
        _APP.processEvents()
        assert states.count(False) == n_false
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


def test_ble_close_is_idempotent():
    conn, old = _make_conn()
    states = []
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: True in states and conn.is_open)
        conn.close()
        _wait_until(lambda: not conn.is_open)
        n_false = states.count(False)
        assert n_false == 1
        conn.close()
        _APP.processEvents()
        conn.close()
        _APP.processEvents()
        assert states.count(False) == 1
    finally:
        _cleanup(conn, old)


def test_ble_write_fail_drops_queued_and_closes():
    created = []

    class Boom(FakeClient):
        def __init__(self, address, disconnected_callback=None):
            FakeClient.__init__(self, address, disconnected_callback)
            created.append(self)

        async def write_gatt_char(self, uuid, data, response=False):
            key = getattr(uuid, "uuid", uuid)
            self.writes.append((str(key), bytes(data), bool(response)))
            raise RuntimeError("write boom")

    conn, old = _make_conn(Boom)
    errs = []
    states = []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert conn.send(b"AAA") == 3
        conn.send(b"BBB")
        assert _wait_until(lambda: bool(errs) and False in states)
        payloads = [w[1] for w in created[-1].writes]
        assert b"BBB" not in payloads
        assert conn.is_open is False
        assert conn.send(b"CCC") == 0
    finally:
        _cleanup(conn, old)


def test_ble_drain_chunk_size_error_fails_link_and_returns_queued():
    created = []

    class BoomMtu(FakeClient):
        def __init__(self, address, disconnected_callback=None):
            FakeClient.__init__(self, address, disconnected_callback)
            created.append(self)

        @property
        def mtu_size(self):
            if getattr(self, "boom", False):
                raise RuntimeError("adapter gone")
            return 23

    conn, old = _make_conn(BoomMtu)
    states = []
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        created[-1].boom = True
        assert conn.send(b"hi") == 2
        assert _wait_until(lambda: False in states and conn._queued == 0)
        assert conn.is_open is False
    finally:
        _cleanup(conn, old)


def test_ble_write_oserror_fails_link_and_logs_traceback(caplog):
    """GATT write OSError: user-visible link drop + debug traceback (B6-3)."""
    import logging

    created = []

    class BoomWrite(FakeClient):
        def __init__(self, address, disconnected_callback=None):
            FakeClient.__init__(self, address, disconnected_callback)
            created.append(self)

        async def write_gatt_char(self, uuid, data, response=False):
            raise OSError("adapter gone")

    conn, old = _make_conn(BoomWrite)
    states = []
    errs = []
    conn.state_changed.connect(states.append)
    conn.error_occurred.connect(errs.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        with caplog.at_level(logging.DEBUG, logger="transport.ble_io"):
            assert conn.send(b"hi") == 2
            assert _wait_until(lambda: False in states and conn._queued == 0)
        assert conn.is_open is False
        assert errs
        assert any(
            rec.exc_info and "BLE write failed" in rec.getMessage()
            for rec in caplog.records)
    finally:
        _cleanup(conn, old)


def test_ble_close_does_not_reset_draining_flag():
    conn, old = _make_conn()
    try:
        conn._draining = True
        conn.close()
        assert conn._draining is True
    finally:
        conn._draining = False
        _cleanup(conn, old)


def test_ble_scanner_stop_allows_immediate_restart():
    ble_io._allow_non_windows = True

    class Instant(object):
        def __init__(self, detection_callback=None, scanning_mode="active", **_kw):
            pass

        async def start(self):
            return

        async def stop(self):
            return

    sc = ble_io.BleScanner()
    sc.scanner_factory = Instant
    try:
        assert sc.start() is True
        sc.stop()
        assert sc.is_scanning is False
        assert sc.start() is True
        assert sc.is_scanning is True
    finally:
        sc.stop()
        ble_io.shutdown_loop()


def test_ble_conn_scan_idle_wait_times_out():
    ble_io._allow_non_windows = True
    old_wait = ble_io.SCAN_IDLE_WAIT_S
    ble_io.SCAN_IDLE_WAIT_S = 0.2
    conn, old = _make_conn()
    try:
        async def _hold_scan():
            ble_io._scan_idle_event().clear()

        assert ble_io.get_loop().submit(_hold_scan()) is not None
        time.sleep(0.05)
        _APP.processEvents()
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open, timeout=2.0)
    finally:
        ble_io.SCAN_IDLE_WAIT_S = old_wait
        _cleanup(conn, old)


def test_ble_conn_waits_until_scan_stops():
    ble_io._allow_non_windows = True
    order = []

    class HoldScan(object):
        def __init__(self, detection_callback=None, scanning_mode="active", **_kw):
            pass

        async def start(self):
            return

        async def stop(self):
            import asyncio
            await asyncio.sleep(0.15)
            order.append("scan_stop")

    class Timed(FakeClient):
        async def connect(self, timeout=None):
            order.append("connect")
            return await FakeClient.connect(self, timeout)

    sc = ble_io.BleScanner()
    sc.scanner_factory = HoldScan
    conn, old = _make_conn(Timed)
    try:
        assert sc.start() is True
        assert _wait_until(lambda: sc.is_scanning)
        assert conn.open() is True
        time.sleep(0.05)
        _APP.processEvents()
        assert "connect" not in order
        sc.stop()
        assert _wait_until(lambda: conn.is_open, timeout=3.0)
        assert order.index("scan_stop") < order.index("connect")
    finally:
        sc.stop()
        _cleanup(conn, old)


def test_ble_scanner_stop_before_event_ready():
    ble_io._allow_non_windows = True
    finished = []

    class Slow(object):
        def __init__(self, detection_callback=None, scanning_mode="active", **_kw):
            self.cb = detection_callback
            self.scanning_mode = scanning_mode
            self.stopped = False

        async def start(self):
            import asyncio
            await asyncio.sleep(0.25)

        async def stop(self):
            self.stopped = True

    sc = ble_io.BleScanner()
    sc.scanner_factory = Slow
    sc.scan_finished.connect(lambda: finished.append(True))
    try:
        assert sc.start() is True
        assert sc.is_scanning is True
        sc.stop()
        assert _wait_until(lambda: finished and not sc.is_scanning, timeout=3.0)
        assert sc.is_scanning is False
    finally:
        sc.stop()
        ble_io.shutdown_loop()


def test_ble_conn_close_during_connect_shuts_down():
    created = []

    class Slow(FakeClient):
        connect_sleep = 0.35

        def __init__(self, address, disconnected_callback=None):
            FakeClient.__init__(self, address, disconnected_callback)
            created.append(self)

    conn, old = _make_conn(Slow)
    states = []
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert conn.is_open is False
        assert _wait_until(lambda: bool(created))
        conn.close()
        assert _wait_until(
            lambda: created[-1].disconnects >= 1, timeout=3.0)
        assert conn.is_open is False
        assert conn._ready is False
        assert True not in states
        assert created[-1].connected is False
    finally:
        _cleanup(conn, old)


def test_get_loop_skips_stopped_instance():
    first = ble_io.get_loop()
    assert first._stopped is False
    ble_io.shutdown_loop()
    assert first._stopped is True

    async def _noop():
        return 1

    assert first.submit(_noop()) is None
    first.call_soon(lambda: None)
    second = ble_io.get_loop()
    try:
        assert second is not first
        assert second._stopped is False
    finally:
        ble_io.shutdown_loop()


def test_fail_open_link_errors_only_when_was_open():
    conn, old = _make_conn()
    errs = []
    conn.error_occurred.connect(errs.append)
    try:
        conn._fail_open_link(ble_io.ERR_GONE)
        _APP.processEvents()
        assert errs == []
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        conn._fail_open_link(ble_io.ERR_GONE)
        assert _wait_until(lambda: ble_io.ERR_GONE in errs)
        n = len(errs)
        conn._fail_open_link(ble_io.ERR_CONNECT)
        _APP.processEvents()
        time.sleep(0.05)
        _APP.processEvents()
        assert len(errs) == n
    finally:
        _cleanup(conn, old)
