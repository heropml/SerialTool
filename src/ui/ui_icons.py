# -*- coding: utf-8 -*-
"""Small code-drawn icons used by the application chrome."""
from PyQt5.QtCore import Qt, QLineF, QRectF
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def _canvas(size):
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(Qt.transparent)
    return pixmap


def plus_icon(color, size=16):
    pixmap = _canvas(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    center = size / 2.0
    radius = 4.25
    painter.drawLine(QLineF(center - radius, center, center + radius, center))
    painter.drawLine(QLineF(center, center - radius, center, center + radius))
    painter.end()
    return QIcon(pixmap)


def close_icon(color, size=12):
    pixmap = _canvas(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.35, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    start = 3.25
    end = size - start
    painter.drawLine(QLineF(start, start, end, end))
    painter.drawLine(QLineF(start, end, end, start))
    painter.end()
    return QIcon(pixmap)


def status_dot_icon(color, size=12):
    pixmap = _canvas(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    dot = 6.0
    offset = (size - dot) / 2.0
    painter.drawEllipse(QRectF(offset, offset, dot, dot))
    painter.end()
    return QIcon(pixmap)


def folder_icon(color, size=16):
    pixmap = _canvas(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    path = QRectF(2.25, 5.0, 11.5, 8.0)
    painter.drawRoundedRect(path, 1.5, 1.5)
    painter.drawLine(QLineF(3.1, 5.0, 3.1, 3.5))
    painter.drawLine(QLineF(3.1, 3.5, 7.0, 3.5))
    painter.drawLine(QLineF(7.0, 3.5, 8.3, 5.0))
    painter.end()
    return QIcon(pixmap)


def pin_icon(color, size=14, pinned=True):
    """图钉：``pinned`` 竖着=已固定，横着=自动隐藏（同 IDE 停靠面板的习惯）。"""
    pixmap = _canvas(size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    center = size / 2.0
    painter.translate(center, center)
    if not pinned:
        painter.rotate(90)
    painter.drawLine(QLineF(-3.2, -4.2, 3.2, -4.2))   # 钉帽
    painter.drawLine(QLineF(-2.2, -4.2, -2.2, 0.6))   # 左肩
    painter.drawLine(QLineF(2.2, -4.2, 2.2, 0.6))     # 右肩
    painter.drawLine(QLineF(-4.0, 0.6, 4.0, 0.6))     # 托盘
    painter.drawLine(QLineF(0.0, 0.6, 0.0, 4.6))      # 针
    painter.end()
    return QIcon(pixmap)
