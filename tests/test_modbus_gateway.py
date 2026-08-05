# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import modbus_master as mm
import modbus_slave as ms
from modbus_gateway import ModbusGatewayEngine


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
