# -*- coding: utf-8 -*-
"""Windows BLE central UART pipe (Bleak), matching SerialConn's Qt signals.

Scan and GATT I/O run on a dedicated asyncio thread. Notify bytes, connection
state and errors are emitted on the Qt thread that owns the QObject.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading

from PyQt5.QtCore import QObject, pyqtSignal

import ble_uuid

_log = logging.getLogger(__name__)

ERR_BT_OFF = "ble:bt-off"
ERR_NO_ADAPTER = "ble:no-adapter"
ERR_GONE = "ble:gone"
ERR_NO_WRITE = "ble:no-write"
ERR_NO_NOTIFY = "ble:no-notify"
ERR_BAD_UUID = "ble:bad-uuid"
ERR_WINDOWS_ONLY = "ble:windows-only"
ERR_NO_BLEAK = "ble:no-bleak"
ERR_CONNECT = "ble:connect"

ERROR_I18N = {
    ERR_BT_OFF: "ble_err_bt_off",
    ERR_NO_ADAPTER: "ble_err_bt_off",
    ERR_GONE: "ble_err_gone",
    ERR_NO_WRITE: "ble_err_no_write",
    ERR_NO_NOTIFY: "ble_err_no_notify",
    ERR_BAD_UUID: "ble_err_bad_uuid",
    ERR_WINDOWS_ONLY: "ble_err_windows_only",
    ERR_NO_BLEAK: "ble_err_no_bleak",
    ERR_CONNECT: "err_connect_failed",
}

MAX_QUEUED_BYTES = 256 * 1024
CONNECT_TIMEOUT_S = 15.0
DEFAULT_ATT_MTU = 23
ATT_HEADER = 3

# Tests may assign a client/scanner factory and skip the Windows gate.
_allow_non_windows = False


def is_windows():
    return sys.platform == "win32"


def write_chunk_size(mtu):
    try:
        n = int(mtu or DEFAULT_ATT_MTU)
    except (TypeError, ValueError):
        n = DEFAULT_ATT_MTU
    return max(1, n - ATT_HEADER)


def fragment_payload(data, chunk_size):
    raw = bytes(data or b"")
    size = int(chunk_size or 20)
    if size <= 0:
        size = 20
    if not raw:
        return []
    return [raw[i:i + size] for i in range(0, len(raw), size)]


def _prop_set(properties):
    return {str(p).strip().lower() for p in (properties or [])}


def char_supports_write(properties):
    props = _prop_set(properties)
    return "write" in props or "write-without-response" in props


def char_supports_notify(properties):
    props = _prop_set(properties)
    return "notify" in props


def prefer_write_without_response(properties):
    """True → write-without-response (Bleak response=False)."""
    props = _prop_set(properties)
    if "write-without-response" in props:
        return True
    if "write" in props:
        return False
    return None


def iter_chars(services):
    """Yield (service_uuid, char_uuid, properties) from a bleak-like services obj."""
    if services is None:
        return
    iterable = services
    if hasattr(services, "services") and not hasattr(services, "__iter__"):
        iterable = services.services
    try:
        svc_iter = list(iterable)
    except TypeError:
        return
    for svc in svc_iter:
        svc_uuid = getattr(svc, "uuid", None)
        chars = getattr(svc, "characteristics", None) or ()
        for char in chars:
            yield (
                svc_uuid,
                getattr(char, "uuid", None),
                list(getattr(char, "properties", None) or []),
            )


def resolve_uart_chars(services, service_uuid, write_uuid, notify_uuid):
    """Validate write/notify characteristics.

    Same UUID for write and notify is allowed. If ``service_uuid`` is set,
    both characteristics must live on that service.
    """
    want_svc = ble_uuid.normalize_uuid(service_uuid) if service_uuid else ""
    want_wr = ble_uuid.normalize_uuid(write_uuid)
    want_nt = ble_uuid.normalize_uuid(notify_uuid)
    if not want_wr or not want_nt:
        return {"ok": False, "error": ERR_BAD_UUID}

    write_hit = None
    notify_hit = None
    for svc_u, char_u, props in iter_chars(services):
        svc_n = ble_uuid.normalize_uuid(svc_u)
        char_n = ble_uuid.normalize_uuid(char_u)
        if want_svc and svc_n != want_svc:
            continue
        if char_n == want_wr and write_hit is None:
            write_hit = (char_n, props)
        if char_n == want_nt and notify_hit is None:
            notify_hit = (char_n, props)

    if write_hit is None:
        return {"ok": False, "error": ERR_NO_WRITE}
    if notify_hit is None:
        return {"ok": False, "error": ERR_NO_NOTIFY}
    if not char_supports_write(write_hit[1]):
        return {"ok": False, "error": ERR_NO_WRITE}
    if not char_supports_notify(notify_hit[1]):
        return {"ok": False, "error": ERR_NO_NOTIFY}
    wwr = prefer_write_without_response(write_hit[1])
    return {
        "ok": True,
        "error": None,
        "write_uuid": write_hit[0],
        "notify_uuid": notify_hit[0],
        "write_without_response": bool(wwr),
    }


def classify_bleak_error(exc):
    text = str(exc or "").lower()
    if "turned off" in text or "powered off" in text or "not available" in text:
        return ERR_BT_OFF
    if "adapter" in text and ("not" in text or "found" in text):
        return ERR_NO_ADAPTER
    if "not found" in text or "no device" in text or "unreachable" in text:
        return ERR_GONE
    return ERR_CONNECT


class _BleLoop(threading.Thread):
    def __init__(self):
        super().__init__(name="CommToolBleLoop", daemon=True)
        self.loop = None
        self._ready = threading.Event()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()
        pending = asyncio.all_tasks(self.loop) if hasattr(asyncio, "all_tasks") else []
        for task in pending:
            task.cancel()
        if pending:
            try:
                self.loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                _log.debug("ble loop drain failed", exc_info=True)
        self.loop.close()

    def wait_ready(self, timeout=5.0):
        return self._ready.wait(timeout)

    def submit(self, coro):
        if not self.wait_ready():
            raise RuntimeError("BLE loop failed to start")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call_soon(self, fn, *args):
        if not self.wait_ready():
            return
        self.loop.call_soon_threadsafe(fn, *args)

    def stop(self):
        if self.loop is None:
            return
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except RuntimeError:
            return
        self.join(timeout=3.0)


_loop = None
_loop_lock = threading.Lock()


def get_loop():
    global _loop
    with _loop_lock:
        if _loop is None or not _loop.is_alive():
            _loop = _BleLoop()
            _loop.start()
        return _loop


def shutdown_loop():
    global _loop
    with _loop_lock:
        inst = _loop
        _loop = None
    if inst is not None:
        inst.stop()


def _import_bleak():
    try:
        from bleak import BleakClient, BleakScanner
        from bleak.exc import BleakError
    except ImportError as exc:
        raise RuntimeError(ERR_NO_BLEAK) from exc
    return BleakClient, BleakScanner, BleakError


def _platform_ok():
    return is_windows() or _allow_non_windows


class BleScanner(QObject):
    """Independent scan helper (does not require a live BleConn)."""

    device_found = pyqtSignal(str, str, object, object)
    scan_finished = pyqtSignal()
    scan_error = pyqtSignal(str)

    scanner_factory = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gen = 0
        self._stop_evt = None
        self._scanning = False

    @property
    def is_scanning(self):
        return bool(self._scanning)

    def start(self):
        if self._scanning:
            return True
        if not _platform_ok():
            self.scan_error.emit(ERR_WINDOWS_ONLY)
            return False
        self._gen += 1
        gen = self._gen
        self._scanning = True
        try:
            get_loop().submit(self._run(gen))
        except Exception as exc:
            self._scanning = False
            token = classify_bleak_error(exc)
            if str(exc) == ERR_NO_BLEAK or "bleak" in str(exc).lower():
                token = ERR_NO_BLEAK
            self.scan_error.emit(token)
            return False
        return True

    def stop(self):
        evt = self._stop_evt
        if evt is not None:
            get_loop().call_soon(evt.set)

    async def _run(self, gen):
        scanner = None
        try:
            factory = self.scanner_factory
            if factory is None:
                _client, BleakScanner, _err = _import_bleak()
                factory = BleakScanner
            self._stop_evt = asyncio.Event()

            def _cb(device, adv):
                if gen != self._gen or not self._scanning:
                    return
                name = (getattr(device, "name", None)
                        or getattr(adv, "local_name", None)
                        or "")
                rssi = getattr(adv, "rssi", None)
                uuids = list(getattr(adv, "service_uuids", None) or [])
                addr = ble_uuid.normalize_address(
                    getattr(device, "address", "") or "")
                if not addr:
                    return
                self.device_found.emit(addr, str(name or ""), rssi, uuids)

            scanner = factory(detection_callback=_cb)
            await scanner.start()
            await self._stop_evt.wait()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if gen == self._gen:
                token = ERR_NO_BLEAK if str(exc) == ERR_NO_BLEAK else (
                    classify_bleak_error(exc))
                self.scan_error.emit(token)
                _log.debug("BLE scan failed: %s", exc, exc_info=True)
        finally:
            self._gen += 1
            if scanner is not None:
                try:
                    await scanner.stop()
                except Exception:
                    _log.debug("BLE scanner stop failed", exc_info=True)
            self._stop_evt = None
            self._scanning = False
            self.scan_finished.emit()


class BleConn(QObject):
    data_received = pyqtSignal(bytes)
    state_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    client_factory = None

    def __init__(self, address, service_uuid="", write_uuid="", notify_uuid="",
                 parent=None):
        super().__init__(parent)
        self._address = ble_uuid.normalize_address(address)
        self._service_uuid = service_uuid or ""
        self._write_uuid = write_uuid or ""
        self._notify_uuid = notify_uuid or ""
        self._gen = 0
        self._ready = False
        self._closing = False
        self._was_open = False
        self._client = None
        self._write_without_response = True
        self._chunk = 20
        self._lock = threading.Lock()
        self._pending = []
        self._queued = 0
        self._draining = False
        self._open_fut = None

    @property
    def is_open(self):
        return bool(self._ready)

    @property
    def address(self):
        return self._address

    def open(self):
        if self._client is not None or self._open_fut is not None:
            self.close()
        if not _platform_ok():
            self.error_occurred.emit(ERR_WINDOWS_ONLY)
            return False
        if not ble_uuid.is_valid_address(self._address):
            self.error_occurred.emit(ERR_GONE)
            return False
        if not ble_uuid.normalize_uuid(self._write_uuid) or not ble_uuid.normalize_uuid(
                self._notify_uuid):
            self.error_occurred.emit(ERR_BAD_UUID)
            return False
        self._closing = False
        self._ready = False
        self._was_open = False
        self._gen += 1
        gen = self._gen
        try:
            self._open_fut = get_loop().submit(self._connect_and_subscribe(gen))
        except Exception as exc:
            token = ERR_NO_BLEAK if "bleak" in str(exc).lower() else classify_bleak_error(exc)
            self.error_occurred.emit(token)
            return False
        return True

    def send(self, data, target=None):
        raw = bytes(data or b"")
        if not raw:
            return 0
        with self._lock:
            if not self._ready or self._closing:
                return 0
            if self._queued + len(raw) > MAX_QUEUED_BYTES:
                return 0
            self._queued += len(raw)
            self._pending.append(raw)
        get_loop().submit(self._drain())
        return len(raw)

    def close(self):
        was_open = self._was_open
        self._closing = True
        self._ready = False
        self._gen += 1
        with self._lock:
            self._pending.clear()
            self._queued = 0
            self._draining = False
        fut = self._open_fut
        if fut is not None and not fut.done():
            fut.cancel()
        self._open_fut = None
        client = self._client
        self._client = None
        notify_uuid = ble_uuid.normalize_uuid(self._notify_uuid)
        if client is not None:
            try:
                get_loop().submit(self._shutdown_client(client, notify_uuid))
            except Exception:
                _log.debug("BLE close submit failed", exc_info=True)
        if was_open:
            self.state_changed.emit(False)

    async def _shutdown_client(self, client, notify_uuid):
        try:
            if notify_uuid:
                stop = getattr(client, "stop_notify", None)
                if callable(stop):
                    await stop(notify_uuid)
        except Exception:
            _log.debug("BLE stop_notify failed", exc_info=True)
        try:
            disc = getattr(client, "disconnect", None)
            if callable(disc):
                await disc()
        except Exception:
            _log.debug("BLE disconnect failed", exc_info=True)

    async def _connect_and_subscribe(self, gen):
        client = None
        notify_started = False
        notify_uuid = ble_uuid.normalize_uuid(self._notify_uuid)
        try:
            factory = self.client_factory
            if factory is None:
                BleakClient, _scanner, _err = _import_bleak()
                factory = BleakClient

            def _disc(_c):
                self._on_remote_drop(gen)

            client = factory(
                self._address, disconnected_callback=_disc)
            await client.connect(timeout=CONNECT_TIMEOUT_S)
            if gen != self._gen or self._closing:
                await self._shutdown_client(client, "")
                return
            resolved = resolve_uart_chars(
                getattr(client, "services", None),
                self._service_uuid, self._write_uuid, self._notify_uuid)
            if not resolved.get("ok"):
                self.error_occurred.emit(resolved.get("error") or ERR_CONNECT)
                await self._shutdown_client(client, "")
                return
            notify_uuid = resolved["notify_uuid"]
            await client.start_notify(
                notify_uuid, lambda _s, data, g=gen: self._on_notify(g, data))
            notify_started = True
            if gen != self._gen or self._closing:
                await self._shutdown_client(client, notify_uuid)
                return
            mtu = getattr(client, "mtu_size", DEFAULT_ATT_MTU)
            self._chunk = write_chunk_size(mtu)
            self._write_uuid = resolved["write_uuid"]
            self._notify_uuid = notify_uuid
            self._write_without_response = bool(
                resolved.get("write_without_response"))
            if gen != self._gen or self._closing:
                await self._shutdown_client(client, notify_uuid)
                return
            self._client = client
            self._ready = True
            self._was_open = True
            self.state_changed.emit(True)
        except asyncio.CancelledError:
            if client is not None:
                await self._shutdown_client(
                    client, notify_uuid if notify_started else "")
        except Exception as exc:
            if gen != self._gen or self._closing:
                if client is not None:
                    await self._shutdown_client(
                        client, notify_uuid if notify_started else "")
                return
            token = classify_bleak_error(exc)
            if isinstance(exc, RuntimeError) and str(exc) == ERR_NO_BLEAK:
                token = ERR_NO_BLEAK
            _log.debug("BLE connect failed: %s", exc, exc_info=True)
            self.error_occurred.emit(token)
            if client is not None:
                await self._shutdown_client(
                    client, notify_uuid if notify_started else "")
        finally:
            if gen == self._gen:
                self._open_fut = None

    def _on_notify(self, gen, data):
        if gen != self._gen or self._closing or not self._ready:
            return
        raw = bytes(data or b"")
        if raw:
            self.data_received.emit(raw)

    def _on_remote_drop(self, gen):
        if gen != self._gen or self._closing:
            return
        if not self._was_open:
            return
        self._ready = False
        self.error_occurred.emit(ERR_GONE)

    async def _drain(self):
        with self._lock:
            if self._draining:
                return
            self._draining = True
        try:
            while True:
                with self._lock:
                    if not self._pending or not self._ready or self._closing:
                        return
                    pkt = self._pending.pop(0)
                client = self._client
                if client is None:
                    with self._lock:
                        self._queued = max(0, self._queued - len(pkt))
                    return
                try:
                    for chunk in fragment_payload(pkt, self._chunk):
                        await client.write_gatt_char(
                            self._write_uuid, chunk,
                            response=not self._write_without_response)
                except Exception as exc:
                    _log.debug("BLE write failed: %s", exc, exc_info=True)
                    if not self._closing:
                        self.error_occurred.emit(classify_bleak_error(exc))
                    return
                finally:
                    with self._lock:
                        self._queued = max(0, self._queued - len(pkt))
        finally:
            with self._lock:
                leftover = bool(self._pending) and self._ready and not self._closing
                self._draining = False
            if leftover:
                await self._drain()
