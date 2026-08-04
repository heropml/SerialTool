import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import io_stats
from main_window import CommTool, PortScannerThread
from structured_record_dialog import StructuredRecordDialog


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


def _sample(tag, ts, value=1):
    return {"timestamp": ts, "source": "modbus", "tag": tag, "value": value,
            "unit": "", "raw": "", "slave": 1, "function": 3, "address": 0}


def test_closing_dialog_ends_paused_replay(tmp_path, monkeypatch):
    """The dialog is a cached single instance: a paused session must not survive close."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("structured-close-paused-test")
    try:
        window._structured_recorder.start()
        window._structured_recorder.add([_sample("A", 1000.0), _sample("B", 1001.0)])
        dlg = StructuredRecordDialog(window)
        try:
            dlg.refresh_rows()
            dlg._toggle_replay()
            assert dlg._timer.isActive()
            dlg._toggle_replay_pause()
            assert dlg._replay_paused
            dlg.close()
            assert not dlg._replay_paused
            assert not dlg._timer.isActive()
            # Reopening must show "start replay", not a live-looking paused session.
            dlg.refresh_rows()
            assert dlg.btn_replay.text() == window._t("structured_replay")
        finally:
            dlg.deleteLater()
    finally:
        window._structured_recorder.stop()
        window.deleteLater()
        _APP.processEvents()


def test_jump_to_session_time_refreshes_hidden_dialog(tmp_path, monkeypatch):
    """Rows recorded while the dialog was hidden must still be reachable."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("structured-jump-refresh-test")
    try:
        window._structured_recorder.start()
        window._structured_recorder.add([_sample("A", 1000.0)])
        window._open_structured_record()
        dlg = window._structured_dlg
        dlg.hide()
        # Hidden dialog: on_samples deliberately skips refresh_rows().
        window._structured_recorder.add([_sample("B", 2000.0)])
        assert len(dlg._replay_rows) == 1
        window.jump_to_session_time(2000.0)
        assert len(dlg._replay_rows) == 2
        assert dlg.table.currentRow() == 1
    finally:
        window._structured_recorder.stop()
        window.deleteLater()
        _APP.processEvents()


def test_non_list_slaves_json_is_rejected(tmp_path, monkeypatch):
    """JSON that parses into a dict used to wipe the slave bank with no warning."""
    from PyQt5.QtWidgets import QDialog, QPlainTextEdit
    from auto_reply_dialog import AutoReplyDialog

    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("ar-slaves-json-test")
    try:
        window._set_ar_modbus({"on": True, "addr": 1, "slaves": [{"addr": 1}, {"addr": 2}]})
        before = window._ar_modbus.get("slaves")
        assert before

        toasts = []
        monkeypatch.setattr(
            CommTool, "toast",
            lambda self, msg, error=False: toasts.append((msg, error)))

        def fake_exec(self):
            for box in self.findChildren(QPlainTextEdit):
                box.setPlainText('{"addr": 1}')      # 合法 JSON，但不是数组
            return QDialog.Accepted

        monkeypatch.setattr(QDialog, "exec_", fake_exec)
        dlg = AutoReplyDialog(window)
        try:
            dlg._open_modbus()
            assert toasts and toasts[-1][1] is True
            assert window._ar_modbus.get("slaves") == before
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_stats_history_wall_time_tracks_monotonic_delta():
    """wall_t must be derived from the monotonic delta, not a fresh time.time()."""
    acc = io_stats.IoStatsAccumulator()
    acc.session_t0_wall = 1_700_000_000.0
    acc.session_t0_mono = 500.0
    acc.note_rx(10)
    acc.tick(now=503.0)
    assert acc.history[-1]["wall_t"] == 1_700_000_003.0
def test_modbus_dialog_commit_preserves_widgetless_fields(tmp_path, monkeypatch):
    """server_id / exception mode+filters / dynamics have no widget in the Modbus
    dialog; committing it must carry them over instead of resetting them."""
    from PyQt5.QtWidgets import QDialog
    from auto_reply_dialog import AutoReplyDialog

    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("ar-widgetless-test")
    try:
        window._set_ar_modbus({
            "on": True, "addr": 1,
            "server_id": "RIG-7",
            "dynamics": [{"space": "holding", "addr": 0, "mode": "inc", "step": 2}],
            "exception": {"enabled": True, "code": 2, "mode": "n", "n": 3,
                          "funcs": [3], "addrs": [10]},
        })
        assert window._ar_modbus.get("server_id") == "RIG-7"

        monkeypatch.setattr(QDialog, "exec_", lambda self: QDialog.Accepted)
        dlg = AutoReplyDialog(window)
        try:
            dlg._open_modbus()
            cfg = window._ar_modbus
            assert cfg.get("server_id") == "RIG-7"
            exc = cfg.get("exception") or {}
            assert exc.get("mode") == "n" and exc.get("n") == 3
            assert exc.get("funcs") == [3] and exc.get("addrs") == [10]
            assert exc.get("enabled") is True and exc.get("code") == 2
            dyn = cfg.get("dynamics") or []
            assert len(dyn) == 1 and dyn[0]["mode"] == "inc" and dyn[0]["step"] == 2
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()
