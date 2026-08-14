# -*- coding: utf-8 -*-
"""TCP Client / TCP Server / UDP / UDP Multicast → libpcap / pcapng.

把 CommTool 录到的应用层收发事件封装成合成以太网 + IPv4 + TCP/UDP 帧，
以便用 Wireshark / tcpdump 打开。不是系统级网卡抓包：没有真实 L2 帧，
TCP 也无三次握手 / 重传语义，只保时间序与载荷方向。

支持范围：
- TCP Client
- TCP Server（每个客户端一条流；广播按该事件当时的对端展开，缺省则按此前已出现的客户端）
- UDP（必须指定唯一远程对端）
- UDP Multicast（remote = 组播组地址/端口）
串口 / UDP 回复模式多对端 → 拒绝导出。

导出格式：经典 ``.pcap`` 或 ``.pcapng``（由路径扩展名或 format= 选择）。
"""
from __future__ import annotations

import ipaddress
import os
import struct
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from net_io import (
    PROTO_TCP_CLIENT, PROTO_TCP_SERVER, PROTO_UDP, PROTO_UDP_MULTICAST,
)

Event = Tuple[float, str, bytes]  # (t_rel, 'rx'|'tx', payload)

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

# pcapng (little-endian section; byte-order magic value 0x1A2B3C4D)
_PCAPNG_SHB = 0x0A0D0D0A
_PCAPNG_BOM = 0x1A2B3C4D
_PCAPNG_IDB = 0x00000001
_PCAPNG_EPB = 0x00000006

# TCP Server broadcast TX sentinel (matches TcpServerConn send target).
PCAP_BROADCAST = "__all__"


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


def as_unicast_peer(value) -> Optional[Tuple[str, int]]:
    """Normalize a per-event / header peer to ``(ipv4, port)``, or None.

    Accepts ``(ip, port)``, ``[ip, port]``, or ``"ip:port"``. A 2-tuple is
    always one peer. Broadcast sentinel ``__all__``, a list of peers, and
    unparseable values return None.
    """
    if value is None or value == PCAP_BROADCAST:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        host, port_value = value[0], value[1]
    elif isinstance(value, str) and ":" in value.strip():
        host, _, port_value = value.strip().rpartition(":")
    else:
        return None
    try:
        ip = str(ipaddress.IPv4Address(str(host).strip().strip("[]")))
        port = _port(port_value)
    except (PcapExportError, TypeError, ValueError, ipaddress.AddressValueError):
        return None
    return ip, port


def _iter_unicast_peers(value):
    """Yield ``(ipv4, port)`` from a sidecar value.

    A 2-tuple/list of ``(ip, port)`` is one peer. A list of those is many
    (TCP Server broadcast recipients captured at send time).
    """
    one = as_unicast_peer(value)
    if one is not None:
        yield one
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            peer = as_unicast_peer(item)
            if peer is not None:
                yield peer


def is_broadcast_peer(value) -> bool:
    return value == PCAP_BROADCAST


def _header_peers(link: Mapping) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    raw = link.get("peers")
    if isinstance(raw, (list, tuple)):
        for item in raw:
            peer = as_unicast_peer(item)
            if peer is not None and peer not in out:
                out.append(peer)
    return out


def collect_tcp_server_peers(
    events: Optional[Sequence[Event]],
    link: Mapping,
) -> List[Tuple[str, int]]:
    """Ordered unique TCP Server clients from header + per-event sidecar."""
    seen: List[Tuple[str, int]] = []

    def add(value) -> None:
        for peer in _iter_unicast_peers(value):
            if peer not in seen:
                seen.append(peer)

    for peer in _header_peers(link):
        add(peer)
    add((link.get("remote_ip"), link.get("remote_port")))
    event_peers = getattr(events, "pcap_peers", ()) or ()
    for item in event_peers:
        add(item)
    return seen


def list_export_peers(
    events: Optional[Sequence[Event]],
    link: Optional[Mapping],
) -> List[Tuple[str, int]]:
    """Peers the user will see in a PCAP (for the export confirm dialog)."""
    try:
        meta = normalize_link(link)
    except PcapExportError:
        return []
    if meta["proto"] == PROTO_TCP_SERVER:
        return collect_tcp_server_peers(events, meta)
    if meta.get("remote_ip") and meta.get("remote_port"):
        return [(meta["remote_ip"], meta["remote_port"])]
    return []


