# -*- coding: utf-8 -*-
"""数据波形图对话框 PlotDialog（基于 pyqtgraph）。

从 RX 数据解析数值，实时绘多通道滚动曲线。与显示区**解耦**：自持缓冲，feed(bytes)
→ 解析 → 各通道环形缓冲；由独立 ~30FPS 定时器统一重绘（不随收包频率），高吞吐不卡 GUI。

三种解析模式：
- 分隔符：每行按 逗号/空白/Tab/分号/自动 拆，每列一条曲线（ASCII 数字流，如 "1.2,3.4"）
- 正则：每行用正则，每个捕获组一条曲线（如 temp=(\\d+).*hum=(\\d+)）
- HEX 字节：**二进制协议**用——按 binproto 的「帧头 + 偏移:类型」从字节里取数值，每字段一条曲线
  （字段定义与帧解析表 frame_dialog 共用 binproto，语义一致）

单实例非模态，复用时刷新主题/语言。pyqtgraph 为可选依赖，main_window 懒导入 + try/except。
"""
import re
import time
from collections import deque

import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
                             QComboBox, QLineEdit, QPushButton, QCheckBox,
                             QScrollArea, QFrame, QFileDialog)

import binproto
from theme import chrome_for
from fonts import localize_qss
from dialogs import _dialog_list_qss, _set_win_titlebar_dark

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
_MODE_DELIM, _MODE_REGEX, _MODE_HEX = 0, 1, 2


