# -*- coding: utf-8 -*-
"""协议帧解析表 FrameParseDialog（多帧多规则，规则用列表编辑）。

规则区为列表：每条一行 = 帧头(hex,可空=兜底) + 字段定义(binproto: 名称=偏移:类型，
数值后加 x 显示十六进制，另支持 hexN/strN) + 删除。点「应用」生效。每个接收包视作一帧，
按帧头前缀匹配**第一条**命中的规则解析。

显示：QTabWidget —「全部」标签按时间看混合帧流（时间|规则|字段串|原始帧）；其余每条规则一个
标签，各自分列（时间+该规则字段+原始帧）。每个表支持 Ctrl+C / 右键 复制·全选、暂停、清空、导出 CSV。
不依赖 pyqtgraph。单实例非模态，复用刷新主题/语言；窗口带最小化/最大化、可拖动缩放。
"""
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QWidget,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QFileDialog, QMenu, QShortcut, QApplication,
                             QTabWidget, QScrollArea, QFrame, QSplitter)

import binproto
from theme import chrome_for
from fonts import localize_qss
from dialogs import _dialog_list_qss, _set_win_titlebar_dark

_MAX_ROWS = 1000   # 每个表最多保留行数（环形，超出删最旧）


def _fmt_num(v):
    return f"{v:.6g}" if isinstance(v, float) else str(v)


def _hex_str(v):
    """整数转十六进制显示（u8x 等用）：0x69 / 负数 -0x..；非整数原样。"""
    if isinstance(v, int):
        return f"0x{v:X}" if v >= 0 else f"-0x{-v:X}"
    return str(v)


def _disp(typ, v):
    """字段值 → 显示文本：None→''；hexN/strN 串原样；数值带 x→十六进制；否则十进制。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return _hex_str(v) if binproto.is_hex_num(typ) else _fmt_num(v)


def _set_interactive(table, widths):
    """列设为可拖拽(Interactive)+给初始宽度；用户可拖动列边界改宽，双击边界自动贴合内容。"""
    hh = table.horizontalHeader()
    hh.setStretchLastSection(False)
    for c, wpx in enumerate(widths):
        hh.setSectionResizeMode(c, QHeaderView.Interactive)
        table.setColumnWidth(c, wpx)


class _CopyTable(QTableWidget):
    """只读表格 + Ctrl+C 复制选中(TSV) + 右键「复制/全选」。供「全部」与各规则标签共用。"""

    def __init__(self, app, parent=None):
        super().__init__(0, 0, parent)
        self.app = app
        self.setObjectName("FrameTable")
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)   # 整行选择：点任何格只选行、永不选列
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)   # 按行滚，便于滚动锁定补偿
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionsClickable(False)   # 点表头不选中整列（拖边界改列宽不受影响）
        self.horizontalHeader().setHighlightSections(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        sc = QShortcut(QKeySequence.Copy, self)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(self._copy_selection)
        self._seq = 0       # 行自增序号（不随环形删行重排）
        self._follow = True # 跟随最新：True=在底部自动跟随；用户往上翻时置 False
        # 右下角浮动「↓最新」：翻上去时出现，点它恢复跟随（同接收数据区）。
        # 父对象用表格本身(不是 viewport)：viewport 子控件在流式刷新时会吞鼠标点击，点不动。
        self._btn_bottom = QPushButton(app._t("to_bottom"), self)
        self._btn_bottom.setObjectName("PlotToBottom")
        self._btn_bottom.setCursor(Qt.PointingHandCursor)
        self._btn_bottom.clicked.connect(self._go_bottom)
        self._btn_bottom.hide()
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _copy_selection(self):
        items = self.selectedItems()
        if not items:
            return
        rows = sorted({it.row() for it in items})
        cols = sorted({it.column() for it in items})
        grid = {(it.row(), it.column()): it.text() for it in items}
        lines = ["\t".join(grid.get((r, c), "") for c in cols) for r in rows]
        QApplication.clipboard().setText("\n".join(lines))

    def _show_menu(self, pos):
        c = chrome_for(self.app._theme_id())
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['card_bg']}; color: {c['text']};
                     border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
            QMenu::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
        """)
        act_copy = menu.addAction(self.app._t("ctx_copy"))
        act_all = menu.addAction(self.app._t("ctx_select_all"))
        chosen = menu.exec_(self.viewport().mapToGlobal(pos))
        menu.deleteLater()
        if chosen is act_copy:
            self._copy_selection()
        elif chosen is act_all:
            self.selectAll()

    def append_row(self, cells):
        self._seq += 1
        sb = self.verticalScrollBar()
        r = self.rowCount()
        self.insertRow(r)
        full = [str(self._seq)] + list(cells)        # 最前面加自增序号
        for c, val in enumerate(full):
            self.setItem(r, c, QTableWidgetItem(val))
        removed = 0
        while self.rowCount() > _MAX_ROWS:
            self.removeRow(0)
            removed += 1
        # 跟随态下滚到最新（紧跟 insertRow 的可靠上下文）；非跟随(往上翻看)时停住，
        # 删顶行时补偿滚动位让视图不跳
        if self._follow:
            self.scrollToBottom()
        elif removed:
            sb.setValue(max(0, sb.value() - removed))
        self._update_bottom_btn()

    def clear_rows(self):
        self.setRowCount(0)
        self._seq = 0
        self._update_bottom_btn()

    def _at_bottom(self):
        sb = self.verticalScrollBar()
        return sb.value() >= sb.maximum() - 2

    def _on_scroll(self, *_):
        # 用户滚动 → 据是否在底部更新跟随态（程序滚动到底也会进来，结果一致）
        self._follow = self._at_bottom()
        self._update_bottom_btn()

    def _go_bottom(self):
        # 点「↓最新」：恢复跟随 + 立即隐藏按钮。真正的滚动靠下一帧 append 的可靠上下文 +
        # 延迟兜底；直接在 clicked 里 scrollToBottom 会被表格视图事件处理吞掉(QTableWidget 特有)。
        self._follow = True
        self._update_bottom_btn()
        QTimer.singleShot(0, self.scrollToBottom)

    def _update_bottom_btn(self):
        want = self.verticalScrollBar().maximum() > 0 and not self._follow
        if want != self._btn_bottom.isVisible():
            self._btn_bottom.setVisible(want)
            if want:
                self._reposition_bottom_btn()
        elif want:
            # 已显示：插入新行后 viewport 会重新盖住按钮，需持续置顶，否则点击穿透到表格、点不动
            self._btn_bottom.raise_()

    def _reposition_bottom_btn(self):
        self._btn_bottom.adjustSize()
        g = self.viewport().geometry()    # viewport 在表格内的区域(含表头偏移)
        bw, bh = self._btn_bottom.width(), self._btn_bottom.height()
        self._btn_bottom.move(max(0, g.x() + g.width() - bw - 14),
                              max(0, g.y() + g.height() - bh - 12))
        self._btn_bottom.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._btn_bottom.isVisible():
            self._reposition_bottom_btn()

    def retranslate_btn(self):
        self._btn_bottom.setText(self.app._t("to_bottom"))


