# -*- coding: utf-8 -*-
"""BLE UART UUID helpers (Qt-free).

Normalize 16/32/128-bit UUID text, compare, swap write/notify, and apply
named UART-style presets. Product combo labels stay English identifiers.
"""
from __future__ import annotations

import re

BT_BASE_SUFFIX = "-0000-1000-8000-00805f9b34fb"
_HEX = re.compile(r"^[0-9a-f]+$")
_DASHED_128 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Nordic UART Service (NUS): write = RX characteristic (phone → device),
# notify = TX characteristic (device → phone).
NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# FFF0 write/notify are templates (common Chinese BLE UART: FFF2 write,
# FFF1 notify). Confirm on-device with scripts/ble_probe.py before treating
# a DUT's sub-characteristics as gospel; the UI always offers Swap.
PROFILE_FFF0 = "fff0"
PROFILE_FFE0 = "ffe0"
PROFILE_NUS = "nus"
PROFILE_CUSTOM = "custom"

PROFILES = (
    PROFILE_FFF0,
    PROFILE_FFE0,
    PROFILE_NUS,
    PROFILE_CUSTOM,
)

# (id, service, write PC→device, notify device→PC)
_PROFILE_UUIDS = {
    PROFILE_FFF0: ("fff0", "fff2", "fff1"),
    PROFILE_FFE0: ("ffe0", "ffe1", "ffe1"),
    PROFILE_NUS: (NUS_SERVICE, NUS_WRITE, NUS_NOTIFY),
}

PROFILE_LABELS = {
    PROFILE_FFF0: "FFF0",
    PROFILE_FFE0: "FFE0",
    PROFILE_NUS: "Nordic UART",
    PROFILE_CUSTOM: "Custom",
}


def _strip_uuid_text(text):
    s = str(text or "").strip().lower()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    if s.startswith("0x"):
        s = s[2:]
    return s.replace(" ", "")


def normalize_uuid(text):
    """Return lowercase dashed 128-bit UUID, or "" if invalid / empty."""
    s = _strip_uuid_text(text)
    if not s:
        return ""
    if _DASHED_128.match(s):
        return s
    hex_only = s.replace("-", "")
    if not _HEX.match(hex_only):
        return ""
    if len(hex_only) == 4:
        return "0000%s%s" % (hex_only, BT_BASE_SUFFIX)
    if len(hex_only) == 8:
        return "%s%s" % (hex_only, BT_BASE_SUFFIX)
    if len(hex_only) == 32:
        return "%s-%s-%s-%s-%s" % (
            hex_only[0:8], hex_only[8:12], hex_only[12:16],
            hex_only[16:20], hex_only[20:32])
    return ""


def is_valid_uuid(text, *, allow_empty=False):
    s = str(text or "").strip()
    if not s:
        return bool(allow_empty)
    return bool(normalize_uuid(s))


def uuids_equal(a, b):
    na, nb = normalize_uuid(a), normalize_uuid(b)
    return bool(na) and na == nb


def short_uuid(text):
    """Compact display: 16-bit alias when on the Bluetooth base UUID."""
    n = normalize_uuid(text)
    if not n:
        return str(text or "").strip()
    if n.endswith(BT_BASE_SUFFIX) and n.startswith("0000"):
        body = n[:8]
        if body.startswith("0000"):
            return body[4:].upper()
        return body.upper()
    return n


def swap_write_notify(write_uuid, notify_uuid):
    """Swap write (PC→device) and notify (device→PC) UUID strings as-is."""
    return str(notify_uuid or ""), str(write_uuid or "")


def normalize_profile(profile_id):
    pid = str(profile_id or "").strip().lower()
    if pid in ("nordic", "nordic uart", "nus"):
        return PROFILE_NUS
    if pid in PROFILES:
        return pid
    return PROFILE_CUSTOM


def preset_uuids(profile_id):
    """Return (service, write, notify) normalized, or None for Custom."""
    pid = normalize_profile(profile_id)
    raw = _PROFILE_UUIDS.get(pid)
    if not raw:
        return None
    return tuple(normalize_uuid(x) for x in raw)


def apply_preset(profile_id, current=None):
    """Fill service/write/notify from a named preset.

    Custom keeps ``current`` (dict) values. Returns a dict with
    ``profile``, ``service_uuid``, ``write_uuid``, ``notify_uuid``.
    """
    current = current if isinstance(current, dict) else {}
    pid = normalize_profile(profile_id)
    filled = preset_uuids(pid)
    if filled is None:
        return {
            "profile": PROFILE_CUSTOM,
            "service_uuid": normalize_uuid(current.get("service_uuid", "")),
            "write_uuid": normalize_uuid(current.get("write_uuid", "")),
            "notify_uuid": normalize_uuid(current.get("notify_uuid", "")),
        }
    service, write, notify = filled
    return {
        "profile": pid,
        "service_uuid": service,
        "write_uuid": write,
        "notify_uuid": notify,
    }


def match_profile(service_uuid, write_uuid, notify_uuid):
    """Best matching preset id, or Custom if none match."""
    svc, wr, ntf = (
        normalize_uuid(service_uuid),
        normalize_uuid(write_uuid),
        normalize_uuid(notify_uuid),
    )
    for pid, raw in _PROFILE_UUIDS.items():
        ps, pw, pn = (normalize_uuid(x) for x in raw)
        if svc == ps and wr == pw and ntf == pn:
            return pid
    return PROFILE_CUSTOM


def normalize_address(text):
    """Uppercase BLE address (colon-separated); empty if blank."""
    s = str(text or "").strip().replace("-", ":")
    if not s:
        return ""
    return s.upper()


def is_valid_address(text):
    s = normalize_address(text)
    if not s:
        return False
    parts = s.split(":")
    if len(parts) != 6:
        return False
    for p in parts:
        if len(p) != 2 or not _HEX.match(p.lower()):
            return False
    return True
