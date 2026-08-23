# -*- coding: utf-8 -*-
"""Global application QSS builder (theme-driven). B5 thin extract from CommTool.apply_style."""
from __future__ import annotations

from ui.theme import _mix


def build_app_qss(chrome, theme, tooltip_bg, tooltip_fg):
    """Build the main-window stylesheet string for chrome+terminal theme colors.

    ``chrome`` is ``chrome_for(theme_id)``; ``theme`` is a THEMES entry
    (needs ``bg`` / ``fg``). Tooltip colors come from ``term_vt.tooltip_colors``.
    """
    c = chrome
    t = theme
    return f"""
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
        QPushButton#GhostBtnSm {{
            background-color: {c['ghost_bg']};
            color: {c['accent']};
            border: 0px;
            border-radius: 7px;
            font-family: 'Segoe UI';
            font-size: 12px;
            font-weight: 500;
            padding: 3px 8px;
            min-height: 16px;
        }}
        QPushButton#GhostBtnSm:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#GhostBtnSm:pressed {{ background-color: {c['ghost_pressed']}; }}
        QPushButton#GhostBtn:checked {{ background-color: {c['accent']}; color: white; }}
        QPushButton#GhostBtn[arActive="true"] {{ background-color: {c['accent']}; color: white; }}
        QPushButton#GhostBtn[arActive="true"]:hover {{ background-color: {c['accent_hover']}; }}
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
        QFrame#QuickStartBar {{
            background-color: {c['ghost_bg']};
            border: 1px solid {c['separator']};
            border-radius: 8px;
        }}
        QLabel#QuickStartTitle {{
            color: {c['text_sec']};
            font-family: 'Segoe UI';
            font-size: 11px;
            font-weight: 600;
        }}
        QPushButton#QuickStartBtn {{
            background-color: {c['card_bg']};
            color: {c['accent']};
            border: 1px solid {c['separator']};
            border-radius: 6px;
            padding: 4px 9px;
            font-family: 'Segoe UI';
            font-size: 11px;
        }}
        QPushButton#QuickStartBtn:hover {{ background-color: {c['ghost_hover']}; }}
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
            background: {c['window_bg']};
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
            padding: 5px 9px;
            font-size: 12px;
            font-weight: 500;
        }}
        QWidget#TitleBar {{
            background-color: {c['window_bg']};
            border-bottom: 1px solid {c['separator']};
        }}
        QPushButton#CtrlBtn, QPushButton#CloseBtn {{
            background-color: transparent;
            color: {c['text']};       /* 自绘 paintEvent 读 palette.ButtonText 取此色 */
            border: 0px;              /* 必须两个 objectName 都覆盖，否则 CloseBtn 留默认边框 */
        }}
        QPushButton#CtrlBtn:hover {{ background-color: {c['title_btn_hover']}; }}
        QPushButton#CloseBtn:hover {{
            background-color: {c['danger']};
            color: #FFFFFF;
        }}
        QPushButton#TbHelpBtn {{
            background-color: transparent; color: {c['text']};
            border: 1px solid transparent; border-radius: 4px;
            padding: 1px 10px; font-family: 'Segoe UI'; font-size: 12px;
        }}
        QPushButton#TbHelpBtn:hover {{ background-color: {c['title_combo_hover']};
                                       border: 1px solid {c['separator']}; }}

        QWidget#WorkbenchBar {{
            background-color: {c['window_bg']};
            border-bottom: 1px solid {c['separator']};
        }}
        QLabel#WorkbenchLabel {{
            color: {c['text_sec']};
            background: transparent;
            padding-right: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#WorkbenchBtn {{
            background-color: transparent;
            color: {c['text']};
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 2px 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#WorkbenchBtn:hover {{
            background-color: {c['title_combo_hover']};
            border-color: {c['separator']};
        }}
        QPushButton#WorkbenchBtn:pressed {{
            background-color: {c['accent']};
            color: #FFFFFF;
        }}
        QPushButton#WorkbenchBtn[active="true"] {{
            background-color: {c['accent']}; color: #FFFFFF; font-weight: 600;
        }}
        QWidget#SessionTabBar {{
            background: transparent;
            border: 0px;
        }}
        QLabel#SessionStripLabel {{
            color: {c['text_sec']};
            background: transparent;
            border: 0px;
            font-size: 11px;
            font-weight: 500;
        }}
        QFrame#SessionSeparator {{
            color: {c['separator']};
            background-color: {c['separator']};
            max-width: 1px;
            margin: 4px 6px;
        }}
        QTabBar#SessionTabs {{
            background: transparent;
            border: 0px;
        }}
        QTabBar#SessionTabs::tab {{
            background: transparent;
            color: {c['text_sec']};
            border: 1px solid transparent;
            border-radius: 6px;
            min-height: 22px;
            padding: 2px 9px;
            margin: 1px;
            font-size: 12px;
        }}
        QTabBar#SessionTabs::tab:hover {{
            background-color: {c['title_combo_hover']};
            color: {c['text']};
        }}
        QTabBar#SessionTabs::tab:selected {{
            background-color: {c['accent']};
            color: #FFFFFF;
            border-color: {c['accent']};
            font-weight: 600;
        }}
        QTabBar#SessionTabs QAbstractButton#SessionCloseBtn {{
            background: transparent;
            border: 0px;
            border-radius: 5px;
            padding: 0px;
            margin: 0px 2px 0px 0px;
        }}
        QTabBar#SessionTabs QAbstractButton#SessionCloseBtn:hover {{
            background-color: rgba(255, 255, 255, 42);
        }}
        QPushButton#SessionAddBtn {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 7px;
            padding: 0px;
        }}
        QPushButton#SessionAddBtn:hover {{
            background-color: {c['title_combo_hover']};
            border-color: {c['separator']};
        }}
        QPushButton#SessionAddBtn:pressed {{
            background-color: {c['ghost_pressed']};
        }}
        QWidget#WorkspaceHost, QWidget#WorkspacePage {{ background-color: {c['window_bg']}; }}
        QLabel#WorkspacePageTitle {{
            color: {c['text']}; background: transparent;
            font-family: 'Segoe UI'; font-size: 22px; font-weight: 700;
        }}
        QLabel#WorkspacePageSubtitle {{
            color: {c['text_sec']}; background: transparent;
            font-family: 'Segoe UI'; font-size: 12px;
        }}
        QFrame#WorkspaceToolCard {{
            background-color: {c['card_bg']}; border: 1px solid {c['separator']};
            border-radius: 12px;
        }}
        QFrame#WorkspaceTemplatePanel {{
            background-color: {_mix(c['card_bg'], c['accent'], 0.05)};
            border: 1px solid {_mix(c['separator'], c['accent'], 0.25)};
            border-radius: 12px;
        }}
        QLabel#WorkspaceTemplatePreview {{
            color: {c['text_sec']}; background: transparent; border: 0px;
            font-family: 'Segoe UI'; font-size: 11px;
        }}
        QFrame#WorkspaceToolCard:hover {{
            background-color: {c['title_combo_hover']}; border-color: {c['accent']};
        }}
        QLabel#WorkspaceToolIcon {{
            background-color: {_mix(c['card_bg'], c['accent'], 0.14)};
            color: {c['accent']}; border: 0px; border-radius: 10px;
            font-family: 'Segoe UI Symbol', 'Segoe UI';
            font-size: 17px; font-weight: 700;
        }}
        QLabel#WorkspaceToolTitle {{
            color: {c['text']}; background: transparent; border: 0px;
            font-family: 'Segoe UI'; font-size: 14px; font-weight: 600;
        }}
        QLabel#WorkspaceStatusBadge {{
            background-color: {_mix(c['card_bg'], c['text_sec'], 0.12)};
            color: {c['text_sec']}; border: 0px; border-radius: 8px;
            padding: 2px 8px; font-family: 'Segoe UI'; font-size: 10px;
        }}
        QLabel#WorkspaceStatusBadge[active="true"] {{
            background-color: {_mix(c['card_bg'], '#34C759', 0.16)};
            color: #28A745; font-weight: 600;
        }}
        QPushButton#WorkspaceOpenBtn {{
            background-color: {c['accent']}; color: #FFFFFF; border: 0px;
            border-radius: 6px; padding: 2px 14px;
            font-family: 'Segoe UI'; font-size: 12px; font-weight: 600;
        }}
        QPushButton#WorkspaceOpenBtn:hover {{ background-color: {c['accent_hover']}; }}
        QFrame#WorkbenchSeparator {{
            color: {c['separator']};
            background-color: {c['separator']};
            max-width: 1px;
            margin: 4px 6px;
        }}
        QPushButton#ProjectBtn {{
            background-color: transparent;
            color: {c['text']};
            border: 1px solid {c['separator']};
            border-radius: 6px;
            padding: 2px 23px 2px 9px;
            font-size: 12px;
        }}
        QPushButton#ProjectBtn:hover {{
            background-color: {c['title_combo_hover']};
            border-color: {c['accent']};
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


def polish_widget_tree(root):
    """Force Qt to re-evaluate styles on ``root`` and all child widgets."""
    from PyQt5.QtWidgets import QWidget
    for w in root.findChildren(QWidget):
        w.style().unpolish(w)
        w.style().polish(w)
