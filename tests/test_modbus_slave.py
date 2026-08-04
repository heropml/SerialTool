import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import modbus_slave
import modbus_master
from modbus_slave import (  # noqa: E402
    ModbusSlave, crc16, iter_frames, iter_ascii_frames, parse_ascii_frame,
    ascii_wrap, lrc8,
)


def request(hex_body):
    body = bytes.fromhex(hex_body)
    return body + crc16(body)


class ModbusFramingTests(unittest.TestCase):
    def assert_all_splits(self, frame):
        for split in range(1, len(frame)):
            first, remainder = iter_frames(frame[:split])
            second, remainder = iter_frames(remainder + frame[split:])
            self.assertEqual(first + second, [frame], split)
            self.assertEqual(remainder, b"", split)

    def test_supported_frames_survive_every_split(self):
        for frame in (
            request("01 03 00 00 00 02"),
            request("01 06 00 01 AB CD"),
            request("01 0F 00 00 00 09 02 55 01"),
            request("01 10 00 00 00 02 04 12 34 56 78"),
        ):
            self.assert_all_splits(frame)

    def test_unknown_function_survives_every_split(self):
        # 0x2B 未实现且带数据段：长度无法由功能码推出，走 CRC 探测分支
        self.assert_all_splits(request("01 2B 00 00 12 34"))
        self.assert_all_splits(request("01 07"))

    def test_bad_frame_resyncs_to_following_valid_frame(self):
        bad = request("01 03 00 00 00 01")[:-1] + b"\x00"
        good = request("01 03 00 01 00 01")
        frames, remainder = iter_frames(bad + good)
        self.assertEqual(frames, [good])
        self.assertEqual(remainder, b"")

    def test_bogus_multi_write_length_does_not_block_next_frame(self):
        bogus = bytes.fromhex("99 10 00 00 00 01 FF")
        good = request("01 03 00 00 00 01")
        frames, remainder = iter_frames(bogus + good)
        self.assertEqual(frames, [good])
        self.assertEqual(remainder, b"")

class ModbusSlaveTests(unittest.TestCase):
    def test_unknown_function_returns_exception(self):
        slave = ModbusSlave(addr=1)
        frame = request("01 07")
        resp = slave.handle(frame)
        self.assertEqual(resp[0], 1)
        self.assertEqual(resp[1], 0x87)  # 0x07 | 0x80
        self.assertEqual(resp[2], 0x01)  # illegal function

    def test_unknown_function_frames_then_returns_exception(self):
        # 切帧 + 处理联贯：未知功能码整帧取出后回「非法功能」
        slave = ModbusSlave(addr=1)
        frame = request("01 2B 00 00 12 34")
        frames, remainder = iter_frames(frame)
        self.assertEqual(remainder, b"")
        self.assertEqual(frames, [frame])
        self.assertEqual(slave.handle(frames[0]), request("01 AB 01"))

    def test_read_past_address_space_returns_exception(self):
        slave = ModbusSlave(addr=1)
        self.assertEqual(slave.handle(request("01 03 FF FF 00 02")), request("01 83 02"))


