import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus.modbus_slave import crc16, ModbusException, ModbusSlave  # noqa: E402
from modbus import modbus_master as mm
from modbus import modbus_slave  # noqa: E402


class BuildRequestTests(unittest.TestCase):
    def test_tcp_transaction_id_rejects_out_of_range_or_fractional(self):
        for tid in (-1, 0x10000, 1.5, "bad"):
            with self.subTest(tid=tid), self.assertRaises(ValueError):
                mm.build_tcp_request(tid, 1, 0x03, 0, 1)
        self.assertEqual(mm.build_tcp_request(0xFFFF, 1, 0x03, 0, 1)[:2], b"\xff\xff")

    def test_rtu_read_holding(self):
        # 读保持寄存器：unit 1, func 03, addr 0, qty 2 → 01 03 0000 0002 + CRC
        f = mm.build_rtu_request(1, 0x03, 0, 2)
        self.assertEqual(f[:6], bytes.fromhex("010300000002"))
        self.assertEqual(crc16(f[:-2]), f[-2:])
        self.assertEqual(len(f), 8)

    def test_rtu_read_qty_rejected_when_invalid(self):
        for qty in (0, 126, 9999, -1, 1.5, "bad", ""):
            with self.subTest(qty=qty), self.assertRaises(ValueError):
                mm.build_rtu_request(1, 0x03, 0, qty)
        for qty in (0, 2001):
            with self.subTest(qty=qty), self.assertRaises(ValueError):
                mm.build_rtu_request(1, 0x01, 0, qty)
        self.assertEqual(mm.build_rtu_request(1, 0x03, 0, 125)[4:6], b"\x00\x7d")
        self.assertEqual(mm.build_rtu_request(1, 0x01, 0, 2000)[4:6], b"\x07\xd0")

    def test_read_range_must_not_cross_address_space(self):
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x03, 0xFFFF, 2)
        with self.assertRaises(ValueError):
            mm.build_tcp_request(1, 1, 0x01, 0xFFFE, 3)

    def test_rtu_write_single_register(self):
        f = mm.build_rtu_request(2, 0x06, 0x10, 0x1234)
        self.assertEqual(f[:6], bytes.fromhex("020600101234"))
        self.assertEqual(crc16(f[:-2]), f[-2:])

    def test_rtu_write_single_coil_on_off(self):
        on = mm.build_rtu_request(1, 0x05, 0, True)
        off = mm.build_rtu_request(1, 0x05, 0, False)
        self.assertEqual(on[4:6], bytes([0xFF, 0x00]))
        self.assertEqual(off[4:6], bytes([0x00, 0x00]))

    def test_tcp_read_mbap(self):
        # tid 1, unit 1, func 03, addr 0, qty 2 → MBAP(0001 0000 0006 01) + PDU(03 0000 0002)
        f = mm.build_tcp_request(1, 1, 0x03, 0, 2)
        self.assertEqual(f, bytes.fromhex("000100000006010300000002"))

    def test_unsupported_func_raises(self):
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x07, 0, 1)   # 0x07 主机不支持（0F/10 现已支持）


class ParseResponseTests(unittest.TestCase):
    def test_read_holding(self):
        pdu = bytes.fromhex("0304" + "1234" + "5678")   # func 03, bc 4, two regs
        self.assertEqual(mm.parse_pdu(0x03, pdu), {"regs": [0x1234, 0x5678]})

    def test_read_coils(self):
        pdu = bytes.fromhex("0101" + "05")              # func 01, bc 1, bits 0b00000101
        out = mm.parse_pdu(0x01, pdu)
        self.assertEqual(out["bits"][:4], [True, False, True, False])

    def test_write_echo(self):
        pdu = bytes.fromhex("06" + "0010" + "1234")
        self.assertEqual(mm.parse_pdu(0x06, pdu), {"echo": (0x10, 0x1234)})

    def test_short_and_trailing_pdu_rejected(self):
        with self.assertRaises(ValueError):
            mm.parse_pdu(0x03, b"\x03")
        with self.assertRaises(ValueError):
            mm.parse_pdu(0x03, bytes.fromhex("03021234AABB"))
        with self.assertRaises(ValueError):
            mm.parse_pdu(0x10, bytes.fromhex("1000000002AABB"))

    def test_exception_raises(self):
        with self.assertRaises(ModbusException) as cm:
            mm.parse_pdu(0x03, bytes([0x83, 0x02]))
        self.assertEqual(cm.exception.code, 0x02)

    def test_func_mismatch(self):
        with self.assertRaises(ValueError):
            mm.parse_pdu(0x03, bytes.fromhex("0404123456 78".replace(" ", "")))


