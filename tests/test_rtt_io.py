# -*- coding: utf-8 -*-
"""SEGGER RTT (J-Link) transport: pure helpers + mocked RttConn (no probe)."""
import os
import sys
import threading
import time
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication

from transport import rtt_io
from transport.rtt_io import RttConn
from project import connection_presets
from sessions.session_host import SessionHostMixin
from ui import conn_ui as cu

_APP = QApplication.instance() or QApplication([])


import pytest


@pytest.fixture(autouse=True)
def _clean_rtt_module_caches():
    """每个用例前后清空 rtt_io 的模块级缓存（器件表 / Library 句柄）。

    这些缓存本是进程级单例（见 rtt_io 内注释），但测试会往里塞假驱动 / 假
    Library，跨用例残留会互相污染，也会把假对象拖到解释器退出时才回收。
    Qt 对象与线程则由 conftest.pytest_sessionfinish 做正常收尾。
    """
    from transport import rtt_io
    rtt_io.clear_device_cache()
    rtt_io._LIBRARY_CACHE.clear()
    rtt_io._clear_probe_history()
    yield
    rtt_io.clear_device_cache()
    rtt_io._LIBRARY_CACHE.clear()
    rtt_io._clear_probe_history()


def _wait_until(pred, timeout=4.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _APP.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


class _FakeEnums:
    class JLinkInterfaces:
        SWD = "enum:swd"
        JTAG = "enum:jtag"


class _FakeJLinkException(RuntimeError):
    pass


class _FakeErrors:
    JLinkException = _FakeJLinkException


class _FakePylink:
    enums = _FakeEnums()
    errors = _FakeErrors()


class FakeJLink:
    """Minimal pylink.JLink surface RttConn relies on."""

    def __init__(self, rx=b"", open_error=None, connect_error=None,
                 read_error=None, write_error=None, memory=None):
        self.calls = []
        self.written = []
        self.rx = bytes(rx)
        self.open_error = open_error
        self.connect_error = connect_error
        self.read_error = read_error
        self.write_error = write_error
        self.memory = memory or {}      # base_addr -> bytes

    def open(self, serial_no=None):
        self.calls.append(("open", serial_no) if serial_no else "open")
        if self.open_error:
            raise RuntimeError(self.open_error)

    def reset(self, ms=0, halt=False):
        self.calls.append(("reset", ms, halt))

    def memory_read32(self, addr, num_words):
        self.calls.append(("mem", addr, num_words))
        out = []
        for i in range(num_words):
            a = addr + i * 4
            word = 0
            for base, blob in self.memory.items():
                if base <= a < base + len(blob):
                    raw = blob[a - base:a - base + 4].ljust(4, b"\x00")
                    word = int.from_bytes(raw, "little")
            out.append(word)
        return out

    def set_tif(self, tif):
        self.calls.append(("tif", tif))

    def connect(self, device, speed=0, verbose=False):
        self.calls.append(("connect", device, speed))
        if self.connect_error:
            raise RuntimeError(self.connect_error)

    def rtt_start(self, addr=None):
        self.calls.append(("rtt_start", addr))

    def rtt_read(self, channel, num):
        if self.read_error:
            raise RuntimeError("RTT control block not found")
        out, self.rx = self.rx, b""
        return out

    def rtt_write(self, channel, data):
        if self.write_error:
            raise RuntimeError("rtt write failed")
        data = bytes(data)
        self.written.append((channel, data))
        return len(data)

    def rtt_stop(self):
        self.calls.append("rtt_stop")

    def close(self):
        self.calls.append("close")


class _GateJLink(FakeJLink):
    """connect() blocks until released: deterministic not-ready assertions."""

    def __init__(self):
        super().__init__()
        self._gate = threading.Event()

    def release(self):
        self._gate.set()

    def connect(self, device, speed=0, verbose=False):
        self._gate.wait(3.0)
        super().connect(device, speed=speed, verbose=verbose)


def _make_conn(jlink, **kw):
    class _TestableRtt(RttConn):
        jlink_factory = staticmethod(lambda: jlink)
        pylink_module = _FakePylink
    kw.setdefault("device", "nRF52840_xxAA")
    return _TestableRtt(**kw)


# ----- pure helpers -----

def test_parse_address():
    assert rtt_io.parse_address(None) == 0
    assert rtt_io.parse_address("") == 0
    assert rtt_io.parse_address("  ") == 0
    assert rtt_io.parse_address("auto") == 0
    assert rtt_io.parse_address("AUTO") == 0
    assert rtt_io.parse_address("0x20000124") == 0x20000124
    assert rtt_io.parse_address("0X10") == 16
    assert rtt_io.parse_address("128") == 128
    assert rtt_io.parse_address("0xzz") is None
    assert rtt_io.parse_address("-4") is None


def test_parse_speed_and_clamp():
    assert rtt_io.parse_speed(None) == 4000
    assert rtt_io.parse_speed("") == 4000
    assert rtt_io.parse_speed(" 4000 ") == 4000
    assert rtt_io.parse_speed("1000") == 1000
    assert rtt_io.parse_speed("abc") is None
    assert rtt_io.parse_speed("0") is None
    assert rtt_io.parse_speed(str(rtt_io.MAX_SPEED_KHZ + 1)) is None
    assert rtt_io.clamp_speed("9") == 9
    assert rtt_io.clamp_speed(0) == rtt_io.MIN_SPEED_KHZ
    assert rtt_io.clamp_speed(None) == 4000
    assert rtt_io.clamp_speed(10 ** 9) == rtt_io.MAX_SPEED_KHZ


def test_channel_and_interface():
    assert rtt_io.normalize_channel(0) == 0
    assert rtt_io.normalize_channel("15") == 15
    assert rtt_io.normalize_channel("") == 0
    assert rtt_io.normalize_channel(16) is None
    assert rtt_io.normalize_channel(-1) is None
    assert rtt_io.normalize_channel("x") is None
    assert rtt_io.normalize_interface("swd") == "SWD"
    assert rtt_io.normalize_interface("JTAG") == "JTAG"
    assert rtt_io.normalize_interface("bogus") == "SWD"
    assert rtt_io.normalize_interface(None) == "SWD"


def test_split_write_and_resolve_interface():
    assert rtt_io.split_write(b"", 4) == []
    assert rtt_io.split_write(b"abcdef", 4) == [b"abcd", b"ef"]
    assert rtt_io.split_write(None) == []
    assert rtt_io.resolve_interface(_FakePylink, "jtag") == "enum:jtag"
    # 非法名先规范化为 SWD，再映射到 pylink 枚举
    assert rtt_io.resolve_interface(_FakePylink, "bad") == "enum:swd"

    class _NoEnums:
        pass
    assert rtt_io.resolve_interface(_NoEnums, "SWD") == "SWD"


def test_classify_error():
    assert rtt_io.classify_error(
        "Unable to load library: JLinkARM.dll") == rtt_io.ERR_NO_JLINK
    # pylink-square 1.7 无驱动时的真实报错（TypeError 文本）
    assert rtt_io.classify_error(
        "Expected to be given a valid DLL.") == rtt_io.ERR_NO_JLINK
    assert rtt_io.classify_error("No J-Link device found") == rtt_io.ERR_NO_PROBE
    assert rtt_io.classify_error("J-Link is busy") == rtt_io.ERR_NO_PROBE
    assert rtt_io.classify_error(
        "Unknown device name (foo)") == rtt_io.ERR_BAD_DEVICE
    assert rtt_io.classify_error(
        "RTT Control Block not found") == rtt_io.ERR_NO_RTT
    assert rtt_io.classify_error("rtt:no-rtt") == "rtt:no-rtt"
    assert rtt_io.classify_error("some other failure") == ""
    assert rtt_io.classify_error(None) == ""


# ----- open-time validation (Qt-free) -----

def _validate(fields):
    return connection_presets.validate_open(
        "RTT", fields, is_valid_ip=lambda *_: True,
        is_local_ipv4=lambda *_: True, is_multicast_ipv4=lambda *_: True)


def test_validate_open_rtt_ok():
    out = _validate({"device": " STM32F103C8 ", "speed": "7200",
                     "interface": "jtag", "address": "0x20000000", "channel": "2"})
    assert out["ok"] is True
    assert out == {"ok": True, "device": "STM32F103C8", "speed": 7200,
                   "interface": "JTAG", "address": 0x20000000, "search_size": 0,
                   "channel": 2, "probe": "", "reset": False}
    # 「起点+范围」写法：地址栏同时给出搜索区间
    out = _validate({"device": "X", "address": "0x20000000+0x1000",
                     "channel": "0", "probe": " 12345678 ", "reset": True})
    assert out["address"] == 0x20000000 and out["search_size"] == 0x1000
    assert out["probe"] == "12345678" and out["reset"] is True


def test_validate_open_rtt_errors():
    assert _validate({}).get("toast") == "rtt_err_no_device"
    assert _validate({"device": "X", "speed": "q"}).get("toast") == "rtt_err_bad_speed"
    assert _validate({"device": "X", "address": "-1"}).get("toast") == "rtt_err_bad_address"
    assert _validate({"device": "X", "channel": "99"}).get("toast") == "rtt_err_bad_channel"


def test_open_fields_from_ui_rtt():
    ui = {"rtt_device": "nRF52840_xxAA", "rtt_speed": "4000",
          "rtt_interface": "SWD", "rtt_address": "", "rtt_channel": 0}
    fields = connection_presets.open_fields_from_ui("RTT", ui)
    out = _validate(fields)
    assert out["ok"] and out["device"] == "nRF52840_xxAA" and out["address"] == 0
    # reconnect tuple -> fields -> validate round trip
    cfg = ("RTT", "nRF52840_xxAA", 4000, "SWD", 0x20000000, 1)
    proto, fields = connection_presets.open_fields_from_reconnect(cfg)
    out = _validate(fields)
    assert proto == "RTT" and out["ok"] and out["address"] == 0x20000000
    assert out["channel"] == 1
    # 新快照（9 元组）：搜索范围 / 探针 / 复位都要原样还原，重连才连回同一路
    cfg = ("RTT", "nRF52840_xxAA", 4000, "SWD", 0x20000000, 1, 0x1000, "9911", True)
    proto, fields = connection_presets.open_fields_from_reconnect(cfg)
    out = _validate(fields)
    assert out["ok"] and out["address"] == 0x20000000
    assert out["search_size"] == 0x1000
    assert out["probe"] == "9911" and out["reset"] is True
    assert connection_presets.rtt_signature(
        proto, out["device"], out["speed"], out["interface"],
        fields["address"], out["channel"], out["probe"], out["reset"]) == cfg


def test_rtt_signature_and_presets():
    sig = connection_presets.rtt_signature(
        "RTT", " X ", "4000", "swd", "0x10", "3")
    assert sig == ("RTT", "X", 4000, "SWD", 16, 3, 0, "", False)
    # 搜索范围 / 探针 / 复位都进签名：改了必须当成另一套连接配置
    sig2 = connection_presets.rtt_signature(
        "RTT", "X", "4000", "swd", "0x10+0x20", "3", probe="99", reset=True)
    assert sig2 == ("RTT", "X", 4000, "SWD", 16, 3, 0x20, "99", True)
    assert sig != sig2
    preset = connection_presets.make_preset("p", {
        "net_proto": "RTT", "rtt_device": "X", "rtt_speed": "4000",
        "rtt_interface": "SWD", "rtt_address": "0x10", "rtt_channel": "0"})
    assert preset["rtt_device"] == "X"
    assert "X" in connection_presets.summary(preset)
    assert connection_presets.match(preset, "x")
    body = connection_presets.normalize(
        {"net_proto": "RTT", "rtt_device": "Y"})
    assert body["rtt_interface"] == "SWD" and body["rtt_channel"] == "0"


def test_resource_keys_rtt():
    key = SessionHostMixin._session_resource_key_from_open
    assert key("RTT", {"device": "NRF52"}) == ("rtt", "nrf52")
    assert key("RTT", {"device": ""}) is None
    assert key("RTT", {"rtt_device": "X"}) == ("rtt", "x")


# ----- conn_ui visibility -----

def test_conn_ui_rtt_rows_and_btn():
    assert cu.PROTO_RTT in cu.CONN_TYPES
    assert cu.PROTO_RTT in cu.visible_conn_types("win32")
    assert cu.PROTO_RTT in cu.visible_conn_types("darwin")
    idle = cu.field_visibility(cu.PROTO_RTT, False)
    assert idle["rtt_rows"] is True
    assert idle["ble_rows"] is False and idle["serial_rows"] is False
    assert idle["open_btn_key"] == "btn_connect"
    live = cu.field_visibility(cu.PROTO_RTT, True)
    assert live["open_btn_key"] == "btn_disconnect"
    assert cu.open_btn_key(cu.PROTO_RTT, False) == "btn_connect"
    assert cu.open_btn_key(cu.PROTO_RTT, True) == "btn_disconnect"


def test_log_naming_rtt():
    from record import log_naming
    assert log_naming.conn_token(
        "RTT", ("RTT", "nRF52840_xxAA", 4000, "SWD", 0, 0)) == "nRF52840_xxAA"
    assert log_naming.conn_token("RTT", ("RTT",)) == "RTT"


# ----- RttConn lifecycle with fake J-Link -----

def test_conn_open_rx_tx_close():
    jl = FakeJLink(rx=b"boot log")
    conn = _make_conn(jl, speed_khz="8000", interface="SWD",
                      rtt_address=0x20000000, channel=0)
    states, errs, rx = [], [], []
    conn.state_changed.connect(lambda up: states.append(up))
    conn.error_occurred.connect(errs.append)
    conn.data_received.connect(rx.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: states == [True]), states
        assert conn.is_open is True
        assert _wait_until(lambda: rx and bytes(rx[0]) == b"boot log")
        assert conn.send(b"AT\r\n") == 4
        assert _wait_until(lambda: jl.written and jl.written[0][1] == b"AT\r\n")
        assert jl.written[0][0] == 0
        assert ("connect", "nRF52840_xxAA", 8000) in jl.calls
        assert ("rtt_start", 0x20000000) in jl.calls
        assert ("tif", "enum:swd") in jl.calls
        assert errs == []
    finally:
        conn.close()
    assert states[-1] is False
    assert conn.is_open is False
    assert "rtt_stop" in jl.calls and "close" in jl.calls
    assert conn.send(b"x") == 0   # 关闭后发送被拒绝


def test_auto_probe_retries_last_successful_then_falls_back():
    first = FakeJLink()
    first.serial_number = 111
    conn = _make_conn(first)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
    finally:
        conn.close()
    assert first.calls[0] == "open"
    assert rtt_io._last_successful_probe() == "111"

    class _FallbackJLink(FakeJLink):
        def __init__(self):
            super().__init__()
            self.serial_number = 222

        def open(self, serial_no=None):
            self.calls.append(("open", serial_no) if serial_no else "open")
            if serial_no == "111":
                raise _FakeJLinkException("cached probe unavailable")

    second = _FallbackJLink()
    conn = _make_conn(second)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
    finally:
        conn.close()
    assert second.calls[:2] == [("open", "111"), "open"]
    assert rtt_io._last_successful_probe() == "222"


def test_explicit_probe_never_falls_back_to_another_probe():
    class _RejectSelectedJLink(FakeJLink):
        def open(self, serial_no=None):
            self.calls.append(("open", serial_no) if serial_no else "open")
            raise RuntimeError("selected probe unavailable")

    rtt_io._LAST_SUCCESSFUL_PROBE = "111"
    jl = _RejectSelectedJLink()
    conn = _make_conn(jl, serial_no="999")
    errs = []
    conn.error_occurred.connect(errs.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: errs)
    finally:
        conn.close()
    assert jl.calls[0] == ("open", "999")
    assert "open" not in jl.calls       # 失败后没有退回自动探针


def test_failed_rtt_start_does_not_replace_last_successful_probe():
    class _StartFailJLink(FakeJLink):
        serial_number = 222

        def rtt_start(self, addr=None):
            self.calls.append(("rtt_start", addr))
            raise RuntimeError("RTT start failed")

    rtt_io._LAST_SUCCESSFUL_PROBE = "111"
    jl = _StartFailJLink()
    conn = _make_conn(jl)
    errs = []
    conn.error_occurred.connect(errs.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: errs)
    finally:
        conn.close()
    assert jl.calls[0] == ("open", "111")
    assert rtt_io._last_successful_probe() == "111"


def test_conn_send_rejected_before_ready():
    jl = _GateJLink()
    conn = _make_conn(jl)
    try:
        assert conn.open() is True
        assert conn.send(b"early") == 0   # 未就绪不入队
        jl.release()
        assert _wait_until(lambda: conn.is_open)
        assert conn.send(b"now") == 3
        assert _wait_until(lambda: jl.written and jl.written[0][1] == b"now")
    finally:
        conn.close()
    assert jl.written[0][1] == b"now"


def test_conn_connect_error_tokens(monkeypatch):
    cases = (
        (FakeJLink(connect_error="Unknown device name (foo)"),
         rtt_io.ERR_BAD_DEVICE),
        (FakeJLink(connect_error="No J-Link device found"),
         rtt_io.ERR_NO_PROBE),
        (FakeJLink(open_error="Unable to load library jlinkarm"),
         rtt_io.ERR_NO_JLINK),
    )
    for jl, token in cases:
        conn = _make_conn(jl)
        errs, states = [], []
        conn.error_occurred.connect(errs.append)
        conn.state_changed.connect(states.append)
        try:
            assert conn.open() is True
            assert _wait_until(lambda: errs), token
            assert errs == [token], errs
            assert states == []
            assert conn.is_open is False
        finally:
            conn.close()

    def _boom():
        raise RuntimeError(rtt_io.ERR_NO_PYLINK)
    monkeypatch.setattr(rtt_io, "_import_pylink", _boom)

    class _NoPylink(RttConn):
        jlink_factory = staticmethod(lambda: FakeJLink())
        pylink_module = None
    conn = _NoPylink("X")
    errs = []
    conn.error_occurred.connect(errs.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: errs)
        assert errs == [rtt_io.ERR_NO_PYLINK]
    finally:
        conn.close()


def test_conn_empty_device_rejected():
    conn = RttConn("  ")
    errs = []
    conn.error_occurred.connect(errs.append)
    assert conn.open() is False
    assert errs == [rtt_io.ERR_NO_DEVICE]


def test_conn_control_block_wait_is_not_fatal(monkeypatch):
    """控制块还没出现 = 等待状态：链路照样算通，只发一次非致命提示。

    参考实现（J-Link RTT Viewer / rtt_t2）就是 rtt_start 成功即连上，
    控制块可能要等固件跑到 SEGGER_RTT 初始化才出现，大 RAM 的片子上
    DLL 自动搜索也远不止几秒 —— 拿它判失败会直接连不上。
    """
    monkeypatch.setattr(rtt_io, "RTT_HINT_S", 0.2)
    monkeypatch.setattr(rtt_io, "POLL_IDLE_S", 0.01)
    jl = FakeJLink(read_error=True)   # rtt_read 一直抛「控制块没找到」
    conn = _make_conn(jl)
    errs, states, notices = [], [], []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    conn.notice_occurred.connect(notices.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: states == [True], timeout=3.0)
        assert conn.is_open is True
        assert conn.control_block_seen is False
        assert _wait_until(lambda: notices, timeout=3.0)
        assert notices == [rtt_io.NOTICE_WAIT_CB]
        _wait_until(lambda: len(notices) > 1, timeout=0.6)
        assert notices == [rtt_io.NOTICE_WAIT_CB]   # 只提示一次，不刷屏
        assert errs == []                           # 全程不算错误
    finally:
        conn.close()
    assert states == [True, False]


def test_conn_empty_read_still_marks_control_block_found():
    """成功空读代表控制块已找到，不能等到首个数据字节才更新状态。"""
    conn = _make_conn(FakeJLink())
    found = []
    conn.control_block_found.connect(lambda: found.append(True))
    try:
        assert conn.open() is True
        assert _wait_until(lambda: found)
        assert conn.control_block_seen is True
        assert found == [True]
    finally:
        conn.close()


def test_conn_transient_read_error_tolerated(monkeypatch):
    """运行中偶发一次读失败只吞掉继续读，不能当掉线。"""
    monkeypatch.setattr(rtt_io, "POLL_IDLE_S", 0.01)
    jl = FakeJLink(rx=b"first")
    conn = _make_conn(jl)
    states, errs, rx = [], [], []
    conn.state_changed.connect(states.append)
    conn.error_occurred.connect(errs.append)
    conn.data_received.connect(rx.append)
    calls = {"n": 0}
    real_read = jl.rtt_read

    def _flaky(channel, num):
        calls["n"] += 1
        if calls["n"] in (3, 4, 5):
            raise RuntimeError("Command not supported by this firmware")
        if calls["n"] == 8:
            jl.rx = b"after glitch"
        return real_read(channel, num)

    try:
        assert conn.open() is True
        assert _wait_until(lambda: states == [True])
        jl.rtt_read = _flaky
        assert _wait_until(
            lambda: any(bytes(b) == b"after glitch" for b in rx), timeout=3.0)
        assert errs == []          # 瞬时错误没有变成掉线
        assert states == [True]
    finally:
        conn.close()


def test_conn_persistent_read_failure_drops(monkeypatch):
    """未知错误持续超过宽限期才判掉线（宽限内一直重试）。"""
    monkeypatch.setattr(rtt_io, "POLL_IDLE_S", 0.01)
    monkeypatch.setattr(rtt_io, "READ_FAIL_GRACE_S", 0.3)
    jl = FakeJLink(rx=b"hi")
    conn = _make_conn(jl)
    states, errs = [], []
    conn.state_changed.connect(states.append)
    conn.error_occurred.connect(errs.append)

    def _dead(channel, num):
        raise RuntimeError("Command not supported by this firmware")

    try:
        assert conn.open() is True
        assert _wait_until(lambda: states == [True])
        jl.rtt_read = _dead
        assert _wait_until(lambda: errs, timeout=3.0)
        assert errs == [rtt_io.ERR_GONE]
    finally:
        conn.close()


def test_conn_runtime_drop_emits_gone(monkeypatch):
    monkeypatch.setattr(rtt_io, "POLL_IDLE_S", 0.01)
    jl = FakeJLink(rx=b"first")
    conn = _make_conn(jl)
    states, errs, rx = [], [], []
    conn.state_changed.connect(lambda up: states.append(up))
    conn.error_occurred.connect(errs.append)
    conn.data_received.connect(rx.append)

    def _die(channel, num):
        raise RuntimeError("usb communication error")
    try:
        assert conn.open() is True
        assert _wait_until(lambda: states == [True])
        jl.rtt_read = _die   # 会话中途 DLL 故障
        assert _wait_until(lambda: errs, timeout=3.0)
        assert errs == [rtt_io.ERR_GONE]
        assert _wait_until(lambda: states == [True, False]), states
    finally:
        conn.close()


def test_conn_open_timeout_watchdog(monkeypatch):
    """connect() 卡死（调试器被占用等）→ 看门狗报 rtt:timeout，不再静默。"""
    monkeypatch.setattr(rtt_io, "CONNECT_TIMEOUT_S", 0.3)
    jl = _GateJLink()   # connect() 阻塞直到 release
    conn = _make_conn(jl)
    errs, states = [], []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: errs, timeout=3.0)
        assert errs == [rtt_io.ERR_TIMEOUT]
        assert conn.is_open is False
    finally:
        conn.close()
    # 看门狗伴随一个 state(False)；应用层因 error 先清掉 conn 不会看到它
    assert _wait_until(lambda: states == [False], timeout=2.0), states
    assert conn.send(b"x") == 0   # 超时后发送被拒绝
    jl.release()                  # 卡住的调用返回后 worker 静默退出
    time.sleep(0.2)
    _APP.processEvents()
    assert errs == [rtt_io.ERR_TIMEOUT]   # 没有二次报错


