# -*- coding: utf-8 -*-
"""Regression tests for High/Medium bugfix batch (H1, M6, M12, …)."""
import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from record import rec_replay
from main_window import CommTool, PortScannerThread
from ui.structured_record_dialog import StructuredRecordDialog

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


def _sample(tag, ts, value=1, source="modbus"):
    return {"timestamp": ts, "source": source, "tag": tag, "value": value,
            "unit": "", "raw": "", "slave": 1, "function": 3, "address": 0}


def test_h1_filter_during_replay_stops_and_resyncs(tmp_path, monkeypatch):
    """Filtering while replaying must stop and rebuild from the new list."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("h1-replay-filter")
    try:
        window._structured_recorder.start()
        window._structured_recorder.add([
            _sample("A", 1000.0),
            _sample("B", 1001.0),
            _sample("A", 1002.0),
        ])
        dlg = StructuredRecordDialog(window)
        try:
            dlg.refresh_rows()
            assert len(dlg._replay_rows) == 3
            dlg._toggle_replay()
            assert dlg._timer.isActive()
            dlg._replay_index = 2
            dlg.ed_search.setText("A")
            # Debounced; force immediate refresh like source filter.
            dlg.refresh_rows()
            assert not dlg._timer.isActive()
            assert not dlg._replay_paused
            assert dlg._replay_index == 0
            assert len(dlg._replay_rows) == 2
            assert all(r["tag"] == "A" for r in dlg._replay_rows)
        finally:
            dlg.deleteLater()
    finally:
        window._structured_recorder.stop()
        window.deleteLater()
        _APP.processEvents()


def test_m6_feed_does_not_clear_named_source_levels():
    from ui.dashboard_dialog import DashboardDialog

    app = types.SimpleNamespace(
        settings=types.SimpleNamespace(
            value=lambda *a, **k: 0 if "mode" in str(a) else "",
            setValue=lambda *a, **k: None,
        ),
        _t=lambda k, **kw: k,
        _theme_id=lambda: "dark",
        _theme=lambda: {"mode": "dark"},
        _codec=lambda: "utf-8",
    )
    # Avoid full UI construction: exercise feed helpers on a light stub.
    dlg = DashboardDialog.__new__(DashboardDialog)
    dlg._paused = False
    dlg._parser = types.SimpleNamespace(feed=lambda data, codec: [("T", 25.0)])
    dlg._values = {}
    dlg._levels = {}
    dlg._named_sources = set()
    dlg._tiles = {"T": {"unit": ""}}
    dlg._order = ["T"]
    dlg._ensure_tile = lambda name: None
    dlg._codec = lambda: "utf-8"

    dlg.feed_named_samples([{"tag": "T", "value": 80, "level": "alarm"}])
    assert dlg._levels.get("T") == "alarm"
    assert "T" in dlg._named_sources
    dlg.feed(b"T=25\n")
    assert dlg._levels.get("T") == "alarm"

    dlg._named_sources.clear()
    dlg._levels["T"] = "warn"
    dlg.feed(b"T=1\n")
    assert "T" not in dlg._levels


def test_m12_load_recovers_header_after_leading_garbage():
    p = os.path.join(tempfile.mkdtemp(), "lead-garbage.ctrec")
    with open(p, "w", encoding="utf-8") as f:
        f.write("not json at all\n")
        f.write('{"hello": 1}\n')
        f.write('{"_": "ctrec", "v": 1}\n')
        f.write('{"t": 0, "d": "rx", "b": "41"}\n')
    try:
        events, header = rec_replay.load(p)
        assert header.get("v") == 1
        assert [b for _t, _d, b in events] == [b"A"]
        assert header.get("bad_lines", 0) >= 2
    finally:
        os.remove(p)


def test_m13_addr_base_out_of_range_kept_with_warning(caplog):
    import logging
    from project.device_resources import normalize_registers

    with caplog.at_level(logging.WARNING, logger="project.device_resources"):
        rec = normalize_registers([{"address": 10, "addr_base": 9}])[0]
    assert rec["addr_base"] == 9
    assert rec["display_address"] == 19
    assert any("addr_base" in r.message for r in caplog.records)
