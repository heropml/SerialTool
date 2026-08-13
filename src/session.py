# -*- coding: utf-8 -*-
"""Per-connection session runtime for terminal multi-tab (v1.5).

CommTool becomes a session manager; each Session owns one conn + RX buffers +
counters. UI widgets stay on the window and bind to the active session.
"""
from __future__ import annotations

import time
import uuid
from collections import deque

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QTextEdit

import io_stats
import macro_recorder
import modbus_slave
import rec_replay
import seq_context
from fonts import mono_font

MAX_SESSIONS = 8
_DEFAULT_TAB_TITLE = "Session"

_CONN_BOOL_KEYS = {
    "serial_dtr", "serial_rts", "net_use_remote",
    "vconn_loopback", "auto_reconnect",
}
_DISPLAY_BOOL_KEYS = {
    "tx_hex", "append_nl_on", "hexdump", "rx_hex",
    "terminal_on", "hexdump_on", "numview_on", "ansi_on",
    "proto_hl_on", "freeze_view", "line_split", "packet_split",
    "show_timestamp",
}


def _persist_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off", ""):
            return False
    return bool(default)

def new_session_id():
    return uuid.uuid4().hex[:10]


def format_default_title(app, index):
    """Localized default tab title: base or base-N (index >= 2)."""
    base = _DEFAULT_TAB_TITLE
    if app is not None and hasattr(app, "_t"):
        try:
            base = app._t("session_default") or base
        except Exception:
            pass
    try:
        n = int(index)
    except (TypeError, ValueError):
        n = 1
    if n <= 1:
        return base
    return "%s-%d" % (base, n)