def test_conn_watchdog_disarmed_on_success(monkeypatch):
    """正常连上后看门狗必须拆除：多等一个周期也不得误报超时。"""
    monkeypatch.setattr(rtt_io, "CONNECT_TIMEOUT_S", 0.4)
    jl = FakeJLink(rx=b"ok")
    conn = _make_conn(jl)
    errs, states = [], []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: states == [True])
        time.sleep(0.7)   # 超过看门狗周期
        _APP.processEvents()
        assert errs == []
        assert states == [True]
        assert conn.is_open is True
    finally:
        conn.close()


def test_conn_write_chunking():
    jl = FakeJLink()
    conn = _make_conn(jl)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        payload = bytes(range(256)) * 4   # 1024 字节 -> WRITE_CHUNK 512 两块
        assert conn.send(payload) == len(payload)
        assert _wait_until(lambda: len(jl.written) >= 2)
        assert jl.written[0][1] == payload[:rtt_io.WRITE_CHUNK]
        assert b"".join(w for _ch, w in jl.written)[:len(payload)] == payload
    finally:
        conn.close()


def test_conn_write_failure_drops_link_and_queue():
    """下行 DLL 异常不能伪装成已发送，也不能留下永远排不掉的队列。"""
    jl = FakeJLink(write_error=True)
    conn = _make_conn(jl)
    errs, states = [], []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert conn.send(b"abc") == 3
        assert _wait_until(lambda: errs)
        assert errs == [rtt_io.ERR_GONE]
        assert _wait_until(lambda: states and states[-1] is False)
        assert states[-1] is False
        assert conn.is_open is False
        assert conn.queued_bytes == 0
    finally:
        conn.close()


