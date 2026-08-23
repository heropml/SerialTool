# -*- coding: utf-8 -*-
"""Qt-free tests for reusable frame/operator/recording resources."""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "src", ROOT / "scripts"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from project.operator_panels import normalize_panels, panel_from_dashboard
from protocol.frame_templates import DuplicateTemplateName, normalize_templates, remove, upsert
from record.session_catalog import MAX_CATALOG_BYTES, load_catalog, remember


def test_frame_template_upsert_replace_and_remove():
    items, template_id = upsert([], "Read status", [["num", "u8", "1", "unit"]])
    assert items[0]["id"] == template_id
    items, same_id = upsert(
        items, "Read status", [["num", "u8", "2", "unit"]], template_id)
    assert same_id == template_id
    assert normalize_templates(items)[0]["fields"][0][2] == "2"
    assert remove(items, template_id) == []


def test_frame_template_replaces_nonfinite_timestamp():
    item = normalize_templates([{
        "id": "x", "name": "Bad time", "updated": "nan",
        "fields": [["num", "u8", "1", "unit"]],
    }])[0]
    assert math.isfinite(item["updated"])
    assert normalize_templates([{"name": "bad", "fields": 1}]) == []


def test_frame_template_duplicate_name_requires_explicit_overwrite():
    items, first_id = upsert([], "A", [["num", "u8", "1", "unit"]])
    items, second_id = upsert(items, "B", [["num", "u8", "2", "unit"]])
    items.append({
        "id": "legacy-duplicate", "name": "B", "updated": 1,
        "fields": [["num", "u8", "9", "unit"]],
    })

    try:
        upsert(items, "B", [["num", "u8", "3", "unit"]], first_id)
    except DuplicateTemplateName as exc:
        assert exc.template_id == second_id
    else:
        raise AssertionError("duplicate template name must require confirmation")

    replaced, active_id = upsert(
        items, "B", [["num", "u8", "3", "unit"]], first_id,
        replace_name_conflict=True)
    assert active_id == first_id
    assert [(item["id"], item["name"]) for item in replaced] == [(first_id, "B")]


def test_operator_panel_normalization_uses_dashboard_config():
    panel = panel_from_dashboard({"dash_mode": 2, "dash_fields": "x=0:u16be"})
    panels = normalize_panels([panel, {"name": "", "dashboard": {}}])
    assert len(panels) == 1
    assert panels[0]["dashboard"]["dash_fields"] == "x=0:u16be"
    assert panel_from_dashboard(None)["dashboard"] == {}
    panel = normalize_panels([{"name": "bad actions", "actions": 1}])[0]
    assert panel["actions"] == []


def test_recording_catalog_remembers_metadata_without_payload(tmp_path):
    recording = tmp_path / "capture.ctrec"
    recording.write_text(
        json.dumps({"_": "ctrec", "v": 1, "created": "2026-08-23",
                    "note": "bench", "link": {"proto": "Virtual"}}) + "\n" +
        json.dumps({"t": 0.0, "d": "rx", "b": "53 45 43 52 45 54"}) + "\n",
        encoding="utf-8")
    catalog = tmp_path / "session-catalog.json"
    remember(catalog, recording)
    items = load_catalog(catalog)
    assert items[0]["proto"] == "Virtual"
    raw = catalog.read_text(encoding="utf-8")
    assert "53 45 43 52 45 54" not in raw


def test_recording_catalog_sanitizes_corrupt_metadata(tmp_path):
    recording = tmp_path / "capture.ctrec"
    recording.write_text(
        json.dumps({"_": "ctrec", "v": 1}) + "\n", encoding="utf-8")
    catalog = tmp_path / "session-catalog.json"
    catalog.write_text(json.dumps({
        "version": 1,
        "items": [{
            "path": str(recording),
            "name": ["not", "text"],
            "proto": {"not": "text"},
            "modified": "nan",
        }],
    }), encoding="utf-8")

    item = load_catalog(catalog)[0]
    assert item["name"] == recording.name
    assert item["proto"] == ""
    assert isinstance(item["modified"], float)


def test_recording_catalog_rejects_boolean_format_version(tmp_path):
    catalog = tmp_path / "session-catalog.json"
    catalog.write_text(json.dumps({"version": True, "items": []}), encoding="utf-8")
    assert load_catalog(catalog) == []
    catalog.write_text(json.dumps({"version": 1, "items": 1}), encoding="utf-8")
    assert load_catalog(catalog) == []


def test_recording_catalog_rejects_oversized_index(tmp_path):
    catalog = tmp_path / "session-catalog.json"
    with catalog.open("wb") as stream:
        stream.seek(MAX_CATALOG_BYTES)
        stream.write(b"x")
    assert load_catalog(catalog) == []
