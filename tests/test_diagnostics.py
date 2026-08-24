# -*- coding: utf-8 -*-
"""Qt-free tests for rolling logs and privacy-redacted support bundles."""
import json
import logging
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import diagnostics


def _remove_commtool_handlers():
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, diagnostics._HANDLER_MARK, False):
            root.removeHandler(handler)
            handler.close()


def test_configure_logging_is_rotating_and_idempotent(tmp_path):
    _remove_commtool_handlers()
    try:
        one = diagnostics.configure_logging(tmp_path)
        two = diagnostics.configure_logging(tmp_path)
        assert one == two
        handlers = [h for h in logging.getLogger().handlers
                    if getattr(h, diagnostics._HANDLER_MARK, False)]
        assert len(handlers) == 1
        assert handlers[0].maxBytes == 2 * 1024 * 1024
        assert handlers[0].backupCount == 3
    finally:
        _remove_commtool_handlers()


def test_logging_setup_failure_does_not_block_startup(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    assert diagnostics.configure_logging(blocker / "logs") == ""


def test_profile_log_name_keeps_processes_on_separate_files(tmp_path):
    _remove_commtool_handlers()
    try:
        path = diagnostics.configure_logging(
            tmp_path, log_name="commtool-profile-2.log")
        assert Path(path).name == "commtool-profile-2.log"
    finally:
        _remove_commtool_handlers()


def test_bundle_redacts_setting_values_and_includes_logs(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / diagnostics.LOG_NAME).write_text("safe failure metadata\n", encoding="utf-8")
    out = tmp_path / "diagnostics.zip"
    settings = {
        "language": "zh",
        "theme": "dark",
        "net_proto": "Serial",
        "rx_hex": True,
        "tx_hex": False,
        "show_timestamp": True,
        "ts_format": "hms",
        "line_split": True,
        "auto_update_check": True,
        "send_history": "TOP-SECRET-PAYLOAD",
        "webhook_url": "https://secret.example/hook",
    }
    diagnostics.create_diagnostic_bundle(out, "9.9.9", log_dir, settings)
    with zipfile.ZipFile(out) as zf:
        assert set(zf.namelist()) >= {
            "system.json", "settings-redacted.json", "logs/commtool.log"}
        report = json.loads(zf.read("settings-redacted.json"))
        assert report["safe_values"] == {
            "language": "zh",
            "theme": "dark",
            "net_proto": "Serial",
            "rx_hex": True,
            "tx_hex": False,
            "show_timestamp": True,
            "ts_format": "hms",
            "line_split": True,
            "auto_update_check": True,
        }
        raw = zf.read("settings-redacted.json").decode("utf-8")
        assert "TOP-SECRET-PAYLOAD" not in raw
        assert "secret.example" not in raw


def test_bundle_uses_only_current_profile_log_family(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "commtool.log").write_text("main", encoding="utf-8")
    (log_dir / "commtool-profile-2.log").write_text("profile", encoding="utf-8")
    out = tmp_path / "diagnostics.zip"
    diagnostics.create_diagnostic_bundle(
        out, "1", log_dir, log_name="commtool-profile-2.log")
    with zipfile.ZipFile(out) as zf:
        assert "logs/commtool-profile-2.log" in zf.namelist()
        assert "logs/commtool.log" not in zf.namelist()