class FrameExtractionTests(unittest.TestCase):
    def _rtu_resp(self, body):
        return body + crc16(body)

    def test_take_rtu_normal(self):
        body = bytes.fromhex("0103" + "04" + "11112222")   # unit1 func3 bc4 + 2 regs
        frame = self._rtu_resp(body)
        res, consumed = mm.take_rtu_response(frame, 1, 0x03, 2)
        self.assertEqual(res, {"regs": [0x1111, 0x2222]})
        self.assertEqual(consumed, len(frame))

    def test_take_rtu_partial_then_complete(self):
        body = bytes.fromhex("0103" + "04" + "11112222")
        frame = self._rtu_resp(body)
        # 半包返回 None，补齐后取出
        self.assertIsNone(mm.take_rtu_response(frame[:5], 1, 0x03, 2))
        res, consumed = mm.take_rtu_response(frame, 1, 0x03, 2)
        self.assertEqual(res["regs"], [0x1111, 0x2222])

    def test_take_rtu_exception(self):
        body = bytes([0x01, 0x83, 0x02])                   # 异常响应
        frame = self._rtu_resp(body)
        with self.assertRaises(ModbusException):
            mm.take_rtu_response(frame, 1, 0x03, 2)

    def test_take_rtu_crc_error(self):
        body = bytes.fromhex("0103" + "04" + "11112222")
        frame = body + b"\x00\x00"                          # 坏 CRC
        with self.assertRaises(ValueError):
            mm.take_rtu_response(frame, 1, 0x03, 2)

    def test_take_rtu_unit_mismatch(self):
        body = bytes.fromhex("0203" + "04" + "11112222")   # 来自 unit 2
        frame = self._rtu_resp(body)
        with self.assertRaises(ValueError):
            mm.take_rtu_response(frame, 1, 0x03, 2)

    def test_take_tcp_normal(self):
        frame = bytes.fromhex("000100000007010304" + "11112222")
        res, consumed = mm.take_tcp_response(frame, 1, 0x03)
        self.assertEqual(res, {"regs": [0x1111, 0x2222]})
        self.assertEqual(consumed, len(frame))

    def test_take_tcp_partial(self):
        frame = bytes.fromhex("000100000007010304" + "11112222")
        self.assertIsNone(mm.take_tcp_response(frame[:6], 1, 0x03))

    def test_take_tcp_tid_mismatch(self):
        frame = bytes.fromhex("000900000007010304" + "11112222")
        with self.assertRaises(ValueError):
            mm.take_tcp_response(frame, 1, 0x03)

    def test_take_tcp_exception(self):
        frame = bytes.fromhex("0001000000030183" + "02")   # len 3: unit+func|0x80+code
        with self.assertRaises(ModbusException):
            mm.take_tcp_response(frame, 1, 0x03)

    def test_take_tcp_rejects_trailing_pdu_bytes(self):
        frame = bytes.fromhex("0001000000070103021234AABB")
        with self.assertRaises(ValueError):
            mm.take_tcp_response(frame, 1, 0x03, req_unit=1)

    def test_take_tcp_matching_skips_late_frame(self):
        late = bytes.fromhex("0001000000050103021111")
        current = bytes.fromhex("0002000000050103022222")
        result, consumed = mm.take_tcp_response_matching(late + current, 2, 0x03, 1)
        self.assertEqual(result, {"regs": [0x2222]})
        self.assertEqual(consumed, len(late + current))

    def test_take_tcp_matching_consumes_late_and_keeps_current_partial(self):
        late = bytes.fromhex("0001000000050103021111")
        current = bytes.fromhex("0002000000050103022222")
        result, consumed = mm.take_tcp_response_matching(late + current[:7], 2, 0x03, 1)
        self.assertIsNone(result)
        self.assertEqual(consumed, len(late))
        result, consumed2 = mm.take_tcp_response_matching(current, 2, 0x03, 1)
        self.assertEqual(result, {"regs": [0x2222]})
        self.assertEqual(consumed2, len(current))

    def test_take_tcp_rejects_oversized_mbap_length(self):
        bad = bytes.fromhex("0001000000FF") + b"\x01\x03"
        with self.assertRaises(ValueError):
            mm.take_tcp_response(bad, 1, 0x03, 1)
        with self.assertRaises(ValueError):
            mm.take_tcp_response_matching(bad, 1, 0x03, 1)


