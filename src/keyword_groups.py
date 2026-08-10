# -*- coding: utf-8 -*-
"""Keyword highlight group model (Qt-free).

S-2 slice: parse/migrate keyword_groups + legacy flat keyword_rules,
resolve active group by name, and build save payload.
"""
import json


def _loads_list(raw):
    """Parse a JSON list from settings text; bad/empty -> []."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def parse_groups(raw):
    """keyword_groups JSON -> list of {name, rules} dicts (rules must be list)."""
    return [
        g for g in _loads_list(raw)
        if isinstance(g, dict) and isinstance(g.get("rules"), list)
    ]


def parse_legacy_rules(raw):
    """Flat keyword_rules JSON -> list (any items kept as stored)."""
    return _loads_list(raw)


def resolve_active_index(groups, active_name):
    """Find group index by name; missing/empty -> -1 (highlight off)."""
    if not active_name:
        return -1
    for i, g in enumerate(groups or ()):
        if g.get("name") == active_name:
            return i
    return -1


def load_groups(groups_raw, legacy_raw, active_name, default_name):
    """Load groups with legacy migration.

    Returns (groups, active_index, loaded_ok).
    loaded_ok=False means we fell back to migration/default (caller should persist).
    """
    groups = parse_groups(groups_raw)
    loaded_ok = bool(groups)
    if not groups:
        old_rules = parse_legacy_rules(legacy_raw)
        groups = [{"name": default_name, "rules": old_rules}]
    active = resolve_active_index(groups, active_name)
    return groups, active, loaded_ok


def active_rules(groups, active_index):
    """Rules of the active group; off/OOB -> []."""
    groups = groups or []
    if 0 <= active_index < len(groups):
        return groups[active_index].get("rules") or []
    return []


def save_fields(groups, active_index):
    """Build (groups_json, active_name) for QSettings persistence."""
    groups = groups or []
    payload = json.dumps(groups, ensure_ascii=False)
    name = (
        groups[active_index]["name"]
        if 0 <= active_index < len(groups)
        else ""
    )
    return payload, name


_MATCH_MODES = ("plain", "regex", "hex")


def normalize_match(value):
    """Legacy rules omit match -> plain (case-sensitive substring)."""
    mode = str(value or "plain").strip().lower()
    return mode if mode in _MATCH_MODES else "plain"


def rule_matches(text, rule, hexdump=False):
    """Return True if rule hits text; uses search_helper for regex/hex safety."""
    import search_helper
    pat = rule.get("pattern") or ""
    if not pat:
        return False
    mode = normalize_match(rule.get("match"))
    # Keep historical plain behavior: case-sensitive substring.
    case_sensitive = True if mode == "plain" else False
    spans = search_helper.find_spans(
        text or "", pat, mode=mode, case_sensitive=case_sensitive,
        hexdump=bool(hexdump), limit=1)
    return any(end > start for start, end in spans)


def rule_spans(text, rule, hexdump=False, limit=None):
    """Return match spans for one keyword rule."""
    import search_helper
    pat = rule.get("pattern") or ""
    if not pat:
        return []
    mode = normalize_match(rule.get("match"))
    case_sensitive = True if mode == "plain" else False
    spans = search_helper.find_spans(
        text or "", pat, mode=mode, case_sensitive=case_sensitive,
        hexdump=bool(hexdump), limit=limit)
    spans = [(start, end) for start, end in spans if end > start]
    return search_helper.to_utf16_spans(text or "", spans)
