# -*- coding: utf-8 -*-
"""Modbus RTU/ASCII 从机模型（纯逻辑，无 Qt 依赖）—— 供自动应答的「Modbus 从机」模式用。

把主机发来的请求帧解析、按功能码从内置寄存器表组装标准响应（RTU 含 CRC / ASCII 含 LRC）；
写类功能码（05/06/0F/10/17）会改运行态寄存器表。被 main_window 在 _auto_reply 里调用。

四类数据区（地址 0 基，Modbus PDU 寻址）：
  线圈 coils(0x，1 位，读 01 / 写 05·0F) · 离散输入 discrete(1x，1 位，只读 02)
  保持寄存器 holding(4x，16 位，读 03 / 写 06·10) · 输入寄存器 input(3x，16 位，只读 04)
未配置地址默认 0（稀疏表）。

除基础读写外还支持诊断类功能码：08 回环诊断 / 0B 事件计数器 / 11 读从机 ID / 17 读写多寄存器。
寄存器值可由 DynamicEngine 动态生成（递增/递减/随机/正弦/斜坡），
响应也可由 ExceptionInjector 按策略改成异常帧，用于测主机的异常处理分支。
"""

from modbus.modbus_dyn import DynamicEngine, ExceptionInjector

# 异常码（响应功能码 = 请求功能码 | 0x80）
EXC_ILLEGAL_FUNCTION = 0x01   # 非法功能
EXC_ILLEGAL_ADDRESS = 0x02    # 非法数据地址
EXC_ILLEGAL_VALUE = 0x03      # 非法数据值
EXC_SLAVE_DEVICE_FAILURE = 0x04   # 从机设备故障（异常注入的默认码）

_READ_FUNCS = (0x01, 0x02, 0x03, 0x04)
_WRITE_SINGLE = (0x05, 0x06)
_WRITE_MULTI = (0x0F, 0x10)
# 广播（地址 0）按规范只允许写类功能码，且从机一律不回响应。
# 17(读写多寄存器) 含读，不可广播；08/0B/11 是诊断类，也都要求点对点。
_BROADCAST_WRITE_FUNCS = _WRITE_SINGLE + _WRITE_MULTI + (0x16,)
SUPPORTED_FUNCS = _READ_FUNCS + _WRITE_SINGLE + _WRITE_MULTI + (0x08, 0x0B, 0x11, 0x16, 0x17, 0x2B)
# Known-function resync is cheap and scans the whole buffer. CRC blind scanning
# for unknown functions is much more expensive, so cap only that second pass.
_RESYNC_UNKNOWN_SCAN_MAX = 512


class ModbusException(Exception):
    """抛出后由 handle() 转成 Modbus 异常响应。"""

    def __init__(self, code):
        super().__init__("modbus exc %d" % code)
        self.code = code


