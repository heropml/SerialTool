# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus import modbus_master as mm
from modbus import modbus_slave as ms
import pytest

from modbus.modbus_gateway import (
    ModbusGatewayEngine, EXC_GATEWAY_NO_RESPONSE,
    parse_unit_map, clamp_timeout_s,
)


def test_parse_unit_map_empty_and_pairs():
    assert parse_unit_map("") == {}
    assert parse_unit_map("  ") == {}
    assert parse_unit_map("1:7, 2=10") == {1: 7, 2: 10}
    assert parse_unit_map("1:7;2:10\n3:11") == {1: 7, 2: 10, 3: 11}


def test_parse_unit_map_rejects_bad_tokens():
    with pytest.raises(ValueError):
        parse_unit_map("1")
    with pytest.raises(ValueError):
        parse_unit_map("1:x")
    with pytest.raises(ValueError):
        parse_unit_map("256:1")
    with pytest.raises(ValueError):
        parse_unit_map("1:256")
    with pytest.raises(ValueError):
        parse_unit_map("-1:1")


def test_clamp_timeout_s():
    assert clamp_timeout_s("1.0") == 1.0
    assert clamp_timeout_s(0) == 0.05
    assert clamp_timeout_s(100) == 30.0
    assert clamp_timeout_s("bad") == 1.0
    assert clamp_timeout_s(None) == 1.0
    assert clamp_timeout_s(float("nan")) == 1.0
    assert clamp_timeout_s(-3) == 0.05


def test_tcp_to_rtu_and_back():
    slave = ms.ModbusSlave(addr=7, holding={0: 0x1234})
    gw = ModbusGatewayEngine(timeout_s=1.0)
    req = mm.build_tcp_request(0x10, 7, 3, 0, 1)
    rtu_out, tcp_out = gw.feed_tcp(req)
    assert len(rtu_out) == 1 and not tcp_out
    resp = slave.handle(rtu_out[0])
    assert resp is not None
    rtu_out2, tcp_out2 = gw.feed_rtu(resp)
    assert not rtu_out2 and len(tcp_out2) == 1
    out = mm.take_tcp_response(tcp_out2[0].frame, 0x10, 3, 7)
    assert out is not None and out[0]["regs"] == [0x1234]


def test_unit_map_and_busy_queue():
    gw = ModbusGatewayEngine(unit_map={1: 7})
    req = mm.build_tcp_request(1, 1, 3, 0, 1)
    rtu_out, _ = gw.feed_tcp(req)
    assert rtu_out[0][0] == 7
    # second while pending -> held back, not dropped
    rtu_out2, _ = gw.feed_tcp(mm.build_tcp_request(2, 1, 3, 0, 1))
    assert rtu_out2 == []
    assert gw.stats["drops"] == 0
    assert gw.stats["tcp_rx"] == 2


def test_queue_overflow_drops():
    gw = ModbusGatewayEngine(max_queue=2)
    for tid in range(5):
        gw.feed_tcp(mm.build_tcp_request(tid + 1, 1, 3, 0, 1))
    assert gw.stats["drops"] == 2       # one in flight + two queued, rest dropped


def test_clients_do_not_share_a_reassembly_buffer():
    """两个客户端各自重组，且响应回到发起方。

    共用一个 _tcp_buf 时，A 的半帧会和 B 的整帧首尾相接被切成错帧，两个请求都丢。
    """
    slave_a = ms.ModbusSlave(addr=1, holding={0: 0xAAAA})
    slave_b = ms.ModbusSlave(addr=2, holding={0: 0xBBBB})
    gw = ModbusGatewayEngine()
    a = mm.build_tcp_request(0x11, 1, 3, 0, 1)
    b = mm.build_tcp_request(0x22, 2, 3, 0, 1)

    rtu1, _ = gw.feed_tcp(a[:5], client="A")          # A 只发到一半
    assert rtu1 == []
    rtu2, _ = gw.feed_tcp(b, client="B")              # B 的整帧不受 A 的残片影响
    assert len(rtu2) == 1 and rtu2[0][0] == 2

    _, reply_b = gw.feed_rtu(slave_b.handle(rtu2[0]))
    assert len(reply_b) == 1 and reply_b[0].client == "B"
    assert mm.take_tcp_response(reply_b[0].frame, 0x22, 3, 2)[0]["regs"] == [0xBBBB]

    rtu3, _ = gw.feed_tcp(a[5:], client="A")          # A 补齐，总线已空
    assert len(rtu3) == 1 and rtu3[0][0] == 1
    _, reply_a = gw.feed_rtu(slave_a.handle(rtu3[0]))
    assert len(reply_a) == 1 and reply_a[0].client == "A"
    assert mm.take_tcp_response(reply_a[0].frame, 0x11, 3, 1)[0]["regs"] == [0xAAAA]


