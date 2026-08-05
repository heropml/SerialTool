# -*- coding: utf-8 -*-
"""Regressions for the gateway / multi-view / trigger-action review fixes."""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import modbus_master as mm
import modbus_slave as ms
from main_window import CommTool, PortScannerThread
from modbus_master_dialog import ModbusMasterDialog
from modbus_gateway import ModbusGatewayEngine, EXC_GATEWAY_NO_RESPONSE

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


# ---------------------------------------------------------------- gateway ---

def test_gateway_reassembles_split_tcp_frame():
    """TCP is a stream: half a MBAP frame must be buffered, not dropped."""
    gw = ModbusGatewayEngine()
    req = mm.build_tcp_request(1, 7, 3, 0, 2)
    rtu_out, _ = gw.feed_tcp(req[:5])
    assert rtu_out == []
    rtu_out, _ = gw.feed_tcp(req[5:])
    assert len(rtu_out) == 1
    assert rtu_out[0][0] == 7 and rtu_out[0][1] == 3


def test_gateway_queues_second_request_until_bus_frees():
    slave = ms.ModbusSlave(addr=1, holding={0: 0x1111, 1: 0x2222})
    gw = ModbusGatewayEngine()
    first, second = mm.build_tcp_request(1, 1, 3, 0, 1), mm.build_tcp_request(2, 1, 3, 1, 1)
    rtu_out, _ = gw.feed_tcp(first + second)          # both frames in one chunk
    assert len(rtu_out) == 1                          # half duplex: one at a time
    assert gw.stats["tcp_rx"] == 2 and gw.stats["drops"] == 0

    rtu_out2, tcp_out2 = gw.feed_rtu(slave.handle(rtu_out[0]))
    assert len(tcp_out2) == 1                         # first answer goes back
    assert len(rtu_out2) == 1                         # queued request now starts
    _, tcp_out3 = gw.feed_rtu(slave.handle(rtu_out2[0]))
    assert len(tcp_out3) == 1
    assert mm.take_tcp_response(tcp_out3[0].frame, 2, 3, 1)[0]["regs"] == [0x2222]


def test_gateway_broadcast_does_not_stall_the_bus():
    """Unit 0 never answers; the next request must not wait for a timeout."""
    gw = ModbusGatewayEngine()
    rtu_out, _ = gw.feed_tcp(mm.build_tcp_request(1, 0, 6, 0, 5))
    assert len(rtu_out) == 1 and rtu_out[0][0] == 0
    rtu_out2, _ = gw.feed_tcp(mm.build_tcp_request(2, 1, 3, 0, 1))
    assert len(rtu_out2) == 1                         # dispatched immediately


def test_gateway_timeout_answers_with_exception_0b():
    gw = ModbusGatewayEngine(timeout_s=0.05)
    gw.feed_tcp(mm.build_tcp_request(9, 1, 3, 0, 1))
    time.sleep(0.06)
    _, tcp_out = gw.tick()
    assert len(tcp_out) == 1
    frame = tcp_out[0].frame
    assert frame[0:2] == b"\x00\x09"                  # same transaction id
    assert frame[7] == 0x83 and frame[8] == EXC_GATEWAY_NO_RESPONSE
    assert gw.stats["timeouts"] == 1


def test_gateway_forwards_slave_exception_response():
    """An RTU exception reply must reach the TCP master, not be chewed away."""
    slave = ms.ModbusSlave(addr=1, holding={0: 1})
    gw = ModbusGatewayEngine()
    # Hand-built frame: the gateway is a pure proxy and must pass through a
    # function code it does not implement itself.
    pdu = bytes([0x63, 0x00, 0x00, 0x00, 0x01])
    req = bytes([0x00, 0x03, 0x00, 0x00, 0x00, len(pdu) + 1, 0x01]) + pdu
    rtu_out, _ = gw.feed_tcp(req)
    assert len(rtu_out) == 1
    resp = slave.handle(rtu_out[0])
    assert resp is not None and resp[1] & 0x80
    _, tcp_out = gw.feed_rtu(resp)
    assert len(tcp_out) == 1
    frame = tcp_out[0].frame
    assert frame[0:2] == b"\x00\x03"
    assert frame[7] == 0xE3 and frame[8] == 0x01   # illegal function
    assert gw.stats["drops"] == 0


