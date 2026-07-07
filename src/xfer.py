# -*- coding: utf-8 -*-
"""XMODEM / XMODEM-1K / YMODEM 文件传输协议（纯逻辑，Qt-free、可 loopback 单测）。

协议收发只依赖注入的两个回调，便于单测（内存双队列对接 send↔recv）：
    getc(n, timeout) -> bytes | None   # 读 n 字节；超时返回 None（已收字节须留存，下次继续）
    putc(data)       -> None           # 发送若干字节

帧格式（发送方→接收方）：
    数据块  [SOH|STX][seq][255-seq][payload...][cksum | crc_hi crc_lo]
            SOH=128 字节块 / STX=1024 字节块；seq 1..255 循环，YMODEM 头块/结束块=0
            校验：checksum = sum(payload)&0xFF（1 字节） 或 crc16（2 字节，大端）
    结束    EOT（单字节 0x04）
接收方→发送方：C(0x43) 请求 CRC 起传 / NAK(0x15) 请求 checksum 起传或重发 /
              ACK(0x06) 单块确认 / CAN(0x18) 取消。

YMODEM 在 XMODEM-1K 基础上：先发第 0 块（SOH，内容 "名字\\0大小 mtime\\0" 补零）带文件名/大小，
数据块用 1K/CRC，EOT 后再发一个全零第 0 块表示批次结束。
"""
import time

SOH = 0x01
STX = 0x02
EOT = 0x04
ACK = 0x06
NAK = 0x15
CAN = 0x18
C = 0x43          # ord('C')，接收方请求 CRC 模式
SUB = 0x1A        # Ctrl-Z，数据块填充字节

# 超时/重试（秒 / 次）——纯逻辑用 time.monotonic 计时，与 GUI 无关
START_TIMEOUT = 3.0      # 等起传字符 / 等首块
ACK_TIMEOUT = 2.0        # 等单块 ACK
BLOCK_TIMEOUT = 2.0      # 接收单块内读字节
START_RETRY = 20         # 起传阶段重试（发送等 C/NAK；接收发 C/NAK）
MAX_RETRY = 10           # 单块重发上限

# 公开模式
MODE_XMODEM = "xmodem"        # 128 字节 + 校验和
MODE_XMODEM_CRC = "xmodem-crc"  # 128 字节 + CRC
MODE_XMODEM_1K = "xmodem1k"   # 1024 字节 + CRC
MODE_YMODEM = "ymodem"        # YMODEM 批量（带文件名/大小）
MODES = (MODE_XMODEM, MODE_XMODEM_CRC, MODE_XMODEM_1K, MODE_YMODEM)


class ByteInbox:
    """线程安全字节缓冲，桥接 GUI 收流与协议 getc：GUI 线程 put()，worker 线程 read()。
    read 攒够 n 才回、超时/关闭返回 None，未取走的字节留存供下次继续；close() 唤醒阻塞的 read（用于取消）。"""

    def __init__(self):
        import threading
        self._buf = bytearray()
        self._cv = threading.Condition()
        self._closed = False

    def put(self, data):
        with self._cv:
            self._buf.extend(data)
            self._cv.notify_all()

    def close(self):
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    def read(self, n, timeout):
        deadline = time.monotonic() + timeout
        with self._cv:
            while len(self._buf) < n:
                if self._closed:
                    return None
                remain = deadline - time.monotonic()
                if remain <= 0:
                    return None
                self._cv.wait(remain)
            out = bytes(self._buf[:n])
            del self._buf[:n]
            return out


class XferError(Exception):
    """传输失败（超时 / 帧错 / 重试耗尽）。"""


class XferCancelled(XferError):
    """本地或对端取消。"""


def _crc16(data):
    """XMODEM CRC-16（多项式 0x1021，初值 0，不反转）。"""
    crc = 0
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def _check_cancel(cancel):
    if cancel and cancel():
        raise XferCancelled("cancelled")


def _mode_params(mode):
    """(块大小偏好, 是否 YMODEM, 是否强制 CRC)。"""
    if mode == MODE_YMODEM:
        return 1024, True, True
    if mode == MODE_XMODEM_1K:
        return 1024, False, True
    if mode == MODE_XMODEM_CRC:
        return 128, False, True
    return 128, False, False


# ==================== 发送 ====================
def _flush_input(getc):
    """读掉残留输入，重发前清管道避免旧字节干扰。"""
    while getc(1, 0.0):
        pass


