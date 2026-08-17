# -*- coding: utf-8 -*-
"""BLE UART UUID helpers (Qt-free).

Normalize 16/32/128-bit UUID text, compare, swap write/notify, and apply
named UART-style presets. Product combo labels stay English identifiers.
"""
from __future__ import annotations

import re

BT_BASE_SUFFIX = "-0000-1000-8000-00805f9b34fb"
# Bluetooth base UUID without hyphens, minus the first 8 hex (used to expand 16/32-bit).
_BT_BASE_REST_HEX = "00001000800000805f9b34fb"
_HEX = re.compile(r"^[0-9a-f]+$")
_DASHED_128 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Nordic UART Service (NUS): write = RX characteristic (phone → device),
# notify = TX characteristic (device → phone).
NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Microchip RN4870 / BM70 transparent UART (Serial Bluetooth Terminal mapping).
MICROCHIP_SERVICE = "49535343-fe7d-4ae5-8fa9-9fafd205e455"
MICROCHIP_WRITE = "49535343-8841-43f4-a8d4-ecbe34729bb3"
MICROCHIP_NOTIFY = "49535343-1e4d-4bd9-ba61-23c647249616"

# FFF0 write/notify are templates (common Chinese BLE UART: FFF2 write,
# FFF1 notify). Confirm on-device with scripts/ble_probe.py before treating
# a DUT's sub-characteristics as gospel; the UI always offers Swap.
PROFILE_FFF0 = "fff0"
PROFILE_FFE0 = "ffe0"
PROFILE_NUS = "nus"
PROFILE_MICROCHIP = "microchip"
PROFILE_CUSTOM = "custom"

PROFILES = (
    PROFILE_FFF0,
    PROFILE_FFE0,
    PROFILE_NUS,
    PROFILE_MICROCHIP,
    PROFILE_CUSTOM,
)

# (id, service, write PC→device, notify device→PC)
_PROFILE_UUIDS = {
    PROFILE_FFF0: ("fff0", "fff2", "fff1"),
    PROFILE_FFE0: ("ffe0", "ffe1", "ffe1"),
    PROFILE_NUS: (NUS_SERVICE, NUS_WRITE, NUS_NOTIFY),
    PROFILE_MICROCHIP: (MICROCHIP_SERVICE, MICROCHIP_WRITE, MICROCHIP_NOTIFY),
}

PROFILE_LABELS = {
    PROFILE_FFF0: "FFF0",
    PROFILE_FFE0: "FFE0",
    PROFILE_NUS: "Nordic UART",
    PROFILE_MICROCHIP: "Microchip UART",
    PROFILE_CUSTOM: "Custom",
}

WRITE_MODE_AUTO = "auto"
WRITE_MODE_WRITE = "write"
WRITE_MODE_WWR = "wwr"
WRITE_MODES = (WRITE_MODE_AUTO, WRITE_MODE_WRITE, WRITE_MODE_WWR)
WRITE_MODE_LABELS = {
    WRITE_MODE_AUTO: "Auto",
    WRITE_MODE_WRITE: "Write",
    WRITE_MODE_WWR: "Write NR",
}


def _strip_uuid_text(text):
    s = str(text or "").strip().lower()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    if s.startswith("0x"):
        s = s[2:]
    return s.replace(" ", "")


def _dash_128(hex32):
    """Insert hyphens into a 32-char hex UUID (lowercase)."""
    return "%s-%s-%s-%s-%s" % (
        hex32[0:8], hex32[8:12], hex32[12:16], hex32[16:20], hex32[20:32])


