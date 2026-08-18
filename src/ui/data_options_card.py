# -*- coding: utf-8 -*-
"""Data-options sidebar card factory (Qt).

S-2 R37: move CommTool.build_data_options_card body here so main_window
stays a thin wrapper. Widgets are attached onto the host `app`.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLineEdit, QPushButton,
    QStackedLayout, QVBoxLayout, QWidget,
)

from ui.theme import COLOR_TEXT_SECONDARY
from ui.ui_tips import set_tooltip
from ui.widgets import (
    Card, CollapsibleSection, IOSSwitch, SuffixLineEdit, make_label,
)
from ui.ui_options import (
    VIEW_MODE_ITEMS,
    ENCODING_CODECS,
    NUMVIEW_TYPE_OPTIONS,
    HEXDUMP_WIDTH_OPTIONS,
    TS_FORMAT_ITEMS,
    LOG_SPLIT_SIZES,
    LINE_NL_FIXED,
    numview_item_label,
    numview_item_data,
)

MAIN_W = 90


def build(app):
    """Build the data-options Card and bind widgets onto `app`.

    Required on `app`: `_t`, `_tr_label`, `_setting_labels`,
    `_hexdump_on`, `_numview_on`, `_ansi_on`, `settings`, plus the
    various `_on_*` / `on_*` / `save_recv` / `clear_recv` handlers.
    """
    card = Card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 10, 14, 10)
    layout.setSpacing(6)
    layout.addWidget(app._tr_label("data_area", 12, bold=True))

    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setColumnStretch(0, 1)
    grid.setColumnMinimumWidth(1, MAIN_W)
    grid.setColumnMinimumWidth(2, MAIN_W)
    grid.setHorizontalSpacing(6)
    grid.setVerticalSpacing(6)

    def lbl(key):
        w = app._tr_label(key, color=COLOR_TEXT_SECONDARY)
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
    # Hidden switches keep legacy settings keys / isChecked() call sites.
    app.sw_rx_hex = IOSSwitch(False)
    app.sw_rx_hex.toggled.connect(app._on_hex_display_changed)
    app.sw_hexdump = IOSSwitch(app._hexdump_on)
    app.sw_hexdump.toggled.connect(app._on_hexdump_toggled)
    app.sw_numview = IOSSwitch(app._numview_on)
    app.sw_numview.toggled.connect(app._on_numview_toggled)
    for _sw in (app.sw_rx_hex, app.sw_hexdump, app.sw_numview):
        _sw.hide()

    app.cb_view_mode = QComboBox()
    for _key, _data in VIEW_MODE_ITEMS:
        app.cb_view_mode.addItem(app._t(_key), _data)
    app.cb_view_mode.setFixedWidth(MAIN_W)
    app.cb_view_mode.setProperty("tr_tooltip", "view_mode_tip")
    set_tooltip(app.cb_view_mode, app._t("view_mode_tip"))
    app.cb_view_mode.currentIndexChanged.connect(app._on_view_mode_changed)

    app.cb_hexdump_width = QComboBox()
    app.cb_hexdump_width.addItems(list(HEXDUMP_WIDTH_OPTIONS))
    app.cb_hexdump_width.setCurrentText("16")
    app.cb_hexdump_width.setFixedWidth(MAIN_W)
    app.cb_hexdump_width.setProperty("tr_tooltip", "hexdump_width_tip")
    set_tooltip(app.cb_hexdump_width, app._t("hexdump_width_tip"))
    app.cb_hexdump_width.currentIndexChanged.connect(app._on_hexdump_width_changed)

    app.cb_numview_type = QComboBox()
    for _t_, _e_ in NUMVIEW_TYPE_OPTIONS:
        app.cb_numview_type.addItem(
            numview_item_label(_t_, _e_), numview_item_data(_t_, _e_))
    app.cb_numview_type.setFixedWidth(MAIN_W)
    app.cb_numview_type.setProperty("tr_tooltip", "numview_type_tip")
    set_tooltip(app.cb_numview_type, app._t("numview_type_tip"))
    app.cb_numview_type.currentIndexChanged.connect(app._on_numview_type_changed)

    app.sw_ansi = IOSSwitch(app._ansi_on)
    app.sw_ansi.toggled.connect(app._on_ansi_toggled)
    _ansi_page = QWidget()
    _ansi_page.setFixedWidth(MAIN_W)
    _ah = QHBoxLayout(_ansi_page)
    _ah.setContentsMargins(0, 0, 0, 0)
    _ah.setSpacing(4)
    app.lbl_ansi = make_label(app._t("ansi_color"), color=COLOR_TEXT_SECONDARY)
    _ah.addStretch(1)
    _ah.addWidget(app.lbl_ansi)
    _ah.addWidget(app.sw_ansi)
    for _w in (_ansi_page, app.lbl_ansi, app.sw_ansi):
        set_tooltip(_w, app._t("ansi_tip"))
    _ansi_page.setProperty("tr_tooltip", "ansi_tip")
    app.sw_ansi.setProperty("tr_tooltip", "ansi_tip")

    # Host first: stacked page without parent would flash as a top-level window.
    _extra_host = QWidget()
    _extra_host.setFixedWidth(MAIN_W)
    app._view_extra = QStackedLayout(_extra_host)
    app._view_extra.setContentsMargins(0, 0, 0, 0)
    _blank = QWidget()
    _blank.setFixedWidth(MAIN_W)
    app._view_extra.addWidget(_ansi_page)            # 0 = text: ANSI
    app._view_extra.addWidget(_blank)                # 1 = HEX: none
    app._view_extra.addWidget(app.cb_hexdump_width)  # 2 = hexdump width
    app._view_extra.addWidget(app.cb_numview_type)   # 3 = numeric type

    grid.addWidget(lbl("view_mode"), row, 0)
    grid.addWidget(_extra_host, row, 1, alignment=Qt.AlignRight)
    grid.addWidget(app.cb_view_mode, row, 2, alignment=Qt.AlignRight)
    row += 1

    app.cb_encoding = QComboBox()
    app.cb_encoding.addItem(app._t("encoding_auto"), "auto")
    for codec_name in ENCODING_CODECS:
        app.cb_encoding.addItem(codec_name, codec_name.lower())
    app.cb_encoding.setFixedWidth(MAIN_W)
    app.cb_encoding.currentIndexChanged.connect(
        lambda _: app._on_encoding_changed())
    extra_row(row, "encoding", app.cb_encoding)
    row += 1

    app.sw_wrap = IOSSwitch(True)
    app.sw_wrap.toggled.connect(app.on_wrap_toggled)
    sw_row(row, "auto_wrap", app.sw_wrap)
    row += 1

    app.sw_show_timestamp = IOSSwitch(False)
    app.cb_ts_format = QComboBox()
    app.cb_ts_format.blockSignals(True)
    for data, key in TS_FORMAT_ITEMS:
        app.cb_ts_format.addItem(app._t(key), data)
    app.cb_ts_format.blockSignals(False)
    app.cb_ts_format.setFixedWidth(MAIN_W)
    app.cb_ts_format.currentIndexChanged.connect(app._on_ts_format_changed)
    sw_extra_row(row, "show_timestamp", app.sw_show_timestamp, app.cb_ts_format)
    row += 1

    app.sw_packet_split = IOSSwitch(False)
    app.ed_packet_timeout = SuffixLineEdit("20", "ms")
    app.ed_packet_timeout.setFixedWidth(MAIN_W)
    sw_extra_row(row, "packet_split", app.sw_packet_split, app.ed_packet_timeout)
    row += 1

    layout.addLayout(grid)

    more = QGridLayout()
    more.setContentsMargins(0, 0, 0, 0)
    more.setColumnStretch(0, 1)
    more.setColumnMinimumWidth(1, MAIN_W)
    more.setColumnMinimumWidth(2, MAIN_W)
    more.setHorizontalSpacing(6)
    more.setVerticalSpacing(6)
    grid, mrow = more, 0

    app.sw_line_split = IOSSwitch(False)
    app.cb_line_nl = QComboBox()
    app.cb_line_nl.addItem(app._t("nl_auto"))
    for _nl in LINE_NL_FIXED:
        app.cb_line_nl.addItem(_nl)
    app.cb_line_nl.setFixedWidth(MAIN_W)
    app.cb_line_nl.currentIndexChanged.connect(
        lambda _: app._flush_pending_cr())
    sw_extra_row(mrow, "line_split", app.sw_line_split, app.cb_line_nl)
    mrow += 1

    app.sw_log_file = IOSSwitch(False)
    set_tooltip(app.sw_log_file, app._t("log_vars_tip"))
    app.sw_log_file.setProperty("tr_tooltip", "log_vars_tip")
    app.sw_log_file.toggled.connect(app.on_log_file_toggled)
    app.cb_log_split = QComboBox()
    app.cb_log_split.setEditable(True)
    app.cb_log_split.addItem(app._t("log_split_none"))
    for s in LOG_SPLIT_SIZES:
        app.cb_log_split.addItem(s)
    app.cb_log_split.setCurrentIndex(0)
    app.cb_log_split.setFixedWidth(MAIN_W)
    set_tooltip(app.cb_log_split, app._t("log_split_tip"))
    app.cb_log_split.setProperty("tr_tooltip", "log_split_tip")
    app.cb_log_split.currentTextChanged.connect(app._on_log_split_changed)
    sw_extra_row(mrow, "real_time_log", app.sw_log_file, app.cb_log_split)
    mrow += 1

    app.ed_max_lines = QLineEdit("10000")
    app.ed_max_lines.setAlignment(Qt.AlignRight)
    app.ed_max_lines.setFixedWidth(MAIN_W)
    app.ed_max_lines.editingFinished.connect(app._on_max_lines_changed)
    extra_row(mrow, "max_lines", app.ed_max_lines)
    mrow += 1

    app.sw_freeze_view = IOSSwitch(False)
    app.sw_freeze_view.setProperty("tr_tooltip", "freeze_view_tip")
    set_tooltip(app.sw_freeze_view, app._t("freeze_view_tip"))
    app.sw_freeze_view.toggled.connect(app._on_freeze_view_toggled)
    sw_row(mrow, "freeze_view", app.sw_freeze_view)
    mrow += 1

    app.sec_recv_more = CollapsibleSection(
        app._t("more_settings"),
        expanded=app.settings.value("sec_recv_more", False, type=bool))
    app.sec_recv_more.setContentLayout(more)
    app.sec_recv_more.toggled.connect(
        lambda on: app.settings.setValue("sec_recv_more", on))
    layout.addWidget(app.sec_recv_more)
    layout.addStretch(1)

    btns = QHBoxLayout()
    btns.setContentsMargins(0, 0, 0, 0)
    btns.setSpacing(6)

    app.btn_save = QPushButton(app._t("save"))
    app.btn_save.setObjectName("GhostBtn")
    app.btn_save.setFixedWidth(MAIN_W)
    app.btn_save.setProperty("tr_text", "save")
    app.btn_save.clicked.connect(app.save_recv)
    btns.addWidget(app.btn_save)

    btns.addStretch(1)

    app.btn_clear_rx = QPushButton(app._t("clear"))
    app.btn_clear_rx.setObjectName("GhostBtn")
    app.btn_clear_rx.setFixedWidth(MAIN_W)
    app.btn_clear_rx.setProperty("tr_text", "clear")
    app.btn_clear_rx.clicked.connect(app.clear_recv)
    btns.addWidget(app.btn_clear_rx)

    layout.addLayout(btns)
    return card
