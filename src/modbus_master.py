# -*- coding: utf-8 -*-
"""Modbus 主机（master / client）逻辑 —— 纯逻辑无 Qt 依赖，供「Modbus 主机轮询」模式用。

职责：
  ① 构造请求帧 —— RTU（尾部追加 CRC16）/ Modbus-TCP（前置 MBAP 头、无 CRC）。
  ② 从从机响应里解析出寄存器 / 线圈值；异常响应（功能码 | 0x80）抛 ModbusException。
  ③ 从跨包字节流里切一帧响应 —— RTU 按「请求功能码 + 数量」预测响应长度并校 CRC；
     Modbus-TCP 按 MBAP 长度字段。

主机是半双工的：一次只在途一条请求，收到响应或超时后才发下一条，因此切帧时
「期望什么响应」由刚发出的请求（unit / func / qty）唯一确定，无需像从机那样做通用切帧。

复用 modbus_slave 的 crc16 / _u16 / ModbusException，避免重复实现。
"""

from modbus_slave import crc16, _u16, ModbusException

READ_FUNCS = (0x01, 0x02, 0x03, 0x04)     # 01 线圈 / 02 离散输入 / 03 保持 / 04 输入寄存器
WRITE_SINGLE = (0x05, 0x06)               # 05 写单线圈 / 06 写单寄存器
WRITE_MULTI = (0x0F, 0x10)                # 0F 写多线圈 / 10 写多寄存器（写值为列表）
SUPPORTED_FUNCS = READ_FUNCS + WRITE_SINGLE + WRITE_MULTI
MAX_TCP_MBAP_LENGTH = 254                  # Unit(1) + 最大 PDU(253)


def _exact_int(value, message="value must be an integer"):
    """解析整数但禁止 1.9→1 这类静默截断；整数值浮点数 1.0 仍可兼容 JSON。
    字符串：`0x/0o/0b` 前缀按对应进制解析，其余按十进制——故 `08`/`010` 这类前导零
    十进制可正常输入（`int(s, 0)` 会把它们当非法八进制拒掉）。"""
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(message)
    try:
        if isinstance(value, str):
            s = value.strip()
            base = 0 if s[:2].lower() in ("0x", "0o", "0b") else 10
            return int(s, base)
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(message)


def strip_local_echo(buf, request):
    """在 RTU 接收缓冲中定位并剥掉一份完整的本地请求回显。

    返回 ``(remainder, found)``。允许回显前存在噪声或上次通信的残留字节；在完整请求
    尚未出现前不消费缓冲，避免 05/06 的请求回显被后续响应解析误判为写成功。
    """
    data = bytes(buf)
    echo = bytes(request)
    if not echo:
        return data, False
    pos = data.find(echo)
    if pos < 0:
        return data, False
    return data[pos + len(echo):], True


def _read_qty(func, qty):
    """严格解析读数量：线圈/离散 1..2000，寄存器 1..125。"""
    value = _exact_int(qty, "read quantity must be an integer")
    hi = 2000 if func in (0x01, 0x02) else 125
    if not 1 <= value <= hi:
        raise ValueError("read quantity must be 1..%d" % hi)
    return value


def _check_address_span(addr, qty):
    """拒绝跨出 16 位 Modbus 地址空间的连续读写范围。"""
    if addr + qty - 1 > 0xFFFF:
        raise ValueError("address range exceeds 65535")


