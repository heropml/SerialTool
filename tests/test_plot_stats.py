# -*- coding: utf-8 -*-
"""Qt-free plot_stats helpers."""
import math
import unittest

import plot_stats


class PlotStatsTests(unittest.TestCase):
    def test_series_stats_empty(self):
        s = plot_stats.series_stats([])
        self.assertEqual(s["count"], 0)
        self.assertIsNone(s["min"])
        self.assertIsNone(s["mean"])

    def test_series_stats_basic(self):
        s = plot_stats.series_stats([1, 2, 3, 4])
        self.assertEqual(s["count"], 4)
        self.assertEqual(s["min"], 1)
        self.assertEqual(s["max"], 4)
        self.assertEqual(s["mean"], 2.5)

    def test_xy_pairs_aligns_by_shared_x(self):
        # CH0 has samples 0,1,2; CH1 skipped sample 1 (missing field) → xs [0,2]
        xs, ys = plot_stats.xy_pairs(
            [0, 1, 2], [1.0, 2.0, 3.0],
            [0, 2], [10.0, 30.0])
        self.assertEqual(xs, [1.0, 3.0])
        self.assertEqual(ys, [10.0, 30.0])

    def test_xy_pairs_truncates_without_shared_x(self):
        # No shared X → empty (cannot safely index-align)
        xs, ys = plot_stats.xy_pairs(
            [0, 1, 2], [10, 20, 30, 40],
            [10, 11], [100, 200, 300])
        self.assertEqual(xs, [])
        self.assertEqual(ys, [])

    def test_histogram_bins_flat(self):
        centers, counts = plot_stats.histogram_bins([5, 5, 5], n_bins=10)
        self.assertEqual(centers, [5.0])
        self.assertEqual(counts, [3])

    def test_histogram_bins_range(self):
        centers, counts = plot_stats.histogram_bins(
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], n_bins=5)
        self.assertEqual(len(centers), 5)
        self.assertEqual(sum(counts), 10)
        self.assertEqual(counts[0], 2)

    def test_histogram_counter(self):
        pairs = plot_stats.histogram_counter([1, 2, 1, 3, 2, 1])
        self.assertEqual(pairs, [(1.0, 3), (2.0, 2), (3.0, 1)])

    def test_series_stats_skips_nan_inf(self):
        s = plot_stats.series_stats([1.0, float("nan"), 3.0, float("inf"), -float("inf")])
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["min"], 1.0)
        self.assertEqual(s["max"], 3.0)
        self.assertEqual(s["mean"], 2.0)

    def test_xy_pairs_skips_nan(self):
        xs, ys = plot_stats.xy_pairs(
            [0, 1, 2], [1.0, float("nan"), 3.0],
            [0, 1, 2], [10.0, 20.0, 30.0])
        self.assertEqual(xs, [1.0, 3.0])
        self.assertEqual(ys, [10.0, 30.0])

    def test_histogram_bins_with_nan_does_not_crash(self):
        centers, counts = plot_stats.histogram_bins(
            [float("nan"), 1.0, 2.0, float("inf"), 3.0], n_bins=3)
        self.assertEqual(len(centers), 3)
        self.assertEqual(sum(counts), 3)

    def test_series_stats_large_finite_mean(self):
        s = plot_stats.series_stats([1e308, 1e308])
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["min"], 1e308)
        self.assertEqual(s["max"], 1e308)
        self.assertTrue(math.isfinite(s["mean"]))
        self.assertEqual(s["mean"], 1e308)

    def test_series_stats_large_opposite_values_cancel_safely(self):
        s = plot_stats.series_stats([1e308, -1e308])
        self.assertEqual(s["count"], 2)
        self.assertTrue(math.isfinite(s["mean"]))
        self.assertEqual(s["mean"], 0.0)

    def test_histogram_bar_width_extreme_range(self):
        centers, counts = plot_stats.histogram_bins([-1e308, 1e308], n_bins=20)
        width = plot_stats.histogram_bar_width(centers)
        self.assertTrue(math.isfinite(width))
        self.assertGreater(width, 0)

    def test_histogram_plot_centers_normalize_unrenderable_range(self):
        centers, _counts = plot_stats.histogram_bins([-1e308, 1e308], n_bins=20)
        plot_centers, scale = plot_stats.histogram_plot_centers(centers)

        self.assertEqual(scale, max(abs(value) for value in centers))
        self.assertTrue(all(math.isfinite(value) for value in plot_centers))
        self.assertLessEqual(max(abs(value) for value in plot_centers), 1.0)

    def test_histogram_bins_extreme_finite_range(self):
        centers, counts = plot_stats.histogram_bins([-1e308, 1e308], n_bins=20)
        self.assertEqual(len(centers), 20)
        self.assertEqual(sum(counts), 2)
        self.assertTrue(all(math.isfinite(center) for center in centers))


if __name__ == "__main__":
    unittest.main()
