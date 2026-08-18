# -*- coding: utf-8 -*-
"""Modbus 主机轮询对话框 ModbusMasterDialog。

每行 = [启用] 名称 | 从机ID | 功能码 | 起始地址 | 数量/写值 | 周期ms → 值 | 状态 [✕]。
轮询引擎在 main_window（_mbm_* 系列）：本对话框只是编辑器 + 结果展示，规则存 app._mbm_rules。
顶部「启用轮询」= app._mbm_on，「传输」= app._mbm_variant（''=按连接自动 / 'rtu' / 'tcp'）。
单实例非模态，复用主窗刷新主题/语言。读类功能码用「数量」，写类(05/06)用同一格当「写值」。
"""
import logging

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QWidget,
                             QPushButton, QCheckBox, QComboBox, QScrollArea, QFrame,
                             QSplitter, QTabBar, QInputDialog)

from ui.theme import chrome_for
from ui.fonts import localize_qss
from ui.dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from ui.ui_tips import set_tooltip
from ui.split_persist import load_split_sizes, save_split_sizes, sync_splitter_group

_log = logging.getLogger(__name__)

# 功能码下拉项：(code, i18n_key)。读 01-04 / 写单 05-06 / 写多 0F-10。
FUNC_ITEMS = [(0x01, "mbm_f1"), (0x02, "mbm_f2"), (0x03, "mbm_f3"),
              (0x04, "mbm_f4"), (0x05, "mbm_f5"), (0x06, "mbm_f6"),
              (0x0F, "mbm_f7"), (0x10, "mbm_f8"),
              (0x08, "mbm_f8d"), (0x0B, "mbm_f11"),
              (0x11, "mbm_f17"), (0x16, "mbm_f22"),
              (0x17, "mbm_f23"), (0x2B, "mbm_f43")]
READ_FUNCS = (0x01, 0x02, 0x03, 0x04)
# Simplified one-shot strip: common daily poke FCs only.
ONESHOT_FUNCS = [(0x01, "mbm_f1"), (0x02, "mbm_f2"), (0x03, "mbm_f3"),
                 (0x04, "mbm_f4"), (0x05, "mbm_f5"), (0x06, "mbm_f6")]
WRITE_MULTI = (0x0F, 0x10)

# 固定列宽（不在可拖 splitter 内）：复选框 / 状态 / 删除。
_CB_W, _ST_W, _DEL_W = 22, 120, 26
# 可拖 splitter 内的列：(i18n键, 最小宽, 初始宽)。每个列边界都可左右拖、所有行+表头同步。
# 顺序即列顺序：名称/从机ID/功能码/起始地址/数量写值/周期ms/值。功能码初始改窄(120)。
_SPLIT_COLS = [("mbm_col_name", 80, 130), ("mbm_col_unit", 44, 64),
               ("mbm_col_func", 92, 120), ("mbm_col_addr", 50, 70),
               ("mbm_col_qty", 100, 200), ("mbm_col_period", 50, 70),
               ("mbm_col_value", 80, 170)]
_DEFAULT_SPLIT = [c[2] for c in _SPLIT_COLS]


class ModbusMasterDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)   # 不传 parent：与自动应答对话框同理，避免无边框主窗 resize 失效
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(820, 360)
        self.resize(1040, 460)

        self._rows = []
        self._view_name = ""
        self._row_rule_index = []  # maps visible row -> global _mbm_rules index
        # 名称~值七列的共享拖动比例，所有行与表头同步；从 settings 恢复上次拖好的列宽，
        # 没存过则 None → 用 _DEFAULT_SPLIT。拖动后在 _sync_splits 里写回 settings 持久化。
        self._split_sizes = self._load_split_sizes()
        self._syncing_split = False        # 防止同步分隔条递归
        self._dirty = False                # 编辑只改草稿；显式点“应用”后才重启轮询，避免误写

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        # 顶栏：启用轮询 + 传输变体 + 添加 + 帮助
        top = QHBoxLayout()
        top.setContentsMargins(9, 0, 0, 0)
        self.cb_enable = QCheckBox()
        self.cb_enable.setObjectName("ArEnable")
        self.cb_enable.setChecked(bool(getattr(app, "_mbm_on", False)))
        self.cb_enable.toggled.connect(self._on_enable)
        top.addWidget(self.cb_enable)
        top.addSpacing(14)
        self.lbl_variant = QLabel()
        top.addWidget(self.lbl_variant)
        self.cb_variant = QComboBox()
        self.cb_variant.setFixedWidth(150)
        self.cb_variant.currentIndexChanged.connect(self._on_variant)
        top.addWidget(self.cb_variant)
        top.addSpacing(14)
        self.cb_echo = QCheckBox()              # 串口本地回显模式（适配器回显发出的帧时勾选）
        self.cb_echo.setChecked(bool(getattr(app, "_mbm_echo", False)))
        self.cb_echo.toggled.connect(self._on_echo)
        top.addWidget(self.cb_echo)
        top.addStretch(1)
        self.btn_apply = QPushButton()
        self.btn_apply.setObjectName("PlotGhostBtn")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._commit)
        top.addWidget(self.btn_apply)
        self.btn_add = QPushButton()
        self.btn_add.setObjectName("PlotGhostBtn")
        self.btn_add.clicked.connect(lambda *_: (self._add_row(), self._schedule()))
        top.addWidget(self.btn_add)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("ArHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help)
        top.addWidget(self.btn_help)
        root.addLayout(top)

        # One-shot strip: poke once without Apply/Enable/period.
        os_row = QHBoxLayout()
        os_row.setContentsMargins(9, 0, 0, 0)
        os_row.setSpacing(6)
        self.lbl_os = QLabel()
        self.lbl_os.setObjectName("ArDesc")
        os_row.addWidget(self.lbl_os)
        self.ed_os_unit = QLineEdit("1")
        self.ed_os_unit.setFixedWidth(44)
        os_row.addWidget(self.ed_os_unit)
        self.cb_os_func = QComboBox()
        self.cb_os_func.setMinimumWidth(120)
        self.cb_os_func.currentIndexChanged.connect(self._os_func_changed)
        os_row.addWidget(self.cb_os_func)
        self.ed_os_addr = QLineEdit("0")
        self.ed_os_addr.setFixedWidth(64)
        os_row.addWidget(self.ed_os_addr)
        self.ed_os_qty = QLineEdit("1")
        self.ed_os_qty.setFixedWidth(88)
        os_row.addWidget(self.ed_os_qty)
        self.btn_os_run = QPushButton()
        self.btn_os_run.setObjectName("PlotGhostBtn")
        self.btn_os_run.clicked.connect(self._oneshot_run)
        os_row.addWidget(self.btn_os_run)
        self.btn_os_cancel = QPushButton()
        self.btn_os_cancel.setObjectName("PlotGhostBtn")
        self.btn_os_cancel.setEnabled(False)
        self.btn_os_cancel.clicked.connect(self._oneshot_cancel)
        os_row.addWidget(self.btn_os_cancel)
        self.lbl_os_result = QLabel("—")
        self.lbl_os_result.setObjectName("ArDesc")
        self.lbl_os_result.setMinimumWidth(160)
        os_row.addWidget(self.lbl_os_result, 1)
        root.addLayout(os_row)

        view_row = QHBoxLayout()
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.currentChanged.connect(self._on_view_changed)
        view_row.addWidget(self.tabs, 1)
        self.btn_add_view = QPushButton("+")
        self.btn_add_view.setObjectName("PlotGhostBtn")
        self.btn_add_view.setFixedWidth(28)
        self.btn_add_view.clicked.connect(self._add_view)
        view_row.addWidget(self.btn_add_view)
        self.btn_del_view = QPushButton("-")
        self.btn_del_view.setObjectName("PlotGhostBtn")
        self.btn_del_view.setFixedWidth(28)
        self.btn_del_view.clicked.connect(self._del_view)
        view_row.addWidget(self.btn_del_view)
        root.addLayout(view_row)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("ArDesc")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setContentsMargins(9, 0, 0, 0)
        root.addWidget(self.lbl_hint)

        # 列标题
        self.hdr = QWidget()
        hh = QHBoxLayout(self.hdr)
        self._hdr_layout = hh
        # 左右各 +1px 补偿数据行所在滚动区(ArScroll)的 1px 边框内缩，使表头与行同宽对齐
        hh.setContentsMargins(10, 2, 7, 2)
        hh.setSpacing(6)
        self._hdr_labels = []
        lead = QLabel()                 # 复选框列占位：与数据行的启用勾选框对齐
        lead.setFixedWidth(_CB_W)
        hh.addWidget(lead)

        # 名称~值 七列全放进可拖 QSplitter：每个列边界都能左右拖、所有行+表头同步
        self._hdr_split = self._make_split()
        for key, minw, _initw in _SPLIT_COLS:
            lb = QLabel()
            lb.setProperty("k", key)
            lb.setMinimumWidth(minw)
            self._hdr_split.addWidget(lb)
            self._hdr_labels.append(lb)
        self._hdr_split.setSizes(self._split_sizes or _DEFAULT_SPLIT)
        self._hdr_split.splitterMoved.connect(lambda *_: self._sync_splits(self._hdr_split))
        hh.addWidget(self._hdr_split, 1)

        lb_st = QLabel()                # 状态：固定列，不在 splitter 内
        lb_st.setProperty("k", "mbm_col_status")
        lb_st.setFixedWidth(_ST_W)
        hh.addWidget(lb_st)
        self._hdr_labels.append(lb_st)
        hdel = QWidget()                # 删除按钮列占位：用真实控件而非 addSpacing，与数据行像素对齐
        hdel.setFixedWidth(_DEL_W)
        hh.addWidget(hdel)
        root.addWidget(self.hdr)

        # 行滚动区
        self.rows_host = QWidget()
        self.rows_v = QVBoxLayout(self.rows_host)
        self.rows_v.setContentsMargins(0, 0, 0, 0)
        self.rows_v.setSpacing(4)
        self.rows_v.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("ArScroll")
        self.scroll.setWidget(self.rows_host)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._update_header_scroll_margin)
        root.addWidget(self.scroll, 1)

        self._rebuild_tabs()
        self.reload_rows()
        self.retranslate()
        self.refresh_theme()
        QTimer.singleShot(0, self._update_header_scroll_margin)

    def _make_split(self):
        sp = QSplitter(Qt.Horizontal)
        sp.setObjectName("MbmSplit")
        sp.setChildrenCollapsible(False)
        sp.setHandleWidth(8)
        return sp

    def _load_split_sizes(self):
        """从 settings 读上次拖好的七列宽；列数不符/非法则 None（用默认）。"""
        return load_split_sizes(
            self.app.settings, "modbus_master_split", len(_DEFAULT_SPLIT))

    def _sync_splits(self, src):
        """任一行(或表头)拖动分隔条 → 所有行 + 表头同步到相同比例（列对齐），并持久化列宽。"""
        def _persist(sizes):
            self._split_sizes = sizes
            # sync 放在 closeEvent，避免拖动时频繁刷盘
            save_split_sizes(self.app.settings, "modbus_master_split", sizes)

        peers = [getattr(self, "_hdr_split", None)] + [r.get("split") for r in self._rows]
        sync_splitter_group(
            src, peers,
            get_busy=lambda: self._syncing_split,
            set_busy=lambda v: setattr(self, "_syncing_split", v),
            on_sizes=_persist,
        )

    def closeEvent(self, e):
        self.app.settings.sync()   # 把拖动列宽刷到磁盘
        super().closeEvent(e)

    def _update_header_scroll_margin(self, *_args):
        """数据区出现垂直滚动条时，表头预留同宽空间，保持 splitter 像素对齐。"""
        bar = self.scroll.verticalScrollBar()
        extra = bar.sizeHint().width() if bar.maximum() > bar.minimum() else 0
        self._hdr_layout.setContentsMargins(10, 2, 7 + extra, 2)
        QTimer.singleShot(0, lambda: self._sync_splits(self._hdr_split))

    # ---------------- 行 ----------------
    def _qty_tip_for(self, code):
        tip = self.app._t("mbm_qty_tip")
        code = int(code or 0)
        if code == 0x08:
            tip = tip + "\n" + self.app._t("mbm_diag_sub_tip")
        elif code == 0x16:
            tip = tip + "\n" + self.app._t("mbm_mask_tip")
        elif code == 0x2B:
            tip = tip + "\n" + self.app._t("mbm_devid_tip")
        return tip

    def _add_row(self, rule=None):
        rule = rule or {}
        r = QWidget()
        r.setObjectName("ArRow")
        rh = QHBoxLayout(r)
        rh.setContentsMargins(9, 0, 6, 0)
        rh.setSpacing(6)

        cb = QCheckBox()
        cb.setFixedWidth(_CB_W)
        cb.setChecked(bool(rule.get("enabled", True)))
        cb.toggled.connect(self._schedule)
        rh.addWidget(cb)

        ed_name = QLineEdit(str(rule.get("name", "") or ""))
        ed_name.setMinimumWidth(_SPLIT_COLS[0][1])
        ed_name.textChanged.connect(self._schedule)

        unit_val = rule.get("unit", 1)
        ed_unit = QLineEdit("" if unit_val is None else str(unit_val))
        ed_unit.setMinimumWidth(_SPLIT_COLS[1][1])
        ed_unit.textChanged.connect(self._schedule)

        cb_func = QComboBox()
        cb_func.setMinimumWidth(_SPLIT_COLS[2][1])
        for code, key in FUNC_ITEMS:
            cb_func.addItem(self.app._t(key), code)
        idx = next((n for n, (code, _k) in enumerate(FUNC_ITEMS)
                    if code == int(rule.get("func", 3) or 3)), 2)
        cb_func.setCurrentIndex(idx)
        cb_func.currentIndexChanged.connect(self._schedule)

        addr_val = rule.get("addr", 0)
        ed_addr = QLineEdit("" if addr_val is None else str(addr_val))
        ed_addr.setMinimumWidth(_SPLIT_COLS[3][1])
        ed_addr.textChanged.connect(self._schedule)

        # 读类=数量；写单(05/06)=写值；写多(0F/10)=多值(逗号/空格分隔)。共用一格。
        func0 = int(rule.get("func", 3) or 3)
        if func0 in READ_FUNCS:
            qty_val = rule.get("qty", 1)
            qty_val = "" if qty_val is None else qty_val
        elif func0 in WRITE_MULTI:
            qty_val = ", ".join(str(x) for x in (rule.get("wvals") or []))
        elif func0 == 0x17:
            rq = rule.get("qty", 1)
            wa = rule.get("write_addr")
            if wa is None:
                rw = rule.get("rw") or {}
                wa = rw.get("write_addr", rule.get("addr", 0))
            vals = rule.get("wvals") or []
            if isinstance(vals, (list, tuple)):
                vals = " ".join(str(x) for x in vals)
            qty_val = "%s @ %s : %s" % (rq, wa, vals)
        else:
            qty_val = rule.get("wval")
            qty_val = "" if qty_val is None else qty_val
            # FC08: show "sub:data" so the sub-function is editable without a
            # dedicated column (still carried as diag_sub on collect).
            if int(rule.get("func") or 0) == 0x08:
                sub = rule.get("diag_sub", 0)
                if sub in (None, ""):
                    sub = 0
                data = qty_val if qty_val != "" else 0
                qty_val = "%s:%s" % (sub, data)
            elif int(rule.get("func") or 0) == 0x16:
                am = rule.get("and_mask", rule.get("diag_sub", 0xFFFF))
                om = rule.get("or_mask", rule.get("diag_data", qty_val if qty_val != "" else 0))
                if am in (None, ""):
                    am = 0xFFFF
                if om in (None, ""):
                    om = 0
                qty_val = "%s:%s" % (am, om)
            elif int(rule.get("func") or 0) == 0x2B:
                rc = rule.get("read_code", rule.get("diag_sub", 1))
                oid = rule.get("object_id", rule.get("diag_data", 0))
                if rc in (None, ""):
                    rc = 1
                if oid in (None, ""):
                    oid = 0
                qty_val = "%s:%s" % (rc, oid)
        ed_qty = QLineEdit(str(qty_val))
        ed_qty.setMinimumWidth(_SPLIT_COLS[4][1])
        set_tooltip(ed_qty, self._qty_tip_for(rule.get("func")))
        ed_qty.textChanged.connect(self._schedule)

        period_val = rule.get("period", 1000)
        ed_period = QLineEdit("" if period_val is None else str(period_val))
        ed_period.setMinimumWidth(_SPLIT_COLS[5][1])
        ed_period.textChanged.connect(self._schedule)

        lbl_val = QLabel("—")
        lbl_val.setObjectName("MbmVal")
        lbl_val.setMinimumWidth(_SPLIT_COLS[6][1])
        lbl_val.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # 名称~值七列全部放入 splitter，与表头逐列对齐并同步拖动。
        split = self._make_split()
        for widget in (ed_name, ed_unit, cb_func, ed_addr, ed_qty, ed_period, lbl_val):
            split.addWidget(widget)
        split.setSizes(self._split_sizes or _DEFAULT_SPLIT)
        split.splitterMoved.connect(lambda *_: self._sync_splits(split))
        rh.addWidget(split, 1)

        lbl_st = QLabel("—")
        lbl_st.setObjectName("MbmSt")
        lbl_st.setFixedWidth(_ST_W)
        rh.addWidget(lbl_st)

        btn_x = QPushButton("✕")
        btn_x.setObjectName("ArDelBtn")
        btn_x.setFixedSize(26, 26)
        rec = {"w": r, "enable": cb, "name": ed_name, "unit": ed_unit, "func": cb_func,
               "addr": ed_addr, "qty": ed_qty, "period": ed_period,
               "val": lbl_val, "st": lbl_st, "split": split,
               # 08 的子功能没有控件（只能由 JSON 配），存下来原样带回 _collect，
               # 否则一次应用就把它重置成 0（=回环诊断）。
               "diag_sub": rule.get("diag_sub")}
        # Re-bind: the earlier currentIndexChanged only dirties; this one
        # reshapes qty when entering/leaving FC08.
        cb_func.currentIndexChanged.connect(
            lambda *_a, _r=rec: self._on_row_func_changed(_r))

        def _del():
            r.setParent(None)
            r.deleteLater()
            if rec in self._rows:
                self._rows.remove(rec)
            self._schedule()

        btn_x.clicked.connect(lambda *_: _del())
        rh.addWidget(btn_x)

        self.rows_v.insertWidget(self.rows_v.count() - 1, r)   # 在末尾 stretch 之前
        self._rows.append(rec)

    def _views(self):
        """Tab order follows view creation order, not rule order.

        Deriving it from the rule list would make tabs jump around whenever
        rules are added or removed. The default view is always first.
        """
        names = [""]
        for g in list(getattr(self.app, "_mbm_views", None) or []):
            g = str(g or "")
            if g and g not in names:
                names.append(g)
        for rule in getattr(self.app, "_mbm_rules", []) or []:
            g = str(rule.get("group", "") or "")
            if g and g not in names:
                names.append(g)
        return names

    def _rebuild_tabs(self, keep=None):
        names = self._views()
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for g in names:
            self.tabs.addTab(g if g else self.app._t("mbm_view_default"))
        if keep is None:
            keep = self._view_name
        idx = names.index(keep) if keep in names else 0
        self._view_name = names[idx]
        self.tabs.setCurrentIndex(idx)
        self.tabs.blockSignals(False)

    def _on_view_changed(self, index):
        if index < 0:
            return
        if self._dirty:
            self._commit()
            if self._dirty:          # refused (device scan busy): stay put
                self._rebuild_tabs(keep=self._view_name)
                return
        names = self._views()
        if 0 <= index < len(names):
            self._view_name = names[index]
        self.reload_rows()

    def _add_view(self):
        text, ok = QInputDialog.getText(
            self, self.app._t("mbm_view_add"), self.app._t("mbm_view_name"))
        if not ok:
            return
        name = (text or "").strip()[:40]
        if not name:
            return
        views = [str(v) for v in (getattr(self.app, "_mbm_views", None) or []) if v]
        if name not in views:
            views.append(name)
        self.app._mbm_views = views
        if hasattr(self.app, "_mbm_save_views"):
            self.app._mbm_save_views()
        self._rebuild_tabs(keep=name)
        self.reload_rows()

    def _del_view(self):
        name = self._view_name
        if not name:
            return
        if self._dirty:
            self._commit()
            if self._dirty:
                return
        # 删视图会当场把这些规则的分组清空并落盘，没有 undo；
        # 而 + / - 两个按钮相邻且只有 28×28，很容易按错。
        count = sum(1 for r in (getattr(self.app, "_mbm_rules", []) or [])
                    if str(r.get("group", "") or "") == name)
        if not self.app._confirm_dlg(self.app._t("mbm_view_del_title"),
                                     self.app._t("mbm_view_del_body",
                                                 name=name, n=count),
                                     ok_text=self.app._t("device_delete")):
            return
        for r in getattr(self.app, "_mbm_rules", []) or []:
            if str(r.get("group", "") or "") == name:
                r["group"] = ""
        self.app._mbm_views = [v for v in (getattr(self.app, "_mbm_views", None) or [])
                              if v != name]
        if hasattr(self.app, "_mbm_save_views"):
            self.app._mbm_save_views()
        if hasattr(self.app, "_mbm_save_rules"):
            self.app._mbm_save_rules()
        self._rebuild_tabs(keep="")
        self.reload_rows()

    def reload_rows(self):
        self._rebuild_tabs()      # imported rules may carry unknown groups
        for rec in self._rows:
            rec["w"].setParent(None)
            rec["w"].deleteLater()
        self._rows = []
        self._row_rule_index = []
        for gi, rule in enumerate(getattr(self.app, "_mbm_rules", []) or []):
            if str(rule.get("group", "") or "") != self._view_name:
                continue
            self._add_row(rule)
            self._row_rule_index.append(gi)
        # 回填已有轮询结果
        results = getattr(self.app, "_mbm_results", {}) or {}
        for i, res in results.items():
            if isinstance(i, int):
                self.update_result(i, res.get("status", ""), res.get("text", ""))
        self._dirty = False
        if hasattr(self, "btn_apply"):
            self.btn_apply.setEnabled(False)

    def reload_config(self):
        """配置导入后同步顶栏开关/传输选项及规则，且不触发保存回调。"""
        for cb, value in ((self.cb_enable, self.app._mbm_on),
                          (self.cb_echo, self.app._mbm_echo)):
            cb.blockSignals(True)
            cb.setChecked(bool(value))
            cb.blockSignals(False)
        self.cb_variant.blockSignals(True)
        idx = self.cb_variant.findData(self.app._mbm_variant)
        self.cb_variant.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_variant.blockSignals(False)
        self._rebuild_tabs()
        self.reload_rows()

    def _on_row_func_changed(self, rec):
        """Keep the qty cell in the shape the active function expects."""
        code = rec["func"].currentData()
        ed = rec["qty"]
        raw = (ed.text() or "").strip()
        if code == 0x08:
            if ":" not in raw:
                # Former read qty / write value -> loopback data under sub 0.
                data = raw if raw != "" else "0"
                ed.blockSignals(True)
                ed.setText("0:%s" % data)
                ed.blockSignals(False)
        elif code == 0x16:
            if ":" not in raw:
                data = raw if raw != "" else "0"
                ed.blockSignals(True)
                ed.setText("0xFFFF:%s" % data)
                ed.blockSignals(False)
        elif code == 0x2B:
            if ":" not in raw:
                ed.blockSignals(True)
                ed.setText("1:0")
                ed.blockSignals(False)
        elif ":" in raw and raw.count(":") == 1 and "@" not in raw:
            # Leaving 08: drop the sub half, keep data as the cell value.
            # Read funcs need qty >= 1 -- FC08 data 0 must not become qty 0.
            _sub, data = raw.split(":", 1)
            data = data.strip() or "0"
            if code in READ_FUNCS:
                try:
                    n = int(data, 0) if data.lower().startswith("0x") else int(data)
                except ValueError:
                    n = 0
                data = "1" if n < 1 else str(n)
            ed.blockSignals(True)
            ed.setText(data)
            ed.blockSignals(False)
        set_tooltip(ed, self._qty_tip_for(code))
        self._schedule()

    def _collect(self):
        out = []
        for rec in self._rows:
            code = rec["func"].currentData()
            field = rec["qty"].text().strip()
            qty_field = field
            wval_field = field
            wvals_field = field
            write_addr = rec["addr"].text().strip()
            if code == 0x17:
                raw = field
                at, colon = raw.find("@"), raw.find(":")
                if 0 <= at < colon:
                    left, right = raw.split(":", 1)
                    qty_part, wa_part = left.split("@", 1)
                    qty_field = qty_part.strip()
                    write_addr = wa_part.strip()
                    wvals_field = right.strip()
                else:
                    toks = raw.replace(",", " ").split()
                    qty_field = toks[0] if toks else "1"
                    wvals_field = " ".join(toks[1:])
                wval_field = wvals_field
            out.append({
                "enabled": rec["enable"].isChecked(),
                "name": rec["name"].text(),
                "group": self._view_name,
                "unit": rec["unit"].text().strip(),
                "func": code,
                "addr": rec["addr"].text().strip(),
                "qty": qty_field,
                "wval": wval_field,
                "wvals": wvals_field,
                "write_addr": write_addr,
                "period": rec["period"].text().strip(),
            })
            if code == 0x08:
                # Qty for 08 is always "sub:data". Bare number = DATA with sub=0
                # (safe loopback). Never treat bare "1" as sub-function 1 -- that
                # is Restart Communications and fires when switching FC03->08.
                # Clearing leftover wval_field ("12:7") is intentional.
                raw = (rec["qty"].text() or "").strip()
                if ":" in raw:
                    left, right = raw.split(":", 1)
                    out[-1]["diag_sub"] = left.strip() or "0"
                    out[-1]["wval"] = right.strip() or "0"
                else:
                    out[-1]["diag_sub"] = "0"
                    out[-1]["wval"] = raw if raw != "" else "0"
                out[-1]["qty"] = "1"
            elif code == 0x16:
                raw = (rec["qty"].text() or "").strip()
                if ":" in raw:
                    left, right = raw.split(":", 1)
                    out[-1]["and_mask"] = left.strip() or "0xFFFF"
                    out[-1]["or_mask"] = right.strip() or "0"
                    out[-1]["wval"] = "%s:%s" % (out[-1]["and_mask"], out[-1]["or_mask"])
                else:
                    out[-1]["and_mask"] = "0xFFFF"
                    out[-1]["or_mask"] = raw if raw != "" else "0"
                    out[-1]["wval"] = "%s:%s" % (out[-1]["and_mask"], out[-1]["or_mask"])
                out[-1]["qty"] = "1"
            elif code == 0x2B:
                raw = (rec["qty"].text() or "").strip()
                if ":" in raw:
                    left, right = raw.split(":", 1)
                    out[-1]["read_code"] = left.strip() or "1"
                    out[-1]["object_id"] = right.strip() or "0"
                else:
                    out[-1]["read_code"] = raw if raw != "" else "1"
                    out[-1]["object_id"] = "0"
                out[-1]["wval"] = "%s:%s" % (out[-1]["read_code"], out[-1]["object_id"])
                out[-1]["qty"] = "1"
            elif rec.get("diag_sub") is not None:
                out[-1]["diag_sub"] = rec["diag_sub"]
        return out

    def _schedule(self):
        # 只标记草稿，不自动提交。尤其功能码从读切到写时，必须由用户显式应用才允许发送。
        if not self._dirty:
            self._clear_result_labels(self.app._t("mbm_st_pending"))
        self._dirty = True
        self.btn_apply.setEnabled(True)

    def _os_func_changed(self, _idx=None):
        """Swap qty field tip: read quantity vs write value."""
        t = self.app._t
        func = self.cb_os_func.currentData()
        if func in (0x05, 0x06):
            set_tooltip(self.ed_os_qty, t("mbm_os_wval_tip"))
            self.ed_os_qty.setPlaceholderText(t("mbm_os_wval_ph"))
        else:
            set_tooltip(self.ed_os_qty, t("mbm_os_qty_tip"))
            self.ed_os_qty.setPlaceholderText(t("mbm_os_qty_ph"))
        self.lbl_os_result.setText("")
        self.lbl_os_result.setStyleSheet("")

    def _oneshot_set_busy(self, busy):
        # Use __dict__ so __new__-constructed test stubs (no QWidget init) work.
        btn = self.__dict__.get("btn_os_run")
        if btn is not None:
            btn.setEnabled(not busy)
        btn = self.__dict__.get("btn_os_cancel")
        if btn is not None:
            btn.setEnabled(bool(busy))

    def _oneshot_cancel(self):
        """Abort an in-flight one-shot (slow link / long timeout)."""
        stop = getattr(self.app, "_stop_device_scan", None)
        if callable(stop):
            stop(cancelled=True)

    def _oneshot_run(self):
        """One-shot read/write via the existing half-duplex engine (_start_device_scan)."""
        if self._scan_locked():
            return
        try:
            from modbus import modbus_master as _mm
            draft = {
                "enabled": True,
                "name": "oneshot",
                "unit": self.ed_os_unit.text().strip() or "1",
                "func": self.cb_os_func.currentData(),
                "addr": self.ed_os_addr.text().strip() or "0",
                "period": 0x7FFFFFFF,
            }
            raw = self.ed_os_qty.text().strip() or "1"
            func = draft["func"]
            if func in (0x05, 0x06):
                draft["wval"] = raw
            else:
                draft["qty"] = raw
            rule = _mm.normalize_poll(draft)
            if rule.get("unit") is None or rule.get("addr") is None:
                raise ValueError("unit/addr")
            if func in (0x05, 0x06):
                if rule.get("wval") is None:
                    raise ValueError("wval")
            elif rule.get("qty") is None:
                raise ValueError("qty")
        except Exception:
            self.app.toast(self.app._t("mbm_os_bad_input"), error=True)
            return

        self.lbl_os_result.setText(self.app._t("mbm_os_running"))
        finished = {"got_result": False}

        def on_result(_i, status, text):
            finished["got_result"] = True
            tip = status or ""
            body = text or ""
            self.lbl_os_result.setText(("%s  %s" % (tip, body)).strip())
            c = chrome_for(self.app._theme_id())
            color = c.get("accent") if tip == "ok" else c.get("text_sec")
            if tip and tip != "ok":
                color = c.get("danger") or c.get("text")
            self.lbl_os_result.setStyleSheet("color: %s;" % color)

        def on_done(cancelled):
            self._oneshot_set_busy(False)
            if cancelled and not finished["got_result"]:
                self.lbl_os_result.setText(self.app._t("mbm_os_cancelled"))
                c = chrome_for(self.app._theme_id())
                self.lbl_os_result.setStyleSheet(
                    "color: %s;" % (c.get("danger") or c.get("text")))

        self._oneshot_set_busy(True)
        ok = self.app._start_device_scan([rule], 1000, on_result, on_done)
        if not ok:
            self.lbl_os_result.setText(self.app._t("mbm_os_failed"))
            self._oneshot_set_busy(False)

    def _scan_locked(self):
        if getattr(self.app, "_device_scan_state", None) is None:
            return False
        self.app.toast_io_exclusive_busy()
        return True

    def _commit(self, _checked=False):
        if self._scan_locked():
            return
        from modbus import modbus_master
        edited = [modbus_master.normalize_poll(r) for r in self._collect()]
        # Splice the edited rows back at their original positions. The engine
        # keys results and timers off the global rule index, so appending this
        # view at the end would renumber every other view's rules.
        merged, mapping = [], []
        pending = iter(edited)
        for rule in (self.app._mbm_rules or []):
            if str(rule.get("group", "") or "") != self._view_name:
                merged.append(rule)
                continue
            nxt = next(pending, None)
            if nxt is None:
                continue                      # row deleted from this view
            mapping.append(len(merged))
            merged.append(nxt)
        for extra in pending:                 # rows added to this view
            mapping.append(len(merged))
            merged.append(extra)
        self.app._mbm_rules = merged
        self._row_rule_index = mapping
        self.app._mbm_save_rules()
        self._dirty = False
        self.btn_apply.setEnabled(False)
        self._clear_result_labels("—")
        self.app._mbm_restart()      # 规则变 → 复位运行态并按需重启轮询

    def _clear_result_labels(self, status_text):
        """草稿行与运行规则索引可能不同；编辑期间清空值并显示待应用，杜绝结果串行。"""
        c = chrome_for(self.app._theme_id())
        for rec in self._rows:
            rec["val"].setText("—")
            rec["st"].setText(status_text)
            rec["st"].setStyleSheet("color: %s;" % c["text_sec"])

    def _warn_apply_first(self):
        if not self._dirty:
            return False
        self.app.toast(self.app._t("mbm_apply_first"), error=True)
        return True

    def _on_enable(self, checked):
        if self._scan_locked():
            self.cb_enable.blockSignals(True)
            self.cb_enable.setChecked(bool(
                self.app._device_scan_state["old_on"]))
            self.cb_enable.blockSignals(False)
            return
        # 停止轮询始终允许；但草稿未应用时不得从停止态启动看不见的旧规则。
        if checked and self._warn_apply_first():
            self.cb_enable.blockSignals(True)
            self.cb_enable.setChecked(bool(self.app._mbm_on))
            self.cb_enable.blockSignals(False)
            return
        # 连接已打开但协议/端点/串口参数与界面不一致时，不制造“已启用但实际不轮询”的假状态。
        if checked and self.app._is_open() and not self.app._mbm_connection_ready():
            self.cb_enable.blockSignals(True)
            self.cb_enable.setChecked(False)
            self.cb_enable.blockSignals(False)
            self.app._mbm_on = False
            try:
                self.app.settings.setValue("modbus_master_on", False)
                self.app.settings.sync()
            except Exception:
                _log.debug("modbus_master_on persist failed", exc_info=True)
            self.app.toast(self.app._t("mbm_reconnect_first"), error=True)
            return
        self.app._set_mbm_enabled(checked)

    def _on_variant(self, _idx):
        if self._scan_locked():
            self.cb_variant.blockSignals(True)
            idx = self.cb_variant.findData(self.app._mbm_variant)
            self.cb_variant.setCurrentIndex(idx if idx >= 0 else 0)
            self.cb_variant.blockSignals(False)
            return
        if self._warn_apply_first():
            self.cb_variant.blockSignals(True)
            idx = self.cb_variant.findData(self.app._mbm_variant)
            self.cb_variant.setCurrentIndex(idx if idx >= 0 else 0)
            self.cb_variant.blockSignals(False)
            return
        self.app._mbm_variant = self.cb_variant.currentData() or ""
        try:
            self.app.settings.setValue("modbus_master_variant", self.app._mbm_variant)
            self.app.settings.sync()
        except Exception:
            _log.debug("modbus_master_variant persist failed", exc_info=True)
        self.app._mbm_restart()

    def _on_echo(self, checked):
        if self._scan_locked():
            self.cb_echo.blockSignals(True)
            self.cb_echo.setChecked(bool(self.app._mbm_echo))
            self.cb_echo.blockSignals(False)
            return
        if self._warn_apply_first():
            self.cb_echo.blockSignals(True)
            self.cb_echo.setChecked(bool(self.app._mbm_echo))
            self.cb_echo.blockSignals(False)
            return
        self.app._mbm_echo = bool(checked)
        try:
            self.app.settings.setValue("modbus_master_echo", self.app._mbm_echo)
            self.app.settings.sync()
        except Exception:
            _log.debug("modbus_master_echo persist failed", exc_info=True)
        self.app._mbm_restart()

    # ---------------- 引擎回调：刷新某行的值/状态 ----------------
    def update_result(self, i, status, text):
        if self._dirty:
            return
        # Engine uses global rule index; map into the visible view rows.
        try:
            row = self._row_rule_index.index(i)
        except (ValueError, AttributeError):
            return
        if not (0 <= row < len(self._rows)):
            return
        rec = self._rows[row]
        c = chrome_for(self.app._theme_id())
        if status == "ok":
            rec["val"].setText(text)
            rec["st"].setText(self.app._t("mbm_st_ok"))
            rec["st"].setStyleSheet("color: %s;" % c["accent"])
        else:
            rec["st"].setText(text)
            rec["st"].setStyleSheet("color: %s;" % c["danger"])

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
        QPushButton#ArDelBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 6px; font-size: 13px;
        }}
        QPushButton#ArDelBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['danger']}; }}
        QPushButton#ArHelpBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 13px;
            font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
        }}
        QPushButton#ArHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        QCheckBox#ArEnable {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 13px; font-weight: 500; }}
        /* 选中时外框高亮：更粗的 accent 边框 + accent 填充，明显区别于未选中 */
        QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 3px;
            border: 1px solid {c['separator']}; background-color: {c['input_bg']}; }}
        QCheckBox::indicator:hover {{ border: 1px solid {c['accent']}; }}
        QCheckBox::indicator:checked {{ background-color: {c['accent']};
            border: 2px solid {c['accent_hover']}; }}
        QCheckBox::indicator:checked:hover {{ border: 2px solid {c['accent']}; }}
        QLabel#ArDesc {{ color: {c['text_sec']}; font-family: 'Segoe UI'; font-size: 11px; }}
        QLabel#MbmVal {{ color: {c['text']}; font-family: 'Consolas','Menlo',monospace; font-size: 12px; }}
        QLabel#MbmSt {{ color: {c['text_sec']}; font-family: 'Segoe UI'; font-size: 12px; }}
        QScrollArea#ArScroll {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
        QScrollArea#ArScroll > QWidget > QWidget {{ background: transparent; }}
        QWidget#ArRow {{ background: transparent; }}
        QSplitter#MbmSplit::handle {{ background: {c['separator']}; margin: 4px 1px; border-radius: 2px; }}
        QSplitter#MbmSplit::handle:hover {{ background: {c['accent']}; }}
        """))
        _style_combo_popups(self, c)

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("mbm_title"))
        self.cb_enable.setText(t("mbm_enable"))
        self.lbl_variant.setText(t("mbm_variant"))
        self.cb_echo.setText(t("mbm_echo"))
        set_tooltip(self.cb_echo, t("mbm_echo_tip"))
        self.btn_apply.setText(t("mbm_apply"))
        self.btn_add.setText(t("mbm_add"))
        set_tooltip(self.btn_add_view, t("mbm_view_add"))
        set_tooltip(self.btn_del_view, t("mbm_view_del"))
        if hasattr(self, "tabs"):
            self._rebuild_tabs(keep=getattr(self, "_view_name", ""))
        set_tooltip(self.btn_help, t("mbm_help_btn"))
        self.lbl_hint.setText(t("mbm_hint"))
        if hasattr(self, "lbl_os"):
            self.lbl_os.setText(t("mbm_os_label"))
            set_tooltip(self.lbl_os, t("mbm_os_tip"))
            set_tooltip(self.ed_os_unit, t("mbm_col_unit"))
            set_tooltip(self.ed_os_addr, t("mbm_col_addr"))
            self.btn_os_run.setText(t("mbm_os_run"))
            if hasattr(self, "btn_os_cancel"):
                self.btn_os_cancel.setText(t("mbm_os_cancel"))
            cur_os = self.cb_os_func.currentData()
            self.cb_os_func.blockSignals(True)
            self.cb_os_func.clear()
            for code, key in ONESHOT_FUNCS:
                self.cb_os_func.addItem(t(key), code)
            j = next((n for n, (code, _k) in enumerate(ONESHOT_FUNCS)
                      if code == cur_os), 2)
            self.cb_os_func.setCurrentIndex(j)
            self.cb_os_func.blockSignals(False)
            self._os_func_changed()
        cur = self.cb_variant.currentData()
        self.cb_variant.blockSignals(True)
        self.cb_variant.clear()
        for data, key in (("", "mbm_variant_auto"), ("rtu", "mbm_variant_rtu"),
                          ("tcp", "mbm_variant_tcp"), ("ascii", "mbm_variant_ascii")):
            self.cb_variant.addItem(t(key), data)
        sel = cur if cur is not None else (getattr(self.app, "_mbm_variant", "") or "")
        idx = self.cb_variant.findData(sel)
        self.cb_variant.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_variant.blockSignals(False)
        for lb in self._hdr_labels:
            lb.setText(t(lb.property("k")))
        # 行内功能码下拉文案随语言刷新（保留当前选择）
        for rec in self._rows:
            combo = rec["func"]
            cur_code = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for code, key in FUNC_ITEMS:
                combo.addItem(t(key), code)
            j = next((n for n, (code, _k) in enumerate(FUNC_ITEMS) if code == cur_code), 2)
            combo.setCurrentIndex(j)
            combo.blockSignals(False)

    def _show_help(self):
        """左对齐、可滚动的说明窗（与自动应答说明窗一致，避免 InfoDialog 居中正文乱折行）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("mbm_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(640, 460)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("mbm_help"))
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        btn_close = QPushButton({"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(
            getattr(self.app, "_lang", "en"), "Close"))
        btn_close.setObjectName("PlotGhostBtn")
        btn_close.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_close)
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
