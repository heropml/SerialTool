# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R51-R55 display/settings/conn helpers."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project import config_io as cfg
from project import connection_presets as cp
from protocol import view_format as vf
from protocol import term_vt
from ui import send_options_card as soc


def test_r51_settings_ini_and_group():
    assert cfg.settings_ini_name("") == "settings.ini"
    assert cfg.settings_ini_name("2") == "settings-2.ini"
    assert cfg.is_settings_ini_filename("settings.ini")
    assert cfg.is_settings_ini_filename("settings-probe.ini")
    assert not cfg.is_settings_ini_filename("settings.ini.lock")
    assert not cfg.is_settings_ini_filename("settings-2.ini.mwlock")
    assert cfg.clamp_group_idx("1", 3) == 1
    assert cfg.clamp_group_idx(9, 3) == 0
    assert cfg.clamp_group_idx("x", 2) == 0
    assert cfg.clamp_group_idx(0, 0) == 0


def test_r51_settings_migrate_into_config(tmp_path):
    base = tmp_path / "app"
    base.mkdir()
    (base / "settings.ini").write_text("[General]\nlanguage=zh\n", encoding="utf-8")
    (base / "settings-2.ini").write_text("[General]\n", encoding="utf-8")
    (base / "settings-probe.ini").write_text("[General]\n", encoding="utf-8")
    (base / "settings.ini.mwlock").write_text("", encoding="utf-8")
    path = cfg.resolve_settings_file("", [(str(base), [str(base)])])
    dest = base / "config"
    assert path == str(dest / "settings.ini")
    assert (dest / "settings.ini").read_text(encoding="utf-8").startswith("[General]")
    assert (dest / "settings-2.ini").is_file()
    assert (dest / "settings-probe.ini").is_file()
    assert not (base / "settings.ini").exists()
    assert not (base / "settings-2.ini").exists()
    assert not (base / "settings.ini.mwlock").exists()


def test_r51_settings_migrate_does_not_overwrite(tmp_path):
    base = tmp_path / "app"
    dest = base / "config"
    dest.mkdir(parents=True)
    (dest / "settings.ini").write_text("NEW\n", encoding="utf-8")
    (base / "settings.ini").write_text("OLD\n", encoding="utf-8")
    (base / "settings.ini.mwlock").write_text("", encoding="utf-8")
    cfg.resolve_settings_file("", [(str(base), [str(base)])])
    assert (dest / "settings.ini").read_text(encoding="utf-8") == "NEW\n"
    assert (base / "settings.ini").read_text(encoding="utf-8") == "OLD\n"
    assert (base / "settings.ini.mwlock").exists()


def test_r51_settings_migrate_copy_failure_keeps_source(tmp_path, monkeypatch):
    base = tmp_path / "app"
    base.mkdir()
    (base / "settings.ini").write_text("KEEP\n", encoding="utf-8")

    def boom(_src, _dst, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(cfg.shutil, "copy2", boom)
    cfg.resolve_settings_file("", [(str(base), [str(base)])])
    assert (base / "settings.ini").read_text(encoding="utf-8") == "KEEP\n"
    assert not (base / "config" / "settings.ini").exists()


def test_r51_settings_migrate_second_legacy_dir(tmp_path):
    """APPDATA 回退时仍要把 NetworkTool / 安装根下的旧 ini 迁进 config/。"""
    dest_parent = tmp_path / "CommTool"
    dest_parent.mkdir()
    old = tmp_path / "NetworkTool"
    old.mkdir()
    (old / "settings.ini").write_text("[General]\nfrom=nt\n", encoding="utf-8")
    path = cfg.resolve_settings_file(
        "", [(str(dest_parent), [str(dest_parent), str(old)])])
    dest = dest_parent / "config" / "settings.ini"
    assert path == str(dest)
    assert dest.read_text(encoding="utf-8") == "[General]\nfrom=nt\n"
    assert not (old / "settings.ini").exists()


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
