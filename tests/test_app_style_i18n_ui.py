# -*- coding: utf-8 -*-
"""B5: app_style QSS builder + i18n_ui retranslate tables/helpers."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ui import app_style
from ui import i18n_ui
from ui.theme import THEMES, THEME_DEFAULT, chrome_for


def test_build_app_qss_embeds_chrome_and_theme_colors():
    for tid in ("default", "dark", "solar_lt"):
        c = chrome_for(tid)
        t = THEMES[tid]
        qss = app_style.build_app_qss(c, t, "#ABCDEF", "#123456")
        assert "QMainWindow" in qss
        assert "QTextEdit#RecvBox" in qss
        assert "QToolTip" in qss
        assert c["window_bg"] in qss
        assert c["accent"] in qss
        assert t["bg"] in qss
        assert t["fg"] in qss
        assert "#ABCDEF" in qss
        assert "#123456" in qss


def test_build_app_qss_default_theme_id_stable():
    c = chrome_for(THEME_DEFAULT)
    t = THEMES[THEME_DEFAULT]
    qss = app_style.build_app_qss(c, t, "#000000", "#FFFFFF")
    assert "QPushButton#PrimaryBtn" in qss
    assert "QWidget#SessionTabBar" in qss


def test_retranslate_dialog_attrs_unique_and_named():
    attrs = i18n_ui.RETRANSLATE_DIALOG_ATTRS
    assert len(attrs) == len(set(attrs))
    assert attrs  # non-empty
    for name in attrs:
        assert name.startswith("_") and name.endswith("_dlg")


def test_retranslate_dialogs_calls_only_present():
    class _Dlg:
        def __init__(self):
            self.n = 0

        def retranslate(self):
            self.n += 1

    class _Host:
        _multi_send_dlg = _Dlg()
        _bridge_dlg = _Dlg()
        _missing_dlg = None

    host = _Host()
    i18n_ui.retranslate_dialogs(
        host, attrs=("_multi_send_dlg", "_bridge_dlg", "_no_such", "_missing_dlg"))
    assert host._multi_send_dlg.n == 1
    assert host._bridge_dlg.n == 1


def test_refill_combo_keys_and_data_items():
    from PyQt5.QtWidgets import QApplication, QComboBox

    app = QApplication.instance() or QApplication([])
    combo = QComboBox()
    combo.addItem("old0")
    combo.addItem("old1")
    combo.setCurrentIndex(1)
    i18n_ui.refill_combo_keys(combo, ("a", "b", "c"), lambda k: "T:" + k)
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "T:a", "T:b", "T:c"]
    assert combo.currentIndex() == 1

    data_combo = QComboBox()
    data_combo.addItem("x", "keep")
    data_combo.addItem("y", "other")
    data_combo.setCurrentIndex(0)
    i18n_ui.refill_combo_data_items(
        data_combo, (("keep", "k1"), ("other", "k2"), ("new", "k3")),
        lambda k: "L:" + k)
    assert data_combo.currentData() == "keep"
    assert data_combo.itemText(0) == "L:k1"
    assert data_combo.count() == 3
    del app
