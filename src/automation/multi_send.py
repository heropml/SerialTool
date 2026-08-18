# -*- coding: utf-8 -*-
"""Multi-send group model + cycle sequence (Qt-free).

S-2 R19: load/migrate multi_send_groups, active items, cycle seq builder.
"""
import json


def _loads_list(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def parse_groups(raw):
    """multi_send_groups JSON -> list of {name, items} dicts."""
    return [
        g for g in _loads_list(raw)
        if isinstance(g, dict) and isinstance(g.get("items"), list)
    ]


def parse_legacy_items(raw):
    """Flat multi_send_items JSON -> list."""
    return _loads_list(raw)


def load_groups(groups_raw, legacy_raw, default_name):
    """Load groups with legacy flat-list migration.

    Returns (groups, loaded_ok). loaded_ok=False -> caller should persist.
    """
    groups = parse_groups(groups_raw)
    loaded_ok = bool(groups)
    if not groups:
        old_items = parse_legacy_items(legacy_raw)
        groups = [{"name": default_name, "items": old_items}]
    return groups, loaded_ok


def active_items(groups, group_idx):
    """Items of the selected group; OOB -> []."""
    groups = groups or []
    if 0 <= group_idx < len(groups):
        return groups[group_idx].get("items") or []
    return []


def build_cycle_seq(items):
    """Checked non-empty items -> [(data, hex, nl, cs, delay), ...]."""
    out = []
    for it in items or ():
        if not it.get("checked"):
            continue
        data = str(it.get("data", "") or "")
        if not data.strip():
            continue
        try:
            delay = max(1, int(it.get("delay", 1000)))
        except (TypeError, ValueError):
            delay = 1000
        try:
            nl = int(it.get("nl", 0))
        except (TypeError, ValueError):
            nl = 0
        try:
            cs = int(it.get("cs", 0))
        except (TypeError, ValueError):
            cs = 0
        out.append((data, bool(it.get("hex", False)), nl, cs, delay))
    return out


def groups_json(groups):
    """Serialize groups for QSettings."""
    return json.dumps(groups or [], ensure_ascii=False)