class RoundTripWithSlaveTests(unittest.TestCase):
    """主机构造的 RTU 请求喂给从机模型，从机响应再由主机解析，端到端闭环。"""
    def test_read_back(self):
        slave = ModbusSlave(addr=1, holding={0: 0xABCD, 1: 0x0001})
        req = mm.build_rtu_request(1, 0x03, 0, 2)
        resp = slave.handle(req)
        res, _ = mm.take_rtu_response(resp, 1, 0x03, 2)
        self.assertEqual(res["regs"], [0xABCD, 0x0001])

    def test_write_then_read(self):
        slave = ModbusSlave(addr=1)
        wreq = mm.build_rtu_request(1, 0x06, 5, 0x7777)
        wresp = slave.handle(wreq)
        wres, _ = mm.take_rtu_response(wresp, 1, 0x06, 1)
        self.assertEqual(wres["echo"], (5, 0x7777))
        rreq = mm.build_rtu_request(1, 0x03, 5, 1)
        rresp = slave.handle(rreq)
        rres, _ = mm.take_rtu_response(rresp, 1, 0x03, 1)
        self.assertEqual(rres["regs"], [0x7777])

    def test_master_rejects_address_space_overflow_before_send(self):
        # 主机安全层不再把必然跨出 16 位地址空间的请求交给设备处理。
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x03, 0xFFFF, 5)


class ReviewFixTests(unittest.TestCase):
    """对抗式 review 指出的缺陷的回归测试。"""
    def test_exception_func_must_match_request(self):
        # 请求 03 收到 84（func 04 的异常码）→ 不是本次异常，应 ValueError 而非 ModbusException
        with self.assertRaises(ValueError):
            mm.parse_pdu(0x03, bytes([0x84, 0x02]))
        # 正确的 83（=03|0x80）→ ModbusException
        with self.assertRaises(ModbusException):
            mm.parse_pdu(0x03, bytes([0x83, 0x02]))

    def test_rtu_take_wrong_exception_func_not_consumed_as_ours(self):
        body = bytes([0x01, 0x84, 0x02])               # unit1, func 84（非本次 03 的异常）
        frame = body + crc16(body)
        with self.assertRaises(ValueError):
            mm.take_rtu_response(frame, 1, 0x03, 2)

    def test_tcp_unit_mismatch_rejected(self):
        # 请求 unit 1，收到 unit 2 的响应 → ValueError
        frame = bytes.fromhex("0001000000050203021111")   # MBAP unit=02 + 03 02 1111
        with self.assertRaises(ValueError):
            mm.take_tcp_response(frame, 1, 0x03, req_unit=1)
        # 同帧但请求 unit 2 → 正常解析
        res, _ = mm.take_tcp_response(frame, 1, 0x03, req_unit=2)
        self.assertEqual(res, {"regs": [0x1111]})

    def test_tcp_unit_match_default_none_still_works(self):
        frame = bytes.fromhex("000100000005010302" + "1111")
        res, _ = mm.take_tcp_response(frame, 1, 0x03)   # req_unit 省略 → 不校 unit
        self.assertEqual(res, {"regs": [0x1111]})

    def test_strip_local_echo_after_noise(self):
        req = mm.build_rtu_request(1, 0x06, 0x10, 0x1234)
        exc_body = bytes.fromhex("018602")
        exc = exc_body + crc16(exc_body)
        rest, found = mm.strip_local_echo(b"\x99\x00" + req + exc, req)
        self.assertTrue(found)
        self.assertEqual(rest, exc)

    def test_strip_local_echo_waits_for_complete_request(self):
        req = mm.build_rtu_request(1, 0x06, 0x10, 0x1234)
        buf = b"\x99" + req[:-1]
        rest, found = mm.strip_local_echo(buf, req)
        self.assertFalse(found)
        self.assertEqual(rest, buf)

    def test_strip_local_echo_exact_prefix(self):
        req = mm.build_rtu_request(1, 0x03, 0, 1)
        response_body = bytes.fromhex("0103021234")
        response = response_body + crc16(response_body)
        rest, found = mm.strip_local_echo(req + response, req)
        self.assertTrue(found)
        self.assertEqual(rest, response)


