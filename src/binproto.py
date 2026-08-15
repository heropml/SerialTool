# -*- coding: utf-8 -*-
"""二进制协议解析原语（不依赖 pyqtgraph）。

波形图(plot_dialog) 与 帧解析表(frame_dialog) 共用，保证两处「帧头 / 字段定义」语义一致：
- 字段定义：`名称=偏移:类型`（名称可省，省则用 "偏移:类型" 当名）
- 类型：数值 u8/i8/u16le/u16be/i16le/i16be/u32../i32../f32le/f32be；
        外加 hexN（N 字节按 HEX 串）/ strN（N 字节 ASCII），后两者仅用于帧解析表展示。
- 帧定位：两种粒度——
    · iter_frames：不带帧长，把上层一个接收块视作一帧，帧头仅作前缀过滤；
    · iter_length_frames / scan_length_frames：带「帧头 + 长度字段」，
      维护跨包字节流按整帧边界切（自动应答与分析层协议帧模式共用）。
"""
import re
import struct

# 数值类型 → (struct 格式, 字节数)。le=小端 be=大端
HEX_FMT = {
    "u8": ("<B", 1), "i8": ("<b", 1),
    "u16le": ("<H", 2), "u16be": (">H", 2), "i16le": ("<h", 2), "i16be": (">h", 2),
    "u32le": ("<I", 4), "u32be": (">I", 4), "i32le": ("<i", 4), "i32be": (">i", 4),
    "f32le": ("<f", 4), "f32be": (">f", 4),
}


class BuildFieldError(ValueError):
    """帧构造失败，并携带出错字段的 0 基索引，供界面精确标红。"""
    def __init__(self, field_index, cause):
        self.field_index = field_index
        super().__init__("field %d: %s" % (field_index + 1, cause))
NUM_TYPES_TIP = " ".join(HEX_FMT.keys())            # 波形图只用数值类型
# 帧解析表另支持 hexN / strN；数值类型后加 x = 十六进制显示（如 u8x → 0x69）
ALL_TYPES_TIP = NUM_TYPES_TIP + " hexN strN  (数值后加 x=十六进制显示, 如 u8x)"

_HEXN = re.compile(r"hex(\d+)$")
_STRN = re.compile(r"str(\d+)$")


def _base_type(typ):
    """剥掉数值类型的 'x' 十六进制显示后缀：'u8x'→('u8', True)；其余→(typ, False)。"""
    if typ.endswith("x") and typ[:-1] in HEX_FMT:
        return typ[:-1], True
    return typ, False


def is_hex_num(typ):
    """是否为「数值 + 十六进制显示」类型（如 u8x）。仅影响显示，read_field 仍返回数字。"""
    return _base_type(typ)[1]


def valid_type(typ):
    base, _ = _base_type(typ)
    return base in HEX_FMT or _HEXN.match(base) is not None or _STRN.match(base) is not None


def read_field(buf, off, typ):
    """从 buf 的 off 处按 typ 取值：数值类型→数字；hexN→HEX 串；strN→ASCII 串；越界/失败→None。
    'x' 后缀（如 u8x）只影响显示，这里仍返回数字（由调用方按需转十六进制）。"""
    if off < 0:
        return None
    base, _hexdisp = _base_type(typ)
    if base in HEX_FMT:
        fmt, sz = HEX_FMT[base]
        if off + sz > len(buf):
            return None
        try:
            return struct.unpack(fmt, buf[off:off + sz])[0]
        except struct.error:
            return None
    m = _HEXN.match(base)
    if m:
        n = int(m.group(1))
        if n <= 0 or off + n > len(buf):
            return None
        return buf[off:off + n].hex(" ").upper()
    m = _STRN.match(base)
    if m:
        n = int(m.group(1))
        if n <= 0 or off + n > len(buf):
            return None
        return buf[off:off + n].decode("ascii", errors="replace").rstrip("\x00")
    return None


def field_size(typ):
    """字段占用字节数：数值类型按 HEX_FMT、hexN/strN 按 N；未知/无固定长度→0。
    是 read_field 的字节跨度镜像——协议高亮据此把字段映射回数据区对应的字节区间。"""
    base, _ = _base_type(typ)
    if base in HEX_FMT:
        return HEX_FMT[base][1]
    m = _HEXN.match(base)
    if m:
        return int(m.group(1))
    m = _STRN.match(base)
    if m:
        return int(m.group(1))
    return 0


