# -*- coding: utf-8 -*-
"""设备寄存器定义、Modbus 标签解码与结构化记录纯逻辑。"""

import csv
import logging
import math
import os
import struct
import time

_LOG = logging.getLogger(__name__)


REGISTER_TYPES = ("u16", "i16", "u32", "i32", "f32", "u64", "i64", "f64", "bit")
REGISTER_ORDERS = (
    "AB", "BA",
    "ABCD", "CDAB", "BADC", "DCBA",
    "ABCDEFGH", "GHEFCDAB", "BADCFEHG", "HGFEDCBA",
)
STRUCTURED_COLUMNS = (
    "timestamp", "source", "tag", "value", "unit", "raw",
    "slave", "function", "address", "display_address", "level",
)
_MAX_ROWS = 200000
_MAX_CSV_BYTES = 64 << 20


def _int(value, default, lo, hi):
    try:
        if isinstance(value, str):
            text = value.strip()
            base = 0 if text[:2].lower() in ("0x", "0o", "0b") else 10
            out = int(text, base)
        else:
            out = int(value)
    except (TypeError, ValueError):
        return default
    return out if lo <= out <= hi else default


def _float(value, default):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def register_width(data_type):
    typ = str(data_type)
    if typ in ("u64", "i64", "f64"):
        return 4
    if typ in ("u32", "i32", "f32"):
        return 2
    return 1


def normalize_register(record):
    """把一条设备寄存器定义规范化为稳定、可序列化的字典。"""
    record = dict(record or {})
    data_type = str(record.get("type", "u16")).lower()
    if data_type not in REGISTER_TYPES:
        data_type = "u16"
    width = register_width(data_type)
    if width == 4:
        default_order = "ABCDEFGH"
    elif width == 2:
        default_order = "ABCD"
    else:
        default_order = "AB"
    order = str(record.get("order", default_order)).upper()
    if order not in REGISTER_ORDERS:
        order = default_order
    if width == 1 and order not in ("AB", "BA"):
        order = "AB"
    if width == 2 and order in ("AB", "BA"):
        order = default_order
    if width == 4 and len(order) != 8:
        order = default_order
    addr_base = _int(record.get("addr_base", 0), 0, 0, 1)
    if record.get("display_address") not in (None, "") and \
            record.get("address") in (None, ""):
        # 界面上填的是按所选地址基显示的地址，这里换回协议用的 0 基地址。
        # 解码和匹配一律用 0 基，addr_base 只影响显示。
        address = _int(record["display_address"], addr_base,
                       addr_base, 0xFFFF + addr_base) - addr_base
    else:
        address = _int(record.get("address", 0), 0, 0, 0xFFFF)
    bit = _int(record.get("bit", 0), 0, 0, 15)

    def _opt_float(key):
        if key not in record or record.get(key) in (None, ""):
            return None
        return _float(record.get(key), None)

    bitfields = str(record.get("bitfields", "") or "")[:200]
    return {
        "enabled": _bool(record.get("enabled", True)),
        "name": str(record.get("name") or "R%d" % address)[:80],
        "slave": _int(record.get("slave", 1), 1, 0, 255),
        "function": _int(record.get("function", 3), 3, 3, 4),
        "address": address,
        "addr_base": addr_base,
        "display_address": address + addr_base,
        "type": data_type,
        "order": order,
        "bit": bit,
        "bitfields": bitfields,
        "scale": _float(record.get("scale", 1), 1.0),
        "offset": _float(record.get("offset", 0), 0.0),
        "unit": str(record.get("unit", ""))[:32],
        "warn_lo": _opt_float("warn_lo"),
        "warn_hi": _opt_float("warn_hi"),
        "alarm_lo": _opt_float("alarm_lo"),
        "alarm_hi": _opt_float("alarm_hi"),
    }


def normalize_registers(records):
    if not isinstance(records, list):
        return []
    return [normalize_register(item) for item in records if isinstance(item, dict)][:2000]


def _ordered_bytes(registers, order):
    raw = b"".join(struct.pack(">H", int(value) & 0xFFFF) for value in registers)
    if len(raw) == 2:
        labels = "AB"
    elif len(raw) == 4:
        labels = "ABCD"
    elif len(raw) == 8:
        labels = "ABCDEFGH"
    else:
        return raw
    if sorted(order) != sorted(labels):
        order = labels
    return bytes(raw[labels.index(ch)] for ch in order)