def normalize_uuid(text):
    """Return lowercase dashed 128-bit UUID, or "" if invalid / empty.

    16-bit (``FFF0``) and 32-bit aliases expand onto the Bluetooth base UUID
    and always use the same hyphenated form as a full 128-bit string, so
    ``uuids_equal("FFF0", "0000FFF0-0000-1000-8000-00805F9B34FB")``.
    """
    s = _strip_uuid_text(text)
    if not s:
        return ""
    if _DASHED_128.match(s):
        return s
    hex_only = s.replace("-", "")
    if not _HEX.match(hex_only):
        return ""
    if len(hex_only) == 4:
        hex_only = "0000" + hex_only + _BT_BASE_REST_HEX
    elif len(hex_only) == 8:
        hex_only = hex_only + _BT_BASE_REST_HEX
    if len(hex_only) == 32:
        return _dash_128(hex_only)
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


def sanitize_ble_name(text):
    """Strip BLE AD leftovers / replacement chars; empty if not a usable name.

    Common debug apps hide unnamed and garbage names. A leading type/length
    byte (e.g. ``\\x04BLGW``) and U+FFFD are dropped. Latin-1 mojibake of
    GBK/UTF-8 is recovered when possible.
    """
    if text is None:
        return ""
    if isinstance(text, (bytes, bytearray)):
        s = _decode_ble_name_bytes(bytes(text))
    else:
        s = str(text)
    s = s.replace("\x00", "").replace("\ufffd", "")
    recovered = _maybe_fix_mojibake(s)
    if recovered:
        s = recovered
    out = []
    for ch in s:
        o = ord(ch)
        if o < 32 or o == 127 or (0x80 <= o < 0xA0):
            continue
        out.append(ch)
    return "".join(out).strip()


def name_from_raw_sections(sections):
    """Complete Local Name (0x09) wins over Shortened Local Name (0x08)."""
    short, complete = "", ""
    for typ, hx in sections or []:
        try:
            code = int(typ)
            raw = bytes.fromhex(str(hx or ""))
        except (TypeError, ValueError):
            continue
        label = sanitize_ble_name(raw)
        if not label:
            continue
        if code == _AD_TYPE_NAME_COMPLETE:
            complete = label
        elif code == _AD_TYPE_NAME_SHORT and not short:
            short = label
    return complete or short


def adv_local_name(device_name=None, adv=None, snap=None):
    """Best usable name: Bleak fields, then AD 0x08/0x09 in the snapshot."""
    snap = snap or {}
    adv_name = ""
    if adv is not None:
        if isinstance(adv, dict):
            adv_name = adv.get("local_name") or ""
        else:
            adv_name = getattr(adv, "local_name", None) or ""
    for candidate in (device_name, adv_name, snap.get("local_name")):
        n = sanitize_ble_name(candidate)
        if n:
            return n
    return name_from_raw_sections(snap.get("raw_sections"))


def _decode_ble_name_bytes(raw):
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            t = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if t and "\ufffd" not in t:
            return t
    return raw.decode("latin-1", "replace")


def _maybe_fix_mojibake(s):
    try:
        raw = s.encode("latin-1")
    except UnicodeEncodeError:
        return ""
    if not raw or all(b < 0x80 for b in raw):
        return ""
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            t = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if t and "\ufffd" not in t and t != s:
            return t
    return ""


def _uuid_text(raw):
    if raw is None:
        return ""
    if hasattr(raw, "uuid") and not isinstance(raw, (str, bytes)):
        raw = getattr(raw, "uuid", raw)
    try:
        return str(raw)
    except Exception:
        return ""


def merge_uuid_lists(*groups):
    """Stable unique UUID list; prefer normalized 128-bit form when valid."""
    out = []
    seen = set()
    for group in groups:
        for raw in group or []:
            text = _uuid_text(raw).strip()
            n = normalize_uuid(text)
            key = n or text.lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(n or text)
    return out


def adv_service_uuids(adv=None, service_uuids=None, service_data=None):
    """Advertised service UUIDs: ``service_uuids`` plus ``service_data`` keys."""
    uuids = service_uuids
    data = service_data
    if adv is not None:
        if uuids is None:
            uuids = getattr(adv, "service_uuids", None)
        if data is None:
            data = getattr(adv, "service_data", None)
    extra = []
    if data:
        try:
            extra = list(data)
        except TypeError:
            extra = []
    return merge_uuid_lists(uuids, extra)


