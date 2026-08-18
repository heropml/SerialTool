# -*- coding: utf-8 -*-
"""Regressions for the gateway / multi-view / trigger-action review fixes."""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus import modbus_master as mm
from modbus import modbus_slave as ms
from main_window import CommTool, PortScannerThread
from ui.modbus_master_dialog import ModbusMasterDialog
from modbus.modbus_gateway import ModbusGatewayEngine, EXC_GATEWAY_NO_RESPONSE

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
    # tick() 接受 now=：直接把时针拨到超时后，不依赖真实 sleep
    gw._pending["t0"] = 1000.0
    _, tcp_out = gw.tick(now=1000.06)
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
    from ui.device_center_dialog import DeviceCenterDialog, _REGISTER_COLUMNS

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
    from ui.device_center_dialog import DeviceCenterDialog, _REGISTER_COLUMNS

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)
    dlg.table = QTableWidget(0, len(_REGISTER_COLUMNS))
    DeviceCenterDialog._append_register(dlg, {"name": "v", "address": 0})
    rec = DeviceCenterDialog._collect_registers(dlg)[0]
    assert rec["warn_lo"] is None and rec["warn_hi"] is None
    assert rec["alarm_lo"] is None and rec["alarm_hi"] is None
    assert rec["bitfields"] == "" and rec["addr_base"] == 0
    dlg.table.deleteLater()


def test_structured_record_table_shows_threshold_level():
    """记录表要显示阈值级别，否则寄存器表里配的 warn/alarm 在界面上仍然无感。"""
    import types
    from ui.structured_record_dialog import StructuredRecordDialog

    texts = {"structured_level_warn": "预警", "structured_level_alarm": "报警"}
    dlg = StructuredRecordDialog.__new__(StructuredRecordDialog)
    dlg.app = types.SimpleNamespace(_t=texts.__getitem__)
    assert dlg._level_text("alarm") == "报警"
    assert dlg._level_text("warn") == "预警"
    assert dlg._level_text("") == ""        # 未配阈值的行保持空白
    assert dlg._level_text(None) == ""


def test_device_center_address_column_uses_the_selected_base():
    """地址列必须按地址基显示，否则切到 1 基后界面上看不出任何变化。"""
    from PyQt5.QtWidgets import QTableWidget
    from ui.device_center_dialog import DeviceCenterDialog, _REGISTER_COLUMNS

    dlg = DeviceCenterDialog.__new__(DeviceCenterDialog)
    dlg.table = QTableWidget(0, len(_REGISTER_COLUMNS))
    DeviceCenterDialog._append_register(dlg, {"name": "v", "address": 40000,
                                              "addr_base": 1})
    assert dlg.table.item(0, 4).text() == "40001"      # 显示按 1 基
    rec = DeviceCenterDialog._collect_registers(dlg)[0]
    assert rec["address"] == 40000                     # 存回去仍是协议 0 基
    assert rec["display_address"] == 40001
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
    from modbus.bridge import BridgeEngine
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
        # Pin pending timestamp so tick() uses deterministic time
        # instead of real time.sleep, avoiding flaky CI failures.
        eng._gateway._pending["t0"] = time.monotonic() - eng._gateway.timeout_s - 0.01
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



