# -*- coding: utf-8 -*-
"""Send-history helpers (Qt-free).

Filter/preview for the history picker; FIFO push/load for persistence.
"""
import json

HIST_CAP = 100


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


def sanitize_list(items, cap=HIST_CAP):
    """Coerce to str list and keep the newest `cap` entries."""
    return [str(x) for x in (items or [])][-cap:]


def load_list(raw, cap=HIST_CAP):
    """Parse send_history JSON; missing/invalid/non-list -> None."""
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except Exception:
        return None
    if not isinstance(v, list):
        return None
    return sanitize_list(v, cap)


def push(hist, text, cap=HIST_CAP):
    """Append after rstrip; adjacent-dedupe; cap FIFO.

    Returns (new_hist, changed). changed=False when empty or adjacent duplicate
    (caller still resets navigation state on duplicate).
    """
    text = (text or "").rstrip("\r\n")
    if not text:
        return list(hist or []), False
    out = list(hist or [])
    if out and out[-1] == text:
        return out, False
    out.append(text)
    if len(out) > cap:
        out = out[-cap:]
    return out, True


def dumps(hist):
    """Serialize FIFO for QSettings."""
    return json.dumps(list(hist or []), ensure_ascii=False)
