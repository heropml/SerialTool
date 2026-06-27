# -*- coding: utf-8 -*-
"""Modbus RTU 从机模型（纯逻辑，无 Qt 依赖）—— 供自动应答的「Modbus 从机」模式用。

把主机发来的 RTU 请求帧解析、按功能码从内置寄存器表组装标准 RTU 响应（含 CRC）；
写类功能码（05/06/0F/10）会改运行态寄存器表。被 main_window 在 _auto_reply 里调用。

四类数据区（地址 0 基，Modbus PDU 寻址）：
  线圈 coils(0x，1 位，读 01 / 写 05·0F) · 离散输入 discrete(1x，1 位，只读 02)
  保持寄存器 holding(4x，16 位，读 03 / 写 06·10) · 输入寄存器 input(3x，16 位，只读 04)
未配置地址默认 0（稀疏表）。
"""

# 异常码（响应功能码 = 请求功能码 | 0x80）
EXC_ILLEGAL_FUNCTION = 0x01   # 非法功能
EXC_ILLEGAL_ADDRESS = 0x02    # 非法数据地址
EXC_ILLEGAL_VALUE = 0x03      # 非法数据值

_READ_FUNCS = (0x01, 0x02, 0x03, 0x04)
_WRITE_SINGLE = (0x05, 0x06)
_WRITE_MULTI = (0x0F, 0x10)
SUPPORTED_FUNCS = _READ_FUNCS + _WRITE_SINGLE + _WRITE_MULTI


class ModbusException(Exception):
    """抛出后由 handle() 转成 Modbus 异常响应。"""
    def __init__(self, code):
        super().__init__("modbus exc %d" % code)
        self.code = code


