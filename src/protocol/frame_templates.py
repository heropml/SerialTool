# -*- coding: utf-8 -*-
"""Reusable frame-builder template collection (Qt-free)."""
from __future__ import annotations

import math
import time
import uuid


MAX_TEMPLATES = 100
MAX_FIELDS = 500
MAX_NAME = 80


class DuplicateTemplateName(ValueError):
    """Raised when saving would replace another template with the same name."""

    def __init__(self, name, template_id):
        super().__init__("template name already exists: %s" % name)
        self.name = str(name)
        self.template_id = str(template_id)


def normalize_field(field):
    if not isinstance(field, (list, tuple)) or len(field) < 3:
        return None
    kind, field_type, value = field[:3]
    name = field[3] if len(field) > 3 else ""
    return [str(kind)[:32], field_type, str(value)[:4096], str(name)[:120]]


def normalize_template(item):
    if not isinstance(item, dict):
        return None
    fields = []
    raw_fields = item.get("fields")
    if not isinstance(raw_fields, (list, tuple)):
        raw_fields = ()
    for field in raw_fields:
        clean = normalize_field(field)
        if clean is not None:
            fields.append(clean)
        if len(fields) >= MAX_FIELDS:
            break
    name = str(item.get("name") or "").strip()[:MAX_NAME]
    if not name or not fields:
        return None
    try:
        updated = float(item.get("updated") or time.time())
    except (TypeError, ValueError, OverflowError):
        updated = time.time()
    if not math.isfinite(updated):
        updated = time.time()
    return {
        "id": str(item.get("id") or uuid.uuid4().hex)[:64],
        "name": name,
        "fields": fields,
        "updated": updated,
    }


def normalize_templates(items):
    out = []
    seen = set()
    for item in items if isinstance(items, list) else ():
        clean = normalize_template(item)
        if clean is None or clean["id"] in seen:
            continue
        seen.add(clean["id"])
        out.append(clean)
        if len(out) >= MAX_TEMPLATES:
            break
    return out


def upsert(items, name, fields, template_id="", replace_name_conflict=False):
    templates = normalize_templates(items)
    target = str(template_id or "")
    item = normalize_template({
        "id": target or uuid.uuid4().hex,
        "name": name,
        "fields": fields,
        "updated": time.time(),
    })
    if item is None:
        raise ValueError("template requires a name and at least one field")
    conflicts = [old for old in templates
                 if old["id"] != item["id"] and old["name"] == item["name"]]
    if conflicts and not replace_name_conflict:
        raise DuplicateTemplateName(item["name"], conflicts[0]["id"])
    templates = [old for old in templates if old["id"] != item["id"]]
    if conflicts:
        # Legacy/manual configs may already contain several rows with this name.
        # One explicit overwrite confirmation covers the whole ambiguous set.
        templates = [old for old in templates if old["name"] != item["name"]]
    templates.insert(0, item)
    return templates[:MAX_TEMPLATES], item["id"]


def remove(items, template_id):
    target = str(template_id or "")
    return [item for item in normalize_templates(items) if item["id"] != target]
