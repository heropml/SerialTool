# -*- coding: utf-8 -*-
"""Privacy-conscious application logging and diagnostic bundle export."""
from __future__ import annotations

import importlib.metadata
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import sys
import threading
from datetime import datetime, timezone
import zipfile


LOG_NAME = "commtool.log"
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3
_HANDLER_MARK = "_commtool_rotating_file"
_SAFE_SETTING_VALUES = {
    "language", "theme", "protocol", "encoding", "recv_hex", "send_hex",
    "timestamp", "timestamp_format", "line_split", "auto_check_update",
}
_DEPENDENCIES = ("PyQt5", "pyserial", "bleak", "pyqtgraph", "numpy", "openpyxl")


def configure_logging(log_dir, level=logging.DEBUG, log_name=LOG_NAME):
    """Install one process-wide rotating handler; logging failure never blocks startup."""
    try:
        directory = os.path.abspath(os.fspath(log_dir))
        os.makedirs(directory, exist_ok=True)
        name = os.path.basename(os.fspath(log_name))
        if not name or name in (".", ".."):
            return ""
    except (OSError, TypeError, ValueError):
        return ""
    path = os.path.join(directory, name)
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, _HANDLER_MARK, False):
            return getattr(handler, "baseFilename", path)
    try:
        handler = RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
            encoding="utf-8", delay=True)
    except (OSError, TypeError, ValueError):
        return ""
    setattr(handler, _HANDLER_MARK, True)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"))
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    return path


def install_exception_logging():
    """Record otherwise-uncaught main/thread exceptions, preserving old hooks."""
    logger = logging.getLogger("commtool.crash")
    old_sys = sys.excepthook

    def on_exception(exc_type, exc, tb):
        logger.critical("uncaught exception", exc_info=(exc_type, exc, tb))
        old_sys(exc_type, exc, tb)

    if not getattr(sys.excepthook, "_commtool_hook", False):
        setattr(on_exception, "_commtool_hook", True)
        sys.excepthook = on_exception

    if hasattr(threading, "excepthook"):
        old_thread = threading.excepthook

        def on_thread_exception(args):
            logger.critical("uncaught thread exception",
                            exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
            old_thread(args)

        if not getattr(threading.excepthook, "_commtool_hook", False):
            setattr(on_thread_exception, "_commtool_hook", True)
            threading.excepthook = on_thread_exception


def dependency_versions(names=_DEPENDENCIES):
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def system_report(app_version):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_version": str(app_version),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable_frozen": bool(getattr(sys, "frozen", False)),
        "dependencies": dependency_versions(),
    }


def _setting_items(settings):
    if settings is None:
        return []
    if hasattr(settings, "allKeys") and hasattr(settings, "value"):
        return [(str(key), settings.value(key)) for key in settings.allKeys()]
    if hasattr(settings, "items"):
        return [(str(key), value) for key, value in settings.items()]
    return []


def sanitize_settings(settings):
    """Return a non-secret settings inventory suitable for support bundles."""
    values = {}
    keys = []
    for key, value in sorted(_setting_items(settings), key=lambda item: item[0]):
        keys.append(key)
        if key in _SAFE_SETTING_VALUES and isinstance(value, (bool, int, float, str)):
            values[key] = str(value)[:80] if isinstance(value, str) else value
    return {"key_count": len(keys), "keys": keys, "safe_values": values}


def _flush_logging():
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except (OSError, ValueError):
            pass


def create_diagnostic_bundle(
        output_path, app_version, log_dir, settings=None, log_name=LOG_NAME):
    """Create a zip containing environment, redacted settings, and rotated logs."""
    destination = os.path.abspath(os.fspath(output_path))
    parent = os.path.dirname(destination)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _flush_logging()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "system.json",
            json.dumps(system_report(app_version), ensure_ascii=False, indent=2))
        zf.writestr(
            "settings-redacted.json",
            json.dumps(sanitize_settings(settings), ensure_ascii=False, indent=2))
        root = os.path.abspath(os.fspath(log_dir))
        name_root = os.path.basename(os.fspath(log_name)) or LOG_NAME
        for index in range(LOG_BACKUPS + 1):
            name = name_root if index == 0 else "%s.%d" % (name_root, index)
            path = os.path.join(root, name)
            if os.path.isfile(path):
                zf.write(path, "logs/" + name)
    return destination