def crc16(data: bytes) -> bytes:
    """Modbus CRC16，返回 2 字节 [lo, hi]（RTU 帧尾的追加顺序）。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def _u16(data: bytes, off: int) -> int:
    """大端 16 位（Modbus 字节序）。越界抛 IndexError，由调用方兜底。"""
    return (data[off] << 8) | data[off + 1]


def expected_len(buf: bytes):
    """据功能码算「一个完整请求帧」的字节长度。
    返回 int=该帧长度；None=还需更多字节才能判断；-1=功能码无法识别（调用方改用 CRC 探测）。"""
    if len(buf) < 2:
        return None
    func = buf[1]
    if func in _READ_FUNCS or func in _WRITE_SINGLE:
        return 8                       # addr(1)+func(1)+地址(2)+数量或值(2)+crc(2)
    if func in _WRITE_MULTI:
        if len(buf) < 7:
            return None                # 还读不到字节计数字段
        byte_count = buf[6]
        return 9 + byte_count          # 7 字节头 + 数据(byte_count) + crc(2)
    return -1                          # 未知功能码


def _crc_scan(rest: bytes, maxlen=256):
    """未知功能码：长度无法由功能码推出 → 从最短(4 字节)起找第一个 CRC 自洽的帧长度。
    这样不支持但合法的功能码（如 07/08/0B…）也能被 handle() 收到、回「非法功能」异常，
    且不会按固定长度乱切而吃掉紧随其后的合法帧。找不到返回 None（等更多字节再试）。"""
    hi = min(maxlen, len(rest))
    for m in range(4, hi + 1):
        if crc16(rest[:m - 2]) == rest[m - 2:m]:
            return m
    return None


def _next_complete_frame(rest: bytes, known_only=False):
    """找损坏前缀之后的完整 CRC 自洽帧；优先找长度确定的已支持功能码。"""
    for off in range(1, len(rest) - 3):
        tail = rest[off:]
        ln = expected_len(tail)
        if ln is None or ln == -1:
            continue
        if len(tail) >= ln and crc16(tail[:ln - 2]) == tail[ln - 2:ln]:
            return off
    if known_only:
        return None
    for off in range(1, len(rest) - 3):
        tail = rest[off:]
        if expected_len(tail) == -1 and _crc_scan(tail) is not None:
            return off
    return None


def _multi_header_valid(rest: bytes):
    """0F/10 请求头的数量与 byte_count 是否自洽；调用时保证已有 7 字节头。"""
    func, qty, byte_count = rest[1], _u16(rest, 4), rest[6]
    if func == 0x0F:
        return 1 <= qty <= 1968 and byte_count == (qty + 7) // 8
    if func == 0x10:
        return 1 <= qty <= 123 and byte_count == qty * 2
    return True


def iter_frames(buf: bytes):
    """从跨包字节流切出完整 RTU 请求帧，返回 (frames, remainder)。
    RTU 本应靠 T3.5 帧间静默分帧；这里没有静默，改用「功能码长度 + CRC 自洽」双重判定，并在 CRC
    不符时逐字节重同步——避免一次错位（线噪声/残留/粘包）后永久失步、把后续所有合法帧静默吞掉。
    已知功能码：按长度取整帧并校验 CRC，符→产出，不符→丢 1 字节重对齐；未知功能码：CRC 探测帧长。
    最小帧 4 字节(addr+func+crc2)。"""
    frames = []
    i, n = 0, len(buf)
    while n - i >= 4:
        rest = buf[i:]
        ln = expected_len(rest)
        if ln is None:
            break                          # 字节不够判断长度（写多功能码还没收到字节计数）→ 等更多字节
        if ln == -1:                        # 未知功能码：长度无法由功能码推出 → CRC 探测
            m = _crc_scan(rest)
            if m is not None:
                frames.append(bytes(rest[:m]))
                i += m
            else:
                # 可能只是未知功能码的半包，不能立即丢首字节。只有后面已经出现一个完整合法帧，
                # 才能证明当前前缀是坏流并安全重同步；否则原样保留等下一批字节。
                off = _next_complete_frame(rest)
                if off is None:
                    break
                i += off
            continue
        if n - i < ln:
            # 0F/10 的 byte_count 可能来自噪声并虚报很大长度。若后方已有 CRC 正确的已知帧，
            # 且请求头内部已不自洽，则跳到后者；头部自洽的合法半包始终原样等待。
            if rest[1] not in _WRITE_MULTI or _multi_header_valid(rest):
                break
            off = _next_complete_frame(rest, known_only=True)
            if off is None:
                break
            i += off
            continue
        if crc16(rest[:ln - 2]) == rest[ln - 2:ln]:
            frames.append(bytes(rest[:ln]))   # 功能码长度 + CRC 双中 → 整帧
            i += ln
        else:
            i += 1                         # CRC 不符（错位/坏帧）→ 丢 1 字节重同步，杜绝永久失步
    return frames, bytes(buf[i:])


class ModbusSlave:
    def __init__(self, addr=1, coils=None, discrete=None, holding=None, input_regs=None):
        self.addr = int(addr) & 0xFF
        self.coils = dict(coils or {})       # {int addr: bool}
        self.discrete = dict(discrete or {})  # {int addr: bool}
        self.holding = dict(holding or {})    # {int addr: int 0..65535}
        self.input = dict(input_regs or {})   # {int addr: int 0..65535}

    # ---- 解析一帧 → 响应字节（或 None=不响应）----
    def handle(self, frame: bytes):
        """frame=一个完整 RTU 帧。返回响应 bytes；CRC 错 / 非本机 / 广播(addr 0) 时返回 None。
        广播帧仍会执行写（无响应）。"""
        if len(frame) < 4:
            return None
        if crc16(frame[:-2]) != frame[-2:]:
            return None                # CRC 不符 → 真实从机静默丢弃
        addr, func = frame[0], frame[1]
        if addr != 0 and addr != self.addr:
            return None                # 不是发给本机
        data = frame[2:-2]             # func 之后、crc 之前
        try:
            pdu = self._exec(func, data)
        except ModbusException as e:
            if addr == 0:
                return None            # 广播不响应（异常也不回）
            pdu = bytes([func | 0x80, e.code])
        except (IndexError, ValueError):
            return None                # 帧畸形（够 CRC 但字段不全）→ 不响应
        if addr == 0:
            return None                # 广播：上面已执行写，但不回响应
        body = bytes([self.addr]) + pdu
        return body + crc16(body)

    # ---- 按功能码执行，返回响应 PDU（func + data），异常抛 ModbusException ----
    def _exec(self, func, data):
        if func in (0x03, 0x04):                      # 读保持 / 输入寄存器
            start, qty = _u16(data, 0), _u16(data, 2)
            if not (1 <= qty <= 125):
                raise ModbusException(EXC_ILLEGAL_VALUE)
            if start + qty > 0x10000:                  # 越过 16 位地址空间 → 非法地址
                raise ModbusException(EXC_ILLEGAL_ADDRESS)
            table = self.holding if func == 0x03 else self.input
            payload = bytearray([qty * 2])
            for i in range(qty):
                v = int(table.get(start + i, 0)) & 0xFFFF
                payload += bytes([(v >> 8) & 0xFF, v & 0xFF])
            return bytes([func]) + bytes(payload)

        if func in (0x01, 0x02):                      # 读线圈 / 离散输入
            start, qty = _u16(data, 0), _u16(data, 2)
            if not (1 <= qty <= 2000):
                raise ModbusException(EXC_ILLEGAL_VALUE)
            if start + qty > 0x10000:                  # 越过 16 位地址空间 → 非法地址
                raise ModbusException(EXC_ILLEGAL_ADDRESS)
            table = self.coils if func == 0x01 else self.discrete
            nbytes = (qty + 7) // 8
            bits = bytearray(nbytes)
            for i in range(qty):
                if table.get(start + i, False):
                    bits[i // 8] |= (1 << (i % 8))
            return bytes([func, nbytes]) + bytes(bits)

        if func == 0x06:                              # 写单个保持寄存器
            addr_, val = _u16(data, 0), _u16(data, 2)
            self.holding[addr_] = val & 0xFFFF
            return bytes([func]) + data[:4]           # 回显 地址+值

        if func == 0x05:                              # 写单个线圈
            addr_, val = _u16(data, 0), _u16(data, 2)
            if val not in (0x0000, 0xFF00):
                raise ModbusException(EXC_ILLEGAL_VALUE)
            self.coils[addr_] = (val == 0xFF00)
            return bytes([func]) + data[:4]           # 回显 地址+值

        if func == 0x10:                              # 写多个保持寄存器
            start, qty, bc = _u16(data, 0), _u16(data, 2), data[4]
            if not (1 <= qty <= 123) or bc != qty * 2 or len(data) < 5 + bc:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            if start + qty > 0x10000:                  # 越过 16 位地址空间 → 非法地址
                raise ModbusException(EXC_ILLEGAL_ADDRESS)
            for i in range(qty):
                self.holding[start + i] = _u16(data, 5 + i * 2) & 0xFFFF
            return bytes([func]) + data[:4]           # 回显 起始地址+数量

        if func == 0x0F:                              # 写多个线圈
            start, qty, bc = _u16(data, 0), _u16(data, 2), data[4]
            if not (1 <= qty <= 1968) or bc != (qty + 7) // 8 or len(data) < 5 + bc:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            if start + qty > 0x10000:                  # 越过 16 位地址空间 → 非法地址
                raise ModbusException(EXC_ILLEGAL_ADDRESS)
            for i in range(qty):
                self.coils[start + i] = bool(data[5 + i // 8] & (1 << (i % 8)))
            return bytes([func]) + data[:4]           # 回显 起始地址+数量

        raise ModbusException(EXC_ILLEGAL_FUNCTION)


def slave_from_config(cfg: dict) -> ModbusSlave:
    """从持久化配置 dict 建 ModbusSlave。稀疏表的键是 str(地址)，这里转回 int；坏值跳过。"""
    def _ints(m, as_bool):
        out = {}
        for k, v in (m or {}).items():
            try:
                a = int(k)
            except (ValueError, TypeError):
                continue
            out[a] = bool(v) if as_bool else (int(v) & 0xFFFF)
        return out
    cfg = cfg or {}
    try:
        addr = int(cfg.get("addr", 1))
    except (ValueError, TypeError):
        addr = 1
    return ModbusSlave(
        addr=addr,
        coils=_ints(cfg.get("coils"), True),
        discrete=_ints(cfg.get("discrete"), True),
        holding=_ints(cfg.get("holding"), False),
        input_regs=_ints(cfg.get("input"), False),
    )
