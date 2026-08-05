# -*- coding: utf-8 -*-
"""设备定义、寄存器表与 Modbus 扫描中心。"""

import csv
import json

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QProgressBar,
    QScrollArea, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from device_resources import REGISTER_ORDERS, REGISTER_TYPES, normalize_registers
from dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from fonts import localize_qss
from theme import chrome_for
from ui_tips import set_tooltip


_REGISTER_COLUMNS = (
    "device_col_enabled", "device_col_name", "device_col_slave", "device_col_func",
    "device_col_address", "device_col_type", "device_col_order", "device_col_bit",
    "device_col_scale", "device_col_offset", "device_col_unit",
)
_MAX_SCAN_TARGETS = 512
_SCAN_STATUS_KEYS = {
    "waiting": "device_scan_waiting",
    "ok": "device_scan_status_ok",
    "timeout": "mbm_st_timeout",
    "err": "device_scan_status_error",
    "exc": "device_scan_status_exception",
}


class DeviceCenterDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(900, 520)
        self.resize(1120, 650)
        self._scan_rows = []
        self._scan_ok = []
        self._scan_completed = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_register_tab(), "")
        self.tabs.addTab(self._build_scan_tab(), "")
        self.reload_cfg()
        self.retranslate()
        self.refresh_theme()

    def _button(self, key, callback):
        button = QPushButton()
        button.setObjectName("PlotGhostBtn")
        button.setProperty("tr_text", key)
        button.clicked.connect(callback)
        return button

    def _build_register_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        self.btn_add = self._button("device_add", self._add_register)
        self.btn_delete = self._button("device_delete", self._delete_registers)
        self.btn_import = self._button("device_import", self._import_registers)
        self.btn_export = self._button("device_export", self._export_registers)
        self.btn_apply = self._button(
            "device_apply", lambda *_: self.commit_pending())
        for button in (self.btn_add, self.btn_delete, self.btn_import, self.btn_export):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_apply)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("PlotHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help_dlg)
        toolbar.addWidget(self.btn_help)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_REGISTER_COLUMNS))
        self.table.setObjectName("DeviceRegisterTable")
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_register_menu)
        layout.addWidget(self.table, 1)
        return page

    def _build_scan_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.lbl_scan_mode = QLabel()
        self.cb_scan_mode = QComboBox()
        self.cb_scan_mode.addItem("", "slave")
        self.cb_scan_mode.addItem("", "register")
        self.lbl_scan_unit = QLabel()
        self.sp_scan_unit = QSpinBox()
        self.sp_scan_unit.setRange(0, 255)
        self.sp_scan_unit.setValue(1)
        self.lbl_scan_start = QLabel()
        self.sp_scan_start = QSpinBox()
        self.sp_scan_start.setRange(0, 65535)
        self.sp_scan_start.setValue(1)
        self.lbl_scan_end = QLabel()
        self.sp_scan_end = QSpinBox()
        self.sp_scan_end.setRange(0, 65535)
        self.sp_scan_end.setValue(10)
        self.lbl_scan_func = QLabel()
        self.cb_scan_func = QComboBox()
        self.cb_scan_func.addItem("03", 3)
        self.cb_scan_func.addItem("04", 4)
        self.lbl_scan_timeout = QLabel()
        self.sp_scan_timeout = QSpinBox()
        self.sp_scan_timeout.setRange(50, 5000)
        self.sp_scan_timeout.setValue(300)
        self.sp_scan_timeout.setSuffix(" ms")
        self.btn_scan = self._button("device_scan_start", self._start_scan)
        self.btn_scan_stop = self._button("device_scan_stop", self._stop_scan)
        self.btn_scan_add = self._button("device_scan_add_results", self._add_scan_results)
        for widget in (
                self.lbl_scan_mode, self.cb_scan_mode, self.lbl_scan_unit, self.sp_scan_unit,
                self.lbl_scan_start, self.sp_scan_start, self.lbl_scan_end, self.sp_scan_end,
                self.lbl_scan_func, self.cb_scan_func, self.lbl_scan_timeout,
                self.sp_scan_timeout, self.btn_scan, self.btn_scan_stop):
            controls.addWidget(widget)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.cb_scan_mode.currentIndexChanged.connect(self._sync_scan_mode)

        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 1)
        layout.addWidget(self.scan_progress)
        self.scan_table = QTableWidget(0, 4)
        self.scan_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.scan_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.scan_table, 1)
        bottom = QHBoxLayout()
        self.lbl_scan_summary = QLabel()
        bottom.addWidget(self.lbl_scan_summary, 1)
        bottom.addWidget(self.btn_scan_add)
        layout.addLayout(bottom)
        self._sync_scan_mode()
        return page

    @staticmethod
    def _item(value=""):
        return QTableWidgetItem(str(value))

    def _scan_status_text(self, status):
        key = _SCAN_STATUS_KEYS.get(str(status))
        return self.app._t(key) if key else str(status)

    def _set_scan_status(self, row, status):
        item = self._item(self._scan_status_text(status))
        item.setData(Qt.UserRole, str(status))
        self.scan_table.setItem(row, 2, item)

    def _refresh_scan_summary(self):
        self.lbl_scan_summary.setText(self.app._t(
            "device_scan_summary", done=len(self._scan_completed),
            total=len(self._scan_rows), found=len(self._scan_ok)))

    @staticmethod
    def _combo(options, current):
        combo = QComboBox()
        for label, value in options:
            combo.addItem(str(label), value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        return combo

    def _append_register(self, record=None):
        rec = normalize_registers([record or {}])[0]
        row = self.table.rowCount()
        self.table.insertRow(row)
        enabled = QTableWidgetItem()
        enabled.setFlags(enabled.flags() | Qt.ItemIsUserCheckable)
        enabled.setCheckState(Qt.Checked if rec["enabled"] else Qt.Unchecked)
        self.table.setItem(row, 0, enabled)
        values = (rec["name"], rec["slave"], None, rec["address"], None,
                  None, rec["bit"], rec["scale"], rec["offset"], rec["unit"])
        for column, value in enumerate(values, 1):
            if value is None:
                continue
            self.table.setItem(row, column, self._item(value))
        self.table.setCellWidget(row, 3, self._combo((("03", 3), ("04", 4)), rec["function"]))
        self.table.setCellWidget(
            row, 5, self._combo(tuple((value, value) for value in REGISTER_TYPES), rec["type"]))
        self.table.setCellWidget(
            row, 6, self._combo(tuple((value, value) for value in REGISTER_ORDERS), rec["order"]))

    def _add_register(self):
        self._append_register({"address": self.table.rowCount()})

    def _delete_registers(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def _collect_registers(self):
        records = []
        for row in range(self.table.rowCount()):
            def text(column, default=""):
                item = self.table.item(row, column)
                return item.text().strip() if item is not None else default
            def combo_value(column, default):
                combo = self.table.cellWidget(row, column)
                return combo.currentData() if combo is not None else default
            records.append({
                "enabled": self.table.item(row, 0).checkState() == Qt.Checked,
                "name": text(1), "slave": text(2, "1"), "function": combo_value(3, 3),
                "address": text(4, "0"), "type": combo_value(5, "u16"),
                "order": combo_value(6, "AB"), "bit": text(7, "0"),
                "scale": text(8, "1"), "offset": text(9, "0"), "unit": text(10),
            })
        return normalize_registers(records)

    @staticmethod
    def _merge_scan_registers(existing, scanned):
        """按 (slave, function, address) 合并扫描结果。

        已存在的行只更新扫描确知的身份字段（name/slave/function/address），
        **保留用户自定义的 type/order/scale/offset/unit/bit/enabled**——否则扫描
        结果（只带身份字段，经 normalize_register 填默认值）会把 u32/scale 0.1 等
        手工配置冲成 u16/1.0，联动解码读数失真。新发现的地址才用扫描结果建新行。
        """
        _IDENTITY = ("name", "slave", "function", "address")

        def _identity(record):
            return (record.get("slave"), record.get("function"), record.get("address"))

        merged = []
        positions = {}
        for record in normalize_registers(existing or []):
            key = _identity(record)
            if key in positions:
                # 旧配置本身可能已经含重复身份；保留第一条的用户元数据，
                # 丢弃后续重复行，避免扫描后继续重复轮询同一寄存器。
                continue
            positions[key] = len(merged)
            merged.append(record)
        for record in normalize_registers(scanned or []):
            key = _identity(record)
            if key in positions:
                # 覆盖已有行时只更新身份字段，保留其它字段（type/scale/unit…）
                updated = dict(merged[positions[key]])
                for field in _IDENTITY:
                    updated[field] = record.get(field, updated[field])
                merged[positions[key]] = updated
            else:
                positions[key] = len(merged)
                merged.append(record)
        return merged

    @staticmethod
    def _migrate_link_tags(old_registers, new_registers, tags):
        """按 (slave, function, address) 把改名前的联动标签迁移到新名称。

        身份必须带上功能码：holding(03) 与 input(04) 常共用同一数值地址，
        若只按 (slave, address) 映射，删掉已联动的 holding 留下同址 input 时会
        静默把联动迁到另一个功能码的寄存器。

        身份映射语义：
        - 旧表中唯一命中 → 查新表同身份：
          - 新表唯一命中 → 迁到新名（改名）
          - 新表无该身份 → 寄存器已删除，移除联动标签
          - 新表身份不唯一 → 不猜测，保留原标签（避免迁错）
        - 旧表中同名多条 → 无法判定是哪一个，保留原标签
        """
        old_by_name = {}
        new_by_identity = {}
        for record in old_registers or []:
            old_by_name.setdefault(record.get("name"), []).append(record)
        for record in new_registers or []:
            identity = (record.get("slave"), record.get("function"),
                        record.get("address"))
            new_by_identity.setdefault(identity, []).append(record)

        migrated = set()
        changed = False
        for tag in set(tags or ()):
            old_matches = old_by_name.get(tag, [])
            if len(old_matches) == 1:
                old = old_matches[0]
                identity = (old.get("slave"), old.get("function"),
                            old.get("address"))
                new_matches = new_by_identity.get(identity, [])
                if len(new_matches) == 1:
                    replacement = new_matches[0].get("name")
                    if replacement:
                        migrated.add(replacement)
                        changed |= replacement != tag
                        continue
                elif not new_matches:
                    # 该寄存器已从表里删除：联动标签跟着移除，否则 `_feed_named_view`
                    # 用已不存在的 name 匹配永远不命中，形成静默失效的悬空标签。
                    changed = True
                    continue
            migrated.add(tag)
        return migrated, changed

    def commit_pending(self, notify=True, refresh_dirty=True):
        old_registers = list(getattr(self.app, "_device_registers", []))
        new_registers = self._collect_registers()
        self.app._device_registers = new_registers
        links_changed = False
        for attr in ("_device_plot_tags", "_device_dash_tags"):
            tags, changed = self._migrate_link_tags(
                old_registers, new_registers, getattr(self.app, attr, set()))
            setattr(self.app, attr, tags)
            links_changed |= changed
        self.app.settings.setValue(
            "device_registers", json.dumps(self.app._device_registers, ensure_ascii=False))
        if links_changed:
            self.app._save_device_link()
        self.app.settings.sync()
        if refresh_dirty:
            self.app._refresh_project_dirty_label()
        if notify:
            self.app.toast(self.app._t("device_saved"))

    def reload_cfg(self):
        self.table.setRowCount(0)
        for record in getattr(self.app, "_device_registers", []):
            self._append_register(record)

    # ---------------- 寄存器 ↔ 绘图/仪表盘 联动 ----------------
    def _selected_register_tags(self):
        """返回选中行（无选中则取当前行）的规范化标签列表。"""
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not rows:
            current = self.table.currentRow()
            rows = [current] if current >= 0 else []
        if not rows:
            return []
        all_regs = self._collect_registers()
        return [all_regs[r]["name"] for r in rows if 0 <= r < len(all_regs)]

    def _on_register_menu(self, pos):
        # 右键点未选行 → 只选该行（符合"点哪行操作哪行"直觉；点已选多行则操作整组选区）
        clicked = self.table.rowAt(pos.y())
        if clicked >= 0:
            rows = {idx.row() for idx in self.table.selectedIndexes()}
            if clicked not in rows:
                self.table.selectRow(clicked)
        tags = self._selected_register_tags()
        if not tags:
            return
        plot_set = self.app._device_plot_tags
        dash_set = self.app._device_dash_tags
        in_plot = sum(1 for t in tags if t in plot_set)
        in_dash = sum(1 for t in tags if t in dash_set)
        menu = QMenu(self)
        # 全部已在 → 可移除；否则 → 加入缺失项
        if in_plot == len(tags) and in_plot:
            act = menu.addAction(self.app._t("device_link_plot_remove", n=len(tags)))
            act.triggered.connect(lambda: self._toggle_link("plot", tags, False))
        else:
            act = menu.addAction(self.app._t("device_link_plot_add", n=len(tags) - in_plot))
            act.triggered.connect(lambda: self._toggle_link("plot", tags, True))
        if in_dash == len(tags) and in_dash:
            act = menu.addAction(self.app._t("device_link_dash_remove", n=len(tags)))
            act.triggered.connect(lambda: self._toggle_link("dash", tags, False))
        else:
            act = menu.addAction(self.app._t("device_link_dash_add", n=len(tags) - in_dash))
            act.triggered.connect(lambda: self._toggle_link("dash", tags, True))
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _toggle_link(self, target, tags, add):
        # 先把表格当前编辑(含改名)提交到 _device_registers，确保联动存的标签与
        # _structured_feed_modbus 解码用的 _device_registers 同源，否则改名不 Apply 会让联动静默失效。
        self.commit_pending(notify=False, refresh_dirty=False)
        attr = "_device_plot_tags" if target == "plot" else "_device_dash_tags"
        cur = set(getattr(self.app, attr, set()))
        if add:
            cur |= set(tags)
        else:
            cur -= set(tags)
        setattr(self.app, attr, cur)
        self.app._save_device_link()
        # 联动标签在 _CFG_KEYS 里（device_plot_tags/device_dash_tags），工程 dirty 指纹会包含它们；
        # 且上方 commit_pending(refresh_dirty=False) 跳过了 dirty 刷新，这里必须补上，
        # 否则 toggle 联动后标题栏仍显示「已保存」。
        self.app._refresh_project_dirty_label()
        name = self.app._t("device_link_plot" if target == "plot" else "device_link_dash")
        self.app.toast(self.app._t("device_link_done", name=name, n=len(tags)))

    def _export_registers(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self.app._t("device_export"), "registers.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        fields = tuple(normalize_registers([{}])[0])
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(self._collect_registers())
        except Exception as exc:
            self.app.toast(str(exc), error=True)

    def _import_registers(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.app._t("device_import"), "", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as stream:
                records = normalize_registers(list(csv.DictReader(stream)))
        except Exception as exc:
            self.app.toast(str(exc), error=True)
            return
        self.table.setRowCount(0)
        for record in records:
            self._append_register(record)

    def _sync_scan_mode(self):
        slave_mode = self.cb_scan_mode.currentData() == "slave"
        maximum = 247 if slave_mode else 65535
        self.sp_scan_start.setMaximum(maximum)
        self.sp_scan_end.setMaximum(maximum)
        self.lbl_scan_unit.setVisible(not slave_mode)
        self.sp_scan_unit.setVisible(not slave_mode)
        self.btn_scan_add.setVisible(not slave_mode)

    def _start_scan(self):
        if self.sp_scan_end.value() < self.sp_scan_start.value():
            self.app.toast(self.app._t("device_scan_bad_range"), error=True)
            return
        mode = self.cb_scan_mode.currentData()
        target_count = self.sp_scan_end.value() - self.sp_scan_start.value() + 1
        if target_count > _MAX_SCAN_TARGETS:
            self.app.toast(self.app._t(
                "device_scan_too_large", limit=_MAX_SCAN_TARGETS), error=True)
            return
        func = int(self.cb_scan_func.currentData())
        rows = []
        if mode == "slave":
            for slave in range(self.sp_scan_start.value(), self.sp_scan_end.value() + 1):
                rows.append({"enabled": True, "name": "Slave %d" % slave, "unit": slave,
                             "func": func, "addr": 0, "qty": 1, "period": 0x7FFFFFFF})
        else:
            slave = self.sp_scan_unit.value()
            for address in range(self.sp_scan_start.value(), self.sp_scan_end.value() + 1):
                rows.append({"enabled": True, "name": "R%d" % address, "unit": slave,
                             "func": func, "addr": address, "qty": 1,
                             "period": 0x7FFFFFFF})
        self._scan_rows = rows
        self._scan_ok = []
        self._scan_completed = set()
        self.scan_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            target = row["unit"] if mode == "slave" else row["addr"]
            self.scan_table.setItem(index, 0, self._item(index + 1))
            self.scan_table.setItem(index, 1, self._item(target))
            self._set_scan_status(index, "waiting")
            self.scan_table.setItem(index, 3, self._item(""))
        self.scan_progress.setRange(0, len(rows))
        self.scan_progress.setValue(0)
        self._refresh_scan_summary()
        self.btn_scan.setEnabled(False)
        if not self.app._start_device_scan(
                rows, self.sp_scan_timeout.value(), self._scan_update, self._scan_done):
            self.btn_scan.setEnabled(True)

    def _stop_scan(self):
        self.app._stop_device_scan(cancelled=True)

    def _scan_update(self, index, status, text):
        if not 0 <= index < self.scan_table.rowCount():
            return
        self._set_scan_status(index, status)
        self.scan_table.setItem(index, 3, self._item(text))
        if status == "ok" and index not in self._scan_ok:
            self._scan_ok.append(index)
        self._scan_completed.add(index)
        self.scan_progress.setValue(len(self._scan_completed))
        self._refresh_scan_summary()

    def _scan_done(self, cancelled=False):
        self.btn_scan.setEnabled(True)
        if cancelled:
            self.lbl_scan_summary.setText(self.app._t("device_scan_cancelled"))

    def _add_scan_results(self):
        if self.cb_scan_mode.currentData() != "register":
            return
        scanned = []
        for index in self._scan_ok:
            row = self._scan_rows[index]
            scanned.append({
                "name": row["name"], "slave": row["unit"],
                "function": row["func"], "address": row["addr"],
            })
        merged = self._merge_scan_registers(self._collect_registers(), scanned)
        self.table.setRowCount(0)
        for record in merged:
            self._append_register(record)
        self.tabs.setCurrentIndex(0)

    # ---------------- 主题 / 语言 ----------------
    def _show_help_dlg(self):
        """弹独立窗口看用法 + 例子（同波形图/仪表盘/结构化记录形制：富文本+滚动+可复制）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("device_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(740, 520)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("device_help"))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setAlignment(Qt.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        btn_close = QPushButton(
            {"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(getattr(self.app, "_lang", "en"), "Close"))
        btn_close.setObjectName("PlotGhostBtn")
        btn_close.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1); row.addWidget(btn_close)
        v.addLayout(row)
        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(f"""
            QDialog {{ background-color: {c['window_bg']}; }}
            QLabel {{ color: {c['text']}; background: transparent;
                      font-family: 'Segoe UI'; font-size: 12px; }}
            QScrollArea {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QPushButton#PlotGhostBtn {{
                background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px;
                font-family: 'Segoe UI'; font-size: 12px; padding: 5px 16px;
            }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        """))
        _set_win_titlebar_dark(dlg, self.app._theme().get("mode") == "dark")
        dlg.exec_()

    def refresh_theme(self):
        c = chrome_for(self.app._theme_id())
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
        QDialog, QWidget {{ background-color: {c['window_bg']}; color: {c['text']}; }}
        QTableWidget {{ background-color: {c['card_bg']}; color: {c['text']};
            alternate-background-color: {c['input_bg']}; border: 1px solid {c['separator']}; }}
        QHeaderView::section {{ background-color: {c['input_bg']}; color: {c['text']};
            border: 0; border-right: 1px solid {c['separator']}; padding: 6px; }}
        QPushButton#PlotGhostBtn {{ background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px; padding: 5px 12px; }}
        QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#PlotHelpBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 13px;
            font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
        }}
        QPushButton#PlotHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        """))
        _style_combo_popups(self, c)
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("device_title"))
        self.tabs.setTabText(0, t("device_register_tab"))
        self.tabs.setTabText(1, t("device_scan_tab"))
        for button in (self.btn_add, self.btn_delete, self.btn_import, self.btn_export,
                       self.btn_apply, self.btn_scan, self.btn_scan_stop, self.btn_scan_add):
            button.setText(t(button.property("tr_text")))
        set_tooltip(self.btn_help, t("device_help_btn"))
        self.table.setHorizontalHeaderLabels([t(key) for key in _REGISTER_COLUMNS])
        self.lbl_scan_mode.setText(t("device_scan_mode"))
        self.cb_scan_mode.setItemText(0, t("device_scan_slave"))
        self.cb_scan_mode.setItemText(1, t("device_scan_register"))
        self.lbl_scan_unit.setText(t("device_col_slave"))
        self.lbl_scan_start.setText(t("device_scan_from"))
        self.lbl_scan_end.setText(t("device_scan_end"))
        self.lbl_scan_func.setText(t("device_col_func"))
        self.lbl_scan_timeout.setText(t("device_scan_timeout"))
        self.scan_table.setHorizontalHeaderLabels([
            "#", t("device_scan_target"), t("device_scan_status"), t("device_scan_result")])
        for row in range(self.scan_table.rowCount()):
            item = self.scan_table.item(row, 2)
            if item is not None and item.data(Qt.UserRole):
                item.setText(self._scan_status_text(item.data(Qt.UserRole)))
        if self._scan_rows:
            self._refresh_scan_summary()

    def closeEvent(self, event):
        self.commit_pending(notify=False)
        self.app._stop_device_scan(cancelled=True)
        super().closeEvent(event)