def format_adv_uuids(uuids, empty="-"):
    """Comma-separated short UUIDs for tables; 16-bit aliases when possible."""
    parts = []
    for u in merge_uuid_lists(uuids):
        parts.append(short_uuid(u) or u)
    return ", ".join(parts) if parts else empty


def format_adv_uuids_full(uuids, empty=""):
    """One normalized UUID per line (tooltip)."""
    parts = []
    for u in merge_uuid_lists(uuids):
        parts.append(normalize_uuid(u) or u)
    return "\n".join(parts) if parts else empty


_MFR_PREVIEW_BYTES = 8
_AD_TYPE_FLAGS = 0x01
_AD_TYPE_NAME_SHORT = 0x08
_AD_TYPE_NAME_COMPLETE = 0x09
_AD_TYPE_TX = 0x0A
_AD_TYPE_APPEARANCE = 0x19
_AD_TYPE_MFR = 0xFF
_AD_TYPE_SVC16 = 0x16
# AD Length is one octet covering type + data, so payload max is 254.
_AD_DATA_MAX = 254

# SIG Appearance generic categories (value & ~0x3F) plus a few common subtypes.
_APPEARANCE = {
    0x0000: "Unknown",
    0x0040: "Generic Phone",
    0x0080: "Generic Computer",
    0x00C0: "Generic Watch",
    0x00C1: "Sports Watch",
    0x0100: "Generic Clock",
    0x0140: "Generic Display",
    0x0180: "Generic Remote Control",
    0x01C0: "Generic Eye-glasses",
    0x0200: "Generic Tag",
    0x0240: "Generic Keyring",
    0x0280: "Generic Media Player",
    0x02C0: "Generic Barcode Scanner",
    0x0300: "Generic Thermometer",
    0x0340: "Generic Heart Rate Sensor",
    0x0380: "Generic Blood Pressure",
    0x03C0: "Generic HID",
    0x03C1: "Keyboard",
    0x03C2: "Mouse",
    0x03C3: "Joystick",
    0x03C4: "Gamepad",
    0x0400: "Generic Glucose Meter",
    0x0440: "Generic Running Walking Sensor",
    0x0480: "Generic Cycling",
    0x0C40: "Generic Pulse Oximeter",
    0x0C80: "Generic Weight Scale",
    0x0D00: "Generic Personal Mobility Device",
    0x0D40: "Generic Continuous Glucose Monitor",
    0x0D80: "Generic Insulin Pump",
    0x0DC0: "Generic Medication Delivery",
    0x1440: "Generic Outdoor Sports Activity",
}

FLAG_BITS = (
    (0x01, "le_limited"),
    (0x02, "le_general"),
    (0x04, "bredr_not"),
    (0x08, "sim_ctrl"),
    (0x10, "sim_host"),
)

_COMPANY_FALLBACK = {
    0x0006: "Microsoft",
    0x000D: "Texas Instruments Inc.",
    0x004C: "Apple, Inc.",
    0x0059: "Nordic Semiconductor ASA",
    0x00E0: "Google",
    0x02E5: "Espressif Inc.",
    0x038F: "Xiaomi Inc.",
}

_WINRT_ADV_TYPE = {
    0: "ADV_IND",
    1: "ADV_DIRECT_IND",
    2: "ADV_SCAN_IND",
    3: "ADV_NONCONN_IND",
    4: "SCAN_RSP",
    5: "ADV_EXT",
}

_manufacturer_map_cache = None


def _manufacturer_map():
    global _manufacturer_map_cache
    if _manufacturer_map_cache is not None:
        return _manufacturer_map_cache
    out = dict(_COMPANY_FALLBACK)
    try:
        from bleak.backends._manufacturers import MANUFACTURERS
        out.update(MANUFACTURERS)
    except ImportError:
        pass
    _manufacturer_map_cache = out
    return out


