# -*- coding: utf-8 -*-
"""S-3 soak / throughput baselines (CI-friendly + optional extended).

Default suite stays under a few seconds:
  - RX burst throughput smoke
  - RX path with side-channels
  - recv document growth bounded by max-lines
  - auto-reconnect schedule/cancel / attempt-limit churn

Set COMMTOOL_SOAK=<seconds> (e.g. 30) to enable an extended RX loop.
True multi-hour soak belongs in a nightly job, not default CI.
"""
import gc
import os
import sys
import time
import tempfile
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


def _fresh_window(monkeypatch, tmp_path, profile="soak-test"):
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
    """Stop timers/scanner so the shared QApplication does not AV later."""
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
        w.close()
    except Exception:
        pass
    try:
        w.deleteLater()
    except Exception:
        pass
    for _ in range(5):
        _APP.processEvents()


def test_rx_burst_throughput_smoke(monkeypatch, tmp_path):
    w = _fresh_window(monkeypatch, tmp_path, "burst")
    try:
        payload = b"0123456789ABCDEF" * 8  # 128 B
        n = 2000
        before = getattr(w, "rx_bytes", 0) or 0
        t0 = time.perf_counter()
        for _ in range(n):
            w._on_data_received_impl(payload)
        elapsed = time.perf_counter() - t0
        after = getattr(w, "rx_bytes", 0) or 0
        assert after - before == n * len(payload)
        assert elapsed < 30.0, "RX burst took %.2fs for %d packets" % (elapsed, n)
        chars = w.txt_recv.document().characterCount()
        assert chars > 0
        assert chars < 50_000_000
        # Soft throughput baseline for CI machines (very conservative).
        pps = n / max(elapsed, 1e-6)
        assert pps > 50.0, "RX path too slow: %.1f pkt/s" % pps
    finally:
        _shutdown_window(w)


def test_rx_burst_with_side_channels_enabled(monkeypatch, tmp_path):
    """Side observers (_rx_side) must not abort the main path under load."""
    w = _fresh_window(monkeypatch, tmp_path, "side")
    try:
        if hasattr(w, "_recorder") and hasattr(w._recorder, "recording"):
            w._recorder.recording = True
        payload = b"PING\r\n"
        for _ in range(500):
            w.on_data_received(payload)
        assert (getattr(w, "rx_bytes", 0) or 0) >= 500 * len(payload)
    finally:
        if hasattr(w, "_recorder"):
            w._recorder.recording = False
        _shutdown_window(w)


def test_recv_max_lines_bounds_document_under_sustained_rx(monkeypatch, tmp_path):
    """Sustained RX must not grow the recv document past max-lines."""
    w = _fresh_window(monkeypatch, tmp_path, "maxlines")
    try:
        # UI clamps max-lines to [100, 1_000_000].
        w.ed_max_lines.setText("100")
        w._on_max_lines_changed()
        assert w.txt_recv.document().maximumBlockCount() == 100
        for i in range(500):
            w._on_data_received_impl(("LINE-%04d\n" % i).encode("ascii"))
        blocks = w.txt_recv.document().blockCount()
        assert blocks <= 102, "blockCount=%d not bounded by max-lines" % blocks
        chars = w.txt_recv.document().characterCount()
        assert chars < 200_000
        assert (getattr(w, "rx_bytes", 0) or 0) > 0
    finally:
        _shutdown_window(w)


def test_recv_char_budget_without_newlines(monkeypatch, tmp_path):
    """P1: max-lines alone is not enough when stream has no newlines.

    With line_split and packet_split off, all RX stays in one QTextBlock;
    setMaximumBlockCount cannot trim. Char budget must clip the document.
    """
    from main_window import _RECV_CHARS_PER_LINE

    w = _fresh_window(monkeypatch, tmp_path, "nobreak")
    try:
        if hasattr(w, "sw_line_split"):
            w.sw_line_split.setChecked(False)
        if hasattr(w, "sw_packet_split"):
            w.sw_packet_split.setChecked(False)
        w.ed_max_lines.setText("100")
        w._on_max_lines_changed()
        budget = w._recv_char_budget()
        assert budget == 100 * _RECV_CHARS_PER_LINE
        payload = b"X" * 64
        for _ in range(2000):
            w._on_data_received_impl(payload)
        chars = w.txt_recv.document().characterCount()
        # characterCount includes trailing paragraph separator (+1).
        assert chars <= budget + 2, "chars=%d budget=%d" % (chars, budget)
        assert w.txt_recv.document().blockCount() <= 2
    finally:
        _shutdown_window(w)


