# -*- coding: utf-8 -*-
"""TCP Client / 单对端 UDP → 标准 libpcap (.pcap) 导出。

把 CommTool 录到的应用层收发事件封装成合成以太网 + IPv4 + TCP/UDP 帧，
以便用 Wireshark / tcpdump 打开。不是系统级网卡抓包：没有真实 L2 帧，
TCP 也无三次握手 / 重传语义，只保时间序与载荷方向。

支持范围（与路线图 P2-4 一致）：
- TCP Client
- UDP（必须指定唯一远程对端）
串口 / TCP Server / UDP 组播 / 回复模式多对端 → 拒绝导出。
"""
from __future__ import annotations

import ipaddress
import struct
from typing import Iterable, Mapping, Optional, Sequence, Tuple

Event = Tuple[float, str, bytes]  # (t_rel, 'rx'|'tx', payload)

PROTO_TCP_CLIENT = "TCP Client"
PROTO_UDP = "UDP"

_PCAP_MAGIC = 0xA1B2C3D4
_PCAP_VER_MAJOR = 2
_PCAP_VER_MINOR = 4
_LINKTYPE_ETHERNET = 1
_SNAPLEN = 65549  # max IPv4 packet (65,535) plus synthetic Ethernet header
_ETH_TYPE_IPV4 = 0x0800
_IP_PROTO_TCP = 6
_IP_PROTO_UDP = 17
_TCP_DATA_OFFSET = 5  # 20-byte header → offset field = 5
_TCP_MAX_PAYLOAD = 65535 - 20 - 20   # IPv4 total length minus IP/TCP headers
_UDP_MAX_PAYLOAD = 65535 - 20 - 8    # legal IPv4 UDP datagram payload


class PcapExportError(ValueError):
    """导出前提不满足或参数非法。"""


def _ipv4_bytes(text: str) -> bytes:
    try:
        addr = ipaddress.IPv4Address(str(text or "").strip())
    except (ipaddress.AddressValueError, ValueError) as e:
        raise PcapExportError("invalid IPv4 address: %r" % text) from e
    return addr.packed


def _port(value) -> int:
    try:
        p = int(value)
    except (TypeError, ValueError) as e:
        raise PcapExportError("invalid port: %r" % value) from e
    if not 1 <= p <= 65535:
        raise PcapExportError("port out of range: %r" % value)
    return p


def normalize_link(link: Optional[Mapping]) -> dict:
    """Validate / normalize a link dict for PCAP export.

    Required keys: proto, remote_ip, remote_port.
    local_ip / local_port default to 10.0.0.1 / 40000 when missing
    (TCP Client often only knows the remote until the socket is up).
    """
    if not isinstance(link, Mapping):
        raise PcapExportError("missing link metadata")
    proto = str(link.get("proto") or "").strip()
    if proto == PROTO_TCP_CLIENT:
        transport = "tcp"
    elif proto == PROTO_UDP:
        transport = "udp"
    else:
        raise PcapExportError(
            "PCAP export only supports TCP Client and single-peer UDP "
            "(got %r)" % proto)

    remote_ip = str(link.get("remote_ip") or "").strip()
    remote_port = link.get("remote_port")
    if not remote_ip or remote_port in (None, ""):
        raise PcapExportError(
            "single remote peer required (remote_ip / remote_port)")

    local_ip = str(link.get("local_ip") or "").strip() or "10.0.0.1"
    local_port = link.get("local_port")
    if local_port in (None, ""):
        local_port = 40000

    return {
        "proto": proto,
        "transport": transport,
        "local_ip": local_ip,
        "local_port": _port(local_port),
        "remote_ip": remote_ip,
        "remote_port": _port(remote_port),
        "local_ip_b": _ipv4_bytes(local_ip),
        "remote_ip_b": _ipv4_bytes(remote_ip),
    }


def can_export_link(link: Optional[Mapping]) -> bool:
    try:
        normalize_link(link)
        return True
    except PcapExportError:
        return False


def _checksum(data: bytes) -> int:
    if len(data) & 1:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _ethernet(src_mac: bytes, dst_mac: bytes, payload: bytes) -> bytes:
    # IEEE 802.3 / Ethernet II: destination MAC first, then source.
    return dst_mac + src_mac + struct.pack("!H", _ETH_TYPE_IPV4) + payload


def _ipv4(src: bytes, dst: bytes, proto: int, payload: bytes) -> bytes:
    total_len = 20 + len(payload)
    header = bytearray(struct.pack(
        "!BBHHHBBH4s4s",
        0x45,          # version=4, IHL=5
        0,             # DSCP/ECN
        total_len,
        0,             # identification
        0x4000,        # don't fragment
        64,            # TTL
        proto,
        0,             # checksum placeholder
        src,
        dst,
    ))
    struct.pack_into("!H", header, 10, _checksum(header))
    return bytes(header) + payload


def _udp(src_port: int, dst_port: int, src_ip: bytes, dst_ip: bytes,
         payload: bytes) -> bytes:
    length = 8 + len(payload)
    header = struct.pack("!HHHH", src_port, dst_port, length, 0)
    pseudo = src_ip + dst_ip + struct.pack("!BBH", 0, _IP_PROTO_UDP, length)
    csum = _checksum(pseudo + header + payload)
    if csum == 0:
        csum = 0xFFFF  # UDP zero means "no checksum"; force a real one
    header = struct.pack("!HHHH", src_port, dst_port, length, csum)
    return header + payload