def company_name(cid):
    try:
        n = int(cid)
    except (TypeError, ValueError):
        return ""
    return str(_manufacturer_map().get(n) or "")


def format_company(cid):
    try:
        n = int(cid)
    except (TypeError, ValueError):
        return str(cid or "")
    name = company_name(n)
    if name:
        return "%s (%04X)" % (name, n)
    return "%04X" % n


def appearance_label(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    n = n & 0xFFFF
    name = _APPEARANCE.get(n) or _APPEARANCE.get(n & ~0x3F)
    hexv = "0x%04X" % n
    if name:
        return "%s (%s)" % (name, hexv)
    return hexv


def adv_flag_keys(flags):
    try:
        n = int(flags)
    except (TypeError, ValueError):
        return []
    return [key for bit, key in FLAG_BITS if n & bit]


def rssi_bars(rssi):
    try:
        n = int(rssi)
    except (TypeError, ValueError):
        return ""
    if n >= -50:
        filled = 4
    elif n >= -65:
        filled = 3
    elif n >= -80:
        filled = 2
    elif n >= -95:
        filled = 1
    else:
        filled = 0
    glyphs = "▂▄▆█"
    return glyphs[:filled] + (" " * (4 - filled))


def format_rssi_cell(rssi, empty=""):
    try:
        n = int(rssi)
    except (TypeError, ValueError):
        return empty
    bars = rssi_bars(n).rstrip()
    if bars:
        return "%s %d" % (bars, n)
    return str(n)


def empty_adv_snapshot():
    return {
        "tx_power": None,
        "connectable": None,
        "manufacturer": [],
        "service_data": [],
        "appearance": None,
        "advertisement_type": "",
        "flags": None,
        "raw_sections": [],
        "local_name": "",
    }


def _payload_hex(raw):
    if raw is None:
        return ""
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).hex()
    return ""


def _adv_type_text(raw):
    if raw is None:
        return ""
    name = getattr(raw, "name", None)
    if name:
        return str(name)
    text = str(raw).strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _mapping_pairs(raw):
    if not raw:
        return []
    try:
        return list(raw.items())
    except (TypeError, AttributeError):
        return []


def snapshot_advertisement(adv=None):
    """Plain dict from Bleak AdvertisementData (safe to queue across threads).

    Also accepts an already-normalized snapshot (``manufacturer`` is a list).
    """
    empty = empty_adv_snapshot()
    if adv is None:
        return empty
    if isinstance(adv, dict) and isinstance(adv.get("manufacturer"), list):
        out = empty_adv_snapshot()
        for key in out:
            if key not in adv:
                continue
            val = adv[key]
            if key in ("manufacturer", "service_data", "raw_sections"):
                out[key] = list(val or [])
            else:
                out[key] = val
        return out
    get = adv.get if isinstance(adv, dict) else (
        lambda key, default=None: getattr(adv, key, default))
    mfr = []
    for cid, payload in _mapping_pairs(get("manufacturer_data")):
        try:
            cid_n = int(cid)
        except (TypeError, ValueError):
            continue
        mfr.append((cid_n, _payload_hex(payload)))
    svc = []
    for uid, payload in _mapping_pairs(get("service_data")):
        text = _uuid_text(uid).strip()
        if not text:
            continue
        svc.append((text, _payload_hex(payload)))
    tx = get("tx_power")
    try:
        tx = int(tx) if tx is not None else None
    except (TypeError, ValueError):
        tx = None
    conn = get("connectable")
    if conn is not None:
        conn = bool(conn)
    appearance = get("appearance")
    try:
        appearance = int(appearance) if appearance is not None else None
    except (TypeError, ValueError):
        appearance = None
    flags = get("flags")
    try:
        flags = int(flags) if flags is not None else None
    except (TypeError, ValueError):
        flags = None
    raw_sections = []
    for item in get("raw_sections") or []:
        try:
            typ, hx = item[0], item[1]
            raw_sections.append((int(typ), str(hx or "")))
        except (TypeError, ValueError, IndexError):
            continue
    out = {
        "tx_power": tx,
        "connectable": conn,
        "manufacturer": mfr,
        "service_data": svc,
        "appearance": appearance,
        "advertisement_type": _adv_type_text(get("advertisement_type")),
        "flags": flags,
        "raw_sections": raw_sections,
        "local_name": sanitize_ble_name(get("local_name") or ""),
    }
    _enrich_from_platform(adv, out)
    if not out.get("local_name"):
        out["local_name"] = name_from_raw_sections(out.get("raw_sections"))
    return out


