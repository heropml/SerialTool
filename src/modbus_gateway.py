# -*- coding: utf-8 -*-
"""Modbus TCP <-> RTU gateway (framing, not byte tunnel)."""
import logging
import time
from collections import deque, namedtuple

from modbus_slave import crc16, ModbusException
from modbus_master import MAX_TCP_MBAP_LENGTH, take_rtu_response, _u16

MAX_QUEUE = 32
# 超时后总线保持空闲的时长（即 RTU 主站的 turnaround delay）。
RECOVERY_S = 0.2
# 重同步每片最多丢掉这么多字节后「让片」，避免噪声线上 take_* 反复扫整缓冲拖死 UI。
# 同一次 feed 会继续扫后续片，直到本批缓冲耗尽或触达硬顶——否则噪声后紧跟的合法帧
# 会留在缓冲里，从机不再发数据时只能等到超时被清掉（静默丢合法响应）。
_RESYNC_SLICE = 8
_RESYNC_TCP_SLICE = 64
_RESYNC_MAX_PER_FEED = 512
MAX_CLIENTS = 16                 # TCP 侧同时保留缓冲的客户端上限，防止 key 无限增长
EXC_GATEWAY_NO_RESPONSE = 0x0B   # Gateway target device failed to respond

# TCP 侧回包：client 是来源客户端标识（None = 单客户端/非 Server 侧，按原样发送）
TcpReply = namedtuple("TcpReply", "client frame")

_GONE = object()   # 请求还在途、来源客户端已断开：回包直接丢弃，不能广播给别人

_LOG = logging.getLogger(__name__)


