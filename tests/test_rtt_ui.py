# -*- coding: utf-8 -*-
"""Offscreen RTT settings rows: visibility, field round-trip, fake-JLink open."""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QCoreApplication, QEvent, QSettings
from PyQt5.QtWidgets import QApplication

import pytest
from PyQt5.QtCore import Qt

from ui import rtt_device_dialog as rdd
from ui.conn_ui import PROTO_BLE, PROTO_RTT, PROTO_SERIAL, visible_conn_types
from transport.rtt_io import RttCatalog, RttConn

_APP = QApplication.instance() or QApplication([])
_WINDOWS = []


@pytest.fixture(autouse=True)
def _no_real_jlink(monkeypatch):
    """别在单测里真去加载 JLinkARM 驱动。

    建窗口就会后台枚举器件表，那会 LoadLibrary 真驱动 —— 结果既随本机装没装
    J-Link 而变（有驱动 14000 项 / 没驱动 15 项），又把原生 DLL 的生命周期
    绑进测试进程。需要器件数据的用例自己喂假数据。
    """
    monkeypatch.setattr(RttCatalog, "start", lambda self: None)


def _make_window(tmp_path, monkeypatch):
    from main_window import CommTool, PortScannerThread

    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(tmp_path / "rtt.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "rtt.ini"), QSettings.IniFormat)
    _WINDOWS.append(w)
    return w


def teardown_function(_fn=None):
    for window in reversed(_WINDOWS):
        window._shutdown()
        _APP.processEvents()
        window.deleteLater()
    _WINDOWS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _pump(seconds=1.0, dt=0.02):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _APP.processEvents()
        time.sleep(dt)


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_rtt_type_shows_rows(tmp_path, monkeypatch, platform):
    from ui import settings_card

    monkeypatch.setattr(settings_card, "visible_conn_types",
                        lambda: visible_conn_types(platform))
    w = _make_window(tmp_path, monkeypatch)
    has_ble = platform == "win32"
    assert (w.cb_proto.findText(PROTO_BLE) >= 0) == has_ble
    initial = PROTO_BLE if has_ble else PROTO_SERIAL
    w.cb_proto.setCurrentText(initial)
    assert w.cb_proto.currentText() == initial
    w._update_net_fields()
    assert w.row_ble_address.isHidden() is not has_ble
    assert w.row_rtt_device.isHidden() is True
    w.cb_proto.setCurrentText(PROTO_RTT)
    assert w.cb_proto.currentText() == PROTO_RTT
    w._update_net_fields()
    assert w.row_rtt_device.isHidden() is False
    assert w.row_rtt_interface.isHidden() is False
    assert w.row_rtt_speed.isHidden() is False
    assert w.row_rtt_address.isHidden() is False
    assert w.row_rtt_channel.isHidden() is False
    assert w.row_rtt_probe.isHidden() is False
    assert w.row_rtt_reset.isHidden() is False
    assert w.row_port.isHidden() is True
    assert w.row_local_ip.isHidden() is True
    assert w.row_ble_address.isHidden() is True

    w.cb_proto.setCurrentText(initial)
    w._update_net_fields()
    assert w.row_rtt_device.isHidden() is True
    assert w.row_ble_address.isHidden() is not has_ble
    assert w.row_port.isHidden() is has_ble


def test_rtt_capture_apply_roundtrip(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w.cb_rtt_device.setCurrentText("nRF52840_xxAA")
    w.cb_rtt_interface.setCurrentText("JTAG")
    w._set_rtt_speed_text("8000")
    w.ed_rtt_address.setText("0x20000000+0x40000")
    w.cb_rtt_channel.setCurrentIndex(3)
    w.cb_rtt_probe.setCurrentText("600100123")
    w.sw_rtt_reset.setChecked(True)
    fields = w._capture_connection_fields()
    assert fields["net_proto"] == PROTO_RTT
    assert fields["rtt_device"] == "nRF52840_xxAA"
    assert fields["rtt_channel"] == "3"   # 预设字段统一字符串化
    assert fields["rtt_probe"] == "600100123"

    w.cb_rtt_device.setCurrentText("")
    w.cb_rtt_interface.setCurrentText("SWD")
    w._set_rtt_speed_text("4000")
    w.ed_rtt_address.setText("")
    w.cb_rtt_channel.setCurrentIndex(0)
    w.cb_rtt_probe.setCurrentIndex(0)
    w.sw_rtt_reset.setChecked(False)
    w._apply_connection_fields(fields)
    assert w.cb_rtt_device.currentText() == "nRF52840_xxAA"
    assert w.cb_rtt_interface.currentText() == "JTAG"
    assert w._rtt_speed_text() == "8000"
    assert w.cb_rtt_speed.currentText() == "8000 kHz"   # 显示带单位
    assert w.ed_rtt_address.text() == "0x20000000+0x40000"
    assert w.cb_rtt_channel.currentIndex() == 3
    assert w._rtt_probe_text() == "600100123"
    assert w.sw_rtt_reset.isChecked() is True

    # UI 直出的签名，必须与从会话字段重建的签名一致；否则后台会话会被
    # _mbm_connection_ready 误判成「界面配置变了」而暂停发送。
    from project.connection_presets import rtt_signature
    assert w._conn_config_signature(PROTO_RTT) == rtt_signature(
        PROTO_RTT, fields.get("rtt_device"), fields.get("rtt_speed"),
        fields.get("rtt_interface"), fields.get("rtt_address"),
        fields.get("rtt_channel"), fields.get("rtt_probe"),
        fields.get("rtt_reset"))

    key = w._session_resource_key_from_open(PROTO_RTT, {"device": "NRF52"})
    assert key == ("rtt", "nrf52")
    w.cb_rtt_device.setCurrentText("MyDev")
    assert w._session_resource_key_from_ui() == ("rtt", "mydev")


def test_rtt_open_validates_device(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w._update_net_fields()
    toasts = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: toasts.append(msg))
    w.cb_rtt_device.setCurrentText("")
    w.toggle_conn()
    _pump(0.3)
    assert w.conn is None
    # toast 已本地化（键 rtt_err_no_device → 中文文案），这里只断言有报错提示
    assert toasts and "nRF52840_xxAA" in toasts[0]


def test_rtt_open_close_with_fake_jlink(tmp_path, monkeypatch):
    from tests.test_rtt_io import FakeJLink, _FakePylink

    jl = FakeJLink(rx=b"hello from target")
    monkeypatch.setattr(RttConn, "jlink_factory", staticmethod(lambda: jl))
    monkeypatch.setattr(RttConn, "pylink_module", _FakePylink)
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w._update_net_fields()
    w.cb_rtt_device.setCurrentText("nRF52840_xxAA")
    w._set_rtt_speed_text("8000")
    w.ed_rtt_address.setText("0x20000000")
    w.cb_rtt_channel.setCurrentIndex(1)

    w.toggle_conn()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        _APP.processEvents()
        if w.conn is not None and w._conn_engaged:
            break
        time.sleep(0.02)
    assert w._conn_engaged is True
    assert w.conn.is_open is True
    assert ("connect", "nRF52840_xxAA", 8000) in jl.calls
    assert ("rtt_start", 0x20000000) in jl.calls
    assert w.lbl_state.text().count("nRF52840_xxAA") >= 1
    assert "RTT" in w._replay_conn_summary()

    # 接收流进数据区（经会话路由）
    deadline = time.monotonic() + 3.0
    doc_text = ""
    while time.monotonic() < deadline:
        _APP.processEvents()
        doc_text = w.txt_recv.toPlainText()
        if "hello from target" in doc_text:
            break
        time.sleep(0.02)
    assert "hello from target" in doc_text
    assert w.lbl_state.text() == w._t(
        "rtt_connected", dev="nRF52840_xxAA", ch=1)

    # 发送经 conn.send 到下行通道
    assert w.conn.send(b"ping") == 4
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not jl.written:
        _APP.processEvents()
        time.sleep(0.02)
    assert jl.written and jl.written[0][0] == 1
    assert jl.written[0][1] == b"ping"

    w.toggle_conn()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and w.conn is not None:
        _APP.processEvents()
        time.sleep(0.02)
    assert w.conn is None
    assert "rtt_stop" in jl.calls and "close" in jl.calls


def test_rtt_device_catalog_stays_out_of_sidebar_combo(tmp_path, monkeypatch):
    """完整器件表只进轻量选择窗，不往侧栏组合框创建上万项。"""
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w._update_net_fields()
    w.cb_rtt_device.setCurrentText("MyPart")
    w._on_rtt_catalog(
        [{"name": "AAA1", "manufacturer": "Acme", "flash": 0, "ram": 0},
         {"name": "BBB2", "manufacturer": "Beta", "flash": 0, "ram": 0},
         {"name": "CCC3", "manufacturer": "", "flash": 0, "ram": 0}],
        ["600100123"])
    assert w.cb_rtt_device.count() < 100
    assert w.cb_rtt_device.currentText() == "MyPart"   # 用户输入不被冲掉
    assert len(w._rtt_devices) == 3
    # 调试器下拉：第 0 项恒为「自动」（空序列号），其后是枚举到的序列号
    assert w.cb_rtt_probe.count() == 2
    assert w._rtt_probe_text() == ""
    w.cb_rtt_probe.setCurrentIndex(1)
    assert w._rtt_probe_text() == "600100123"


def test_rtt_notice_is_toast_not_drop(tmp_path, monkeypatch):
    """控制块提示只弹 toast，连接状态不动。"""
    from transport import rtt_io

    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w._update_net_fields()
    toasts = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: toasts.append(msg))
    session = w.active_session()
    w._route_session_notice(session.id, rtt_io.NOTICE_WAIT_CB)
    assert toasts and toasts[0] == w._t("rtt_notice_waiting_cb")
    assert w.conn is None


def _picker_rows():
    return [
        {"name": "STM32H743VI", "manufacturer": "ST", "core": "Cortex-M7",
         "flash": 2 * 1024 * 1024, "ram": 512 * 1024},
        {"name": "STM32H743ZI", "manufacturer": "ST", "core": "Cortex-M7",
         "flash": 2 * 1024 * 1024, "ram": 512 * 1024},
        {"name": "nRF52840_xxAA", "manufacturer": "Nordic Semi",
         "core": "Cortex-M4", "flash": 1024 * 1024, "ram": 256 * 1024},
        {"name": "GD32F303CC", "manufacturer": "GigaDevice", "core": "Cortex-M4",
         "flash": 256 * 1024, "ram": 48 * 1024},
        {"name": "Cortex-M4", "manufacturer": "Unspecified", "core": "Cortex-M4",
         "flash": 0, "ram": 0},
    ]


def test_rtt_device_picker_filter_and_pick(tmp_path, monkeypatch):
    """上万项器件表放不进下拉：弹窗按 名称+厂商 多关键字过滤，选中回填。"""
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w._update_net_fields()
    monkeypatch.setattr(w, "_ensure_rtt_catalog", lambda: None)
    from transport import rtt_io
    monkeypatch.setattr(rtt_io, "list_devices", lambda: pytest.fail(
        "picker must not enumerate synchronously"))
    monkeypatch.setattr(rtt_io, "find_jlink_dll", lambda: pytest.fail(
        "picker must not scan DLLs synchronously"))
    w._rtt_devices = _picker_rows()
    w._on_rtt_device_pick()
    _APP.processEvents()
    dlg = w._rtt_dev_dlg
    assert dlg.model.rowCount() == 5

    def _names(query):
        dlg.ed_search.setText(query)
        _APP.processEvents()
        return [dlg.proxy.index(r, rdd.COL_NAME).data()
                for r in range(dlg.proxy.rowCount())]

    assert _names("") == ["STM32H743VI", "STM32H743ZI", "nRF52840_xxAA",
                          "GD32F303CC", "Cortex-M4"]
    assert _names("h743") == ["STM32H743VI", "STM32H743ZI"]
    assert _names("nordic") == ["nRF52840_xxAA"]     # 按厂商也能搜
    # 空格分词是 AND，且不管字段顺序
    assert _names("st h743zi") == ["STM32H743ZI"]
    assert _names("zzz") == []
    # 内核列也在搜索范围内：搜内核名会命中该内核的全部器件
    assert _names("cortex-m4") == ["nRF52840_xxAA", "GD32F303CC", "Cortex-M4"]

    _names("h743zi")
    dlg.table.selectRow(0)
    dlg._use_selected()
    _APP.processEvents()
    assert w.cb_rtt_device.currentText() == "STM32H743ZI"
    assert dlg.isVisible() is False
    # 重开时定位到当前器件
    w._on_rtt_device_pick()
    _APP.processEvents()
    idx = dlg.table.currentIndex()
    assert dlg.proxy.index(idx.row(), rdd.COL_NAME).data() == "STM32H743ZI"
    dlg.hide()


def test_rtt_device_picker_columns_and_column_filters(tmp_path, monkeypatch):
    """五列 + 厂商/内核逐列筛选（对齐 RTT Viewer 的 Target Device Settings）。"""
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w._update_net_fields()
    monkeypatch.setattr(w, "_ensure_rtt_catalog", lambda: None)
    w._rtt_devices = _picker_rows()
    w._on_rtt_device_pick()
    _APP.processEvents()
    dlg = w._rtt_dev_dlg

    assert dlg.model.columnCount() == 5
    row = [dlg.proxy.index(0, c).data() for c in range(5)]
    assert row == ["ST", "STM32H743VI", "Cortex-M7", "2 MB", "512 KB"]
    # 容量为 0 显示破折号，而不是 "0 B"
    assert rdd.format_size(0) == "—"
    assert rdd.format_size(20480) == "20 KB"
    assert rdd.format_size(2 * 1024 * 1024) == "2 MB"

    # 下拉选项 = 表里实际出现过的值，首项是「全部」
    vendors = [dlg.cb_vendor.itemText(i) for i in range(dlg.cb_vendor.count())]
    cores = [dlg.cb_core.itemText(i) for i in range(dlg.cb_core.count())]
    assert vendors[1:] == ["GigaDevice", "Nordic Semi", "ST", "Unspecified"]
    assert cores[1:] == ["Cortex-M4", "Cortex-M7"]
    assert dlg.cb_vendor.itemData(0) == "" and dlg.cb_core.itemData(0) == ""

    def shown():
        return [dlg.proxy.index(r, rdd.COL_NAME).data()
                for r in range(dlg.proxy.rowCount())]

    dlg.cb_vendor.setCurrentIndex(dlg.cb_vendor.findText("ST"))
    _APP.processEvents()
    assert shown() == ["STM32H743VI", "STM32H743ZI"]

    dlg.cb_vendor.setCurrentIndex(0)
    dlg.cb_core.setCurrentIndex(dlg.cb_core.findText("Cortex-M4"))
    _APP.processEvents()
    assert shown() == ["nRF52840_xxAA", "GD32F303CC", "Cortex-M4"]

    # 列筛选与搜索框是 AND
    dlg.ed_search.setText("gd32")
    _APP.processEvents()
    assert shown() == ["GD32F303CC"]

    dlg._reset_filters()
    _APP.processEvents()
    assert len(shown()) == 5
    assert dlg.ed_search.text() == ""
    assert dlg.cb_vendor.currentIndex() == 0 and dlg.cb_core.currentIndex() == 0
    dlg.hide()


def test_rtt_device_picker_sorts_size_numerically(tmp_path, monkeypatch):
    """容量列按字节数排序，不能按 "512 KB" / "2 MB" 的字面排。"""
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w._update_net_fields()
    monkeypatch.setattr(w, "_ensure_rtt_catalog", lambda: None)
    w._rtt_devices = _picker_rows()
    w._on_rtt_device_pick()
    _APP.processEvents()
    dlg = w._rtt_dev_dlg

    dlg.table.sortByColumn(rdd.COL_FLASH, Qt.DescendingOrder)
    _APP.processEvents()
    sizes = [dlg.proxy.index(r, rdd.COL_FLASH).data()
             for r in range(dlg.proxy.rowCount())]
    assert sizes == ["2 MB", "2 MB", "1 MB", "256 KB", "—"]
    dlg.table.sortByColumn(-1, Qt.AscendingOrder)
    dlg.hide()


def test_rtt_driver_dir_must_contain_dll(tmp_path, monkeypatch):
    """指错驱动目录：明确报错，且不能把原来能用的配置顶掉。"""
    from transport import rtt_io

    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_RTT)
    w._update_net_fields()
    toasts = []
    monkeypatch.setattr(w, "toast", lambda msg, error=False: toasts.append((error, msg)))
    monkeypatch.setattr(w, "_ensure_rtt_catalog", lambda: None)
    monkeypatch.setattr(rtt_io, "dll_in_directory", lambda path, mod=None: None)

    empty = tmp_path / "no_driver"
    empty.mkdir()
    w._reload_rtt_catalog(str(empty))
    assert toasts and toasts[-1][0] is True
    assert toasts[-1][1] == w._t("rtt_dev_driver_bad")
    assert w.settings.value("rtt_dll_path", None) is None

    monkeypatch.setattr(rtt_io, "dll_in_directory",
                        lambda path, mod=None: str(path) + "/JLink_x64.dll")
    previous = w._rtt_catalog_thread
    w._reload_rtt_catalog(str(empty))
    assert w.settings.value("rtt_dll_path") == str(empty)
    assert w._rtt_catalog_thread is not previous
    rtt_io.set_dll_hint("")


def test_slow_rtt_catalog_is_kept_until_finished():
    """等待超时后目录 worker 脱离窗口，结束时再销毁。"""
    from main_window import CommTool

    callbacks = []

    class _Signal:
        def disconnect(self):
            pass

        def connect(self, callback):
            callbacks.append(callback)

    class _SlowCatalog:
        def __init__(self):
            self.ready = _Signal()
            self.finished = _Signal()
            self.deleted = False

        def isRunning(self):
            return True

        def wait(self, _ms):
            return False

        def deleteLater(self):
            self.deleted = True

    th = _SlowCatalog()
    host = type("Host", (), {"_rtt_catalog_thread": th})()
    CommTool._stop_rtt_catalog(host)
    assert host._rtt_catalog_thread is None
    assert th.deleted is False
    assert len(callbacks) == 1
    callbacks[0]()
    assert th.deleted is True