def normalize_link(link: Optional[Mapping]) -> dict:
    """Validate / normalize a link dict for PCAP export.

    TCP Client / UDP / UDP Multicast require a single remote_ip/remote_port.
    TCP Server needs a concrete local_ip/local_port; remote is optional
    because clients come from per-event peers (and optional header ``peers``).
    local_ip / local_port default to 10.0.0.1 / 40000 when missing
    (TCP Client often only knows the remote until the socket is up),
    except TCP Server which requires local_port (the listen port).
    """
    if not isinstance(link, Mapping):
        raise PcapExportError("missing link metadata")
    proto = str(link.get("proto") or "").strip()
    if proto in (PROTO_TCP_CLIENT, PROTO_TCP_SERVER):
        transport = "tcp"
    elif proto in (PROTO_UDP, PROTO_UDP_MULTICAST):
        transport = "udp"
    else:
        raise PcapExportError(
            "PCAP export only supports TCP Client/Server and "
            "UDP / UDP Multicast (got %r)" % proto)

    local_ip = str(link.get("local_ip") or "").strip() or "10.0.0.1"
    # Bind-all is valid for listening, but not as a synthetic PCAP host.
    if local_ip in ("0.0.0.0", "::", "::0"):
        raise PcapExportError(
            "wildcard local_ip is not exportable (need a concrete host IPv4)")
    local_port = link.get("local_port")
    if proto == PROTO_TCP_SERVER:
        if local_port in (None, ""):
            raise PcapExportError("TCP Server requires local_port")
    elif local_port in (None, ""):
        local_port = 40000

    remote_ip = str(link.get("remote_ip") or "").strip()
    remote_port = link.get("remote_port")
    has_remote = bool(remote_ip) and remote_port not in (None, "")
    if proto != PROTO_TCP_SERVER and not has_remote:
        raise PcapExportError(
            "single remote peer required (remote_ip / remote_port)")

    local_ip_b = _ipv4_bytes(local_ip)
    remote_ip_b = _ipv4_bytes(remote_ip) if has_remote else None
    remote_port_n = _port(remote_port) if has_remote else None
    if proto == PROTO_UDP_MULTICAST and not 224 <= remote_ip_b[0] <= 239:
        raise PcapExportError("UDP Multicast remote_ip must be an IPv4 multicast group")

    meta = {
        "proto": proto,
        "transport": transport,
        "local_ip": local_ip,
        "local_port": _port(local_port),
        "remote_ip": remote_ip if has_remote else None,
        "remote_port": remote_port_n,
        "local_ip_b": local_ip_b,
        "remote_ip_b": remote_ip_b,
        "rx_peer_ip_b": None,
        "rx_peer_port": None,
        "peers": _header_peers(link),
    }
    # Older recordings retain one sender in the header; current recordings
    # carry the sender with each multicast RX event.
    if proto == PROTO_UDP_MULTICAST:
        peer_ip = str(link.get("rx_peer_ip") or "").strip()
        peer_port = link.get("rx_peer_port")
        if peer_ip and peer_port not in (None, ""):
            meta["rx_peer_ip_b"] = _ipv4_bytes(peer_ip)
            meta["rx_peer_port"] = _port(peer_port)
    return meta


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


def _ipv4_multicast_mac(addr: bytes) -> bytes:
    """Map an IPv4 multicast group to its Ethernet destination MAC."""
    return b"\x01\x00\x5e" + bytes((addr[1] & 0x7F, addr[2], addr[3]))


def build_frame(direction: str, payload: bytes, link: Mapping,
                tcp_state: dict, event_peer=None) -> bytes:
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
    if link.get("proto") == PROTO_TCP_SERVER and event_peer is not None:
        peer = as_unicast_peer(event_peer)
        if peer is None:
            raise PcapExportError("invalid TCP Server client endpoint")
        rem_ip = _ipv4_bytes(peer[0])
        rem_port = peer[1]
    if rem_ip is None or rem_port is None:
        raise PcapExportError(
            "single remote peer required (remote_ip / remote_port)")

    if direction == "tx":
        # Unicast: local → remote. Multicast: local → group (remote=group).
        src_mac, dst_mac = local_mac, remote_mac
        src_ip, dst_ip = loc_ip, rem_ip
        sport, dport = loc_port, rem_port
    elif link.get("proto") == PROTO_UDP_MULTICAST:
        # Multicast RX is sender → group (not group → local).
        if event_peer is not None:
            try:
                peer_ip_text, peer_port_value = event_peer
            except (TypeError, ValueError) as e:
                raise PcapExportError("invalid multicast RX peer") from e
            peer_ip = _ipv4_bytes(peer_ip_text)
            peer_port = _port(peer_port_value)
        else:
            # Old recordings only have a single sender in the header. New live
            # recordings pass the sender with each RX event instead.
            peer_ip = link.get("rx_peer_ip_b")
            peer_port = link.get("rx_peer_port")
        if peer_ip is None or peer_port is None:
            raise PcapExportError("multicast RX requires sender endpoint")
        src_mac, dst_mac = remote_mac, local_mac
        src_ip, dst_ip = peer_ip, rem_ip
        sport, dport = peer_port, rem_port
    else:
        # Unicast RX: remote → local.
        src_mac, dst_mac = remote_mac, local_mac
        src_ip, dst_ip = rem_ip, loc_ip
        sport, dport = rem_port, loc_port

    if link.get("proto") == PROTO_UDP_MULTICAST:
        # Both outbound datagrams and received group traffic target the same
        # IPv4 multicast Ethernet address, never the local host's unicast MAC.
        dst_mac = _ipv4_multicast_mac(rem_ip)

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


