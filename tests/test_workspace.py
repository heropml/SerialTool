import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication, QLabel, QDialog, QWidgetAction

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main_window import CommTool, PortScannerThread
from ui.device_center_dialog import DeviceCenterDialog, _REGISTER_COLUMNS
from ui.plot_dialog import PlotDialog
from project.project_model import load_project, make_project, save_project
from ui.widgets import IOSSwitch


_APP = QApplication.instance() or QApplication([])


def _patch_window_runtime(monkeypatch, settings_path, notices):
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(settings_path)))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: notices.append(
            (title, body, is_error)))


def _search_text(window, text):
    """输入搜索词并同步触发搜索（B1 打字防抖在无事件循环的测试里不自动触发）。"""
    window.ed_search.setText(text)
    window._search_debounce.timeout.emit()


def test_workspace_pages_and_tool_icons_initialize(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("workspace-test")
    try:
        _APP.processEvents()
        icons = window.findChildren(QLabel, "WorkspaceToolIcon")
        assert window.workspace_stack.count() == 6
        assert len(icons) == 18  # includes I/O Graph entry under data tools
        assert len({icon.text() for icon in icons}) >= 12
        assert window.btn_xfer.text() == window._t("xfer_title")
        assert window.cb_workspace_template.count() == 8
        assert "device_title" in {item[0] for item in window._workspace_specs("protocol")}
        data_keys = {item[0] for item in window._workspace_specs("data")}
        assert "structured_title" in data_keys
        assert "plot_io_graph" in data_keys
        tcp_index = window.cb_workspace_template.findData("modbus_tcp")
        window.cb_workspace_template.setCurrentIndex(tcp_index)
        assert "TCP Client" in window.lbl_workspace_template_preview.text()

        window._switch_workspace("protocol", persist=False)
        assert window._active_workspace == "protocol"
        assert window._workbench_buttons["protocol"].property("active") == "true"

        status_badges = window.findChildren(QLabel, "WorkspaceStatusBadge")
        modbus_badge = next(
            badge for badge in status_badges if badge.property("tool_key") == "mbm_open")
        assert not modbus_badge.isHidden()
        assert modbus_badge.text() == window._t("workspace_inactive")
        window._mbm_on = True
        window._refresh_workspace_statuses()
        assert modbus_badge.text() == window._t("workspace_enabled")
        assert modbus_badge.property("active") == "true"

        menu = window._build_project_menu()
        custom_actions = [action for action in menu.actions()
                          if isinstance(action, QWidgetAction) and action.defaultWidget()]
        assert len(custom_actions) == 1
        restore_row = custom_actions[0].defaultWidget()
        assert restore_row.findChild(IOSSwitch) is not None
        # QWidgetAction 不会继承 QMenu::item 的 18px 文本内边距；自定义行需
        # 自己补齐，避免“启动时恢复上次工程”比普通菜单项向左偏。
        assert restore_row.layout().contentsMargins().left() == 19
        menu.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_switch_workspace_ignores_missing_page_index(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("workspace-missing-index-test")
    try:
        _APP.processEvents()
        previous_index = window.workspace_stack.currentIndex()
        previous_workspace = window._active_workspace
        monkeypatch.setattr(window, "_workspace_page_indexes", {})

        window._switch_workspace("protocol")

        assert window.workspace_stack.currentIndex() == previous_index
        assert window._active_workspace == previous_workspace
        assert notices == []
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_switch_workspace_invalid_key_falls_back_to_terminal(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("workspace-invalid-key-test")
    try:
        _APP.processEvents()
        window._switch_workspace("not-a-workspace", persist=False)
        assert window._active_workspace == "terminal"
        assert window.workspace_stack.currentIndex() == window._workspace_page_indexes["terminal"]
        assert window._workbench_buttons["terminal"].property("active") == "true"
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_device_scan_temporarily_reuses_and_restores_modbus_engine(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("device-scan-test")
    updates = []
    done = []
    try:
        _APP.processEvents()
        old_rules = [{"enabled": True, "name": "old", "unit": 1,
                      "func": 3, "addr": 0, "qty": 1, "period": 1000}]
        window._mbm_rules = old_rules
        window._mbm_results = {5: {"status": "ok", "text": "before scan"}}
        window._mbm_on = True
        window.active_session()._mbm_enabled = True
        window.settings.setValue("modbus_master", "persisted-rules")
        window.settings.setValue("modbus_master_on", True)
        window.settings.setValue("modbus_master_variant", "rtu")
        window.settings.setValue("modbus_master_echo", True)
        window.settings.sync()
        monkeypatch.setattr(window, "_is_open", lambda: True)
        monkeypatch.setattr(window, "_mbm_connection_ready", lambda: True)
        busy_calls = []
        monkeypatch.setattr(
            window, "_io_task_busy",
            lambda exclude=(): busy_calls.append(tuple(exclude)) or
            ("modbus" not in exclude))
        monkeypatch.setattr(window, "_mbm_restart", lambda: None)
        rules = [
            {"enabled": True, "unit": 1, "func": 3, "addr": 0, "qty": 1,
             "period": 0x7FFFFFFF},
            {"enabled": True, "unit": 2, "func": 3, "addr": 0, "qty": 1,
             "period": 0x7FFFFFFF},
        ]
        assert window._start_device_scan(
            rules, 250, lambda *args: updates.append(args),
            lambda cancelled: done.append(cancelled)) is True
        assert window._device_scan_timeout_ms == 250
        assert window._mbm_on is True
        assert window._mbm_rules is old_rules
        assert window._mbm_poll_rules() is not old_rules
        assert busy_calls == [("modbus",)]
        window._mbm_results[5]["text"] = "mutated during scan"

        # Scan no longer hijacks window rules; enable switch still blocked.
        window._set_mbm_enabled(False)
        assert window._mbm_rules is old_rules
        assert window._mbm_on is True

        window._device_scan_result(0, "ok", "1")
        window._device_scan_result(1, "timeout", "timeout")
        _APP.processEvents()

        assert [item[1] for item in updates] == ["ok", "timeout"]
        assert done == [False]
        assert window._device_scan_state is None
        assert window._mbm_rules is old_rules
        assert window._mbm_on is True
        assert window._mbm_results == {5: {"status": "ok", "text": "before scan"}}
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_device_scan_temporarily_disables_autoreply(tmp_path, monkeypatch):
    """扫描与主机互斥：接管时临时关闭自动应答从机，结束后恢复——
    否则 _mbm_on && _ar_on 双开破坏「开主机必关从机」不变量。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("scan-ar-test")
    updates, done = [], []
    try:
        _APP.processEvents()
        window._ar_on = True
        window.active_session()._ar_enabled = True
        window._mbm_on = False
        window.settings.setValue("autoreply_on", True)
        window._mbm_rules = [{"enabled": True, "name": "old", "unit": 1,
                              "func": 3, "addr": 0, "qty": 1, "period": 1000}]
        window.settings.setValue("modbus_master", "persisted-rules")
        window.settings.setValue("modbus_master_on", False)
        window._mbm_connection_ready = lambda: True
        monkeypatch.setattr(window, "_is_open", lambda: True)
        monkeypatch.setattr(window, "_io_task_busy", lambda exclude=(): ("modbus" not in exclude))
        monkeypatch.setattr(window, "_mbm_restart", lambda: None)
        rules = [{"enabled": True, "unit": 1, "func": 3, "addr": 0, "qty": 1,
                  "period": 0x7FFFFFFF}]
        assert window._start_device_scan(
            rules, 250, lambda *a: updates.append(a),
            lambda c: done.append(c)) is True
        # 扫描接管：从机被临时关掉，主机开启
        assert window._ar_on is False
        assert window.btn_autoreply.property("arActive") == "false"
        assert window._mbm_on is True
        window._device_scan_result(0, "ok", "1")
        _APP.processEvents()
        # 扫描结束：从机恢复
        assert window._ar_on is True
        assert window.btn_autoreply.property("arActive") == "true"
        assert window._mbm_on is False
        assert window.settings.value("autoreply_on", type=bool) is True
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_structured_record_collects_modbus_and_protocol_fields(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("structured-record-test")
    try:
        _APP.processEvents()
        window._device_registers = [{
            "name": "voltage", "slave": 1, "function": 3,
            "address": 0, "type": "u16", "scale": 0.1, "unit": "V",
        }]
        window.settings.setValue("frame_rules", "AA | cmd=1:u8")
        window._structured_recorder.start(clear=True)
        window._structured_feed_modbus(
            {"unit": 1, "func": 3, "addr": 0}, {"regs": [330]})
        window._structured_feed_protocol(bytes.fromhex("AA 05"))

        rows = window._structured_recorder.rows
        assert [(row["source"], row["tag"]) for row in rows] == [
            ("modbus", "voltage"), ("protocol", "cmd")]
        assert rows[0]["value"] == 33
        assert rows[1]["value"] == 5
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_protocol_frame_mode_splits_sticky_and_split_rx(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("stream-frame-sticky-test")
    try:
        _APP.processEvents()
        window.settings.setValue("frame_rules", "AABB | cmd=3:u8")
        window._proto_rules_raw = None
        window._set_stream_frame({
            "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
            "len_extra": 3,
        })
        window._structured_recorder.start(clear=True)
        # extra=3: AA BB | len | cmd ; L=1 → 4-byte frames
        window.on_data_received(bytes.fromhex("AA BB 01 05 AA BB 01 06"))
        vals = [row["value"] for row in window._structured_recorder.rows
                if row.get("source") == "protocol"]
        assert vals == [5, 6]

        window._structured_recorder.clear()
        window._structured_recorder.start(clear=True)
        window._reset_stream_frames_all(reset_diag=True)
        window.on_data_received(bytes.fromhex("AA BB 01"))
        assert window._structured_recorder.rows == []
        window.on_data_received(bytes.fromhex("07"))
        vals = [row["value"] for row in window._structured_recorder.rows
                if row.get("source") == "protocol"]
        assert vals == [7]
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_protocol_frame_mode_isolates_sessions_and_clears_on_close(
        tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("stream-frame-session-test")
    try:
        _APP.processEvents()
        window._set_stream_frame({
            "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
            "len_extra": 3,
        })
        first = window.active_session()
        second = window.add_session(activate=False)
        half = bytes.fromhex("AA BB 01")
        full = bytes.fromhex("AA BB 01 05")
        with window._with_session(first):
            assert window._analysis_rx_units(half) == []
        with window._with_session(second):
            assert window._analysis_rx_units(full) == [full]
        with window._with_session(first):
            assert window._analysis_rx_units(bytes.fromhex("05")) == [full]
            assert window._analysis_rx_units(half) == []
            window.close_conn(update_ui=False)
            assert window._analysis_rx_units(bytes.fromhex("05")) == []
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_tcp_server_client_disconnect_drops_half_frame(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("stream-frame-client-drop")
    try:
        _APP.processEvents()
        from ui.conn_ui import PROTO_TCP_SERVER
        window._set_stream_frame({
            "on": True, "header": "AA BB", "len_off": 2, "len_width": 1,
            "len_extra": 3,
        })
        window._conn_proto = PROTO_TCP_SERVER
        peer = ("10.0.0.8", 5000)
        half = bytes.fromhex("AA BB 01")
        full = bytes.fromhex("AA BB 01 05")
        with window._with_session(window.active_session()):
            assert window._analysis_rx_units(half, source=peer) == []
            window._on_clients_changed([])
            assert window._analysis_rx_units(bytes.fromhex("05"), source=peer) == []
            assert window._analysis_rx_units(full, source=peer) == [full]
        background = window.add_session(activate=False)
        with window._with_session(background):
            window._conn_proto = PROTO_TCP_SERVER
            assert window._analysis_rx_units(half, source=peer) == []
        window._route_session_clients(background.id, [])
        with window._with_session(background):
            assert window._analysis_rx_units(bytes.fromhex("05"), source=peer) == []
            assert window._analysis_rx_units(full, source=peer) == [full]
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_structured_modbus_ignores_device_scan_and_survives_decode_error(
        tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("structured-scan-isolation-test")
    try:
        _APP.processEvents()
        window._device_registers = [{
            "name": "voltage", "slave": 1, "function": 3,
            "address": 0, "type": "u16",
        }]
        window._structured_recorder.start(clear=True)
        window._device_scan_state = {"active": True}
        window._structured_feed_modbus(
            {"unit": 1, "func": 3, "addr": 0}, {"regs": [330]})
        assert window._structured_recorder.rows == []

        window._device_scan_state = None
        from project import device_resources
        monkeypatch.setattr(
            device_resources, "decode_modbus_samples",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("bad decode")))
        window._structured_feed_modbus(
            {"unit": 1, "func": 3, "addr": 0}, {"regs": [330]})
        assert window._structured_recorder.rows == []

        results = []
        info = {"i": 0, "unit": 1, "func": 3, "addr": 0, "qty": 1,
                "variant": "tcp", "exp_write": None}
        window._mbm_inflight = dict(info)
        monkeypatch.setattr(window, "_mbm_set_result",
                            lambda *args: results.append(args))
        window._mbm_apply(info, {"regs": [330]})
        assert results and results[0][1] == "ok"
        assert window._mbm_inflight is None
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_device_and_structured_dialogs_open_from_workspace(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("resource-dialog-test")
    try:
        _APP.processEvents()
        window._open_device_center()
        window._open_structured_record()
        _APP.processEvents()

        assert window._device_center_dlg.tabs.count() == 2
        assert (window._device_center_dlg.table.columnCount()
                == len(_REGISTER_COLUMNS))
        assert window._structured_dlg.table.columnCount() == 7   # 末列是阈值级别
        assert window._structured_dlg.btn_help.objectName() == "PlotHelpBtn"
        assert window._device_center_dlg.btn_help.objectName() == "PlotHelpBtn"
        assert window._device_center_dlg.windowTitle() == window._t("device_title")
        assert window._structured_dlg.windowTitle() == window._t("structured_title")

        started = []
        toasts = []
        monkeypatch.setattr(window, "_start_device_scan",
                            lambda *args: started.append(args) or True)
        monkeypatch.setattr(window, "toast",
                            lambda text, error=False: toasts.append((text, error)))
        dialog = window._device_center_dlg
        dialog.cb_scan_mode.setCurrentIndex(
            dialog.cb_scan_mode.findData("register"))
        dialog.sp_scan_start.setValue(0)
        dialog.sp_scan_end.setValue(512)
        dialog._start_scan()
        assert started == []
        assert toasts == [(window._t("device_scan_too_large", limit=512), True)]

        dialog.sp_scan_end.setValue(1)
        dialog._start_scan()
        dialog._scan_update(0, "timeout", "detail")
        assert dialog.scan_table.item(0, 2).text() == window._t("mbm_st_timeout")
        assert dialog.scan_progress.value() == 1
        monkeypatch.setattr(window, "_t", lambda key, **_kwargs: "tr:" + key)
        dialog.retranslate()
        assert dialog.scan_table.item(0, 2).text() == "tr:mbm_st_timeout"
        assert dialog.scan_progress.value() == 1
    finally:
        for dialog in (window._device_center_dlg, window._structured_dlg):
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
        window._device_center_dlg = None
        window._structured_dlg = None
        window.deleteLater()
        _APP.processEvents()


def test_scan_results_merge_by_register_identity(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("scan-merge-test")
    dialog = None
    try:
        _APP.processEvents()
        window._open_device_center()
        dialog = window._device_center_dlg
        dialog.cb_scan_mode.setCurrentIndex(dialog.cb_scan_mode.findData("register"))
        dialog._append_register({"name": "old", "slave": 1, "function": 3,
                                 "address": 10})
        dialog._scan_rows = [
            {"name": "R10", "unit": 1, "func": 3, "addr": 10},
            {"name": "R11", "unit": 1, "func": 3, "addr": 11},
        ]
        dialog._scan_ok = [0, 1]
        dialog._add_scan_results()
        dialog._add_scan_results()
        records = dialog._collect_registers()
        assert len(records) == 2
        assert [(r["slave"], r["function"], r["address"], r["name"])
                for r in records] == [(1, 3, 10, "R10"), (1, 3, 11, "R11")]
    finally:
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
        window.deleteLater()
        _APP.processEvents()


def test_scan_merge_preserves_custom_register_metadata():
    """扫描合并同址时只更新身份字段，保留用户自定义 type/scale/unit——
    否则 u32/scale 0.1 会被扫描结果的默认 u16/1.0 冲掉，联动解码读数失真。"""
    existing = [{"name": "voltage", "slave": 1, "function": 3, "address": 10,
                 "type": "u32", "scale": 0.1, "unit": "V"}]
    scanned = [{"name": "R10", "slave": 1, "function": 3, "address": 10},
               {"name": "R11", "slave": 1, "function": 3, "address": 11}]
    merged = DeviceCenterDialog._merge_scan_registers(existing, scanned)
    assert len(merged) == 2
    # 同址 (1,3,10)：元数据保留，name 被扫描结果更新
    r10 = next(r for r in merged if r["address"] == 10)
    assert r10["name"] == "R10"
    assert r10["type"] == "u32" and r10["scale"] == 0.1 and r10["unit"] == "V"
    # 新地址 (1,3,11)：扫描结果建新行（默认 u16）
    r11 = next(r for r in merged if r["address"] == 11)
    assert r11["type"] == "u16"


def test_scan_merge_collapses_existing_duplicate_registers():
    """扫描合并应清理旧配置中已有的同身份重复行，保留第一条用户元数据。"""
    existing = [
        {"name": "first", "slave": 1, "function": 3, "address": 10,
         "type": "u32", "scale": 0.1, "unit": "V"},
        {"name": "duplicate", "slave": 1, "function": 3, "address": 10,
         "type": "i16", "scale": 2, "unit": "bad"},
    ]
    merged = DeviceCenterDialog._merge_scan_registers(
        existing, [{"name": "R10", "slave": 1, "function": 3, "address": 10}])
    assert len(merged) == 1
    assert merged[0]["name"] == "R10"
    assert merged[0]["type"] == "u32"
    assert merged[0]["scale"] == 0.1
    assert merged[0]["unit"] == "V"


def test_main_window_project_save_packs_workspace_resources(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("project-resource-save-test")
    project_path = tmp_path / "resources.ctproj"
    try:
        _APP.processEvents()
        window._project_path = str(project_path)
        window._project_name = "Resources"
        window._device_registers = [{"name": "temp", "address": 5}]
        window.settings.setValue(
            "device_registers", json.dumps(window._device_registers, ensure_ascii=False))
        window._device_plot_tags = {"temp"}
        window._device_dash_tags = set()
        window._save_device_link()
        window._snippets = [{"name": "read", "text": "01 03", "hex": True}]
        window._save_snippets()
        window.settings.setValue("sequence_rules", json.dumps([{"send": "AT"}]))
        window.settings.setValue(
            "script_lib", json.dumps([{"name": "check", "code": "log('ok')"}]))
        window.settings.setValue("dash_fields", "temp=5:u16be")
        window.settings.sync()

        assert window.save_project() is True
        payload = load_project(str(project_path))

        assert payload["resources"]["device"]["registers"][0]["name"] == "temp"
        assert payload["resources"]["device"]["plot_tags"] == ["temp"]
        assert payload["resources"]["send"]["snippets"][0]["name"] == "read"
        assert payload["resources"]["automation"]["sequences"][0]["send"] == "AT"
        assert payload["resources"]["automation"]["scripts"][0]["name"] == "check"
        assert payload["resources"]["dashboard"]["dash_fields"] == "temp=5:u16be"
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_protocol_template_can_be_applied_to_current_workspace(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("template-apply-test")
    try:
        _APP.processEvents()
        monkeypatch.setattr(window, "_confirm_dlg", lambda *args, **kwargs: True)
        monkeypatch.setattr(window, "_prepare_project_switch", lambda: True)
        index = window.cb_workspace_template.findData("modbus_rtu")
        window.cb_workspace_template.setCurrentIndex(index)
        window._apply_workspace_protocol_template()

        assert window.settings.value("net_proto") == "Serial"
        assert window.settings.value("rx_hex", False, type=bool) is True
        assert window.settings.value("tx_hex", False, type=bool) is True
        assert int(window.settings.value("checksum_idx")) == 5
        assert notices == []
    finally:
        window.deleteLater()
        _APP.processEvents()


@pytest.mark.parametrize("template_id", ["raw", "at", "nmea"])
def test_protocol_template_clears_legacy_frame_rules(
        tmp_path, monkeypatch, template_id):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool(f"template-clear-{template_id}-test")
    try:
        _APP.processEvents()
        window.settings.setValue("frame_rules", "AA 55 | old=2:u8")
        window.settings.setValue("frame_header", "AA 55")
        window.settings.setValue("frame_fields", "cmd=2:u8")
        window.settings.sync()
        monkeypatch.setattr(window, "_confirm_dlg", lambda *args, **kwargs: True)
        monkeypatch.setattr(window, "_prepare_project_switch", lambda: True)

        index = window.cb_workspace_template.findData(template_id)
        window.cb_workspace_template.setCurrentIndex(index)
        window._apply_workspace_protocol_template()

        assert window.settings.value("frame_rules", "") == ""
        assert not window.settings.contains("frame_header")
        assert not window.settings.contains("frame_fields")
        assert notices == []
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_protocol_template_apply_rolls_back_on_ui_reload_failure(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("template-rollback-test")
    try:
        _APP.processEvents()
        window.settings.setValue("net_proto", "UDP")
        window.settings.setValue("frame_rules", "KEEP")
        window.settings.setValue("frame_header", "AA 55")
        window.settings.setValue("frame_fields", "cmd=2:u8")
        window.settings.sync()
        monkeypatch.setattr(window, "_confirm_dlg", lambda *args, **kwargs: True)
        monkeypatch.setattr(window, "_prepare_project_switch", lambda: True)
        monkeypatch.setattr(
            window, "_apply_loaded_settings",
            lambda: (_ for _ in ()).throw(RuntimeError("reload failed")))
        index = window.cb_workspace_template.findData("modbus_rtu")
        window.cb_workspace_template.setCurrentIndex(index)
        window._apply_workspace_protocol_template()

        assert window.settings.value("net_proto") == "UDP"
        assert window.settings.value("frame_rules") == "KEEP"
        assert window.settings.value("frame_header") == "AA 55"
        assert window.settings.value("frame_fields") == "cmd=2:u8"
        assert notices and notices[-1][2] is True
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_last_project_is_restored_silently_on_startup(tmp_path, monkeypatch):
    project_path = tmp_path / "meter.ctproj"
    save_project(str(project_path), make_project(
        "Meter", {"device_type": "modbus"}, {"rx_hex": True}, "test"))
    settings_path = tmp_path / "settings.ini"
    settings = QSettings(str(settings_path), QSettings.IniFormat)
    settings.setValue("restore_last_project", True)
    settings.setValue("last_project_path", str(project_path))
    settings.sync()

    notices = []
    _patch_window_runtime(monkeypatch, settings_path, notices)
    window = CommTool("restore-test")
    try:
        _APP.processEvents()
        _APP.processEvents()
        assert window._project_path == os.path.abspath(str(project_path))
        assert window._project_name == "Meter"
        assert notices == []
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_broken_last_project_is_forgotten_without_startup_dialog(tmp_path, monkeypatch):
    project_path = tmp_path / "broken.ctproj"
    project_path.write_text("not json", encoding="utf-8")
    settings_path = tmp_path / "settings.ini"
    settings = QSettings(str(settings_path), QSettings.IniFormat)
    settings.setValue("restore_last_project", True)
    settings.setValue("last_project_path", str(project_path))
    settings.setValue("recent_projects", '["%s"]' % str(project_path).replace("\\", "\\\\"))
    settings.sync()

    notices = []
    _patch_window_runtime(monkeypatch, settings_path, notices)
    window = CommTool("broken-restore-test")
    try:
        _APP.processEvents()
        _APP.processEvents()
        assert window._project_path is None
        assert window.settings.value("last_project_path", "") == ""
        assert str(project_path) not in window._recent_projects()
        assert notices == []
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_modbus_slave_ascii_sends_text_frame_rtu_sends_hex(tmp_path, monkeypatch):
    """A 落地：从机 ASCII 变体把响应按 ASCII 字面字节发（hex_mode=False、':' 开头）；
    RTU 变体仍按 hex 串发（hex_mode=True）。验证 _modbus_send 的分支不互相串味。"""
    from modbus import modbus_slave, modbus_master
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("modbus-ascii-slave-test")
    try:
        _APP.processEvents()
        monkeypatch.setattr(window, "_is_open", lambda: True)
        window._ar_on = True
        window.active_session()._ar_enabled = True
        monkeypatch.setattr(window, "_ar_apply_fault", lambda frame: (frame, None))
        sent = []
        monkeypatch.setattr(window, "_send_text",
                            lambda *a, **k: sent.append((a[0], k.get("hex_mode"))))

        # ASCII 变体：holding[0]=0x1234，读 1 个寄存器
        window._ar_modbus = {"on": True, "variant": "ascii", "addr": 1,
                             "holding": {"0": 0x1234}}
        window._modbus = modbus_slave.slave_from_config(window._ar_modbus)
        window._ar_buf = b""
        window._auto_reply(b":010300000001FB\r\n")
        assert len(sent) == 1
        text, hex_mode = sent[0]
        assert hex_mode is False                 # ASCII 帧按文本字节发，不是 hex 编码
        assert text.startswith(":") and text.endswith("\r\n")
        assert "1234" in text                    # 寄存器值出现在 ASCII 帧里

        # RTU 变体（回归）：同样寄存器，响应按 hex 串发
        sent.clear()
        window._ar_modbus = {"on": True, "variant": "rtu", "addr": 1,
                             "holding": {"0": 0x1234}}
        window._modbus = modbus_slave.slave_from_config(window._ar_modbus)
        window._ar_buf = b""
        window._auto_reply(modbus_master.build_rtu_request(1, 3, 0, 1))
        assert len(sent) == 1
        text, hex_mode = sent[0]
        assert hex_mode is True
        assert text.replace(" ", "").upper().startswith("0103021234")
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_modbus_master_ascii_variant_builds_and_feeds_ascii(tmp_path, monkeypatch):
    """A 落地：主机 ascii 变体 → _mbm_variant_eff=ascii；_mbm_feed 走 take_ascii_response。"""
    from modbus import modbus_master
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("modbus-ascii-master-test")
    try:
        _APP.processEvents()
        window._mbm_variant = "ascii"
        assert window._mbm_variant_eff() == "ascii"

        results = []
        monkeypatch.setattr(window, "_mbm_set_result",
                            lambda i, status, text="": results.append((i, status)))
        window._mbm_inflight = {"i": 0, "unit": 1, "func": 3, "qty": 1, "addr": 0,
                                "variant": "ascii", "tid": None,
                                "echo": None, "exp_write": None}
        window._mbm_buf = b""
        # 从机 holding[0]=0x000A 的 ASCII 响应：01 03 02 00 0A，LRC=F0
        window._mbm_feed(b":010302000AF0\r\n")
        assert results == [(0, "ok")]
        assert window._mbm_inflight is None      # 响应处理完，inflight 已释放
        assert window._mbm_buf == b""
        assert modbus_master.take_ascii_response  # 路由目标存在（静态断言护栏）
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_device_register_link_routes_samples_to_plot_and_dashboard(tmp_path, monkeypatch):
    """B 落地：device_plot_tags/device_dash_tags 命中的寄存器样本分别喂给波形图/仪表盘；
    未命中的不喂。验证 _structured_feed_modbus 的联动分发。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("device-link-test")
    try:
        _APP.processEvents()
        window._device_registers = [
            {"name": "voltage", "slave": 1, "function": 3, "address": 0,
             "type": "u16", "scale": 0.1, "unit": "V"},
            {"name": "current", "slave": 1, "function": 3, "address": 1,
             "type": "u16", "scale": 0.1, "unit": "A"},
        ]
        window._device_plot_tags = {"voltage"}
        window._device_dash_tags = {"current"}

        plot_calls, dash_calls = [], []

        class FakeDlg:
            def isVisible(self_): return True

            def feed_named_samples(self_, samples):
                plot_calls.extend(samples)

        class FakeDash:
            def isVisible(self_): return True

            def feed_named_samples(self_, samples):
                dash_calls.extend(samples)

        window._plot_dlg = FakeDlg()
        window._dash_dlg = FakeDash()
        # holding[0]=330(→33.0V) holding[1]=50(→5.0A)
        window._structured_feed_modbus(
            {"unit": 1, "func": 3, "addr": 0}, {"regs": [330, 50]})
        assert len(plot_calls) == 1 and plot_calls[0]["tag"] == "voltage"
        assert plot_calls[0]["value"] == 33.0 and plot_calls[0]["unit"] == "V"
        assert len(dash_calls) == 1 and dash_calls[0]["tag"] == "current"
        assert dash_calls[0]["value"] == 5.0

        # 标签不在联动集 → 不喂；对话框不可见 → 也不喂
        plot_calls.clear()
        window._device_plot_tags = set()
        window._structured_feed_modbus(
            {"unit": 1, "func": 3, "addr": 0}, {"regs": [330, 50]})
        assert plot_calls == []
    finally:
        window._plot_dlg = None
        window._dash_dlg = None
        window.deleteLater()
        _APP.processEvents()


def test_plot_feed_named_samples_shares_x_within_response():
    """B 落地：一次 Modbus 响应含多个寄存器时，各通道共享同一 X 坐标、采样序号只进一。
    这是对「同一响应各通道 X 轴错位」的回归防护。"""
    plot = PlotDialog.__new__(PlotDialog)          # 绕过 __init__（依赖 pyqtgraph）
    plot._paused = False
    plot._x_time = False
    plot._t0 = None
    plot._sample_idx = 0
    plot._name_to_idx = {}
    plot._pos_to_idx = {}
    plot._channels = []
    plot._ensure_channel = lambda i, name=None: plot._channels.append(
        {"name": name, "xs": [], "ys": []})

    # 同一次响应喂 2 个样本：a、b 应共享 x=0，序号只进一
    plot.feed_named_samples([{"tag": "a", "value": 1}, {"tag": "b", "value": 2}])
    assert plot._channels[0]["name"] == "a" and plot._channels[0]["xs"] == [0]
    assert plot._channels[1]["name"] == "b" and plot._channels[1]["xs"] == [0]
    assert plot._sample_idx == 1

    # 第二次响应：a 落在 x=1（序号已推进）
    plot.feed_named_samples([{"tag": "a", "value": 3}])
    assert plot._channels[0]["xs"] == [0, 1]
    assert plot._sample_idx == 2

    # 暂停 / 空列表不推进序号
    plot._paused = True
    plot.feed_named_samples([{"tag": "a", "value": 4}])
    assert plot._sample_idx == 2
    plot._paused = False
    plot.feed_named_samples([])
    assert plot._sample_idx == 2


def test_plot_feed_named_samples_x_time_shared_within_response():
    """B 落地：x_time 模式下同一响应各通道也共享时间戳（各取一次 monotonic 会微差）。"""
    plot = PlotDialog.__new__(PlotDialog)
    plot._paused = False
    plot._x_time = True
    plot._t0 = None
    plot._sample_idx = 0
    plot._name_to_idx = {}
    plot._pos_to_idx = {}
    plot._channels = []
    plot._ensure_channel = lambda i, name=None: plot._channels.append(
        {"name": name, "xs": [], "ys": []})

    plot.feed_named_samples([{"tag": "a", "value": 1}, {"tag": "b", "value": 2}])
    assert plot._channels[0]["xs"] == plot._channels[1]["xs"]
    assert len(plot._channels[0]["xs"]) == 1
    assert plot._sample_idx == 1


def test_plot_named_and_position_channels_are_isolated():
    """具名联动通道与分隔符/正则/HEX 的位置通道不能共享曲线。"""
    plot = PlotDialog.__new__(PlotDialog)
    plot._paused = False
    plot._x_time = False
    plot._t0 = None
    plot._sample_idx = 0
    plot._name_to_idx = {}
    plot._pos_to_idx = {}
    plot._channels = []
    plot._ensure_channel = lambda i, name=None: plot._channels.append(
        {"name": name or f"CH{i + 1}", "xs": [], "ys": []})

    plot.feed_named_samples([{"tag": "temp", "value": 10}])
    plot._append_vals([20])
    plot._append_vals([30])

    assert len(plot._channels) == 2
    assert plot._channels[0]["name"] == "temp"
    assert list(plot._channels[0]["ys"]) == [10]
    assert list(plot._channels[1]["ys"]) == [20, 30]


def test_toggle_link_refreshes_project_dirty_label(tmp_path):
    """B 落地：联动标签在 _CFG_KEYS 里，toggle 后必须刷新工程 dirty 标签，
    否则标题栏仍显示「已保存」而实际工程内容已变。"""
    from PyQt5.QtWidgets import QTableWidget

    calls = []
    app = type("StubApp", (), {})()
    app.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    app._device_registers = []
    app._device_plot_tags = set()
    app._device_dash_tags = set()
    app._save_device_link = lambda: app.settings.setValue(
        "device_plot_tags",
        json.dumps(sorted(app._device_plot_tags), ensure_ascii=False))
    app._refresh_project_dirty_label = lambda: calls.append("refresh")
    app._t = lambda key, **kw: key
    app.toast = lambda *args, **kw: None

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)     # 绕过 __init__（依赖完整 UI）
    dlg.app = app
    dlg.table = QTableWidget(0, 11)

    dlg._toggle_link("plot", ["temp"], True)
    assert calls == ["refresh"]                  # dirty 标签已刷新
    assert app._device_plot_tags == {"temp"}
    assert json.loads(app.settings.value("device_plot_tags")) == ["temp"]


def test_device_apply_migrates_links_after_register_rename(tmp_path):
    """寄存器改名后直接 Apply，波形/仪表盘联动应按 slave+address 迁移。"""
    app = type("StubApp", (), {})()
    app.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    app._device_registers = [{"name": "voltage", "slave": 1, "function": 3, "address": 10}]
    app._device_plot_tags = {"voltage"}
    app._device_dash_tags = {"voltage"}
    app._save_device_link = lambda: (
        app.settings.setValue("device_plot_tags", json.dumps(sorted(app._device_plot_tags))),
        app.settings.setValue("device_dash_tags", json.dumps(sorted(app._device_dash_tags))))
    app._refresh_project_dirty_label = lambda: None

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)
    dlg.app = app
    dlg._collect_registers = lambda: [{"name": "volt_new", "slave": 1, "function": 3, "address": 10}]
    dlg.commit_pending(notify=False)

    assert app._device_plot_tags == {"volt_new"}
    assert app._device_dash_tags == {"volt_new"}
    assert json.loads(app.settings.value("device_plot_tags")) == ["volt_new"]
    assert json.loads(app.settings.value("device_dash_tags")) == ["volt_new"]


def test_device_apply_removes_links_after_register_delete(tmp_path):
    """寄存器删除后 Apply，联动标签应随之移除——否则 `_feed_named_view` 用已不存在的
    name 匹配永远不命中，形成静默失效的悬空标签。"""
    app = type("StubApp", (), {})()
    app.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    app._device_registers = [
        {"name": "voltage", "slave": 1, "function": 3, "address": 10},
        {"name": "current", "slave": 1, "function": 3, "address": 11},
    ]
    app._device_plot_tags = {"voltage", "current"}
    app._device_dash_tags = {"voltage"}
    app._save_device_link = lambda: (
        app.settings.setValue("device_plot_tags", json.dumps(sorted(app._device_plot_tags))),
        app.settings.setValue("device_dash_tags", json.dumps(sorted(app._device_dash_tags))))
    app._refresh_project_dirty_label = lambda: None

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)
    dlg.app = app
    # 删掉 voltage（address=10），只留 current
    dlg._collect_registers = lambda: [{"name": "current", "slave": 1, "function": 3, "address": 11}]
    dlg.commit_pending(notify=False)

    assert app._device_plot_tags == {"current"}       # voltage 标签被移除
    assert app._device_dash_tags == set()             # 唯一标签删除后清空
    assert json.loads(app.settings.value("device_plot_tags")) == ["current"]


def test_migrate_link_tags_preserves_when_identity_ambiguous(tmp_path):
    """迁移逻辑对「身份不唯一」保持保守：不把联动静默迁到错误记录。"""
    app = type("StubApp", (), {})()
    app.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    # 新表里 (slave=1, address=10) 出现两条 → 无法判定 voltage 该迁到哪条，保留原标签
    app._device_registers = [{"name": "voltage", "slave": 1, "function": 3, "address": 10}]
    app._device_plot_tags = {"voltage"}
    app._device_dash_tags = set()
    app._save_device_link = lambda: (
        app.settings.setValue("device_plot_tags", json.dumps(sorted(app._device_plot_tags))),
        app.settings.setValue("device_dash_tags", json.dumps(sorted(app._device_dash_tags))))
    app._refresh_project_dirty_label = lambda: None

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)
    dlg.app = app
    dlg._collect_registers = lambda: [
        {"name": "voltage", "slave": 1, "function": 3, "address": 10},
        {"name": "voltage_dup", "slave": 1, "function": 3, "address": 10},
    ]
    dlg.commit_pending(notify=False)

    assert app._device_plot_tags == {"voltage"}       # 保留原标签，不猜测


