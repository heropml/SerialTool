# -*- coding: utf-8 -*-
"""Recv/TX view formatters (Qt-free).

S-2 slice: HEX string and hexdump layout live here so tests and a future
headless renderer do not need CommTool.
"""
HEXDUMP_WIDTHS = (8, 16, 32, 64)


def bytes_to_hex(data):
    """Bytes -> 'AA BB CC' (no trailing space)."""
    return bytes(data or b"").hex(" ").upper()


def format_hexdump(data, per=16):
    """Bytes -> classic hexdump lines: offset + HEX (split halves) + |ASCII|.

    per must be 8/16/32/64 (else 16). Empty input -> ''.
    Lines are newline-joined without a trailing newline.
    """
    data = bytes(data or b"")
    per = per if per in HEXDUMP_WIDTHS else 16
    half = per // 2
    hex_w = per * 3
    lines = []
    for off in range(0, len(data), per):
        chunk = data[off: off + per]
        hexs = ["%02X" % b for b in chunk]
        hex_col = (" ".join(hexs[:half]) + "  " + " ".join(hexs[half:])).ljust(hex_w)
        ascii_col = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append("%08X  %s |%s|" % (off, hex_col, ascii_col))
    return "\n".join(lines)


def with_leading_newline(text, enabled):
    """Prefix a multi-line view block with \\n when timestamp/arrow headers are on."""
    if text and enabled:
        return "\n" + text
    return text or ""


# Direction arrows (U+2192 RIGHTWARDS, U+2190 LEFTWARDS)
ARROW_TX = "\u2192 "
ARROW_RX = "\u2190 "


def timestamp_prefix(fmt, direction, *, now=None, wall_time=None, anchor=None):
    """Build '[ts] arrow' block prefix for RX/TX view.

    fmt: absolute | time | epoch | relative (else absolute)
    direction: 'tx' uses ARROW_TX, else ARROW_RX
    now: datetime for absolute/time (required for those formats)
    wall_time: float seconds for epoch/relative
    anchor: relative-mode start; None -> set to wall_time on first call

    Returns (text, new_anchor). new_anchor only changes in relative mode.
    """
    arrow = ARROW_TX if direction == "tx" else ARROW_RX
    if fmt == "time":
        ts = "%02d:%02d:%02d.%03d" % (
            now.hour, now.minute, now.second, now.microsecond // 1000)
    elif fmt == "epoch":
        ts = "%.3f" % wall_time
    elif fmt == "relative":
        if anchor is None:
            anchor = wall_time
        ts = "+%.3f" % (wall_time - anchor)
    else:  # absolute
        ts = ("%04d/%02d/%02d %02d:%02d:%02d.%03d"
              % (now.year, now.month, now.day, now.hour, now.minute,
                 now.second, now.microsecond // 1000))
    return "[%s] %s" % (ts, arrow), anchor


def view_mode_of_state(hexdump_on, numview_on, rx_hex):
    """Map view toggles -> mode id used by the view-mode combo.

    Priority matches receive path: dump > num > hex > text.
    """
    if hexdump_on:
        return "dump"
    if numview_on:
        return "num"
    return "hex" if rx_hex else "text"


def view_extra_index(mode, terminal_on=False):
    """Stacked widget page for mode extras; terminal forces text page (0)."""
    if terminal_on:
        return 0
    return {"text": 0, "hex": 1, "dump": 2, "num": 3}.get(mode, 0)
