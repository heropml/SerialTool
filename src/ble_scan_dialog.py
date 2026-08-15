# -*- coding: utf-8 -*-
"""BLE device picker: scan results in a dedicated window (not the sidebar)."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from fonts import localize_qss, mono_font
from theme import chrome_for
from dialogs import _dialog_list_qss, _set_win_titlebar_dark


class _RssiItem(QTableWidgetItem):
    """Sort RSSI by numeric UserRole, not lexicographic text."""

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
        self.setWindowFlags(
            Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
            | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(560, 420)
        self.resize(640, 500)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.btn_scan = QPushButton()
        self.btn_scan.setObjectName("MsPrimaryBtn")
        self.btn_scan.setMinimumHeight(30)
        self.btn_scan.clicked.connect(self._on_scan)
        top.addWidget(self.btn_scan)
        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("MsGhostBtn")
        self.btn_stop.setMinimumHeight(30)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        top.addWidget(self.btn_stop)
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("MsHint")
        top.addWidget(self.lbl_status, 1)
        root.addLayout(top)

        self.ed_search = QLineEdit()
        self.ed_search.setObjectName("SnipSearch")
        self.ed_search.textChanged.connect(self._apply_filter)
        root.addWidget(self.ed_search)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("BleScanTable")
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setFont(mono_font(10))
        self.table.itemDoubleClicked.connect(lambda *_: self._use_selected())
        root.addWidget(self.table, 1)

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

        self.retranslate()
        self.refresh_theme()
        self.set_scanning(False)

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("ble_scan_title"))
        self.btn_scan.setText(t("ble_scan"))
        self.btn_stop.setText(t("ble_scan_stop"))
        self.btn_use.setText(t("ble_scan_use"))
        self.btn_close.setText(t("cancel"))
        self.ed_search.setPlaceholderText(t("ble_scan_search_ph"))
        self.lbl_hint.setText(t("ble_scan_hint"))
        self.table.setHorizontalHeaderLabels([
            t("ble_col_name"), t("ble_col_addr"), t("ble_col_rssi")])
        scanning = bool(
            getattr(getattr(self.app, "_ble_scanner", None), "is_scanning", False))
        self.set_scanning(scanning)

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
            padding: 6px 8px; font-family: 'Segoe UI'; font-size: 11px;
        }}
        QPushButton#MsPrimaryBtn {{
            background-color: {acc}; color: #FFFFFF; border: none;
            border-radius: 8px; padding: 6px 14px; font-weight: 600;
        }}
        QPushButton#MsPrimaryBtn:disabled {{ background-color: {sep}; color: {sec}; }}
        QPushButton#MsGhostBtn {{
            background-color: {card}; color: {txt};
            border: 1px solid {sep}; border-radius: 8px; padding: 6px 14px;
        }}
        QPushButton#MsGhostBtn:disabled {{ color: {sec}; }}
        """.format(
            sec=c["text_sec"], inp=c["input_bg"], sep=c["separator"],
            txt=c["text"], acc=c["accent"], focus=c["input_focus_bg"],
            card=c["card_bg"],
            alt=c.get("window_bg") or c["card_bg"],
        )
        self.setStyleSheet(localize_qss(qss))
        _set_win_titlebar_dark(self, c.get("mode") == "dark")

    def clear_devices(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self._apply_filter()

    def upsert(self, address, name, rssi):
        addr = str(address or "").upper()
        if not addr:
            return
        unnamed = self.app._t("ble_unnamed")
        label = name or unnamed
        rssi_s = "" if rssi is None else str(rssi)
        try:
            rssi_n = int(rssi) if rssi is not None else -999
        except (TypeError, ValueError):
            rssi_n = -999
        self.table.setSortingEnabled(False)
        r = -1
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 1)
            if item is not None and item.text() == addr:
                r = i
                break
        if r >= 0:
            name_item = self.table.item(r, 0)
            rssi_item = self.table.item(r, 2)
            if name_item is not None:
                name_item.setText(label)
                name_item.setData(Qt.UserRole, name or "")
            if rssi_item is not None:
                rssi_item.setText(rssi_s)
                rssi_item.setData(Qt.UserRole, rssi_n)
        else:
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(label)
            name_item.setData(Qt.UserRole, name or "")
            addr_item = QTableWidgetItem(addr)
            rssi_item = _RssiItem(rssi_s)
            rssi_item.setData(Qt.UserRole, rssi_n)
            rssi_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, addr_item)
            self.table.setItem(r, 2, rssi_item)
        self.table.setSortingEnabled(True)
        self._apply_filter()

    def set_scanning(self, on):
        self.btn_scan.setEnabled(not on)
        self.btn_stop.setEnabled(bool(on))
        n = self.table.rowCount()
        if on:
            self.lbl_status.setText(self.app._t("ble_scan_status_on", n=n))
        else:
            self.lbl_status.setText(self.app._t("ble_scan_status_off", n=n))

    def _apply_filter(self):
        q = (self.ed_search.text() or "").strip().lower()
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0)
            addr = self.table.item(r, 1)
            blob = " ".join([
                name.text() if name is not None else "",
                addr.text() if addr is not None else "",
            ]).lower()
            self.table.setRowHidden(r, bool(q) and q not in blob)
        scanning = bool(
            getattr(getattr(self.app, "_ble_scanner", None), "is_scanning", False))
        self.set_scanning(scanning)

    def _on_scan(self):
        start = getattr(self.app, "_start_ble_scan", None)
        if callable(start):
            start()

    def _on_stop(self):
        stop = getattr(self.app, "_stop_ble_scan", None)
        if callable(stop):
            stop("user")

    def _use_selected(self):
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        name_item = self.table.item(row, 0)
        addr_item = self.table.item(row, 1)
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

    def closeEvent(self, event):
        if not self._closing:
            self._closing = True
            stop = getattr(self.app, "_stop_ble_scan", None)
            if callable(stop):
                stop()
            self._closing = False
        super().closeEvent(event)
