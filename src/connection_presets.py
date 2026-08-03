# -*- coding: utf-8 -*-
"""Named connection presets (favorites). Qt-free data logic for unit tests."""
import json
import time
import uuid

MAX_PRESETS = 100
MAX_NAME = 200
MAX_NOTE = 500
MAX_RECENT = 8

CONN_FIELD_KEYS = (
    "net_proto",
    "ser_port", "ser_baud", "ser_databits", "ser_parity", "ser_stopbits", "ser_flow",
    "serial_dtr", "serial_rts",
    "net_local_ip", "net_local_port",
    "net_remote_ip", "net_remote_port", "net_use_remote", "net_group_addr",
    "vconn_loopback",
    "auto_reconnect",
)

_DEFAULTS = {
    "net_proto": "Serial",
    "ser_port": "",
    "ser_baud": "115200",
    "ser_databits": "8",
    "ser_parity": "None",
    "ser_stopbits": "1",
    "ser_flow": "None",
    "serial_dtr": True,
    "serial_rts": True,
    "net_local_ip": "0.0.0.0",
    "net_local_port": "8080",
    "net_remote_ip": "",
    "net_remote_port": "",
    "net_use_remote": False,
    "net_group_addr": "239.0.0.1",
    "vconn_loopback": False,
    "auto_reconnect": True,
}


def _bool(v, default=False):
    if v is None:
        return bool(default)
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0", "no", "off")
    return bool(v)


def _str(v, default="", limit=None):
    if v is None:
        text = str(default)
    else:
        text = str(v)
    if limit is not None:
        return text[:limit]
    return text


def _new_id():
    return uuid.uuid4().hex


def normalize(item):
    if not isinstance(item, dict):
        item = {}
    fields = {}
    for key in CONN_FIELD_KEYS:
        default = _DEFAULTS[key]
        raw = item.get(key, default)
        if isinstance(default, bool):
            fields[key] = _bool(raw, default)
        else:
            fields[key] = _str(raw, default)
    last_used = item.get("last_used", 0)
    try:
        last_used = float(last_used or 0)
    except (TypeError, ValueError):
        last_used = 0.0
    pid = _str(item.get("id", ""), "").strip() or _new_id()
    return {
        "id": pid[:64],
        "name": _str(item.get("name", ""), "", MAX_NAME).strip() or "Untitled",
        "note": _str(item.get("note", ""), "", MAX_NOTE),
        "last_used": last_used,
        **fields,
    }


def sanitize_list(items):
    if not isinstance(items, list):
        return []
    out = [normalize(x) for x in items if isinstance(x, dict)]
    return out[:MAX_PRESETS]


def capture_fields(src):
    src = src if isinstance(src, dict) else {}
    fields = {}
    for key in CONN_FIELD_KEYS:
        default = _DEFAULTS[key]
        raw = src.get(key, default)
        if isinstance(default, bool):
            fields[key] = _bool(raw, default)
        else:
            fields[key] = _str(raw, default)
    return fields


def make_preset(name, fields, note="", preset_id=None, last_used=None):
    body = dict(_DEFAULTS)
    body.update(capture_fields(fields))
    body["id"] = (preset_id or _new_id())[:64]
    body["name"] = _str(name, "Untitled", MAX_NAME).strip() or "Untitled"
    body["note"] = _str(note, "", MAX_NOTE)
    if last_used is None:
        body["last_used"] = 0.0
    else:
        try:
            body["last_used"] = float(last_used)
        except (TypeError, ValueError):
            body["last_used"] = 0.0
    return normalize(body)


def find_index(items, preset_id):
    pid = _str(preset_id, "").strip()
    if not pid:
        return -1
    for i, item in enumerate(items or []):
        if item.get("id") == pid:
            return i
    return -1


def find_by_id(items, preset_id):
    idx = find_index(items, preset_id)
    return None if idx < 0 else items[idx]


def upsert(items, preset):
    items = sanitize_list(items)
    preset = normalize(preset)
    idx = find_index(items, preset["id"])
    if idx < 0:
        if len(items) >= MAX_PRESETS:
            raise ValueError("presets full")
        items.append(preset)
        return items, len(items) - 1
    items[idx] = preset
    return items, idx


def delete_by_id(items, preset_id):
    items = sanitize_list(items)
    idx = find_index(items, preset_id)
    if idx < 0:
        return items, None
    removed = items.pop(idx)
    return items, removed


def duplicate(items, preset_id, name_suffix=" (copy)"):
    items = sanitize_list(items)
    src = find_by_id(items, preset_id)
    if src is None:
        return items, None
    if len(items) >= MAX_PRESETS:
        raise ValueError("presets full")
    clone = dict(src)
    clone["id"] = _new_id()
    base = src.get("name", "Untitled")
    suffix = _str(name_suffix, " (copy)", 40)
    clone["name"] = (base + suffix)[:MAX_NAME]
    clone["last_used"] = 0.0
    items.append(normalize(clone))
    return items, items[-1]


def touch_last_used(items, preset_id, when=None):
    items = sanitize_list(items)
    idx = find_index(items, preset_id)
    if idx < 0:
        return items, None
    item = dict(items[idx])
    item["last_used"] = float(when if when is not None else time.time())
    items.pop(idx)
    items.insert(0, normalize(item))
    return items, items[0]


def sort_by_recent(items):
    items = sanitize_list(items)
    return sorted(
        items,
        key=lambda p: (-float(p.get("last_used") or 0), p.get("name", "").lower()),
    )


def recent_ids(items, limit=MAX_RECENT):
    ordered = sort_by_recent(items)
    return [p["id"] for p in ordered if p.get("last_used")][: max(0, int(limit))]


def summary(preset):
    p = normalize(preset)
    proto = p.get("net_proto") or "Serial"
    if proto == "Serial":
        detail = "%s @ %s" % (p.get("ser_port") or "?", p.get("ser_baud") or "?")
    elif proto == "TCP Client":
        detail = "%s:%s" % (p.get("net_remote_ip") or "?", p.get("net_remote_port") or "?")
    elif proto in ("TCP Server", "UDP", "UDP Multicast"):
        detail = "%s:%s" % (p.get("net_local_ip") or "?", p.get("net_local_port") or "?")
        if proto == "UDP Multicast":
            detail = "%s / %s" % (p.get("net_group_addr") or "?", detail)
    elif proto == "Virtual":
        detail = "loopback" if p.get("vconn_loopback") else "sink"
    else:
        detail = proto
    return "%s | %s" % (proto, detail)


def display_label(preset):
    p = normalize(preset)
    return "%s - %s" % (p["name"], summary(p))


def match(preset, query):
    q = (query or "").strip().lower()
    if not q:
        return True
    p = normalize(preset)
    blob = " ".join([
        p.get("name", ""), p.get("note", ""), summary(p),
        p.get("ser_port", ""), p.get("net_remote_ip", ""), p.get("net_local_ip", ""),
    ]).lower()
    return q in blob


def filter_presets(items, query):
    return [(i, p) for i, p in enumerate(items) if match(p, query)]


def to_json(items):
    return json.dumps(
        {"type": "commtool-connection-presets", "version": 1,
         "presets": sanitize_list(items)},
        ensure_ascii=False, indent=2)


def from_json(text):
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        raise ValueError("bad json: %s" % e)
    if isinstance(data, list):
        return sanitize_list(data)
    if isinstance(data, dict):
        for key in ("presets", "items", "connection_presets"):
            if isinstance(data.get(key), list):
                return sanitize_list(data[key])
    raise ValueError("no preset list found")

