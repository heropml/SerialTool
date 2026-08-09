# -*- coding: utf-8 -*-
"""Per-connection session runtime for terminal multi-tab (v1.5).

CommTool becomes a session manager; each Session owns one conn + RX buffers +
counters. UI widgets stay on the window and bind to the active session.
"""
from __future__ import annotations

import itertools
import time
import uuid

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QTextEdit

import io_stats
from fonts import mono_font

MAX_SESSIONS = 8
_DEFAULT_TAB_TITLE = "Session"


def _new_id():
    return uuid.uuid4().hex[:10]


class Session:
    """One concurrent connection + receive view + reconnect state."""

    __slots__ = (
        "id", "title", "app",
        "conn", "_conn_proto", "_conn_cfg", "_conn_engaged",
        "rx_bytes", "tx_bytes", "rx_packets", "tx_packets",
        "rx_errors", "tx_errors",
        "_rx_rate", "_tx_rate", "_rx_peak", "_tx_peak",
        "_rx_bytes_mark", "_tx_bytes_mark", "_rate_time_mark",
        "_io_stats",
        "_reconnect_attempts", "_reconnect_timer",
        "_serial_reconnect_cfg", "_reconnect_snapshot", "_user_closing",
        "_serial_device", "_serial_missing_count",
        "_freeze_view",
        "_last_recv_time", "_last_direction", "_pending_line_break",
        "_rx_decode_buffer", "_rx_decode_buffers",
        "_rx_pending_cr", "_rx_pending_cr_source",
        "_inc_decoder", "_inc_decoders", "_txt_ends_with_nl",
        "_numview_carries",
        "_ansi_state", "_ansi_pending", "_ansi_states", "_ansi_pendings",
        "_term_pos", "_term_sgr", "_term_esc", "_term_discard_csi",
        "_term_discard_osc", "_term_osc_prev_esc", "_term_streams",
        "_ar_buf", "_ar_gap_timer",
        "txt_recv",
        "_bookmarks", "_bookmark_idx", "_recv_highlight_line",
        "conn_fields", "send_draft", "period_ms", "period_on",
        "display_opts", "log_wanted", "log_base_path", "log_seg",
        "clients", "udp_peer",
        "_tab_index",
    )

    def __init__(self, app, title=None, session_id=None):
        self.app = app
        self.id = session_id or _new_id()
        self.title = title or _DEFAULT_TAB_TITLE
        self._tab_index = -1

        self.conn = None
        self._conn_proto = None
        self._conn_cfg = None
        self._conn_engaged = False

        self.rx_bytes = 0
        self.tx_bytes = 0
        self.rx_packets = 0
        self.tx_packets = 0
        self.rx_errors = 0
        self.tx_errors = 0
        self._rx_rate = 0
        self._tx_rate = 0
        self._rx_peak = 0
        self._tx_peak = 0
        self._rx_bytes_mark = 0
        self._tx_bytes_mark = 0
        self._rate_time_mark = time.monotonic()
        self._io_stats = io_stats.IoStatsAccumulator()

        self._reconnect_attempts = 0
        self._serial_reconnect_cfg = None
        self._reconnect_snapshot = None
        self._user_closing = False
        self._serial_device = None
        self._serial_missing_count = 0
        self._reconnect_timer = QTimer(app)
        self._reconnect_timer.setSingleShot(True)
        # Closure reads self.id at fire time (restore may rewrite id).
        # Do not connect a Session bound method: Session is not a QObject.
        self._reconnect_timer.timeout.connect(
            lambda _s=self: _s.app._try_reconnect_for(_s.id))

        self._freeze_view = False
        self._reset_recv_fields()
        self._ar_buf = b""
        self._ar_gap_timer = QTimer(app)
        self._ar_gap_timer.setSingleShot(True)
        self._ar_gap_timer.timeout.connect(
            lambda _s=self: _s.app._ar_flush_for(_s.id))

        self.txt_recv = None
        self._bookmarks = []
        self._bookmark_idx = -1
        self._recv_highlight_line = -1

        self.conn_fields = {}
        self.send_draft = ""
        self.period_ms = "1000"
        self.period_on = False
        self.display_opts = {}
        self.log_wanted = False
        self.log_base_path = ""
        self.log_seg = 0
        self.clients = []
        self.udp_peer = None

    def _reset_recv_fields(self):
        self._last_recv_time = 0.0
        self._last_direction = None
        self._pending_line_break = False
        self._rx_decode_buffer = b""
        self._rx_decode_buffers = {}
        self._rx_pending_cr = False
        self._rx_pending_cr_source = None
        self._inc_decoder = None
        self._inc_decoders = {}
        self._txt_ends_with_nl = True
        self._numview_carries = {}
        self._ansi_state = None
        self._ansi_pending = ""
        self._ansi_states = {}
        self._ansi_pendings = {}
        self._term_pos = None
        self._term_sgr = None
        self._term_esc = ""
        self._term_discard_csi = False
        self._term_discard_osc = False
        self._term_osc_prev_esc = False
        self._term_streams = {}


    def ensure_recv_widget(self, font_size=10):
        """Create the per-session QTextEdit if missing (parented later into stack)."""
        if self.txt_recv is not None:
            return self.txt_recv
        te = QTextEdit()
        te.setReadOnly(True)
        te.setObjectName("RecvBox")
        te.setFont(mono_font(font_size))
        te.setLineWrapMode(QTextEdit.WidgetWidth)
        te.document().setMaximumBlockCount(10000)
        te.setProperty("session_id", self.id)
        self.txt_recv = te
        return te

    def is_open(self):
        return bool(self.conn and getattr(self.conn, "is_open", False))

    def resource_key(self):
        """Conflict key: serial port name or local bind (proto, ip, port)."""
        proto = self._conn_proto
        cfg = self._conn_cfg
        if not proto or not cfg:
            return None
        # cfg shapes mirror _conn_config_signature
        try:
            from virtual_io import PROTO_VIRTUAL
            from conn_ui import PROTO_SERIAL
        except Exception:
            PROTO_VIRTUAL = "Virtual"
            PROTO_SERIAL = "Serial"
        if proto == PROTO_SERIAL and len(cfg) > 1 and cfg[1]:
            return ("serial", str(cfg[1]).upper())
        if proto == PROTO_VIRTUAL:
            return None  # virtual is in-process; allow many
        # network: local bind conflicts on same (proto family, local_ip, local_port)
        if len(cfg) >= 1:
            # signatures vary; prefer explicit local fields when present
            local_ip = ""
            local_port = ""
            if len(cfg) >= 3:
                # common: (mode, remote_ip, remote_port) or (mode, local_ip, local_port, ...)
                pass
            return ("net", proto, tuple(cfg))
        return ("net", proto, tuple(cfg) if cfg else ())

    def tab_label(self, closed_label="-"):
        """Short label for QTabBar: conn token or placeholder.

        Shared connection UI always keeps a serial-port combo value, so a UDP
        session's conn_fields may still contain ser_port=COM1. Prefer proto:
        only use ser_port when this session is (or defaults to) serial.
        """
        import log_naming
        token = log_naming.conn_token(self._conn_proto, self._conn_cfg)
        if token:
            return token
        if self.conn_fields:
            try:
                from conn_ui import PROTO_SERIAL, PROTO_TCP_CLIENT
            except Exception:
                PROTO_SERIAL = "Serial"
                PROTO_TCP_CLIENT = "TCP Client"
            proto = self.conn_fields.get("net_proto") or ""
            port = self.conn_fields.get("ser_port") or ""
            rip = self.conn_fields.get("net_remote_ip") or ""
            rport = self.conn_fields.get("net_remote_port") or ""
            # Network session: never fall back to leftover serial combo text.
            if proto and proto != PROTO_SERIAL:
                if proto == PROTO_TCP_CLIENT and rip and rport:
                    return "%s_%s" % (rip, rport)
                return str(proto)
            if port:
                return str(port)
            if rip and rport:
                return "%s:%s" % (rip, rport)
            if proto:
                return str(proto)
        return self.title or closed_label

    def to_persist(self):
        return {
            "id": self.id,
            "title": self.title,
            "conn_fields": dict(self.conn_fields or {}),
            "send_draft": self.send_draft or "",
            "period_ms": self.period_ms or "1000",
            "period_on": bool(self.period_on),
            "display_opts": dict(self.display_opts or {}),
            "log_wanted": bool(self.log_wanted),
            "log_base_path": self.log_base_path or "",
            "log_seg": int(self.log_seg or 0),
        }

    @classmethod
    def from_persist(cls, app, data):
        data = data or {}
        s = cls(app, title=data.get("title"), session_id=data.get("id") or None)
        s.conn_fields = dict(data.get("conn_fields") or {})
        s.send_draft = data.get("send_draft") or ""
        s.period_ms = data.get("period_ms") or "1000"
        s.period_on = bool(data.get("period_on", False))
        s.display_opts = dict(data.get("display_opts") or {})
        s._freeze_view = bool(s.display_opts.get("freeze_view", False))
        s.log_wanted = bool(data.get("log_wanted", False))
        s.log_base_path = data.get("log_base_path") or ""
        try:
            s.log_seg = max(0, int(data.get("log_seg", 0) or 0))
        except (TypeError, ValueError):
            s.log_seg = 0
        return s


# Stable counter for default titles Session-2, Session-3, ...
_title_seq = itertools.count(2)


def next_default_title(base="Session"):
    n = next(_title_seq)
    return "%s-%d" % (base, n)
