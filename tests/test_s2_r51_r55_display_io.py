# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R51-R55 display/settings/conn helpers."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config_io as cfg
import connection_presets as cp
import view_format as vf
import term_vt
import send_options_card as soc


def test_r51_settings_ini_and_group():
    assert cfg.settings_ini_name("") == "settings.ini"
    assert cfg.settings_ini_name("2") == "settings-2.ini"
    assert cfg.clamp_group_idx("1", 3) == 1
    assert cfg.clamp_group_idx(9, 3) == 0
    assert cfg.clamp_group_idx("x", 2) == 0
    assert cfg.clamp_group_idx(0, 0) == 0


def test_r51_mbm_gates():
    assert cfg.normalize_mbm_variant("rtu") == "rtu"
    assert cfg.normalize_mbm_variant("nope") == ""
    assert cfg.mbm_import_enabled(True, is_open=False) is True
    assert cfg.mbm_import_enabled(True, is_open=True) is False
    assert cfg.ar_mbm_mutex_disable_ar(True, True) is True
    assert cfg.ar_mbm_mutex_disable_ar(True, False) is False


def test_r52_term_section():
    assert soc.term_section_expanded(False, True) is True
    assert soc.term_section_expanded(True, False) is True
    assert soc.term_section_expanded(False, False) is False


def test_r53_view_format_block_helpers():
    assert vf.recv_view_prop(True, False, False) == vf.VIEW_HEXDUMP
    assert vf.recv_view_prop(False, True, True) == vf.VIEW_NUMERIC
    assert vf.recv_view_prop(False, False, True) == vf.VIEW_HEX
    assert vf.recv_view_prop(False, False, False) == vf.VIEW_TEXT

    idle = vf.force_block_prefix_plan(
        force_new_block=False, ends_with_nl=False, show_timestamp=True)
    assert idle == {"need_leading_nl": False, "want_ts": False}
    plan = vf.force_block_prefix_plan(
        force_new_block=True, ends_with_nl=False, show_timestamp=True)
    assert plan["need_leading_nl"] is True and plan["want_ts"] is True

    pieces, ends = vf.log_block_pieces(
        text="hi\n", force_new_block=True, log_ends_with_nl=False,
        prefix="[ts] ", show_timestamp=True)
    assert pieces[0] == "\n" and pieces[1] == "[ts] " and pieces[2] == "hi\n"
    assert ends is True

    assert vf.offsets_after_trim(10, 25, 40) == (15, 30)
    assert vf.offsets_after_trim(100, 5) == (0,)


def test_r54_open_fields_and_serial_extras():
    assert cp.open_fields_from_ui("Serial", {"port": "COM3", "baud": "115200"}) == {
        "port": "COM3", "baud": "115200"}
    assert cp.open_fields_from_ui("Virtual", {}) == {}
    assert cp.open_fields_from_ui("TCP Client", {
        "remote_ip": "1.2.3.4", "remote_port": "80"}) == {
        "remote_ip": "1.2.3.4", "remote_port": "80"}
    proto, fields = cp.open_fields_from_reconnect(
        ("Serial", "COM1", "9600", "8", "None", "1", "none"))
    assert proto == "Serial" and fields["port"] == "COM1"
    extras = cp.serial_extras_from_reconnect(
        ("Serial", "COM1", "9600", "8", "None", "1"))
    assert extras == ("8", "None", "1", None)
    assert cp.serial_extras_from_reconnect(("Serial", "COM1")) is None


def test_r55_term_vt():
    st = term_vt.resolve_stream_state(
        {}, None, global_sgr="G", global_esc="\x1b[",
        global_discard_csi=True, global_discard_osc=False,
        global_osc_prev_esc=True)
    assert st["use_global"] and st["esc"] == "\x1b[" and st["discard_csi"]
    st2 = term_vt.resolve_stream_state(
        {"peer": {"sgr": "P", "esc": "x"}}, "peer",
        global_sgr="G", global_esc="", global_discard_csi=False,
        global_discard_osc=False, global_osc_prev_esc=False)
    assert not st2["use_global"] and st2["sgr"] == "P"
    out = term_vt.store_stream_state(
        {}, "peer", sgr=1, esc="", discard_csi=False,
        discard_osc=True, osc_prev_esc=False)
    assert out["peer"]["discard_osc"] is True
    assert term_vt.term_pos_after_trim(50, 10, 100) == 40
    assert term_vt.term_pos_after_trim(50, 60, 100) == 0
    assert term_vt.term_pos_after_trim(200, 0, 50) == 50
    bg, fg = term_vt.tooltip_colors("dark")
    assert bg == "#F2F2F7" and fg == "#1C1C1E"