# ------------------------------------------------------------- FC43 detail ---

def test_fc43_regular_stream_covers_objects_up_to_0x7f():
    """Read code 2 is basic+regular (0x00-0x7F), not an arbitrary first few."""
    slave = ms.ModbusSlave(addr=1, device_id_objects={0x10: b"regular", 0x90: b"ext"})
    req = mm.build_rtu_request(1, 0x2B, 0, {"read_code": 2, "object_id": 0})
    out = mm.take_rtu_response(slave.handle(req), 1, 0x2B, 1)
    objects = out[0]["device_id"]["objects"]
    assert 0x10 in objects and objects[0x10] == b"regular"
    assert 0x90 not in objects            # extended stays out of the regular stream


def test_fc43_zero_object_response_parses():
    """A device may legally answer with no objects; PDU is 7 bytes, not 8."""
    parsed = mm.parse_pdu(0x2B, bytes([0x2B, 0x0E, 0x01, 0x81, 0x00, 0x00, 0x00]))
    assert parsed["device_id"]["objects"] == {}
    assert parsed["device_id"]["read_code"] == 1


# ------------------------------------------------------- device center cols ---

def test_device_register_thresholds_round_trip():
    from PyQt5.QtWidgets import QTableWidget
    from device_center_dialog import DeviceCenterDialog, _REGISTER_COLUMNS

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)   # UI-free: table only
    dlg.table = QTableWidget(0, len(_REGISTER_COLUMNS))
    DeviceCenterDialog._append_register(dlg, {
        "name": "v", "address": 4, "type": "u32", "order": "CDAB",
        "addr_base": 1, "bitfields": "0:4:lo,4:4:hi",
        "warn_lo": 1.5, "warn_hi": 8, "alarm_hi": 9.5,
    })
    rec = DeviceCenterDialog._collect_registers(dlg)[0]
    assert rec["addr_base"] == 1 and rec["display_address"] == 5
    assert rec["bitfields"] == "0:4:lo,4:4:hi"
    assert rec["warn_lo"] == 1.5 and rec["warn_hi"] == 8.0
    assert rec["alarm_lo"] is None and rec["alarm_hi"] == 9.5
    dlg.table.deleteLater()


def test_device_register_blank_thresholds_stay_unset():
    from PyQt5.QtWidgets import QTableWidget
    from device_center_dialog import DeviceCenterDialog, _REGISTER_COLUMNS

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)
    dlg.table = QTableWidget(0, len(_REGISTER_COLUMNS))
    DeviceCenterDialog._append_register(dlg, {"name": "v", "address": 0})
    rec = DeviceCenterDialog._collect_registers(dlg)[0]
    assert rec["warn_lo"] is None and rec["warn_hi"] is None
    assert rec["alarm_lo"] is None and rec["alarm_hi"] is None
    assert rec["bitfields"] == "" and rec["addr_base"] == 0
    dlg.table.deleteLater()


# ---------------------------------------------------------- bridge wiring ---

class _FakeConn(QObject):
    data_received = pyqtSignal(bytes)
    state_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.is_open = True
        self.sent = []

    def send(self, data):
        self.sent.append(bytes(data))
        return len(data)

    def close(self):
        self.is_open = False


def _gw_bridge():
    from bridge import BridgeEngine
    eng = BridgeEngine()
    a, b = _FakeConn(), _FakeConn()
    eng.set_connection(0, a)
    eng.set_connection(1, b)
    eng.set_modbus_gateway(True)
    assert eng.start()
    return eng, a, b


