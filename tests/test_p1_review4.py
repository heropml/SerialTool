import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import modbus_master
import modbus_slave
from main_window import CommTool, PortScannerThread
from modbus_master_dialog import ModbusMasterDialog


_APP = QApplication.instance() or QApplication([])


def _patch_window_runtime(monkeypatch, settings_path):
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(settings_path)))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)


def test_fc23_qty_field_with_colon_before_at_is_not_fatal(tmp_path, monkeypatch):
    """'2 : 3 @ 10' used to raise ValueError while unpacking the '@' split.

    That ordering is not a supported format, so the requirement is that it
    degrades into a rule the poller rejects (empty write values) instead of
    crashing the dialog — assert that outcome, not merely the absence of a raise.
    """
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("mbm-fc23-parse-test")
    try:
        window._mbm_rules = [{
            "enabled": True, "name": "rw", "unit": 1, "func": 0x17,
            "addr": 0, "qty": 1, "period": 1000,
            "wvals": [1], "write_addr": 10,
        }]
        dlg = ModbusMasterDialog(window)
        try:
            dlg._rows[0]["qty"].setText("2 : 3 @ 10")
            collected = dlg._collect()
            assert len(collected) == 1
            bad = modbus_master.normalize_poll(collected[0])
            assert bad["func"] == 0x17
            assert bad["qty"] == 2
            # ": 3 @ 10" 不是合法值列表 → 整组作废（绝不能截半写进错误地址）
            assert bad["rw"]["write_vals"] == []

            dlg._rows[0]["qty"].setText("2 @ 10 : 1 2")
            rule = modbus_master.normalize_poll(dlg._collect()[0])
            assert rule["write_addr"] == 10
            assert rule["rw"]["write_vals"] == [1, 2]
            assert rule["qty"] == 2
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_slave_without_server_id_inherits_top_level(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("mbm-serverid-inherit-test")
    try:
        cfg = window._norm_ar_modbus({
            "on": True, "addr": 1, "server_id": "MyDev",
            "slaves": [{"addr": 1}, {"addr": 2, "server_id": "Other"}],
        })
        assert "server_id" not in cfg["slaves"][0]
        bank = modbus_slave.slave_bank_from_config(cfg)
        assert bank.slaves[1].server_id == b"MyDev"
        assert bank.slaves[2].server_id == b"Other"
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_diag_and_server_id_results_are_translated(tmp_path, monkeypatch):
    """Comparing against window._t(...) would pass even if i18n returned raw keys,
    so assert on the rendered text and on the languages actually differing."""
    import i18n

    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("mbm-result-i18n-test")
    try:
        rendered = {}
        for lang in ("zh", "en", "zh_tw"):
            window._L = i18n.TR[lang]
            diag = window._mbm_fmt_result({"func": 0x08, "qty": 1}, {"diag": (0, 0x1234)})
            events = window._mbm_fmt_result(
                {"func": 0x0B, "qty": 1}, {"status": 0, "event_count": 7})
            sid = window._mbm_fmt_result(
                {"func": 0x11, "qty": 1}, {"server_id": b"CommTool", "run": True})
            for text in (diag, events, sid):
                assert "mbm_st_" not in text        # 没落回键名
                assert "{" not in text              # 占位符全部替换掉了
            # 回环数据同时给十进制与十六进制，便于和发出的值对照
            assert "4660" in diag and "0x1234" in diag
            assert "7" in events
            assert "CommTool" in sid
            rendered[lang] = (diag, events, sid)
        # 三张表各自生效，不是同一份英文兜底。
        assert rendered["zh"] != rendered["en"]
        assert rendered["zh_tw"] != rendered["en"]
    finally:
        window.deleteLater()
        _APP.processEvents()
