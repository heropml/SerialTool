# -*- coding: utf-8 -*-
"""RTT target-device picker: the J-Link driver's full device table in a window.

The driver ships ~14000 devices, far too many for a sidebar dropdown. Same
data J-Link RTT Viewer's "Target Device Settings" shows — manufacturer,
device, core, flash, RAM — with its per-column filtering (vendor and core
are dropdowns built from what the table actually contains) plus a free-text
box that ANDs space-separated terms across the text columns. The footer
names the JLinkARM DLL the list came from and lets the user point at
another install, since pylink itself only ever scans C:.
"""
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QTableView, QVBoxLayout,
)

from ui.dialogs import _dialog_list_qss, _set_win_titlebar_dark
from ui.fonts import mono_font
from ui.theme import chrome_for

COL_VENDOR, COL_NAME, COL_CORE, COL_FLASH, COL_RAM = range(5)
_COL_WIDTHS = (150, 240, 130, 90, 90)
_TEXT_COLS = (COL_VENDOR, COL_NAME, COL_CORE)
_DASH = "—"


def format_size(num_bytes):
    """字节数 -> 人读的容量；0/未知 -> 破折号（与 RTT Viewer 的空值一致）。"""
    try:
        value = int(num_bytes or 0)
    except (TypeError, ValueError):
        return _DASH
    if value <= 0:
        return _DASH
    for unit, step in (("MB", 1024 * 1024), ("KB", 1024)):
        if value >= step:
            text = ("%.1f" % (value / float(step))).rstrip("0").rstrip(".")
            return "%s %s" % (text, unit)
    return "%d B" % value


class _DeviceTableModel(QAbstractTableModel):
    """直接映射器件字典，避免为 1.4 万行创建约 7 万个 QStandardItem。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._values = []
        self._headers = [""] * 5

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 5

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        values = self._values[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return values[col]
        if role == Qt.UserRole:
            if col == COL_FLASH:
                return int(row.get("flash") or 0)
            if col == COL_RAM:
                return int(row.get("ram") or 0)
            return values[col]
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if (role == Qt.DisplayRole and orientation == Qt.Horizontal
                and 0 <= section < len(self._headers)):
            return self._headers[section]
        return super().headerData(section, orientation, role)

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows or [])
        self._values = [
            (str(row.get("manufacturer") or ""),
             str(row.get("name") or ""),
             str(row.get("core") or ""),
             format_size(row.get("flash")),
             format_size(row.get("ram")))
            for row in self._rows
        ]
        self.endResetModel()

    def set_headers(self, headers):
        self._headers = list(headers)
        self.headerDataChanged.emit(Qt.Horizontal, 0, len(self._headers) - 1)


class _DeviceFilter(QSortFilterProxyModel):
    """Per-column equality (vendor / core) plus AND-ed free-text terms.

    ``st h743`` matches STM32H743xx regardless of which column each term
    lands in — the table mixes vendor prefixes into device names.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._terms = []
        self._vendor = ""
        self._core = ""

    def set_query(self, text):
        self._terms = [t for t in str(text or "").lower().split() if t]
        self.invalidateFilter()

    def set_column_filters(self, vendor="", core=""):
        self._vendor = str(vendor or "")
        self._core = str(core or "")
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()

        def cell(col):
            return model.index(row, col, parent).data() or ""

        if self._vendor and cell(COL_VENDOR) != self._vendor:
            return False
        if self._core and cell(COL_CORE) != self._core:
            return False
        if not self._terms:
            return True
        blob = " ".join(cell(col) for col in _TEXT_COLS).lower()
        return all(term in blob for term in self._terms)