class ModbusAsciiTests(unittest.TestCase):
    def test_lrc_and_wrap_roundtrip(self):
        body = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x02])
        self.assertEqual(lrc8(body), 0xFA)
        wrapped = ascii_wrap(body)
        self.assertEqual(wrapped, b":010300000002FA\r\n")
        self.assertEqual(parse_ascii_frame(wrapped), (0x01, 0x03, bytes([0x00, 0x00, 0x00, 0x02])))

    def test_handle_ascii_replies_with_correct_lrc(self):
        slave = ModbusSlave(addr=1, holding={0: 0x1234, 1: 0x5678})
        resp = slave.handle_ascii(ascii_wrap(bytes([1, 0x03, 0, 0, 0, 2])))
        self.assertEqual(resp, b":01030412345678E4\r\n")
        # 响应 LRC 必须自洽
        self.assertIsNotNone(parse_ascii_frame(resp))

    def test_handle_ascii_broadcast_and_wrong_unit_silent(self):
        slave = ModbusSlave(addr=1, holding={0: 5})
        # 广播写 addr0 → 无响应
        self.assertIsNone(slave.handle_ascii(ascii_wrap(bytes([0, 0x06, 0, 4, 0, 1]))))
        # 非本机 → 无响应
        self.assertIsNone(slave.handle_ascii(ascii_wrap(bytes([2, 0x03, 0, 0, 0, 1]))))

    def test_handle_ascii_lrc_error_silent(self):
        slave = ModbusSlave(addr=1)
        self.assertIsNone(slave.handle_ascii(b":010300000002FB\r\n"))   # LRC 改坏

    def test_handle_ascii_exception_reply(self):
        # 读未配置 coils 不会异常（默认 0）；用越界地址触发非法地址(02)
        slave = ModbusSlave(addr=1)
        resp = slave.handle_ascii(ascii_wrap(bytes([1, 0x03, 0xFF, 0xFF, 0x00, 0x02])))
        parsed = parse_ascii_frame(resp)
        self.assertEqual(parsed[1], 0x83)         # 0x03 | 0x80
        self.assertEqual(parsed[2], bytes([0x02]))

    def test_handle_ascii_writes_mutate_runtime(self):
        slave = ModbusSlave(addr=1)
        slave.handle_ascii(ascii_wrap(bytes([1, 0x06, 0, 4, 0x12, 0x34])))
        self.assertEqual(slave.holding[4], 0x1234)

    def test_handle_ascii_empty_pdu_silent(self):
        slave = ModbusSlave(addr=1)
        # 仅 addr+func+lrc，func 后无 payload → _exec IndexError → None
        self.assertIsNone(slave.handle_ascii(ascii_wrap(bytes([1, 0x03]))))

    def test_iter_ascii_frames_split_partial_and_garbage(self):
        f1 = b":010300000002FA\r\n"
        f2 = b":01030412345678E4\r\n"
        # 粘包：两帧完整 → 都切出
        self.assertEqual(iter_ascii_frames(f1 + f2), ([f1, f2], b""))
        # 半包：第二帧无 \n → 保留
        self.assertEqual(iter_ascii_frames(f1 + b":01030"), ([f1], b":01030"))
        # 无帧首：前导垃圾整体丢弃
        self.assertEqual(iter_ascii_frames(b"GARBAGE"), ([], b""))
        # 帧首但未完：保留从 ':' 起
        self.assertEqual(iter_ascii_frames(b":0103"), ([], b":0103"))

    def test_parse_ascii_frame_rejects_malformed(self):
        for bad in (b"", b":010\r\n", b":01ZZ\r\n", b"\x01\x03\r\n", b":010300000002FB\r\n"):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_ascii_frame(bad))

    def test_rtu_handle_still_works_after_ascii_addition(self):
        # 回归：RTU handle/CRC 路径未受 _respond 重构影响
        slave = ModbusSlave(addr=1, holding={0: 0x1234})
        resp = slave.handle(request("01 03 00 00 00 01"))
        self.assertEqual(resp, request("01 03 02 12 34"))