def _build_pdu(func, addr, qty_or_val):
    """组 PDU（func 起，不含 unit / crc / mbap）。
    读 01-04：qty_or_val=数量；写 06：qty_or_val=寄存器值；写 05：qty_or_val 真→ON(0xFF00) 假→OFF。"""
    addr = _exact_int(addr, "address must be an integer")
    if not 0 <= addr <= 0xFFFF:
        raise ValueError("address must be 0..65535")
    if func in READ_FUNCS:
        qty = _read_qty(func, qty_or_val)
        _check_address_span(addr, qty)
        return bytes([func, (addr >> 8) & 0xFF, addr & 0xFF, (qty >> 8) & 0xFF, qty & 0xFF])
    if func == 0x06:
        v = _exact_int(qty_or_val, "register value must be an integer")
        if not 0 <= v <= 0xFFFF:
            raise ValueError("register value must be 0..65535")
        return bytes([func, (addr >> 8) & 0xFF, addr & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
    if func == 0x05:
        coil = _exact_int(qty_or_val, "coil value must be an integer")
        if coil not in (0, 1):
            raise ValueError("coil value must be 0 or 1")
        v = 0xFF00 if coil else 0x0000
        return bytes([func, (addr >> 8) & 0xFF, addr & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
    if func == 0x10:                       # 写多寄存器：addr + qty + byte_count + 数据；qty_or_val=值列表
        seq = qty_or_val if isinstance(qty_or_val, (list, tuple)) else [qty_or_val]
        vals = [_exact_int(x, "register values must be integers") for x in seq]
        if not vals:
            raise ValueError("write-multiple registers requires at least one value")
        if len(vals) > 123:
            raise ValueError("write-multiple registers accepts at most 123 values")
        if any(v < 0 or v > 0xFFFF for v in vals):
            raise ValueError("register values must be 0..65535")
        qty = len(vals)
        _check_address_span(addr, qty)
        body = bytearray([func, (addr >> 8) & 0xFF, addr & 0xFF,
                          (qty >> 8) & 0xFF, qty & 0xFF, qty * 2])
        for v in vals:
            body += bytes([(v >> 8) & 0xFF, v & 0xFF])
        return bytes(body)
    if func == 0x0F:                       # 写多线圈：addr + qty + byte_count + 位；qty_or_val=0/1 列表
        seq = qty_or_val if isinstance(qty_or_val, (list, tuple)) else [qty_or_val]
        vals = [_exact_int(x, "coil values must be integers") for x in seq]
        if not vals:
            raise ValueError("write-multiple coils requires at least one value")
        if len(vals) > 1968:
            raise ValueError("write-multiple coils accepts at most 1968 values")
        if any(v not in (0, 1) for v in vals):
            raise ValueError("coil values must be 0 or 1")
        qty = len(vals)
        _check_address_span(addr, qty)
        bits = bytearray((qty + 7) // 8)
        for i, v in enumerate(vals):
            if v:
                bits[i // 8] |= (1 << (i % 8))
        return bytes(bytearray([func, (addr >> 8) & 0xFF, addr & 0xFF,
                                (qty >> 8) & 0xFF, qty & 0xFF, (qty + 7) // 8]) + bits)
    raise ValueError("unsupported function 0x%02X" % func)


def build_rtu_request(unit, func, addr, qty_or_val):
    """RTU 请求帧 = unit + PDU + CRC16。"""
    unit = _exact_int(unit, "RTU unit must be an integer")
    if not 0 <= unit <= 247:
        raise ValueError("RTU unit must be 0..247")
    body = bytes([unit]) + _build_pdu(func, addr, qty_or_val)
    return body + crc16(body)


def build_tcp_request(tid, unit, func, addr, qty_or_val):
    """Modbus-TCP 请求帧 = MBAP(事务ID + 协议ID0 + 长度 + unit) + PDU，无 CRC。"""
    unit = _exact_int(unit, "TCP unit must be an integer")
    if not 0 <= unit <= 255:
        raise ValueError("TCP unit must be 0..255")
    pdu = _build_pdu(func, addr, qty_or_val)
    length = len(pdu) + 1                  # unit(1) + PDU
    tid &= 0xFFFF
    mbap = bytes([(tid >> 8) & 0xFF, tid & 0xFF, 0x00, 0x00,
                  (length >> 8) & 0xFF, length & 0xFF, unit])
    return mbap + pdu


def parse_pdu(req_func, pdu):
    """解析响应 PDU（func 起）。成功返回 dict；异常响应抛 ModbusException；帧畸形抛 ValueError。
      读 01/02 → {"bits": [bool, ...]}（含末字节多余填充位，调用方按数量截断）
      读 03/04 → {"regs": [int, ...]}
      写 05/06 → {"echo": (addr, value)}"""
    if not pdu:
        raise ValueError("empty pdu")
    func = pdu[0]
    if func & 0x80:                                    # 异常响应：func|0x80 + 异常码
        if func != ((req_func | 0x80) & 0xFF):        # 必须是本次请求功能码的异常码（req 03 → 83）
            raise ValueError("exception func mismatch: req 0x%02X resp 0x%02X" % (req_func, func))
        if len(pdu) != 2:
            raise ValueError("bad exception response length")
        raise ModbusException(pdu[1])
    if func != req_func:
        raise ValueError("function mismatch: req 0x%02X resp 0x%02X" % (req_func, func))
    if func in (0x03, 0x04):                           # 读保持 / 输入寄存器
        if len(pdu) < 2:
            raise ValueError("short register response")
        bc = pdu[1]
        if bc % 2 or len(pdu) != 2 + bc:
            raise ValueError("bad register byte count")
        return {"regs": [_u16(pdu, 2 + i * 2) for i in range(bc // 2)]}
    if func in (0x01, 0x02):                           # 读线圈 / 离散输入
        if len(pdu) < 2:
            raise ValueError("short coil response")
        bc = pdu[1]
        if len(pdu) != 2 + bc:
            raise ValueError("bad coil byte count")
        bits = [bool(pdu[2 + i // 8] & (1 << (i % 8))) for i in range(bc * 8)]
        return {"bits": bits}
    if func in (0x05, 0x06, 0x0F, 0x10):               # 写类 → 回显 地址 + 值(单)/数量(多)
        if len(pdu) != 5:
            raise ValueError("bad write echo length")
        return {"echo": (_u16(pdu, 1), _u16(pdu, 3))}
    raise ValueError("unsupported response function 0x%02X" % func)


def rtu_normal_len(req_func, qty):
    """正常（非异常）RTU 响应总长度（含 unit + CRC2）。写类固定回显 8 字节。"""
    if req_func in (0x03, 0x04):
        return 5 + _read_qty(req_func, qty) * 2                # unit+func+bc + qty*2 + crc2
    if req_func in (0x01, 0x02):
        return 5 + (_read_qty(req_func, qty) + 7) // 8         # unit+func+bc + ceil(qty/8) + crc2
    if req_func in WRITE_SINGLE or req_func in WRITE_MULTI:
        return 8                                               # unit+func+addr2+(值/数量)2 + crc2
    return None


def take_rtu_response(buf, req_unit, req_func, qty):
    """从 RTU 字节流尝试取出对刚发请求的一帧响应。
    返回 (result_dict, consumed_len)；字节不够返回 None；CRC 错 / unit 不符抛 ValueError；
    从机异常响应抛 ModbusException。
    先判异常响应（func|0x80 → 固定 5 字节），否则按预测长度取整帧。"""
    if len(buf) < 2:
        return None
    if buf[0] != (int(req_unit) & 0xFF):
        raise ValueError("unit mismatch")
    func = buf[1]
    if func & 0x80:                                   # 异常：unit + (func|0x80) + code + crc2
        if len(buf) < 5:
            return None
        frame = bytes(buf[:5])
        if crc16(frame[:-2]) != frame[-2:]:
            raise ValueError("crc error")
        parse_pdu(req_func, frame[1:-2])              # 必抛 ModbusException
        raise ValueError("unreachable")
    ln = rtu_normal_len(req_func, qty)
    if ln is None:
        raise ValueError("unsupported function 0x%02X" % req_func)
    if len(buf) < ln:
        return None
    frame = bytes(buf[:ln])
    if crc16(frame[:-2]) != frame[-2:]:
        raise ValueError("crc error")
    return parse_pdu(req_func, frame[1:-2]), ln


def take_tcp_response(buf, req_tid, req_func, req_unit=None):
    """从 Modbus-TCP 字节流尝试取出一帧响应。
    返回 (result_dict, consumed_len)；字节不够返回 None；事务ID / 协议ID / 从机ID 不符抛 ValueError；
    从机异常响应抛 ModbusException。"""
    if len(buf) < 6:
        return None
    length = (buf[4] << 8) | buf[5]
    total = 6 + length
    if not 2 <= length <= MAX_TCP_MBAP_LENGTH:
        raise ValueError("bad mbap length %d" % length)   # 至少 unit + func
    if len(buf) < total:
        return None                                        # 还需更多字节
    frame = bytes(buf[:total])
    tid = (frame[0] << 8) | frame[1]
    proto = (frame[2] << 8) | frame[3]
    if proto != 0:
        raise ValueError("bad protocol id %d" % proto)
    if req_tid is not None and tid != (req_tid & 0xFFFF):
        raise ValueError("transaction id mismatch")
    if req_unit is not None and frame[6] != (int(req_unit) & 0xFF):
        raise ValueError("unit mismatch")
    return parse_pdu(req_func, frame[7:]), total


def take_tcp_response_matching(buf, req_tid, req_func, req_unit=None):
    """从 TCP 流中跳过完整的旧事务帧，寻找当前请求的响应。

    返回 ``(result_or_none, consumed_len)``：没有完整匹配帧时 result 为 None，consumed_len
    仍会指出可安全丢弃的旧 TID/Unit 完整帧字节数。这样迟到响应与当前响应粘包时不会把
    后者一起清空；当前事务本身的畸形 PDU 仍抛 ValueError。
    """
    data = bytes(buf)
    off = 0
    while True:
        if len(data) - off < 6:
            return None, off
        length = (data[off + 4] << 8) | data[off + 5]
        if not 2 <= length <= MAX_TCP_MBAP_LENGTH:
            raise ValueError("bad mbap length %d" % length)
        total = 6 + length
        if len(data) - off < total:
            return None, off
        frame = data[off:off + total]
        proto = (frame[2] << 8) | frame[3]
        if proto != 0:
            raise ValueError("bad protocol id %d" % proto)
        tid = (frame[0] << 8) | frame[1]
        unit_matches = req_unit is None or frame[6] == (int(req_unit) & 0xFF)
        if (req_tid is not None and tid != (req_tid & 0xFFFF)) or not unit_matches:
            off += total                       # 迟到/非本请求完整帧：安全跳过，继续找当前响应
            continue
        return parse_pdu(req_func, frame[7:]), off + total


def _as_bool(v, default=True):
    """稳健解析启用标志：字符串 'false'/'0'/'no'/'off'/'' → False（避免非空字符串恒为 True）。"""
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(v)


def normalize_poll(rec):
    """把一条轮询配置规范化成 dict（容错 str/0x/缺字段）。键：
      name 名称 · unit 从机ID · func 功能码 · addr 起始地址 · qty 数量 · period 周期ms ·
      enabled 启用 · wval 写值(05/06 用) · wvals 写值列表(0F/10 用)。
      读类 qty / period 非法时为 None；写单 qty=1；写多 qty=len(wvals)。"""
    def _vals(v):                                  # 解析多值；任一项非法则整组无效，禁止地址错位写入
        seq = v if isinstance(v, (list, tuple)) else str(v or "").replace(",", " ").split()
        out = []
        for t in seq:
            try:
                out.append(_exact_int(t))
            except (ValueError, TypeError):
                return []                          # 不能静默跳项：后续值会前移并写到错误地址
        return out

    def _write_value(v, func):
        """解析单写值并严格校验范围；None 表示输入无效。"""
        try:
            value = _exact_int(v)
        except (ValueError, TypeError):
            return None
        if func == 0x05:
            return value if value in (0, 1) else None
        return value if 0 <= value <= 0xFFFF else None

    def _bounded(v, lo, hi):
        """严格解析有界整数；None 表示空白、非法或越界。"""
        try:
            value = _exact_int(v)
        except (ValueError, TypeError):
            return None
        return value if lo <= value <= hi else None

    try:
        func = _exact_int(rec.get("func", 3))
    except ValueError:
        func = 3
    if func not in SUPPORTED_FUNCS:
        func = 3
    unit = _bounded(rec.get("unit", 1), 0, 255)  # TCP Unit ID 是完整 1 字节；RTU >247 由调度层拒绝
    addr = _bounded(rec.get("addr", 0), 0, 0xFFFF)
    period = _bounded(rec.get("period", 1000), 20, 0x7FFFFFFF)  # QTimer interval 是有符号 int
    wval, wvals = 0, []
    if func in READ_FUNCS:
        try:
            qty = _read_qty(func, rec.get("qty", 1))
        except ValueError:
            qty = None
    elif func in WRITE_SINGLE:
        qty = 1
        wval = _write_value(rec.get("wval"), func)
    else:                                          # WRITE_MULTI：写值列表，qty=列表长度
        raw = rec.get("wvals")
        if raw in (None, "", []):
            raw = rec.get("wval", "")
        vals = _vals(raw)
        if func == 0x0F:
            vals = vals if len(vals) <= 1968 and all(x in (0, 1) for x in vals) else []
        else:
            vals = vals if len(vals) <= 123 and all(0 <= x <= 0xFFFF for x in vals) else []
        wvals = vals                 # 空/非法 → 留空，不默认 [0]（避免静默写 0；由引擎判输入错误）
        qty = len(wvals) or 1        # qty 至少 1（仅用于读响应长度预测；写多空值不会真发）
    return {
        "name": str(rec.get("name", "") or ""),
        "unit": unit,
        "func": func,
        "addr": addr,
        "qty": qty,
        "period": period,
        "enabled": _as_bool(rec.get("enabled", True)),
        "wval": wval,
        "wvals": wvals,
    }