def test_terminal_char_budget_without_newlines(monkeypatch, tmp_path):
    """P1: terminal path must apply the same char budget (bypasses append_block)."""
    from main_window import _RECV_CHARS_PER_LINE

    w = _fresh_window(monkeypatch, tmp_path, "term-nobreak")
    try:
        w._terminal_on = True
        w.ed_max_lines.setText("100")
        w._on_max_lines_changed()
        budget = w._recv_char_budget()
        assert budget == 100 * _RECV_CHARS_PER_LINE
        payload = b"X" * 64
        for _ in range(2000):
            w._on_data_received_impl(payload)
        chars = w.txt_recv.document().characterCount()
        assert chars <= budget + 2, "chars=%d budget=%d" % (chars, budget)
        last = w.txt_recv.document().characterCount() - 1
        assert w._term_pos is None or 0 <= w._term_pos <= last
    finally:
        _shutdown_window(w)


def test_reconnect_schedule_cancel_and_limit_churn(monkeypatch, tmp_path):
    """Auto-reconnect timer churn + serial attempt cap stay deterministic."""
    w = _fresh_window(monkeypatch, tmp_path, "reconn")
    try:
        w.settings.setValue("auto_reconnect", True)
        opens = []
        w.open_conn = lambda reconnect_cfg=None: opens.append(reconnect_cfg)
        cfg = ("Serial", "COM9", 9600, "8", "None", "1", "None")
        w._serial_reconnect_cfg = cfg
        w._available_serial_devices = {"COM9"}
        w._reconnect_attempts = 0
        w.conn = None
        w._user_closing = False

        # Cancel churn: schedule then cancel repeatedly.
        for _ in range(20):
            w._schedule_reconnect()
            assert w._reconnect_timer.isActive()
            w._cancel_reconnect()
            assert not w._reconnect_timer.isActive()

        # Attempt-limit: keep failing open until serial budget is exhausted.
        w._reconnect_attempts = 0
        w._serial_reconnect_cfg = cfg
        opens.clear()
        for _ in range(w._serial_reconnect_limit + 5):
            if w._serial_reconnect_cfg is None:
                break
            w._try_reconnect()
            w._cancel_reconnect()
        assert w._serial_reconnect_cfg is None
        assert w._reconnect_attempts == 0
        assert len(opens) == w._serial_reconnect_limit
    finally:
        _shutdown_window(w)


def test_mixed_rx_tx_counter_burst(monkeypatch, tmp_path):
    """RX/TX counters and rate tick stay coherent under mixed bursts."""
    w = _fresh_window(monkeypatch, tmp_path, "mixed")
    try:
        rx_n, tx_n = 300, 200
        payload = b"X" * 32
        for _ in range(rx_n):
            w._on_data_received_impl(payload)
        for _ in range(tx_n):
            w._stat_note_tx(len(payload))
        assert w.rx_bytes == rx_n * len(payload)
        assert w.tx_bytes == tx_n * len(payload)
        assert w.rx_packets >= rx_n
        assert w.tx_packets >= tx_n
        # Rate tick should not throw and should leave peaks non-negative.
        if hasattr(w, "_tick_rate"):
            w._tick_rate()
        assert getattr(w, "_rx_rate", 0) >= 0
        assert getattr(w, "_tx_rate", 0) >= 0
    finally:
        _shutdown_window(w)



def test_terminal_toggle_char_budget_burst(monkeypatch, tmp_path):
    """S-3: flipping terminal mode mid-burst must not unbounded-grow the doc."""
    from main_window import _RECV_CHARS_PER_LINE

    w = _fresh_window(monkeypatch, tmp_path, "term-toggle")
    try:
        w.ed_max_lines.setText("100")
        w._on_max_lines_changed()
        budget = w._recv_char_budget()
        assert budget == 100 * _RECV_CHARS_PER_LINE
        payload = b"Z" * 48
        for i in range(1200):
            w._terminal_on = (i % 40) >= 20
            w._on_data_received_impl(payload)
            if i % 100 == 0:
                _APP.processEvents()
        chars = w.txt_recv.document().characterCount()
        assert chars <= budget + 2, "chars=%d budget=%d" % (chars, budget)
    finally:
        _shutdown_window(w)