def test_migrate_link_tags_does_not_retarget_across_function(tmp_path):
    """Same slave+address but different function must not steal the link.

    Holding(03) and input(04) commonly share numeric addresses. Deleting a
    linked holding row while an input row at the same address remains must
    drop the link, not silently retarget it to the other function's tag.
    """
    app = type("StubApp", (), {})()
    app.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    app._device_registers = [
        {"name": "hold_v", "slave": 1, "function": 3, "address": 10},
        {"name": "in_v", "slave": 1, "function": 4, "address": 10},
    ]
    app._device_plot_tags = {"hold_v"}
    app._device_dash_tags = {"hold_v"}
    app._save_device_link = lambda: (
        app.settings.setValue("device_plot_tags", json.dumps(sorted(app._device_plot_tags))),
        app.settings.setValue("device_dash_tags", json.dumps(sorted(app._device_dash_tags))))
    app._refresh_project_dirty_label = lambda: None

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)
    dlg.app = app
    # Delete holding; keep input at same slave/address
    dlg._collect_registers = lambda: [
        {"name": "in_v", "slave": 1, "function": 4, "address": 10},
    ]
    dlg.commit_pending(notify=False)

    assert app._device_plot_tags == set()
    assert app._device_dash_tags == set()



def test_timestamp_prefix_formats(tmp_path, monkeypatch):
    """C 落地：时间戳四种格式各按预期渲染，关闭时不显示。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("ts-fmt-test")
    try:
        _APP.processEvents()
        window.sw_show_timestamp.setChecked(True)
        window._ts_format = "absolute"
        assert window._timestamp_prefix("tx").startswith("[20") and window._timestamp_prefix("tx").endswith("→ ")
        window._ts_format = "time"
        p = window._timestamp_prefix("rx")
        assert p.startswith("[") and p.endswith("← ") and ":" in p
        window._ts_format = "epoch"
        pe = window._timestamp_prefix("tx")
        assert pe.startswith("[1") and "." in pe
        window._ts_format = "relative"
        window._ts_anchor = None
        assert window._timestamp_prefix("rx").startswith("[+0.")   # 锚点首次定，≈0
        window.sw_show_timestamp.setChecked(False)
        assert window._timestamp_prefix("tx") == ""
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_freeze_view_blocks_append(tmp_path, monkeypatch):
    """C 落地：冻结视图时不向数据区追加；解冻后恢复追加。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("freeze-test")
    try:
        _APP.processEvents()
        before = window.txt_recv.toPlainText()
        window._freeze_view = True
        window._append_block_data("FROZEN_PAYLOAD", "rx", force_new_block=True)
        assert window.txt_recv.toPlainText() == before
        assert "FROZEN_PAYLOAD" not in window.txt_recv.toPlainText()
        window._freeze_view = False
        window._append_block_data("LIVE_PAYLOAD", "rx", force_new_block=True)
        assert "LIVE_PAYLOAD" in window.txt_recv.toPlainText()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_freeze_view_has_hover_help(tmp_path, monkeypatch):
    """冻结显示开关应提供说明性鼠标悬浮框。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("freeze-tooltip-test")
    try:
        _APP.processEvents()
        assert window.sw_freeze_view.property("tr_tooltip") == "freeze_view_tip"
        from ui.ui_tips import tip_html
        assert window.sw_freeze_view.toolTip() == tip_html(window._t("freeze_view_tip"))
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_display_preferences_flush_and_refresh_project_dirty(tmp_path, monkeypatch):
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("display-preferences-dirty-test")
    calls = []
    try:
        _APP.processEvents()
        monkeypatch.setattr(window, "_refresh_project_dirty_label",
                            lambda: calls.append(True))
        window.cb_ts_format.setCurrentIndex(window.cb_ts_format.findData("relative"))
        window.sw_freeze_view.setChecked(True)
        assert window.settings.value("ts_format") == "relative"
        assert window.settings.value("freeze_view", type=bool) is True
        assert len(calls) == 2
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_search_modes_collect_matches(tmp_path, monkeypatch):
    """C 落地：搜索三模式（纯文本/正则/HEX）各自正确收集匹配。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("search-modes-test")
    try:
        _APP.processEvents()
        window.txt_recv.setPlainText("AA BB CC 12 34")

        window._search_mode = "plain"
        _search_text(window, "aa")
        assert len(window._search_matches) == 1

        window._search_mode = "regex"
        _search_text(window, r"\d+")
        assert len(window._search_matches) == 2

        window._search_mode = "hex"
        _search_text(window, "AABB")
        assert len(window._search_matches) == 1

        window._search_mode = "hex"
        _search_text(window, "GGHH")          # 非法 hex
        assert window._search_matches == []
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_search_count_marks_capped_matches(tmp_path, monkeypatch):
    """大流搜索只建立有限选区时，计数必须明确提示仍有未展示匹配。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("search-cap-test")
    try:
        _APP.processEvents()
        window._search_mode = "hex"
        window.txt_recv.setPlainText("00 " * (window._KW_MAX_SELECTIONS + 10))
        _search_text(window, "00")
        assert len(window._search_matches) == window._KW_MAX_SELECTIONS
        assert window._search_match_capped is True
        assert window.lbl_search_cnt.text() == (
            "1/%d+" % window._KW_MAX_SELECTIONS)
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_search_non_bmp_positions_match_qt_utf16_offsets(tmp_path, monkeypatch):
    """搜索含 emoji 的文本时，Python 码点偏移必须转换为 Qt UTF-16 光标偏移。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("search-utf16-test")
    try:
        _APP.processEvents()
        window.txt_recv.setPlainText("A😀 ERROR")
        window._search_mode = "plain"
        _search_text(window, "ERROR")
        assert len(window._search_matches) == 1
        cursor = window._search_matches[0]
        assert (cursor.selectionStart(), cursor.selectionEnd()) == (4, 9)
        assert cursor.selectedText() == "ERROR"
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_modbus_slave_variant_survives_normalize(tmp_path, monkeypatch):
    """Bugbot#1(high)：从机 ASCII variant 必须穿过 _norm_ar_modbus，否则 Apply 后 _modbus_feed
    退回 RTU、ASCII 从机配置静默失效。"""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("ar-variant-norm-test")
    try:
        _APP.processEvents()
        window._set_ar_modbus({"on": True, "variant": "ascii", "addr": 1,
                               "holding": {"0": 1}})
        assert window._ar_modbus["variant"] == "ascii"
        # 坏值 / 缺省 → 回落 rtu
        window._set_ar_modbus({"on": True, "variant": "weird", "addr": 1})
        assert window._ar_modbus["variant"] == "rtu"
        window._set_ar_modbus({"on": True, "addr": 1})
        assert window._ar_modbus["variant"] == "rtu"
        # ASCII 落盘后仍可读回
        assert json.loads(window.settings.value("autoreply_modbus"))["variant"] in ("ascii", "rtu")
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_ascii_master_timeout_longer_than_rtu_for_same_request(tmp_path, monkeypatch):
    """Bugbot#3(med)：ASCII 响应是 hex 编码、约 2 倍 RTU 长度；超时必须按 ASCII 帧长估算，
    否则低波特率大包下超时偏短而误判。"""
    from modbus import modbus_master
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("ascii-timeout-test")
    try:
        _APP.processEvents()
        window._conn_proto = "Serial"        # 走 _mbm_timeout_ms 的串口分支（按波特率算传输时间）
        window._device_scan_state = None
        monkeypatch.setattr(window, "_mbm_serial_baud", lambda: 1200)
        monkeypatch.setattr(window, "_mbm_serial_char_bits", lambda: 10)
        r = {"func": 3, "qty": 10}
        rtu_to = window._mbm_timeout_ms(modbus_master.build_rtu_request(1, 3, 0, 10), r)
        ascii_to = window._mbm_timeout_ms(modbus_master.build_ascii_request(1, 3, 0, 10), r)
        assert ascii_to > rtu_to
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_ascii_master_strips_local_echo_before_parsing(tmp_path, monkeypatch):
    """Bugbot#2(med)：半双工 RS-485 开本地回显时，ASCII 请求帧会被回显回来；
    inflight 必须登记 echo 并在解析前剥掉，否则回显会被当成响应误解析。"""
    from modbus import modbus_master, modbus_slave
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("ascii-echo-test")
    try:
        _APP.processEvents()
        results = []
        monkeypatch.setattr(window, "_mbm_set_result",
                            lambda i, s, text="": results.append((i, s)))
        req = modbus_master.build_ascii_request(1, 3, 0, 1)
        resp = modbus_slave.ModbusSlave(addr=1, holding={0: 0x000A}).handle_ascii(req)
        window._mbm_echo = True
        window._mbm_inflight = {"i": 0, "unit": 1, "func": 3, "qty": 1, "addr": 0,
                                "variant": "ascii", "tid": None, "echo": req,
                                "exp_write": None}
        window._mbm_buf = b""
        window._mbm_feed(req + resp)          # 回显 + 真响应 粘在一起
        assert results == [(0, "ok")]         # 剥掉回显后正确解析真响应
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_rtu_slave_addr_58_sends_binary_not_ascii_mangled(tmp_path, monkeypatch):
    """复审#1(med)：RTU 从机地址 58=0x3A=':'，_modbus_send 必须按 variant 路由、不能嗅探首字节——
    否则 RTU 二进制响应被 decode('ascii','replace') 破坏，主机侧 CRC 必败、该地址永远收不到响应。"""
    from modbus import modbus_master, modbus_slave
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("rtu-addr58-test")
    try:
        _APP.processEvents()
        monkeypatch.setattr(window, "_is_open", lambda: True)
        window._ar_on = True
        window.active_session()._ar_enabled = True
        monkeypatch.setattr(window, "_ar_apply_fault", lambda frame: (frame, None))
        sent = []
        monkeypatch.setattr(window, "_send_text",
                            lambda *a, **k: sent.append((a[0], k.get("hex_mode"))))
        # RTU 变体、从机地址 58：响应首字节 = unit = 0x3A = ':'
        window._ar_modbus = {"on": True, "variant": "rtu", "addr": 58, "holding": {"0": 0x1234}}
        window._modbus = modbus_slave.slave_from_config(window._ar_modbus)
        window._ar_buf = b""
        window._auto_reply(modbus_master.build_rtu_request(58, 3, 0, 1))
        assert len(sent) == 1
        text, hex_mode = sent[0]
        assert hex_mode is True                       # RTU → hex 串（非 ASCII 文本通道）
        assert text.split()[0].upper() == "3A"        # 响应首字节正确是 addr=58=0x3A，未被破坏
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_ascii_master_resyncs_past_bad_frame_in_one_chunk(tmp_path, monkeypatch):
    """复审#3(low-med)：单 chunk 内坏帧+好帧粘在一起时，ASCII _mbm_feed 应丢坏帧继续解好帧，
    而非一次失败就 return 让好帧搁到超时。"""
    from modbus import modbus_master, modbus_slave
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("ascii-resync-test")
    try:
        _APP.processEvents()
        results = []
        monkeypatch.setattr(window, "_mbm_set_result",
                            lambda i, s, text="": results.append((i, s)))
        req = modbus_master.build_ascii_request(1, 3, 0, 1)
        good_resp = modbus_slave.ModbusSlave(addr=1, holding={0: 0x000A}).handle_ascii(req)
        bad = b":ZZZZnotvalidhex\r\n"                  # 非法 hex → take_ascii_response 抛 ValueError
        window._mbm_inflight = {"i": 0, "unit": 1, "func": 3, "qty": 1, "addr": 0,
                                "variant": "ascii", "tid": None, "echo": None, "exp_write": None}
        window._mbm_buf = b""
        window._mbm_feed(bad + good_resp)            # 坏帧 + 好帧 同一 chunk
        assert results == [(0, "ok")]                 # 坏帧被跳过、好帧解析成功
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_freeze_view_still_writes_log_file(tmp_path, monkeypatch):
    """复审#5(med)：冻结视图时实时日志(Log to File)仍要落盘——不能因 _append_block_data 顶部
    早 return 跳过 _log_file 写入，否则冻结期间日志静默丢一段数据。"""
    import io
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("freeze-log-test")
    try:
        _APP.processEvents()
        log = io.StringIO()
        window._log_file = log
        window._txt_ends_with_nl = True
        window._log_ends_with_nl = True
        monkeypatch.setattr(window, "_maybe_rotate_log", lambda now=None: None)  # 隔离轮转依赖
        window.sw_show_timestamp.setChecked(False)
        window._freeze_view = True
        window._append_block_data("FROZEN_LINE\n", "rx", force_new_block=True)
        assert "FROZEN_LINE" not in window.txt_recv.toPlainText()   # 视图确实冻结
        assert "FROZEN_LINE" in log.getvalue()                       # 但日志照常写
    finally:
        window._log_file = None
        window._freeze_view = False
        window.deleteLater()
        _APP.processEvents()


