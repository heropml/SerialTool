import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
        self.assert_all_splits(request("01 08 00 00 12 34"))

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
        frame = request("01 08 00 00 12 34")
        frames, remainder = iter_frames(frame)
        self.assertEqual(remainder, b"")
        self.assertEqual(slave.handle(frames[0]), request("01 88 01"))

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


if __name__ == "__main__":
    unittest.main()
