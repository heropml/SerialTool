# -*- coding: utf-8 -*-
"""DLOG wave mode (rtt_t2 TAG=DLOG M*n protocol) in PlotDialog."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main_window import CommTool, PortScannerThread
from ui.plot_dialog import PlotDialog, _MODE_DLOG

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


def _make(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("plot-dlog-test")
    dlg = PlotDialog(window)
    dlg.cb_mode.setCurrentIndex(_MODE_DLOG)   # 触发 _save_cfg 持久化
    return window, dlg


def test_dlog_mode_parses_and_ignores_logs(tmp_path, monkeypatch):
    window, dlg = _make(tmp_path, monkeypatch)
    try:
        dlg.feed(b"[I] boot ok\r\n")
        dlg.feed(b"TAG=DLOG M*1(12,34,56)\n")
        dlg.feed(b"[W] some warning line 12.34 with numbers\n")
        dlg.feed(b"TAG=DLOG M*1(22,44,66)\r\n")
        names = [ch["name"] for ch in dlg._channels]
        assert names == ["DLOG1", "DLOG2", "DLOG3"], names
        assert list(dlg._channels[0]["ys"]) == [1.2, 2.2]
        assert list(dlg._channels[1]["ys"]) == [3.4, 4.4]
        assert list(dlg._channels[2]["ys"]) == [5.6, 6.6]
        # 每个 DLOG 行推进一个采样序号；日志行不推进
        assert dlg._sample_idx == 2
    finally:
        dlg.close()
        dlg.deleteLater()
        window.deleteLater()
        _APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_dlog_mode_variants(tmp_path, monkeypatch):
    window, dlg = _make(tmp_path, monkeypatch)
    try:
        dlg.feed(b"  tag=dlog m*0(42,0,0)\n")             # 大小写/前导空白
        dlg.feed(b"TAG=DLOG SN(7)M*1(-15, +20,0)\n")      # SN/符号/小数缩放
        dlg.feed(b"BDSCOL(255)TAG=DLOG M*0(1,2,3,4)\n")   # 颜色前缀/四通道
        dlg.feed(b"TAG=DLOG M*3()\n")                     # 空括号忽略
        dlg.feed(b"TAG=DLOG M*0(a,1)\n")                  # 非数值占位：该列跳过
        dlg.feed(b"TAG=OTHER M*0(9,9,9)\n")               # 别的 TAG 忽略
        dlg.feed(b"TAG=DLOG M*0(7,8,9)")                  # 无换行：暂不解析
        assert [ch["name"] for ch in dlg._channels] == [
            "DLOG1", "DLOG2", "DLOG3", "DLOG4"]
        assert list(dlg._channels[0]["ys"]) == [42.0, -1.5, 1.0]
        assert list(dlg._channels[1]["ys"]) == [0.0, 2.0, 2.0, 1.0]
        assert list(dlg._channels[2]["ys"]) == [0.0, 0.0, 3.0]
        assert list(dlg._channels[3]["ys"]) == [4.0]
    finally:
        dlg.close()
        dlg.deleteLater()
        window.deleteLater()
        _APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_dlog_mode_persists_and_cursor_stats_has_std(tmp_path, monkeypatch):
    window, dlg = _make(tmp_path, monkeypatch)
    try:
        assert dlg.cb_mode.count() == 4
        assert window.settings.value("plot_mode") == 3
        dlg.feed(b"TAG=DLOG M*0(1,2)\nTAG=DLOG M*0(3,4)\n")
        dlg._refresh_cursor_stats_cache()
        text = dlg._cursor_stats_extra
        assert "DLOG1" in text and "mean=" in text and "std=" in text
        # 总体标准差：[1,3] → sqrt(1.0)
        assert "std=1" in text
    finally:
        dlg.close()
        dlg.deleteLater()
        window.deleteLater()
        _APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
