# -*- coding: utf-8 -*-
"""Send-options sidebar card factory (Qt).

S-2 R36: move CommTool.build_send_options_card body here so main_window
stays a thin wrapper. Widgets are attached onto the host `app`.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QVBoxLayout,
)

from ui.i18n import CHECKSUM_KEYS
from ui.theme import COLOR_TEXT_SECONDARY
from ui.widgets import Card, CollapsibleSection, IOSSwitch, SuffixLineEdit
from ui.ui_options import APPEND_NL_OPTIONS, TERM_ENTER_OPTIONS

MAIN_W = 90
_TERM_FRAME_QSS = (
    "QFrame#SettingsGroup{border:1px solid rgba(0,122,255,0.7);border-radius:8px;"
    "background:transparent;}"
)


def term_section_expanded(saved_expanded, terminal_on):
    """Collapsible terminal section: keep open when terminal mode is on."""
    return bool(saved_expanded) or bool(terminal_on)


def build(app):
    """Build the send-options Card and bind widgets onto `app`.

    Required on `app`: `_t`, `_tr_label`, `_setting_labels` (dict),
    `_terminal_on`, `_terminal_echo`, `_terminal_enter`, `settings`,
    `on_period_toggled`, `_set_terminal_enabled`, `_on_term_echo_changed`,
    `_on_term_enter_changed`.
    """
    card = Card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 10, 14, 10)
    layout.setSpacing(6)
    layout.addWidget(app._tr_label("send_area", 12, bold=True))

    grid = QGridLayout()
    # Lock switch/combo columns so this card and its collapsible share widths.
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setColumnStretch(0, 1)
    grid.setColumnMinimumWidth(1, MAIN_W)
    grid.setColumnMinimumWidth(2, MAIN_W)
    grid.setHorizontalSpacing(6)
    grid.setVerticalSpacing(6)

    def lbl(key):
        w = app._tr_label(key, color=COLOR_TEXT_SECONDARY)
        # List per key: same i18n key may appear on multiple cards.
        app._setting_labels.setdefault(key, []).append(w)
        return w

    def sw_row(row, key, sw):
        grid.addWidget(lbl(key), row, 0)
        grid.addWidget(sw, row, 2, alignment=Qt.AlignRight)

    def sw_extra_row(row, key, sw, extra):
        grid.addWidget(lbl(key), row, 0)
        grid.addWidget(sw, row, 1, alignment=Qt.AlignRight)
        grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

    def extra_row(row, key, extra):
        grid.addWidget(lbl(key), row, 0)
        grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

    row = 0
    app.sw_tx_hex = IOSSwitch(False)
    sw_row(row, "hex_send", app.sw_tx_hex)
    row += 1

    app.sw_append_newline = IOSSwitch(False)
    app.cb_append_nl = QComboBox()
    for _nl in APPEND_NL_OPTIONS:
        app.cb_append_nl.addItem(_nl)
    app.cb_append_nl.setFixedWidth(MAIN_W)
    sw_extra_row(row, "append_newline", app.sw_append_newline, app.cb_append_nl)
    row += 1

    app.sw_period = IOSSwitch(False)
    app.sw_period.toggled.connect(app.on_period_toggled)
    app.ed_period_ms = SuffixLineEdit("1000", "ms")
    app.ed_period_ms.setFixedWidth(MAIN_W)
    sw_extra_row(row, "period", app.sw_period, app.ed_period_ms)
    row += 1

    app.cb_checksum = QComboBox()
    for ck_key in CHECKSUM_KEYS:
        app.cb_checksum.addItem(app._t(ck_key))
    app.cb_checksum.setFixedWidth(MAIN_W)
    extra_row(row, "checksum", app.cb_checksum)
    row += 1

    layout.addLayout(grid)

    term_frame = QFrame()
    term_frame.setObjectName("SettingsGroup")
    term_frame.setStyleSheet(_TERM_FRAME_QSS)
    tg = QGridLayout(term_frame)
    tg.setContentsMargins(10, 6, 10, 6)
    tg.setColumnStretch(0, 1)
    tg.setColumnMinimumWidth(2, MAIN_W)
    tg.setHorizontalSpacing(6)
    tg.setVerticalSpacing(6)

    app.sw_terminal = IOSSwitch(app._terminal_on)
    app.sw_terminal.toggled.connect(app._set_terminal_enabled)
    tg.addWidget(lbl("term_mode"), 0, 0)
    tg.addWidget(app.sw_terminal, 0, 2, alignment=Qt.AlignRight)

    app.sw_term_echo = IOSSwitch(app._terminal_echo)
    app.sw_term_echo.toggled.connect(app._on_term_echo_changed)
    tg.addWidget(lbl("term_echo"), 1, 0)
    tg.addWidget(app.sw_term_echo, 1, 2, alignment=Qt.AlignRight)

    app.cb_term_enter = QComboBox()
    for _nl in TERM_ENTER_OPTIONS:
        app.cb_term_enter.addItem(_nl)
    app.cb_term_enter.setCurrentIndex(app._terminal_enter)
    app.cb_term_enter.setFixedWidth(MAIN_W)
    app.cb_term_enter.currentIndexChanged.connect(app._on_term_enter_changed)
    tg.addWidget(lbl("term_enter"), 2, 0)
    tg.addWidget(app.cb_term_enter, 2, 2, alignment=Qt.AlignRight)

    app.sec_send_term = CollapsibleSection(
        app._t("term_mode"),
        expanded=term_section_expanded(
            app.settings.value("sec_send_term", False, type=bool),
            app._terminal_on))
    _tl = QVBoxLayout()
    _tl.setContentsMargins(0, 0, 0, 0)
    _tl.addWidget(term_frame)
    app.sec_send_term.setContentLayout(_tl)
    app.sec_send_term.toggled.connect(
        lambda on: app.settings.setValue("sec_send_term", on))
    layout.addWidget(app.sec_send_term)
    return card
