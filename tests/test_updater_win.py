# -*- coding: utf-8 -*-
"""Windows updater paths: manifest order, Setup URL, MZ gate, installer launch."""
from __future__ import annotations

import http.client
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QApplication

from updater import (
    UPDATE_MANIFEST_URLS,
    UpdateDownloader,
    _DownloadWorker,
    _ManifestWorker,
    run_installer,
)

_APP = QApplication.instance() or QApplication([])


def _pump(seconds=0.5):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        _APP.processEvents()
        time.sleep(0.01)


def test_manifest_urls_gitee_before_github():
    assert len(UPDATE_MANIFEST_URLS) >= 2
    assert "gitee.com" in UPDATE_MANIFEST_URLS[0]
    assert "githubusercontent.com" in UPDATE_MANIFEST_URLS[1]


def test_active_manifest_windows_setup_url():
    """Primary download url must be the Gitee Setup for the declared version."""
    manifest = json.loads((ROOT / "latest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    expected = (
        "https://gitee.com/heropml/SerialTool/releases/download/"
        "comm-v%s/CommTool_Setup_v%s.exe" % (version, version)
    )
    assert manifest.get("url") == expected


def test_downloader_rejects_non_https():
    finished = []
    d = UpdateDownloader("http://example.com/CommTool_Setup_v9.exe")
    d.finished.connect(lambda path, err: finished.append((path, err)))
    d.start()
    _pump(0.2)
    assert finished
    path, err = finished[0]
    assert path == ""
    assert err  # updater_bad_url (or translated)


def test_download_worker_rejects_non_mz_on_win32(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    out = tmp_path / "CommTool_Setup_v1.5.3_1.exe"

    class _Resp:
        headers = {"Content-Length": "12"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return b"<!DOCTYPE html>"

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _Resp())

    done = []
    w = _DownloadWorker("https://example.com/x.exe", str(out))
    w.done.connect(lambda path, err: done.append((path, err)))
    w.start()
    assert w.wait(5000)
    _pump(0.1)
    assert done
    path, err = done[0]
    assert path == ""
    assert err
    assert not out.exists()


def test_download_worker_accepts_mz_header_on_win32(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    out = tmp_path / "CommTool_Setup_v1.5.3_2.exe"
    payload = b"MZ" + b"\0" * 64

    class _Resp:
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return payload

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _Resp())

    done = []
    w = _DownloadWorker("https://example.com/ok.exe", str(out))
    w.done.connect(lambda path, err: done.append((path, err)))
    w.start()
    assert w.wait(5000)
    _pump(0.1)
    assert done == [(str(out), "")]
    assert out.read_bytes()[:2] == b"MZ"


def test_download_worker_skips_mz_check_off_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    out = tmp_path / "CommTool_v1.5.3_1.dmg"
    payload = b"not-an-mz-but-ok-on-mac"

    class _Resp:
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return payload

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _Resp())

    done = []
    w = _DownloadWorker("https://example.com/a.dmg", str(out))
    w.done.connect(lambda path, err: done.append((path, err)))
    w.start()
    assert w.wait(5000)
    _pump(0.1)
    assert done == [(str(out), "")]


def test_manifest_worker_falls_back_to_second_source(monkeypatch):
    calls = []

    class _Ok:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return json.dumps({
                "version": "9.9.9",
                "url": "https://gitee.com/x/CommTool_Setup_v9.9.9.exe",
                "notes": "n",
            }).encode("utf-8")

    def _urlopen(req, timeout=None, context=None):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise OSError("primary down")
        return _Ok()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    got = []
    w = _ManifestWorker("1.0.0")
    w.got.connect(lambda info, err: got.append((info, err)))
    w.start()
    assert w.wait(5000)
    _pump(0.1)
    assert len(calls) >= 2
    assert calls[0] == UPDATE_MANIFEST_URLS[0]
    assert calls[1] == UPDATE_MANIFEST_URLS[1]
    assert got and got[0][1] == ""
    info = got[0][0]
    assert info["version"] == "9.9.9"
    assert info["newer"] is True
    assert info["source"] == UPDATE_MANIFEST_URLS[1]


def test_manifest_worker_handles_truncated_http_body(monkeypatch):
    """IncompleteRead must not kill the worker without emitting got."""
    assert issubclass(http.client.IncompleteRead, http.client.HTTPException)

    class _Trunc:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            raise http.client.IncompleteRead(b"{")

    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: _Trunc())

    got = []
    w = _ManifestWorker("1.0.0")
    w.got.connect(lambda info, err: got.append((info, err)))
    w.start()
    assert w.wait(5000)
    _pump(0.1)
    assert got
    info, err = got[0]
    assert info is None
    assert err  # last source IncompleteRead message


def test_download_worker_handles_truncated_http_body(tmp_path, monkeypatch):
    """Truncated body must emit done and remove the partial installer."""
    out = tmp_path / "CommTool_Setup_v1.5.3_trunc.exe"

    class _Trunc:
        headers = {"Content-Length": "100"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            raise http.client.IncompleteRead(b"MZ")

    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: _Trunc())

    done = []
    w = _DownloadWorker("https://example.com/trunc.exe", str(out))
    w.done.connect(lambda path, err: done.append((path, err)))
    w.start()
    assert w.wait(5000)
    _pump(0.1)
    assert done
    path, err = done[0]
    assert path == ""
    assert "IncompleteRead" in err or err
    assert not out.exists()


def test_run_installer_false_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert run_installer(r"C:\Temp\Setup.exe") is False


def test_run_installer_windows_launches_detached(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    setup = tmp_path / "CommTool_Setup_v1.5.3.exe"
    setup.write_bytes(b"MZ")
    seen = {}

    def _popen(args, creationflags=0):
        seen["args"] = list(args)
        seen["flags"] = creationflags
        return mock.Mock()

    monkeypatch.setattr(subprocess, "Popen", _popen)
    assert run_installer(str(setup)) is True
    assert seen["args"] == [str(setup)]
    assert seen["flags"] == subprocess.CREATE_NEW_PROCESS_GROUP


def test_run_installer_windows_oserror_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    setup = tmp_path / "missing_setup.exe"

    def _boom(*_a, **_k):
        raise OSError("launch failed")

    monkeypatch.setattr(subprocess, "Popen", _boom)
    assert run_installer(str(setup)) is False