class PlotDialog(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        # 独立窗口 + 最小化/最大化/关闭按钮；原生边框可拖动移动 + 拖边缩放
        # （波形是数据视图，常需放大/最大化看细节）
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
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

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ===== 顶部工具条 =====
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.lbl_mode = QLabel()
        self.cb_mode = QComboBox()           # 0=分隔符 1=正则 2=HEX字节
        self.cb_mode.addItems(["", "", ""])
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cb_sep = QComboBox()            # 分隔符（5 项，仅分隔符模式）
        self.cb_sep.addItems(["", "", "", "", ""])
        self.cb_sep.currentIndexChanged.connect(lambda *_: self._save_cfg())
        self.ed_regex = QLineEdit()          # 仅正则模式
        self.ed_regex.editingFinished.connect(self._on_regex_changed)
        self.ed_header = QLineEdit()         # 仅 HEX 字节模式：帧头过滤（hex，可空）
        self.ed_header.setMaximumWidth(120)
        self.ed_header.editingFinished.connect(self._on_header_changed)
        self.ed_fields = QLineEdit()         # 仅 HEX 字节模式：字段定义
        self.ed_fields.setToolTip(binproto.NUM_TYPES_TIP)
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

        self.btn_pause = QPushButton()
        self.btn_pause.setObjectName("PlotGhostBtn")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("PlotGhostBtn")
        self.btn_clear.clicked.connect(self._clear)
        self.btn_export = QPushButton()
        self.btn_export.setObjectName("PlotGhostBtn")
        self.btn_export.clicked.connect(self._export_csv)

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
        bar.addSpacing(8)
        bar.addWidget(self.btn_pause)
        bar.addWidget(self.btn_clear)
        bar.addWidget(self.btn_export)
        root.addLayout(bar)

        # ===== 绘图区 =====
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setClipToView(True)        # 只绘可视范围，长曲线更省
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.getAxis("bottom").enableAutoSIPrefix(False)  # 样本序号不该被缩成 (x0.001)
        root.addWidget(self.plot, 1)

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
            self.cb_mode.setCurrentIndex(_to_int(s.value("plot_mode", 0), 0, 2))
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
            self._on_mode_changed(save=False)
        finally:
            self._loading_cfg = False

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

    # ---------------- 数据入口 ----------------
    def _codec(self):
        c = self.app._get_codec()
        return "utf-8" if (not c or c == "auto") else c

    def feed(self, data: bytes):
        """主窗口收包时调用（仅本对话框可见时）。HEX 模式按帧取字段；文本模式缓冲拆行。"""
        if self._paused:
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
        except Exception:
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
        if self.cb_mode.currentIndex() == _MODE_REGEX:
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
        for i, v in enumerate(vals):
            if not isinstance(v, (int, float)):
                continue
            ch = self._ensure_channel(i, names[i] if names else None)
            ch["xs"].append(x)
            ch["ys"].append(v)
        self._sample_idx += 1

    def _ensure_channel(self, i, name=None):
        while len(self._channels) <= i:
            idx = len(self._channels)
            color = _CH_COLORS[idx % len(_CH_COLORS)]
            nm = name if (name and len(self._channels) == i) else f"CH{idx + 1}"
            curve = self.plot.plot([], [], pen=pg.mkPen(color, width=2), name=nm)
            cb = QCheckBox(nm)
            cb.setChecked(True)
            cb.setStyleSheet(f"color:{color}; font-weight:600;")
            cb.toggled.connect(lambda on, c=curve: c.setVisible(on))
            self._ch_h.insertWidget(self._ch_h.count() - 1, cb)   # 插在末尾 stretch 之前
            self._channels.append({
                "name": nm, "color": color, "curve": curve, "cb": cb,
                "xs": deque(maxlen=self._max_points),
                "ys": deque(maxlen=self._max_points),
            })
        return self._channels[i]

    # ---------------- 重绘 ----------------
    def _redraw(self):
        for ch in self._channels:
            if ch["cb"].isChecked():
                ch["curve"].setData(list(ch["xs"]), list(ch["ys"]))

    # ---------------- 工具条回调 ----------------
    def _on_mode_changed(self, *_args, save=True):
        mode = self.cb_mode.currentIndex()
        self.cb_sep.setVisible(mode == _MODE_DELIM)
        self.ed_regex.setVisible(mode == _MODE_REGEX)
        self.ed_header.setVisible(mode == _MODE_HEX)
        self.ed_fields.setVisible(mode == _MODE_HEX)
        if save:                 # 切模式（非初次加载）：通道含义变了，清空重建
            self._clear()
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
                self.app.toast(self.app._t("plot_regex_bad"), error=True)
        if save:
            self._save_cfg()

    def _on_fields_changed(self, *_args, save=True):
        try:
            self._hex_fields = binproto.parse_field_spec(self.ed_fields.text())
        except (ValueError, TypeError):
            self._hex_fields = []
            self.app.toast(self.app._t("plot_fields_bad"), error=True)
        if save:                 # 字段定义变了：通道含义变，清空重建
            self._clear()
            self._save_cfg()

    def _on_header_changed(self, *_args, save=True):
        try:
            self._hex_header = binproto.parse_hex_header(self.ed_header.text())
            self._hex_header_valid = True
        except ValueError:
            # 非法输入时停止 HEX 解析，不能退化成“空帧头=匹配全部”。
            self._hex_header_valid = False
            self.app.toast(self.app._t("plot_header_bad"), error=True)
        if save:                 # 帧头变了：过滤范围变，清空避免新旧数据混在一起
            self._clear()
            self._save_cfg()

    def _on_maxpts_changed(self, *_args):
        self._max_points = self.cb_maxpts.currentData()
        for ch in self._channels:    # 重建定长队列，保留最近的点
            ch["xs"] = deque(ch["xs"], maxlen=self._max_points)
            ch["ys"] = deque(ch["ys"], maxlen=self._max_points)
        self._save_cfg()

    def _on_xaxis_changed(self, *_args):
        self._x_time = self.cb_xaxis.currentIndex() == 1
        self._clear()                # X 轴含义变了，旧点无意义，清空重来
        self.plot.setLabel("bottom",
                           self.app._t("plot_x_time" if self._x_time else "plot_x_index"))
        self._save_cfg()

    def _toggle_pause(self):
        self._paused = not self._paused
        self.btn_pause.setText(self.app._t("plot_resume" if self._paused else "plot_pause"))

    def _clear(self):
        for ch in self._channels:
            self.plot.removeItem(ch["curve"])
            ch["cb"].setParent(None)
            ch["cb"].deleteLater()
        self._channels = []
        self._sample_idx = 0
        self._t0 = None
        self._decode_buf = ""

    def _export_csv(self):
        if not self._channels:
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
        for ch in self._channels:
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
        QScrollArea#PlotChScroll {{ background: transparent; border: 0px; }}
        QScrollArea#PlotChScroll > QWidget > QWidget {{ background: transparent; }}
        """))
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
        self.btn_pause.setText(t("plot_resume" if self._paused else "plot_pause"))
        self.btn_clear.setText(t("plot_clear"))
        self.btn_export.setText(t("plot_export"))
        self.lbl_hint.setText(t("plot_hint"))
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
        self._save_cfg()
        super().closeEvent(e)


def _to_int(v, lo, hi):
    """QSettings 取值容错转 int 并钳制到 [lo, hi]。"""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, n))
