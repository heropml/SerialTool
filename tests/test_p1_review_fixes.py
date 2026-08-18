import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus import modbus_dyn
from modbus import modbus_slave
from record import rec_replay
from transport import io_stats


class ReviewFixTests(unittest.TestCase):
    def test_hits_not_inflated_in_always_mode(self):
        inj = modbus_dyn.ExceptionInjector(
            {"enabled": True, "code": 4, "mode": "always", "funcs": [3]})
        for _ in range(5):
            self.assertEqual(inj.should_raise(3, 0), 4)
        self.assertEqual(inj.policy.get("_hits", 0), 0)
        inj.policy["mode"] = "once"
        self.assertEqual(inj.should_raise(3, 0), 4)
        self.assertIsNone(inj.should_raise(3, 0))

    def test_io_stats_session_anchor_is_stable(self):
        """会话锚点只能在 reset 时动；被 tick 重写的话，
        history 里的 wall_t 会随重写而跳变。"""
        acc = io_stats.IoStatsAccumulator()
        acc.session_t0_mono = 100.0
        acc.session_t0_wall = 1_700_000_000.0
        acc.note_rx(4)
        acc.tick(now=101.0)
        acc.note_rx(4)
        acc.tick(now=102.0)
        self.assertEqual(acc.session_t0_mono, 100.0)
        self.assertEqual(acc.session_t0_wall, 1_700_000_000.0)
        self.assertEqual([h["wall_t"] for h in acc.history],
                         [1_700_000_001.0, 1_700_000_002.0])
        acc.reset()
        self.assertNotEqual(acc.session_t0_mono, 100.0)

    def test_pause_captures_elapsed_on_monotonic_clock(self):
        import time
        got = []
        p = rec_replay.Player([(0.0, "rx", b"A"), (1.0, "rx", b"B")], got.append)
        now = time.monotonic()
        p.start(now)
        p.tick(now)
        p.pause(now + 0.4)
        self.assertAlmostEqual(p._pause_elapsed, 0.4, places=6)
        p.resume(now + 100.0)
        self.assertEqual(p.tick(now + 100.5), 0)
        self.assertEqual(p.tick(now + 100.7), 1)

    def test_step_finished_does_not_rewrite_clock(self):
        p = rec_replay.Player([(0.0, "rx", b"A")], lambda b: None)
        p.start(0.0)
        p.step(1.0)
        self.assertTrue(p.finished)
        started = p.started_at
        elapsed = p._pause_elapsed
        self.assertEqual(p.step(9.0), 0)
        self.assertEqual(p.started_at, started)
        self.assertEqual(p._pause_elapsed, elapsed)

    def test_unknown_func_noise_resyncs(self):
        # Unsupported FC 0x63 garbage then a valid read request.
        good = bytes.fromhex("010300000001")
        good = good + modbus_slave.crc16(good)
        junk = bytes([0x01, 0x63, 0x00, 0x01, 0x02, 0x03])  # no valid CRC prefix
        frames, rem = modbus_slave.iter_frames(junk + good)
        self.assertEqual(frames, [good])
        self.assertEqual(rem, b"")


if __name__ == "__main__":
    unittest.main()
