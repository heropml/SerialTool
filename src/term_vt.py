# -*- coding: utf-8 -*-
"""Terminal stream-state helpers (Qt-free). S-2 R55."""
from __future__ import annotations


def resolve_stream_state(streams, source, *, global_sgr, global_esc,
                         global_discard_csi, global_discard_osc, global_osc_prev_esc):
    """Pick per-peer or global terminal parser state.

    Returns dict: sgr, esc, discard_csi, discard_osc, osc_prev_esc, use_global.
    """
    if source is None:
        return {
            "sgr": global_sgr,
            "esc": global_esc or "",
            "discard_csi": bool(global_discard_csi),
            "discard_osc": bool(global_discard_osc),
            "osc_prev_esc": bool(global_osc_prev_esc),
            "use_global": True,
        }
    stream = (streams or {}).get(source, {}) or {}
    return {
        "sgr": stream.get("sgr"),
        "esc": stream.get("esc", "") or "",
        "discard_csi": bool(stream.get("discard_csi", False)),
        "discard_osc": bool(stream.get("discard_osc", False)),
        "osc_prev_esc": bool(stream.get("osc_prev_esc", False)),
        "use_global": False,
    }


def store_stream_state(streams, source, *, sgr, esc, discard_csi, discard_osc,
                       osc_prev_esc):
    """Write per-peer stream state into streams dict; return streams."""
    out = streams if isinstance(streams, dict) else {}
    out[source] = {
        "sgr": sgr,
        "esc": esc or "",
        "discard_csi": bool(discard_csi),
        "discard_osc": bool(discard_osc),
        "osc_prev_esc": bool(osc_prev_esc),
    }
    return out


def term_pos_after_trim(pos, trimmed, last_char_index):
    """Adjust terminal cursor after document trim; clamp into [0, last]."""
    if pos is None:
        return None
    try:
        p = max(0, int(pos) - max(0, int(trimmed or 0)))
        last = max(0, int(last_char_index))
    except (TypeError, ValueError):
        return None
    return p if p <= last else last


def tooltip_colors(mode):
    """Return (tooltip_bg, tooltip_fg) for theme mode (matches CommTool QSS)."""
    if mode == "dark":
        return "#F2F2F7", "#1C1C1E"
    return "#1C1C1E", "#FFFFFF"
