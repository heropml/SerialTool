import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from record import rec_replay
from record import pcap_export
from main_window import CommTool, PortScannerThread
from ui.rec_replay_dialog import RecReplayDialog


_APP = QApplication.instance() or QApplication([])


def _patch_window_runtime(monkeypatch, settings_path):
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(settings_path)))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)


def test_fc08_loopback_echo_is_validated(tmp_path, monkeypatch):
    """FC08 sub-0 is a loopback test: a wrong echo must not be reported as OK."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("mbm-fc08-validate-test")
    try:
        bad = window._t("mbm_st_badresp")
        info = {"func": 0x08, "qty": 1, "exp_diag": (0, 0x1234)}
        assert window._mbm_validate(info, {"diag": (0, 0x1234)}) is None
        assert window._mbm_validate(info, {"diag": (0, 0x9999)}) == bad
        assert window._mbm_validate(info, {"diag": (1, 0x1234)}) == bad
        # Non-zero sub-functions return counters etc., so only the sub echo counts.
        sub_b = {"func": 0x08, "qty": 1, "exp_diag": (0x0B, 0)}
        assert window._mbm_validate(sub_b, {"diag": (0x0B, 42)}) is None
        assert window._mbm_validate(sub_b, {"diag": (0x0C, 42)}) == bad
        # Old inflight dicts without exp_diag must stay permissive.
        assert window._mbm_validate({"func": 0x08, "qty": 1}, {"diag": (0, 1)}) is None
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_fc23_read_half_feeds_structured_samples(tmp_path, monkeypatch):
    """FC23's read half is holding registers; register defs only allow FC 3/4."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("mbm-fc23-structured-test")
    try:
        window._device_registers = [{
            "enabled": True, "name": "T1", "slave": 1, "function": 3,
            "address": 0, "type": "u16", "order": "AB", "unit": "C",
        }]
        window._structured_recorder.start()
        window._structured_feed_modbus(
            {"func": 0x17, "unit": 1, "addr": 0, "qty": 2}, {"regs": [10, 20]})
        rows = list(window._structured_recorder.rows)
        assert [r["tag"] for r in rows] == ["T1"]
        assert rows[0]["value"] == 10
    finally:
        window._structured_recorder.stop()
        window.deleteLater()
        _APP.processEvents()


def test_seeded_random_is_reproducible_after_reset():
    """A seeded rule must replay the same sequence after reset(), not continue it."""
    from modbus import modbus_dyn
    rules = [{"space": "holding", "addr": 0, "mode": "random",
              "min": 0, "max": 0xFFFF, "period_ms": 1000, "seed": 7}]
    eng = modbus_dyn.DynamicEngine(rules, now=0.0)
    first = [eng.value("holding", 0, now=t) for t in (0.0, 1.0, 2.0)]
    eng.reset(now=0.0)
    assert [eng.value("holding", 0, now=t) for t in (0.0, 1.0, 2.0)] == first
    assert len(set(first)) > 1


def test_replay_controls_disabled_while_not_playing(tmp_path, monkeypatch):
    """Pause/step/seek only act on a live player, so they must not look clickable."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("rr-controls-test")
    try:
        dlg = RecReplayDialog(window)
        try:
            widgets = (dlg.btn_pause, dlg.btn_step, dlg.ed_seek, dlg.btn_seek)
            assert not dlg.is_playing()
            assert [w.isEnabled() for w in widgets] == [False] * 4
            # 真实 Player，但不 start()/不接定时器：只让 is_playing() 为真
            dlg._player = rec_replay.Player([(0.0, "rx", b"A")], lambda *_: None)
            dlg._sync_controls()
            assert [w.isEnabled() for w in widgets] == [True] * 4
            dlg._player = None
            dlg._sync_controls()
            assert [w.isEnabled() for w in widgets] == [False] * 4
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_recording_dialog_keeps_multicast_peer_sidecar(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("rr-mcast-peer-sidecar")
    try:
        dlg = RecReplayDialog(window)
        try:
            link = {
                "proto": "UDP Multicast",
                "local_ip": "10.0.0.1", "local_port": 5000,
                "remote_ip": "239.0.0.1", "remote_port": 5000,
            }
            window._recorder.start(link=link)
            window._recorder.on_rx(b"A", t=1.0, source=("10.0.0.9", 40000))
            window._recorder.on_rx(b"B", t=1.1, source=("10.0.0.10", 40001))
            dlg.stop_recording()
            frames = pcap_export._iter_frames(
                dlg._events, pcap_export.normalize_link(dlg._link))
            assert [frame[26:30] for _t, frame in frames] == [
                bytes([10, 0, 0, 9]), bytes([10, 0, 0, 10])]
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()
