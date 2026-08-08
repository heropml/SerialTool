# -*- coding: utf-8 -*-
"""PC closed-loop soaks: Virtual TX->RX, TCP/UDP localhost, drop/reopen,
multi-client TCP, UDP no-remote, log size-rotate, .ctrec record (no hardware).

Default CI stays short (a few seconds). Optional gates:

  COMMTOOL_SOAK=<seconds>     extend Virtual / TCP / UDP / churn loops
  COMMTOOL_SOAK_METRICS=<path>  write a small JSON summary when set
  (also covers drop/reopen + TCP reconnect + recv-doc flood profiles)

One-shot runner: scripts/soak_local.bat
"""
from __future__ import print_function

import json
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

_APP = QApplication.instance() or QApplication([])


def _quiet_patches(monkeypatch):
    from main_window import CommTool, PortScannerThread
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)
    monkeypatch.setattr(CommTool, "toast", lambda self, *a, **k: None)


def _fresh_window(monkeypatch, tmp_path, profile="loop-soak"):
    _quiet_patches(monkeypatch)
    from main_window import CommTool
    ini = tmp_path / ("%s.ini" % profile)
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool(profile)
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    if hasattr(w, "sw_hexdump"):
        w.sw_hexdump.setChecked(False)
    if hasattr(w, "_hexdump_on"):
        w._hexdump_on = False
    if hasattr(w, "_terminal_on"):
        w._terminal_on = False
    return w


def _shutdown_window(w):
    try:
        for attr in ("send_timer", "_reconnect_timer", "_ms_cycle_timer",
                     "_seq_timer", "_kw_timer", "_ctrl_poll_timer",
                     "_reset_timer", "_rate_timer"):
            t = getattr(w, attr, None)
            if t is not None:
                t.stop()
        scanner = getattr(w, "port_scanner", None)
        if scanner is not None:
            scanner.stop()
    except Exception:
        pass
    try:
        if getattr(w, "conn", None) is not None:
            try:
                w.conn.close()
            except Exception:
                pass
            w.conn = None
    except Exception:
        pass
    try:
        w.close()
    except Exception:
        pass
    try:
        w.deleteLater()
    except Exception:
        pass
    for _ in range(5):
        _APP.processEvents()


def _soak_seconds():
    raw = os.environ.get("COMMTOOL_SOAK")
    if raw is None or not str(raw).strip():
        return None
    try:
        return max(1.0, float(raw))
    except ValueError:
        return None


def _pump(seconds=0.05):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        _APP.processEvents()


def _wait_until(pred, timeout=2.0, step=0.01):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        _APP.processEvents()
        if pred():
            return True
        time.sleep(step)
    return pred()


def _rss_mb():
    # Best-effort process RSS in MiB (Windows via ctypes; else None).
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return round(counters.WorkingSetSize / (1024.0 * 1024.0), 2)
    except Exception:
        return None
    return None


def _maybe_write_metrics(payload):
    """Append one case into a JSON list file (create or merge)."""
    path = str(os.environ.get("COMMTOOL_SOAK_METRICS", "") or "").strip()
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data["ts"] = time.time()
    rss = _rss_mb()
    if rss is not None:
        data["rss_mb"] = rss
    rows = []
    if out.is_file():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(prev, list):
                rows = prev
            elif isinstance(prev, dict):
                rows = [prev]
        except Exception:
            rows = []
    rows.append(data)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")


# ---- Virtual loopback (serial-path substitute) ----

def test_virtual_loopback_tx_rx_closed_loop(monkeypatch, tmp_path):
    """TX via VirtualConn(loopback) must arrive as RX on the main window."""
    from virtual_io import VirtualConn, PROTO_VIRTUAL

    w = _fresh_window(monkeypatch, tmp_path, "vloop")
    try:
        conn = VirtualConn(loopback=True)
        assert conn.open() is True
        w.conn = conn
        w._conn_engaged = True
        w._conn_proto = PROTO_VIRTUAL
        conn.data_received.connect(w.on_data_received)

        payload = b"LOOP-" + b"A" * 32
        n = 40
        before_rx = int(getattr(w, "rx_bytes", 0) or 0)
        sent = 0
        for _ in range(n):
            sent += conn.send(payload)
        assert sent == n * len(payload)
        assert _wait_until(
            lambda: (int(getattr(w, "rx_bytes", 0) or 0) - before_rx)
            >= sent,
            timeout=3.0)
        got = int(getattr(w, "rx_bytes", 0) or 0) - before_rx
        assert got == sent
        _maybe_write_metrics({
            "case": "virtual_loopback",
            "packets": n,
            "bytes": sent,
            "rx_bytes": got,
        })
    finally:
        _shutdown_window(w)