# ----- 地址栏「起点+范围」与控制块搜索 -----

def test_parse_address_spec_forms():
    assert rtt_io.parse_address_spec(None) == (0, 0)
    assert rtt_io.parse_address_spec("") == (0, 0)
    assert rtt_io.parse_address_spec("auto") == (0, 0)
    assert rtt_io.parse_address_spec("0x20000000") == (0x20000000, 0)
    assert rtt_io.parse_address_spec("0x20000000+0x1000") == (0x20000000, 0x1000)
    assert rtt_io.parse_address_spec("0x20000000 4096") == (0x20000000, 4096)
    assert rtt_io.parse_address_spec("0x20000000..0x20001000") == (0x20000000, 0x1000)
    # 范围上限收敛，避免一次扫穿整片地址空间
    big = rtt_io.parse_address_spec("0x20000000+0xFFFFFFF")
    assert big == (0x20000000, rtt_io.MAX_SEARCH_BYTES)
    assert rtt_io.parse_address_spec("0x20001000..0x20000000") is None
    assert rtt_io.parse_address_spec("0x20000000+0") is None
    assert rtt_io.parse_address_spec("0x20000002+0x1000") is None
    assert rtt_io.parse_address_spec("0x20000000+12") is None
    assert rtt_io.parse_address_spec("zz+1") is None
    # 旧接口仍只取起点
    assert rtt_io.parse_address("0x20000000+0x1000") == 0x20000000
    assert rtt_io.parse_search_size("0x20000000+0x1000") == 0x1000
    assert rtt_io.parse_search_size("0x20000000") == 0