def test_freeze_log_and_view_keep_independent_line_state(tmp_path, monkeypatch):
    """冻结期间日志继续推进，但不能改变可见文本区的行尾拼块状态。"""
    import io
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("freeze-line-state-test")
    try:
        _APP.processEvents()
        log = io.StringIO()
        window._log_file = log
        window._log_ends_with_nl = True
        window.sw_show_timestamp.setChecked(False)

        window._append_block_data("PARTIAL", "rx", force_new_block=False)
        assert window._txt_ends_with_nl is False
        window._freeze_view = True
        window._append_block_data("FROZEN_LINE\n", "rx", force_new_block=True)
        assert window._txt_ends_with_nl is False
        assert window.txt_recv.toPlainText() == "PARTIAL"

        window._freeze_view = False
        window._append_block_data("LIVE", "rx", force_new_block=True)
        assert window.txt_recv.toPlainText() == "PARTIAL\nLIVE"
        assert log.getvalue() == "PARTIAL\nFROZEN_LINE\nLIVE"
    finally:
        window._log_file = None
        window._freeze_view = False
        window.deleteLater()
        _APP.processEvents()


@pytest.mark.parametrize(
    "dialog_result,save_result,save_cancelled,expected,save_calls,notice_calls",
    ((QDialog.Rejected, True, False, False, 0, 0),   # Cancel
     (QDialog.Accepted, True, False, True, 1, 0),    # Save succeeds
     (QDialog.Accepted, False, True, False, 1, 1),   # Save dialog cancelled
     (QDialog.Accepted, False, False, False, 1, 0),  # Save failed and reported
     (2, True, False, True, 0, 0)),   # Don't Save
)
def test_confirm_project_switch_result_branches(
        monkeypatch, dialog_result, save_result, save_cancelled, expected,
        save_calls, notice_calls):
    import main_window as main_window_module

    captured = []

    class _Dialog:
        ThirdAction = 2

        def __init__(self, *args, **kwargs):
            captured.append((args, kwargs))

        @staticmethod
        def exec_():
            return dialog_result

    class _Host:
        _project_name = "Meter"
        _project_save_cancelled = False

        @staticmethod
        def _project_is_dirty():
            return True

        @staticmethod
        def _t(key, **kwargs):
            return "%s:%s" % (key, kwargs.get("name", ""))

        @staticmethod
        def _theme_id():
            return "dark"

        def save_project(self):
            self.save_calls += 1
            self._project_save_cancelled = save_cancelled
            return save_result

        @staticmethod
        def _info_dlg(*args, **kwargs):
            captured.append((args, kwargs))

        save_calls = 0

    monkeypatch.setattr(main_window_module, "InfoDialog", _Dialog)
    host = _Host()
    assert CommTool._confirm_project_switch(host) is expected
    assert host.save_calls == save_calls
    assert captured[0][1]["is_warning"] is True
    assert "is_error" not in captured[0][1]
    assert len(captured) == 1 + notice_calls
    if notice_calls:
        assert captured[1][0] == ("project_save:", "project_save_cancelled:")


