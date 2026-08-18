# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R24/R25 (config bool/snapshot/font/offset)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project.config_keys import PROJECT_PERSONAL_KEYS, CFG_KEYS
from project import config_io as cio


def test_settings_to_bool():
    assert cio.settings_to_bool(True) is True
    assert cio.settings_to_bool(False) is False
    assert cio.settings_to_bool("true") is True
    assert cio.settings_to_bool("YES") is True
    assert cio.settings_to_bool("1") is True
    assert cio.settings_to_bool("false") is False
    assert cio.settings_to_bool(1, default=False) is False  # int -> default
    assert cio.settings_to_bool(None, default=True) is True


def test_snapshot_excludes_personal_and_none():
    assert "theme" in PROJECT_PERSONAL_KEYS
    vals = {
        "theme": "dark",
        "language": "zh",
        "auto_update_check": True,
        "rx_hex": False,
        "send_text": "hi",
        "missing": None,
    }

    def get(k):
        return vals.get(k)

    snap = cio.snapshot_project_settings(get, keys=("theme", "rx_hex", "send_text", "nope"))
    assert snap == {"rx_hex": False, "send_text": "hi"}
    fp = cio.project_fingerprint(snap)
    assert fp == json.dumps(snap, ensure_ascii=False, sort_keys=True, default=str)
    assert "auto_update_check" in CFG_KEYS


def test_font_and_profile_offset():
    assert cio.clamp_recv_font_size(3) == 7
    assert cio.clamp_recv_font_size(99) == 28
    assert cio.clamp_recv_font_size("12") == 12
    assert cio.clamp_recv_font_size("x", default=10) == 10
    assert cio.profile_cascade_offset("1") == 40
    assert cio.profile_cascade_offset("3") == 80
    assert cio.profile_cascade_offset("99") == 40 * 8
    assert cio.profile_cascade_offset("bad") == 40
