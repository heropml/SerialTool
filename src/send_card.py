# -*- coding: utf-8 -*-
"""Send area card factory (Qt).

S-2 R40: CommTool.build_send_card thin wrapper.
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QPushButton, QScrollArea, QTextEdit, QVBoxLayout,
    QWidget,
)

from fonts import mono_font
from ui_tips import set_tooltip
from widgets import Card


def build(app):
    """Build the send-area Card and bind widgets onto `app`."""
    """右侧主区域：发送区"""
    card = Card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(10)
    layout.addWidget(app._tr_label("send_area", 13, bold=True))

    # ---- 多条发送快捷栏：选分组 + ▶/■ 循环 + 命令平铺直接发 ----
    app._ms_groups, _ms_ok = app._load_ms_groups()
    try:
        app._ms_group_idx = int(app.settings.value("multi_send_group_idx", 0))
    except (ValueError, TypeError):
        app._ms_group_idx = 0
    if not (0 <= app._ms_group_idx < len(app._ms_groups)):
        app._ms_group_idx = 0
    if not _ms_ok:    # 迁移/首次/损坏 → 落盘，避免每次启动重复迁移
        app._save_ms_groups()
    # 发送模板库：常用命令随手取用，数据存这里、SnippetsDialog 只是编辑器
    app._snippets, _snip_ok = app._load_snippets()
    if not _snip_ok:
        app._save_snippets()
    app._connection_presets, _cpreset_ok = app._load_connection_presets()
    if not _cpreset_ok:
        app._save_connection_presets()
    app._rebuild_connection_preset_combo()
    app._ms_cycle_seq = []
    app._ms_cycle_idx = 0
    app._ms_cycle_timer = QTimer(app)
    app._ms_cycle_timer.setSingleShot(True)
    app._ms_cycle_timer.timeout.connect(app._ms_cycle_step)

    ms_bar = QHBoxLayout()
    ms_bar.setSpacing(6)
    app.btn_multi = QPushButton(app._t("multi_send"))
    app.btn_multi.setObjectName("GhostBtn")
    app.btn_multi.setProperty("tr_text", "multi_send")
    app.btn_multi.clicked.connect(app.open_multi_send)
    ms_bar.addWidget(app.btn_multi)
    app.btn_ms_cycle = QPushButton(app._t("ms_cycle"))
    app.btn_ms_cycle.setObjectName("GhostBtn")
    app.btn_ms_cycle.clicked.connect(app._ms_toggle_cycle)
    ms_bar.addWidget(app.btn_ms_cycle)
    app.cb_ms_group = QComboBox()
    app.cb_ms_group.setMinimumWidth(110)
    # 高度跟左右 GhostBtn 等高：用 setFixedHeight 而非 setMinimumHeight——后者会被 QComboBox 在
    # styleSheet apply 期间的内部 sizePolicy 计算覆盖回默认 (~22px)
    app.cb_ms_group.setFixedHeight(28)
    app.cb_ms_group.currentIndexChanged.connect(app._on_ms_group_changed)
    ms_bar.addWidget(app.cb_ms_group)
    app._ms_quick_host = QWidget()
    app._ms_quick_host.setObjectName("MsQuickHost")
    app._ms_quick_h = QHBoxLayout(app._ms_quick_host)
    app._ms_quick_h.setContentsMargins(0, 0, 0, 0)
    app._ms_quick_h.setSpacing(6)
    app._ms_quick_host.setAutoFillBackground(False)
    ms_qscroll = QScrollArea()
    ms_qscroll.setObjectName("MsQuickScroll")
    ms_qscroll.setWidget(app._ms_quick_host)
    ms_qscroll.setWidgetResizable(True)
    ms_qscroll.setFrameShape(QFrame.NoFrame)
    ms_qscroll.setFixedHeight(38)
    ms_qscroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    ms_qscroll.viewport().setAutoFillBackground(False)
    ms_bar.addWidget(ms_qscroll, 1)
    layout.addLayout(ms_bar)
    app._rebuild_ms_group_combo()
    app._rebuild_ms_quick_bar()

    app.txt_send = QTextEdit()
    app.txt_send.setObjectName("SendBox")
    app.txt_send.setFont(mono_font(10))
    # 固定高度、不拉伸：否则与接收区(数据区)抢垂直空间，发送卡片被压缩导致按钮和发送框重叠
    app.txt_send.setFixedHeight(64)
    # 占位文案随终端模式而定（启动恢复 terminal_mode=True 时也用对的那句）；
    # tr_placeholder 属性供语言切换 _apply_language 刷新，终端模式时由 _set_terminal_enabled 改它。
    _ph = "term_send_ph" if app._terminal_on else "send_placeholder"
    app.txt_send.setProperty("tr_placeholder", _ph)
    app.txt_send.installEventFilter(app)   # ↑↓ 历史导航（在 eventFilter 里处理）
    app.txt_send.setPlaceholderText(app._t(_ph))
    # 悬浮提示：动态字段语法 + ↑↓ 历史；语言切换由 _apply_language 通过 tr_tooltip 刷新
    app.txt_send.setProperty("tr_tooltip", "send_box_tip")
    set_tooltip(app.txt_send, app._t("send_box_tip"))
    layout.addWidget(app.txt_send)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)        # 与上一行 ms_bar 同 spacing → 两行同列按钮右边缘对齐
    app.btn_load = QPushButton(app._t("read_file"))
    app.btn_load.setObjectName("GhostBtn")
    app.btn_load.setProperty("tr_text", "read_file")
    app.btn_load.clicked.connect(app.load_file_to_send)
    btn_row.addWidget(app.btn_load)

    app.btn_clear_tx = QPushButton(app._t("clear"))
    app.btn_clear_tx.setObjectName("GhostBtn")
    app.btn_clear_tx.setProperty("tr_text", "clear")
    app.btn_clear_tx.clicked.connect(lambda: app.txt_send.clear())
    btn_row.addWidget(app.btn_clear_tx)

    # 自动应答（紧挨清空；启用时按钮高亮：动态属性 arActive 配 QSS [arActive="true"]）
    # 单击 → _ar_btn_clicked 延时打开对话框；双击（eventFilter 捕获）→ 翻转总开关。
    app.btn_autoreply = QPushButton(app._t("ar_open"))
    app.btn_autoreply.setObjectName("GhostBtn")
    app.btn_autoreply.setProperty("tr_text", "ar_open")
    app.btn_autoreply.setProperty("arActive", "true" if app._ar_on else "false")
    set_tooltip(app.btn_autoreply, app._t("ar_btn_tip"))
    app.btn_autoreply.setProperty("tr_tooltip", "ar_btn_tip")   # 语言切换时由 _apply_language 刷新
    app.btn_autoreply.clicked.connect(app._ar_btn_clicked)
    app.btn_autoreply.installEventFilter(app)
    btn_row.addWidget(app.btn_autoreply)

    # 工作台页面化后，发送模板库也需要在终端保留直接可见入口。
    app.btn_snippets = QPushButton(app._t("snip_title"))
    app.btn_snippets.setObjectName("GhostBtn")
    app.btn_snippets.setProperty("tr_text", "snip_title")
    app.btn_snippets.clicked.connect(app.open_snippets)
    btn_row.addWidget(app.btn_snippets)

    app.btn_send_hist = QPushButton(app._t("send_hist_btn"))
    app.btn_send_hist.setObjectName("GhostBtn")
    app.btn_send_hist.setProperty("tr_text", "send_hist_btn")
    app.btn_send_hist.setProperty("tr_tooltip", "send_hist_tip")
    set_tooltip(app.btn_send_hist, app._t("send_hist_tip"))
    app.btn_send_hist.clicked.connect(app.open_send_history)
    btn_row.addWidget(app.btn_send_hist)

    # 工作台页面化后「终端」不再弹功能菜单，文件传输必须保留一个直接可见入口。
    app.btn_xfer = QPushButton(app._t("xfer_title"))
    app.btn_xfer.setObjectName("GhostBtn")
    app.btn_xfer.setProperty("tr_text", "xfer_title")
    app.btn_xfer.clicked.connect(app.open_xfer)
    btn_row.addWidget(app.btn_xfer)
    # 前三列仍与上一行多条发送控件对齐；模板库与文件传输作为快捷动作依次排在后面。

    btn_row.addStretch(1)

    app.btn_send = QPushButton(app._t("send_btn"))
    app.btn_send.setObjectName("PrimaryBtn")
    app.btn_send.setMinimumHeight(36)
    app.btn_send.setMinimumWidth(120)
    app.btn_send.setProperty("tr_text", "send_btn")
    app.btn_send.clicked.connect(app.do_send)
    btn_row.addWidget(app.btn_send)

    layout.addLayout(btn_row)
    return card