def test_virtual_loopback_survives_link_drop_mid_burst(monkeypatch, tmp_path):
    """Mid-burst simulate_link_drop must stop further RX without crashing."""
    from virtual_io import VirtualConn, PROTO_VIRTUAL

    w = _fresh_window(monkeypatch, tmp_path, "vdrop")
    try:
        conn = VirtualConn(loopback=True)
        assert conn.open() is True
        w.conn = conn
        w._conn_engaged = True
        w._conn_proto = PROTO_VIRTUAL
        w._user_closing = False
        conn.data_received.connect(w.on_data_received)
        conn.error_occurred.connect(w._on_conn_error)

        payload = b"X" * 16
        for _ in range(10):
            conn.send(payload)
        _pump(0.05)
        assert conn.simulate_link_drop("pc-loop-drop") is True
        _pump(0.05)
        assert not conn.is_open
        # Further send must be a no-op (0 bytes).
        assert conn.send(payload) == 0
    finally:
        _shutdown_window(w)


@pytest.mark.skipif(_soak_seconds() is None,
                    reason="set COMMTOOL_SOAK=<seconds> for extended virtual loop")
def test_extended_virtual_loopback_soak(monkeypatch, tmp_path):
    from virtual_io import VirtualConn, PROTO_VIRTUAL

    seconds = _soak_seconds()
    w = _fresh_window(monkeypatch, tmp_path, "vloop-ext")
    try:
        conn = VirtualConn(loopback=True)
        assert conn.open() is True
        w.conn = conn
        w._conn_engaged = True
        w._conn_proto = PROTO_VIRTUAL
        conn.data_received.connect(w.on_data_received)

        payload = b"SOAK" * 8
        before = int(getattr(w, "rx_bytes", 0) or 0)
        sent = 0
        cycles = 0
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            sent += conn.send(payload)
            cycles += 1
            if cycles % 25 == 0:
                _APP.processEvents()
        assert _wait_until(
            lambda: (int(getattr(w, "rx_bytes", 0) or 0) - before) >= sent,
            timeout=5.0)
        got = int(getattr(w, "rx_bytes", 0) or 0) - before
        assert got == sent
        _maybe_write_metrics({
            "case": "virtual_loopback_extended",
            "seconds": seconds,
            "cycles": cycles,
            "bytes": sent,
            "rx_bytes": got,
        })
    finally:
        _shutdown_window(w)


# ---- TCP localhost echo ----

def test_tcp_localhost_echo_closed_loop():
    """Server echoes client payloads on 127.0.0.1 (port 0)."""
    from net_io import TcpServerConn, TcpClientConn

    srv = TcpServerConn("127.0.0.1", 0)
    cli = TcpClientConn("127.0.0.1", 1)  # port patched after listen
    rx = []

    def _echo(data, key):
        srv.send(data, target=key)

    try:
        assert srv.open() is True
        port = srv.bound_port
        assert port > 0
        cli._port = port
        srv.data_received_from.connect(_echo)
        cli.data_received.connect(lambda b: rx.append(bytes(b)))

        assert cli.open() is True
        assert _wait_until(lambda: cli.is_open and srv.bridge_ready, timeout=3.0)

        payload = b"TCP-ECHO-" + b"B" * 24
        n = 30
        sent = 0
        for _ in range(n):
            sent += cli.send(payload)
            _APP.processEvents()
        assert sent == n * len(payload)
        assert _wait_until(
            lambda: sum(len(x) for x in rx) >= sent, timeout=3.0)
        assert sum(len(x) for x in rx) == sent
        _maybe_write_metrics({
            "case": "tcp_localhost_echo",
            "port": port,
            "packets": n,
            "bytes": sent,
            "rx_bytes": sum(len(x) for x in rx),
        })
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass
        _pump(0.05)