def parse_hex_header(text):
    """'54' / '54 00' / '5400' → bytes；空→b''；非法 hex/奇数长度抛 ValueError。"""
    t = text.replace(" ", "").replace(",", "")
    if not t:
        return b""
    return bytes.fromhex(t)


def parse_field_spec(text):
    """'名称=偏移:类型, ...' → [(name, off, typ), ...]。名称可省（用 '偏移:类型' 当名）。
    格式/类型非法抛 ValueError。"""
    specs = []
    for tok in text.split(","):
        tok = tok.strip()
        if not tok:
            continue
        name, body = None, tok
        if "=" in tok:
            name, body = tok.split("=", 1)
            name, body = name.strip(), body.strip()
        if ":" not in body:
            raise ValueError(tok)
        off_s, typ = body.split(":", 1)
        off = int(off_s.strip())
        typ = typ.strip().lower()
        if off < 0 or not valid_type(typ):
            raise ValueError(tok)
        specs.append((name or body, off, typ))
    return specs


def _parse_build_int(s):
    """构造侧数值解析：'0x1A'/'0X1A' 按十六进制，其余按十进制（负数、正负号均可）。"""
    s = str(s).strip()
    neg = s[:1] in "+-"
    body = s[1:] if neg else s
    if body[:2].lower() == "0x":
        return int(s, 16)
    return int(s, 10)


def pack_field(value, typ):
    """把 value 按 typ 打包成 bytes —— read_field 的镜像（帧构造器用）。
    数值类型(HEX_FMT，如 u8/u16be/f32le) → struct.pack；'ascii' → ASCII 编码；'hex' → 解析 HEX 串。
    非法输入 raise ValueError。"""
    if typ in HEX_FMT:
        fmt = HEX_FMT[typ][0]
        try:
            num = float(value) if typ.startswith("f") else _parse_build_int(value)
            return struct.pack(fmt, num)
        except (ValueError, OverflowError, struct.error) as e:
            raise ValueError("%s: %s" % (typ, e))
    if typ == "ascii":
        try:
            return str(value).encode("ascii")
        except UnicodeEncodeError as e:
            raise ValueError("ascii: %s" % e)
    if typ == "hex":
        return parse_hex_header(str(value))          # 复用：清空格/逗号后 bytes.fromhex，奇数/非法抛 ValueError
    raise ValueError("unknown build type: %s" % typ)


def build_frame(fields, checksum_fn):
    """按字段列表拼一整帧 bytes（帧构造器用）。fields = [(kind, typ, value), ...]：
      kind='num'/'ascii'/'hex' → 用 typ+value 经 pack_field 打包；
      kind='length'            → typ 为宽度(数值类型 u8/u16be…)，值自动 = 其后所有字段字节数，按宽打包；
      kind='checksum'          → typ 为算法下标(CHECKSUM_KEYS 的 index)，值自动 = checksum_fn(已拼字节, 下标)。
    checksum_fn(data:bytes, algo_idx:int) -> bytes 注入（解耦，实参用 CommTool.compute_checksum）。
    length 覆盖「其后全部字节」、checksum 覆盖「其前全部字节」（隐式范围，覆盖 Modbus CRC / NMEA XOR /
    帧头+长度+载荷）。任一字段非法 raise ValueError。"""
    sizes = []                                       # 先算每字段字节长，供 length 累加其后长度
    for idx, (kind, typ, value) in enumerate(fields):
        try:
            if kind == "num":
                if typ not in HEX_FMT:
                    raise ValueError("numeric field requires numeric type: %s" % typ)
                sizes.append(len(pack_field(value, typ)))
            elif kind == "ascii":
                if typ != "ascii":
                    raise ValueError("ascii field requires ascii type: %s" % typ)
                sizes.append(len(pack_field(value, typ)))
            elif kind == "hex":
                if typ != "hex":
                    raise ValueError("hex field requires hex type: %s" % typ)
                sizes.append(len(pack_field(value, typ)))
            elif kind == "length":
                if typ not in ("u8", "u16be"):
                    raise ValueError("unsupported length width: %s" % typ)
                sizes.append(HEX_FMT[typ][1])
            elif kind == "checksum":
                w = len(checksum_fn(b"\x00", int(typ)))   # 用非空数据探得该算法输出宽度
                if w == 0:                                # typ=0(无校验)/非法下标 → 显式报错，不静默贡献 0 字节
                    raise ValueError("invalid checksum algorithm: %s" % typ)
                sizes.append(w)
            else:
                raise ValueError("unknown field kind: %s" % kind)
        except Exception as e:
            raise BuildFieldError(idx, e) from e
    out = bytearray()
    for idx, (kind, typ, value) in enumerate(fields):
        try:
            if kind in ("num", "ascii", "hex"):
                out += pack_field(value, typ)
            elif kind == "length":
                out += pack_field(sum(sizes[idx + 1:]), typ)        # 其后字节数，按宽度编码
            elif kind == "checksum":
                if not out:
                    raise ValueError("checksum requires preceding data")
                out += checksum_fn(bytes(out), int(typ))            # 其前全部字节的校验
        except Exception as e:
            raise BuildFieldError(idx, e) from e
    return bytes(out)


