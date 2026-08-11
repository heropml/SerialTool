# -*- coding: utf-8 -*-
"""Qt-free dashboard widget helpers + painted tile widgets for gauge/LED/progress."""
from __future__ import annotations

import math
from typing import Optional, Tuple

WIDGET_NUMBER = "number"
WIDGET_GAUGE = "gauge"
WIDGET_LED = "led"
WIDGET_PROGRESS = "progress"
WIDGET_KINDS = (WIDGET_NUMBER, WIDGET_GAUGE, WIDGET_LED, WIDGET_PROGRESS)


def normalize_widget(kind) -> str:
    text = str(kind or "").strip().lower()
    return text if text in WIDGET_KINDS else WIDGET_NUMBER


def progress_ratio(val: float, lo: Optional[float], hi: Optional[float]) -> float:
    """Map value into [0, 1] using thresholds.

    - Both missing → default 0..100
    - One-sided → do not invent 0/100 opposite of alert semantics; use a span
      of ``abs(bound)`` (or 1) anchored at the provided bound.
    """
    try:
        v = float(val)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    if lo is None and hi is None:
        low, high = 0.0, 100.0
    elif lo is None:
        high = float(hi)
        span = abs(high) if high != 0.0 else 1.0
        low = high - span
    elif hi is None:
        low = float(lo)
        span = abs(low) if low != 0.0 else 1.0
        high = low + span
    else:
        low, high = float(lo), float(hi)
    if not math.isfinite(low) or not math.isfinite(high) or high == low:
        return 0.0 if v <= low else 1.0
    ratio = (v - low) / (high - low)
    if ratio < 0.0:
        return 0.0
    if ratio > 1.0:
        return 1.0
    return ratio


def gauge_angle_deg(val: float, lo: Optional[float], hi: Optional[float]) -> float:
    """Needle angle: 225° (low) → -45° (high), clockwise via bottom."""
    return 225.0 - progress_ratio(val, lo, hi) * 270.0


def led_state(level: str, out_of_range: bool) -> str:
    """Return led visual state: off | ok | warn | alarm."""
    if out_of_range or level == "alarm":
        return "alarm"
    if level == "warn":
        return "warn"
    return "ok"


try:
    from PyQt5.QtCore import Qt, QRectF, QPointF
    from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont
    from PyQt5.QtWidgets import QWidget
except Exception:  # pragma: no cover - Qt-free helpers still importable
    QWidget = object  # type: ignore


class DashGaugeWidget(QWidget):  # type: ignore[misc]
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ratio = 0.0
        self._text = "--"
        self._color = QColor("#4C8BF5")
        self.setMinimumSize(120, 70)

    def set_value(self, text, ratio, color):
        self._text = str(text)
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        side = min(w, h * 1.4)
        cx, cy = w * 0.5, h * 0.72
        r = side * 0.38
        pen = QPen(QColor(self._color))
        pen.setWidth(6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        # Background arc
        pen_bg = QPen(QColor(self._color.red(), self._color.green(),
                             self._color.blue(), 50))
        pen_bg.setWidth(6)
        pen_bg.setCapStyle(Qt.RoundCap)
        p.setPen(pen_bg)
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.drawArc(rect, 225 * 16, -270 * 16)
        p.setPen(pen)
        span = int(-270 * 16 * self._ratio)
        p.drawArc(rect, 225 * 16, span)
        # Needle (reuse gauge_angle_deg mapping: ratio 0..1 ≡ value in [0,1])
        ang = math.radians(gauge_angle_deg(self._ratio, 0.0, 1.0))
        nx = cx + math.cos(ang) * (r - 4)
        ny = cy - math.sin(ang) * (r - 4)
        p.setPen(QPen(self._color, 2))
        p.drawLine(QPointF(cx, cy), QPointF(nx, ny))
        p.setPen(QColor("#888888"))
        font = QFont("Segoe UI", 10)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, h * 0.55, w, h * 0.4), Qt.AlignCenter, self._text)


class DashLedWidget(QWidget):  # type: ignore[misc]
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "off"
        self._text = "--"
        self.setMinimumSize(120, 50)

    def set_state(self, state, text):
        self._state = state or "off"
        self._text = str(text)
        self.update()

    def paintEvent(self, _e):
        colors = {
            "ok": QColor("#32D74B"),
            "warn": QColor("#E6A23C"),
            "alarm": QColor("#E03131"),
            "off": QColor("#888888"),
        }
        c = colors.get(self._state, colors["off"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = min(28, self.height() - 8)
        x = 10
        y = (self.height() - d) // 2
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawEllipse(x, y, d, d)
        # soft glow ring
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 90), 3))
        p.drawEllipse(x - 2, y - 2, d + 4, d + 4)
        p.setPen(QColor("#CCCCCC") if self._state == "off" else c)
        font = QFont("Segoe UI", 12)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(x + d + 8, 0, self.width() - x - d - 16, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self._text)


class DashProgressWidget(QWidget):  # type: ignore[misc]
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ratio = 0.0
        self._text = "--"
        self._color = QColor("#4C8BF5")
        self.setMinimumSize(120, 40)

    def set_value(self, text, ratio, color):
        self._text = str(text)
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        margin = 8
        bar_h = 12
        y = self.height() // 2 - bar_h // 2 + 6
        track = QRectF(margin, y, self.width() - 2 * margin, bar_h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._color.red(), self._color.green(),
                          self._color.blue(), 40))
        p.drawRoundedRect(track, 6, 6)
        fill_w = track.width() * self._ratio
        if fill_w > 0:
            p.setBrush(self._color)
            p.drawRoundedRect(QRectF(track.x(), track.y(), fill_w, track.height()),
                              6, 6)
        p.setPen(self._color)
        font = QFont("Segoe UI", 10)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(margin, 2, self.width() - 2 * margin, y - 2),
                   Qt.AlignLeft | Qt.AlignVCenter, self._text)