def test_tcp_localhost_peer_drop_stops_echo():
    """Closing the client must leave the server listening without clients."""
    from net_io import TcpServerConn, TcpClientConn

    srv = TcpServerConn("127.0.0.1", 0)
    cli = TcpClientConn("127.0.0.1", 1)
    try:
        assert srv.open() is True
        cli._port = srv.bound_port
        assert cli.open() is True
        assert _wait_until(lambda: cli.is_open and srv.bridge_ready, timeout=3.0)
        cli.close()
        assert _wait_until(lambda: (not cli.is_open) and (not srv.bridge_ready),
                           timeout=3.0)
        assert srv.is_open
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass
        _pump(0.05)


@pytest.mark.skipif(_soak_seconds() is None,
                    reason="set COMMTOOL_SOAK=<seconds> for extended TCP echo")
def test_extended_tcp_localhost_echo_soak():
    from net_io import TcpServerConn, TcpClientConn

    seconds = _soak_seconds()
    srv = TcpServerConn("127.0.0.1", 0)
    cli = TcpClientConn("127.0.0.1", 1)
    rx_bytes = [0]

    def _echo(data, key):
        srv.send(data, target=key)

    def _on_rx(b):
        rx_bytes[0] += len(b)

    try:
        assert srv.open() is True
        cli._port = srv.bound_port
        srv.data_received_from.connect(_echo)
        cli.data_received.connect(_on_rx)
        assert cli.open() is True
        assert _wait_until(lambda: cli.is_open and srv.bridge_ready, timeout=3.0)

        payload = b"N" * 64
        sent = 0
        cycles = 0
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            sent += cli.send(payload)
            cycles += 1
            if cycles % 20 == 0:
                _APP.processEvents()
        assert _wait_until(lambda: rx_bytes[0] >= sent, timeout=5.0)
        assert rx_bytes[0] == sent
        _maybe_write_metrics({
            "case": "tcp_localhost_echo_extended",
            "seconds": seconds,
            "cycles": cycles,
            "bytes": sent,
            "rx_bytes": rx_bytes[0],
        })
    finally:
        try:
            cli.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass
        _pump(0.05)


# ---- UDP localhost pair ----

def test_udp_localhost_pair_closed_loop():
    """Two UdpConn on 127.0.0.1 exchange datagrams (port 0)."""
    from net_io import UdpConn

    a = UdpConn("127.0.0.1", 0, "127.0.0.1", 0)
    b = UdpConn("127.0.0.1", 0, "127.0.0.1", 0)
    rx_a, rx_b = [], []
    try:
        assert a.open() is True
        assert b.open() is True
        pa, pb = a.bound_port, b.bound_port
        assert pa > 0 and pb > 0 and pa != pb
        a._remote_port = pb
        b._remote_port = pa
        a.data_received.connect(lambda d: rx_a.append(bytes(d)))
        b.data_received.connect(lambda d: rx_b.append(bytes(d)))

        payload = b"UDP-" + b"C" * 20
        n = 25
        sent_ab = sent_ba = 0
        for _ in range(n):
            sent_ab += a.send(payload)
            sent_ba += b.send(payload)
            _APP.processEvents()
        assert sent_ab == n * len(payload)
        assert sent_ba == n * len(payload)
        assert _wait_until(
            lambda: (sum(len(x) for x in rx_b) >= sent_ab
                     and sum(len(x) for x in rx_a) >= sent_ba),
            timeout=3.0)
        assert sum(len(x) for x in rx_b) == sent_ab
        assert sum(len(x) for x in rx_a) == sent_ba
        _maybe_write_metrics({
            "case": "udp_localhost_pair",
            "ports": [pa, pb],
            "bytes_ab": sent_ab,
            "bytes_ba": sent_ba,
        })
    finally:
        try:
            a.close()
        except Exception:
            pass
        try:
            b.close()
        except Exception:
            pass
        _pump(0.05)


@pytest.mark.skipif(_soak_seconds() is None,
                    reason="set COMMTOOL_SOAK=<seconds> for extended UDP pair")