def crc16(data):
    """Modbus CRC16，返回 2 字节 [lo, hi]（RTU 帧尾的追加顺序）。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def _u16(data, off):
    """大端 16 位（Modbus 字节序）。越界抛 IndexError，由调用方兜底。"""
    return (data[off] << 8) | data[off + 1]


def lrc8(data):
    """Modbus ASCII 纵向冗余校验：8 位二进制补码和（覆盖 addr+PDU），返回 0..255。"""
    return (-sum(data)) & 0xFF


def ascii_wrap(body):
    """addr+PDU → 完整 ASCII 帧 ``:`` + hex(addr+pdu+lrc).upper() + ``\\r\\n``。"""
    chunk = body + bytes((lrc8(body),))
    return b":" + chunk.hex().upper().encode("ascii") + b"\r\n"


def parse_ascii_frame(frame):
    """完整 ASCII 帧 → (addr, func, data) 或 None（非 ASCII / LRC 错 / 畸形）。
    data = func 之后、LRC 之前的 payload。frame 含 ``:`` 与 CRLF；末尾 CRLF 容错缺失。"""
    if len(frame) < 4 or frame[:1] != b":":
        return None
    raw_hex = frame[1:].rstrip(b"\r\n")
    # ASCII 内容只能是偶数个十六进制字符，最少 addr+func+lrc = 3 字节 = 6 hex
    if len(raw_hex) < 6 or len(raw_hex) % 2:
        return None
    try:
        raw = bytes.fromhex(raw_hex.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return None
    if lrc8(raw[:-1]) != raw[-1]:
        return None
    return raw[0], raw[1], raw[2:-1]


def iter_ascii_frames(buf):
    """从字节流切出完整 ASCII 帧（``:`` 起、``\\n`` 止）。返回 (frames, remainder)。

    ``:`` 不可能出现在 hex 内容里，故每个 ``:`` 必为帧首；未见到 ``\\n`` 的尾部原样保留等更多字节。
    LRC 在切帧阶段不校验（坏帧交给 parse_ascii_frame → handle 返回 None 静默丢弃，与 RTU CRC 失败一致）。
    """
    frames, i = [], 0
    while True:
        start = buf.find(b":", i)
        if start < 0:
            return frames, b""            # 无帧首：前导垃圾整体丢弃
        end = buf.find(b"\n", start)
        if end < 0:
            return frames, buf[start:]    # 帧未完：保留从 ':' 起的尾部
        frames.append(buf[start:end + 1])
        i = end + 1


def expected_len(buf):
    """据功能码算「一个完整请求帧」的字节长度。
    返回 int=该帧长度；None=还需更多字节才能判断；-1=功能码无法识别（调用方改用 CRC 探测）。"""
    if len(buf) < 2:
        return None
    func = buf[1]
    # 读 01-04 / 写单 05-06 / 诊断 08：addr(1)+func(1)+地址或子功能(2)+数量或值(2)+crc(2)
    if func in _READ_FUNCS or func in _WRITE_SINGLE or func == 0x08:
        return 8
    if func in (0x0B, 0x11):
        return 4                          # 无数据段：addr(1)+func(1)+crc(2)
    if func == 0x16:
        return 10                         # addr+and+or + crc
    if func == 0x2B:
        return 7                          # MEI + read_code + object_id + crc
    if func in _WRITE_MULTI:
        # 7 字节头 + 数据(byte_count) + crc(2)；还读不到字节计数字段就先等
        return None if len(buf) < 7 else 9 + buf[6]
    if func == 0x17:
        # 11 字节头（读地址/读数量/写地址/写数量/字节计数）+ 写数据 + crc(2)
        return None if len(buf) < 11 else 13 + buf[10]
    return -1                             # 未知功能码


def _crc_scan(rest, maxlen=256):
    """未知功能码：长度无法由功能码推出 → 从最短(4 字节)起找第一个 CRC 自洽的帧长度。
    这样不支持但合法的功能码也能被 handle() 收到、回「非法功能」异常，
    且不会按固定长度乱切而吃掉紧随其后的合法帧。找不到返回 None（等更多字节再试）。"""
    limit = min(maxlen, len(rest))
    crc = 0xFFFF
    # Grow the candidate body one byte at a time. Recomputing crc16(rest[:n])
    # for every n makes one blind scan quadratic before resync even advances.
    for body_end in range(1, limit - 1):
        crc ^= rest[body_end - 1]
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
        size = body_end + 2
        if size >= 4 and bytes((crc & 0xFF, (crc >> 8) & 0xFF)) == rest[body_end:size]:
            return size
    return None


def _fc08_loopback_len(rest):
    """08 sub-function 0 (Return Query Data) carries `N x 2` data bytes per spec
    6.8, so expected_len()'s 8 is only its shortest legal form. Return the
    CRC-confirmed length of a longer one, else None.
    Every other sub-function has a fixed 2-byte data field (0x0A..0x12/0x14 are
    all `00 00`), so 8 stays right for them -- do not widen this.
    Only consulted after the 8-byte reading already failed CRC, so a well-formed
    minimal frame can never be re-cut here."""
    if len(rest) < 10 or rest[1] != 0x08 or _u16(rest, 2) != 0:
        return None
    for size in range(10, min(256, len(rest)) + 1, 2):   # data is N x 2 -> even
        if crc16(rest[:size - 2]) == rest[size - 2:size]:
            return size
    return None


def _fc08_no_data_len(rest):
    """Short form of an 08 request: sub-function code and no data field, so 6
    bytes instead of 8. Spec 6.8 always specifies a 2-byte request data field
    (`00 00` for 0x0A..0x12/0x14), so this is only a tolerance fallback -- it is
    consulted after the 8-byte reading already failed CRC, and it answers with
    Illegal Data Value rather than dropping the request without a word.
    Sub-function 0 is excluded: its data field is `N x 2` bytes, so a short read
    there could cut a still-arriving loopback frame. Returns 6 or None."""
    if len(rest) < 6 or rest[1] != 0x08 or _u16(rest, 2) == 0:
        return None
    return 6 if crc16(rest[:4]) == rest[4:6] else None


def _fc08_loopback_growing(rest):
    """True when `rest` is too short to tell a corrupt 8-byte 08 loopback frame
    from the start of a longer one, so the caller must wait for more bytes
    rather than drop the leading byte and lose the frame for good."""
    return len(rest) < 10 and rest[1] == 0x08 and _u16(rest, 2) == 0


def _next_complete_frame(rest, known_only=False):
    """找损坏前缀之后的完整 CRC 自洽帧；优先找长度确定的已支持功能码。
    known_only=True 时只认长度可推的功能码，不做 CRC 盲扫（半包重同步场景用，避免误判）。"""
    for off in range(1, len(rest) - 3):
        tail = rest[off:]
        size = expected_len(tail)
        if size in (None, -1):
            continue
        if len(tail) >= size and crc16(tail[:size - 2]) == tail[size - 2:size]:
            return off
    if known_only:
        return None
    # 第二轮：未知功能码靠 CRC 探测，噪声之后照样能重新对齐
    for off in range(1, min(len(rest) - 3, _RESYNC_UNKNOWN_SCAN_MAX + 1)):
        tail = rest[off:]
        if expected_len(tail) == -1 and _crc_scan(tail) is not None:
            return off
        if _fc08_loopback_len(tail) is not None:
            return off
        if _fc08_no_data_len(tail) is not None:
            return off
    return None


def _multi_header_valid(rest):
    """0F/10 请求头的数量与 byte_count 是否自洽；头不足 7 字节时按「暂且可信」处理。"""
    if len(rest) < 7:
        return True
    func, qty, count = rest[1], _u16(rest, 4), rest[6]
    if func == 0x0F:
        return 1 <= qty <= 1968 and count == (qty + 7) // 8
    if func == 0x10:
        return 1 <= qty <= 123 and count == qty * 2
    return True


def _fc23_header_valid(rest):
    """17 请求头的读/写数量与 byte_count 是否自洽；头不足 11 字节时按「暂且可信」处理。
    17 的 byte_count 同样可能被噪声污染成大值（最多虚报 255 → 帧长 268），
    没有这道校验就会把后续所有合法帧一起吞掉，直到缓冲上限才恢复。"""
    if len(rest) < 11:
        return True
    read_qty = _u16(rest, 4)
    write_qty = _u16(rest, 8)
    byte_count = rest[10]
    return (1 <= read_qty <= 125 and 1 <= write_qty <= 121
            and byte_count == write_qty * 2)


def iter_frames(buf):
    """从跨包字节流切出完整 RTU 请求帧，返回 (frames, remainder)。
    RTU 本应靠 T3.5 帧间静默分帧；这里没有静默，改用「功能码长度 + CRC 自洽」双重判定，并在 CRC
    不符时逐字节重同步——避免一次错位（线噪声/残留/粘包）后永久失步、把后续所有合法帧静默吞掉。
    已知功能码：按长度取整帧并校验 CRC，符→产出，不符→丢 1 字节重对齐；未知功能码：CRC 探测帧长。
    最小帧 4 字节(addr+func+crc2)。"""
    frames, i = [], 0
    view = memoryview(buf)                 # suffix slices stay O(1) views
    while len(buf) - i >= 4:
        rest = view[i:]
        size = expected_len(rest)
        if size is None:
            break                         # 字节不够判断长度 → 等更多字节
        if size == -1:                    # 未知功能码：长度无法由功能码推出 → CRC 探测
            size = _crc_scan(rest)
            if size is None:
                # 可能只是未知功能码的半包，不能立即丢首字节。只有后面已经出现一个完整合法帧，
                # 才能证明当前前缀是坏流并安全重同步；否则原样保留等下一批字节。
                off = _next_complete_frame(rest)
                if off is None:
                    break
                i += off
                continue
        if len(rest) < size:
            short = _fc08_no_data_len(rest)
            if short is not None:
                frames.append(bytes(rest[:short]))   # 6-byte 08 request
                i += short
                continue
            # 0F/10/17 的 byte_count 可能来自噪声并虚报很大长度。若请求头内部已不自洽，
            # 且后方已有 CRC 正确的已知帧，则跳到后者；头部自洽的合法半包始终原样等待。
            recover = False
            if rest[1] in _WRITE_MULTI:
                recover = not _multi_header_valid(rest)
            elif rest[1] == 0x17:
                recover = not _fc23_header_valid(rest)
            if not recover:
                break
            off = _next_complete_frame(rest, known_only=True)
            if off is None:
                break
            i += off
            continue
        if crc16(rest[:size - 2]) == rest[size - 2:size]:
            frames.append(bytes(rest[:size]))    # 功能码长度 + CRC 双中 → 整帧
            i += size
        else:
            longer = _fc08_loopback_len(rest) or _fc08_no_data_len(rest)
            if longer is not None:
                frames.append(bytes(rest[:longer]))   # long or short 08 frame
                i += longer
            elif _fc08_loopback_growing(rest):
                break                     # may still be arriving: keep every byte
            else:
                i += 1                        # CRC 不符：丢 1 字节重对齐
    return frames, bytes(buf[i:])


class ModbusSlave:
    """单个从机：四张稀疏寄存器表 + 动态值引擎 + 异常注入器 + 总线计数器。"""

    def __init__(self, addr=1, coils=None, discrete=None, holding=None,
                 input_regs=None, dynamics=None, exception_policy=None,
                 server_id=b"CommTool", device_id_objects=None):
        self.addr = max(0, min(0xFF, int(addr)))   # clamp 而非回绕：addr=300 不能静默变成 44
        self.coils = dict(coils or {})
        self.discrete = dict(discrete or {})
        self.holding = dict(holding or {})
        self.input = dict(input_regs or {})
        self.dynamic_engine = DynamicEngine(dynamics)
        self.exception_injector = ExceptionInjector(exception_policy)
        self.server_id = (server_id.encode("utf-8") if isinstance(server_id, str)
                          else bytes(server_id or b"CommTool"))
        self.device_id_objects = self._norm_device_id_objects(device_id_objects)
        # 0B「读事件计数器」用：收到的合法报文数 / CRC·LRC 校验失败数，均按 16 位回绕
        self.bus_msg_count = 0
        self.bus_comm_error = 0

    @staticmethod
    def _norm_device_id_objects(objects):
        """Map object id 0..255 -> bytes; defaults cover basic Vendor/Product/Rev."""
        defaults = {
            0: b"CommTool",
            1: b"Slave",
            2: b"1.0",
        }
        out = dict(defaults)
        for key, value in (objects or {}).items():
            try:
                oid = int(key)
            except (TypeError, ValueError):
                continue
            if not 0 <= oid <= 255:
                continue
            if isinstance(value, str):
                value = value.encode("utf-8", "replace")
            else:
                value = bytes(value or b"")
            out[oid] = value[:240]
        return out

    def _value(self, space, table, addr):
        """读取某地址的当前值：动态规则优先，没有规则就回落到静态表（缺省 0）。"""
        return self.dynamic_engine.value(space, addr, fallback=table.get(addr, 0))

    def _write(self, space, table, addr, value):
        """主机写入：落静态表，同时通知动态引擎（写入会覆盖该点的动态值直到复位）。"""
        table[addr] = value
        self.dynamic_engine.note_write(space, addr, value)

    def _inject(self, func, data):
        """按注入策略决定是否把本次请求变成异常响应。
        只有带地址字段的功能码才提取起始地址供 addrs 过滤；08 的前两字节是子功能，不是地址。"""
        start = None
        if func in (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x0F, 0x10, 0x16, 0x17) and len(data) >= 2:
            start = _u16(data, 0)
        if func == 0x17 and len(data) >= 6:
            # 17 同时读写两段：写段起始地址也要参与addrs 过滤，否则只盯写入地址的策略永远不生效。
            start = (start, _u16(data, 4))
        code = self.exception_injector.should_raise(func, start)
        if code is not None:
            raise ModbusException(code)

    def _respond(self, addr, func, data):
        """执行请求并组出「从机地址 + PDU」；广播(addr=0)执行写但不回响应。
        畸形数据（越界索引/坏值）静默丢弃，与 CRC 失败一致，不回异常帧。"""
        try:
            pdu = self._exec(func, data, allow_inject=(addr != 0))
        except ModbusException as exc:
            pdu = bytes((func | 0x80, exc.code))
        except (IndexError, ValueError):
            return None
        return None if addr == 0 else bytes((self.addr,)) + pdu

    def handle(self, frame):
        """完整 RTU 请求帧 → 完整 RTU 响应帧（含 CRC）；不该应答时返回 None。"""
        if len(frame) < 4 or crc16(frame[:-2]) != frame[-2:]:
            self.bus_comm_error += 1
            return None
        addr, func = frame[0], frame[1]
        if addr not in (0, self.addr) or (addr == 0 and func not in _BROADCAST_WRITE_FUNCS):
            return None
        self.bus_msg_count = (self.bus_msg_count + 1) & 0xFFFF
        body = self._respond(addr, func, frame[2:-2])
        return None if body is None else body + crc16(body)

    def handle_ascii(self, frame):
        """完整 ASCII 请求帧 → 完整 ASCII 响应帧（含 LRC）；不该应答时返回 None。"""
        parsed = parse_ascii_frame(frame)
        if parsed is None:
            self.bus_comm_error += 1
            return None
        addr, func, data = parsed
        if addr not in (0, self.addr) or (addr == 0 and func not in _BROADCAST_WRITE_FUNCS):
            return None
        self.bus_msg_count = (self.bus_msg_count + 1) & 0xFFFF
        body = self._respond(addr, func, data)
        return None if body is None else ascii_wrap(body)

    def _read_regs(self, func, start, qty):
        """03/04 读寄存器的公共实现；17 的读段也复用它（按 03 取保持寄存器）。"""
        if not 1 <= qty <= 125:
            raise ModbusException(EXC_ILLEGAL_VALUE)
        if start + qty > 0x10000:                 # 越过 16 位地址空间 → 非法地址
            raise ModbusException(EXC_ILLEGAL_ADDRESS)
        table, space = (self.holding, "holding") if func == 3 else (self.input, "input")
        out = bytearray((qty * 2,))               # 首字节 = 后续字节数
        for i in range(qty):
            value = int(self._value(space, table, start + i)) & 0xFFFF
            out += bytes((value >> 8, value & 0xFF))
        return bytes((func,)) + bytes(out)

    def _exec(self, func, data, allow_inject=True):
        """按功能码执行请求，返回响应 PDU（func + 数据）。data = func 之后的请求负载。
        allow_inject=False 用于广播：广播照常执行写，但不做异常注入（本来也没人收响应）。"""
        if allow_inject:
            self._inject(func, data)

        if func in (0x03, 0x04):                  # 读保持 / 输入寄存器
            return self._read_regs(func, _u16(data, 0), _u16(data, 2))

        if func in (0x01, 0x02):                  # 读线圈 / 离散输入
            start, qty = _u16(data, 0), _u16(data, 2)
            if not 1 <= qty <= 2000:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            if start + qty > 0x10000:             # 越过 16 位地址空间 → 非法地址
                raise ModbusException(EXC_ILLEGAL_ADDRESS)
            table, space = ((self.coils, "coils") if func == 0x01
                            else (self.discrete, "discrete"))
            bits = bytearray((qty + 7) // 8)
            for i in range(qty):
                if self._value(space, table, start + i):
                    bits[i // 8] |= 1 << (i % 8)
            return bytes((func, len(bits))) + bytes(bits)

        if func == 0x05:                          # 写单个线圈
            addr, value = _u16(data, 0), _u16(data, 2)
            if value not in (0x0000, 0xFF00):
                raise ModbusException(EXC_ILLEGAL_VALUE)
            self._write("coils", self.coils, addr, value == 0xFF00)
            return bytes((func,)) + data[:4]      # 回显 地址+值

        if func == 0x06:                          # 写单个保持寄存器
            addr, value = _u16(data, 0), _u16(data, 2)
            self._write("holding", self.holding, addr, value)
            return bytes((func,)) + data[:4]      # 回显 地址+值

        if func in (0x0F, 0x10):                  # 写多个线圈 / 保持寄存器
            start, qty, count = _u16(data, 0), _u16(data, 2), data[4]
            expected = (qty + 7) // 8 if func == 0x0F else qty * 2
            limit = 1968 if func == 0x0F else 123
            if not 1 <= qty <= limit or count != expected or len(data) < 5 + count:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            if start + qty > 0x10000:             # 越过 16 位地址空间 → 非法地址
                raise ModbusException(EXC_ILLEGAL_ADDRESS)
            for i in range(qty):
                if func == 0x0F:
                    bit = bool(data[5 + i // 8] & (1 << (i % 8)))
                    self._write("coils", self.coils, start + i, bit)
                else:
                    self._write("holding", self.holding, start + i, _u16(data, 5 + 2 * i))
            return bytes((func,)) + data[:4]      # 回显 起始地址+数量

        if func == 0x08:                          # 诊断：只实现子功能 0（回环，原样回请求数据）
            if _u16(data, 0) != 0:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            # Spec 6.8: the loopback reply must be identical to the request, so
            # echo every data word instead of only the first one.
            if len(data) % 2 or len(data) > 252:      # N x 2, and PDU <= 253
                raise ModbusException(EXC_ILLEGAL_VALUE)
            return bytes((func,)) + data

        if func == 0x0B:                          # 读事件计数器：状态(2)恒 0 + 计数(2)
            return bytes((func, 0, 0,
                          self.bus_msg_count >> 8, self.bus_msg_count & 0xFF))

        if func == 0x11:                          # 读从机 ID：ID 串 + 运行指示(0xFF=运行中)
            # 末字节留给运行指示，ID 最长 250，保证 byte_count 不溢出单字节
            sid = bytes(self.server_id or b"")[:250]
            payload = sid + b"\xff"
            if len(payload) < 2:                  # ID 为空时补一字节，满足 bc>=2 的解析约定
                payload = b"\x00\xff"
            return bytes((func, len(payload))) + payload

        if func == 0x16:                          # Mask Write Register
            if len(data) < 6:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            addr, and_m, or_m = _u16(data, 0), _u16(data, 2), _u16(data, 4)
            cur = int(self._value("holding", self.holding, addr)) & 0xFFFF
            # Spec: result = (current AND and) OR (or AND NOT and)
            result = (cur & and_m) | (or_m & (~and_m & 0xFFFF))
            self._write("holding", self.holding, addr, result & 0xFFFF)
            return bytes((func,)) + data[:6]      # echo addr+and+or

        if func == 0x2B:                          # Encapsulated Interface Transport
            if len(data) < 3:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            mei, read_code, obj_id = data[0], data[1], data[2]
            if mei != 0x0E:
                raise ModbusException(EXC_ILLEGAL_FUNCTION)
            objs = self.device_id_objects
            if read_code == 1:                     # basic stream
                ids = [i for i in (0, 1, 2) if i in objs]
                conformity = 0x81                 # basic + individual access
            elif read_code == 2:                   # basic + regular stream
                ids = sorted(i for i in objs if i < 0x80)
                conformity = 0x82
            elif read_code == 3:                   # extended stream
                ids = sorted(i for i in objs if i >= 0x80)
                if not ids:
                    ids = sorted(objs)
                conformity = 0x83
            elif read_code == 4:                   # specific object
                if obj_id not in objs:
                    raise ModbusException(EXC_ILLEGAL_ADDRESS)
                ids = [obj_id]
                conformity = 0x81
            else:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            # Pack objects; keep PDU under 253 bytes (func already counted outside).
            body = bytearray()
            packed = 0
            more = 0
            next_id = 0
            for oid in ids:
                val = bytes(objs[oid])
                chunk = bytes((oid, len(val))) + val
                # header after objects: mei+rc+conf+more+next+nobj = 6
                if 1 + 6 + len(body) + len(chunk) > 253:
                    more = 0xFF
                    next_id = oid
                    break
                body += chunk
                packed += 1
            return bytes((func, mei, read_code, conformity, more, next_id, packed)) + bytes(body)

        if func == 0x17:                          # 读写多个寄存器：先写后读（规范要求的次序）
            rs, rq = _u16(data, 0), _u16(data, 2)
            ws, wq, count = _u16(data, 4), _u16(data, 6), data[8]
            if not 1 <= rq <= 125 or not 1 <= wq <= 121 or count != wq * 2 or len(data) < 9 + count:
                raise ModbusException(EXC_ILLEGAL_VALUE)
            if rs + rq > 0x10000 or ws + wq > 0x10000:
                raise ModbusException(EXC_ILLEGAL_ADDRESS)
            for i in range(wq):
                self._write("holding", self.holding, ws + i, _u16(data, 9 + i * 2))
            response = self._read_regs(0x03, rs, rq)
            return bytes((func,)) + response[1:]  # 换成 17 的功能码，字节计数+数据照搬

        raise ModbusException(EXC_ILLEGAL_FUNCTION)


def slave_from_config(cfg):
    """从持久化配置 dict 建 ModbusSlave。稀疏表的键是 str(地址)，这里转回 int；坏值跳过。"""
    cfg = cfg or {}

    def conv(data, boolean):
        out = {}
        for key, value in (data or {}).items():
            try:
                out[int(key)] = bool(value) if boolean else int(value) & 0xFFFF
            except (TypeError, ValueError):
                continue
        return out

    try:
        addr = int(cfg.get("addr", 1))
    except (TypeError, ValueError):
        addr = 1
    # Same range as the dialog's _norm_ar_modbus: 0 is broadcast-only and
    # 248+ is reserved, so a hand-edited addr:300 must not answer as 44.
    addr = max(1, min(247, addr))
    return ModbusSlave(
        addr=addr,
        coils=conv(cfg.get("coils"), True),
        discrete=conv(cfg.get("discrete"), True),
        holding=conv(cfg.get("holding"), False),
        input_regs=conv(cfg.get("input"), False),
        dynamics=cfg.get("dynamics"),
        exception_policy=cfg.get("exception"),
        server_id=cfg.get("server_id", b"CommTool"),
        device_id_objects=cfg.get("device_id_objects"),
    )


class MultiSlaveBank:
    """一条总线上的多个从机：按帧首地址分发；广播帧转给全部从机且不回响应。
    与 ModbusSlave 接口一致（handle / handle_ascii），main_window 可直接互换使用。"""

    def __init__(self, slaves=None, on=True):
        self.slaves = {s.addr: s for s in (slaves or []) if isinstance(s, ModbusSlave)}
        self.on = bool(on)

    def handle(self, frame):
        if not self.on or len(frame) < 2:
            return None
        if frame[0] == 0:                         # 广播：非写类不受理，写类全员执行但都不回
            if frame[1] not in _BROADCAST_WRITE_FUNCS:
                return None
            for slave in self.slaves.values():
                slave.handle(frame)
            return None
        slave = self.slaves.get(frame[0])
        return slave.handle(frame) if slave else None

    def handle_ascii(self, frame):
        if not self.on:
            return None
        parsed = parse_ascii_frame(frame)
        if parsed is None:
            return None
        if parsed[0] == 0:
            if parsed[1] not in _BROADCAST_WRITE_FUNCS:
                return None
            for slave in self.slaves.values():
                slave.handle_ascii(frame)
            return None
        slave = self.slaves.get(parsed[0])
        return slave.handle_ascii(frame) if slave else None


def _merge_slave_cfg(base, item):
    """子从机没单独配的动态规则/异常策略/从机 ID，继承顶层同名配置。"""
    out = dict(item or {})
    for key in ("dynamics", "exception", "server_id"):
        if key not in out or out.get(key) in (None, {}, []):
            if key in base:
                out[key] = base[key]
    return out


def slave_bank_from_config(cfg):
    """从持久化配置建 MultiSlaveBank：有 slaves 列表就多从机，否则按顶层配置建单从机。
    重复地址只保留第一个（同地址两台从机会互相抢答，等于配置错误）。"""
    cfg = cfg or {}
    if not isinstance(cfg, dict):
        return MultiSlaveBank()
    # slaves 为空列表时不能当多从机处理，否则整个银行为空、所有请求静默无响应
    if isinstance(cfg.get("slaves"), list) and cfg.get("slaves"):
        items = []
        seen = set()
        for item in cfg["slaves"]:
            if not isinstance(item, dict):
                continue
            slave = slave_from_config(_merge_slave_cfg(cfg, item))
            if slave.addr in seen:
                continue
            seen.add(slave.addr)
            items.append(slave)
        return MultiSlaveBank(items, cfg.get("on", True))
    return MultiSlaveBank([slave_from_config(cfg)], cfg.get("on", True))
