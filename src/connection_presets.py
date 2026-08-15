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
    "ble_address", "ble_name", "ble_profile",
    "ble_service_uuid", "ble_write_uuid", "ble_notify_uuid",
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
    "ble_address": "",
    "ble_name": "",
    "ble_profile": "fff0",
    "ble_service_uuid": "FFF0",
    "ble_write_uuid": "FFF2",
    "ble_notify_uuid": "FFF1",
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
    elif proto == "BLE":
        detail = p.get("ble_name") or p.get("ble_address") or "?"
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
        p.get("ble_address", ""), p.get("ble_name", ""),
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



def parse_port(text):
    """Parse a TCP/UDP port string -> int 1..65535, else None."""
    try:
        p = int(str(text).strip())
    except (ValueError, TypeError):
        return None
    return p if 1 <= p <= 65535 else None


def serial_signature(proto, port, baud, databits, parity, stopbits, flow):
    """Serial connection config signature tuple."""
    return (proto, port, baud, databits, parity, stopbits, flow)


def tcp_client_signature(proto, ip, port):
    """TCP client connection config signature tuple."""
    return (proto, ip, port)


def ble_signature(proto, address, service_uuid, write_uuid, notify_uuid):
    """BLE connection config signature tuple."""
    import ble_uuid
    return (
        proto,
        ble_uuid.normalize_address(address),
        ble_uuid.normalize_uuid(service_uuid) if service_uuid else "",
        ble_uuid.normalize_uuid(write_uuid),
        ble_uuid.normalize_uuid(notify_uuid),
    )


def proto_only_signature(proto):
    """Non-serial / non-tcp-client signature (proto only)."""
    return (proto,)


def parse_baud(text):
    """Parse baud-rate text -> positive int, else None."""
    try:
        baud = int(str(text).strip())
    except (TypeError, ValueError):
        return None
    return baud if baud > 0 else None


def _toast_err(key):
    return {"ok": False, "toast": key}


def _dialog_err(title_key, body_key):
    return {"ok": False, "dialog": (title_key, body_key)}


def validate_open(proto, fields, *, is_valid_ip, is_local_ipv4, is_multicast_ipv4):
    """Validate connection UI fields before constructing a Conn.

    Returns {"ok": True, ...payload} or
            {"ok": False, "toast": err_key} or
            {"ok": False, "dialog": (title_key, body_key)}.

    Payload keys by proto:
      Serial: port, baud
      Virtual: (empty)
      TCP Server: local_ip, port
      TCP Client: ip, port
      UDP Multicast: local_ip, group, port
      UDP: local_ip, lport, rip, rport
      BLE: address, service_uuid, write_uuid, notify_uuid
    """
    fields = fields or {}
    proto = proto or ""

    if proto == "Serial":
        port = fields.get("port")
        if not port:
            return _toast_err("err_no_port")
        baud = parse_baud(fields.get("baud"))
        if baud is None:
            return _toast_err("err_bad_baud")
        return {"ok": True, "port": port, "baud": baud}

    if proto == "Virtual":
        return {"ok": True}

    if proto == "TCP Server":
        local_ip = str(fields.get("local_ip") or "").strip()
        if not is_local_ipv4(local_ip):
            return _dialog_err("err_not_local_ip_title", "err_not_local_ip")
        port = parse_port(fields.get("local_port"))
        if port is None:
            return _toast_err("err_bad_port")
        return {"ok": True, "local_ip": local_ip, "port": port}

    if proto == "TCP Client":
        ip = str(fields.get("remote_ip") or "").strip()
        port = parse_port(fields.get("remote_port"))
        if not is_valid_ip(ip):
            return _toast_err("err_bad_ip")
        if port is None:
            return _toast_err("err_bad_port")
        return {"ok": True, "ip": ip, "port": port}

    if proto == "BLE":
        import ble_uuid
        address = ble_uuid.normalize_address(
            fields.get("address") or fields.get("ble_address"))
        if not ble_uuid.is_valid_address(address):
            return _toast_err("ble_err_no_address")
        service = str(
            fields.get("service_uuid") or fields.get("ble_service_uuid") or "").strip()
        write = str(
            fields.get("write_uuid") or fields.get("ble_write_uuid") or "").strip()
        notify = str(
            fields.get("notify_uuid") or fields.get("ble_notify_uuid") or "").strip()
        if service and not ble_uuid.is_valid_uuid(service):
            return _toast_err("ble_err_bad_uuid")
        if not ble_uuid.is_valid_uuid(write) or not ble_uuid.is_valid_uuid(notify):
            return _toast_err("ble_err_bad_uuid")
        return {
            "ok": True,
            "address": address,
            "service_uuid": ble_uuid.normalize_uuid(service) if service else "",
            "write_uuid": ble_uuid.normalize_uuid(write),
            "notify_uuid": ble_uuid.normalize_uuid(notify),
        }

    if proto == "UDP Multicast":
        local_ip = str(fields.get("local_ip") or "").strip()
        if not is_local_ipv4(local_ip):
            return _dialog_err("err_not_local_ip_title", "err_not_local_ip")
        port = parse_port(fields.get("local_port"))
        if port is None:
            return _toast_err("err_bad_port")
        group = str(fields.get("group") or "").strip()
        if not is_multicast_ipv4(group):
            return _toast_err("err_not_multicast")
        return {"ok": True, "local_ip": local_ip, "group": group, "port": port}

    # UDP (default / else)
    local_ip = str(fields.get("local_ip") or "").strip()
    if not is_local_ipv4(local_ip):
        return _dialog_err("err_not_local_ip_title", "err_not_local_ip")
    lport = parse_port(fields.get("local_port"))
    if lport is None:
        return _toast_err("err_bad_port")
    if fields.get("use_remote"):
        rip = str(fields.get("remote_ip") or "").strip()
        rport = parse_port(fields.get("remote_port"))
        if not is_valid_ip(rip):
            return _toast_err("err_bad_ip")
        if rport is None:
            return _toast_err("err_bad_port")
    else:
        rip, rport = "", 0
    return {"ok": True, "local_ip": local_ip, "lport": lport, "rip": rip, "rport": rport}


