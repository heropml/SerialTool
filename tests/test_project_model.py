import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from project.project_model import (
    MAX_PROJECT_BYTES, PROJECT_FORMAT, PROJECT_VERSION, ProjectError,
    collect_project_resources,
    load_project, make_project, merge_project_resources, prepare_project_settings,
    save_project,
)


def test_project_round_trip(tmp_path):
    path = tmp_path / "device.ctproj"
    payload = make_project(
        "Device A",
        {"device_type": "Modbus"},
        {"rx_hex": True, "frame_rules": "[]"},
        "1.0",
    )

    save_project(str(path), payload)
    loaded = load_project(str(path))

    assert loaded["format"] == PROJECT_FORMAT
    assert loaded["format_version"] == PROJECT_VERSION
    assert loaded["name"] == "Device A"
    assert loaded["metadata"]["device_type"] == "Modbus"
    assert loaded["settings"]["rx_hex"] is True


def test_project_rejects_other_json(tmp_path):
    path = tmp_path / "other.ctproj"
    path.write_text(json.dumps({"settings": {}}), encoding="utf-8")

    with pytest.raises(ProjectError, match="not a CommTool project"):
        load_project(str(path))


def test_project_rejects_oversized_file_before_json_parse(tmp_path):
    path = tmp_path / "oversized.ctproj"
    with path.open("wb") as stream:
        stream.seek(MAX_PROJECT_BYTES)
        stream.write(b"x")
    with pytest.raises(ProjectError, match="project too large"):
        load_project(str(path))


def test_project_rejects_unknown_version(tmp_path):
    path = tmp_path / "future.ctproj"
    path.write_text(json.dumps({
        "format": PROJECT_FORMAT,
        "format_version": PROJECT_VERSION + 1,
        "metadata": {},
        "settings": {},
    }), encoding="utf-8")

    with pytest.raises(ProjectError, match="unsupported project version"):
        load_project(str(path))


@pytest.mark.parametrize("bad_version", [True, 2.0, "2"])
def test_project_rejects_non_integer_version(tmp_path, bad_version):
    path = tmp_path / "bad-version.ctproj"
    path.write_text(json.dumps({
        "format": PROJECT_FORMAT,
        "format_version": bad_version,
        "metadata": {},
        "settings": {},
        "resources": {},
    }), encoding="utf-8")

    with pytest.raises(ProjectError, match="unsupported project version"):
        load_project(str(path))


def test_v1_project_remains_loadable(tmp_path):
    path = tmp_path / "legacy.ctproj"
    path.write_text(json.dumps({
        "format": PROJECT_FORMAT, "format_version": 1,
        "metadata": {}, "settings": {"rx_hex": True},
    }), encoding="utf-8")
    loaded = load_project(str(path))
    assert loaded["settings"]["rx_hex"] is True
    assert loaded["resources"] == {}


def test_project_resources_pack_and_restore_workspace_assets():
    settings = {
        "device_registers": json.dumps([{"name": "temp", "address": 1}]),
        "device_plot_tags": json.dumps(["temp"]),
        "device_dash_tags": json.dumps(["temp", "hum"]),
        "snippets": json.dumps([{"name": "read", "text": "01 03"}]),
        "multi_send_groups": json.dumps([{"name": "default", "items": []}]),
        "sequence_rules": json.dumps([{"send": "AT"}]),
        "script_lib": json.dumps([{"name": "test", "code": "log('ok')"}]),
        "dash_fields": "temp=0:u16be",
    }
    resources = collect_project_resources(settings)
    assert resources["device"]["registers"][0]["name"] == "temp"
    assert resources["device"]["plot_tags"] == ["temp"]
    assert resources["device"]["dash_tags"] == ["temp", "hum"]
    assert resources["send"]["snippets"][0]["name"] == "read"
    assert resources["automation"]["sequences"][0]["send"] == "AT"
    assert resources["dashboard"]["dash_fields"] == "temp=0:u16be"

    restored = merge_project_resources({}, resources)
    assert json.loads(restored["device_registers"])[0]["address"] == 1
    assert json.loads(restored["device_plot_tags"]) == ["temp"]
    assert json.loads(restored["device_dash_tags"]) == ["temp", "hum"]
    assert json.loads(restored["script_lib"])[0]["name"] == "test"
    assert restored["dash_fields"] == "temp=0:u16be"


def test_prepare_settings_drops_old_project_rules_but_keeps_personal_preferences():
    previous = {
        "theme": "dark",
        "language": "zh",
        "autoreply_rules": "OLD",
        "frame_rules": "OLD_FRAME",
    }
    incoming = {"net_proto": "UDP", "theme": "default", "language": "en",
                "unknown": "ignored"}
    allowed = ("theme", "language", "autoreply_rules", "frame_rules", "net_proto")

    result = prepare_project_settings(incoming, previous, allowed)

    assert result == {"net_proto": "UDP", "theme": "dark", "language": "zh"}


def test_prepare_settings_empty_project_keeps_only_personal_preferences():
    previous = {"theme": "dark", "language": "zh", "net_proto": "UDP"}

    result = prepare_project_settings(
        {}, previous, ("theme", "language", "net_proto", "rx_hex"))

    assert result == {"theme": "dark", "language": "zh"}


def test_prepare_settings_personal_only_incoming_cannot_override_local_values():
    previous = {"theme": "default", "language": "zh_tw"}
    incoming = {"theme": "dark", "language": "en", "auto_update_check": False}

    result = prepare_project_settings(
        incoming, previous, ("theme", "language", "auto_update_check"))

    assert result == {"theme": "default", "language": "zh_tw"}


def test_prepare_settings_ignores_none_personal_and_unknown_keys():
    previous = {"theme": None, "language": None}
    incoming = {"net_proto": "TCP Client", "not_allowed": "ignored"}

    result = prepare_project_settings(
        incoming, previous, ("theme", "language", "net_proto"))

    assert result == {"net_proto": "TCP Client"}


def test_save_project_closes_raw_fd_and_removes_temp_if_fdopen_fails(
        tmp_path, monkeypatch):
    payload = make_project("Device A", {}, {}, "1.0")
    real_close = os.close
    closed = []

    def tracking_close(fd):
        closed.append(fd)
        real_close(fd)

    def broken_fdopen(*_args, **_kwargs):
        raise OSError("fdopen failed")

    monkeypatch.setattr(os, "close", tracking_close)
    monkeypatch.setattr(os, "fdopen", broken_fdopen)

    with pytest.raises(OSError, match="fdopen failed"):
        save_project(str(tmp_path / "device.ctproj"), payload)

    assert len(closed) == 1
    assert not list(tmp_path.glob(".commtool-*.tmp"))
