# -*- coding: utf-8 -*-
"""Session manager mixin for CommTool - multi-tab concurrent sessions (v1.5)."""
from __future__ import annotations

import json
import logging

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QTabBar, QHBoxLayout, QPushButton, QWidget, QLabel, QTextEdit, QDialog,
)

from sessions.session import Session, MAX_SESSIONS, format_default_title, new_session_id
from ui.theme import chrome_for
from ui.ui_icons import close_icon, plus_icon, status_dot_icon
from ui.ui_tips import set_tooltip

_log = logging.getLogger("commtool.session")

_BACKGROUND_DISPLAY_DEFAULTS = {
    "tx_hex": False,
    "append_nl_on": False,
    "append_nl": 0,
    "checksum": 0,
    "terminal_on": False,
    "hexdump": False,
    "hexdump_on": False,
    "hexdump_width": "16",
    "numview_on": False,
    "numview_spec": ("u16", "le"),
    "rx_hex": False,
    "line_split": False,
    "line_nl": 0,
    "packet_split": False,
    "packet_timeout": "0",
    "show_timestamp": False,
    "ts_format": "absolute",
    "ansi_on": False,
    "proto_hl_on": False,
    "freeze_view": False,
    "encoding": "auto",
}

# Attributes forwarded between CommTool and the current session context.
_SESSION_PROXY_ATTRS = (
    "conn", "_conn_proto", "_conn_cfg", "_conn_engaged",
    "rx_bytes", "tx_bytes", "rx_packets", "tx_packets",
    "rx_errors", "tx_errors",
    "_rx_rate", "_tx_rate", "_rx_peak", "_tx_peak",
    "_rx_bytes_mark", "_tx_bytes_mark", "_rate_time_mark",
    "_io_stats",
    "_reconnect_attempts", "_serial_reconnect_cfg",
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
    "_ar_gap_timer",
    "_ar_state", "_ar_sm_pending", "_ar_sm_queue", "_ar_sm_draining",
    "_ar_generation", "_ar_seq",
    "_modbus", "_modbus_buffers", "_ar_stream_buffers", "_reset_timer",
    "_bookmarks", "_bookmark_idx", "_recv_highlight_line", "_proto_fields",
    "_log_file", "_log_file_path", "_log_opened_at",
    "_log_ends_with_nl", "_log_limit",
    "_send_count",
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
    "_script_worker", "_script_conn", "_script_quiet_until",
    "_macro", "_recorder",
    "_dsl_ops", "_dsl_idx", "_dsl_gen", "_dsl_record",
    "_mbm_enabled", "_mbm_inflight", "_mbm_buf", "_mbm_tid",
    "_mbm_due", "_mbm_results", "_mbm_guard_until",
    "_mbm_sched", "_mbm_to",
    "_device_scan_state",
    "_ar_enabled",
    "_xfer_worker", "_xfer_conn", "_xfer_target", "_xfer_send_bridge",
    "_replay_on", "_replay_drive_tx",
)


def _assert_session_proxy_attrs():
    """Fail fast if a window proxy name is not a Session slot (manual sync drift)."""
    slots = set(Session.__slots__)
    missing = [name for name in _SESSION_PROXY_ATTRS if name not in slots]
    if missing:
        raise AssertionError(
            "CommTool session proxies missing from Session.__slots__: %s"
            % ", ".join(missing))


def _install_session_proxies(cls):
    """Install property proxies on CommTool for session-owned attributes."""
    for name in _SESSION_PROXY_ATTRS:
        if hasattr(cls, name) and isinstance(getattr(cls, name), property):
            continue

        def _make(attr):
            def getter(self, _a=attr):
                s = self._session_ctx()
                return getattr(s, _a) if s is not None else None

            def setter(self, value, _a=attr):
                s = self._session_ctx()
                if s is not None:
                    setattr(s, _a, value)
                else:
                    _log.debug("session proxy dropped write (no session context)")

            return property(getter, setter)

        setattr(cls, name, _make(name))

    # Compatibility aliases used by the pre-session log rotation path/tests.
    # Keep one source of truth instead of leaving stale window attributes.
    for legacy_name, session_name in (
            ("_log_base_path", "log_base_path"),
            ("_log_seg", "log_seg")):
        if (hasattr(cls, legacy_name)
                and isinstance(getattr(cls, legacy_name), property)):
            continue

        def _make_alias(attr):
            def getter(self, _a=attr):
                s = self._session_ctx()
                return getattr(s, _a) if s is not None else None

            def setter(self, value, _a=attr):
                s = self._session_ctx()
                if s is not None:
                    setattr(s, _a, value)
                else:
                    _log.debug("session proxy dropped write (no session context)")

            return property(getter, setter)

        setattr(cls, legacy_name, _make_alias(session_name))

    # txt_recv: prefer context session widget
    if not (hasattr(cls, "txt_recv") and isinstance(getattr(cls, "txt_recv"), property)):
        def _txt_get(self):
            s = self._session_ctx()
            if s is not None and s.txt_recv is not None:
                return s.txt_recv
            return object.__getattribute__(self, "_txt_recv_fallback") \
                if hasattr(self, "_txt_recv_fallback") else None

        def _txt_set(self, value):
            s = self._session_ctx()
            if s is not None:
                s.txt_recv = value
            self._txt_recv_fallback = value

        cls.txt_recv = property(_txt_get, _txt_set)

    # Per-session AR assemble buffer (rules stay global)
    if not (hasattr(cls, "_ar_buf") and isinstance(getattr(cls, "_ar_buf"), property)):
        def _ar_get(self):
            s = self._session_ctx()
            return s._ar_buf if s is not None else b""

        def _ar_set(self, value):
            s = self._session_ctx()
            if s is not None:
                s._ar_buf = value

        cls._ar_buf = property(_ar_get, _ar_set)

    # Window-facing reconnect timer forwards to the context session's timer.
    if not (hasattr(cls, "_reconnect_timer") and isinstance(getattr(cls, "_reconnect_timer"), property)):
        def _rt_get(self):
            # Tests may install a double via assignment; honor that override first.
            ov = self.__dict__.get("_reconnect_timer_override")
            if ov is not None:
                return ov
            _ctx = getattr(self, "_session_ctx", None)
            sess = _ctx() if callable(_ctx) else None
            if sess is not None and getattr(sess, "_reconnect_timer", None) is not None:
                return sess._reconnect_timer
            return getattr(self, "_reconnect_timer_fallback", None)

        def _rt_set(self, value):
            # Tests/embedders may temporarily install a timer double.  Assigning
            # the real context/fallback timer back means "restore dynamic
            # routing", not "pin this QObject forever": a session reset can
            # delete that timer and otherwise leave a dangling PyQt wrapper.
            _ctx = getattr(self, "_session_ctx", None)
            sess = _ctx() if callable(_ctx) else None
            native = (getattr(sess, "_reconnect_timer", None)
                      if sess is not None else None)
            fallback = getattr(self, "_reconnect_timer_fallback", None)
            if value is None or value is native or value is fallback:
                self.__dict__.pop("_reconnect_timer_override", None)
            else:
                self.__dict__["_reconnect_timer_override"] = value

        cls._reconnect_timer = property(_rt_get, _rt_set)

    # Window-facing period timer forwards to the context session's timer.
    if not (hasattr(cls, "send_timer") and isinstance(getattr(cls, "send_timer"), property)):
        def _st_get(self):
            ov = self.__dict__.get("_send_timer_override")
            if ov is not None:
                return ov
            _ctx = getattr(self, "_session_ctx", None)
            sess = _ctx() if callable(_ctx) else None
            if sess is not None and getattr(sess, "_period_timer", None) is not None:
                return sess._period_timer
            return getattr(self, "_send_timer_fallback", None)

        def _st_set(self, value):
            _ctx = getattr(self, "_session_ctx", None)
            sess = _ctx() if callable(_ctx) else None
            native = (getattr(sess, "_period_timer", None)
                      if sess is not None else None)
            fallback = getattr(self, "_send_timer_fallback", None)
            if value is None or value is native or value is fallback:
                self.__dict__.pop("_send_timer_override", None)
            else:
                self.__dict__["_send_timer_override"] = value

        cls.send_timer = property(_st_get, _st_set)

    # Multi-send cycle timer / seq / idx → context (or active) session.
    if not (hasattr(cls, "_ms_cycle_timer")
            and isinstance(getattr(cls, "_ms_cycle_timer"), property)):
        def _ms_timer_get(self):
            ov = self.__dict__.get("_ms_cycle_timer_override")
            if ov is not None:
                return ov
            _ctx = getattr(self, "_session_ctx", None)
            sess = _ctx() if callable(_ctx) else None
            if sess is None:
                _active = getattr(self, "active_session", None)
                sess = _active() if callable(_active) else None
            if sess is not None and getattr(sess, "_ms_cycle_timer", None) is not None:
                return sess._ms_cycle_timer
            return getattr(self, "_ms_cycle_timer_fallback", None)

        def _ms_timer_set(self, value):
            _ctx = getattr(self, "_session_ctx", None)
            sess = _ctx() if callable(_ctx) else None
            if sess is None:
                _active = getattr(self, "active_session", None)
                sess = _active() if callable(_active) else None
            native = (getattr(sess, "_ms_cycle_timer", None)
                      if sess is not None else None)
            fallback = getattr(self, "_ms_cycle_timer_fallback", None)
            if value is None or value is native or value is fallback:
                self.__dict__.pop("_ms_cycle_timer_override", None)
            else:
                self.__dict__["_ms_cycle_timer_override"] = value

        cls._ms_cycle_timer = property(_ms_timer_get, _ms_timer_set)

    for _ms_attr in ("_ms_cycle_seq", "_ms_cycle_idx"):
        if hasattr(cls, _ms_attr) and isinstance(getattr(cls, _ms_attr), property):
            continue

        def _make_ms(attr):
            def getter(self, _a=attr):
                _ctx = getattr(self, "_session_ctx", None)
                sess = _ctx() if callable(_ctx) else None
                if sess is None:
                    _active = getattr(self, "active_session", None)
                    sess = _active() if callable(_active) else None
                if sess is not None:
                    return getattr(sess, _a)
                return [] if _a == "_ms_cycle_seq" else 0

            def setter(self, value, _a=attr):
                _ctx = getattr(self, "_session_ctx", None)
                sess = _ctx() if callable(_ctx) else None
                if sess is None:
                    _active = getattr(self, "active_session", None)
                    sess = _active() if callable(_active) else None
                if sess is not None:
                    setattr(sess, _a, value)

            return property(getter, setter)

        setattr(cls, _ms_attr, _make_ms(_ms_attr))

    _assert_session_proxy_attrs()