def parse_bitfields(text):
    """Parse 'start:width:name,...' into [(start, width, name), ...]."""
    out = []
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        toks = part.split(":")
        if len(toks) < 2:
            continue
        try:
            start = int(toks[0].strip(), 0)
            width = int(toks[1].strip(), 0)
        except ValueError:
            continue
        if not 0 <= start <= 63 or not 1 <= width <= 64 or start + width > 64:
            continue
        name = (toks[2].strip() if len(toks) >= 3 else "b%d" % start)[:40]
        out.append((start, width, name or ("b%d" % start)))
        # Check for overlap with existing bitfields
        for (es, ew, en) in out[:-1]:
            if not (start + width <= es or es + ew <= start):
                _LOG.warning("bitfield '%s' (%d:%d) overlaps with '%s' (%d:%d)",
                            name, start, start + width, en, es, es + ew)
                out.pop()
                break
    return out[:32]


def decode_bitfields(word_value, fields):
    """Extract unsigned bitfield values from a 16/32/64-bit integer."""
    value = int(word_value) & ((1 << 64) - 1)
    result = {}
    for start, width, name in fields:
        mask = (1 << width) - 1
        result[name] = (value >> start) & mask
    return result


def value_level(value, rec):
    """Return '' / 'warn' / 'alarm' based on optional thresholds."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    alo, ahi = rec.get("alarm_lo"), rec.get("alarm_hi")
    wlo, whi = rec.get("warn_lo"), rec.get("warn_hi")
    if alo is not None and v <= float(alo):
        return "alarm"
    if ahi is not None and v >= float(ahi):
        return "alarm"
    if wlo is not None and v <= float(wlo):
        return "warn"
    if whi is not None and v >= float(whi):
        return "warn"
    return ""


def decode_register_value(definition, registers):
    """按类型、字节序、倍率和偏移解码一条寄存器定义。"""
    rec = normalize_register(definition)
    width = register_width(rec["type"])
    if len(registers) < width:
        raise ValueError("not enough registers")
    words = [int(value) & 0xFFFF for value in registers[:width]]
    raw = _ordered_bytes(words, rec["order"])
    typ = rec["type"]
    if typ == "bit":
        value = 1 if (words[0] & (1 << rec["bit"])) else 0
    elif typ == "u16":
        value = int.from_bytes(raw, "big", signed=False)
    elif typ == "i16":
        value = int.from_bytes(raw, "big", signed=True)
    elif typ == "u32":
        value = int.from_bytes(raw, "big", signed=False)
    elif typ == "i32":
        value = int.from_bytes(raw, "big", signed=True)
    elif typ == "u64":
        value = int.from_bytes(raw, "big", signed=False)
    elif typ == "i64":
        value = int.from_bytes(raw, "big", signed=True)
    elif typ == "f64":
        value = struct.unpack(">d", raw)[0]
        if not math.isfinite(value):
            raise ValueError("non-finite float")
    else:  # f32
        value = struct.unpack(">f", raw)[0]
        if not math.isfinite(value):
            raise ValueError("non-finite float")
    value = value * rec["scale"] + rec["offset"]
    return value, " ".join("%04X" % word for word in words)


def decode_modbus_samples(definitions, slave, function, start_address, registers,
                          timestamp=None):
    """将一次 03/04 响应映射为命名标签样本。"""
    values = list(registers or [])
    start = int(start_address)
    now = time.time() if timestamp is None else float(timestamp)
    samples = []
    # Avoid re-normalizing when the caller already passes normalized definitions
    # (all production callers do). Detect by checking the first item for the
    # "enabled" key that normalize_register always adds.
    _normed = (definitions
               and isinstance(definitions[0], dict)
               and "enabled" in definitions[0])
    for rec in (definitions if _normed else normalize_registers(definitions)):
        if (not rec["enabled"] or rec["slave"] != int(slave)
                or rec["function"] != int(function)):
            continue
        offset = rec["address"] - start
        width = register_width(rec["type"])
        if offset < 0 or offset + width > len(values):
            continue
        try:
            value, raw = decode_register_value(rec, values[offset:offset + width])
        except (TypeError, ValueError, struct.error):
            continue
        level = value_level(value, rec)
        samples.append({
            "timestamp": now,
            "source": "modbus",
            "tag": rec["name"],
            "value": value,
            "unit": rec["unit"],
            "raw": raw,
            "slave": rec["slave"],
            "function": rec["function"],
            "address": rec["address"],
            "display_address": rec.get("display_address", rec["address"]),
            "level": level,
        })
        fields = parse_bitfields(rec.get("bitfields"))
        if fields:
            # Bitfields always unpack the unsigned integer before scale/offset.
            words = [int(v) & 0xFFFF for v in values[offset:offset + width]]
            packed = int.from_bytes(_ordered_bytes(words, rec["order"]), "big", signed=False)
            for fname, fval in decode_bitfields(packed, fields).items():
                samples.append({
                    "timestamp": now,
                    "source": "modbus",
                    "tag": "%s.%s" % (rec["name"], fname),
                    "value": fval,
                    "unit": "",
                    "raw": raw,
                    "slave": rec["slave"],
                    "function": rec["function"],
                    "address": rec["address"],
                    "display_address": rec.get("display_address", rec["address"]),
                    "level": "",
                })
    return samples


def normalize_sample(sample):
    sample = dict(sample or {})
    value = sample.get("value", "")
    if isinstance(value, float) and not math.isfinite(value):
        value = ""
    return {
        "timestamp": _float(sample.get("timestamp", time.time()), time.time()),
        "source": str(sample.get("source", "protocol"))[:32],
        "tag": str(sample.get("tag", ""))[:120],
        "value": value,
        "unit": str(sample.get("unit", ""))[:32],
        "raw": str(sample.get("raw", ""))[:4096],
        "slave": sample.get("slave", ""),
        "function": sample.get("function", ""),
        "address": sample.get("address", ""),
        # 按地址基显示的地址和阈值结果一并入库，否则寄存器里配的
        # addr_base / warn / alarm 到了结构化记录就丢了。
        "display_address": sample.get("display_address",
                                      sample.get("address", "")),
        "level": str(sample.get("level", "") or "")[:8],
    }


class StructuredRecorder:
    """内存结构化记录器；CSV 文件可再次载入、查询与回放。"""

    def __init__(self, max_rows=_MAX_ROWS):
        self.max_rows = max(1, int(max_rows))
        self.rows = []
        self.recording = False
        self.truncated = False

    def start(self, clear=False):
        if clear:
            self.clear()
        self.recording = True

    def stop(self):
        self.recording = False

    def clear(self):
        self.rows = []
        self.truncated = False

    def add(self, samples):
        if not self.recording:
            return 0
        added = 0
        for sample in samples or ():
            if len(self.rows) >= self.max_rows:
                self.truncated = True
                break
            row = normalize_sample(sample)
            if not row["tag"]:
                continue
            self.rows.append(row)
            added += 1
        return added

    def query(self, text="", source=""):
        needle = str(text or "").strip().lower()
        source = str(source or "").strip().lower()
        return [row for row in self.rows
                if (not source or row["source"].lower() == source)
                and (not needle or needle in row["tag"].lower()
                     or needle in str(row["value"]).lower())]

    def save_csv(self, path, rows=None):
        selected = list(self.rows if rows is None else rows)
        with open(path, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=STRUCTURED_COLUMNS)
            writer.writeheader()
            for row in selected:
                out = normalize_sample(row)
                out["timestamp"] = "%.6f" % out["timestamp"]
                writer.writerow(out)
        return len(selected)

    def load_csv(self, path):
        if os.path.getsize(path) > _MAX_CSV_BYTES:
            raise ValueError("CSV file is too large")
        rows = []
        with open(path, "r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not {"timestamp", "tag", "value"}.issubset(reader.fieldnames):
                raise ValueError("invalid structured CSV")
            for item in reader:
                if len(rows) >= self.max_rows:
                    self.truncated = True
                    break
                value = item.get("value", "")
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    pass
                item["value"] = value
                rows.append(normalize_sample(item))
        rows.sort(key=lambda row: row["timestamp"])
        self.rows = rows
        return len(rows)