def _merge_adv_types(*texts):
    parts = []
    for text in texts:
        for item in str(text or "").split("+"):
            item = item.strip()
            if item and item not in parts:
                parts.append(item)
    return " + ".join(parts)


def _winrt_events(adv):
    pdata = getattr(adv, "platform_data", None)
    if not pdata:
        return []
    try:
        raw_pair = pdata[1] if len(pdata) >= 2 else None
    except (TypeError, IndexError):
        return []
    if raw_pair is None:
        return []
    events = []
    for attr in ("adv", "scan"):
        ev = getattr(raw_pair, attr, None)
        if ev is not None:
            events.append(ev)
    if not events:
        try:
            events = [x for x in raw_pair if x is not None]
        except TypeError:
            events = []
    return events


def _enrich_from_platform(adv, out):
    """Copy Flags / Appearance / type / RAW sections from WinRT platform_data."""
    events = _winrt_events(adv)
    if not events:
        return
    flags = out.get("flags")
    appearance = out.get("appearance")
    kinds = []
    if out.get("advertisement_type"):
        kinds.append(out["advertisement_type"])
    sections = list(out.get("raw_sections") or [])
    connectable = out.get("connectable")
    seen_sec = set(sections)
    for ev in events:
        try:
            at = getattr(ev, "advertisement_type", None)
            if at is not None:
                try:
                    code = int(at)
                except (TypeError, ValueError):
                    code = None
                name = _WINRT_ADV_TYPE.get(code, _adv_type_text(at))
                if name and name not in kinds:
                    kinds.append(name)
                if code in (0, 1):
                    connectable = True
                elif code in (2, 3) and connectable is None:
                    connectable = False
            advertisement = getattr(ev, "advertisement", None)
            if advertisement is None:
                continue
            ln = sanitize_ble_name(getattr(advertisement, "local_name", None) or "")
            if ln and not out.get("local_name"):
                out["local_name"] = ln
            fl = getattr(advertisement, "flags", None)
            if fl is not None:
                try:
                    n = int(fl)
                    flags = n if flags is None else (int(flags) | n)
                except (TypeError, ValueError):
                    pass
            try:
                sec_iter = advertisement.data_sections
            except Exception:
                sec_iter = ()
            for sec in sec_iter or ():
                try:
                    typ = int(getattr(sec, "data_type"))
                    data = bytes(getattr(sec, "data") or b"")
                except (TypeError, ValueError, AttributeError):
                    continue
                item = (typ, data.hex())
                if item not in seen_sec:
                    seen_sec.add(item)
                    sections.append(item)
                if typ == _AD_TYPE_APPEARANCE and appearance is None and len(data) >= 2:
                    appearance = int.from_bytes(data[:2], "little")
                if typ == _AD_TYPE_FLAGS and flags is None and data:
                    flags = data[0]
        except Exception:
            continue
    out["flags"] = flags
    out["appearance"] = appearance
    out["raw_sections"] = sections
    if not out.get("local_name"):
        out["local_name"] = name_from_raw_sections(sections)
    if kinds:
        out["advertisement_type"] = " + ".join(kinds)
    if connectable is not None:
        out["connectable"] = connectable