def _tcp(src_port: int, dst_port: int, seq: int, ack: int,
         src_ip: bytes, dst_ip: bytes, payload: bytes) -> bytes:
    flags = 0x18  # PSH + ACK
    window = 65535
    header = struct.pack(
        "!HHIIBBHHH",
        src_port, dst_port, seq & 0xFFFFFFFF, ack & 0xFFFFFFFF,
        (_TCP_DATA_OFFSET << 4), flags, window, 0, 0)
    pseudo = (src_ip + dst_ip
              + struct.pack("!BBH", 0, _IP_PROTO_TCP, len(header) + len(payload)))
    csum = _checksum(pseudo + header + payload)
    header = struct.pack(
        "!HHIIBBHHH",
        src_port, dst_port, seq & 0xFFFFFFFF, ack & 0xFFFFFFFF,
        (_TCP_DATA_OFFSET << 4), flags, window, csum, 0)
    return header + payload


def _mac_pair() -> Tuple[bytes, bytes]:
    # Locally-administered unicast MACs — stable for Wireshark display.
    return (b"\x02\x00\x00\x00\x00\x01", b"\x02\x00\x00\x00\x00\x02")


def build_frame(direction: str, payload: bytes, link: Mapping,
                tcp_state: dict) -> bytes:
    """Build one Ethernet frame for an rx/tx application payload."""
    if direction not in ("rx", "tx"):
        raise PcapExportError("bad direction: %r" % direction)
    data = bytes(payload or b"")
    if not data:
        raise PcapExportError("empty payload")
    limit = _UDP_MAX_PAYLOAD if link["transport"] == "udp" else _TCP_MAX_PAYLOAD
    if len(data) > limit:
        raise PcapExportError(
            "%s payload too large: %d > %d" %
            (link["transport"].upper(), len(data), limit))

    local_mac, remote_mac = _mac_pair()
    loc_ip = link["local_ip_b"]
    rem_ip = link["remote_ip_b"]
    loc_port = link["local_port"]
    rem_port = link["remote_port"]

    if direction == "tx":
        src_mac, dst_mac = local_mac, remote_mac
        src_ip, dst_ip = loc_ip, rem_ip
        sport, dport = loc_port, rem_port
    else:
        src_mac, dst_mac = remote_mac, local_mac
        src_ip, dst_ip = rem_ip, loc_ip
        sport, dport = rem_port, loc_port

    if link["transport"] == "udp":
        l4 = _udp(sport, dport, src_ip, dst_ip, data)
        ip = _ipv4(src_ip, dst_ip, _IP_PROTO_UDP, l4)
    else:
        key = "tx" if direction == "tx" else "rx"
        seq = tcp_state[key]
        ack_key = "rx" if direction == "tx" else "tx"
        ack = tcp_state[ack_key]
        l4 = _tcp(sport, dport, seq, ack, src_ip, dst_ip, data)
        tcp_state[key] = (seq + len(data)) & 0xFFFFFFFF
        ip = _ipv4(src_ip, dst_ip, _IP_PROTO_TCP, l4)

    return _ethernet(src_mac, dst_mac, ip)


def events_to_pcap(
    events: Sequence[Event],
    link: Mapping,
    *,
    wall_t0: Optional[float] = None,
) -> bytes:
    """Convert recorder events to a classic libpcap byte string."""
    meta = normalize_link(link)
    if not events:
        raise PcapExportError("no events to export")

    tcp_state = {"tx": 1000, "rx": 2000}
    out = bytearray()
    out += struct.pack(
        "<IHHIIII",
        _PCAP_MAGIC, _PCAP_VER_MAJOR, _PCAP_VER_MINOR,
        0, 0, _SNAPLEN, _LINKTYPE_ETHERNET)

    base = float(wall_t0) if wall_t0 is not None else 0.0
    for t_rel, direction, payload in events:
        if direction not in ("rx", "tx") or not payload:
            continue
        ts = base + max(0.0, float(t_rel))
        sec = int(ts)
        usec = int(round((ts - sec) * 1_000_000.0))
        if usec >= 1_000_000:
            sec += 1
            usec -= 1_000_000
        data = bytes(payload)
        if meta["transport"] == "tcp":
            chunks = (data[off:off + _TCP_MAX_PAYLOAD]
                      for off in range(0, len(data), _TCP_MAX_PAYLOAD))
        else:
            chunks = (data,)
        for chunk in chunks:
            frame = build_frame(direction, chunk, meta, tcp_state)
            out += struct.pack("<IIII", sec, usec, len(frame), len(frame))
            out += frame

    # Global header only → nothing usable
    if len(out) <= 24:
        raise PcapExportError("no events to export")
    return bytes(out)


def export_pcap_file(path: str, events: Iterable[Event], link: Mapping,
                     *, wall_t0: Optional[float] = None) -> int:
    """Write a .pcap file; return the number of packets written."""
    ev = [(float(t), d, bytes(b)) for t, d, b in events
          if d in ("rx", "tx") and b]
    data = events_to_pcap(ev, link, wall_t0=wall_t0)
    with open(path, "wb") as f:
        f.write(data)
    off = 24
    n = 0
    while off + 16 <= len(data):
        incl = struct.unpack_from("<I", data, off + 8)[0]
        off += 16 + incl
        n += 1
    return n
