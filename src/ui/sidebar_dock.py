# -*- coding: utf-8 -*-
"""左侧栏「自动隐藏」控制器（图钉，观感同 XShell 的会话管理器）。

两种状态：

  · 固定     — 侧栏留在主分隔条里，和右侧一起分空间（默认，即原有行为）
  · 自动隐藏 — 侧栏从分隔条摘出，工作区左缘只留一条竖标签；鼠标移到竖标签上
               侧栏以浮层滑出、盖在数据区上方，鼠标移开约 0.5s 后自动收回。

浮层是 ``host``（strip + splitter 那一行）的子控件，**不是**顶层窗口：
这样它跟着工作区裁剪，切换工作台分类时随 QStackedLayout 一起隐藏，
不会飘在别的页面上面。
"""
from PyQt5.QtCore import (QEasingCurve, QEvent, QObject, QPoint,
                          QPropertyAnimation, QRect, QRectF, Qt, QTimer,
                          pyqtSignal)
from PyQt5.QtGui import QColor, QCursor, QPainter, QPen
from PyQt5.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox,
                             QLineEdit, QVBoxLayout, QWidget)

from ui.fonts import ui_font
from ui.ui_icons import pin_icon
from ui.ui_tips import set_tooltip

STRIP_WIDTH = 22          # 竖标签宽度（够放 10px 竖排文字 + 左右留白）
_OPEN_DELAY_MS = 90       # 鼠标扫过竖标签的抖动过滤
_SLIDE_MS = 130           # 滑入 / 滑出动画
_POLL_MS = 220            # 收回判定轮询
_HIDE_TICKS = 2           # 连续 N 次「鼠标不在浮层上」才收回（≈0.45s）
_FALLBACK_W = 300         # 拿不到分隔条宽度时的兜底宽度（同 init_ui 默认值）


class _SidebarStrip(QWidget):
    """左缘竖标签：鼠标移上去发 ``hovered``，点击发 ``clicked``。"""

    hovered = pyqtSignal()
    left = pyqtSignal()
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarStrip")
        self.setFixedWidth(STRIP_WIDTH)
        self.setCursor(Qt.PointingHandCursor)
        self._text = ""
        self._fg = "#6B7280"
        self._bg = "#FFFFFF"
        self._hover_bg = "#E5E7EB"
        self._border = "#D1D5DB"
        self._hover = False

    def set_text(self, text):
        self._text = str(text or "")
        self.update()

    def set_colors(self, fg, bg, hover_bg, border):
        self._fg, self._bg, self._hover_bg = fg, bg, hover_bg
        self._border = border
        self.update()

    def enterEvent(self, ev):
        self._hover = True
        self.update()
        self.hovered.emit()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        self.update()
        self.left.emit()
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 浅色主题下标签底色和窗口底色很接近，描一圈边才看得出这是个可点的标签
        p.setPen(QPen(QColor(self._border), 1))
        p.setBrush(QColor(self._hover_bg if self._hover else self._bg))
        p.drawRoundedRect(QRectF(2.5, 0.5, max(self.width() - 5.0, 1.0),
                                 max(self.height() - 1.0, 1.0)), 5, 5)
        if not self._text:
            return
        p.setPen(QColor(self._fg))
        p.setFont(ui_font(10))
        # 竖排：逆时针转 90°，文字自下而上、贴标签顶端（同多数 IDE 的停靠标签）
        p.translate(0, self.height())
        p.rotate(-90)
        p.drawText(QRect(0, 0, max(self.height() - 10, 1), self.width()),
                   Qt.AlignRight | Qt.AlignVCenter, self._text)