@pytest.mark.parametrize("dialog_result,expected", ((QDialog.Rejected, False), (2, True)))
def test_confirm_project_switch_dirty_check_failure_is_reported(
        monkeypatch, dialog_result, expected):
    import main_window as main_window_module

    captured = []

    class _Dialog:
        ThirdAction = 2

        def __init__(self, *args, **kwargs):
            captured.append((args, kwargs))

        @staticmethod
        def exec_():
            return dialog_result

    class _Host:
        @staticmethod
        def _project_is_dirty():
            raise OSError("cannot collect pending editor")

        @staticmethod
        def _t(key, **kwargs):
            return "%s:%s" % (key, kwargs.get("err", ""))

        @staticmethod
        def _theme_id():
            return "dark"

    monkeypatch.setattr(main_window_module, "InfoDialog", _Dialog)
    assert CommTool._confirm_project_switch(_Host()) is expected
    args, kwargs = captured[0]
    assert args == ("project_save:",
                    "project_save_fail:cannot collect pending editor")
    assert kwargs["ok_text"] == "cancel:"
    assert kwargs["third_text"] == "project_force_continue:"
    assert kwargs["is_error"] is True
    assert kwargs["theme_id"] == "dark"


def test_save_project_collect_failure_is_reported():
    notices = []

    class _Host:
        _project_path = "broken.ctproj"
        _project_name = "Meter"
        _project_meta = {}

        @staticmethod
        def _collect_project_settings():
            raise OSError("disk unavailable")

        @staticmethod
        def _t(key, **kwargs):
            return "%s:%s" % (key, kwargs.get("err", ""))

        @staticmethod
        def _info_dlg(title, body, is_error=False):
            notices.append((title, body, is_error))

    host = _Host()
    assert CommTool.save_project(host) is False
    assert host._project_save_cancelled is False
    assert notices == [
        ("project_save:", "project_save_fail:disk unavailable", True)]


