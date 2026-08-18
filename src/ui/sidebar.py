# -*- coding: utf-8 -*-
"""Left sidebar factory (Qt).

S-2 R41: assemble settings / data-options / send-options cards.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget


def build(app):
    """Build the scrollable left sidebar hosting the three option cards."""
    host = QWidget()
    host.setObjectName("SidebarHost")
    v = QVBoxLayout(host)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(10)
    v.addWidget(app.build_settings_card())
    v.addWidget(app.build_data_options_card(), 1)
    app._left_send_card = app.build_send_options_card()
    v.addWidget(app._left_send_card)

    scroll = QScrollArea()
    scroll.setWidget(host)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setObjectName("Sidebar")
    scroll.setMinimumWidth(305)
    scroll.setMaximumWidth(380)
    return scroll
