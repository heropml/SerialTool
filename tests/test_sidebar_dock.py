# -*- coding: utf-8 -*-
"""侧栏自动隐藏（图钉）：摘出/固定、浮层开关、分隔条状态与持久化。"""
from __future__ import print_function

import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QCoreApplication, QEvent, QSettings
from PyQt5.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])
_TEST_WINDOWS = []


@pytest.fixture(autouse=True)
def _dispose_test_windows():
    yield
    for window in reversed(_TEST_WINDOWS):
        window._shutdown()
        _APP.processEvents()
        window.deleteLater()
    _TEST_WINDOWS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _window(monkeypatch, tmp_path, profile="sidebar-dock"):
    from main_window import CommTool, PortScannerThread
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "toast", lambda *a, **k: None)
    ini = tmp_path / ("%s.ini" % profile)
    monkeypatch.setattr(
        CommTool, "_settings_file", staticmethod(lambda profile="": str(ini)))
    w = CommTool(profile)
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    _TEST_WINDOWS.append(w)
    return w, ini


def _pump(n=6, dt=0.02):
    for _ in range(n):
        _APP.processEvents()
        time.sleep(dt)


def test_default_is_pinned_and_strip_hidden(monkeypatch, tmp_path):
    """默认固定：侧栏留在分隔条里，竖标签不出现。"""
    w, _ = _window(monkeypatch, tmp_path)
    dock = w._sidebar_dock
    assert dock.is_pinned()
    assert w.h_splitter.count() == 2
    assert w.h_splitter.widget(0) is w.sidebar
    assert not dock.strip.isVisible()
    assert not dock.flyout.isVisible()


def test_unpin_moves_sidebar_into_flyout(monkeypatch, tmp_path):
    """摘出：侧栏搬进浮层，分隔条只剩右侧，竖标签接管左缘。"""
    w, _ = _window(monkeypatch, tmp_path)
    w.show()
    _pump()
    dock = w._sidebar_dock
    dock.set_pinned(False)
    _pump()
    assert not dock.is_pinned()
    assert w.h_splitter.count() == 1
    assert w.sidebar.parent() is dock.flyout
    assert dock.strip.isVisible()
    assert not dock.flyout.isVisible()


def test_flyout_open_close_and_repin(monkeypatch, tmp_path):
    """竖标签点开浮层 → 收回 → 再固定，侧栏回到分隔条第 0 位。"""
    w, _ = _window(monkeypatch, tmp_path)
    w.show()
    _pump()
    dock = w._sidebar_dock
    dock.set_pinned(False)
    dock.open_flyout()
    _pump()
    assert dock.flyout_open()
    assert dock.flyout.width() >= w.sidebar.minimumWidth()

    dock.close_flyout(immediate=True)
    assert not dock.flyout.isVisible()

    dock.set_pinned(True)
    _pump()
    assert dock.is_pinned()
    assert w.h_splitter.widget(0) is w.sidebar
    assert w.sidebar.isVisible()
    assert not dock.strip.isVisible()
    sizes = w.h_splitter.sizes()
    assert sizes[0] >= w.sidebar.minimumWidth()


def test_split_state_survives_autohide(monkeypatch, tmp_path):
    """自动隐藏期间落盘的 h_splitter 仍是两栏那份，不会把左右比例弄丢。"""
    w, _ = _window(monkeypatch, tmp_path)
    w.show()
    _pump()
    dock = w._sidebar_dock
    docked_state = bytes(w.h_splitter.saveState())
    dock.set_pinned(False)
    _pump()
    assert bytes(dock.split_state()) == docked_state


def test_autohide_flag_round_trips(monkeypatch, tmp_path):
    """开着自动隐藏退出 → 重开仍是自动隐藏。"""
    w, ini = _window(monkeypatch, tmp_path, "dock-persist")
    w.show()
    _pump()
    w._sidebar_dock.set_pinned(False)
    w._save_settings()
    _pump()
    assert QSettings(str(ini), QSettings.IniFormat).value("sidebar_autohide") \
        in (True, "true")

    w2, _ = _window(monkeypatch, tmp_path, "dock-persist")
    _pump()
    assert not w2._sidebar_dock.is_pinned()
    assert w2.h_splitter.count() == 1


def test_hidden_workspace_closes_flyout(monkeypatch, tmp_path):
    """切到别的工作台分类：浮层立刻收掉，不会飘在其他页面上。"""
    w, _ = _window(monkeypatch, tmp_path)
    w.show()
    _pump()
    dock = w._sidebar_dock
    dock.set_pinned(False)
    dock.open_flyout()
    _pump()
    assert dock.flyout.isVisible()
    w._switch_workspace("data")
    _pump()
    assert not dock.flyout.isVisible()
    assert dock.flyout.isHidden()
    w._switch_workspace("terminal")
    _pump()
    assert not dock.flyout.isVisible()


def test_language_switch_refreshes_strip(monkeypatch, tmp_path):
    """竖标签文字是自绘的，切语言要跟着换。"""
    from ui.i18n import TR
    w, _ = _window(monkeypatch, tmp_path)
    dock = w._sidebar_dock
    w._set_language("en")
    _pump()
    assert dock.strip._text == TR["en"]["sidebar_tab"]
    w._set_language("zh")
    _pump()
    assert dock.strip._text == TR["zh"]["sidebar_tab"]


def test_brief_strip_hover_does_not_open_flyout(monkeypatch, tmp_path):
    """快速扫过不展开；再次停留仍能正常展开。"""
    from PyQt5.QtTest import QTest
    from ui.sidebar_dock import _OPEN_DELAY_MS

    w, _ = _window(monkeypatch, tmp_path)
    w.show()
    _pump()
    dock = w._sidebar_dock
    dock.set_pinned(False)
    _APP.processEvents()

    _APP.sendEvent(dock.strip, QEvent(QEvent.Enter))
    _APP.sendEvent(dock.strip, QEvent(QEvent.Leave))
    QTest.qWait(_OPEN_DELAY_MS + 40)
    assert not dock.flyout_open()

    _APP.sendEvent(dock.strip, QEvent(QEvent.Enter))
    QTest.qWait(_OPEN_DELAY_MS + 40)
    assert dock.flyout_open()
