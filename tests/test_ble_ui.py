# -*- coding: utf-8 -*-
"""Offscreen BLE settings: type visibility, swap, scan dialog, preset round-trip."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QCoreApplication, QEvent, QSettings
from PyQt5.QtWidgets import QApplication, QHBoxLayout

from conn_ui import PROTO_BLE

_APP = QApplication.instance() or QApplication([])
_WINDOWS = []


def _make_window(tmp_path, monkeypatch):
    from main_window import CommTool, PortScannerThread

    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(tmp_path / "ble.ini")))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)
    w = CommTool()
    w.settings = QSettings(str(tmp_path / "ble.ini"), QSettings.IniFormat)
    # BLE rows still need a selectable type in off-Windows UI tests.
    if w.cb_proto.findText(PROTO_BLE) < 0:
        w.cb_proto.addItem(PROTO_BLE)
    _WINDOWS.append(w)
    return w


def teardown_function(_fn=None):
    for window in reversed(_WINDOWS):
        window._shutdown()
        _APP.processEvents()
        window.deleteLater()
    _WINDOWS.clear()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_ble_type_shows_rows_and_swap(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_BLE)
    w._update_net_fields()
    assert w.row_ble_scan.isHidden() is False
    assert w.row_port.isHidden() is True
    assert w.ed_ble_write.text().upper().endswith("FFF2") or w.ed_ble_write.text().upper() == "FFF2"
    wr, ntf = w.ed_ble_write.text(), w.ed_ble_notify.text()
    w._on_ble_swap_clicked()
    assert w.ed_ble_write.text() == ntf
    assert w.ed_ble_notify.text() == wr


def test_ble_scan_dialog_is_reused(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    first = w._ble_scan_dialog()
    assert w._ble_scan_dialog() is first


def test_ble_scan_dialog_select_and_preset_roundtrip(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_BLE)
    w._update_net_fields()
    assert not hasattr(w, "tbl_ble")
    dlg = w._ble_scan_dialog()
    dlg.upsert("69:1E:38:38:39:0D", "GEE7016691F98FE", -51, ["fff0"])
    dlg.upsert("69:1E:38:38:39:0D", "GEE7016691F98FE", -40, ["180A"])
    assert dlg.table.rowCount() == 1
    assert dlg.table.columnCount() == 8
    assert "-40" in dlg.table.item(0, 3).text()
    uuid_txt = dlg.table.item(0, 2).text()
    assert "FFF0" in uuid_txt
    assert "180A" in uuid_txt
    hh = dlg.table.horizontalHeader()
    assert hh.sectionsMovable() is True
    from PyQt5.QtWidgets import QHeaderView
    assert hh.sectionResizeMode(0) == QHeaderView.Interactive
    dlg.ed_search.setText("fff0")
    assert dlg.table.isRowHidden(0) is False
    dlg.ed_search.setText("no-such")
    assert dlg.table.isRowHidden(0) is True
    dlg.ed_search.setText("")
    assert dlg.btn_filter.isCheckable()
    assert dlg.btn_filter.isChecked()
    assert dlg.btn_scan.objectName() == "BleScanStartBtn"
    assert dlg.btn_stop.objectName() == "BleScanStopBtn"
    dlg.set_scanning(False)
    assert dlg.btn_scan.isEnabled()
    assert dlg.btn_stop.isEnabled() is False
    dlg.set_scanning(True)
    assert dlg.btn_scan.isEnabled() is False
    assert dlg.btn_stop.isEnabled()
    dlg.set_scanning(False)
    dlg.table.selectRow(0)
    dlg._use_selected()
    assert w.ed_ble_address.text() == "69:1E:38:38:39:0D"
    assert "69:1E:38:38:39:0D" not in dlg._last_connect
    assert "GEE701" in w.ed_ble_name.text()
    fields = w._capture_connection_fields()
    assert fields["net_proto"] == PROTO_BLE
    assert fields["ble_address"] == "69:1E:38:38:39:0D"
    w.ed_ble_address.setText("")
    w.ed_ble_name.setText("")
    w._apply_connection_fields(fields)
    assert w.ed_ble_address.text() == "69:1E:38:38:39:0D"
    assert w.cb_proto.currentText() == PROTO_BLE
    key = w._session_resource_key_from_open(PROTO_BLE, {
        "address": "69:1E:38:38:39:0D"})
    assert key == ("ble", "69:1E:38:38:39:0D")


def _row_by_addr(dlg, addr):
    want = addr.upper()
    for i in range(dlg.table.rowCount()):
        item = dlg.table.item(i, 1)
        if item is not None and item.text() == want:
            return i
    return -1


def test_ble_scan_filter_hides_unnamed_by_default(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    assert dlg.btn_filter.isChecked() is True
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE7016691F98FE", -51, ["fff0"])
    dlg.upsert("AA:BB:CC:DD:EE:02", "", -70, [])
    dlg.upsert("AA:BB:CC:DD:EE:03", "\x04BLGW", -60, ["fff0"])
    dlg.upsert("AA:BB:CC:DD:EE:04", "\ufffd", -80, [])
    named = _row_by_addr(dlg, "AA:BB:CC:DD:EE:01")
    unnamed = _row_by_addr(dlg, "AA:BB:CC:DD:EE:02")
    garbled = _row_by_addr(dlg, "AA:BB:CC:DD:EE:03")
    junk = _row_by_addr(dlg, "AA:BB:CC:DD:EE:04")
    assert named >= 0 and unnamed >= 0 and garbled >= 0 and junk >= 0
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(unnamed) is True
    assert dlg.table.isRowHidden(garbled) is False
    assert dlg.table.item(garbled, 0).text() == "BLGW"
    assert dlg.table.isRowHidden(junk) is True
    assert dlg._visible_count() == 2
    dlg.upsert("AA:BB:CC:DD:EE:05", "", -65, ["fe95"], {
        "manufacturer": [(0x038F, "aa")],
    })
    xiaomi = _row_by_addr(dlg, "AA:BB:CC:DD:EE:05")
    assert xiaomi >= 0
    assert dlg.table.isRowHidden(xiaomi) is False
    dlg.upsert("AA:BB:CC:DD:EE:06", "", -72, None, {
        "raw_sections": [(0x09, b"LynkCo".hex())],
    })
    named_ad = _row_by_addr(dlg, "AA:BB:CC:DD:EE:06")
    assert named_ad >= 0
    assert dlg.table.isRowHidden(named_ad) is False
    assert dlg.table.item(named_ad, 0).text() == "LynkCo"
    assert dlg._visible_count() == 4
    dlg.btn_filter.setChecked(False)
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(unnamed) is False
    assert dlg.table.isRowHidden(garbled) is False
    assert dlg.table.isRowHidden(junk) is False
    assert dlg._visible_count() == 6
    dlg.upsert("AA:BB:CC:DD:EE:01", "", -40, None)
    named = _row_by_addr(dlg, "AA:BB:CC:DD:EE:01")
    assert "GEE701" in dlg.table.item(named, 0).text()
    assert "-40" in dlg.table.item(named, 3).text()


def test_ble_scan_filter_rules_selectable(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    dlg.chk_filt["hide_empty"].setChecked(False)
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"], {
        "connectable": True, "manufacturer": [(0x004C, "aa")],
    })
    dlg.upsert("AA:BB:CC:DD:EE:02", "", -70, ["fe95"], {
        "connectable": False, "manufacturer": [],
    })
    named = _row_by_addr(dlg, "AA:BB:CC:DD:EE:01")
    unnamed = _row_by_addr(dlg, "AA:BB:CC:DD:EE:02")
    dlg.chk_filt["named_only"].setChecked(True)
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(unnamed) is True
    dlg.chk_filt["named_only"].setChecked(False)
    dlg.chk_filt["connectable"].setChecked(True)
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(unnamed) is True
    dlg.chk_filt["connectable"].setChecked(False)
    dlg.chk_filt["has_mfr"].setChecked(True)
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(unnamed) is True
    dlg.chk_filt["has_mfr"].setChecked(False)
    dlg.chk_filt["has_uuid"].setChecked(True)
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(unnamed) is False
    dlg.remember_last_connect("AA:BB:CC:DD:EE:01", when=1700000000)
    dlg.chk_filt["last_used"].setChecked(True)
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(unnamed) is True
    dlg.chk_filt["last_used"].setChecked(False)
    dlg.chk_filt["hide_stale"].setChecked(True)
    dlg._meta["AA:BB:CC:DD:EE:02"] = {"seen": 0.0, "stale": True}
    dlg._apply_filter()
    assert dlg.table.isRowHidden(unnamed) is True
    dlg.btn_filter.setChecked(False)
    assert dlg.filter_box.isVisible() is False
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(unnamed) is False


def test_ble_scan_filter_uses_ui_point_size(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    chk = dlg.chk_filt["named_only"]
    hint = dlg.lbl_filt_rules
    assert chk.font().pointSize() == 10 or chk.font().pixelSize() >= 12
    assert hint.font().pointSize() == 10 or hint.font().pixelSize() >= 12


def test_ble_scan_filter_rules_wrap_to_width(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    flow = dlg._filt_flow
    one = flow.heightForWidth(2000)
    many = flow.heightForWidth(160)
    assert one > 0
    assert many > one


def test_ble_scan_repeat_start_keeps_rows(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_BLE)
    w._update_net_fields()
    dlg = w._ble_scan_dialog()
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE7016691F98FE", -51, ["fff0"])
    assert dlg.table.rowCount() == 1

    class _Busy(object):
        is_scanning = True

        def start(self):
            raise AssertionError("must not restart scan")

        def stop(self):
            pass

    w._ble_scanner = _Busy()
    assert w._start_ble_scan() is True
    assert dlg.table.rowCount() == 1
    assert w.btn_ble_scan.isEnabled() is False
    w._ble_scanner.is_scanning = False
    w._sync_ble_scan_buttons()
    assert w.btn_ble_scan.isEnabled() is True


def test_ble_scan_adv_columns_tooltip_and_search(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    adv = {
        "tx_power": 4,
        "connectable": True,
        "manufacturer": [(0x004C, "100612")],
        "service_data": [("fff0", "01")],
        "appearance": 0x40,
        "advertisement_type": "ADV_IND",
    }
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"], adv)
    assert dlg.table.columnCount() == 8
    assert "-51" in dlg.table.item(0, 3).text()
    assert dlg.table.item(0, 4).text() == "+4"
    assert dlg.table.item(0, 5).text() == "●"
    mfr = dlg.table.item(0, 7).text()
    assert "004C" in mfr
    assert "100612" in mfr
    assert "Apple" in mfr
    tip = dlg.table.item(0, 0).toolTip()
    assert "ADV_IND" in tip
    assert "004C" in tip
    assert "0040" in tip
    assert "Generic Phone" in tip
    dlg.table.selectRow(0)
    detail = dlg.txt_detail.toPlainText()
    assert "Apple" in detail
    assert "Generic Phone" in detail
    assert w._t("ble_adv_svc_n", n=1) in detail
    dlg._copy_detail()
    assert "Apple" in QApplication.clipboard().text()
    dlg.ed_search.setText("apple")
    assert dlg.table.isRowHidden(0) is False
    dlg.ed_search.setText("004c")
    assert dlg.table.isRowHidden(0) is False
    dlg.ed_search.setText("adv_ind")
    assert dlg.table.isRowHidden(0) is False
    dlg.ed_search.setText("no-such-mfr")
    assert dlg.table.isRowHidden(0) is True
    dlg.ed_search.setText("")
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -40, None, {
        "manufacturer": [(0x02E5, "abcd")],
        "connectable": False,
    })
    assert "-40" in dlg.table.item(0, 3).text()
    assert dlg.table.item(0, 5).text() == "●"
    assert "004C" in dlg.table.item(0, 7).text()
    assert "02E5" in dlg.table.item(0, 7).text()
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", None, None)
    assert "-40" in dlg.table.item(0, 3).text()


def test_ble_scan_interval_stale_and_rssi_filter(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    clock = [100.0]
    dlg._now = lambda: clock[0]
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"])
    assert dlg.table.item(0, 6).text() == w._t("ble_uuid_none")
    clock[0] = 100.152
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -48, ["fff0"])
    assert dlg.table.item(0, 6).text() == "152"
    assert "▂" in dlg.table.item(0, 3).text() or "▄" in dlg.table.item(0, 3).text()
    top = dlg.layout().itemAt(0).layout()
    assert top.indexOf(dlg.btn_rssi) == top.indexOf(dlg.btn_filter) + 1
    assert dlg.rssi_panel.parentWidget() is dlg._rssi_popup
    assert dlg._rssi_popup.isHidden() is True
    assert dlg.btn_rssi.isCheckable() is False
    dlg.btn_rssi.click()
    assert dlg._rssi_popup.isVisible() is True
    assert dlg.rssi_switch_row.layout().itemAt(0).widget() is dlg.lbl_rssi_filter
    assert dlg.rssi_switch_row.layout().itemAt(2).widget() is dlg.sw_rssi
    dlg.sw_rssi.setChecked(True)
    dlg.sl_rssi.setValue(-40)
    assert dlg.btn_rssi.property("active") is True
    assert dlg.rssi_panel.isEnabled() is True
    assert dlg.table.isRowHidden(0) is True
    dlg.btn_filter.setChecked(False)
    assert dlg.filter_box.isHidden() is True
    assert dlg.rssi_panel.isEnabled() is False
    assert dlg.table.isRowHidden(0) is False
    dlg.btn_filter.setChecked(True)
    assert dlg.rssi_panel.isEnabled() is True
    assert dlg.table.isRowHidden(0) is True
    dlg.sw_rssi.setChecked(False)
    assert dlg.table.isRowHidden(0) is False
    assert dlg.rssi_panel.isEnabled() is False
    dlg.sw_rssi.setChecked(True)
    assert dlg.rssi_panel.isEnabled() is True
    dlg.sw_rssi.setChecked(False, animate=False)
    assert dlg.sw_rssi._circle_pos == 2
    dlg.sw_rssi.setChecked(True, animate=False)
    assert dlg.sw_rssi._circle_pos == 18
    clock[0] = 110.0
    dlg._refresh_stale()
    from PyQt5.QtGui import QColor
    fg = dlg.table.item(0, 0).foreground().color()
    sec = QColor(dlg._chrome()["text_sec"])
    assert fg == sec


def test_ble_scan_hidden_stops_stale_timer(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    assert dlg._stale_timer.isActive() is False
    dlg.show()
    _APP.processEvents()
    assert dlg._stale_timer.isActive() is True
    dlg.hide()
    _APP.processEvents()
    assert dlg._stale_timer.isActive() is False


def test_ble_scan_retranslate_refreshes_row_tooltip(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"], {
        "connectable": True,
    })
    before = dlg.table.item(0, 0).toolTip()
    assert w._t("ble_adv_conn_yes") in before
    w._set_language("en")
    dlg.retranslate()
    after = dlg.table.item(0, 0).toolTip()
    assert "Connectable: yes" in after


def test_ble_scan_theme_repaints_stable_rows(tmp_path, monkeypatch):
    from PyQt5.QtGui import QColor
    from theme import chrome_for

    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"])
    before = dlg.table.item(0, 0).foreground().color()
    assert before == QColor(chrome_for("default")["text"])
    idx = w.cb_theme.findData("dark")
    assert idx >= 0
    w.cb_theme.blockSignals(True)
    w.cb_theme.setCurrentIndex(idx)
    w.cb_theme.blockSignals(False)
    dlg.refresh_theme()
    after = dlg.table.item(0, 0).foreground().color()
    assert after == QColor(chrome_for("dark")["text"])
    assert after != before


def test_ble_scan_splitter_keeps_detail_on_resize(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    from PyQt5.QtWidgets import QSplitter
    split = dlg.findChildren(QSplitter)[0]
    assert split.childrenCollapsible() is False
    assert split.count() == 2
    assert dlg.txt_detail.minimumHeight() == 96
    assert dlg.txt_detail.maximumHeight() > 1000
    dlg.show()
    _APP.processEvents()
    before = split.sizes()
    assert before[1] > 80
    dlg.resize(dlg.width(), dlg.height() + 160)
    _APP.processEvents()
    after = split.sizes()
    assert abs(after[1] - before[1]) <= 4
    assert after[0] > before[0]


def test_ble_conn_signature_includes_write_mode(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    w.cb_proto.setCurrentText(PROTO_BLE)
    w._update_net_fields()
    w.ed_ble_address.setText("AA:BB:CC:DD:EE:FF")
    auto = w._conn_config_signature(PROTO_BLE)
    idx = w.cb_ble_write_mode.findData("wwr")
    assert idx >= 0
    w.cb_ble_write_mode.setCurrentIndex(idx)
    wwr = w._conn_config_signature(PROTO_BLE)
    assert auto != wwr
    assert auto[-1] == "auto"
    assert wwr[-1] == "wwr"


def test_ble_last_connect_uses_conn_address_not_sidebar(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    w.cb_proto.setCurrentText(PROTO_BLE)
    w._update_net_fields()
    w.ed_ble_address.setText("AA:BB:CC:DD:EE:FF")
    w._conn_proto = PROTO_BLE
    w.conn = type("Conn", (), {"address": "AA:BB:CC:DD:EE:01"})()
    w._update_conn_status = lambda: None
    w._update_net_fields = lambda: None
    w._cancel_reconnect = lambda: None
    try:
        w._on_conn_state_changed(True)
        assert "AA:BB:CC:DD:EE:01" in dlg._last_connect
        assert "AA:BB:CC:DD:EE:FF" not in dlg._last_connect
    finally:
        w.conn = None
        w._conn_engaged = False


def test_ble_scan_last_connect_stamp(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"])
    dlg.remember_last_connect("AA:BB:CC:DD:EE:01", when=1700000000)
    dlg.table.selectRow(0)
    when = dlg._format_last_connect("AA:BB:CC:DD:EE:01")
    assert when
    assert when in dlg.txt_detail.toPlainText()
    assert w._t("ble_adv_last_connect", when=when) in dlg.txt_detail.toPlainText()


def test_ble_scan_last_used_refilters_after_stamp(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    dlg.chk_filt["hide_empty"].setChecked(False)
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"])
    dlg.upsert("AA:BB:CC:DD:EE:02", "Other", -70, ["fe95"])
    named = _row_by_addr(dlg, "AA:BB:CC:DD:EE:01")
    other = _row_by_addr(dlg, "AA:BB:CC:DD:EE:02")
    dlg.chk_filt["last_used"].setChecked(True)
    assert dlg.table.isRowHidden(named) is True
    assert dlg.table.isRowHidden(other) is True
    dlg.remember_last_connect("aa-bb-cc-dd-ee-01", when=1700000000)
    assert dlg.table.isRowHidden(named) is False
    assert dlg.table.isRowHidden(other) is True
    dlg.table.selectRow(named)
    when = dlg._format_last_connect("AA:BB:CC:DD:EE:01")
    assert when
    assert w._t("ble_adv_last_connect", when=when) in dlg.txt_detail.toPlainText()


def test_ble_scan_showevent_reloads_last_used(tmp_path, monkeypatch):
    from ble_scan_dialog import remember_ble_connect

    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    dlg.chk_filt["hide_empty"].setChecked(False)
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"])
    remember_ble_connect(w.settings, "AA:BB:CC:DD:EE:01", when=1700000000)
    dlg.chk_filt["last_used"].setChecked(True)
    assert dlg.table.isRowHidden(_row_by_addr(dlg, "AA:BB:CC:DD:EE:01")) is True
    dlg.show()
    _APP.processEvents()
    assert dlg.table.isRowHidden(_row_by_addr(dlg, "AA:BB:CC:DD:EE:01")) is False


def test_ble_scan_has_mfr_without_snap(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    dlg.chk_filt["hide_empty"].setChecked(False)
    dlg.upsert("AA:BB:CC:DD:EE:01", "GEE701", -51, ["fff0"], {
        "manufacturer": [(0x004C, "aa")],
    })
    dlg.upsert("AA:BB:CC:DD:EE:02", "Other", -70, ["fe95"], {
        "manufacturer": [],
    })
    dlg.chk_filt["has_mfr"].setChecked(True)
    named = _row_by_addr(dlg, "AA:BB:CC:DD:EE:01")
    other = _row_by_addr(dlg, "AA:BB:CC:DD:EE:02")
    assert dlg._row_blocked_by_rules(named) is False
    assert dlg._row_blocked_by_rules(other) is True


def test_ble_rssi_filter_label_has_object_name(tmp_path, monkeypatch):
    w = _make_window(tmp_path, monkeypatch)
    dlg = w._ble_scan_dialog()
    assert dlg.lbl_rssi_filter.objectName() == "BleRssiFilter"


def test_flow_layout_respects_margins():
    from PyQt5.QtWidgets import QLabel, QWidget
    from widgets import FlowLayout

    host = QWidget()
    flow = FlowLayout(host, margin=8, spacing=4)
    a = QLabel("AAAA")
    b = QLabel("BBBB")
    flow.addWidget(a)
    flow.addWidget(b)
    wrapped = flow.heightForWidth(40)
    assert wrapped >= (
        a.sizeHint().height() + b.sizeHint().height() + 4 + 16)