class SidebarDock(QObject):
    """把侧栏在「分隔条里固定」和「左缘自动隐藏」两种形态之间搬来搬去。"""

    def __init__(self, app, sidebar, splitter, host):
        super().__init__(host)
        self.app = app
        self.sidebar = sidebar
        self.splitter = splitter
        self.host = host
        self.btn_pin = None
        self._pin_color = "#6B7280"
        self._pinned = True
        self._width = 0
        self._docked_state = None    # 摘出前的 splitter.saveState()，退出时照旧落盘
        self._miss = 0
        self._closing = False

        self.strip = _SidebarStrip(host)
        self.strip.hide()
        self.strip.hovered.connect(self._on_strip_hovered)
        self.strip.clicked.connect(self._on_strip_clicked)

        self.flyout = QWidget(host)
        self.flyout.setObjectName("SidebarFlyout")
        self._flyout_layout = QVBoxLayout(self.flyout)
        self._flyout_layout.setContentsMargins(0, 0, 0, 0)
        self._flyout_layout.setSpacing(0)
        self.flyout.hide()

        self._anim = QPropertyAnimation(self.flyout, b"pos", self)
        self._anim.setDuration(_SLIDE_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

        self._open_timer = QTimer(self)
        self._open_timer.setSingleShot(True)
        self._open_timer.setInterval(_OPEN_DELAY_MS)
        self._open_timer.timeout.connect(self.open_flyout)
        self.strip.left.connect(self._open_timer.stop)

        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_MS)
        self._poll.timeout.connect(self._tick)

        host.installEventFilter(self)

    # ----- 对外 -----
    def bind_pin_button(self, btn):
        """接上侧栏标题行的图钉按钮（可为 None：没按钮也能用竖标签）。"""
        self.btn_pin = btn
        if btn is not None:
            # 单发延时：点击发生在侧栏内部，等信号派发完再搬控件，
            # 免得在 sender 的祖先上做 reparent。
            btn.clicked.connect(lambda *_: QTimer.singleShot(0, self.toggle))
        self._refresh_pin_button()

    def is_pinned(self):
        return self._pinned

    def toggle(self):
        self.set_pinned(not self._pinned)

    def set_pinned(self, pinned):
        pinned = bool(pinned)
        if pinned == self._pinned:
            self._refresh_pin_button()
            return
        if pinned:
            self._dock()
        else:
            self._undock()
        self._pinned = pinned
        self._refresh_pin_button()

    def split_state(self):
        """退出时该写进 QSettings 的 h_splitter 状态。

        自动隐藏时 splitter 里只剩右侧一个控件，直接 saveState 会把用户的
        左右比例弄丢（下次固定回来宽度全乱），所以回放摘出前存下的那份。
        """
        if not self._pinned and self._docked_state is not None:
            return self._docked_state
        return self.splitter.saveState()

    def retranslate(self):
        self.strip.set_text(self.app._t("sidebar_tab"))
        set_tooltip(self.strip, self.app._t("sidebar_strip_tip"))
        self._refresh_pin_button()

    def apply_theme(self, chrome):
        self.strip.set_colors(chrome["text_sec"], chrome["card_bg"],
                              chrome["ghost_hover"], chrome["separator"])
        self.flyout.setStyleSheet(
            "QWidget#SidebarFlyout {background: %s; border-right: 1px solid %s;}"
            % (chrome["window_bg"], chrome["separator"]))
        self._pin_color = chrome["text_sec"]
        self._refresh_pin_button()

    # ----- 固定 / 摘出 -----
    def _undock(self):
        sizes = self.splitter.sizes()
        if sizes and sizes[0] > 0:
            self._width = sizes[0]
        self._docked_state = self.splitter.saveState()
        self._flyout_layout.addWidget(self.sidebar)   # 从 splitter 搬进浮层
        w = self._flyout_width()
        self.flyout.setGeometry(STRIP_WIDTH - w, 0, w, max(self.host.height(), 1))
        self.flyout.hide()
        self.strip.show()

    def _dock(self):
        self._open_timer.stop()
        self._poll.stop()
        self._anim.stop()
        self._closing = False
        self.flyout.hide()
        self.strip.hide()
        self.splitter.insertWidget(0, self.sidebar)   # 搬回分隔条
        self.sidebar.show()
        w = self._flyout_width()
        rest = self.splitter.width() - w - self.splitter.handleWidth()
        self.splitter.setSizes([w, max(rest, 1)])
        self._docked_state = None

    # ----- 浮层 -----
    def open_flyout(self):
        if self._pinned:
            return
        self._open_timer.stop()
        self._closing = False
        self._anim.stop()
        w = self._flyout_width()
        self.flyout.resize(w, max(self.host.height(), 1))
        if not self.flyout.isVisible():
            self.flyout.move(STRIP_WIDTH - w, 0)
            self.flyout.show()
        self.flyout.raise_()
        self._anim.setStartValue(self.flyout.pos())
        self._anim.setEndValue(QPoint(STRIP_WIDTH, 0))
        self._anim.start()
        self._miss = 0
        self._poll.start()

    def close_flyout(self, immediate=False):
        self._open_timer.stop()
        self._poll.stop()
        # 切页时祖先已隐藏，仍需显式关闭浮层，避免切回后随页面重新显示。
        if not self.flyout.isVisibleTo(self.host):
            return
        if immediate:
            self._anim.stop()
            self._closing = False
            self.flyout.hide()
            return
        self._closing = True
        self._anim.stop()
        self._anim.setStartValue(self.flyout.pos())
        self._anim.setEndValue(QPoint(STRIP_WIDTH - self.flyout.width(), 0))
        self._anim.start()

    def flyout_open(self):
        return self.flyout.isVisible() and not self._closing

    # ----- 内部 -----
    def _flyout_width(self):
        w = int(self._width or _FALLBACK_W)
        lo = self.sidebar.minimumWidth() or 0
        hi = self.sidebar.maximumWidth()
        if hi and hi < 16777215:
            w = min(w, hi)
        return max(w, lo, 120)

    def _on_strip_hovered(self):
        if not self._pinned and not self.flyout_open():
            self._open_timer.start()

    def _on_strip_clicked(self):
        if self._pinned:
            return
        if self.flyout_open():
            self.close_flyout()
        else:
            self.open_flyout()

    def _on_anim_finished(self):
        if self._closing:
            self.flyout.hide()
            self._closing = False

    def _keeps_open(self):
        """这些情况别收回：下拉弹出中 / 模态框开着 / 焦点在浮层里的输入框。"""
        if QApplication.activePopupWidget() is not None:
            return True
        if QApplication.activeModalWidget() is not None:
            return True
        fw = QApplication.focusWidget()
        if fw is not None and self.flyout.isAncestorOf(fw):
            if isinstance(fw, (QLineEdit, QAbstractSpinBox)):
                return True
            if isinstance(fw, QComboBox) and fw.isEditable():
                return True
        return False

    def _tick(self):
        if self._pinned or not self.flyout.isVisible():
            self._poll.stop()
            return
        if self._closing or self._keeps_open():
            self._miss = 0
            return
        pos = QCursor.pos()
        if self._contains(self.flyout, pos) or self._contains(self.strip, pos):
            self._miss = 0
            return
        self._miss += 1
        if self._miss >= _HIDE_TICKS:
            self._miss = 0
            self.close_flyout()

    @staticmethod
    def _contains(widget, global_pos):
        if widget is None or not widget.isVisible():
            return False
        return widget.rect().contains(widget.mapFromGlobal(global_pos))

    def _refresh_pin_button(self):
        btn = self.btn_pin
        if btn is None:
            return
        btn.setIcon(pin_icon(self._pin_color, 14, pinned=self._pinned))
        key = "sidebar_autohide_tip" if self._pinned else "sidebar_pin_tip"
        btn.setProperty("tr_tooltip", key)
        set_tooltip(btn, self.app._t(key))

    def eventFilter(self, obj, ev):
        if obj is self.host:
            kind = ev.type()
            if kind == QEvent.Resize and self.flyout.isVisible():
                self.flyout.resize(self.flyout.width(),
                                   max(self.host.height(), 1))
            elif kind in (QEvent.Hide, QEvent.HideToParent):
                self.close_flyout(immediate=True)
        return False
