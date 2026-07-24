# -*- coding: utf-8 -*-
"""工具箱的纯转换逻辑（Qt-free，可单测）。

两类：
- 字节序列互转：HEX ⇄ 文本(按编码) ⇄ 十进制字节 ⇄ 二进制字节；
- 单值多进制：一个整数在 十进制 / HEX / 二进制 / 八进制 间转（可配位宽 + 有无符号）。

界面(toolbox_dialog)只管收集输入 / 显示，转换规则全在这里，便于单元测试。

另含两个供主数据区使用的纯函数（同样 Qt-free）：
- hex_line_selection_to_bytes：结合整行布局提取选中的 HEX 字节（供选中即算校验和）；
- format_numeric：字节流按数值类型渲染成序列文本（供数值视图）。
"""
import re
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


# ---------------- 数据区 HEX 选区 → 字节（选中即算校验和） ----------------
def hex_line_selection_to_bytes(line, selection_start, selection_end, hexdump=False,
                                limit=None):
    """从一整条显示行中提取「被完整选中」的 HEX 字节。

    本函数同时拿到未裁剪的整行和选区列范围，因此能辨认并跳过：
    - 普通 HEX 视图行首的时间戳和方向箭头；
    - HEX 转储的偏移列与 ASCII 列；
    - 从装饰文本或 ASCII 列内部开始的局部选区。

    只有两个十六进制字符都落在选区内才计入，半个字节 token 继续采用「宁可少算、不猜值」
    的原则。selection_end 为 Python 切片式的开区间。

    limit：取够这么多字节就停。上限必须能在「行内」生效——HEX 显示模式下不换行时整段数据
    可能全挤在一条逻辑行里（实测 1 MB 数据只分 8 块），只在调用方按行收工的话上限形同虚设。
    """
    line = str(line)
    try:
        lo = max(0, int(selection_start))
        hi = min(len(line), int(selection_end))
    except (TypeError, ValueError):
        return b""
    if lo >= hi:
        return b""

    data_start = 0
    data_end = len(line)
    if hexdump:
        # 必须看到完整的「8 位偏移 + 至少两个空格」行头才把它当转储行；否则不对任意文本猜列。
        head = re.match(r"^[0-9A-Fa-f]{8}\s{2,}", line)
        if not head:
            return b""
        data_start = head.end()
        bar = line.find("|", data_start)
        if bar >= 0:
            data_end = bar
    else:
        # 普通 HEX 行的装饰都在数据前：时间戳 [...], 方向箭头 ←/→。基于完整行定位，
        # 即使选区只截到时间戳中的 "26"，也不会把它误认成 0x26。
        if line.startswith("["):
            close = line.find("]")
            if close >= 0:
                data_start = close + 1
        for arrow in ("\u2190", "\u2192"):
            pos = line.rfind(arrow, data_start)
            if pos >= 0:
                data_start = max(data_start, pos + len(arrow))

    out = bytearray()
    token_re = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")
    for match in token_re.finditer(line, data_start, data_end):
        if lo <= match.start() and match.end() <= hi:
            out.append(int(match.group(0), 16))
            if limit is not None and len(out) > limit:
                break
    return bytes(out)


# ---------------- 字节流 → 数值序列（数值视图） ----------------
# 值：(字节宽度, struct 码, 每行默认个数, 显示列宽)。
# 窄类型每行多放几个、宽类型少放，行宽大致相当。
# 列宽按该类型的极值写死（u16→65535 占 5、i16→-32768 占 6、f32→-1.23457e+38 占 12），
# 不按本块最大值现算：现算的话每个收包各自成块、各算各的宽，量级一变纵向就参差
# （1 2 3 / 4660 65535 / 7 8 三行对不齐）。写死才能让整条流始终对齐到同一网格。
# 万一某个值超出该宽度，rjust 只是不补空格、不会截断，最多那一行凸出来。
NUM_TYPES = {
    "u8":  (1, "B", 16, 3), "i8":  (1, "b", 16, 4),
    "u16": (2, "H", 16, 5), "i16": (2, "h", 16, 6),
    "u32": (4, "I", 8, 10), "i32": (4, "i", 8, 11),
    "f32": (4, "f", 8, 12),
}


def format_numeric(data, typ="u16", endian="le", per_line=0):
    """字节流 → 数值序列文本，返回 (文本, 余数字节)。

    余数（不够凑满一个元素的尾部字节）不丢弃也不显示，而是原样返回，由调用方带到下一包
    继续拼——串口上一个 u16 被拆到两个收包里是常态，按包截断会让整条流从此错位。
    每行 per_line 个（0=按类型取默认值），各值右对齐到该类型的固定列宽（见 NUM_TYPES），
    使前后各块纵向对齐成列便于扫读。
    typ 不认识时回退 u16；data 不足一个元素时返回 ("", 原始字节)。
    """
    data = bytes(data)
    size, code, dflt, w = NUM_TYPES.get(typ, NUM_TYPES["u16"])
    n = len(data) // size
    if n <= 0:
        return "", data
    vals = struct.unpack(("<" if endian == "le" else ">") + str(n) + code, data[:n * size])
    # %.6g：定点/科学计数自动切换，既不会把 1.5 印成 1.500000，也不会丢掉 1e-8 的量级
    strs = ["%.6g" % v for v in vals] if code == "f" else [str(v) for v in vals]
    per = per_line if per_line > 0 else dflt
    lines = [" ".join(s.rjust(w) for s in strs[i:i + per])
             for i in range(0, len(strs), per)]
    return "\n".join(lines), data[n * size:]