def test_extended_udp_localhost_pair_soak():
    from net_io import UdpConn

    seconds = _soak_seconds()
    a = UdpConn("127.0.0.1", 0, "127.0.0.1", 0)
    b = UdpConn("127.0.0.1", 0, "127.0.0.1", 0)
    rx_b = [0]
    try:
        assert a.open() is True and b.open() is True
        a._remote_port = b.bound_port
        b._remote_port = a.bound_port
        b.data_received.connect(lambda d: rx_b.__setitem__(0, rx_b[0] + len(d)))

        payload = b"U" * 48
        sent = 0
        cycles = 0
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            sent += a.send(payload)
            cycles += 1
            if cycles % 20 == 0:
                _APP.processEvents()
        assert _wait_until(lambda: rx_b[0] >= sent, timeout=5.0)
        assert rx_b[0] == sent
        _maybe_write_metrics({
            "case": "udp_localhost_pair_extended",
            "seconds": seconds,
            "cycles": cycles,
            "bytes": sent,
            "rx_bytes": rx_b[0],
        })
    finally:
        try:
            a.close()
        except Exception:
            pass
        try:
            b.close()
        except Exception:
            pass
        _pump(0.05)


# ---- Drop / reconnect closed loops (still no hardware) ----

def _attach_virtual(w, loopback=True):
    from virtual_io import VirtualConn, PROTO_VIRTUAL
    conn = VirtualConn(loopback=loopback)
    assert conn.open() is True
    w.conn = conn
    w._conn_engaged = True
    w._conn_proto = PROTO_VIRTUAL
    w._user_closing = False
    conn.data_received.connect(w.on_data_received)
    return conn


def test_virtual_drop_reopen_continues_loopback(monkeypatch, tmp_path):
    """After simulate_link_drop, a fresh VirtualConn must keep TX->RX integrity."""
    w = _fresh_window(monkeypatch, tmp_path, "v-reopen")
    try:
        payload = b"PHASE-" + b"D" * 20
        total_sent = 0
        before = int(getattr(w, "rx_bytes", 0) or 0)

        conn = _attach_virtual(w, loopback=True)
        for _ in range(15):
            total_sent += conn.send(payload)
        assert _wait_until(
            lambda: (int(getattr(w, "rx_bytes", 0) or 0) - before) >= total_sent,
            timeout=3.0)

        assert conn.simulate_link_drop("phase-drop") is True
        _pump(0.05)
        assert not conn.is_open

        conn2 = _attach_virtual(w, loopback=True)
        phase2 = 0
        for _ in range(15):
            phase2 += conn2.send(payload)
        total_sent += phase2
        assert _wait_until(
            lambda: (int(getattr(w, "rx_bytes", 0) or 0) - before) >= total_sent,
            timeout=3.0)
        got = int(getattr(w, "rx_bytes", 0) or 0) - before
        assert got == total_sent
        _maybe_write_metrics({
            "case": "virtual_drop_reopen",
            "bytes": total_sent,
            "rx_bytes": got,
            "reopen": 1,
        })
    finally:
        _shutdown_window(w)


def test_tcp_reconnect_after_client_close_continues_echo():
    """Client close + reopen must resume echo with byte integrity."""
    from net_io import TcpServerConn, TcpClientConn

    srv = TcpServerConn("127.0.0.1", 0)
    rx = []

    def _echo(data, key):
        srv.send(data, target=key)

    try:
        assert srv.open() is True
        port = srv.bound_port
        srv.data_received_from.connect(_echo)

        def _new_client():
            c = TcpClientConn("127.0.0.1", port)
            c.data_received.connect(lambda b: rx.append(bytes(b)))
            assert c.open() is True
            assert _wait_until(lambda: c.is_open and srv.bridge_ready, timeout=3.0)
            return c

        cli = _new_client()
        payload = b"RE-" + b"E" * 16
        sent = 0
        for _ in range(12):
            sent += cli.send(payload)
            _APP.processEvents()
        assert _wait_until(lambda: sum(len(x) for x in rx) >= sent, timeout=3.0)

        cli.close()
        assert _wait_until(lambda: not srv.bridge_ready, timeout=3.0)

        cli2 = _new_client()
        phase2 = 0
        for _ in range(12):
            phase2 += cli2.send(payload)
            _APP.processEvents()
        sent += phase2
        assert _wait_until(lambda: sum(len(x) for x in rx) >= sent, timeout=3.0)
        assert sum(len(x) for x in rx) == sent
        _maybe_write_metrics({
            "case": "tcp_reconnect_echo",
            "port": port,
            "bytes": sent,
            "rx_bytes": sum(len(x) for x in rx),
            "reopen": 1,
        })
        cli2.close()
    finally:
        try:
            srv.close()
        except Exception:
            pass
        _pump(0.05)