def _wait_start(getc, cancel, force_crc):
    """等接收方起传字符：返回 True=CRC / False=checksum。force_crc 时只认 C。"""
    for _ in range(START_RETRY):
        _check_cancel(cancel)
        c = getc(1, START_TIMEOUT)
        if not c:
            continue
        if c[0] == C:
            return True
        if c[0] == NAK and not force_crc:
            return False
        if c[0] == CAN:
            raise XferCancelled("remote cancelled")
    raise XferError("no start char from receiver")


def _send_block(getc, putc, seq, payload, use_crc, cancel):
    """发一块并等 ACK；NAK/超时重发，CAN/耗尽抛错。"""
    header = STX if len(payload) == 1024 else SOH
    frame = bytes([header, seq & 0xFF, (255 - (seq & 0xFF)) & 0xFF]) + payload
    if use_crc:
        crc = _crc16(payload)
        frame += bytes([(crc >> 8) & 0xFF, crc & 0xFF])
    else:
        frame += bytes([sum(payload) & 0xFF])
    for _ in range(MAX_RETRY):
        _check_cancel(cancel)
        putc(frame)
        c = getc(1, ACK_TIMEOUT)
        if c and c[0] == ACK:
            return
        if c and c[0] == CAN:
            raise XferCancelled("remote cancelled")
        # NAK 或超时 → 重发
    raise XferError("block %d not acknowledged" % seq)


def _send_eot(getc, putc, cancel):
    """发 EOT 等 ACK（YMODEM 首个 EOT 可能被 NAK，重发即可）。"""
    for _ in range(MAX_RETRY):
        _check_cancel(cancel)
        putc(bytes([EOT]))
        c = getc(1, ACK_TIMEOUT)
        if c and c[0] == ACK:
            return
    raise XferError("EOT not acknowledged")


def _send_data(getc, putc, data, block_size, use_crc, cancel, progress, seq0=1):
    """把 data 按块发出（末尾块 <=128 时缩到 128、否则用 block_size）。返回下一个 seq。"""
    total = len(data)
    off = 0
    seq = seq0
    while off < total:
        remain = total - off
        bs = 128 if (block_size == 128 or remain <= 128) else 1024
        chunk = data[off:off + bs]
        payload = chunk + bytes([SUB]) * (bs - len(chunk))
        _send_block(getc, putc, seq, payload, use_crc, cancel)
        off += len(chunk)
        seq = (seq + 1) & 0xFF
        if progress:
            progress(off, total)
    return seq


def _ymodem_header(name, size):
    """YMODEM 第 0 块 128 字节 payload："名字\\0大小 mtime\\0" 补零到 128。"""
    base = (name or "").replace("\\", "/").split("/")[-1]
    info = base.encode("utf-8", "replace") + b"\x00" + ("%d 0" % size).encode("ascii") + b"\x00"
    if len(info) > 128:
        info = info[:128]
    return info + b"\x00" * (128 - len(info))


def send_file(getc, putc, data, mode=MODE_YMODEM, name="", cancel=None, progress=None):
    """发送 data（bytes）。mode∈MODES；YMODEM 用 name 作文件名。返回已发字节数。"""
    data = bytes(data)
    block_size, ymodem, force_crc = _mode_params(mode)
    if ymodem:
        # 头块：等 C → 发第 0 块（名字/大小）→ 等 C → 发数据 → EOT → 结束全零块
        _wait_start(getc, cancel, True)
        _send_block(getc, putc, 0, _ymodem_header(name, len(data)), True, cancel)
        _wait_start(getc, cancel, True)
        _send_data(getc, putc, data, 1024, True, cancel, progress, seq0=1)
        _send_eot(getc, putc, cancel)
        _wait_start(getc, cancel, True)          # 接收方为下一文件再发 C
        _send_block(getc, putc, 0, b"\x00" * 128, True, cancel)  # 全零块=批次结束
    else:
        use_crc = _wait_start(getc, cancel, force_crc)
        _send_data(getc, putc, data, block_size, use_crc, cancel, progress, seq0=1)
        _send_eot(getc, putc, cancel)
    return len(data)


# ==================== 接收 ====================
def _recv_open(getc, putc, use_crc, cancel):
    """反复发起传字符直到收到首个头字节；返回该字节值（SOH/STX/EOT）。"""
    start = C if use_crc else NAK
    for _ in range(START_RETRY):
        _check_cancel(cancel)
        putc(bytes([start]))
        c = getc(1, START_TIMEOUT)
        if c:
            return c[0]
    raise XferError("no response from sender")