def test_reconnect_churn_under_rx_burst(monkeypatch, tmp_path):
    """S-3: reconnect schedule/cancel interleaved with RX must stay stable."""
    w = _fresh_window(monkeypatch, tmp_path, "reconn-rx")
    try:
        w.settings.setValue("auto_reconnect", True)
        opens = []
        w.open_conn = lambda reconnect_cfg=None: opens.append(reconnect_cfg)
        cfg = ("Serial", "COM9", 9600, "8", "None", "1", "None")
        w._serial_reconnect_cfg = cfg
        w._available_serial_devices = {"COM9"}
        w._reconnect_attempts = 0
        w.conn = None
        w._user_closing = False
        payload = b"RX" * 16
        for i in range(80):
            w._schedule_reconnect()
            w._on_data_received_impl(payload)
            if i % 2 == 0:
                w._cancel_reconnect()
            if i % 10 == 0:
                _APP.processEvents()
        w._cancel_reconnect()
        assert not w._reconnect_timer.isActive()
        assert w.rx_bytes == 80 * len(payload)
    finally:
        _shutdown_window(w)


def _soak_seconds_from_env(env=None):
    """Parse COMMTOOL_SOAK; return None if unset/blank/invalid.

    Default CI cap is 600s. Set COMMTOOL_SOAK_NIGHTLY=1 to allow up to 4h
    for overnight jobs (still no real serial hardware required).
    """
    env = os.environ if env is None else env
    raw = env.get("COMMTOOL_SOAK")
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    nightly = str(env.get("COMMTOOL_SOAK_NIGHTLY", "")).strip().lower() in (
        "1", "true", "yes", "on",
    )
    cap = 14400.0 if nightly else 600.0
    try:
        return max(1.0, min(float(text), cap))
    except (TypeError, ValueError):
        return None


def test_soak_seconds_from_env_rejects_invalid():
    assert _soak_seconds_from_env({}) is None
    assert _soak_seconds_from_env({"COMMTOOL_SOAK": ""}) is None
    assert _soak_seconds_from_env({"COMMTOOL_SOAK": "abc"}) is None
    assert _soak_seconds_from_env({"COMMTOOL_SOAK": "5"}) == 5.0
    assert _soak_seconds_from_env({"COMMTOOL_SOAK": "0.5"}) == 1.0
    assert _soak_seconds_from_env({"COMMTOOL_SOAK": "9999"}) == 600.0
    assert _soak_seconds_from_env(
        {"COMMTOOL_SOAK": "9999", "COMMTOOL_SOAK_NIGHTLY": "1"}) == 9999.0
    assert _soak_seconds_from_env(
        {"COMMTOOL_SOAK": "99999", "COMMTOOL_SOAK_NIGHTLY": "1"}) == 14400.0


@pytest.mark.skipif(
    _soak_seconds_from_env() is None,
    reason="set COMMTOOL_SOAK=<seconds> for extended soak",
)
def test_extended_rx_soak_optional(monkeypatch, tmp_path):
    """Optional longer RX loop; memory must not climb without bound."""
    seconds = _soak_seconds_from_env()
    assert seconds is not None
    w = _fresh_window(monkeypatch, tmp_path, "extsoak")
    try:
        w.ed_max_lines.setText("200")
        w._on_max_lines_changed()
        payload = b"SOAK" * 16
        t0 = time.perf_counter()
        n = 0
        samples = []
        while time.perf_counter() - t0 < seconds:
            for _ in range(50):
                w._on_data_received_impl(payload)
                n += 1
            _APP.processEvents()
            if n % 500 == 0:
                gc.collect()
                samples.append(w.txt_recv.document().characterCount())
        assert n >= 50
        assert w.rx_bytes == n * len(payload)
        assert w.txt_recv.document().blockCount() <= 220
        budget = w._recv_char_budget()
        assert w.txt_recv.document().characterCount() <= budget + 2
        # Later samples should not keep growing forever (char/block budget).
        if len(samples) >= 2:
            assert samples[-1] <= budget + 2
            assert samples[-1] <= samples[0] * 3 + 50_000
    finally:
        _shutdown_window(w)