def iter_frames(buf, header):
    """每个接收包视作一帧（适配串口按间隔分包、每包一帧的设备）。
    无帧头 → 返回 [整包]；有帧头 → 包以帧头**开头**才返回 [整包]，否则 []（过滤掉非目标帧）。
    帧头只作「包开头前缀」筛选、**不在包内搜索**——否则帧头字节恰好出现在别的帧数据里会被误切。
    字段偏移相对包(帧)起点。"""
    if not header:
        return [buf]
    return [buf] if buf.startswith(header) else []


def _hex_sample(buf, n=16):
    """Short HEX sample for diagnostics; empty if no bytes."""
    chunk = bytes(buf or b"")[:n]
    return chunk.hex(" ").upper() if chunk else ""


def scan_length_frames(buf, header, len_off, len_width, len_extra,
                       len_be=False, max_frame=4096):
    """Same split as iter_length_frames, plus discard / wait counters.

    Returns (frames, remaining, stats) where stats keys are:
      header_skip, bad_length, oversize, waiting, last_reason, last_sample.
    Empty header → no frames, remaining is the original buf (caller passthrough).
    """
    stats = {
        "header_skip": 0,
        "bad_length": 0,
        "oversize": 0,
        "waiting": 0,
        "last_reason": "",
        "last_sample": "",
    }
    buf = bytes(buf or b"")
    header = bytes(header or b"")
    if not header:
        stats["waiting"] = len(buf)
        return [], buf, stats
    i, n = 0, len(buf)
    frames = []
    while i < n:
        j = buf.find(header, i)
        if j < 0:
            tail = len(header) - 1
            skip = n - i - tail if tail > 0 else n - i
            if skip < 0:
                skip = 0
            if skip:
                stats["header_skip"] += skip
                stats["last_reason"] = "header_skip"
                stats["last_sample"] = _hex_sample(buf[i:])
            remaining = buf[n - tail:] if tail > 0 else b""
            stats["waiting"] = len(remaining)
            return frames, remaining, stats
        if j > i:
            stats["header_skip"] += j - i
            stats["last_reason"] = "header_skip"
            stats["last_sample"] = _hex_sample(buf[i:j])
        i = j
        need = len_off + len_width
        if n - i < need:
            remaining = buf[i:]
            stats["waiting"] = len(remaining)
            return frames, remaining, stats
        L = int.from_bytes(buf[i + len_off:i + need], "big" if len_be else "little")
        total = L + len_extra
        if total < need or total > max_frame:
            stats["last_sample"] = _hex_sample(buf[i:i + need])
            if total > max_frame:
                stats["oversize"] += 1
                stats["last_reason"] = "oversize"
            else:
                stats["bad_length"] += 1
                stats["last_reason"] = "bad_length"
            i += 1
            continue
        if n - i < total:
            remaining = buf[i:]
            stats["waiting"] = len(remaining)
            return frames, remaining, stats
        frames.append(buf[i:i + total])
        i += total
    remaining = buf[i:]
    stats["waiting"] = len(remaining)
    return frames, remaining, stats


