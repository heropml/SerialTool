# -*- coding: utf-8 -*-
"""iOS 风格控件：IOSSwitch / TitleBar / Card / make_label。"""
import sys
from PyQt5.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QPoint,
                          pyqtSignal, pyqtProperty)
from PyQt5.QtGui import QColor, QPainter, QBrush, QIcon, QPen, QPalette
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QFrame, QHBoxLayout,
                             QComboBox, QGraphicsDropShadowEffect, QMainWindow,
                             QApplication)
from theme import COLOR_TEXT, COLOR_TEXT_SECONDARY, COLOR_GREEN
from fonts import ui_font


# ============== iOS 风格滑动开关 ==============
class IOSSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 24)
        self._checked = checked
        self._circle_pos = 18 if checked else 2
        self.setCursor(Qt.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"circle_pos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        # 关态轨道 / 旋钮颜色可被主题覆盖（默认 iOS 浅色作 fallback）；开态恒用 COLOR_GREEN
        self._track_off = QColor("#E5E5EA")
        self._knob = QColor("#FFFFFF")

    def set_theme_colors(self, track_off, knob):
        """主窗口切主题时调用：让关态开关跟随主题深浅（开态仍用通用绿）。"""
        self._track_off = QColor(track_off)
        self._knob = QColor(knob)
        self.update()

    def isChecked(self):
        return self._checked

    def setChecked(self, value, animate=True):
        if self._checked == value:
            return
        self._checked = value
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._circle_pos)
            self._anim.setEndValue(18 if value else 2)
            self._anim.start()
        else:
            self._circle_pos = 18 if value else 2
            self.update()
        self.toggled.emit(value)

    def get_circle_pos(self):
        return self._circle_pos

    def set_circle_pos(self, v):
        self._circle_pos = v
        self.update()

    circle_pos = pyqtProperty(int, get_circle_pos, set_circle_pos)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track_color = QColor(COLOR_GREEN) if self._checked else self._track_off
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(0, 0, 40, 24, 12, 12)
        shadow = QColor(0, 0, 0, 40)
        p.setBrush(QBrush(shadow))
        p.drawEllipse(self._circle_pos, 3, 20, 20)
        p.setBrush(QBrush(self._knob))
        p.drawEllipse(self._circle_pos, 2, 20, 20)


# ============== 窗口控制按钮（自绘，不依赖系统字体） ==============
class _CtrlBtn(QPushButton):
    """最小化/最大化/还原/关闭：QPainter 手画图标，跨主题色（QSS color → palette）+ 跨平台稳定。
    用自绘是因为 Segoe Fluent Icons / MDL2 Assets 在部分 Win11 上 Qt 字体匹配挂掉（X 字形空白）。"""
    KIND_MIN, KIND_MAX, KIND_RESTORE, KIND_CLOSE = range(4)

    def __init__(self, kind, parent=None):
        super().__init__("", parent)      # 空文本：图标全靠 paintEvent 画
        self._kind = kind
        self._hover = False
        self.setFixedSize(46, 36)
        self.setFocusPolicy(Qt.NoFocus)
        self.setObjectName("CloseBtn" if kind == self.KIND_CLOSE else "CtrlBtn")

    def set_kind(self, k):
        if k != self._kind:
            self._kind = k
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, ev):
        super().paintEvent(ev)            # 让 QSS 画底色（含 :hover 红底）
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)  # 像素对齐 → 线条清爽
        # 关闭悬停 = 白笔（背景已是红）；其它走 QSS color: 同步过来的 palette.ButtonText
        if self._kind == self.KIND_CLOSE and self._hover:
            col = QColor("#FFFFFF")
        else:
            col = self.palette().color(QPalette.ButtonText)
        p.setPen(QPen(col, 1.0))
        s = 10                            # 图标边长（Win11 标准 ~10px）
        cx, cy = self.width() // 2, self.height() // 2
        x, y = cx - s // 2, cy - s // 2
        if self._kind == self.KIND_MIN:
            p.drawLine(x, cy, x + s - 1, cy)
        elif self._kind == self.KIND_MAX:
            p.drawRect(x, y, s - 1, s - 1)
        elif self._kind == self.KIND_RESTORE:
            sz = s - 3
            p.drawRect(x, y + 2, sz, sz)         # 后框（左下）
            p.drawRect(x + 2, y, sz, sz)         # 前框（右上）
        elif self._kind == self.KIND_CLOSE:
            p.drawLine(x, y, x + s - 1, y + s - 1)
            p.drawLine(x, y + s - 1, x + s - 1, y)
        p.end()