class WriteMultiTests(unittest.TestCase):
    """0F 写多线圈 / 10 写多寄存器。"""
    def test_build_rtu_write_multi_registers(self):
        # unit1 func10 addr0 qty2 bc4 + 1234 5678 + CRC
        f = mm.build_rtu_request(1, 0x10, 0, [0x1234, 0x5678])
        self.assertEqual(f[:-2], bytes.fromhex("0110000000020412345678"))
        self.assertEqual(crc16(f[:-2]), f[-2:])

    def test_build_rtu_write_multi_coils(self):
        # 5 个线圈 1,0,1,1,0 → bits 0b00001101 = 0x0D, qty=5, bc=1
        f = mm.build_rtu_request(1, 0x0F, 0, [1, 0, 1, 1, 0])
        self.assertEqual(f[:7], bytes.fromhex("010F0000000501"))
        self.assertEqual(f[7], 0x0D)

    def test_build_tcp_write_multi(self):
        f = mm.build_tcp_request(1, 1, 0x10, 0, [0x1111, 0x2222])
        # MBAP(7B) length = unit(1)+pdu(6 header +4 data)=11 → 000B
        self.assertEqual(f[:7], bytes.fromhex("00010000000B01"))
        self.assertEqual(f[7:], bytes.fromhex("10000000020411112222"))

    def test_build_write_multi_rejects_empty_values(self):
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x10, 0, [])
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x0F, 0, [])

    def test_build_write_multi_rejects_too_many_values(self):
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x10, 0, [0] * 124)
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x0F, 0, [0] * 1969)

    def test_build_write_multi_rejects_address_span_overflow(self):
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x10, 0xFFFF, [1, 2])
        with self.assertRaises(ValueError):
            mm.build_rtu_request(0, 0x0F, 0xFFFF, [1, 0])

    def test_parse_write_multi_echo(self):
        pdu = bytes.fromhex("10" + "0000" + "0002")     # func10 addr0 qty2
        self.assertEqual(mm.parse_pdu(0x10, pdu), {"echo": (0, 2)})

    def test_roundtrip_write_multi_then_read(self):
        slave = ModbusSlave(addr=1)
        wreq = mm.build_rtu_request(1, 0x10, 10, [0xAAAA, 0xBBBB, 0xCCCC])
        wres, _ = mm.take_rtu_response(slave.handle(wreq), 1, 0x10, 3)
        self.assertEqual(wres["echo"], (10, 3))          # 回显 起始地址 + 数量
        rres, _ = mm.take_rtu_response(slave.handle(mm.build_rtu_request(1, 0x03, 10, 3)), 1, 0x03, 3)
        self.assertEqual(rres["regs"], [0xAAAA, 0xBBBB, 0xCCCC])

    def test_roundtrip_write_multi_coils(self):
        slave = ModbusSlave(addr=1)
        wreq = mm.build_rtu_request(1, 0x0F, 0, [1, 0, 1])
        wres, _ = mm.take_rtu_response(slave.handle(wreq), 1, 0x0F, 3)
        self.assertEqual(wres["echo"], (0, 3))
        rres, _ = mm.take_rtu_response(slave.handle(mm.build_rtu_request(1, 0x01, 0, 3)), 1, 0x01, 3)
        self.assertEqual(rres["bits"][:3], [True, False, True])

    def test_normalize_write_multi_parses_list(self):
        out = mm.normalize_poll({"func": 0x10, "addr": 0, "wval": "100, 200, 0x10"})
        self.assertEqual(out["wvals"], [100, 200, 16])
        self.assertEqual(out["qty"], 3)

    def test_normalize_write_multi_rejects_out_of_range(self):
        self.assertEqual(mm.normalize_poll({"func": 0x0F, "wval": "0 2 1"})["wvals"], [])
        self.assertEqual(mm.normalize_poll({"func": 0x10, "wval": "-1 2"})["wvals"], [])
        self.assertEqual(mm.normalize_poll({"func": 0x10, "wval": "1 70000"})["wvals"], [])
        self.assertEqual(mm.normalize_poll({"func": 0x10, "wvals": [1.9]})["wvals"], [])

    def test_normalize_write_multi_rejects_too_many_values(self):
        self.assertEqual(mm.normalize_poll({"func": 0x10, "wvals": [0] * 124})["wvals"], [])
        self.assertEqual(mm.normalize_poll({"func": 0x0F, "wvals": [0] * 1969})["wvals"], [])

    def test_normalize_write_multi_from_wvals_list(self):
        # 从已规范化的持久配置(含 wvals 列表)再规范化不丢值
        out = mm.normalize_poll({"func": 0x10, "wvals": [1, 2, 3], "wval": 0})
        self.assertEqual(out["wvals"], [1, 2, 3])

    def test_normalize_write_multi_empty_stays_empty(self):
        # 空白/非法 → wvals 保持空（不默认 [0]，由引擎判输入错误，杜绝静默写 0）
        self.assertEqual(mm.normalize_poll({"func": 0x10, "wval": "  "})["wvals"], [])
        self.assertEqual(mm.normalize_poll({"func": 0x0F, "wval": "abc"})["wvals"], [])

    def test_normalize_write_multi_rejects_mixed_invalid_values(self):
        # 任一项非法必须整组拒绝；若只跳过 abc，300 会从地址 +2 错移到 +1。
        self.assertEqual(mm.normalize_poll(
            {"func": 0x10, "wval": "100, abc, 300"})["wvals"], [])
        self.assertEqual(mm.normalize_poll(
            {"func": 0x0F, "wval": "1, nope, 0"})["wvals"], [])


