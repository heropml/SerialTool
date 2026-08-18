# -*- coding: utf-8 -*-
"""CSV dataset for data-driven sequence rounds (Qt-free).

Each non-empty data row becomes one sequence round. Column headers become
${name} seed variables via seq_context.RoundContext(seed=...).
"""
from __future__ import print_function

import csv
import io
import os

from automation import seq_context

MAX_CSV_BYTES = 8 << 20          # 8 MiB
MAX_ROWS = 10000
MAX_COLS = 64
MAX_CELL = seq_context.MAX_VALUE

# Preferred columns for report device label (first hit wins).
ID_HEADERS = ("device_id", "device", "id", "sn", "serial", "name")


class DatasetError(ValueError):
    """User-facing load/validate failure; .code is an i18n key."""

    def __init__(self, code, **kwargs):
        self.code = str(code or "csv_error")
        self.kwargs = dict(kwargs)
        ValueError.__init__(self, self.code)


def _clip_cell(value):
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > MAX_CELL:
        text = text[:MAX_CELL]
    return text


def is_empty_row(row):
    """True when every cell is blank/whitespace."""
    if not isinstance(row, dict):
        return True
    for v in row.values():
        if str(v or "").strip():
            return False
    return True


def normalize_header(name):
    """Return a valid ${var} name or empty string if unusable."""
    return seq_context._clip_name(str(name or "").strip())


def validate_headers(headers):
    """Validate/normalize header list. Returns ordered unique valid names."""
    if not headers:
        raise DatasetError("seq_csv_no_header")
    raw = [str(h or "").strip() for h in headers]
    if not any(raw):
        raise DatasetError("seq_csv_no_header")
    if len(raw) > MAX_COLS:
        raise DatasetError("seq_csv_too_many_cols", n=MAX_COLS)

    seen = set()
    out = []
    for h in raw:
        if not h:
            raise DatasetError("seq_csv_blank_header")
        name = normalize_header(h)
        if not name:
            raise DatasetError("seq_csv_bad_header", name=h)
        if name in seen:
            raise DatasetError("seq_csv_dup_header", name=name)
        seen.add(name)
        out.append(name)
    return out


def row_to_seed(row, headers):
    """Map a DictReader row to a sanitized seed dict keyed by normalized headers."""
    if not isinstance(row, dict):
        return {}
    seed = {}
    for h in headers:
        if h in row:
            seed[h] = _clip_cell(row.get(h))
        else:
            found = None
            for k, v in row.items():
                if normalize_header(k) == h:
                    found = v
                    break
            seed[h] = _clip_cell(found)
    return seq_context.sanitize_ctx(seed)


def pick_row_label(seeds, headers=None):
    """Human label for reports: first preferred id column with a value."""
    seeds = seeds or {}
    order = list(ID_HEADERS)
    if headers:
        for h in headers:
            hl = str(h).lower()
            if hl in ID_HEADERS and h not in order:
                order.append(h)
    for key in order:
        if key in seeds and str(seeds.get(key) or "").strip():
            return str(seeds[key]).strip()
        for k, v in seeds.items():
            if str(k).lower() == key and str(v or "").strip():
                return str(v).strip()
    return ""


# Excel on Chinese Windows often saves CSV as GBK/GB18030; try UTF-8 first.
_CSV_ENCODINGS = ("utf-8-sig", "gb18030", "latin-1")


def _decode_csv_bytes(data):
    """Decode CSV bytes with encoding fallback. latin-1 always succeeds."""
    last = None
    for enc in _CSV_ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError as e:
            last = e
            continue
    # Unreachable while latin-1 is listed; kept for API clarity.
    raise DatasetError("seq_csv_encoding", e=str(last or "decode"))


def load_dataset(path, max_bytes=MAX_CSV_BYTES, max_rows=MAX_ROWS):
    """Load CSV into a dataset dict.

    Returns dict with path, headers, rows[{number,seeds,label,raw}],
    skipped_empty, truncated, encoding.
    Tries utf-8-sig, then gb18030 (Excel/GBK), then latin-1.
    """
    path = os.path.abspath(str(path or ""))
    if not path or not os.path.isfile(path):
        raise DatasetError("seq_csv_missing")
    try:
        size = os.path.getsize(path)
    except OSError:
        raise DatasetError("seq_csv_missing")
    if size > int(max_bytes):
        raise DatasetError("seq_csv_too_large", mb=max(1, int(max_bytes) // (1024 * 1024)))

    try:
        with open(path, "rb") as binary:
            raw_bytes = binary.read()
    except OSError:
        raise DatasetError("seq_csv_missing")

    text, encoding = _decode_csv_bytes(raw_bytes)
    stream = io.StringIO(text, newline="")
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise DatasetError("seq_csv_no_header")
    headers = validate_headers(reader.fieldnames)

    rows = []
    skipped = 0
    truncated = False
    file_row = 1  # header line
    for raw in reader:
        file_row += 1
        mapped = {}
        for orig, norm in zip(reader.fieldnames, headers):
            mapped[norm] = raw.get(orig, "")
        if is_empty_row(mapped):
            skipped += 1
            continue
        if len(rows) >= int(max_rows):
            truncated = True
            break
        seeds = row_to_seed(mapped, headers)
        rows.append({
            "number": file_row,
            "seeds": seeds,
            "label": pick_row_label(seeds, headers),
            "raw": mapped,
        })

    if not rows:
        raise DatasetError("seq_csv_no_rows")

    return {
        "path": path,
        "headers": headers,
        "rows": rows,
        "skipped_empty": skipped,
        "truncated": truncated,
        "encoding": encoding,
    }


def dataset_status(ds):
    """Short status: 'N rows | col1, col2, ...'"""
    if not ds:
        return ""
    headers = ds.get("headers") or []
    n = len(ds.get("rows") or [])
    cols = ", ".join(headers[:8])
    if len(headers) > 8:
        cols += ", ..."
    return "%d rows | %s" % (n, cols)