def test_deleting_a_view_asks_first(tmp_path, monkeypatch):
    """删视图会当场清空那些规则的分组并落盘，没有 undo，必须先问。

    + / - 两个按钮相邻且只有 28×28，按错很容易。
    """
    _patch_window_runtime(monkeypatch, tmp_path / "delview.ini")
    window = CommTool("mbm-del-view")
    try:
        window._mbm_rules = [_rule("a0", "A", 0), _rule("a1", "A", 1),
                             _rule("b0", "B", 2)]
        window._mbm_views = ["A", "B"]
        monkeypatch.setattr(CommTool, "_mbm_restart", lambda self: None)
        asked = []
        monkeypatch.setattr(window, "_confirm_dlg",
                            lambda title, body, **kw: (asked.append(body), False)[1])
        dlg = ModbusMasterDialog(window)
        try:
            dlg.tabs.setCurrentIndex(1)
            assert dlg._view_name == "A"
            dlg._del_view()
            assert len(asked) == 1
            assert "A" in asked[0] and "2" in asked[0]   # 告知名字与受影响条数
            assert window._mbm_views == ["A", "B"]       # 取消 → 一点都没动
            assert [r["group"] for r in window._mbm_rules] == ["A", "A", "B"]

            monkeypatch.setattr(window, "_confirm_dlg", lambda *a, **k: True)
            dlg._del_view()
            assert window._mbm_views == ["B"]            # 确认 → 才真删
            assert [r["group"] for r in window._mbm_rules] == ["", "", "B"]
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
        # 子进程的寿命由哨兵文件控制，不看墙上时间：用固定 sleep 取样时，
        # 机器一卡 sleep 就会超调到子进程（0.6s）已退出，在 CI 上偶发失败。
        child = tmp_path / "child.py"
        child.write_text(
            "import os, sys, time\n"
            "deadline = time.time() + 10\n"
            "while not os.path.exists(sys.argv[1]) and time.time() < deadline:\n"
            "    time.sleep(0.02)\n", encoding="utf-8")
        sentinel = tmp_path / "go"
        rule = {"run_cmd_on": True,
                "run_cmd": '"%s" "%s" "%s"' % (sys.executable, child, sentinel)}
        window._trg_run_cmd(rule, "t", 0, 1)
        procs = []
        for _ in range(250):
            with window._trg_action_lock:
                procs = list(window._trg_procs)
            if procs:
                break
            time.sleep(0.02)
        assert procs, "子进程没起来"
        proc = procs[0]
        # 哨兵未出现 → 子进程必定还活着 → 名额不得释放
        for _ in range(5):
            assert proc.poll() is None
            assert window._trg_action_busy == 1
            time.sleep(0.02)

        sentinel.write_text("go", encoding="utf-8")
        for _ in range(250):
            if window._trg_action_busy == 0:
                break
            time.sleep(0.02)
        assert window._trg_action_busy == 0     # 子进程退出后才释放
    finally:
        sentinel.write_text("go", encoding="utf-8")
        window._trg_stop_procs()
        window.deleteLater()
        _APP.processEvents()


def test_run_cmd_children_are_tracked_and_reaped(tmp_path, monkeypatch):
    """退出必须收掉外部程序拉起的子进程。

    动作 worker 是 daemon 线程，解释器退出时会被直接掐掉，但它启动的是独立的
    OS 进程：不主动回收的话，命令跑得久或卡死时 CommTool 关了它们还在。
    """
    _patch_window_runtime(monkeypatch, tmp_path / "reap.ini")
    window = CommTool("trg-reap")
    try:
        rule = {"run_cmd_on": True,
                "run_cmd": '"%s" -c "import time;time.sleep(30)"' % sys.executable}
        window._trg_run_cmd(rule, "t", 0, 1)
        procs = []
        for _ in range(100):
            with window._trg_action_lock:
                procs = list(window._trg_procs)
            if procs:
                break
            time.sleep(0.02)
        assert procs, "子进程句柄没有登记到 _trg_procs"
        proc = procs[0]
        assert proc.poll() is None

        window._trg_stop_procs()
        for _ in range(100):
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        assert proc.poll() is not None      # 已终止
        assert not window._trg_procs        # 表也清空
    finally:
        window._trg_stop_procs()
        window.deleteLater()
        _APP.processEvents()