class ModbusGatewayEngine:
    """Translate Modbus-TCP (MBAP) requests to RTU and map responses back.

    Side A speaks Modbus-TCP; side B speaks Modbus RTU.
    The RTU bus is half-duplex, so only one request is in flight at a time and
    the rest wait in a bounded queue. Pure framing/proxy -- does not execute
    PDU logic.

    超时后的恢复窗口：总线先空闲 recovery_s 再发下一笔。RTU 没有事务号，
    同从机、同功能码、同数量的两笔请求，其响应逐字节相同；不隔开的话上一笔
    迟到的响应会被当成这一笔的答复，上游拿到别人的寄存器值却没任何报错。

    多客户端：每个 TCP 客户端有独立的重组缓冲，请求入队时记下来源，回包只发回
    该客户端。共用一个缓冲会让不同客户端的分片首尾相接被切成错帧，共用一条回包
    路径则会把 A 的响应广播给 B、C。
    """

    def __init__(self, unit_map=None, timeout_s=1.0, max_queue=MAX_QUEUE,
                 max_clients=MAX_CLIENTS, recovery_s=RECOVERY_S):
        self.unit_map = dict(unit_map or {})
        self.timeout_s = max(0.05, float(timeout_s))
        self.max_queue = max(1, int(max_queue))
        self.max_clients = max(1, int(max_clients))
        self.recovery_s = max(0.0, float(recovery_s))
        self._recover_until = 0.0
        self._pending = None
        self._queue = deque()
        self._tcp_bufs = {}          # client -> bytearray，按来源隔离重组
        self._rtu_buf = bytearray()
        self.stats = {"tcp_rx": 0, "rtu_tx": 0, "rtu_rx": 0, "tcp_tx": 0,
                      "timeouts": 0, "drops": 0}

    def reset(self):
        self._pending = None
        self._recover_until = 0.0
        self._queue.clear()
        self._tcp_bufs.clear()
        self._rtu_buf.clear()

    def map_unit(self, unit):
        unit = int(unit) & 0xFF
        return int(self.unit_map.get(unit, unit)) & 0xFF

    @property
    def clients(self):
        """当前保留了重组缓冲的客户端标识。"""
        return list(self._tcp_bufs)

    def forget_client(self, client):
        """客户端断开：丢掉它的重组缓冲和排队请求。

        已经发到 RTU 总线上的那条请求不能撤回，但回包不再有去处，标记后丢弃，
        避免落到广播路径上发给其他客户端。
        """
        self._tcp_bufs.pop(client, None)
        kept = [r for r in self._queue if r["client"] != client]
        dropped = len(self._queue) - len(kept)
        if dropped:
            self._queue.clear()
            self._queue.extend(kept)
            self.stats["drops"] += dropped
        if self._pending is not None and self._pending["client"] == client:
            self._pending["client"] = _GONE

    @staticmethod
    def _request_qty(func, pdu):
        """Best-effort qty for take_rtu_response length prediction."""
        try:
            if func in (0x01, 0x02, 0x03, 0x04, 0x17) and len(pdu) >= 5:
                return _u16(pdu, 3)
        except Exception:
            _LOG.debug("_request_qty failed", exc_info=True)
        return 1

    @staticmethod
    def _mbap(tid, unit, pdu):
        length = 1 + len(pdu)
        return bytes([(tid >> 8) & 0xFF, tid & 0xFF, 0x00, 0x00,
                      (length >> 8) & 0xFF, length & 0xFF, unit & 0xFF]) + bytes(pdu)

    def _reply(self, pending, pdu, tcp_out):
        """把回包投递给发起请求的客户端；来源已断开则丢弃。"""
        if pending["client"] is _GONE:
            self.stats["drops"] += 1
            return
        tcp_out.append(TcpReply(pending["client"],
                                self._mbap(pending["tid"], pending["unit_tcp"], pdu)))
        self.stats["tcp_tx"] += 1

    # ---- side A: Modbus TCP ------------------------------------------------

    def _take_tcp_frame(self, buf):
        """Pop one complete MBAP frame off one client's buffer, else None.

        垃圾数据时逐字节重同步，但每轮最多扫描 64 字节头部以防 O(n²) 阻塞
        Qt 事件循环；未消费的数据留给下次 feed_tcp 继续处理。
        """
        _scanned = 0
        while True:
            if len(buf) < 6:
                return None
            length = (buf[4] << 8) | buf[5]
            if length < 2 or length > MAX_TCP_MBAP_LENGTH:
                del buf[0]                    # not a plausible header, resync
                self.stats["drops"] += 1
                _scanned += 1
                if _scanned >= _RESYNC_TCP_SLICE:
                    return None               # 一片扫完：feed_tcp 决定是否继续
                continue
            total = 6 + length
            if len(buf) < total:
                return None
            frame = bytes(buf[:total])
            del buf[:total]
            return frame

    def feed_tcp(self, data, client=None, now=None):
        """Accept TCP bytes from one client; return (rtu_frames, tcp_replies).

        client 是来源标识（TCP Server 侧的 "ip:port"）。不同客户端各自重组，
        互不影响；回包按此标识定向送回。
        """
        buf = self._tcp_bufs.get(client)
        if buf is None:
            if len(self._tcp_bufs) >= self.max_clients:
                self.stats["drops"] += 1
                return [], []
            buf = self._tcp_bufs[client] = bytearray()
        buf.extend(bytes(data or b""))
        rtu_out, tcp_out = [], []
        drops_at_start = self.stats["drops"]
        while True:
            drops_before = self.stats["drops"]
            frame = self._take_tcp_frame(buf)
            if frame is None:
                # 片上限让出 vs 字节不够：前者且缓冲里还有头，同一次 feed 继续扫，
                # 否则噪声+合法帧同批到达时合法帧会卡到下一次收包。
                if (len(buf) >= 6 and self.stats["drops"] > drops_before
                        and self.stats["drops"] - drops_at_start < _RESYNC_MAX_PER_FEED):
                    continue
                break
            self.stats["tcp_rx"] += 1
            proto = (frame[2] << 8) | frame[3]
            pdu = frame[7:]
            if proto != 0:
                self.stats["drops"] += 1
                _LOG.debug("non-Modbus protocol ID %d in TCP frame, dropped", proto)
                continue
            if len(self._queue) >= self.max_queue:
                self.stats["drops"] += 1
                _LOG.debug("gateway queue full (%d), dropping request",
                           self.max_queue)
                continue
            self._queue.append({"tid": (frame[0] << 8) | frame[1],
                                "unit_tcp": frame[6], "pdu": pdu,
                                "client": client})
        self._pump(rtu_out, now)
        return rtu_out, tcp_out

    def _pump(self, rtu_out, now=None):
        """Start queued requests while the RTU bus is free.

        超时后的恢复窗口内不发新请求：让上一笔迟到的响应落在「无
        pending」的时段里被当作无主流量丢掉，而不是冒充下一笔的答复。

        广播请求（unit=0）不等回复，循环会一口气把所有广播帧发出去。
        每轮最多发 _BROADCAST_BURST 个广播帧后让出事件循环，给 RTU 响应
        回来的机会，避免 TX 缓冲溢出。
        """
        if self._recover_until:
            if (time.monotonic() if now is None else float(now)) < self._recover_until:
                return
            self._recover_until = 0.0
        _bcasts = 0
        while self._pending is None and self._queue:
            req = self._queue.popleft()
            unit_rtu = self.map_unit(req["unit_tcp"])
            body = bytes([unit_rtu]) + req["pdu"]
            rtu_out.append(body + crc16(body))
            self.stats["rtu_tx"] += 1
            self._rtu_buf.clear()
            if unit_rtu == 0:
                _bcasts += 1
                if _bcasts >= 4:
                    return      # yield: 避免一次性突发太多广播帧
                continue      # broadcast: no reply is coming, keep the bus free
            func = req["pdu"][0]
            self._pending = {
                "tid": req["tid"],
                "unit_tcp": req["unit_tcp"],
                "unit_rtu": unit_rtu,
                "client": req["client"],
                "t0": time.monotonic(),
                "func": func,
                "qty": self._request_qty(func, req["pdu"]),
            }

    # ---- side B: Modbus RTU ------------------------------------------------

    def feed_rtu(self, data, now=None):
        """Accept RTU bytes; return (rtu_frames_to_send, tcp_replies).

        噪声数据时逐字节重同步（CRC/单位不匹配），每轮最多丢弃 _RESYNC_MAX
        字节后让出事件循环，避免 O(n²) 阻塞 UI 线程。
        """
        rtu_out, tcp_out = [], []
        self._rtu_buf.extend(bytes(data or b""))
        if self._pending is None:
            # 无主流量。超时后的恢复窗口等的就是这个：上一笔的迟到响应
            # 落到这里被丢掉，不会去冒充下一笔的答复。
            self._rtu_buf.clear()
            self._pump(rtu_out, now)
            return rtu_out, tcp_out
        _drops = 0
        _drops_total = 0
        while self._pending is not None and self._rtu_buf:
            pending = self._pending
            try:
                taken = take_rtu_response(bytes(self._rtu_buf), pending["unit_rtu"],
                                          pending["func"], pending.get("qty", 1))
            except ModbusException as exc:
                # Slave exception reply is a fixed 5-byte frame, already
                # CRC-checked by take_rtu_response. Forward it verbatim.
                del self._rtu_buf[:5]
                self.stats["rtu_rx"] += 1
                self._reply(pending,
                            bytes([(pending["func"] | 0x80) & 0xFF, exc.code & 0xFF]),
                            tcp_out)
                self._pending = None
                _drops = 0
                continue
            except Exception:
                del self._rtu_buf[0]          # CRC / unit mismatch: resync
                self.stats["drops"] += 1
                _drops += 1
                if _drops >= _RESYNC_SLICE:
                    # 一片让出：重置计数后继续扫本批剩余，避免合法帧卡到超时。
                    # 硬顶防极端噪声单次 feed 拖死事件循环。
                    if _drops_total + _drops >= _RESYNC_MAX_PER_FEED:
                        self._pump(rtu_out, now)
                        return rtu_out, tcp_out
                    _drops_total += _drops
                    _drops = 0
                continue
            if taken is None:
                break                         # need more bytes
            _result, consumed = taken
            frame = bytes(self._rtu_buf[:consumed])
            del self._rtu_buf[:consumed]
            self.stats["rtu_rx"] += 1
            self._reply(pending, frame[1:-2], tcp_out)
            self._pending = None
            _drops = 0
        self._pump(rtu_out, now)
        return rtu_out, tcp_out

    def tick(self, now=None):
        """Expire the in-flight request; return (rtu_frames, tcp_replies).

        A timed-out request answers the TCP master with exception 0x0B rather
        than leaving it to wait for its own timeout.
        """
        rtu_out, tcp_out = [], []
        now = time.monotonic() if now is None else float(now)
        if self._pending is not None:
            if now - self._pending["t0"] >= self.timeout_s:
                expired = self._pending
                self._pending = None
                self._rtu_buf.clear()
                self.stats["timeouts"] += 1
                # 超时不等于从机不会再开口。它的响应与下一笔同形状请求的
                # 响应逐字节相同，紧接着发下一笔的话，迟到的那帧会被当成它的
                # 答复——上游拿到别人的寄存器值，却没有任何报错。
                self._recover_until = now + self.recovery_s
                self._reply(expired,
                            bytes([(expired["func"] | 0x80) & 0xFF,
                                   EXC_GATEWAY_NO_RESPONSE]),
                            tcp_out)
        self._pump(rtu_out, now)
        return rtu_out, tcp_out