class FrameParseDialog(QDialog):
    def __init__(self, app):
        # parent=None：避免干扰主窗 WM_NCHITTEST（同 AutoReplyDialog 等）。主窗 _shutdown 显式收。
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(620, 420)
        self.resize(900, 580)

        self._paused = False
        self._rules = []          # [{header(bytes), header_str, fields:[(name,off,typ)], table}]
        self._rule_rows = []      # 规则编辑行：[{w, h(QLineEdit帧头), f(QLineEdit字段)}]
        self._all_table = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)
        self._split = QSplitter(Qt.Vertical)          # 规则区 / 数据表 之间可拖拽分隔条
        self._split.setObjectName("FrameSplit")
        self._split.setChildrenCollapsible(False)
        root.addWidget(self._split, 1)

        # ===== 规则区（上半，可往上拖小、把空间让给表格）=====
        top = QWidget()
        topv = QVBoxLayout(top)
        topv.setContentsMargins(0, 0, 0, 0)
        topv.setSpacing(6)
        # 顶行：「解析规则」标题 + 右上角「?」按钮（点开看完整说明 + 例子，原 lbl_help 太挤）
        head = QHBoxLayout()
        head.setSpacing(6)
        self.lbl_rules = QLabel()
        head.addWidget(self.lbl_rules)
        head.addStretch(1)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("FrameHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help_dlg)
        head.addWidget(self.btn_help)
        topv.addLayout(head)

        self._rows_host = QWidget()
        self._rows_v = QVBoxLayout(self._rows_host)
        self._rows_v.setContentsMargins(0, 0, 0, 0)
        self._rows_v.setSpacing(4)
        self._rows_v.addStretch(1)
        self._rows_host.setAutoFillBackground(False)
        self._rules_scroll = QScrollArea()
        self._rules_scroll.setObjectName("FrameRulesScroll")
        self._rules_scroll.setWidget(self._rows_host)
        self._rules_scroll.setWidgetResizable(True)
        self._rules_scroll.setFrameShape(QFrame.NoFrame)
        self._rules_scroll.setMinimumHeight(54)
        self._rules_scroll.viewport().setAutoFillBackground(False)
        topv.addWidget(self._rules_scroll, 1)

        # ===== 按钮行 =====
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_add = QPushButton()
        self.btn_add.setObjectName("PlotGhostBtn")
        self.btn_add.clicked.connect(lambda *_: self._add_rule_row())
        self.btn_apply = QPushButton()
        self.btn_apply.setObjectName("PlotPrimaryBtn")
        self.btn_apply.clicked.connect(self._apply_rules)
        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_apply)
        bar.addStretch(1)
        self.btn_pause = QPushButton()
        self.btn_pause.setObjectName("PlotGhostBtn")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("PlotGhostBtn")
        self.btn_clear.clicked.connect(self._clear)
        self.btn_export = QPushButton()
        self.btn_export.setObjectName("PlotGhostBtn")
        self.btn_export.clicked.connect(self._export_csv)
        bar.addWidget(self.btn_pause)
        bar.addWidget(self.btn_clear)
        bar.addWidget(self.btn_export)
        topv.addLayout(bar)

        # ===== 标签页（下半）=====
        self.tabs = QTabWidget()
        self.tabs.setObjectName("FrameTabs")
        self._split.addWidget(top)
        self._split.addWidget(self.tabs)
        self._split.setStretchFactor(0, 0)
        self._split.setStretchFactor(1, 1)
        self._split.setSizes([165, 380])

        self.retranslate()
        self._load_cfg()                 # 建规则行
        self._apply_rules(save=False)    # 按规则建标签
        self.refresh_theme()

    # ---------------- 规则行（列表）----------------
    def _add_rule_row(self, header="", fields=""):
        t = self.app._t
        row = QWidget()
        row.setObjectName("FrameRuleRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(6, 3, 6, 3)
        h.setSpacing(6)
        ed_h = QLineEdit(header)
        ed_h.setPlaceholderText(t("frame_hdr"))
        ed_h.setMaximumWidth(96)
        ed_f = QLineEdit(fields)
        ed_f.setPlaceholderText(t("frame_fields_ph"))
        ed_f.setToolTip(binproto.ALL_TYPES_TIP)
        btn_del = QPushButton("✕")
        btn_del.setObjectName("FrameDelBtn")
        btn_del.setFixedSize(26, 26)
        num = QLabel()
        num.setObjectName("FrameRuleNo")
        num.setMinimumWidth(18)
        rec = {"w": row, "h": ed_h, "f": ed_f, "num": num}
        btn_del.clicked.connect(lambda *_: self._del_rule_row(rec))
        h.addWidget(num)
        h.addWidget(QLabel(t("frame_hdr")))
        h.addWidget(ed_h)
        h.addWidget(QLabel(t("frame_fld")))
        h.addWidget(ed_f, 1)
        h.addWidget(btn_del)
        self._rows_v.insertWidget(self._rows_v.count() - 1, row)   # 插在末尾 stretch 之前
        self._rule_rows.append(rec)
        self._renumber_rules()

    def _del_rule_row(self, rec):
        rec["w"].setParent(None)
        rec["w"].deleteLater()
        if rec in self._rule_rows:
            self._rule_rows.remove(rec)
        self._renumber_rules()
        self._apply_rules()      # 删除立即生效：移除该规则并停掉其数据（删空则全部停）

    def _show_help_dlg(self):
        """弹独立窗口看帮助文档（富文本 + 多例子；原 lbl_help 占顶部太挤，挪到按需查看）。
        与 auto_reply_dialog._show_help_dlg 同形制：可滚动、可选中复制例子里的字符串。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("frame_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(760, 540)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("frame_help"))
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

    def reload_cfg(self):
        """从 QSettings 重新读 frame_rules → 清空当前规则行 → 重建。供配置导入后刷新。
        注意：_add_rule_row 会 connect textChanged → _save_cfg，构建期间临时改 _ar_rules 写回是按
        当前 widget 状态走，不会读 settings；清空+重建过程中 _save_cfg 会被频繁触发但结果就是当前内存
        状态写回 settings，对刚导入的值无破坏（用户接下来编辑也按新内存）。"""
        # 静默删除所有旧行（不触发 _apply_rules 的中间态）
        for rec in list(self._rule_rows):
            rec["w"].setParent(None)
            rec["w"].deleteLater()
        self._rule_rows.clear()
        self._load_cfg()
        self._renumber_rules()
        self._apply_rules()

    def _renumber_rules(self):
        for i, rec in enumerate(self._rule_rows):
            rec["num"].setText(f"{i + 1}")

    # ---------------- 持久化 ----------------
    def _load_cfg(self):
        s = self.app.settings
        text = s.value("frame_rules", "") or ""
        if not text:    # 迁移旧单规则配置（frame_header / frame_fields）
            oh = (s.value("frame_header", "") or "").strip()
            of = (s.value("frame_fields", "") or "").strip()
            if of:
                text = (oh + " | " + of) if oh else of
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            hdr_s, fld_s = (ln.split("|", 1) if "|" in ln else ("", ln))
            self._add_rule_row(hdr_s.strip(), fld_s.strip())
        if not self._rule_rows:        # 至少给一空行，方便上手
            self._add_rule_row()

    def _save_cfg(self):
        lines = []
        for rec in self._rule_rows:
            hdr_s = rec["h"].text().strip()
            fld_s = rec["f"].text().strip()
            if not fld_s:
                continue
            lines.append((hdr_s + " | " + fld_s) if hdr_s else fld_s)
        self.app.settings.setValue("frame_rules", "\n".join(lines))

    # ---------------- 规则解析 / 建表 ----------------
    def _apply_rules(self, *_a, save=True):
        rules = []
        for rec in self._rule_rows:
            hdr_s = rec["h"].text().strip()
            fld_s = rec["f"].text().strip()
            if not fld_s:
                continue
            try:
                header = binproto.parse_hex_header(hdr_s)
                fields = binproto.parse_field_spec(fld_s)
            except (ValueError, TypeError):
                self.app.toast(self.app._t("frame_rule_bad", line=(hdr_s + " | " + fld_s)), error=True)
                continue
            if not fields:
                continue
            rules.append({"header": header, "header_str": hdr_s or "*",
                          "fields": fields, "table": None})
        self._rules = rules
        self._rebuild_tabs()
        if save:
            self._save_cfg()

    def _rebuild_tabs(self):
        t = self.app._t
        self.tabs.clear()
        self._all_table = _CopyTable(self.app)
        all_cols = ["#", t("frame_col_time"), t("frame_col_rule"),
                    t("frame_col_fields"), t("frame_col_raw")]
        self._all_table.setColumnCount(len(all_cols))
        self._all_table.setHorizontalHeaderLabels(all_cols)
        _set_interactive(self._all_table, [46, 80, 56, 280, 460])   # 列宽可拖
        self.tabs.addTab(self._all_table, t("frame_tab_all"))
        for rule in self._rules:
            tbl = _CopyTable(self.app)
            cols = ["#", t("frame_col_time")] + [f[0] for f in rule["fields"]] + [t("frame_col_raw")]
            tbl.setColumnCount(len(cols))
            tbl.setHorizontalHeaderLabels(cols)
            # 宽度：# / 时间 + 每字段 90 + 原始帧 460；均可拖
            _set_interactive(tbl, [46, 80] + [90] * len(rule["fields"]) + [460])
            rule["table"] = tbl
            self.tabs.addTab(tbl, rule["header_str"])

    # ---------------- 数据入口 ----------------
    def feed(self, data: bytes):
        if self._paused or not self._rules:
            return
        buf = bytes(data)
        rule = next((r for r in self._rules if not r["header"] or buf.startswith(r["header"])), None)
        if rule is None:
            return
        vals = [binproto.read_field(buf, off, typ) for _n, off, typ in rule["fields"]]
        if all(v is None for v in vals):
            return
        ts = time.strftime("%H:%M:%S")
        raw = buf.hex(" ").upper()
        field_str = " ".join(f"{nm}={_disp(typ, v)}"
                             for (nm, _o, typ), v in zip(rule["fields"], vals) if v is not None)
        self._all_table.append_row([ts, rule["header_str"], field_str, raw])
        cells = [ts] + [_disp(typ, v) for (_n, _o, typ), v in zip(rule["fields"], vals)] + [raw]
        rule["table"].append_row(cells)

    # ---------------- 回调 ----------------
    def _toggle_pause(self):
        self._paused = not self._paused
        self.btn_pause.setText(self.app._t("plot_resume" if self._paused else "plot_pause"))

    def _clear(self):
        if self._all_table:
            self._all_table.clear_rows()
        for rule in self._rules:
            if rule["table"]:
                rule["table"].clear_rows()

    def _export_csv(self):
        tbl = self.tabs.currentWidget()
        if not isinstance(tbl, _CopyTable) or tbl.rowCount() == 0:
            self.app.toast(self.app._t("plot_no_data"), error=True)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.app._t("frame_export_title"), "frames.csv",
            "CSV (*.csv);;All Files (*)")
        if not path:
            return
        try:
            import csv
            cols = tbl.columnCount()
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow([tbl.horizontalHeaderItem(c).text() for c in range(cols)])
                for r in range(tbl.rowCount()):
                    w.writerow([(tbl.item(r, c).text() if tbl.item(r, c) else "")
                                for c in range(cols)])
            self.app.toast(self.app._t("saved_to", path=path))
        except Exception as e:
            self.app.toast(self.app._t("err_save_failed", e=e), error=True)

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
        QPushButton#PlotPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 12px;
            font-weight: 500; padding: 4px 16px;
        }}
        QPushButton#FrameDelBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 6px; font-size: 13px;
        }}
        QPushButton#FrameDelBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['danger']}; }}
        QPushButton#FrameHelpBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 13px;
            font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
        }}
        QPushButton#FrameHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        QPushButton#PlotToBottom {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 13px; padding: 4px 12px; font-family: 'Segoe UI'; font-size: 11px;
        }}
        QPushButton#PlotToBottom:hover {{ background-color: {c['accent_hover']}; }}
        QScrollArea#FrameRulesScroll {{
            background: transparent; border: 1px solid {c['separator']}; border-radius: 6px;
        }}
        QScrollArea#FrameRulesScroll > QWidget > QWidget {{ background: transparent; }}
        QWidget#FrameRuleRow {{ background: transparent; }}
        QSplitter#FrameSplit::handle:vertical {{ height: 5px; background: transparent; }}
        QSplitter#FrameSplit::handle:vertical:hover {{ background: {c['accent']}; }}
        QTabWidget::pane {{ border: 1px solid {c['separator']}; border-radius: 8px; top: -1px; }}
        QTabBar::tab {{
            background: {c['input_bg']}; color: {c['text_sec']}; padding: 5px 12px;
            border: 1px solid {c['separator']}; border-bottom: 0px; margin-right: 2px;
            border-top-left-radius: 6px; border-top-right-radius: 6px;
            font-family: 'Segoe UI'; font-size: 11px;
        }}
        QTabBar::tab:selected {{ background: {c['card_bg']}; color: {c['text']}; }}
        QTableWidget#FrameTable {{
            background-color: {c['card_bg']}; color: {c['text']};
            gridline-color: {c['separator']}; border: 0px;
            font-family: 'Consolas'; font-size: 12px; outline: 0px;
        }}
        QTableWidget#FrameTable::item {{ padding: 2px 6px; }}
        QTableWidget#FrameTable::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
        QHeaderView::section {{
            background-color: {c['input_bg']}; color: {c['text_sec']}; border: 0px;
            border-right: 1px solid {c['separator']}; border-bottom: 1px solid {c['separator']};
            padding: 4px 6px; font-family: 'Segoe UI'; font-size: 11px;
        }}
        """))

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("frame_title"))
        self.lbl_rules.setText(t("frame_rules"))
        self.btn_help.setToolTip(t("frame_help_btn"))
        self.btn_add.setText(t("frame_add_rule"))
        self.btn_apply.setText(t("frame_apply"))
        self.btn_pause.setText(t("plot_resume" if self._paused else "plot_pause"))
        self.btn_clear.setText(t("plot_clear"))
        self.btn_export.setText(t("plot_export"))
        for rec in self._rule_rows:        # 行内占位符随语言
            rec["h"].setPlaceholderText(t("frame_hdr"))
            rec["f"].setPlaceholderText(t("frame_fields_ph"))
        if self._all_table is not None:
            self.tabs.setTabText(0, t("frame_tab_all"))
            self._all_table.setHorizontalHeaderLabels(
                ["#", t("frame_col_time"), t("frame_col_rule"), t("frame_col_fields"), t("frame_col_raw")])
            self._all_table.retranslate_btn()
            for i, rule in enumerate(self._rules):
                cols = ["#", t("frame_col_time")] + [f[0] for f in rule["fields"]] + [t("frame_col_raw")]
                rule["table"].setHorizontalHeaderLabels(cols)
                rule["table"].retranslate_btn()
                self.tabs.setTabText(1 + i, rule["header_str"])

    # ---------------- 生命周期 ----------------
    def closeEvent(self, e):
        self._save_cfg()
        super().closeEvent(e)
