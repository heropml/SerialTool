# -*- coding: utf-8 -*-
"""Smoke tests for S-2 R39-R42 UI factories."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QTextEdit, QWidget

_APP = QApplication.instance() or QApplication([])

from ui import receive_card as rc
from ui import send_card as sc
from ui import sidebar as sb
from ui import workspace_ui as wu
from ui import ui_options as uo
from ui.widgets import make_label, Card


class _BaseHost(QWidget):
    def __init__(self):
        super(_BaseHost, self).__init__()
        self.settings = _FakeSettings()
        self._recv_font_size = 10
        self._terminal_on = False
        self._ar_on = False
        self._project_name = ""
        self._project_path = ""

    def _t(self, key, **_kw):
        return key

    def _tr_label(self, key, size=None, bold=False, color=None):
        return make_label(self._t(key), color=color)

    def _theme_id(self):
        return "light"


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


def _noop(*_a, **_k):
    pass


def test_receive_search_bar_catalog():
    host = _BaseHost()
    host.txt_recv = QTextEdit()
    # stub handlers used by search bar
    for name in (
        "_do_search", "_search_next", "_on_search_mode_changed",
        "_on_search_case_toggled", "_search_prev", "_close_search",
        "_style_search_bar",
    ):
        setattr(host, name, _noop)
    rc.build_search_bar(host)
    assert host.cb_search_mode.count() == len(uo.SEARCH_MODE_ITEMS)
    assert host._search_bar.isHidden()
    assert host.btn_search_prev.text() == "\u25b2"  # up triangle
    assert host.btn_search_next.text() == "\u25bc"  # down triangle
    assert host.btn_search_close.text() == "\u2715"


def test_sidebar_assembles_cards():
    host = _BaseHost()
    host.build_settings_card = lambda: Card()
    host.build_data_options_card = lambda: Card()
    host.build_send_options_card = lambda: Card()
    scroll = sb.build(host)
    assert scroll.objectName() == "Sidebar"
    assert scroll.minimumWidth() == 305
    assert host._left_send_card is not None


def test_workbench_bar_buttons():
    host = _BaseHost()
    host._switch_workspace = _noop
    host._show_project_menu = _noop
    host._update_project_label = _noop
    bar = wu.build_workbench_bar(host)
    assert bar.objectName() == "WorkbenchBar"
    assert set(host._workbench_buttons) == {
        "terminal", "protocol", "simulation", "automation", "data", "bridge",
    }


def test_protocol_template_panel():
    host = _BaseHost()
    host._workspace_template_options = lambda: (("project_proto_raw", "raw"),)
    host._update_workspace_template_preview = _noop
    host._apply_workspace_protocol_template = _noop
    panel = wu.build_protocol_template_panel(host)
    assert panel.objectName() == "WorkspaceTemplatePanel"
    assert host.cb_workspace_template.count() == 1