def _tcp_flow_state(states: dict, peer: Tuple[str, int]) -> dict:
    st = states.get(peer)
    if st is None:
        st = {"tx": 1000, "rx": 2000}
        states[peer] = st
    return st


def _event_chunks(meta: Mapping, data: bytes):
    if meta["transport"] == "tcp":
        return [data[off:off + _TCP_MAX_PAYLOAD]
                for off in range(0, len(data), _TCP_MAX_PAYLOAD)]
    return [data]


def _tcp_server_targets(event_peer, meta: Mapping,
                        known: Sequence[Tuple[str, int]]):
    """Resolve one TCP Server event to one or more client endpoints.

    Prefer a recipient list stored on the event. ``__all__`` expands only to
    clients already seen in this walk (not the whole recording).
    """
    explicit = list(_iter_unicast_peers(event_peer))
    if explicit:
        return explicit
    if is_broadcast_peer(event_peer):
        if not known:
            raise PcapExportError("TCP Server broadcast has no known clients")
        return list(known)
    if meta.get("remote_ip") and meta.get("remote_port"):
        peer = as_unicast_peer((meta["remote_ip"], meta["remote_port"]))
        if peer is not None:
            return [peer]
    raise PcapExportError("TCP Server event missing client endpoint")


def _iter_frames(
    events: Sequence[Event],
    meta: Mapping,
    *,
    wall_t0: Optional[float] = None,
) -> List[Tuple[float, bytes]]:
    """Build (timestamp_sec, ethernet_frame) list from recorder events."""
    tcp_states: dict = {}
    shared_tcp = {"tx": 1000, "rx": 2000}
    base = float(wall_t0) if wall_t0 is not None else 0.0
    frames: List[Tuple[float, bytes]] = []
    event_peers = getattr(events, "pcap_peers", ()) or ()
    known: List[Tuple[str, int]] = []
    if meta.get("proto") == PROTO_TCP_SERVER:
        # Legacy single-peer files may TX before any sidecar RX. Seed only the
        # header remote, never the full-session ``peers`` list.
        seed = as_unicast_peer((meta.get("remote_ip"), meta.get("remote_port")))
        if seed is not None:
            known.append(seed)
    for i, (t_rel, direction, payload) in enumerate(events):
        if direction not in ("rx", "tx") or not payload:
            continue
        ts = base + max(0.0, float(t_rel))
        chunks = _event_chunks(meta, bytes(payload))
        event_peer = event_peers[i] if i < len(event_peers) else None
        if meta.get("proto") == PROTO_TCP_SERVER:
            targets = _tcp_server_targets(event_peer, meta, known)
            for peer in targets:
                state = _tcp_flow_state(tcp_states, peer)
                for chunk in chunks:
                    frames.append((
                        ts, build_frame(direction, chunk, meta, state,
                                        event_peer=peer)))
            for peer in targets:
                if peer not in known:
                    known.append(peer)
        else:
            for chunk in chunks:
                frames.append((ts, build_frame(
                    direction, chunk, meta, shared_tcp,
                    event_peer=event_peer)))
    return frames


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

    frames = _iter_frames(events, meta, wall_t0=wall_t0)
    if not frames:
        raise PcapExportError("all events have empty payload")

    out = bytearray()
    out += struct.pack(
        "<IHHIIII",
        _PCAP_MAGIC, _PCAP_VER_MAJOR, _PCAP_VER_MINOR,
        0, 0, _SNAPLEN, _LINKTYPE_ETHERNET)

    for ts, frame in frames:
        ts = max(0.0, float(ts))
        sec = int(ts)
        usec = int(round((ts - sec) * 1_000_000.0))
        if usec >= 1_000_000:
            sec += 1
            usec -= 1_000_000
        out += struct.pack("<IIII", sec, usec, len(frame), len(frame))
        out += frame
    return bytes(out)