def test_save_project_dialog_cancel_sets_cancelled_marker(monkeypatch):
    import main_window as main_window_module

    class _Host:
        _project_path = None
        _project_name = "Meter"

        @staticmethod
        def _t(key, **_kwargs):
            return key

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName",
        lambda *_args, **_kwargs: ("", ""))
    host = _Host()
    assert CommTool.save_project(host) is False
    assert host._project_save_cancelled is True


def test_search_lazy_pages_with_next_prev(tmp_path, monkeypatch):
    """Capped search keeps full-document next/previous wrap semantics."""
    notices = []
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini", notices)
    window = CommTool("search-lazy-test")
    try:
        _APP.processEvents()
        # Shrink page size so the test stays cheap.
        window._KW_MAX_SELECTIONS = 5
        window._search_mode = "hex"
        window.txt_recv.setPlainText("00 " * 14)  # 14 hits
        _search_text(window, "00")
        assert len(window._search_matches) == 5
        assert window._search_match_capped is True
        assert window.lbl_search_cnt.text() == "1/5+"

        # Advance to end of page 1, then one more ▼ → page 2
        window._search_idx = 4
        window._search_next()
        assert len(window._search_matches) == 5
        assert window._search_idx == 0
        assert len(window._search_page_starts) == 2
        assert window._search_page_starts[0] == 0
        assert window.lbl_search_cnt.text().startswith("6/")
        assert "+" in window.lbl_search_cnt.text()

        # ▼ until last page (4 remaining → page of 4, not capped)
        window._search_idx = 4
        window._search_next()
        assert len(window._search_matches) == 4
        assert window._search_match_capped is False
        assert window.lbl_search_cnt.text() == "11/14"

        # ▲ from first of last page → previous page last match
        window._search_idx = 0
        window._search_prev()
        assert len(window._search_matches) == 5
        assert window._search_idx == 4
        assert window.lbl_search_cnt.text().startswith("10/")

        # Last global match + ▼ wraps to the first page/match.
        window._search_idx = 4
        window._search_next()
        assert len(window._search_page_starts) == 3
        assert len(window._search_matches) == 4
        window._search_idx = 3
        window._search_next()
        assert window._search_page_starts == [0]
        assert window._search_idx == 0
        assert window.lbl_search_cnt.text() == "1/5+"

        # First global match + ▲ lazily finds the final page/match.
        window._search_prev()
        assert len(window._search_page_starts) == 3
        assert len(window._search_matches) == 4
        assert window._search_idx == 3
        assert window.lbl_search_cnt.text() == "14/14"
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_example_projects_validate_and_merge(tmp_path):
    """Shipped examples/ packs load as v2 projects with useful resources."""
    from project.project_model import load_project, merge_project_resources, validate
    examples = Path(__file__).resolve().parents[1] / "examples"
    files = sorted(examples.glob("*.ctproj"))
    assert len(files) >= 3
    for path in files:
        payload = load_project(str(path))
        validate(payload)
        merged = merge_project_resources(
            payload.get("settings") or {}, payload.get("resources") or {})
        assert isinstance(merged, dict)
        # Every demo ships at least one connection preset name.
        import json
        presets = json.loads(merged.get("connection_presets") or "[]")
        assert presets, path.name


