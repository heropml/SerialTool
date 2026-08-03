# -*- coding: utf-8 -*-
"""Sequence variable context: ${name} expand + response extractors (Qt-free)."""
import re
import binascii

try:
    import triggers
except Exception:  # pragma: no cover
    triggers = None

try:
    import binproto
except Exception:  # pragma: no cover
    binproto = None

MAX_VARS = 200
MAX_NAME = 64
MAX_VALUE = 4000
MAX_EXTRACTORS = 32

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
# Named capture group token in DSL (Python re group name rules).
_GROUP_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_group_token(token):
    """True if DSL trailing segment is a numeric or explicit named group."""
    s = str(token or "").strip()
    if not s:
        return False
    if s.lstrip("-").isdigit():
        return True
    return s.startswith("group=") and bool(_GROUP_NAME_RE.match(s[6:]))

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _clip_name(name):
    name = str(name or "").strip()
    if not name or not _NAME_RE.match(name):
        return ""
    return name[:MAX_NAME]


def _clip_value(value):
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        value = binascii.hexlify(bytes(value)).decode("ascii")
    text = str(value)
    return text[:MAX_VALUE]


def sanitize_ctx(ctx):
    if not isinstance(ctx, dict):
        return {}
    out = {}
    for k, v in ctx.items():
        name = _clip_name(k)
        if not name:
            continue
        out[name] = _clip_value(v)
        if len(out) >= MAX_VARS:
            break
    return out


def expand(template, ctx):
    """Replace ${name} from ctx. Unknown names become empty string. $${ -> literal ${"""
    text = "" if template is None else str(template)
    ctx = sanitize_ctx(ctx)
    if "${" not in text:
        return text

    def repl(m):
        return ctx.get(m.group(1), "")

    parts = text.split("$${", 1)
    out = []
    while True:
        out.append(_VAR_RE.sub(repl, parts[0]))
        if len(parts) == 1:
            break
        out.append("${")
        parts = parts[1].split("$${", 1)
    return "".join(out)



def referenced_vars(template):
    """Return ordered unique ${name} names in template (honours $${ escape)."""
    text = "" if template is None else str(template)
    if "${" not in text:
        return []
    names = []
    seen = set()
    parts = text.split("$${", 1)
    while True:
        for m in _VAR_RE.finditer(parts[0]):
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                names.append(name)
        if len(parts) == 1:
            break
        parts = parts[1].split("$${", 1)
    return names


def missing_vars(template, ctx):
    """Names referenced by ${name} but absent from ctx (after sanitize)."""
    ctx = sanitize_ctx(ctx)
    return [name for name in referenced_vars(template) if name not in ctx]


def normalize_extractor(spec):
    if not isinstance(spec, dict):
        return None
    name = _clip_name(spec.get("as") or spec.get("name") or "")
    kind = str(spec.get("kind") or "").strip().lower()
    if not name or kind not in ("text", "hex", "regex", "modbus"):
        return None
    out = {"as": name, "kind": kind}
    if kind == "text":
        out["pattern"] = str(spec.get("pattern") or "")
    elif kind == "hex":
        try:
            out["offset"] = max(0, int(spec.get("offset", 0)))
            out["length"] = max(0, int(spec.get("length", 0) or spec.get("len", 0)))
        except (TypeError, ValueError):
            return None
    elif kind == "regex":
        out["pattern"] = str(spec.get("pattern") or "")
        g = spec.get("group", 1)
        try:
            out["group"] = int(g)
        except (TypeError, ValueError):
            out["group"] = str(g or 1)
        if not out["pattern"]:
            return None
    elif kind == "modbus":
        out["type"] = str(spec.get("type") or "u16be")
        try:
            out["offset"] = max(0, int(spec.get("offset", 0)))
        except (TypeError, ValueError):
            return None
    return out


def sanitize_extractors(items):
    if not isinstance(items, list):
        return []
    out = []
    for raw in items:
        n = normalize_extractor(raw)
        if n:
            out.append(n)
        if len(out) >= MAX_EXTRACTORS:
            break
    return out


