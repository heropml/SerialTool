# -*- coding: utf-8 -*-
"""数值仪表盘 DashboardDialog：把 RX 流解析成命名数值通道，每通道一张大字号卡片显示当前值，
超阈值变红（闪烁）。解析复用 stream_parse.NumericStreamParser（分隔符/正则/HEX字段三模式），
配置与波形图相互独立（自己的 dash_* 设置）。单实例非模态，复用刷新主题/语言。
"""
from PyQt5.QtCore import Qt, QTimer, QRect, QSize, QPoint
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
                             QComboBox, QLineEdit, QPushButton, QScrollArea, QFrame,
                             QLayout)

import stream_parse
from stream_parse import MODE_DELIM, MODE_REGEX, MODE_HEX
import binproto
from theme import chrome_for, _mix
from fonts import localize_qss
from dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups

_TILE_W, _TILE_H = 160, 90
_MAX_TILES = 64        # 通道卡片上限：防分隔符模式下畸形长行（上千列）建出海量卡片卡死 UI


class FlowLayout(QLayout):
    """自动换行的流式布局（Qt 官方示例精简移植）：卡片按可用宽度从左到右排、满则换行。"""

    def __init__(self, parent=None, margin=0, spacing=10):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x, y, line_h = rect.x(), rect.y(), 0
        spacing = self.spacing()
        for item in self._items:
            w, h = item.sizeHint().width(), item.sizeHint().height()
            next_x = x + w + spacing
            if next_x - spacing > rect.right() and line_h > 0:
                x = rect.x()
                y = y + line_h + spacing
                next_x = x + w + spacing
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_h = max(line_h, h)
        return y + line_h - rect.y()


def _fmt(v):
    """数值 → 紧凑显示：整数去小数点，其余最多 6 位有效数字。"""
    try:
        if float(v).is_integer() and abs(v) < 1e15:
            return str(int(v))
    except (ValueError, OverflowError):
        pass
    return f"{v:.6g}"


