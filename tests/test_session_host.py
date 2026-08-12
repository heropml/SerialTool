# -*- coding: utf-8 -*-
"""session_host 契约单测：资源互斥键、后台显示默认、代理与关键多会话不变量。

行为级覆盖（切标签硬拦 / 后台 RX 不喂引擎 / 循环发送自动停）仍在
``tests/test_multi_session.py``；本文件钉住可 Qt-free / 轻量复现的契约。
"""
from __future__ import print_function

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

from session_host import SessionHostMixin, _BACKGROUND_DISPLAY_DEFAULTS

_APP = QApplication.instance() or QApplication([])


# ---- Qt-free contracts -------------------------------------------------

def test_resource_key_serial_and_skips():
    key = SessionHostMixin._session_resource_key_from_open(
        "Serial", {"port": "com3"})
    assert key == ("serial", "COM3")
    assert SessionHostMixin._session_resource_key_from_open("Virtual", {}) is None
    assert SessionHostMixin._session_resource_key_from_open("TCP Client", {
        "local_port": "9000"}) is None


def test_resource_key_net_bind_normalizes_port():
    key = SessionHostMixin._session_resource_key_from_open(
        "TCP Server", {"local_ip": "127.0.0.1", "local_port": "9000"})
    assert key == ("net-bind", "127.0.0.1", "9000")
    key2 = SessionHostMixin._session_resource_key_from_open(
        "UDP", {"local_port": "42"})
    assert key2[0] == "net-bind" and key2[2] == "42"


def test_resource_keys_conflict_wildcard_bind():
    a = ("net-bind", "0.0.0.0", "9000")
    b = ("net-bind", "127.0.0.1", "9000")
    c = ("net-bind", "127.0.0.1", "9001")
    d = ("serial", "COM1")
    assert SessionHostMixin._session_resource_keys_conflict(a, b)
    assert not SessionHostMixin._session_resource_keys_conflict(b, c)
    assert not SessionHostMixin._session_resource_keys_conflict(a, d)
    assert SessionHostMixin._session_resource_keys_conflict(
        ("serial", "COM1"), ("serial", "COM1"))
    assert not SessionHostMixin._session_resource_keys_conflict(
        ("serial", "COM1"), ("serial", "COM2"))


def test_background_display_defaults_cover_view_mutex_keys():
    for key in ("rx_hex", "hexdump_on", "numview_on", "terminal_on",
                "freeze_view", "ansi_on", "show_timestamp"):
        assert key in _BACKGROUND_DISPLAY_DEFAULTS
    opts = SessionHostMixin._background_display_opts(None)
    assert opts["rx_hex"] is False
    assert opts["terminal_on"] is False


# ---- Light GUI contracts ------------------------------------------------

def _quiet(monkeypatch):
    from main_window import CommTool, PortScannerThread
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "toast", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "_confirm_dlg", lambda *a, **k: True)


def _window(monkeypatch, tmp_path, profile="sess-host"):
    _quiet(monkeypatch)
    from main_window import CommTool
    ini = tmp_path / ("%s.ini" % profile)
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool(profile)
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    return w


def _pump(n=20, dt=0.01):
    for _ in range(n):
        _APP.processEvents()
        time.sleep(dt)


def _open_virtual(w):
    from virtual_io import PROTO_VIRTUAL
    w.cb_proto.setCurrentText(PROTO_VIRTUAL)
    w._update_net_fields()
    if hasattr(w, "sw_vconn_loop"):
        w.sw_vconn_loop.setChecked(True, animate=False)
    w.open_conn()
    assert w.conn is not None and w.conn.is_open


def test_session_proxies_track_active_session(monkeypatch, tmp_path):
    """conn / rx_bytes 等代理随 active session 切换，不串台。"""
    w = _window(monkeypatch, tmp_path, "proxy")
    _open_virtual(w)
    s1 = w.active_session()
    w.txt_send.setPlainText("A")
    w.do_send()
    _pump()
    rx1 = w.rx_bytes
    assert rx1 >= 1
    assert w.conn is s1.conn

    w.add_session(activate=True)
    s2 = w.active_session()
    assert s2 is not s1
    assert w.conn is s2.conn
    assert w.rx_bytes == 0
    _open_virtual(w)
    w.txt_send.setPlainText("BB")
    w.do_send()
    _pump()
    assert w.rx_bytes >= 2
    assert s1.rx_bytes == rx1
    w.switch_session(s1.id)
    assert w.conn is s1.conn
    assert w.rx_bytes == rx1
    w._close_all_sessions()


def test_exclusive_busy_blocks_leave_and_cycle_stops(monkeypatch, tmp_path):
    """窗口独占任务硬拦切标签；多条循环发送切走时自动停（leave-safe）。"""
    w = _window(monkeypatch, tmp_path, "busy")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    monkeypatch.setattr(w, "_io_task_busy", lambda exclude=(): True)
    assert w._session_exclusive_busy()
    assert w.switch_session(s2.id) is False
    assert w.active_session().id == s1.id

    # Multi-send is leave-safe (excluded from exclusive busy): switch stops it.
    monkeypatch.setattr(w, "_io_task_busy", lambda exclude=(): False)
    w._ms_cycle_seq = [("AA", False, 0, 0, 1000)]
    w._ms_cycle_timer.start(60000)
    assert w._ms_cycle_timer.isActive()
    assert w.switch_session(s2.id) is True
    assert w.active_session().id == s2.id
    assert not w._ms_cycle_timer.isActive()
    w._close_all_sessions()


def test_background_rx_does_not_feed_window_engines(monkeypatch, tmp_path):
    """后台会话 RX 更新本会话计数，不喂窗口级脚本引擎。"""
    w = _window(monkeypatch, tmp_path, "bg-rx-host")
    _open_virtual(w)
    s1 = w.active_session()
    w.add_session(activate=True)
    _open_virtual(w)
    fed = {"script": 0}

    class _Worker(object):
        def feed(self, data):
            fed["script"] += 1

    w._script_worker = _Worker()
    monkeypatch.setattr(w, "_script_running", lambda: True)
    monkeypatch.setattr(w, "_seq_running", lambda: False)
    s1.conn.inject(b"NO-SCRIPT")
    _pump()
    assert fed["script"] == 0
    assert s1.rx_bytes >= 9
    w._close_all_sessions()