def test_virtual_loopback_recv_doc_bounded_under_flood(monkeypatch, tmp_path):
    """Loopback flood must keep recv document within max-lines budget."""
    w = _fresh_window(monkeypatch, tmp_path, "v-flood")
    try:
        w.ed_max_lines.setText("100")
        w._on_max_lines_changed()
        assert w.txt_recv.document().maximumBlockCount() == 100

        conn = _attach_virtual(w, loopback=True)
        for i in range(400):
            conn.send(("LINE-%04d\n" % i).encode("ascii"))
            if i % 40 == 0:
                _APP.processEvents()
        assert _wait_until(
            lambda: int(getattr(w, "rx_bytes", 0) or 0) > 0, timeout=3.0)
        _pump(0.1)
        blocks = w.txt_recv.document().blockCount()
        assert blocks <= 102, "blockCount=%d" % blocks
        chars = w.txt_recv.document().characterCount()
        assert chars < 200_000
        _maybe_write_metrics({
            "case": "virtual_flood_doc_bound",
            "blocks": blocks,
            "chars": chars,
            "rx_bytes": int(getattr(w, "rx_bytes", 0) or 0),
        })
    finally:
        _shutdown_window(w)


@pytest.mark.skipif(_soak_seconds() is None,
                    reason="set COMMTOOL_SOAK=<seconds> for drop/reopen churn")
def test_extended_virtual_drop_reopen_churn(monkeypatch, tmp_path):
    """Repeated drop/reopen under COMMTOOL_SOAK keeps TX/RX matched."""
    seconds = _soak_seconds()
    w = _fresh_window(monkeypatch, tmp_path, "v-churn-ext")
    try:
        payload = b"CHURN" * 4
        before = int(getattr(w, "rx_bytes", 0) or 0)
        sent = 0
        drops = 0
        t0 = time.perf_counter()
        conn = _attach_virtual(w, loopback=True)
        while time.perf_counter() - t0 < seconds:
            for _ in range(8):
                sent += conn.send(payload)
            _APP.processEvents()
            # Drain pending loopback timers before drop so RX matches TX.
            assert _wait_until(
                lambda s=sent, b=before: (
                    int(getattr(w, "rx_bytes", 0) or 0) - b) >= s,
                timeout=2.0)
            assert conn.simulate_link_drop("churn") is True
            drops += 1
            _pump(0.01)
            conn = _attach_virtual(w, loopback=True)
        _pump(0.2)
        got = int(getattr(w, "rx_bytes", 0) or 0) - before
        assert got == sent, "rx=%d sent=%d drops=%d" % (got, sent, drops)
        _maybe_write_metrics({
            "case": "virtual_drop_reopen_extended",
            "seconds": seconds,
            "drops": drops,
            "bytes": sent,
            "rx_bytes": got,
        })
    finally:
        _shutdown_window(w)


# ---- Remaining PC-only closed loops ----

def test_tcp_multiclient_broadcast_and_target():
    """Two clients: targeted echo stays private; broadcast reaches both;
    dropping one client must not break the other."""
    from net_io import TcpServerConn, TcpClientConn

    srv = TcpServerConn("127.0.0.1", 0)
    rx_a, rx_b = [], []

    def _echo(data, key):
        srv.send(data, target=key)

    try:
        assert srv.open() is True
        port = srv.bound_port

        def _client(bucket):
            c = TcpClientConn("127.0.0.1", port)
            c.data_received.connect(lambda b, bucket=bucket: bucket.append(bytes(b)))
            assert c.open() is True
            assert _wait_until(lambda: c.is_open, timeout=3.0)
            return c

        cli_a = _client(rx_a)
        cli_b = _client(rx_b)
        assert _wait_until(lambda: len(srv._clients) == 2, timeout=3.0)
        srv.data_received_from.connect(_echo)

        # Targeted echo: only A should see its own payload echoed.
        payload_a = b"ONLY-A-" + b"1" * 12
        assert cli_a.send(payload_a) == len(payload_a)
        assert _wait_until(lambda: sum(len(x) for x in rx_a) >= len(payload_a),
                           timeout=3.0)
        assert sum(len(x) for x in rx_a) == len(payload_a)
        assert sum(len(x) for x in rx_b) == 0

        # Broadcast from server reaches both.
        bcast = b"BCAST-" + b"2" * 10
        assert srv.send(bcast) == len(bcast)
        assert _wait_until(
            lambda: (sum(len(x) for x in rx_a) >= len(payload_a) + len(bcast)
                     and sum(len(x) for x in rx_b) >= len(bcast)),
            timeout=3.0)

        # Drop B; A continues echo.
        before_a = sum(len(x) for x in rx_a)
        cli_b.close()
        assert _wait_until(lambda: len(srv._clients) == 1, timeout=3.0)
        payload2 = b"AFTER-B-" + b"3" * 8
        assert cli_a.send(payload2) == len(payload2)
        assert _wait_until(
            lambda: sum(len(x) for x in rx_a) >= before_a + len(payload2),
            timeout=3.0)
        assert sum(len(x) for x in rx_b) == len(bcast)
        _maybe_write_metrics({
            "case": "tcp_multiclient",
            "port": port,
            "clients": 2,
            "rx_a": sum(len(x) for x in rx_a),
            "rx_b": sum(len(x) for x in rx_b),
        })
        cli_a.close()
    finally:
        try:
            srv.close()
        except Exception:
            pass
        _pump(0.05)


