# -*- coding: utf-8 -*-
"""主窗口 CommTool（统一串口/网络调试工具）。"""
import codecs
import json
import os
import sys
import time
import serial
from datetime import datetime
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QSettings, QEvent
from PyQt5.QtGui import (QColor, QTextCursor, QTextCharFormat,
                         QFontMetrics, QTextFormat, QPalette)
from PyQt5.QtWidgets import (QWidget, QMainWindow, QLabel, QPushButton, QComboBox,
                             QTextEdit, QLineEdit, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QSplitter, QScrollArea, QFrame, QFileDialog, QStatusBar,
                             QSystemTrayIcon, QMenu, QApplication)
try:
    from version import __version__ as APP_VERSION
except Exception:
    APP_VERSION = "0.0.0"
from theme import (ROLE_PROP, ROLE_TS, ROLE_RX, ROLE_TX, THEMES, THEME_DEFAULT, _mix,
                   chrome_for, COLOR_TEXT, COLOR_TEXT_SECONDARY, COLOR_BLUE)
from i18n import TR, CHECKSUM_KEYS
from app_icon import get_app_icon
from fonts import ui_font, mono_font, localize_qss
from widgets import make_label, IOSSwitch, TitleBar, Card
from net_io import (TcpServerConn, TcpClientConn, UdpConn, UdpGroupConn,
                    PROTO_TCP_SERVER, PROTO_TCP_CLIENT, PROTO_UDP, PROTO_UDP_MULTICAST,
                    PROTOCOLS, SEND_NO_TARGET, ERR_CONN_TIMEOUT, local_ipv4_list, is_multicast_ipv4,
                    is_valid_ip)
from serial_io import SerialConn, PortScannerThread, OneShotPortScanner
from dialogs import CloseDialog, MultiSendDialog, KeywordHighlightDialog, AboutDialog

# 串口作为统一连接层的一种「类型」，排在网络协议之前一起进 cb_proto 下拉。
# 不放进 net_io.PROTOCOLS 是为保持 net_io 纯网络语义；这里组合成完整下拉列表。
PROTO_SERIAL = "Serial"
CONN_TYPES = [PROTO_SERIAL] + PROTOCOLS


class ThemedToolTip(QLabel):
    """不透明主题化 tooltip（仅 macOS 用）。

    macOS 上 Qt 给原生 QToolTip 套样式表后会把它设为半透明窗口，背景不绘制，
    文字直接叠在底层控件上看不清。这里自绘一个：用 autoFillBackground + palette
    上色（基于调色板的填充一定不透明，不走会触发半透明的 QSS 背景），边框用
    QFrame.Box（颜色取前景色）。Windows 仍用原生圆角 tooltip。"""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(True)
        self.setContentsMargins(9, 6, 9, 6)
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setLineWidth(1)
        self.setFont(ui_font(10))
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_text(self, gpos, text, bg, fg):
        if not text:
            self.hide()
            return
        self.setText(text)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(bg))
        pal.setColor(QPalette.WindowText, QColor(fg))
        self.setPalette(pal)
        self.adjustSize()
        self._place(gpos)
        self.show()
        self.raise_()
        self._hide_timer.start(15000)   # 兜底自动隐藏（鼠标点击/移动也会触发隐藏）

    def _place(self, gpos):
        screen = QApplication.screenAt(gpos) or QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QRect(0, 0, 99999, 99999)
        w, h = self.width(), self.height()
        x = gpos.x() + 14
        y = gpos.y() + 18
        if x + w > geo.right():
            x = max(geo.left(), gpos.x() - w - 6)
        if y + h > geo.bottom():
            y = max(geo.top(), gpos.y() - h - 6)
        self.move(x, y)