def merge_adv_snapshots(old, new):
    """Union advertisement fields; later packets fill in missing details."""
    old = snapshot_advertisement(old) if old else empty_adv_snapshot()
    new = snapshot_advertisement(new) if new else empty_adv_snapshot()
    out = empty_adv_snapshot()
    out["tx_power"] = (
        new["tx_power"] if new["tx_power"] is not None else old["tx_power"])
    # Sticky True: WinRT often mixes ADV_IND with a later non-connectable
    # scan response; "seen as connectable this scan" is what the UART picker wants.
    if new["connectable"] is True or old["connectable"] is True:
        out["connectable"] = True
    elif new["connectable"] is False or old["connectable"] is False:
        out["connectable"] = False
    out["appearance"] = (
        new["appearance"] if new["appearance"] is not None else old["appearance"])
    out["local_name"] = new.get("local_name") or old.get("local_name") or ""
    out["advertisement_type"] = _merge_adv_types(
        old["advertisement_type"], new["advertisement_type"])
    if new["flags"] is not None and old["flags"] is not None:
        out["flags"] = int(old["flags"]) | int(new["flags"])
    else:
        out["flags"] = (
            new["flags"] if new["flags"] is not None else old["flags"])
    seen_sec, sections = set(), []
    for item in list(old["raw_sections"]) + list(new["raw_sections"]):
        if item in seen_sec:
            continue
        seen_sec.add(item)
        sections.append(item)
    out["raw_sections"] = sections
    order, payloads = [], {}
    for cid, hx in list(old["manufacturer"]) + list(new["manufacturer"]):
        if cid not in payloads:
            order.append(cid)
        payloads[cid] = hx
    out["manufacturer"] = [(cid, payloads[cid]) for cid in order]
    svc_order, svc_map = [], {}
    for uid, hx in list(old["service_data"]) + list(new["service_data"]):
        key = normalize_uuid(uid) or str(uid).lower()
        if key not in svc_map:
            svc_order.append(key)
        svc_map[key] = (uid, hx)
    out["service_data"] = [svc_map[key] for key in svc_order]
    return out


def format_mfr_preview(snapshot, empty="-"):
    """Short manufacturer column: company ID + first payload bytes."""
    pairs = (snapshot or {}).get("manufacturer") or []
    if not pairs:
        return empty
    limit = _MFR_PREVIEW_BYTES * 2
    parts = []
    for cid, hx in pairs:
        body = (hx or "")[:limit]
        if len(hx or "") > limit:
            body += "…"
        label = format_company(cid)
        if body:
            parts.append("%s %s" % (label, body))
        else:
            parts.append(label)
    return ", ".join(parts)


def format_hex_spaced(hx):
    hx = str(hx or "")
    return " ".join(hx[i:i + 2] for i in range(0, len(hx), 2)).upper()


def _reconstruct_sections(snap, uuids=None):
    sections = []
    flags = (snap or {}).get("flags")
    if flags is not None:
        sections.append((_AD_TYPE_FLAGS, "%02x" % (int(flags) & 0xFF)))
    appearance = (snap or {}).get("appearance")
    if appearance is not None:
        sections.append((
            _AD_TYPE_APPEARANCE,
            int(appearance).to_bytes(2, "little").hex()))
    tx = (snap or {}).get("tx_power")
    if tx is not None:
        try:
            sections.append((
                _AD_TYPE_TX,
                int(tx).to_bytes(1, "little", signed=True).hex()))
        except (OverflowError, ValueError):
            pass
    for uid in merge_uuid_lists(uuids):
        n = normalize_uuid(uid)
        if n and n.endswith(BT_BASE_SUFFIX) and n.startswith("0000"):
            alias = n[4:8]
            try:
                raw = int(alias, 16).to_bytes(2, "little").hex()
            except ValueError:
                continue
            sections.append((0x03, raw))
    for uid, hx in (snap or {}).get("service_data") or []:
        n = normalize_uuid(uid)
        payload = str(hx or "")
        if n and n.endswith(BT_BASE_SUFFIX) and n.startswith("0000"):
            try:
                head = int(n[4:8], 16).to_bytes(2, "little").hex()
            except ValueError:
                head = ""
            if head:
                sections.append((_AD_TYPE_SVC16, head + payload))
                continue
        sections.append((_AD_TYPE_SVC16, payload))
    for cid, hx in (snap or {}).get("manufacturer") or []:
        try:
            head = int(cid).to_bytes(2, "little").hex()
        except (TypeError, ValueError, OverflowError):
            continue
        sections.append((_AD_TYPE_MFR, head + str(hx or "")))
    return sections


