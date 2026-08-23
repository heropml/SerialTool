# -*- coding: utf-8 -*-
"""Operator-panel resource schema built on top of the existing dashboard."""
from __future__ import annotations

import uuid


MAX_PANELS = 20
MAX_ACTIONS = 100


def normalize_panel(item):
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or "").strip()[:80]
    if not name:
        return None
    config = item.get("dashboard")
    if not isinstance(config, dict):
        config = {}
    raw_actions = item.get("actions")
    if not isinstance(raw_actions, (list, tuple)):
        raw_actions = ()
    actions = [dict(action) for action in raw_actions
               if isinstance(action, dict)][:MAX_ACTIONS]
    return {
        "id": str(item.get("id") or uuid.uuid4().hex)[:64],
        "name": name,
        "dashboard": dict(config),
        "actions": actions,
    }


def normalize_panels(items):
    out, seen = [], set()
    for raw in items if isinstance(items, list) else ():
        panel = normalize_panel(raw)
        if panel is None or panel["id"] in seen:
            continue
        seen.add(panel["id"])
        out.append(panel)
        if len(out) >= MAX_PANELS:
            break
    return out


def panel_from_dashboard(settings, name="Main panel"):
    settings = dict(settings) if isinstance(settings, dict) else {}
    keys = (
        "dash_mode", "dash_sep", "dash_regex", "dash_fields", "dash_header",
        "dash_thresholds", "dash_widget",
    )
    dashboard = {key: settings[key] for key in keys if key in settings}
    return normalize_panel({"name": name, "dashboard": dashboard, "actions": []})
