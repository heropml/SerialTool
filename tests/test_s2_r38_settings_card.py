# -*- coding: utf-8 -*-
"""Tests for S-2 R38 settings_card factory."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

import settings_card as sc
import serial_params as sp
from conn_ui import visible_conn_types
from widgets import make_label


class _FakeHost(QObject):
    def __init__(self):
        super(_FakeHost, self).__init__()
        self.conn = None
        self._calls = []

    def _t(self, key, **_kw):
        return key

    def _tr_label(self, key, size=None, bold=False, color=None):
        return make_label(self._t(key), color=color)

    def _label_col_width(self):
        return 72

    def _on_connection_preset_activated(self, *_a):
        pass

    def save_connection_preset_from_ui(self, prompt_name=False):
        pass

    def open_connection_presets(self):
        pass

    def _update_net_fields(self):
        self._calls.append("update_net")

    def _on_serial_port_selected(self, *_a):
        pass

    def refresh_ports(self):
        pass

    def _on_flow_changed(self, *_a):
        pass

    def _apply_serial_params_live(self, *_a):
        pass

    def _on_vconn_loop_toggled(self, *_a):
        pass

    def _on_ble_scan_clicked(self):
        pass

    def _on_ble_profile_changed(self, *_a):
        pass

    def _on_ble_swap_clicked(self):
        pass

    def toggle_conn(self):
        pass

    def _on_dtr_toggled(self, *_a):
        pass

    def _on_rts_toggled(self, *_a):
        pass

    def _pulse_reset(self):
        pass

    def _send_break(self):
        pass

    def _poll_ctrl_lines(self):
        pass

    def _rebuild_connection_preset_combo(self):
        self._calls.append("rebuild_preset")


def test_build_serial_catalogs_and_conn_types():
    host = _FakeHost()
    card = sc.build(host)
    assert card is not None
    shown = visible_conn_types()
    assert host.cb_proto.count() == len(shown)
    assert [host.cb_proto.itemText(i) for i in range(host.cb_proto.count())] == shown
    assert host.cb_baud.count() == len(sp.BAUD_RATES)
    assert host.cb_baud.currentText() == "115200"
    assert list(host.cb_databits.itemText(i) for i in range(host.cb_databits.count())) == list(sp.DATABITS_OPTIONS)
    assert host.cb_parity.count() == len(sp.PARITY_OPTIONS)
    assert host.cb_stopbits.currentText() == "1"
    assert host.cb_flow.currentText() == "None"
    assert set(host._ctrl_dots) == {"cts", "dsr", "dcd", "ri"}
    assert host._ctrl_poll_timer.interval() == 200
    assert "update_net" in host._calls
    assert "rebuild_preset" in host._calls
    assert host.btn_refresh.text() == "\u27f3"
    assert host._ctrl_dots["cts"].text() == "\u25cf"
    assert hasattr(host, "btn_ble_scan")
    assert not hasattr(host, "tbl_ble")
    assert not hasattr(host, "btn_ble_stop")
    assert host.cb_ble_profile.count() == 5
    assert host.cb_ble_write_mode.count() == 3
