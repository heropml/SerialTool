
# -*- coding: utf-8 -*-
"""Tests for updater.mac_download_candidates (Mac publish order)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from updater import (cleanup_temp_installers, is_newer,
                     mac_download_candidates)
import check_mac_asset


def test_mac_download_candidates_github_before_gitee():
    raw = [
        "https://gitee.com/heropml/SerialTool/releases/download/comm-v1.5.0/CommTool_v1.5.0.dmg",
        "https://github.com/heropml/SerialTool/releases/download/comm-v1.5.0/CommTool_v1.5.0.dmg",
    ]
    out = mac_download_candidates(raw)
    assert out[0].startswith("https://github.com/")
    assert "gitee.com" in out[1]


def test_mac_download_candidates_filters_and_dedupes():
    assert mac_download_candidates("https://github.com/x/y.dmg") == [
        "https://github.com/x/y.dmg"]
    assert mac_download_candidates([
        "http://insecure.example/a.dmg",
        "https://github.com/x/a.dmg",
        "https://github.com/x/a.dmg",
        123,
    ]) == ["https://github.com/x/a.dmg"]


def test_active_manifest_mac_urls_match_gate():
    """Windows-first publish leaves url_mac empty until Mac gate verifies the DMG.

    When urls are present they must be the GitHub asset for the same version
    (no prefilled dead links / Gitee-only Mac entries).
    """
    manifest = json.loads((ROOT / "latest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    expected = (
        "https://github.com/heropml/SerialTool/releases/download/"
        "comm-v%s/CommTool_v%s.dmg" % (version, version)
    )
    got = mac_download_candidates(manifest.get("url_mac"))
    assert got in ([], [expected])
    if got:
        assert got[0] == expected


def test_invalid_version_never_forces_an_update():
    assert is_newer("1.5.1", "broken") is False
    assert is_newer("broken", "1.5.0") is False
    assert is_newer("1.5.1", "1.5.0") is True
    assert is_newer("1.5.0", "1.5.0-rc1") is True


def test_prerelease_suffix_ordering():
    from updater import _parse_version
    # rc2 > rc1 (same base, higher suffix number)
    assert is_newer("1.5.0-rc2", "1.5.0-rc1") is True
    # rc1 < rc2
    assert is_newer("1.5.0-rc1", "1.5.0-rc2") is False
    # beta < rc (alphabetical: "beta" < "rc")
    assert is_newer("1.5.0-rc1", "1.5.0-beta1") is True
    # release > any prerelease
    assert is_newer("1.5.0", "1.5.0-rc99") is True
    # alpha < beta
    assert is_newer("1.5.0-beta1", "1.5.0-alpha2") is True
    # suffix without number → number defaults to 0
    assert is_newer("1.5.0-rc2", "1.5.0-rc") is True
    # different base versions still compared by main version
    assert is_newer("1.5.1-rc1", "1.5.0") is True
    # Extra numeric components must not shift the prerelease tuple into an int
    # comparison (which used to raise TypeError). Trailing zero is equivalent.
    assert is_newer("1.5.0.0-rc1", "1.5.0-rc1") is False
    assert is_newer("1.5.0-rc1", "1.5.0.0-rc1") is False
    assert is_newer("1.5.0.1-rc1", "1.5.0-rc1") is True


def test_cleanup_removes_stale_exe_and_dmg_but_keeps_recent(tmp_path, monkeypatch):
    import os
    import time
    import updater

    stale_exe = tmp_path / "CommTool_Setup_v1.5.0_1.exe"
    stale_dmg = tmp_path / "CommTool_v1.5.0_1.dmg"
    recent = tmp_path / "CommTool_v1.5.0_2.dmg"
    unrelated = tmp_path / "keep.dmg"
    for path in (stale_exe, stale_dmg, recent, unrelated):
        path.write_bytes(b"x")
    old = time.time() - 601
    os.utime(stale_exe, (old, old))
    os.utime(stale_dmg, (old, old))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))

    cleanup_temp_installers()

    assert not stale_exe.exists()
    assert not stale_dmg.exists()
    assert recent.exists()
    assert unrelated.exists()


def test_mac_asset_gate_falls_back_to_public_github_api(monkeypatch):
    monkeypatch.setattr(
        check_mac_asset, "_run_gh",
        lambda _args: (_ for _ in ()).throw(RuntimeError("gh unavailable")))

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "assets": [{"name": "CommTool_v1.5.0.dmg"}],
            }).encode("utf-8")

    seen = {}

    def _urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(check_mac_asset.urllib.request, "urlopen", _urlopen)
    data = check_mac_asset._release_data("heropml/SerialTool", "comm-v1.5.0")
    assert data["assets"][0]["name"] == "CommTool_v1.5.0.dmg"
    assert seen == {
        "url": "https://api.github.com/repos/heropml/SerialTool/releases/tags/comm-v1.5.0",
        "timeout": 20,
    }
    assert check_mac_asset.main(["1.5.0"]) == 0


def test_mac_asset_gate_rejects_missing_asset(monkeypatch):
    monkeypatch.setattr(check_mac_asset, "_release_data", lambda *_: {"assets": []})
    with pytest.raises(SystemExit, match="missing"):
        check_mac_asset.main(["1.5.0"])
