# -*- coding: utf-8 -*-
"""数据波形图对话框 PlotDialog（基于 pyqtgraph）。

从 RX 数据解析数值，实时绘多通道滚动曲线。与显示区**解耦**：自持缓冲，feed(bytes)
→ 解析 → 各通道环形缓冲；由独立 ~30FPS 定时器统一重绘（不随收包频率），高吞吐不卡 GUI。

四种解析模式：
- 分隔符：每行按 逗号/空白/Tab/分号/自动 拆，每列一条曲线（ASCII 数字流，如 "1.2,3.4"）
- 正则：每行用正则，每个捕获组一条曲线（如 temp=(\\d+).*hum=(\\d+)）
- HEX 字节：**二进制协议**用——按 binproto 的「帧头 + 偏移:类型」从字节里取数值，每字段一条曲线
  （字段定义与帧解析表 frame_dialog 共用 binproto，语义一致）
- DLOG：rtt_t2 风格的 TAG=DLOG M*n(x,y,z) 文本协议，零配置只解析 DLOG 行（RTT 调波常用）

单实例非模态，复用时刷新主题/语言。pyqtgraph 为可选依赖，main_window 懒导入 + try/except。
"""
import logging
import re
import time
import csv
from collections import deque

import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
                             QComboBox, QLineEdit, QPushButton, QCheckBox,
                             QScrollArea, QFrame, QFileDialog)

from protocol import binproto
from record import plot_stats
from ui.theme import chrome_for
from ui.fonts import localize_qss
from ui.ui_tips import set_tooltip
from ui.dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups

_log = logging.getLogger("commtool.plot")

pg.setConfigOptions(antialias=True)

# 通道配色循环（iOS 风格高饱和；通道数超出则取模复用）
_CH_COLORS = ["#FF453A", "#32D74B", "#0A84FF", "#FF9F0A", "#BF5AF2",
              "#5AC8FA", "#FFD60A", "#FF2D55", "#30D158", "#64D2FF",
              "#AC8E68", "#8E8E93"]

# 滚动窗口可选点数
_MAXPTS = [200, 500, 1000, 2000, 5000]

# 分隔符下拉各项对应的「拆分正则」
_SEP_RX = [r",", r"\s+", r"\t", r";", r"[,\s;]+"]

# 模式索引
_MODE_DELIM, _MODE_REGEX, _MODE_HEX, _MODE_DLOG = 0, 1, 2, 3
_VIEW_WAVE, _VIEW_XY, _VIEW_HIST = 0, 1, 2
_IO_GRAPH_TAGS = ("rx_Bps", "tx_Bps", "rx_pps", "tx_pps")
_NO_JUMP_TAGS = frozenset(_IO_GRAPH_TAGS)

# rtt_t2 波形协议行：TAG=DLOG [SN(n)]M*n(x,y,z)。n 是小数位数，
# 括号里的整数需除以 10**n；TAG 前可带 BDSCOL 颜色标签等日志前缀。
_DLOG_RX = re.compile(
    r"tag=dlog(?:\s+sn\s*\([^)]*\))?\s*m\*(\d+)\s*\(([^)]*)\)",
    re.IGNORECASE)


