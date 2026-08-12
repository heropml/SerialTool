# -*- coding: utf-8 -*-
"""主界面 QComboBox 禁止悬停滚轮误触。"""
from __future__ import print_function

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QWheelEvent
from PyQt5.QtWidgets import QApplication, QComboBox, QWidget, QVBoxLayout

from widgets import find_combo_ancestor, should_block_combo_wheel

_APP = QApplication.instance() or QApplication([])


def _wheel(widget):
    # Qt5: QWheelEvent(pos, globalPos, pixelDelta, angleDelta, buttons, modifiers, phase, inverted)
    return QWheelEvent(
        QPoint(5, 5), widget.mapToGlobal(QPoint(5, 5)),
        QPoint(0, 0), QPoint(0, 120),
        Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)


def test_find_combo_ancestor_from_line_edit():
    root = QWidget()
    cb = QComboBox(root)
    cb.setEditable(True)
    assert find_combo_ancestor(cb) is cb
    assert find_combo_ancestor(cb.lineEdit()) is cb
    assert find_combo_ancestor(root) is None
    root.deleteLater()


def test_should_block_when_popup_closed():
    cb = QComboBox()
    cb.addItems(["a", "b", "c"])
    cb.show()
    _APP.processEvents()
    assert should_block_combo_wheel(cb) is True
    cb.showPopup()
    _APP.processEvents()
    # offscreen popup visibility can vary; if view reports visible, must not block
    if cb.view() is not None and cb.view().isVisible():
        assert should_block_combo_wheel(cb) is False
    cb.hidePopup()
    cb.deleteLater()


def test_main_window_filter_blocks_closed_combo_wheel(monkeypatch, tmp_path):
    from main_window import CommTool, PortScannerThread
    from PyQt5.QtCore import QSettings

    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    ini = tmp_path / "combo-wheel.ini"
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool("combo-wheel")
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    w.show()
    _APP.processEvents()

    assert hasattr(w, "cb_baud")
    before = w.cb_baud.currentIndex()
    # Drive through the same app-level filter path used at runtime.
    ev = _wheel(w.cb_baud)
    blocked = w.eventFilter(w.cb_baud, ev)
    assert blocked is True
    assert w.cb_baud.currentIndex() == before

    # Combo outside the main window tree is not blocked by this filter branch.
    orphan = QComboBox()
    orphan.addItems(["x", "y"])
    assert w.eventFilter(orphan, _wheel(orphan)) is not True
    orphan.deleteLater()
    w._close_all_sessions()
    w.close()