def test_shutdown_reaps_run_cmd_children(tmp_path, monkeypatch):
    """回收动作要挂在退出流程上，不能只是有个能用的方法。"""
    _patch_window_runtime(monkeypatch, tmp_path / "reap2.ini")
    window = CommTool("trg-reap2")
    called = []
    try:
        window._trg_stop_procs = lambda: called.append(True)
        window._shutdown()
        assert called == [True]
    finally:
        window.deleteLater()
        _APP.processEvents()


_SIGKILL = getattr(signal, "SIGKILL", 9)   # Windows 的 signal 没有 SIGKILL


class _FakeProc:
    """Popen 替身：模拟一个长跑的子进程，被终止后 wait() 才返回。

    若 wait() 立即返回，等于命令瞬时自己跑完了，回收逻辑根本无从验证。
    """

    def __init__(self, pid=4242):
        self.pid = pid
        self._done = threading.Event()

    @property
    def dead(self):
        return self._done.is_set()

    def poll(self):
        return 0 if self._done.is_set() else None

    def wait(self, timeout=None):
        if not self._done.wait(5 if timeout is None else timeout):
            raise subprocess.TimeoutExpired("fake", timeout)
        return 0

    def terminate(self):
        self._done.set()

    def kill(self):
        self._done.set()


def _fake_launch(monkeypatch, on_call=None, proc=None):
    """把 run_cmd 里的 Popen 换成替身，返回它收到的 kwargs。"""
    import subprocess
    seen = {}
    proc = proc or _FakeProc()

    def fake_popen(cmd, **kwargs):
        seen.update(kwargs)
        if on_call is not None:
            on_call()
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return seen, proc


def test_shutdown_waits_for_a_launch_in_flight(tmp_path, monkeypatch):
    """Popen 返回与句柄登记之间有窗口，退出必须等这段收尾。

    只扫一遍 _trg_procs 的话，正好落在窗口里的进程谁都不管，CommTool 关掉后
    它会留在系统里。
    """
    _patch_window_runtime(monkeypatch, tmp_path / "race.ini")
    window = CommTool("trg-race")
    killed = []
    started = threading.Event()
    release = threading.Event()
    try:
        _, proc = _fake_launch(monkeypatch, on_call=lambda: (started.set(),
                                                             release.wait(5)))
        monkeypatch.setattr(
            type(window), "_trg_kill_proc",
            staticmethod(lambda p: (killed.append(p), p.terminate())))

        window._trg_run_cmd({"run_cmd_on": True, "run_cmd": "x"}, "t", 0, 1)
        assert started.wait(3), "worker 没进到 Popen"
        # 此刻进程「已启动、未登记」——正是竞态窗口
        with window._trg_action_lock:
            assert window._trg_launching == 1
            assert not window._trg_procs

        threading.Timer(0.15, release.set).start()
        t0 = time.time()
        window._trg_stop_procs()
        assert time.time() - t0 >= 0.1      # 确实等了在途启动
        assert killed == [proc]             # 没漏掉
    finally:
        release.set()
        window.deleteLater()
        _APP.processEvents()


def test_no_new_actions_once_shutdown_started(tmp_path, monkeypatch):
    """闸门竖起后不再拉新进程，否则边收边起永远收不干净。"""
    _patch_window_runtime(monkeypatch, tmp_path / "race2.ini")
    window = CommTool("trg-race2")
    try:
        calls = []
        _fake_launch(monkeypatch, on_call=lambda: calls.append(1))
        window._trg_stop_procs()

        assert window._trg_spawn_action(lambda: None) is False
        window._trg_run_cmd({"run_cmd_on": True, "run_cmd": "x"}, "t", 0, 1)
        time.sleep(0.1)
        assert calls == []                  # 一个都没起
        assert window._trg_action_dropped == 0   # 这不算「因上限丢弃」
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_run_cmd_starts_a_new_session_off_windows(tmp_path, monkeypatch):
    """POSIX 上 shell=True 只杀 shell 会漏掉孙进程，所以要自成进程组。"""
    _patch_window_runtime(monkeypatch, tmp_path / "race3.ini")
    window = CommTool("trg-race3")
    try:
        monkeypatch.setattr(sys, "platform", "linux")
        seen, _ = _fake_launch(monkeypatch)
        window._trg_run_cmd({"run_cmd_on": True, "run_cmd": "x"}, "t", 0, 1)
        for _ in range(100):
            if seen:
                break
            time.sleep(0.02)
        assert seen.get("start_new_session") is True
        assert "creationflags" not in seen
    finally:
        window._trg_stop_procs()
        window.deleteLater()
        _APP.processEvents()


