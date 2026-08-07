# -*- coding: utf-8 -*-
"""Send-history helpers (Qt-free): fuzzy filter for the history picker.

History itself stays in MainWindow (_send_hist FIFO); this module only
filters/display-previews so the dialog and tests stay thin.
"""


def match_hist(text, query):
    """Case-insensitive substring match; empty query matches everything."""
    q = (query or "").strip().lower()
    if not q:
        return True
    return q in (text or "").lower()


def filter_hist(items, query):
    """Return [(original_index, text), ...] preserving source indices.

    Newest-first display is the caller's job (pass a reversed view or reverse
    the result); this keeps stable index mapping back into the FIFO list.
    """
    return [(i, t) for i, t in enumerate(items) if match_hist(t, query)]


def preview_hist(text, max_len=72):
    """Single-line list label: collapse whitespace and truncate."""
    s = " ".join((text or "").split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "\u2026"
