# -*- coding: utf-8 -*-
"""Receive-path text helpers (Qt-free).

S-2 slice: Auto decode, newline splitting, and ANSI span geometry live here so
tests and a future headless renderer do not need CommTool.
"""
import re


def decode_auto_chunk(buf, data):
    """Incremental Auto decode: UTF-8 first, keep a partial trailing char,
    fall back to GBK on real garbage.

    Returns (text, new_buf).
    """
    buf = (buf or b"") + (data or b"")
    if not buf:
        return "", b""
    try:
        return buf.decode("utf-8"), b""
    except UnicodeDecodeError as e:
        if e.end == len(buf) and "unexpected end of data" in str(e.reason):
            try:
                return buf[: e.start].decode("utf-8"), buf[e.start :]
            except UnicodeDecodeError:
                pass
        return buf.decode("gbk", errors="replace"), b""


def split_lines_with_offsets(text, nl_mode):
    """Split text by newline mode; return (segments, start_offsets).

    nl_mode: 1=CRLF, 2=LF, 3=CR, else Auto (CRLF|CR|LF).
    Equivalent to normalizing then split, but keeps original offsets for ANSI.
    """
    text = text or ""
    sep = {1: r"\r\n", 2: r"\n", 3: r"\r"}.get(nl_mode, r"\r\n|\r|\n")
    segs, starts, pos = [], [], 0
    for m in re.finditer(sep, text):
        segs.append(text[pos : m.start()])
        starts.append(pos)
        pos = m.end()
    segs.append(text[pos:])
    starts.append(pos)
    return segs, starts


def ansi_flatten(runs):
    """ansi.parse runs -> (plain_text, [(start, end, style), ...]).

    Default-styled segments are omitted from spans so plain text stays on the
    fast whole-insert path.
    """
    parts, spans, pos = [], [], 0
    for seg, st in runs or ():
        if not seg:
            continue
        parts.append(seg)
        if not st.is_default():
            spans.append((pos, pos + len(seg), st))
        pos += len(seg)
    return "".join(parts), spans


def ansi_shift(spans, delta, limit):
    """Shift style spans by delta and clip to [0, limit)."""
    if not spans:
        return spans
    out = []
    for s, e, st in spans:
        s2, e2 = max(0, s + delta), min(limit, e + delta)
        if s2 < e2:
            out.append((s2, e2, st))
    return out


def ansi_slice(spans, start, end):
    """Keep spans overlapping [start, end); rebase to line-relative offsets.

    Returns [(rel_off, length, style), ...].
    """
    out = []
    for s, e, st in spans or ():
        a, b = max(s, start), min(e, end)
        if a < b:
            out.append((a - start, b - a, st))
    return out
