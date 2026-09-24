# -*- coding: utf-8 -*-
"""启动提速的回归护栏：主题 QSS 只整树刷一遍、RTT 器件表构造完再枚举、app 级过滤器快速放行。"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QCoreApplication, QEvent, QSettings
from PyQt5.QtWidgets import QApplication

import pytest

from transport.rtt_io import RttCatalog
from ui import app_style
from ui.conn_ui import PROTO_RTT

_APP = QApplication.instance() or QApplication([])
_WINDOWS = []


@pytest.fixture(autouse=True)
def _no_real_jlink(monkeypatch):
    monkeypatch.setattr(RttCatalog, "start", lambda self: None)


def _make_window(tmp_path, monkeypatch, theme=None):
    from main_window import CommTool, PortScannerThread

    ini = str(tmp_path / "startup.ini")
    if theme is not None:
        s = QSettings(ini, QSettings.IniFormat)
        s.setValue("theme", theme)
        s.sync()
    monkeypatch.setattr(
        CommTool, "_settings_file", staticmethod(lambda profile="": ini))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    w = CommTool()
    _WINDOWS.append(w)
    return w


def teardown_function(_fn=None):
    for window in reversed(_WINDOWS):
        window._shutdown()
        _APP.processEvents()
        window.deleteLater()
    _WINDOWS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _pump(seconds, dt=0.02):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _APP.processEvents()
        time.sleep(dt)


def test_saved_theme_applied_once_at_startup(tmp_path, monkeypatch):
    calls = []
    real = app_style.polish_widget_tree
    monkeypatch.setattr(app_style, "polish_widget_tree",
                        lambda root: (calls.append(root), real(root)))
    w = _make_window(tmp_path, monkeypatch, theme="dark")
    # 构造里就按已存主题出 QSS，不先刷一遍默认主题
    assert len(calls) == 1
    qss = w.styleSheet()
    w.show()
    _pump(0.3)   # 跑掉 _theme_apply_timer 的延后 _on_theme_changed
    assert w.cb_theme.currentData() == "dark"
    assert w.styleSheet() == qss
    assert len(calls) == 1   # QSS 没变 → 不再整树 unpolish/polish

    # 运行期真切主题仍整树重刷
    idx = next(i for i in range(w.cb_theme.count())
               if w.cb_theme.itemData(i) == "default")
    w.cb_theme.setCurrentIndex(idx)
    assert len(calls) == 2
    assert w.styleSheet() != qss


def test_rtt_catalog_waits_until_window_constructed(tmp_path, monkeypatch):
    from main_window import CommTool

    started = []
    monkeypatch.setattr(RttCatalog, "start", lambda self: started.append(self))
    real_restore = CommTool._restore_sessions_settings

    def restore_into_rtt(self):
        real_restore(self)
        # 模拟上次停在 RTT：构造期间切到 RTT 不应立刻起枚举线程
        self.cb_proto.setCurrentText(PROTO_RTT)
        assert self.cb_proto.currentText() == PROTO_RTT
        assert getattr(self, "_rtt_catalog_thread", None) is None

    monkeypatch.setattr(CommTool, "_restore_sessions_settings", restore_into_rtt)
    w = _make_window(tmp_path, monkeypatch)
    assert not started
    assert w._rtt_catalog_start_timer.isActive()
    w.show()
    _pump(0.6)
    assert w._first_painted
    assert len(started) == 1
    assert w._rtt_catalog_hold is False


def test_rtt_catalog_starts_after_first_paint_even_if_restore_blocks(tmp_path, monkeypatch):
    """「恢复上次工程」卡住 UI 超过定时时长：枚举仍须排在首帧绘制之后。"""
    from main_window import CommTool

    order = []
    monkeypatch.setattr(RttCatalog, "start", lambda self: order.append("catalog"))
    real_paint = CommTool.paintEvent

    def paint(self, event):
        if "paint" not in order:
            order.append("paint")
        real_paint(self, event)

    def slow_restore_into_rtt(self):
        self.cb_proto.setCurrentText(PROTO_RTT)
        time.sleep(0.5)
        order.append("restored")

    monkeypatch.setattr(CommTool, "paintEvent", paint)
    monkeypatch.setattr(CommTool, "_restore_last_project", slow_restore_into_rtt)
    w = _make_window(tmp_path, monkeypatch)
    w._rtt_catalog_start_timer.setInterval(100)   # 比恢复耗时短，模拟兜底定时器先到点
    w._rtt_catalog_start_timer.start()
    w.show()
    _pump(1.0)
    assert "catalog" in order and "paint" in order
    assert order.index("paint") < order.index("catalog")


def test_rtt_catalog_fallback_when_window_never_shown(tmp_path, monkeypatch):
    """托盘 / 不显示窗口：没有首帧也要在兜底时间后照常枚举。"""
    from main_window import CommTool

    started = []
    monkeypatch.setattr(RttCatalog, "start", lambda self: started.append(self))
    real_restore = CommTool._restore_sessions_settings

    def restore_into_rtt(self):
        real_restore(self)
        self.cb_proto.setCurrentText(PROTO_RTT)

    monkeypatch.setattr(CommTool, "_restore_sessions_settings", restore_into_rtt)
    w = _make_window(tmp_path, monkeypatch)
    w._rtt_catalog_start_timer.setInterval(100)
    w._rtt_catalog_start_timer.start()
    _pump(0.4)
    assert not w._first_painted
    assert len(started) == 1


def test_rtt_catalog_skipped_when_startup_ends_on_other_type(tmp_path, monkeypatch):
    """构造期间切过 RTT、最终停在串口：保持期结束时不应枚举。"""
    from main_window import CommTool

    started = []
    monkeypatch.setattr(RttCatalog, "start", lambda self: started.append(self))
    real_restore = CommTool._restore_sessions_settings

    def restore_via_rtt(self):
        real_restore(self)
        serial = self.cb_proto.currentText()
        self.cb_proto.setCurrentText(PROTO_RTT)
        self.cb_proto.setCurrentText(serial)
        assert self.cb_proto.currentText() != PROTO_RTT

    monkeypatch.setattr(CommTool, "_restore_sessions_settings", restore_via_rtt)
    w = _make_window(tmp_path, monkeypatch)
    w.show()
    _pump(0.6)
    assert not started
    assert w._rtt_catalog_hold is False
    # 之后用户再切到 RTT 照常立即枚举
    w.cb_proto.setCurrentText(PROTO_RTT)
    assert len(started) == 1


def test_project_restore_into_rtt_still_deferred(tmp_path, monkeypatch):
    """事件循环里 0ms 的「恢复上次工程」切到 RTT，也要等保持期结束再枚举。"""
    from main_window import CommTool

    started = []
    seen_at_restore = []
    monkeypatch.setattr(RttCatalog, "start", lambda self: started.append(self))

    def restore_project_into_rtt(self):
        self.cb_proto.setCurrentText(PROTO_RTT)
        seen_at_restore.append(len(started))

    monkeypatch.setattr(CommTool, "_restore_last_project", restore_project_into_rtt)
    w = _make_window(tmp_path, monkeypatch)
    w.show()
    _pump(0.6)
    assert seen_at_restore == [0]
    assert len(started) == 1
    assert w.cb_proto.currentText() == PROTO_RTT


def test_device_pick_during_hold_starts_immediately(tmp_path, monkeypatch):
    from main_window import CommTool

    started = []
    monkeypatch.setattr(RttCatalog, "start", lambda self: started.append(self))
    w = _make_window(tmp_path, monkeypatch)
    assert w._rtt_catalog_hold is True
    w._on_rtt_device_pick()
    assert len(started) == 1
    w._rtt_dev_dlg.hide()
    w.show()
    _pump(0.5)   # 首帧后的放行不重复起
    assert len(started) == 1


def test_app_event_filter_skips_unrelated_events(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    for et in (QEvent.Polish, QEvent.ChildAdded, QEvent.LayoutRequest,
               QEvent.Paint, QEvent.Show, QEvent.Move):
        assert et not in w._ef_types
        assert w.eventFilter(w.txt_send, QEvent(et)) is False
    # eventFilter 里实际分派的事件类型都得留在白名单里
    for et in (QEvent.Wheel, QEvent.ToolTip, QEvent.KeyPress,
               QEvent.ShortcutOverride, QEvent.MouseButtonPress, QEvent.Resize,
               QEvent.ContextMenu, QEvent.MouseButtonDblClick, QEvent.Leave):
        assert et in w._ef_types
