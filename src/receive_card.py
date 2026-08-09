# -*- coding: utf-8 -*-
"""Receive (data) area card factory (Qt).

S-2 R39: CommTool.build_receive_card / _build_search_bar thin wrappers.
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
    QWidget, QStackedWidget,
)

from fonts import ui_font, mono_font
from theme import COLOR_TEXT_SECONDARY, COLOR_BLUE
from ui_tips import set_tooltip
from widgets import Card
from ui_options import SEARCH_MODE_ITEMS


def build_search_bar(app):
    """Floating Ctrl+F search bar over txt_recv (hidden by default)."""
    """创建悬浮在 txt_recv 右上角的查找栏（默认隐藏）。"""
    app._search_term = ""
    app._search_matches = []     # 存 QTextCursor
    app._search_idx = -1
    app._search_match_capped = False
    app._search_mode = "plain"   # plain / regex / hex
    app._search_case = False     # 大小写敏感
    app._search_bar = QWidget(app.txt_recv)
    row = QHBoxLayout(app._search_bar)
    row.setContentsMargins(8, 6, 8, 6)
    row.setSpacing(6)
    app.ed_search = QLineEdit()
    app.ed_search.setProperty("tr_placeholder", "search_ph")
    app.ed_search.setPlaceholderText(app._t("search_ph"))
    app.ed_search.setFixedWidth(180)
    app.ed_search.textChanged.connect(app._do_search)
    app.ed_search.returnPressed.connect(app._search_next)
    app.cb_search_mode = QComboBox()
    app.cb_search_mode.setProperty("tr_tooltip", "search_mode")
    set_tooltip(app.cb_search_mode, app._t("search_mode"))
    app.cb_search_mode.setFixedWidth(54)
    app.cb_search_mode.blockSignals(True)
    for data, key in SEARCH_MODE_ITEMS:
        app.cb_search_mode.addItem(app._t(key), data)
    app.cb_search_mode.blockSignals(False)
    app.cb_search_mode.currentIndexChanged.connect(lambda *_: app._on_search_mode_changed())
    app.btn_search_case = QPushButton("Aa")
    app.btn_search_case.setProperty("tr_tooltip", "search_case")
    set_tooltip(app.btn_search_case, app._t("search_case"))
    app.btn_search_case.setCheckable(True)
    app.btn_search_case.setFixedWidth(30)
    app.btn_search_case.toggled.connect(app._on_search_case_toggled)
    app.lbl_search_cnt = QLabel("")
    app.btn_search_prev = QPushButton("▲")
    app.btn_search_prev.setProperty("tr_tooltip", "search_prev")
    set_tooltip(app.btn_search_prev, app._t("search_prev"))
    app.btn_search_prev.setCursor(Qt.PointingHandCursor)
    app.btn_search_prev.setFixedSize(26, 26)
    app.btn_search_prev.clicked.connect(app._search_prev)
    app.btn_search_next = QPushButton("▼")
    app.btn_search_next.setProperty("tr_tooltip", "search_next")
    set_tooltip(app.btn_search_next, app._t("search_next"))
    app.btn_search_next.setCursor(Qt.PointingHandCursor)
    app.btn_search_next.setFixedSize(26, 26)
    app.btn_search_next.clicked.connect(app._search_next)
    app.btn_search_close = QPushButton("✕")
    app.btn_search_close.setCursor(Qt.PointingHandCursor)
    app.btn_search_close.setFixedSize(26, 26)
    app.btn_search_close.clicked.connect(app._close_search)
    row.addWidget(app.ed_search)
    row.addWidget(app.cb_search_mode)
    row.addWidget(app.btn_search_case)
    row.addWidget(app.lbl_search_cnt)
    row.addWidget(app.btn_search_prev)
    row.addWidget(app.btn_search_next)
    row.addWidget(app.btn_search_close)
    app._style_search_bar()
    app._search_bar.hide()



def build(app):
    """Build the receive-area Card and bind widgets/timers onto `app`."""
    """右侧主区域：数据区"""
    card = Card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(10)

    title_row = QHBoxLayout()
    title_row.addWidget(app._tr_label("data_area", 13, bold=True))
    title_row.addSpacing(10)
    app.legend_label = QLabel(
        f'<span style="color:{COLOR_TEXT_SECONDARY};">{app._t("legend_rx")}</span>'
        f'&nbsp;&nbsp;'
        f'<span style="color:{COLOR_BLUE};">{app._t("legend_tx")}</span>'
    )
    app.legend_label.setFont(ui_font(10))
    app.legend_label.setStyleSheet("background: transparent;")
    title_row.addWidget(app.legend_label)
    title_row.addStretch(1)

    # 生效分组下拉（顶部「（关闭）」+ 各分组）—— 选哪个分组就按哪个分组高亮
    app.cb_kw_group = QComboBox()
    app.cb_kw_group.setMinimumWidth(96)
    app.cb_kw_group.currentIndexChanged.connect(app._on_kw_group_changed)
    title_row.addWidget(app.cb_kw_group)
    title_row.addSpacing(6)

    app.btn_keyword = QPushButton(app._t("kw_highlight"))
    app.btn_keyword.setObjectName("GhostBtn")
    app.btn_keyword.setProperty("tr_text", "kw_highlight")
    app.btn_keyword.clicked.connect(app.open_keyword_highlight)
    title_row.addWidget(app.btn_keyword)
    title_row.addSpacing(6)

    # 只显高亮行：可切换按钮，开启后数据区只保留命中关键字的行（折叠其余）
    app.btn_filter_hl = QPushButton(app._t("filter_highlight"))
    app.btn_filter_hl.setObjectName("GhostBtn")
    app.btn_filter_hl.setCheckable(True)
    app.btn_filter_hl.setProperty("tr_text", "filter_highlight")
    app.btn_filter_hl.toggled.connect(app._on_filter_hl_toggled)
    title_row.addWidget(app.btn_filter_hl)
    title_row.addSpacing(6)

    # 波形图 / 帧解析 / Modbus 主机 已挪到标题栏「功能」菜单（见 _show_titlebar_func_menu），
    # 数据区工具栏只留数据显示相关（关键字高亮 / 只显高亮行 / 字号）。
    title_row.addSpacing(2)

    app.btn_font_dec = QPushButton("A−")
    app.btn_font_dec.setObjectName("IconBtn")
    app.btn_font_dec.setFixedSize(34, 30)
    app.btn_font_dec.setProperty("tr_tooltip", "font_dec")
    set_tooltip(app.btn_font_dec, app._t("font_dec"))
    app.btn_font_dec.clicked.connect(lambda: app.change_recv_font_size(-1))
    title_row.addWidget(app.btn_font_dec)

    app.btn_font_inc = QPushButton("A+")
    app.btn_font_inc.setObjectName("IconBtn")
    app.btn_font_inc.setFixedSize(34, 30)
    app.btn_font_inc.setProperty("tr_tooltip", "font_inc")
    set_tooltip(app.btn_font_inc, app._t("font_inc"))
    app.btn_font_inc.clicked.connect(lambda: app.change_recv_font_size(+1))
    title_row.addWidget(app.btn_font_inc)

    layout.addLayout(title_row)

    # Per-session receive views in a stack (multi-tab concurrent sessions).
    app.recv_stack = QStackedWidget()
    app.recv_stack.setObjectName("RecvStack")
    session = app.active_session() if hasattr(app, "active_session") else None
    if session is not None:
        app._ensure_session_recv_widget(session)
        te = session.txt_recv
    else:
        te = QTextEdit()
        te.setReadOnly(True)
        te.setObjectName("RecvBox")
        te.setFont(mono_font(app._recv_font_size))
        te.setLineWrapMode(QTextEdit.WidgetWidth)
        te.document().setMaximumBlockCount(10000)
        app.recv_stack.addWidget(te)
    app._txt_recv_fallback = te
    te.setProperty("tr_tooltip", "sel_chk_hint")
    set_tooltip(te, app._t("sel_chk_hint"))
    if app.recv_stack.indexOf(te) < 0:
        app.recv_stack.addWidget(te)
    app.recv_stack.setCurrentWidget(te)
    layout.addWidget(app.recv_stack, 1)
    build_search_bar(app)

    # ----- 单击行高亮 + 滚动锁定/回到底部（仿 SuperCom）-----
    app._recv_highlight_line = -1
    app._bookmarks = []  # QTextCursor list (session-scoped)
    app._bookmark_idx = -1          # bookmark nav index, -1 = none yet
    # 关键字高亮分组: [{name, rules:[{pattern,mode,scope,color,enabled}]}]，_keyword_active=生效分组(-1关闭)
    app._keyword_groups, app._keyword_active, _kw_ok = app._load_keyword_groups()
    if not _kw_ok:      # 迁移/首次/损坏 → 落盘，避免每次启动重复迁移
        app._save_keyword_groups()
    app._rebuild_kw_group_combo()      # 填充标题栏分组下拉
    # 节流定时器：收数据高频，关键字重扫合并到 ~150ms 一次，避免卡顿
    app._kw_timer = QTimer(app)
    app._kw_timer.setSingleShot(True)
    app._kw_timer.setInterval(150)
    app._kw_timer.timeout.connect(app._refresh_extra_selections)
    # 选中即算校验和：selectionChanged 在拖选过程中逐字符触发，节流到 ~120ms 一次，
    # 否则每动一格就跑 9 遍纯 Python 校验循环，长选区拖选会明显掉帧
    app._sel_chk_timer = QTimer(app)
    app._sel_chk_timer.setSingleShot(True)
    app._sel_chk_timer.setInterval(120)
    app._sel_chk_timer.timeout.connect(app._update_sel_checksum)
    app.txt_recv.selectionChanged.connect(app._sel_chk_timer.start)
    # 浮动「回到底部」按钮：做成 txt_recv 子控件，悬在右下角；翻到上面才显示
    app.btn_to_bottom = QPushButton(app._t("to_bottom"), app.txt_recv)
    app.btn_to_bottom.setObjectName("ToBottomBtn")
    app.btn_to_bottom.setProperty("tr_text", "to_bottom")
    app.btn_to_bottom.setCursor(Qt.PointingHandCursor)
    app.btn_to_bottom.clicked.connect(app._scroll_recv_to_bottom)
    app.btn_to_bottom.hide()
    # 滚动路由由 SessionHostMixin._ensure_session_recv_widget 统一绑定，
    # 首个标签也不在这里重复连接。
    # 监听 viewport 点击(行高亮) 和 txt_recv 尺寸变化(重定位按钮)
    app.txt_recv.viewport().installEventFilter(app)
    app.txt_recv.installEventFilter(app)
    # 自定义右键菜单（跟随程序语言）：在 eventFilter 拦截 ContextMenu 事件弹出
    # （QTextEdit 的右键事件发往 viewport，CustomContextMenu 信号路由不稳，故走 eventFilter）
    app.txt_recv.setContextMenuPolicy(Qt.PreventContextMenu)

    return card

