# -*- coding: utf-8 -*-
"""Workspace / workbench / project-menu UI factories (Qt).

S-2 R42: CommTool thin wrappers for remaining build helpers.
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
    QVBoxLayout, QWidget, QWidgetAction,
)

from theme import chrome_for
from ui_tips import set_tooltip
from widgets import IOSSwitch


def build_protocol_template_panel(app):
    panel = QFrame()
    panel.setObjectName("WorkspaceTemplatePanel")
    layout = QHBoxLayout(panel)
    layout.setContentsMargins(18, 13, 14, 13)
    layout.setSpacing(12)
    icon = QLabel("T")
    icon.setObjectName("WorkspaceToolIcon")
    icon.setAlignment(Qt.AlignCenter)
    icon.setFixedSize(42, 42)
    layout.addWidget(icon)
    text_box = QVBoxLayout()
    text_box.setSpacing(2)
    title = QLabel(app._t("workspace_template_title"))
    title.setObjectName("WorkspaceToolTitle")
    title.setProperty("tr_text", "workspace_template_title")
    text_box.addWidget(title)
    app.lbl_workspace_template_preview = QLabel()
    app.lbl_workspace_template_preview.setObjectName("WorkspaceTemplatePreview")
    text_box.addWidget(app.lbl_workspace_template_preview)
    layout.addLayout(text_box, 1)
    app.cb_workspace_template = QComboBox()
    app.cb_workspace_template.setMinimumWidth(150)
    for text_key, template_id in app._workspace_template_options():
        app.cb_workspace_template.addItem(app._t(text_key), template_id)
    app.cb_workspace_template.currentIndexChanged.connect(
        app._update_workspace_template_preview)
    layout.addWidget(app.cb_workspace_template)
    apply_btn = QPushButton(app._t("workspace_template_apply"))
    apply_btn.setObjectName("WorkspaceOpenBtn")
    apply_btn.setProperty("tr_text", "workspace_template_apply")
    apply_btn.setFixedHeight(30)
    apply_btn.clicked.connect(app._apply_workspace_protocol_template)
    layout.addWidget(apply_btn)
    app._update_workspace_template_preview()
    return panel



def build_workspace_page(app, key):
    page = QWidget()
    page.setObjectName("WorkspacePage")
    outer = QVBoxLayout(page)
    outer.setContentsMargins(34, 28, 34, 28)
    outer.setSpacing(8)
    title = QLabel(app._t("wb_" + key))
    title.setObjectName("WorkspacePageTitle")
    title.setProperty("tr_text", "wb_" + key)
    outer.addWidget(title)
    subtitle_key = "workspace_" + key + "_tip"
    subtitle = QLabel(app._t(subtitle_key))
    subtitle.setObjectName("WorkspacePageSubtitle")
    subtitle.setProperty("tr_text", subtitle_key)
    subtitle.setWordWrap(True)
    outer.addWidget(subtitle)
    outer.addSpacing(16)
    if key == "protocol":
        outer.addWidget(build_protocol_template_panel(app))
        outer.addSpacing(8)
    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(14)
    for column in range(3):
        grid.setColumnStretch(column, 1)
    for index, (title_key, icon_text, callback) in enumerate(app._workspace_specs(key)):
        card = QFrame()
        card.setObjectName("WorkspaceToolCard")
        card.setMinimumHeight(86)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(12)
        icon = QLabel(icon_text)
        icon.setObjectName("WorkspaceToolIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(42, 42)
        card_layout.addWidget(icon, 0, Qt.AlignVCenter)
        tool_title = QLabel(app._t(title_key))
        tool_title.setObjectName("WorkspaceToolTitle")
        tool_title.setProperty("tr_text", title_key)
        tool_title.setWordWrap(True)
        card_layout.addWidget(tool_title, 1, Qt.AlignVCenter)
        status_badge = QLabel()
        status_badge.setObjectName("WorkspaceStatusBadge")
        status_badge.setProperty("tool_key", title_key)
        status_badge.setAlignment(Qt.AlignCenter)
        status_badge.hide()
        card_layout.addWidget(status_badge, 0, Qt.AlignVCenter)
        open_btn = QPushButton(app._t("workspace_open"))
        open_btn.setObjectName("WorkspaceOpenBtn")
        open_btn.setProperty("tr_text", "workspace_open")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setFixedHeight(30)
        open_btn.clicked.connect(lambda _checked=False, cb=callback: cb())
        card_layout.addWidget(open_btn, 0, Qt.AlignVCenter)
        grid.addWidget(card, index // 3, index % 3)
    outer.addLayout(grid)
    outer.addStretch(1)
    return page



def build_workbench_bar(app):
    """Top workbench nav: feature group menus + project menu."""
    bar = QWidget(app)
    bar.setObjectName("WorkbenchBar")
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(20, 5, 20, 5)
    layout.setSpacing(6)

    label = QLabel(app._t("workbench_label"))
    label.setObjectName("WorkbenchLabel")
    label.setProperty("tr_text", "workbench_label")
    layout.addWidget(label)

    app._workbench_buttons = {}
    for key in ("terminal", "protocol", "simulation", "automation", "data", "bridge"):
        btn = QPushButton(app._t("wb_" + key))
        btn.setObjectName("WorkbenchBtn")
        btn.setProperty("tr_text", "wb_" + key)
        btn.setProperty("active", "false")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(30)
        btn.clicked.connect(lambda _checked=False, k=key: app._switch_workspace(k))
        layout.addWidget(btn)
        app._workbench_buttons[key] = btn
    layout.addStretch(1)

    project_sep = QFrame()
    project_sep.setObjectName("WorkbenchSeparator")
    project_sep.setFrameShape(QFrame.VLine)
    layout.addWidget(project_sep)
    app.btn_project_menu = QPushButton(app._t("project_menu"))
    app.btn_project_menu.setObjectName("ProjectBtn")
    app.btn_project_menu.setCursor(Qt.PointingHandCursor)
    app.btn_project_menu.setFixedHeight(30)
    app.btn_project_menu.setMinimumWidth(76)
    app.btn_project_menu.setMaximumWidth(200)
    app.btn_project_menu.clicked.connect(app._show_project_menu)
    layout.addWidget(app.btn_project_menu)
    app._update_project_label()
    return bar



def build_project_menu(app):
    menu = QMenu(app)
    c = chrome_for(app._theme_id())
    menu.setStyleSheet(f"""
        QMenu {{ background-color: {c['card_bg']}; color: {c['text']};
                 border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px; }}
        QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
        QMenu::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
        QMenu::separator {{ height: 1px; background-color: {c['separator']};
                            margin: 5px 10px; }}
        QWidget#ProjectRestoreRow {{ background: transparent; border-radius: 5px; }}
        QLabel#ProjectRestoreLabel {{ color: {c['text']}; background: transparent;
                                       font-family: 'Segoe UI'; font-size: 12px; }}
    """)
    for text_key, callback in (("project_new", app.new_project),
                               ("project_open", app.open_project)):
        menu.addAction(app._t(text_key)).triggered.connect(
            lambda _checked=False, cb=callback: cb())
    recent = app._recent_projects()
    if recent:
        recent_menu = menu.addMenu(app._t("project_recent"))
        recent_menu.setToolTipsVisible(True)
        for path in recent:
            action = recent_menu.addAction(os.path.basename(path))
            set_tooltip(action, path)
            action.triggered.connect(
                lambda _checked=False, p=path: app._open_project_path(p))
        recent_menu.addSeparator()
        recent_menu.addAction(app._t("project_recent_clear")).triggered.connect(
            app._clear_recent_projects)
    menu.addSeparator()
    menu.addAction(app._t("project_save")).triggered.connect(
        lambda *_: app.save_project())
    menu.addAction(app._t("project_save_as")).triggered.connect(
        lambda *_: app.save_project(save_as=True))
    if app._project_name or app._project_path:
        menu.addSeparator()
        menu.addAction(app._t("project_close")).triggered.connect(
            lambda *_: app.close_project())
    menu.addSeparator()
    restore_action = QWidgetAction(menu)
    restore_row = QWidget()
    restore_row.setObjectName("ProjectRestoreRow")
    restore_layout = QHBoxLayout(restore_row)
    # QMenu 本身有 4px padding，普通菜单项另有 18px 左内边距。
    # QWidgetAction 的内容从 action 矩形起点直接布局，因此这里用 19px
    # （含 1px 的样式边界补偿），让文字起点与“新建 / 打开 / 保存”一致。
    restore_layout.setContentsMargins(19, 5, 10, 5)
    restore_layout.setSpacing(18)
    restore_label = QLabel(app._t("project_restore_on_startup"))
    restore_label.setObjectName("ProjectRestoreLabel")
    restore_layout.addWidget(restore_label, 1)
    restore_switch = IOSSwitch(
        app.settings.value("restore_last_project", True, type=bool))
    restore_switch.set_theme_colors(c['separator'], "#FFFFFF")
    restore_switch.toggled.connect(app._set_restore_last_project)
    restore_layout.addWidget(restore_switch)
    restore_action.setDefaultWidget(restore_row)
    menu.addAction(restore_action)
    return menu