def parse_extract_dsl(text):
    """Parse compact DSL into extractor list.

    Forms (semicolon or comma separated):
      name=text
      name=text:substr
      name=hex:offset:length
      name=regex:pattern:group
      name=modbus:type:offset
    """
    text = str(text or "").strip()
    if not text:
        return []
    specs = []
    for chunk in re.split(r"[;,]", text):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, rest = chunk.split("=", 1)
        rest = rest.strip()
        if not rest:
            continue
        parts = rest.split(":")
        kind = parts[0].strip().lower()
        if kind == "text":
            specs.append({"as": name, "kind": "text",
                          "pattern": ":".join(parts[1:]) if len(parts) > 1 else ""})
        elif kind == "hex" and len(parts) >= 3:
            specs.append({"as": name, "kind": "hex",
                          "offset": parts[1], "length": parts[2]})
        elif kind == "regex" and len(parts) >= 2:
            # Trailing :N is the legacy numeric group form; named groups use
            # explicit :group=name so regexes ending in :identifier stay intact.
            if len(parts) >= 3 and _is_group_token(parts[-1]):
                group_token = parts[-1].strip()
                group = (group_token[6:] if group_token.startswith("group=")
                         else group_token)
                pattern = ":".join(parts[1:-1])
            else:
                group = 1
                pattern = ":".join(parts[1:])
            specs.append({"as": name, "kind": "regex", "pattern": pattern, "group": group})
        elif kind == "modbus" and len(parts) >= 3:
            specs.append({"as": name, "kind": "modbus",
                          "type": parts[1], "offset": parts[2]})
    return sanitize_extractors(specs)


def extractors_to_dsl(specs):
    specs = sanitize_extractors(specs)
    parts = []
    for s in specs:
        kind = s["kind"]
        if kind == "text":
            if s.get("pattern"):
                parts.append("%s=text:%s" % (s["as"], s["pattern"]))
            else:
                parts.append("%s=text" % s["as"])
        elif kind == "hex":
            parts.append("%s=hex:%s:%s" % (s["as"], s.get("offset", 0), s.get("length", 0)))
        elif kind == "regex":
            group = s.get("group", 1)
            suffix = str(group) if isinstance(group, int) else "group=" + str(group)
            parts.append("%s=regex:%s:%s" % (s["as"], s.get("pattern", ""), suffix))
        elif kind == "modbus":
            parts.append("%s=modbus:%s:%s" % (s["as"], s.get("type", "u16be"), s.get("offset", 0)))
    return "; ".join(parts)


def _decode_text(buf, codec="utf-8"):
    try:
        enc = "utf-8" if not codec or codec == "auto" else codec
        return bytes(buf).decode(enc, errors="replace")
    except Exception:
        return ""


def extract(buf, specs, text=None, codec="utf-8"):
    """Run extractors against response buffer. Returns dict of captured vars."""
    specs = sanitize_extractors(specs)
    if not specs:
        return {}
    raw = bytes(buf or b"")
    if text is None:
        text = _decode_text(raw, codec)
    out = {}
    for spec in specs:
        kind = spec["kind"]
        name = spec["as"]
        try:
            if kind == "text":
                pat = spec.get("pattern") or ""
                if pat and pat not in text:
                    continue
                out[name] = _clip_value(pat if pat else text)
            elif kind == "hex":
                off = int(spec.get("offset", 0))
                ln = int(spec.get("length", 0))
                if ln <= 0 or off >= len(raw):
                    continue
                chunk = raw[off: off + ln]
                if len(chunk) < ln:
                    continue
                out[name] = binascii.hexlify(chunk).decode("ascii")
            elif kind == "regex":
                pattern = spec.get("pattern") or ""
                compiled = None
                if triggers is not None:
                    compiled = triggers.compile_regex(pattern)
                else:
                    try:
                        compiled = re.compile(pattern)
                    except re.error:
                        compiled = None
                if compiled is None:
                    continue
                m = compiled.search(text)
                if not m:
                    continue
                g = spec.get("group", 1)
                try:
                    if isinstance(g, int):
                        val = m.group(g)
                    else:
                        val = m.group(str(g))
                except (IndexError, KeyError):
                    continue
                if val is None:
                    continue
                out[name] = _clip_value(val)
            elif kind == "modbus":
                if binproto is None:
                    continue
                typ = spec.get("type") or "u16be"
                off = int(spec.get("offset", 0))
                try:
                    val = binproto.read_field(raw, off, typ)
                    if val is None:
                        continue
                except Exception:
                    continue
                out[name] = _clip_value(val)
        except Exception:
            continue
        if len(out) >= MAX_VARS:
            break
    return out


class RoundContext(object):
    """Per-round isolated variable scope."""

    def __init__(self, seed=None):
        self._data = sanitize_ctx(seed)

    def reset(self, seed=None):
        self._data = sanitize_ctx(seed)

    def update(self, extracted):
        self._data.update(sanitize_ctx(extracted))
        if len(self._data) > MAX_VARS:
            keys = list(self._data.keys())
            for k in keys[: len(keys) - MAX_VARS]:
                self._data.pop(k, None)

    def get(self, name, default=""):
        return self._data.get(name, default)

    def as_dict(self):
        return dict(self._data)