def open_fields_from_ui(proto, ui):
    """Build validate_open fields dict from a flat UI snapshot."""
    u = ui if isinstance(ui, dict) else {}
    proto = str(proto or "")
    if proto == "Serial":
        return {"port": u.get("port"), "baud": u.get("baud")}
    if proto == "Virtual":
        return {}
    if proto == "TCP Client":
        return {"remote_ip": u.get("remote_ip"), "remote_port": u.get("remote_port")}
    if proto == "UDP Multicast":
        return {
            "local_ip": u.get("local_ip"), "local_port": u.get("local_port"),
            "group": u.get("group"),
        }
    if proto == "TCP Server":
        return {"local_ip": u.get("local_ip"), "local_port": u.get("local_port")}
    if proto == "BLE":
        return {
            "address": u.get("ble_address") or u.get("address"),
            "service_uuid": u.get("ble_service_uuid") or u.get("service_uuid"),
            "write_uuid": u.get("ble_write_uuid") or u.get("write_uuid"),
            "notify_uuid": u.get("ble_notify_uuid") or u.get("notify_uuid"),
        }
    return {
        "local_ip": u.get("local_ip"), "local_port": u.get("local_port"),
        "use_remote": u.get("use_remote"),
        "remote_ip": u.get("remote_ip"), "remote_port": u.get("remote_port"),
    }


def open_fields_from_reconnect(reconnect_cfg):
    """Serial reconnect_cfg tuple -> (proto, fields)."""
    cfg = tuple(reconnect_cfg or ())
    if not cfg:
        return "", {}
    proto = cfg[0]
    if proto == "Serial" and len(cfg) >= 3:
        return proto, {"port": cfg[1], "baud": cfg[2]}
    return proto, {}


def serial_extras_from_reconnect(reconnect_cfg):
    """(databits, parity, stopbits, flow) or None if incomplete."""
    cfg = tuple(reconnect_cfg or ())
    if len(cfg) < 6:
        return None
    flow = cfg[6] if len(cfg) > 6 else None
    return cfg[3], cfg[4], cfg[5], flow

