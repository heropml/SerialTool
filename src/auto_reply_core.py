# -*- coding: utf-8 -*-
"""Auto-reply match / CRC / checksum core (Qt-free).

Extracted from main_window.CommTool for S-2: keep matching and
checksum algorithms testable without PyQt5.
"""
import re
import time

def crc_impl(data, width=16, poly=0x1021, init=0x0000,
                 refin=False, refout=False, xorout=0x0000, byteorder="big"):
    """通用 CRC 实现。放在模块顶层，供主进程 ctx 和 spawn 脚本子进程共用。"""
    data = bytes(data)
    mask = (1 << width) - 1
    topbit = 1 << (width - 1)

    def _refl(v, n):
        r = 0
        for i in range(n):
            if v & (1 << i):
                r |= 1 << (n - 1 - i)
        return r

    reg = init & mask
    for b in data:
        if refin:
            b = _refl(b, 8)
        reg ^= (b << (width - 8)) & mask
        for _ in range(8):
            reg = ((reg << 1) ^ poly) & mask if (reg & topbit) else (reg << 1) & mask
    if refout:
        reg = _refl(reg, width)
    reg = (reg ^ xorout) & mask
    return reg.to_bytes((width + 7) // 8, byteorder)


def to_int(v, default=0):
    """容错 int：ini/json 被手改成非数字时不让启动崩。"""
    try:
        return int(v or 0)
    except (ValueError, TypeError):
        return default


def parse_hex_pat(s):
    """解析 HEX 匹配 pattern → list[(值, 掩码)]，命中条件 (字节 & 掩码) == (值 & 掩码)。
    支持（D 位掩码/字段级匹配）：
      AB          整字节精确         → (0xAB, 0xFF)
      ?? / XX     整字节通配         → (0x00, 0x00)
      A? / ?5     半字节通配(X 同 ?) → (0xA0, 0xF0) / (0x05, 0x0F)
      b:1xxxxxx1  位级掩码(8 位 0/1/x，x=该位不关心) → (0x81, 0x81)
    为保证旧规则零回归，先完整尝试旧解析（删除空格后按字节解析）；旧语法能成功时
    立即返回，只有失败后才按新掩码语法解析。`b:…` 的冒号在旧 HEX 中非法，
    因此任意数量的位掩码都不会与旧规则撞义；token 须由空格/边界切出。
    格式错误返回 None（整条规则跳过，与原行为一致）。"""
    # 旧版会先删除所有半字节之间的空格；例如 `A b10000000` 是合法的
    # `AB 10 00 00 00`。必须先跑原解析器，否则中间的 b-token 会抢占旧语义。
    legacy = s.replace(" ", "").upper()
    if legacy and len(legacy) % 2 == 0:
        legacy_out = []
        for i in range(0, len(legacy), 2):
            pair = legacy[i:i + 2]
            if pair in ("??", "XX"):
                legacy_out.append((0x00, 0x00))
            else:
                try:
                    legacy_out.append((int(pair, 16), 0xFF))
                except ValueError:
                    break
        else:
            return legacy_out

    out = []
    buf = []   # 累积的 HEX 半字节字符（跨空格拼接）

    def flush_hex():
        chars = "".join(buf)
        buf.clear()
        if not chars:
            return True
        if len(chars) % 2:
            return False
        for i in range(0, len(chars), 2):
            val = msk = 0
            for nib in (chars[i], chars[i + 1]):
                val <<= 4
                msk <<= 4
                if nib in "?X":
                    pass                       # 通配半字节：掩码该半字节为 0
                elif nib in "0123456789ABCDEF":
                    val |= int(nib, 16)
                    msk |= 0xF
                else:
                    return False
            out.append((val, msk))
        return True

    for tok in s.upper().split():
        if tok.startswith("B:") and len(tok) == 10 and all(c in "01X" for c in tok[2:]):
            if not flush_hex():                # 先消化前面累积的 hex
                return None
            val = msk = 0
            for c in tok[2:]:
                val <<= 1
                msk <<= 1
                if c == "1":
                    val |= 1
                    msk |= 1
                elif c == "0":
                    msk |= 1
                # 'X'：该位 val/msk 均 0（不关心）
            out.append((val, msk))
        else:
            buf.append(tok)
    if not flush_hex():
        return None
    return out or None


def hex_at(pat, data, off):
    """带掩码的 HEX pattern 是否在 data 偏移 off 处命中。pat 元素为 (值, 掩码)：
    命中需 (data[off+i] & 掩码) == (值 & 掩码)。掩码 0xFF=精确、0x00=整字节通配。"""
    if off < 0 or off + len(pat) > len(data):
        return False
    for i, (v, m) in enumerate(pat):
        if (data[off + i] & m) != (v & m):
            return False
    return True


def hit_test(rule, data, text):
    """rule 是否匹配 data（text=已按编码解码的文本，文本模式用）。只测匹配本身，
    不含 verify / 长度 / 冷却 —— 供实时匹配(_ar_match)与离线测试器(_ar_preview)共用。"""
    m = (rule.get("match") or "").strip()
    if not m:
        return False
    mode = to_int(rule.get("mode", 0))     # 0=包含 1=相等 2=前缀
    if mode not in (0, 1, 2):
        mode = 0       # 配置坏掉退回「包含」
    if rule.get("match_hex", True):
        pat = parse_hex_pat(m)
        if not pat:
            return False
        n = len(pat)
        if mode == 2:
            return hex_at(pat, data, 0)
        if mode == 1:
            return len(data) == n and hex_at(pat, data, 0)
        return any(hex_at(pat, data, i) for i in range(len(data) - n + 1))
    if mode == 1:
        return text.strip() == m
    if mode == 2:
        return text.startswith(m)
    return m in text


def crc(data, width=16, poly=0x1021, init=0x0000,
            refin=False, refout=False, xorout=0x0000, byteorder="big"):
    """通用参数化 CRC（Rocksoft 模型）→ bytes（width//8 字节，按 byteorder）。
    覆盖 CCITT / Modbus / XMODEM / 任意自定义多项式，供脚本 ctx.crc 调用。"""
    return crc_impl(data, width, poly, init, refin, refout, xorout, byteorder)


def parse_delay(v):
    """C7 延时字段 → (min,max) ms。支持 'N'(固定) 或 'N-M'(随机范围)；坏值回退 (0,0)。"""
    s = str(v if v is not None else "").strip()
    body = s[1:] if s.startswith("-") else s     # 开头负号不当分隔符
    if "-" in body:
        head, _, tail = body.partition("-")
        if s.startswith("-"):
            head = "-" + head
        lo = to_int(head, 0)
        hi = to_int(tail, 0)
        return (lo, hi) if hi >= lo else (hi, lo)
    n = to_int(s, 0)
    return (n, n)


def norm_idx(v, n):
    """把可能为负的下标归一到 [0..]：负数从末尾算（-1=最后一字节）。"""
    i = int(v)
    return i + n if i < 0 else i


def compute_checksum(data: bytes, index: int) -> bytes:
    if not data or index <= 0:
        return b""
    if index == 1:  # ADD8
        return bytes([sum(data) & 0xFF])
    if index == 2:  # ~ADD8
        return bytes([(~sum(data)) & 0xFF])
    if index == 3:  # XOR8
        x = 0
        for b in data:
            x ^= b
        return bytes([x])
    if index == 4:  # CRC8 (poly 0x07)
        reg = 0
        for b in data:
            reg ^= b
            for _ in range(8):
                reg = ((reg << 1) ^ 0x07) & 0xFF if (reg & 0x80) else (reg << 1) & 0xFF
        return bytes([reg])
    if index == 5:  # ModbusCRC16
        reg = 0xFFFF
        for b in data:
            reg ^= b
            for _ in range(8):
                reg = (reg >> 1) ^ 0xA001 if (reg & 1) else (reg >> 1)
        return bytes([reg & 0xFF, (reg >> 8) & 0xFF])
    if index == 6:  # CCITT-CRC16
        reg = 0xFFFF
        for b in data:
            reg ^= (b << 8)
            for _ in range(8):
                reg = ((reg << 1) ^ 0x1021) & 0xFFFF if (reg & 0x8000) else (reg << 1) & 0xFFFF
        return bytes([(reg >> 8) & 0xFF, reg & 0xFF])
    if index == 7:  # CRC32
        import zlib
        val = zlib.crc32(data) & 0xFFFFFFFF
        return bytes([(val >> 24) & 0xFF, (val >> 16) & 0xFF,
                      (val >> 8) & 0xFF, val & 0xFF])
    if index == 8:  # ADD16
        s = sum(data) & 0xFFFF
        return bytes([(s >> 8) & 0xFF, s & 0xFF])
    if index == 9:  # MOBUS: CRC8 with poly 0x31
        reg = 0
        for b in data:
            reg ^= b
            for _ in range(8):
                reg = ((reg << 1) ^ 0x31) & 0xFF if (reg & 0x80) else (reg << 1) & 0xFF
        return bytes([reg])
    return b""


def frame_ok(frame: bytes, idx: int) -> bool:
    """收包校验：尾部 N 字节应等于前面内容按算法 idx 算出的校验。idx<=0 不校验直接放行。
    帧太短或校验不符 → False（不应答）。"""
    if idx <= 0:
        return True
    try:
        n = len(compute_checksum(b"\x00", idx))   # 该算法校验字节数(MOBUS=1, CRC16=2…)
    except Exception:
        return True
    if n == 0 or len(frame) <= n:
        return False
    try:
        return compute_checksum(frame[:-n], idx) == frame[-n:]
    except Exception:
        return False



# ----- Config normalizers (S-2 R10) -----------------------------------------

def state_tokens(when):
    """Rule 'when' field -> state token list (comma-separated, strip each).

    Empty -> [] meaning match-any when SM is on.
    """
    return [t.strip() for t in str(when or "").split(",") if t.strip()]


def norm_frame(cfg):
    """Normalize header+length framing config; pre-parse header bytes as _header.

    _header is runtime-only: bad hex -> b'' (treated as disabled by auto_reply).
    """
    import binproto
    cfg = cfg or {}
    w = to_int(cfg.get("len_width", 2))
    out = {
        "on": bool(cfg.get("on", False)),
        "header": str(cfg.get("header", "")),
        "len_off": max(0, to_int(cfg.get("len_off", 0))),
        "len_width": w if w in (1, 2, 4) else 2,
        "len_be": bool(cfg.get("len_be", False)),
        "len_extra": max(0, to_int(cfg.get("len_extra", 0))),
    }
    try:
        out["_header"] = binproto.parse_hex_header(out["header"])
    except ValueError:
        out["_header"] = b""
    return out


def norm_fault(cfg):
    """Normalize global fault-injection percentages (0..100)."""
    cfg = cfg or {}

    def pct(v):
        return max(0, min(100, to_int(v, 0)))

    return {
        "on": bool(cfg.get("on", False)),
        "drop": pct(cfg.get("drop", 0)),
        "badcrc": pct(cfg.get("badcrc", 0)),
        "badlen": pct(cfg.get("badlen", 0)),
    }


def norm_sm(cfg):
    """Normalize state-machine config (on + init)."""
    cfg = cfg or {}
    return {
        "on": bool(cfg.get("on", False)),
        "init": str(cfg.get("init", "") or "").strip(),
    }


def _regmap(m, as_bool):
    out = {}
    if isinstance(m, dict):
        for k, v in m.items():
            try:
                a = int(k)
            except (ValueError, TypeError):
                continue
            out[str(a)] = bool(v) if as_bool else (to_int(v) & 0xFFFF)
    return out


def norm_modbus(cfg):
    """Normalize Modbus slave bank config (top-level + optional slaves list)."""
    cfg = cfg or {}
    variant = str(cfg.get("variant", "rtu") or "rtu").lower()
    if variant not in ("rtu", "ascii"):
        variant = "rtu"
    slaves_in = cfg.get("slaves")
    slaves_out = []
    if isinstance(slaves_in, list) and slaves_in:
        for item in slaves_in:
            if not isinstance(item, dict):
                continue
            entry = {
                "addr": max(1, min(247, to_int(item.get("addr", 1)) or 1)),
                "coils": _regmap(item.get("coils"), True),
                "discrete": _regmap(item.get("discrete"), True),
                "holding": _regmap(item.get("holding"), False),
                "input": _regmap(item.get("input"), False),
                "dynamics": (item.get("dynamics")
                             if isinstance(item.get("dynamics"), list) else []),
                "exception": (item.get("exception")
                              if isinstance(item.get("exception"), dict) else {}),
            }
            if item.get("server_id"):
                entry["server_id"] = item["server_id"]
            slaves_out.append(entry)
    base = {
        "on": bool(cfg.get("on", False)),
        "addr": max(1, min(247, to_int(cfg.get("addr", 1)) or 1)),
        "variant": variant,
        "coils": _regmap(cfg.get("coils"), True),
        "discrete": _regmap(cfg.get("discrete"), True),
        "holding": _regmap(cfg.get("holding"), False),
        "input": _regmap(cfg.get("input"), False),
        "dynamics": cfg.get("dynamics") if isinstance(cfg.get("dynamics"), list) else [],
        "exception": cfg.get("exception") if isinstance(cfg.get("exception"), dict) else {},
        "server_id": cfg.get("server_id", "CommTool"),
    }
    if slaves_out:
        base["slaves"] = slaves_out
    return base


import re as _re
import random as _random


def reply_hex_bytes(text):
    """Parse hex-mode reply text -> bytes; bad hex -> None.

    Strips /* */ // # comments, 0x prefixes, and common separators.
    """
    s = _re.sub(r"/\*.*?\*/", "", text or "", flags=_re.DOTALL)
    s = _re.sub(r"//[^\n]*", "", s)
    s = _re.sub(r"#[^\n]*", "", s)
    s = s.replace("0x", "").replace("0X", "")
    s = "".join(c for c in s if c not in " \t\r\n-:,;")
    if not s or len(s) % 2:
        return None
    try:
        return bytes.fromhex(s)
    except ValueError:
        return None


def reply_bytes(text, hexmode, encode_fn):
    """Reply text -> bytes; hexmode uses reply_hex_bytes, else encode_fn(text)."""
    if not hexmode:
        return encode_fn(text or "")
    return reply_hex_bytes(text)


def apply_cs_segs(buf, segs, checksum_fn):
    """Apply checksum segments onto bytearray buf in order; return buf."""
    buf = buf if isinstance(buf, bytearray) else bytearray(buf or b"")
    for seg in (segs or []):
        try:
            algo = to_int(seg.get("algo", 0))
            if algo <= 0:
                continue
            n = len(buf)
            lo = norm_idx(seg.get("start", 0), n)
            end = seg.get("end", None)
            hi = (n - 1) if end in (None, "") else norm_idx(end, n)
            if lo < 0 or hi < lo or hi >= n:
                continue
            chk = checksum_fn(bytes(buf[lo:hi + 1]), algo)
            if not chk:
                continue
            at = seg.get("at", None)
            if at in (None, ""):
                buf += chk
            else:
                pos = norm_idx(at, len(buf))
                if pos < 0 or pos + len(chk) > len(buf):
                    continue
                buf[pos:pos + len(chk)] = chk
        except Exception:
            continue
    return buf


def compose_frame(text, hexmode, cs_segs, cs, encode_fn, checksum_fn=None):
    """Single reply segment -> final TX bytes (or None on bad hex)."""
    checksum_fn = checksum_fn or compute_checksum
    data = reply_bytes(text, hexmode, encode_fn)
    if data is None:
        return None
    buf = apply_cs_segs(bytearray(data), cs_segs or [], checksum_fn)
    csi = to_int(cs)
    if csi > 0:
        buf += checksum_fn(bytes(buf), csi)
    return bytes(buf)


def apply_fault(frame, fault_cfg, rng=None):
    """Global fault injection.

    Returns (frame_or_None, tags) where tags is a list of
    'drop' | 'badlen' | 'badcrc'. Caller localizes notes.
    """
    fc = fault_cfg or {}
    if not fc.get("on") or not frame:
        return frame, []
    rng = _random if rng is None else rng
    if rng.random() * 100 < to_int(fc.get("drop", 0)):
        return None, ["drop"]
    buf = bytearray(frame)
    tags = []
    if len(buf) > 1 and rng.random() * 100 < to_int(fc.get("badlen", 0)):
        buf.pop()
        tags.append("badlen")
    if len(buf) >= 1 and rng.random() * 100 < to_int(fc.get("badcrc", 0)):
        buf[-1] ^= 0xFF
        tags.append("badcrc")
    return bytes(buf), tags


_SUBST_RE = _re.compile(
    r"\{r(\d+)(?:([+^])(0x[0-9A-Fa-f]+|\d+)|-(\d+))?\}"
)


def subst_reply(reply, data, hex_mode, seq=0, ts_ms=None):
    """Substitute reply placeholders; return (text, new_seq).

    Placeholders: {rN} {rN-M} {rN+K} {rN^K} {seq} {ts}.
    {seq} advances seq only when present. ts_ms defaults to None -> 0 bytes path
    uses provided ms (caller supplies wall clock).
    """
    data = bytes(data or b"")
    reply = reply or ""
    sep = " " if hex_mode else ""

    def byte_s(b):
        return "%02X" % (b & 0xFF) if hex_mode else chr(b & 0xFF)

    def bytes_s(bs):
        return sep.join(byte_s(b) for b in bs)

    def parse_k(s):
        return int(s, 16) if s.lower().startswith("0x") else int(s)

    if ts_ms is None:
        ts_ms = int(time.time() * 1000) & 0xFFFFFFFF
    else:
        ts_ms = int(ts_ms) & 0xFFFFFFFF
    ts_bytes = bytes([
        (ts_ms >> 24) & 0xFF, (ts_ms >> 16) & 0xFF,
        (ts_ms >> 8) & 0xFF, ts_ms & 0xFF,
    ])
    out = reply.replace("{ts}", bytes_s(ts_bytes))
    seq = int(seq or 0) & 0xFF
    if "{seq}" in out:
        seq = (seq + 1) & 0xFF
        out = out.replace("{seq}", byte_s(seq))

    def repl(m):
        n = int(m.group(1))
        op = m.group(2)
        arg = m.group(3)
        rng = m.group(4)
        if rng is not None:
            m_ = int(rng)
            lo, hi = (n, m_) if n <= m_ else (m_, n)
            return bytes_s([data[i] for i in range(lo, hi + 1) if 0 <= i < len(data)])
        if op is not None:
            if not (0 <= n < len(data)):
                return ""
            try:
                k = parse_k(arg)
            except ValueError:
                return ""
            return byte_s((data[n] + k) & 0xFF if op == "+" else data[n] ^ k)
        return byte_s(data[n]) if 0 <= n < len(data) else ""

    return _SUBST_RE.sub(repl, out), seq


def build_parts(rule, data, seq=0, ts_ms=None):
    """Split rule.reply on '|', substitute each segment.

    Returns (parts_list, new_seq). Empty segments skipped.
    """
    rule = rule or {}
    hexmode = bool(rule.get("reply_hex", True))
    parts = []
    for s in str(rule.get("reply", "") or "").split("|"):
        s = s.strip()
        if not s:
            continue
        text, seq = subst_reply(s, data, hexmode, seq=seq, ts_ms=ts_ms)
        parts.append(text)
    return parts, seq


def state_ok(sm_on, when, current_state):
    """SM gate: off -> True; on -> when empty (any) or current in tokens."""
    if not sm_on:
        return True
    toks = state_tokens(when)
    return (not toks) or (current_state in toks)


def next_state(sm_on, rule, current_state):
    """After a successful send: if SM on and goto set, return goto; else current."""
    if not sm_on:
        return current_state
    rule = rule or {}
    goto = str(rule.get("goto", "") or "").strip()
    return goto if goto else current_state