class Session:
    """One concurrent connection + receive view + reconnect state."""

    __slots__ = (
        "id", "title", "title_index", "app",
        "conn", "_conn_proto", "_conn_cfg", "_conn_engaged",
        "rx_bytes", "tx_bytes", "rx_packets", "tx_packets",
        "rx_errors", "tx_errors",
        "_rx_rate", "_tx_rate", "_rx_peak", "_tx_peak",
        "_rx_bytes_mark", "_tx_bytes_mark", "_rate_time_mark",
        "_io_stats",
        "_reconnect_attempts", "_reconnect_timer",
        "_serial_reconnect_cfg", "_reconnect_snapshot", "_user_closing",
        "_serial_device", "_serial_missing_count",
        "_freeze_view", "_ts_anchor",
        "_last_recv_time", "_last_direction", "_pending_line_break",
        "_rx_decode_buffer", "_rx_decode_buffers",
        "_rx_pending_cr", "_rx_pending_cr_source",
        "_inc_decoder", "_inc_decoders", "_txt_ends_with_nl",
        "_numview_carries",
        "_ansi_state", "_ansi_pending", "_ansi_states", "_ansi_pendings",
        "_term_pos", "_term_sgr", "_term_esc", "_term_discard_csi",
        "_term_discard_osc", "_term_osc_prev_esc", "_term_streams",
        "_ar_buf", "_ar_gap_timer",
        "_ar_state", "_ar_sm_pending", "_ar_sm_queue", "_ar_sm_draining",
        "_ar_generation", "_ar_seq",
        "_ar_enabled",
        "_modbus", "_modbus_buffers", "_reset_timer",
        "_period_timer",
        "_ms_cycle_timer", "_ms_cycle_seq", "_ms_cycle_idx",
        # Sequence runtime (rules stay on the window; each tab can run its own).
        "_seq_on", "_seq_gen", "_seq_steps", "_seq_idx", "_seq_attempt",
        "_seq_buf", "_seq_results", "_seq_summary", "_seq_ctx",
        "_seq_runtime_step", "_seq_loops", "_seq_loop_i", "_seq_stop_on_fail",
        "_seq_rounds", "_seq_round_t0", "_seq_t0", "_seq_step_total_t0",
        "_seq_started_at", "_seq_finished_at",
        "_seq_dataset", "_seq_dataset_row", "_seq_round_snapshot_taken",
        "_seq_retry_not_before", "_seq_retry_quiet_until",
        "_seq_retry_quiet_deadline",
        "_seq_waiting_mbm", "_seq_wait_mbm_variant", "_seq_wait_mbm_until",
        "_seq_timer",
        # Script / MBM / recording / macro / DSL / scan / xfer / replay: per-session runtime.
        "_script_worker", "_script_conn", "_script_quiet_until", "_script_log",
        "_macro", "_recorder",
        "_dsl_ops", "_dsl_idx", "_dsl_gen", "_dsl_record",
        "_mbm_enabled", "_mbm_wanted", "_mbm_inflight", "_mbm_buf", "_mbm_tid",
        "_mbm_due", "_mbm_results", "_mbm_guard_until",
        "_mbm_sched", "_mbm_to",
        "_device_scan_state", "_scan_capture",
        "_xfer_worker", "_xfer_conn", "_xfer_target", "_xfer_send_bridge",
        "_xfer_log",
        "_replay_on", "_replay_drive_tx", "_replay_player",
        "_rr_capture",
        "txt_recv",
        "_bookmarks", "_bookmark_idx", "_recv_highlight_line", "_proto_fields",
        "conn_fields", "send_draft", "period_ms", "period_on",
        "_send_count", "send_target",
        "display_opts", "log_wanted", "log_base_path", "log_seg",
        "_log_file", "_log_file_path", "_log_opened_at",
        "_log_ends_with_nl", "_log_limit",
        "clients", "udp_peer",
        "_tab_index",
    )

    def __init__(self, app, title=None, session_id=None, title_index=None):
        self.app = app
        self.id = session_id or new_session_id()
        # title_index: auto-localized default (1, 2, 3...); None = custom title.
        if title_index is not None:
            self.title_index = int(title_index)
            self.title = format_default_title(app, self.title_index)
        elif title:
            self.title_index = None
            self.title = title
        else:
            self.title_index = 1
            self.title = format_default_title(app, 1)
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
        self._ts_anchor = None
        self._reset_recv_fields()
        self._ar_enabled = False
        self._ar_buf = b""
        self._ar_gap_timer = QTimer(app)
        self._ar_gap_timer.setSingleShot(True)
        self._ar_gap_timer.timeout.connect(
            lambda _s=self: _s.app._ar_flush_for(_s.id))
        sm = getattr(app, "_ar_sm", None)
        self._ar_state = sm.get("init", "") if isinstance(sm, dict) else ""
        self._ar_sm_pending = None
        self._ar_sm_queue = deque()
        self._ar_sm_draining = False
        self._ar_generation = 0
        self._ar_seq = 0
        # Slave register bank is per-session; config ``_ar_modbus`` stays window-shared.
        # First session is created before CommTool loads settings — rebuild later.
        cfg = getattr(app, "_ar_modbus", None)
        self._modbus = (
            modbus_slave.slave_bank_from_config(cfg) if cfg is not None
            else modbus_slave.slave_bank_from_config({}))
        self._modbus_buffers = {}
        self._reset_timer = QTimer(app)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(
            lambda _s=self: _s.app._pulse_reset_release_for(_s.id))

        self._period_timer = QTimer(app)
        self._period_timer.timeout.connect(
            lambda _s=self: _s.app._period_send_for(_s.id))

        # Multi-send cycle: per-session (align with period TX); survives tab switch.
        self._ms_cycle_seq = []
        self._ms_cycle_idx = 0
        self._ms_cycle_timer = QTimer(app)
        self._ms_cycle_timer.setSingleShot(True)
        self._ms_cycle_timer.timeout.connect(
            lambda _s=self: _s.app._ms_cycle_step_for(_s.id))

        # Sequence runtime: each tab can run its own run; rules stay on the window.
        self._seq_on = False
        self._seq_ctx = seq_context.RoundContext()
        self._seq_runtime_step = None
        self._seq_steps = []
        self._seq_idx = 0
        self._seq_attempt = 1
        self._seq_buf = b""
        self._seq_results = []
        self._seq_summary = None
        self._seq_gen = 0
        self._seq_started_at = ""
        self._seq_finished_at = ""
        self._seq_loops = 1
        self._seq_dataset = None
        self._seq_dataset_row = None
        self._seq_round_snapshot_taken = False
        self._seq_loop_i = 0
        self._seq_stop_on_fail = False
        self._seq_rounds = []
        self._seq_round_t0 = 0.0
        self._seq_t0 = 0.0
        self._seq_step_total_t0 = 0.0
        self._seq_retry_not_before = 0.0
        self._seq_retry_quiet_until = 0.0
        self._seq_retry_quiet_deadline = 0.0
        self._seq_waiting_mbm = False
        self._seq_wait_mbm_variant = ""
        self._seq_wait_mbm_until = 0.0
        self._seq_timer = QTimer(app)
        self._seq_timer.setSingleShot(True)
        self._seq_timer.timeout.connect(
            lambda _s=self: _s.app._seq_on_timeout_for(_s.id))

        self._script_worker = None
        self._script_conn = None
        self._script_quiet_until = 0.0
        self._script_log = []
        self._macro = macro_recorder.MacroRecorder()
        self._recorder = rec_replay.StreamRecorder()
        self._dsl_ops = None
        self._dsl_idx = 0
        self._dsl_gen = 0
        self._dsl_record = True
        self._mbm_enabled = False
        self._mbm_wanted = False
        self._mbm_inflight = None
        self._mbm_buf = b""
        self._mbm_tid = 0
        self._mbm_due = {}
        self._mbm_results = {}
        self._mbm_guard_until = 0.0
        self._mbm_sched = QTimer(app)
        self._mbm_sched.setSingleShot(True)
        self._mbm_sched.timeout.connect(
            lambda _s=self: _s.app._mbm_tick_for(_s.id))
        self._mbm_to = QTimer(app)
        self._mbm_to.setSingleShot(True)
        self._mbm_to.timeout.connect(
            lambda _s=self: _s.app._mbm_on_timeout_for(_s.id))
        self._device_scan_state = None
        self._scan_capture = None
        self._xfer_worker = None
        self._xfer_conn = None
        self._xfer_target = None
        self._xfer_send_bridge = None
        self._xfer_log = []
        self._replay_on = False
        self._replay_drive_tx = False
        self._replay_player = None
        self._rr_capture = None

        self.txt_recv = None
        self._bookmarks = []
        self._bookmark_idx = -1
        self._recv_highlight_line = -1
        self._proto_fields = deque(maxlen=3000)

        self.conn_fields = {}
        self.send_draft = ""
        self.period_ms = "1000"
        self.period_on = False
        self._send_count = 0
        self.send_target = "__all__"
        self.display_opts = {}
        self.log_wanted = False
        self.log_base_path = ""
        self.log_seg = 0
        self._log_file = None
        self._log_file_path = ""
        self._log_opened_at = None
        self._log_ends_with_nl = True
        self._log_limit = 0
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
        try:
            from virtual_io import PROTO_VIRTUAL
            from conn_ui import PROTO_SERIAL
        except Exception:
            PROTO_VIRTUAL = "Virtual"
            PROTO_SERIAL = "Serial"
        if proto == PROTO_SERIAL and len(cfg) > 1 and cfg[1]:
            return ("serial", str(cfg[1]).upper())
        if proto == PROTO_VIRTUAL:
            return None
        if len(cfg) >= 1:
            return ("net", proto, tuple(cfg))
        return ("net", proto, tuple(cfg) if cfg else ())

    def has_custom_title(self):
        """True when the user set an explicit tab name (title_index cleared)."""
        return self.title_index is None and bool(self.title)

    def connection_label(self, closed_label="-"):
        """Real port/address label for tooltips (ignores custom_title)."""
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
        if self.title_index is not None:
            return format_default_title(self.app, self.title_index)
        return closed_label

    def tab_label(self, closed_label="-"):
        """Short label for QTabBar: custom title, else conn token / default."""
        if self.has_custom_title():
            return self.title
        return self.connection_label(closed_label=closed_label)

    def set_custom_title(self, name):
        """Set or clear optional custom tab title.

        Empty name clears the custom title and restores an auto title_index.
        Duplicate custom titles are allowed (tooltip still shows the real
        connection label).
        """
        text = (name or "").strip()
        if len(text) > 40:
            text = text[:40].rstrip()
        if not text:
            indices = set()
            if self.app is not None:
                for other in getattr(self.app, "_sessions", []) or []:
                    if other is self:
                        continue
                    if other.title_index is not None:
                        indices.add(other.title_index)
            self.title_index = 1
            while self.title_index in indices:
                self.title_index += 1
            self.title = format_default_title(self.app, self.title_index)
            return self.title
        self.title_index = None
        self.title = text
        return self.title

    def to_persist(self):
        return {
            "id": self.id,
            "title": self.title,
            "title_index": self.title_index,
            "custom_title": self.title if self.title_index is None else "",
            "conn_fields": dict(self.conn_fields or {}),
            "send_draft": self.send_draft or "",
            "period_ms": self.period_ms or "1000",
            "period_on": bool(self.period_on),
            "send_count": int(self._send_count or 0) & 0xFF,
            "send_target": self.send_target if self.send_target is not None else "__all__",
            "display_opts": dict(self.display_opts or {}),
            "log_wanted": bool(self.log_wanted),
            "log_base_path": self.log_base_path or "",
            "log_seg": int(self.log_seg or 0),
            # per-session 引擎开关：随标签持久化，重启后各标签状态不丢。
            "ar_enabled": bool(getattr(self, "_ar_enabled", False)),
            "mbm_enabled": bool(getattr(self, "_mbm_enabled", False)),
            "mbm_wanted": bool(getattr(self, "_mbm_wanted", False)),
        }

    @classmethod
    def from_persist(cls, app, data):
        s = cls(app)
        s.load_persist(data)
        return s

    def load_persist(self, data):
        """Restore persisted fields onto an existing or newly-created session."""
        data = data if isinstance(data, dict) else {}
        raw_idx = data.get("title_index", None)
        title = data.get("title")
        custom = data.get("custom_title")
        explicit_custom = isinstance(custom, str) and bool(custom.strip())
        if explicit_custom:
            title = custom.strip()
            raw_idx = None
        if not isinstance(title, str):
            title = None
        if not explicit_custom and raw_idx is None and isinstance(title, str):
            # Migrate old English defaults so language switches keep working.
            if title == _DEFAULT_TAB_TITLE or title == "Session":
                raw_idx = 1
            elif title.startswith("Session-"):
                try:
                    raw_idx = int(title.split("-", 1)[1])
                except (TypeError, ValueError):
                    raw_idx = None
        try:
            parsed_idx = int(raw_idx) if raw_idx is not None else None
        except (TypeError, ValueError):
            parsed_idx = None
        if parsed_idx is not None:
            self.title_index = parsed_idx
            self.title = format_default_title(self.app, self.title_index)
        elif title:
            self.title_index = None
            self.title = title
        else:
            self.title_index = 1
            self.title = format_default_title(self.app, 1)
        raw_id = data.get("id")
        if isinstance(raw_id, (str, int)) and str(raw_id).strip():
            self.id = str(raw_id).strip()
        conn_fields = data.get("conn_fields")
        self.conn_fields = ({str(key): value for key, value in conn_fields.items()
                             if isinstance(value, (str, int, float, bool))
                             or value is None}
                            if isinstance(conn_fields, dict) else {})
        for key in _CONN_BOOL_KEYS & set(self.conn_fields):
            self.conn_fields[key] = _persist_bool(self.conn_fields[key])
        send_draft = data.get("send_draft")
        self.send_draft = send_draft if isinstance(send_draft, str) else ""
        period_ms = data.get("period_ms")
        self.period_ms = (str(period_ms) if isinstance(period_ms, (str, int, float))
                          and str(period_ms) else "1000")
        self.period_on = _persist_bool(data.get("period_on", False))
        try:
            self._send_count = int(data.get("send_count", 0) or 0) & 0xFF
        except (TypeError, ValueError):
            self._send_count = 0
        self.send_target = data.get("send_target")
        if not isinstance(self.send_target, (str, int, float, bool)):
            self.send_target = "__all__"
        display_opts = data.get("display_opts")
        self.display_opts = dict(display_opts) if isinstance(display_opts, dict) else {}
        for key in _DISPLAY_BOOL_KEYS & set(self.display_opts):
            self.display_opts[key] = _persist_bool(self.display_opts[key])
        self._freeze_view = self.display_opts.get("freeze_view", False)
        self.log_wanted = _persist_bool(data.get("log_wanted", False))
        log_base_path = data.get("log_base_path")
        self.log_base_path = log_base_path if isinstance(log_base_path, str) else ""
        try:
            self.log_seg = max(0, int(data.get("log_seg", 0) or 0))
        except (TypeError, ValueError):
            self.log_seg = 0
        # per-session 引擎开关：旧存档缺省为 False（与原行为一致）。
        self._ar_enabled = _persist_bool(data.get("ar_enabled", False))
        self._mbm_enabled = _persist_bool(data.get("mbm_enabled", False))
        self._mbm_wanted = _persist_bool(data.get("mbm_wanted", self._mbm_enabled))