class DashboardDialog(QDialog):
    def __init__(self, app):
        # parent=None：避免干扰主窗 WM_NCHITTEST（同波形图/帧解析）。主窗 _shutdown 显式收。
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(560, 340)
        self.resize(820, 520)

        self._paused = False
        self._parser = stream_parse.NumericStreamParser()
        self._values = {}          # name -> 最新 float
        self._tiles = {}           # name -> {frame, lbl_name, lbl_val, lbl_unit, alert, state}
        self._order = []           # 通道出现顺序
        self._thresholds = {}      # name -> (lo, hi, unit)
        self._loading_cfg = False
        self._blink_on = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ===== 顶部工具条（解析模式 + 参数）=====
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.lbl_mode = QLabel()
        self.cb_mode = QComboBox()          # 0=分隔符 1=正则 2=HEX字节
        self.cb_mode.addItems(["", "", ""])
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cb_sep = QComboBox()
        self.cb_sep.addItems(["", "", "", "", ""])
        self.cb_sep.currentIndexChanged.connect(self._on_sep_changed)
        self.ed_regex = QLineEdit()
        self.ed_regex.editingFinished.connect(self._on_regex_changed)
        self.ed_header = QLineEdit()
        self.ed_header.setMaximumWidth(110)
        self.ed_header.editingFinished.connect(self._on_header_changed)
        self.ed_fields = QLineEdit()
        self.ed_fields.setToolTip(binproto.NUM_TYPES_TIP)
        self.ed_fields.editingFinished.connect(self._on_fields_changed)
        bar.addWidget(self.lbl_mode)
        bar.addWidget(self.cb_mode)
        bar.addWidget(self.cb_sep)
        bar.addWidget(self.ed_regex, 1)
        bar.addWidget(self.ed_header)
        bar.addWidget(self.ed_fields, 1)
        self.btn_pause = QPushButton()
        self.btn_pause.setObjectName("PlotGhostBtn")
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("PlotGhostBtn")
        self.btn_clear.clicked.connect(self._clear)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("PlotHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help_dlg)
        bar.addSpacing(8)
        bar.addWidget(self.btn_pause)
        bar.addWidget(self.btn_clear)
        bar.addWidget(self.btn_help)
        root.addLayout(bar)

        # ===== 阈值配置行 =====
        thr = QHBoxLayout()
        thr.setSpacing(8)
        self.lbl_thresh = QLabel()
        self.ed_thresh = QLineEdit()
        self.ed_thresh.editingFinished.connect(self._on_thresh_changed)
        thr.addWidget(self.lbl_thresh)
        thr.addWidget(self.ed_thresh, 1)
        root.addLayout(thr)

        # ===== 卡片区（流式布局 + 滚动）=====
        self._tile_host = QWidget()
        self._flow = FlowLayout(self._tile_host, margin=2, spacing=10)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("DashScroll")
        self._scroll.setWidget(self._tile_host)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self._scroll, 1)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("MsHint")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        # 值刷新 ~10Hz（与收包频率解耦）；告警闪烁 ~2Hz
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_tiles)
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)

        self.retranslate()
        self._load_cfg()
        self.refresh_theme()

    # ---------------- 配置持久化 ----------------
    def _codec(self):
        c = self.app._get_codec()
        return "utf-8" if (not c or c == "auto") else c

    def _load_cfg(self):
        s = self.app.settings
        self._loading_cfg = True
        try:
            self.cb_mode.setCurrentIndex(_to_int(s.value("dash_mode", 0), 0, 2))
            self.cb_sep.setCurrentIndex(_to_int(s.value("dash_sep", 0), 0, 4))
            self._parser.sep_index = self.cb_sep.currentIndex()
            self.ed_regex.setText(s.value("dash_regex", "") or "")
            self._on_regex_changed(save=False)
            self.ed_fields.setText(s.value("dash_fields", "") or "")
            self._on_fields_changed(save=False)
            self.ed_header.setText(s.value("dash_header", "") or "")
            self._on_header_changed(save=False)
            self.ed_thresh.setText(s.value("dash_thresholds", "") or "")
            self._on_thresh_changed(save=False)
            self._on_mode_changed(save=False)
        finally:
            self._loading_cfg = False

    def reload_cfg(self):
        """配置导入后调用：清掉旧卡片/数据，再按新设置重建。"""
        self._clear()
        self._load_cfg()

    def _save_cfg(self):
        if self._loading_cfg:
            return
        s = self.app.settings
        s.setValue("dash_mode", self.cb_mode.currentIndex())
        s.setValue("dash_sep", self.cb_sep.currentIndex())
        s.setValue("dash_regex", self.ed_regex.text())
        s.setValue("dash_fields", self.ed_fields.text())
        s.setValue("dash_header", self.ed_header.text())
        s.setValue("dash_thresholds", self.ed_thresh.text())

    # ---------------- 数据入口 ----------------
    def feed(self, data: bytes):
        """主窗口收包时调用（仅本对话框可见时）。解析出的每个通道更新为最新值 + 建卡片。"""
        if self._paused:
            return
        for name, val in self._parser.feed(data, self._codec()):
            if name in self._tiles:
                self._values[name] = val
            elif len(self._tiles) < _MAX_TILES:      # 未建卡且未到上限 → 新建
                self._values[name] = val
                self._ensure_tile(name)
            # 已到卡片上限的新通道：直接丢弃（不建卡、不记值），避免畸形长行卡死

    def reset_stream(self):
        """切断当前数据流的跨包状态，但保留卡片上的最近值。用于暂停/隐藏/重连等
        中间数据不会继续喂入解析器的场景，避免恢复后把断点两侧残段误拼成一行。"""
        self._parser.reset()

    def feed_named_samples(self, samples):
        """寄存器表联动喂入：直接按 (tag, value[, unit]) 更新卡片，绕过文本解析。
        与 feed() 共用 _values/_tiles；单位优先用阈值配置的，否则用样本带的。"""
        if self._paused:
            return
        for s in samples:
            name = s.get("tag")
            val = s.get("value")
            if not name or not isinstance(val, (int, float)):
                continue
            name = str(name)
            if name not in self._tiles:
                if len(self._tiles) >= _MAX_TILES:
                    continue
                self._ensure_tile(name)
            self._values[name] = val
            unit = s.get("unit") or ""
            if unit:
                self._tiles[name]["unit"] = str(unit)

    # ---------------- 卡片 ----------------
    def _ensure_tile(self, name):
        frame = QFrame()
        frame.setObjectName("DashTile")
        frame.setFixedSize(_TILE_W, _TILE_H)
        v = QVBoxLayout(frame)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(2)
        lbl_name = QLabel(name)
        lbl_name.setObjectName("DashName")
        row = QHBoxLayout()
        row.setSpacing(4)
        lbl_val = QLabel("--")
        lbl_val.setObjectName("DashVal")
        lbl_unit = QLabel("")
        lbl_unit.setObjectName("DashUnit")
        row.addWidget(lbl_val)
        row.addWidget(lbl_unit, 0, Qt.AlignBottom)
        row.addStretch(1)
        v.addWidget(lbl_name)
        v.addStretch(1)
        v.addLayout(row)
        self._flow.addWidget(frame)
        self._tiles[name] = {"frame": frame, "lbl_name": lbl_name, "lbl_val": lbl_val,
                             "lbl_unit": lbl_unit, "alert": False, "state": None}
        self._order.append(name)

    def _refresh_tiles(self):
        for name in self._order:
            tile = self._tiles[name]
            val = self._values.get(name)
            if val is None:
                continue
            lo, hi, unit = self._thresholds.get(name, (None, None, ""))
            tile["lbl_val"].setText(_fmt(val))
            tile["lbl_unit"].setText(unit or tile.get("unit", ""))
            tile["alert"] = ((lo is not None and val < lo)
                             or (hi is not None and val > hi))
            self._apply_tile_style(tile)

    def _apply_tile_style(self, tile):
        """按告警态 + 闪烁相位置 state 属性（"" / alert / alert2），变化才 repolish。"""
        if tile["alert"]:
            st = "alert2" if self._blink_on else "alert"
        else:
            st = ""
        if tile["state"] != st:
            tile["state"] = st
            f = tile["frame"]
            f.setProperty("state", st)
            f.style().unpolish(f)
            f.style().polish(f)

    def _blink(self):
        self._blink_on = not self._blink_on
        for name in self._order:
            tile = self._tiles[name]
            if tile["alert"]:
                self._apply_tile_style(tile)

    # ---------------- 工具条回调 ----------------
    def _on_mode_changed(self, *_a, save=True):
        mode = self.cb_mode.currentIndex()
        self._parser.mode = mode
        self.cb_sep.setVisible(mode == MODE_DELIM)
        self.ed_regex.setVisible(mode == MODE_REGEX)
        self.ed_header.setVisible(mode == MODE_HEX)
        self.ed_fields.setVisible(mode == MODE_HEX)
        if save:                # 切模式：通道含义变了，清空重建
            self._clear()
            self._save_cfg()

    def _on_sep_changed(self, *_a):
        self._parser.sep_index = self.cb_sep.currentIndex()
        if not self._loading_cfg:
            self._clear()
            self._save_cfg()

    def _on_regex_changed(self, *_a, save=True):
        if not self._parser.set_regex(self.ed_regex.text()):
            self.app.toast(self.app._t("plot_regex_bad"), error=True)
        if save:
            self._clear()
            self._save_cfg()

    def _on_fields_changed(self, *_a, save=True):
        if not self._parser.set_fields(self.ed_fields.text()):
            self.app.toast(self.app._t("plot_fields_bad"), error=True)
        if save:
            self._clear()
            self._save_cfg()

    def _on_header_changed(self, *_a, save=True):
        if not self._parser.set_header(self.ed_header.text()):
            self.app.toast(self.app._t("plot_header_bad"), error=True)
        if save:
            self._clear()
            self._save_cfg()

    def _on_thresh_changed(self, *_a, save=True):
        self._thresholds = self._parse_thresholds(self.ed_thresh.text())
        if save:
            self._save_cfg()

    @staticmethod
    def _parse_thresholds(text):
        """`名称:下限~上限:单位` 逗号分隔 → {name: (lo, hi, unit)}。下/上限可留空=该侧不限；
        非法数值该通道忽略阈值（仍显示）。"""
        result = {}
        for tok in (text or "").split(","):
            tok = tok.strip()
            if not tok:
                continue
            parts = tok.split(":")
            name = parts[0].strip()
            if not name:
                continue
            lo = hi = None
            unit = ""
            if len(parts) >= 2 and parts[1].strip():
                rng = parts[1].strip()
                if "~" in rng:
                    a, b = rng.split("~", 1)
                    try:
                        lo = float(a) if a.strip() else None
                        hi = float(b) if b.strip() else None
                    except ValueError:
                        lo = hi = None
            if len(parts) >= 3:
                unit = parts[2].strip()
            result[name] = (lo, hi, unit)
        return result

    def _toggle_pause(self):
        self._paused = not self._paused
        self.reset_stream()
        self.btn_pause.setText(self.app._t("plot_resume" if self._paused else "plot_pause"))

    def _clear(self):
        while self._flow.count():
            item = self._flow.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._tiles.clear()
        self._order = []
        self._values.clear()
        self._parser.reset()

    # ---------------- 主题 / 语言 ----------------
    def _show_help_dlg(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("dash_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(720, 500)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("dash_help"))
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

    def refresh_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")
        c = chrome_for(self.app._theme_id())
        alert_bg = _mix(c["card_bg"], c["danger"], 0.20)
        alert2_bg = _mix(c["card_bg"], c["danger"], 0.42)
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
        QScrollArea#DashScroll {{ background: transparent; border: 0px; }}
        QScrollArea#DashScroll > QWidget > QWidget {{ background: transparent; }}
        QFrame#DashTile {{
            background-color: {c['card_bg']}; border: 1px solid {c['separator']};
            border-radius: 10px;
        }}
        QFrame#DashTile[state="alert"] {{ background-color: {alert_bg}; border: 1px solid {c['danger']}; }}
        QFrame#DashTile[state="alert2"] {{ background-color: {alert2_bg}; border: 1px solid {c['danger']}; }}
        QLabel#DashName {{ color: {c['text_sec']}; font-family: 'Segoe UI'; font-size: 12px; }}
        QLabel#DashVal {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 26px; font-weight: 600; }}
        QLabel#DashUnit {{ color: {c['text_sec']}; font-family: 'Segoe UI'; font-size: 12px; padding-bottom: 4px; }}
        QFrame#DashTile[state="alert"] QLabel#DashVal, QFrame#DashTile[state="alert2"] QLabel#DashVal {{ color: {c['danger']}; }}
        """))
        _style_combo_popups(self, c)

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("dash_title"))
        self.lbl_mode.setText(t("plot_mode"))
        self.cb_mode.setItemText(MODE_DELIM, t("plot_mode_delim"))
        self.cb_mode.setItemText(MODE_REGEX, t("plot_mode_regex"))
        self.cb_mode.setItemText(MODE_HEX, t("plot_mode_hex"))
        for i, key in enumerate(("plot_sep_comma", "plot_sep_space", "plot_sep_tab",
                                 "plot_sep_semicolon", "plot_sep_auto")):
            self.cb_sep.setItemText(i, t(key))
        self.ed_regex.setPlaceholderText(t("plot_regex_ph"))
        self.ed_header.setPlaceholderText(t("plot_header_ph"))
        self.ed_fields.setPlaceholderText(t("plot_fields_ph"))
        self.lbl_thresh.setText(t("dash_thresh"))
        self.ed_thresh.setPlaceholderText(t("dash_thresh_ph"))
        self.btn_pause.setText(t("plot_resume" if self._paused else "plot_pause"))
        self.btn_clear.setText(t("plot_clear"))
        self.btn_help.setToolTip(t("plot_help_btn"))
        self.lbl_hint.setText(t("dash_hint"))

    # ---------------- 生命周期 ----------------
    def showEvent(self, e):
        super().showEvent(e)
        if not self._timer.isActive():
            self._timer.start(100)          # 10 Hz 值刷新
        if not self._blink_timer.isActive():
            self._blink_timer.start(500)    # 2 Hz 告警闪烁

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()
        self._blink_timer.stop()
        self.reset_stream()                 # 隐藏期间 RX 不会 feed，恢复时必须从新边界开始

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
