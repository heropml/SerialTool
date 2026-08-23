# -*- coding: utf-8 -*-
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from update_manifest_integrity import main, update_manifest


def test_update_manifest_integrity_fields(tmp_path):
    artifact = tmp_path / "setup.exe"
    artifact.write_bytes(b"MZ-test-package")
    manifest = tmp_path / "latest.json"
    manifest.write_text(json.dumps({"version": "2.0.0"}), encoding="utf-8")
    assert update_manifest(manifest, artifact, "windows", version="2.0.0") is True
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert data["size"] == artifact.stat().st_size


def test_update_manifest_version_mismatch_is_noop(tmp_path):
    artifact = tmp_path / "app.dmg"
    artifact.write_bytes(b"dmg")
    manifest = tmp_path / "latest.json"
    before = '{"version":"1.0.0"}'
    manifest.write_text(before, encoding="utf-8")
    assert update_manifest(manifest, artifact, "mac", version="2.0.0") is False
    assert manifest.read_text(encoding="utf-8") == before


def test_update_manifest_cli_version_mismatch_is_failure(tmp_path):
    artifact = tmp_path / "app.dmg"
    artifact.write_bytes(b"dmg")
    manifest = tmp_path / "latest.json"
    manifest.write_text('{"version":"1.0.0"}', encoding="utf-8")
    assert main([
        str(manifest), str(artifact), "mac", "--version", "2.0.0",
    ]) == 2


def test_update_manifest_rejects_empty_artifact(tmp_path):
    artifact = tmp_path / "empty.exe"
    artifact.write_bytes(b"")
    manifest = tmp_path / "latest.json"
    before = '{"version":"2.0.0"}'
    manifest.write_text(before, encoding="utf-8")
    try:
        update_manifest(manifest, artifact, "windows", version="2.0.0")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("empty artifact was accepted")
    assert manifest.read_text(encoding="utf-8") == before
