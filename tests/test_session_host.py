# -*- coding: utf-8 -*-
"""session_host 契约单测：资源互斥键、后台显示默认、代理与关键多会话不变量。

行为级覆盖（任务钉住 owner / 后台 RX 只喂 owner 引擎 / 循环 per-session）仍在
``tests/test_multi_session.py``；本文件钉住可 Qt-free / 轻量复现的契约。
"""
from __future__ import print_function

import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication, QEvent, QSettings

from session_host import (
    SessionHostMixin, _BACKGROUND_DISPLAY_DEFAULTS, _SESSION_PROXY_ATTRS,
    _assert_session_proxy_attrs,
)
from session import Session

_APP = QApplication.instance() or QApplication([])
_TEST_WINDOWS = []


@pytest.fixture(autouse=True)
def _dispose_test_windows():
    """Destroy each window after stopping timers, workers, and app hooks."""
    yield
    for window in reversed(_TEST_WINDOWS):
        window._shutdown()
        _APP.processEvents()
        window.deleteLater()
    _TEST_WINDOWS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


# ---- Qt-free contracts -------------------------------------------------

def test_resource_key_serial_and_skips():
    key = SessionHostMixin._session_resource_key_from_open(
        "Serial", {"port": "com3"})
    assert key == ("serial", "COM3")
    assert SessionHostMixin._session_resource_key_from_open("Virtual", {}) is None
    assert SessionHostMixin._session_resource_key_from_open("TCP Client", {
        "local_port": "9000"}) is None
    ble = SessionHostMixin._session_resource_key_from_open(
        "BLE", {"address": "69:1e:38:38:39:0d"})
    assert ble == ("ble", "69:1E:38:38:39:0D")
    assert SessionHostMixin._session_resource_key_from_open(
        "BLE", {"address": "69-1e-38-38-39-0d"}) == ble
    assert SessionHostMixin._session_resource_keys_conflict(
        ble, ("ble", "69:1E:38:38:39:0D"))
    assert not SessionHostMixin._session_resource_keys_conflict(
        ble, ("ble", "AA:BB:CC:DD:EE:FF"))


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


def test_session_proxy_attrs_are_session_slots():
    """Window proxies must exist on Session; a missing slot would AttributeError."""
    _assert_session_proxy_attrs()
    assert set(_SESSION_PROXY_ATTRS) <= set(Session.__slots__)


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

    def _settings_file(profile_name=""):
        # Honor profile so two windows in one test do not share lock/ini.
        name = profile_name or profile or "default"
        return str(tmp_path / ("%s.ini" % name))

    monkeypatch.setattr(
        CommTool, "_settings_file", staticmethod(_settings_file))
    w = CommTool(profile)
    w.settings = QSettings(_settings_file(profile), QSettings.IniFormat)
    _TEST_WINDOWS.append(w)
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


def test_soft_leave_allows_switch_busy_blocks_close(monkeypatch, tmp_path):
    """独占任务钉在启动会话：可切标签；关闭忙会话仍拦截；循环切走后继续。"""
    w = _window(monkeypatch, tmp_path, "busy")
    _open_virtual(w)
    s1 = w.active_session()
    s2 = w.add_session(activate=False)
    w._replay_on = True
    w._io_bind_owner("replay", s1)
    assert w._hard_busy_owned_by(s1)
    assert w.switch_session(s2.id) is True
    assert w.active_session().id == s2.id
    assert w.close_session(s1.id, confirm=False) is False
    assert w.find_session(s1.id) is s1

    s1._replay_on = False
    w._io_clear_owner("replay")
    s1._ms_cycle_timer.start(60000)
    assert s1._ms_cycle_timer.isActive()
    assert w.switch_session(s1.id) is True
    assert w.switch_session(s2.id) is True
    assert w.active_session().id == s2.id
    assert s1._ms_cycle_timer.isActive()
    w._close_all_sessions()


def test_background_rx_feeds_owner_script_not_others(monkeypatch, tmp_path):
    """后台 RX：仅喂该会话自己的脚本 worker。"""
    w = _window(monkeypatch, tmp_path, "bg-rx-host")
    _open_virtual(w)
    s1 = w.active_session()
    w.add_session(activate=True)
    _open_virtual(w)
    fed = {"script": 0}

    class _Worker(object):
        def feed(self, data):
            fed["script"] += 1

    s1._script_worker = _Worker()
    monkeypatch.setattr(w, "_script_running", lambda: True)
    monkeypatch.setattr(w, "_seq_running", lambda: False)
    s1.conn.inject(b"YES-SCRIPT")
    _pump()
    assert fed["script"] == 1
    assert s1.rx_bytes >= 10

    fed["script"] = 0
    s1._script_worker = None
    s1.conn.inject(b"NO-SCRIPT")
    _pump()
    assert fed["script"] == 0
    w._close_all_sessions()


def test_route_background_session_data_skips_on_data_received(monkeypatch, tmp_path):
    """_route_session_data 对非活跃会话走 _on_background_session_data，不调 on_data_received。"""
    w = _window(monkeypatch, tmp_path, "route-bg")
    _open_virtual(w)
    s1 = w.active_session()
    w.add_session(activate=True)
    _open_virtual(w)

    calls = {"received": 0, "bg": 0}
    monkeypatch.setattr(
        w, "on_data_received",
        lambda data, reply_target=None: calls.__setitem__(
            "received", calls["received"] + 1))
    monkeypatch.setattr(
        w, "_on_background_session_data",
        lambda data, reply_target=None: calls.__setitem__(
            "bg", calls["bg"] + 1))

    w._route_session_data(s1.id, b"HELLO")  # s1 现在是后台会话
    assert calls["received"] == 0           # 不走 on_data_received
    assert calls["bg"] == 1                 # 走后台渲染/引擎路径

    # 正向路径：活跃会话仍走 on_data_received（与后台分支对称钉死）
    s2 = w.active_session()
    w._route_session_data(s2.id, b"ACTIVE")
    assert calls["received"] == 1
    assert calls["bg"] == 1
    w._close_all_sessions()


def test_themed_text_input_dialog_uses_ms_buttons(monkeypatch, tmp_path):
    """Rename / preset prompts use MsPrimaryBtn + MsGhostBtn (not native QInputDialog)."""
    from PyQt5.QtWidgets import QPushButton, QInputDialog

    w = _window(monkeypatch, tmp_path, "themed-input")
    dlg = w._build_themed_text_input_dialog("T", "P", "hello")
    assert not isinstance(dlg, QInputDialog)
    assert dlg.textValue() == "hello"
    names = {b.objectName() for b in dlg.findChildren(QPushButton)}
    assert "MsPrimaryBtn" in names
    assert "MsGhostBtn" in names
    dlg.close()
    w._close_all_sessions()