def test_search_control_block():
    blob = b"\x00" * 100 + b"SEGGER RTT\x00" + b"\x11" * 100
    jl = FakeJLink(memory={0x20000000: blob})
    hit = rtt_io.search_control_block(jl, 0x20000000, len(blob))
    assert hit == 0x20000000 + 100
    # magic 跨块也要命中（块大小临时调小，让 magic 骑在边界上）
    small = 16
    orig = rtt_io.SEARCH_CHUNK_BYTES
    try:
        rtt_io.SEARCH_CHUNK_BYTES = small
        jl2 = FakeJLink(memory={0x20000000: b"\x00" * 12 + b"SEGGER RTT"})
        assert rtt_io.search_control_block(jl2, 0x20000000, 64) == 0x2000000C
    finally:
        rtt_io.SEARCH_CHUNK_BYTES = orig
    # 没有 magic / 读不到内存都返回 None，由调用方退回 DLL 自动搜索
    assert rtt_io.search_control_block(
        FakeJLink(memory={0x20000000: b"\x00" * 64}), 0x20000000, 64) is None
    # memory_read32 按 4 字节读；范围非 4 的倍数时不能误命中范围外的尾字节
    outside = FakeJLink(memory={
        0x20000000: b"\x00" * 18 + b"SEGGER RTT"})
    assert rtt_io.search_control_block(outside, 0x20000000, 18) is None
    assert rtt_io.search_control_block(jl, 0x20000000, 0) is None