def _pcapng_pad(data: bytes) -> bytes:
    pad = (4 - (len(data) & 3)) & 3
    return data + (b"\x00" * pad)


def _pcapng_block(block_type: int, body: bytes) -> bytes:
    # total length includes type(4) + len(4) + padded body + trailing len(4)
    body = _pcapng_pad(body)
    total = 12 + len(body)
    return (struct.pack("<II", block_type, total) + body
            + struct.pack("<I", total))


def events_to_pcapng(
    events: Sequence[Event],
    link: Mapping,
    *,
    wall_t0: Optional[float] = None,
) -> bytes:
    """Convert recorder events to a minimal little-endian pcapng byte string.

    Layout: Section Header Block + Interface Description Block (Ethernet)
    + one Enhanced Packet Block per synthetic frame.
    """
    meta = normalize_link(link)
    if not events:
        raise PcapExportError("no events to export")

    frames = _iter_frames(events, meta, wall_t0=wall_t0)
    if not frames:
        raise PcapExportError("all events have empty payload")

    out = bytearray()
    # SHB: type is endian-independent; BOM 0x1A2B3C4D written LE → 4D 3C 2B 1A
    shb_body = struct.pack(
        "<IHHQ",
        _PCAPNG_BOM,
        1, 0,                 # major, minor
        0xFFFFFFFFFFFFFFFF,   # section length unknown
    )
    out += _pcapng_block(_PCAPNG_SHB, shb_body)

    # IDB: LINKTYPE_ETHERNET, snaplen
    idb_body = struct.pack("<HHI", _LINKTYPE_ETHERNET, 0, _SNAPLEN)
    out += _pcapng_block(_PCAPNG_IDB, idb_body)

    for ts, frame in frames:
        # Default if_tsresol = microseconds
        usec_total = int(round(max(0.0, float(ts)) * 1_000_000.0))
        ts_high = (usec_total >> 32) & 0xFFFFFFFF
        ts_low = usec_total & 0xFFFFFFFF
        pkt = _pcapng_pad(frame)
        epb_body = (
            struct.pack("<IIIII", 0, ts_high, ts_low, len(frame), len(frame))
            + pkt
        )
        out += _pcapng_block(_PCAPNG_EPB, epb_body)

    return bytes(out)


def _detect_format(path: str, format: Optional[str]) -> str:
    if format:
        fmt = str(format).strip().lower()
        if fmt in ("pcap", "pcapng"):
            return fmt
        raise PcapExportError("unknown PCAP format: %r" % format)
    ext = os.path.splitext(str(path or ""))[1].lower()
    return "pcapng" if ext == ".pcapng" else "pcap"


def _count_classic_packets(data: bytes) -> int:
    off = 24
    n = 0
    while off + 16 <= len(data):
        incl = struct.unpack_from("<I", data, off + 8)[0]
        off += 16 + incl
        n += 1
    return n


def _count_pcapng_packets(data: bytes) -> int:
    """Count Enhanced Packet Blocks in a little-endian pcapng blob."""
    off = 0
    n = 0
    while off + 8 <= len(data):
        btype, total = struct.unpack_from("<II", data, off)
        if total < 12 or off + total > len(data):
            break
        if btype == _PCAPNG_EPB:
            n += 1
        off += total
    return n


def export_pcap_file(path: str, events: Iterable[Event], link: Mapping,
                     *, wall_t0: Optional[float] = None,
                     format: Optional[str] = None) -> int:
    """Write a .pcap / .pcapng file; return the number of packets written.

    ``format`` defaults from the path extension (``.pcapng`` → pcapng, else classic).
    """
    if hasattr(events, "pcap_peers"):
        # StreamRecorder's event container keeps endpoint metadata parallel to
        # its public three-tuples. Do not copy it into a plain list here.
        raw = ev = events
    else:
        raw = list(events)
        ev = [(float(t), d, bytes(b)) for t, d, b in raw
              if d in ("rx", "tx") and b]
    if raw and not ev:
        raise PcapExportError("all events have empty payload")
    fmt = _detect_format(path, format)
    if fmt == "pcapng":
        data = events_to_pcapng(ev, link, wall_t0=wall_t0)
        n = _count_pcapng_packets(data)
    else:
        data = events_to_pcap(ev, link, wall_t0=wall_t0)
        n = _count_classic_packets(data)
    with open(path, "wb") as f:
        f.write(data)
    return n
