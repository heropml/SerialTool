# -*- coding: utf-8 -*-
"""iOS 风格控件：IOSSwitch / TitleBar / Card / make_label。"""
import sys
from PyQt5.QtCore import (Qt, QPropertyAnimation, QEasingCurve, QPoint,
                          pyqtSignal, pyqtProperty)
from PyQt5.QtGui import QColor, QPainter, QBrush, QIcon
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QFrame, QHBoxLayout,
                             QComboBox, QGraphicsDropShadowEffect, QMainWindow)
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


# ============== 自定义标题栏 ==============
class TitleBar(QWidget):
    HEIGHT = 36

    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self._win = parent
        self._drag_pos = None
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

        # 用 Segoe UI 里可靠的 Unicode 字符
        self._ch_min = "−"
        self._ch_max = "□"
        self._ch_restore = "❐"
        self._ch_close = "×"

        self.btn_min = self._mk_btn(self._ch_min)
        self.btn_max = self._mk_btn(self._ch_max)
        self.btn_close = self._mk_btn(self._ch_close)
        self.btn_close.setObjectName("CloseBtn")
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

        self.btn_min.clicked.connect(self._win.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self._win.close)

    def _mk_btn(self, text):
        btn = QPushButton(text)
        btn.setFixedSize(46, self.HEIGHT)
        btn.setObjectName("CtrlBtn")
        btn.setFocusPolicy(Qt.NoFocus)
        return btn

    def set_app_icon(self, qicon: QIcon):
        if qicon and not qicon.isNull():
            self.icon_label.setPixmap(qicon.pixmap(16, 16))

    def set_title(self, text: str):
        self.title_label.setText(text)

    def update_max_icon(self):
        self.btn_max.setText(self._ch_restore if self._win.isMaximized() else self._ch_max)

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()
        self.update_max_icon()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 非 Windows 且未最大化：用原生系统移动（拖动更跟手，避免手动 move 的脱节感）
            if sys.platform != "win32" and not self._win.isMaximized():
                wh = self._win.windowHandle()
                if wh is not None:
                    self._drag_pos = None
                    wh.startSystemMove()
                    event.accept()
                    return
            # Windows 或已最大化：沿用手动拖动（含最大化时拖动→还原的逻辑）
            if self._win.isMaximized():
                self._drag_pos = None
            else:
                self._drag_pos = event.globalPos() - self._win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
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
        if event.button() == Qt.LeftButton:
            self._toggle_max()
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


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