def test_bridge_gateway_round_trip_records_both_directions():
    """Both legs must update tx counters and rate samples, not just one."""
    eng, a, b = _gw_bridge()
    try:
        slave = ms.ModbusSlave(addr=1, holding={0: 0x0042})
        a.data_received.emit(mm.build_tcp_request(1, 1, 3, 0, 1))
        assert len(b.sent) == 1 and b.sent[0][0] == 1
        b.data_received.emit(slave.handle(b.sent[0]))
        assert len(a.sent) == 1
        assert mm.take_tcp_response(a.sent[0], 1, 3, 1)[0]["regs"] == [0x0042]

        stats = {}
        eng.stats_updated.connect(lambda *v: stats.update(
            dict(zip("a_rx a_tx b_rx b_tx a_rate b_rate".split(), v))))
        eng._tick_rate()
        assert stats["a_rate"] > 0 and stats["b_rate"] > 0
        assert stats["a_tx"] == len(a.sent[0]) and stats["b_tx"] == len(b.sent[0])
    finally:
        eng.stop()


def test_bridge_gateway_timeout_reaches_side_a():
    eng, a, b = _gw_bridge()
    try:
        eng._gateway.timeout_s = 0.05
        a.data_received.emit(mm.build_tcp_request(4, 1, 3, 0, 1))
        assert len(b.sent) == 1
        assert a.sent == []
        time.sleep(0.06)
        eng._tick_gateway()
        assert len(a.sent) == 1
        assert a.sent[0][7] == 0x83 and a.sent[0][8] == EXC_GATEWAY_NO_RESPONSE
    finally:
        eng.stop()


# ------------------------------------------------------------ master views ---

def _rule(name, group, addr):
    return mm.normalize_poll({"enabled": True, "name": name, "group": group,
                              "unit": 1, "func": 3, "addr": addr, "qty": 1,
                              "period": 1000})


def test_view_commit_keeps_global_rule_order(tmp_path, monkeypatch):
    """Applying one view must not renumber the other views' rules.

    The engine reports results by global rule index, so a reshuffle here shows
    another view's answer on the wrong row.
    """
    _patch_window_runtime(monkeypatch, tmp_path / "views.ini")
    window = CommTool("mbm-views-order")
    try:
        window._mbm_rules = [_rule("d0", "", 0), _rule("d1", "", 1),
                             _rule("a0", "A", 10), _rule("a1", "A", 11)]
        window._mbm_views = ["A"]
        monkeypatch.setattr(CommTool, "_mbm_restart", lambda self: None)
        dlg = ModbusMasterDialog(window)
        try:
            assert dlg._view_name == ""
            assert dlg._row_rule_index == [0, 1]
            dlg._dirty = True
            dlg._commit()
            names = [r["name"] for r in window._mbm_rules]
            assert names == ["d0", "d1", "a0", "a1"]
            assert dlg._row_rule_index == [0, 1]

            dlg.tabs.setCurrentIndex(1)                  # switch to view A
            assert dlg._view_name == "A"
            assert dlg._row_rule_index == [2, 3]
            dlg._dirty = True
            dlg._commit()
            assert [r["name"] for r in window._mbm_rules] == ["d0", "d1", "a0", "a1"]
            assert dlg._row_rule_index == [2, 3]
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_view_tab_order_is_stable(tmp_path, monkeypatch):
    """Tabs follow view creation order, so they never jump while editing."""
    _patch_window_runtime(monkeypatch, tmp_path / "tabs.ini")
    window = CommTool("mbm-views-tabs")
    try:
        window._mbm_rules = [_rule("a0", "A", 0)]        # default view has no rules
        window._mbm_views = ["A", "B"]
        monkeypatch.setattr(CommTool, "_mbm_restart", lambda self: None)
        dlg = ModbusMasterDialog(window)
        try:
            assert dlg._views() == ["", "A", "B"]
            assert dlg.tabs.count() == 3
            assert dlg._view_name == ""                  # default is always first
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


# --------------------------------------------------------- trigger actions ---

