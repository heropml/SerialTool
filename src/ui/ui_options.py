# -*- coding: utf-8 -*-
"""UI combo catalogs for CommTool settings cards (Qt-free).

S-2 R34: shared by build_data_options_card / build_send_options_card /
_apply_language so first fill and i18n refill stay in sync.
"""
from project.config_io import TS_FORMATS
from protocol.view_format import HEXDUMP_WIDTHS

# (i18n_key, combo userData)
VIEW_MODE_ITEMS = (
    ("view_text", "text"),
    ("view_hex", "hex"),
    ("view_dump", "dump"),
    ("view_num", "num"),
)

ENCODING_CODECS = (
    "UTF-8", "GBK", "GB2312", "GB18030", "Big5", "ASCII", "Latin-1",
)

# (type, endian); empty endian => 8-bit label without LE/BE suffix
NUMVIEW_TYPE_OPTIONS = (
    ("u8", ""), ("i8", ""),
    ("u16", "le"), ("u16", "be"), ("i16", "le"), ("i16", "be"),
    ("u32", "le"), ("u32", "be"), ("i32", "le"), ("i32", "be"),
    ("f32", "le"), ("f32", "be"),
)

HEXDUMP_WIDTH_OPTIONS = tuple(str(w) for w in HEXDUMP_WIDTHS)

# (combo data, i18n_key); order follows config_io.TS_FORMATS
TS_FORMAT_ITEMS = tuple((fmt, "ts_fmt_%s" % fmt) for fmt in TS_FORMATS)

LOG_SPLIT_SIZES = ("1M", "2M", "5M", "10M", "20M", "50M", "100M")

# Fixed combo texts after the translated "nl_auto" item
LINE_NL_FIXED = ("CRLF", "LF", "CR")
APPEND_NL_OPTIONS = ("CRLF", "LF", "CR")
# Terminal Enter order differs historically (CR first)
TERM_ENTER_OPTIONS = ("CR", "LF", "CRLF")

# (combo data, i18n_key)
SEARCH_MODE_ITEMS = (
    ("plain", "search_mode_plain"),
    ("regex", "search_mode_regex"),
    ("hex", "search_mode_hex"),
)


def numview_item_label(typ, endian=""):
    """Combo display text: 'u8' or 'u16 LE'."""
    typ = typ or ""
    endian = endian or ""
    return typ if not endian else "%s %s" % (typ, endian.upper())


def numview_item_data(typ, endian=""):
    """Combo userData: (type, endian) with empty endian stored as 'le'."""
    return (typ or "", endian or "le")
