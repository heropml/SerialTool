# -*- coding: utf-8 -*-
"""P1 wrap-up: bookmarks, status-bar jump, session-diff wall_t0 jump."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QTableWidgetItem
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import Qt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main_window import CommTool, PortScannerThread
from record import rec_replay
from record import rec_diff
from ui.rec_diff_dialog import RecDiffDialog

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


def test_stream_recorder_writes_wall_t0(tmp_path):
    rec = rec_replay.StreamRecorder()
    rec.start()
    rec.on_rx(b"hi")
    path = tmp_path / "a.ctrec"
    rec.save(str(path), note="t")
    events, header = rec_replay.load(str(path))
    assert "wall_t0" in header
    assert isinstance(header["wall_t0"], float)
    assert events and events[0][1] == "rx"


def test_rec_diff_row_jump_uses_wall_t0(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("rd-jump-test")
    jumped = []
    window.jump_to_session_time = lambda wall_t: jumped.append(wall_t)
    try:
        for name, wall0, payload in (("a.ctrec", 1000.0, b"A"), ("b.ctrec", 2000.0, b"B")):
            rec = rec_replay.StreamRecorder()
            rec.start()
            rec._t0 = 0.0
            rec._wall_t0 = wall0
            rec.on_rx(payload, t=0.5)
            rec.save(str(tmp_path / name))

        dlg = RecDiffDialog(window)
        try:
            for side, name in (("a", "a.ctrec"), ("b", "b.ctrec")):
                path = str(tmp_path / name)
                events, header = rec_replay.load(path)
                setattr(dlg, "_path_%s" % side, path)
                setattr(dlg, "_events_%s" % side, events)
                setattr(dlg, "_wall_t0_%s" % side, float(header["wall_t0"]))
            dlg._result = rec_diff.compare(dlg._events_a, dlg._events_b)
            dlg._fill_table()
            assert dlg.table.rowCount() >= 1
            dlg._on_row_jump(0, 0)
            assert jumped
            assert abs(jumped[0] - 1000.5) < 1e-6
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_rec_diff_jump_toasts_without_wall_t0(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("rd-jump-nowall")
    toasts = []
    window.toast = lambda msg, error=False: toasts.append((msg, error))
    window.jump_to_session_time = lambda wall_t: None
    try:
        dlg = RecDiffDialog(window)
        try:
            dlg._wall_t0_a = None
            dlg._wall_t0_b = None
            row = {"kind": rec_diff.SAME, "t_a": 0.1, "t_b": 0.1,
                   "dir_a": "rx", "dir_b": "rx",
                   "bytes_a": b"x", "bytes_b": b"x"}
            dlg.table.setRowCount(1)
            dlg.table.setColumnCount(1)
            item = QTableWidgetItem("x")
            item.setData(Qt.UserRole, row)
            dlg.table.setItem(0, 0, item)
            dlg._on_row_jump(0, 0)
            assert toasts and toasts[-1][1] is True
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_status_bar_jump_uses_latest_history(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("stat-jump-test")
    jumped = []
    window.jump_to_session_time = lambda wall_t: jumped.append(wall_t)
    try:
        window._io_stats.session_t0_wall = 1_700_000_000.0
        window._io_stats.session_t0_mono = 100.0
        window._io_stats.note_rx(4)
        window._io_stats.tick(now=105.0)
        window._jump_from_io_stats()
        assert jumped and abs(jumped[0] - 1_700_000_005.0) < 1e-6
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_bookmarks_toggle_and_navigate(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("bm-test")
    try:
        window.txt_recv.setPlainText("line0\nline1\nline2\nline3\n")
        doc = window.txt_recv.document()

        def _goto_block(n):
            cur = QTextCursor(doc.findBlockByNumber(n))
            window.txt_recv.setTextCursor(cur)

        _goto_block(1)
        window._bookmark_toggle()
        _goto_block(3)
        window._bookmark_toggle()
        assert len(window._bookmarks) == 2

        _goto_block(0)
        window._bookmark_idx = -1
        window._bookmark_next()
        assert window.txt_recv.textCursor().block().blockNumber() == 1

        window._bookmark_next()
        assert window.txt_recv.textCursor().block().blockNumber() == 3

        window._bookmark_prev()
        assert window.txt_recv.textCursor().block().blockNumber() == 1

        _goto_block(1)
        window._bookmark_toggle()
        assert len(window._bookmarks) == 1

        window.clear_recv()
        assert window._bookmarks == []
    finally:
        window.deleteLater()
        _APP.processEvents()



def test_bookmarks_wraparound(tmp_path, monkeypatch):
    """F2 / Shift+F2 wrap around the bookmark list."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("bm-wrap-test")
    try:
        window.txt_recv.setPlainText("line0\nline1\nline2\nline3\n")
        doc = window.txt_recv.document()

        def _goto_block(n):
            window.txt_recv.setTextCursor(QTextCursor(doc.findBlockByNumber(n)))

        for n in (1, 3):
            _goto_block(n)
            window._bookmark_toggle()
        assert len(window._bookmarks) == 2

        _goto_block(0)
        window._bookmark_idx = -1
        window._bookmark_next()  # -> 1
        window._bookmark_next()  # -> 3
        window._bookmark_next()  # wrap -> 1
        assert window.txt_recv.textCursor().block().blockNumber() == 1
        assert window._bookmark_idx == 0

        window._bookmark_prev()  # wrap back -> 3
        assert window.txt_recv.textCursor().block().blockNumber() == 3
        assert window._bookmark_idx == 1
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_ansi_full_clear_drops_bookmarks(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("bm-ansi-clear-test")
    try:
        window.txt_recv.setPlainText("old0\nold1")
        window.txt_recv.setTextCursor(QTextCursor(window.txt_recv.document().findBlockByNumber(1)))
        window._bookmark_toggle()
        assert window._bookmarks

        window._term_handle_csi(
            QTextCursor(window.txt_recv.document().end()), "\x1b[2J")
        assert window._bookmarks == []
        assert window._bookmark_idx == -1
        assert window._recv_highlight_line == -1
    finally:
        window.deleteLater()
        _APP.processEvents()
