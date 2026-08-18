# -*- coding: utf-8 -*-
"""Stateful protocol-frame assembly for the analysis path (Qt-free).

Wraps binproto.scan_length_frames. Auto-reply keeps using iter_length_frames
on its own buffers; this module is the session-scoped analysis framer.

Default: one received chunk = one analysis unit (compat). Protocol mode
emits zero or more complete frames; UDP stays datagram-as-frame unless
udp_stream is set.
"""
from __future__ import annotations

from protocol import binproto

PROTO_TCP_SERVER = "TCP Server"
PROTO_UDP = "UDP"
PROTO_UDP_MULTICAST = "UDP Multicast"
_UDP_PROTOS = (PROTO_UDP, PROTO_UDP_MULTICAST)

LENGTH_BUF_MAX = 8192
LENGTH_BUF_KEEP = 512


def should_assemble(cfg, proto):
    """True when analysis should run header+length framing."""
    cfg = cfg or {}
    if not cfg.get("on") or not cfg.get("_header"):
        return False
    if proto in _UDP_PROTOS and not cfg.get("udp_stream"):
        return False
    return True


def source_key(proto, source):
    """TCP Server: one assembler per client; others share one session buffer."""
    if proto == PROTO_TCP_SERVER:
        return source
    return None


def _cfg_fingerprint(cfg):
    cfg = cfg or {}
    return (
        bytes(cfg.get("_header") or b""),
        int(cfg.get("len_off", 0) or 0),
        int(cfg.get("len_width", 2) or 2),
        int(cfg.get("len_extra", 0) or 0),
        bool(cfg.get("len_be", False)),
        int(cfg.get("max_frame", 4096) or 4096),
    )


class FrameStreamAssembler:
    """Stateful wrapper: feed chunks, emit complete frames + last stats."""

    def __init__(self, header=b"", len_off=0, len_width=2, len_extra=0,
                 len_be=False, max_frame=4096):
        self.header = bytes(header or b"")
        self.len_off = int(len_off or 0)
        self.len_width = int(len_width or 2)
        self.len_extra = int(len_extra or 0)
        self.len_be = bool(len_be)
        self.max_frame = int(max_frame or 4096)
        self._buf = b""
        self.last_stats = {
            "header_skip": 0, "bad_length": 0, "oversize": 0,
            "waiting": 0, "last_reason": "", "last_sample": "",
        }

    @classmethod
    def from_cfg(cls, cfg):
        cfg = cfg or {}
        return cls(
            header=cfg.get("_header") or b"",
            len_off=cfg.get("len_off", 0),
            len_width=cfg.get("len_width", 2),
            len_extra=cfg.get("len_extra", 0),
            len_be=cfg.get("len_be", False),
            max_frame=cfg.get("max_frame", 4096),
        )

    @property
    def fingerprint(self):
        return (
            self.header, self.len_off, self.len_width,
            self.len_extra, self.len_be, self.max_frame,
        )

    def reset(self):
        self._buf = b""
        self.last_stats["waiting"] = 0

    def feed(self, data):
        """Append a chunk; return complete frames (possibly empty)."""
        self._buf += bytes(data or b"")
        frames, remaining, stats = binproto.scan_length_frames(
            self._buf, self.header, self.len_off, self.len_width,
            self.len_extra, self.len_be, self.max_frame)
        if len(remaining) > LENGTH_BUF_MAX:
            dropped = len(remaining) - LENGTH_BUF_KEEP
            remaining = remaining[-LENGTH_BUF_KEEP:]
            stats = dict(stats)
            stats["header_skip"] = int(stats.get("header_skip", 0) or 0) + dropped
            stats["waiting"] = len(remaining)
            stats["last_reason"] = "header_skip"
        self._buf = remaining
        self.last_stats = stats
        return frames


class FrameAssemblerMap:
    """Per-source assemblers (TCP Server clients vs one serial/TCP Client buf)."""

    def __init__(self):
        self._by_source = {}

    def reset(self):
        self._by_source.clear()

    def discard(self, source):
        self._by_source.pop(source, None)

    def retain_sources(self, active_sources):
        """Keep session-level (None) buffer and any source still in active_sources."""
        active = set(active_sources)
        for key in list(self._by_source):
            if key is None:
                continue
            if key not in active:
                self._by_source.pop(key, None)

    def feed(self, data, source, cfg):
        fp = _cfg_fingerprint(cfg)
        asm = self._by_source.get(source)
        if asm is None or asm.fingerprint != fp:
            asm = FrameStreamAssembler.from_cfg(cfg)
            self._by_source[source] = asm
        frames = asm.feed(data)
        return frames, asm.last_stats


def analysis_rx_units(cfg, proto, data, source, assemblers):
    """Map one RX chunk to analysis units.

    Returns (units, stats). stats is None in chunk/compat mode.
    """
    data = bytes(data or b"")
    if not should_assemble(cfg, proto):
        return [data], None
    frames, stats = assemblers.feed(data, source_key(proto, source), cfg)
    return frames, stats