# ============== 主窗口 ==============
class CommTool(QMainWindow):
    RESIZE_MARGIN = 6

    def __init__(self):
        super().__init__()
        # macOS 用原生窗口边框（红黄绿交通灯 + 系统原生缩放）；Windows/Linux 仍是自定义无边框
        if sys.platform == "darwin":
            self.setWindowFlags(Qt.Window)
        else:
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        # 边缘缩放：Windows 走下面的 nativeEvent(WM_NCHITTEST)；macOS 由原生边框处理；
        # 其它（Linux）无边框又无原生缩放 → 应用级事件过滤器手动实现（悬停光标 + 拖拽改几何）。
        self._manual_resize = sys.platform not in ("win32", "darwin")
        self._resize_edges = Qt.Edges()
        self._resize_start_geo = None
        self._resize_start_mouse = None
        self._hover_cursor_shape = None
        # macOS：原生 QToolTip 加样式后背景透明，改用自绘不透明 tooltip，需 app 级
        # 事件过滤器拦截 ToolTip 事件（Windows/Linux 原生 tooltip 正常，不拦截）。
        self._mac_tooltip = sys.platform == "darwin"
        self._tooltip_popup = None
        if self._manual_resize or self._mac_tooltip:
            QApplication.instance().installEventFilter(self)

        self.conn = None          # 当前连接：SerialConn / TcpServerConn / TcpClientConn / UdpConn(...)
        self._conn_engaged = False   # 连接是否已成功建立 → 区分"打开失败"与"运行时断开"的错误文案
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.rx_packets = 0       # 收发包计数：RX=每次到达一块、TX=每次成功发送
        self.tx_packets = 0
        self.rx_errors = 0        # RX 错误：接收处理异常 + 连接/链路错误
        self.tx_errors = 0        # TX 错误：发送失败（无对端 / 写失败 / 异常）
        self._rx_rate = 0         # 当前速率 B/s（每秒采样一次的字节增量）
        self._tx_rate = 0
        self._rx_peak = 0         # 峰值速率 B/s
        self._tx_peak = 0
        self._rx_bytes_mark = 0   # 上次采样时的累计字节，用于算每秒增量
        self._tx_bytes_mark = 0

        # 串口端口扫描（仅串口模式用）：后台轮询线程避免 comports() 卡 GUI
        self._last_port_list = []
        self._oneshot_scan = None
        self.port_scanner = None
        self._pending_restore_port = None   # 启动时待恢复的上次串口设备名

        self.send_timer = QTimer(self)
        self.send_timer.timeout.connect(self.do_send)

        # 收发速率采样：1Hz 取字节增量近似 B/s + 记录峰值，并刷新状态栏统计
        # （start 推迟到 init_ui 之后，确保首个 tick 触发时 lbl_rx_stat 已创建）
        self._rate_timer = QTimer(self)
        self._rate_timer.timeout.connect(self._tick_rate)

        self._reset_recv_state()   # 接收解析状态（方向/缓冲/增量解码器/换行）统一初始化
        self._log_file = None
        self._log_file_path = ""
        self._log_limit = 0       # 分包字节上限，0=不分包
        self._log_base_path = ""  # 用户选的原始路径，分包时据此派生 _001/_002...
        self._log_seg = 0         # 当前分包序号
        self._recv_font_size = 10

        self.settings = QSettings(self._settings_file(), QSettings.IniFormat)
        saved_lang = self.settings.value("language", "zh")
        self._lang = saved_lang if saved_lang in TR else "zh"
        self._L = TR[self._lang]

        self._closing_real = False
        self._tray = None

        self.init_ui()
        self._rate_timer.start(1000)   # init_ui 后再启动统计采样，保证首 tick 时 lbl_rx_stat 已存在
        # 鼠标跟踪：仅手动缩放（Linux）需要——悬停时也产生 MouseMove 以实时切换缩放光标。
        if self._manual_resize:
            self.setMouseTracking(True)
            self.centralWidget().setMouseTracking(True)
            if hasattr(self, "title_bar"):
                self.title_bar.setMouseTracking(True)
        self.refresh_ports()       # 启动即扫一次串口，cb_port 立刻有内容供恢复上次选择
        self.apply_style()
        self._load_settings()
        self._setup_tray()

        self.port_scanner = PortScannerThread(interval_ms=1500)
        self.port_scanner.scan_complete.connect(self._on_port_scan_complete)
        self.port_scanner.start()

    def _t(self, key, **kwargs) -> str:
        s = self._L.get(key, key)
        return s.format(**kwargs) if kwargs else s

    def _theme_label(self, theme_id: str) -> str:
        """主题显示名 — 优先用翻译 key (theme_<id>)，缺失就回退到 THEMES['label'] 英文名"""
        key = f"theme_{theme_id}"
        s = self._L.get(key)
        if s:
            return s
        return THEMES.get(theme_id, {}).get("label", theme_id)

    def _theme_id(self) -> str:
        if not hasattr(self, "cb_theme"):
            return THEME_DEFAULT
        return self.cb_theme.currentData() or THEME_DEFAULT

    def _set_state_color(self, opened: bool):
        """状态点色：打开 = 通用绿（任何主题都看得清）；关闭 = 主题 danger 红"""
        color = "#34C759" if opened else chrome_for(self._theme_id())["danger"]
        self.lbl_state.setStyleSheet(f"color: {color};")

    def _is_open(self) -> bool:
        """是否已建立连接并可发送（统一状态判断，替代原 self.ser and self.ser.is_open）。"""
        return bool(self.conn and self.conn.is_open)

    def _label_col_width(self) -> int:
        """网络设置左侧标签列宽：按当前语言下各标签的最大实测文本宽度自适应，
        避免英文单词(如 Remote Port)被输入框遮挡。"""
        keys = ("protocol_type", "local_ip", "local_port", "group_addr",
                "remote_ip", "remote_port", "target_client", "use_remote",
                "port", "baud_rate", "data_bits", "parity", "stop_bits")
        fm = QFontMetrics(ui_font(11))
        w = max(fm.horizontalAdvance(self._t(k)) for k in keys)
        return max(44, w + 9)  # +9 右边距；中文下至少 44 保持原观感

    def _tr_label(self, key, size=11, bold=False, color=COLOR_TEXT):
        lbl = make_label(self._t(key), size, bold, color)
        lbl.setProperty("tr_text", key)
        # 自动挂 tooltip：若同名 _tip 键存在则用它，语言切换时由 _apply_language 同步
        tip_key = key + "_tip"
        if tip_key in self._L:
            lbl.setToolTip(self._L[tip_key])
            lbl.setProperty("tr_tooltip", tip_key)
        return lbl

    # ----- UI 构建 -----
    def init_ui(self):
        self.setWindowTitle(self._t("app_title"))
        self.resize(1140, 740)
        self.setMinimumSize(960, 600)

        central = QWidget()
        central.setObjectName("Central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏
        self.title_bar = TitleBar(self)
        self.title_bar.set_title(self._t("app_title"))
        self.title_bar.set_app_icon(get_app_icon())

        self.cb_language = self.title_bar.cb_language
        self.cb_language.addItem(TR["zh"]["lang_zh"], "zh")
        self.cb_language.addItem(TR["en"]["lang_en"], "en")
        self.cb_language.addItem(TR["zh_tw"]["lang_tw"], "zh_tw")
        lang_idx = {"zh": 0, "en": 1, "zh_tw": 2}.get(self._lang, 0)
        self.cb_language.setCurrentIndex(lang_idx)
        self.cb_language.currentIndexChanged.connect(
            lambda i: self._set_language(self.cb_language.itemData(i)))

        # 主题下拉 — 也在标题栏左侧
        self.cb_theme = self.title_bar.cb_theme
        for theme_id in THEMES.keys():
            self.cb_theme.addItem(self._theme_label(theme_id), theme_id)
        self.cb_theme.setProperty("tr_tooltip", "theme_tip")
        self.cb_theme.setToolTip(self._t("theme_tip"))
        self.cb_theme.currentIndexChanged.connect(lambda _: self._on_theme_changed())

        root.addWidget(self.title_bar)

        # 内容
        content = QWidget()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 12, 20, 12)
        content_layout.setSpacing(10)
        root.addWidget(content, 1)

        # 右侧改用 QVBoxLayout（去掉 v_splitter）：数据区拉伸，发送区自然高度贴底
        # 这样和左侧 sidebar 的结构一致（左侧 3 张卡也是数据区拉伸 + 发送区贴底）
        right_container = QWidget()
        right_v = QVBoxLayout(right_container)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(10)
        right_v.addWidget(self.build_receive_card(), 1)   # 数据区：拉伸吃多余空间
        self._right_send_card = self.build_send_card()
        right_v.addWidget(self._right_send_card)           # 发送区：自然高度，贴底

        # 主水平分隔条：左侧 sidebar | 右侧 container
        self.h_splitter = QSplitter(Qt.Horizontal)
        self.h_splitter.setChildrenCollapsible(False)
        self.h_splitter.setHandleWidth(8)
        self.h_splitter.addWidget(self.build_sidebar())
        self.h_splitter.addWidget(right_container)
        self.h_splitter.setStretchFactor(0, 0)
        self.h_splitter.setStretchFactor(1, 1)
        self.h_splitter.setSizes([280, 860])

        content_layout.addWidget(self.h_splitter, 1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(f"background: transparent; color: {COLOR_TEXT_SECONDARY};")
        # 左右边距和上面的 content_layout (20px) 对齐
        self.status_bar.setContentsMargins(20, 0, 20, 0)
        self.status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self.status_bar)
        self.lbl_rx_stat = QLabel("RX 0 B")
        self.lbl_tx_stat = QLabel("TX 0 B")
        self.lbl_state = QLabel(self._t("state_closed"))
        self._set_state_color(opened=False)
        for lbl in (self.lbl_state, self.lbl_rx_stat, self.lbl_tx_stat):
            lbl.setFont(ui_font(10))

        def _sep():
            """竖线分隔符（无自带色 → 跟随状态栏 text_sec，主题自适应）"""
            s = QLabel("│")
            s.setFont(ui_font(10))
            s.setObjectName("StatusSep")
            return s

        # 三个状态项放左下角 — 用 addWidget 而非 addPermanentWidget
        # (addPermanentWidget 会贴右边；addWidget 走左边，缺点是 toast 出现时会被临时遮盖)
        self.status_bar.addWidget(self.lbl_state)
        self.status_bar.addWidget(_sep())
        self.status_bar.addWidget(self.lbl_rx_stat)
        self.status_bar.addWidget(_sep())
        self.status_bar.addWidget(self.lbl_tx_stat)

        # 状态栏右键 → 重置统计
        self.status_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.status_bar.customContextMenuRequested.connect(self._stat_context_menu)

        # 实时记录文件路径 — 右下角(版本号左侧)，仅记录时显示，太长中间省略+悬停看全路径
        self.lbl_log_path = QLabel("")
        self.lbl_log_path.setFont(ui_font(9))
        self.lbl_log_path.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self._log_path_elide_w = 560
        self.status_bar.addPermanentWidget(self.lbl_log_path)
        self._log_path_sep = _sep()
        self._log_path_sep.hide()    # 未记录时隐藏这条分隔，避免悬空
        self.status_bar.addPermanentWidget(self._log_path_sep)

        # 版本号 — 右下角 (addPermanentWidget 走右边)
        self.lbl_version = QLabel(f"v{APP_VERSION}")
        self.lbl_version.setFont(ui_font(10))
        self.lbl_version.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self.status_bar.addPermanentWidget(self.lbl_version)

        # 同步最大行数
        self._on_max_lines_changed()
        self._refresh_stat_labels()   # 状态栏 RX/TX 统计初始文案 + tooltip

    def build_sidebar(self):
        host = QWidget()
        host.setObjectName("SidebarHost")
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(self.build_settings_card())
        # 数据区 options 卡片 stretch=1，吃多余高度（保存/清空按钮始终贴卡片底部）
        v.addWidget(self.build_data_options_card(), 1)
        # 发送区卡片：自然高度，贴侧边栏底部
        self._left_send_card = self.build_send_options_card()
        v.addWidget(self._left_send_card)
        # 不加底部 stretch — 让发送区和右侧 send_card 同样贴底

        scroll = QScrollArea()
        scroll.setWidget(host)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("Sidebar")
        scroll.setMinimumWidth(260)
        scroll.setMaximumWidth(380)
        return scroll

    def build_settings_card(self):
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(self._tr_label("conn_settings", 12, bold=True))

        def make_row(label_key, field):
            """一行：固定宽标签 + 字段，整行包成 QWidget 便于按协议显隐。"""
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            lbl = self._tr_label(label_key, color=COLOR_TEXT_SECONDARY)
            lbl.setFixedWidth(self._label_col_width())
            lbl.setProperty("tr_fixedw", True)
            rl.addWidget(lbl)
            rl.addWidget(field, 1)
            layout.addWidget(row)
            return row

        # 连接类型：串口 + 网络协议，统一进一个下拉
        self.cb_proto = QComboBox()
        self.cb_proto.addItems(CONN_TYPES)
        self.cb_proto.currentIndexChanged.connect(lambda _: self._update_net_fields())
        make_row("protocol_type", self.cb_proto)

        # ===== 串口字段（仅 Serial 类型显示）=====
        # 端口：下拉 + ⟳ 刷新按钮，包成一个容器塞进 make_row 的字段位
        port_box = QWidget()
        pbl = QHBoxLayout(port_box)
        pbl.setContentsMargins(0, 0, 0, 0)
        pbl.setSpacing(6)
        self.cb_port = QComboBox()
        self.cb_port.setMinimumWidth(100)
        pbl.addWidget(self.cb_port, 1)
        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setObjectName("IconBtn")
        self.btn_refresh.setFixedSize(30, 26)
        self.btn_refresh.clicked.connect(self.refresh_ports)
        pbl.addWidget(self.btn_refresh)
        self.row_port = make_row("port", port_box)

        self.cb_baud = QComboBox()
        self.cb_baud.setEditable(True)
        for b in ["1200", "2400", "4800", "9600", "19200", "38400", "57600",
                  "115200", "230400", "256000", "460800", "500000", "512000",
                  "600000", "750000", "921600", "1000000", "1500000", "2000000"]:
            self.cb_baud.addItem(b)
        self.cb_baud.setCurrentText("115200")
        self.row_baud = make_row("baud_rate", self.cb_baud)

        self.cb_databits = QComboBox()
        self.cb_databits.addItems(["5", "6", "7", "8"])
        self.cb_databits.setCurrentText("8")
        self.row_databits = make_row("data_bits", self.cb_databits)

        self.cb_parity = QComboBox()
        self.cb_parity.addItems(["None", "Even", "Odd", "Mark", "Space"])
        self.row_parity = make_row("parity", self.cb_parity)

        self.cb_stopbits = QComboBox()
        self.cb_stopbits.addItems(["1", "1.5", "2"])
        self.cb_stopbits.setCurrentText("1")
        self.row_stopbits = make_row("stop_bits", self.cb_stopbits)

        # 本地 IP（TCP Server / UDP）— 下拉本机网卡 IP，可编辑
        self.cb_local_ip = QComboBox()
        self.cb_local_ip.setEditable(True)
        self.cb_local_ip.setMinimumWidth(100)
        self.cb_local_ip.addItems(local_ipv4_list())
        self.row_local_ip = make_row("local_ip", self.cb_local_ip)

        # 组播地址（仅 UDP Multicast）
        self.ed_group = QLineEdit("239.0.0.1")
        self.row_group = make_row("group_addr", self.ed_group)

        # 本地端口
        self.ed_local_port = QLineEdit("8080")
        self.row_local_port = make_row("local_port", self.ed_local_port)

        # 指定远程 开关（仅 UDP）：关=回复最近对端；开=固定发往下面的远程地址
        self.sw_udp_remote = IOSSwitch(False)
        self.sw_udp_remote.toggled.connect(lambda _=False: self._update_net_fields())
        sw_row = QWidget()
        swl = QHBoxLayout(sw_row)
        swl.setContentsMargins(0, 0, 0, 0)
        swl.setSpacing(6)
        sw_lbl = self._tr_label("use_remote", color=COLOR_TEXT_SECONDARY)
        sw_lbl.setFixedWidth(self._label_col_width())
        sw_lbl.setProperty("tr_fixedw", True)
        swl.addWidget(sw_lbl)
        swl.addWidget(self.sw_udp_remote)
        swl.addStretch(1)
        layout.addWidget(sw_row)
        self.row_udp_remote = sw_row

        # 远程 IP（TCP Client 必填 / UDP 由「指定远程」开关启用）
        self.ed_remote_ip = QLineEdit()
        self.row_remote_ip = make_row("remote_ip", self.ed_remote_ip)

        # 远程端口
        self.ed_remote_port = QLineEdit()
        self.row_remote_port = make_row("remote_port", self.ed_remote_port)

        # 目标客户端（仅 TCP Server 监听后显示）
        self.cb_target = QComboBox()
        self.row_target = make_row("target_client", self.cb_target)

        # 动作按钮（文案随协议/状态变化）
        self.btn_open = QPushButton(self._t("btn_listen"))
        self.btn_open.setObjectName("PrimaryBtn")
        self.btn_open.setMinimumHeight(34)
        self.btn_open.clicked.connect(self.toggle_conn)
        layout.addWidget(self.btn_open)

        self._update_net_fields()
        return card

    def _update_net_fields(self):
        """按当前连接类型 + 连接状态，显隐字段行并刷新动作按钮文案。"""
        proto = self.cb_proto.currentText()
        engaged = self.conn is not None
        is_serial = proto == PROTO_SERIAL
        is_srv = proto == PROTO_TCP_SERVER
        is_cli = proto == PROTO_TCP_CLIENT
        is_udp = proto == PROTO_UDP
        is_grp = proto == PROTO_UDP_MULTICAST
        # 串口字段：仅串口类型显示
        for row in (self.row_port, self.row_baud, self.row_databits,
                    self.row_parity, self.row_stopbits):
            row.setVisible(is_serial)
        if is_serial:
            # 串口类型下网络行全部隐藏，按钮文案走串口键，提前返回
            for row in (self.row_local_ip, self.row_group, self.row_local_port,
                        self.row_udp_remote, self.row_remote_ip, self.row_remote_port,
                        self.row_target):
                row.setVisible(False)
            self.btn_open.setText(self._t("btn_serial_close" if engaged else "btn_serial_open"))
            return
        self.row_local_ip.setVisible(is_srv or is_udp or is_grp)   # 组播时=出网卡
        self.row_group.setVisible(is_grp)
        self.row_local_port.setVisible(is_srv or is_udp or is_grp)
        self.row_udp_remote.setVisible(is_udp)        # 「指定远程」开关仅普通 UDP
        self.row_remote_ip.setVisible(is_cli or is_udp)
        self.row_remote_port.setVisible(is_cli or is_udp)
        # 「目标」行仅在 TCP Server 已监听**且**有客户端连入(cb_target 已填充)时显示，
        # 避免刚监听、还没客户端时露出一个空下拉
        self.row_target.setVisible(is_srv and engaged and self.cb_target.count() > 0)
        # 远程框启用：TCP Client 恒启用；UDP 看「指定远程」开关；连接期间整体锁定(灰)
        remote_en = (not engaged) and (is_cli or (is_udp and self.sw_udp_remote.isChecked()))
        self.ed_remote_ip.setEnabled(remote_en)
        self.ed_remote_port.setEnabled(remote_en)
        if engaged:
            key = {PROTO_TCP_SERVER: "btn_listen_stop",
                   PROTO_TCP_CLIENT: "btn_disconnect",
                   PROTO_UDP: "btn_udp_close",
                   PROTO_UDP_MULTICAST: "btn_udp_close"}[proto]
        else:
            key = {PROTO_TCP_SERVER: "btn_listen",
                   PROTO_TCP_CLIENT: "btn_connect",
                   PROTO_UDP: "btn_udp_open",
                   PROTO_UDP_MULTICAST: "btn_udp_open"}[proto]
        self.btn_open.setText(self._t(key))

    def build_data_options_card(self):
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(self._tr_label("data_area", 12, bold=True))

        MAIN_W = 90
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        def lbl(key):
            return self._tr_label(key, color=COLOR_TEXT_SECONDARY)

        def sw_row(row, key, sw):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(sw, row, 2, alignment=Qt.AlignRight)

        def sw_extra_row(row, key, sw, extra):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(sw, row, 1, alignment=Qt.AlignRight)
            grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

        def extra_row(row, key, extra):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

        def input_with_ms(input_widget):
            input_widget.setAlignment(Qt.AlignRight)
            box = QWidget()
            box.setFixedWidth(MAIN_W)
            h = QHBoxLayout(box); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
            h.addWidget(input_widget, 1)
            h.addWidget(make_label("ms", color=COLOR_TEXT_SECONDARY))
            return box

        row = 0
        self.sw_rx_hex = IOSSwitch(False)
        # 切 HEX/文本 显示时复位增量解码状态。HEX 分支的字节不进文本解码流(见
        # _on_data_received_impl)，若不复位，文本模式残留的半个多字节会和切回文本后的
        # 新数据错位拼接 → 整段乱码。代价仅是丢掉那个正好跨切换点、注定要被劈开的字符
        # ——两害取其轻，是有意行为，勿当 bug 移除（移除会把"丢一字符"换成"乱码一片"）。
        self.sw_rx_hex.toggled.connect(lambda _=False: self._on_encoding_changed())
        sw_row(row, "hex_display", self.sw_rx_hex); row += 1

        # 字符编码 — 影响 RX 解码、TX 编码、文件加载
        self.cb_encoding = QComboBox()
        self.cb_encoding.addItem(self._t("encoding_auto"), "auto")
        for codec_name in ("UTF-8", "GBK", "GB2312", "GB18030", "Big5", "ASCII", "Latin-1"):
            self.cb_encoding.addItem(codec_name, codec_name.lower())
        self.cb_encoding.setFixedWidth(MAIN_W)
        self.cb_encoding.currentIndexChanged.connect(lambda _: self._on_encoding_changed())
        extra_row(row, "encoding", self.cb_encoding); row += 1

        self.sw_wrap = IOSSwitch(True)
        self.sw_wrap.toggled.connect(self.on_wrap_toggled)
        sw_row(row, "auto_wrap", self.sw_wrap); row += 1

        self.sw_show_timestamp = IOSSwitch(False)
        sw_row(row, "show_timestamp", self.sw_show_timestamp); row += 1

        self.sw_packet_split = IOSSwitch(False)
        sw_row(row, "packet_split", self.sw_packet_split); row += 1

        self.ed_packet_timeout = QLineEdit("20")
        extra_row(row, "timeout", input_with_ms(self.ed_packet_timeout)); row += 1

        self.sw_line_split = IOSSwitch(False)
        self.cb_line_nl = QComboBox()
        self.cb_line_nl.addItem(self._t("nl_auto"))
        self.cb_line_nl.addItem("CRLF")
        self.cb_line_nl.addItem("LF")
        self.cb_line_nl.addItem("CR")
        self.cb_line_nl.setFixedWidth(MAIN_W)
        # 切换换行模式时把待定 \r 冲出来（防止从 CRLF 切到 LF/CR 后旧 \r 永远见不到）
        self.cb_line_nl.currentIndexChanged.connect(lambda _: self._flush_pending_cr())
        sw_extra_row(row, "line_split", self.sw_line_split, self.cb_line_nl); row += 1

        self.sw_log_file = IOSSwitch(False)
        self.sw_log_file.toggled.connect(self.on_log_file_toggled)
        # 实时记录按文件大小分包：到设定大小切到新文件（可编辑自定义，如 3M）
        self.cb_log_split = QComboBox()
        self.cb_log_split.setEditable(True)
        self.cb_log_split.addItem(self._t("log_split_none"))   # 不分包
        for s in ("1M", "2M", "5M", "10M", "20M", "50M", "100M"):
            self.cb_log_split.addItem(s)
        self.cb_log_split.setCurrentIndex(0)
        self.cb_log_split.setFixedWidth(MAIN_W)
        self.cb_log_split.setToolTip(self._t("log_split_tip"))
        self.cb_log_split.setProperty("tr_tooltip", "log_split_tip")
        self.cb_log_split.currentTextChanged.connect(self._on_log_split_changed)
        sw_extra_row(row, "real_time_log", self.sw_log_file, self.cb_log_split); row += 1


        self.ed_max_lines = QLineEdit("10000")
        self.ed_max_lines.setAlignment(Qt.AlignRight)
        self.ed_max_lines.setFixedWidth(MAIN_W)
        self.ed_max_lines.editingFinished.connect(self._on_max_lines_changed)
        extra_row(row, "max_lines", self.ed_max_lines); row += 1

        layout.addLayout(grid)
        layout.addStretch(1)  # 卡片被拉伸时吃掉多余空间，让按钮始终贴卡片底部

        # 保存 / 清空：保存贴左，清空贴右
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(6)

        self.btn_save = QPushButton(self._t("save"))
        self.btn_save.setObjectName("GhostBtn")
        self.btn_save.setFixedWidth(MAIN_W)
        self.btn_save.setProperty("tr_text", "save")
        self.btn_save.clicked.connect(self.save_recv)
        btns.addWidget(self.btn_save)

        btns.addStretch(1)

        self.btn_clear_rx = QPushButton(self._t("clear"))
        self.btn_clear_rx.setObjectName("GhostBtn")
        self.btn_clear_rx.setFixedWidth(MAIN_W)
        self.btn_clear_rx.setProperty("tr_text", "clear")
        self.btn_clear_rx.clicked.connect(self.clear_recv)
        btns.addWidget(self.btn_clear_rx)

        layout.addLayout(btns)
        return card

    def build_send_options_card(self):
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(self._tr_label("send_area", 12, bold=True))

        MAIN_W = 90
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        def lbl(key):
            return self._tr_label(key, color=COLOR_TEXT_SECONDARY)

        def sw_row(row, key, sw):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(sw, row, 2, alignment=Qt.AlignRight)

        def sw_extra_row(row, key, sw, extra):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(sw, row, 1, alignment=Qt.AlignRight)
            grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

        def extra_row(row, key, extra):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

        def input_with_ms(input_widget):
            input_widget.setAlignment(Qt.AlignRight)
            box = QWidget()
            box.setFixedWidth(MAIN_W)
            h = QHBoxLayout(box); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
            h.addWidget(input_widget, 1)
            h.addWidget(make_label("ms", color=COLOR_TEXT_SECONDARY))
            return box

        row = 0
        self.sw_tx_hex = IOSSwitch(False)
        sw_row(row, "hex_send", self.sw_tx_hex); row += 1

        self.sw_append_newline = IOSSwitch(False)
        self.cb_append_nl = QComboBox()
        self.cb_append_nl.addItem("CRLF")
        self.cb_append_nl.addItem("LF")
        self.cb_append_nl.addItem("CR")
        self.cb_append_nl.setFixedWidth(MAIN_W)
        sw_extra_row(row, "append_newline", self.sw_append_newline, self.cb_append_nl); row += 1

        self.sw_period = IOSSwitch(False)
        self.sw_period.toggled.connect(self.on_period_toggled)
        self.ed_period_ms = QLineEdit("1000")
        sw_extra_row(row, "period", self.sw_period,
                     input_with_ms(self.ed_period_ms)); row += 1

        self.cb_checksum = QComboBox()
        for ck_key in CHECKSUM_KEYS:
            self.cb_checksum.addItem(self._t(ck_key))
        self.cb_checksum.setFixedWidth(MAIN_W)
        extra_row(row, "checksum", self.cb_checksum); row += 1

        layout.addLayout(grid)
        return card

    def build_receive_card(self):
        """右侧主区域：数据区"""
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.addWidget(self._tr_label("data_area", 13, bold=True))
        title_row.addSpacing(10)
        self.legend_label = QLabel(
            f'<span style="color:{COLOR_TEXT_SECONDARY};">{self._t("legend_rx")}</span>'
            f'&nbsp;&nbsp;'
            f'<span style="color:{COLOR_BLUE};">{self._t("legend_tx")}</span>'
        )
        self.legend_label.setFont(ui_font(10))
        self.legend_label.setStyleSheet("background: transparent;")
        title_row.addWidget(self.legend_label)
        title_row.addStretch(1)

        # 生效分组下拉（顶部「（关闭）」+ 各分组）—— 选哪个分组就按哪个分组高亮
        self.cb_kw_group = QComboBox()
        self.cb_kw_group.setMinimumWidth(96)
        self.cb_kw_group.currentIndexChanged.connect(self._on_kw_group_changed)
        title_row.addWidget(self.cb_kw_group)
        title_row.addSpacing(6)

        self.btn_keyword = QPushButton(self._t("kw_highlight"))
        self.btn_keyword.setObjectName("GhostBtn")
        self.btn_keyword.setProperty("tr_text", "kw_highlight")
        self.btn_keyword.clicked.connect(self.open_keyword_highlight)
        title_row.addWidget(self.btn_keyword)
        title_row.addSpacing(6)

        # 只显高亮行：可切换按钮，开启后数据区只保留命中关键字的行（折叠其余）
        self.btn_filter_hl = QPushButton(self._t("filter_highlight"))
        self.btn_filter_hl.setObjectName("GhostBtn")
        self.btn_filter_hl.setCheckable(True)
        self.btn_filter_hl.setProperty("tr_text", "filter_highlight")
        self.btn_filter_hl.toggled.connect(self._on_filter_hl_toggled)
        title_row.addWidget(self.btn_filter_hl)
        title_row.addSpacing(8)

        self.btn_font_dec = QPushButton("A−")
        self.btn_font_dec.setObjectName("IconBtn")
        self.btn_font_dec.setFixedSize(34, 30)
        self.btn_font_dec.setProperty("tr_tooltip", "font_dec")
        self.btn_font_dec.setToolTip(self._t("font_dec"))
        self.btn_font_dec.clicked.connect(lambda: self.change_recv_font_size(-1))
        title_row.addWidget(self.btn_font_dec)

        self.btn_font_inc = QPushButton("A+")
        self.btn_font_inc.setObjectName("IconBtn")
        self.btn_font_inc.setFixedSize(34, 30)
        self.btn_font_inc.setProperty("tr_tooltip", "font_inc")
        self.btn_font_inc.setToolTip(self._t("font_inc"))
        self.btn_font_inc.clicked.connect(lambda: self.change_recv_font_size(+1))
        title_row.addWidget(self.btn_font_inc)

        layout.addLayout(title_row)

        self.txt_recv = QTextEdit()
        self.txt_recv.setReadOnly(True)
        self.txt_recv.setObjectName("RecvBox")
        self.txt_recv.setFont(mono_font(self._recv_font_size))
        self.txt_recv.setLineWrapMode(QTextEdit.WidgetWidth)
        self.txt_recv.document().setMaximumBlockCount(10000)
        layout.addWidget(self.txt_recv, 1)
        self._build_search_bar()

        # ----- 单击行高亮 + 滚动锁定/回到底部（仿 SuperCom）-----
        self._recv_highlight_line = -1          # 当前高亮的块号，-1 表示无
        # 关键字高亮分组: [{name, rules:[{pattern,mode,scope,color,enabled}]}]，_keyword_active=生效分组(-1关闭)
        self._keyword_groups, self._keyword_active, _kw_ok = self._load_keyword_groups()
        if not _kw_ok:      # 迁移/首次/损坏 → 落盘，避免每次启动重复迁移
            self._save_keyword_groups()
        self._rebuild_kw_group_combo()      # 填充标题栏分组下拉
        # 节流定时器：收数据高频，关键字重扫合并到 ~150ms 一次，避免卡顿
        self._kw_timer = QTimer(self)
        self._kw_timer.setSingleShot(True)
        self._kw_timer.setInterval(150)
        self._kw_timer.timeout.connect(self._refresh_extra_selections)
        # 浮动「回到底部」按钮：做成 txt_recv 子控件，悬在右下角；翻到上面才显示
        self.btn_to_bottom = QPushButton(self._t("to_bottom"), self.txt_recv)
        self.btn_to_bottom.setObjectName("ToBottomBtn")
        self.btn_to_bottom.setProperty("tr_text", "to_bottom")
        self.btn_to_bottom.setCursor(Qt.PointingHandCursor)
        self.btn_to_bottom.clicked.connect(self._scroll_recv_to_bottom)
        self.btn_to_bottom.hide()
        # 滚动条变化时判断是否在底部，决定按钮显隐
        self.txt_recv.verticalScrollBar().valueChanged.connect(self._on_recv_scroll)
        # 监听 viewport 点击(行高亮) 和 txt_recv 尺寸变化(重定位按钮)
        self.txt_recv.viewport().installEventFilter(self)
        self.txt_recv.installEventFilter(self)
        # 自定义右键菜单（跟随程序语言）：在 eventFilter 拦截 ContextMenu 事件弹出
        # （QTextEdit 的右键事件发往 viewport，CustomContextMenu 信号路由不稳，故走 eventFilter）
        self.txt_recv.setContextMenuPolicy(Qt.PreventContextMenu)

        return card

    def _recv_context_menu(self, global_pos):
        """数据区右键菜单：复制 / 全选 / 清空 / 保存，文字跟随程序语言。"""
        menu = QMenu(self.txt_recv)
        c = chrome_for(self._theme_id())
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['card_bg']}; color: {c['text']};
                     border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
            QMenu::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
            QMenu::item:disabled {{ color: {c['text_sec']}; }}
            QMenu::separator {{ height: 1px; background: {c['separator']}; margin: 4px 8px; }}
        """)
        has_sel = self.txt_recv.textCursor().hasSelection()
        has_text = bool(self.txt_recv.document().characterCount() > 1)
        act_search = menu.addAction(self._t("search"))
        menu.addSeparator()
        act_copy = menu.addAction(self._t("ctx_copy"))
        act_copy.setEnabled(has_sel)
        act_all = menu.addAction(self._t("ctx_select_all"))
        act_all.setEnabled(has_text)
        menu.addSeparator()
        act_clear = menu.addAction(self._t("clear"))
        act_clear.setEnabled(has_text)
        act_save = menu.addAction(self._t("save"))
        act_save.setEnabled(has_text)
        chosen = menu.exec_(global_pos)
        if chosen is act_search:
            self._open_search()
        elif chosen is act_copy:
            self.txt_recv.copy()
        elif chosen is act_all:
            self.txt_recv.selectAll()
        elif chosen is act_clear:
            self.clear_recv()
        elif chosen is act_save:
            self.save_recv()

    # ----- 数据区：滚动锁定 + 单击行高亮 -----
    def eventFilter(self, obj, event):
        # macOS：拦截 ToolTip → 自绘不透明 tooltip（原生加样式后背景透明看不清）
        if self._mac_tooltip:
            et0 = event.type()
            if et0 == QEvent.ToolTip:
                return self._show_mac_tooltip(obj, event)
            # 鼠标点击 / 滚轮 → 收起已显示的自绘 tooltip（贴近原生行为）
            elif (self._tooltip_popup is not None and self._tooltip_popup.isVisible()
                  and et0 in (QEvent.MouseButtonPress, QEvent.Wheel)):
                self._tooltip_popup.hide()

        # 无边框窗口的手动缩放（仅 Linux：Windows 用 nativeEvent、macOS 用原生边框）：
        # 边缘左键按下→抓鼠标记起点，拖动→改几何，松开→释放；悬停→切换缩放光标。
        if self._manual_resize:
            et = event.type()
            if (et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton
                    and not self._resize_edges
                    and (obj is self or (isinstance(obj, QWidget) and self.isAncestorOf(obj)))
                    and self.isActiveWindow() and not self.isMaximized() and self.isVisible()):
                pos = self.mapFromGlobal(event.globalPos())
                if self.rect().contains(pos):
                    edges = self._edges_at(pos)
                    if edges:
                        self._resize_edges = edges
                        self._resize_start_geo = self.geometry()
                        self._resize_start_mouse = event.globalPos()
                        # 应用级覆盖光标：整个拖动期间稳定显示缩放光标，不受 setGeometry 影响
                        QApplication.setOverrideCursor(self._resize_cursor(edges))
                        self.grabMouse()
                        return True
            elif et == QEvent.MouseMove and self._resize_edges:
                if QApplication.mouseButtons() & Qt.LeftButton:
                    self._perform_resize(event.globalPos())
                else:
                    # 没收到释放事件（grab 丢失等）→ 主动收尾，避免覆盖光标卡死
                    self._end_resize()
                return True
            elif et == QEvent.MouseButtonRelease and self._resize_edges:
                self._end_resize()
                return True
            elif (et == QEvent.MouseMove and not self._resize_edges
                    and not (event.buttons() & Qt.LeftButton)
                    and (obj is self or (isinstance(obj, QWidget) and self.isAncestorOf(obj)))):
                # 悬停（未按键）在边缘 → 切换缩放光标，让用户一眼看出可拖拽缩放
                if self.isActiveWindow() and not self.isMaximized():
                    pos = self.mapFromGlobal(event.globalPos())
                    self._update_hover_cursor(
                        self._edges_at(pos) if self.rect().contains(pos) else Qt.Edges())

        if hasattr(self, "txt_recv"):
            # 接收区尺寸变化 → 重定位浮动「回到底部」按钮 + 查找栏
            if obj is self.txt_recv and event.type() == QEvent.Resize:
                self._reposition_to_bottom_btn()
                if hasattr(self, "_search_bar"):
                    self._reposition_search_bar()
            # Ctrl+F 打开查找栏 / Esc 关闭（查找栏可见时）
            elif obj is self.txt_recv and event.type() == QEvent.KeyPress:
                if (event.key() == Qt.Key_F
                        and event.modifiers() & Qt.ControlModifier):
                    self._open_search()
                    return True
                if (event.key() == Qt.Key_Escape and hasattr(self, "_search_bar")
                        and self._search_bar.isVisible()):
                    self._close_search()
                    return True
            elif obj is self.txt_recv.viewport():
                # 右键 → 自定义中文菜单（拦截并消费，阻止 Qt 默认菜单）
                if event.type() == QEvent.ContextMenu:
                    self._recv_context_menu(event.globalPos())
                    return True
                # 左键单击 → 整行高亮
                elif (event.type() == QEvent.MouseButtonPress
                      and event.button() == Qt.LeftButton):
                    self._highlight_recv_line(event.pos())
        return super().eventFilter(obj, event)

    def _show_mac_tooltip(self, obj, event):
        """macOS：取目标部件 toolTip 文本，按当前主题不透明显示自绘 tooltip。
        有文本则返回 True 消费事件（阻止透明的原生 tooltip）；无文本交还默认。"""
        text = obj.toolTip() if isinstance(obj, QWidget) else ""
        if not text:
            if self._tooltip_popup is not None:
                self._tooltip_popup.hide()
            return False
        tid = self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT
        t = THEMES.get(tid, THEMES[THEME_DEFAULT])
        # 配色刻意与 QSS 里的 QToolTip 一致（见 apply_style 的 tooltip_bg/fg）：dark 模式
        # 用浅底深字、light 用深底白字——这是有意的反差 tooltip（非写反），改这里要同步 QSS。
        bg = "#F2F2F7" if t.get("mode") == "dark" else "#1C1C1E"
        fg = "#1C1C1E" if t.get("mode") == "dark" else "#FFFFFF"
        if self._tooltip_popup is None:
            self._tooltip_popup = ThemedToolTip()
        self._tooltip_popup.show_text(event.globalPos(), text, bg, fg)
        return True

    def _recv_at_bottom(self, slack: int = 4) -> bool:
        sb = self.txt_recv.verticalScrollBar()
        return sb.value() >= sb.maximum() - slack

    def _scroll_recv_to_bottom(self):
        sb = self.txt_recv.verticalScrollBar()
        sb.setValue(sb.maximum())
        self.btn_to_bottom.hide()

    def _on_recv_scroll(self, _value=None):
        """用户往上翻 → 显示「回到底部」；回到底部 → 隐藏并恢复跟随"""
        self.btn_to_bottom.setVisible(not self._recv_at_bottom())
        self._reposition_to_bottom_btn()

    def _reposition_to_bottom_btn(self):
        if not hasattr(self, "btn_to_bottom"):
            return
        self.btn_to_bottom.adjustSize()
        vp = self.txt_recv.viewport()
        bw = self.btn_to_bottom.width()
        bh = self.btn_to_bottom.height()
        # 右下角，留 12px 边距（基于 viewport 尺寸，避开滚动条）
        x = vp.width() - bw - 12
        y = vp.height() - bh - 12
        self.btn_to_bottom.move(max(0, x), max(0, y))
        self.btn_to_bottom.raise_()

    # ----- 数据区：内嵌浮动查找栏（浏览器 Ctrl+F 风格）-----
    def _build_search_bar(self):
        """创建悬浮在 txt_recv 右上角的查找栏（默认隐藏）。"""
        self._search_term = ""
        self._search_matches = []     # 存 QTextCursor
        self._search_idx = -1
        self._search_bar = QWidget(self.txt_recv)
        row = QHBoxLayout(self._search_bar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)
        self.ed_search = QLineEdit()
        self.ed_search.setProperty("tr_placeholder", "search_ph")
        self.ed_search.setPlaceholderText(self._t("search_ph"))
        self.ed_search.setFixedWidth(180)
        self.ed_search.textChanged.connect(self._do_search)
        self.ed_search.returnPressed.connect(self._search_next)
        self.lbl_search_cnt = QLabel("")
        self.btn_search_prev = QPushButton("▲")
        self.btn_search_prev.setProperty("tr_tooltip", "search_prev")
        self.btn_search_prev.setToolTip(self._t("search_prev"))
        self.btn_search_prev.setCursor(Qt.PointingHandCursor)
        self.btn_search_prev.setFixedSize(26, 26)
        self.btn_search_prev.clicked.connect(self._search_prev)
        self.btn_search_next = QPushButton("▼")
        self.btn_search_next.setProperty("tr_tooltip", "search_next")
        self.btn_search_next.setToolTip(self._t("search_next"))
        self.btn_search_next.setCursor(Qt.PointingHandCursor)
        self.btn_search_next.setFixedSize(26, 26)
        self.btn_search_next.clicked.connect(self._search_next)
        self.btn_search_close = QPushButton("✕")
        self.btn_search_close.setCursor(Qt.PointingHandCursor)
        self.btn_search_close.setFixedSize(26, 26)
        self.btn_search_close.clicked.connect(self._close_search)
        row.addWidget(self.ed_search)
        row.addWidget(self.lbl_search_cnt)
        row.addWidget(self.btn_search_prev)
        row.addWidget(self.btn_search_next)
        row.addWidget(self.btn_search_close)
        self._style_search_bar()
        self._search_bar.hide()

    def _style_search_bar(self):
        """按当前主题给查找栏上色（卡片底 + ghost 按钮）。"""
        c = chrome_for(self._theme_id())
        self._search_bar.setStyleSheet(f"""
            QWidget {{ background-color: {c['card_bg']};
                       border: 1px solid {c['separator']}; border-radius: 8px; }}
            QLineEdit {{ background-color: {c['input_bg']}; color: {c['text']};
                         border: 1px solid {c['separator']}; border-radius: 6px;
                         padding: 3px 6px; }}
            QLabel {{ background: transparent; border: none; color: {c['text_sec']};
                      padding: 0 2px; }}
            QPushButton {{ background-color: {c['ghost_bg']}; color: {c['text']};
                           border: none; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {c['ghost_hover']}; }}
        """)

    def _open_search(self):
        """打开查找栏：定位 + 聚焦，若数据区有选中文本则填入。"""
        if not hasattr(self, "_search_bar"):
            return
        sel = self.txt_recv.textCursor().selectedText()
        if sel and " " not in sel:
            # block 掉 textChanged：否则 setText 先触发一次 _do_search，下面又显式搜一次（双重全文扫描）
            self.ed_search.blockSignals(True)
            self.ed_search.setText(sel)
            self.ed_search.blockSignals(False)
        self._style_search_bar()
        self._search_bar.show()
        self._reposition_search_bar()
        self.ed_search.setFocus()
        self.ed_search.selectAll()
        if self.ed_search.text():
            self._do_search()

    def _do_search(self, text=None):
        """输入变化时：交给 _refresh_extra_selections 统一收集匹配 + 刷新高亮/计数，再定位首个。"""
        self._search_term = self.ed_search.text()
        self._search_idx = 0 if self._search_term else -1
        self._refresh_extra_selections()   # 搜索段会收集匹配、clamp idx、刷新计数
        if not self._search_term:
            self._search_matches = []
            self._update_search_count()
        if self._search_matches:
            self._goto_match(self._search_idx)

    def _update_search_count(self):
        if not hasattr(self, "lbl_search_cnt"):
            return
        if self._search_matches:
            self.lbl_search_cnt.setText(
                f"{self._search_idx + 1}/{len(self._search_matches)}")
        elif self._search_term:
            self.lbl_search_cnt.setText(self._t("search_no_match"))
        else:
            self.lbl_search_cnt.setText("")
        # 计数文本变化会改变查找栏所需宽度，重新自适应 + 定位，避免子控件被压缩重叠
        if hasattr(self, "_search_bar"):
            self._reposition_search_bar()

    def _search_next(self):
        if not self._search_matches:
            return
        self._search_idx = (self._search_idx + 1) % len(self._search_matches)
        self._goto_match(self._search_idx)
        # 导航不改变文档，匹配列表不变：只重新着色当前匹配(内部含计数刷新)，免去全文 doc.find 重建
        self._refresh_extra_selections(rebuild_search=False)

    def _search_prev(self):
        if not self._search_matches:
            return
        self._search_idx = (self._search_idx - 1) % len(self._search_matches)
        self._goto_match(self._search_idx)
        self._refresh_extra_selections(rebuild_search=False)

    def _goto_match(self, idx):
        if not (0 <= idx < len(self._search_matches)):
            return
        self.txt_recv.setTextCursor(self._search_matches[idx])
        self.txt_recv.ensureCursorVisible()

    def _close_search(self):
        if hasattr(self, "_search_bar"):
            self._search_bar.hide()
        self._search_term = ""
        self._search_matches = []
        self._search_idx = -1
        if hasattr(self, "lbl_search_cnt"):
            self.lbl_search_cnt.setText("")
        self._refresh_extra_selections()

    def _reposition_search_bar(self):
        if not hasattr(self, "_search_bar"):
            return
        self._search_bar.adjustSize()
        vp = self.txt_recv.viewport()
        if vp is None:   # 极早期(showEvent 之前)viewport 可能尚未就绪，避免 AttributeError
            return
        bw = self._search_bar.width()
        x = vp.width() - bw - 12
        y = 12
        self._search_bar.move(max(0, x), max(0, y))
        self._search_bar.raise_()

    def _highlight_recv_line(self, pos):
        """单击数据区某一行 → 整行高亮；点已高亮行则取消"""
        cur = self.txt_recv.cursorForPosition(pos)
        block_no = cur.blockNumber()
        if block_no == self._recv_highlight_line:
            self._recv_highlight_line = -1
        else:
            self._recv_highlight_line = block_no
        self._refresh_extra_selections()

    def _apply_recv_highlight(self):
        """兼容旧调用名：刷新所有叠加高亮(行高亮 + 关键字高亮)"""
        self._refresh_extra_selections()

    def _schedule_keyword_rebuild(self):
        """收到新数据时调用：生效分组有规则 或 搜索栏活跃 → 启动节流定时器重扫"""
        if self._kw_timer.isActive():
            return
        if self._active_rules() or getattr(self, "_search_term", ""):
            self._kw_timer.start()

    _KW_MAX_SELECTIONS = 2000  # 安全上限，避免像 '00' 这种在 HEX 流里匹配出上万条

    def _refresh_extra_selections(self, rebuild_search=True):
        """统一构建数据区叠加高亮：关键字着色(背景/文字，分收/发范围) + 单击行高亮(最上层)；
        若开启「只显高亮行」过滤，则隐藏未命中关键字的行(块可见性折叠)。"""
        if not hasattr(self, "txt_recv"):
            return
        doc = self.txt_recv.document()
        sels = []
        # 1. 关键字高亮（生效分组；区分大小写子串匹配；按规则 scope 限定 收/发/收发）
        rules = [r for r in self._active_rules()
                 if r.get("enabled", True) and r.get("pattern")]
        # (pattern, QColor, is_bg, scope) — scope: 'both'/'rx'/'tx'
        parsed = [(r["pattern"], QColor(r.get("color", "#FFD60A")),
                   r.get("mode", "bg") == "bg", r.get("scope", "both")) for r in rules]
        # 过滤仅在有 启用+非空 规则时才生效，避免"开了过滤却没规则 → 全空"
        filter_on = self._filter_active()
        capped = False
        dirty = False
        block = doc.begin()
        while block.isValid():
            block_has_match = False
            if parsed and not capped:
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    role = frag.charFormat().property(ROLE_PROP) if frag.isValid() else None
                    if role in (ROLE_RX, ROLE_TX):
                        ftext = frag.text()
                        base = frag.position()
                        for pat, col, is_bg, scope in parsed:
                            if scope == "rx" and role != ROLE_RX:
                                continue
                            if scope == "tx" and role != ROLE_TX:
                                continue
                            start = 0
                            while True:
                                idx = ftext.find(pat, start)
                                if idx < 0:
                                    break
                                block_has_match = True
                                sel = QTextEdit.ExtraSelection()
                                if is_bg:
                                    sel.format.setBackground(col)
                                    # 背景模式：按背景亮度自动配黑/白文字，避免深色主题下
                                    # 浅色文字落在亮高亮底上看不清（亮底配黑字、暗底配白字）。
                                    lum = (0.299 * col.red() + 0.587 * col.green()
                                           + 0.114 * col.blue())
                                    sel.format.setForeground(
                                        QColor("#1C1C1E") if lum > 140 else QColor("#FFFFFF"))
                                else:
                                    sel.format.setForeground(col)
                                cur = QTextCursor(doc)
                                cur.setPosition(base + idx)
                                cur.setPosition(base + idx + len(pat), QTextCursor.KeepAnchor)
                                cur.setKeepPositionOnInsert(True)   # 防末尾追加新数据时该选区延伸把新行也高亮
                                sel.cursor = cur
                                sels.append(sel)
                                start = idx + len(pat)
                                if len(sels) >= self._KW_MAX_SELECTIONS:
                                    capped = True
                                    break
                            if capped:
                                break
                    it += 1
                    if capped:
                        break
            # 过滤：开启时只留命中行；关闭时所有行可见（恢复）
            want_vis = block_has_match if filter_on else True
            if block.isVisible() != want_vis:
                block.setVisible(want_vis)
                dirty = True
            block = block.next()
        if dirty:
            doc.markContentsDirty(0, doc.characterCount())
            self.txt_recv.viewport().update()
        # 2. 单击行高亮（放最后 → 画在最上层），中性半透明，不跟文字撞色
        if self._recv_highlight_line >= 0:
            block = doc.findBlockByNumber(self._recv_highlight_line)
            if block.isValid():
                is_dark = self._theme().get("mode") == "dark"
                hl = QColor(255, 255, 255, 46) if is_dark else QColor(0, 0, 0, 38)
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(hl)
                sel.format.setProperty(QTextFormat.FullWidthSelection, True)
                sel.cursor = QTextCursor(block)
                sels.append(sel)
            else:
                self._recv_highlight_line = -1
        # 3. 搜索高亮（叠加在最上层）：所有匹配淡黄，当前匹配橙色
        if getattr(self, "_search_term", ""):
            if rebuild_search:
                # 文档可能已变(实时接收新数据 / 搜索词变化)：全文 doc.find 重建匹配列表。
                # 导航(上一个/下一个)不改文档，走 rebuild_search=False 跳过这段，避免大文档每次点击都全文扫描。
                self._search_matches = []
                pos = 0
                while True:
                    cur = doc.find(self._search_term, pos)
                    if cur.isNull():
                        break
                    cur.setKeepPositionOnInsert(True)   # 同上：防选区随末尾插入延伸
                    self._search_matches.append(cur)
                    pos = cur.selectionEnd()
                if not (0 <= self._search_idx < len(self._search_matches)):
                    self._search_idx = 0 if self._search_matches else -1
            # 用(已缓存或刚重建的)匹配列表着色：当前匹配橙色、其余淡黄
            for i, cur in enumerate(self._search_matches):
                sel = QTextEdit.ExtraSelection()
                col = QColor("#FFA940") if i == self._search_idx else QColor("#FFE58F")
                sel.format.setBackground(col)
                sel.format.setForeground(QColor("#1C1C1E"))  # 深色文字配亮黄/橙底，深色主题也看得清
                sel.cursor = cur
                sels.append(sel)
            self._update_search_count()
        self.txt_recv.setExtraSelections(sels)

    # ----- 关键字高亮：分组模型（多个命名分组，每组多条规则，单个生效分组）-----
    def _load_keyword_groups(self):
        """加载分组 + 生效分组名。兼容旧版扁平 keyword_rules → 迁移成「默认」分组。
        返回 (groups, active_index, loaded_ok)；loaded_ok=False 表示走了迁移/默认(损坏或缺失)，
        调用方据此落盘，避免每次启动重复迁移。active=-1 表示关闭。"""
        groups = []
        raw = self.settings.value("keyword_groups", "")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    groups = [g for g in data
                              if isinstance(g, dict) and isinstance(g.get("rules"), list)]
            except Exception:
                groups = []
        loaded_ok = bool(groups)
        if not groups:
            # 迁移旧扁平规则(若有)到「默认」分组
            old_rules = []
            old = self.settings.value("keyword_rules", "")
            if old:
                try:
                    parsed = json.loads(old)
                    if isinstance(parsed, list):
                        old_rules = parsed
                except Exception:
                    pass
            groups = [{"name": self._t("kw_default_group"), "rules": old_rules}]
        # 生效分组按名称记忆(索引会因增删变动)
        active = -1
        active_name = self.settings.value("keyword_active", "")
        if active_name:
            for i, g in enumerate(groups):
                if g.get("name") == active_name:
                    active = i
                    break
        return groups, active, loaded_ok

    def _save_keyword_groups(self):
        self.settings.setValue("keyword_groups",
                               json.dumps(self._keyword_groups, ensure_ascii=False))
        name = (self._keyword_groups[self._keyword_active]["name"]
                if 0 <= self._keyword_active < len(self._keyword_groups) else "")
        self.settings.setValue("keyword_active", name)
        self.settings.remove("keyword_rules")    # 清理已迁移的旧扁平键
        self.settings.sync()

    def _active_rules(self):
        """当前生效分组的规则列表；关闭(-1)或越界时返回空列表。"""
        if 0 <= self._keyword_active < len(self._keyword_groups):
            return self._keyword_groups[self._keyword_active]["rules"]
        return []

    def _apply_keyword_rules(self):
        """规则内容变更后：持久化 + 立即重扫高亮（绕过节流，立刻见效）"""
        self._save_keyword_groups()
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _rebuild_kw_group_combo(self):
        """重建数据区标题栏的分组下拉：顶部「（关闭）」+ 各分组名，选中当前生效分组。"""
        if not hasattr(self, "cb_kw_group"):
            return
        self.cb_kw_group.blockSignals(True)
        self.cb_kw_group.clear()
        self.cb_kw_group.addItem(self._t("kw_group_off"), -1)
        for i, g in enumerate(self._keyword_groups):
            self.cb_kw_group.addItem(g.get("name", f"组{i + 1}"), i)
        sel = 0
        for k in range(self.cb_kw_group.count()):
            if self.cb_kw_group.itemData(k) == self._keyword_active:
                sel = k
                break
        self.cb_kw_group.setCurrentIndex(sel)
        self.cb_kw_group.blockSignals(False)

    def _on_kw_group_changed(self, _i=None):
        """主界面切换生效分组：按哪个分组高亮。"""
        data = self.cb_kw_group.currentData()
        self._keyword_active = data if data is not None else -1
        self._save_keyword_groups()
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _kw_groups_changed(self):
        """弹窗里增/删/重命名分组后：钳制生效索引、存盘、重建主下拉、刷新高亮。"""
        if self._keyword_active >= len(self._keyword_groups):
            self._keyword_active = -1
        self._save_keyword_groups()
        self._rebuild_kw_group_combo()
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _on_filter_hl_toggled(self, _on=None):
        """切换「只显高亮行」：立即重算可见性"""
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _filter_active(self) -> bool:
        """「只显高亮行」是否真正生效：开关开 且 至少有一条 启用+非空 的规则。
        _append_block_data 与 _refresh_extra_selections 共用，避免判断不一致导致闪烁。"""
        if not (hasattr(self, "btn_filter_hl") and self.btn_filter_hl.isChecked()):
            return False
        return any(r.get("enabled", True) and r.get("pattern")
                   for r in self._active_rules())

    def _block_has_keyword_match(self, block) -> bool:
        """单个块的 RX/TX 正文是否命中生效分组里任一启用规则(按 scope 限定 收/发)"""
        rules = [r for r in self._active_rules()
                 if r.get("enabled", True) and r.get("pattern")]
        if not rules:
            return False
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            role = frag.charFormat().property(ROLE_PROP) if frag.isValid() else None
            if role in (ROLE_RX, ROLE_TX):
                ftext = frag.text()
                for r in rules:
                    scope = r.get("scope", "both")
                    if scope == "rx" and role != ROLE_RX:
                        continue
                    if scope == "tx" and role != ROLE_TX:
                        continue
                    if r["pattern"] in ftext:
                        return True
            it += 1
        return False

    def _role_color(self, role, theme=None):
        """数据区某角色(时间戳/RX/TX)在指定主题下的文字色"""
        theme = theme or self._theme()
        if role == ROLE_TS:
            return _mix(theme["ts"], theme["fg"], 0.40)
        if role == ROLE_TX:
            return theme["tx"]
        return theme["fg"]          # ROLE_RX 及兜底

    def _recolor_history(self):
        """切主题时把数据区已有文字按角色重涂成新主题色，避免浅↔深切换后看不见。
        遍历所有 fragment 读 ROLE_PROP，先收集区间再统一改(改格式会让迭代器失效)。
        大文档优化：合并相邻同色区间 + beginEditBlock 批处理 + 关刷新，避免逐片段重排卡死。"""
        theme = self._theme()
        doc = self.txt_recv.document()
        # 每个角色的目标色只算一次(原来每片段都建 QColor + 调 _role_color)
        role_col = {r: QColor(self._role_color(r, theme))
                    for r in (None, ROLE_TS, ROLE_RX, ROLE_TX)}
        ranges = []  # (start, end, QColor)，相邻同色自动合并
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    role = frag.charFormat().property(ROLE_PROP)
                    col = role_col.get(role, role_col[None])
                    start = frag.position()
                    end = start + frag.length()
                    if ranges and ranges[-1][1] == start and ranges[-1][2] == col:
                        ranges[-1] = (ranges[-1][0], end, col)   # 合并相邻同色
                    else:
                        ranges.append((start, end, col))
                it += 1
            block = block.next()
        if not ranges:
            return
        self.txt_recv.setUpdatesEnabled(False)
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        try:
            for start, end, col in ranges:
                cur.setPosition(start)
                cur.setPosition(end, QTextCursor.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setForeground(col)
                cur.mergeCharFormat(fmt)
        finally:
            cur.endEditBlock()
            self.txt_recv.setUpdatesEnabled(True)

    def build_send_card(self):
        """右侧主区域：发送区"""
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._tr_label("send_area", 13, bold=True))

        # ---- 多条发送快捷栏：选分组 + ▶/■ 循环 + 命令平铺直接发 ----
        self._ms_groups, _ms_ok = self._load_ms_groups()
        try:
            self._ms_group_idx = int(self.settings.value("multi_send_group_idx", 0))
        except (ValueError, TypeError):
            self._ms_group_idx = 0
        if not (0 <= self._ms_group_idx < len(self._ms_groups)):
            self._ms_group_idx = 0
        if not _ms_ok:    # 迁移/首次/损坏 → 落盘，避免每次启动重复迁移
            self._save_ms_groups()
        self._ms_cycle_seq = []
        self._ms_cycle_idx = 0
        self._ms_cycle_timer = QTimer(self)
        self._ms_cycle_timer.setSingleShot(True)
        self._ms_cycle_timer.timeout.connect(self._ms_cycle_step)

        ms_bar = QHBoxLayout()
        ms_bar.setSpacing(6)
        self.btn_multi = QPushButton(self._t("multi_send"))
        self.btn_multi.setObjectName("GhostBtn")
        self.btn_multi.setProperty("tr_text", "multi_send")
        self.btn_multi.clicked.connect(self.open_multi_send)
        ms_bar.addWidget(self.btn_multi)
        self.btn_ms_cycle = QPushButton(self._t("ms_cycle"))
        self.btn_ms_cycle.setObjectName("GhostBtn")
        self.btn_ms_cycle.clicked.connect(self._ms_toggle_cycle)
        ms_bar.addWidget(self.btn_ms_cycle)
        self.cb_ms_group = QComboBox()
        self.cb_ms_group.setMinimumWidth(110)
        self.cb_ms_group.currentIndexChanged.connect(self._on_ms_group_changed)
        ms_bar.addWidget(self.cb_ms_group)
        self._ms_quick_host = QWidget()
        self._ms_quick_host.setObjectName("MsQuickHost")
        self._ms_quick_h = QHBoxLayout(self._ms_quick_host)
        self._ms_quick_h.setContentsMargins(0, 0, 0, 0)
        self._ms_quick_h.setSpacing(6)
        self._ms_quick_host.setAutoFillBackground(False)
        ms_qscroll = QScrollArea()
        ms_qscroll.setObjectName("MsQuickScroll")
        ms_qscroll.setWidget(self._ms_quick_host)
        ms_qscroll.setWidgetResizable(True)
        ms_qscroll.setFrameShape(QFrame.NoFrame)
        ms_qscroll.setFixedHeight(38)
        ms_qscroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ms_qscroll.viewport().setAutoFillBackground(False)
        ms_bar.addWidget(ms_qscroll, 1)
        layout.addLayout(ms_bar)
        self._rebuild_ms_group_combo()
        self._rebuild_ms_quick_bar()

        self.txt_send = QTextEdit()
        self.txt_send.setObjectName("SendBox")
        self.txt_send.setFont(mono_font(10))
        # 固定高度、不拉伸：否则与接收区(数据区)抢垂直空间，发送卡片被压缩导致按钮和发送框重叠
        self.txt_send.setFixedHeight(64)
        self.txt_send.setProperty("tr_placeholder", "send_placeholder")
        self.txt_send.setPlaceholderText(self._t("send_placeholder"))
        layout.addWidget(self.txt_send)

        btn_row = QHBoxLayout()
        self.btn_load = QPushButton(self._t("read_file"))
        self.btn_load.setObjectName("GhostBtn")
        self.btn_load.setProperty("tr_text", "read_file")
        self.btn_load.clicked.connect(self.load_file_to_send)
        btn_row.addWidget(self.btn_load)

        self.btn_clear_tx = QPushButton(self._t("clear"))
        self.btn_clear_tx.setObjectName("GhostBtn")
        self.btn_clear_tx.setProperty("tr_text", "clear")
        self.btn_clear_tx.clicked.connect(lambda: self.txt_send.clear())
        btn_row.addWidget(self.btn_clear_tx)

        btn_row.addStretch(1)

        self.btn_send = QPushButton(self._t("send_btn"))
        self.btn_send.setObjectName("PrimaryBtn")
        self.btn_send.setMinimumHeight(36)
        self.btn_send.setMinimumWidth(120)
        self.btn_send.setProperty("tr_text", "send_btn")
        self.btn_send.clicked.connect(self.do_send)
        btn_row.addWidget(self.btn_send)

        layout.addLayout(btn_row)
        return card

    def apply_style(self):
        """根据当前主题构建全局 QSS — light/dark 模式整体切换"""
        tid = self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT
        c = chrome_for(tid)
        t = THEMES.get(tid, THEMES[THEME_DEFAULT])

        # Tooltip 在 dark mode 用浅色 (反差)，light 用深色
        tooltip_bg = "#F2F2F7" if t.get("mode") == "dark" else "#1C1C1E"
        tooltip_fg = "#1C1C1E" if t.get("mode") == "dark" else "#FFFFFF"

        qss = f"""
        QMainWindow, QWidget#Central, QWidget#Content {{
            background-color: {c['window_bg']};
        }}
        QFrame#Card {{
            background-color: {c['card_bg']};
            border-radius: 14px;
            border: 0px;
        }}
        QLabel {{ color: {c['text']}; background: transparent; }}
        QComboBox, QLineEdit {{
            background-color: {c['input_bg']};
            border: 1px solid {c['separator']};
            border-radius: 6px;
            padding: 2px 7px;
            min-height: 16px;
            font-family: 'Segoe UI';
            font-size: 11px;
            color: {c['text']};
            selection-background-color: {c['accent']};
        }}
        QComboBox:focus, QLineEdit:focus {{
            border: 1px solid {c['accent']};
            background-color: {c['input_focus_bg']};
        }}
        QComboBox:disabled, QLineEdit:disabled {{
            background-color: {c['card_bg']};
            color: {_mix(c['text_sec'], c['card_bg'], 0.45)};
            border: 1px solid {_mix(c['separator'], c['card_bg'], 0.5)};
        }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {c['text_sec']};
            margin-right: 8px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['combo_dropdown_bg']};
            color: {c['text']};
            border: 1px solid {c['separator']};
            border-radius: 0px;
            padding: 4px;
            outline: 0px;
            selection-background-color: {c['accent']};
            selection-color: #FFFFFF;
        }}
        QPushButton#PrimaryBtn {{
            background-color: {c['accent']};
            color: white;
            border: 0px;
            border-radius: 9px;
            font-family: 'Segoe UI';
            font-size: 12px;
            font-weight: 600;
            padding: 5px 16px;
        }}
        QPushButton#PrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#PrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#PrimaryBtn[state="open"] {{ background-color: {c['danger']}; }}
        QPushButton#PrimaryBtn[state="open"]:hover {{ background-color: {c['danger_hover']}; }}
        QPushButton#GhostBtn {{
            background-color: {c['ghost_bg']};
            color: {c['accent']};
            border: 0px;
            border-radius: 7px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 500;
            padding: 5px 12px;
            min-height: 18px;
        }}
        QPushButton#GhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#GhostBtn:pressed {{ background-color: {c['ghost_pressed']}; }}
        QPushButton#GhostBtn:checked {{ background-color: {c['accent']}; color: white; }}
        QPushButton#IconBtn {{
            background-color: {c['ghost_bg']};
            color: {c['text_sec']};
            border: 0px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton#IconBtn:hover {{
            background-color: {c['ghost_hover']};
            color: {c['accent']};
        }}
        QScrollArea#MsQuickScroll, QWidget#MsQuickHost {{ background: transparent; border: 0px; }}
        QPushButton#MsQuickBtn {{
            background-color: {c['ghost_bg']}; color: {c['text']}; border: 1px solid {c['separator']};
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 11px; padding: 2px 10px;
        }}
        QPushButton#MsQuickBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        QPushButton#MsQuickBtn:pressed {{ background-color: {c['ghost_pressed']}; }}
        QPushButton#ToBottomBtn {{
            background-color: {c['accent']};
            color: white;
            border: 0px;
            border-radius: 13px;
            padding: 4px 14px;
            font-family: 'Segoe UI';
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#ToBottomBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#ToBottomBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QTextEdit#RecvBox {{
            background-color: {t['bg']};
            border: 1px solid {c['separator']};
            border-radius: 10px;
            padding: 10px;
            color: {t['fg']};
            selection-background-color: {c['accent']};
        }}
        QTextEdit#SendBox {{
            background-color: {c['input_bg']};
            border: 1px solid {c['separator']};
            border-radius: 10px;
            padding: 10px;
            color: {c['text']};
            selection-background-color: {c['accent']};
        }}
        QTextEdit#RecvBox:focus, QTextEdit#SendBox:focus {{
            border: 1px solid {c['accent']};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {c['scrollbar']};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_hover']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QStatusBar {{
            background: transparent;
            color: {c['text_sec']};
            border-top: 1px solid {c['separator']};
        }}
        QStatusBar QLabel {{ color: {c['text_sec']}; background: transparent; }}
        QStatusBar::item {{ border: 0px; }}
        QToolTip {{
            background-color: {tooltip_bg};
            color: {tooltip_fg};
            border: 0px;
            border-radius: 6px;
            padding: 4px 8px;
        }}
        QWidget#TitleBar {{
            background-color: {c['window_bg']};
            border-bottom: 1px solid {c['separator']};
        }}
        QPushButton#CtrlBtn {{
            background-color: transparent;
            color: {c['text']};
            border: 0px;
            font-size: 14px;
            font-family: 'Segoe UI';
        }}
        QPushButton#CtrlBtn:hover {{ background-color: {c['title_btn_hover']}; }}
        QPushButton#CloseBtn:hover {{
            background-color: {c['danger']};
            color: #FFFFFF;
        }}
        QWidget#TitleBar QComboBox {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 1px 8px;
            min-height: 22px;
            font-size: 12px;
            color: {c['text']};
        }}
        QWidget#TitleBar QComboBox:hover {{
            background-color: {c['title_combo_hover']};
        }}
        QWidget#TitleBar QComboBox::drop-down {{
            border: none;
            width: 18px;
        }}
        QScrollArea#Sidebar {{
            background: transparent;
            border: 0px;
        }}
        QScrollArea#Sidebar > QWidget > QWidget {{
            background: transparent;
        }}
        QWidget#SidebarHost {{
            background: transparent;
        }}
        """
        self.setStyleSheet(localize_qss(qss))
        # 强制所有子 widget 重新评估样式 —— Qt 有时 setStyleSheet 后旧子组件保留缓存样式
        # 典型表现：重启后从设置里恢复主题，title bar 变了但中间数据区还是旧色
        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)

        # 下拉弹出容器(QComboBoxPrivateContainer)是独立顶层窗口，其底色走系统调色板默认白，
        # 深色主题下圆角/边框处会露白边。这里把每个下拉的弹出容器背景刷成下拉色，彻底消除白边。
        for combo in self.findChildren(QComboBox):
            popup = combo.view().window()
            popup.setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")

    # ----- 连接 打开/关闭 -----
    def toggle_conn(self):
        if self.conn is not None:
            self.close_conn()
        else:
            self.open_conn()

    @staticmethod
    def _bytes_to_hex(data):
        """字节序列 → 'AA BB CC' 十六进制串（不含尾随空格，调用方按需自加）。
        data 两处调用方都是 bytes（接收信号 / do_send 构造），直接用 bytes.hex。"""
        return data.hex(" ").upper()   # C 级实现，大块数据明显快于逐字节 f-string

    @staticmethod
    def _parse_port(text):
        try:
            p = int(str(text).strip())
        except ValueError:
            return None
        return p if 1 <= p <= 65535 else None

    def open_conn(self):
        proto = self.cb_proto.currentText()
        if proto == PROTO_SERIAL:
            port = self.cb_port.currentData()   # cb_port 不可编辑，currentData 即设备名；无串口/未扫描时为空
            if not port:
                self.toast(self._t("err_no_port"), error=True)
                return
            try:
                baud = int(self.cb_baud.currentText())
            except ValueError:
                self.toast(self._t("err_bad_baud"), error=True)
                return
            parity_map = {"None": serial.PARITY_NONE, "Even": serial.PARITY_EVEN,
                          "Odd": serial.PARITY_ODD, "Mark": serial.PARITY_MARK,
                          "Space": serial.PARITY_SPACE}
            stopbits_map = {"1": serial.STOPBITS_ONE, "1.5": serial.STOPBITS_ONE_POINT_FIVE,
                            "2": serial.STOPBITS_TWO}
            databits_map = {"5": serial.FIVEBITS, "6": serial.SIXBITS,
                            "7": serial.SEVENBITS, "8": serial.EIGHTBITS}
            conn = SerialConn(port, baud, databits_map[self.cb_databits.currentText()],
                              parity_map[self.cb_parity.currentText()],
                              stopbits_map[self.cb_stopbits.currentText()])
        elif proto == PROTO_TCP_SERVER:
            port = self._parse_port(self.ed_local_port.text())
            if port is None:
                self.toast(self._t("err_bad_port"), error=True)
                return
            conn = TcpServerConn(self.cb_local_ip.currentText().strip(), port)
        elif proto == PROTO_TCP_CLIENT:
            ip = self.ed_remote_ip.text().strip()
            port = self._parse_port(self.ed_remote_port.text())
            if not is_valid_ip(ip):
                self.toast(self._t("err_bad_ip"), error=True)
                return
            if port is None:
                self.toast(self._t("err_bad_port"), error=True)
                return
            conn = TcpClientConn(ip, port)
        elif proto == PROTO_UDP_MULTICAST:
            port = self._parse_port(self.ed_local_port.text())
            if port is None:
                self.toast(self._t("err_bad_port"), error=True)
                return
            group = self.ed_group.text().strip()
            if not is_multicast_ipv4(group):
                self.toast(self._t("err_not_multicast"), error=True)
                return
            conn = UdpGroupConn(self.cb_local_ip.currentText().strip(), group, port)
        else:  # UDP
            lport = self._parse_port(self.ed_local_port.text())
            if lport is None:
                self.toast(self._t("err_bad_port"), error=True)
                return
            if self.sw_udp_remote.isChecked():
                # 指定远程：IP/端口必填且合法，固定发往该地址
                rip = self.ed_remote_ip.text().strip()
                rport = self._parse_port(self.ed_remote_port.text())
                if not is_valid_ip(rip):   # 校验 IP 字面量，挡掉 "not.a.valid.ip" 之类
                    self.toast(self._t("err_bad_ip"), error=True)
                    return
                if rport is None:
                    self.toast(self._t("err_bad_port"), error=True)
                    return
            else:
                rip, rport = "", 0   # 不指定远程：回复最近发来数据的对端
            conn = UdpConn(self.cb_local_ip.currentText().strip(), lport, rip, rport)

        conn.data_received.connect(self.on_data_received)
        conn.error_occurred.connect(self._on_conn_error)
        conn.state_changed.connect(self._on_conn_state_changed)
        # clients_changed / peer_changed 是网络连接专有信号；SerialConn 没有，按需连接
        if hasattr(conn, "clients_changed"):
            conn.clients_changed.connect(self._on_clients_changed)
        if hasattr(conn, "peer_changed"):
            conn.peer_changed.connect(self._on_udp_peer_changed)

        # 先赋值再 open()：TCP Server / UDP / 组播的 open() 会**同步**发出 state_changed(True)，
        # 此时 self.conn 必须已指向 conn，否则 _on_conn_state_changed 看到 None、状态栏先跑一次「未连接」
        self.conn = conn
        if not conn.open():   # 同步失败(端口占用/绑定失败)：error_occurred 已触发 _on_conn_error → close_conn 复位
            if self.conn is conn:   # 兜底：万一 _on_conn_error 未清理，这里补清
                self.conn = None
                conn.deleteLater()
            return

        self.btn_open.setProperty("state", "open")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        self.set_settings_enabled(False)
        self._update_net_fields()
        self._update_conn_status()

    def _reset_recv_state(self):
        """统一重置接收解析状态：连接打开/关闭、清空数据区时调用，保证三处一致。"""
        self._last_recv_time = 0.0
        self._last_direction = None
        self._pending_line_break = False
        self._rx_decode_buffer = b""
        self._rx_pending_cr = False
        self._inc_decoder = None
        self._txt_ends_with_nl = True

    def _on_conn_error(self, msg):
        """连接层致命错误：监听/连接/绑定失败 或 连接过程中出错。"""
        proto = self.cb_proto.currentText() if hasattr(self, "cb_proto") else ""
        key = {PROTO_SERIAL: "err_open_failed",
               PROTO_TCP_SERVER: "err_listen_failed",
               PROTO_TCP_CLIENT: "err_connect_failed",
               PROTO_UDP: "err_bind_failed",
               PROTO_UDP_MULTICAST: "err_bind_failed"}.get(proto, "err_connect_failed")
        # 串口已打开成功后 reader 运行时报错(拔出/掉线等)：文案用"连接中断"而非"打开失败"
        if proto == PROTO_SERIAL and self._conn_engaged:
            key = "err_serial_runtime"
        if msg == ERR_CONN_TIMEOUT:   # net_io 超时哨兵 → 按当前语言翻译（避免硬编码中文）
            msg = self._t("err_conn_timeout")
        self.rx_errors += 1           # 连接/链路错误计入 RX 侧错误统计
        self._refresh_stat_labels(with_tooltip=False)
        self.toast(self._t(key, e=msg), error=True)
        if self.conn is not None:
            self.close_conn()

    def _on_conn_state_changed(self, up):
        """已连接/监听(up=True) 或 对端断开(up=False)。
        主动 close_conn() 会先 blockSignals，断开的 False 不会回到这里。"""
        if up:
            self._conn_engaged = True   # 已成功建立 → 此后的 error 属"运行时"而非"打开失败"
            self._update_conn_status()
            self._update_net_fields()   # TCP Server 连上后显示「目标」行
        elif self.conn is not None:
            self.toast(self._t("net_peer_closed"))
            self.close_conn()

    def _on_clients_changed(self, clients):
        """TCP Server 客户端列表变化 → 刷新「目标」下拉（含「全部」）。"""
        if not hasattr(self, "cb_target"):
            return
        cur = self.cb_target.currentData()
        self.cb_target.blockSignals(True)
        self.cb_target.clear()
        self.cb_target.addItem(self._t("client_all"), "__all__")
        for key, label in clients:
            self.cb_target.addItem(label, key)
        idx = self.cb_target.findData(cur) if cur else 0
        self.cb_target.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_target.blockSignals(False)
        self._update_net_fields()   # 客户端 0↔有 变化时同步「目标」行的显隐

    def _on_udp_peer_changed(self, ip, port):
        """UDP 收到新对端时，若「指定远程」关闭(回复模式)，把灰显的远程框刷成最近对端地址。
        纯显示——让用户看到当前在跟谁通信、发送会回复给谁；之后打开「指定远程」即预填好该对端。
        「指定远程」打开时不刷(那是用户固定的目标，不能被覆盖)。"""
        if (self.cb_proto.currentText() == PROTO_UDP
                and not self.sw_udp_remote.isChecked()):
            self.ed_remote_ip.setText(ip)
            self.ed_remote_port.setText(str(port))

    def _update_conn_status(self):
        """刷新状态栏左下角的连接状态文本 + 状态点颜色。"""
        if self.conn is None:
            self.lbl_state.setText(self._t("state_closed"))
            self._set_state_color(opened=False)
            return
        proto = self.cb_proto.currentText()
        if proto == PROTO_SERIAL:
            port = self.cb_port.currentData() or ""
            self.lbl_state.setText(f"● {port} @ {self.cb_baud.currentText()}")
            self._set_state_color(opened=True)
            return
        if proto == PROTO_TCP_SERVER:
            addr = f"{self.cb_local_ip.currentText().strip()}:{self.ed_local_port.text().strip()}"
            self.lbl_state.setText(self._t("net_listening", proto="TCP", addr=addr))
            self._set_state_color(opened=True)
        elif proto == PROTO_TCP_CLIENT:
            if self.conn.is_open:
                addr = f"{self.ed_remote_ip.text().strip()}:{self.ed_remote_port.text().strip()}"
                self.lbl_state.setText(self._t("net_connected", addr=addr))
                self._set_state_color(opened=True)
            else:
                self.lbl_state.setText(self._t("net_connecting"))
                self._set_state_color(opened=False)
        elif proto == PROTO_UDP_MULTICAST:
            addr = f"{self.ed_group.text().strip()}:{self.ed_local_port.text().strip()}"
            self.lbl_state.setText(self._t("net_group_joined", addr=addr))
            self._set_state_color(opened=True)
        else:  # UDP
            addr = f"{self.cb_local_ip.currentText().strip()}:{self.ed_local_port.text().strip()}"
            self.lbl_state.setText(self._t("net_udp_bound", addr=addr))
            self._set_state_color(opened=True)

    def _send_target(self):
        """TCP Server 模式下，当前选中的发送目标客户端 key（"__all__"=全部）；其余协议返回 None。"""
        if (self.cb_proto.currentText() == PROTO_TCP_SERVER
                and hasattr(self, "cb_target") and self.cb_target.count() > 0):
            return self.cb_target.currentData()
        return None

    def _flush_pending_cr(self):
        """把跨包待定的 \\r 输出出来。
        场景：CRLF 模式下对端只发了孤立 \\r 然后没下文，断开连接/切模式时
        如果不冲掉，用户永远看不到那个 \\r。"""
        if not self._rx_pending_cr:
            return
        self._rx_pending_cr = False
        force_new = (self._last_direction != "rx") or self._pending_line_break
        self._append_block_data("\r", direction="rx", force_new_block=force_new)
        self._last_direction = "rx"

    def close_conn(self):
        if self.sw_period.isChecked():
            self.sw_period.setChecked(False)
        # 停多条发送循环定时器：否则非 closeEvent 路径(点断开/对端断开/连接错误)断连后，
        # 下一 tick 的 _ms_cycle_step 还会再弹一个「未连接」toast，造成双重错误提示
        self._ms_stop_cycle()
        # 断开前先把待定 \r 显示出来，否则数据丢用户视觉
        # 同时要在关闭实时日志前执行，保证日志和屏幕显示一致。
        self._flush_pending_cr()
        if self.sw_log_file.isChecked():
            self.sw_log_file.setChecked(False)
        conn = self.conn
        self.conn = None    # 先置空，避免 close() 触发的 state_changed(False) 回调重入
        self._conn_engaged = False
        if conn:
            try:
                conn.blockSignals(True)
                conn.close()
            except Exception:
                pass
            conn.deleteLater()

        self._reset_recv_state()   # 顺带补齐原先漏掉的 _inc_decoder / _txt_ends_with_nl

        self.btn_open.setProperty("state", "")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        self.lbl_state.setText(self._t("state_closed"))
        self._set_state_color(opened=False)
        self.set_settings_enabled(True)
        if hasattr(self, "cb_target"):
            self.cb_target.clear()
        self._update_net_fields()

    # ----- 串口端口扫描 -----
    def refresh_ports(self):
        """点 ⟳ 时调用 — 用一次性后台线程，避免慢驱动卡 GUI。
        结果通过 _on_port_scan_complete 回 GUI 线程（和后台轮询线程共用处理逻辑）。
        线程**不挂 parent**：万一退出时 wait 超时 comports() 还卡住，线程对象不会跟着
        主窗口一起销毁；finished 后 deleteLater 自清，_clear_oneshot_scan 置 None 避免悬空。
        """
        if getattr(self, "_oneshot_scan", None) and self._oneshot_scan.isRunning():
            return  # 节流：上一次还在跑就忽略
        scan = OneShotPortScanner()  # 故意无 parent
        self._oneshot_scan = scan
        scan.scan_complete.connect(self._on_port_scan_complete)
        scan.finished.connect(lambda: self._clear_oneshot_scan(scan))
        scan.finished.connect(scan.deleteLater)
        scan.start()

    def _clear_oneshot_scan(self, scan):
        """deleteLater 之后清掉 Python 属性引用，避免下次 isRunning() 访问已删 C++ 对象。
        `is scan` 守卫：如果期间已经创建了新 scan，不清新的。"""
        if getattr(self, "_oneshot_scan", None) is scan:
            self._oneshot_scan = None

    def _populate_port_combo(self, port_list, keep_device=None):
        self.cb_port.blockSignals(True)
        self.cb_port.clear()
        for device, label in port_list:
            self.cb_port.addItem(label, device)
        if keep_device:
            for i in range(self.cb_port.count()):
                if self.cb_port.itemData(i) == keep_device:
                    self.cb_port.setCurrentIndex(i)
                    break
        self.cb_port.blockSignals(False)

    def _on_port_scan_complete(self, port_list):
        if not port_list:
            port_list = [("", self._t("no_ports"))]
        # 串口已连接时不动 cb_port：端口占用中，也别打断用户的当前选择
        if self.conn is not None and self.cb_proto.currentText() == PROTO_SERIAL:
            return
        if self.cb_port.view().isVisible():   # 下拉正展开时不刷，避免选项跳动
            return
        if port_list == self._last_port_list:
            return
        # 优先保留用户当前选择；启动恢复时 cb_port 还空，则用待恢复端口选回上次设备
        keep = self.cb_port.currentData() or getattr(self, "_pending_restore_port", None)
        self._last_port_list = port_list
        self._populate_port_combo(port_list, keep)
        # 待恢复端口确实匹配上了才清除；没插上时保留，等设备出现的那次扫描再选回
        if (getattr(self, "_pending_restore_port", None)
                and self.cb_port.currentData() == self._pending_restore_port):
            self._pending_restore_port = None

    def _wait_oneshot_scan(self):
        """退出前确保一次性端口扫描线程结束 — 否则可能 QThread: Destroyed while running。"""
        scan = getattr(self, "_oneshot_scan", None)
        if scan and scan.isRunning():
            scan.wait(2000)

    def set_settings_enabled(self, enabled):
        # 远程框(ed_remote_*)启用由 _update_net_fields 统管(TCP恒开/UDP看开关)；
        # 目标客户端下拉(cb_target)连接期间要可切换发送目标，不锁
        for w in (self.cb_proto, self.cb_local_ip, self.ed_local_port,
                  self.ed_group, self.sw_udp_remote,
                  self.cb_port, self.cb_baud, self.cb_databits,
                  self.cb_parity, self.cb_stopbits, self.btn_refresh):
            w.setEnabled(enabled)

    # ----- 主题 -----
    def _theme(self) -> dict:
        return THEMES.get(self._theme_id(), THEMES[THEME_DEFAULT])

    def _apply_theme_label_styles(self, chrome: dict = None):
        c = chrome or chrome_for(self._theme_id())
        for lbl in self.findChildren(QLabel):
            role = lbl.property("theme_color_role")
            if role == "primary":
                lbl.setStyleSheet(f"color: {c['text']}; background: transparent;")
            elif role == "secondary":
                lbl.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")

    def _update_legend_label(self, chrome: dict = None):
        if not hasattr(self, "legend_label"):
            return
        c = chrome or chrome_for(self._theme_id())
        t = self._theme()
        self.legend_label.setText(
            f'<span style="color:{c["text_sec"]};">{self._t("legend_rx")}</span>'
            f'&nbsp;&nbsp;'
            f'<span style="color:{t["tx"]};">{self._t("legend_tx")}</span>'
        )

    def _on_theme_changed(self):
        """切换主题：整体重建 QSS — 侧边栏卡片/按钮/输入框/标题栏/数据区都跟着 light/dark 切换。
        数据区历史文字按角色(时间戳/RX/TX)重涂成新主题色，避免浅↔深切换后看不见。"""
        # 1. 重建全局 QSS，apply_style 会读 cb_theme 当前选项自适应
        self.apply_style()
        # 2. 内联 setStyleSheet 的几处也跟着 chrome palette 刷
        c = chrome_for(self._theme_id())
        self._apply_theme_label_styles(c)
        if hasattr(self, "lbl_version"):
            self.lbl_version.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")
        if hasattr(self, "lbl_log_path"):
            self.lbl_log_path.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")
        if hasattr(self, "status_bar"):
            self.status_bar.setStyleSheet(f"background: transparent; color: {c['text_sec']};")
        if hasattr(self, "lbl_state"):
            self._set_state_color(opened=self._is_open())
        if hasattr(self, "title_bar") and hasattr(self.title_bar, "title_label"):
            self.title_bar.title_label.setStyleSheet(
                f"color: {c['text_sec']}; background: transparent;")
        self._update_legend_label(c)
        # iOS 开关是 custom-paint、不走 QSS，切主题时手动让关态色跟随主题（开态恒用绿）
        for sw in self.findChildren(IOSSwitch):
            sw.set_theme_colors(c["separator"], "#FFFFFF")
        # 数据区历史文字按角色重涂成新主题色 + 行高亮换色（否则浅↔深切换后文字看不见）
        if hasattr(self, "txt_recv"):
            self._recolor_history()
            self._apply_recv_highlight()
        if hasattr(self, "_search_bar"):
            self._style_search_bar()
        # 多条发送/关键字高亮弹窗若开着也跟着换主题
        if getattr(self, "_multi_send_dlg", None) is not None:
            self._multi_send_dlg.refresh_theme()
        if getattr(self, "_keyword_dlg", None) is not None:
            self._keyword_dlg.refresh_theme()

    # ----- 接收 -----
    def _get_codec(self) -> str:
        """当前 RX/TX/文件 编码模式 — 'auto' 或具体 codec 名"""
        if hasattr(self, "cb_encoding"):
            return self.cb_encoding.currentData() or "auto"
        return "auto"

    def _send_codec(self) -> str:
        """TX 用的具体 codec — Auto 模式下默认 utf-8"""
        c = self._get_codec()
        return "utf-8" if c == "auto" else c

    def _on_encoding_changed(self):
        """切换编码时重置增量解码状态，悬挂字节别用新 codec 错误解码"""
        self._rx_decode_buffer = b""
        enc = self._get_codec()
        if enc == "auto":
            self._inc_decoder = None
        else:
            try:
                self._inc_decoder = codecs.getincrementaldecoder(enc)(errors="replace")
            except (LookupError, TypeError):
                self._inc_decoder = None  # 罕见的找不到 codec 直接回退 auto

    def _decode_rx(self, data: bytes) -> str:
        """按选定编码增量解码。Auto 走 UTF-8 优先 / GBK 回退；其他走 Python 标准增量解码器"""
        if self._get_codec() != "auto":
            if self._inc_decoder is None:
                # 第一次调用 / 刚切到具体编码 — 初始化
                self._on_encoding_changed()
            if self._inc_decoder is not None:
                return self._inc_decoder.decode(data, final=False)
            # codec lookup 失败兜底
            return data.decode("latin-1")

        # Auto 模式 — 原 UTF-8 优先, 不完整就缓存, 真乱码回退 GBK
        self._rx_decode_buffer += data
        if not self._rx_decode_buffer:
            return ""
        try:
            text = self._rx_decode_buffer.decode("utf-8")
            self._rx_decode_buffer = b""
            return text
        except UnicodeDecodeError as e:
            if (e.end == len(self._rx_decode_buffer)
                    and "unexpected end of data" in str(e.reason)):
                try:
                    text = self._rx_decode_buffer[:e.start].decode("utf-8")
                    self._rx_decode_buffer = self._rx_decode_buffer[e.start:]
                    return text
                except UnicodeDecodeError:
                    pass
            text = self._rx_decode_buffer.decode("gbk", errors="replace")
            self._rx_decode_buffer = b""
            return text

    def on_data_received(self, data: bytes):
        # 顶层异常保护：解码/插入等意外异常不应静默丢数据(传到事件循环只在 stderr 打印)
        try:
            self._on_data_received_impl(data)
        except Exception as e:
            self.rx_errors += 1
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("err_rx", e=e), error=True)

    def _on_data_received_impl(self, data: bytes):
        self.rx_bytes += len(data)
        self.rx_packets += 1
        # 标签刷新交给 1Hz 的 _rate_timer：高频收包路径只累加整数计数器，
        # 不每包重建文案 + setText（会触发状态栏重排），高吞吐下避免无谓的 GUI 线程开销。

        use_hex = self.sw_rx_hex.isChecked()
        use_line_split = self.sw_line_split.isChecked() and not use_hex
        now = time.monotonic()

        if use_hex:
            text = self._bytes_to_hex(data) + " "
        else:
            text = self._decode_rx(data)

        # 跨 chunk 的 \r\n 处理 — Auto(0) 和 CRLF(1) 都需要
        # （LF/CR 模式因为单字符就是终止符，无歧义，不需要 defer）
        cross_chunk_crlf = False
        nl_mode_for_defer = self.cb_line_nl.currentIndex() if use_line_split else -1
        if nl_mode_for_defer in (0, 1):
            if self._rx_pending_cr:
                if text.startswith("\n"):
                    text = text[1:]
                    cross_chunk_crlf = True
                else:
                    # 没接到 \n —— Auto 模式下 \r 单字符也是换行；
                    # CRLF 模式下 \r 单字符是数据（不是终止符），但 QTextEdit
                    # 渲染时仍会把它当换行显示。两种模式都先把 \r 还回去，
                    # 后续 split 按规则处理（Auto 把它当换行；CRLF 视为数据）
                    text = "\r" + text
                self._rx_pending_cr = False
            if text.endswith("\r"):
                self._rx_pending_cr = True
                text = text[:-1]

            if cross_chunk_crlf and not text:
                self._pending_line_break = True
                self._last_recv_time = now
                return

        if use_line_split:
            nl_mode = self.cb_line_nl.currentIndex()
            if nl_mode == 1:
                segments = text.split("\r\n")
            elif nl_mode == 2:
                segments = text.split("\n")
            elif nl_mode == 3:
                segments = text.split("\r")
            else:
                normalized = text.replace("\r\n", "\n").replace("\r", "\n")
                segments = normalized.split("\n")
        else:
            segments = [text]

        for i, seg in enumerate(segments):
            is_first = (i == 0)
            is_last = (i == len(segments) - 1)

            if is_first:
                force_new_block = (
                    (self._last_direction != "rx")
                    or self._pending_line_break
                    or cross_chunk_crlf  # 跨包 CRLF 也算上一次换行
                )
                if not force_new_block and self.sw_packet_split.isChecked():
                    try:
                        timeout_ms = max(1, int(self.ed_packet_timeout.text()))
                    except ValueError:
                        timeout_ms = 20
                    gap_ms = (now - self._last_recv_time) * 1000.0
                    if gap_ms > timeout_ms:
                        force_new_block = True
            else:
                force_new_block = True

            if is_last and seg == "" and use_line_split and len(segments) > 1:
                continue

            self._append_block_data(seg, direction="rx", force_new_block=force_new_block)
            self._last_direction = "rx"

        if use_line_split:
            self._pending_line_break = (segments[-1] == "" and len(segments) > 1)
        else:
            self._pending_line_break = False
        self._last_recv_time = now

    def _append_block_data(self, text: str, direction: str, force_new_block: bool):
        theme = self._theme()
        # TX 用主题里的 tx 色，RX 用 fg 默认色（主题切换后旧文字不会重涂）
        body_color = theme["tx"] if direction == "tx" else theme["fg"]
        # 滚动锁定：插入前先记住是否在底部；用独立游标插入，避免动可见光标/选区/视图
        was_at_bottom = self._recv_at_bottom()
        cursor = QTextCursor(self.txt_recv.document())
        cursor.movePosition(QTextCursor.End)

        log_pieces = []

        if force_new_block:
            if not self._txt_ends_with_nl:
                cursor.insertText("\n")
                log_pieces.append("\n")
                self._txt_ends_with_nl = True
            prefix = ""
            if self.sw_show_timestamp.isChecked():
                now = datetime.now()
                prefix = (f"[{now.year}/{now.month:02d}/{now.day:02d} "
                          f"{now.hour:02d}:{now.minute:02d}:{now.second:02d} "
                          f"{now.microsecond // 1000:03d}] ")
                # 箭头跟时间戳绑一起：时间戳关掉时也不显示，纯数据更干净
                prefix += "→ " if direction == "tx" else "← "
            if prefix:
                # 时间戳 + 箭头用 ts 灰色（淡化）
                ts_fmt = QTextCharFormat()
                # 时间戳色朝正文 fg 靠拢 40%，提高对比度（原 ts 偏淡看不清）
                ts_fmt.setForeground(QColor(self._role_color(ROLE_TS, theme)))
                ts_fmt.setProperty(ROLE_PROP, ROLE_TS)
                cursor.setCharFormat(ts_fmt)
                cursor.insertText(prefix)
                log_pieces.append(prefix)
                self._txt_ends_with_nl = False

        # 正文用 body_color
        body_role = ROLE_TX if direction == "tx" else ROLE_RX
        body_fmt = QTextCharFormat()
        body_fmt.setForeground(QColor(body_color))
        body_fmt.setProperty(ROLE_PROP, body_role)
        cursor.setCharFormat(body_fmt)
        cursor.insertText(text)
        log_pieces.append(text)
        if text:
            self._txt_ends_with_nl = text.endswith("\n")

        reset = QTextCharFormat()
        reset.setForeground(QColor(theme["fg"]))
        cursor.setCharFormat(reset)
        # 只有原本就在底部才跟随到最新；用户往上翻看时保持定住
        # 过滤开启时，立即决定刚追加这行的可见性 —— 在滚动到底之前完成，
        # 避免"先显示→滚到底→150ms后异步隐藏→高度收缩跳动"的抖动
        if self._filter_active():
            blk = cursor.block()
            vis = self._block_has_keyword_match(blk)
            if blk.isVisible() != vis:
                blk.setVisible(vis)
                self.txt_recv.document().markContentsDirty(
                    blk.position(), max(1, blk.length()))

        if was_at_bottom:
            sb = self.txt_recv.verticalScrollBar()
            sb.setValue(sb.maximum())

        self._schedule_keyword_rebuild()    # 节流重扫关键字高亮(着色)

        if self._log_file:
            try:
                self._log_file.write("".join(log_pieces))
                self._log_file.flush()
                self._maybe_rotate_log()    # 超过分包上限则切到下一个文件
            except Exception as e:
                self.toast(self._t("err_log_write", e=e), error=True)
                self._close_log_file()
                self.sw_log_file.setChecked(False)

    # ----- 多条发送：分组数据 + 主界面快捷栏 + 循环 -----
    def _load_ms_groups(self):
        """加载多条发送分组；兼容旧版扁平 multi_send_items → 迁移成「默认」分组。
        返回 (groups, loaded_ok)；loaded_ok=False 表示走了迁移/默认(损坏或缺失)，调用方据此落盘。"""
        groups = []
        raw = self.settings.value("multi_send_groups", "")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    groups = [g for g in data
                              if isinstance(g, dict) and isinstance(g.get("items"), list)]
            except Exception:
                groups = []
        loaded_ok = bool(groups)
        if not groups:
            old_items = []
            old = self.settings.value("multi_send_items", "")
            if old:
                try:
                    parsed = json.loads(old)
                    if isinstance(parsed, list):
                        old_items = parsed
                except Exception:
                    pass
            groups = [{"name": self._t("kw_default_group"), "items": old_items}]
        return groups, loaded_ok

    def _save_ms_groups(self):
        self.settings.setValue("multi_send_groups",
                               json.dumps(self._ms_groups, ensure_ascii=False))
        self.settings.setValue("multi_send_group_idx", self._ms_group_idx)
        self.settings.remove("multi_send_items")    # 清理已迁移的旧扁平键
        self.settings.sync()

    def _ms_active_items(self):
        if 0 <= self._ms_group_idx < len(self._ms_groups):
            return self._ms_groups[self._ms_group_idx]["items"]
        return []

    def _send_ms_item(self, item):
        self._send_text(item.get("data", ""),
                        hex_mode=bool(item.get("hex", False)),
                        newline=int(item.get("nl", 0)),
                        checksum=int(item.get("cs", 0)))

    def _rebuild_ms_group_combo(self):
        if not hasattr(self, "cb_ms_group"):
            return
        self.cb_ms_group.blockSignals(True)
        self.cb_ms_group.clear()
        for i, g in enumerate(self._ms_groups):
            self.cb_ms_group.addItem(g.get("name", f"组{i + 1}"), i)
        if not (0 <= self._ms_group_idx < len(self._ms_groups)):
            self._ms_group_idx = 0
        self.cb_ms_group.setCurrentIndex(self._ms_group_idx)
        self.cb_ms_group.blockSignals(False)

    def _on_ms_group_changed(self, _i=None):
        data = self.cb_ms_group.currentData()
        self._ms_group_idx = data if data is not None else 0
        self._ms_stop_cycle()
        self._save_ms_groups()
        self._rebuild_ms_quick_bar()

    def _rebuild_ms_quick_bar(self):
        """重建快捷发送按钮：选中分组里每条非空命令一个按钮，点击立即发。"""
        if not hasattr(self, "_ms_quick_h"):
            return
        while self._ms_quick_h.count():
            it = self._ms_quick_h.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for item in self._ms_active_items():
            if not str(item.get("data", "")).strip():
                continue
            label = (item.get("name") or "").strip() or item.get("data", "")
            if len(label) > 16:
                label = label[:15] + "…"
            btn = QPushButton(label)
            btn.setObjectName("MsQuickBtn")
            btn.setToolTip(item.get("data", ""))
            btn.clicked.connect(lambda _=False, it=item: self._send_ms_item(it))
            self._ms_quick_h.addWidget(btn)
        self._ms_quick_h.addStretch(1)

    def _ms_groups_changed(self):
        """弹窗编辑分组后回调：钳制索引、存盘、重建主界面下拉与快捷栏。"""
        if self._ms_group_idx >= len(self._ms_groups):
            self._ms_group_idx = max(0, len(self._ms_groups) - 1)
        self._save_ms_groups()
        self._rebuild_ms_group_combo()
        self._rebuild_ms_quick_bar()
        # 循环运行中编辑了条目：实时刷新发送序列，下一轮即用新数据（序列变空则下一步自停）
        if self._ms_cycle_timer.isActive():
            self._ms_cycle_seq = self._build_ms_cycle_seq()

    # ----- 多条发送：循环（按每行延时）-----
    def _build_ms_cycle_seq(self):
        """当前分组里勾选且非空的条目 → 循环发送序列 (data, hex, nl, cs, delay)。"""
        return [(it.get("data", ""), bool(it.get("hex", False)), int(it.get("nl", 0)),
                 int(it.get("cs", 0)), max(1, int(it.get("delay", 1000))))
                for it in self._ms_active_items()
                if it.get("checked") and str(it.get("data", "")).strip()]

    def _ms_toggle_cycle(self):
        if self._ms_cycle_timer.isActive():
            self._ms_stop_cycle()
            return
        seq = self._build_ms_cycle_seq()
        if not seq:
            self.toast(self._t("ms_none_checked"), error=True)
            return
        if not self._is_open():
            self.toast(self._t("net_not_open"), error=True)
            return
        self._ms_cycle_seq = seq
        self._ms_cycle_idx = 0
        self._set_ms_cycle_btn(True)
        self._ms_cycle_step()

    def _ms_cycle_step(self):
        if not self._ms_cycle_seq:
            self._ms_stop_cycle()
            return
        if not self._is_open():
            self.toast(self._t("net_not_open"), error=True)
            self._ms_stop_cycle()
            return
        data, hx, nl, cs, delay = self._ms_cycle_seq[self._ms_cycle_idx % len(self._ms_cycle_seq)]
        # 发送失败(坏数据/写异常等)立即停止，避免每轮都刷错误 toast
        # (空命令在 _ms_toggle_cycle 构建序列时已过滤，这里的 False 都是真失败)
        if not self._send_text(data, hex_mode=hx, newline=nl, checksum=cs):
            self._ms_stop_cycle()
            return
        self._ms_cycle_idx += 1
        self._ms_cycle_timer.start(delay)

    def _ms_stop_cycle(self):
        if hasattr(self, "_ms_cycle_timer"):
            self._ms_cycle_timer.stop()
        self._set_ms_cycle_btn(False)

    def _set_ms_cycle_btn(self, running):
        if hasattr(self, "btn_ms_cycle"):
            self.btn_ms_cycle.setText(self._t("ms_cycle_stop" if running else "ms_cycle"))

    # ----- 发送 -----
    def open_multi_send(self):
        """打开多条发送弹窗（单实例，复用并刷新主题/语言）"""
        if getattr(self, "_multi_send_dlg", None) is None:
            self._multi_send_dlg = MultiSendDialog(self)
        dlg = self._multi_send_dlg
        if dlg._save_timer.isActive():   # 重复打开前先落盘待提交编辑，避免 _reload_rows 清掉
            dlg._commit_now()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg._reload_group_list()
        dlg._reload_rows()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_keyword_highlight(self):
        """打开关键字高亮配置弹窗（单实例，复用并刷新主题/语言）"""
        if getattr(self, "_keyword_dlg", None) is None:
            self._keyword_dlg = KeywordHighlightDialog(self)
        dlg = self._keyword_dlg
        if dlg._commit_timer.isActive():   # 重复打开前先落盘待提交编辑
            dlg._commit_now()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg._reload_group_list()    # 复用时同步最新分组
        dlg._reload_rows()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def do_send(self):
        raw = self.txt_send.toPlainText()
        if not raw:
            return
        ok = self._send_text(raw)
        # 定时发送时任何发送失败(数据格式错误/未连接/无目标/写失败)都关掉定时器，
        # 避免格式错误等确定性失败每周期刷一次 toast 形成轰炸
        if not ok and self.sw_period.isChecked():
            self.sw_period.setChecked(False)

    def _send_text(self, raw, hex_mode=None, newline=None, checksum=None) -> bool:
        """解析并发送一段文本(HEX/文本)，复用追加换行+校验+显示。
        hex_mode/newline/checksum 为 None 时用主界面全局设置；多条发送可逐条传入独立值。
          newline: None=全局; 0=无 1=CRLF 2=LF 3=CR
          checksum: None=全局; 否则校验项索引(0=无…)
        成功返回 True"""
        if not self._is_open():
            self.toast(self._t("net_not_open"), error=True)
            return False
        if not raw:
            return False
        use_hex = self.sw_tx_hex.isChecked() if hex_mode is None else hex_mode

        try:
            if use_hex:
                import re as _re
                # 1. 先剥掉注释 — 否则注释里 "face" "dead" "beef" 这些 a-f 字符会被当数据
                cleaned = _re.sub(r'/\*.*?\*/', '', raw, flags=_re.DOTALL)   # 块注释
                cleaned = _re.sub(r'//[^\n]*', '', cleaned)                    # 行注释 //
                cleaned = _re.sub(r'#[^\n]*', '', cleaned)                     # 行注释 #
                # 2. 去掉 0x/0X 前缀
                cleaned = cleaned.replace("0x", "").replace("0X", "")
                # 3. 移除允许的分隔符（空白、- : , ;）
                allowed_seps = set(" \t\r\n-:,;")
                filtered = "".join(c for c in cleaned if c not in allowed_seps)
                if not filtered:
                    return False
                # 4. 检查剩下的必须全是 hex —— 出现 ZZ / G 这种就报错，不再静默丢弃
                bad_chars = sorted(set(c for c in filtered
                                       if c not in "0123456789abcdefABCDEF"))
                if bad_chars:
                    err = self._t(
                        "err_hex_invalid_chars",
                        chars=" ".join(repr(c) for c in bad_chars),
                    )
                    self.toast(
                        self._t("err_hex_bad", e=err),
                        error=True,
                    )
                    return False
                if len(filtered) % 2 != 0:
                    self.toast(self._t("err_hex_odd"), error=True)
                    return False
                data = bytes.fromhex(filtered)
            else:
                # 按选定编码发送（默认 UTF-8）— 让用户能给 GBK 设备发中文
                data = raw.encode(self._send_codec(), errors="replace")
        except ValueError as e:
            self.toast(self._t("err_hex_bad", e=e), error=True)
            return False

        # 追加换行 - HEX 和 ASCII 模式都生效
        if newline is None:
            if self.sw_append_newline.isChecked():
                nl_idx = self.cb_append_nl.currentIndex()  # 0=CRLF,1=LF,2=CR
                data += {0: b"\r\n", 1: b"\n", 2: b"\r"}.get(nl_idx, b"\r\n")
        else:
            data += {1: b"\r\n", 2: b"\n", 3: b"\r"}.get(newline, b"")  # 0=无

        # 追加校验
        cs_idx = self.cb_checksum.currentIndex() if checksum is None else checksum
        try:
            data = data + self.compute_checksum(data, cs_idx)
        except Exception as e:
            self.toast(self._t("err_checksum", e=e), error=True)
            return False

        try:
            sent = self.conn.send(data, self._send_target())
        except Exception as e:
            self.tx_errors += 1
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("err_send_failed", e=e), error=True)
            return False
        if sent == SEND_NO_TARGET:   # UDP 无对端 / TCP Server 无客户端
            self.tx_errors += 1
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("net_no_target"), error=True)
            return False
        if sent <= 0:                # 底层 write/writeDatagram 失败（对端断开/网络不可达等）
            self.tx_errors += 1
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("net_send_failed"), error=True)
            return False

        self.tx_bytes += len(data)
        self.tx_packets += 1
        # 同收包路径：成功发送只累加计数器，标签刷新交 1Hz 定时器（多帧连发时不每帧重排状态栏）。

        # 显示到数据区 — 只看「HEX 显示」开关(数据区显示格式)，和发送模式无关：
        # 接收按 HEX 显示，发送也按 HEX 显示，RX/TX 统一
        if self.sw_rx_hex.isChecked():
            display = self._bytes_to_hex(data) + " "
        else:
            display = data.decode(self._send_codec(), errors="replace")
        self._append_block_data(display, direction="tx", force_new_block=True)
        self._last_direction = "tx"
        return True

    @staticmethod
    def compute_checksum(data: bytes, index: int) -> bytes:
        if not data or index <= 0:
            return b""
        if index == 1:  # ADD8
            return bytes([sum(data) & 0xFF])
        if index == 2:  # ~ADD8
            return bytes([(~sum(data)) & 0xFF])
        if index == 3:  # XOR8
            x = 0
            for b in data:
                x ^= b
            return bytes([x])
        if index == 4:  # CRC8 (poly 0x07)
            crc = 0
            for b in data:
                crc ^= b
                for _ in range(8):
                    crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
            return bytes([crc])
        if index == 5:  # ModbusCRC16
            crc = 0xFFFF
            for b in data:
                crc ^= b
                for _ in range(8):
                    crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
            return bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        if index == 6:  # CCITT-CRC16
            crc = 0xFFFF
            for b in data:
                crc ^= (b << 8)
                for _ in range(8):
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
            return bytes([(crc >> 8) & 0xFF, crc & 0xFF])
        if index == 7:  # CRC32
            import zlib
            crc = zlib.crc32(data) & 0xFFFFFFFF
            return bytes([(crc >> 24) & 0xFF, (crc >> 16) & 0xFF,
                          (crc >> 8) & 0xFF, crc & 0xFF])
        if index == 8:  # ADD16
            s = sum(data) & 0xFFFF
            return bytes([(s >> 8) & 0xFF, s & 0xFF])
        if index == 9:  # MOBUS: CRC8 with poly 0x31
            crc = 0
            for b in data:
                crc ^= b
                for _ in range(8):
                    crc = ((crc << 1) ^ 0x31) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
            return bytes([crc])
        return b""

    def on_period_toggled(self, on):
        if on:
            try:
                ms = int(self.ed_period_ms.text())
                if ms < 10:
                    raise ValueError(self._t("err_min_period"))
            except ValueError as e:
                self.toast(self._t("err_period_bad", e=e), error=True)
                self.sw_period.setChecked(False)
                return
            if not self._is_open():
                self.toast(self._t("net_not_open"), error=True)
                self.sw_period.setChecked(False)
                return
            self.send_timer.start(ms)
        else:
            self.send_timer.stop()

    def on_wrap_toggled(self, on):
        self.txt_recv.setLineWrapMode(
            QTextEdit.WidgetWidth if on else QTextEdit.NoWrap)

    # ----- 日志记录 -----
    def _parse_log_limit(self, text) -> int:
        """把分包大小文本解析成字节；无数字(如「不分包」)返回 0。无单位默认 MB。"""
        import re
        m = re.search(r'(\d+(?:\.\d+)?)\s*([KkMmGg]?)', text or "")
        if not m:
            return 0
        val = float(m.group(1))
        mult = {"K": 1024, "M": 1024 * 1024, "G": 1024 ** 3}.get(m.group(2).upper(), 1024 * 1024)
        return int(val * mult)

    def _on_log_split_changed(self, _text=None):
        """改分包大小：实时记录进行中也即时生效。"""
        self._log_limit = self._parse_log_limit(self.cb_log_split.currentText())

    def _log_segment_path(self) -> str:
        """当前分包序号对应的文件名：第 0 包用原始路径，之后加 _001/_002…后缀。"""
        if self._log_seg <= 0:
            return self._log_base_path
        root, ext = os.path.splitext(self._log_base_path)
        return f"{root}_{self._log_seg:03d}{ext}"

    def _set_log_path_label(self, path):
        """更新状态栏的日志文件路径显示（仅记录时显示，太长中间省略，悬停看全路径）。"""
        if not hasattr(self, "lbl_log_path"):
            return
        if not path:
            self.lbl_log_path.setText("")
            self.lbl_log_path.setToolTip("")
            if hasattr(self, "_log_path_sep"):
                self._log_path_sep.hide()
            return
        fm = QFontMetrics(self.lbl_log_path.font())
        w = getattr(self, "_log_path_elide_w", 560)
        self.lbl_log_path.setText("📝 " + fm.elidedText(path, Qt.ElideMiddle, w))
        self.lbl_log_path.setToolTip(path)
        if hasattr(self, "_log_path_sep"):
            self._log_path_sep.show()

    def _open_log_segment(self, path) -> bool:
        try:
            self._log_file = open(path, "a", encoding="utf-8")
            self._log_file_path = path
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._log_file.write(self._t("log_header", time=ts))
            self._log_file.flush()
            self._set_log_path_label(path)
            return True
        except Exception as e:
            self.toast(self._t("err_open_log", e=e), error=True)
            return False

    def _maybe_rotate_log(self):
        """写入后若超过分包上限，切到下一个分包文件。"""
        if not (self._log_file and self._log_limit > 0):
            return
        try:
            if self._log_file.tell() < self._log_limit:
                return
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._log_file.write(self._t("log_footer", time=ts))
            self._log_file.flush()    # close 前先刷盘，避免 close 失败时尾部缓冲丢失
            self._log_file.close()
        except Exception:
            pass
        self._log_seg += 1
        self._log_file = None
        if not self._open_log_segment(self._log_segment_path()):
            self.sw_log_file.setChecked(False)

    def on_log_file_toggled(self, on):
        if on:
            path, _ = QFileDialog.getSaveFileName(
                self, self._t("dlg_log_path"),
                f"data_log_{datetime.now():%Y%m%d_%H%M%S}.log",
                self._t("filter_text"))
            if not path:
                self.sw_log_file.blockSignals(True)   # 取消选择 → 关开关但别递归回调本函数
                self.sw_log_file.setChecked(False)
                self.sw_log_file.blockSignals(False)
                return
            self._log_limit = self._parse_log_limit(self.cb_log_split.currentText())
            self._log_base_path = path
            self._log_seg = 0
            if self._open_log_segment(path):
                self.toast(self._t("log_started", path=path))
            else:
                self.sw_log_file.setChecked(False)
        else:
            self._close_log_file()

    def _close_log_file(self):
        if self._log_file:
            try:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._log_file.write(self._t("log_footer", time=ts))
                self._log_file.flush()
                self._log_file.close()
            except Exception:
                pass
            self.toast(self._t("log_stopped", path=self._log_file_path))
            self._log_file = None
            self._log_file_path = ""
            self._set_log_path_label("")

    def change_recv_font_size(self, delta):
        new_size = self._recv_font_size + delta
        new_size = max(7, min(28, new_size))
        if new_size == self._recv_font_size:
            return
        self._recv_font_size = new_size
        self.txt_recv.setFont(mono_font(new_size))
        self.toast(self._t("font_size_msg", size=new_size))

    def _on_max_lines_changed(self):
        if not hasattr(self, 'ed_max_lines'):
            return
        try:
            n = int(self.ed_max_lines.text())
        except ValueError:
            n = self.txt_recv.document().maximumBlockCount() or 10000
        n = max(100, min(1_000_000, n))
        self.ed_max_lines.setText(str(n))
        if hasattr(self, 'txt_recv'):
            self.txt_recv.document().setMaximumBlockCount(n)

    # ----- 文件 -----
    def save_recv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self._t("dlg_save_data"),
            f"save_log_{datetime.now():%Y%m%d_%H%M%S}.log",
            self._t("filter_text_save"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt_recv.toPlainText())
            self.toast(self._t("saved_to", path=path))
        except Exception as e:
            self.toast(self._t("err_save_failed", e=e), error=True)

    def load_file_to_send(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._t("dlg_load_file"), "", self._t("filter_all"))
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            if self.sw_tx_hex.isChecked():
                self.txt_send.setPlainText(self._bytes_to_hex(data))
            else:
                # 按选定编码读取（默认 utf-8），lossy 容错避免文件偶有坏字节就报错
                self.txt_send.setPlainText(data.decode(self._send_codec(), errors="replace"))
        except Exception as e:
            self.toast(self._t("err_read_failed", e=e), error=True)

    def clear_recv(self):
        self.txt_recv.clear()
        self._recv_highlight_line = -1
        self.txt_recv.setExtraSelections([])
        self.btn_to_bottom.hide()
        self._reset_stats()
        self._reset_recv_state()

    # ----- 工具 -----
    @staticmethod
    def fmt_bytes(n):
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n/1024:.1f} KB"
        return f"{n/1024/1024:.2f} MB"

    # ----- 收发速率 / 包统计 -----
    def _fmt_rate(self, bps):
        return self.fmt_bytes(int(bps)) + "/s"

    def _tick_rate(self):
        """1Hz 采样：用本秒字节增量近似 B/s，并记录峰值，再刷新状态栏。"""
        self._rx_rate = max(0, self.rx_bytes - self._rx_bytes_mark)
        self._tx_rate = max(0, self.tx_bytes - self._tx_bytes_mark)
        self._rx_bytes_mark = self.rx_bytes
        self._tx_bytes_mark = self.tx_bytes
        if self._rx_rate > self._rx_peak:
            self._rx_peak = self._rx_rate
        if self._tx_rate > self._tx_peak:
            self._tx_peak = self._tx_rate
        self._refresh_stat_labels()

    def _refresh_stat_labels(self, with_tooltip=True):
        """刷新状态栏 RX/TX 统计：字节 · 包数 · 速率（错误 >0 时追加 ⚠）。
        高频收发路径传 with_tooltip=False 跳过 tooltip 重建，tooltip 走 1Hz 采样刷新。"""
        if not hasattr(self, "lbl_rx_stat"):
            return
        unit = self._t("stat_pkt_unit")
        rx = f"RX {self.fmt_bytes(self.rx_bytes)} · {self.rx_packets} {unit} · {self._fmt_rate(self._rx_rate)}"
        if self.rx_errors:
            rx += f" · ⚠{self.rx_errors}"
        tx = f"TX {self.fmt_bytes(self.tx_bytes)} · {self.tx_packets} {unit} · {self._fmt_rate(self._tx_rate)}"
        if self.tx_errors:
            tx += f" · ⚠{self.tx_errors}"
        self.lbl_rx_stat.setText(rx)
        self.lbl_tx_stat.setText(tx)
        if with_tooltip:
            self.lbl_rx_stat.setToolTip(self._stat_tooltip("rx"))
            self.lbl_tx_stat.setToolTip(self._stat_tooltip("tx"))

    def _stat_tooltip(self, direction):
        if direction == "rx":
            head, b, p, r, pk, e = (self._t("stat_tip_rx"), self.rx_bytes,
                                    self.rx_packets, self._rx_rate, self._rx_peak, self.rx_errors)
        else:
            head, b, p, r, pk, e = (self._t("stat_tip_tx"), self.tx_bytes,
                                    self.tx_packets, self._tx_rate, self._tx_peak, self.tx_errors)
        total = self.fmt_bytes(b) + (f" ({b:,} B)" if b >= 1024 else "")
        return "\n".join([
            head,
            f"{self._t('stat_total')}: {total}",
            f"{self._t('stat_packets')}: {p:,}",
            f"{self._t('stat_rate')}: {self._fmt_rate(r)}",
            f"{self._t('stat_peak')}: {self._fmt_rate(pk)}",
            f"{self._t('stat_errors')}: {e:,}",
        ])

    def _reset_stats(self):
        """清零收发统计（字节/包/错误/速率/峰值），不动数据区内容。"""
        self.rx_bytes = self.tx_bytes = 0
        self.rx_packets = self.tx_packets = 0
        self.rx_errors = self.tx_errors = 0
        self._rx_rate = self._tx_rate = 0
        self._rx_peak = self._tx_peak = 0
        self._rx_bytes_mark = self._tx_bytes_mark = 0
        self._refresh_stat_labels()

    def _stat_context_menu(self, pos):
        """状态栏右键：重置统计（文字跟随语言、配色跟随主题）。"""
        menu = QMenu(self.status_bar)
        c = chrome_for(self._theme_id())
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['card_bg']}; color: {c['text']};
                     border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
            QMenu::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
        """)
        act_reset = menu.addAction(self._t("stat_reset"))
        chosen = menu.exec_(self.status_bar.mapToGlobal(pos))
        menu.deleteLater()   # 每次右键新建、挂在 status_bar 下；exec_ 后主动回收，避免累积为常驻子对象
        if chosen is act_reset:
            self._reset_stats()

    def toast(self, msg, error=False):
        if error:
            self.status_bar.showMessage("⚠ " + msg, 3500)
        else:
            self.status_bar.showMessage("✓ " + msg, 2500)

    # ----- 多语言 -----
    def _set_language(self, lang: str):
        if lang not in TR or lang == self._lang:
            return
        self._lang = lang
        self._L = TR[lang]
        self.settings.setValue("language", lang)
        self.settings.sync()
        self._apply_language()

    def _apply_language(self):
        self.setWindowTitle(self._t("app_title"))
        if hasattr(self, "title_bar"):
            self.title_bar.set_title(self._t("app_title"))

        for w in self.findChildren(QWidget):
            k = w.property("tr_text")
            if k:
                try:
                    w.setText(self._t(k))
                except Exception:
                    pass
            k = w.property("tr_placeholder")
            if k:
                try:
                    w.setPlaceholderText(self._t(k))
                except Exception:
                    pass
            k = w.property("tr_tooltip")
            if k:
                try:
                    w.setToolTip(self._t(k))
                except Exception:
                    pass
            # 固定宽标签（网络设置左列）随语言调整列宽，避免英文被遮挡
            if w.property("tr_fixedw"):
                w.setFixedWidth(self._label_col_width())

        self._apply_theme_label_styles()
        self._update_legend_label()

        if hasattr(self, "cb_checksum"):
            idx = self.cb_checksum.currentIndex()
            self.cb_checksum.blockSignals(True)
            self.cb_checksum.clear()
            for ck_key in CHECKSUM_KEYS:
                self.cb_checksum.addItem(self._t(ck_key))
            if 0 <= idx < self.cb_checksum.count():
                self.cb_checksum.setCurrentIndex(idx)
            self.cb_checksum.blockSignals(False)

        if hasattr(self, "cb_line_nl"):
            self.cb_line_nl.setItemText(0, self._t("nl_auto"))

        if hasattr(self, "cb_encoding"):
            self.cb_encoding.setItemText(0, self._t("encoding_auto"))

        # 主题下拉的 9 项也跟着语言切换
        if hasattr(self, "cb_theme"):
            self.cb_theme.blockSignals(True)
            for i in range(self.cb_theme.count()):
                tid = self.cb_theme.itemData(i)
                if tid:
                    self.cb_theme.setItemText(i, self._theme_label(tid))
            self.cb_theme.blockSignals(False)

        # 网络设置区：动作按钮文案随协议/状态、字段行随协议显隐重算
        if hasattr(self, "cb_proto"):
            self._update_net_fields()

        # 状态栏连接文本随语言刷新
        if hasattr(self, "lbl_state"):
            if self.conn is not None:
                self._update_conn_status()
            else:
                self.lbl_state.setText(self._t("state_closed"))

        # 状态栏 RX/TX 统计的包单位 + tooltip 随语言刷新
        self._refresh_stat_labels()

        # 「目标」下拉里的「全部」项随语言刷新
        if hasattr(self, "cb_target") and self.cb_target.count() > 0:
            self.cb_target.setItemText(0, self._t("client_all"))

        if self._tray:
            self._tray.setToolTip(self._t("app_title"))
            if hasattr(self, "_tray_show_action"):
                self._tray_show_action.setText(self._t("tray_show"))
            if hasattr(self, "_tray_about_action"):
                self._tray_about_action.setText(self._t("about"))
            if hasattr(self, "_tray_quit_action"):
                self._tray_quit_action.setText(self._t("tray_quit"))

        # 数据区分组下拉的「（关闭）」项随语言变
        if hasattr(self, "cb_kw_group"):
            self._rebuild_kw_group_combo()
        # 日志分包下拉的「不分包」项随语言变
        if hasattr(self, "cb_log_split"):
            self.cb_log_split.blockSignals(True)
            self.cb_log_split.setItemText(0, self._t("log_split_none"))
            self.cb_log_split.blockSignals(False)
        # 多条发送循环按钮文字随语言变
        if hasattr(self, "btn_ms_cycle"):
            self._set_ms_cycle_btn(self._ms_cycle_timer.isActive())
        # 多条发送/关键字高亮弹窗若开着也跟着切语言
        if getattr(self, "_multi_send_dlg", None) is not None:
            self._multi_send_dlg.retranslate()
        if getattr(self, "_keyword_dlg", None) is not None:
            self._keyword_dlg.retranslate()

    # ----- 持久化 -----
    @staticmethod
    def _settings_file() -> str:
        """
        优先 exe 同级目录（绿色版/U 盘携带特性），写不动就回退 %APPDATA%\\CommTool\\。
        场景：用户装到 Program Files（安装时选"为所有用户"），普通用户运行无写权限。
        macOS：不走绿色版逻辑（绝不写进 .app 包内 —— 会破坏签名、重装即丢），
        固定用 ~/Library/Application Support/CommTool/。
        """
        if sys.platform == "darwin":
            cfg_dir = os.path.join(
                os.path.expanduser("~/Library/Application Support"), "CommTool")
            new_ini = os.path.join(cfg_dir, "settings.ini")
            # 向后兼容：早期 Mac 版曾回退到 ~/CommTool/，已有则沿用，避免设置丢失。
            legacy = os.path.join(os.path.expanduser("~"), "CommTool", "settings.ini")
            if not os.path.exists(new_ini) and os.path.exists(legacy):
                return legacy
            try:
                os.makedirs(cfg_dir, exist_ok=True)
            except Exception:
                pass
            return new_ini

        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))

        portable = os.path.join(base, "settings.ini")

        # 判定 portable 路径可不可用：
        # - 文件已存在 → 测试能否打开追加写（覆盖只读文件场景）
        # - 文件不存在 → 在目录里试写一个临时文件
        def _portable_writable():
            if os.path.exists(portable):
                try:
                    with open(portable, "a"):
                        pass
                    return True
                except (OSError, PermissionError):
                    return False
            test = os.path.join(base, ".write_test")
            try:
                with open(test, "w"):
                    pass
            except (OSError, PermissionError):
                return False
            # 写成功 = 目录可写；删测试文件是 best-effort，删不掉(杀软锁等)也不该误判为不可写
            try:
                os.remove(test)
            except OSError:
                pass
            return True

        if _portable_writable():
            return portable

        # 回退用户配置目录
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        cfg_dir = os.path.join(appdata, "CommTool")
        new_ini = os.path.join(cfg_dir, "settings.ini")
        # 向后兼容：旧版 NetworkTool 的配置在 %APPDATA%\NetworkTool\。新目录尚无配置、
        # 旧目录已有 → 继续沿用旧文件，避免改名后老用户设置全部丢失（读写都走旧路径）。
        old_ini = os.path.join(appdata, "NetworkTool", "settings.ini")
        if not os.path.exists(new_ini) and os.path.exists(old_ini):
            return old_ini
        try:
            os.makedirs(cfg_dir, exist_ok=True)
        except Exception:
            pass
        return new_ini

    def _save_settings(self):
        try:
            s = self.settings
            s.setValue("geometry", self.saveGeometry())
            s.setValue("h_splitter", self.h_splitter.saveState())
            s.setValue("recv_font_size", self._recv_font_size)
            s.setValue("rx_hex", self.sw_rx_hex.isChecked())
            s.setValue("wrap", self.sw_wrap.isChecked())
            s.setValue("show_timestamp", self.sw_show_timestamp.isChecked())
            s.setValue("packet_split", self.sw_packet_split.isChecked())
            s.setValue("line_split", self.sw_line_split.isChecked())
            s.setValue("line_nl_mode", self.cb_line_nl.currentIndex())
            s.setValue("encoding", self.cb_encoding.currentData())
            s.setValue("theme", self.cb_theme.currentData())
            s.setValue("packet_timeout", self.ed_packet_timeout.text())
            s.setValue("max_lines", self.ed_max_lines.text())
            s.setValue("filter_highlight", self.btn_filter_hl.isChecked())
            s.setValue("log_split", self.cb_log_split.currentText())
            s.setValue("tx_hex", self.sw_tx_hex.isChecked())
            s.setValue("append_newline", self.sw_append_newline.isChecked())
            s.setValue("append_nl_mode", self.cb_append_nl.currentIndex())
            s.setValue("period_ms", self.ed_period_ms.text())
            s.setValue("checksum_idx", self.cb_checksum.currentIndex())
            s.setValue("send_text", self.txt_send.toPlainText())
            s.setValue("net_proto", self.cb_proto.currentText())
            s.setValue("net_local_ip", self.cb_local_ip.currentText())
            s.setValue("net_local_port", self.ed_local_port.text())
            s.setValue("net_remote_ip", self.ed_remote_ip.text())
            s.setValue("net_remote_port", self.ed_remote_port.text())
            s.setValue("net_use_remote", self.sw_udp_remote.isChecked())
            s.setValue("net_group_addr", self.ed_group.text())
            # 串口设置
            s.setValue("ser_port", self.cb_port.currentData() or "")
            s.setValue("ser_baud", self.cb_baud.currentText())
            s.setValue("ser_databits", self.cb_databits.currentText())
            s.setValue("ser_parity", self.cb_parity.currentText())
            s.setValue("ser_stopbits", self.cb_stopbits.currentText())
            s.sync()
        except Exception:
            pass

    def _load_settings(self):
        s = self.settings

        def to_bool(v, default=False):
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.lower() in ("true", "1", "yes")
            return default

        def restore_combo(combo, key):
            v = s.value(key, None)
            if v is None or v == "":
                return
            v = str(v)
            idx = combo.findText(v)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif combo.isEditable():
                combo.setEditText(v)

        try:
            geo = s.value("geometry")
            if geo:
                self.restoreGeometry(geo)
            h_state = s.value("h_splitter")
            if h_state:
                self.h_splitter.restoreState(h_state)
        except Exception:
            pass

        try:
            size = int(s.value("recv_font_size", 10))
            self._recv_font_size = max(7, min(28, size))
            self.txt_recv.setFont(mono_font(self._recv_font_size))
        except (ValueError, TypeError):
            pass

        legacy_ts = s.value("timestamp", None)
        show_ts_raw = s.value("show_timestamp", legacy_ts if legacy_ts is not None else False)
        pkt_split_raw = s.value("packet_split", False)   # 不继承旧 timestamp 键：分包与时间戳互相独立，老用户升级不该被强制开分包
        self.sw_rx_hex.setChecked(to_bool(s.value("rx_hex", False)), animate=False)
        self.sw_wrap.setChecked(to_bool(s.value("wrap", True)), animate=False)
        self.sw_show_timestamp.setChecked(to_bool(show_ts_raw), animate=False)
        self.sw_packet_split.setChecked(to_bool(pkt_split_raw), animate=False)
        self.sw_line_split.setChecked(to_bool(s.value("line_split", False)), animate=False)
        self.btn_filter_hl.blockSignals(True)
        self.btn_filter_hl.setChecked(to_bool(s.value("filter_highlight", False)))
        self.btn_filter_hl.blockSignals(False)
        log_split = s.value("log_split", "")
        if log_split:
            self.cb_log_split.setCurrentText(str(log_split))
        try:
            nl_idx = int(s.value("line_nl_mode", 0))
            if 0 <= nl_idx < self.cb_line_nl.count():
                self.cb_line_nl.setCurrentIndex(nl_idx)
        except (ValueError, TypeError):
            pass
        # 字符编码 — 按 codec name 查 itemData 找回上次选项
        enc_saved = s.value("encoding", "auto") or "auto"
        for i in range(self.cb_encoding.count()):
            if self.cb_encoding.itemData(i) == enc_saved:
                self.cb_encoding.setCurrentIndex(i)
                break
        # 触发一次 _on_encoding_changed 初始化增量解码器
        self._on_encoding_changed()

        # 主题 — 按 theme_id 查 itemData
        theme_saved = s.value("theme", THEME_DEFAULT) or THEME_DEFAULT
        # 静默切到目标 idx — 不让 setCurrentIndex 在 __init__ 阶段触发 _on_theme_changed
        # （此时 widget 还没完成首次 show，Qt setStyleSheet 不会完全 propagate 到子组件）
        self.cb_theme.blockSignals(True)
        for i in range(self.cb_theme.count()):
            if self.cb_theme.itemData(i) == theme_saved:
                self.cb_theme.setCurrentIndex(i)
                break
        self.cb_theme.blockSignals(False)
        # 推迟到 event loop 启动后再应用 — 此时所有 widget 已 show，setStyleSheet 全部生效
        QTimer.singleShot(0, self._on_theme_changed)
        self.sw_tx_hex.setChecked(to_bool(s.value("tx_hex", False)), animate=False)
        self.sw_append_newline.setChecked(to_bool(s.value("append_newline", False)), animate=False)
        try:
            nl_idx = int(s.value("append_nl_mode", 0))
            if 0 <= nl_idx < self.cb_append_nl.count():
                self.cb_append_nl.setCurrentIndex(nl_idx)
        except (ValueError, TypeError):
            pass
        self.on_wrap_toggled(self.sw_wrap.isChecked())

        v = s.value("packet_timeout")
        if v:
            self.ed_packet_timeout.setText(str(v))
        v = s.value("max_lines")
        if v:
            self.ed_max_lines.setText(str(v))
            self._on_max_lines_changed()
        v = s.value("period_ms")
        if v:
            self.ed_period_ms.setText(str(v))
        v = s.value("send_text")
        if v:
            self.txt_send.setPlainText(str(v))

        try:
            ck_idx = int(s.value("checksum_idx", 0))
            if 0 <= ck_idx < self.cb_checksum.count():
                self.cb_checksum.setCurrentIndex(ck_idx)
        except (ValueError, TypeError):
            pass
        # 连接设置恢复（类型下拉含串口+网络协议）
        restore_combo(self.cb_proto, "net_proto")
        v = s.value("net_local_ip", None)
        if v:
            self.cb_local_ip.setCurrentText(str(v))
        v = s.value("net_local_port", None)
        if v:
            self.ed_local_port.setText(str(v))
        v = s.value("net_remote_ip", None)
        if v:
            self.ed_remote_ip.setText(str(v))
        v = s.value("net_remote_port", None)
        if v:
            self.ed_remote_port.setText(str(v))
        self.sw_udp_remote.setChecked(to_bool(s.value("net_use_remote", False)), animate=False)
        v = s.value("net_group_addr", None)
        if v:
            self.ed_group.setText(str(v))
        # 串口设置恢复
        restore_combo(self.cb_baud, "ser_baud")
        restore_combo(self.cb_databits, "ser_databits")
        restore_combo(self.cb_parity, "ser_parity")
        restore_combo(self.cb_stopbits, "ser_stopbits")
        # cb_port 由后台扫描异步填充，此刻多半还空 → 记下待恢复端口，
        # 首次扫描结果到达时(_on_port_scan_complete)再按设备名选回上次端口。
        self._pending_restore_port = (s.value("ser_port", "") or None)
        self._update_net_fields()   # 按恢复的类型+开关刷新字段显隐/启用 + 按钮文案

    # ----- 系统托盘 -----
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(get_app_icon(), self)
        self._tray.setToolTip(self._t("app_title"))

        menu = QMenu()
        self._tray_show_action = menu.addAction(self._t("tray_show"))
        self._tray_show_action.triggered.connect(self._show_from_tray)
        self._tray_about_action = menu.addAction(self._t("about"))
        self._tray_about_action.triggered.connect(self.open_about)
        menu.addSeparator()
        self._tray_quit_action = menu.addAction(self._t("tray_quit"))
        self._tray_quit_action.triggered.connect(self._real_quit)
        self._tray.setContextMenu(menu)

        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            # 点托盘图标 toggle：窗口正显示就缩小到托盘，已隐藏/最小化就恢复
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _real_quit(self):
        self._closing_real = True
        self.close()

    def open_about(self):
        """打开「关于 + 检查更新」对话框（托盘菜单触发）。"""
        dlg = AboutDialog(
            tr=self._t,
            app_name=self._t("app_title"),
            version=APP_VERSION,
            icon=get_app_icon(),
            theme_id=self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT,
            on_quit=self._real_quit,
            parent=self,
        )
        dlg.exec_()

    def showEvent(self, event):
        super().showEvent(event)
        # 第一次显示后做一次：把右侧发送区卡片的高度上限设为左侧发送区卡片的实际高度
        # 这样右侧发送区不会因为 QTextEdit 的 Expanding 策略吃掉过多空间，顶底都和左侧对齐
        if not getattr(self, "_height_synced", False):
            self._height_synced = True
            QTimer.singleShot(0, self._sync_right_send_height)
        # 跨显示器后状态栏等透明区域不重绘的修复：监听屏幕切换（只连一次）
        if not getattr(self, "_screen_sig_connected", False):
            wh = self.windowHandle()
            if wh is not None:
                wh.screenChanged.connect(self._on_screen_changed)
                self._screen_sig_connected = True
        # 无边框窗口默认丢了 WS_MINIMIZEBOX 样式，任务栏图标 / Aero 无法最小化；
        # 用 Windows API 把最小化 + 最大化框样式加回去（只做一次）。
        if sys.platform == "win32" and not getattr(self, "_minbox_set", False):
            self._minbox_set = True
            try:
                import ctypes
                hwnd = int(self.winId())
                GWL_STYLE = -16
                WS_MINIMIZEBOX = 0x00020000
                WS_MAXIMIZEBOX = 0x00010000
                cur = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                ctypes.windll.user32.SetWindowLongW(
                    hwnd, GWL_STYLE, cur | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
            except Exception:
                pass

    def _on_screen_changed(self, _screen):
        # 窗口移到另一个显示器后强制重绘（含底部透明状态栏），
        # 修复多屏 backing store 不刷新导致状态栏显示空白的问题。
        self.repaint()
        if hasattr(self, "status_bar"):
            self.status_bar.repaint()

    def _sync_right_send_height(self):
        try:
            if hasattr(self, "_left_send_card") and hasattr(self, "_right_send_card"):
                h = self._left_send_card.height()
                # 上限取「左侧高度」与「右侧内容最小高度」的较大值：
                # 否则左侧卡片变矮(字号/间距缩小)时，会把内容更多的右侧(含多条发送快捷栏)压到重叠
                need = self._right_send_card.minimumSizeHint().height()
                if h > 60:
                    self._right_send_card.setMaximumHeight(max(h, need))
        except Exception:
            pass

    def changeEvent(self, e):
        if e.type() == e.WindowStateChange and hasattr(self, "title_bar"):
            self.title_bar.update_max_icon()
            # 最大化/还原后底部透明状态栏可能不重绘（尤其副屏），延迟一拍强制刷新
            if hasattr(self, "status_bar"):
                QTimer.singleShot(0, self.status_bar.repaint)
        super().changeEvent(e)

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0024:  # WM_GETMINMAXINFO
                    # 无边框窗口最大化时限制到当前显示器的「工作区」，否则会覆盖任务栏 /
                    # 超出屏幕底部，导致状态栏被挤出看不到（尤其副屏没有任务栏时整屏覆盖）。
                    class _PT(ctypes.Structure):
                        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

                    class _RC(ctypes.Structure):
                        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                                    ("r", ctypes.c_long), ("b", ctypes.c_long)]

                    class _MI(ctypes.Structure):
                        _fields_ = [("cb", ctypes.c_ulong), ("rcMon", _RC),
                                    ("rcWork", _RC), ("flags", ctypes.c_ulong)]

                    class _MMI(ctypes.Structure):
                        _fields_ = [("ptRes", _PT), ("ptMaxSize", _PT), ("ptMaxPos", _PT),
                                    ("ptMinTrack", _PT), ("ptMaxTrack", _PT)]

                    hmon = ctypes.windll.user32.MonitorFromWindow(int(self.winId()), 2)
                    if hmon:
                        mi = _MI()
                        mi.cb = ctypes.sizeof(_MI)
                        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
                        w = mi.rcWork
                        mon = mi.rcMon
                        mmi = _MMI.from_address(int(msg.lParam))
                        mmi.ptMaxPos.x = w.l - mon.l       # 最大化位置（相对显示器左上）
                        mmi.ptMaxPos.y = w.t - mon.t
                        mmi.ptMaxSize.x = w.r - w.l        # 最大化尺寸 = 工作区尺寸
                        mmi.ptMaxSize.y = w.b - w.t
                        mmi.ptMaxTrack.x = w.r - w.l
                        mmi.ptMaxTrack.y = w.b - w.t
                    return True, 0
                if msg.message == 0x0084:  # WM_NCHITTEST
                    lparam = msg.lParam
                    x = ctypes.c_short(lparam & 0xFFFF).value
                    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                    # lParam 是物理像素；开 HiDPI 缩放后 Qt 用逻辑像素，需按设备像素比换算，
                    # 否则缩放热区与实际边缘错位、拖不动窗口
                    dpr = self.devicePixelRatioF() or 1.0
                    pt = self.mapFromGlobal(QPoint(int(x / dpr), int(y / dpr)))
                    if self.isMaximized():
                        return False, 0
                    m = self.RESIZE_MARGIN
                    on_left = pt.x() < m
                    on_right = pt.x() >= self.width() - m
                    on_top = pt.y() < m
                    on_bottom = pt.y() >= self.height() - m
                    if on_top and on_left:
                        return True, 13
                    if on_top and on_right:
                        return True, 14
                    if on_bottom and on_left:
                        return True, 16
                    if on_bottom and on_right:
                        return True, 17
                    if on_left:
                        return True, 10
                    if on_right:
                        return True, 11
                    if on_top:
                        return True, 12
                    if on_bottom:
                        return True, 15
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    # ----- 无边框窗口缩放（macOS / Linux：手动实现，不依赖 startSystemResize）-----
    def _edges_at(self, pos):
        """鼠标点相对窗口的边缘命中，返回 Qt.Edges（无命中则为 0）。"""
        m = self.RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        edges = Qt.Edges()
        if x <= m:
            edges |= Qt.LeftEdge
        elif x >= w - m:
            edges |= Qt.RightEdge
        if y <= m:
            edges |= Qt.TopEdge
        elif y >= h - m:
            edges |= Qt.BottomEdge
        return edges

    def _resize_cursor(self, edges):
        """命中边缘对应的缩放光标（仅在拖拽期间用 grabMouse 设置）。"""
        if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            return Qt.SizeFDiagCursor
        if edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            return Qt.SizeBDiagCursor
        if edges & (Qt.LeftEdge | Qt.RightEdge):
            return Qt.SizeHorCursor
        if edges & (Qt.TopEdge | Qt.BottomEdge):
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def _perform_resize(self, gpos):
        """按拖拽位移调整窗口几何，遵守最小尺寸。"""
        g = QRect(self._resize_start_geo)
        dx = gpos.x() - self._resize_start_mouse.x()
        dy = gpos.y() - self._resize_start_mouse.y()
        minw, minh = self.minimumWidth(), self.minimumHeight()
        e = self._resize_edges
        if e & Qt.LeftEdge:
            g.setLeft(min(g.left() + dx, g.right() - minw + 1))
        elif e & Qt.RightEdge:
            g.setRight(max(g.right() + dx, g.left() + minw - 1))
        if e & Qt.TopEdge:
            g.setTop(min(g.top() + dy, g.bottom() - minh + 1))
        elif e & Qt.BottomEdge:
            g.setBottom(max(g.bottom() + dy, g.top() + minh - 1))
        self.setGeometry(g)

    def _end_resize(self):
        """结束缩放：清状态、释放鼠标、还原覆盖光标。"""
        self._resize_edges = Qt.Edges()
        self.releaseMouse()
        QApplication.restoreOverrideCursor()

    def _update_hover_cursor(self, edges):
        """悬停边缘时设置/复位缩放光标（带状态去抖，避免反复 set/unset）。"""
        shape = self._resize_cursor(edges) if edges else None
        if shape == self._hover_cursor_shape:
            return
        self._hover_cursor_shape = shape
        if shape is not None:
            self.setCursor(shape)
        else:
            self.unsetCursor()

    def leaveEvent(self, e):
        # 鼠标离开窗口 → 复位悬停缩放光标；缩放进行中不动，避免拖拽时光标被清成箭头
        if not self._resize_edges and self._hover_cursor_shape is not None:
            self._hover_cursor_shape = None
            self.unsetCursor()
        super().leaveEvent(e)

    def _shutdown(self):
        """退出前统一清理。closeEvent 的两条退出路径（直接退出 / 选「退出」）共用：
        以前两段逐行复制，加清理步骤极易漏改其中一条导致线程/定时器泄漏，故抽成一处。"""
        if hasattr(self, "_ms_cycle_timer"):
            self._ms_cycle_timer.stop()   # 先停循环定时器，避免销毁中触发 toast
        if hasattr(self, "_rate_timer"):
            self._rate_timer.stop()       # 同停 1Hz 统计采样：避免 accept 后、窗口析构前残余 tick 去 setText 已销毁的标签
        self._save_settings()
        self.close_conn()
        self._close_log_file()
        if self.port_scanner:
            self.port_scanner.stop()
        self._wait_oneshot_scan()
        if self._tooltip_popup is not None:   # macOS 自绘 tooltip 是独立顶层窗，主动收掉避免退出瞬间残留屏上
            self._tooltip_popup.hide()
            self._tooltip_popup.deleteLater()
            self._tooltip_popup = None
        if self._tray:
            self._tray.hide()

    def closeEvent(self, e):
        if self._closing_real or not self._tray:
            self._shutdown()
            e.accept()
            return

        dlg = CloseDialog(
            self._t("close_prompt"),
            self._t("close_minimize"),
            self._t("close_quit"),
            self._t("close_cancel"),
            theme_id=self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT,
            parent=self,
        )
        dlg.exec_()
        choice = dlg.result_value()

        if choice == CloseDialog.RESULT_MIN:
            e.ignore()
            self.hide()
            self._tray.showMessage(
                self._t("app_title"),
                self._t("tray_minimized", app=self._t("app_title")),
                QSystemTrayIcon.Information,
                2000
            )
        elif choice == CloseDialog.RESULT_QUIT:
            self._closing_real = True
            self._shutdown()
            e.accept()
        else:
            e.ignore()