def test_example_project_generation_is_stable_and_dual_session_loops_back(tmp_path):
    """Generated demos are reproducible and the virtual starter works immediately."""
    from scripts import build_example_projects as builder
    from project.project_model import merge_project_resources

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    builders = (
        builder.build_modbus, builder.build_at, builder.build_dual_session,
        builder.build_nmea, builder.build_fixed_header,
        builder.build_sensor_csv, builder.build_tcp_client_debug,
        builder.build_keyword_highlight_demo, builder.build_dash_gauge_demo,
    )
    for build in builders:
        build(first)
        build(second)

    for path in sorted(first.glob("*.ctproj")):
        assert path.read_bytes() == (second / path.name).read_bytes()
        shipped = Path(__file__).resolve().parents[1] / "examples" / path.name
        assert path.read_bytes() == shipped.read_bytes()

    dual = load_project(str(first / "dual_session_demo.ctproj"))
    merged = merge_project_resources(
        dual.get("settings") or {}, dual.get("resources") or {})
    assert merged.get("vconn_loopback") is True
    presets = json.loads(merged.get("connection_presets") or "[]")
    ids = [item["id"] for item in presets]
    assert len(ids) == len(set(ids))


def test_example_projects_are_in_platform_installers():
    """Repository examples must also reach Windows installers and the Mac DMG."""
    root = Path(__file__).resolve().parents[1]
    iss = (root / "scripts" / "CommTool.iss").read_text(encoding="utf-8")
    mac = (root / "scripts" / "build_macos.sh").read_text(encoding="utf-8")
    assert 'Source: "..\\examples\\*.ctproj"' in iss
    assert 'cp -R examples "$STAGE/Examples"' in mac