class NormalizePollTests(unittest.TestCase):
    def test_defaults_and_coercion(self):
        out = mm.normalize_poll({"unit": "0x02", "func": "3", "addr": "0x10",
                                 "qty": "4", "period": "500"})
        self.assertEqual((out["unit"], out["func"], out["addr"], out["qty"], out["period"]),
                         (2, 3, 16, 4, 500))

    def test_bad_func_falls_back(self):
        self.assertEqual(mm.normalize_poll({"func": 99})["func"], 3)
        self.assertEqual(mm.normalize_poll({"func": 15.9})["func"], 3)  # 不得截断成写功能 0F

    def test_unit_and_address_are_not_silently_coerced(self):
        for rec in (
            {"unit": "bad", "addr": 0}, {"unit": 999, "addr": 0},
            {"unit": -1, "addr": 0}, {"unit": 1, "addr": "bad"},
            {"unit": 1, "addr": 70000}, {"unit": 1, "addr": -1},
            {"unit": 1.9, "addr": 0}, {"unit": 1, "addr": 2.8},
        ):
            out = mm.normalize_poll(rec)
            self.assertTrue(out["unit"] is None or out["addr"] is None, rec)

    def test_enabled_string_false_is_disabled(self):
        # 字符串 'false'/'0'/'no'/'off'/'' 不能被当成启用（非空字符串 bool 恒为 True 的坑）
        for v in ("false", "False", "0", "no", "off", ""):
            self.assertFalse(mm.normalize_poll({"func": 3, "enabled": v})["enabled"], v)
        for v in ("true", "1", "yes", True, 1):
            self.assertTrue(mm.normalize_poll({"func": 3, "enabled": v})["enabled"], v)
        self.assertEqual(mm.normalize_poll({"func": 3, "enabled": 0})["enabled"], False)
        # 缺省 → 启用
        self.assertTrue(mm.normalize_poll({"func": 3})["enabled"])

    def test_tcp_unit_255_is_preserved(self):
        self.assertEqual(mm.normalize_poll({"unit": 255, "func": 3})["unit"], 255)

    def test_build_rejects_invalid_unit_and_address(self):
        with self.assertRaises(ValueError):
            mm.build_rtu_request(248, 0x03, 0, 1)
        with self.assertRaises(ValueError):
            mm.build_tcp_request(1, 256, 0x03, 0, 1)
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x03, 70000, 1)

    def test_write_qty_forced_one(self):
        self.assertEqual(mm.normalize_poll({"func": 6, "qty": 50})["qty"], 1)

    def test_read_qty_is_not_silently_coerced(self):
        for func, bad_values in ((1, (0, 2001, "bad", "")),
                                 (3, (0, 126, "bad", ""))):
            for qty in bad_values:
                with self.subTest(func=func, qty=qty):
                    self.assertIsNone(mm.normalize_poll({"func": func, "qty": qty})["qty"])

    def test_write_single_rejects_invalid_or_out_of_range(self):
        self.assertIsNone(mm.normalize_poll({"func": 5, "wval": 2})["wval"])
        self.assertIsNone(mm.normalize_poll({"func": 6, "wval": -1})["wval"])
        self.assertIsNone(mm.normalize_poll({"func": 6, "wval": 70000})["wval"])
        self.assertIsNone(mm.normalize_poll({"func": 6, "wval": 1.9})["wval"])
        self.assertEqual(mm.normalize_poll({"func": 6, "wval": 65535})["wval"], 65535)

    def test_build_write_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x05, 0, 2)
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x06, 0, 70000)
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x0F, 0, [0, 2])
        with self.assertRaises(ValueError):
            mm.build_rtu_request(1, 0x10, 0, [-1, 1])

    def test_period_is_strict_and_bounded(self):
        for period in ("", "bad", 0, 19, -1, 20.5, 0x80000000):
            with self.subTest(period=period):
                self.assertIsNone(mm.normalize_poll({"period": period})["period"])
        self.assertEqual(mm.normalize_poll({"period": 20})["period"], 20)


