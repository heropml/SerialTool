# -*- coding: utf-8 -*-
"""工具箱的纯转换逻辑（Qt-free，可单测）。

两类：
- 字节序列互转：HEX ⇄ 文本(按编码) ⇄ 十进制字节 ⇄ 二进制字节；
- 单值多进制：一个整数在 十进制 / HEX / 二进制 / 八进制 间转（可配位宽 + 有无符号）。

界面(toolbox_dialog)只管收集输入 / 显示，转换规则全在这里，便于单元测试。
"""
import struct

# ---------------- 字节序列 ⇄ 各表示 ----------------
def hex_to_bytes(s):
    """'01 41 FF' / '0141FF' / '01,41' → bytes；空→b''；非法字符/奇数长度 raise ValueError。"""
    t = "".join(s.split()).replace(",", "")      # 去所有空白 + 逗号
    if not t:
        return b""
    return bytes.fromhex(t)                       # 奇数长度 / 非 hex 字符 → ValueError


def bytes_to_hex(b):
    """bytes → '01 41 FF'（大写、空格分隔）。"""
    return b.hex(" ").upper()


def text_to_bytes(s, encoding="utf-8"):
    """文本 → bytes（按编码）。编码不支持该字符 raise（UnicodeEncodeError 属 ValueError 子类）。"""
    return s.encode(encoding)


def bytes_to_text(b, encoding="utf-8"):
    """bytes → 可显示文本；无法按编码解码的字节用 \\xNN 转义（可读、不炸）。"""
    return b.decode(encoding, errors="backslashreplace")


def dec_to_bytes(s):
    """'1 65 255' → bytes；每个数须 0..255，逗号或空白分隔；越界/非数 raise ValueError。"""
    out = bytearray()
    for tok in s.replace(",", " ").split():
        n = int(tok)                              # 非数 → ValueError
        if not 0 <= n <= 255:
            raise ValueError("byte out of range 0..255: %s" % tok)
        out.append(n)
    return bytes(out)


def bytes_to_dec(b):
    """bytes → '1 65 255'。"""
    return " ".join(str(x) for x in b)


def bin_to_bytes(s):
    """'00000001 01000001' → bytes；每组 1..8 位二进制，逗号或空白分隔；非法 raise ValueError。"""
    out = bytearray()
    for tok in s.replace(",", " ").split():
        if not tok or len(tok) > 8 or any(c not in "01" for c in tok):
            raise ValueError("bad binary group (1..8 bits of 0/1): %s" % tok)
        out.append(int(tok, 2))
    return bytes(out)


def bytes_to_bin(b):
    """bytes → '00000001 01000001'（每字节 8 位）。"""
    return " ".join(format(x, "08b") for x in b)


# ---------------- 单值多进制 ----------------
_BASES = {"dec": 10, "hex": 16, "bin": 2, "oct": 8}


def parse_value(s, base_name, width):
    """某进制字符串 → width 位无符号 raw 值。base_name∈{dec,hex,bin,oct}；
    十进制允许负号（按补码落进 width 位）；正数超出位宽 / 空 / 非法 raise ValueError。"""
    s = s.strip()
    if not s:
        raise ValueError("empty")
    if width not in (8, 16, 32, 64):
        raise ValueError("bad width: %s" % width)
    n = int(s, _BASES[base_name])                 # 非法 → ValueError；dec 允许负号
    mask = (1 << width) - 1
    if n > mask:
        raise ValueError("value out of range for %s-bit unsigned: %s" % (width, s))
    return n & mask                               # 负数按补码取低 width 位


def format_value(raw, width, signed):
    """width 位无符号 raw → {dec,hex,bin,oct} 四种字符串（hex/bin 补齐到位宽）。
    signed=True 时十进制按补码解读（最高位为符号位）。"""
    dec = raw
    if signed and (raw >> (width - 1)) & 1:
        dec = raw - (1 << width)
    return {
        "dec": str(dec),
        "hex": format(raw, "X").zfill(width // 4),
        "bin": format(raw, "b").zfill(width),
        "oct": format(raw, "o"),
    }


def parse_bits(s, width):
    """'0, 3 7' -> bit mask；bit 号须在 0..width-1。空 -> 0。"""
    if width not in (8, 16, 32, 64):
        raise ValueError("bad width: %s" % width)
    raw = s.replace(",", " ").strip()
    if not raw:
        return 0
    mask = 0
    for tok in raw.split():
        bit = int(tok)
        if not 0 <= bit < width:
            raise ValueError("bit out of range 0..%s: %s" % (width - 1, tok))
        mask |= 1 << bit
    return mask


def bits_from_value(raw, width):
    """width 位 raw -> '0, 3, 7'。"""
    raw &= (1 << width) - 1
    return ", ".join(str(i) for i in range(width) if raw & (1 << i))


# ---------------- 字节序列解释 / 自定义 CRC ----------------
def interpret_bytes(data, endian="be"):
    """把字节序列按常见类型解释；字节不足时该项为空。endian='le'/'be'。"""
    data = bytes(data)
    order = "little" if endian == "le" else "big"
    prefix = "<" if endian == "le" else ">"

    def _int(n, signed=False):
        return str(int.from_bytes(data[:n], order, signed=signed)) if len(data) >= n else ""

    ascii_text = "".join(chr(b) if 32 <= b <= 126 else "." for b in data)
    out = {
        "ascii": ascii_text,
        "u16": _int(2, False),
        "i16": _int(2, True),
        "u32": _int(4, False),
        "i32": _int(4, True),
        "f32": "",
    }
    if len(data) >= 4:
        out["f32"] = ("%g" % struct.unpack(prefix + "f", data[:4])[0])
    return out


def custom_crc(data, width=16, poly=0x1021, init=0, refin=False,
               refout=False, xorout=0, byteorder="big"):
    """通用 Rocksoft CRC；返回按 byteorder 排列的校验 bytes。"""
    data = bytes(data)
    if width not in (8, 16, 32, 64):
        raise ValueError("bad width: %s" % width)
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