class PlotDialog(QDialog):
    def __init__(self, app):
        # parent=None：避免干扰主窗 WM_NCHITTEST（同 AutoReplyDialog/MultiSendDialog）。
        # 主窗 _shutdown 显式收。
        super().__init__(None)
        self.app = app
        # 独立窗口 + 最小化/最大化/关闭按钮；原生边框可拖动移动 + 拖边缩放
        # （波形是数据视图，常需放大/最大化看细节）
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(640, 380)
        self.resize(880, 540)

        self._paused = False
        self._decode_buf = ""        # 文本模式：跨包未成行的残段
        self._max_points = 1000
        self._x_time = False         # X 轴：False=样本序号，True=时间(s)
        self._sample_idx = 0
        self._t0 = None              # 时间轴起点（time.monotonic）
        self._regex = None           # 已编译的正则（正则模式）
        self._hex_fields = []        # HEX 模式字段：[(name, offset, typ), ...]
        self._hex_header = b""       # HEX 模式帧头过滤（空=每包一帧、不过滤）
        self._hex_header_valid = True
        self._loading_cfg = False     # 恢复配置时屏蔽下拉框信号触发的回写
        self._channels = []          # [{name, xs(deque), ys(deque), curve, color, cb}]
        self._pos_to_idx = {}        # 文本/帧解析：逻辑位置 → _channels 中的实际下标
        self._name_to_idx = {}       # 寄存器联动：tag → 通道下标（按名而非位置定位）
        self._io_graph_mode = False
        self._io_graph_restore = None
        self._right_vb = None          # dual-Y secondary ViewBox (lazy)
        self._hist_item = None         # BarGraphItem for histogram mode
        self._hist_scale = None        # x normalization scale for extreme histograms
        self._v_line = None
        self._h_line = None
        self._last_cursor = (0.0, 0.0)
        self._cursor_stats_fp = None   # cache key for channel stats text
        self._cursor_stats_extra = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ===== 顶部工具条 =====
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.lbl_mode = QLabel()
        self.cb_mode = QComboBox()           # 0=分隔符 1=正则 2=HEX字节 3=DLOG
        self.cb_mode.addItems(["", "", "", ""])
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cb_sep = QComboBox()            # 分隔符（5 项，仅分隔符模式）
        self.cb_sep.addItems(["", "", "", "", ""])
        self.cb_sep.currentIndexChanged.connect(self._on_sep_changed)
        self.ed_regex = QLineEdit()          # 仅正则模式
        self.ed_regex.editingFinished.connect(self._on_regex_changed)
        self.ed_header = QLineEdit()         # 仅 HEX 字节模式：帧头过滤（hex，可空）
        self.ed_header.setMaximumWidth(120)
        self.ed_header.editingFinished.connect(self._on_header_changed)
        self.ed_fields = QLineEdit()         # 仅 HEX 字节模式：字段定义
        set_tooltip(self.ed_fields, binproto.NUM_TYPES_TIP)
        self.ed_fields.editingFinished.connect(self._on_fields_changed)
        self.lbl_win = QLabel()
        self.cb_maxpts = QComboBox()
        for n in _MAXPTS:
            self.cb_maxpts.addItem(str(n), n)
        self.cb_maxpts.currentIndexChanged.connect(self._on_maxpts_changed)
        self.lbl_x = QLabel()
        self.cb_xaxis = QComboBox()          # 0=样本序号 1=时间
        self.cb_xaxis.addItems(["", ""])
        self.cb_xaxis.currentIndexChanged.connect(self._on_xaxis_changed)
        self.lbl_view = QLabel()
        self.cb_view = QComboBox()           # 0=波形 1=XY 2=直方图
        self.cb_view.setObjectName("plot_view")
        self.cb_view.addItems(["", "", ""])
        self.cb_view.currentIndexChanged.connect(self._on_view_changed)
        self.cb_dual_y = QCheckBox()
        self.cb_dual_y.setObjectName("plot_dual_y")
        self.cb_dual_y.toggled.connect(self._on_dual_y_changed)

        self.btn_pause = QPushButton()
        self.btn_pause.setObjectName("PlotGhostBtn")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("PlotGhostBtn")
        self.btn_clear.clicked.connect(self._clear)
        self.btn_export = QPushButton()
        self.btn_export.setObjectName("PlotGhostBtn")
        self.btn_export.clicked.connect(self._export_csv)
        # 使用说明：右上角 26×26 「?」icon button，弹独立窗口（与帧解析/自动应答同形制）
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("PlotHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help_dlg)

        bar.addWidget(self.lbl_mode)
        bar.addWidget(self.cb_mode)
        bar.addWidget(self.cb_sep)
        bar.addWidget(self.ed_regex, 1)
        bar.addWidget(self.ed_header)
        bar.addWidget(self.ed_fields, 1)
        bar.addWidget(self.lbl_win)
        bar.addWidget(self.cb_maxpts)
        bar.addWidget(self.lbl_x)
        bar.addWidget(self.cb_xaxis)
        bar.addWidget(self.lbl_view)
        bar.addWidget(self.cb_view)
        bar.addWidget(self.cb_dual_y)
        bar.addSpacing(8)
        bar.addWidget(self.btn_pause)
        bar.addWidget(self.btn_clear)
        bar.addWidget(self.btn_export)
        bar.addWidget(self.btn_help)
        root.addLayout(bar)

        # ===== 绘图区 =====
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setClipToView(True)        # 只绘可视范围，长曲线更省
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.getAxis("bottom").enableAutoSIPrefix(False)  # 样本序号不该被缩成 (x0.001)
        root.addWidget(self.plot, 1)
        self.plot.scene().sigMouseClicked.connect(self._on_plot_clicked)
        self._init_cursor()

        # ===== 通道勾选条（横向滚动）=====
        self._ch_bar = QWidget()
        self._ch_h = QHBoxLayout(self._ch_bar)
        self._ch_h.setContentsMargins(2, 0, 2, 0)
        self._ch_h.setSpacing(12)
        self._ch_h.addStretch(1)
        self._ch_bar.setAutoFillBackground(False)
        ch_scroll = QScrollArea()
        ch_scroll.setObjectName("PlotChScroll")
        ch_scroll.setWidget(self._ch_bar)
        ch_scroll.setWidgetResizable(True)
        ch_scroll.setFrameShape(QFrame.NoFrame)
        ch_scroll.setFixedHeight(38)
        ch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        ch_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ch_scroll.viewport().setAutoFillBackground(False)
        root.addWidget(ch_scroll)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("MsHint")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)
        self.lbl_cursor = QLabel()
        self.lbl_cursor.setObjectName("MsHint")
        self.lbl_cursor.setWordWrap(True)
        root.addWidget(self.lbl_cursor)

        # 重绘定时器（随显示启停，见 show/hideEvent）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._redraw)

        self.retranslate()      # 先填充下拉文案
        self._load_cfg()        # 再按存档恢复选择
        self.refresh_theme()

    # ---------------- 配置持久化 ----------------
    def _load_cfg(self):
        s = self.app.settings
        self._loading_cfg = True
        try:
            self.cb_mode.setCurrentIndex(_to_int(s.value("plot_mode", 0), 0, 3))
            self.cb_sep.setCurrentIndex(_to_int(s.value("plot_sep", 0), 0, 4))
            self.ed_regex.setText(s.value("plot_regex", "") or "")
            self._on_regex_changed(save=False)
            self.ed_fields.setText(s.value("plot_hex_fields", "") or "")
            self._on_fields_changed(save=False)
            self.ed_header.setText(s.value("plot_hex_header", "") or "")
            self._on_header_changed(save=False)
            mp = _to_int(s.value("plot_maxpts", 1000), 1, 10 ** 9)
            i = self.cb_maxpts.findData(mp)
            self.cb_maxpts.setCurrentIndex(i if i >= 0 else _MAXPTS.index(1000))
            self._max_points = self.cb_maxpts.currentData()
            self.cb_xaxis.setCurrentIndex(_to_int(s.value("plot_xaxis", 0), 0, 1))
            self._x_time = self.cb_xaxis.currentIndex() == 1
            self.cb_view.setCurrentIndex(_to_int(s.value("plot_view", 0), 0, 2))
            dual = s.value("plot_dual_y", False)
            if isinstance(dual, str):
                dual = dual.lower() in ("1", "true", "yes")
            self.cb_dual_y.setChecked(bool(dual))
            self._on_mode_changed(save=False)
            self._ensure_dual_y(self.cb_dual_y.isChecked())
        finally:
            self._loading_cfg = False

    def reload_cfg(self):
        """配置导入后调用：先清掉所有曲线数据 + 通道，再按新设置重建。
        否则旧解析模式/字段下采集的数据点会跟新配置的曲线混在一起绘制。"""
        self._clear()
        self._load_cfg()

    def _save_cfg(self):
        if self._loading_cfg:
            return
        s = self.app.settings
        s.setValue("plot_mode", self.cb_mode.currentIndex())
        s.setValue("plot_sep", self.cb_sep.currentIndex())
        s.setValue("plot_regex", self.ed_regex.text())
        s.setValue("plot_hex_fields", self.ed_fields.text())
        s.setValue("plot_hex_header", self.ed_header.text())
        s.setValue("plot_maxpts", self.cb_maxpts.currentData())
        s.setValue("plot_xaxis", self.cb_xaxis.currentIndex())
        s.setValue("plot_view", self.cb_view.currentIndex())
        s.setValue("plot_dual_y", self.cb_dual_y.isChecked())

    # ---------------- 数据入口 ----------------
    def _codec(self):
        c = self.app._get_codec()
        return "utf-8" if (not c or c == "auto") else c

    def feed(self, data: bytes):
        """主窗口收包时调用（仅本对话框可见时）。HEX 模式按帧取字段；文本模式缓冲拆行。"""
        if self._paused or vars(self).get("_io_graph_mode", False):
            return
        if self.cb_mode.currentIndex() == _MODE_HEX:
            if not self._hex_header_valid:
                return
            for frame in binproto.iter_frames(bytes(data), self._hex_header):
                self._extract_frame(frame)
            return
        # 文本模式：解码 + 缓冲 + 拆完整行
        try:
            text = data.decode(self._codec(), errors="replace")
        except (LookupError, UnicodeError, TypeError, AttributeError):
            _log.debug("plot decode failed", exc_info=True)
            return
        self._decode_buf += text
        if len(self._decode_buf) > 65536:    # 长期收不到换行：防缓冲无限膨胀
            self._decode_buf = self._decode_buf[-4096:]
        norm = self._decode_buf.replace("\r\n", "\n").replace("\r", "\n")
        parts = norm.split("\n")
        self._decode_buf = parts.pop()       # 最后一段可能未完成，留到下次
        for line in parts:
            line = line.strip()
            if line:
                self._parse_line(line)

    # ---------------- 解析 ----------------
    def _parse_line(self, line):
        mode = self.cb_mode.currentIndex()
        if mode == _MODE_DLOG:
            m = _DLOG_RX.search(line)
            if not m:
                return          # 只认 TAG=DLOG 行，其余（日志/其它报文）整行忽略
            precision = int(m.group(1))
            if precision > 308:  # 防止畸形外部输入令浮点缩放溢出
                return
            scale = 10.0 ** precision
            vals = []
            for tok in re.split(r"[,\s]+", m.group(2).strip()):
                if not tok:
                    continue
                try:
                    vals.append(float(tok) / scale)
                except ValueError:
                    vals.append(None)
            if not vals:
                return
            self._append_vals(
                vals, names=["DLOG%d" % (i + 1) for i in range(len(vals))])
            return
        if mode == _MODE_REGEX:
            if self._regex is None:
                return
            m = self._regex.search(line)
            if not m:
                return
            tokens = m.groups() if m.groups() else (m.group(0),)
        else:                                # 分隔符
            tokens = re.split(_SEP_RX[self.cb_sep.currentIndex()], line)
        vals = []
        for tok in tokens:
            tok = (tok or "").strip()
            if tok == "":
                vals.append(None)
                continue
            try:
                vals.append(float(tok))
            except ValueError:
                vals.append(None)
        self._append_vals(vals)

    def _extract_frame(self, frame):
        if not self._hex_fields:
            return
        vals = [binproto.read_field(frame, off, typ) for _name, off, typ in self._hex_fields]
        self._append_vals(vals, names=[f[0] for f in self._hex_fields])

    def _append_vals(self, vals, names=None):
        # 波形只画数值；hexN/strN 等非数值（帧解析表才用）在这里跳过
        if not any(isinstance(v, (int, float)) for v in vals):
            return
        if self._x_time:
            if self._t0 is None:
                self._t0 = time.monotonic()
            x = time.monotonic() - self._t0
        else:
            x = self._sample_idx
        appended = False
        for i, v in enumerate(vals):
            if not isinstance(v, (int, float)):
                continue
            pos_to_idx = getattr(self, "_pos_to_idx", None)
            if pos_to_idx is None:    # 兼容不经 __init__ 构造的测试/旧对象
                pos_to_idx = self._pos_to_idx = {}
            idx = pos_to_idx.get(i)
            if idx is None:
                idx = len(self._channels)
                pos_to_idx[i] = idx
                self._ensure_channel(idx, names[i] if names else None)
                ch = self._channels[idx]
            else:
                ch = self._channels[idx]
            ch["xs"].append(x)
            ch["ys"].append(v)
            appended = True
            walls = ch.get("walls")
            if walls is not None:
                walls.append(time.time())
        if appended:
            self._cursor_stats_fp = None
        self._sample_idx += 1

    def feed_named_samples(self, samples):
        """寄存器表联动喂入：按 tag 名定位/创建通道（与文本位置通道解耦），每响应一个采样点。
        samples = [{"tag":..,"value":..}, ...]；非数值跳过。同一批样本（同一次 Modbus 响应）
        共享同一个 X 坐标——否则一次响应里的多个寄存器会落在不同的采样点，波形横向错位。"""
        if self._paused or not samples:
            return
        if vars(self).get("_io_graph_mode", False):
            samples = [s for s in samples if s.get("tag") in _IO_GRAPH_TAGS]
            if not samples:
                return
        if self._x_time:
            if self._t0 is None:
                self._t0 = time.monotonic()
            x = time.monotonic() - self._t0
        else:
            x = self._sample_idx
        appended = False
        wall = None
        for s in samples:
            if wall is None and s.get("timestamp") is not None:
                try:
                    wall = float(s.get("timestamp"))
                except (TypeError, ValueError):
                    wall = None
            if self._append_named(s.get("tag"), s.get("value"), x=x, bump=False,
                                 wall=wall):
                appended = True
        if appended:                     # 本响应实际画了点才推进采样序号
            self._sample_idx += 1

    def _append_named(self, name, value, x=None, bump=True, wall=None):
        if not name or not isinstance(value, (int, float)):
            return False
        if x is None:
            if self._x_time:
                if self._t0 is None:
                    self._t0 = time.monotonic()
                x = time.monotonic() - self._t0
            else:
                x = self._sample_idx
        idx = self._name_to_idx.get(name)
        if idx is None:
            idx = len(self._channels)
            self._name_to_idx[name] = idx
            self._ensure_channel(idx, str(name))
        ch = self._channels[idx]
        ch["xs"].append(x)
        ch["ys"].append(value)
        self._cursor_stats_fp = None
        if name in _NO_JUMP_TAGS:
            ch["jumpable"] = False
        walls = ch.get("walls")
        if walls is not None:
            # Real sample timestamps stay jumpable; rate ticks use time.time()
            # but are excluded via jumpable=False above.
            walls.append(float(wall) if wall is not None else time.time())
        if bump:
            self._sample_idx += 1
        return True

    def _ensure_channel(self, i, name=None):
        while len(self._channels) <= i:
            idx = len(self._channels)
            color = _CH_COLORS[idx % len(_CH_COLORS)]
            nm = name if (name and len(self._channels) == i) else f"CH{idx + 1}"
            curve = self.plot.plot([], [], pen=pg.mkPen(color, width=2), name=nm)
            cb = QCheckBox(nm)
            cb.setChecked(True)
            cb.setStyleSheet(f"color:{color}; font-weight:600;")
            cb.toggled.connect(self._on_channel_toggled)
            self._ch_h.insertWidget(self._ch_h.count() - 1, cb)   # 插在末尾 stretch 之前
            self._channels.append({
                "name": nm, "color": color, "curve": curve, "cb": cb,
                "xs": deque(maxlen=self._max_points),
                "ys": deque(maxlen=self._max_points),
                "walls": deque(maxlen=self._max_points),
                "jumpable": nm not in _NO_JUMP_TAGS,
                "on_right": False,
            })
        return self._channels[i]

    def _on_channel_toggled(self, *_args):
        self._redraw()

    def ensure_named_channels(self, names, exclusive=False):
        """Create named tag channels if missing; check them; optionally hide others."""
        keep_indices = set()
        for name in names:
            if not name:
                continue
            name = str(name)
            idx = self._name_to_idx.get(name)
            if idx is None:
                idx = len(self._channels)
                self._name_to_idx[name] = idx
                self._ensure_channel(idx, name)
            keep_indices.add(idx)
            ch = self._channels[idx]
            ch["cb"].setChecked(True)
            ch["curve"].setVisible(True)
            if name in _NO_JUMP_TAGS:
                ch["jumpable"] = False
        if exclusive and keep_indices:
            for idx, ch in enumerate(self._channels):
                on = idx in keep_indices
                ch["cb"].setChecked(on)
                ch["curve"].setVisible(on)

    def _snapshot_io_graph_state(self):
        """Capture axis/sample counters + per-channel series for a reversible I/O view."""
        series = []
        checks = []
        for ch in self._channels:
            checks.append(ch["cb"].isChecked())
            series.append((
                list(ch["xs"]),
                list(ch["ys"]),
                list(ch["walls"]) if ch.get("walls") is not None else None,
            ))
        return {
            "axis": self.cb_xaxis.currentIndex(),
            "view": self.cb_view.currentIndex(),
            "dual_y": self.cb_dual_y.isChecked(),
            "checks": checks,
            "sample_idx": self._sample_idx,
            "t0": self._t0,
            "series": series,
        }

    def apply_io_graph_preset(self):
        """One-click Wireshark-style I/O Graph: time axis + rate channels only.

        Temporary and reversible: does not wipe existing plot samples. Ordinary
        RX ``feed()`` / non-rate named samples are ignored while active; rate
        channels get a clean time-axis series that is discarded on leave.
        """
        if self._io_graph_mode:
            return False
        self._io_graph_restore = self._snapshot_io_graph_state()
        self._io_graph_mode = True
        self._set_cursor_visible(False)
        self._set_io_graph_controls(True)
        self.cb_xaxis.blockSignals(True)
        self.cb_xaxis.setCurrentIndex(1)
        self.cb_xaxis.blockSignals(False)
        self._x_time = True
        # Fresh time origin for the temporary rate overlay only.
        self._t0 = None
        self.plot.setLabel("bottom", self.app._t("plot_x_time"))
        self.ensure_named_channels(_IO_GRAPH_TAGS, exclusive=True)
        # Keep non-rate buffers intact (unchecked); clear rate series so the
        # temporary time-axis points never mix with prior sample-index data.
        for tag in _IO_GRAPH_TAGS:
            idx = self._name_to_idx.get(tag)
            if idx is None:
                continue
            ch = self._channels[idx]
            ch["xs"].clear()
            ch["ys"].clear()
            if ch.get("walls") is not None:
                ch["walls"].clear()
            ch["curve"].setData([], [])
        return True

    def leave_io_graph_preset(self):
        """Return to the plot state captured before the temporary I/O view."""
        if not self._io_graph_mode:
            return
        snap = self._io_graph_restore
        self._io_graph_mode = False
        self._io_graph_restore = None
        self._set_io_graph_controls(False)
        if not isinstance(snap, dict):
            # Backward-compatible tuple snapshot from older builds.
            axis, checks, sample_idx, time_origin = snap or (
                self.cb_xaxis.currentIndex(), [], self._sample_idx, self._t0)
            self.cb_xaxis.blockSignals(True)
            self.cb_xaxis.setCurrentIndex(axis)
            self.cb_xaxis.blockSignals(False)
            self._x_time = axis == 1
            self._sample_idx = sample_idx
            self._t0 = time_origin
            self.plot.setLabel(
                "bottom",
                self.app._t("plot_x_time" if self._x_time else "plot_x_index"))
            for idx, ch in enumerate(self._channels):
                on = checks[idx] if idx < len(checks) else False
                ch["cb"].setChecked(on)
                ch["curve"].setVisible(on)
            return

        axis = int(snap.get("axis", 0) or 0)
        view = int(snap.get("view", _VIEW_WAVE) or 0)
        dual_y = bool(snap.get("dual_y", False))
        self.cb_xaxis.blockSignals(True)
        self.cb_xaxis.setCurrentIndex(axis)
        self.cb_xaxis.blockSignals(False)
        self._x_time = axis == 1
        self._sample_idx = snap.get("sample_idx", 0)
        self._t0 = snap.get("t0")
        self.plot.setLabel(
            "bottom",
            self.app._t("plot_x_time" if self._x_time else "plot_x_index"))

        series = list(snap.get("series") or [])
        checks = list(snap.get("checks") or [])
        for idx, ch in enumerate(self._channels):
            if idx < len(series):
                xs, ys, walls = series[idx]
                ch["xs"] = deque(xs, maxlen=self._max_points)
                ch["ys"] = deque(ys, maxlen=self._max_points)
                if walls is not None:
                    ch["walls"] = deque(walls, maxlen=self._max_points)
                elif "walls" in ch:
                    ch["walls"] = deque(
                        [0.0] * len(xs), maxlen=self._max_points)
                on = bool(checks[idx]) if idx < len(checks) else False
                ch["cb"].setChecked(on)
                ch["curve"].setVisible(on)
                if on:
                    ch["curve"].setData(list(ch["xs"]), list(ch["ys"]))
                else:
                    ch["curve"].setData([], [])
            else:
                # Created only during the temporary I/O view (usually rate tags).
                ch["xs"].clear()
                ch["ys"].clear()
                if ch.get("walls") is not None:
                    ch["walls"].clear()
                ch["cb"].setChecked(False)
                ch["curve"].setVisible(False)
                ch["curve"].setData([], [])
        self.cb_view.blockSignals(True)
        self.cb_view.setCurrentIndex(view)
        self.cb_view.blockSignals(False)
        self.cb_dual_y.blockSignals(True)
        self.cb_dual_y.setChecked(dual_y)
        self.cb_dual_y.blockSignals(False)
        self._cursor_stats_fp = None
        self._redraw()

    def restart_io_graph_series(self):
        """Start a fresh rate segment after the active session changes.

        The generic plot snapshot remains untouched and can still be restored
        when leaving the temporary I/O view.
        """
        if not self._io_graph_mode:
            return False
        self._t0 = None
        for tag in _IO_GRAPH_TAGS:
            idx = self._name_to_idx.get(tag)
            if idx is None:
                continue
            ch = self._channels[idx]
            ch["xs"].clear()
            ch["ys"].clear()
            if ch.get("walls") is not None:
                ch["walls"].clear()
            ch["curve"].setData([], [])
        return True

    # ---------------- 重绘 / 视图 ----------------
    def _checked_channels(self):
        return [(i, ch) for i, ch in enumerate(self._channels) if ch["cb"].isChecked()]

    def _ensure_dual_y(self, enabled):
        """Lazily create / show the right ViewBox for dual-Y mode."""
        p1 = self.plot.plotItem
        if enabled:
            if self._right_vb is None:
                self._right_vb = pg.ViewBox()
                p1.scene().addItem(self._right_vb)
                p1.getAxis("right").linkToView(self._right_vb)
                self._right_vb.setXLink(p1)
                p1.vb.sigResized.connect(self._sync_right_vb)
            p1.showAxis("right")
            self._right_vb.setVisible(True)
            self._sync_right_vb()
        else:
            if self._right_vb is not None:
                self._right_vb.setVisible(False)
            p1.hideAxis("right")
            for ch in self._channels:
                self._place_curve(ch, on_right=False)

    def _sync_right_vb(self):
        if self._right_vb is None:
            return
        try:
            self._right_vb.setGeometry(self.plot.plotItem.vb.sceneBoundingRect())
        except Exception:
            _log.debug("sync right viewbox geometry failed", exc_info=True)

    def _place_curve(self, ch, on_right):
        curve = ch.get("curve")
        if curve is None:
            return
        want = bool(on_right) and self._right_vb is not None
        if bool(ch.get("on_right")) == want:
            return
        try:
            if ch.get("on_right") and self._right_vb is not None:
                self._right_vb.removeItem(curve)
            else:
                self.plot.plotItem.removeItem(curve)
        except Exception:
            _log.debug("remove curve before reparent failed", exc_info=True)
        try:
            if want:
                self._right_vb.addItem(curve)
            else:
                self.plot.plotItem.addItem(curve)
        except Exception:
            _log.debug("place curve on axis failed", exc_info=True)
        ch["on_right"] = want

    def _clear_hist_item(self):
        if self._hist_item is not None:
            try:
                self.plot.removeItem(self._hist_item)
            except Exception:
                _log.debug("remove histogram item failed", exc_info=True)
            self._hist_item = None

    def _clear_hist_axis_scale(self):
        if getattr(self, "_hist_scale", None) is not None:
            self.plot.getAxis("bottom").setTicks(None)
        self._hist_scale = None

    def _set_hist_axis_scale(self, real_centers, plot_centers, scale):
        if scale is None:
            self._clear_hist_axis_scale()
            return

        tick_indexes = sorted(set((0, len(real_centers) // 2, len(real_centers) - 1)))
        ticks = [
            (plot_centers[index], "%.4g" % real_centers[index])
            for index in tick_indexes
        ]
        self.plot.getAxis("bottom").setTicks([ticks])
        self._hist_scale = scale

    def _redraw(self):
        io_mode = bool(getattr(self, "_io_graph_mode", False))
        view = _VIEW_WAVE if io_mode else self.cb_view.currentIndex()
        dual = (not io_mode) and self.cb_dual_y.isChecked() and view == _VIEW_WAVE
        self._ensure_dual_y(dual)

        if view != _VIEW_HIST:
            self._clear_hist_item()
            self._clear_hist_axis_scale()

        checked = self._checked_channels()

        if view == _VIEW_XY:
            for ch in self._channels:
                self._place_curve(ch, on_right=False)
                ch["curve"].setVisible(False)
                ch["curve"].setData([], [])
            if len(checked) >= 2:
                (_i0, ch_a), (_i1, ch_b) = checked[0], checked[1]
                xs, ys = plot_stats.xy_pairs(
                    ch_a["xs"], ch_a["ys"], ch_b["xs"], ch_b["ys"])
                ch_a["curve"].setVisible(True)
                ch_a["curve"].setData(xs, ys)
                for _i, ch in checked[2:]:
                    ch["curve"].setVisible(False)
            return

        if view == _VIEW_HIST:
            for ch in self._channels:
                self._place_curve(ch, on_right=False)
                ch["curve"].setVisible(False)
                ch["curve"].setData([], [])
            if checked:
                _i, ch0 = checked[0]
                centers, counts = plot_stats.histogram_bins(ch0["ys"])
                if centers:
                    plot_centers, scale = plot_stats.histogram_plot_centers(centers)
                    self._set_hist_axis_scale(centers, plot_centers, scale)
                    width = plot_stats.histogram_bar_width(plot_centers)
                    if self._hist_item is None:
                        self._hist_item = pg.BarGraphItem(
                            x=plot_centers, height=counts, width=width,
                            brush=ch0["color"])
                        self.plot.addItem(self._hist_item)
                    else:
                        self._hist_item.setOpts(
                            x=plot_centers, height=counts, width=width,
                            brush=ch0["color"])
                else:
                    self._clear_hist_item()
                    self._clear_hist_axis_scale()
            else:
                self._clear_hist_item()
                self._clear_hist_axis_scale()
            return

        # waveform (default / I/O Graph)
        for idx, ch in enumerate(self._channels):
            on = ch["cb"].isChecked()
            use_right = dual and idx > 0 and on
            self._place_curve(ch, on_right=use_right)
            ch["curve"].setVisible(on)
            if on:
                ch["curve"].setData(list(ch["xs"]), list(ch["ys"]))
            else:
                ch["curve"].setData([], [])

    def _set_io_graph_controls(self, io_on):
        """I/O Graph forces waveform; disable view/dual-Y while active."""
        for w in (getattr(self, "lbl_view", None),
                  getattr(self, "cb_view", None),
                  getattr(self, "cb_dual_y", None)):
            if w is not None:
                w.setEnabled(not io_on)
        if not io_on:
            return
        if hasattr(self, "cb_view"):
            self.cb_view.blockSignals(True)
            self.cb_view.setCurrentIndex(_VIEW_WAVE)
            self.cb_view.blockSignals(False)
        if hasattr(self, "cb_dual_y"):
            self.cb_dual_y.blockSignals(True)
            self.cb_dual_y.setChecked(False)
            self.cb_dual_y.blockSignals(False)

    def _init_cursor(self):
        pen = pg.mkPen("#888888", width=1, style=Qt.DashLine)
        self._v_line = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self._h_line = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self._v_line.setVisible(False)
        self._h_line.setVisible(False)
        self.plot.addItem(self._v_line, ignoreBounds=True)
        self.plot.addItem(self._h_line, ignoreBounds=True)
        self.plot.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def _set_cursor_visible(self, on):
        if self._v_line is not None:
            self._v_line.setVisible(on)
        if self._h_line is not None:
            self._h_line.setVisible(on)
        if not on and hasattr(self, "lbl_cursor"):
            self.lbl_cursor.setText("")

    def _cursor_stats_fingerprint(self):
        return tuple(
            (ch["name"], len(ch["ys"]), ch["cb"].isChecked())
            for ch in self._channels)

    def _on_mouse_moved(self, pos):
        if getattr(self, "_io_graph_mode", False):
            self._set_cursor_visible(False)
            return
        if not self.plot.sceneBoundingRect().contains(pos):
            self._set_cursor_visible(False)
            return
        try:
            mouse = self.plot.plotItem.vb.mapSceneToView(pos)
            x, y = float(mouse.x()), float(mouse.y())
        except Exception:
            _log.debug("map cursor scene to view failed", exc_info=True)
            return
        display_x = x
        hist_scale = getattr(self, "_hist_scale", None)
        if hist_scale is not None:
            x = max(-1.0, min(1.0, x)) * hist_scale

        self._last_cursor = (x, y)
        self._set_cursor_visible(True)
        self._v_line.setPos(display_x)
        self._h_line.setPos(y)
        self._update_cursor_label(x, y)

    def _refresh_cursor_stats_cache(self):
        """Recompute channel min/max/mean text when series lengths change."""
        fp = self._cursor_stats_fingerprint()
        if fp == getattr(self, "_cursor_stats_fp", None):
            return
        self._cursor_stats_fp = fp
        parts = []
        for _idx, ch in self._checked_channels():
            st = plot_stats.series_stats(ch["ys"])
            if st["count"] <= 0:
                continue
            parts.append(
                "%s: n=%d min=%.4g max=%.4g mean=%.4g std=%.4g" % (
                    ch["name"], st["count"], st["min"], st["max"],
                    st["mean"], st["std"]))
        self._cursor_stats_extra = (
            ("  |  " + "  ".join(parts)) if parts else "")

    def _update_cursor_label(self, x, y):
        if not hasattr(self, "lbl_cursor"):
            return
        self._refresh_cursor_stats_cache()
        extra = getattr(self, "_cursor_stats_extra", "") or ""
        try:
            text = self.app._t("plot_cursor_fmt", x=x, y=y, stats=extra)
        except Exception:
            text = "x=%.4g  y=%.4g%s" % (x, y, extra)
        self.lbl_cursor.setText(text)

    def _on_view_changed(self, *_args):
        if self._loading_cfg:
            return
        # XY / histogram disable dual-Y placement without clearing buffers.
        if self.cb_view.currentIndex() != _VIEW_WAVE:
            self._ensure_dual_y(False)
        self._cursor_stats_fp = None
        self._redraw()
        self._save_cfg()

    def _on_dual_y_changed(self, *_args):
        if self._loading_cfg:
            return
        self._redraw()
        self._save_cfg()

    # ---------------- 工具条回调 ----------------
    def _on_mode_changed(self, *_args, save=True):
        mode = self.cb_mode.currentIndex()
        self.cb_sep.setVisible(mode == _MODE_DELIM)
        self.ed_regex.setVisible(mode == _MODE_REGEX)
        self.ed_header.setVisible(mode == _MODE_HEX)
        self.ed_fields.setVisible(mode == _MODE_HEX)
        if save:                 # 切模式（非初次加载）：通道含义变了，清空重建
            self._clear_after_io_graph()
            self._save_cfg()

    def _on_sep_changed(self, *_args, save=True):
        if save:                 # 分隔规则变了：旧列含义不能与新解析结果混用
            self._clear_after_io_graph()
            self._save_cfg()

    def _on_regex_changed(self, *_args, save=True):
        pat = self.ed_regex.text().strip()
        if not pat:
            self._regex = None
        else:
            try:
                self._regex = re.compile(pat)
            except re.error:
                self._regex = None
                if not self._loading_cfg:
                    self.app.toast(self.app._t("plot_regex_bad"), error=True)
        if save:
            # 捕获组/字段含义可能改变；先退出临时 I/O 视图，再清空旧曲线。
            self._clear_after_io_graph()
            self._save_cfg()

    def _on_fields_changed(self, *_args, save=True):
        try:
            self._hex_fields = binproto.parse_field_spec(self.ed_fields.text())
        except (ValueError, TypeError):
            self._hex_fields = []
            if not self._loading_cfg:
                self.app.toast(self.app._t("plot_fields_bad"), error=True)
        if save:                 # 字段定义变了：通道含义变，清空重建
            self._clear_after_io_graph()
            self._save_cfg()

    def _on_header_changed(self, *_args, save=True):
        try:
            self._hex_header = binproto.parse_hex_header(self.ed_header.text())
            self._hex_header_valid = True
        except ValueError:
            # 非法输入时停止 HEX 解析，不能退化成“空帧头=匹配全部”。
            self._hex_header_valid = False
            if not self._loading_cfg:
                self.app.toast(self.app._t("plot_header_bad"), error=True)
        if save:                 # 帧头变了：过滤范围变，清空避免新旧数据混在一起
            self._clear_after_io_graph()
            self._save_cfg()

    def _on_maxpts_changed(self, *_args):
        self._max_points = self.cb_maxpts.currentData()
        for ch in self._channels:
            ch["xs"] = deque(ch["xs"], maxlen=self._max_points)
            ch["ys"] = deque(ch["ys"], maxlen=self._max_points)
            if "walls" in ch:
                ch["walls"] = deque(ch["walls"], maxlen=self._max_points)
            else:
                # 旧配置 channel 无 walls，回填零值以支持双击跳转
                ch["walls"] = deque([0] * len(ch["xs"]), maxlen=self._max_points)
        self._save_cfg()

    def _on_xaxis_changed(self, *_args):
        # Leaving the temporary I/O view first restores preserved samples. Only
        # clear when the user picked an axis different from the restored one.
        if getattr(self, "_io_graph_mode", False):
            desired = self.cb_xaxis.currentIndex()
            self.leave_io_graph_preset()
            restored = self.cb_xaxis.currentIndex()
            if desired == restored:
                return
            self.cb_xaxis.blockSignals(True)
            self.cb_xaxis.setCurrentIndex(desired)
            self.cb_xaxis.blockSignals(False)
            self._x_time = desired == 1
            self._clear()
            self.plot.setLabel(
                "bottom",
                self.app._t("plot_x_time" if self._x_time else "plot_x_index"))
            self._save_cfg()
            return
        self._x_time = self.cb_xaxis.currentIndex() == 1
        self._clear()                # X 轴含义变了，旧点无意义，清空重来
        self.plot.setLabel("bottom",
                           self.app._t("plot_x_time" if self._x_time else "plot_x_index"))
        self._save_cfg()

    def _toggle_pause(self):
        self._paused = not self._paused
        self.btn_pause.setText(self.app._t("plot_resume" if self._paused else "plot_pause"))

    def _on_plot_clicked(self, event):
        """Double-click nearest sample -> jump_to_session_time(wall)."""
        if event.double() is not True:
            return
        if not self._channels:
            return
        try:
            mouse_point = self.plot.plotItem.vb.mapSceneToView(event.scenePos())
            x_click = float(mouse_point.x())
        except Exception:
            _log.debug("map plot click to view failed", exc_info=True)
            return
        try:
            y_click = float(mouse_point.y())
        except Exception:
            _log.debug("plot click y fallback", exc_info=True)
            y_click = 0.0
        best_wall, best_score = None, None
        for ch in self._channels:
            if ch.get("jumpable") is False or ch["name"] in _NO_JUMP_TAGS:
                continue
            xs = list(ch.get("xs") or ())
            ys = list(ch.get("ys") or ())
            if not xs or len(ys) != len(xs):
                continue
            walls = ch.get("walls")
            if walls is None or len(walls) != len(xs):
                padded = list(walls or ())
                if len(padded) < len(xs):
                    padded.extend([0.0] * (len(xs) - len(padded)))
                else:
                    padded = padded[:len(xs)]
                ch["walls"] = deque(padded, maxlen=self._max_points)
                walls = list(ch["walls"])
            else:
                walls = list(walls)
            for i, xv in enumerate(xs):
                # View coords: weight X a bit more (time axis) but include Y so
                # a click on the device curve beats a rate series sharing X.
                score = abs(float(xv) - x_click) + 0.25 * abs(float(ys[i]) - y_click)
                if best_score is None or score < best_score:
                    best_score, best_wall = score, float(walls[i])
        if best_wall is None:
            return
        jump = getattr(self.app, "jump_to_session_time", None)
        if callable(jump):
            jump(best_wall)


    def _clear_after_io_graph(self):
        """Restore any reversible I/O snapshot, then wipe — mode/header changes."""
        if getattr(self, "_io_graph_mode", False):
            self.leave_io_graph_preset()
        self._clear()

    def _clear(self):
        self._clear_hist_item()
        self._clear_hist_axis_scale()
        for ch in self._channels:
            try:
                if ch.get("on_right") and self._right_vb is not None:
                    self._right_vb.removeItem(ch["curve"])
                else:
                    self.plot.removeItem(ch["curve"])
            except Exception:
                try:
                    self.plot.removeItem(ch["curve"])
                except Exception:
                    _log.debug("remove curve on clear failed", exc_info=True)
            ch["cb"].setParent(None)
            ch["cb"].deleteLater()
        self._channels = []
        self._pos_to_idx = {}
        self._name_to_idx = {}
        self._sample_idx = 0
        self._t0 = None
        self._decode_buf = ""
        # Explicit clear discards the reversible I/O snapshot (user asked to wipe).
        self._io_graph_mode = False
        self._io_graph_restore = None
        self._set_cursor_visible(False)

    def _export_csv(self):
        channels = self._channels
        if getattr(self, "_io_graph_mode", False):
            # 临时 I/O 视图只导出当前四条速率曲线；被快照保留、UI 已隐藏的
            # 普通解析曲线仍使用原采样轴，不能混进同一份 CSV。
            rate_indices = {
                self._name_to_idx.get(tag) for tag in _IO_GRAPH_TAGS
            }
            channels = [
                ch for idx, ch in enumerate(self._channels)
                if idx in rate_indices
            ]
        if not channels:
            self.app.toast(self.app._t("plot_no_data"), error=True)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.app._t("plot_export_title"), "plot_data.csv",
            "CSV (*.csv);;All Files (*)")
        if not path:
            return
        # 每通道两列 (x, value) 并排，行数取最长通道；通道间 x 可能不齐（有缺值），故不强行对齐
        header = []
        cols = []
        for ch in channels:
            header += [f"{ch['name']}_x", ch["name"]]
            cols.append((list(ch["xs"]), list(ch["ys"])))
        rows = max((len(xs) for xs, _ in cols), default=0)
        try:
            import csv
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(header)
                for r in range(rows):
                    line = []
                    for xs, ys in cols:
                        if r < len(xs):
                            line += [xs[r], ys[r]]
                        else:
                            line += ["", ""]
                    w.writerow(line)
            self.app.toast(self.app._t("saved_to", path=path))
        except (OSError, UnicodeError, csv.Error) as e:
            self.app.toast(self.app._t("err_save_failed", e=e), error=True)

    # ---------------- 主题 / 语言 ----------------
    def _show_help_dlg(self):
        """弹独立窗口看波形图用法 + 例子（同帧解析/自动应答形制：富文本+滚动+可复制）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("plot_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(760, 540)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("plot_help"))
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
            {"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(getattr(self.app, "_lang", "en"), "Close"))
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
        QPushButton#PlotHelpBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 13px;
            font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
        }}
        QPushButton#PlotHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        QScrollArea#PlotChScroll {{ background: transparent; border: 0px; }}
        QScrollArea#PlotChScroll > QWidget > QWidget {{ background: transparent; }}
        """))
        _style_combo_popups(self, c)
        # pyqtgraph 配色跟随主题
        self.plot.setBackground(c["card_bg"])
        axis_pen = pg.mkPen(c["separator"])
        text_pen = pg.mkPen(c["text"])
        for ax in ("left", "bottom", "top", "right"):
            a = self.plot.getAxis(ax)
            a.setPen(axis_pen)
            a.setTextPen(text_pen)

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("plot_title"))
        self.lbl_mode.setText(t("plot_mode"))
        self.cb_mode.setItemText(_MODE_DELIM, t("plot_mode_delim"))
        self.cb_mode.setItemText(_MODE_REGEX, t("plot_mode_regex"))
        self.cb_mode.setItemText(_MODE_HEX, t("plot_mode_hex"))
        self.cb_mode.setItemText(_MODE_DLOG, t("plot_mode_dlog"))
        for i, key in enumerate(("plot_sep_comma", "plot_sep_space", "plot_sep_tab",
                                 "plot_sep_semicolon", "plot_sep_auto")):
            self.cb_sep.setItemText(i, t(key))
        self.ed_regex.setPlaceholderText(t("plot_regex_ph"))
        self.ed_header.setPlaceholderText(t("plot_header_ph"))
        self.ed_fields.setPlaceholderText(t("plot_fields_ph"))
        self.lbl_win.setText(t("plot_window"))
        self.lbl_x.setText(t("plot_xaxis"))
        self.cb_xaxis.setItemText(0, t("plot_x_index"))
        self.cb_xaxis.setItemText(1, t("plot_x_time"))
        self.lbl_view.setText(t("plot_view"))
        self.cb_view.setItemText(_VIEW_WAVE, t("plot_view_wave"))
        self.cb_view.setItemText(_VIEW_XY, t("plot_view_xy"))
        self.cb_view.setItemText(_VIEW_HIST, t("plot_view_hist"))
        self.cb_dual_y.setText(t("plot_dual_y"))
        self.cb_dual_y.setToolTip(t("plot_dual_y_tip"))
        self.btn_pause.setText(t("plot_resume" if self._paused else "plot_pause"))
        self.btn_clear.setText(t("plot_clear"))
        set_tooltip(self.plot, t("plot_jump_tip"))
        self.btn_export.setText(t("plot_export"))
        set_tooltip(self.btn_help, t("plot_help_btn"))
        self.lbl_hint.setText(t("plot_hint"))
        if getattr(self, "_last_cursor", None):
            self._update_cursor_label(*self._last_cursor)
        self.plot.setLabel("bottom",
                           t("plot_x_time" if self._x_time else "plot_x_index"))

    # ---------------- 生命周期 ----------------
    def showEvent(self, e):
        super().showEvent(e)
        if not self._timer.isActive():
            self._timer.start(33)        # ~30 FPS

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def closeEvent(self, e):
        # Closing while in I/O Graph must restore preserved samples for next open.
        if getattr(self, "_io_graph_mode", False):
            self.leave_io_graph_preset()
        self._save_cfg()
        super().closeEvent(e)


def _to_int(v, lo, hi):
    """QSettings 取值容错转 int 并钳制到 [lo, hi]。"""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, n))