def test_udp_no_remote_then_reply_last_peer():
    """Empty remote => SEND_NO_TARGET until a peer speaks; then reply works."""
    from net_io import UdpConn, SEND_NO_TARGET

    sink = UdpConn("127.0.0.1", 0, "", 0)
    peer = UdpConn("127.0.0.1", 0, "127.0.0.1", 0)
    got = []
    peer_rx = []
    try:
        assert sink.open() is True
        assert peer.open() is True
        peer._remote_port = sink.bound_port
        sink.data_received.connect(lambda d: got.append(bytes(d)))
        peer.data_received.connect(lambda d: peer_rx.append(bytes(d)))

        assert sink.send(b"NOPE") == SEND_NO_TARGET
        assert not sink.bridge_ready

        hello = b"HELLO-PEER"
        assert peer.send(hello) == len(hello)
        assert _wait_until(lambda: got == [hello], timeout=3.0)
        assert sink.bridge_ready

        reply = b"REPLY-OK"
        assert sink.send(reply) == len(reply)
        assert _wait_until(lambda: peer_rx == [reply], timeout=3.0)
        _maybe_write_metrics({
            "case": "udp_no_remote_then_last_peer",
            "ports": [sink.bound_port, peer.bound_port],
        })
    finally:
        try:
            sink.close()
        except Exception:
            pass
        try:
            peer.close()
        except Exception:
            pass
        _pump(0.05)


def test_udp_fixed_remote_works_without_prior_rx():
    """Configured remote must send successfully with no prior datagram."""
    from net_io import UdpConn, SEND_NO_TARGET

    a = UdpConn("127.0.0.1", 0, "127.0.0.1", 0)
    b = UdpConn("127.0.0.1", 0, "127.0.0.1", 0)
    rx = []
    try:
        assert a.open() is True and b.open() is True
        a._remote_port = b.bound_port
        b.data_received.connect(lambda d: rx.append(bytes(d)))
        assert a.bridge_ready
        payload = b"FIXED-REMOTE"
        n = a.send(payload)
        assert n == len(payload), "send returned %r" % (n,)
        assert n != SEND_NO_TARGET
        _APP.processEvents()
        assert _wait_until(
            lambda: sum(len(x) for x in rx) >= len(payload), timeout=3.0), rx
        assert b"".join(rx) == payload
        _maybe_write_metrics({
            "case": "udp_fixed_remote",
            "bytes": len(payload),
        })
    finally:
        try:
            a.close()
        except Exception:
            pass
        try:
            b.close()
        except Exception:
            pass
        _pump(0.05)