def test_kill_proc_uses_the_process_group_off_windows(monkeypatch):
    """回收走 killpg：按组号杀，组长退出后后代仍用它的 PID 当 PGID。"""
    import os as _os
    signals = []
    proc = _FakeProc(pid=777)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(_os, "killpg",
                        lambda pgid, sig: (signals.append((pgid, sig)),
                                           proc.terminate()),
                        raising=False)          # Windows 的 os 没有 killpg
    CommTool._trg_kill_proc(proc)
    assert signals == [(777, signal.SIGTERM), (777, _SIGKILL)]
    assert proc.dead


def test_kill_proc_sigkills_the_group_even_if_the_leader_is_gone(monkeypatch):
    """组长（父 shell）已退不等于整组已死，SIGKILL 不能省。

    run_cmd 走 shell=True，句柄指向的是 shell；它很容易先退，而真正干活的
    孙进程还留在同一个进程组里——只看组长死没死就会放跑它们。
    """
    import os as _os
    signals = []
    proc = _FakeProc(pid=779)
    proc.terminate()                            # 组长已经不在了
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(_os, "killpg",
                        lambda pgid, sig: signals.append((pgid, sig)),
                        raising=False)
    CommTool._trg_kill_proc(proc)
    assert signals == [(779, signal.SIGTERM), (779, _SIGKILL)]


def test_kill_proc_stops_once_the_group_is_gone(monkeypatch):
    """SIGKILL 报 ProcessLookupError 就是整组已消失，不必再走通用兵底。"""
    import os as _os
    calls = []
    proc = _FakeProc(pid=780)
    fallback = []
    monkeypatch.setattr(type(proc), "terminate",
                        lambda self: fallback.append(1))

    def killpg(pgid, sig):
        calls.append(sig)
        if sig != signal.SIGTERM:
            raise ProcessLookupError
        _FakeProc.kill(proc)                    # SIGTERM 就把组长收了

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(_os, "killpg", killpg, raising=False)
    CommTool._trg_kill_proc(proc)
    assert calls == [signal.SIGTERM, _SIGKILL]
    assert fallback == []                       # 没再走 terminate 那条兼容路径


def test_kill_proc_falls_back_when_taskkill_reports_failure(monkeypatch):
    """taskkill 非 0 退出且进程还活着时不能就此当完成。

    原来只要 taskkill 没抛异常就 return，报错退出（如拒访问）也算收完了。
    """
    proc = _FakeProc(pid=781)
    monkeypatch.setattr(sys, "platform", "win32")

    class _Res:
        returncode = 1

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Res())
    CommTool._trg_kill_proc(proc)
    assert proc.dead                            # 退回 terminate/kill 收住了


def test_taskkill_success_skips_the_fallback(monkeypatch):
    proc = _FakeProc(pid=782)
    monkeypatch.setattr(sys, "platform", "win32")

    class _Res:
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Res())
    CommTool._trg_kill_proc(proc)
    assert not proc.dead                        # taskkill 说收完了，不再多杀一道



def test_taskkill_skipped_when_pid_is_none(monkeypatch):
    """Windows: proc.pid may be None before the child fully starts."""
    proc = _FakeProc(pid=None)
    runs = []
    monkeypatch.setattr(sys, "platform", "win32")

    def _run(*a, **k):
        runs.append(a)

        class _Res:
            returncode = 0

        return _Res()

    monkeypatch.setattr(subprocess, "run", _run)
    CommTool._trg_kill_proc(proc)
    assert runs == []
    assert proc.dead  # fell through to terminate/kill


