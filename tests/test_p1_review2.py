import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus import modbus_master as mm
from modbus import modbus_slave
from modbus import modbus_dyn


class Review2Tests(unittest.TestCase):
    def test_fc17_timeout_budget_not_eight(self):
        self.assertEqual(mm.rtu_normal_len(0x11, 1), 256)

    def test_fc08_invalid_data_stays_none(self):
        p = mm.normalize_poll({"func": 8, "wval": "bad"})
        self.assertIsNone(p["diag_data"])
        p2 = mm.normalize_poll({"func": 8, "diag_sub": "xyz"})
        self.assertIsNone(p2["diag_sub"])
        p3 = mm.normalize_poll({"func": 8})
        self.assertEqual(p3["diag_sub"], 0)
        self.assertEqual(p3["diag_data"], 0)

    def test_dynamic_write_override_cleared_by_reset(self):
        eng = modbus_dyn.DynamicEngine([
            {"space": "holding", "addr": 0, "mode": "inc",
             "step": 1, "min": 0, "max": 100, "period_ms": 1000}],
            now=0.0)
        eng.note_write("holding", 0, 42)
        self.assertEqual(eng.value("holding", 0, now=5.0), 42)
        eng.reset(now=0.0)
        self.assertEqual(eng.rules[("holding", 0)]["mode"], "inc")
        self.assertEqual(eng.value("holding", 0, now=3.0), 3)

    def test_fc17_long_id_keeps_run_byte(self):
        sid = b"X" * 300
        s = modbus_slave.ModbusSlave(addr=1, server_id=sid)
        req = mm.build_rtu_request(1, 0x11, 0, 0)
        resp = s.handle(req)
        parsed = mm.parse_pdu(0x11, resp[1:-2])
        self.assertEqual(len(parsed["server_id"]), 250)
        self.assertTrue(parsed["run"])

    def test_bad_fc23_header_resyncs_to_next_frame(self):
        bad = bytes([1, 0x17, 0, 0, 0, 1, 0, 0, 0, 1, 250])
        good = mm.build_rtu_request(1, 0x03, 0, 1)
        frames, remainder = modbus_slave.iter_frames(bad + good)
        self.assertEqual(frames, [good])
        self.assertEqual(remainder, b"")


if __name__ == "__main__":
    unittest.main()
