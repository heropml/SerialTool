# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R34 ui_options catalogs."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config_io as cio
import ui_options as uo
import view_format as vf


def test_view_mode_unique_ids():
    keys = [k for k, _ in uo.VIEW_MODE_ITEMS]
    datas = [d for _, d in uo.VIEW_MODE_ITEMS]
    assert keys == ["view_text", "view_hex", "view_dump", "view_num"]
    assert datas == ["text", "hex", "dump", "num"]
    assert len(set(datas)) == 4


def test_hexdump_widths_follow_view_format():
    assert uo.HEXDUMP_WIDTH_OPTIONS == tuple(str(w) for w in vf.HEXDUMP_WIDTHS)
    assert "16" in uo.HEXDUMP_WIDTH_OPTIONS


def test_ts_format_items_match_config_io():
    assert [d for d, _ in uo.TS_FORMAT_ITEMS] == list(cio.TS_FORMATS)
    assert all(k.startswith("ts_fmt_") for _, k in uo.TS_FORMAT_ITEMS)


def test_numview_label_and_data():
    assert uo.numview_item_label("u8", "") == "u8"
    assert uo.numview_item_label("u16", "le") == "u16 LE"
    assert uo.numview_item_data("u8", "") == ("u8", "le")
    assert uo.numview_item_data("i32", "be") == ("i32", "be")
    assert len(uo.NUMVIEW_TYPE_OPTIONS) == 12


def test_nl_and_search_catalogs():
    assert uo.LINE_NL_FIXED == ("CRLF", "LF", "CR")
    assert uo.APPEND_NL_OPTIONS == ("CRLF", "LF", "CR")
    assert uo.TERM_ENTER_OPTIONS == ("CR", "LF", "CRLF")
    assert uo.TERM_ENTER_OPTIONS != uo.APPEND_NL_OPTIONS  # intentional order
    assert [d for d, _ in uo.SEARCH_MODE_ITEMS] == ["plain", "regex", "hex"]
    assert "UTF-8" in uo.ENCODING_CODECS and "GBK" in uo.ENCODING_CODECS
    assert uo.LOG_SPLIT_SIZES[0] == "1M" and uo.LOG_SPLIT_SIZES[-1] == "100M"
