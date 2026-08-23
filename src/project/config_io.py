# -*- coding: utf-8 -*-
"""Config import/export helpers (Qt-free).

S-2 R22: security gate transforms + export/coerce for CommTool / project apply.
Confirm dialogs stay in the GUI layer.
"""
import json
import os
import shutil

from project.config_keys import CFG_KEYS, PROJECT_PERSONAL_KEYS


def parse_json_list(raw):
    """JSON string or list -> list; missing/invalid/non-list -> None.

    An empty list ``[]`` is a valid value (user intentionally cleared all
    items) and is returned as-is, **not** as ``None``.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    return data if isinstance(data, list) else None


def trigger_external_count(rules):
    """Count rules with non-empty run_cmd or webhook_url (detect only)."""
    n = 0
    for r in rules or ():
        if not isinstance(r, dict):
            continue
        if str(r.get("run_cmd") or "").strip() or str(r.get("webhook_url") or "").strip():
            n += 1
    return n


def strip_trigger_externals(rules):
    """Copy rules without external action fields (incl. run_cmd_on / webhook)."""
    out = []
    for r in rules or ():
        if not isinstance(r, dict):
            out.append(r)
            continue
        nr = dict(r)
        for key in ("run_cmd", "run_cmd_on", "webhook", "webhook_url",
                    "webhook_allow_insecure"):
            nr.pop(key, None)
        out.append(nr)
    return out


def script_lib_code_count(items):
    """Count script_lib entries with non-empty code."""
    return sum(
        1 for it in (items or ())
        if isinstance(it, dict) and str(it.get("code") or "").strip()
    )


def drop_script_lib(data):
    """Shallow copy without script_lib / script_active."""
    new = dict(data or {})
    new.pop("script_lib", None)
    new.pop("script_active", None)
    return new


def ar_script_count(rules):
    """Count autoreply rules with non-empty script."""
    return sum(
        1 for r in (rules or ())
        if isinstance(r, dict) and str(r.get("script") or "").strip()
    )


def strip_ar_scripts(rules):
    """Copy rules without script field."""
    out = []
    for r in rules or ():
        if not isinstance(r, dict):
            out.append(r)
            continue
        nr = dict(r)
        nr.pop("script", None)
        out.append(nr)
    return out


def collect_export_settings(get_value, keys=CFG_KEYS):
    """Build settings dict from a getter; skip None only (keep False/0/\"\")."""
    out = {}
    for k in keys:
        v = get_value(k)
        if v is None:
            continue
        out[k] = v
    return out


def build_export_payload(settings, *, app="CommTool", version=""):
    """Wrap settings for JSON export."""
    return {"_app": app, "_version": version, "settings": dict(settings or {})}


def coerce_setting_value(v):
    """dict/list -> JSON string for QSettings loaders; else passthrough."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def coerce_imported_settings(data, keys=CFG_KEYS):
    """Filter to allowed keys and coerce nested JSON."""
    out = {}
    for k, v in (data or {}).items():
        if k in keys:
            out[k] = coerce_setting_value(v)
    return out


def dumps_list(items):
    """Serialize a list field for QSettings."""
    return json.dumps(items or [], ensure_ascii=False)

def settings_to_bool(v, default=False):
    """QSettings-ish bool: bool passthrough; str true/1/yes; else default."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return default


def project_fingerprint(settings):
    """Stable JSON fingerprint for dirty detection."""
    return json.dumps(settings or {}, ensure_ascii=False, sort_keys=True, default=str)


def snapshot_project_settings(get_value, keys=CFG_KEYS, personal=None):
    """Project keys present in settings, excluding personal prefs / None."""
    personal = PROJECT_PERSONAL_KEYS if personal is None else frozenset(personal or ())
    out = {}
    for k in keys:
        if k in personal:
            continue
        v = get_value(k)
        if v is not None:
            out[k] = v
    return out


def clamp_int(v, lo, hi, default=None):
    """Parse int and clamp to [lo, hi]; on failure return default or lo."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return lo if default is None else default
    return max(lo, min(hi, n))


def clamp_recv_font_size(v, default=10):
    """Receive pane mono font size (7..28)."""
    return clamp_int(v, 7, 28, default=default)


def profile_cascade_offset(profile, step=40, max_n=8):
    """Cascade offset for a new numbered profile window."""
    try:
        n = int(profile)
    except (TypeError, ValueError):
        n = 2
    return step * max(1, min(n - 1, max_n))

TS_FORMATS = ("absolute", "time", "relative", "epoch")

# Field names reset when switching to an incomplete profile (widget attrs).
RESET_LINE_EDITS = (
    "ed_packet_timeout", "ed_max_lines", "ed_period_ms",
    "ed_local_port", "ed_remote_ip", "ed_remote_port", "ed_group",
)
RESET_COMBOS = (
    "cb_local_ip", "cb_proto", "cb_baud", "cb_databits",
    "cb_parity", "cb_stopbits", "cb_log_split",
)


def normalize_ts_format(v, default="absolute"):
    """Allowlisted timestamp format id."""
    v = v or default
    return v if v in TS_FORMATS else default


def normalize_encoding(v, default="auto"):
    """Codec name or 'auto'."""
    return (v or default) or default


def clamp_combo_index(v, count, default=0):
    """Parse combo index and clamp; invalid -> default."""
    try:
        idx = int(v)
    except (TypeError, ValueError):
        return default
    if count <= 0 or not 0 <= idx < count:
        return default
    return idx


def try_combo_index(v, count):
    """Parse combo index; invalid/OOB -> None (leave widget alone)."""
    try:
        idx = int(v)
    except (TypeError, ValueError):
        return None
    if count <= 0 or not 0 <= idx < count:
        return None
    return idx


def resolve_view_mutex(hexdump_on, numview_on):
    """Prefer hexdump when both dump and numeric views are on."""
    if hexdump_on and numview_on:
        return True, False
    return bool(hexdump_on), bool(numview_on)


def resolve_combo_text(value, options, editable=False):
    """Map a saved combo value to an apply decision.

    Returns None, ("index", i), or ("edit", text).
    """
    if value is None or value == "":
        return None
    text_v = str(value)
    options = list(options or ())
    try:
        return ("index", options.index(text_v))
    except ValueError:
        if editable:
            return ("edit", text_v)
        return None


def parse_json_dict(raw):
    """JSON string or dict -> dict; missing/invalid/non-dict -> None.

    An empty dict ``{}`` is a valid value and is returned as-is, **not** as
    ``None`` (same empty-vs-missing rule as parse_json_list).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def parse_json_object_list(raw):
    """JSON list keeping only dict items; missing/invalid -> None."""
    items = parse_json_list(raw)
    if items is None:
        return None
    return [r for r in items if isinstance(r, dict)]


def capture_field_defaults(values):
    """Copy txt_send + RESET_* keys present in values."""
    values = values or {}
    out = {}
    if "txt_send" in values:
        out["txt_send"] = values["txt_send"]
    for n in RESET_LINE_EDITS:
        if n in values:
            out[n] = values[n]
    for n in RESET_COMBOS:
        if n in values:
            out[n] = values[n]
    return out

def clamp_max_lines(v, default=10000):
    """Receive max-lines spin (100..1_000_000)."""
    return clamp_int(v, 100, 1_000_000, default=default)


# --- S-2 R51/R52: settings path + apply-loaded gates ---


def settings_ini_name(profile=""):
    """settings.ini or settings-<profile>.ini."""
    return "settings.ini" if not profile else "settings-%s.ini" % profile


SETTINGS_SUBDIR = "config"


def is_settings_ini_filename(name):
    """True for settings.ini / settings-*.ini (not QSettings .lock / .mwlock)."""
    if not name or not name.endswith(".ini"):
        return False
    return name == "settings.ini" or name.startswith("settings-")


def settings_dir(base):
    """Directory that holds settings.ini (``<base>/config``)."""
    return os.path.join(base, SETTINGS_SUBDIR)


def ensure_writable_dir(path):
    """Create ``path`` and probe a temp file. True if this process can write there."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return False
    test = os.path.join(path, ".write_test")
    try:
        with open(test, "w"):
            pass
    except (OSError, PermissionError):
        return False
    try:
        os.remove(test)
    except OSError:
        pass
    return True


def migrate_legacy_settings(dest_dir, legacy_dirs):
    """Copy leftover settings*.ini into dest_dir, then drop the old copies.

    Never overwrites a file already in dest_dir. Source (and sibling lock
    files) are removed only after a successful copy; dest-exists or copy
    failure leaves the original in place for the next launch.
    """
    dest_dir = os.path.abspath(dest_dir)
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError:
        return
    seen = set()
    for raw in legacy_dirs or ():
        legacy = os.path.abspath(raw)
        if legacy in seen or not os.path.isdir(legacy):
            continue
        if os.path.normcase(legacy) == os.path.normcase(dest_dir):
            continue
        seen.add(legacy)
        try:
            names = os.listdir(legacy)
        except OSError:
            continue
        for name in names:
            if not is_settings_ini_filename(name):
                continue
            src = os.path.join(legacy, name)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(dest_dir, name)
            if os.path.exists(dst):
                continue
            try:
                shutil.copy2(src, dst)
            except OSError:
                continue
            try:
                os.remove(src)
            except OSError:
                pass
            for extra in (src + ".mwlock", src + ".lock"):
                try:
                    os.remove(extra)
                except OSError:
                    pass


def resolve_settings_file(profile, candidates):
    """Pick the first writable ``<parent>/config`` and return the ini path.

    ``candidates`` is ``[(dest_parent, legacy_dirs), ...]``. Each writable
    dest migrates settings*.ini out of ``legacy_dirs`` first. The last
    candidate is used even if the directory is not writable (QSettings still
    gets a path).
    """
    name = settings_ini_name(profile)
    last_dest = None
    items = list(candidates or ())
    for i, (dest_parent, legacy_dirs) in enumerate(items):
        dest = settings_dir(dest_parent)
        last_dest = dest
        writable = ensure_writable_dir(dest)
        if not writable and i + 1 < len(items):
            continue
        if writable:
            migrate_legacy_settings(dest, list(legacy_dirs or ()))
        else:
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError:
                pass
        return os.path.join(dest, name)
    if last_dest:
        return os.path.join(last_dest, name)
    return name


def clamp_group_idx(idx, n_groups):
    """Clamp multi-send / keyword group index into [0, n) or 0."""
    try:
        i = int(idx)
    except (TypeError, ValueError):
        i = 0
    n = int(n_groups or 0)
    if n <= 0:
        return 0
    return i if 0 <= i < n else 0


def normalize_mbm_variant(v):
    """Whitelist Modbus master variant; unknown -> empty string."""
    s = "" if v is None else str(v)
    return s if s in ("", "rtu", "tcp", "ascii") else ""


def mbm_import_enabled(requested, is_open):
    """Import may enable master only when no live connection is open."""
    return bool(requested) and not bool(is_open)


def ar_mbm_mutex_disable_ar(ar_on, mbm_on):
    """True when both AR and MBM are on after load (master wins -> disable AR)."""
    return bool(ar_on) and bool(mbm_on)
