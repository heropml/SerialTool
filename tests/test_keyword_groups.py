# -*- coding: utf-8 -*-
"""Qt-free tests for keyword_groups (S-2 R13)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol import keyword_groups as kg


def test_parse_and_load_ok():
    raw = json.dumps([
        {"name": "A", "rules": [{"pattern": "x"}]},
        {"name": "B", "rules": []},
        {"name": "bad", "rules": "nope"},
        "skip",
    ])
    groups, active, ok = kg.load_groups(raw, "", "B", "Default")
    assert ok is True
    assert len(groups) == 2
    assert active == 1
    assert kg.active_rules(groups, 0) == [{"pattern": "x"}]
    assert kg.active_rules(groups, -1) == []


def test_migrate_legacy_flat_rules():
    legacy = json.dumps([{"pattern": "ERR", "enabled": True}])
    groups, active, ok = kg.load_groups("", legacy, "", "Default")
    assert ok is False
    assert groups == [{"name": "Default", "rules": [{"pattern": "ERR", "enabled": True}]}]
    assert active == -1


def test_corrupt_falls_back_to_default_empty():
    groups, active, ok = kg.load_groups("{not json", "also-bad", "X", "Default")
    assert ok is False
    assert groups == [{"name": "Default", "rules": []}]
    assert active == -1


def test_save_fields():
    groups = [{"name": "G1", "rules": []}, {"name": "G2", "rules": [{"p": 1}]}]
    payload, name = kg.save_fields(groups, 1)
    assert name == "G2"
    assert json.loads(payload) == groups
    payload, name = kg.save_fields(groups, -1)
    assert name == ""
