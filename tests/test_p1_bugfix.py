import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import modbus_slave
import modbus_master as mm
import modbus_dyn
import rec_replay


class BroadcastAndFc23Tests(unittest.TestCase):
    def test_fc23_not_broadcastable(self):
        self.assertNotIn(0x17, modbus_slave._BROADCAST_WRITE_FUNCS)
        s = modbus_slave.ModbusSlave(addr=1, holding={0: 1})
        req = mm.build_rtu_request(0, 0x17, 0,
            {"read_addr": 0, "read_qty": 1, "write_addr": 1, "write_vals": [9]})
        self.assertIsNone(s.handle(req))
        self.assertNotIn(1, s.holding)

    def test_broadcast_write_ignores_exception_injection(self):
        s = modbus_slave.ModbusSlave(
            addr=1, holding={0: 0},
            exception_policy={"enabled": True, "code": 4, "mode": "always", "funcs": [6]})
        req = mm.build_rtu_request(0, 6, 0, 42)
        self.assertIsNone(s.handle(req))
        self.assertEqual(s.holding[0], 42)

    def test_multi_slave_inherits_top_level_exception(self):
        bank = modbus_slave.slave_bank_from_config({
            "on": True,
            "exception": {"enabled": True, "code": 4, "mode": "once", "funcs": [3]},
            "slaves": [{"addr": 1, "holding": {"0": 7}}],
        })
        req = mm.build_rtu_request(1, 3, 0, 1)
        with self.assertRaises(modbus_slave.ModbusException):
            mm.parse_pdu(3, bank.handle(req)[1:-2])

    def test_addr_filter_skips_addressless_funcs(self):
        inj = modbus_dyn.ExceptionInjector(
            {"enabled": True, "code": 4, "mode": "always", "addrs": [10]})
        self.assertIsNone(inj.should_raise(0x0B, None))
        self.assertEqual(inj.should_raise(3, 10), 4)

    def test_fc17_rejects_short_payload(self):
        with self.assertRaises(ValueError):
            mm.parse_pdu(0x11, bytes([0x11, 1, 0xFF]))


class PlayerBugfixTests(unittest.TestCase):
    def test_pause_with_now_captures_elapsed(self):
        got = []
        p = rec_replay.Player([(0.0, "rx", b"A"), (1.0, "rx", b"B")], got.append)
        p.start(0.0)
        p.tick(0.0)
        p.pause(0.4)
        p.resume(100.0)
        self.assertEqual(p.tick(100.5), 0)
        self.assertEqual(p.tick(100.6), 1)
        self.assertEqual(got, [b"A", b"B"])

    def test_seek_preserves_paused(self):
        p = rec_replay.Player([(0.0, "rx", b"A"), (1.0, "rx", b"B")], lambda b: None)
        p.start(0.0)
        p.pause(0.0)
        p.seek(1.0, 10.0)
        self.assertTrue(p.paused)
        self.assertEqual(p.tick(20.0), 0)

    def test_step_last_in_loop_resets_clock(self):
        got = []
        p = rec_replay.Player(
            [(0.0, "rx", b"A"), (1.0, "rx", b"B")], got.append, loop=True)
        p.start(0.0)
        p.step(0.0)  # A
        p.step(1.0)  # B -> loop restart at media t=0
        # Only the first event of the new loop is due; must not dump the whole loop.
        self.assertEqual(p.tick(1.0), 1)
        self.assertEqual(got, [b"A", b"B", b"A"])
        self.assertEqual(p.tick(1.5), 0)
        self.assertEqual(p.tick(2.0), 1)
        self.assertEqual(got, [b"A", b"B", b"A", b"B"])


if __name__ == "__main__":
    unittest.main()
