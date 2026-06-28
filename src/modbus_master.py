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
SUPPORTED_FUNCS = READ_FUNCS + WRITE_SINGLE


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


def _read_qty_clamp(func, qty):
    """读数量上限：线圈/离散 1..2000，寄存器 1..125（Modbus 规范）。"""
    hi = 2000 if func in (0x01, 0x02) else 125
    return max(1, min(int(qty), hi))


def _build_pdu(func, addr, qty_or_val):
    """组 PDU（func 起，不含 unit / crc / mbap）。
    读 01-04：qty_or_val=数量；写 06：qty_or_val=寄存器值；写 05：qty_or_val 真→ON(0xFF00) 假→OFF。"""
    addr &= 0xFFFF
    if func in READ_FUNCS:
        qty = _read_qty_clamp(func, qty_or_val)
        return bytes([func, (addr >> 8) & 0xFF, addr & 0xFF, (qty >> 8) & 0xFF, qty & 0xFF])
    if func == 0x06:
        v = int(qty_or_val) & 0xFFFF
        return bytes([func, (addr >> 8) & 0xFF, addr & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
    if func == 0x05:
        v = 0xFF00 if qty_or_val else 0x0000
        return bytes([func, (addr >> 8) & 0xFF, addr & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
    raise ValueError("unsupported function 0x%02X" % func)


def build_rtu_request(unit, func, addr, qty_or_val):
    """RTU 请求帧 = unit + PDU + CRC16。"""
    body = bytes([int(unit) & 0xFF]) + _build_pdu(func, addr, qty_or_val)
    return body + crc16(body)


def build_tcp_request(tid, unit, func, addr, qty_or_val):
    """Modbus-TCP 请求帧 = MBAP(事务ID + 协议ID0 + 长度 + unit) + PDU，无 CRC。"""
    pdu = _build_pdu(func, addr, qty_or_val)
    length = len(pdu) + 1                  # unit(1) + PDU
    tid &= 0xFFFF
    mbap = bytes([(tid >> 8) & 0xFF, tid & 0xFF, 0x00, 0x00,
                  (length >> 8) & 0xFF, length & 0xFF, int(unit) & 0xFF])
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
        raise ModbusException(pdu[1] if len(pdu) > 1 else 0)
    if func != req_func:
        raise ValueError("function mismatch: req 0x%02X resp 0x%02X" % (req_func, func))
    if func in (0x03, 0x04):                           # 读保持 / 输入寄存器
        bc = pdu[1]
        if bc % 2 or len(pdu) < 2 + bc:
            raise ValueError("bad register byte count")
        return {"regs": [_u16(pdu, 2 + i * 2) for i in range(bc // 2)]}
    if func in (0x01, 0x02):                           # 读线圈 / 离散输入
        bc = pdu[1]
        if len(pdu) < 2 + bc:
            raise ValueError("bad coil byte count")
        bits = [bool(pdu[2 + i // 8] & (1 << (i % 8))) for i in range(bc * 8)]
        return {"bits": bits}
    if func in (0x05, 0x06):                           # 写单线圈 / 单寄存器 → 回显 地址+值
        if len(pdu) < 5:
            raise ValueError("short echo")
        return {"echo": (_u16(pdu, 1), _u16(pdu, 3))}
    raise ValueError("unsupported response function 0x%02X" % func)


def rtu_normal_len(req_func, qty):
    """正常（非异常）RTU 响应总长度（含 unit + CRC2）。写类固定回显 8 字节。"""
    if req_func in (0x03, 0x04):
        return 5 + _read_qty_clamp(req_func, qty) * 2          # unit+func+bc + qty*2 + crc2
    if req_func in (0x01, 0x02):
        return 5 + (_read_qty_clamp(req_func, qty) + 7) // 8   # unit+func+bc + ceil(qty/8) + crc2
    if req_func in WRITE_SINGLE:
        return 8                                               # unit+func+addr2+val2 + crc2
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
    if length < 2:
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


def normalize_poll(rec):
    """把一条轮询配置规范化成 dict（容错 str/0x/缺字段）。键：
      name 名称 · unit 从机ID · func 功能码 · addr 起始地址 · qty 数量 · period 周期ms ·
      enabled 启用 · wval 写值(写类用)。读类 func 时 qty 钳到规范上限，写类 qty 置 1。"""
    def _int(v, default=0, base=0):
        try:
            if isinstance(v, str):
                return int(v.strip(), base) if v.strip() else default
            return int(v)
        except (ValueError, TypeError):
            return default
    func = _int(rec.get("func", 3))
    if func not in SUPPORTED_FUNCS:
        func = 3
    unit = max(0, min(_int(rec.get("unit", 1)), 247))
    addr = max(0, min(_int(rec.get("addr", 0)), 0xFFFF))
    if func in READ_FUNCS:
        qty = _read_qty_clamp(func, _int(rec.get("qty", 1)))
    else:
        qty = 1
    return {
        "name": str(rec.get("name", "") or ""),
        "unit": unit,
        "func": func,
        "addr": addr,
        "qty": qty,
        "period": max(20, _int(rec.get("period", 1000))),
        "enabled": bool(rec.get("enabled", True)),
        "wval": _int(rec.get("wval", 0)),
    }