class AsciiRequestTests(unittest.TestCase):
    def test_ascii_read_holding_known_frame(self):
        # 读 slave1 addr0 qty2：01 03 00 00 00 02，sum=06，LRC=FA
        f = mm.build_ascii_request(1, 0x03, 0, 2)
        self.assertEqual(f, b":010300000002FA\r\n")

    def test_ascii_unit_range_matches_rtu(self):
        for unit in (248, -1, 999):
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                mm.build_ascii_request(unit, 0x03, 0, 1)

    def test_ascii_round_trip_via_slave(self):
        slave = ModbusSlave(addr=1, holding={0: 0x1234, 1: 0x5678})
        resp = slave.handle_ascii(mm.build_ascii_request(1, 0x03, 0, 2))
        self.assertEqual(resp, b":01030412345678E4\r\n")
        result, consumed = mm.take_ascii_response(resp, 1, 0x03)
        self.assertEqual(result, {"regs": [0x1234, 0x5678]})
        self.assertEqual(consumed, len(resp))

    def test_ascii_write_echo_round_trip(self):
        slave = ModbusSlave(addr=2)
        resp = slave.handle_ascii(mm.build_ascii_request(2, 0x06, 0x10, 0x1234))
        result, _ = mm.take_ascii_response(resp, 2, 0x06)
        self.assertEqual(result, {"echo": (0x10, 0x1234)})

    def test_ascii_exception_response_raises(self):
        # 非法功能码 0x41 → 异常 func 0xC1 code 01
        from modbus.modbus_slave import ascii_wrap
        bad = ascii_wrap(bytes([1, 0x41, 0, 0, 0, 1]))
        resp = ModbusSlave(addr=1).handle_ascii(bad)
        self.assertIsNotNone(resp)
        with self.assertRaises(ModbusException) as ctx:
            mm.take_ascii_response(resp, 1, 0x41)
        self.assertEqual(ctx.exception.code, 0x01)

    def test_ascii_lrc_error_raises_value_error(self):
        # 改坏 LRC 末位 → take 抛 ValueError（坏帧）
        bad = b":010300000002FB\r\n"
        with self.assertRaises(ValueError):
            mm.take_ascii_response(bad, 1, 0x03)

    def test_ascii_unit_mismatch_raises(self):
        resp = ModbusSlave(addr=2, holding={0: 1}).handle_ascii(mm.build_ascii_request(2, 0x03, 0, 1))
        with self.assertRaises(ValueError):
            mm.take_ascii_response(resp, 1, 0x03)   # 请求 unit=1 但响应来自 unit=2

    def test_ascii_partial_returns_none(self):
        self.assertIsNone(mm.take_ascii_response(b":0103", 1, 0x03))
        self.assertIsNone(mm.take_ascii_response(b"garbage_no_colon", 1, 0x03))

    def test_ascii_consumes_leading_garbage(self):
        resp = ModbusSlave(addr=1, holding={0: 0x000A}).handle_ascii(mm.build_ascii_request(1, 0x03, 0, 1))
        result, consumed = mm.take_ascii_response(b"XX\r\n" + resp, 1, 0x03)
        self.assertEqual(result, {"regs": [0x000A]})
        self.assertEqual(consumed, len(b"XX\r\n" + resp))


