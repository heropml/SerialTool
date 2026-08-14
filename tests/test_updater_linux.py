# -*- coding: utf-8 -*-
"""Tests for updater.linux_download_candidates and Linux installer launch."""
import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtWidgets import QApplication

from updater import (cleanup_temp_installers, linux_download_candidates,
                     run_linux_installer)

_APP = QApplication.instance() or QApplication([])


def test_linux_download_candidates_github_before_gitee():
    raw = [
        "https://gitee.com/heropml/SerialTool/releases/download/comm-v1.5.7/CommTool_Setup_v1.5.7_linux_x86_64.run",
        "https://github.com/heropml/SerialTool/releases/download/comm-v1.5.7/CommTool_Setup_v1.5.7_linux_x86_64.run",
    ]
    out = linux_download_candidates(raw)
    assert out[0].startswith("https://github.com/")
    assert "gitee.com" in out[1]


def test_linux_download_candidates_filters_and_dedupes():
    assert linux_download_candidates(
        "https://github.com/x/CommTool_Setup_v1.run") == [
        "https://github.com/x/CommTool_Setup_v1.run"]
    assert linux_download_candidates([
        "http://insecure.example/a.run",
        "https://github.com/x/a.run",
        "https://github.com/x/a.run",
        123,
    ]) == ["https://github.com/x/a.run"]


def test_active_manifest_linux_urls_match_gate():
    """url_linux is empty until the GitHub .run is uploaded, then that exact URL."""
    manifest = json.loads((ROOT / "latest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    expected = (
        "https://github.com/heropml/SerialTool/releases/download/"
        "comm-v%s/CommTool_Setup_v%s_linux_x86_64.run" % (version, version)
    )
    got = linux_download_candidates(manifest.get("url_linux"))
    assert got in ([], [expected])
    if got:
        assert got[0] == expected


def test_cleanup_removes_stale_run_but_keeps_recent(tmp_path, monkeypatch):
    import os
    import time
    import updater

    stale = tmp_path / "CommTool_Setup_v1.5.7_linux_x86_64_1.run"
    recent = tmp_path / "CommTool_Setup_v1.5.7_linux_x86_64_2.run"
    unrelated = tmp_path / "keep.run"
    for path in (stale, recent, unrelated):
        path.write_bytes(b"x")
    old = time.time() - 601
    os.utime(stale, (old, old))
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))

    cleanup_temp_installers()

    assert not stale.exists()
    assert recent.exists()
    assert unrelated.exists()


def test_run_linux_installer_false_off_linux(monkeypatch, tmp_path):
    monkeypatch.setattr("updater._is_linux", lambda: False)
    assert run_linux_installer(str(tmp_path / "x.run")) is False


def test_run_linux_installer_launches_delayed_bash(monkeypatch, tmp_path):
    setup = tmp_path / "CommTool_Setup_v1.5.7_linux_x86_64.run"
    setup.write_bytes(b"#!/bin/bash\n")
    seen = {}

    def _popen(args, **kw):
        seen["args"] = args
        seen["kw"] = kw
        class _P:
            pass
        return _P()

    monkeypatch.setattr("updater._is_linux", lambda: True)
    monkeypatch.setattr("updater.subprocess.Popen", _popen)
    assert run_linux_installer(str(setup)) is True
    assert seen["args"][0] == "bash"
    assert str(setup) in seen["args"]
    assert seen["kw"].get("start_new_session") is True


def test_download_worker_rejects_non_shebang_on_linux(tmp_path, monkeypatch):
    import updater

    monkeypatch.setattr("updater._is_windows", lambda: False)
    monkeypatch.setattr("updater._is_linux", lambda: True)
    out = tmp_path / "CommTool_Setup_v1.run"

    class _Resp:
        headers = {"Content-Length": "12"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, n=-1):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return b"<html>nope"

        def close(self):
            pass

    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _Resp())
    w = updater._DownloadWorker("https://example.com/x.run", str(out))
    done = []
    w.done.connect(lambda path, err: done.append((path, err)))
    w.run()
    assert done
    assert done[0][0] == ""
    assert not out.exists()


def test_download_worker_accepts_shebang_on_linux(tmp_path, monkeypatch):
    import updater

    monkeypatch.setattr("updater._is_windows", lambda: False)
    monkeypatch.setattr("updater._is_linux", lambda: True)
    out = tmp_path / "CommTool_Setup_v1.run"
    payload = b"#!/usr/bin/env bash\necho ok\n"

    class _Resp:
        headers = {"Content-Length": str(len(payload))}

        def __init__(self):
            self._data = payload
            self._off = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, n=-1):
            if self._off >= len(self._data):
                return b""
            chunk = self._data[self._off:self._off + n]
            self._off += len(chunk)
            return chunk

        def close(self):
            pass

    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _Resp())
    w = updater._DownloadWorker("https://example.com/x.run", str(out))
    done = []
    w.done.connect(lambda path, err: done.append((path, err)))
    w.run()
    assert done == [(str(out), "")]
    assert out.read_bytes().startswith(b"#!")
