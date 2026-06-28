import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus_slave import crc16, ModbusException, ModbusSlave  # noqa: E402
import modbus_master as mm  # noqa: E402


class BuildRequestTests(unittest.TestCase):
    def test_rtu_read_holding(self):
        # 读保持寄存器：unit 1, func 03, addr 0, qty 2 → 01 03 0000 0002 + CRC
        f = mm.build_rtu_request(1, 0x03, 0, 2)
        self.assertEqual(f[:6], bytes.fromhex("010300000002"))
        self.assertEqual(crc16(f[:-2]), f[-2:])
        self.assertEqual(len(f), 8)

    def test_rtu_read_qty_clamped(self):
        # 寄存器读数量上限 125
        f = mm.build_rtu_request(1, 0x03, 0, 9999)
        self.assertEqual(f[4:6], bytes([0x00, 125]))

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
            mm.build_rtu_request(1, 0x10, 0, 1)


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

    def test_illegal_address_exception(self):
        slave = ModbusSlave(addr=1)
        req = mm.build_rtu_request(1, 0x03, 0xFFFF, 5)   # 越过地址空间
        resp = slave.handle(req)
        with self.assertRaises(ModbusException):
            mm.take_rtu_response(resp, 1, 0x03, 5)


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


class NormalizePollTests(unittest.TestCase):
    def test_defaults_and_coercion(self):
        out = mm.normalize_poll({"unit": "0x02", "func": "3", "addr": "0x10",
                                 "qty": "4", "period": "500"})
        self.assertEqual((out["unit"], out["func"], out["addr"], out["qty"], out["period"]),
                         (2, 3, 16, 4, 500))

    def test_bad_func_falls_back(self):
        self.assertEqual(mm.normalize_poll({"func": 99})["func"], 3)

    def test_write_qty_forced_one(self):
        self.assertEqual(mm.normalize_poll({"func": 6, "qty": 50})["qty"], 1)

    def test_period_floor(self):
        self.assertEqual(mm.normalize_poll({"period": 1})["period"], 20)


if __name__ == "__main__":
    unittest.main()
