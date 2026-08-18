# -*- coding: utf-8 -*-
"""Five-step new-project wizard. Collects intent; main window applies it."""

from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
    QWizard, QWizardPage,
)
from ui.fonts import localize_qss
from project.project_templates import (
    DEVICE_IDS, PROTOCOL_IDS, recommended_connection,
    recommended_device_connection, recommended_protocol, recommended_views,
)
from ui.theme import THEME_DEFAULT, chrome_for


class ProjectWizard(QWizard):
    def __init__(self, texts, connection_types, parent=None, theme_id=None):
        super().__init__(parent)
        self._t = texts
        self._theme_id = theme_id or THEME_DEFAULT
        self.setWindowTitle(texts["title"])
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(620, 430)

        self.ed_name = QLineEdit(texts["default_name"])
        self.cb_device = QComboBox()
        for label, value in zip(texts["device_types"], DEVICE_IDS):
            self.cb_device.addItem(label, value)
        self.addPage(self._device_page())

        self.cb_connection = QComboBox()
        self.cb_connection.addItems(connection_types)
        self.addPage(self._connection_page())

        self.cb_protocol = QComboBox()
        for label, value in zip(texts["protocol_types"], PROTOCOL_IDS):
            self.cb_protocol.addItem(label, value)
        self.cb_protocol.currentIndexChanged.connect(self._sync_protocol_defaults)
        self.addPage(self._protocol_page())

        self.chk_terminal = QCheckBox(texts["view_terminal"])
        self.chk_terminal.setChecked(True)
        # Terminal log is always on; keep the checkbox checked and disabled.
        self.chk_terminal.setEnabled(False)
        self.chk_hex = QCheckBox(texts["view_hex"])
        self.chk_timestamp = QCheckBox(texts["view_timestamp"])
        self.chk_timestamp.setChecked(True)
        self.chk_plot = QCheckBox(texts["view_plot"])
        self.chk_dashboard = QCheckBox(texts["view_dashboard"])
        self.addPage(self._display_page())

        self.lbl_summary = QLabel()
        self.lbl_summary.setWordWrap(True)
        self.addPage(self._summary_page())
        self.currentIdChanged.connect(self._refresh_summary)

        self.cb_device.currentIndexChanged.connect(self._sync_device_defaults)
        self._sync_device_defaults()

        self.setButtonText(self.BackButton, texts["back"])
        self.setButtonText(self.NextButton, texts["next"])
        self.setButtonText(self.FinishButton, texts["finish"])
        self.setButtonText(self.CancelButton, texts["cancel"])
        self.button(self.NextButton).setObjectName("WizardPrimaryBtn")
        self.button(self.FinishButton).setObjectName("WizardPrimaryBtn")
        self._apply_theme()

    def _apply_theme(self):
        c = chrome_for(self._theme_id)
        self.setStyleSheet(localize_qss(f"""
        QWizard {{
            background-color: {c['window_bg']};
            color: {c['text']};
        }}
        QWizard QWidget {{
            color: {c['text']};
            background-color: transparent;
        }}
        QWizard QLabel {{
            color: {c['text']};
        }}
        QWizard QLineEdit, QWizard QComboBox {{
            background-color: {c['input_bg']};
            color: {c['text']};
            border: 1px solid {c['separator']};
            border-radius: 6px;
            padding: 4px 8px;
            min-height: 26px;
        }}
        QWizard QComboBox::drop-down {{
            border: 0px;
            width: 22px;
        }}
        QWizard QCheckBox {{
            color: {c['text']};
            spacing: 8px;
        }}
        QWizard QCheckBox::indicator {{
            width: 16px;
            height: 16px;
        }}
        QFrame#qt_wizard_header {{
            background-color: {c['card_bg']};
            border: 0px;
            border-bottom: 1px solid {c['separator']};
        }}
        QLabel#qt_wizard_title {{
            color: {c['text']};
            font-size: 16px;
            font-weight: 600;
        }}
        QLabel#qt_wizard_subtitle {{
            color: {c['text_sec']};
        }}
        QPushButton {{
            background-color: {c['ghost_bg']};
            color: {c['text']};
            border: 1px solid {c['separator']};
            border-radius: 6px;
            padding: 5px 14px;
            min-height: 28px;
        }}
        QPushButton:hover {{
            background-color: {c['ghost_hover']};
        }}
        QPushButton:pressed {{
            background-color: {c['ghost_pressed']};
        }}
        QPushButton#WizardPrimaryBtn {{
            background-color: {c['accent']};
            color: #FFFFFF;
            border: 1px solid {c['accent']};
        }}
        QPushButton#WizardPrimaryBtn:hover {{
            background-color: {c['accent_hover']};
        }}
        QPushButton#WizardPrimaryBtn:pressed {{
            background-color: {c['accent_pressed']};
        }}
        QPushButton#WizardPrimaryBtn:disabled {{
            background-color: {c['separator']};
            color: {c['text_sec']};
        }}
        """))
        for combo in self.findChildren(QComboBox):
            try:
                combo.view().window().setStyleSheet(
                    f"background-color: {c['combo_dropdown_bg']};")
            except (AttributeError, RuntimeError):
                pass

    def _page(self, title, subtitle):
        page = QWizardPage()
        page.setTitle(title)
        page.setSubTitle(subtitle)
        return page

    def _device_page(self):
        p = self._page(self._t["step_device"], self._t["step_device_tip"])
        form = QFormLayout(p)
        form.addRow(self._t["name"], self.ed_name)
        form.addRow(self._t["device"], self.cb_device)
        p.registerField("projectName*", self.ed_name)
        # Spaces-only is not a real name; block Next until strip() is non-empty.
        p.isComplete = lambda: bool(self.ed_name.text().strip())  # type: ignore
        self.ed_name.textChanged.connect(lambda *_: p.completeChanged.emit())
        return p

    def _connection_page(self):
        p = self._page(self._t["step_connection"], self._t["step_connection_tip"])
        form = QFormLayout(p)
        form.addRow(self._t["connection"], self.cb_connection)
        return p

    def _protocol_page(self):
        p = self._page(self._t["step_protocol"], self._t["step_protocol_tip"])
        form = QFormLayout(p)
        form.addRow(self._t["protocol"], self.cb_protocol)
        return p

    def _display_page(self):
        p = self._page(self._t["step_display"], self._t["step_display_tip"])
        layout = QVBoxLayout(p)
        for chk in (self.chk_terminal, self.chk_hex, self.chk_timestamp,
                    self.chk_plot, self.chk_dashboard):
            layout.addWidget(chk)
        layout.addStretch(1)
        return p

    def _summary_page(self):
        p = self._page(self._t["step_save"], self._t["step_save_tip"])
        layout = QVBoxLayout(p)
        layout.addWidget(self.lbl_summary)
        layout.addStretch(1)
        return p

    def _refresh_summary(self, page_id):
        if page_id != self.pageIds()[-1]:
            return
        self.lbl_summary.setText(self._t["summary"].format(
            name=self.ed_name.text().strip(),
            device=self.cb_device.currentText(),
            connection=self.cb_connection.currentText(),
            protocol=self.cb_protocol.currentText(),
        ))

    def _sync_protocol_defaults(self, *_):
        protocol_id = self.cb_protocol.currentData() or "raw"
        wanted = recommended_connection(protocol_id, self.cb_connection.currentText())
        idx = self.cb_connection.findText(wanted)
        if idx >= 0:
            self.cb_connection.setCurrentIndex(idx)
        views = recommended_views(protocol_id)
        self.chk_hex.setChecked(views["hex"])
        self.chk_timestamp.setChecked(views["timestamp"])
        self.chk_plot.setChecked(views["plot"])
        self.chk_dashboard.setChecked(views["dashboard"])

    def _sync_device_defaults(self, *_):
        device_id = self.cb_device.currentData() or "generic"
        protocol_id = recommended_protocol(device_id)
        old_protocol = self.cb_protocol.currentData()
        idx = self.cb_protocol.findData(protocol_id)
        if idx >= 0:
            # Block signals so views reset only when protocol actually changes.
            self.cb_protocol.blockSignals(True)
            self.cb_protocol.setCurrentIndex(idx)
            self.cb_protocol.blockSignals(False)
            # Only sync views/connection from the protocol that is actually selected.
            if protocol_id != old_protocol:
                self._sync_protocol_defaults()
        wanted = recommended_device_connection(
            device_id, self.cb_connection.currentText())
        conn_idx = self.cb_connection.findText(wanted)
        if conn_idx >= 0:
            self.cb_connection.setCurrentIndex(conn_idx)

    def result_data(self):
        return {
            "name": self.ed_name.text().strip(),
            "device_type": self.cb_device.currentData(),
            "device_label": self.cb_device.currentText(),
            "connection_type": self.cb_connection.currentText(),
            "protocol_template": self.cb_protocol.currentData(),
            "protocol_label": self.cb_protocol.currentText(),
            "views": {
                "terminal": True,
                "hex": self.chk_hex.isChecked(),
                "timestamp": self.chk_timestamp.isChecked(),
                "plot": self.chk_plot.isChecked(),
                "dashboard": self.chk_dashboard.isChecked(),
            },
        }