def test_ar_kill_skips_taskkill_when_pid_is_none(monkeypatch):
    from unittest import mock
    runs = []
    monkeypatch.setattr(sys, "platform", "win32")

    def _run(*a, **k):
        runs.append(a)

        class _Res:
            returncode = 0

        return _Res()

    monkeypatch.setattr(subprocess, "run", _run)
    proc = mock.Mock()
    proc.pid = None
    proc.is_alive.return_value = True
    proc.join = mock.Mock()
    proc.close = mock.Mock()
    CommTool._ar_kill_worker(proc, None, group_ready=True)
    assert runs == []
    proc.join.assert_called()


def test_process_registered_after_shutdown_is_killed_by_its_worker(tmp_path, monkeypatch):
    """_trg_stop_procs 可能已经扫完并返回，此后登记的句柄就无人回收了。

    所以退出态下不再往 _trg_procs 里放，直接由当前 worker 收掉。
    """
    _patch_window_runtime(monkeypatch, tmp_path / "race4.ini")
    window = CommTool("trg-race4")
    killed = []
    try:
        gate = threading.Event()
        _, proc = _fake_launch(monkeypatch, on_call=lambda: gate.wait(5))
        monkeypatch.setattr(
            type(window), "_trg_kill_proc",
            staticmethod(lambda p: (killed.append(p), p.terminate())))

        window._trg_run_cmd({"run_cmd_on": True, "run_cmd": "x"}, "t", 0, 1)
        for _ in range(300):                    # 等 worker 进到 Popen 里
            with window._trg_action_lock:
                if window._trg_launching == 1:
                    break
            time.sleep(0.01)
        with window._trg_action_lock:
            window._trg_stopping = True         # 模拟“已扫完并返回”
        gate.set()                              # Popen 现在才返回，登记落在门禁之后

        for _ in range(300):
            if killed:
                break
            time.sleep(0.01)
        assert killed == [proc]                 # worker 自己收掉了
        with window._trg_action_lock:
            assert not window._trg_procs        # 也没残留在集合里
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_kill_proc_falls_back_when_not_a_group(monkeypatch):
    """没成组（killpg 失败）时退回 terminate，不能就此放过进程。"""
    import os as _os

    def boom(pgid, sig):
        raise ProcessLookupError

    proc = _FakeProc(pid=778)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(_os, "killpg", boom, raising=False)
    CommTool._trg_kill_proc(proc)
    assert proc.dead


def test_shell_value_neutralises_metacharacters():
    """占位符的值必须变成 shell 惰性文本。"""
    q = CommTool._trg_shell_value
    payloads = ("; rm -rf /", "&& del x", "| tee x", "$(id)", "`id`", "a\nrm y")
    for payload in payloads:
        quoted = q(payload)
        assert "\n" not in quoted and "\r" not in quoted
        if sys.platform == "win32":
            # 整体被双引号包住，且内部没有能提前收尾的引号
            assert quoted.startswith('"') and quoted.endswith('"')
            assert '"' not in quoted[1:-1]
            assert "%" not in quoted and "!" not in quoted
        else:
            import shlex
            expected = "".join(ch for ch in payload if ch >= " ")
            assert shlex.split(quoted) == [expected]


