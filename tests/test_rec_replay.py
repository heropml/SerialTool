import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from record import rec_replay  # noqa: E402


class RecordingFormatTests(unittest.TestCase):
    def test_boolean_version_is_not_accepted_as_version_one(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.ctrec"
            path.write_text(
                json.dumps({"_": "ctrec", "v": True}) + "\n",
                encoding="utf-8")
            with self.assertRaises(rec_replay.RecordError):
                rec_replay.load(path)


class PlayerControlTests(unittest.TestCase):
    def setUp(self):
        self.events = [(0.0, "rx", b"A"), (1.0, "rx", b"B"), (2.0, "rx", b"C")]
        self.got = []
        self.player = rec_replay.Player(self.events, self.got.append)
        self.player.start(0.0)

    def test_pause_freezes_elapsed_time_until_resume(self):
        self.assertEqual(self.player.tick(0.0), 1)
        self.player.tick(0.4)
        self.player.pause(0.4)
        self.assertTrue(self.player.paused)
        self.assertEqual(self.player.tick(100.0), 0)
        self.player.resume(100.0)
        self.assertFalse(self.player.paused)
        self.assertEqual(self.player.tick(100.5), 0)
        self.assertEqual(self.player.tick(100.6), 1)
        self.assertEqual(self.got, [b"A", b"B"])

    def test_step_emits_one_event_without_catching_up(self):
        self.player.pause(0.0)
        self.assertEqual(self.player.step(10.0), 1)
        self.assertEqual(self.got, [b"A"])
        self.assertEqual(self.player.tick(10.0), 0)
        self.player.resume(10.0)
        self.assertEqual(self.player.tick(10.5), 0)
        self.assertEqual(self.player.tick(11.0), 1)
        self.assertEqual(self.got, [b"A", b"B"])

    def test_seek_positions_next_event_and_resets_clock(self):
        self.assertEqual(self.player.seek(1.0, 50.0), 1.0)
        self.assertEqual(self.player.position, 1.0)
        self.assertEqual(self.player.tick(50.0), 1)
        self.assertEqual(self.got, [b"B"])
        self.assertEqual(self.player.position, 2.0)
        self.assertEqual(self.player.seek(99.0, 60.0), 2.0)
        self.assertTrue(self.player.finished)
        self.assertEqual(self.player.position, 2.0)

    def test_position_is_duration_when_finished(self):
        self.player.tick(2.0)
        self.assertTrue(self.player.finished)
        self.assertEqual(self.player.position, self.player.duration)


if __name__ == "__main__":
    unittest.main()
