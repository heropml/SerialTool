# -*- coding: utf-8 -*-
"""数据区右键：选区转文本 / HEX。"""
from __future__ import print_function

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import convert


def test_selection_bytes_for_text_prefers_extracted_hex():
    data = convert.selection_bytes_for_text_convert(b"T\x00\x00B", "ignored")
    assert data == b"T\x00\x00B"
    assert convert.bytes_to_text(data, "utf-8").startswith("T")


def test_selection_bytes_for_text_parses_raw_hex():
    data = convert.selection_bytes_for_text_convert(None, "54 00 00 42")
    assert data == bytes.fromhex("54000042")
    assert convert.selection_bytes_for_text_convert(None, "ZZ") is None
    assert convert.selection_bytes_for_text_convert(b"", "  ") is None


def test_selection_bytes_for_hex_from_text():
    data = convert.selection_bytes_for_hex_convert(None, "AB", encoding="utf-8")
    assert data == b"AB"
    assert convert.bytes_to_hex(data) == "41 42"


def test_selection_bytes_for_hex_normalizes_extracted():
    data = convert.selection_bytes_for_hex_convert(b"\x54\x00", "54 00")
    assert data == b"\x54\x00"


def test_normalize_qtext_selection():
    assert convert.normalize_qtext_selection("a\u2029b") == "a\nb"


def test_ctx_convert_rejects_oversized_text_selection(monkeypatch, tmp_path):
    """文本→HEX 路径须在编码前按选区字符数卡上限（P2）。"""
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from PyQt5.QtGui import QTextCursor
    from main_window import CommTool, PortScannerThread

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    ini = tmp_path / "ctx-convert-limit.ini"
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool("ctx-convert-limit")
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    toasts = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: toasts.append((msg, error)))
    monkeypatch.setattr(w, "_info_dlg", lambda *a, **k: None)
    monkeypatch.setattr(w, "_selected_hex_bytes", lambda *a, **k: None)

    big = "A" * (w._CTX_CONVERT_MAX + 1)
    w.txt_recv.setPlainText(big)
    cur = QTextCursor(w.txt_recv.document())
    cur.select(QTextCursor.Document)
    w.txt_recv.setTextCursor(cur)
    app.clipboard().setText("sentinel")
    w._ctx_convert_selection(to_hex=True)
    assert app.clipboard().text() == "sentinel"
    assert toasts and toasts[-1][1] is True
    w._close_all_sessions()
    w.close()


def test_ctx_convert_copies_clipboard(monkeypatch, tmp_path):
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from PyQt5.QtGui import QTextCursor
    from main_window import CommTool, PortScannerThread

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    ini = tmp_path / "ctx-convert.ini"
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool("ctx-convert")
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    toasts = []
    shown = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: toasts.append((msg, error)))
    monkeypatch.setattr(
        w, "_info_dlg",
        lambda title, body, is_error=False: shown.append((title, body)))

    w.txt_recv.setPlainText("[12:00:00.000] \u2190 54 00 00 42 F3")
    text = w.txt_recv.toPlainText()
    start = text.index("54 00 00 42")
    cur = QTextCursor(w.txt_recv.document())
    cur.setPosition(start)
    cur.setPosition(start + len("54 00 00 42"), QTextCursor.KeepAnchor)
    w.txt_recv.setTextCursor(cur)
    # Offscreen plain text has no VIEW_PROP; stub the same extractor HEX 视图会走的路径。
    monkeypatch.setattr(
        w, "_selected_hex_bytes",
        lambda cursor, limit=None: bytes.fromhex("54000042"))

    expected_text = convert.bytes_to_text(bytes.fromhex("54000042"), "utf-8")
    w._ctx_convert_selection(to_hex=False)
    assert app.clipboard().text() == expected_text
    assert shown and shown[-1][1] == expected_text
    assert toasts and toasts[-1][1] is False

    toasts.clear()
    shown.clear()
    w._ctx_convert_selection(to_hex=True)
    assert app.clipboard().text() == "54 00 00 42"
    assert shown and shown[-1][1] == "54 00 00 42"
    w._close_all_sessions()
    w.close()