def test_run_cmd_placeholders_cannot_inject_a_second_command(tmp_path, monkeypatch):
    """占位符的值不能变成命令。

    命令里写的是无害的 echo，name 里塞的「分隔符 + 第二条命令」只能当文本。
    导入门禁只让人确认「这份配置含外部命令动作」，不会让人逐字段去读 name，
    所以命令看着无害、name 里藏毒是真实的欺骗面。
    """
    _patch_window_runtime(monkeypatch, tmp_path / "inject.ini")
    window = CommTool("trg-inject")
    try:
        pwned = tmp_path / "pwned"
        out = tmp_path / "out.txt"
        sep = "&" if sys.platform == "win32" else ";"
        # 用 mkdir 而不是带重定向的命令：注入的 `> x` 会和用户自己的
        # `> out.txt` 撞车，两个重定向叠在一条命令上反而看不出注入效果。
        payload = 'zzz %s mkdir "%s"' % (sep, pwned)
        window._trg_run_cmd({"run_cmd_on": True,
                             "run_cmd": 'echo {name}> "%s"' % out},
                            payload, 0, 1)
        for _ in range(250):
            with window._trg_action_lock:
                idle = not window._trg_procs and not window._trg_launching
            if out.exists() and idle:
                break
            time.sleep(0.02)
        assert out.exists(), "无害的那条命令本身要能跑"
        assert not pwned.exists(), "注入的第二条命令被执行了"   # 修复前这里会红
        assert "zzz" in out.read_text(errors="replace")   # 值仍作为文本传了进去
    finally:
        window._trg_stop_procs()
        window.deleteLater()
        _APP.processEvents()


def test_run_cmd_gives_up_a_hung_child(tmp_path, monkeypatch):
    """挂死的命令不能永久占着并发名额。

    _TRG_MAX_ACTIONS 个名额全被卡住就等于这个功能废了；到点按整组收掉。
    """
    _patch_window_runtime(monkeypatch, tmp_path / "hang.ini")
    window = CommTool("trg-hang")
    try:
        monkeypatch.setattr(type(window), "_TRG_CMD_TIMEOUT", 0.05)
        killed = []
        _, proc = _fake_launch(monkeypatch)          # _FakeProc.wait 会超时
        monkeypatch.setattr(
            type(window), "_trg_kill_proc",
            staticmethod(lambda p: (killed.append(p), p.terminate())))

        window._trg_run_cmd({"run_cmd_on": True, "run_cmd": "x"}, "t", 0, 1)
        for _ in range(300):
            if killed:
                break
            time.sleep(0.01)
        assert killed == [proc]                     # 超时后被收掉
        for _ in range(300):
            if window._trg_action_busy == 0:
                break
            time.sleep(0.01)
        assert window._trg_action_busy == 0         # 名额也还回来了
        with window._trg_action_lock:
            assert not window._trg_procs
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_a_child_that_exits_in_time_is_not_killed(tmp_path, monkeypatch):
    """正常退出的命令不能被超时逻辑误杀。"""
    _patch_window_runtime(monkeypatch, tmp_path / "quick.ini")
    window = CommTool("trg-quick")
    try:
        killed = []
        proc = _FakeProc()
        proc.terminate()                            # 开场就已退出：wait 立即返回
        _fake_launch(monkeypatch, proc=proc)
        monkeypatch.setattr(type(window), "_trg_kill_proc",
                            staticmethod(lambda p: killed.append(p)))
        window._trg_run_cmd({"run_cmd_on": True, "run_cmd": "x"}, "t", 0, 1)
        for _ in range(300):
            if window._trg_action_busy == 0:
                break
            time.sleep(0.01)
        assert window._trg_action_busy == 0
        assert killed == []
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_atexit_backs_up_a_missed_close_event(tmp_path, monkeypatch):
    """崩溃 / sys.exit 跑不到 closeEvent，子进程不能就此残留。"""
    import atexit as _atexit
    registered = []
    monkeypatch.setattr(_atexit, "register",
                        lambda fn, *a, **k: (registered.append(fn), fn)[1])
    _patch_window_runtime(monkeypatch, tmp_path / "atexit.ini")
    window = CommTool("trg-atexit")
    try:
        assert window._trg_stop_procs in registered
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_normal_shutdown_unregisters_the_atexit_hook(tmp_path, monkeypatch):
    """正常退出已经收完，兵底要注销：否则每开一个窗口就多拉着一个已销毁的窗口。"""
    import atexit as _atexit
    live = []
    monkeypatch.setattr(_atexit, "register", lambda fn, *a, **k: (live.append(fn), fn)[1])
    monkeypatch.setattr(_atexit, "unregister",
                        lambda fn: live.remove(fn) if fn in live else None)
    _patch_window_runtime(monkeypatch, tmp_path / "atexit2.ini")
    window = CommTool("trg-atexit2")
    try:
        assert window._trg_stop_procs in live
        window._shutdown()
        assert window._trg_stop_procs not in live
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_dropped_actions_show_up_in_the_triggers_dialog(tmp_path, monkeypatch):
    """被并发上限丢掉的动作必须有地方看得到。

    丢弃时命中数照涨，但 webhook / 外部程序根本没跑；不说一声的话
    用户只能对着「命中 500 次」猜为什么告警没发出去。
    """
    from automation import triggers
    from ui.triggers_dialog import TriggersDialog
    _patch_window_runtime(monkeypatch, tmp_path / "dropped.ini")
    window = CommTool("trg-dropped")
    try:
        window._triggers = [triggers.normalize({"name": "r0", "pattern": "X"})]
        dlg = TriggersDialog(window)
        try:
            dlg._refresh_stats()
            assert dlg.lbl_dropped.text() == ""      # 没丢弃 → 不占位

            with window._trg_action_lock:
                window._trg_action_dropped = 3
            dlg._refresh_stats()
            assert "3" in dlg.lbl_dropped.text()

            dlg._reset_stats()                       # 「重置统计」要连它一起清
            assert window._trg_dropped_actions() == 0
            assert dlg.lbl_dropped.text() == ""
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_collect_registers_survives_a_missing_checkbox(tmp_path, monkeypatch):
    """第 0 列缺项时不能 AttributeError。

    旁边每个列都走 text() / combo_value() 并带默认值，只有这一列直接
    .checkState()；缺项按启用算，与 normalize_registers 的默认值一致。
    """
    from ui.device_center_dialog import DeviceCenterDialog
    _patch_window_runtime(monkeypatch, tmp_path / "regs.ini")
    window = CommTool("dev-regs")
    try:
        dlg = DeviceCenterDialog(window)
        try:
            dlg._append_register({"name": "t0", "address": 5})
            dlg.table.takeItem(0, 0)                 # 把勾选框抽掉
            records = dlg._collect_registers()       # 不崩
            assert len(records) == 1
            assert records[0]["enabled"] is True
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


