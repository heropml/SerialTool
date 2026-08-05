# -*- coding: utf-8 -*-
"""会话比较对话框 RecDiffDialog：选两个 .ctrec，逐条对齐比出差异。

典型用途：新旧固件各录一次，回答「行为哪里不一样」——哪一帧内容变了、谁多发/少发了、
时序差多少。对齐算法在 Qt-free 的 rec_diff 里（LCS，少一帧不会让后续全部错位）。
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QCheckBox, QComboBox, QLineEdit,
                             QScrollArea, QFrame)
from PyQt5.QtGui import QColor

import rec_diff
import rec_replay
from theme import chrome_for
from fonts import localize_qss, mono_font, ui_font
from dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from ui_tips import set_tooltip

_MAX_ROWS = 5000        # 表格渲染上限：差异动辄上万行时只画前 N 条，其余引导去导出 CSV
_HEX_PREVIEW = 24       # 单元格里最多显示多少字节，长帧截断加省略号（完整值在 tooltip / CSV）


class RecDiffDialog(QDialog):
    def __init__(self, app):
        # parent=None：同其它工具对话框，避免干扰主窗 WM_NCHITTEST。主窗 _shutdown 显式收。
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(680, 420)
        self.resize(980, 600)

        self._path_a = ""
        self._path_b = ""
        self._events_a = []
        self._events_b = []
        self._result = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ===== 两个文件选择行 =====
        for side in ("a", "b"):
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel()
            btn = QPushButton()
            btn.setObjectName("PlotGhostBtn")
            btn.clicked.connect(lambda _c, s=side: self._on_pick(s))
            name = QLabel()
            name.setObjectName("MsHint")
            row.addWidget(lbl)
            row.addWidget(btn)
            row.addWidget(name, 1)
            setattr(self, "lbl_%s" % side, lbl)
            setattr(self, "btn_%s" % side, btn)
            setattr(self, "name_%s" % side, name)
            root.addLayout(row)

        # ===== 操作行 =====
        ops = QHBoxLayout()
        ops.setSpacing(8)
        self.btn_cmp = QPushButton()
        self.btn_cmp.setObjectName("PlotPrimaryBtn")
        self.btn_cmp.clicked.connect(self._on_compare)
        self.chk_only_diff = QCheckBox()
        self.cb_dir_filter = QComboBox()
        self.cb_dir_filter.addItem("", "")
        self.cb_dir_filter.addItem("RX", "rx")
        self.cb_dir_filter.addItem("TX", "tx")
        self.cb_dir_filter.currentIndexChanged.connect(self._fill_table)
        self.ed_min_dt = QLineEdit("")
        self.ed_min_dt.setFixedWidth(64)
        self.ed_min_dt.setPlaceholderText("|dt|")
        self.ed_min_dt.editingFinished.connect(self._fill_table)
        self.chk_only_diff.setChecked(True)
        self.chk_only_diff.toggled.connect(self._fill_table)
        self.lbl_stat = QLabel()
        self.lbl_stat.setObjectName("MsHint")
        self.btn_export = QPushButton()
        self.btn_export.setObjectName("PlotGhostBtn")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("PlotHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.clicked.connect(self._show_help)
        ops.addWidget(self.btn_cmp)
        ops.addWidget(self.chk_only_diff)
        ops.addWidget(self.cb_dir_filter)
        ops.addWidget(self.ed_min_dt)
        ops.addWidget(self.lbl_stat, 1)
        ops.addWidget(self.btn_export)
        ops.addWidget(self.btn_help)
        root.addLayout(ops)

        # ===== 差异表 =====
        self.table = QTableWidget(0, 6)
        self.table.setObjectName("DiffTable")
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        for col in (0, 1, 2, 3):
            hh.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("MsHint")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        self.refresh_theme()
        self.retranslate()
        self._sync_controls()

    # ---------------- 载入 ----------------
    def _on_pick(self, side):
        t = self.app._t
        # 过滤器同 RecReplayDialog 的写法（那边也是字面量，两处保持一致）
        path, _ = QFileDialog.getOpenFileName(self, t("rd_pick", s=side.upper()), "",
                                              "CommTool 录制 (*.ctrec);;All Files (*)")
        if not path:
            return
        try:
            events, header = rec_replay.load(path)
        except Exception as e:      # RecordError（格式坏）与其它 IO 异常一律提示、不进选择
            self.app.toast(t("rd_load_failed", e=e), error=True)
            return
        setattr(self, "_path_%s" % side, path)
        setattr(self, "_events_%s" % side, events)
        getattr(self, "name_%s" % side).setText(
            t("rd_loaded", f=os.path.basename(path), n=len(events)))
        set_tooltip(getattr(self, "name_%s" % side), path)
        self._result = None
        self.table.setRowCount(0)
        self.lbl_stat.setText("")
        self._sync_controls()

    def _sync_controls(self):
        # 就绪＝两侧都选了文件，按 _path 判而不是 _events：空录制（有效文件但 0 事件）
        # 也是合法输入——「设备这次一条都没回」正是要比出来的差异，用事件数判会把它锁死。
        ready = bool(self._path_a and self._path_b)
        self.btn_cmp.setEnabled(ready)
        # 按筛选后的行判禁用：筛到一行不剩时导出只会得到一个只有表头的文件。
        self.btn_export.setEnabled(self._result is not None
                                   and bool(self._filtered_rows()))

    # ---------------- 比较 ----------------
    def _on_compare(self):
        if not (self._path_a and self._path_b):
            return
        self._result = rec_diff.compare(self._events_a, self._events_b)
        self._fill_table()
        self._sync_controls()

    def _filtered_rows(self):
        rows = list(self._result["rows"] if self._result else [])
        if self.chk_only_diff.isChecked():
            rows = [r for r in rows if r["kind"] != rec_diff.SAME]
        direction = self.cb_dir_filter.currentData() if hasattr(self, "cb_dir_filter") else ""
        min_dt = None
        if hasattr(self, "ed_min_dt"):
            raw = (self.ed_min_dt.text() or "").strip()
            if raw:
                try:
                    min_dt = float(raw)
                except ValueError:
                    min_dt = None
        if direction or min_dt is not None:
            rows = rec_diff.filter_rows(rows, direction=direction or None, min_dt=min_dt)
        return rows

    def _fill_table(self):
        t = self.app._t
        self.table.setRowCount(0)
        if self._result is None:
            return
        rows = self._filtered_rows()
        shown = rows[:_MAX_ROWS]
        c = chrome_for(self.app._theme_id())
        # 差异配色跟随主题：改动用强调色、单边缺失用告警色，同 SAME 行不上色
        tint = {
            rec_diff.DIFF: QColor(c["accent"]),
            rec_diff.ONLY_A: QColor(c["danger"]),
            rec_diff.ONLY_B: QColor(c["danger"]),
        }
        self.table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            kind_txt = t("rd_kind_%s" % r["kind"])
            cells = [
                kind_txt,
                "" if r["ia"] is None else str(r["ia"]),
                "" if r["ib"] is None else str(r["ib"]),
                "" if r["dt"] is None else "%+.3f" % r["dt"],
                self._hex_cell(r["bytes_a"], r["dir_a"]),
                self._hex_cell(r["bytes_b"], r["dir_b"]),
            ]
            for col, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                if col >= 4:
                    item.setFont(mono_font(9))
                    full = (r["bytes_a"] if col == 4 else r["bytes_b"])
                    if full:
                        set_tooltip(item, full.hex(" ").upper())
                else:
                    item.setFont(ui_font(9))
                if col in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if r["kind"] in tint:
                    item.setForeground(tint[r["kind"]])
                self.table.setItem(i, col, item)
        st = self._result["stats"]
        # 计数按当前筛选后的行统计：否则筛完表变短、汇总数字不变，两边矛盾。
        seen = {rec_diff.SAME: 0, rec_diff.DIFF: 0,
                rec_diff.ONLY_A: 0, rec_diff.ONLY_B: 0}
        for r in rows:
            if r["kind"] in seen:
                seen[r["kind"]] += 1
        parts = [t("rd_stat", same=seen[rec_diff.SAME], diff=seen[rec_diff.DIFF],
                   a=seen[rec_diff.ONLY_A], b=seen[rec_diff.ONLY_B])]
        if st["identical"]:
            parts.append(t("rd_identical"))
        if abs(st["max_dt"]) > 0.0005:
            parts.append(t("rd_max_dt", v="%+.3f" % st["max_dt"]))
        if self._result["degraded"]:
            parts.append(t("rd_degraded"))
        if len(rows) > _MAX_ROWS:
            parts.append(t("rd_truncated", n=_MAX_ROWS, total=len(rows)))
        self.lbl_stat.setText("  ·  ".join(parts))
        self._sync_controls()          # 筛选变化会改写可导出行数

    @staticmethod
    def _hex_cell(data, direction):
        if not data:
            return ""
        arrow = "←" if direction == "rx" else "→"
        body = data[:_HEX_PREVIEW].hex(" ").upper()
        if len(data) > _HEX_PREVIEW:
            body += " …(%dB)" % len(data)
        return "%s %s" % (arrow, body)

    # ---------------- 导出 ----------------
    def _on_export(self):
        t = self.app._t
        if self._result is None:
            return
        path, selected = QFileDialog.getSaveFileName(
            self, t("rd_export"), "session_diff.csv",
            t("rd_csv_filter") + ";;" + t("rd_jsonl_filter"))
        if not path:
            return
        try:
            rows = self._filtered_rows()
            if path.lower().endswith(".csv") and "jsonl" in (selected or "").lower():
                path = path[:-4] + ".jsonl"
            elif not path.lower().endswith((".csv", ".jsonl")):
                path += ".jsonl" if "jsonl" in (selected or "").lower() else ".csv"
            as_jsonl = path.lower().endswith(".jsonl")
            with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
                if as_jsonl:
                    f.write(rec_diff.rows_to_jsonl(rows))
                else:
                    f.write(rec_diff.rows_to_csv(rows))
            self.app.toast(t("rd_exported", path=path))
        except Exception as e:
            self.app.toast(t("rd_export_failed", e=e), error=True)

    def _show_help(self):
        """自绘主题化帮助窗（对齐录制/回放的 _show_help_dlg，不用系统 QMessageBox）。"""
        t = self.app._t
        dlg = QDialog(self)
        dlg.setWindowTitle(t("rd_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(720, 460)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(t("rd_help"))
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
            {"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(self.app._lang, "Close"))
        btn_close.setObjectName("PlotGhostBtn")
        btn_close.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_close)
        v.addLayout(row)
        c = chrome_for(self.app._theme_id())
        _set_win_titlebar_dark(dlg, self.app._theme().get("mode") == "dark")
        dlg.setStyleSheet(localize_qss(f"""
            QDialog {{ background-color: {c['window_bg']}; }}
            QLabel {{ color: {c['text']}; background: transparent;
                      font-family: 'Segoe UI'; font-size: 12px; }}
            QScrollArea {{ background: transparent; border: 1px solid {c['separator']};
                           border-radius: 6px; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QPushButton#PlotGhostBtn {{
                background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px;
                font-family: 'Segoe UI'; font-size: 12px; padding: 5px 16px;
            }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        """))
        dlg.exec_()

    # ---------------- 主题 / 语言 ----------------
    def refresh_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")
        c = chrome_for(self.app._theme_id())
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
        QPushButton#PlotGhostBtn {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
            font-family: 'Segoe UI'; font-size: 12px; padding: 4px 12px;
        }}
        QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#PlotGhostBtn:disabled {{ color: {c['text_sec']}; }}
        QPushButton#PlotPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 12px;
            font-weight: 500; padding: 4px 16px;
        }}
        QPushButton#PlotPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#PlotPrimaryBtn:disabled {{
            background-color: {c['input_bg']}; color: {c['text_sec']};
        }}
        QPushButton#PlotHelpBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 13px;
            font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
        }}
        QPushButton#PlotHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        QTableWidget#DiffTable {{
            background-color: {c['card_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
            gridline-color: {c['separator']};
            alternate-background-color: {c['input_bg']};
        }}
        QTableWidget#DiffTable::item:selected {{
            background-color: {c['accent']}; color: white;
        }}
        QHeaderView::section {{
            background-color: {c['input_bg']}; color: {c['text_sec']};
            border: 0px; border-bottom: 1px solid {c['separator']};
            padding: 4px 8px; font-family: 'Segoe UI'; font-size: 11px;
        }}
        """))
        _style_combo_popups(self, c)
        if self._result is not None:
            self._fill_table()       # 差异配色取自主题，换主题要重画

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("rd_title"))
        self.lbl_a.setText(t("rd_side_a"))
        self.lbl_b.setText(t("rd_side_b"))
        self.btn_a.setText(t("rd_choose"))
        self.btn_b.setText(t("rd_choose"))
        self.btn_cmp.setText(t("rd_compare"))
        self.chk_only_diff.setText(t("rd_only_diff"))
        self.btn_export.setText(t("rd_export"))
        set_tooltip(self.btn_help, t("rd_help_btn"))
        self.lbl_hint.setText(t("rd_hint"))
        self.table.setHorizontalHeaderLabels([
            t("rd_col_kind"), t("rd_col_ia"), t("rd_col_ib"),
            t("rd_col_dt"), t("rd_col_a"), t("rd_col_b")])
        # 文件名描述是套翻译模板拼的（"{f}（{n} 条）"），切语言要按新模板重渲染；
        # 未选文件时回到「未选择」。两种情况都要刷，否则切到英文后仍显示中文格式。
        for side in ("a", "b"):
            path = getattr(self, "_path_%s" % side)
            events = getattr(self, "_events_%s" % side)
            lbl = getattr(self, "name_%s" % side)
            if path:
                lbl.setText(t("rd_loaded", f=os.path.basename(path), n=len(events)))
            else:
                lbl.setText(t("rd_none"))
        if self._result is not None:
            self._fill_table()
