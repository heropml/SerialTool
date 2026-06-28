# -*- coding: utf-8 -*-
"""Modbus 主机轮询对话框 ModbusMasterDialog。

每行 = [启用] 名称 | 从机ID | 功能码 | 起始地址 | 数量/写值 | 周期ms → 值 | 状态 [✕]。
轮询引擎在 main_window（_mbm_* 系列）：本对话框只是编辑器 + 结果展示，规则存 app._mbm_rules。
顶部「启用轮询」= app._mbm_on，「传输」= app._mbm_variant（''=按连接自动 / 'rtu' / 'tcp'）。
单实例非模态，复用主窗刷新主题/语言。读类功能码用「数量」，写类(05/06)用同一格当「写值」。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QWidget,
                             QPushButton, QCheckBox, QComboBox, QScrollArea, QFrame)

from theme import chrome_for
from fonts import localize_qss
from dialogs import _dialog_list_qss, _set_win_titlebar_dark

# 功能码下拉项：(code, i18n_key)。读 01-04 / 写 05-06。
FUNC_ITEMS = [(0x01, "mbm_f1"), (0x02, "mbm_f2"), (0x03, "mbm_f3"),
              (0x04, "mbm_f4"), (0x05, "mbm_f5"), (0x06, "mbm_f6")]
READ_FUNCS = (0x01, 0x02, 0x03, 0x04)


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
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._commit)

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
        hh.setContentsMargins(9, 2, 6, 2)
        hh.setSpacing(6)
        self._hdr_labels = []
        for key, w in (("mbm_col_name", 120), ("mbm_col_unit", 64), ("mbm_col_func", 150),
                       ("mbm_col_addr", 80), ("mbm_col_qty", 80), ("mbm_col_period", 80)):
            lb = QLabel()
            lb.setProperty("k", key)
            lb.setFixedWidth(w)
            hh.addWidget(lb)
            self._hdr_labels.append(lb)
        lb_val = QLabel(); lb_val.setProperty("k", "mbm_col_value")
        hh.addWidget(lb_val, 1)
        self._hdr_labels.append(lb_val)
        lb_st = QLabel(); lb_st.setProperty("k", "mbm_col_status"); lb_st.setFixedWidth(120)
        hh.addWidget(lb_st)
        self._hdr_labels.append(lb_st)
        hh.addSpacing(30)   # 删除按钮列
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
        root.addWidget(self.scroll, 1)

        self.reload_rows()
        self.retranslate()
        self.refresh_theme()

    # ---------------- 行 ----------------
    def _add_row(self, rule=None):
        rule = rule or {}
        r = QWidget()
        r.setObjectName("ArRow")
        rh = QHBoxLayout(r)
        rh.setContentsMargins(9, 0, 6, 0)
        rh.setSpacing(6)

        cb = QCheckBox()
        cb.setChecked(bool(rule.get("enabled", True)))
        cb.toggled.connect(self._schedule)
        rh.addWidget(cb)

        ed_name = QLineEdit(str(rule.get("name", "") or ""))
        ed_name.setFixedWidth(110)
        ed_name.textChanged.connect(self._schedule)
        rh.addWidget(ed_name)

        ed_unit = QLineEdit(str(rule.get("unit", 1)))
        ed_unit.setFixedWidth(64)
        ed_unit.textChanged.connect(self._schedule)
        rh.addWidget(ed_unit)

        cb_func = QComboBox()
        cb_func.setFixedWidth(150)
        for code, key in FUNC_ITEMS:
            cb_func.addItem(self.app._t(key), code)
        idx = next((n for n, (code, _k) in enumerate(FUNC_ITEMS)
                    if code == int(rule.get("func", 3) or 3)), 2)
        cb_func.setCurrentIndex(idx)
        cb_func.currentIndexChanged.connect(self._schedule)
        rh.addWidget(cb_func)

        ed_addr = QLineEdit(str(rule.get("addr", 0)))
        ed_addr.setFixedWidth(80)
        ed_addr.textChanged.connect(self._schedule)
        rh.addWidget(ed_addr)

        # 读类=数量；写类(05/06)=写值。共用一格。
        func0 = int(rule.get("func", 3) or 3)
        qty_val = rule.get("qty", 1) if func0 in READ_FUNCS else rule.get("wval", 0)
        ed_qty = QLineEdit(str(qty_val))
        ed_qty.setFixedWidth(80)
        ed_qty.textChanged.connect(self._schedule)
        rh.addWidget(ed_qty)

        ed_period = QLineEdit(str(rule.get("period", 1000)))
        ed_period.setFixedWidth(80)
        ed_period.textChanged.connect(self._schedule)
        rh.addWidget(ed_period)

        lbl_val = QLabel("—")
        lbl_val.setObjectName("MbmVal")
        lbl_val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rh.addWidget(lbl_val, 1)

        lbl_st = QLabel("—")
        lbl_st.setObjectName("MbmSt")
        lbl_st.setFixedWidth(120)
        rh.addWidget(lbl_st)

        btn_x = QPushButton("✕")
        btn_x.setObjectName("ArDelBtn")
        btn_x.setFixedSize(26, 26)
        rec = {"w": r, "enable": cb, "name": ed_name, "unit": ed_unit, "func": cb_func,
               "addr": ed_addr, "qty": ed_qty, "period": ed_period,
               "val": lbl_val, "st": lbl_st}

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
        self._save_timer.start()

    def _commit(self):
        import modbus_master
        self.app._mbm_rules = [modbus_master.normalize_poll(r) for r in self._collect()]
        self.app._mbm_save_rules()
        self.app._mbm_restart()      # 规则变 → 复位运行态并按需重启轮询

    def _on_enable(self, checked):
        self.app._mbm_on = bool(checked)
        try:
            self.app.settings.setValue("modbus_master_on", self.app._mbm_on)
            self.app.settings.sync()
        except Exception:
            pass
        self.app._update_mbm_btn()    # 标题栏「Modbus 主机」按钮高亮跟随开关
        self.app._mbm_restart()

    def _on_variant(self, _idx):
        self.app._mbm_variant = self.cb_variant.currentData() or ""
        try:
            self.app.settings.setValue("modbus_master_variant", self.app._mbm_variant)
            self.app.settings.sync()
        except Exception:
            pass
        self.app._mbm_restart()

    def _on_echo(self, checked):
        self.app._mbm_echo = bool(checked)
        try:
            self.app.settings.setValue("modbus_master_echo", self.app._mbm_echo)
            self.app.settings.sync()
        except Exception:
            pass
        self.app._mbm_restart()

    # ---------------- 引擎回调：刷新某行的值/状态 ----------------
    def update_result(self, i, status, text):
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
        """))

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("mbm_title"))
        self.cb_enable.setText(t("mbm_enable"))
        self.lbl_variant.setText(t("mbm_variant"))
        self.cb_echo.setText(t("mbm_echo"))
        self.cb_echo.setToolTip(t("mbm_echo_tip"))
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
