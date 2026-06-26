# -*- coding: utf-8 -*-
"""二进制协议解析原语（不依赖 pyqtgraph）。

波形图(plot_dialog) 与 帧解析表(frame_dialog) 共用，保证两处「帧头 / 字段定义」语义一致：
- 字段定义：`名称=偏移:类型`（名称可省，省则用 "偏移:类型" 当名）
- 类型：数值 u8/i8/u16le/u16be/i16le/i16be/u32../i32../f32le/f32be；
        外加 hexN（N 字节按 HEX 串）/ strN（N 字节 ASCII），后两者仅用于帧解析表展示。
- 帧定位：两种粒度——
    · iter_frames：不带帧长，把上层一个接收块视作一帧，帧头仅作前缀过滤；
    · iter_length_frames：带「帧头 + 长度字段」，维护跨包字节流按整帧边界切，
      能处理串口/TCP 的粘包与拆包（自动应答的「帧头+长度组帧」用它）。
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


def iter_frames(buf, header):
    """每个接收包视作一帧（适配串口按间隔分包、每包一帧的设备）。
    无帧头 → 返回 [整包]；有帧头 → 包以帧头**开头**才返回 [整包]，否则 []（过滤掉非目标帧）。
    帧头只作「包开头前缀」筛选、**不在包内搜索**——否则帧头字节恰好出现在别的帧数据里会被误切。
    字段偏移相对包(帧)起点。"""
    if not header:
        return [buf]
    return [buf] if buf.startswith(header) else []


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
    frames = []
    if not header:
        return frames, buf
    i, n = 0, len(buf)
    while i < n:
        j = buf.find(header, i)
        if j < 0:
            # 没找到帧头：丢弃绝大部分垃圾，只留末尾 len(header)-1 字节（可能是半个帧头）
            tail = len(header) - 1
            return frames, (buf[n - tail:] if tail > 0 else b"")
        i = j                                       # 对齐帧头（丢弃 j 之前的垃圾字节）
        need = len_off + len_width
        if n - i < need:
            break                                   # 长度字段还没收齐 → 等下次
        L = int.from_bytes(buf[i + len_off:i + need], "big" if len_be else "little")
        total = L + len_extra
        if total < need or total > max_frame:
            i += 1                                  # 坏长度：跳过这个帧头，继续找下一个
            continue
        if n - i < total:
            break                                   # 整帧还没收齐 → 等下次
        frames.append(buf[i:i + total])
        i += total
    return frames, buf[i:]
