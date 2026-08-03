# -*- coding: utf-8 -*-
"""设备寄存器定义、Modbus 标签解码与结构化记录纯逻辑。"""

import csv
import math
import os
import struct
import time


REGISTER_TYPES = ("u16", "i16", "u32", "i32", "f32", "bit")
REGISTER_ORDERS = ("AB", "BA", "ABCD", "CDAB", "BADC", "DCBA")
STRUCTURED_COLUMNS = (
    "timestamp", "source", "tag", "value", "unit", "raw",
    "slave", "function", "address",
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
    return 2 if str(data_type) in ("u32", "i32", "f32") else 1


def normalize_register(record):
    """把一条设备寄存器定义规范化为稳定、可序列化的字典。"""
    record = dict(record or {})
    data_type = str(record.get("type", "u16")).lower()
    if data_type not in REGISTER_TYPES:
        data_type = "u16"
    default_order = "ABCD" if register_width(data_type) == 2 else "AB"
    order = str(record.get("order", default_order)).upper()
    if order not in REGISTER_ORDERS:
        order = default_order
    if register_width(data_type) == 1 and order not in ("AB", "BA"):
        order = "AB"
    if register_width(data_type) == 2 and order in ("AB", "BA"):
        order = default_order
    address = _int(record.get("address", 0), 0, 0, 0xFFFF)
    bit = _int(record.get("bit", 0), 0, 0, 15)
    return {
        "enabled": _bool(record.get("enabled", True)),
        "name": str(record.get("name") or "R%d" % address)[:80],
        "slave": _int(record.get("slave", 1), 1, 0, 255),
        "function": _int(record.get("function", 3), 3, 3, 4),
        "address": address,
        "type": data_type,
        "order": order,
        "bit": bit,
        "scale": _float(record.get("scale", 1), 1.0),
        "offset": _float(record.get("offset", 0), 0.0),
        "unit": str(record.get("unit", ""))[:32],
    }


def normalize_registers(records):
    if not isinstance(records, list):
        return []
    return [normalize_register(item) for item in records if isinstance(item, dict)][:2000]


def _ordered_bytes(registers, order):
    raw = b"".join(struct.pack(">H", int(value) & 0xFFFF) for value in registers)
    labels = "AB" if len(raw) == 2 else "ABCD"
    if len(raw) not in (2, 4) or sorted(order) != sorted(labels):
        order = labels
    return bytes(raw[labels.index(ch)] for ch in order)


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
    else:
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
    for rec in normalize_registers(definitions):
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