def test_trigger_action_import_gate_strips_external_actions(tmp_path, monkeypatch):
    import json
    _patch_window_runtime(monkeypatch, tmp_path / "gate.ini")
    window = CommTool("trg-gate")
    try:
        rules = [{"name": "a", "pattern": "x", "run_cmd": "calc.exe", "run_cmd_on": True},
                 {"name": "b", "pattern": "y", "webhook_url": "http://h", "webhook": True},
                 {"name": "c", "pattern": "z"}]
        data = {"triggers": json.dumps(rules)}

        asked = []
        window._ar_confirm = lambda title, body: (asked.append(body), False)[1]
        out = json.loads(window._gate_imported_trigger_actions(data)["triggers"])
        assert len(asked) == 1 and "2" in asked[0]
        assert all("run_cmd" not in r and "webhook_url" not in r for r in out)
        assert [r["name"] for r in out] == ["a", "b", "c"]

        window._ar_confirm = lambda title, body: True
        kept = json.loads(window._gate_imported_trigger_actions(data)["triggers"])
        assert kept[0]["run_cmd"] == "calc.exe"
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_trigger_action_gate_is_silent_without_external_actions(tmp_path, monkeypatch):
    import json
    _patch_window_runtime(monkeypatch, tmp_path / "gate2.ini")
    window = CommTool("trg-gate-quiet")
    try:
        data = {"triggers": json.dumps([{"name": "a", "pattern": "x", "beep": True}])}
        window._ar_confirm = lambda title, body: (_ for _ in ()).throw(
            AssertionError("must not prompt"))
        assert window._gate_imported_trigger_actions(data) is data
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_trigger_actions_are_capped_in_flight(tmp_path, monkeypatch):
    """Cooldown can be 0; without a cap a busy link spawns unbounded workers."""
    import threading
    _patch_window_runtime(monkeypatch, tmp_path / "cap.ini")
    window = CommTool("trg-cap")
    try:
        release = threading.Event()
        started = threading.Semaphore(0)

        def _block():
            started.release()
            release.wait(5)

        ok = [window._trg_spawn_action(_block) for _ in range(window._TRG_MAX_ACTIONS)]
        assert all(ok)
        for _ in range(window._TRG_MAX_ACTIONS):
            assert started.acquire(timeout=5)
        assert window._trg_spawn_action(_block) is False
        assert window._trg_action_dropped == 1
        release.set()
        for _ in range(50):
            if window._trg_action_busy == 0:
                break
            time.sleep(0.05)
        assert window._trg_action_busy == 0
        assert window._trg_spawn_action(lambda: None) is True
    finally:
        release.set()
        window.deleteLater()
        _APP.processEvents()


def test_run_cmd_holds_its_slot_until_the_child_exits(tmp_path, monkeypatch):
    """并发上限必须覆盖子进程的存活期，而不只是启动动作。

    Popen() 启动即返回。worker 若不等待，线程几微秒就退出并把名额还回去，
    上限就只限制「同时在启动中的动作数」——冷却设 0 时子进程照样无限堆积。
    """
    _patch_window_runtime(monkeypatch, tmp_path / "runcmd.ini")
    window = CommTool("trg-runcmd")
    try:
        rule = {"run_cmd_on": True,
                "run_cmd": '"%s" -c "import time;time.sleep(0.6)"' % sys.executable}
        window._trg_run_cmd(rule, "t", 0, 1)
        # 在子进程存活期中段取样：不等待的话此刻 worker 早已退出、名额已归还。
        # 用固定时刻而非"轮询到 1 就通过"，避免恰好撞上启动瞬间造成误判。
        time.sleep(0.25)
        assert window._trg_action_busy == 1     # 子进程还在跑，名额不能释放
        for _ in range(100):
            if window._trg_action_busy == 0:
                break
            time.sleep(0.05)
        assert window._trg_action_busy == 0     # 子进程退出后才释放
    finally:
        window.deleteLater()
        _APP.processEvents()