def test_log_size_rotate_under_virtual_loopback(monkeypatch, tmp_path):
    """Tiny size limit must roll log segments while Virtual RX keeps flowing."""
    from datetime import datetime

    w = _fresh_window(monkeypatch, tmp_path, "log-roll")
    try:
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        base = str(log_dir / "soak.log")
        w._log_base_path = base
        w._log_seg = 0
        w._log_limit = 1200
        w.sw_log_file.blockSignals(True)
        w.sw_log_file.setChecked(True)
        w.sw_log_file.blockSignals(False)
        now = datetime.now()
        assert w._open_log_segment(w._log_segment_path(now), when=now)

        conn = _attach_virtual(w, loopback=True)
        for i in range(250):
            conn.send(("L%04d-" % i + ("X" * 48) + "\n").encode("ascii"))
            if i % 25 == 0:
                _APP.processEvents()
        assert _wait_until(lambda: int(getattr(w, "rx_bytes", 0) or 0) > 0,
                           timeout=3.0)
        _pump(0.15)
        assert w._log_seg >= 1, "expected size rotate, seg=%d" % w._log_seg
        files = sorted(log_dir.glob("soak*.log"))
        assert len(files) >= 2, "files=%s" % [f.name for f in files]
        total = sum(f.stat().st_size for f in files if f.is_file())
        assert total > 0
        w._close_log_file()
        _maybe_write_metrics({
            "case": "log_size_rotate",
            "segments": int(w._log_seg) + 1,
            "files": len(files),
            "bytes_on_disk": total,
            "rx_bytes": int(getattr(w, "rx_bytes", 0) or 0),
        })
    finally:
        try:
            w._close_log_file()
        except Exception:
            pass
        _shutdown_window(w)


def test_ctrec_record_under_virtual_loopback(monkeypatch, tmp_path):
    """.ctrec stream recorder captures Virtual loopback RX/TX offline."""
    w = _fresh_window(monkeypatch, tmp_path, "ctrec")
    try:
        conn = _attach_virtual(w, loopback=True)
        w._recorder.start()
        assert w._recorder.recording
        payload = b"CTREC-" + b"R" * 16
        sent = 0
        for _ in range(20):
            # TX side via recorder hook used by main window send path:
            w._record_stream_tx(payload)
            sent += conn.send(payload)
        assert _wait_until(
            lambda: int(getattr(w, "rx_bytes", 0) or 0) >= sent, timeout=3.0)
        _pump(0.05)
        w._recorder.stop()
        assert w._recorder.rx_count >= 1
        assert w._recorder.tx_count >= 1
        out = tmp_path / "loop.ctrec"
        w._recorder.save(str(out))
        assert out.is_file() and out.stat().st_size > 0
        text = out.read_text(encoding="utf-8", errors="replace")
        assert "ctrec" in text.lower() or "_\"ctrec\"" in text or "\"_\"" in text
        _maybe_write_metrics({
            "case": "ctrec_virtual_loopback",
            "rx_events": w._recorder.rx_count,
            "tx_events": w._recorder.tx_count,
            "file_bytes": out.stat().st_size,
        })
    finally:
        try:
            w._recorder.stop()
        except Exception:
            pass
        _shutdown_window(w)


@pytest.mark.skipif(_soak_seconds() is None,
                    reason="set COMMTOOL_SOAK=<seconds> for extended log rotate")
def test_extended_log_rotate_virtual_flood(monkeypatch, tmp_path):
    """Longer Virtual flood under tiny log limit keeps rotating cleanly."""
    from datetime import datetime

    seconds = _soak_seconds()
    w = _fresh_window(monkeypatch, tmp_path, "log-roll-ext")
    try:
        log_dir = tmp_path / "logs_ext"
        log_dir.mkdir()
        w._log_base_path = str(log_dir / "ext.log")
        w._log_seg = 0
        w._log_limit = 2048
        w.sw_log_file.blockSignals(True)
        w.sw_log_file.setChecked(True)
        w.sw_log_file.blockSignals(False)
        now = datetime.now()
        assert w._open_log_segment(w._log_segment_path(now), when=now)
        conn = _attach_virtual(w, loopback=True)
        t0 = time.perf_counter()
        n = 0
        while time.perf_counter() - t0 < seconds:
            conn.send(("E%05d-" % n + ("Y" * 64) + "\n").encode("ascii"))
            n += 1
            if n % 40 == 0:
                _APP.processEvents()
        _pump(0.2)
        files = list(log_dir.glob("ext*.log"))
        assert w._log_seg >= 1
        assert len(files) >= 2
        w._close_log_file()
        _maybe_write_metrics({
            "case": "log_size_rotate_extended",
            "seconds": seconds,
            "loops": n,
            "segments": int(w._log_seg) + 1,
            "files": len(files),
        })
    finally:
        try:
            w._close_log_file()
        except Exception:
            pass
        _shutdown_window(w)

