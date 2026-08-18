# -*- coding: utf-8 -*-
"""BLE device picker: scan results in a dedicated window (not the sidebar)."""
import json
import time
from datetime import datetime

from PyQt5.QtCore import QEvent, QPoint, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QSizePolicy, QSlider, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from fonts import localize_qss, mono_font, ui_font
from theme import chrome_for
from dialogs import _dialog_list_qss, _set_win_titlebar_dark
from widgets import IOSSwitch
import ble_uuid

(COL_NO, COL_NAME, COL_ADDR, COL_UUID, COL_RSSI, COL_TX, COL_CONN, COL_INT,
 COL_MFR) = range(9)
_COL_WIDTHS = (52, 168, 138, 148, 88, 48, 56, 56, 160)
_CONN_YES, _CONN_NO = "●", "○"
_STALE_SEC = 8.0
_INT_MIN_S, _INT_MAX_S = 0.02, 12.0
_RSSI_SLIDER_MIN, _RSSI_SLIDER_MAX, _RSSI_SLIDER_DEFAULT = -100, -30, -84
_LAST_CONNECT_KEY = "ble_last_connect"
_LAST_CONNECT_MAX = 80
_RSSI_ON_KEY = "ble_rssi_filter_on"
_RSSI_MIN_KEY = "ble_rssi_min"
_FILT_ON_KEY = "ble_filt_on"
_FILT_RULES_KEY = "ble_filt_rules"
_FILT_RULES = (
    ("hide_empty", True),
    ("named_only", False),
    ("connectable", False),
    ("has_uuid", False),
    ("has_mfr", False),
    ("hide_stale", False),
    ("last_used", False),
)


def _last_connect_key(address):
    return ble_uuid.normalize_address(address) or str(address or "").upper()


def load_ble_last_connect(settings):
    raw = ""
    if settings is not None:
        raw = settings.value(_LAST_CONNECT_KEY, "") or ""
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, value in data.items():
        addr = _last_connect_key(key)
        if not addr:
            continue
        try:
            out[addr] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def remember_ble_connect(settings, address, when=None):
    addr = _last_connect_key(address)
    if not addr or settings is None:
        return {}
    data = load_ble_last_connect(settings)
    data[addr] = float(when if when is not None else time.time())
    if len(data) > _LAST_CONNECT_MAX:
        keep = sorted(data.items(), key=lambda kv: kv[1], reverse=True)
        data = dict(keep[:_LAST_CONNECT_MAX])
    settings.setValue(_LAST_CONNECT_KEY, json.dumps(data))
    return data


class _RssiItem(QTableWidgetItem):
    """Sort RSSI / interval by numeric UserRole, not lexicographic text."""

    def __lt__(self, other):
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole) if other is not None else None
        try:
            return int(a) < int(b)
        except (TypeError, ValueError):
            return super().__lt__(other)


class BleScanDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self._closing = False
        self._meta = {}
        self._now = time.monotonic
        self.setWindowFlags(
            Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
            | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(900, 500)
        self.resize(1020, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.btn_scan = QPushButton()
        self.btn_scan.setObjectName("BleScanStartBtn")
        self.btn_scan.setMinimumHeight(32)
        self.btn_scan.setMinimumWidth(96)
        self.btn_scan.clicked.connect(self._on_scan)
        top.addWidget(self.btn_scan)
        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("BleScanStopBtn")
        self.btn_stop.setMinimumHeight(32)
        self.btn_stop.setMinimumWidth(96)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        top.addWidget(self.btn_stop)
        self.btn_filter = QPushButton()
        self.btn_filter.setObjectName("BleFilterBtn")
        self.btn_filter.setMinimumHeight(32)
        self.btn_filter.setMinimumWidth(96)
        self.btn_filter.clicked.connect(self._show_filter_popup)
        top.addWidget(self.btn_filter)
        self.btn_rssi = QPushButton()
        self.btn_rssi.setObjectName("BleRssiBtn")
        self.btn_rssi.setMinimumHeight(32)
        self.btn_rssi.clicked.connect(self._show_rssi_popup)
        top.addWidget(self.btn_rssi)
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("MsHint")
        top.addWidget(self.lbl_status, 1)
        root.addLayout(top)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.ed_search = QLineEdit()
        self.ed_search.setObjectName("SnipSearch")
        self.ed_search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.ed_search, 1)
        root.addLayout(search_row)

        self._rssi_popup = None
        self._filter_popup = None
        self._popup_hide_from_toggle = False
        self._renumbering = False
        self._build_rssi_popup()
        self._build_filter_popup()
        self._last_connect = {}

        self.table = QTableWidget(0, 9)
        self.table.setObjectName("BleScanTable")
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionsMovable(True)
        if hasattr(hh, "setFirstSectionMovable"):
            hh.setFirstSectionMovable(False)
        hh.setMinimumSectionSize(48)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for col, width in enumerate(_COL_WIDTHS):
            hh.setSectionResizeMode(col, QHeaderView.Interactive)
            self.table.setColumnWidth(col, width)
        hh.blockSignals(True)
        hh.setSortIndicator(-1, Qt.AscendingOrder)
        hh.blockSignals(False)
        hh.sortIndicatorChanged.connect(self._on_table_sorted)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setFont(mono_font(10))
        self.table.itemDoubleClicked.connect(lambda *_: self._use_selected())
        self.table.itemSelectionChanged.connect(self._refresh_detail)

        detail = QWidget()
        dlay = QVBoxLayout(detail)
        dlay.setContentsMargins(0, 0, 0, 0)
        dlay.setSpacing(4)
        dhead = QHBoxLayout()
        dhead.setSpacing(6)
        self.lbl_detail = QLabel()
        self.lbl_detail.setObjectName("MsHint")
        dhead.addWidget(self.lbl_detail, 1)
        self.btn_copy = QPushButton()
        self.btn_copy.setObjectName("MsGhostBtn")
        self.btn_copy.setMinimumHeight(28)
        self.btn_copy.clicked.connect(self._copy_detail)
        dhead.addWidget(self.btn_copy)
        dlay.addLayout(dhead)
        self.txt_detail = QPlainTextEdit()
        self.txt_detail.setObjectName("BleAdvDetail")
        self.txt_detail.setReadOnly(True)
        self.txt_detail.setMinimumHeight(96)
        self.txt_detail.setFont(mono_font(10))
        dlay.addWidget(self.txt_detail, 1)

        self._split = QSplitter(Qt.Vertical)
        self._split.setObjectName("BleScanSplit")
        self._split.setChildrenCollapsible(False)
        self._split.setHandleWidth(8)
        self._split.addWidget(self.table)
        self._split.addWidget(detail)
        self._split.setStretchFactor(0, 1)
        self._split.setStretchFactor(1, 0)
        self._split.setSizes([400, 196])
        root.addWidget(self._split, 1)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("MsHint")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_use = QPushButton()
        self.btn_use.setObjectName("MsPrimaryBtn")
        self.btn_use.setMinimumHeight(32)
        self.btn_use.clicked.connect(self._use_selected)
        row.addWidget(self.btn_use)
        row.addStretch(1)
        self.btn_close = QPushButton()
        self.btn_close.setObjectName("MsGhostBtn")
        self.btn_close.setMinimumHeight(32)
        self.btn_close.clicked.connect(self.close)
        row.addWidget(self.btn_close)
        root.addLayout(row)

        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(1000)
        self._stale_timer.timeout.connect(self._refresh_stale)

        self._last_connect = load_ble_last_connect(
            getattr(self.app, "settings", None))
        self._restore_filter_prefs()
        self._restore_rssi_prefs()
        self.retranslate()
        self.refresh_theme()
        self.set_scanning(False)
        self._sync_filter_panel()
        self._sync_rssi_panel()
        self._refresh_detail()

    def _build_filter_popup(self):
        pop = QDialog(self, Qt.Popup)
        pop.setObjectName("BleFilterPopup")
        pop.setMinimumWidth(460)
        lay = QVBoxLayout(pop)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.lbl_filter_title = QLabel()
        self.lbl_filter_title.setObjectName("BleFilterTitle")
        self.lbl_filter_title.setFont(ui_font(14, bold=True))
        head.addWidget(self.lbl_filter_title)
        head.addStretch(1)
        self.btn_filter_close = QPushButton("×")
        self.btn_filter_close.setObjectName("BleFilterCloseBtn")
        self.btn_filter_close.setFixedSize(28, 28)
        self.btn_filter_close.clicked.connect(pop.close)
        head.addWidget(self.btn_filter_close)
        lay.addLayout(head)
        self.filter_card = QWidget()
        self.filter_card.setObjectName("BleFilterCard")
        card_lay = QVBoxLayout(self.filter_card)
        card_lay.setContentsMargins(14, 10, 14, 12)
        card_lay.setSpacing(8)
        self.filter_switch_row = QWidget()
        self.filter_switch_row.setObjectName("BleFilterSwitchRow")
        switch_lay = QHBoxLayout(self.filter_switch_row)
        switch_lay.setContentsMargins(0, 2, 0, 2)
        switch_lay.setSpacing(8)
        self.lbl_filter_enable = QLabel()
        self.lbl_filter_enable.setObjectName("BleFilterEnable")
        self.lbl_filter_enable.setFont(ui_font(11, bold=True))
        switch_lay.addWidget(self.lbl_filter_enable)
        switch_lay.addStretch(1)
        self.sw_filter = IOSSwitch(True)
        self.sw_filter.toggled.connect(self._on_filter_toggled)
        switch_lay.addWidget(self.sw_filter)
        card_lay.addWidget(self.filter_switch_row)
        self._filter_divider = QFrame()
        self._filter_divider.setObjectName("BleFilterDivider")
        self._filter_divider.setFrameShape(QFrame.NoFrame)
        self._filter_divider.setFixedHeight(1)
        card_lay.addWidget(self._filter_divider)
        self.filter_rules_panel = QWidget()
        self.filter_rules_panel.setObjectName("BleFilterRulesPanel")
        rules_lay = QVBoxLayout(self.filter_rules_panel)
        rules_lay.setContentsMargins(0, 0, 0, 0)
        rules_lay.setSpacing(8)
        self.lbl_filt_rules = QLabel()
        self.lbl_filt_rules.setObjectName("BleFiltHint")
        self.lbl_filt_rules.setFont(ui_font(10))
        rules_lay.addWidget(self.lbl_filt_rules)
        self._filt_grid = QGridLayout()
        self._filt_grid.setContentsMargins(0, 2, 0, 0)
        self._filt_grid.setHorizontalSpacing(20)
        self._filt_grid.setVerticalSpacing(10)
        self._filt_grid.setColumnStretch(0, 1)
        self._filt_grid.setColumnStretch(1, 1)
        self.chk_filt = {}
        for i, (key, default) in enumerate(_FILT_RULES):
            chk = QCheckBox()
            chk.setObjectName("BleFiltChk")
            chk.setChecked(bool(default))
            chk.setFont(ui_font(10))
            chk.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            chk.toggled.connect(self._on_filter_rule_toggled)
            self.chk_filt[key] = chk
            self._filt_grid.addWidget(chk, i // 2, i % 2)
        rules_lay.addLayout(self._filt_grid)
        card_lay.addWidget(self.filter_rules_panel)
        lay.addWidget(self.filter_card)
        pop._suppress_reopen = False
        pop.installEventFilter(self)
        self._filter_popup = pop

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Hide
                and obj in (self._filter_popup, self._rssi_popup)
                and not self._popup_hide_from_toggle):
            obj._suppress_reopen = True
            QTimer.singleShot(0, lambda: self._clear_popup_suppress(obj))
        return super().eventFilter(obj, event)

    def _clear_popup_suppress(self, pop):
        if pop is None:
            return
        try:
            pop.objectName()
        except RuntimeError:
            return
        if QApplication.mouseButtons() != Qt.NoButton:
            QTimer.singleShot(30, lambda: self._clear_popup_suppress(pop))
            return
        pop._suppress_reopen = False

    def _toggle_popup_below(self, anchor, pop, prepare):
        if pop is None:
            return
        if pop.isVisible():
            self._popup_hide_from_toggle = True
            pop.hide()
            self._popup_hide_from_toggle = False
            return
        if getattr(pop, "_suppress_reopen", False):
            pop._suppress_reopen = False
            return
        other = (self._rssi_popup if pop is self._filter_popup
                 else self._filter_popup)
        if other is not None and other.isVisible():
            self._popup_hide_from_toggle = True
            other.hide()
            self._popup_hide_from_toggle = False
        prepare()
        self._show_popup_below(anchor, pop)

    def _show_popup_below(self, anchor, pop):
        pop.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = QApplication.desktop().availableGeometry(anchor)
        x = max(screen.left(), min(pos.x(), screen.right() - pop.width() + 1))
        y = pos.y()
        if y + pop.height() > screen.bottom() + 1:
            y = anchor.mapToGlobal(QPoint(0, -pop.height() - 4)).y()
        pop.move(x, max(screen.top(), y))
        pop.show()

    def _show_filter_popup(self):
        self._toggle_popup_below(
            self.btn_filter, self._filter_popup,
            lambda: (self._sync_filter_panel(),
                     self._refresh_filter_popup_theme()))

    def _build_rssi_popup(self):
        pop = QDialog(self, Qt.Popup)
        pop.setObjectName("BleRssiPopup")
        pop.setMinimumWidth(380)
        lay = QVBoxLayout(pop)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(12)
        head = QHBoxLayout()
        self.lbl_rssi_title = QLabel()
        self.lbl_rssi_title.setObjectName("BleRssiTitle")
        self.lbl_rssi_title.setFont(ui_font(14, bold=True))
        head.addWidget(self.lbl_rssi_title)
        head.addStretch(1)
        self.btn_rssi_close = QPushButton("×")
        self.btn_rssi_close.setObjectName("BleRssiCloseBtn")
        self.btn_rssi_close.setFixedSize(28, 28)
        self.btn_rssi_close.clicked.connect(pop.close)
        head.addWidget(self.btn_rssi_close)
        lay.addLayout(head)
        self.rssi_switch_row = QWidget()
        self.rssi_switch_row.setObjectName("BleRssiSwitchRow")
        switch_lay = QHBoxLayout(self.rssi_switch_row)
        switch_lay.setContentsMargins(14, 10, 14, 10)
        self.lbl_rssi_filter = QLabel()
        self.lbl_rssi_filter.setObjectName("BleRssiFilter")
        self.lbl_rssi_filter.setFont(ui_font(11, bold=True))
        switch_lay.addWidget(self.lbl_rssi_filter)
        switch_lay.addStretch(1)
        self.sw_rssi = IOSSwitch(False)
        self.sw_rssi.setLayoutDirection(Qt.LeftToRight)
        self.sw_rssi.toggled.connect(self._on_rssi_filter_toggled)
        switch_lay.addWidget(self.sw_rssi)
        lay.addWidget(self.rssi_switch_row)
        self.rssi_panel = QWidget()
        self.rssi_panel.setObjectName("BleRssiPanel")
        panel_lay = QVBoxLayout(self.rssi_panel)
        panel_lay.setContentsMargins(14, 12, 14, 14)
        panel_lay.setSpacing(8)
        self.lbl_rssi_threshold = QLabel()
        self.lbl_rssi_threshold.setObjectName("BleRssiThreshold")
        self.lbl_rssi_threshold.setFont(ui_font(10))
        panel_lay.addWidget(self.lbl_rssi_threshold)
        value_row = QHBoxLayout()
        self.lbl_rssi_cur = QLabel()
        self.lbl_rssi_cur.setObjectName("BleRssiValue")
        self.lbl_rssi_cur.setFont(ui_font(22, bold=True))
        value_row.addWidget(self.lbl_rssi_cur)
        value_row.addStretch(1)
        panel_lay.addLayout(value_row)
        self.sl_rssi = QSlider(Qt.Horizontal)
        self.sl_rssi.setObjectName("BleRssiSlider")
        self.sl_rssi.setRange(_RSSI_SLIDER_MIN, _RSSI_SLIDER_MAX)
        self.sl_rssi.setValue(_RSSI_SLIDER_DEFAULT)
        self.sl_rssi.setPageStep(5)
        self.sl_rssi.setSingleStep(1)
        self.sl_rssi.setMinimumWidth(320)
        self.sl_rssi.setMaximumHeight(24)
        self.sl_rssi.valueChanged.connect(self._on_rssi_slider)
        panel_lay.addWidget(self.sl_rssi)
        bounds = QHBoxLayout()
        self.lbl_rssi_lo = QLabel("%d dBm" % _RSSI_SLIDER_MIN)
        self.lbl_rssi_lo.setObjectName("BleRssiBound")
        self.lbl_rssi_lo.setFont(ui_font(10))
        self.lbl_rssi_hi = QLabel("%d dBm" % _RSSI_SLIDER_MAX)
        self.lbl_rssi_hi.setObjectName("BleRssiBound")
        self.lbl_rssi_hi.setFont(ui_font(10))
        bounds.addWidget(self.lbl_rssi_lo)
        bounds.addStretch(1)
        bounds.addWidget(self.lbl_rssi_hi)
        panel_lay.addLayout(bounds)
        lay.addWidget(self.rssi_panel)
        self.lbl_rssi_hint = QLabel()
        self.lbl_rssi_hint.setObjectName("BleRssiHint")
        self.lbl_rssi_hint.setWordWrap(True)
        self.lbl_rssi_hint.setFont(ui_font(10))
        lay.addWidget(self.lbl_rssi_hint)
        pop._suppress_reopen = False
        pop.installEventFilter(self)
        self._rssi_popup = pop

    def _show_rssi_popup(self):
        self._toggle_popup_below(
            self.btn_rssi, self._rssi_popup,
            lambda: (self._sync_rssi_panel(),
                     self._refresh_rssi_popup_theme()))

    def _refresh_filter_popup_theme(self):
        if self._filter_popup is None:
            return
        c = chrome_for(self.app.cb_theme.currentData() if hasattr(
            self.app, "cb_theme") else None)
        self._filter_popup.setStyleSheet(localize_qss("""
            QDialog#BleFilterPopup {{
                background-color: {card}; border: 1px solid {sep}; border-radius: 12px;
            }}
            QLabel#BleFilterTitle, QLabel#BleFilterEnable {{ color: {txt}; }}
            QWidget#BleFilterCard {{
                background-color: {inp}; border-radius: 10px;
            }}
            QFrame#BleFilterDivider {{ background-color: {sep}; border: none; }}
            QLabel#BleFiltHint {{ color: {sec}; }}
            QCheckBox#BleFiltChk {{ color: {txt}; spacing: 8px; }}
            QPushButton#BleFilterCloseBtn {{
                background: transparent; color: {txt}; border: none; font-size: 28px;
            }}
            QPushButton#BleFilterCloseBtn:hover {{ background: {ghost}; border-radius: 14px; }}
        """.format(card=c["card_bg"], sep=c["separator"], txt=c["text"],
                   inp=c["input_bg"], sec=c["text_sec"], ghost=c["ghost_hover"])))
        self.sw_filter.set_theme_colors(c["separator"], "#FFFFFF")

    def _refresh_rssi_popup_theme(self):
        if self._rssi_popup is None:
            return
        c = chrome_for(self.app.cb_theme.currentData() if hasattr(
            self.app, "cb_theme") else None)
        self._rssi_popup.setStyleSheet(localize_qss("""
            QDialog#BleRssiPopup {{
                background-color: {card}; border: 1px solid {sep}; border-radius: 12px;
            }}
            QLabel#BleRssiTitle, QLabel#BleRssiFilter {{ color: {txt}; }}
            QWidget#BleRssiSwitchRow, QWidget#BleRssiPanel {{
                background-color: {inp}; border-radius: 10px;
            }}
            QLabel#BleRssiThreshold, QLabel#BleRssiBound, QLabel#BleRssiHint {{
                color: {sec};
            }}
            QLabel#BleRssiValue {{ color: {acc}; }}
            QPushButton#BleRssiCloseBtn {{
                background: transparent; color: {txt}; border: none; font-size: 28px;
            }}
            QPushButton#BleRssiCloseBtn:hover {{ background: {ghost}; border-radius: 14px; }}
            QSlider#BleRssiSlider::groove:horizontal {{
                height: 5px; background: {sep}; border-radius: 2px;
            }}
            QSlider#BleRssiSlider::sub-page:horizontal {{
                background: {acc}; border-radius: 2px;
            }}
            QSlider#BleRssiSlider::handle:horizontal {{
                width: 16px; height: 16px; margin: -6px 0;
                background: {card}; border: 2px solid {acc}; border-radius: 8px;
            }}
        """.format(card=c["card_bg"], sep=c["separator"], txt=c["text"],
                   inp=c["input_bg"], sec=c["text_sec"], acc=c["accent"],
                   ghost=c["ghost_hover"])))
        self.sw_rssi.set_theme_colors(c["separator"], "#FFFFFF")

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("ble_scan_title"))
        self.btn_scan.setText(t("ble_scan_go"))
        self.btn_stop.setText(t("ble_scan_halt"))
        self.btn_use.setText(t("ble_scan_use"))
        self.btn_close.setText(t("cancel"))
        self.ed_search.setPlaceholderText(t("ble_scan_search_ph"))
        self.btn_filter.setText(t("ble_scan_filter"))
        self.btn_filter.setToolTip(t("ble_scan_filter_tip"))
        self.lbl_filter_title.setText(t("ble_scan_filter"))
        self.lbl_filter_enable.setText(t("ble_filt_enable"))
        self.btn_rssi.setText(t("ble_scan_rssi_filter"))
        self.lbl_filt_rules.setText(t("ble_filt_rules"))
        for key, _default in _FILT_RULES:
            self.chk_filt[key].setText(t("ble_filt_" + key))
        self.lbl_hint.setText(t("ble_scan_hint"))
        self.lbl_detail.setText(t("ble_scan_detail"))
        self.btn_copy.setText(t("ble_scan_copy"))
        self.lbl_rssi_title.setText(t("ble_scan_rssi_filter"))
        self.lbl_rssi_filter.setText(t("ble_scan_rssi_filter"))
        self.lbl_rssi_threshold.setText(t("ble_scan_rssi_threshold"))
        self._refresh_rssi_labels()
        self.table.setHorizontalHeaderLabels([
            t("ble_col_no"), t("ble_col_name"), t("ble_col_addr"),
            t("ble_col_uuid"), t("ble_col_rssi"), t("ble_col_tx"),
            t("ble_col_conn"), t("ble_col_int"), t("ble_col_mfr")])
        scanning = bool(
            getattr(getattr(self.app, "_ble_scanner", None), "is_scanning", False))
        self.set_scanning(scanning)
        self._refresh_row_tooltips()
        self._refresh_detail()

    def refresh_theme(self):
        tid = self.app.cb_theme.currentData() if hasattr(self.app, "cb_theme") else None
        c = chrome_for(tid)
        qss = _dialog_list_qss(c) + """
        QLabel#MsHint {{ color: {sec}; font-size: 11px; }}
        QLineEdit#SnipSearch {{
            background-color: {inp}; border: 1px solid {sep};
            border-radius: 6px; padding: 6px 10px; color: {txt};
            font-family: 'Segoe UI'; font-size: 12px;
        }}
        QLineEdit#SnipSearch:focus {{
            border: 1px solid {acc}; background-color: {focus};
        }}
        QWidget#BleRssiPanel {{
            background: transparent;
        }}
        QLabel#BleRssiBound {{
            color: {sec}; font-family: 'Segoe UI'; font-size: 10pt;
        }}
        QLabel#BleRssiValue {{
            color: {acc}; font-family: 'Segoe UI'; font-size: 10pt; font-weight: 600;
        }}
        QSlider#BleRssiSlider::groove:horizontal {{
            height: 4px; background: {sep}; border-radius: 2px;
        }}
        QSlider#BleRssiSlider::sub-page:horizontal {{
            background: {acc}; border-radius: 2px;
        }}
        QSlider#BleRssiSlider::handle:horizontal {{
            width: 14px; height: 14px; margin: -6px 0;
            background: {acc}; border-radius: 7px;
        }}
        QSplitter#BleScanSplit::handle:vertical {{
            height: 8px; background: transparent;
        }}
        QSplitter#BleScanSplit::handle:vertical:hover {{
            background: {acc};
        }}
        QTableWidget#BleScanTable {{
            background-color: {card}; color: {txt};
            border: 1px solid {sep}; border-radius: 8px; padding: 2px;
            gridline-color: transparent; outline: 0px;
            alternate-background-color: {alt};
        }}
        QTableWidget#BleScanTable::item {{ padding: 4px 8px; }}
        QTableWidget#BleScanTable::item:selected {{
            background-color: {acc}; color: #FFFFFF;
        }}
        QHeaderView::section {{
            background-color: {card}; color: {sec};
            border: 0px; border-bottom: 1px solid {sep};
            border-right: 1px solid {sep};
            padding: 6px 8px; font-family: 'Segoe UI'; font-size: 11px;
        }}
        QPlainTextEdit#BleAdvDetail {{
            background-color: {inp}; color: {txt};
            border: 1px solid {sep}; border-radius: 8px; padding: 6px 8px;
        }}
        QLabel#MsHint[scanning="true"] {{ color: {acc}; font-weight: 600; }}
        QPushButton#BleScanStartBtn {{
            background-color: {acc}; color: #FFFFFF; border: none;
            border-radius: 8px; padding: 6px 16px; font-weight: 600;
        }}
        QPushButton#BleScanStartBtn:hover {{ background-color: {acc_h}; }}
        QPushButton#BleScanStartBtn:pressed {{ background-color: {acc_p}; }}
        QPushButton#BleScanStartBtn:disabled {{ background-color: {sep}; color: {sec}; }}
        QPushButton#BleScanStopBtn {{
            background-color: {danger}; color: #FFFFFF; border: none;
            border-radius: 8px; padding: 6px 16px; font-weight: 600;
        }}
        QPushButton#BleScanStopBtn:hover {{ background-color: {danger_h}; }}
        QPushButton#BleScanStopBtn:disabled {{
            background-color: {card}; color: {sec}; border: 1px solid {sep};
        }}
        QPushButton#BleFilterBtn {{
            background-color: {card}; color: {txt};
            border: 1px solid {sep}; border-radius: 8px;
            padding: 6px 16px; font-weight: 600;
        }}
        QPushButton#BleFilterBtn:hover {{ background-color: {ghost_h}; }}
        QPushButton#BleFilterBtn[active="true"] {{
            background-color: {acc}; color: #FFFFFF; border: none;
        }}
        QPushButton#BleFilterBtn[active="true"]:hover {{ background-color: {acc_h}; }}
        QPushButton#BleRssiBtn {{
            background-color: {card}; color: {txt}; border: 1px solid {sep};
            border-radius: 8px; padding: 6px 12px; font-weight: 600;
        }}
        QPushButton#BleRssiBtn:hover {{ background-color: {ghost_h}; }}
        QPushButton#BleRssiBtn[active="true"] {{
            background-color: {acc}; color: #FFFFFF; border: none;
        }}
        QPushButton#BleRssiBtn[active="true"]:hover {{ background-color: {acc_h}; }}
        QPushButton#MsPrimaryBtn {{
            background-color: {acc}; color: #FFFFFF; border: none;
            border-radius: 8px; padding: 6px 14px; font-weight: 600;
        }}
        QPushButton#MsPrimaryBtn:hover {{ background-color: {acc_h}; }}
        QPushButton#MsPrimaryBtn:pressed {{ background-color: {acc_p}; }}
        QPushButton#MsPrimaryBtn:disabled {{ background-color: {sep}; color: {sec}; }}
        QPushButton#MsGhostBtn {{
            background-color: {card}; color: {txt};
            border: 1px solid {sep}; border-radius: 8px; padding: 6px 14px;
        }}
        QPushButton#MsGhostBtn:hover {{ background-color: {ghost_h}; }}
        QPushButton#MsGhostBtn:disabled {{ color: {sec}; }}
        """.format(
            sec=c["text_sec"], inp=c["input_bg"], sep=c["separator"],
            txt=c["text"], acc=c["accent"], acc_h=c["accent_hover"],
            acc_p=c["accent_pressed"], focus=c["input_focus_bg"],
            card=c["card_bg"], danger=c["danger"],
            danger_h=c["danger_hover"], ghost_h=c["ghost_hover"],
            alt=c.get("window_bg") or c["card_bg"],
        )
        self.setStyleSheet(localize_qss(qss))
        _set_win_titlebar_dark(self, c.get("mode") == "dark")
        self._refresh_filter_popup_theme()
        self._refresh_rssi_popup_theme()
        self._refresh_stale()
        self._repaint_rows()

    def clear_devices(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self._meta.clear()
        self._apply_filter()
        self._refresh_detail()

    def _no_item(self, n):
        item = _RssiItem(str(n))
        item.setData(Qt.UserRole, int(n))
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _on_table_sorted(self, logical, _order):
        if self._renumbering or logical < 0:
            return
        if logical == COL_NO:
            hh = self.table.horizontalHeader()
            hh.blockSignals(True)
            hh.setSortIndicator(-1, Qt.AscendingOrder)
            hh.blockSignals(False)
        # Real header clicks emit this before the model is reordered.
        QTimer.singleShot(0, self._renumber_rows)

    def _renumber_rows(self):
        if getattr(self, "_renumbering", False):
            return
        self._renumbering = True
        try:
            n = 1
            for r in range(self.table.rowCount()):
                if self.table.isRowHidden(r):
                    continue
                item = self.table.item(r, COL_NO)
                if item is None:
                    self.table.setItem(r, COL_NO, self._no_item(n))
                else:
                    if item.text() != str(n):
                        item.setText(str(n))
                    item.setData(Qt.UserRole, n)
                n += 1
        finally:
            self._renumbering = False

    def _uuid_item(self, uuids):
        empty = self.app._t("ble_uuid_none")
        text = ble_uuid.format_adv_uuids(uuids, empty=empty)
        item = QTableWidgetItem(text)
        merged = ble_uuid.merge_uuid_lists(uuids)
        item.setData(Qt.UserRole, merged)
        tip = ble_uuid.format_adv_uuids_full(merged)
        item.setToolTip(tip or text)
        return item

    def _tx_item(self, snap):
        tx = (snap or {}).get("tx_power")
        if tx is None:
            text, role = "", -999
        else:
            try:
                role = int(tx)
                text = "%+d" % role
            except (TypeError, ValueError):
                text, role = "", -999
        item = _RssiItem(text)
        item.setData(Qt.UserRole, role)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def _conn_item(self, snap):
        flag = (snap or {}).get("connectable")
        if flag is True:
            text, role = _CONN_YES, 1
        elif flag is False:
            text, role = _CONN_NO, 0
        else:
            text, role = self.app._t("ble_uuid_none"), -1
        item = _RssiItem(text)
        item.setData(Qt.UserRole, role)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _int_item(self, interval_ms):
        empty = self.app._t("ble_uuid_none")
        if interval_ms is None:
            text, role = empty, -1
        else:
            try:
                role = int(round(float(interval_ms)))
                text = str(role)
            except (TypeError, ValueError):
                text, role = empty, -1
        item = _RssiItem(text)
        item.setData(Qt.UserRole, role)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def _mfr_item(self, snap):
        empty = self.app._t("ble_uuid_none")
        text = ble_uuid.format_mfr_preview(snap, empty=empty)
        item = QTableWidgetItem(text)
        item.setData(Qt.UserRole, dict(snap or {}))
        return item

    def _row_tooltip(self, rssi, uuids, snap, interval_ms=None, addr=""):
        t = self.app._t
        empty = t("ble_uuid_none")
        snap = snap or {}
        lines = []
        if rssi is not None and rssi != -999:
            lines.append(t("ble_adv_rssi", n=rssi))
        if snap.get("tx_power") is not None:
            lines.append(t("ble_adv_tx", n=snap["tx_power"]))
        conn = snap.get("connectable")
        if conn is True:
            lines.append(t("ble_adv_conn_yes"))
        elif conn is False:
            lines.append(t("ble_adv_conn_no"))
        kind = snap.get("advertisement_type") or ""
        if kind:
            lines.append(t("ble_adv_type", kind=kind))
        if interval_ms is not None:
            try:
                lines.append(t("ble_adv_interval", n=int(round(float(interval_ms)))))
            except (TypeError, ValueError):
                pass
        if snap.get("flags") is not None:
            keys = ble_uuid.adv_flag_keys(snap["flags"])
            bits = ", ".join(t("ble_flag_" + k) for k in keys) or empty
            lines.append(t("ble_adv_flags", bits=bits, n="%02X" % int(snap["flags"])))
        if snap.get("appearance") is not None:
            lines.append(t(
                "ble_adv_appearance",
                label=ble_uuid.appearance_label(snap["appearance"])))
        lines.append(t("ble_adv_svc_n", n=len(ble_uuid.merge_uuid_lists(uuids))))
        uuid_full = ble_uuid.format_adv_uuids_full(uuids)
        if uuid_full:
            lines.append(t("ble_adv_uuids"))
            lines.append(uuid_full)
        when = self._format_last_connect(addr)
        if when:
            lines.append(t("ble_adv_last_connect", when=when))
        mfr_lines = []
        for cid, hx in snap.get("manufacturer") or []:
            body = ble_uuid.format_hex_spaced(hx) or empty
            mfr_lines.append("%s  %s" % (ble_uuid.format_company(cid), body))
        if mfr_lines:
            lines.append(t("ble_adv_mfr"))
            lines.extend(mfr_lines)
        svc_lines = []
        for uid, hx in snap.get("service_data") or []:
            label = ble_uuid.short_uuid(uid) or uid
            body = ble_uuid.format_hex_spaced(hx) or empty
            svc_lines.append("%s  %s" % (label, body))
        if svc_lines:
            lines.append(t("ble_adv_svc_data"))
            lines.extend(svc_lines)
        raw, rebuilt = ble_uuid.format_raw_hex(snap, uuids)
        if raw:
            lines.append(t("ble_adv_raw_rebuilt" if rebuilt else "ble_adv_raw"))
            lines.append(raw)
        return "\n".join(lines)

    def _refresh_row_tooltips(self):
        for r in range(self.table.rowCount()):
            rssi_item = self.table.item(r, COL_RSSI)
            uuid_item = self.table.item(r, COL_UUID)
            int_item = self.table.item(r, COL_INT)
            try:
                rssi_n = int(rssi_item.data(Qt.UserRole)) if rssi_item else -999
            except (TypeError, ValueError):
                rssi_n = -999
            uuids = list(uuid_item.data(Qt.UserRole) or []) if uuid_item else []
            interval = None
            if int_item is not None:
                try:
                    interval = int(int_item.data(Qt.UserRole))
                except (TypeError, ValueError):
                    interval = None
            self._apply_row_tooltip(r, rssi_n, uuids, self._row_snap(r), interval)

    def _apply_row_tooltip(self, row, rssi_n, uuids, snap, interval_ms=None):
        addr_item = self.table.item(row, COL_ADDR)
        addr = addr_item.text() if addr_item is not None else ""
        tip = self._row_tooltip(rssi_n, uuids, snap, interval_ms, addr)
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is not None:
                item.setToolTip(tip)

    def _touch_meta(self, addr):
        # Local discovery cadence (EWMA of callback gaps), not the peripheral
        # Advertising Interval from the packet.
        now = self._now()
        meta = self._meta.get(addr) or {}
        prev_seen = meta.get("seen")
        interval = meta.get("interval")
        if prev_seen is not None:
            dt = now - prev_seen
            if _INT_MIN_S <= dt <= _INT_MAX_S:
                ms = dt * 1000.0
                interval = ms if interval is None else (0.4 * ms + 0.6 * interval)
        self._meta[addr] = {"seen": now, "interval": interval, "stale": False}
        return interval

    def upsert(self, address, name, rssi, uuids=None, adv=None):
        addr = str(address or "").upper()
        if not addr:
            return
        self.table.setSortingEnabled(False)
        r = -1
        for i in range(self.table.rowCount()):
            item = self.table.item(i, COL_ADDR)
            if item is not None and item.text() == addr:
                r = i
                break
        clean = ble_uuid.sanitize_ble_name(name)
        if r >= 0:
            name_item = self.table.item(r, COL_NAME)
            prev = ""
            if name_item is not None:
                prev = name_item.data(Qt.UserRole) or ""
            if not clean:
                clean = ble_uuid.sanitize_ble_name(prev)
        unnamed = self.app._t("ble_unnamed")
        label = clean or unnamed
        keep_rssi = False
        if rssi is None and r >= 0:
            rssi_item = self.table.item(r, COL_RSSI)
            if rssi_item is not None:
                keep_rssi = True
                rssi_s = rssi_item.text()
                try:
                    rssi_n = int(rssi_item.data(Qt.UserRole))
                except (TypeError, ValueError):
                    rssi_n = -999
        if not keep_rssi:
            try:
                rssi_n = int(rssi) if rssi is not None else -999
            except (TypeError, ValueError):
                rssi_n = -999
            rssi_s = (
                "" if rssi is None else ble_uuid.format_rssi_cell(rssi_n, empty=""))
        old_uuids = []
        old_snap = {}
        if r >= 0:
            uuid_item = self.table.item(r, COL_UUID)
            if uuid_item is not None:
                old_uuids = list(uuid_item.data(Qt.UserRole) or [])
            mfr_item = self.table.item(r, COL_MFR)
            if mfr_item is not None:
                old_snap = dict(mfr_item.data(Qt.UserRole) or {})
        merged_uuids = ble_uuid.merge_uuid_lists(
            old_uuids, None if uuids is None else uuids)
        snap = ble_uuid.merge_adv_snapshots(old_snap, adv)
        if not clean:
            clean = ble_uuid.adv_local_name(None, None, snap)
            label = clean or unnamed
        interval_ms = self._touch_meta(addr)
        if r >= 0:
            name_item = self.table.item(r, COL_NAME)
            rssi_item = self.table.item(r, COL_RSSI)
            if name_item is not None:
                name_item.setText(label)
                name_item.setData(Qt.UserRole, clean)
            if rssi_item is not None and not keep_rssi:
                rssi_item.setText(rssi_s)
                rssi_item.setData(Qt.UserRole, rssi_n)
            self.table.setItem(r, COL_UUID, self._uuid_item(merged_uuids))
            self.table.setItem(r, COL_TX, self._tx_item(snap))
            self.table.setItem(r, COL_CONN, self._conn_item(snap))
            self.table.setItem(r, COL_INT, self._int_item(interval_ms))
            self.table.setItem(r, COL_MFR, self._mfr_item(snap))
        else:
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(label)
            name_item.setData(Qt.UserRole, clean)
            addr_item = QTableWidgetItem(addr)
            rssi_item = _RssiItem(rssi_s)
            rssi_item.setData(Qt.UserRole, rssi_n)
            rssi_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, COL_NO, self._no_item(r + 1))
            self.table.setItem(r, COL_NAME, name_item)
            self.table.setItem(r, COL_ADDR, addr_item)
            self.table.setItem(r, COL_UUID, self._uuid_item(merged_uuids))
            self.table.setItem(r, COL_RSSI, rssi_item)
            self.table.setItem(r, COL_TX, self._tx_item(snap))
            self.table.setItem(r, COL_CONN, self._conn_item(snap))
            self.table.setItem(r, COL_INT, self._int_item(interval_ms))
            self.table.setItem(r, COL_MFR, self._mfr_item(snap))
        self._paint_row(r, False)
        self._apply_row_tooltip(r, rssi_n, merged_uuids, snap, interval_ms)
        self.table.setSortingEnabled(True)
        self._apply_filter()
        if self._selected_addr() == addr:
            self._refresh_detail()

    def _visible_count(self):
        return sum(
            1 for i in range(self.table.rowCount())
            if not self.table.isRowHidden(i))

    def set_scanning(self, on):
        n = self.table.rowCount()
        shown = self._visible_count()
        if shown < n:
            key = "ble_scan_status_on_filt" if on else "ble_scan_status_off_filt"
            text = self.app._t(key, n=n, shown=shown)
        elif on:
            text = self.app._t("ble_scan_status_on", n=n)
        else:
            text = self.app._t("ble_scan_status_off", n=n)
        scanning_prop = "true" if on else "false"
        same = (
            self.btn_scan.isEnabled() == (not on)
            and self.btn_stop.isEnabled() == bool(on)
            and self.lbl_status.property("scanning") == scanning_prop
            and self.lbl_status.text() == text)
        self.btn_scan.setEnabled(not on)
        self.btn_stop.setEnabled(bool(on))
        self.lbl_status.setProperty("scanning", scanning_prop)
        self.lbl_status.setText(text)
        if same:
            return
        for w in (self.btn_scan, self.btn_stop, self.lbl_status):
            sty = w.style()
            sty.unpolish(w)
            sty.polish(w)
            w.update()

    def _row_named(self, row):
        item = self.table.item(row, COL_NAME)
        if item is None:
            return False
        return bool(item.data(Qt.UserRole) or "")

    def _row_snap(self, row):
        mfr = self.table.item(row, COL_MFR)
        return dict(mfr.data(Qt.UserRole) or {}) if mfr is not None else {}

    def _row_has_adv_payload(self, row):
        uuid = self.table.item(row, COL_UUID)
        if uuid is not None and (uuid.data(Qt.UserRole) or []):
            return True
        snap = self._row_snap(row)
        if snap.get("manufacturer") or snap.get("service_data"):
            return True
        if snap.get("local_name"):
            return True
        return False

    def _row_connectable(self, row):
        item = self.table.item(row, COL_CONN)
        try:
            return int(item.data(Qt.UserRole)) == 1
        except (TypeError, ValueError, AttributeError):
            return False

    def _row_stale(self, row):
        addr_item = self.table.item(row, COL_ADDR)
        addr = addr_item.text() if addr_item is not None else ""
        return bool((self._meta.get(addr) or {}).get("stale"))

    def _row_last_used(self, row):
        addr_item = self.table.item(row, COL_ADDR)
        addr = addr_item.text() if addr_item is not None else ""
        return bool(self._last_connect.get(_last_connect_key(addr)))

    def _row_blocked_by_rules(self, row, snap=None):
        named = self._row_named(row)
        if self._filt("named_only") and not named:
            return True
        if self._filt("hide_empty") and not named and not self._row_has_adv_payload(row):
            return True
        if self._filt("connectable") and not self._row_connectable(row):
            return True
        if self._filt("has_uuid"):
            uuid = self.table.item(row, COL_UUID)
            if not (uuid is not None and (uuid.data(Qt.UserRole) or [])):
                return True
        if self._filt("has_mfr"):
            if snap is None:
                snap = self._row_snap(row)
            if not (snap.get("manufacturer") or []):
                return True
        if self._filt("hide_stale") and self._row_stale(row):
            return True
        if self._filt("last_used") and not self._row_last_used(row):
            return True
        return False

    def _on_filter_toggled(self, _on=False):
        self._sync_filter_panel()
        self._save_filter_prefs()
        self._apply_filter()

    def _on_filter_rule_toggled(self, _on=False):
        self._save_filter_prefs()
        self._apply_filter()

    def _sync_filter_panel(self):
        on = bool(self.sw_filter.isChecked())
        self.btn_filter.setProperty("active", on)
        self.btn_filter.style().unpolish(self.btn_filter)
        self.btn_filter.style().polish(self.btn_filter)
        self.btn_filter.update()
        self.filter_rules_panel.setEnabled(on)
        self._sync_rssi_panel()

    def _filt(self, key):
        chk = self.chk_filt.get(key)
        return bool(chk.isChecked()) if chk is not None else False

    def _restore_filter_prefs(self):
        settings = getattr(self.app, "settings", None)
        rules = {key: bool(default) for key, default in _FILT_RULES}
        on = True
        if settings is not None:
            raw_on = settings.value(_FILT_ON_KEY, True)
            if isinstance(raw_on, str):
                on = raw_on.strip().lower() not in ("0", "false", "no")
            else:
                on = bool(raw_on)
            raw = settings.value(_FILT_RULES_KEY, "") or ""
            try:
                data = json.loads(raw) if raw else {}
            except (TypeError, ValueError):
                data = {}
            if isinstance(data, dict):
                for key, default in _FILT_RULES:
                    if key not in data:
                        continue
                    val = data[key]
                    if isinstance(val, str):
                        rules[key] = val.strip().lower() in ("1", "true", "yes")
                    else:
                        rules[key] = bool(val)
        self.sw_filter.blockSignals(True)
        self.sw_filter.setChecked(on, animate=False)
        self.sw_filter.blockSignals(False)
        for key, chk in self.chk_filt.items():
            chk.blockSignals(True)
            chk.setChecked(bool(rules.get(key)))
            chk.blockSignals(False)

    def _save_filter_prefs(self):
        settings = getattr(self.app, "settings", None)
        if settings is None:
            return
        settings.setValue(_FILT_ON_KEY, bool(self.sw_filter.isChecked()))
        data = {key: bool(self.chk_filt[key].isChecked()) for key, _d in _FILT_RULES}
        settings.setValue(_FILT_RULES_KEY, json.dumps(data))

    def _restore_rssi_prefs(self):
        settings = getattr(self.app, "settings", None)
        on, value = False, _RSSI_SLIDER_DEFAULT
        if settings is not None:
            raw_on = settings.value(_RSSI_ON_KEY, False)
            if isinstance(raw_on, str):
                on = raw_on.strip().lower() in ("1", "true", "yes")
            else:
                on = bool(raw_on)
            try:
                value = int(settings.value(_RSSI_MIN_KEY, _RSSI_SLIDER_DEFAULT))
            except (TypeError, ValueError):
                value = _RSSI_SLIDER_DEFAULT
        value = max(_RSSI_SLIDER_MIN, min(_RSSI_SLIDER_MAX, value))
        self.sw_rssi.blockSignals(True)
        self.sl_rssi.blockSignals(True)
        self.sw_rssi.setChecked(on, animate=False)
        self.sl_rssi.setValue(value)
        self.sw_rssi.blockSignals(False)
        self.sl_rssi.blockSignals(False)

    def _save_rssi_prefs(self):
        settings = getattr(self.app, "settings", None)
        if settings is None:
            return
        settings.setValue(_RSSI_ON_KEY, bool(self.sw_rssi.isChecked()))
        settings.setValue(_RSSI_MIN_KEY, int(self.sl_rssi.value()))

    def _sync_rssi_panel(self):
        enabled = bool(self.sw_filter.isChecked())
        on = bool(enabled and self.sw_rssi.isChecked())
        self.btn_rssi.setProperty("active", on)
        self.btn_rssi.style().unpolish(self.btn_rssi)
        self.btn_rssi.style().polish(self.btn_rssi)
        self.btn_rssi.update()
        self.sw_rssi.setEnabled(enabled)
        self.rssi_panel.setEnabled(on)
        self._refresh_rssi_labels()

    def _refresh_rssi_labels(self):
        n = int(self.sl_rssi.value())
        bars = ble_uuid.rssi_bars(n).rstrip()
        if bars:
            self.lbl_rssi_cur.setText("%s  %d dBm" % (bars, n))
        else:
            self.lbl_rssi_cur.setText("%d dBm" % n)
        tip = self.app._t("ble_scan_rssi_hint", n=n)
        self.lbl_rssi_hint.setText(tip)
        for w in (self.btn_rssi, self.sw_rssi, self.sl_rssi,
                  self.lbl_rssi_cur, self.lbl_rssi_filter):
            w.setToolTip(tip)

    def _on_rssi_filter_toggled(self, _on=False):
        self._sync_rssi_panel()
        self._save_rssi_prefs()
        self._apply_filter()

    def _on_rssi_slider(self, _value=0):
        self._refresh_rssi_labels()
        self._save_rssi_prefs()
        self._apply_filter()

    def _rssi_min(self):
        if not self.sw_rssi.isChecked():
            return None
        return int(self.sl_rssi.value())

    def _format_last_connect(self, addr):
        ts = self._last_connect.get(_last_connect_key(addr))
        if not ts:
            return ""
        try:
            return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            return ""

    def remember_last_connect(self, address, when=None):
        settings = getattr(self.app, "settings", None)
        data = remember_ble_connect(settings, address, when)
        if data:
            self._last_connect = data
        else:
            addr = _last_connect_key(address)
            if addr:
                self._last_connect[addr] = float(
                    when if when is not None else time.time())
        self._apply_filter()
        self._refresh_detail()

    def _apply_filter(self):
        q = (self.ed_search.text() or "").strip().lower()
        filter_on = self.sw_filter.isChecked()
        min_rssi = self._rssi_min() if filter_on else None
        for r in range(self.table.rowCount()):
            uuid = self.table.item(r, COL_UUID)
            uuid_extra = ""
            if uuid is not None:
                uuid_extra = " ".join(uuid.data(Qt.UserRole) or [])
            snap = {}
            mfr = self.table.item(r, COL_MFR)
            if mfr is not None:
                snap = dict(mfr.data(Qt.UserRole) or {})
            cells = []
            for col in range(self.table.columnCount()):
                if col == COL_NO:
                    continue
                item = self.table.item(r, col)
                if item is None:
                    continue
                cells.append(item.text() or "")
                cells.append(item.toolTip() or "")
            blob = " ".join(cells + [
                uuid_extra,
                ble_uuid.search_blob_for_adv(snap),
            ]).lower()
            hide = bool(q) and q not in blob
            if filter_on and self._row_blocked_by_rules(r, snap):
                hide = True
            if min_rssi is not None:
                rssi_item = self.table.item(r, COL_RSSI)
                try:
                    rssi_n = int(rssi_item.data(Qt.UserRole)) if rssi_item else -999
                except (TypeError, ValueError):
                    rssi_n = -999
                if rssi_n < min_rssi:
                    hide = True
            self.table.setRowHidden(r, hide)
        scanning = bool(
            getattr(getattr(self.app, "_ble_scanner", None), "is_scanning", False))
        self.set_scanning(scanning)
        self._renumber_rows()

    def _chrome(self):
        tid = self.app.cb_theme.currentData() if hasattr(self.app, "cb_theme") else None
        return chrome_for(tid)

    def _paint_row(self, row, stale):
        c = self._chrome()
        color = QColor(c["text_sec"] if stale else c["text"])
        brush = QBrush(color)
        no_brush = QBrush(QColor(c["text_sec"]))
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is not None:
                item.setForeground(no_brush if col == COL_NO else brush)

    def _repaint_rows(self):
        for r in range(self.table.rowCount()):
            self._paint_row(r, self._row_stale(r))

    def _refresh_stale(self):
        now = self._now()
        changed = False
        for r in range(self.table.rowCount()):
            addr_item = self.table.item(r, COL_ADDR)
            addr = addr_item.text() if addr_item is not None else ""
            meta = self._meta.get(addr) or {}
            seen = meta.get("seen")
            stale = seen is None or (now - seen) >= _STALE_SEC
            if meta.get("stale") == stale:
                continue
            changed = True
            meta["stale"] = stale
            self._meta[addr] = meta
            self._paint_row(r, stale)
        if changed and self.sw_filter.isChecked() and self._filt("hide_stale"):
            self._apply_filter()

    def _selected_row(self):
        items = self.table.selectedItems()
        if not items:
            return -1
        return items[0].row()

    def _selected_addr(self):
        row = self._selected_row()
        if row < 0:
            return ""
        item = self.table.item(row, COL_ADDR)
        return item.text() if item is not None else ""

    def _refresh_detail(self):
        row = self._selected_row()
        if row < 0:
            self.txt_detail.setPlainText(self.app._t("ble_scan_detail_empty"))
            self.btn_copy.setEnabled(False)
            return
        rssi_item = self.table.item(row, COL_RSSI)
        uuid_item = self.table.item(row, COL_UUID)
        mfr_item = self.table.item(row, COL_MFR)
        int_item = self.table.item(row, COL_INT)
        try:
            rssi_n = int(rssi_item.data(Qt.UserRole)) if rssi_item else -999
        except (TypeError, ValueError):
            rssi_n = -999
        uuids = list(uuid_item.data(Qt.UserRole) or []) if uuid_item else []
        snap = dict(mfr_item.data(Qt.UserRole) or {}) if mfr_item else {}
        interval = None
        if int_item is not None:
            try:
                role = int(int_item.data(Qt.UserRole))
                if role >= 0:
                    interval = role
            except (TypeError, ValueError):
                interval = None
        text = self._row_tooltip(rssi_n, uuids, snap, interval, self._selected_addr())
        self.txt_detail.setPlainText(text or self.app._t("ble_scan_detail_empty"))
        self.btn_copy.setEnabled(bool(text))

    def _copy_detail(self):
        text = self.txt_detail.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)

    def _on_scan(self):
        start = getattr(self.app, "_start_ble_scan", None)
        if callable(start):
            start()

    def _on_stop(self):
        stop = getattr(self.app, "_stop_ble_scan", None)
        if callable(stop):
            stop("user")

    def _use_selected(self):
        row = self._selected_row()
        if row < 0:
            return
        addr_item = self.table.item(row, COL_ADDR)
        name_item = self.table.item(row, COL_NAME)
        addr = addr_item.text() if addr_item is not None else ""
        name = ""
        if name_item is not None:
            name = name_item.data(Qt.UserRole) or ""
            if not name and name_item.text() != self.app._t("ble_unnamed"):
                name = name_item.text()
        apply_fn = getattr(self.app, "_apply_ble_device", None)
        if callable(apply_fn) and addr:
            apply_fn(addr, name)
        stop = getattr(self.app, "_stop_ble_scan", None)
        if callable(stop):
            stop()
        self.hide()

    def showEvent(self, event):
        self._last_connect = load_ble_last_connect(
            getattr(self.app, "settings", None))
        super().showEvent(event)
        self._stale_timer.start()
        self._apply_filter()
        self._refresh_detail()

    def hideEvent(self, event):
        self._stale_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        if not self._closing:
            self._closing = True
            stop = getattr(self.app, "_stop_ble_scan", None)
            if callable(stop):
                stop()
            self._closing = False
        super().closeEvent(event)
