# -*- coding: utf-8 -*-
"""Tests for S-2 R37 data_options_card factory."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

from ui import data_options_card as doc
from ui import ui_options as uo
from ui.widgets import make_label


class _FakeSettings(object):
    def __init__(self):
        self._d = {}

    def value(self, key, default=None, type=None):
        v = self._d.get(key, default)
        if type is bool:
            return bool(v)
        return v

    def setValue(self, key, value):
        self._d[key] = value


class _FakeHost(object):
    def __init__(self):
        self._setting_labels = {}
        self._hexdump_on = False
        self._numview_on = True
        self._ansi_on = True
        self.settings = _FakeSettings()

    def _t(self, key, **_kw):
        return key

    def _tr_label(self, key, size=None, bold=False, color=None):
        return make_label(self._t(key), color=color)

    def _on_hex_display_changed(self, *_a):
        pass

    def _on_hexdump_toggled(self, *_a):
        pass

    def _on_numview_toggled(self, *_a):
        pass

    def _on_view_mode_changed(self, *_a):
        pass

    def _on_hexdump_width_changed(self, *_a):
        pass

    def _on_numview_type_changed(self, *_a):
        pass

    def _on_ansi_toggled(self, *_a):
        pass

    def _on_encoding_changed(self, *_a):
        pass

    def on_wrap_toggled(self, *_a):
        pass

    def _on_ts_format_changed(self, *_a):
        pass

    def _flush_pending_cr(self, *_a):
        pass

    def on_log_file_toggled(self, *_a):
        pass

    def _on_log_split_changed(self, *_a):
        pass

    def _on_max_lines_changed(self, *_a):
        pass

    def _on_freeze_view_toggled(self, *_a):
        pass

    def save_recv(self, *_a):
        pass

    def clear_recv(self, *_a):
        pass


def test_build_fills_catalogs_and_hidden_switches():
    host = _FakeHost()
    card = doc.build(host)
    assert card is not None
    assert host.cb_view_mode.count() == len(uo.VIEW_MODE_ITEMS)
    assert host.cb_view_mode.itemData(0) == "text"
    assert host.cb_hexdump_width.count() == len(uo.HEXDUMP_WIDTH_OPTIONS)
    assert host.cb_numview_type.count() == len(uo.NUMVIEW_TYPE_OPTIONS)
    assert host.cb_encoding.itemData(0) == "auto"
    assert host.cb_encoding.count() == 1 + len(uo.ENCODING_CODECS)
    assert host.cb_ts_format.count() == len(uo.TS_FORMAT_ITEMS)
    assert host.cb_line_nl.count() == 1 + len(uo.LINE_NL_FIXED)
    assert host.cb_log_split.count() == 1 + len(uo.LOG_SPLIT_SIZES)
    assert host.sw_rx_hex.isHidden()
    assert host.sw_hexdump.isHidden()
    assert host.sw_numview.isHidden()
    assert host.sw_numview.isChecked() is True
    assert host.sw_ansi.isChecked() is True
    assert host._view_extra.count() == 4
    assert "view_mode" in host._setting_labels
    assert host.btn_save.property("tr_text") == "save"
    assert host.btn_clear_rx.property("tr_text") == "clear"