class ModbusMasterP1Tests(unittest.TestCase):
    def test_build_parse_fc08(self):
        req = mm.build_rtu_request(1, 8, 0, 0xABCD)
        self.assertEqual(req[1], 8)
        pdu = bytes([8, 0, 0, 0xAB, 0xCD])
        self.assertEqual(mm.parse_pdu(8, pdu)["diag"], (0, 0xABCD))

    def test_build_parse_fc23(self):
        req = mm.build_rtu_request(
            1, 0x17, 0,
            {"read_addr": 0, "read_qty": 2, "write_addr": 10, "write_vals": [1, 2]})
        self.assertEqual(req[1], 0x17)
        s = modbus_slave.ModbusSlave(addr=1, holding={0: 7, 1: 8})
        resp = s.handle(req)
        self.assertEqual(mm.parse_pdu(0x17, resp[1:-2])["regs"], [7, 8])
        self.assertEqual(s.holding[10], 1)
        self.assertEqual(s.holding[11], 2)

    def test_fc23_invalid_read_qty_fails_at_build_time(self):
        """FC23 读数量非法时必须在建帧阶段报错。

        normalize_poll 会把非法数量存成 None（保持 None 才能让上层报错，而不是
        静默改成别的值）。轮询发送前的建帧被 try/except 兜住并把错落到那条规则
        上；要是建帧反而放过 None，后面按 帧长 算超时的一步就会带着 None 崩掉。
        """
        for bad in ("abc", "", 0, 9999, None):
            r = mm.normalize_poll({"func": 0x17, "addr": 0, "qty": bad,
                                   "write_addr": 5, "wvals": "1,2"})
            self.assertIsNone(r["qty"])
            with self.assertRaises(ValueError):
                mm.build_rtu_request(1, 0x17, r["addr"],
                                     (r["qty"], r["write_addr"], r["wvals"]))
            with self.assertRaises(ValueError):
                mm.rtu_normal_len(0x17, r["qty"])

    def test_normalize_poll_new_funcs(self):
        p = mm.normalize_poll({"func": 8, "wval": 5})
        self.assertEqual(p["func"], 8)
        p = mm.normalize_poll({"func": 0x0B})
        self.assertEqual(p["func"], 0x0B)


if __name__ == "__main__":
    unittest.main()
