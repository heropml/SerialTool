# -*- coding: utf-8 -*-
"""Qt-free helpers for plot cursor stats, XY pairing, and histograms."""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, List, Optional, Sequence, Tuple


def _finite_floats(values: Optional[Iterable]) -> List[float]:
    """Coerce to float and drop non-finite / non-numeric samples."""
    out: List[float] = []
    for y in values or ():
        try:
            v = float(y)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            out.append(v)
    return out


def series_stats(ys: Optional[Iterable]) -> dict:
    """Return count / min / max / mean / std for a numeric series (empty-safe).

    NaN / ±inf and non-numeric values are skipped.
    Mean and variance are accumulated in a normalized range so large finite
    samples do not overflow, even when positive and negative values cancel
    each other. ``std`` is the population standard deviation (σ, ÷n) to match
    rtt_t2-style wave viewers.
    """
    vals = _finite_floats(ys)
    if not vals:
        return {"count": 0, "min": None, "max": None, "mean": None, "std": None}
    scale = max(abs(v) for v in vals)
    if scale == 0.0:
        mean = 0.0
        std = 0.0
    else:
        scaled = [v / scale for v in vals]
        mean_scaled = math.fsum(scaled) / len(vals)
        mean = max(-1.0, min(1.0, mean_scaled)) * scale
        var_scaled = math.fsum(
            (v - mean_scaled) * (v - mean_scaled) for v in scaled) / len(vals)
        # 在归一化域开方后再放大：var_scaled * scale² 会先于开方溢出
        std = math.sqrt(var_scaled) * scale
    return {
        "count": len(vals),
        "min": min(vals),
        "max": max(vals),
        "mean": mean,
        "std": std,
    }


def xy_pairs(xs0, ys0, xs1, ys1) -> Tuple[List[float], List[float]]:
    """Align two channels by shared X sample index/time, then plot y0 vs y1.

    Channels may omit a sample when a field is missing (``_append_vals`` skips
    non-numeric cells). Joining on ``xs`` keeps ``(1,10)→(3,30)`` instead of
    wrongly pairing by array index as ``(2,30)``.
    Non-finite coordinates are dropped.
    """
    def _by_x(xs, ys):
        out = {}
        for x, y in zip(xs or (), ys or ()):
            try:
                xf, yf = float(x), float(y)
            except (TypeError, ValueError):
                continue
            if math.isfinite(xf) and math.isfinite(yf):
                out[xf] = yf
        return out

    m0, m1 = _by_x(xs0, ys0), _by_x(xs1, ys1)
    out_x: List[float] = []
    out_y: List[float] = []
    for x in sorted(set(m0) & set(m1)):
        out_x.append(m0[x])
        out_y.append(m1[x])
    return out_x, out_y


def histogram_bins(
    ys: Optional[Sequence],
    n_bins: int = 20,
) -> Tuple[List[float], List[int]]:
    """Build fixed-width histogram bins (numpy-free).

    Returns (centers, counts). Degenerate / empty / non-finite series handled safely.
    """
    vals = _finite_floats(ys)
    if not vals:
        return [], []
    n_bins = max(1, int(n_bins or 1))
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return [lo], [len(vals)]
    # Work in a normalized range so two finite endpoints whose subtraction
    # overflows (for example -1e308 and 1e308) still form valid bins.
    scale = max(abs(lo), abs(hi))
    lo_scaled = lo / scale
    width = ((hi / scale) - lo_scaled) / float(n_bins)
    counts = [0] * n_bins
    centers = [(lo_scaled + (i + 0.5) * width) * scale
               for i in range(n_bins)]
    for v in vals:
        idx = int(((v / scale) - lo_scaled) / width)
        if idx >= n_bins:
            idx = n_bins - 1
        elif idx < 0:
            idx = 0
        counts[idx] += 1
    return centers, counts


def histogram_bar_width(centers: Sequence[float]) -> float:
    """Bar width for ``BarGraphItem`` without overflowing extreme finite spans.

    ``(centers[-1] - centers[0]) / (n-1)`` overflows for ``[-1e308, 1e308]``.
    Scale first, then re-multiply so the result stays finite when possible.
    """
    if not centers:
        return 1.0
    if len(centers) == 1:
        c0 = float(centers[0])
        if not math.isfinite(c0) or c0 == 0.0:
            return 1.0
        w = abs(c0) * 0.05
        return w if math.isfinite(w) and w > 0 else 1.0
    scale = max(abs(float(c)) for c in centers) or 1.0
    if not math.isfinite(scale) or scale == 0.0:
        return 1.0
    span_scaled = float(centers[-1]) / scale - float(centers[0]) / scale
    width = (span_scaled / float(len(centers) - 1)) * scale * 0.8
    if not math.isfinite(width) or width <= 0:
        return 1.0
    return width


def histogram_plot_centers(centers: Sequence[float]) -> Tuple[List[float], Optional[float]]:
    """Return drawable histogram centers and, when necessary, their scale.

    ``BarGraphItem`` derives its bounding rectangle from the first and last
    bar edges.  Finite IEEE-754 values can still produce a non-finite span
    there (for example ``-1e308`` through ``1e308``).  Normalize only such
    unrenderable ranges; the caller can retain original-units labels with the
    returned scale.
    """
    values = [float(value) for value in centers]
    if not values:
        return [], None

    width = histogram_bar_width(values)
    left = values[0] - width / 2.0
    right = values[-1] + width / 2.0
    if math.isfinite(left) and math.isfinite(right) and math.isfinite(right - left):
        return values, None

    scale = max(abs(value) for value in values)
    if not math.isfinite(scale) or scale == 0.0:
        return values, None
    return [value / scale for value in values], scale


def histogram_counter(ys: Optional[Iterable]) -> List[Tuple[float, int]]:
    """Discrete-value histogram via Counter; returns sorted [(value, count), ...]."""
    c: Counter = Counter()
    for v in _finite_floats(ys):
        c[v] += 1
    return sorted(c.items())