def test_forget_client_drops_its_queued_and_pending_work():
    """客户端断开后，它那条在途请求的响应必须丢弃，不能落到广播路径上。"""
    slave = ms.ModbusSlave(addr=1, holding={0: 0x1234})
    gw = ModbusGatewayEngine()
    rtu_out, _ = gw.feed_tcp(mm.build_tcp_request(1, 1, 3, 0, 1), client="A")
    gw.feed_tcp(mm.build_tcp_request(2, 1, 3, 0, 1), client="A")   # 这条还在排队
    assert len(rtu_out) == 1 and len(gw._queue) == 1

    gw.forget_client("A")
    assert "A" not in gw.clients and not gw._queue

    _, tcp_out = gw.feed_rtu(slave.handle(rtu_out[0]))
    assert tcp_out == []


def test_other_clients_keep_working_after_one_disconnects():
    slave = ms.ModbusSlave(addr=2, holding={0: 0x5678})
    gw = ModbusGatewayEngine()
    gw.feed_tcp(mm.build_tcp_request(1, 1, 3, 0, 1)[:4], client="A")   # A 留了个残片
    gw.forget_client("A")
    rtu_out, _ = gw.feed_tcp(mm.build_tcp_request(2, 2, 3, 0, 1), client="B")
    assert len(rtu_out) == 1 and rtu_out[0][0] == 2
    _, reply = gw.feed_rtu(slave.handle(rtu_out[0]))
    assert len(reply) == 1 and reply[0].client == "B"


def test_max_clients_caps_buffer_growth():
    """客户端标识不能无限堆积，否则短连接反复接入会撑爆内存。"""
    gw = ModbusGatewayEngine(max_clients=2)
    for name in ("A", "B"):
        gw.feed_tcp(b"\x00", client=name)
    assert len(gw.clients) == 2
    rtu_out, tcp_out = gw.feed_tcp(b"\x00", client="C")
    assert rtu_out == [] and tcp_out == []
    assert "C" not in gw.clients and gw.stats["drops"] >= 1


# ------------------------------------------------------------------ tick ---
# tick() 接受 now=，超时行为可以完全确定性地测，不需要 sleep。

def _inflight(gw, tid=0x10, unit=1, client="c1", t0=1000.0):
    """发一条请求让它在途，并把计时起点钉在 t0。"""
    rtu_out, _ = gw.feed_tcp(mm.build_tcp_request(tid, unit, 3, 0, 1), client=client)
    assert len(rtu_out) == 1
    gw._pending["t0"] = t0
    return rtu_out[0]


def test_tick_before_timeout_keeps_waiting():
    gw = ModbusGatewayEngine(timeout_s=1.0)
    _inflight(gw, t0=1000.0)
    rtu_out, tcp_out = gw.tick(now=1000.99)
    assert rtu_out == [] and tcp_out == []
    assert gw._pending is not None          # 仍在等回包
    assert gw.stats["timeouts"] == 0


def test_tick_timeout_answers_0x0b_to_the_requester():
    """超时要主动回 MBAP 异常 0x0B，而不是让 TCP 主机自己等超时。"""
    gw = ModbusGatewayEngine(timeout_s=1.0)
    _inflight(gw, tid=0x77, unit=9, client="10.0.0.5:1111", t0=1000.0)
    rtu_out, tcp_out = gw.tick(now=1001.0)      # 正好到点即算超时
    assert rtu_out == []
    assert len(tcp_out) == 1
    reply = tcp_out[0]
    assert reply.client == "10.0.0.5:1111"      # 只回发起方
    frame = reply.frame
    assert frame[:2] == b"\x00\x77"             # tid 原样
    assert frame[6] == 9                        # unit 原样
    assert frame[7] == 0x83                     # func | 0x80
    assert frame[8] == EXC_GATEWAY_NO_RESPONSE  # 0x0B
    assert gw._pending is None                  # 总线已释放
    assert gw.stats["timeouts"] == 1


def test_tick_timeout_releases_the_bus_for_the_next_request():
    """超时后要把排队的下一条发出去，否则网关就此卡住。

    但不能紧接着就发：上一笔的迟到响应会被当成新那笔的答复。
    先空闲一个恢复窗口，窗口过后必须真的发出去。
    """
    gw = ModbusGatewayEngine(timeout_s=1.0)
    _inflight(gw, tid=1, unit=1, client="A", t0=1000.0)
    rtu_out, _ = gw.feed_tcp(mm.build_tcp_request(2, 2, 3, 0, 1), client="B")
    assert rtu_out == []                        # 在途期间排队

    rtu_out, tcp_out = gw.tick(now=1001.0)
    assert len(tcp_out) == 1                    # 上一条的 0x0B 立即回
    assert rtu_out == []                        # 但总线先空着
    assert gw._pending is None

    rtu_out, _ = gw.tick(now=1001.0 + gw.recovery_s + 0.01)
    assert len(rtu_out) == 1 and rtu_out[0][0] == 2   # 窗口过后上总线
    assert gw._pending is not None and gw._pending["client"] == "B"