class _TargetJLink(FakeJLink):
    """同时暴露探针/目标在线检查（真 pylink 的两者含义不同）。"""

    def __init__(self, online=True, **kw):
        super().__init__(**kw)
        self.online = online
        self.swo_flushed = 0

    def connected(self):
        self.calls.append(("connected", True))
        return True

    def target_connected(self):
        self.calls.append(("target_connected", self.online))
        return self.online

    def swo_flush(self):
        self.swo_flushed += 1


def test_conn_confirms_target_and_flushes_swo():
    """rtt_start 前确认目标而非仅确认探针，并刷新 SWO。"""
    jl = _TargetJLink(online=True, rx=b"x")
    conn = _make_conn(jl)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert ("target_connected", True) in jl.calls
        assert not any(isinstance(c, tuple) and c[0] == "connected"
                       for c in jl.calls)
        assert jl.swo_flushed == 1
    finally:
        conn.close()


def test_conn_target_offline_reports_no_target():
    """connect() 返回了但目标其实掉线：早报 rtt:no-target，不进 rtt_start。"""
    jl = _TargetJLink(online=False)
    conn = _make_conn(jl)
    errs, states = [], []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: errs, timeout=3.0)
        assert errs == [rtt_io.ERR_NO_TARGET]
        assert states == []
        assert not any(isinstance(c, tuple) and c[0] == "rtt_start"
                       for c in jl.calls)
    finally:
        conn.close()


def test_catalog_and_connection_serialize_dll_access(monkeypatch):
    """器件枚举与 RTT 收发不可同时进入进程级 JLinkARM DLL。"""
    started = threading.Event()
    release = threading.Event()
    ready = []

    def _devices():
        started.set()
        release.wait(2.0)
        return [{"name": "Part"}]

    monkeypatch.setattr(rtt_io, "list_devices", _devices)
    monkeypatch.setattr(rtt_io, "list_probes", lambda: [])
    monkeypatch.setattr(rtt_io, "find_jlink_dll", lambda: "fake.dll")
    catalog = rtt_io.RttCatalog()
    catalog.ready.connect(lambda devices, probes: ready.append((devices, probes)))
    catalog.start()
    assert started.wait(1.0)

    jl = FakeJLink()
    conn = _make_conn(jl)
    try:
        assert conn.open() is True
        time.sleep(0.05)
        assert jl.calls == []
        release.set()
        assert catalog.wait(2000)
        assert _wait_until(lambda: ready)
        assert _wait_until(lambda: conn.is_open)
    finally:
        release.set()
        conn.close()
        catalog.wait(2000)


