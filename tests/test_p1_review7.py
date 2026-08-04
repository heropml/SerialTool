import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import modbus_master
import modbus_slave
import rec_diff
import rec_replay
from main_window import CommTool, PortScannerThread
from rec_diff_dialog import RecDiffDialog
from rec_replay_dialog import RecReplayDialog


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


def test_step_pauses_before_advancing(tmp_path, monkeypatch):
    """Stepping while the clock runs used to inject the next event early."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("rr-step-pause-test")
    try:
        dlg = RecReplayDialog(window)
        try:
            events = [(0.0, "rx", b"A"), (1.0, "rx", b"B"), (2.0, "rx", b"C")]
            got = []
            player = rec_replay.Player(events, got.append)
            now = rec_replay.time.monotonic()
            player.start(now)
            player.tick(now)               # 第 1 条按时到点
            assert len(got) == 1
            dlg._player = player
            dlg._on_step()
            assert player.paused           # 单步必须先暂停，时钟不再自己往前跑
            assert not dlg._timer.isActive()
            assert len(got) == 2
            # 暂停后走过的媒体时间停在被单步的事件上，恢复时不会补喷后续事件。
            assert player.tick(now + 5.0) == 0
            player.resume(now + 5.0)
            assert player.tick(now + 5.0) == 0
            assert player.tick(now + 6.1) == 1
            assert len(got) == 3
        finally:
            dlg._player = None
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def _diff_dialog_with_rows(window):
    dlg = RecDiffDialog(window)
    dlg._path_a = "a.ctrec"
    dlg._path_b = "b.ctrec"
    dlg._events_a = [(0.0, "rx", b"\x01"), (1.0, "tx", b"\x02")]
    dlg._events_b = [(0.0, "rx", b"\x01"), (1.0, "tx", b"\x99")]
    dlg._on_compare()
    return dlg


def test_diff_stats_follow_visible_rows(tmp_path, monkeypatch):
    """Filtering shrank the table but left the summary counters at global values."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("rd-stats-filter-test")
    try:
        dlg = _diff_dialog_with_rows(window)
        try:
            dlg.chk_only_diff.setChecked(False)
            dlg._fill_table()
            assert len(dlg._filtered_rows()) == 2
            same_all = dlg.lbl_stat.text()

            dlg.cb_dir_filter.setCurrentIndex(dlg.cb_dir_filter.findData("tx"))
            dlg._fill_table()
            assert len(dlg._filtered_rows()) == 1
            assert dlg.lbl_stat.text() != same_all
            assert dlg.lbl_stat.text() == window._t(
                "rd_stat", same=0, diff=1, a=0, b=0)
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_export_disabled_when_filter_hides_everything(tmp_path, monkeypatch):
    """An empty filtered view used to export a header-only CSV and report success."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("rd-export-empty-test")
    try:
        dlg = _diff_dialog_with_rows(window)
        try:
            assert dlg.btn_export.isEnabled()
            dlg.ed_min_dt.setText("999")       # |dt| 门限筛掉全部配对行
            dlg._fill_table()
            assert dlg._filtered_rows() == []
            assert not dlg.btn_export.isEnabled()
            dlg.ed_min_dt.setText("")
            dlg._fill_table()
            assert dlg.btn_export.isEnabled()
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_fc23_exception_policy_matches_write_address():
    """An addrs policy aimed at FC23's written registers never fired before."""
    policy = {"enabled": True, "code": 4, "mode": "always",
              "funcs": [0x17], "addrs": [5]}
    s = modbus_slave.ModbusSlave(
        addr=1, holding={0: 10, 1: 20, 5: 0}, exception_policy=policy)
    req = modbus_master.build_rtu_request(
        1, 0x17, 0,
        {"read_addr": 0, "read_qty": 2, "write_addr": 5, "write_vals": [99]})
    resp = s.handle(req)
    assert resp[1] == 0x97                 # 0x17 | 0x80
    assert resp[2] == 4
    assert s.holding[5] == 0               # 注入发生在写入之前，不留半个写

    # 读段地址命中同样有效（原有行为不能回退）。
    s2 = modbus_slave.ModbusSlave(
        addr=1, holding={0: 10, 1: 20, 5: 0},
        exception_policy=dict(policy, addrs=[0]))
    assert s2.handle(req)[1] == 0x97

    # 都不命中时正常放行。
    s3 = modbus_slave.ModbusSlave(
        addr=1, holding={0: 10, 1: 20, 5: 0},
        exception_policy=dict(policy, addrs=[77]))
    assert modbus_master.parse_pdu(0x17, s3.handle(req)[1:-2])["regs"] == [10, 20]
    assert s3.holding[5] == 99


def test_once_mode_not_double_counted_by_multi_address_check():
    """The multi-candidate address check must stay a single should_raise call."""
    import modbus_dyn
    inj = modbus_dyn.ExceptionInjector(
        {"enabled": True, "code": 4, "mode": "once", "funcs": [0x17], "addrs": [5]})
    assert inj.should_raise(0x17, (0, 5)) == 4
    assert inj.should_raise(0x17, (0, 5)) is None
    assert inj.policy["_hits"] == 1