class SessionHostMixin:
    """Mixin: sessions tab bar, active binding, conflict checks."""

    MAX_SESSIONS = MAX_SESSIONS

    def _init_session_host(self):
        self._sessions = []
        self._active_session_id = None
        self._rx_context = None
        self._display_context = None
        self._switching_session = False
        self._session_tab_bar = None
        self._btn_new_session = None
        self.recv_stack = None
        # First session before any UI
        s = Session(self, title_index=1)
        self._sessions.append(s)
        self._active_session_id = s.id

    def sessions(self):
        return list(self._sessions)

    def active_session(self):
        sid = self._active_session_id
        for s in self._sessions:
            if s.id == sid:
                return s
        return self._sessions[0] if self._sessions else None

    def _session_ctx(self):
        if self._rx_context is not None:
            return self._rx_context
        return self.active_session()

    @staticmethod
    def _background_display_opts(session):
        opts = dict(_BACKGROUND_DISPLAY_DEFAULTS)
        if session is not None and isinstance(session.display_opts, dict):
            opts.update(session.display_opts)
        opts["background"] = True
        return opts

    def find_session(self, session_id):
        for s in self._sessions:
            if s.id == session_id:
                return s
        return None

    def find_session_by_conn(self, conn):
        if conn is None:
            return None
        for s in self._sessions:
            if s.conn is conn:
                return s
        return None

    def _with_session(self, session):
        """Context-manager style: temporarily set RX/context session."""
        class _Ctx:
            def __init__(self, host, sess):
                self.host = host
                self.sess = sess
                self.prev = None

            def __enter__(self):
                self.prev = self.host._rx_context
                self.host._rx_context = self.sess
                return self.sess

            def __exit__(self, *exc):
                self.host._rx_context = self.prev

        return _Ctx(self, session)

    # ---- Tab UI ----
    def _build_session_tab_bar(self):
        """Build tab bar + [+] above the terminal splitter; call from init_ui."""
        wrap = QWidget()
        wrap.setObjectName("SessionTabBar")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(6)

        lbl = QLabel(self._t("session_list"))
        lbl.setObjectName("SessionStripLabel")
        lbl.setProperty("tr_text", "session_list")
        lbl.setProperty("tr_tooltip", "session_list_tip")
        set_tooltip(lbl, self._t("session_list_tip"))
        row.addWidget(lbl, 0)
        self._session_strip_label = lbl

        bar = QTabBar()
        bar.setObjectName("SessionTabs")
        bar.setExpanding(False)
        bar.setDocumentMode(True)
        bar.setUsesScrollButtons(True)
        bar.setElideMode(Qt.ElideRight)
        bar.setTabsClosable(False)
        bar.setMovable(False)
        bar.setDrawBase(False)
        bar.setFixedHeight(30)
        bar.setIconSize(QSize(12, 12))
        bar.currentChanged.connect(self._on_session_tab_changed)
        bar.tabCloseRequested.connect(self._on_session_tab_close)
        bar.tabBarDoubleClicked.connect(self._on_session_tab_double_clicked)
        self._session_tab_bar = bar
        row.addWidget(bar, 1)

        btn = QPushButton()
        btn.setObjectName("SessionAddBtn")
        btn.setFixedSize(28, 28)
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setProperty("tr_tooltip", "session_new")
        set_tooltip(btn, self._t("session_new"))
        btn.clicked.connect(self._on_new_session_clicked)
        self._btn_new_session = btn
        row.addWidget(btn, 0)

        self._rebuild_session_tabs(select_id=self._active_session_id)
        return wrap

    def _rebuild_session_tabs(self, select_id=None):
        bar = self._session_tab_bar
        if bar is None:
            return
        bar.blockSignals(True)
        while bar.count():
            bar.removeTab(0)
        for i, s in enumerate(self._sessions):
            s._tab_index = i
            tip = s.tab_label()
            idx = bar.addTab(tip)
            bar.setTabData(idx, s.id)
            bar.setTabToolTip(idx, tip)
        # Native close buttons can remain painted after setTabButton replacement
        # on Windows. Keep the native feature off and install only our own buttons.
        bar.setTabsClosable(False)
        if len(self._sessions) > 1:
            for i in range(bar.count()):
                sid = bar.tabData(i)
                native_close = bar.tabButton(i, QTabBar.RightSide)
                if native_close is not None:
                    native_close.hide()
                    native_close.deleteLater()
                close_btn = QPushButton(bar)
                close_btn.setObjectName("SessionCloseBtn")
                close_btn.setFixedSize(18, 18)
                close_btn.setIconSize(QSize(12, 12))
                close_btn.setCursor(Qt.PointingHandCursor)
                close_btn.setFocusPolicy(Qt.NoFocus)
                close_btn.setFlat(True)
                set_tooltip(close_btn, self._t("session_close"))
                close_btn.clicked.connect(
                    lambda _checked=False, _sid=sid: self.close_session(_sid))
                bar.setTabButton(i, QTabBar.RightSide, close_btn)
        target = select_id or self._active_session_id
        for i in range(bar.count()):
            if bar.tabData(i) == target:
                bar.setCurrentIndex(i)
                break
        bar.blockSignals(False)
        self._refresh_session_tab_styles()

    def _refresh_session_tab_styles(self):
        bar = self._session_tab_bar
        if bar is None:
            return
        c = chrome_for(self._theme_id())
        if self._btn_new_session is not None:
            self._btn_new_session.setIcon(plus_icon(c["text"], 16))
        for i in range(bar.count()):
            sid = bar.tabData(i)
            s = self.find_session(sid)
            if s is None:
                continue
            label = s.tab_label()
            selected = i == bar.currentIndex()
            reconnect_timer = getattr(s, "_reconnect_timer", None)
            reconnecting = (not s.is_open() and reconnect_timer is not None
                            and reconnect_timer.isActive())
            if s.is_open():
                marker = status_dot_icon("#34C759", 12)
            elif reconnecting:
                marker = status_dot_icon(
                    c.get("warning", "#FF9F0A"), 12)
            else:
                marker = status_dot_icon(
                    "#FFFFFF" if selected else c["text_sec"], 12)
            tip_lines = []
            if s.has_custom_title():
                tip_lines.append(s.connection_label())
            tip_lines.append(self._session_tab_status_line(s, reconnecting))
            if s.period_on:
                tip_lines.append(self._t("session_tip_period_on"))
            busy_owned = getattr(self, "_hard_busy_owned_by", None)
            if callable(busy_owned) and busy_owned(s):
                tip_lines.append(self._t("session_tip_engine_busy"))
            if s._log_file is not None:
                tip_lines.append(self._t("session_tip_log_on"))
            elif s.log_wanted:
                tip_lines.append(self._t("session_tip_log_wanted"))
            bar.setTabText(i, label)
            bar.setTabIcon(i, marker)
            bar.setTabToolTip(i, "\n".join(tip_lines))
            bar.setTabData(i, s.id)
            close_btn = bar.tabButton(i, QTabBar.RightSide)
            if close_btn is not None:
                close_btn.setObjectName("SessionCloseBtn")
                close_btn.setIcon(close_icon(
                    "#FFFFFF" if selected else c["text_sec"], 12))
                close_btn.setIconSize(QSize(12, 12))
                close_btn.setFixedSize(18, 18)
                close_btn.setCursor(Qt.PointingHandCursor)
                close_btn.setFocusPolicy(Qt.NoFocus)
                set_tooltip(close_btn, self._t("session_close"))


    def _session_tab_status_line(self, session, reconnecting=False):
        if session.is_open():
            return self._t("session_tip_connected")
        if reconnecting:
            return self._t("session_tip_reconnecting")
        return self._t("session_tip_closed")

    def _on_new_session_clicked(self):
        if len(self._sessions) >= MAX_SESSIONS:
            self.toast(self._t("session_limit", n=MAX_SESSIONS))
            return
        self.add_session(activate=True)

    def add_session(self, activate=True, persist_data=None):
        if len(self._sessions) >= MAX_SESSIONS:
            return None
        if persist_data:
            s = Session.from_persist(self, persist_data)
        else:
            indices = [x.title_index for x in self._sessions
                       if x.title_index is not None]
            s = Session(self, title_index=max([1] + indices) + 1)
        while self.find_session(s.id) is not None:
            s.id = new_session_id()
        self._sessions.append(s)
        self._ensure_session_recv_widget(s)
        if self._session_tab_bar is not None:
            self._rebuild_session_tabs(
                select_id=s.id if activate else self._active_session_id)
        if activate:
            self.switch_session(s.id)
        if persist_data is None and hasattr(self, "_schedule_workspace_autosave"):
            self._schedule_workspace_autosave()
        return s

    def _on_session_tab_changed(self, index):
        if self._switching_session or index < 0:
            return
        bar = self._session_tab_bar
        if bar is None:
            return
        sid = bar.tabData(index)
        if sid and sid != self._active_session_id:
            self.switch_session(sid)

    def _on_session_tab_double_clicked(self, index):
        """Rename session tab (optional custom_title). Empty clears rename."""
        bar = self._session_tab_bar
        if bar is None or index < 0:
            return
        sid = bar.tabData(index)
        s = self.find_session(sid)
        if s is None:
            return
        current = s.title if s.has_custom_title() else ""
        builder = getattr(self, "_build_themed_text_input_dialog", None)
        if not callable(builder):
            return
        dlg = builder(
            self._t("session_rename"), self._t("session_rename_prompt"),
            current)
        if dlg.exec_() != QDialog.Accepted:
            return
        text = dlg.textValue()
        s.set_custom_title(text)
        self._refresh_session_tab_styles()
        if hasattr(self, "_schedule_workspace_autosave"):
            self._schedule_workspace_autosave()

    def _on_session_tab_close(self, index):
        bar = self._session_tab_bar
        if bar is None or len(self._sessions) <= 1:
            return
        sid = bar.tabData(index)
        self.close_session(sid)

    def _ensure_session_recv_widget(self, session):
        te = session.ensure_recv_widget(getattr(self, "_recv_font_size", 10))
        # max_lines is window-wide.  New/reset tabs must inherit the current
        # limit instead of silently falling back to Session's 10000 default.
        max_lines = None
        for other in self._sessions:
            if other is not session and other.txt_recv is not None:
                max_lines = other.txt_recv.document().maximumBlockCount()
                break
        if not max_lines and hasattr(self, "ed_max_lines"):
            try:
                max_lines = int(self.ed_max_lines.text())
            except (TypeError, ValueError):
                max_lines = None
        if max_lines and max_lines > 0:
            te.document().setMaximumBlockCount(max_lines)
        if hasattr(self, "sw_wrap"):
            te.setLineWrapMode(
                QTextEdit.WidgetWidth if self.sw_wrap.isChecked()
                else QTextEdit.NoWrap)
        te.setProperty("tr_tooltip", "sel_chk_hint")
        set_tooltip(te, self._t("sel_chk_hint"))
        te.setContextMenuPolicy(Qt.PreventContextMenu)
        te.viewport().installEventFilter(self)
        te.installEventFilter(self)
        if hasattr(self, "_sel_chk_timer"):
            te.selectionChanged.connect(self._sel_chk_timer.start)
        if hasattr(self, "_refresh_quick_start"):
            te.textChanged.connect(self._refresh_quick_start)
        if hasattr(self, "_on_recv_scroll"):
            te.verticalScrollBar().valueChanged.connect(
                lambda value, _s=session: self._on_session_recv_scroll(_s, value))
        if self.recv_stack is not None:
            # Avoid double-add
            if self.recv_stack.indexOf(te) < 0:
                self.recv_stack.addWidget(te)
        return te

    def _on_session_recv_scroll(self, session, value):
        if session.id == self._active_session_id:
            self._on_recv_scroll(value)

    def _session_exclusive_busy(self):
        """Close-guard: current/context session owns a hard-busy engine.

        Tab switch is soft-leave — engines stay pinned to their owner session
        and keep receiving in the background. Closing that owner tab is still
        blocked while the engine runs.
        """
        busy_owned = getattr(self, "_hard_busy_owned_by", None)
        if callable(busy_owned):
            return bool(busy_owned(
                self._session_ctx() or self.active_session()))
        return bool(self._io_task_busy(exclude=("periodic", "multi")))

    def _release_leave_safe_window_tasks(self):
        """Stop window tasks that must not migrate across tabs; return keys stopped.

        Currently empty — multi-send cycle is per-session like periodic send.
        Kept as an extension point for future leave-safe window tasks.
        """
        return []

    def _toast_leave_safe_stopped(self, stopped):
        if not stopped:
            return
        toast_fn = getattr(self, "toast_session_leave_stopped", None)
        if callable(toast_fn):
            toast_fn(stopped)
            return
        # Fallback when host mixin is used without CommTool toast helper.
        sep = self._t("io_task_sep")
        tasks = sep.join(self._t("io_task_%s" % name) for name in stopped)
        self.toast(self._t("session_leave_stopped", tasks=tasks))

    def close_session(self, session_id, confirm=True):
        if len(self._sessions) <= 1:
            return False
        s = self.find_session(session_id)
        if s is None:
            return False
        closing_index = self._sessions.index(s)
        # Busy: cannot close a tab that owns a hard-busy engine.
        busy_owned = getattr(self, "_hard_busy_owned_by", None)
        if callable(busy_owned):
            if busy_owned(s):
                self.toast_session_busy()
                return False
        elif s.id == self._active_session_id and self._session_exclusive_busy():
            self.toast_session_busy()
            return False
        # Always confirm tab close (X); connected sessions warn about disconnect.
        if confirm and hasattr(self, "_confirm_dlg"):
            name = s.tab_label()
            body_key = ("session_close_confirm_open" if s.conn is not None
                        else "session_close_confirm")
            reconnect_active = s._reconnect_timer.isActive()
            reconnect_remaining = (s._reconnect_timer.remainingTime()
                                   if reconnect_active else -1)
            period_active = s._period_timer.isActive()
            period_interval = s._period_timer.interval()
            had_conn = s.conn is not None
            previous_user_closing = s._user_closing
            s._user_closing = True
            if reconnect_active:
                s._reconnect_timer.stop()
            if period_active:
                s._period_timer.stop()
            confirmed = False
            try:
                confirmed = bool(self._confirm_dlg(
                    self._t("session_close"), self._t(body_key, name=name),
                    danger=True))
            finally:
                if not confirmed:
                    s._user_closing = previous_user_closing
                    if reconnect_active:
                        s._reconnect_timer.start(max(500, reconnect_remaining))
                    if period_active and s.period_on and s.is_open():
                        s._period_timer.start(period_interval)
            if not confirmed:
                # The link may drop while the modal dialog is open. Its state
                # callback sees _user_closing and correctly avoids reconnect;
                # cancelling the close must put that session back into policy.
                if not reconnect_active and had_conn and s.conn is None:
                    with self._with_session(s):
                        self._schedule_reconnect()
                return False
        was_active = s.id == self._active_session_id
        if was_active:
            # Confirmed leave: drop any remaining leave-safe window tasks.
            self._release_leave_safe_window_tasks()
        # Close connection for this session
        with self._with_session(s):
            s._user_closing = True
            if s.conn is not None:
                self.close_conn(update_ui=(s.id == self._active_session_id))
            s._user_closing = False
            if s._reconnect_timer.isActive():
                s._reconnect_timer.stop()
            if s._ar_gap_timer.isActive():
                s._ar_gap_timer.stop()
            if s._period_timer.isActive():
                s._period_timer.stop()
            s.period_on = False
            ms_timer = getattr(s, "_ms_cycle_timer", None)
            if ms_timer is not None and ms_timer.isActive():
                stop_ms = getattr(self, "_ms_stop_cycle", None)
                if callable(stop_ms):
                    stop_ms(s)
                else:
                    ms_timer.stop()
                    s._ms_cycle_seq = []
                    s._ms_cycle_idx = 0
            # Same "stop first" pattern as period/ms — do not rely only on
            # close_conn → _seq_abort (conn may already be None).
            seq_timer = getattr(s, "_seq_timer", None)
            if seq_timer is not None and seq_timer.isActive():
                seq_timer.stop()
            if getattr(s, "_seq_on", False):
                abort = getattr(self, "_seq_abort", None)
                if callable(abort):
                    abort("seq_aborted_disc")
            if getattr(s, "_log_file", None) is not None:
                try:
                    self._close_log_file(session=s, toast=False)
                except (OSError, RuntimeError, TypeError):
                    _log.debug("close session log failed", exc_info=True)
            s.log_wanted = False
        # Floating receive controls are children of the active QTextEdit. Move
        # them out before deleting that view or their C++ objects die with it.
        if was_active:
            for attr in ("_search_bar", "btn_to_bottom"):
                widget = getattr(self, attr, None)
                if widget is not None:
                    widget.setParent(self)
        # Remove recv widget
        if self.recv_stack is not None and s.txt_recv is not None:
            recv_widget = s.txt_recv
            self.recv_stack.removeWidget(recv_widget)
            if getattr(self, "_txt_recv_fallback", None) is recv_widget:
                self._txt_recv_fallback = None
            recv_widget.deleteLater()
            s.txt_recv = None
        self._sessions = [x for x in self._sessions if x is not s]
        # Per-session auto-reply cooldown maps are runtime-only. Drop the dead
        # id so repeated tab churn cannot grow every shared rule indefinitely.
        for rule in getattr(self, "_ar_rules", ()):
            by_session = rule.get("_last_by_session")
            if isinstance(by_session, dict):
                by_session.pop(s.id, None)
        self._dispose_session_timers(s)
        if was_active:
            neighbor_index = min(closing_index, len(self._sessions) - 1)
            self._active_session_id = self._sessions[neighbor_index].id
        self._rebuild_session_tabs(select_id=self._active_session_id)
        if was_active:
            target = self.active_session()
            self._txt_recv_fallback = target.txt_recv
            self._load_session_into_ui(target)
            if self.recv_stack is not None and target.txt_recv is not None:
                self.recv_stack.setCurrentWidget(target.txt_recv)
            self._restore_session_network_ui(target)
            self._reparent_recv_overlays(target.txt_recv)
            self._refresh_stat_labels()
            plot_changed = getattr(self, "_on_active_session_plot_changed", None)
            if callable(plot_changed):
                plot_changed()
            if hasattr(self, "_schedule_keyword_rebuild"):
                self._schedule_keyword_rebuild()
            if hasattr(self, "_search_matches"):
                self._search_matches = []
                self._search_idx = -1
                self._search_match_capped = False
                self._search_scan_end = 0
                self._search_page_starts = [0]
                if hasattr(self, "lbl_search_cnt"):
                    self.lbl_search_cnt.setText("")
            seq_notify = getattr(self, "_seq_notify", None)
            if callable(seq_notify):
                seq_notify()
        if hasattr(self, "_schedule_workspace_autosave"):
            self._schedule_workspace_autosave()
        return True

    def switch_session(self, session_id):
        if session_id == self._active_session_id:
            return True
        target = self.find_session(session_id)
        if target is None:
            return False
        cur = self.active_session()
        # Soft leave: pinned engines keep running on the owner session.
        if cur is not None:
            stopped = self._release_leave_safe_window_tasks()
            self._toast_leave_safe_stopped(stopped)
            stop_ble = getattr(self, "_stop_ble_scan", None)
            if callable(stop_ble):
                stop_ble("leave")
        begin_autosave_pause = getattr(
            self, "_begin_workspace_autosave_pause", None)
        end_autosave_pause = getattr(
            self, "_end_workspace_autosave_pause", None)
        autosave_paused = (callable(begin_autosave_pause)
                           and callable(end_autosave_pause))
        if autosave_paused:
            begin_autosave_pause()
        self._switching_session = True
        try:
            if cur is not None:
                self._save_ui_into_session(cur)
            self._active_session_id = target.id
            self._load_session_into_ui(target)
            if self.recv_stack is not None and target.txt_recv is not None:
                self.recv_stack.setCurrentWidget(target.txt_recv)
            self._restore_session_network_ui(target)
            self._reparent_recv_overlays(target.txt_recv)
            self._rebuild_session_tabs(select_id=target.id)
            self._refresh_stat_labels()
            plot_changed = getattr(self, "_on_active_session_plot_changed", None)
            if callable(plot_changed):
                plot_changed()
            self._sync_open_button_from_session(target)
            refresh_quick = getattr(self, "_refresh_quick_start", None)
            if callable(refresh_quick):
                refresh_quick()
            seq_notify = getattr(self, "_seq_notify", None)
            if callable(seq_notify):
                seq_notify()
            self._mbm_on = bool(getattr(target, "_mbm_enabled", False))
            self._ar_on = bool(getattr(target, "_ar_enabled", False))
            sync_ar = getattr(self, "_sync_autoreply_ui", None)
            if callable(sync_ar):
                sync_ar()
            mbm_dlg = getattr(self, "_mbm_dlg", None)
            if mbm_dlg is not None:
                if hasattr(mbm_dlg, "cb_enable"):
                    cb = mbm_dlg.cb_enable
                    cb.blockSignals(True)
                    cb.setChecked(bool(getattr(target, "_mbm_enabled", False)))
                    cb.blockSignals(False)
                reload_rows = getattr(mbm_dlg, "reload_rows", None)
                if callable(reload_rows):
                    try:
                        reload_rows()
                    except Exception:
                        _log.debug("mbm dialog reload on switch failed", exc_info=True)
            script_dlg = getattr(self, "_script_dlg", None)
            if script_dlg is not None:
                show_log = getattr(script_dlg, "show_session_log", None)
                if callable(show_log):
                    try:
                        show_log()
                    except Exception:
                        _log.debug("script console log switch failed", exc_info=True)
                if hasattr(script_dlg, "_set_running_ui"):
                    script_dlg._set_running_ui(bool(
                        getattr(self, "_script_running", lambda: False)()))
            xfer_dlg = getattr(self, "_xfer_dlg", None)
            sync_xfer = getattr(xfer_dlg, "sync_session", None) if xfer_dlg is not None else None
            if callable(sync_xfer):
                try:
                    sync_xfer()
                except Exception:
                    _log.debug("xfer dialog switch failed", exc_info=True)
            rr_dlg = getattr(self, "_rr_dlg", None)
            sync_rr = getattr(rr_dlg, "sync_session", None) if rr_dlg is not None else None
            if callable(sync_rr):
                try:
                    sync_rr()
                except Exception:
                    _log.debug("rec/replay dialog switch failed", exc_info=True)
            device_dlg = getattr(self, "_device_center_dlg", None)
            sync_scan = getattr(device_dlg, "sync_session", None) if device_dlg is not None else None
            if callable(sync_scan):
                try:
                    sync_scan()
                except Exception:
                    _log.debug("device center scan switch failed", exc_info=True)
            if hasattr(self, "_schedule_keyword_rebuild"):
                self._schedule_keyword_rebuild()
            # Search hits are document-bound; drop them on switch.
            if hasattr(self, "_search_matches"):
                self._search_matches = []
                self._search_idx = -1
                self._search_match_capped = False
                self._search_scan_end = 0
                self._search_page_starts = [0]
                if hasattr(self, "lbl_search_cnt"):
                    self.lbl_search_cnt.setText("")
        finally:
            self._switching_session = False
            if autosave_paused:
                end_autosave_pause()
        if hasattr(self, "_schedule_workspace_autosave"):
            self._schedule_workspace_autosave()
        return True

    @staticmethod
    def _dispose_session_timers(session):
        """Destroy Qt timers when a session permanently leaves the host."""
        for name in ("_reconnect_timer", "_ar_gap_timer", "_period_timer",
                     "_reset_timer", "_ms_cycle_timer", "_seq_timer",
                     "_mbm_sched", "_mbm_to"):
            timer = getattr(session, name, None)
            if timer is None:
                continue
            if timer.isActive():
                timer.stop()
            timer.deleteLater()

    def _restore_session_network_ui(self, session):
        """Restore connection-owned transient UI after a tab switch."""
        if not hasattr(self, "cb_target"):
            return
        if session is not None and "Server" in str(session._conn_proto or ""):
            # _on_clients_changed rebuilds the shared combo and snapshots its
            # selection. Keep this session's choice before that shared UI work.
            want = getattr(session, "send_target", None)
            with self._with_session(session):
                self._on_clients_changed(list(session.clients or []))
            # Restore this session's chosen client after the combo rebuild.
            if want is not None and hasattr(self, "cb_target"):
                idx = self.cb_target.findData(want)
                if idx < 0:
                    idx = 0
                    session.send_target = self.cb_target.itemData(0)
                self.cb_target.blockSignals(True)
                self.cb_target.setCurrentIndex(idx)
                self.cb_target.blockSignals(False)
                session.send_target = self.cb_target.currentData()
        else:
            self.cb_target.clear()
        peer = getattr(session, "udp_peer", None) if session is not None else None
        if peer and session.id == self._active_session_id:
            with self._with_session(session):
                self._on_udp_peer_changed(peer[0], peer[1])
        sync_ctrl_poll = getattr(self, "_sync_ctrl_poll_for_active_session", None)
        if callable(sync_ctrl_poll):
            sync_ctrl_poll()

    def _reparent_recv_overlays(self, txt):
        """Move search bar / to-bottom button onto the active recv widget."""
        if txt is None:
            return
        for attr in ("_search_bar", "btn_to_bottom"):
            w = getattr(self, attr, None)
            if w is None:
                continue
            w.setParent(txt)
            if attr == "btn_to_bottom":
                w.hide()
            # reposition on next resize
        if hasattr(self, "_reposition_to_bottom_btn"):
            try:
                self._reposition_to_bottom_btn()
            except (RuntimeError, AttributeError, TypeError):
                _log.debug("reposition to-bottom button failed", exc_info=True)
        if hasattr(self, "_reposition_search_bar"):
            try:
                self._reposition_search_bar()
            except (RuntimeError, AttributeError, TypeError):
                _log.debug("reposition search bar failed", exc_info=True)

    def _save_ui_into_session(self, session):
        if session is None:
            return
        try:
            session.conn_fields = self._capture_connection_fields()
        except (TypeError, ValueError, RuntimeError, AttributeError):
            _log.debug("capture conn fields failed", exc_info=True)
        if hasattr(self, "txt_send"):
            session.send_draft = self.txt_send.toPlainText()
        # Display / send options snapshot (best-effort)
        opts = {}
        for attr, key in (
            ("sw_tx_hex", "tx_hex"),
            ("sw_append_newline", "append_nl_on"),
            ("sw_hexdump", "hexdump"),
            ("sw_rx_hex", "rx_hex"),
        ):
            w = getattr(self, attr, None)
            if w is None:
                continue
            if hasattr(w, "isChecked"):
                opts[key] = bool(w.isChecked())
            elif hasattr(w, "currentText"):
                opts[key] = w.currentText()
            elif hasattr(w, "currentData"):
                opts[key] = w.currentData()
        # Store combo indices so background TX does not depend on translated labels.
        if hasattr(self, "cb_append_nl"):
            opts["append_nl"] = int(self.cb_append_nl.currentIndex())
        if hasattr(self, "cb_checksum"):
            opts["checksum"] = int(self.cb_checksum.currentIndex())
        # Only TCP/UDP Server sidebars own cb_target; other protos must not
        # clobber a session's last server target while the combo is stale.
        if ("Server" in str(session._conn_proto or "")
                and hasattr(self, "cb_target") and self.cb_target.count() > 0):
            session.send_target = self.cb_target.currentData()
        opts.update({
            "terminal_on": bool(getattr(self, "_terminal_on", False)),
            "hexdump_on": bool(getattr(self, "_hexdump_on", False)),
            "numview_on": bool(getattr(self, "_numview_on", False)),
            "ansi_on": bool(getattr(self, "_ansi_on", False)),
            "proto_hl_on": bool(getattr(self, "_proto_hl_on", False)),
            "freeze_view": bool(getattr(self, "_freeze_view", False)),
            "line_split": bool(self.sw_line_split.isChecked())
            if hasattr(self, "sw_line_split") else False,
            "line_nl": int(self.cb_line_nl.currentIndex())
            if hasattr(self, "cb_line_nl") else 0,
            "packet_split": bool(self.sw_packet_split.isChecked())
            if hasattr(self, "sw_packet_split") else False,
            "packet_timeout": self.ed_packet_timeout.text()
            if hasattr(self, "ed_packet_timeout") else "0",
            "show_timestamp": bool(self.sw_show_timestamp.isChecked())
            if hasattr(self, "sw_show_timestamp") else False,
            "ts_format": getattr(self, "_ts_format", "absolute"),
            "encoding": self.cb_encoding.currentData()
            if hasattr(self, "cb_encoding") else "auto",
            "hexdump_width": self.cb_hexdump_width.currentText()
            if hasattr(self, "cb_hexdump_width") else "16",
            "numview_spec": self._numview_spec()
            if hasattr(self, "_numview_spec") else ("u16", "le"),
            "log_split": self.cb_log_split.currentText()
            if hasattr(self, "cb_log_split") else "",
        })
        session.display_opts = opts
        if hasattr(self, "sw_log_file"):
            # While disconnected, the switch is shown off even if log_wanted is
            # preserved for auto-reconnect — never clear intent from that UI.
            if session._log_file is not None or self.sw_log_file.isChecked():
                session.log_wanted = True
            elif session.is_open():
                session.log_wanted = False
            if hasattr(self, "cb_log_split") and hasattr(self, "_parse_log_limit"):
                session._log_limit = self._parse_log_limit(
                    self.cb_log_split.currentText())
        if hasattr(self, "ed_period_ms"):
            session.period_ms = self.ed_period_ms.text()
        if hasattr(self, "sw_period"):
            # Keep running timers authoritative when leaving a background-capable tab.
            if session._period_timer.isActive():
                session.period_on = True
            elif session.is_open():
                session.period_on = bool(self.sw_period.isChecked())
            elif self.sw_period.isChecked():
                # Disconnected: adopt explicit ON; do not clear reconnect intent
                # when the switch is shown off because the link is down.
                session.period_on = True

    def _load_session_into_ui(self, session):
        if session is None:
            return
        previous_switching = self._switching_session
        self._switching_session = True
        try:
            try:
                self._apply_connection_fields(session.conn_fields or {})
            except (TypeError, ValueError):
                _log.debug("invalid persisted connection fields", exc_info=True)
                session.conn_fields = {}
            if hasattr(self, "txt_send"):
                self.txt_send.setPlainText(session.send_draft or "")
            if hasattr(self, "ed_period_ms") and session.period_ms:
                self.ed_period_ms.setText(str(session.period_ms))
            self._restore_session_periodic(session)
            if hasattr(self, "_set_ms_cycle_btn"):
                ms_timer = getattr(session, "_ms_cycle_timer", None)
                self._set_ms_cycle_btn(
                    bool(ms_timer is not None and ms_timer.isActive()))
            # Missing fields in an old/partial snapshot must not inherit the
            # previously active tab's controls.  Use the same deterministic
            # defaults as background processing, then overlay this session.
            opts = dict(_BACKGROUND_DISPLAY_DEFAULTS)
            if isinstance(session.display_opts, dict):
                opts.update(session.display_opts)
            for attr, key in (
                ("sw_tx_hex", "tx_hex"),
                ("sw_append_newline", "append_nl_on"),
                ("sw_hexdump", "hexdump"),
                ("sw_rx_hex", "rx_hex"),
                ("sw_line_split", "line_split"),
                ("sw_packet_split", "packet_split"),
                ("sw_show_timestamp", "show_timestamp"),
                ("sw_ansi", "ansi_on"),
                ("sw_numview", "numview_on"),
            ):
                if key not in opts:
                    continue
                w = getattr(self, attr, None)
                if w is not None and hasattr(w, "setChecked"):
                    w.blockSignals(True)
                    w.setChecked(bool(opts[key]))
                    w.blockSignals(False)
            if "hexdump" in opts:
                self._hexdump_on = bool(opts["hexdump"])
            if "numview_on" in opts:
                self._numview_on = bool(opts["numview_on"])
            if "ansi_on" in opts:
                self._ansi_on = bool(opts["ansi_on"])
            self._terminal_on = bool(opts.get("terminal_on", False))
            if hasattr(self, "sw_terminal"):
                self.sw_terminal.blockSignals(True)
                self.sw_terminal.setChecked(self._terminal_on)
                self.sw_terminal.blockSignals(False)
            self._proto_hl_on = bool(opts.get("proto_hl_on", False))
            if hasattr(self, "_frame_dlg") and self._frame_dlg is not None:
                self._frame_dlg.sync_highlight()
            if hasattr(self, "_apply_terminal_ui"):
                self._apply_terminal_ui(self._terminal_on)
            freeze = bool(opts.get("freeze_view", session._freeze_view))
            if self._terminal_on:
                freeze = False
            session._freeze_view = freeze
            if hasattr(self, "sw_freeze_view"):
                self.sw_freeze_view.blockSignals(True)
                self.sw_freeze_view.setChecked(freeze, animate=False)
                self.sw_freeze_view.blockSignals(False)
            for attr, key in (("cb_append_nl", "append_nl"),
                              ("cb_checksum", "checksum")):
                if key not in opts:
                    continue
                w = getattr(self, attr, None)
                if w is None:
                    continue
                w.blockSignals(True)
                raw = opts[key]
                try:
                    idx = int(raw)
                    if 0 <= idx < w.count():
                        w.setCurrentIndex(idx)
                    elif hasattr(w, "setCurrentText"):
                        w.setCurrentText(str(raw))
                except (TypeError, ValueError):
                    if hasattr(w, "setCurrentText"):
                        w.setCurrentText(str(raw))
                w.blockSignals(False)
            if "line_nl" in opts and hasattr(self, "cb_line_nl"):
                self.cb_line_nl.blockSignals(True)
                try:
                    idx = int(opts["line_nl"])
                except (TypeError, ValueError):
                    idx = 0
                self.cb_line_nl.setCurrentIndex(
                    idx if 0 <= idx < self.cb_line_nl.count() else 0)
                self.cb_line_nl.blockSignals(False)
            if "packet_timeout" in opts and hasattr(self, "ed_packet_timeout"):
                self.ed_packet_timeout.blockSignals(True)
                self.ed_packet_timeout.setText(str(opts["packet_timeout"]))
                self.ed_packet_timeout.blockSignals(False)
            if "encoding" in opts and hasattr(self, "cb_encoding"):
                idx = self.cb_encoding.findData(opts["encoding"])
                if idx >= 0:
                    self.cb_encoding.blockSignals(True)
                    self.cb_encoding.setCurrentIndex(idx)
                    self.cb_encoding.blockSignals(False)
            if "hexdump_width" in opts and hasattr(self, "cb_hexdump_width"):
                self.cb_hexdump_width.blockSignals(True)
                self.cb_hexdump_width.setCurrentText(str(opts["hexdump_width"]))
                self.cb_hexdump_width.blockSignals(False)
            if "numview_spec" in opts and hasattr(self, "cb_numview_type"):
                raw_spec = opts["numview_spec"]
                spec = tuple(raw_spec) if isinstance(raw_spec, (tuple, list)) else raw_spec
                idx = self.cb_numview_type.findData(spec)
                if idx >= 0:
                    self.cb_numview_type.blockSignals(True)
                    self.cb_numview_type.setCurrentIndex(idx)
                    self.cb_numview_type.blockSignals(False)
            if "ts_format" in opts:
                self._ts_format = str(opts["ts_format"])
                if hasattr(self, "cb_ts_format"):
                    idx = self.cb_ts_format.findData(self._ts_format)
                    if idx >= 0:
                        self.cb_ts_format.blockSignals(True)
                        self.cb_ts_format.setCurrentIndex(idx)
                        self.cb_ts_format.blockSignals(False)
            if "log_split" in opts and hasattr(self, "cb_log_split"):
                self.cb_log_split.blockSignals(True)
                self.cb_log_split.setCurrentText(str(opts["log_split"]))
                self.cb_log_split.blockSignals(False)
            if hasattr(self, "_parse_log_limit") and hasattr(self, "cb_log_split"):
                session._log_limit = self._parse_log_limit(
                    opts.get("log_split") or self.cb_log_split.currentText())
            if hasattr(self, "_refresh_hex_toggle_state"):
                self._refresh_hex_toggle_state()
            # Live log is per-session: sync switch/label only; never close others.
            if hasattr(self, "sw_log_file"):
                logging_on = session._log_file is not None
                self.sw_log_file.blockSignals(True)
                self.sw_log_file.setChecked(logging_on)
                self.sw_log_file.blockSignals(False)
                if hasattr(self, "_set_log_path_label"):
                    self._set_log_path_label(
                        session._log_file_path if logging_on else "")
            self._sync_open_button_from_session(session)
            if session.is_open():
                self.set_settings_enabled(False)
            else:
                self.set_settings_enabled(True)
            self._update_net_fields()
        finally:
            self._switching_session = previous_switching

    def _sync_session_period_timer(self, session):
        """Start/stop one session's period timer from its own intent."""
        if session is None or getattr(session, "_period_timer", None) is None:
            return
        timer = session._period_timer
        if session.period_on:
            try:
                ms = int(session.period_ms or "1000")
                if ms < 10:
                    raise ValueError(self._t("err_min_period"))
            except (TypeError, ValueError) as e:
                # Imported/persisted sessions bypass the live toggle validator.
                # Disable an invalid schedule instead of silently running at 10ms.
                session.period_on = False
                if timer.isActive():
                    timer.stop()
                if session is self.active_session():
                    self.toast(self._t("err_period_bad", e=e), error=True)
                return
        want = bool(session.period_on and session.is_open())
        if not want:
            if timer.isActive():
                timer.stop()
            return
        if timer.isActive() and timer.interval() == ms:
            return
        timer.start(ms)

    def _restore_session_periodic(self, session):
        """Sync sidebar period switch to this session; leave other timers alone."""
        if not hasattr(self, "sw_period"):
            return
        self._sync_session_period_timer(session)
        want = bool(session and session.period_on and session.is_open())
        self.sw_period.blockSignals(True)
        self.sw_period.setChecked(want)
        self.sw_period.blockSignals(False)

    def _period_send_for(self, sid):
        """Timer callback: TX using the owning session's draft/conn/opts."""
        session = self.find_session(sid)
        if session is None:
            return
        if not session.period_on or not session.is_open():
            if session._period_timer.isActive():
                session._period_timer.stop()
            return
        is_active = session is self.active_session()
        opts = (dict(session.display_opts or {}) if is_active
                else self._background_display_opts(session))
        if is_active:
            if hasattr(self, "txt_send"):
                raw = self.txt_send.toPlainText()
                session.send_draft = raw
            # Read only TX controls here.  A 10 ms timer must not snapshot the
            # entire connection sidebar and every receive/display option.
            if hasattr(self, "sw_tx_hex"):
                opts["tx_hex"] = bool(self.sw_tx_hex.isChecked())
            if hasattr(self, "sw_append_newline"):
                opts["append_nl_on"] = bool(self.sw_append_newline.isChecked())
            if hasattr(self, "cb_append_nl"):
                opts["append_nl"] = int(self.cb_append_nl.currentIndex())
            if hasattr(self, "cb_checksum"):
                opts["checksum"] = int(self.cb_checksum.currentIndex())
            if hasattr(self, "cb_encoding"):
                opts["encoding"] = self.cb_encoding.currentData()
            if ("Server" in str(session._conn_proto or "")
                    and hasattr(self, "cb_target") and self.cb_target.count() > 0):
                session.send_target = self.cb_target.currentData()
        else:
            raw = session.send_draft or ""
        if not raw:
            return
        hex_mode = bool(opts.get("tx_hex", False))
        try:
            checksum = int(opts.get("checksum", 0) or 0)
        except (TypeError, ValueError):
            checksum = 0
        # Pass the owning session/current UI selection explicitly; None would
        # make _send_text consult a potentially stale display snapshot.
        if bool(opts.get("append_nl_on", False)):
            try:
                # Combo index is 0/1/2; _send_text's explicit override is 1/2/3.
                newline = int(opts.get("append_nl", 0) or 0) + 1
            except (TypeError, ValueError):
                newline = 1
        else:
            newline = 0
        target = None
        if "Server" in str(session._conn_proto or ""):
            target = session.send_target
        with self._with_session(session):
            # Only the engine-owning session pauses its own period TX.
            if self._period_tx_blocked(session):
                return
            previous_ctx = getattr(self, "_display_context", None)
            if not is_active:
                # Keep RX/TX display+log formatting on this session's opts.
                self._display_context = dict(opts)
                self._display_context["background"] = True
            errors_before = int(getattr(session, "tx_errors", 0) or 0)
            try:
                ok = self._send_with_subst(
                    raw, hex_mode=hex_mode, newline=newline, checksum=checksum,
                    target=target, encoding=opts.get("encoding"),
                    record_macro=False, notify_ui=is_active,
                    # Recorder is session-gated inside _record_stream_tx;
                    # triggers always need the TX bytes (background tabs too).
                    feed_window_engines=True)
            finally:
                if not is_active:
                    self._display_context = previous_ctx
            if not ok:
                # Background format/preflight failures are deliberately silent
                # in the active UI.  Preserve one observable error on the
                # owning tab; transport failures already increment it below.
                if (not is_active
                        and int(getattr(session, "tx_errors", 0) or 0)
                        == errors_before):
                    self._stat_note_tx_error()
                session.period_on = False
                if session._period_timer.isActive():
                    session._period_timer.stop()
                if session is self.active_session() and hasattr(self, "sw_period"):
                    self.sw_period.blockSignals(True)
                    self.sw_period.setChecked(False)
                    self.sw_period.blockSignals(False)

    def _sync_open_button_from_session(self, session):
        if not hasattr(self, "btn_open"):
            return
        opened = bool(session and session.is_open())
        self.btn_open.setProperty("state", "open" if opened else "")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        if hasattr(self, "_update_net_fields"):
            self._update_net_fields()
        if hasattr(self, "_update_conn_status"):
            try:
                self._update_conn_status()
            except (RuntimeError, AttributeError, TypeError, ValueError):
                _log.debug("update conn status after session sync failed",
                           exc_info=True)

    # ---- Resource conflict ----
    @staticmethod
    def _session_resource_key_from_open(proto, fields):
        """Build a canonical exclusive-resource key from open() fields."""
        fields = fields or {}
        proto = str(proto or "")
        if proto == "Virtual" or proto == "TCP Client":
            return None
        if proto == "Serial":
            port = fields.get("port")
            return ("serial", str(port).upper()) if port else None
        if proto == "BLE":
            addr = str(fields.get("address") or fields.get("ble_address") or "").strip()
            if not addr:
                return None
            from transport import ble_uuid
            addr = ble_uuid.normalize_address(addr)
            return ("ble", addr) if addr else None
        port = fields.get("local_port")
        if not port:
            return None
        try:
            port = str(int(str(port)))
        except (TypeError, ValueError):
            port = str(port)
        ip = str(fields.get("local_ip") or "0.0.0.0").strip()
        return ("net-bind", ip, port)

    def _session_resource_key_from_ui(self):
        """Build conflict key from current sidebar fields (before open)."""
        proto = self.cb_proto.currentText() if hasattr(self, "cb_proto") else ""
        fields = {
            "port": self.cb_port.currentData() if hasattr(self, "cb_port") else None,
            "local_ip": (self.cb_local_ip.currentText()
                         if hasattr(self, "cb_local_ip") else ""),
            "local_port": (self.ed_local_port.text()
                           if hasattr(self, "ed_local_port") else ""),
            "address": (self.ed_ble_address.text()
                        if hasattr(self, "ed_ble_address") else ""),
        }
        return self._session_resource_key_from_open(proto, fields)

    def _session_resource_key(self, session):
        if session is None or session.conn is None:
            return None
        proto = session._conn_proto
        if (not session.is_open()
                and str(proto or "") != "BLE"):
            return None
        cfg = session._conn_cfg
        if proto == "Serial" and cfg and len(cfg) > 1:
            return ("serial", str(cfg[1]).upper())
        if proto == "BLE" and cfg and len(cfg) > 1 and cfg[1]:
            from transport import ble_uuid
            addr = ble_uuid.normalize_address(cfg[1])
            return ("ble", addr) if addr else None
        snapshot = getattr(session, "_reconnect_snapshot", None) or {}
        if snapshot:
            key = self._session_resource_key_from_open(
                snapshot.get("proto") or proto, snapshot.get("fields") or {})
            if key is not None:
                return key
        fields = session.conn_fields or {}
        key = self._session_resource_key_from_open(proto, {
            "port": fields.get("ser_port"),
            "local_ip": fields.get("net_local_ip"),
            "local_port": fields.get("net_local_port"),
            "address": fields.get("ble_address"),
        })
        if key is not None:
            return key
        if cfg and len(cfg) >= 3 and "Server" in str(proto):
            return self._session_resource_key_from_open(proto, {
                "local_ip": cfg[1], "local_port": cfg[2]})
        return None

    @staticmethod
    def _session_resource_keys_conflict(left, right):
        if left is None or right is None or left[0] != right[0]:
            return False
        if left[0] == "serial":
            return left == right
        if left[0] == "net-bind":
            _kind, left_ip, left_port = left
            _kind, right_ip, right_port = right
            wildcard = {"", "0.0.0.0", "::", "::0"}
            return (left_port == right_port
                    and (left_ip == right_ip
                         or left_ip in wildcard or right_ip in wildcard))
        return left == right

    def check_session_resource_conflict(self, key=None, session=None):
        """Return the session conflicting with an intended open, if any."""
        key = key if key is not None else self._session_resource_key_from_ui()
        if key is None:
            return None
        candidate = session or self._session_ctx() or self.active_session()
        for s in self._sessions:
            if candidate is not None and s.id == candidate.id:
                continue
            other = self._session_resource_key(s)
            if self._session_resource_keys_conflict(key, other):
                return s
        return None

    # ---- Signal routing ----
    def _bind_conn_signals(self, conn, session):
        sid = session.id
        # Capture conn identity so queued RX after close/reconnect is dropped.
        if hasattr(conn, "data_received_from"):
            conn.data_received_from.connect(
                lambda data, target=None, _sid=sid, _c=conn:
                    self._route_session_data(_sid, data, target, _c))
        else:
            conn.data_received.connect(
                lambda data, _sid=sid, _c=conn:
                    self._route_session_data(_sid, data, None, _c))
        conn.error_occurred.connect(
            lambda msg, _sid=sid: self._route_session_error(_sid, msg))
        conn.state_changed.connect(
            lambda opened, _sid=sid: self._route_session_state(_sid, opened))
        if hasattr(conn, "clients_changed"):
            conn.clients_changed.connect(
                lambda clients, _sid=sid: self._route_session_clients(_sid, clients))
        if hasattr(conn, "peer_changed"):
            # peer_changed emits (ip, port)  - do not treat port as session id.
            conn.peer_changed.connect(
                lambda ip, port, _sid=sid: self._route_session_peer(_sid, ip, port))

    def _route_session_data(self, session_id, data, reply_target=None, source_conn=None):
        s = self.find_session(session_id)
        if s is None:
            return
        if source_conn is not None and s.conn is not source_conn:
            return
        with self._with_session(s):
            if s.id == self._active_session_id:
                self.on_data_received(data, reply_target)
            else:
                # Background: view/stats/log + session-pinned engines (AR/MBM/…).
                self._on_background_session_data(data, reply_target)

    def _on_background_session_data(self, data, reply_target=None):
        """Render with the owning session's options; feed session-pinned engines."""
        s = self._session_ctx()
        if s is None:
            return
        feed_xfer = getattr(self, "_feed_xfer_if_owned", None)
        if callable(feed_xfer) and feed_xfer(data):
            return
        previous = self._display_context
        self._display_context = self._background_display_opts(s)
        self._display_context["proto_hl_on"] = False
        try:
            try:
                self._on_data_received_impl(data, source=reply_target)
            except (RuntimeError, ValueError, TypeError, OSError, UnicodeError):
                self._stat_note_rx_error()
                _log.debug("background session RX failed", exc_info=True)
            units = data
            analysis = getattr(self, "_analysis_rx_units", None)
            if callable(analysis):
                try:
                    units = analysis(data, source=reply_target)
                except (RuntimeError, ValueError, TypeError):
                    _log.debug("background session frame assemble failed",
                               exc_info=True)
                    units = [bytes(data)]
            # Keep the owning tab's display/codec context while its pinned
            # engines process RX.  Some engine paths send replies immediately;
            # restoring the visible tab here would format those replies with
            # another session's options.
            feed_engines = getattr(self, "_feed_session_engines", None)
            if callable(feed_engines):
                try:
                    feed_engines(data, reply_target=reply_target,
                                 analysis_units=units)
                except (RuntimeError, ValueError, TypeError, OSError):
                    _log.debug(
                        "background session engine feed failed", exc_info=True)
            trg = getattr(self, "_triggers_feed", None)
            if callable(trg):
                try:
                    self._rx_side(
                        "automation.triggers.feed",
                        lambda: trg(data, "rx", source=reply_target))
                except (RuntimeError, ValueError, TypeError, OSError):
                    _log.debug(
                        "background session trigger feed failed", exc_info=True)
        finally:
            self._display_context = previous

    def _route_session_error(self, session_id, msg):
        s = self.find_session(session_id)
        if s is None:
            return
        active = s.id == self._active_session_id
        with self._with_session(s):
            self._on_conn_error(msg, update_ui=active)
        self._refresh_session_tab_styles()

    def _route_session_state(self, session_id, opened):
        s = self.find_session(session_id)
        if s is None:
            return
        with self._with_session(s):
            # Only drive full UI state changes when this is the active session
            if s.id == self._active_session_id:
                self._on_conn_state_changed(opened)
            else:
                if opened:
                    s._conn_engaged = True
                    s._reconnect_attempts = 0
                    if s._reconnect_timer.isActive():
                        s._reconnect_timer.stop()
                    # Keep the Modbus master pinned to its owning background
                    # tab alive after reconnect, without applying active-tab
                    # UI state changes.
                    # Keep this session's Modbus master alive after reconnect.
                    resume = getattr(self, "_mbm_resume_after_link_up", None)
                    if callable(resume):
                        resume()
                    elif getattr(s, "_mbm_enabled", False):
                        self._mbm_restart()
                elif s.conn is not None:
                    # Background drop: tear down without stealing sidebar
                    self.close_conn(
                        update_ui=False, preserve_session_intent=True)
                    if not s._user_closing:
                        self._schedule_reconnect()
        self._refresh_session_tab_styles()

    def _route_session_clients(self, session_id, clients):
        s = self.find_session(session_id)
        if s is None:
            return
        s.clients = list(clients or [])
        if s.id != self._active_session_id:
            active = {key for key, _label in s.clients}
            if (s.send_target not in (None, "__all__")
                    and s.send_target not in active):
                s.send_target = "__all__"
            with self._with_session(s):
                self._numview_carries = {
                    key: value for key, value in self._numview_carries.items()
                    if key in active}
                self._rx_decode_buffers = {
                    key: value for key, value in self._rx_decode_buffers.items()
                    if key in active}
                self._inc_decoders = {
                    key: value for key, value in self._inc_decoders.items()
                    if key in active}
                self._ansi_states = {
                    key: value for key, value in self._ansi_states.items()
                    if key in active}
                self._ansi_pendings = {
                    key: value for key, value in self._ansi_pendings.items()
                    if key in active}
                self._term_streams = {
                    key: value for key, value in self._term_streams.items()
                    if key in active}
                drop = getattr(self, "_drop_stale_tcp_client_framers", None)
                if callable(drop):
                    drop(active)
                if (self._rx_pending_cr
                        and self._rx_pending_cr_source not in active):
                    self._rx_pending_cr = False
                    self._rx_pending_cr_source = None
            return
        with self._with_session(s):
            self._on_clients_changed(clients)
        if hasattr(self, "cb_target") and self.cb_target.count() > 0:
            s.send_target = self.cb_target.currentData()

    def _route_session_peer(self, session_id, ip, port):
        s = self.find_session(session_id)
        if s is None:
            return
        s.udp_peer = (ip, port)
        if s.id != self._active_session_id:
            return
        with self._with_session(s):
            self._on_udp_peer_changed(ip, port)

    # ---- Reconnect per session ----
    def _try_reconnect_for(self, session_id):
        s = self.find_session(session_id)
        if s is None:
            return
        with self._with_session(s):
            # If reconnecting a background session, open_conn must use
            # session's stashed cfg, not necessarily current UI.
            self._try_reconnect()
        self._refresh_session_tab_styles()

    def _ar_flush_for(self, session_id):
        """Run a silence-gap flush in the session that armed its timer."""
        s = self.find_session(session_id)
        if s is None:
            return
        with self._with_session(s):
            self._ar_flush()
        if s.id == self._active_session_id:
            self._sync_open_button_from_session(s)

    def _cancel_session_reconnect(self, session=None):
        s = session or self._session_ctx()
        if s is not None and s._reconnect_timer.isActive():
            s._reconnect_timer.stop()

    # ---- Persist ----
    def _save_sessions_settings(self):
        if not hasattr(self, "settings"):
            return
        # Snapshot active UI into active session first
        cur = self.active_session()
        if cur is not None:
            self._save_ui_into_session(cur)
        payload = [s.to_persist() for s in self._sessions]
        self.settings.setValue("sessions_v1", json.dumps(payload, ensure_ascii=False))
        self.settings.setValue("active_session_id", self._active_session_id or "")

    def _install_fresh_session_runtime(self, retain_old=False):
        """Replace current tabs with one closed session; optionally retain them for rollback."""
        cur = self.active_session()
        if retain_old and cur is not None:
            self._save_ui_into_session(cur)
        old_sessions = list(self._sessions)
        old_active_id = self._active_session_id
        old_intents = {
            session.id: {
                "period_on": bool(session.period_on),
                "log_wanted": bool(session.log_wanted),
                "mbm_enabled": bool(getattr(session, "_mbm_enabled", False)),
                "mbm_wanted": bool(getattr(session, "_mbm_wanted", False)),
                "ar_enabled": bool(getattr(session, "_ar_enabled", False)),
            }
            for session in old_sessions
        } if retain_old else {}
        self._close_all_sessions(update_active_ui=True)
        for attr in ("_search_bar", "btn_to_bottom"):
            w = getattr(self, attr, None)
            if w is not None:
                w.setParent(self)
        if self.recv_stack is not None:
            for old in old_sessions:
                if old.txt_recv is not None:
                    self.recv_stack.removeWidget(old.txt_recv)
                    if not retain_old:
                        old.txt_recv.deleteLater()
                        old.txt_recv = None
        self._txt_recv_fallback = None
        if not retain_old:
            for old in old_sessions:
                self._dispose_session_timers(old)
        self._sessions = []
        self._rx_context = None
        self._display_context = None
        fresh = Session(self, title_index=1)
        self._sessions.append(fresh)
        self._active_session_id = fresh.id
        self._ensure_session_recv_widget(fresh)
        self._txt_recv_fallback = fresh.txt_recv
        if self.recv_stack is not None and fresh.txt_recv is not None:
            self.recv_stack.setCurrentWidget(fresh.txt_recv)
            self._reparent_recv_overlays(fresh.txt_recv)
        self._rebuild_session_tabs(select_id=fresh.id)
        if retain_old:
            return {
                "sessions": old_sessions,
                "active_id": old_active_id,
                "intents": old_intents,
            }
        return None

    def _reset_sessions_runtime(self):
        """Drop the current profile's sessions and create one closed default."""
        self._install_fresh_session_runtime(retain_old=False)

    def _begin_sessions_runtime_reset(self):
        """Install a fresh tab while retaining the closed old tabs for rollback."""
        return self._install_fresh_session_runtime(retain_old=True)

    def _commit_sessions_runtime_reset(self, snapshot):
        """Permanently dispose tabs retained by _begin_sessions_runtime_reset."""
        if not isinstance(snapshot, dict):
            return
        for old in snapshot.get("sessions", ()):
            if old.txt_recv is not None:
                if self.recv_stack is not None and self.recv_stack.indexOf(old.txt_recv) >= 0:
                    self.recv_stack.removeWidget(old.txt_recv)
                old.txt_recv.deleteLater()
                old.txt_recv = None
            self._dispose_session_timers(old)

    def _rollback_sessions_runtime_reset(self, snapshot):
        """Discard the temporary fresh tab and restore retained closed tabs/views."""
        if not isinstance(snapshot, dict) or not snapshot.get("sessions"):
            return
        self._close_all_sessions(update_active_ui=True)
        for attr in ("_search_bar", "btn_to_bottom"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setParent(self)
        for current in list(self._sessions):
            if current.txt_recv is not None:
                if self.recv_stack is not None:
                    self.recv_stack.removeWidget(current.txt_recv)
                current.txt_recv.deleteLater()
                current.txt_recv = None
            self._dispose_session_timers(current)

        self._sessions = list(snapshot["sessions"])
        intents = snapshot.get("intents", {})
        for session in self._sessions:
            raw = intents.get(session.id, {})
            if isinstance(raw, dict):
                period_on = bool(raw.get("period_on", False))
                log_wanted = bool(raw.get("log_wanted", False))
                mbm_enabled = bool(raw.get("mbm_enabled", False))
                mbm_wanted = bool(raw.get("mbm_wanted", mbm_enabled))
                ar_enabled = bool(raw.get("ar_enabled", False))
            else:
                period_on = bool(raw[0]) if raw else False
                log_wanted = bool(raw[1]) if len(raw) > 1 else False
                mbm_enabled = bool(raw[2]) if len(raw) > 2 else False
                mbm_wanted = mbm_enabled
                ar_enabled = False
            session.period_on = period_on
            session.log_wanted = log_wanted
            session._mbm_enabled = mbm_enabled
            session._mbm_wanted = mbm_wanted
            session._ar_enabled = ar_enabled
            if mbm_enabled:
                bind = getattr(self, "_io_bind_owner", None)
                if callable(bind):
                    bind("modbus", session)
                restart = getattr(self, "_mbm_restart", None)
                if callable(restart):
                    with self._with_session(session):
                        restart()
        wanted = snapshot.get("active_id")
        self._active_session_id = (
            wanted if any(s.id == wanted for s in self._sessions)
            else self._sessions[0].id)
        self._rx_context = None
        self._display_context = None
        if self.recv_stack is not None:
            for session in self._sessions:
                if session.txt_recv is not None and self.recv_stack.indexOf(session.txt_recv) < 0:
                    self.recv_stack.addWidget(session.txt_recv)
        target = self.active_session()
        self._txt_recv_fallback = target.txt_recv
        self._rebuild_session_tabs(select_id=target.id)
        self._load_session_into_ui(target)
        self._ar_on = bool(getattr(target, "_ar_enabled", False))
        self._mbm_on = bool(getattr(target, "_mbm_enabled", False))
        sync_ar = getattr(self, "_sync_autoreply_ui", None)
        if callable(sync_ar):
            sync_ar()
        if self.recv_stack is not None and target.txt_recv is not None:
            self.recv_stack.setCurrentWidget(target.txt_recv)
        self._restore_session_network_ui(target)
        self._reparent_recv_overlays(target.txt_recv)
        self._refresh_stat_labels()
        self._sync_open_button_from_session(target)
        if hasattr(self, "_schedule_keyword_rebuild"):
            self._schedule_keyword_rebuild()

    def _restore_sessions_settings(self):
        """Replace tabs from settings without auto-opening connections."""
        if not hasattr(self, "settings"):
            return
        raw = self.settings.value("sessions_v1", "")
        if not raw:
            return
        try:
            payload = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            _log.debug("sessions_v1 JSON parse failed", exc_info=True)
            return
        if not isinstance(payload, list) or not payload:
            return
        items = [dict(item) for item in payload if isinstance(item, dict)]
        if not items:
            return
        self._reset_sessions_runtime()
        seen_ids = set()
        used_title_indices = set()
        restored = []
        for item in items:
            raw_id = item.get("id")
            sid = str(raw_id).strip() if isinstance(raw_id, (str, int)) else ""
            while not sid or sid in seen_ids:
                sid = new_session_id()
            item["id"] = sid
            if not restored:
                session = self._sessions[0]
                session.load_persist(item)
                self._active_session_id = session.id
                if session.txt_recv is not None:
                    session.txt_recv.setProperty("session_id", session.id)
            else:
                session = self.add_session(activate=False, persist_data=item)
                if session is None:
                    break
            if session.title_index is not None:
                idx = int(session.title_index)
                if idx < 1 or idx in used_title_indices:
                    idx = max([1] + list(used_title_indices)) + 1
                    session.title_index = idx
                    session.title = format_default_title(self, idx)
                used_title_indices.add(idx)
            seen_ids.add(session.id)
            restored.append(session)
            if len(restored) >= MAX_SESSIONS:
                break
        want = str(self.settings.value("active_session_id", "") or "")
        if want and self.find_session(want):
            self._active_session_id = want
        restore_log = getattr(self, "_restore_session_log_intent", None)
        if callable(restore_log):
            for session in restored:
                restore_log(session)
        self._rebuild_session_tabs(select_id=self._active_session_id)
        self._load_session_into_ui(self.active_session())
        if self.recv_stack is not None:
            te = self.active_session().txt_recv
            if te is not None:
                self.recv_stack.setCurrentWidget(te)
                self._reparent_recv_overlays(te)
        reconcile = getattr(self, "_io_reconcile_session_owners", None)
        if callable(reconcile):
            reconcile()

    def _close_all_sessions(self, update_active_ui=False):
        """Window shutdown: disconnect every session."""
        active_id = self._active_session_id
        for s in list(self._sessions):
            s._user_closing = True
            if s._reconnect_timer.isActive():
                s._reconnect_timer.stop()
            if s._ar_gap_timer.isActive():
                s._ar_gap_timer.stop()
            if s._period_timer.isActive():
                s._period_timer.stop()
            if s._reset_timer.isActive():
                s._reset_timer.stop()
            ms_timer = getattr(s, "_ms_cycle_timer", None)
            if ms_timer is not None and ms_timer.isActive():
                ms_timer.stop()
            s._ms_cycle_seq = []
            s._ms_cycle_idx = 0
            seq_timer = getattr(s, "_seq_timer", None)
            if seq_timer is not None and seq_timer.isActive():
                seq_timer.stop()
            for name in ("_mbm_sched", "_mbm_to"):
                timer = getattr(s, name, None)
                if timer is not None and timer.isActive():
                    timer.stop()
            s._mbm_enabled = False
            s._mbm_inflight = None
            s.period_on = False
            with self._with_session(s):
                update_ui = bool(update_active_ui and s.id == active_id)
                if s.conn is not None or update_ui:
                    self.close_conn(update_ui=update_ui)
                elif getattr(s, "_seq_on", False):
                    # No conn / no UI path — still abort so _seq_timer cannot fire
                    # after the session is torn down.
                    abort = getattr(self, "_seq_abort", None)
                    if callable(abort):
                        abort("seq_aborted_disc")
                if s._log_file is not None:
                    try:
                        self._close_log_file(session=s, toast=False)
                    except (OSError, RuntimeError, TypeError):
                        _log.debug("shutdown log close failed", exc_info=True)
                s.log_wanted = False
            s._user_closing = False