def test_confirm_target_and_swo_skipped_when_unsupported():
    """老 pylink / 注入对象没有 connected()/swo_flush() 时，不能因此连不上。"""
    jl = FakeJLink(rx=b"x")   # 两个 API 都没有
    assert not hasattr(jl, "connected")
    conn = _make_conn(jl)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)   # 照常连上
    finally:
        conn.close()


def test_conn_searches_block_then_starts():
    """填了搜索范围：先自己扫出控制块地址，再拿精确地址启 RTT。"""
    blob = b"\x00" * 40 + b"SEGGER RTT" + b"\x00" * 40
    jl = FakeJLink(rx=b"x", memory={0x20000000: blob})
    conn = _make_conn(jl, rtt_address=0x20000000, search_size=len(blob))
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert ("rtt_start", 0x20000028) in jl.calls
    finally:
        conn.close()


def test_conn_search_miss_falls_back_to_auto():
    """搜不到不算失败：退回 DLL 自动搜索（rtt_start(None)）。"""
    jl = FakeJLink(rx=b"x", memory={0x20000000: b"\x00" * 64})
    conn = _make_conn(jl, rtt_address=0x20000000, search_size=64)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert ("rtt_start", None) in jl.calls
    finally:
        conn.close()


# ----- 探针序列号 / 连接时复位 -----

def test_conn_probe_serial_and_reset():
    jl = FakeJLink(rx=b"x")
    conn = _make_conn(jl, serial_no=" 600100123 ", reset_on_open=True)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert ("open", "600100123") in jl.calls
        assert ("reset", rtt_io.RESET_MS, False) in jl.calls
    finally:
        conn.close()

    jl2 = FakeJLink(rx=b"x")
    conn2 = _make_conn(jl2)          # 默认：自动选调试器、不复位
    try:
        assert conn2.open() is True
        assert _wait_until(lambda: conn2.is_open)
        assert "open" in jl2.calls
        assert not any(isinstance(c, tuple) and c[0] == "reset" for c in jl2.calls)
    finally:
        conn2.close()


def test_normalize_probe():
    assert rtt_io.normalize_probe(None) == ""
    assert rtt_io.normalize_probe("  ") == ""
    assert rtt_io.normalize_probe("auto") == ""
    assert rtt_io.normalize_probe(" 12345678 ") == "12345678"


# ----- 错误归类：pylink 真实文案 -----

def test_classify_error_pylink_messages():
    cases = {
        # errors.JLinkException 把 DLL 错误码翻成这些固定英文句
        "Unsupported device selected.": rtt_io.ERR_BAD_DEVICE,
        "User did not specify core to connect to.": rtt_io.ERR_BAD_DEVICE,
        "No connection to emulator.": rtt_io.ERR_NO_PROBE,
        "Emulator connection error.": rtt_io.ERR_NO_PROBE,
        "DLL has not been opened.  Did you call '.connect()'?": rtt_io.ERR_NO_JLINK,
        "Target system has no power.": rtt_io.ERR_NO_TARGET,
        "Could not find supported CPU.": rtt_io.ERR_NO_TARGET,
        "Target interface error.": rtt_io.ERR_NO_TARGET,
        "Target CPU is in low power mode.": rtt_io.ERR_NO_TARGET,
        "Given speed exceeds max speed of 50000.": rtt_io.ERR_BAD_SPEED,
        "Given speed is too slow.  Minimum is 5.": rtt_io.ERR_BAD_SPEED,
        "The RTT Control Block has not yet been found (wait?)": rtt_io.ERR_NO_RTT,
    }
    for text, token in cases.items():
        assert rtt_io.classify_error(text) == token, text
    # 每个 token 都要有对应文案，否则用户看到的是英文原文
    from ui import i18n
    for token in cases.values():
        key = rtt_io.ERROR_I18N[token]
        for lang in i18n.TR:
            assert key in i18n.TR[lang], (lang, key)


def test_speed_bounds_match_pylink():
    # pylink 的 JLink.MIN_JTAG_SPEED = 5 / MAX_JTAG_SPEED = 50000
    assert rtt_io.MIN_SPEED_KHZ == 5 and rtt_io.MAX_SPEED_KHZ == 50000
    assert rtt_io.parse_speed("4") is None
    assert rtt_io.parse_speed("5") == 5
    assert rtt_io.clamp_speed(1) == 5


# ----- 器件表 / 调试器枚举 -----

def test_list_supported_devices_from_dll(monkeypatch):
    class _Dev:
        def __init__(self, name):
            self.name = name

    class _FakeJL:
        def num_supported_devices(self):
            return 4

        def supported_device(self, idx):
            return _Dev(["A", "B", "A", ""][idx])

    monkeypatch.setattr(rtt_io, "_DEVICE_CACHE", None)
    monkeypatch.setattr(rtt_io, "_new_jlink", lambda mod=None: _FakeJL())
    assert rtt_io.list_supported_devices(refresh=True) == ["A", "B"]

    # 没装驱动（构造就抛）时退回内置候选，界面照样能用
    def _boom(mod=None):
        raise TypeError("Expected to be given a valid DLL.")
    monkeypatch.setattr(rtt_io, "_new_jlink", _boom)
    assert rtt_io.list_supported_devices(refresh=True) == list(rtt_io.COMMON_DEVICES)
    monkeypatch.setattr(rtt_io, "_DEVICE_CACHE", None)


def test_list_probes(monkeypatch):
    class _Info:
        SerialNumber = 600100123

    class _FakeJL:
        def connected_emulators(self):
            return [_Info()]

    monkeypatch.setattr(rtt_io, "_new_jlink", lambda mod=None: _FakeJL())
    assert rtt_io.list_probes() == ["600100123"]

    def _boom(mod=None):
        raise TypeError("Expected to be given a valid DLL.")
    monkeypatch.setattr(rtt_io, "_new_jlink", _boom)
    assert rtt_io.list_probes() == []


# ----- 上一个连接没退干净时不再并发进 DLL -----

def test_open_rejected_while_previous_worker_stuck(monkeypatch):
    monkeypatch.setattr(rtt_io, "JOIN_TIMEOUT_S", 0.1)
    jl = _GateJLink()          # connect() 卡住，close() join 不回来
    conn = _make_conn(jl)
    errs = []
    conn.error_occurred.connect(errs.append)
    try:
        assert conn.open() is True
        conn.close()           # worker 仍卡在 DLL 调用里
        assert conn.open() is False
        assert _wait_until(lambda: errs)
        assert errs[-1] == rtt_io.ERR_BUSY
    finally:
        jl.release()
        time.sleep(0.2)
        conn.close()


