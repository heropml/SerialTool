# -*- coding: utf-8 -*-
"""Tests for S-2 R36 send_options_card factory."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

import send_options_card as soc
import ui_options as uo
from i18n import CHECKSUM_KEYS
from widgets import make_label


class _FakeSettings(object):
    def __init__(self, values=None):
        self._d = dict(values or {})

    def value(self, key, default=None, type=None):
        v = self._d.get(key, default)
        if type is bool:
            return bool(v)
        return v

    def setValue(self, key, value):
        self._d[key] = value


class _FakeHost(object):
    def __init__(self, terminal_on=False, enter_idx=1):
        self._setting_labels = {}
        self._terminal_on = terminal_on
        self._terminal_echo = True
        self._terminal_enter = enter_idx
        self.settings = _FakeSettings({"sec_send_term": False})
        self.period_calls = []
        self.term_calls = []

    def _t(self, key, **_kw):
        return key

    def _tr_label(self, key, size=None, bold=False, color=None):
        return make_label(self._t(key), color=color)

    def on_period_toggled(self, on):
        self.period_calls.append(on)

    def _set_terminal_enabled(self, on):
        self.term_calls.append(("term", on))

    def _on_term_echo_changed(self, on):
        self.term_calls.append(("echo", on))

    def _on_term_enter_changed(self, idx):
        self.term_calls.append(("enter", idx))


def test_term_section_expanded():
    assert soc.term_section_expanded(False, False) is False
    assert soc.term_section_expanded(True, False) is True
    assert soc.term_section_expanded(False, True) is True
    assert soc.term_section_expanded(None, True) is True


def test_build_attaches_widgets_and_catalogs():
    host = _FakeHost(terminal_on=True, enter_idx=2)
    card = soc.build(host)
    assert card is not None
    assert host.cb_append_nl.count() == len(uo.APPEND_NL_OPTIONS)
    assert host.cb_append_nl.itemText(0) == uo.APPEND_NL_OPTIONS[0]
    assert host.cb_term_enter.count() == len(uo.TERM_ENTER_OPTIONS)
    assert host.cb_term_enter.currentIndex() == 2
    assert host.cb_checksum.count() == len(CHECKSUM_KEYS)
    assert host.cb_checksum.itemText(0) == "ck_none"
    assert "hex_send" in host._setting_labels
    assert "term_mode" in host._setting_labels
    assert host.sec_send_term is not None
    # terminal_on forces section expanded even if settings say collapsed
    assert host.sw_terminal.isChecked() is True