def test_deleting_a_trigger_asks_first(tmp_path, monkeypatch):
    """Deleting a trigger is irreversible; always confirm with trg_* copy."""
    from automation import triggers
    from ui.triggers_dialog import TriggersDialog
    _patch_window_runtime(monkeypatch, tmp_path / "trg.ini")
    window = CommTool("trg-del-confirm")
    try:
        window._triggers = [triggers.normalize({"name": "alarm", "pattern": "ERR"})]
        dlg = TriggersDialog(window)
        try:
            dlg._cur = 0
            seen = {}

            def _confirm(title, body, ok_text=None, danger=True):
                seen["title"] = title
                seen["body"] = body
                seen["ok_text"] = ok_text
                return False

            monkeypatch.setattr(window, "_confirm_dlg", _confirm)
            dlg._delete()
            assert seen["title"] == window._t("trg_del_title")
            assert "alarm" in seen["body"]
            # Must not reuse the Modbus-view copy ("rules are kept").
            assert "view" not in seen["body"].lower()
            assert "默认视图" not in seen["body"] and "default view" not in seen["body"].lower()
            assert len(dlg._items) == 1

            monkeypatch.setattr(window, "_confirm_dlg", lambda *a, **k: True)
            dlg._delete()
            assert dlg._items == []
        finally:
            dlg.close()
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()