def test_new_conn_rejected_while_previous_worker_stuck(monkeypatch):
    """主窗口会重建 RttConn；互斥必须跨实例，而不只是单实例保护。"""
    monkeypatch.setattr(rtt_io, "JOIN_TIMEOUT_S", 0.1)
    jl = _GateJLink()
    conn1 = _make_conn(jl)
    conn2 = _make_conn(FakeJLink())
    errs = []
    conn2.error_occurred.connect(errs.append)
    try:
        assert conn1.open() is True
        conn1.close()
        assert conn2.open() is False
        assert _wait_until(lambda: errs)
        assert errs == [rtt_io.ERR_BUSY]
    finally:
        jl.release()
        time.sleep(0.2)
        conn1.close()
        conn2.close()


# ----- J-Link 驱动发现（Windows DLL / macOS dylib / Linux so） -----

@pytest.fixture(params=[
    ("win32", "JLink_x64.dll"),
    ("darwin", "libjlinkarm.dylib"),
    ("linux", "libjlinkarm.so"),
], ids=["windows", "macos", "linux"])
def driver_name(request, monkeypatch):
    platform, name = request.param
    # 只替换被测模块的 sys 引用，避免影响 pytest / pathlib / Qt 的宿主平台。
    monkeypatch.setattr(rtt_io, "sys", types.SimpleNamespace(platform=platform))
    _isolate_discovery(monkeypatch)
    return name


def _fake_install(tmp_path, name="JLink_V926", dll="JLink_x64.dll"):
    d = tmp_path / "Program Files" / "SEGGER" / name
    d.mkdir(parents=True)
    (d / dll).write_bytes(b"not a real dll")
    return str(d)


def _isolate_discovery(monkeypatch):
    """屏蔽本机真实安装，让断言只反映被测的输入。"""
    monkeypatch.setattr(rtt_io, "_registry_jlink_dirs", lambda: [])
    monkeypatch.setattr(rtt_io, "_scan_jlink_dirs", lambda: [])
    monkeypatch.setattr(rtt_io, "_dll_hint", "")
    for var in rtt_io.JLINK_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_find_jlink_dll_from_hint_dir(tmp_path, driver_name):
    install = _fake_install(tmp_path, dll=driver_name)
    assert rtt_io.find_jlink_dll() is None          # 隔离后确实找不到
    found = rtt_io.find_jlink_dll(hint=install)
    assert found == os.path.join(install, driver_name)
    # 直接给 DLL 文件路径也认
    assert rtt_io.find_jlink_dll(hint=found) == found


def test_find_jlink_dll_from_env(tmp_path, monkeypatch, driver_name):
    install = _fake_install(tmp_path, dll=driver_name)
    monkeypatch.setenv(rtt_io.JLINK_ENV_VARS[0], install)
    assert rtt_io.find_jlink_dll() == os.path.join(install, driver_name)
    monkeypatch.delenv(rtt_io.JLINK_ENV_VARS[0])
    assert rtt_io.find_jlink_dll() is None


def test_find_jlink_dll_from_registry(tmp_path, monkeypatch):
    _isolate_discovery(monkeypatch)
    monkeypatch.setattr(rtt_io, "sys", types.SimpleNamespace(platform="win32"))
    install = _fake_install(tmp_path)
    # 注册表（SEGGER 装在哪个盘都会写）。
    monkeypatch.setattr(rtt_io, "_registry_jlink_dirs", lambda: [install])
    assert rtt_io.find_jlink_dll() == os.path.join(install, "JLink_x64.dll")


def test_scan_covers_green_copy_roots(tmp_path):
    r"""绿色版 / 手动解压没有注册表项，扫描要覆盖盘根的 SEGGER 与 Tools\SEGGER。"""
    for sub in (("SEGGER", "JLink_V800"),
                ("Tools", "SEGGER", "JLink_V810"),
                ("Program Files", "SEGGER", "JLink_V926")):
        d = tmp_path.joinpath(*sub)
        d.mkdir(parents=True)
        (d / "JLink_x64.dll").write_bytes(b"x")
    names = {os.path.basename(d) for d in rtt_io._scan_roots_under(str(tmp_path))}
    assert names == {"JLink_V800", "JLink_V810", "JLink_V926"}
    # 空盘不会炸
    assert rtt_io._scan_roots_under(str(tmp_path / "nope")) == []


def test_find_jlink_dll_prefers_newest_version(tmp_path, monkeypatch, driver_name):
    old = _fake_install(tmp_path / "a", "JLink_V794", dll=driver_name)
    new = _fake_install(tmp_path / "b", "JLink_V926", dll=driver_name)
    monkeypatch.setattr(rtt_io, "_scan_jlink_dirs",
                        lambda: sorted([old, new],
                                       key=lambda d: os.path.basename(d),
                                       reverse=True))
    assert rtt_io.find_jlink_dll().startswith(new)


def test_dll_in_directory_does_not_fall_back(tmp_path, monkeypatch, driver_name):
    """手指的目录没有驱动就得如实说没有，不能被兜底搜索掩盖。"""
    install = _fake_install(tmp_path, dll=driver_name)
    monkeypatch.setattr(rtt_io, "_scan_jlink_dirs", lambda: [install])
    empty = tmp_path / "empty"
    empty.mkdir()
    assert rtt_io.find_jlink_dll() is not None      # 兜底能找到
    assert rtt_io.dll_in_directory(str(empty)) is None
    assert rtt_io.dll_in_directory("") is None
    assert rtt_io.dll_in_directory(install) == os.path.join(install, driver_name)


def test_set_dll_hint_roundtrip(tmp_path, driver_name):
    install = _fake_install(tmp_path, dll=driver_name)
    try:
        rtt_io.set_dll_hint(install)
        assert rtt_io.get_dll_hint() == install
        assert rtt_io.find_jlink_dll() == os.path.join(install, driver_name)
    finally:
        rtt_io.set_dll_hint("")
    assert rtt_io.find_jlink_dll() is None