class ModbusP1Tests(unittest.TestCase):
    def test_multi_slave_bank_dispatch(self):
        a = modbus_slave.ModbusSlave(addr=1, holding={0: 11})
        b = modbus_slave.ModbusSlave(addr=2, holding={0: 22})
        bank = modbus_slave.MultiSlaveBank([a, b])
        req1 = modbus_master.build_rtu_request(1, 3, 0, 1)
        req2 = modbus_master.build_rtu_request(2, 3, 0, 1)
        r1 = bank.handle(req1)
        r2 = bank.handle(req2)
        self.assertEqual(modbus_master.parse_pdu(3, r1[1:-2])["regs"], [11])
        self.assertEqual(modbus_master.parse_pdu(3, r2[1:-2])["regs"], [22])
        self.assertIsNone(bank.handle(modbus_master.build_rtu_request(3, 3, 0, 1)))

    def test_exception_injection_once(self):
        s = modbus_slave.ModbusSlave(
            addr=1, holding={0: 1},
            exception_policy={"enabled": True, "code": 4, "mode": "once", "funcs": [3]},
        )
        req = modbus_master.build_rtu_request(1, 3, 0, 1)
        with self.assertRaises(modbus_slave.ModbusException):
            modbus_master.parse_pdu(3, s.handle(req)[1:-2])
        regs = modbus_master.parse_pdu(3, s.handle(req)[1:-2])["regs"]
        self.assertEqual(regs, [1])

    def test_dynamic_inc(self):
        s = modbus_slave.ModbusSlave(
            addr=1, holding={0: 0},
            dynamics=[{"space": "holding", "addr": 0, "mode": "inc",
                       "step": 1, "min": 0, "max": 100, "period_ms": 1000}],
        )
        s.dynamic_engine.reset(now=0.0)
        self.assertEqual(s.dynamic_engine.value("holding", 0, fallback=0, now=0.0), 0)
        self.assertEqual(s.dynamic_engine.value("holding", 0, fallback=0, now=2.5), 2)

    def test_fc08_echo(self):
        s = modbus_slave.ModbusSlave(addr=1)
        req = modbus_master.build_rtu_request(1, 8, 0, 0x1234)
        resp = s.handle(req)
        self.assertEqual(modbus_master.parse_pdu(8, resp[1:-2])["diag"], (0, 0x1234))

    def test_fc11_event_counter(self):
        s = modbus_slave.ModbusSlave(addr=1, holding={0: 1})
        s.handle(modbus_master.build_rtu_request(1, 3, 0, 1))
        req = modbus_master.build_rtu_request(1, 0x0B, 0, 0)
        resp = s.handle(req)
        parsed = modbus_master.parse_pdu(0x0B, resp[1:-2])
        self.assertGreaterEqual(parsed["event_count"], 1)

    def test_fc17_server_id(self):
        s = modbus_slave.ModbusSlave(addr=1, server_id=b"CT")
        req = modbus_master.build_rtu_request(1, 0x11, 0, 0)
        resp = s.handle(req)
        parsed = modbus_master.parse_pdu(0x11, resp[1:-2])
        self.assertTrue(parsed["server_id"].startswith(b"CT"))
        self.assertTrue(parsed["run"])

    def test_fc23_read_write(self):
        s = modbus_slave.ModbusSlave(addr=1, holding={0: 10, 1: 20, 5: 0})
        req = modbus_master.build_rtu_request(
            1, 0x17, 0,
            {"read_addr": 0, "read_qty": 2, "write_addr": 5, "write_vals": [99]})
        resp = s.handle(req)
        self.assertEqual(modbus_master.parse_pdu(0x17, resp[1:-2])["regs"], [10, 20])
        self.assertEqual(s.holding[5], 99)