def _recv_block(getc, header, use_crc, cancel):
    """已读到头字节 header(SOH/STX)，读完该块 → (seq, payload) 或 None(校验/长度失败)。"""
    bs = 1024 if header == STX else 128
    rest = getc(bs + 2 + (2 if use_crc else 1), BLOCK_TIMEOUT)
    if not rest or len(rest) < bs + 2 + (2 if use_crc else 1):
        return None
    seq, cseq = rest[0], rest[1]
    payload = rest[2:2 + bs]
    if (seq + cseq) & 0xFF != 0xFF:
        return None
    if use_crc:
        got = (rest[2 + bs] << 8) | rest[3 + bs]
        if got != _crc16(payload):
            return None
    else:
        if rest[2 + bs] != (sum(payload) & 0xFF):
            return None
    return seq, payload


def _parse_ymodem_header(payload):
    """解析第 0 块 → (name, size)；空名（全零块）返回 ("", 0)。"""
    nul = payload.find(b"\x00")
    name = payload[:nul].decode("utf-8", "replace") if nul > 0 else ""
    size = 0
    if nul >= 0:
        tail = payload[nul + 1:].split(b"\x00", 1)[0].strip()
        tok = tail.split()
        if tok:
            try:
                size = int(tok[0])
            except ValueError:
                size = 0
    return name, size


def recv_file(getc, putc, mode=MODE_YMODEM, cancel=None, progress=None):
    """接收 → (data: bytes, meta: dict)。meta 含 name/size（XMODEM 无则空）。"""
    block_size, ymodem, force_crc = _mode_params(mode)
    use_crc = force_crc or (mode != MODE_XMODEM)
    meta = {}
    size = None

    header = _recv_open(getc, putc, use_crc, cancel)
    expected = 0 if ymodem else 1

    if ymodem:
        # 首个块必是第 0 块（文件名/大小）
        if header not in (SOH, STX):
            raise XferError("expected YMODEM header block")
        blk = _recv_block(getc, header, use_crc, cancel)
        if not blk:
            raise XferError("bad YMODEM header block")
        seq, payload = blk
        name, size = _parse_ymodem_header(payload)
        if not name:                      # 上来就全零块=无文件
            putc(bytes([ACK]))
            return b"", {}
        meta["name"] = name
        meta["size"] = size
        putc(bytes([ACK]))
        # 头块确认后，为数据阶段再发一次 C，并读下一头字节
        header = _recv_open(getc, putc, use_crc, cancel)
        expected = 1

    data = bytearray()
    while True:
        _check_cancel(cancel)
        if header == EOT:
            putc(bytes([ACK]))
            break
        if header == CAN:
            raise XferCancelled("remote cancelled")
        if header not in (SOH, STX):
            _flush_input(getc)
            putc(bytes([NAK]))
            h = getc(1, BLOCK_TIMEOUT)
            header = h[0] if h else None
            if header is None:
                header = _recv_open(getc, putc, use_crc, cancel)
            continue
        blk = _recv_block(getc, header, use_crc, cancel)
        if not blk:
            _flush_input(getc)
            putc(bytes([NAK]))
        else:
            seq, payload = blk
            if seq == expected:
                data.extend(payload)
                expected = (expected + 1) & 0xFF
                putc(bytes([ACK]))
                if progress:
                    progress(len(data), size)
            elif seq == (expected - 1) & 0xFF:
                putc(bytes([ACK]))         # 重复块（我方 ACK 丢了）→ 再确认，不重复追加
            else:
                raise XferError("block sequence error: got %d expected %d" % (seq, expected))
        h = getc(1, BLOCK_TIMEOUT)
        header = h[0] if h else None
        if header is None:
            _flush_input(getc)
            putc(bytes([NAK]))
            h = getc(1, START_TIMEOUT)
            header = h[0] if h else None
            if header is None:
                raise XferError("timeout waiting for block")

    out = bytes(data)
    if ymodem:
        if size is not None:
            out = out[:size]              # 去掉末块填充
        # 结束阶段：为下一文件发 C，收全零块并 ACK（单文件批次收尾）
        try:
            hh = _recv_open(getc, putc, use_crc, cancel)
            if hh in (SOH, STX):
                b2 = _recv_block(getc, hh, use_crc, cancel)
                putc(bytes([ACK]))
        except XferError:
            pass                          # 对端未发结束块也不影响已收数据
    return out, meta
