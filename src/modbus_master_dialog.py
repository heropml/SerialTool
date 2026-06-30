# -*- coding: utf-8 -*-
"""Modbus 主机轮询对话框 ModbusMasterDialog。

每行 = [启用] 名称 | 从机ID | 功能码 | 起始地址 | 数量/写值 | 周期ms → 值 | 状态 [✕]。
轮询引擎在 main_window（_mbm_* 系列）：本对话框只是编辑器 + 结果展示，规则存 app._mbm_rules。
顶部「启用轮询」= app._mbm_on，「传输」= app._mbm_variant（''=按连接自动 / 'rtu' / 'tcp'）。
单实例非模态，复用主窗刷新主题/语言。读类功能码用「数量」，写类(05/06)用同一格当「写值」。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QWidget,
                             QPushButton, QCheckBox, QComboBox, QScrollArea, QFrame, QSplitter)

from theme import chrome_for
from fonts import localize_qss
from dialogs import _dialog_list_qss, _set_win_titlebar_dark

# 功能码下拉项：(code, i18n_key)。读 01-04 / 写单 05-06 / 写多 0F-10。
FUNC_ITEMS = [(0x01, "mbm_f1"), (0x02, "mbm_f2"), (0x03, "mbm_f3"),
              (0x04, "mbm_f4"), (0x05, "mbm_f5"), (0x06, "mbm_f6"),
              (0x0F, "mbm_f7"), (0x10, "mbm_f8")]
READ_FUNCS = (0x01, 0x02, 0x03, 0x04)
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
        self._split_sizes = None          # 名称~值七列的共享拖动比例，所有行与表头同步
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

    def _sync_splits(self, src):
        """任一行(或表头)拖动分隔条 → 所有行 + 表头同步到相同比例（列对齐）。"""
        if self._syncing_split:
            return
        sizes = src.sizes()
        if not sizes or sum(sizes) <= 0:
            return
        self._split_sizes = sizes
        self._syncing_split = True
        try:
            targets = [getattr(self, "_hdr_split", None)] + [r.get("split") for r in self._rows]
            for sp in targets:
                if sp is not None and sp is not src:
                    sp.setSizes(sizes)
        finally:
            self._syncing_split = False

    def _update_header_scroll_margin(self, *_args):
        """数据区出现垂直滚动条时，表头预留同宽空间，保持 splitter 像素对齐。"""
        bar = self.scroll.verticalScrollBar()
        extra = bar.sizeHint().width() if bar.maximum() > bar.minimum() else 0
        self._hdr_layout.setContentsMargins(10, 2, 7 + extra, 2)
        QTimer.singleShot(0, lambda: self._sync_splits(self._hdr_split))

    # ---------------- 行 ----------------
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
        else:
            qty_val = rule.get("wval")
            qty_val = "" if qty_val is None else qty_val
        ed_qty = QLineEdit(str(qty_val))
        ed_qty.setMinimumWidth(_SPLIT_COLS[4][1])
        ed_qty.setToolTip(self.app._t("mbm_qty_tip"))
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
               "val": lbl_val, "st": lbl_st, "split": split}

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

    def reload_rows(self):
        for rec in self._rows:
            rec["w"].setParent(None)
            rec["w"].deleteLater()
        self._rows = []
        for rule in getattr(self.app, "_mbm_rules", []):
            self._add_row(rule)
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
        self.reload_rows()

    def _collect(self):
        out = []
        for rec in self._rows:
            code = rec["func"].currentData()
            field = rec["qty"].text().strip()
            out.append({
                "enabled": rec["enable"].isChecked(),
                "name": rec["name"].text(),
                "unit": rec["unit"].text().strip(),
                "func": code,
                "addr": rec["addr"].text().strip(),
                "qty": field,      # 读类按数量解析
                "wval": field,     # 写类按写值解析（normalize 按 func 取其一）
                "period": rec["period"].text().strip(),
            })
        return out

    def _schedule(self):
        # 只标记草稿，不自动提交。尤其功能码从读切到写时，必须由用户显式应用才允许发送。
        if not self._dirty:
            self._clear_result_labels(self.app._t("mbm_st_pending"))
        self._dirty = True
        self.btn_apply.setEnabled(True)

    def _commit(self):
        import modbus_master
        self.app._mbm_rules = [modbus_master.normalize_poll(r) for r in self._collect()]
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
                pass
            self.app._update_mbm_btn()
            self.app.toast(self.app._t("mbm_reconnect_first"), error=True)
            return
        self.app._set_mbm_enabled(checked)

    def _on_variant(self, _idx):
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
            pass
        self.app._mbm_restart()

    def _on_echo(self, checked):
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
            pass
        self.app._mbm_restart()

    # ---------------- 引擎回调：刷新某行的值/状态 ----------------
    def update_result(self, i, status, text):
        if self._dirty:
            return                  # 运行态索引与草稿行不再可靠，应用前不回填实时结果
        if not (0 <= i < len(self._rows)):
            return
        rec = self._rows[i]
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

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("mbm_title"))
        self.cb_enable.setText(t("mbm_enable"))
        self.lbl_variant.setText(t("mbm_variant"))
        self.cb_echo.setText(t("mbm_echo"))
        self.cb_echo.setToolTip(t("mbm_echo_tip"))
        self.btn_apply.setText(t("mbm_apply"))
        self.btn_add.setText(t("mbm_add"))
        self.btn_help.setToolTip(t("mbm_help_btn"))
        self.lbl_hint.setText(t("mbm_hint"))
        cur = self.cb_variant.currentData()
        self.cb_variant.blockSignals(True)
        self.cb_variant.clear()
        for data, key in (("", "mbm_variant_auto"), ("rtu", "mbm_variant_rtu"), ("tcp", "mbm_variant_tcp")):
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