def _ad_records(typ, data):
    """Emit one or more legal BLE AD structures for ``data``.

    Length is a single octet (type + payload). Payloads longer than 254 bytes
    are split into same-type structures so the dump stays parseable; the
    length field is never wrapped with ``& 0xFF``.
    """
    ad_type = int(typ) & 0xFF
    if not data:
        return (bytes((1, ad_type)),)
    recs = []
    for off in range(0, len(data), _AD_DATA_MAX):
        chunk = data[off:off + _AD_DATA_MAX]
        recs.append(bytes((len(chunk) + 1, ad_type)) + chunk)
    return tuple(recs)


def format_raw_hex(snap, uuids=None):
    """Return (spaced HEX, rebuilt). rebuilt True if AD was reconstructed."""
    sections = list((snap or {}).get("raw_sections") or [])
    rebuilt = not bool(sections)
    if rebuilt:
        sections = _reconstruct_sections(snap, uuids)
    blob = []
    for typ, hx in sections:
        try:
            recs = _ad_records(typ, bytes.fromhex(str(hx or "")))
        except (TypeError, ValueError):
            continue
        blob.extend(rec.hex() for rec in recs)
    return format_hex_spaced("".join(blob)), rebuilt


def search_blob_for_adv(snapshot):
    """Lowercase haystack: company IDs, payloads, type, appearance."""
    snap = snapshot or {}
    parts = [str(snap.get("advertisement_type") or "")]
    if snap.get("appearance") is not None:
        parts.append("%04x" % int(snap["appearance"]))
        parts.append(str(int(snap["appearance"])))
        parts.append(appearance_label(snap["appearance"]))
    if snap.get("flags") is not None:
        parts.append("%02x" % int(snap["flags"]))
        parts.extend(adv_flag_keys(snap["flags"]))
    if snap.get("tx_power") is not None:
        parts.append(str(snap["tx_power"]))
    conn = snap.get("connectable")
    if conn is True:
        parts.append("connectable")
    elif conn is False:
        parts.append("nonconnectable")
    for cid, hx in snap.get("manufacturer") or []:
        parts.append("%04x" % int(cid))
        parts.append(str(int(cid)))
        parts.append(hx or "")
        parts.append(format_hex_spaced(hx))
        parts.append(company_name(cid))
    for uid, hx in snap.get("service_data") or []:
        parts.append(str(uid))
        parts.append(short_uuid(uid))
        parts.append(hx or "")
        parts.append(format_hex_spaced(hx))
    return " ".join(parts).lower()


def swap_write_notify(write_uuid, notify_uuid):
    """Swap write (PC→device) and notify (device→PC) UUID strings as-is."""
    return str(notify_uuid or ""), str(write_uuid or "")


def normalize_profile(profile_id):
    pid = str(profile_id or "").strip().lower()
    if pid in ("nordic", "nordic uart", "nus"):
        return PROFILE_NUS
    if pid in ("microchip", "microchip uart", "rn4870", "bm70"):
        return PROFILE_MICROCHIP
    if pid in PROFILES:
        return pid
    return PROFILE_CUSTOM


def normalize_write_mode(mode):
    s = str(mode or "").strip().lower().replace("_", "-").replace(" ", "")
    if s in ("write", "wr", "withresponse"):
        return WRITE_MODE_WRITE
    if s in ("wwr", "writenr", "write-without-response", "writenoresponse",
             "noresponse"):
        return WRITE_MODE_WWR
    return WRITE_MODE_AUTO


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
