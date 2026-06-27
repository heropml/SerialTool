import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus_slave import ModbusSlave, crc16, iter_frames  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