class Fc08DiagnosticsTests(unittest.TestCase):
    """Spec 6.8: an 08 request is sub-function(2) + data(N x 2 bytes). Only
    sub-function 0 (Return Query Data) varies in length -- 0x0A..0x12 and 0x14
    all carry a fixed `00 00`, so those stay plain 8-byte frames."""

    COUNTER_SUBS = (0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x14)

    def loopback(self, words):
        body = bytes((1, 8, 0, 0))
        for word in words:
            body += bytes(((word >> 8) & 0xFF, word & 0xFF))
        return body + crc16(body)

    def test_counter_subfunctions_are_plain_eight_byte_frames(self):
        for sub in self.COUNTER_SUBS:
            req = modbus_master.build_rtu_request(1, 8, 0, (sub, 0x0000))
            self.assertEqual(len(req), 8, hex(sub))
            self.assertEqual(modbus_slave.expected_len(req), 8, hex(sub))
            self.assertEqual(iter_frames(req), ([req], b""), hex(sub))

    def test_unimplemented_subfunction_answers_illegal_value(self):
        # Only sub-function 0 is simulated, so 0x0C and friends must come back
        # as an exception instead of being silently swallowed.
        s = ModbusSlave(addr=1)
        for sub in self.COUNTER_SUBS:
            resp = s.handle(modbus_master.build_rtu_request(1, 8, 0, (sub, 0)))
            self.assertIsNotNone(resp, hex(sub))
            self.assertEqual((resp[1], resp[2]),
                             (0x88, modbus_slave.EXC_ILLEGAL_VALUE), hex(sub))

    def test_multi_word_loopback_is_framed_and_echoed_verbatim(self):
        for words in ([0xAABB, 0xCCDD], [1, 2, 3], list(range(1, 21))):
            req = self.loopback(words)
            self.assertEqual(iter_frames(req), ([req], b""), words)
            # "The entire response message should be identical to the request."
            self.assertEqual(ModbusSlave(addr=1).handle(req), req, words)

    def test_multi_word_loopback_survives_every_split(self):
        frame = self.loopback([0xAABB, 0xCCDD])
        for split in range(1, len(frame)):
            first, remainder = iter_frames(frame[:split])
            second, remainder = iter_frames(remainder + frame[split:])
            self.assertEqual(first + second, [frame], split)
            self.assertEqual(remainder, b"", split)

    def test_long_loopback_does_not_swallow_the_next_frame(self):
        req = self.loopback([0xAABB, 0xCCDD])
        nxt = modbus_master.build_rtu_request(1, 3, 0, 1)
        self.assertEqual(iter_frames(req + nxt), ([req, nxt], b""))

    def test_loopback_data_must_be_whole_words(self):
        body = bytes((1, 8, 0, 0)) + b"\xAA\xBB\xCC"   # 3 data bytes, not N x 2
        frame = body + crc16(body)
        resp = ModbusSlave(addr=1).handle(frame)
        self.assertEqual((resp[1], resp[2]),
                         (0x88, modbus_slave.EXC_ILLEGAL_VALUE))

    def test_crc_collision_prefix_reads_as_the_shorter_frame(self):
        # `01 08 00 00 00 01 21 CB CC DD 95 59` is CRC-valid read as 8 bytes and
        # CRC-valid read as 12: its first data word happens to equal crc16 of the
        # six bytes before it. Nothing in the byte stream can separate the two
        # readings -- only T3.5 silence could -- so the reader takes the shorter
        # one, same as it does for every other function code. Preferring the
        # longer reading would let a 1-in-65536 CRC match merge a plain 8-byte
        # loopback with the frame behind it, trading a short echo for a request
        # lost outright.
        head = bytes((1, 8, 0, 0, 0, 1))
        self.assertEqual(crc16(head), b"\x21\xCB")          # collision armed
        long_body = head + crc16(head) + b"\xCC\xDD"
        long_frame = long_body + crc16(long_body)
        self.assertEqual(long_frame.hex(" "),
                         "01 08 00 00 00 01 21 cb cc dd 95 59")

        short = head + crc16(head)
        self.assertEqual(iter_frames(long_frame), ([short], long_frame[8:]))
        self.assertEqual(ModbusSlave(addr=1).handle(short), short)
        # The 4 orphaned bytes must not become a frame, nor eat the next one.
        nxt = modbus_master.build_rtu_request(1, 3, 0, 1)
        self.assertEqual(iter_frames(long_frame[8:]), ([], long_frame[8:]))
        self.assertEqual(iter_frames(long_frame[8:] + nxt), ([nxt], b""))

    def short_req(self, sub, unit=1):
        """Short form: sub-function code with no data field at all."""
        body = bytes((unit, 8, (sub >> 8) & 0xFF, sub & 0xFF))
        return body + crc16(body)

    def test_short_form_request_is_framed_and_answered(self):
        # Spec 6.8 does specify a 2-byte request data field, but a master that
        # omits it should still get Illegal Data Value instead of silence.
        for sub in self.COUNTER_SUBS:
            req = self.short_req(sub)
            self.assertEqual(len(req), 6, hex(sub))
            self.assertEqual(iter_frames(req), ([req], b""), hex(sub))
            resp = ModbusSlave(addr=1).handle(req)
            self.assertIsNotNone(resp, hex(sub))
            self.assertEqual((resp[1], resp[2]),
                             (0x88, modbus_slave.EXC_ILLEGAL_VALUE), hex(sub))

    def test_short_and_other_frames_coexist_in_one_buffer(self):
        short = self.short_req(0x0C)
        eight = modbus_master.build_rtu_request(1, 8, 0, (0x0C, 0x0000))
        loop = self.loopback([0xAABB, 0xCCDD])
        other = modbus_master.build_rtu_request(1, 3, 0, 1)
        for stream in ([short, eight], [eight, short], [short, short],
                       [short, other], [loop, short],
                       [short, loop, eight, other]):
            self.assertEqual(iter_frames(b"".join(stream)), (list(stream), b""),
                             [f.hex(" ") for f in stream])

    def test_short_form_survives_every_split(self):
        frame = self.short_req(0x0C)
        for split in range(1, len(frame)):
            first, remainder = iter_frames(frame[:split])
            second, remainder = iter_frames(remainder + frame[split:])
            self.assertEqual(first + second, [frame], split)
            self.assertEqual(remainder, b"", split)

    def collide_loopback(self):
        """A sub-function-0 loopback frame whose first data word equals
        crc16(header), so its first 6 bytes look like a complete short frame.
        Only the `sub != 0` exclusion keeps it from being cut in half."""
        header = bytes((1, 8, 0, 0))
        body = header + crc16(header) + b"\xCC\xDD"
        return body + crc16(body)

    def test_short_form_never_cuts_a_long_loopback(self):
        frame = self.collide_loopback()
        self.assertEqual(crc16(frame[:4]), frame[4:6])      # the trap is armed
        self.assertIsNone(modbus_slave._fc08_no_data_len(frame))
        self.assertEqual(iter_frames(frame), ([frame], b""))
        self.assertEqual(ModbusSlave(addr=1).handle(frame), frame)
        plain = self.loopback([0xAABB, 0xCCDD])
        self.assertIsNone(modbus_slave._fc08_no_data_len(plain))

    def test_resync_lands_on_a_short_form_frame(self):
        # Garbage with an unrecognised function code must not swallow the 6-byte
        # request that follows it.
        short = self.short_req(0x0C)
        for junk in (bytes((0xAA, 0x99, 0x11, 0x22, 0x33)),
                     bytes((0x7F, 0x66, 0x01)),
                     bytes((0x12, 0x5A, 0xDE, 0xAD, 0xBE, 0xEF))):
            self.assertEqual(modbus_slave.expected_len(junk + short), -1, junk)
            self.assertEqual(modbus_slave._next_complete_frame(junk + short),
                             len(junk), junk)
            self.assertEqual(iter_frames(junk + short), ([short], b""), junk)


class SlaveFromConfigTests(unittest.TestCase):
    def test_addr_is_clamped_to_the_legal_range(self):
        # A hand-edited addr:300 used to be masked to 44 and answer as slave 44.
        for raw, want in ((300, 247), (248, 247), (247, 247), (17, 17),
                          (1, 1), (0, 1), (-5, 1), ("bad", 1), (None, 1)):
            self.assertEqual(
                modbus_slave.slave_from_config({"addr": raw}).addr, want, raw)

    def test_clamped_slave_answers_on_the_clamped_address(self):
        s = modbus_slave.slave_from_config({"addr": 300, "holding": {"0": 7}})
        self.assertIsNone(s.handle(modbus_master.build_rtu_request(44, 3, 0, 1)))
        resp = s.handle(modbus_master.build_rtu_request(247, 3, 0, 1))
        self.assertEqual(modbus_master.parse_pdu(3, resp[1:-2])["regs"], [7])


if __name__ == "__main__":
    unittest.main()
