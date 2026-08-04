# -*- coding: utf-8 -*-
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import rec_diff  # noqa: E402
import project_model  # noqa: E402


class RecDiffFilterTests(unittest.TestCase):
    def test_filter_rows_by_kind_and_direction(self):
        rows = [
            {"kind": rec_diff.SAME, "dir_a": "rx", "dir_b": "rx", "dt": 0.0,
             "bytes_a": b"A", "bytes_b": b"A"},
            {"kind": rec_diff.DIFF, "dir_a": "tx", "dir_b": "tx", "dt": 0.1,
             "bytes_a": b"B", "bytes_b": b"C"},
            {"kind": rec_diff.ONLY_A, "dir_a": "rx", "dir_b": None, "dt": None,
             "bytes_a": b"D", "bytes_b": b""},
        ]
        out = rec_diff.filter_rows(rows, kinds={rec_diff.DIFF, rec_diff.ONLY_A}, direction="rx")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["kind"], rec_diff.ONLY_A)
        out2 = rec_diff.filter_rows(rows, min_dt=0.05)
        # Unilateral rows (dt=None) must not be dropped by min_dt.
        self.assertEqual([r["kind"] for r in out2],
                         [rec_diff.DIFF, rec_diff.ONLY_A])

    def test_rows_to_jsonl(self):
        rows = [{"kind": rec_diff.DIFF, "dir_a": "tx", "dir_b": "tx",
                 "t_a": 0.1, "t_b": 0.2, "dt": 0.1,
                 "bytes_a": b"\x01", "bytes_b": b"\x02", "ia": 0, "ib": 0}]
        text = rec_diff.rows_to_jsonl(rows)
        self.assertTrue(text.endswith("\n"))
        lines = text.strip().splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        self.assertEqual(rec, {
            "kind": rec_diff.DIFF, "ia": 0, "ib": 0,
            "dir_a": "tx", "dir_b": "tx",
            "t_a": 0.1, "t_b": 0.2, "dt": 0.1,
            "bytes_a": "01", "bytes_b": "02",
        })


class ProjectPlotResourceTests(unittest.TestCase):
    def test_plot_keys_roundtrip(self):
        settings = {
            "plot_mode": 1,
            "plot_sep": 2,
            "plot_regex": "x=(\\d+)",
            "dash_mode": 0,
        }
        res = project_model.collect_project_resources(settings)
        self.assertEqual(res["plot"]["plot_mode"], 1)
        self.assertIn("plot_regex", res["plot"])
        merged = project_model.merge_project_resources({}, res)
        self.assertEqual(merged["plot_mode"], 1)
        self.assertEqual(merged["plot_regex"], "x=(\\d+)")


if __name__ == "__main__":
    unittest.main()
