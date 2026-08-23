# -*- coding: utf-8 -*-
"""Local index for .ctrec recordings (metadata only; payload stays in files)."""
from __future__ import annotations

import json
import math
import os
import tempfile


CATALOG_VERSION = 1
MAX_ITEMS = 200
MAX_HEADER_BYTES = 1 << 20
MAX_CATALOG_BYTES = 2 << 20


def _safe_text(value, limit):
    if isinstance(value, (dict, list, tuple)):
        return ""
    text = str(value or "")
    return text.encode("utf-8", "replace").decode("utf-8")[:limit]


def inspect_recording(path):
    full = os.path.abspath(os.fspath(path))
    stat = os.stat(full)
    with open(full, "r", encoding="utf-8") as stream:
        line = stream.readline(MAX_HEADER_BYTES + 1)
    if len(line) > MAX_HEADER_BYTES:
        raise ValueError("recording header is too large")
    header = json.loads(line)
    version = header.get("v") if isinstance(header, dict) else None
    if (not isinstance(header, dict) or header.get("_") != "ctrec"
            or type(version) is not int or version != 1):
        raise ValueError("not a CommTool recording")
    return {
        "path": full,
        "name": os.path.basename(full),
        "created": _safe_text(header.get("created"), 80),
        "note": _safe_text(header.get("note"), 240),
        "size": int(stat.st_size),
        "modified": float(stat.st_mtime),
        "proto": _safe_text((header.get("link") or {}).get("proto"), 80)
        if isinstance(header.get("link"), dict) else "",
    }


def _normalize_catalog_item(item):
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        return None
    full = os.path.abspath(item["path"])
    try:
        stat = os.stat(full)
    except OSError:
        return None
    if not os.path.isfile(full):
        return None
    try:
        modified = float(item.get("modified", stat.st_mtime))
    except (TypeError, ValueError, OverflowError):
        modified = float(stat.st_mtime)
    if not math.isfinite(modified):
        modified = float(stat.st_mtime)
    return {
        "path": full,
        "name": _safe_text(item.get("name"), 255) or os.path.basename(full),
        "created": _safe_text(item.get("created"), 80),
        "note": _safe_text(item.get("note"), 240),
        "size": int(stat.st_size),
        "modified": modified,
        "proto": _safe_text(item.get("proto"), 80),
    }


def load_catalog(path):
    try:
        if os.path.getsize(path) > MAX_CATALOG_BYTES:
            return []
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError, TypeError):
        return []
    version = data.get("version") if isinstance(data, dict) else None
    if type(version) is not int or version != CATALOG_VERSION:
        return []
    out = []
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return []
    for item in raw_items:
        clean = _normalize_catalog_item(item)
        if clean is not None:
            out.append(clean)
        if len(out) >= MAX_ITEMS:
            break
    return out


def save_catalog(path, items):
    destination = os.path.abspath(os.fspath(path))
    folder = os.path.dirname(destination)
    os.makedirs(folder, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".catalog-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"version": CATALOG_VERSION, "items": list(items)[:MAX_ITEMS]},
                      stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_path, destination)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def remember(catalog_path, recording_path):
    item = inspect_recording(recording_path)
    target = os.path.normcase(item["path"])
    items = [old for old in load_catalog(catalog_path)
             if os.path.normcase(str(old.get("path") or "")) != target]
    items.insert(0, item)
    save_catalog(catalog_path, items)
    return items[:MAX_ITEMS]