class RttDeviceDialog(QDialog):
    """Pick one device name and hand it back to the sidebar."""

    def __init__(self, app):
        # parent=None: keep out of the frameless main window's Qt parent chain
        # (same reason as the other dialogs); _shutdown collects it.
        super().__init__(None)
        self.app = app
        self._rows = []
        self._syncing = False
        self.setWindowFlags(
            Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
            | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(720, 460)
        self.resize(880, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        # 筛选条：厂商 / 内核用下拉（选项就是表里实际有的值），其余靠搜索框
        filters = QHBoxLayout()
        filters.setSpacing(6)
        self.cb_vendor = QComboBox()
        self.cb_vendor.setMinimumWidth(150)
        self.cb_vendor.setMaxVisibleItems(20)
        self.cb_vendor.currentIndexChanged.connect(self._apply_column_filters)
        filters.addWidget(self.cb_vendor)
        self.cb_core = QComboBox()
        self.cb_core.setMinimumWidth(130)
        self.cb_core.setMaxVisibleItems(20)
        self.cb_core.currentIndexChanged.connect(self._apply_column_filters)
        filters.addWidget(self.cb_core)
        self.ed_search = QLineEdit()
        self.ed_search.setObjectName("SnipSearch")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(self._on_search)
        filters.addWidget(self.ed_search, 1)
        self.btn_reset = QPushButton()
        self.btn_reset.setObjectName("MsGhostBtn")
        self.btn_reset.setMinimumHeight(28)
        self.btn_reset.clicked.connect(self._reset_filters)
        filters.addWidget(self.btn_reset)
        root.addLayout(filters)

        self.model = _DeviceTableModel(self)
        self.proxy = _DeviceFilter(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setSortRole(Qt.UserRole)

        self.table = QTableView()
        self.table.setObjectName("RttDeviceTable")
        self.table.setModel(self.proxy)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setFont(mono_font(10))
        self.table.doubleClicked.connect(lambda *_: self._use_selected())
        # 默认保持驱动给出的顺序（与 RTT Viewer 一致）：setSortingEnabled 会
        # 立刻按第 0 列排一遍，用 sortByColumn(-1) 退回源模型顺序，之后用户
        # 点表头照样能排。
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for col, width in enumerate(_COL_WIDTHS):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            self.table.setColumnWidth(col, width)
        root.addWidget(self.table, 1)

        drv = QHBoxLayout()
        drv.setSpacing(6)
        self.lbl_driver = QLabel()
        self.lbl_driver.setObjectName("MsHint")
        self.lbl_driver.setWordWrap(True)
        drv.addWidget(self.lbl_driver, 1)
        self.btn_driver = QPushButton()
        self.btn_driver.setObjectName("MsGhostBtn")
        self.btn_driver.setMinimumHeight(28)
        self.btn_driver.clicked.connect(self._pick_driver)
        drv.addWidget(self.btn_driver)
        root.addLayout(drv)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.lbl_count = QLabel()
        self.lbl_count.setObjectName("MsHint")
        actions.addWidget(self.lbl_count, 1)
        self.btn_use = QPushButton()
        self.btn_use.setObjectName("MsGhostBtn")
        self.btn_use.setMinimumHeight(30)
        self.btn_use.setMinimumWidth(88)
        self.btn_use.clicked.connect(self._use_selected)
        actions.addWidget(self.btn_use)
        self.btn_close = QPushButton()
        self.btn_close.setObjectName("MsGhostBtn")
        self.btn_close.setMinimumHeight(30)
        self.btn_close.setMinimumWidth(88)
        self.btn_close.clicked.connect(self.hide)
        actions.addWidget(self.btn_close)
        root.addLayout(actions)

        self.retranslate()
        self.refresh_theme()

    # ---- data ----

    def set_devices(self, rows):
        """rows: list of dicts from rtt_io.list_devices()."""
        self._rows = list(rows or [])
        self.model.set_rows(self._rows)
        self._rebuild_column_filters()
        self._refresh_count()

    def _rebuild_column_filters(self):
        """厂商 / 内核下拉的选项 = 表里实际出现过的值（首项是「全部」）。"""
        vendors = sorted({str(r.get("manufacturer") or "").strip()
                          for r in self._rows} - {""},
                         key=lambda v: v.lower())
        # 驱动没给名字的内核只有十六进制 id，沉到列表末尾，别挡住有名字的
        cores = sorted({str(r.get("core") or "").strip()
                        for r in self._rows} - {""},
                       key=lambda v: (v.upper().startswith("0X"), v.lower()))
        self._syncing = True
        for combo, values, all_key in (
                (self.cb_vendor, vendors, "rtt_dev_all_vendors"),
                (self.cb_core, cores, "rtt_dev_all_cores")):
            keep = combo.currentData() or ""
            combo.clear()
            combo.addItem(self.app._t(all_key), "")
            for value in values:
                combo.addItem(value, value)
            index = combo.findData(keep)
            combo.setCurrentIndex(index if index >= 0 else 0)
        self._syncing = False
        self._apply_column_filters()

    def set_driver(self, path):
        t = self.app._t
        self.lbl_driver.setText(
            t("rtt_dev_driver", path=path) if path
            else t("rtt_dev_driver_missing"))

    def select_device(self, name):
        """Preselect the currently configured device and scroll it into view."""
        name = str(name or "").strip()
        if not name:
            return
        for row in range(self.proxy.rowCount()):
            index = self.proxy.index(row, COL_NAME)
            if (index.data() or "") == name:
                self.table.setCurrentIndex(index)
                self.table.scrollTo(index, QAbstractItemView.PositionAtCenter)
                return

    def _refresh_count(self):
        self.lbl_count.setText(self.app._t(
            "rtt_dev_count",
            shown=self.proxy.rowCount(), total=self.model.rowCount()))

    def _apply_column_filters(self, *_args):
        if self._syncing:
            return
        self.proxy.set_column_filters(
            self.cb_vendor.currentData() or "",
            self.cb_core.currentData() or "")
        self._refresh_count()

    def _on_search(self, text):
        self.proxy.set_query(text)
        self._refresh_count()

    def _reset_filters(self):
        self._syncing = True
        self.ed_search.clear()
        self.cb_vendor.setCurrentIndex(0)
        self.cb_core.setCurrentIndex(0)
        self._syncing = False
        self.proxy.set_query("")
        self._apply_column_filters()

    def _use_selected(self):
        index = self.table.currentIndex()
        if not index.isValid():
            return
        name = self.proxy.index(index.row(), COL_NAME).data() or ""
        apply_fn = getattr(self.app, "_apply_rtt_device", None)
        if name and callable(apply_fn):
            apply_fn(name)
        self.hide()

    def _pick_driver(self):
        """Point at another J-Link install (pylink only ever scans C:)."""
        import os

        from transport import rtt_io
        current = (getattr(self.app, "_rtt_driver_path", "")
                   or rtt_io.get_dll_hint())
        start = (current if current and os.path.isdir(current)
                 else os.path.dirname(current) if current else "")
        directory = QFileDialog.getExistingDirectory(
            self, self.app._t("rtt_dev_driver_pick"), start)
        if not directory:
            return
        reload_fn = getattr(self.app, "_reload_rtt_catalog", None)
        if callable(reload_fn):
            reload_fn(directory)

    # ---- chrome ----

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("rtt_dev_title"))
        self.ed_search.setPlaceholderText(t("rtt_dev_search_ph"))
        self.btn_use.setText(t("rtt_dev_use"))
        self.btn_close.setText(t("cancel"))
        self.btn_reset.setText(t("rtt_dev_reset"))
        self.btn_driver.setText(t("rtt_dev_driver_change"))
        self.model.set_headers([
            t("rtt_dev_col_vendor"), t("rtt_dev_col_name"),
            t("rtt_dev_col_core"), t("rtt_dev_col_flash"),
            t("rtt_dev_col_ram")])
        if self.cb_vendor.count():
            self.cb_vendor.setItemText(0, t("rtt_dev_all_vendors"))
        if self.cb_core.count():
            self.cb_core.setItemText(0, t("rtt_dev_all_cores"))
        self._refresh_count()

    def refresh_theme(self):
        tid = (self.app.cb_theme.currentData()
               if hasattr(self.app, "cb_theme") else None)
        c = chrome_for(tid)
        self.setStyleSheet(_dialog_list_qss(c) + """
        QLineEdit#SnipSearch {{
            background-color: {inp}; border: 1px solid {sep};
            border-radius: 6px; padding: 6px 10px; color: {txt};
            font-family: 'Segoe UI'; font-size: 12px;
        }}
        QLineEdit#SnipSearch:focus {{
            border: 1px solid {acc}; background-color: {focus};
        }}
        QTableView#RttDeviceTable {{
            background-color: {card}; alternate-background-color: {win};
            color: {txt}; border: 1px solid {sep}; border-radius: 8px;
            gridline-color: {sep}; outline: 0px;
            selection-background-color: {acc}; selection-color: #FFFFFF;
        }}
        QTableView#RttDeviceTable::item {{ padding: 2px 6px; }}
        QHeaderView::section {{
            background-color: {win}; color: {sec}; border: 0px;
            border-bottom: 1px solid {sep}; padding: 4px 6px;
            font-family: 'Segoe UI'; font-size: 11px;
        }}
        """.format(inp=c["input_bg"], sep=c["separator"], txt=c["text"],
                   acc=c["accent"], focus=c["input_focus_bg"],
                   card=c["card_bg"], win=c["window_bg"], sec=c["text_sec"]))
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")

    def showEvent(self, event):
        super().showEvent(event)
        self.ed_search.setFocus()
        self.ed_search.selectAll()
