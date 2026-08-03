# -*- coding: utf-8 -*-
"""CommTool 工程文件格式与读写。工程设置继续使用主窗口现有配置键。"""

import json
import os
import tempfile


PROJECT_FORMAT = "commtool-project"
PROJECT_VERSION = 2
SUPPORTED_PROJECT_VERSIONS = (1, 2)

_DASHBOARD_KEYS = (
    "dash_mode", "dash_sep", "dash_regex", "dash_fields",
    "dash_header", "dash_thresholds",
)


class ProjectError(ValueError):
    pass


def make_project(name, metadata, settings, app_version, resources=None):
    return {
        "format": PROJECT_FORMAT,
        "format_version": PROJECT_VERSION,
        "app_version": str(app_version),
        "name": str(name or "Untitled"),
        "metadata": dict(metadata or {}),
        "settings": dict(settings or {}),
        "resources": dict(resources or {}),
    }


def validate(payload):
    if not isinstance(payload, dict):
        raise ProjectError("invalid project")
    if payload.get("format") != PROJECT_FORMAT:
        raise ProjectError("not a CommTool project")
    version = payload.get("format_version")
    if version not in SUPPORTED_PROJECT_VERSIONS:
        raise ProjectError("unsupported project version: %s" % version)
    if not isinstance(payload.get("settings"), dict):
        raise ProjectError("invalid project settings")
    if not isinstance(payload.get("metadata", {}), dict):
        raise ProjectError("invalid project metadata")
    if version >= 2 and not isinstance(payload.get("resources", {}), dict):
        raise ProjectError("invalid project resources")
    payload.setdefault("resources", {})
    return payload


def _json_value(settings, key, default):
    value = dict(settings or {}).get(key, default)
    if isinstance(value, type(default)):
        return value
    if not isinstance(value, str) or not value:
        return default
    try:
        decoded = json.loads(value)
    except Exception:
        return default
    return decoded if isinstance(decoded, type(default)) else default


def collect_project_resources(settings):
    """从现有 QSettings 形态提取显式工程资源包。设置仍保留一份，兼容旧版本。"""
    settings = dict(settings or {})
    return {
        "device": {
            "registers": _json_value(settings, "device_registers", []),
            "plot_tags": _json_value(settings, "device_plot_tags", []),
            "dash_tags": _json_value(settings, "device_dash_tags", []),
        },
        "send": {
            "snippets": _json_value(settings, "snippets", []),
            "groups": _json_value(settings, "multi_send_groups", []),
        },
        "connection": {
            "presets": _json_value(settings, "connection_presets", []),
        },
        "automation": {
            "sequences": _json_value(settings, "sequence_rules", []),
            "scripts": _json_value(settings, "script_lib", []),
        },
        "dashboard": {
            key: settings[key] for key in _DASHBOARD_KEYS if key in settings
        },
    }


def merge_project_resources(settings, resources):
    """把 v2 资源包映射回主窗口设置；资源值优先，支持手工精简 settings 的工程。"""
    merged = dict(settings or {})
    resources = resources if isinstance(resources, dict) else {}
    device = resources.get("device", {})
    send = resources.get("send", {})
    connection = resources.get("connection", {})
    automation = resources.get("automation", {})
    dashboard = resources.get("dashboard", {})
    mappings = (
        (device, "registers", "device_registers"),
        (device, "plot_tags", "device_plot_tags"),
        (device, "dash_tags", "device_dash_tags"),
        (send, "snippets", "snippets"),
        (send, "groups", "multi_send_groups"),
        (connection, "presets", "connection_presets"),
        (automation, "sequences", "sequence_rules"),
        (automation, "scripts", "script_lib"),
    )
    for container, resource_key, setting_key in mappings:
        if isinstance(container, dict) and resource_key in container:
            merged[setting_key] = json.dumps(container[resource_key], ensure_ascii=False)
    if isinstance(dashboard, dict):
        for key in _DASHBOARD_KEYS:
            if key in dashboard:
                merged[key] = dashboard[key]
    return merged


def load_project(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return validate(json.load(f))
    except ProjectError:
        raise
    except Exception as e:
        raise ProjectError(str(e)) from e


def save_project(path, payload):
    """同目录临时文件 + replace，避免写到一半留下损坏工程。"""
    validate(payload)
    folder = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".commtool-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temp_path, path)
    except Exception:
        # 若 os.fdopen() 自身失败，它不会接管 fd；Windows 上未关闭的句柄
        # 还会阻止下面删除临时文件。正常进入 with 后 EBADF 可安全忽略。
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def prepare_project_settings(incoming, previous, allowed_keys,
                             personal_keys=("theme", "language", "auto_update_check")):
    """过滤工程键；个人偏好始终采用本机值，其它缺项回默认，禁止跨工程泄漏。"""
    incoming = dict(incoming or {})
    previous = dict(previous or {})
    allowed = set(allowed_keys)
    result = {key: value for key, value in incoming.items() if key in allowed}
    for key in personal_keys:
        result.pop(key, None)  # 兼容旧工程：即使文件里带了，也不能覆盖本机个人偏好
        if key in allowed and previous.get(key) is not None:
            result[key] = previous[key]
    return result
