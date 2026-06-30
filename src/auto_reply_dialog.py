# -*- coding: utf-8 -*-
"""自动应答对话框 AutoReplyDialog。

规则列表：每行 [启用] 收到[匹配] [HEX] [模式] → 回[应答] [HEX] [校验] 冷却[ms] [✕]。
收到数据匹配任一启用规则 → 自动发送其应答（复用主窗口 _send_text，应答可带校验/自动CRC）。
匹配/发送逻辑在 main_window（即使本对话框没开也生效）；本对话框只是编辑器，规则存 app._ar_rules。
单实例非模态，复用刷新主题/语言；窗口带最小化/最大化。
"""
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QWidget,
                             QPushButton, QCheckBox, QComboBox, QScrollArea, QFrame, QSplitter,
                             QPlainTextEdit)

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
        self._rid_seq = 0                    # 给每行/源规则盖稳定 id，运行态(_hits/_last)按身份迁移，不按索引
        self._syncing = False                # 防止同步分隔条时递归
        self._split_sizes = None             # 收到/回复两框的共享分隔比例
        self._save_timer = QTimer(self)      # 去抖：连改时合并落盘
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._commit)
        self._stats_timer = QTimer(self)     # A3：定时把各行命中计数刷成运行态 _hits（仅窗口可见时跑，见 show/hideEvent）
        self._stats_timer.setInterval(700)
        self._stats_timer.timeout.connect(self._refresh_stats)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(9, 0, 0, 0)   # 与下方带 1px 边框的「帧头组帧」框/规则行的复选框左缘对齐
        self.cb_enable = QCheckBox()
        self.cb_enable.setObjectName("ArEnable")
        self.cb_enable.setChecked(bool(getattr(app, "_ar_on", False)))
        self.cb_enable.toggled.connect(self._on_enable)
        top.addWidget(self.cb_enable)
        top.addStretch(1)
        self.btn_test = QPushButton()           # A2 规则测试器（离线预览）
        self.btn_test.setObjectName("PlotGhostBtn")
        self.btn_test.clicked.connect(self._open_tester)
        top.addWidget(self.btn_test)
        self.btn_reset_stats = QPushButton()    # A3 重置命中统计
        self.btn_reset_stats.setObjectName("PlotGhostBtn")
        self.btn_reset_stats.clicked.connect(self._on_reset_stats)
        top.addWidget(self.btn_reset_stats)
        self.btn_modbus = QPushButton()         # B4 Modbus 从机配置入口（启用时按钮带 ● 标记）
        self.btn_modbus.setObjectName("PlotGhostBtn")
        self.btn_modbus.clicked.connect(self._open_modbus)
        top.addWidget(self.btn_modbus)
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

        # B4：Modbus 从机模式提示条（开启时显示，说明下方规则/状态机/帧头组帧不参与）
        self.lbl_modbus_active = QLabel()
        self.lbl_modbus_active.setObjectName("ArModbusBanner")   # 醒目:主色加粗(refresh_theme 里样式)
        self.lbl_modbus_active.setWordWrap(True)
        self.lbl_modbus_active.setContentsMargins(9, 0, 0, 0)  # 左缩进 9px：行首 ● 与「启用」/各框复选框左缘对齐
        self.lbl_modbus_active.setVisible(False)
        root.addWidget(self.lbl_modbus_active)

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
        self.lbl_frame_desc = QLabel()        # 右侧一句话说明
        self.lbl_frame_desc.setObjectName("ArDesc")
        frow.addWidget(self.lbl_frame_desc)
        self.btn_frame_help = QPushButton("?")    # 「?」→ 带例子的用法说明
        self.btn_frame_help.setObjectName("ArHelpBtn")
        self.btn_frame_help.setFixedSize(24, 24)
        self.btn_frame_help.setCursor(Qt.PointingHandCursor)
        self.btn_frame_help.clicked.connect(
            lambda *_: self._show_help_dlg(self.app._t("ar_frame_help_title"),
                                           self.app._t("ar_frame_help")))
        frow.addWidget(self.btn_frame_help)
        root.addWidget(self._frame_box)

        # C6 全局故障注入（整条串口一份）：按概率丢包/错CRC/错长度，专测主机重传与容错
        self._fault_box = QFrame()
        self._fault_box.setObjectName("ArFrameBox")    # 复用带边框样式
        xrow = QHBoxLayout(self._fault_box)
        xrow.setContentsMargins(8, 6, 8, 6)
        xrow.setSpacing(6)
        xc = getattr(app, "_ar_fault", {}) or {}
        self.cb_fault_on = QCheckBox()
        self.cb_fault_on.setChecked(bool(xc.get("on")))
        self.cb_fault_on.toggled.connect(self._schedule)
        xrow.addWidget(self.cb_fault_on)
        self.lbl_fdrop = QLabel()
        xrow.addWidget(self.lbl_fdrop)
        self.ed_fdrop = QLineEdit(str(xc.get("drop", 0)))
        self.ed_fdrop.setMaximumWidth(44)
        self.ed_fdrop.textChanged.connect(self._schedule)
        xrow.addWidget(self.ed_fdrop)
        xrow.addWidget(QLabel("%"))
        self.lbl_fbadcrc = QLabel()
        xrow.addWidget(self.lbl_fbadcrc)
        self.ed_fbadcrc = QLineEdit(str(xc.get("badcrc", 0)))
        self.ed_fbadcrc.setMaximumWidth(44)
        self.ed_fbadcrc.textChanged.connect(self._schedule)
        xrow.addWidget(self.ed_fbadcrc)
        xrow.addWidget(QLabel("%"))
        self.lbl_fbadlen = QLabel()
        xrow.addWidget(self.lbl_fbadlen)
        self.ed_fbadlen = QLineEdit(str(xc.get("badlen", 0)))
        self.ed_fbadlen.setMaximumWidth(44)
        self.ed_fbadlen.textChanged.connect(self._schedule)
        xrow.addWidget(self.ed_fbadlen)
        xrow.addWidget(QLabel("%"))
        xrow.addStretch(1)
        self.lbl_fault_desc = QLabel()        # 右侧一句话说明
        self.lbl_fault_desc.setObjectName("ArDesc")
        xrow.addWidget(self.lbl_fault_desc)
        self.btn_fault_help = QPushButton("?")    # 「?」→ 带例子的用法说明
        self.btn_fault_help.setObjectName("ArHelpBtn")
        self.btn_fault_help.setFixedSize(24, 24)
        self.btn_fault_help.setCursor(Qt.PointingHandCursor)
        self.btn_fault_help.clicked.connect(
            lambda *_: self._show_help_dlg(self.app._t("ar_fault_help_title"),
                                           self.app._t("ar_fault_help")))
        xrow.addWidget(self.btn_fault_help)
        root.addWidget(self._fault_box)

        # C8 多步状态机（全局）：每条规则可「仅在某状态应答」并「应答后跳转」，串成按帧序列推进的握手。
        # 启用后每行才显示 when/goto 两列（_apply_sm_cols 控制）；关闭=忽略，等于普通模式。
        self._sm_box = QFrame()
        self._sm_box.setObjectName("ArFrameBox")    # 复用带边框样式
        srow = QHBoxLayout(self._sm_box)
        srow.setContentsMargins(8, 6, 8, 6)
        srow.setSpacing(6)
        sc = getattr(app, "_ar_sm", {}) or {}
        self.cb_sm_on = QCheckBox()
        self.cb_sm_on.setChecked(bool(sc.get("on")))
        self.cb_sm_on.toggled.connect(self._on_sm_toggle)
        srow.addWidget(self.cb_sm_on)
        self.lbl_sm_init = QLabel()
        srow.addWidget(self.lbl_sm_init)
        self.ed_sm_init = QLineEdit(str(sc.get("init", "")))
        self.ed_sm_init.setMaximumWidth(90)
        self.ed_sm_init.textChanged.connect(self._schedule)
        srow.addWidget(self.ed_sm_init)
        self.lbl_sm_cur = QLabel()                  # "当前"
        srow.addWidget(self.lbl_sm_cur)
        self.lbl_sm_cur_val = QLabel()              # 实时当前状态值（_refresh_stats 刷新）
        self.lbl_sm_cur_val.setObjectName("ArHits")
        srow.addWidget(self.lbl_sm_cur_val)
        self.btn_sm_reset = QPushButton()
        self.btn_sm_reset.setObjectName("PlotGhostBtn")
        self.btn_sm_reset.clicked.connect(self._on_sm_reset)
        srow.addWidget(self.btn_sm_reset)
        srow.addStretch(1)
        self.lbl_sm_desc = QLabel()                 # 右侧一句话说明
        self.lbl_sm_desc.setObjectName("ArDesc")
        srow.addWidget(self.lbl_sm_desc)
        self.btn_sm_help = QPushButton("?")
        self.btn_sm_help.setObjectName("ArHelpBtn")
        self.btn_sm_help.setFixedSize(24, 24)
        self.btn_sm_help.setCursor(Qt.PointingHandCursor)
        self.btn_sm_help.clicked.connect(
            lambda *_: self._show_help_dlg(self.app._t("ar_sm_help_title"),
                                           self.app._t("ar_sm_help")))
        srow.addWidget(self.btn_sm_help)
        root.addWidget(self._sm_box)

        self._rows_host = QWidget()
        self._rows_v = QVBoxLayout(self._rows_host)
        self._rows_v.setContentsMargins(0, 0, 0, 0)
        self._rows_v.setSpacing(4)
        self._rows_v.addStretch(1)
        self._rows_host.setAutoFillBackground(False)
        scroll = QScrollArea()
        self._rows_scroll = scroll                  # 存引用：Modbus 开启时整块置灰
        scroll.setObjectName("ArScroll")
        scroll.setWidget(self._rows_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        root.addWidget(scroll, 100)   # 大 stretch：规则区可见时填满；末尾再留 stretch 1 锚定（规则区隐藏时把内容顶到上方）
        root.addStretch(1)            # Modbus 模式隐藏规则区后，由它占住下方空白，避免故障注入框上下飘

        self.retranslate()
        self.reload_rows()    # 初次构造也走统一路径
        self.refresh_theme()

    # ---------------- 规则行 ----------------
    def _add_row(self, rule=None):
        t = self.app._t
        rule = rule or {}
        self._rid_seq += 1
        rid = self._rid_seq
        rule["_rid"] = rid          # 给源规则 dict 盖同一稳定 id（_ 前缀，落盘时剥离），供 _commit 按身份迁移运行态
        row = QWidget()
        row.setObjectName("ArRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 3, 6, 3)   # 左 8：与各框（ArScroll 1px 边框 + 8）同列，勾选框左缘对齐
        h.setSpacing(0)                    # 空复选框后不再叠加布局间距，使「收到」与上方复选框文字左缘对齐

        cb_on = QCheckBox()
        cb_on.setChecked(bool(rule.get("on", True)))
        ed_match = QLineEdit(str(rule.get("match") or ""))   # str() 容错：配置被手改成非字符串/null 也不崩
        ed_match.setPlaceholderText(t("ar_match_ph"))
        btn_mhelp = QPushButton("?")            # D：匹配掩码语法小帮助（点 → 示例气泡）
        btn_mhelp.setObjectName("ArHelpBtn")
        btn_mhelp.setFixedSize(20, 20)
        btn_mhelp.setCursor(Qt.PointingHandCursor)
        btn_mhelp.setToolTip({"zh": "匹配语法 / 掩码示例", "en": "Match syntax / mask examples",
                              "zh_tw": "匹配語法 / 遮罩範例"}.get(self.app._lang, "Match syntax"))
        btn_mhelp.clicked.connect(lambda *_: self._show_mask_help(btn_mhelp))
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
        ed_reply = QLineEdit(str(rule.get("reply") or ""))   # 同上：str() 容错
        ed_reply.setPlaceholderText(t("ar_reply_ph"))
        cb_rhex = QCheckBox("HEX")
        cb_rhex.setChecked(bool(rule.get("reply_hex", True)))
        cb_cs = QComboBox()
        for k in CHECKSUM_KEYS:
            cb_cs.addItem(t(k))
        cb_cs.setCurrentIndex(_i(rule.get("cs", 0)))
        btn_seg = QPushButton()                 # 「校验段」(内层/额外校验) 编辑入口；有段显示数量
        btn_seg.setObjectName("ArSegBtn")
        btn_seg.setCursor(Qt.PointingHandCursor)
        btn_script = QPushButton()              # B5「脚本」编辑入口；有脚本显 ●
        btn_script.setObjectName("ArSegBtn")
        btn_script.setCursor(Qt.PointingHandCursor)
        # delay=回复 turnaround；cooldown=触发限流（两回事，旧 cooldown 配置原义保留）
        ed_cd = QLineEdit(str(rule.get("delay", "0")))   # C7：支持 "100"(固定) 或 "100-300"(随机范围)
        ed_cd.setMaximumWidth(72)
        ed_cd.setToolTip(t("ar_delay_tip"))
        ed_cdwn = QLineEdit(str(_i(rule.get("cooldown", 0))))
        ed_cdwn.setMaximumWidth(56)
        ed_cdwn.setToolTip(t("ar_cooldown_tip"))
        ed_gap = QLineEdit(str(_i(rule.get("gap", 0))))   # 整包静默(实际取各规则最大值)
        ed_gap.setMaximumWidth(56)
        ed_gap.setToolTip(t("ar_gap_tip"))
        btn_del = QPushButton("✕")
        btn_del.setObjectName("ArDelBtn")
        btn_del.setFixedSize(26, 26)
        lbl_hits = QLabel()                      # A3 命中计数（_refresh_stats 定时刷新）
        lbl_hits.setObjectName("ArHits")
        # C8 状态机：when=仅在此状态才命中（可逗号分隔多个），goto=应答后跳转到。仅状态机开启时显示+生效。
        ed_when = QLineEdit(str(rule.get("when") or ""))     # str() 容错：手改成非字符串/null 也不崩
        ed_when.setMaximumWidth(80)
        ed_goto = QLineEdit(str(rule.get("goto") or ""))
        ed_goto.setMaximumWidth(80)

        # 共所有可翻译子件存入 rec：retranslate() 切语言时统一刷新（否则 label/combo/tooltip 残留旧语言）
        lbl_match = QLabel(t("ar_match"))
        lbl_verify = QLabel(t("ar_verify"))
        lbl_gap = QLabel(t("ar_gap"))
        lbl_reply = QLabel(t("ar_reply"))
        lbl_delay = QLabel(t("ar_delay"))
        lbl_cdwn = QLabel(t("ar_cooldown"))
        rec = {"w": row, "on": cb_on, "match": ed_match, "mhex": cb_mhex, "mode": cb_mode,
               "verify": cb_verify, "reply": ed_reply, "rhex": cb_rhex, "cs": cb_cs,
               "seg_btn": btn_seg, "cs_segs": list(rule.get("cs_segs", []) or []),
               "script_btn": btn_script, "script": str(rule.get("script") or ""),
               "script_on": bool(rule.get("script_on", True)),
               "hits_lbl": lbl_hits, "mhelp": btn_mhelp, "_rid": rid,
               "cd": ed_cd, "cdwn": ed_cdwn, "gap": ed_gap,
               "when": ed_when, "goto": ed_goto,
               "lbl_match": lbl_match, "lbl_verify": lbl_verify, "lbl_gap": lbl_gap,
               "lbl_reply": lbl_reply, "lbl_delay": lbl_delay, "lbl_cdwn": lbl_cdwn}
        btn_del.clicked.connect(lambda *_: self._del_row(rec))
        btn_seg.clicked.connect(lambda *_: self._edit_cs_segs(rec))
        btn_script.clicked.connect(lambda *_: self._edit_script(rec))
        self._update_seg_btn(rec)
        self._update_script_btn(rec)
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
        ed_when.textChanged.connect(self._schedule)
        ed_goto.textChanged.connect(self._schedule)

        # 「收到」组（收包侧：匹配/HEX/模式/收校验/整包超时）
        left = QWidget()
        lh = QHBoxLayout(left)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(6)
        lh.addWidget(ed_when)          # C8：仅状态（默认隐藏，状态机开启时显示）
        lh.addWidget(lbl_match)
        lh.addWidget(ed_match, 1)
        lh.addWidget(btn_mhelp)
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
        rh.addWidget(btn_seg)
        rh.addWidget(btn_script)
        rh.addWidget(lbl_delay)
        rh.addWidget(ed_cd)
        rh.addWidget(QLabel("ms"))
        rh.addWidget(lbl_cdwn)
        rh.addWidget(ed_cdwn)
        rh.addWidget(QLabel("ms"))
        rh.addWidget(ed_goto)          # C8：应答后跳转（默认隐藏，状态机开启时显示）
        # 两组之间放分隔条：拖动即可调「收到框」「回复框」宽度（各行同步）
        split = QSplitter(Qt.Horizontal)
        split.setObjectName("ArRowSplit")
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        split.addWidget(left)
        split.addWidget(right)
        split.splitterMoved.connect(lambda *_: self._sync_splitters(split))
        rec["split"] = split

        h.addWidget(cb_on)            # 启用勾选框直接放行布局(与各框勾选框同层级)，避免分隔条嵌套挤偏左缘
        h.addWidget(split, 1)
        h.addSpacing(6)
        h.addWidget(lbl_hits)
        h.addSpacing(6)
        h.addWidget(btn_del)
        if self._split_sizes:                # 新行采用当前已有的分隔比例
            split.setSizes(self._split_sizes)
        else:
            split.setSizes([360, 480])
        self._rows_v.insertWidget(self._rows_v.count() - 1, row)
        self._rows.append(rec)
        _smon = bool(getattr(self, "cb_sm_on", None) and self.cb_sm_on.isChecked())
        ed_when.setVisible(_smon)     # C8：仅状态机开启时显示这两列
        ed_goto.setVisible(_smon)

    def _apply_sm_cols(self):
        """状态机开 → 显示每行 when/goto 列；关 → 隐藏（保持行不拥挤，引擎也忽略 when/goto）。"""
        on = self.cb_sm_on.isChecked()
        for rec in self._rows:
            for k in ("when", "goto"):
                w = rec.get(k)
                if w is not None:
                    w.setVisible(on)

    def _on_sm_toggle(self, on):
        """状态机开关：显示/隐藏每行 when/goto 列 + 去抖落盘 _ar_sm.on。"""
        self._apply_sm_cols()
        self._schedule()

    def _on_sm_reset(self):
        """把『当前状态』拉回初始状态。有未提交编辑先落盘，再走 _ar_reset_state
        （复位到 init + 代际 +1，作废在途延迟应答，避免旧 goto 稍后覆盖这次重置）。"""
        if self._save_timer.isActive():
            self._commit()
        self.app._ar_reset_state()
        self._refresh_stats()

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

    # ---------------- A3 命中统计 ----------------
    def _refresh_stats(self):
        """定时把各行「命中 N」刷成对应规则的运行态 _hits（按 _rid 身份对应，不按索引）。
        隐藏时直接返回（配合 show/hideEvent 停表，避免关窗后空跑）。"""
        if not self.isVisible():
            return
        by_rid = {r.get("_rid"): r for r in getattr(self.app, "_ar_rules", [])
                  if r.get("_rid") is not None}
        t = self.app._t
        for rec in self._rows:
            lbl = rec.get("hits_lbl")
            if lbl is None:
                continue
            r = by_rid.get(rec.get("_rid"))
            n = self.app._ar_to_int(r.get("_hits", 0)) if r else 0
            lbl.setText(t("ar_hits", n=n))
        # C8：实时刷新「当前状态」（空状态显示占位）
        cur = getattr(self.app, "_ar_state", "")
        self.lbl_sm_cur_val.setText(cur if cur else t("ar_sm_empty"))

    def _on_reset_stats(self):
        self.app._ar_reset_stats()
        self._refresh_stats()

    # ---------------- A2 规则测试器（离线预览）----------------
    def _open_tester(self):
        """输入一帧 HEX → 调 app._ar_preview 看命中哪条规则 + 应答预览（不发送、不计数）。"""
        t = self.app._t
        dlg = QDialog(self)
        dlg.setWindowTitle(t("ar_test_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(560, 340)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        hint = QLabel(t("ar_test_hint"))
        hint.setWordWrap(True)
        hint.setObjectName("ArCsHint")
        v.addWidget(hint)
        row = QHBoxLayout()
        ed = QLineEdit()
        ed.setPlaceholderText(t("ar_test_ph"))
        btn = QPushButton(t("ar_test_run"))
        btn.setObjectName("PlotGhostBtn")
        row.addWidget(ed, 1)
        row.addWidget(btn)
        v.addLayout(row)
        out = QLabel()
        out.setWordWrap(True)
        out.setAlignment(Qt.AlignTop)
        out.setTextInteractionFlags(Qt.TextSelectableByMouse)
        out.setObjectName("ArTestOut")
        oscroll = QScrollArea()
        oscroll.setObjectName("ArScroll")
        oscroll.setWidget(out)
        oscroll.setWidgetResizable(True)
        oscroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(oscroll, 1)

        def run():
            s = "".join(ch for ch in ed.text() if ch not in " \t\r\n-:,;")
            s = s.replace("0x", "").replace("0X", "")
            frame = None
            if s and len(s) % 2 == 0:
                try:
                    frame = bytes.fromhex(s)
                except ValueError:
                    frame = None
            if frame is None:
                out.setText(t("ar_test_bad_hex"))
                return
            res = self.app._ar_preview(frame)
            sm_on = res.get("sm_on")
            st = res.get("state", "")
            st_disp = st if st else t("ar_sm_empty")
            lines = []
            if sm_on:                                   # C8：先显示当前状态
                lines.append(t("ar_test_state", s=st_disp))
            if res.get("index", -1) < 0:
                if sm_on and res.get("state_skip") is not None:
                    lines.append(t("ar_test_state_skip", s=st_disp))   # 内容命中但状态不符
                else:
                    lines.append(t("ar_test_no_match"))
                out.setText("\n".join(lines))
                return
            lines.append(t("ar_test_matched", n=res["index"] + 1))
            if not res.get("verify_ok"):
                lines.append(t("ar_test_verify_fail"))
            else:
                serr = res.get("script_err")
                if serr:
                    lines.append(t("ar_script_err", e=serr))   # B5：脚本错误显示在测试器里
                else:
                    reps = res.get("replies", [])
                    if not reps:
                        lines.append(t("ar_test_no_reply"))
                    for r in reps:
                        lines.append("→ " + (r if r else t("ar_test_reply_bad")))
            if sm_on and res.get("goto"):               # C8：应答后跳转
                lines.append(t("ar_test_goto", s=res["goto"]))
            out.setText("\n".join(lines))

        btn.clicked.connect(lambda *_: run())
        ed.returnPressed.connect(run)
        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
            QLabel#ArCsHint {{ color: {c['text_sec']}; background: transparent;
                               font-family: 'Segoe UI'; font-size: 11px; }}
            QLabel#ArTestOut {{ color: {c['text']}; background: transparent;
                                font-family: 'Segoe UI'; font-size: 12px; }}
            QScrollArea#ArScroll {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
            QScrollArea#ArScroll > QWidget > QWidget {{ background: transparent; }}
            QPushButton#PlotGhostBtn {{
                background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px;
                font-family: 'Segoe UI'; font-size: 12px; padding: 5px 16px;
            }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        """))
        _set_win_titlebar_dark(dlg, self.app._theme().get("mode") == "dark")
        dlg.exec_()

    # ---------------- 校验段（内层/额外校验）----------------
    def _update_seg_btn(self, rec):
        """按 rec['cs_segs'] 数量刷新按钮文案：有段显示「校验段 (N)」。"""
        btn = rec.get("seg_btn")
        if btn is not None:
            n = len(rec.get("cs_segs", []) or [])
            btn.setText(self.app._t("ar_cs_btn") + (f" ({n})" if n else ""))

    def _update_script_btn(self, rec):
        """有脚本显「脚本 ●」，否则「脚本」。"""
        btn = rec.get("script_btn")
        if btn is None:
            return
        has_code = bool((rec.get("script") or "").strip())
        active = has_code and bool(rec.get("script_on", True))    # 启用且有代码才生效
        btn.setText(self.app._t("ar_script_btn"))   # 不加 ●，纯靠颜色区分：启用=蓝、禁用/无码=灰
        btn.setToolTip(self.app._t("ar_script_tip"))
        c = chrome_for(self.app._theme_id())
        if active:   # 启用：按钮文字 + ● 变蓝(accent)，一眼看出此行走脚本
            btn.setStyleSheet(
                "QPushButton{background-color:transparent;color:%s;border:1px solid %s;"
                "border-radius:6px;font-family:'Segoe UI';font-size:11px;padding:3px 8px;font-weight:700;}"
                "QPushButton:hover{background-color:%s;color:%s;}"
                % (c["accent"], c["accent"], c["ghost_hover"], c["accent"]))
        else:
            btn.setStyleSheet("")   # 无代码或已禁用 → 回退灰样式（有代码但禁用时 ● 为灰）
        # 仅「启用且有代码」时该行静态回复部分让位置灰；禁用脚本则恢复静态可编辑
        for key in ("lbl_reply", "reply", "rhex", "cs", "seg_btn"):
            w = rec.get(key)
            if w is not None:
                w.setEnabled(not active)
        if rec.get("reply") is not None:
            rec["reply"].setToolTip(self.app._t("ar_script_mode_tip") if active else "")

    def _edit_script(self, rec):
        """编辑某条规则的「脚本应答」(Python)：定义 reply(frame, ctx) 动态生成应答。
        确定后写回 rec['script'] 去抖落盘。空脚本=不启用，行为与静态模板一致。"""
        t = self.app._t
        dlg = QDialog(self)
        dlg.setWindowTitle(t("ar_script_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(660, 500)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        hint = QLabel(t("ar_script_help"))
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.RichText)
        hint.setObjectName("ArCsHint")
        v.addWidget(hint)
        editor = QPlainTextEdit()
        editor.setObjectName("ArScriptEdit")
        editor.setPlainText((rec.get("script") or "").strip() or t("ar_script_tmpl"))
        v.addWidget(editor, 1)
        # 内置测试：输入一帧 → 跑当前编辑器里的脚本看输出（无需先确定、无副作用）
        trow = QHBoxLayout()
        trow.setSpacing(6)
        ed_test = QLineEdit()
        ed_test.setPlaceholderText(t("ar_script_test_ph"))
        btn_test = QPushButton(t("ar_test_run"))
        btn_test.setObjectName("PlotGhostBtn")
        trow.addWidget(ed_test, 1)
        trow.addWidget(btn_test)
        v.addLayout(trow)
        lbl_out = QLabel("")
        lbl_out.setWordWrap(True)
        lbl_out.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(lbl_out)

        def run_test():
            s = "".join(ch for ch in ed_test.text() if ch not in " \t\r\n-:,;")
            s = s.replace("0x", "").replace("0X", "")
            frame = None
            if s and len(s) % 2 == 0:
                try:
                    frame = bytes.fromhex(s)
                except ValueError:
                    frame = None
            if frame is None:
                lbl_out.setText(t("ar_test_bad_hex"))
                return
            parts, err = self.app._ar_script_eval(
                {"script": editor.toPlainText()}, frame, preview=True)
            if err:
                lbl_out.setText(t("ar_script_err", e=err))
            elif parts:
                lbl_out.setText(" | ".join(parts))
            else:
                lbl_out.setText(t("ar_script_none"))

        btn_test.clicked.connect(run_test)

        btns = QHBoxLayout()
        cb_en = QCheckBox(t("ar_script_enable"))          # 左下角：启用/禁用脚本（保留代码不删）
        cb_en.setChecked(bool(rec.get("script_on", True)))
        cb_en.toggled.connect(lambda on: editor.setEnabled(on))
        editor.setEnabled(cb_en.isChecked())              # 禁用 → 编辑器变灰、不可输入
        btns.addWidget(cb_en)
        btns.addStretch(1)
        lmap = lambda zh, en, tw: {"zh": zh, "en": en, "zh_tw": tw}.get(self.app._lang, en)
        btn_cancel = QPushButton(lmap("取消", "Cancel", "取消"))
        btn_cancel.setObjectName("PlotGhostBtn")
        btn_ok = QPushButton(lmap("确定", "OK", "確定"))
        btn_ok.setObjectName("ArOkBtn")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(dlg.accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        v.addLayout(btns)
        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
            QDialog {{ background-color: {c['window_bg']}; }}
            QLabel {{ color: {c['text']}; background: transparent;
                     font-family: 'Segoe UI'; font-size: 12px; }}
            QLabel#ArCsHint {{ color: {c['text_sec']}; }}
            QPlainTextEdit#ArScriptEdit {{ background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px;
                font-family: Menlo, Consolas, 'Courier New', monospace; font-size: 12px; }}
            QPlainTextEdit#ArScriptEdit:disabled {{ background-color: {c['window_bg']}; color: {c['text_sec']};
                border: 1px solid {c['separator']}; }}
            QLineEdit {{ background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px; padding: 4px; }}
            QPushButton#PlotGhostBtn {{ background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px; padding: 5px 14px; }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
            QPushButton#ArOkBtn {{ background-color: {c['accent']}; color: #FFFFFF;
                border: none; border-radius: 6px; padding: 5px 16px; }}
        """))
        if dlg.exec_() == QDialog.Accepted:
            rec["script"] = editor.toPlainText().strip()
            rec["script_on"] = cb_en.isChecked()
            self._update_script_btn(rec)
            self._schedule()

    def _edit_cs_segs(self, rec):
        """编辑某条应答规则的「校验段」列表（算法 | 起始 | 结束 | 填入位置），
        确定后写回 rec['cs_segs'] 并去抖落盘。每段对应答帧 [start..end] 算校验、
        写到 at（留空=追加），在尾部 cs 之前、按从上到下顺序计算。"""
        t = self.app._t
        _i = self.app._ar_to_int
        dlg = QDialog(self)
        dlg.setWindowTitle(t("ar_cs_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(600, 380)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        hint = QLabel(t("ar_cs_help"))
        hint.setWordWrap(True)
        hint.setObjectName("ArCsHint")
        v.addWidget(hint)
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        for key, w in (("ar_cs_algo", 150), ("ar_cs_start", 60),
                       ("ar_cs_end", 60), ("ar_cs_at", 80)):
            lb = QLabel(t(key))
            lb.setFixedWidth(w)
            hdr.addWidget(lb)
        hdr.addStretch(1)
        v.addLayout(hdr)
        rows_host = QWidget()
        rows_v = QVBoxLayout(rows_host)
        rows_v.setContentsMargins(0, 0, 0, 0)
        rows_v.setSpacing(4)
        rows_v.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("ArScroll")
        scroll.setWidget(rows_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        seg_rows = []

        def add_seg(seg=None):
            seg = seg or {}
            r = QWidget()
            rh = QHBoxLayout(r)
            rh.setContentsMargins(0, 0, 0, 0)
            rh.setSpacing(6)
            algo = QComboBox()
            algo.setFixedWidth(150)
            for k in CHECKSUM_KEYS:
                algo.addItem(t(k))
            algo.setCurrentIndex(_i(seg.get("algo", 0)))
            ed_start = QLineEdit(str(_i(seg.get("start", 0))))
            ed_start.setFixedWidth(60)
            e_end = seg.get("end", None)
            ed_end = QLineEdit("" if e_end in (None, "") else str(e_end))
            ed_end.setFixedWidth(60)
            e_at = seg.get("at", None)
            ed_at = QLineEdit("" if e_at in (None, "") else str(e_at))
            ed_at.setFixedWidth(80)
            btn_x = QPushButton("✕")
            btn_x.setObjectName("ArDelBtn")
            btn_x.setFixedSize(26, 26)
            srec = {"w": r, "algo": algo, "start": ed_start, "end": ed_end, "at": ed_at}

            def _del():
                r.setParent(None)
                r.deleteLater()
                if srec in seg_rows:
                    seg_rows.remove(srec)

            btn_x.clicked.connect(lambda *_: _del())
            for w in (algo, ed_start, ed_end, ed_at, btn_x):
                rh.addWidget(w)
            rh.addStretch(1)
            rows_v.insertWidget(rows_v.count() - 1, r)
            seg_rows.append(srec)

        for seg in (rec.get("cs_segs", []) or []):
            add_seg(seg)

        btn_add = QPushButton(t("ar_cs_add"))
        btn_add.setObjectName("PlotGhostBtn")
        btn_add.clicked.connect(lambda *_: add_seg())
        ok_txt = {"zh": "确定", "en": "OK", "zh_tw": "確定"}.get(self.app._lang, "OK")
        cancel_txt = {"zh": "取消", "en": "Cancel", "zh_tw": "取消"}.get(self.app._lang, "Cancel")
        btn_ok = QPushButton(ok_txt)
        btn_ok.setObjectName("PlotGhostBtn")
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel = QPushButton(cancel_txt)
        btn_cancel.setObjectName("PlotGhostBtn")
        btn_cancel.clicked.connect(dlg.reject)
        brow = QHBoxLayout()
        brow.addWidget(btn_add)
        brow.addStretch(1)
        brow.addWidget(btn_cancel)
        brow.addWidget(btn_ok)
        v.addLayout(brow)

        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
            QLabel#ArCsHint {{ color: {c['text_sec']}; background: transparent;
                               font-family: 'Segoe UI'; font-size: 11px; }}
            QScrollArea#ArScroll {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
            QScrollArea#ArScroll > QWidget > QWidget {{ background: transparent; }}
            QPushButton#PlotGhostBtn {{
                background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px;
                font-family: 'Segoe UI'; font-size: 12px; padding: 5px 16px;
            }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
            QPushButton#ArDelBtn {{
                background-color: transparent; color: {c['text_sec']};
                border: 1px solid {c['separator']}; border-radius: 6px; font-size: 13px;
            }}
            QPushButton#ArDelBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['danger']}; }}
        """))
        _set_win_titlebar_dark(dlg, self.app._theme().get("mode") == "dark")
        if dlg.exec_() != QDialog.Accepted:
            return

        def _opt(le):
            txt = le.text().strip()
            if txt == "":
                return None
            try:
                return int(txt)
            except ValueError:
                return None     # 非法输入按"留空"处理：结束=到帧尾、填入位置=追加（绝不静默覆盖偏移 0）

        segs = []
        for sr in seg_rows:
            ai = sr["algo"].currentIndex()
            if ai <= 0:                 # 算法=无 → 该段无意义，丢弃
                continue
            st = _opt(sr["start"])
            segs.append({"algo": ai, "start": 0 if st is None else st,
                         "end": _opt(sr["end"]), "at": _opt(sr["at"])})
        rec["cs_segs"] = segs
        self._update_seg_btn(rec)
        self._schedule()

    # ---------------- B4 Modbus 从机 ----------------
    _MB_SPACES = (("holding", "ar_mb_holding"), ("input", "ar_mb_input"),
                  ("coils", "ar_mb_coil"), ("discrete", "ar_mb_discrete"))

    def _update_modbus_btn(self):
        """按钮文案 + 模式切换：Modbus 启用时按钮加 ● 标记，并把「不参与」的部分（规则区 / 状态机 /
        帧头组帧 + 规则操作按钮）明显淡化（~35% 透明 + 禁用）——保留原位、内容仍在但一眼看出是灰的
        （macOS 浅色主题下单纯 setEnabled 太弱、直接隐藏又留大片空白）。故障注入框保留（仍作用于
        Modbus 响应）+ 顶部提示条，消除「看着启用却不响应」的困惑。"""
        on = bool((getattr(self.app, "_ar_modbus", {}) or {}).get("on"))
        self.btn_modbus.setText(self.app._t("ar_modbus") + (" ●" if on else ""))
        # Modbus 开 → 不参与的部分全部隐藏（帧头组帧 / 状态机 / 规则列表 + 测试·重置·添加），
        # 只留 故障注入框（仍作用于 Modbus 响应）+ 醒目提示条；末尾 stretch 把内容顶到上方、下方留空白。
        for w in (self._rows_scroll, self._sm_box, self._frame_box,
                  self.btn_test, self.btn_reset_stats, self.btn_add):
            w.setVisible(not on)
        self.lbl_modbus_active.setVisible(on)
        if on:
            self.lbl_modbus_active.setText(self.app._t("ar_modbus_active"))

    def _open_modbus(self):
        """B4：编辑 Modbus 从机配置（启用 + 从机地址 + 寄存器表）。确定 → app._set_ar_modbus()。"""
        t = self.app._t
        _i = self.app._ar_to_int
        cfg = getattr(self.app, "_ar_modbus", {}) or {}
        space_keys = [s[0] for s in self._MB_SPACES]

        def _parse_int(txt, default=None):
            txt = (txt or "").strip()
            if txt == "":
                return default
            try:
                return int(txt, 16) if txt.lower().startswith("0x") else int(txt)
            except ValueError:
                return default

        dlg = QDialog(self)
        dlg.setWindowTitle(t("ar_modbus_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(640, 470)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        hint = QLabel(t("ar_modbus_hint"))
        hint.setWordWrap(True)
        hint.setObjectName("ArCsHint")
        v.addWidget(hint)

        # 顶行：启用 + 从机地址 + ? 帮助
        top = QHBoxLayout()
        top.setSpacing(8)
        cb_on = QCheckBox(t("ar_modbus_on"))
        cb_on.setChecked(bool(cfg.get("on")))
        top.addWidget(cb_on)
        top.addSpacing(12)
        top.addWidget(QLabel(t("ar_modbus_addr")))
        ed_addr = QLineEdit(str(_i(cfg.get("addr", 1))))
        ed_addr.setFixedWidth(60)
        top.addWidget(ed_addr)
        top.addStretch(1)
        btn_help = QPushButton("?")
        btn_help.setObjectName("ArHelpBtn")
        btn_help.setFixedSize(24, 24)
        btn_help.setCursor(Qt.PointingHandCursor)
        btn_help.clicked.connect(
            lambda *_: self._show_help_dlg(t("ar_modbus_help_title"), t("ar_modbus_help")))
        top.addWidget(btn_help)
        v.addLayout(top)

        # 表头
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        lb_sp = QLabel(t("ar_modbus_space")); lb_sp.setFixedWidth(130); hdr.addWidget(lb_sp)
        lb_st = QLabel(t("ar_modbus_start")); lb_st.setFixedWidth(80); hdr.addWidget(lb_st)
        hdr.addWidget(QLabel(t("ar_modbus_values")), 1)
        hdr.addSpacing(32)
        v.addLayout(hdr)

        rows_host = QWidget()
        rows_v = QVBoxLayout(rows_host)
        rows_v.setContentsMargins(0, 0, 0, 0)
        rows_v.setSpacing(4)
        rows_v.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("ArScroll")
        scroll.setWidget(rows_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        reg_rows = []

        def add_reg(space="holding", start=0, values=""):
            r = QWidget()
            rh = QHBoxLayout(r)
            rh.setContentsMargins(0, 0, 0, 0)
            rh.setSpacing(6)
            cb_space = QComboBox()
            cb_space.setFixedWidth(130)
            for _k, lk in self._MB_SPACES:
                cb_space.addItem(t(lk))
            cb_space.setCurrentIndex(space_keys.index(space) if space in space_keys else 0)
            ed_start = QLineEdit(str(start))
            ed_start.setFixedWidth(80)
            ed_vals = QLineEdit(values)
            ed_vals.setPlaceholderText("0x1234, 100, 0x00FF …")
            btn_x = QPushButton("✕")
            btn_x.setObjectName("ArDelBtn")
            btn_x.setFixedSize(26, 26)
            rrec = {"w": r, "space": cb_space, "start": ed_start, "vals": ed_vals}

            def _del():
                r.setParent(None)
                r.deleteLater()
                if rrec in reg_rows:
                    reg_rows.remove(rrec)

            btn_x.clicked.connect(lambda *_: _del())
            rh.addWidget(cb_space)
            rh.addWidget(ed_start)
            rh.addWidget(ed_vals, 1)
            rh.addWidget(btn_x)
            rows_v.insertWidget(rows_v.count() - 1, r)
            reg_rows.append(rrec)

        # 从配置重建行：每个空间按「连续地址」分组成一行（start + 逗号分隔的值）
        def _runs(m):
            items = sorted((int(k), val) for k, val in (m or {}).items())
            out = []
            for a, val in items:
                if out and a == out[-1][0] + len(out[-1][1]):
                    out[-1][1].append(val)
                else:
                    out.append((a, [val]))
            return out

        any_row = False
        for space, _lk in self._MB_SPACES:
            is_bool = space in ("coils", "discrete")
            for start, vals in _runs(cfg.get(space)):
                vs = ", ".join(("1" if v else "0") if is_bool else str(int(v)) for v in vals)
                add_reg(space, start, vs)
                any_row = True
        if not any_row:
            add_reg()

        btn_add = QPushButton(t("ar_modbus_add"))
        btn_add.setObjectName("PlotGhostBtn")
        btn_add.clicked.connect(lambda *_: add_reg())
        ok_txt = {"zh": "确定", "en": "OK", "zh_tw": "確定"}.get(self.app._lang, "OK")
        cancel_txt = {"zh": "取消", "en": "Cancel", "zh_tw": "取消"}.get(self.app._lang, "Cancel")
        btn_ok = QPushButton(ok_txt); btn_ok.setObjectName("PlotGhostBtn"); btn_ok.clicked.connect(dlg.accept)
        btn_cancel = QPushButton(cancel_txt); btn_cancel.setObjectName("PlotGhostBtn"); btn_cancel.clicked.connect(dlg.reject)
        brow = QHBoxLayout()
        brow.addWidget(btn_add)
        brow.addStretch(1)
        brow.addWidget(btn_cancel)
        brow.addWidget(btn_ok)
        v.addLayout(brow)

        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
            QLabel#ArCsHint {{ color: {c['text_sec']}; background: transparent;
                               font-family: 'Segoe UI'; font-size: 11px; }}
            QScrollArea#ArScroll {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
            QScrollArea#ArScroll > QWidget > QWidget {{ background: transparent; }}
            QPushButton#PlotGhostBtn {{
                background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px;
                font-family: 'Segoe UI'; font-size: 12px; padding: 5px 16px;
            }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
            QPushButton#ArHelpBtn {{
                background-color: transparent; color: {c['text_sec']};
                border: 1px solid {c['separator']}; border-radius: 12px;
                font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
            }}
            QPushButton#ArHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
            QPushButton#ArDelBtn {{
                background-color: transparent; color: {c['text_sec']};
                border: 1px solid {c['separator']}; border-radius: 6px; font-size: 13px;
            }}
            QPushButton#ArDelBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['danger']}; }}
        """))
        _set_win_titlebar_dark(dlg, self.app._theme().get("mode") == "dark")
        if dlg.exec_() != QDialog.Accepted:
            return

        out = {"on": cb_on.isChecked(), "addr": _parse_int(ed_addr.text(), 1),
               "coils": {}, "discrete": {}, "holding": {}, "input": {}}
        for rr in reg_rows:
            space = space_keys[rr["space"].currentIndex()]
            start = _parse_int(rr["start"].text(), None)
            if start is None:
                continue
            is_bool = space in ("coils", "discrete")
            for off, tok in enumerate(rr["vals"].text().split(",")):
                val = _parse_int(tok, None)
                if val is None:
                    continue
                out[space][str(start + off)] = bool(val) if is_bool else (val & 0xFFFF)
        self.app._set_ar_modbus(out)
        self._update_modbus_btn()

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
        # C6 故障注入控件同步（配置导入 / 外部修改 _ar_fault 后）
        xc = getattr(self.app, "_ar_fault", {}) or {}
        xw = (self.cb_fault_on, self.ed_fdrop, self.ed_fbadcrc, self.ed_fbadlen)
        for w in xw:
            w.blockSignals(True)
        self.cb_fault_on.setChecked(bool(xc.get("on")))
        self.ed_fdrop.setText(str(xc.get("drop", 0)))
        self.ed_fbadcrc.setText(str(xc.get("badcrc", 0)))
        self.ed_fbadlen.setText(str(xc.get("badlen", 0)))
        for w in xw:
            w.blockSignals(False)
        # C8 状态机控件同步（配置导入 / 外部修改 _ar_sm 后）
        sc = getattr(self.app, "_ar_sm", {}) or {}
        sw = (self.cb_sm_on, self.ed_sm_init)
        for w in sw:
            w.blockSignals(True)
        self.cb_sm_on.setChecked(bool(sc.get("on")))
        self.ed_sm_init.setText(str(sc.get("init", "")))
        for w in sw:
            w.blockSignals(False)
        self._apply_sm_cols()      # 行重建后按当前开关显示/隐藏 when/goto 列
        self._update_modbus_btn()  # B4：配置导入后刷新 Modbus 按钮 ● 标记

    # ---------------- 落盘 ----------------
    def _schedule(self, *_):
        self._save_timer.start()

    def _on_enable(self, on):
        self.app._set_autoreply_enabled(on)

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
                "cs_segs": rec.get("cs_segs", []),
                "script": rec.get("script", ""),     # B5：脚本应答（Python），空=不启用
                "script_on": rec.get("script_on", True),   # 启用开关：禁用则保留代码但不生效
                "delay": rec["cd"].text().strip(),   # C7：存原始文本（"100" 或 "100-300"）

                "cooldown": _n(rec["cdwn"]),
                "gap": _n(rec["gap"]),
                "when": rec["when"].text().strip(),   # C8：仅在此状态(可逗号分隔)才命中；空=任意
                "goto": rec["goto"].text().strip(),   # C8：应答后跳转到的状态；空=不变
            })
        # 保留运行态命中统计/冷却：按稳定 id(_rid) 迁移（rules 与 _rows 同序一一对应），
        # 删中间行/重排后也不会张冠李戴（_last 是冷却时刻，错配会误抑制/误触发应答）。
        old_by_rid = {o.get("_rid"): o for o in getattr(self.app, "_ar_rules", [])
                      if o.get("_rid") is not None}
        for r, rec in zip(rules, self._rows):
            r["_rid"] = rec.get("_rid")
            src = old_by_rid.get(rec.get("_rid"))
            if src:
                for k in ("_hits", "_hit_time", "_last"):
                    if k in src:
                        r[k] = src[k]
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
        # C6 全局故障注入配置
        self.app._set_ar_fault({
            "on": self.cb_fault_on.isChecked(),
            "drop": _n(self.ed_fdrop),
            "badcrc": _n(self.ed_fbadcrc),
            "badlen": _n(self.ed_fbadlen),
        })
        # C8 状态机配置（放最后：_set_ar_sm 会把当前状态复位到新 init，要在上面各 _ar_reset_buf 之后）
        self.app._set_ar_sm({
            "on": self.cb_sm_on.isChecked(),
            "init": self.ed_sm_init.text().strip(),
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
        QPushButton#ArSegBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 6px;
            font-family: 'Segoe UI'; font-size: 11px; padding: 3px 8px;
        }}
        QPushButton#ArSegBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        QLabel#ArHits {{ color: {c['text_sec']}; font-family: 'Segoe UI'; font-size: 11px; }}
        QLabel#ArDesc {{ color: {c['text_sec']}; font-family: 'Segoe UI'; font-size: 11px; }}
        QLabel#ArModbusBanner {{ color: {c['accent']}; font-family: 'Segoe UI'; font-size: 12px; font-weight: 600; }}
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
        /* B5：脚本模式下该行静态回复部分置灰——明显的禁用态（扁平底 + 淡字 + 虚线框） */
        QLineEdit:disabled {{ background-color: {c['window_bg']}; color: {c['text_sec']};
            border: 1px solid {c['separator']}; }}
        QComboBox:disabled {{ background-color: {c['window_bg']}; color: {c['text_sec']};
            border: 1px solid {c['separator']}; }}
        QCheckBox:disabled {{ color: {c['text_sec']}; }}
        QPushButton#ArSegBtn:disabled {{ background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; }}
        QLabel:disabled {{ color: {c['text_sec']}; }}
        """))

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("ar_title"))
        self.cb_enable.setText(t("ar_enable"))
        self.btn_add.setText(t("ar_add"))
        self.btn_test.setText(t("ar_test"))
        self.btn_reset_stats.setText(t("ar_reset_stats"))
        self.btn_modbus.setToolTip(t("ar_modbus_tip"))
        self._update_modbus_btn()                    # B4：按钮文案(含 ● 标记)随语言/开关刷新
        self.btn_help.setToolTip(t("ar_help_btn"))   # 按钮文字固定 "?", 悬停看完整文案
        self.cb_frame_on.setText(t("ar_frame_on"))
        self.cb_frame_on.setToolTip(t("ar_frame_tip"))
        self.lbl_fhdr.setText(t("ar_frame_hdr"))
        self.lbl_foff.setText(t("ar_frame_off"))
        self.lbl_fwidth.setText(t("ar_frame_width"))
        self.lbl_fextra.setText(t("ar_frame_extra"))
        self.cb_fault_on.setText(t("ar_fault_on"))
        self.cb_fault_on.setToolTip(t("ar_fault_tip"))
        self.lbl_fdrop.setText(t("ar_fault_drop"))
        self.lbl_fbadcrc.setText(t("ar_fault_badcrc"))
        self.lbl_fbadlen.setText(t("ar_fault_badlen"))
        self.lbl_frame_desc.setText(t("ar_frame_desc"))
        self.lbl_fault_desc.setText(t("ar_fault_desc"))
        # C8 状态机框
        self.cb_sm_on.setText(t("ar_sm_on"))
        self.cb_sm_on.setToolTip(t("ar_sm_tip"))
        self.lbl_sm_init.setText(t("ar_sm_init"))
        self.ed_sm_init.setPlaceholderText(t("ar_sm_init_ph"))
        self.lbl_sm_cur.setText(t("ar_sm_cur"))
        self.btn_sm_reset.setText(t("ar_sm_reset"))
        self.lbl_sm_desc.setText(t("ar_sm_desc"))
        # 当前状态为空时显示本地化占位符 → 切语言时立即刷新（否则残留旧语言到下个 700ms tick）
        _cur = getattr(self.app, "_ar_state", "")
        self.lbl_sm_cur_val.setText(_cur if _cur else t("ar_sm_empty"))
        mode_items = [t("ar_mode_contains"), t("ar_mode_equals"), t("ar_mode_prefix")]
        cs_items = [t(k) for k in CHECKSUM_KEYS]
        for rec in self._rows:
            rec["match"].setPlaceholderText(t("ar_match_ph"))
            rec["mhelp"].setToolTip({"zh": "匹配语法 / 掩码示例", "en": "Match syntax / mask examples",
                                     "zh_tw": "匹配語法 / 遮罩範例"}.get(self.app._lang, "Match syntax"))
            rec["reply"].setPlaceholderText(t("ar_reply_ph"))
            rec["when"].setPlaceholderText(t("ar_when_ph"))    # C8
            rec["when"].setToolTip(t("ar_when_tip"))
            rec["goto"].setPlaceholderText(t("ar_goto_ph"))
            rec["goto"].setToolTip(t("ar_goto_tip"))
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
            rec["cd"].setToolTip(t("ar_delay_tip"))
            self._update_seg_btn(rec)
            rec["seg_btn"].setToolTip(t("ar_cs_tip"))
            self._update_script_btn(rec)
            rec["script_btn"].setToolTip(t("ar_script_tip"))
            rec["hits_lbl"].setToolTip(t("ar_hits_tip"))
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

    def _show_mask_help(self, anchor):
        """点「匹配」框旁的小 ? → 弹掩码语法示例气泡（Qt.Popup：点外部自动关闭）。"""
        pop = QDialog(self, Qt.Popup)
        pop.setObjectName("ArMaskTip")
        pop.setAttribute(Qt.WA_DeleteOnClose)   # 关闭即销毁，避免多次点击累积
        v = QVBoxLayout(pop)
        v.setContentsMargins(12, 10, 12, 10)
        lbl = QLabel(self.app._t("ar_mask_help"))
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(False)          # 每条示例单行不折行，气泡宽度自适应最长行
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)   # 例子可复制
        v.addWidget(lbl)
        c = chrome_for(self.app._theme_id())
        pop.setStyleSheet(localize_qss(f"""
            QDialog#ArMaskTip {{ background-color: {c['input_bg']};
                border: 1px solid {c['separator']}; border-radius: 8px; }}
            QLabel {{ color: {c['text']}; background: transparent;
                     font-family: 'Segoe UI'; font-size: 12px; }}
        """))
        pop.adjustSize()
        pop.move(anchor.mapToGlobal(QPoint(0, anchor.height() + 4)))
        pop.show()

    def _show_help_dlg(self, title=None, body=None):
        """弹独立窗口展示说明（富文本+可滚动）。无参=自动应答总说明；带 title/body=某框的用法举例。
        （顶部「?」走 clicked(checked=False)，title=False→走默认，仍是总说明。）"""
        dlg = QDialog(self)
        dlg.setWindowTitle(title or self.app._t("ar_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(760, 520)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(body or self.app._t("ar_help"))
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

    def showEvent(self, e):
        self._refresh_stats()          # 显示即刷一次，别等首个 tick
        self._stats_timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._stats_timer.stop()       # 关窗/隐藏即停，避免单例窗关掉后仍每 700ms 空跑
        super().hideEvent(e)

    def closeEvent(self, e):
        if self._save_timer.isActive():
            self._commit()
        super().closeEvent(e)