def iter_length_frames(buf, header, len_off, len_width, len_extra,
                       len_be=False, max_frame=4096):
    """按「帧头 + 长度字段」从字节流 buf 中切出完整帧，处理串口/TCP 的粘包与拆包。

    与 iter_frames（每包一帧、帧头仅前缀过滤）不同：本函数面向**跨包字节流**——
    用帧头定位帧起点、再读长度字段算出整帧边界，凑满一帧才产出，半帧留到下次拼。

    header    : 帧头 bytes（须非空；空则不组帧、原样退回 buf 交调用方处理）
    len_off   : 长度字段相对帧头首字节的偏移
    len_width : 长度字段字节数（1/2/4）
    len_extra : 整帧总长 = 长度字段值 + len_extra（固定开销：帧头/序号/校验等非 Data 部分）
    len_be    : 长度字段大端？默认小端
    max_frame : 整帧长上限，超过即判为坏长度（防御异常数据令缓冲无限等待/吃内存）

    返回 (frames: list[bytes], remaining: bytes)：
        frames    依次切出的完整帧
        remaining 不足一帧的尾部（含可能的半个帧头），调用方须作为下次输入的前缀续上
    """
    frames, remaining, _stats = scan_length_frames(
        buf, header, len_off, len_width, len_extra, len_be, max_frame)
    return frames, remaining


def _to_int(v, default=0):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return default


def norm_stream_frame(cfg):
    """Normalize analysis-layer stream-framing config (independent of auto-reply).

    Missing / empty cfg → protocol mode off (chunk = one frame). Runtime-only
    ``_header`` is parsed bytes; bad hex → b'' (treated as disabled).
    """
    cfg = cfg or {}
    w = _to_int(cfg.get("len_width", 2), 2)
    mf = _to_int(cfg.get("max_frame", 4096), 4096)
    if mf < 16:
        mf = 16
    elif mf > 1024 * 1024:
        mf = 1024 * 1024
    out = {
        "on": bool(cfg.get("on", False)),
        "udp_stream": bool(cfg.get("udp_stream", False)),
        "header": str(cfg.get("header", "")),
        "len_off": max(0, _to_int(cfg.get("len_off", 0))),
        "len_width": w if w in (1, 2, 4) else 2,
        "len_be": bool(cfg.get("len_be", False)),
        "len_extra": max(0, _to_int(cfg.get("len_extra", 0))),
        "max_frame": mf,
    }
    try:
        out["_header"] = parse_hex_header(out["header"])
    except ValueError:
        out["_header"] = b""
    return out


def extract_rule_fields(rule, frame):
    """Extract named fields from a complete frame.

    Returns (pairs, ok, oob) where pairs is [(name, off, typ, value), ...]
    for successful reads; oob counts missing/out-of-range fields.
    """
    pairs = []
    ok = oob = 0
    frame = bytes(frame or b"")
    for name, off, typ in (rule or {}).get("fields") or ():
        size = field_size(typ)
        if size <= 0 or off < 0 or off + size > len(frame):
            oob += 1
            continue
        value = read_field(frame, off, typ)
        if value is None:
            oob += 1
            continue
        ok += 1
        pairs.append((name, off, typ, value))
    return pairs, ok, oob


# ----- frame_rules (S-2 R11) ------------------------------------------------

def parse_frame_rules(raw):
    """Parse multiline frame_rules text -> list of rule dicts.

    Each rule: {header: bytes, header_str: str, fields: [(name, off, typ), ...]}.
    Blank / #comment lines skipped; malformed lines skipped (not raised).
    Lines without '|' treat the whole line as field spec (empty header).
    """
    rules = []
    for ln in str(raw or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        hdr_s, fld_s = (ln.split("|", 1) if "|" in ln else ("", ln))
        try:
            header = parse_hex_header(hdr_s.strip())
            fields = parse_field_spec(fld_s.strip())
        except (ValueError, TypeError):
            continue
        if fields:
            rules.append({
                "header": header,
                "header_str": hdr_s.strip() or "*",
                "fields": fields,
            })
    return rules


def first_matching_rule(rules, data):
    """First rule whose header is empty or a prefix of data; else None."""
    data = bytes(data or b"")
    for r in rules or ():
        hdr = r.get("header") or b""
        if not hdr or data.startswith(hdr):
            return r
    return None


def field_disp(typ, v):
    """Field value -> tooltip/display text.

    hexN/strN keep string form; numeric types with 'x' -> hex; else decimal/float.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if is_hex_num(typ) and isinstance(v, int):
        return ("0x%X" % v) if v >= 0 else ("-0x%X" % (-v))
    if isinstance(v, float):
        return "%.6g" % v
    return str(v)
