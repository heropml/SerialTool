import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus import modbus_master as mm
from modbus import modbus_slave
from modbus import modbus_dyn
from record import rec_diff


class Review3Tests(unittest.TestCase):
    def test_fc23_write_addr_top_level_roundtrip(self):
        p = mm.normalize_poll({
            "func": 0x17, "addr": 0, "qty": 1,
            "write_addr": 10, "wvals": [1, 2]})
        self.assertEqual(p["write_addr"], 10)
        self.assertEqual(p["rw"]["write_addr"], 10)
        # Old saved shape: only nested rw
        p2 = mm.normalize_poll({
            "func": 0x17, "addr": 0, "qty": 1,
            "rw": {"write_addr": 10, "write_vals": [1]},
            "wvals": [1]})
        self.assertEqual(p2["write_addr"], 10)

    def test_dyn_min_equals_max_stays_in_range(self):
        eng = modbus_dyn.DynamicEngine([
            {"space": "holding", "addr": 0, "mode": "inc",
             "step": 1, "min": 10, "max": 10, "period_ms": 100}],
            now=0.0)
        for t in (0.0, 0.5, 1.0, 5.0):
            self.assertEqual(eng.value("holding", 0, now=t), 10)
        eng2 = modbus_dyn.DynamicEngine([
            {"space": "holding", "addr": 1, "mode": "sine",
             "min": 7, "max": 7, "period_ms": 1000}],
            now=0.0)
        self.assertEqual(eng2.value("holding", 1, now=0.25), 7)

    def test_empty_slaves_falls_back_to_top_level(self):
        bank = modbus_slave.slave_bank_from_config({
            "on": True, "addr": 3, "holding": {"0": 9}, "slaves": []})
        self.assertIn(3, bank.slaves)
        self.assertEqual(bank.slaves[3].holding.get(0), 9)

    def test_min_dt_keeps_unilateral_rows(self):
        rows = [
            {"kind": rec_diff.DIFF, "dt": 0.01},
            {"kind": rec_diff.ONLY_A, "dt": None},
            {"kind": rec_diff.ONLY_B, "dt": None},
            {"kind": rec_diff.DIFF, "dt": 0.2},
        ]
        out = rec_diff.filter_rows(rows, min_dt=0.05)
        self.assertEqual([r["kind"] for r in out],
                         [rec_diff.ONLY_A, rec_diff.ONLY_B, rec_diff.DIFF])


if __name__ == "__main__":
    unittest.main()