# ============== 自定义标题栏 ==============
class TitleBar(QWidget):
    HEIGHT = 36

    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self._win = parent
        self._drag_pos = None
        self._sysmove_origin = None   # 非 Windows：按下点，拖动超阈值才发起原生系统移动
        self.setObjectName("TitleBar")
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(6)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        layout.addWidget(self.icon_label)

        self.title_label = QLabel("")
        self.title_label.setFont(ui_font(10))
        self.title_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(self.title_label)

        # 语言 + 主题切换全部左侧 — 紧挨标题（旧版语言在右上现挪到左上）
        layout.addSpacing(12)
        self.cb_language = QComboBox()
        self.cb_language.setMinimumWidth(96)
        self.cb_language.setFixedHeight(26)
        layout.addWidget(self.cb_language)

        self.cb_theme = QComboBox()
        self.cb_theme.setMinimumWidth(120)
        self.cb_theme.setFixedHeight(26)
        layout.addWidget(self.cb_theme)

        layout.addStretch(1)

        self.btn_min = _CtrlBtn(_CtrlBtn.KIND_MIN, self)
        self.btn_max = _CtrlBtn(_CtrlBtn.KIND_MAX, self)
        self.btn_close = _CtrlBtn(_CtrlBtn.KIND_CLOSE, self)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

        self.btn_min.clicked.connect(self._win.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self._win.close)

        if sys.platform == "darwin":
            # macOS 用系统原生红黄绿交通灯 → 隐藏自定义的最小化/最大化/关闭按钮
            self.btn_min.hide()
            self.btn_max.hide()
            self.btn_close.hide()

    def set_app_icon(self, qicon: QIcon):
        if qicon and not qicon.isNull():
            self.icon_label.setPixmap(qicon.pixmap(16, 16))

    def set_title(self, text: str):
        self.title_label.setText(text)

    def update_max_icon(self):
        self.btn_max.set_kind(_CtrlBtn.KIND_RESTORE if self._win.isMaximized() else _CtrlBtn.KIND_MAX)

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()
        self.update_max_icon()

    def mousePressEvent(self, event):
        # macOS：标准原生标题栏由系统接管窗口拖动/缩放/双击，自定义栏不处理（避免冲突与卡死）
        if sys.platform == "darwin":
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton:
            # 仅 Linux 用原生 startSystemMove（且延迟到真正拖动超阈值再发起，避免双击触发）。
            # Windows 走「手动 move」——逐帧 move() 且检查按键，绝不会卡死。
            if sys.platform != "win32" and not self._win.isMaximized():
                self._sysmove_origin = event.globalPos()
                self._drag_pos = None
                event.accept()
                return
            # Windows / macOS / 已最大化：手动拖动（含最大化时拖动→还原的逻辑）
            self._sysmove_origin = None
            if self._win.isMaximized():
                self._drag_pos = None
            else:
                self._drag_pos = event.globalPos() - self._win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if sys.platform == "darwin":
            super().mouseMoveEvent(event)
            return
        # 兜底：实际左键已松开就结束拖动并清状态。event.buttons() 可能因 showNormal/最大化切换
        # 变陈旧，导致「鼠标不按、窗口却一直跟手移动」；用 QApplication 查真实按键状态最可靠。
        if not (QApplication.mouseButtons() & Qt.LeftButton):
            self._drag_pos = None
            self._sysmove_origin = None
            return
        if event.buttons() == Qt.LeftButton:
            # Linux：移动超过阈值才发起原生系统移动（双击无位移 → 不触发）
            if self._sysmove_origin is not None:
                if (event.globalPos() - self._sysmove_origin).manhattanLength() > 6:
                    self._sysmove_origin = None
                    wh = self._win.windowHandle()
                    if wh is not None:
                        wh.startSystemMove()
                event.accept()
                return
            if self._win.isMaximized():
                ratio = event.x() / max(self.width(), 1)
                # 先取还原后的宽度（normalGeometry 不受最大化状态影响）。否则 showNormal()
                # 后立即 width() 可能仍是最大化宽度，drag_pos 偏移过大、窗口与鼠标严重脱节
                # （窗口跑一边、鼠标在另一边）。
                new_w = self._win.normalGeometry().width()
                self._win.showNormal()
                self.update_max_icon()
                if new_w <= 0:
                    new_w = self._win.width()
                self._drag_pos = QPoint(int(new_w * ratio), event.y())
                self._win.move(event.globalPos() - self._drag_pos)
            elif self._drag_pos is not None:
                self._win.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if sys.platform == "darwin":
            super().mouseDoubleClickEvent(event)
            return
        if event.button() == Qt.LeftButton:
            self._toggle_max()
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._sysmove_origin = None


# ============== 带阴影的卡片 ==============
class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)


# ============== 标签 ==============
def make_label(text, size=11, bold=False, color=COLOR_TEXT):
    lbl = QLabel(text)
    f = ui_font(size, bold)
    lbl.setFont(f)
    if color == COLOR_TEXT_SECONDARY:
        lbl.setProperty("theme_color_role", "secondary")
    elif color == COLOR_TEXT:
        lbl.setProperty("theme_color_role", "primary")
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


