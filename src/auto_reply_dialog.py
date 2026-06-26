# -*- coding: utf-8 -*-
"""自动应答对话框 AutoReplyDialog。

规则列表：每行 [启用] 收到[匹配] [HEX] [模式] → 回[应答] [HEX] [校验] 冷却[ms] [✕]。
收到数据匹配任一启用规则 → 自动发送其应答（复用主窗口 _send_text，应答可带校验/自动CRC）。
匹配/发送逻辑在 main_window（即使本对话框没开也生效）；本对话框只是编辑器，规则存 app._ar_rules。
单实例非模态，复用刷新主题/语言；窗口带最小化/最大化。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QWidget,
                             QPushButton, QCheckBox, QComboBox, QScrollArea, QFrame, QSplitter)

from theme import chrome_for
from fonts import localize_qss
from i18n import CHECKSUM_KEYS
from dialogs import _dialog_list_qss, _set_win_titlebar_dark


class AutoReplyDialog(QDialog):
    def __init__(self, app):
        # 故意不传 parent 给 super → 与主窗的 Qt 父子链彻底断开。原因：把 app(主窗)作为父时，
        # Qt 在 Windows 上似乎与无边框主窗的 nativeEvent(WM_NCHITTEST) 处理产生干扰，
        # 表现为打开此对话框后主窗边缘 resize 失效（且关闭后不恢复）。生命周期改在主窗
        # _shutdown() 里显式 close+deleteLater，避免主窗关闭后此独立顶层窗残留。
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(720, 360)
        self.resize(960, 460)

        self._rows = []
        self._syncing = False                # 防止同步分隔条时递归
        self._split_sizes = None             # 收到/回复两框的共享分隔比例
        self._save_timer = QTimer(self)      # 去抖：连改时合并落盘
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._commit)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        top = QHBoxLayout()
        self.cb_enable = QCheckBox()
        self.cb_enable.setObjectName("ArEnable")
        self.cb_enable.setChecked(bool(getattr(app, "_ar_on", False)))
        self.cb_enable.toggled.connect(self._on_enable)
        top.addWidget(self.cb_enable)
        top.addStretch(1)
        self.btn_add = QPushButton()
        self.btn_add.setObjectName("PlotGhostBtn")
        self.btn_add.clicked.connect(lambda *_: (self._add_row(), self._schedule()))
        top.addWidget(self.btn_add)
        # 使用说明：26×26 「?」icon button，文案放 tooltip（点开弹独立窗口看完整说明）
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("ArHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help_dlg)
        top.addWidget(self.btn_help)
        root.addLayout(top)

        # 帧头+长度组帧（全局，整条串口一份）：有帧头+长度字段的协议优先用它，跨包按整帧
        # 边界切分、正确处理粘包/拆包；启用后优先于各规则的「整包」静默超时。
        self._frame_box = QFrame()
        self._frame_box.setObjectName("ArFrameBox")    # 带边框，与下方规则区(ArScroll)风格/左右对齐一致
        frow = QHBoxLayout(self._frame_box)
        frow.setContentsMargins(8, 6, 8, 6)
        frow.setSpacing(6)
        fc = getattr(app, "_ar_frame", {}) or {}
        self.cb_frame_on = QCheckBox()
        self.cb_frame_on.setChecked(bool(fc.get("on")))
        self.cb_frame_on.toggled.connect(self._schedule)
        frow.addWidget(self.cb_frame_on)
        self.lbl_fhdr = QLabel()
        frow.addWidget(self.lbl_fhdr)
        self.ed_fhdr = QLineEdit(str(fc.get("header", "")))
        self.ed_fhdr.setMaximumWidth(110)
        self.ed_fhdr.textChanged.connect(self._schedule)
        frow.addWidget(self.ed_fhdr)
        self.lbl_foff = QLabel()
        frow.addWidget(self.lbl_foff)
        self.ed_foff = QLineEdit(str(fc.get("len_off", 0)))
        self.ed_foff.setMaximumWidth(46)
        self.ed_foff.textChanged.connect(self._schedule)
        frow.addWidget(self.ed_foff)
        self.lbl_fwidth = QLabel()
        frow.addWidget(self.lbl_fwidth)
        self.cb_fwidth = QComboBox()
        self.cb_fwidth.addItems(["1", "2", "4"])
        self.cb_fwidth.setCurrentText(str(fc.get("len_width", 2)))
        self.cb_fwidth.currentIndexChanged.connect(self._schedule)
        frow.addWidget(self.cb_fwidth)
        self.cb_fbe = QComboBox()
        self.cb_fbe.addItems(["LE", "BE"])      # 长度字段字节序：小端/大端（工程通用缩写，不翻译）
        self.cb_fbe.setCurrentIndex(1 if fc.get("len_be") else 0)
        self.cb_fbe.currentIndexChanged.connect(self._schedule)
        frow.addWidget(self.cb_fbe)
        self.lbl_fextra = QLabel()
        frow.addWidget(self.lbl_fextra)
        self.ed_fextra = QLineEdit(str(fc.get("len_extra", 0)))
        self.ed_fextra.setMaximumWidth(46)
        self.ed_fextra.textChanged.connect(self._schedule)
        frow.addWidget(self.ed_fextra)
        frow.addStretch(1)
        root.addWidget(self._frame_box)

        self._rows_host = QWidget()
        self._rows_v = QVBoxLayout(self._rows_host)
        self._rows_v.setContentsMargins(0, 0, 0, 0)
        self._rows_v.setSpacing(4)
        self._rows_v.addStretch(1)
        self._rows_host.setAutoFillBackground(False)
        scroll = QScrollArea()
        scroll.setObjectName("ArScroll")
        scroll.setWidget(self._rows_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        root.addWidget(scroll, 1)

        self.retranslate()
        self.reload_rows()    # 初次构造也走统一路径
        self.refresh_theme()

    # ---------------- 规则行 ----------------
    def _add_row(self, rule=None):
        t = self.app._t
        rule = rule or {}
        row = QWidget()
        row.setObjectName("ArRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(6, 3, 6, 3)
        h.setSpacing(6)

        cb_on = QCheckBox()
        cb_on.setChecked(bool(rule.get("on", True)))
        ed_match = QLineEdit(rule.get("match", ""))
        ed_match.setPlaceholderText(t("ar_match_ph"))
        cb_mhex = QCheckBox("HEX")
        cb_mhex.setChecked(bool(rule.get("match_hex", True)))
        # 复用主窗的容错 int：ini/json 被手改成非数字（如 gap:"abc"）也不让初始化崩
        _i = self.app._ar_to_int
        cb_mode = QComboBox()
        cb_mode.addItems([t("ar_mode_contains"), t("ar_mode_equals"), t("ar_mode_prefix")])
        cb_mode.setCurrentIndex(_i(rule.get("mode", 0)))
        cb_verify = QComboBox()       # 收包校验（对收到帧验校验，通过才应答）
        for k in CHECKSUM_KEYS:
            cb_verify.addItem(t(k))
        cb_verify.setCurrentIndex(_i(rule.get("verify", 0)))
        cb_verify.setToolTip(t("ar_verify_tip"))
        ed_reply = QLineEdit(rule.get("reply", ""))
        ed_reply.setPlaceholderText(t("ar_reply_ph"))
        cb_rhex = QCheckBox("HEX")
        cb_rhex.setChecked(bool(rule.get("reply_hex", True)))
        cb_cs = QComboBox()
        for k in CHECKSUM_KEYS:
            cb_cs.addItem(t(k))
        cb_cs.setCurrentIndex(_i(rule.get("cs", 0)))
        # delay=回复 turnaround；cooldown=触发限流（两回事，旧 cooldown 配置原义保留）
        ed_cd = QLineEdit(str(_i(rule.get("delay", 0))))
        ed_cd.setMaximumWidth(56)
        ed_cdwn = QLineEdit(str(_i(rule.get("cooldown", 0))))
        ed_cdwn.setMaximumWidth(56)
        ed_cdwn.setToolTip(t("ar_cooldown_tip"))
        ed_gap = QLineEdit(str(_i(rule.get("gap", 0))))   # 整包静默(实际取各规则最大值)
        ed_gap.setMaximumWidth(56)
        ed_gap.setToolTip(t("ar_gap_tip"))
        btn_del = QPushButton("✕")
        btn_del.setObjectName("ArDelBtn")
        btn_del.setFixedSize(26, 26)

        # 共所有可翻译子件存入 rec：retranslate() 切语言时统一刷新（否则 label/combo/tooltip 残留旧语言）
        lbl_match = QLabel(t("ar_match"))
        lbl_verify = QLabel(t("ar_verify"))
        lbl_gap = QLabel(t("ar_gap"))
        lbl_reply = QLabel(t("ar_reply"))
        lbl_delay = QLabel(t("ar_delay"))
        lbl_cdwn = QLabel(t("ar_cooldown"))
        rec = {"w": row, "on": cb_on, "match": ed_match, "mhex": cb_mhex, "mode": cb_mode,
               "verify": cb_verify, "reply": ed_reply, "rhex": cb_rhex, "cs": cb_cs,
               "cd": ed_cd, "cdwn": ed_cdwn, "gap": ed_gap,
               "lbl_match": lbl_match, "lbl_verify": lbl_verify, "lbl_gap": lbl_gap,
               "lbl_reply": lbl_reply, "lbl_delay": lbl_delay, "lbl_cdwn": lbl_cdwn}
        btn_del.clicked.connect(lambda *_: self._del_row(rec))
        # 任何改动 → 去抖落盘
        cb_on.toggled.connect(self._schedule)
        cb_mhex.toggled.connect(self._schedule)
        cb_rhex.toggled.connect(self._schedule)
        cb_mode.currentIndexChanged.connect(self._schedule)
        cb_verify.currentIndexChanged.connect(self._schedule)
        cb_cs.currentIndexChanged.connect(self._schedule)
        ed_match.textChanged.connect(self._schedule)
        ed_reply.textChanged.connect(self._schedule)
        ed_cd.textChanged.connect(self._schedule)
        ed_cdwn.textChanged.connect(self._schedule)
        ed_gap.textChanged.connect(self._schedule)

        # 「收到」组（收包侧：匹配/HEX/模式/收校验/整包超时）
        left = QWidget()
        lh = QHBoxLayout(left)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(6)
        lh.addWidget(cb_on)
        lh.addWidget(lbl_match)
        lh.addWidget(ed_match, 1)
        lh.addWidget(cb_mhex)
        lh.addWidget(cb_mode)
        lh.addWidget(lbl_verify)
        lh.addWidget(cb_verify)
        lh.addWidget(lbl_gap)
        lh.addWidget(ed_gap)
        lh.addWidget(QLabel("ms"))
        # 「回复」组（应答侧：回复/HEX/校验/延时/冷却）
        right = QWidget()
        rh = QHBoxLayout(right)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(6)
        rh.addWidget(QLabel("→"))
        rh.addWidget(lbl_reply)
        rh.addWidget(ed_reply, 1)
        rh.addWidget(cb_rhex)
        rh.addWidget(cb_cs)
        rh.addWidget(lbl_delay)
        rh.addWidget(ed_cd)
        rh.addWidget(QLabel("ms"))
        rh.addWidget(lbl_cdwn)
        rh.addWidget(ed_cdwn)
        rh.addWidget(QLabel("ms"))
        # 两组之间放分隔条：拖动即可调「收到框」「回复框」宽度（各行同步）
        split = QSplitter(Qt.Horizontal)
        split.setObjectName("ArRowSplit")
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        split.addWidget(left)
        split.addWidget(right)
        split.splitterMoved.connect(lambda *_: self._sync_splitters(split))
        rec["split"] = split

        h.addWidget(split, 1)
        h.addWidget(btn_del)
        if self._split_sizes:                # 新行采用当前已有的分隔比例
            split.setSizes(self._split_sizes)
        else:
            split.setSizes([360, 480])
        self._rows_v.insertWidget(self._rows_v.count() - 1, row)
        self._rows.append(rec)

    def _sync_splitters(self, src):
        """一行拖动分隔条 → 所有行同步到相同比例（列对齐）。"""
        if self._syncing:
            return
        sizes = src.sizes()
        if len(sizes) != 2 or sum(sizes) <= 0:
            return
        self._split_sizes = sizes
        self._syncing = True
        try:
            for rec in self._rows:
                sp = rec.get("split")
                if sp is not None and sp is not src:
                    sp.setSizes(sizes)
        finally:
            self._syncing = False

    def _del_row(self, rec):
        rec["w"].setParent(None)
        rec["w"].deleteLater()
        if rec in self._rows:
            self._rows.remove(rec)
        self._schedule()

    def reload_rows(self):
        """按 app._ar_rules 重建所有规则行。配置导入/外部修改 _ar_rules 后调用——
        否则旧对话框内 _rows 是陈旧的，下次 _commit() 会把旧行覆盖回 _ar_rules。"""
        # 阻止 _del_row 触发的去抖落盘把"清空过程的中间态"写回去
        if self._save_timer.isActive():
            self._save_timer.stop()
        for rec in list(self._rows):
            rec["w"].setParent(None)
            rec["w"].deleteLater()
        self._rows.clear()
        for rule in getattr(self.app, "_ar_rules", []):
            self._add_row(rule)
        if not self._rows:
            self._add_row()
        # 同步顶部启用 checkbox（_ar_on 也可能被导入改了）
        self.cb_enable.blockSignals(True)
        self.cb_enable.setChecked(bool(getattr(self.app, "_ar_on", False)))
        self.cb_enable.blockSignals(False)
        # 同步帧头+长度组帧控件（配置导入 / 外部修改 _ar_frame 后）
        fc = getattr(self.app, "_ar_frame", {}) or {}
        fw = (self.cb_frame_on, self.ed_fhdr, self.ed_foff, self.cb_fwidth, self.cb_fbe, self.ed_fextra)
        for w in fw:
            w.blockSignals(True)
        self.cb_frame_on.setChecked(bool(fc.get("on")))
        self.ed_fhdr.setText(str(fc.get("header", "")))
        self.ed_foff.setText(str(fc.get("len_off", 0)))
        self.cb_fwidth.setCurrentText(str(fc.get("len_width", 2)))
        self.cb_fbe.setCurrentIndex(1 if fc.get("len_be") else 0)
        self.ed_fextra.setText(str(fc.get("len_extra", 0)))
        for w in fw:
            w.blockSignals(False)

    # ---------------- 落盘 ----------------
    def _schedule(self, *_):
        self._save_timer.start()

    def _on_enable(self, on):
        self.app._ar_on = bool(on)
        self.app.settings.setValue("autoreply_on", bool(on))
        self.app._ar_reset_buf()              # 跟 _toggle_ar_on 一致：切换时清半帧缓冲
        self.app._update_autoreply_btn()      # 主界面按钮跟随高亮

    def _commit(self):
        def _n(le):
            try:
                return max(0, int(le.text() or "0"))
            except ValueError:
                return 0
        rules = []
        for rec in self._rows:
            rules.append({
                "on": rec["on"].isChecked(),
                "match": rec["match"].text(),
                "match_hex": rec["mhex"].isChecked(),
                "mode": rec["mode"].currentIndex(),
                "verify": rec["verify"].currentIndex(),
                "reply": rec["reply"].text(),
                "reply_hex": rec["rhex"].isChecked(),
                "cs": rec["cs"].currentIndex(),
                "delay": _n(rec["cd"]),
                "cooldown": _n(rec["cdwn"]),
                "gap": _n(rec["gap"]),
            })
        self.app._set_ar_rules(rules)
        # 帧头+长度组帧（全局配置）随规则一起去抖落盘
        self.app._set_ar_frame({
            "on": self.cb_frame_on.isChecked(),
            "header": self.ed_fhdr.text(),
            "len_off": _n(self.ed_foff),
            "len_width": int(self.cb_fwidth.currentText()),
            "len_be": self.cb_fbe.currentIndex() == 1,
            "len_extra": _n(self.ed_fextra),
        })

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
        QFrame#ArFrameBox {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
        QScrollArea#ArScroll {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
        QScrollArea#ArScroll > QWidget > QWidget {{ background: transparent; }}
        QWidget#ArRow {{ background: transparent; }}
        QSplitter#ArRowSplit::handle {{ background: {c['separator']}; margin: 5px 1px; border-radius: 2px; }}
        QSplitter#ArRowSplit::handle:hover {{ background: {c['accent']}; }}
        """))

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("ar_title"))
        self.cb_enable.setText(t("ar_enable"))
        self.btn_add.setText(t("ar_add"))
        self.btn_help.setToolTip(t("ar_help_btn"))   # 按钮文字固定 "?", 悬停看完整文案
        self.cb_frame_on.setText(t("ar_frame_on"))
        self.cb_frame_on.setToolTip(t("ar_frame_tip"))
        self.lbl_fhdr.setText(t("ar_frame_hdr"))
        self.lbl_foff.setText(t("ar_frame_off"))
        self.lbl_fwidth.setText(t("ar_frame_width"))
        self.lbl_fextra.setText(t("ar_frame_extra"))
        mode_items = [t("ar_mode_contains"), t("ar_mode_equals"), t("ar_mode_prefix")]
        cs_items = [t(k) for k in CHECKSUM_KEYS]
        for rec in self._rows:
            rec["match"].setPlaceholderText(t("ar_match_ph"))
            rec["reply"].setPlaceholderText(t("ar_reply_ph"))
            # 行内 label 文本
            rec["lbl_match"].setText(t("ar_match"))
            rec["lbl_verify"].setText(t("ar_verify"))
            rec["lbl_gap"].setText(t("ar_gap"))
            rec["lbl_reply"].setText(t("ar_reply"))
            rec["lbl_delay"].setText(t("ar_delay"))
            rec["lbl_cdwn"].setText(t("ar_cooldown"))
            # tooltip
            rec["verify"].setToolTip(t("ar_verify_tip"))
            rec["gap"].setToolTip(t("ar_gap_tip"))
            rec["cdwn"].setToolTip(t("ar_cooldown_tip"))
            # combo 项（保留当前选中索引）：模式 + 收/发校验
            for combo, items in ((rec["mode"], mode_items),
                                 (rec["verify"], cs_items),
                                 (rec["cs"], cs_items)):
                idx = combo.currentIndex()
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(items)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)

    def _show_help_dlg(self):
        """弹独立窗口展示使用说明（富文本+可滚动）。原 lbl_help 占顶部太挤，改成按需查看。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("ar_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(760, 520)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("ar_help"))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setAlignment(Qt.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)   # 让用户复制例子
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        # 用语言 map 给 close 按钮文案，避免为单点新增 i18n 键
        btn_close = QPushButton({"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(self.app._lang, "Close"))
        btn_close.setObjectName("PlotGhostBtn")
        btn_close.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_close)
        v.addLayout(row)
        # 主题/字体跟自动应答弹窗一致
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

    def closeEvent(self, e):
        if self._save_timer.isActive():
            self._commit()
        super().closeEvent(e)