def test_tick_timeout_for_a_departed_client_emits_no_reply():
    """客户端已断开：回包无处可去，直接丢，不能落到广播路径。"""
    gw = ModbusGatewayEngine(timeout_s=1.0)
    _inflight(gw, client="gone", t0=1000.0)
    gw.forget_client("gone")
    rtu_out, tcp_out = gw.tick(now=1001.0)
    assert tcp_out == []                        # 不回给任何人
    assert gw.stats["timeouts"] == 1            # 但超时照记
    assert gw._pending is None


def test_tick_is_a_noop_without_anything_in_flight():
    gw = ModbusGatewayEngine(timeout_s=1.0)
    assert gw.tick(now=1e9) == ([], [])
    assert gw.stats["timeouts"] == 0


def test_tick_uses_wall_clock_when_now_is_omitted():
    """省略 now 时退回 time.monotonic()，生产路径就是这么调的。"""
    gw = ModbusGatewayEngine(timeout_s=0.0)     # 0 超时 → 立即到点
    _inflight(gw, t0=0.0)
    rtu_out, tcp_out = gw.tick()
    assert len(tcp_out) == 1
    assert tcp_out[0].frame[8] == EXC_GATEWAY_NO_RESPONSE


def _read_req(tid):
    """FC03 读 1 个寄存器；两笔这样的请求在 RTU 上的响应逐字节相同。"""
    return mm.build_tcp_request(tid, 1, 3, 0, 1)


def _read_resp(value):
    body = bytes([1, 0x03, 0x02, (value >> 8) & 0xFF, value & 0xFF])
    return body + ms.crc16(body)


def test_a_late_reply_after_timeout_is_not_given_to_the_next_request():
    """超时后迟到的响应不能冒充下一笔的答复。

    RTU 没有事务号，同从机、同功能码、同数量的两笔请求，响应逐字节
    相同。若超时后紧接着发下一笔，迟到的那帧会被当成它的答复，上游
    拿到的是别人的寄存器值却没任何报错——错数据比报错危险。
    """
    gw = ModbusGatewayEngine(timeout_s=1.0)          # recovery_s 默认 0.2
    gw.feed_tcp(_read_req(1), client="A", now=0.0)
    gw.feed_tcp(_read_req(2), client="B", now=0.0)
    t0 = gw._pending["t0"]

    rtu_out, tcp_out = gw.tick(now=t0 + 1.5)
    assert [r.client for r in tcp_out] == ["A"]      # A 拿到 0x0B
    assert tcp_out[0].frame[-1] == EXC_GATEWAY_NO_RESPONSE
    assert rtu_out == []                             # 恢复窗口内总线保持空闲

    _, tcp_out = gw.feed_rtu(_read_resp(0xAAAA), now=t0 + 1.55)
    assert tcp_out == []                             # 迟到帧当无主流量丢掉


def test_the_bus_resumes_once_the_recovery_window_passes():
    gw = ModbusGatewayEngine(timeout_s=1.0)
    gw.feed_tcp(_read_req(1), client="A", now=0.0)
    gw.feed_tcp(_read_req(2), client="B", now=0.0)
    t0 = gw._pending["t0"]
    gw.tick(now=t0 + 1.5)

    rtu_out, _ = gw.tick(now=t0 + 1.5 + gw.recovery_s + 0.01)
    assert len(rtu_out) == 1                         # B 终于上总线
    assert gw._pending["client"] == "B"

    _, tcp_out = gw.feed_rtu(_read_resp(0xBBBB), now=t0 + 1.8)
    assert len(tcp_out) == 1 and tcp_out[0].client == "B"
    assert tcp_out[0].frame[9:11] == bytes([0xBB, 0xBB])   # 拿到的是自己的数据


def test_recovery_window_costs_nothing_when_nothing_times_out():
    """没超时就不该有任何额外延迟。"""
    gw = ModbusGatewayEngine(timeout_s=1.0)
    rtu_out, _ = gw.feed_tcp(_read_req(9), client="A", now=0.0)
    assert len(rtu_out) == 1


def test_recovery_can_be_switched_off():
    """recovery_s=0 退回旧行为，给不需要这层保护的场景留口子。"""
    gw = ModbusGatewayEngine(timeout_s=1.0, recovery_s=0)
    gw.feed_tcp(_read_req(1), client="A", now=0.0)
    gw.feed_tcp(_read_req(2), client="B", now=0.0)
    rtu_out, _ = gw.tick(now=gw._pending["t0"] + 1.5)
    assert len(rtu_out) == 1