def test_make_jlink_uses_found_dll(tmp_path, driver_name):
    install = _fake_install(tmp_path, dll=driver_name)
    seen = {}

    class _Lib:
        def __init__(self, dllpath=None):
            seen["dllpath"] = dllpath

    class _JL:
        def __init__(self, lib=None):
            seen["lib"] = lib

    mod = types.SimpleNamespace(Library=_Lib, JLink=_JL, enums=_FakeEnums())
    rtt_io.make_jlink(mod, hint=install)
    assert seen["dllpath"] == os.path.join(install, driver_name)
    assert isinstance(seen["lib"], _Lib)
    # 找不到就退回 pylink 自己的查找（不传 lib）
    seen.clear()
    rtt_io.make_jlink(mod)
    assert seen.get("lib") is None


class _Area:
    def __init__(self, addr, size):
        self.Addr = addr
        self.Size = size


def _dev_info(name, manufacturer, core, ram=0, areas=()):
    class _Info:
        pass
    info = _Info()
    info.name = name
    info.manufacturer = manufacturer
    info.Core = core
    info.RAMSize = ram
    info.FlashSize = sum(a.Size for a in areas)
    info.aFlashArea = list(areas) + [_Area(0, 0)] * 4   # 结构体是定长数组，尾部补 0
    return info


def _fake_catalog(monkeypatch, infos):
    class _FakeJL:
        def num_supported_devices(self):
            return len(infos)

        def supported_device(self, idx):
            return infos[idx]

    rtt_io.clear_device_cache()
    monkeypatch.setattr(rtt_io, "_new_jlink", lambda mod=None: _FakeJL())


def test_list_devices_carries_vendor_core_and_flash(monkeypatch):
    """列表要能填满 厂商 / 内核 / Flash / RAM 四列。

    内核名取该 Core id 下厂商为 Unspecified 的「通用内核」条目（驱动表就是
    这么组织的，也正是 RTT Viewer 的 Core 列）。
    """
    m7 = 0x0E0100FF
    infos = [
        _dev_info("Cortex-M7", "Unspecified", m7),
        _dev_info("STM32H743VI", "ST", m7, ram=524288, areas=(
            _Area(0x08000000, 0x100000),    # bank1 1MB
            _Area(0x08100000, 0x100000),    # bank2 1MB，与 bank1 连续
            _Area(0x90000000, 0x10000000),  # 外扩 QSPI：不能算进片内容量
        )),
    ]
    _fake_catalog(monkeypatch, infos)
    rows = rtt_io.list_devices(refresh=True)
    assert rows[1] == {"name": "STM32H743VI", "manufacturer": "ST",
                       "core_id": m7, "core": "Cortex-M7",
                       "flash": 2 * 1024 * 1024, "ram": 524288}
    assert rows[0]["core"] == "Cortex-M7"
    assert rtt_io.list_supported_devices() == ["Cortex-M7", "STM32H743VI"]
    rtt_io.clear_device_cache()


def test_core_name_falls_back_to_pylink_enum(monkeypatch):
    """驱动表没给通用条目的老内核，用 pylink 的 JLinkCore 名字兜底。"""
    arm7tdmi_s = 0x070001FF
    _fake_catalog(monkeypatch, [_dev_info("ADuC7023", "ADI", arm7tdmi_s)])
    rows = rtt_io.list_devices(refresh=True)
    assert rows[0]["core"] == "ARM7TDMI-S"
    # 连 pylink 都不认识的 id：退回十六进制，至少还能按内核分组筛
    _fake_catalog(monkeypatch, [_dev_info("Weird", "X", 0x16040001)])
    rows = rtt_io.list_devices(refresh=True)
    assert rows[0]["core"] == "0X16040001"
    rtt_io.clear_device_cache()


def test_speed_presets_are_jlink_steps():
    """下拉档位必须是 J-Link 真正生效的分频（48000/N），且都在合法区间。"""
    presets = rtt_io.SPEED_PRESETS_KHZ
    assert rtt_io.DEFAULT_SPEED_KHZ in presets
    assert presets == tuple(sorted(set(presets)))
    for value in presets:
        assert rtt_io.MIN_SPEED_KHZ <= value <= rtt_io.MAX_SPEED_KHZ
        assert rtt_io.parse_speed(str(value)) == value
    for value in (600, 750, 1000, 1334, 2000, 2667, 3200, 4000):
        assert value in presets      # RTT Viewer 下拉里可见的那几档


# ----- 没插调试器要立刻失败（别耗满看门狗） -----

class _ProbeJLink(FakeJLink):
    """带 num_connected_emulators / exec_command 的 jlink（真 pylink 有）。"""

    def __init__(self, probes=1, **kw):
        super().__init__(**kw)
        self.probes = probes
        self.commands = []

    def num_connected_emulators(self):
        return self.probes

    def exec_command(self, cmd):
        self.commands.append(cmd)
        return 0


def test_conn_no_probe_fails_fast():
    """JLINKARM_Open 找不到调试器时会重试/弹窗卡几十秒，先数一下就能秒回。"""
    jl = _ProbeJLink(probes=0)
    conn = _make_conn(jl)
    errs, states = [], []
    conn.error_occurred.connect(errs.append)
    conn.state_changed.connect(states.append)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: errs, timeout=3.0)   # 远早于 CONNECT_TIMEOUT_S
        assert errs == [rtt_io.ERR_NO_PROBE]
        assert states == []
        assert "open" not in jl.calls                   # 压根没进 open()
    finally:
        conn.close()


def test_conn_silences_dll_dialogs():
    """连上后立刻关掉 JLinkARM 的弹窗，后台 worker 不会卡在无人点的对话框上。"""
    jl = _ProbeJLink(probes=1, rx=b"x")
    conn = _make_conn(jl)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert set(rtt_io.SILENT_COMMANDS) <= set(jl.commands)
        assert "HideDeviceSelection" in jl.commands
    finally:
        conn.close()


def test_probe_precheck_skipped_when_unsupported():
    """老 pylink / 注入的假对象没有这个 API 时，不能因此连不上。"""
    jl = FakeJLink(rx=b"x")             # 没有 num_connected_emulators
    assert not hasattr(jl, "num_connected_emulators")
    conn = _make_conn(jl)
    try:
        assert conn.open() is True
        assert _wait_until(lambda: conn.is_open)
        assert "open" in jl.calls
    finally:
        conn.close()
