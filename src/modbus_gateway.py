# -*- coding: utf-8 -*-
"""Modbus TCP <-> RTU gateway (framing, not byte tunnel)."""
import logging
import time
from collections import deque, namedtuple

from modbus_slave import crc16, ModbusException
from modbus_master import MAX_TCP_MBAP_LENGTH, take_rtu_response, _u16

MAX_QUEUE = 32
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

    多客户端：每个 TCP 客户端有独立的重组缓冲，请求入队时记下来源，回包只发回
    该客户端。共用一个缓冲会让不同客户端的分片首尾相接被切成错帧，共用一条回包
    路径则会把 A 的响应广播给 B、C。
    """

    def __init__(self, unit_map=None, timeout_s=1.0, max_queue=MAX_QUEUE,
                 max_clients=MAX_CLIENTS):
        self.unit_map = dict(unit_map or {})
        self.timeout_s = max(0.05, float(timeout_s))
        self.max_queue = max(1, int(max_queue))
        self.max_clients = max(1, int(max_clients))
        self._pending = None
        self._queue = deque()
        self._tcp_bufs = {}          # client -> bytearray，按来源隔离重组
        self._rtu_buf = bytearray()
        self.stats = {"tcp_rx": 0, "rtu_tx": 0, "rtu_rx": 0, "tcp_tx": 0,
                      "timeouts": 0, "drops": 0}

    def reset(self):
        self._pending = None
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
            pass
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
                if _scanned >= 64:
                    return None               # yield: 下次 feed 继续
                continue
            total = 6 + length
            if len(buf) < total:
                return None
            frame = bytes(buf[:total])
            del buf[:total]
            return frame

    def feed_tcp(self, data, client=None):
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
        while True:
            frame = self._take_tcp_frame(buf)
            if frame is None:
                break
            self.stats["tcp_rx"] += 1
            proto = (frame[2] << 8) | frame[3]
            pdu = frame[7:]
            if proto != 0:
                self.stats["drops"] += 1
                continue
            if len(self._queue) >= self.max_queue:
                self.stats["drops"] += 1
                _LOG.debug("gateway queue full (%d), dropping request",
                           self.max_queue)
                continue
            self._queue.append({"tid": (frame[0] << 8) | frame[1],
                                "unit_tcp": frame[6], "pdu": pdu,
                                "client": client})
        self._pump(rtu_out)
        return rtu_out, tcp_out

    def _pump(self, rtu_out):
        """Start queued requests while the RTU bus is free.

        广播请求（unit=0）不等回复，循环会一口气把所有广播帧发出去。
        每轮最多发 _BROADCAST_BURST 个广播帧后让出事件循环，给 RTU 响应
        回来的机会，避免 TX 缓冲溢出。
        """
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

    def feed_rtu(self, data):
        """Accept RTU bytes; return (rtu_frames_to_send, tcp_replies).

        噪声数据时逐字节重同步（CRC/单位不匹配），每轮最多丢弃 _RESYNC_MAX
        字节后让出事件循环，避免 O(n²) 阻塞 UI 线程。
        """
        rtu_out, tcp_out = [], []
        self._rtu_buf.extend(bytes(data or b""))
        if self._pending is None:
            self._rtu_buf.clear()             # unsolicited traffic
            self._pump(rtu_out)
            return rtu_out, tcp_out
        _drops = 0
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
                if _drops >= 8:
                    return rtu_out, tcp_out    # yield: 下次 feed 继续
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
        self._pump(rtu_out)
        return rtu_out, tcp_out

    def tick(self, now=None):
        """Expire the in-flight request; return (rtu_frames, tcp_replies).

        A timed-out request answers the TCP master with exception 0x0B rather
        than leaving it to wait for its own timeout.
        """
        rtu_out, tcp_out = [], []
        if self._pending is not None:
            now = time.monotonic() if now is None else float(now)
            if now - self._pending["t0"] >= self.timeout_s:
                expired = self._pending
                self._pending = None
                self._rtu_buf.clear()
                self.stats["timeouts"] += 1
                self._reply(expired,
                            bytes([(expired["func"] | 0x80) & 0xFF,
                                   EXC_GATEWAY_NO_RESPONSE]),
                            tcp_out)
        self._pump(rtu_out)
        return rtu_out, tcp_out
