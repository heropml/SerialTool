# -*- coding: utf-8 -*-
"""Tests for S-4 size roll helpers + Modbus oneshot strip wiring."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication, QLineEdit, QComboBox, QLabel, QPushButton

_APP = QApplication.instance() or QApplication([])

import log_naming  # noqa: E402
import modbus_master  # noqa: E402


def test_parse_size_limit_units():
    assert log_naming.parse_size_limit("2M") == 2 * 1024 * 1024
    assert log_naming.parse_size_limit("512K") == 512 * 1024
    assert log_naming.parse_size_limit("1.5G") == int(1.5 * 1024 ** 3)
    assert log_naming.parse_size_limit("3") == 3 * 1024 * 1024  # bare -> MB
    assert log_naming.parse_size_limit("none") == 0
    assert log_naming.parse_size_limit("") == 0


def test_should_roll_size_combined_with_date_semantics():
    assert log_naming.should_roll_size(0, 100) is False
    assert log_naming.should_roll_size(100, 100) is True
    assert log_naming.should_roll_size(101, 100) is True
    assert log_naming.should_roll_size(9999, 0) is False
    assert log_naming.should_roll_size(None, 100) is False
    assert log_naming.should_roll_size(-1, 100) is False
    assert log_naming.should_roll_size(100, None) is False
    assert log_naming.should_roll_size(100, "abc") is False
    assert log_naming.should_roll_size(100, "200") is False
    assert log_naming.should_roll_size(200, "200") is True


def test_oneshot_normalize_read_and_write():
    r = modbus_master.normalize_poll({
        "enabled": True, "unit": 1, "func": 3, "addr": 10, "qty": 2,
        "period": 0x7FFFFFFF,
    })
    assert r["func"] == 3 and r["qty"] == 2 and r["addr"] == 10
    w = modbus_master.normalize_poll({
        "enabled": True, "unit": 1, "func": 6, "addr": 10, "wval": 0x1234,
        "period": 0x7FFFFFFF,
    })
    assert w["func"] == 6 and w["wval"] == 0x1234 and w["qty"] == 1


def test_oneshot_run_reuses_device_scan():
    from modbus_master_dialog import ModbusMasterDialog, ONESHOT_FUNCS

    class FakeApp:
        def __init__(self):
            self._mbm_on = False
            self._mbm_variant = ""
            self._mbm_echo = False
            self._mbm_rules = []
            self.settings = mock.Mock()
            self.settings.value = mock.Mock(return_value="")
            self._t = lambda k, **kw: k
            self.toasts = []
            self.toast = lambda msg, error=False: self.toasts.append((msg, error))
            self.scan_calls = []

        def _start_device_scan(self, rules, timeout_ms, on_result, on_done):
            self.scan_calls.append((rules, timeout_ms, on_result, on_done))
            on_result(0, "ok", "4660")
            on_done(False)
            return True

        def _theme_id(self):
            return "light"

    app = FakeApp()
    dlg = ModbusMasterDialog.__new__(ModbusMasterDialog)
    dlg.app = app
    dlg.ed_os_unit = QLineEdit("1")
    dlg.ed_os_addr = QLineEdit("0")
    dlg.ed_os_qty = QLineEdit("1")
    dlg.cb_os_func = QComboBox()
    for code, key in ONESHOT_FUNCS:
        dlg.cb_os_func.addItem(key, code)
    dlg.cb_os_func.setCurrentIndex(2)  # FC03
    dlg.lbl_os_result = QLabel()
    dlg.btn_os_run = QPushButton()
    dlg._scan_locked = lambda: False
    dlg._oneshot_run()
    assert len(app.scan_calls) == 1
    rule = app.scan_calls[0][0][0]
    assert rule["func"] == 3
    assert "4660" in dlg.lbl_os_result.text()


def test_oneshot_cancelled_clears_running_placeholder():
    from modbus_master_dialog import ModbusMasterDialog, ONESHOT_FUNCS

    class FakeApp:
        def __init__(self):
            self._t = lambda k, **kw: k
            self.toast = lambda *a, **k: None

        def _start_device_scan(self, rules, timeout_ms, on_result, on_done):
            # Simulate disconnect: cancel without delivering a result.
            on_done(True)
            return True

        def _theme_id(self):
            return "light"

    app = FakeApp()
    dlg = ModbusMasterDialog.__new__(ModbusMasterDialog)
    dlg.app = app
    dlg.ed_os_unit = QLineEdit("1")
    dlg.ed_os_addr = QLineEdit("0")
    dlg.ed_os_qty = QLineEdit("1")
    dlg.cb_os_func = QComboBox()
    for code, key in ONESHOT_FUNCS:
        dlg.cb_os_func.addItem(key, code)
    dlg.cb_os_func.setCurrentIndex(2)
    dlg.lbl_os_result = QLabel()
    dlg._scan_locked = lambda: False
    dlg._oneshot_run()
    assert dlg.lbl_os_result.text() == "mbm_os_cancelled"


def test_oneshot_func_change_clears_stale_result():
    from modbus_master_dialog import ModbusMasterDialog, ONESHOT_FUNCS

    class FakeApp:
        def __init__(self):
            self._t = lambda k, **kw: k

    dlg = ModbusMasterDialog.__new__(ModbusMasterDialog)
    dlg.app = FakeApp()
    dlg.ed_os_qty = QLineEdit("1")
    dlg.cb_os_func = QComboBox()
    for code, key in ONESHOT_FUNCS:
        dlg.cb_os_func.addItem(key, code)
    dlg.cb_os_func.setCurrentIndex(2)  # FC03
    dlg.lbl_os_result = QLabel("4660")
    dlg._os_func_changed()
    assert dlg.lbl_os_result.text() == ""
    dlg.cb_os_func.setCurrentIndex(4)  # FC05
    dlg.lbl_os_result.setText("ok")
    dlg._os_func_changed()
    assert dlg.lbl_os_result.text() == ""


def _oneshot_dlg(app, func_index=2, qty="1"):
    from modbus_master_dialog import ModbusMasterDialog, ONESHOT_FUNCS

    dlg = ModbusMasterDialog.__new__(ModbusMasterDialog)
    dlg.app = app
    dlg.ed_os_unit = QLineEdit("1")
    dlg.ed_os_addr = QLineEdit("0")
    dlg.ed_os_qty = QLineEdit(qty)
    dlg.cb_os_func = QComboBox()
    for code, key in ONESHOT_FUNCS:
        dlg.cb_os_func.addItem(key, code)
    dlg.cb_os_func.setCurrentIndex(func_index)
    dlg.lbl_os_result = QLabel()
    dlg.btn_os_run = QPushButton()
    dlg.btn_os_cancel = QPushButton()
    dlg.btn_os_cancel.setEnabled(False)
    return dlg


def test_oneshot_fc05_write_uses_wval():
    class FakeApp:
        def __init__(self):
            self._t = lambda k, **kw: k
            self.toast = lambda *a, **k: None
            self.scan_calls = []

        def _start_device_scan(self, rules, timeout_ms, on_result, on_done):
            self.scan_calls.append(rules[0])
            on_result(0, "ok", "1")
            on_done(False)
            return True

        def _theme_id(self):
            return "light"

    app = FakeApp()
    dlg = _oneshot_dlg(app, func_index=4, qty="1")  # FC05
    dlg._scan_locked = lambda: False
    dlg._oneshot_run()
    assert len(app.scan_calls) == 1
    rule = app.scan_calls[0]
    assert rule["func"] == 5
    assert rule.get("wval") == 1
    assert dlg.btn_os_run.isEnabled()
    assert not dlg.btn_os_cancel.isEnabled()


def test_oneshot_scan_locked_guard_toasts_and_skips():
    from modbus_master_dialog import ModbusMasterDialog

    class FakeApp:
        def __init__(self):
            self._t = lambda k, **kw: k
            self.toasts = []
            self.toast = lambda msg, error=False: self.toasts.append((msg, error))
            self.scan_calls = []
            self._device_scan_state = {"busy": True}

        def toast_io_exclusive_busy(self, exclude=()):
            self.toast(self._t("io_exclusive_busy"), error=True)

        def _start_device_scan(self, *a, **k):
            self.scan_calls.append(1)
            return True

    app = FakeApp()
    dlg = _oneshot_dlg(app)
    dlg._scan_locked = ModbusMasterDialog._scan_locked.__get__(dlg, ModbusMasterDialog)
    dlg._oneshot_run()
    assert app.scan_calls == []
    assert app.toasts and app.toasts[0][0] == "io_exclusive_busy"


def test_oneshot_start_false_marks_failed():
    class FakeApp:
        def __init__(self):
            self._t = lambda k, **kw: k
            self.toast = lambda *a, **k: None

        def _start_device_scan(self, *a, **k):
            return False

        def _theme_id(self):
            return "light"

    app = FakeApp()
    dlg = _oneshot_dlg(app)
    dlg._scan_locked = lambda: False
    dlg._oneshot_run()
    assert dlg.lbl_os_result.text() == "mbm_os_failed"
    assert dlg.btn_os_run.isEnabled()
    assert not dlg.btn_os_cancel.isEnabled()


def test_oneshot_cancel_calls_stop_device_scan():
    class FakeApp:
        def __init__(self):
            self._t = lambda k, **kw: k
            self.stops = []

        def _stop_device_scan(self, cancelled=False):
            self.stops.append(cancelled)

    app = FakeApp()
    dlg = _oneshot_dlg(app)
    dlg._oneshot_cancel()
    assert app.stops == [True]
