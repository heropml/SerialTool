import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from project_templates import DEVICE_IDS, PROTOCOL_IDS
from project_wizard import ProjectWizard
from dialogs import InfoDialog
from theme import chrome_for

_APP = QApplication.instance() or QApplication([])


def _texts():
    return {
        "title": "New Project",
        "default_name": "Untitled",
        "name": "Name",
        "device": "Device",
        "connection": "Connection",
        "protocol": "Protocol",
        "step_device": "Device",
        "step_device_tip": "Choose device",
        "step_connection": "Connection",
        "step_connection_tip": "Choose connection",
        "step_protocol": "Protocol",
        "step_protocol_tip": "Choose protocol",
        "step_display": "Display",
        "step_display_tip": "Choose views",
        "step_save": "Save",
        "step_save_tip": "Review",
        "view_terminal": "Terminal",
        "view_hex": "Hex",
        "view_timestamp": "Timestamp",
        "view_plot": "Plot",
        "view_dashboard": "Dashboard",
        "summary": "{name}/{device}/{connection}/{protocol}",
        "back": "上一步",
        "next": "下一步",
        "finish": "完成",
        "cancel": "取消",
        "device_types": list(DEVICE_IDS),
        "protocol_types": list(PROTOCOL_IDS),
    }


def _wizard():
    return ProjectWizard(_texts(), ["Serial", "UDP", "TCP Client"])


def test_wizard_has_five_pages_and_terminal_is_required():
    wizard = _wizard()
    try:
        assert len(wizard.pageIds()) == 5
        assert wizard.chk_terminal.isChecked()
        assert not wizard.chk_terminal.isEnabled()
    finally:
        wizard.close()


def test_wizard_uses_application_theme_instead_of_native_green_header():
    wizard = ProjectWizard(
        _texts(), ["Serial", "UDP", "TCP Client"], theme_id="dark")
    try:
        qss = wizard.styleSheet()
        assert "qt_wizard_header" in qss
        assert "WizardPrimaryBtn" in qss
        assert wizard.button(wizard.NextButton).objectName() == "WizardPrimaryBtn"
        assert wizard.buttonText(wizard.BackButton) == "上一步"
        assert wizard.buttonText(wizard.NextButton) == "下一步"
        assert "<" not in wizard.buttonText(wizard.BackButton)
        assert ">" not in wizard.buttonText(wizard.NextButton)
        assert wizard.buttonText(wizard.CancelButton) == "取消"
    finally:
        wizard.close()


def test_device_selection_updates_protocol_connection_and_views():
    wizard = _wizard()
    try:
        wizard.cb_device.setCurrentIndex(
            wizard.cb_device.findData("modbus"))

        assert wizard.cb_protocol.currentData() == "modbus_rtu"
        assert wizard.cb_connection.currentText() == "Serial"
        assert wizard.chk_hex.isChecked()
        assert wizard.chk_timestamp.isChecked()
    finally:
        wizard.close()


def test_protocol_selection_updates_connection_and_views():
    wizard = _wizard()
    try:
        wizard.cb_protocol.setCurrentIndex(
            wizard.cb_protocol.findData("modbus_tcp"))
        assert wizard.cb_connection.currentText() == "TCP Client"
        assert wizard.chk_hex.isChecked()

        wizard.cb_protocol.setCurrentIndex(wizard.cb_protocol.findData("at"))
        assert wizard.cb_connection.currentText() == "Serial"
        assert not wizard.chk_hex.isChecked()
    finally:
        wizard.close()


def test_result_data_uses_stable_ids_not_translated_labels():
    wizard = _wizard()
    try:
        wizard.ed_name.setText("Meter")
        wizard.cb_device.setCurrentIndex(
            wizard.cb_device.findData("modbus"))
        data = wizard.result_data()

        assert data["name"] == "Meter"
        assert data["device_type"] == "modbus"
        assert data["protocol_template"] == "modbus_rtu"
        assert data["views"]["terminal"] is True
    finally:
        wizard.close()


def test_themed_confirm_dialog_exposes_distinct_third_action():
    dialog = InfoDialog(
        "Unsaved", "Save changes?", ok_text="Save", confirm=True,
        cancel_text="Cancel", third_text="Don't Save", parent=None)
    try:
        dialog.btn_third.click()
        assert dialog.result() == InfoDialog.ThirdAction
    finally:
        dialog.close()


def test_manual_connection_survives_after_protocol_recommend():
    """User can override the recommended connection; template honors it."""
    wizard = ProjectWizard(
        _texts(), ["Serial", "UDP", "TCP Server", "TCP Client"])
    try:
        wizard.cb_protocol.setCurrentIndex(
            wizard.cb_protocol.findData("modbus_tcp"))
        assert wizard.cb_connection.currentText() == "TCP Client"
        wizard.cb_connection.setCurrentText("TCP Server")
        data = wizard.result_data()
        assert data["connection_type"] == "TCP Server"
        from project_templates import protocol_template_settings
        cfg = protocol_template_settings(
            data["protocol_template"], data["connection_type"])
        assert cfg["net_proto"] == "TCP Server"
    finally:
        wizard.close()


def test_device_change_keeps_views_when_protocol_unchanged():
    wizard = _wizard()
    try:
        # Ensure protocol is raw, tick plot, switch to another device that also uses raw.
        wizard.cb_device.setCurrentIndex(wizard.cb_device.findData("generic"))
        assert wizard.cb_protocol.currentData() == "raw"
        wizard.chk_plot.setChecked(True)
        wizard.cb_device.setCurrentIndex(wizard.cb_device.findData("network"))
        assert wizard.cb_protocol.currentData() == "raw"
        assert wizard.chk_plot.isChecked()
    finally:
        wizard.close()

def test_whitespace_name_is_incomplete_until_real_text():
    wizard = _wizard()
    try:
        page = wizard.page(wizard.pageIds()[0])
        wizard.ed_name.setText("   ")
        assert not page.isComplete()
        wizard.ed_name.setText("Meter")
        assert page.isComplete()
    finally:
        wizard.close()


def test_discard_third_button_is_neutral_not_danger():
    dialog = InfoDialog(
        "Unsaved", "Save changes?", ok_text="Save", confirm=True,
        cancel_text="Cancel", third_text="Don't Save", parent=None)
    try:
        assert dialog.btn_third.objectName() == "DialogGhostBtn"
    finally:
        dialog.close()


def test_info_dialog_warning_uses_warning_icon_and_color():
    dialog = InfoDialog("Unsaved", "Save changes?", is_warning=True,
                        theme_id="dark", parent=None)
    try:
        icon = dialog.findChild(QLabel, "DialogStatusIcon")
        assert icon is not None
        assert icon.text() == "!"
        assert chrome_for("dark")["warning"] in icon.styleSheet()
    finally:
        dialog.close()
