# -*- coding: utf-8 -*-
"""Session manager mixin for CommTool - multi-tab concurrent sessions (v1.5)."""
from __future__ import annotations

import json
import logging

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QTabBar, QHBoxLayout, QPushButton, QWidget, QLabel,
)

from session import Session, MAX_SESSIONS, next_default_title
from theme import chrome_for
from ui_icons import close_icon, plus_icon, status_dot_icon
from ui_tips import set_tooltip

_log = logging.getLogger("commtool.session")

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
    "_freeze_view",
    "_last_recv_time", "_last_direction", "_pending_line_break",
    "_rx_decode_buffer", "_rx_decode_buffers",
    "_rx_pending_cr", "_rx_pending_cr_source",
    "_inc_decoder", "_inc_decoders", "_txt_ends_with_nl",
    "_numview_carries",
    "_ansi_state", "_ansi_pending", "_ansi_states", "_ansi_pendings",
    "_term_pos", "_term_sgr", "_term_esc", "_term_discard_csi",
    "_term_discard_osc", "_term_osc_prev_esc", "_term_streams",
    "_ar_gap_timer",
    "_bookmarks", "_bookmark_idx", "_recv_highlight_line",
)


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

            return property(getter, setter)

        setattr(cls, name, _make(name))

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
            # Allow early __init__ / tests to assign a timer double.
            self.__dict__["_reconnect_timer_override"] = value
            self._reconnect_timer_fallback = value

        cls._reconnect_timer = property(_rt_get, _rt_set)


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
        s = Session(self, title="Session")
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
            if s.is_open():
                marker = status_dot_icon("#34C759", 12)
            else:
                marker = status_dot_icon(
                    "#FFFFFF" if selected else c["text_sec"], 12)
            bar.setTabText(i, label)
            bar.setTabIcon(i, marker)
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
            s = Session(self, title=next_default_title())
        self._sessions.append(s)
        self._ensure_session_recv_widget(s)
        if self._session_tab_bar is not None:
            self._rebuild_session_tabs(
                select_id=s.id if activate else self._active_session_id)
        if activate:
            self.switch_session(s.id)
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

    def _on_session_tab_close(self, index):
        bar = self._session_tab_bar
        if bar is None or len(self._sessions) <= 1:
            return
        sid = bar.tabData(index)
        self.close_session(sid)

    def _ensure_session_recv_widget(self, session):
        te = session.ensure_recv_widget(getattr(self, "_recv_font_size", 10))
        te.setProperty("tr_tooltip", "sel_chk_hint")
        set_tooltip(te, self._t("sel_chk_hint"))
        te.setContextMenuPolicy(Qt.PreventContextMenu)
        te.viewport().installEventFilter(self)
        te.installEventFilter(self)
        if hasattr(self, "_sel_chk_timer"):
            te.selectionChanged.connect(self._sel_chk_timer.start)
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
        """Block leaving active session for exclusive I/O tasks only.

        Periodic send pauses on switch. Multi-send stays exclusive because its
        sequence/timer is window-owned and cannot safely migrate to another conn.
        """
        return bool(self._io_task_busy(exclude=("periodic",)))

    def close_session(self, session_id):
        if len(self._sessions) <= 1:
            return False
        s = self.find_session(session_id)
        if s is None:
            return False
        # Busy: cannot close/switch away from the busy active session's work
        if s.id == self._active_session_id and self._session_exclusive_busy():
            self.toast(self._t("session_busy"))
            return False
        if s.is_open() and hasattr(self, "_confirm_dlg"):
            if not self._confirm_dlg(
                    self._t("session_close"),
                    self._t("session_close_confirm"),
                    danger=True):
                return False
        was_active = s.id == self._active_session_id
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
        # Floating receive controls are children of the active QTextEdit. Move
        # them out before deleting that view or their C++ objects die with it.
        if was_active:
            for attr in ("_search_bar", "btn_to_bottom"):
                widget = getattr(self, attr, None)
                if widget is not None:
                    widget.setParent(self)
        # Remove recv widget
        if self.recv_stack is not None and s.txt_recv is not None:
            self.recv_stack.removeWidget(s.txt_recv)
            s.txt_recv.deleteLater()
            s.txt_recv = None
        self._sessions = [x for x in self._sessions if x.id != s.id]
        self._dispose_session_timers(s)
        if was_active:
            self._active_session_id = self._sessions[0].id
        self._rebuild_session_tabs(select_id=self._active_session_id)
        if was_active:
            target = self.active_session()
            self._load_session_into_ui(target)
            if self.recv_stack is not None and target.txt_recv is not None:
                self.recv_stack.setCurrentWidget(target.txt_recv)
            self._restore_session_network_ui(target)
            self._reparent_recv_overlays(target.txt_recv)
            self._refresh_stat_labels()
            if hasattr(self, "_schedule_keyword_rebuild"):
                self._schedule_keyword_rebuild()
            if hasattr(self, "_search_matches"):
                self._search_matches = []
                self._search_idx = -1
                if hasattr(self, "lbl_search_cnt"):
                    self.lbl_search_cnt.setText("")
        return True

    def switch_session(self, session_id):
        if session_id == self._active_session_id:
            return True
        target = self.find_session(session_id)
        if target is None:
            return False
        cur = self.active_session()
        # Block leaving a busy session
        if cur is not None and self._session_exclusive_busy():
            self.toast(self._t("session_busy"))
            # Snap tab bar back
            self._rebuild_session_tabs(select_id=self._active_session_id)
            return False
        self._switching_session = True
        try:
            if cur is not None:
                self._save_ui_into_session(cur)
                # Leaving session: release live log handle (one file globally).
                if hasattr(self, "sw_log_file") and self.sw_log_file.isChecked():
                    cur.log_wanted = True
                    self.sw_log_file.blockSignals(True)
                    self.sw_log_file.setChecked(False)
                    self.sw_log_file.blockSignals(False)
                    try:
                        self._close_log_file()
                    except Exception:
                        pass
            # Trigger decoding is window-owned. A partial character/tail from
            # the old tab must never become the prefix of the new tab's data.
            if hasattr(self, "_reset_trigger_decoders"):
                self._reset_trigger_decoders()
            self._active_session_id = target.id
            self._load_session_into_ui(target)
            if self.recv_stack is not None and target.txt_recv is not None:
                self.recv_stack.setCurrentWidget(target.txt_recv)
            self._restore_session_network_ui(target)
            self._reparent_recv_overlays(target.txt_recv)
            self._rebuild_session_tabs(select_id=target.id)
            self._refresh_stat_labels()
            self._sync_open_button_from_session(target)
            if hasattr(self, "_schedule_keyword_rebuild"):
                self._schedule_keyword_rebuild()
            # Search hits are document-bound; drop them on switch.
            if hasattr(self, "_search_matches"):
                self._search_matches = []
                self._search_idx = -1
                if hasattr(self, "lbl_search_cnt"):
                    self.lbl_search_cnt.setText("")
        finally:
            self._switching_session = False
        return True

    @staticmethod
    def _dispose_session_timers(session):
        """Destroy Qt timers when a session permanently leaves the host."""
        for name in ("_reconnect_timer", "_ar_gap_timer"):
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
            with self._with_session(session):
                self._on_clients_changed(list(session.clients or []))
        else:
            self.cb_target.clear()
        peer = getattr(session, "udp_peer", None) if session is not None else None
        if peer and session.id == self._active_session_id:
            with self._with_session(session):
                self._on_udp_peer_changed(peer[0], peer[1])

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
            except Exception:
                pass
        if hasattr(self, "_reposition_search_bar"):
            try:
                self._reposition_search_bar()
            except Exception:
                pass

    def _save_ui_into_session(self, session):
        if session is None:
            return
        try:
            session.conn_fields = self._capture_connection_fields()
        except Exception:
            _log.debug("capture conn fields failed", exc_info=True)
        if hasattr(self, "txt_send"):
            session.send_draft = self.txt_send.toPlainText()
        if hasattr(self, "ed_period_ms"):
            session.period_ms = self.ed_period_ms.text()
        if hasattr(self, "sw_period"):
            session.period_on = bool(self.sw_period.isChecked())
        # Display / send options snapshot (best-effort)
        opts = {}
        for attr, key in (
            ("sw_tx_hex", "tx_hex"),
            ("sw_append_newline", "append_nl_on"),
            ("cb_append_nl", "append_nl"),
            ("cb_checksum", "checksum"),
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
        })
        session.display_opts = opts
        if hasattr(self, "sw_log_file"):
            session.log_wanted = bool(self.sw_log_file.isChecked())
            session.log_base_path = getattr(self, "_log_base_path", "") or ""
            session.log_seg = int(getattr(self, "_log_seg", 0) or 0)

    def _load_session_into_ui(self, session):
        if session is None:
            return
        self._switching_session = True
        try:
            if session.conn_fields:
                self._apply_connection_fields(session.conn_fields)
            if hasattr(self, "txt_send"):
                self.txt_send.setPlainText(session.send_draft or "")
            if hasattr(self, "ed_period_ms") and session.period_ms:
                self.ed_period_ms.setText(str(session.period_ms))
            self._restore_session_periodic(session)
            opts = session.display_opts or {}
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
                if w is not None and hasattr(w, "setCurrentText"):
                    w.blockSignals(True)
                    w.setCurrentText(str(opts[key]))
                    w.blockSignals(False)
            if "line_nl" in opts and hasattr(self, "cb_line_nl"):
                self.cb_line_nl.blockSignals(True)
                self.cb_line_nl.setCurrentIndex(int(opts["line_nl"]))
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
            if hasattr(self, "_refresh_hex_toggle_state"):
                self._refresh_hex_toggle_state()
            # Live log is window-global (one file): restore per-session intent without
            # re-opening the file dialog (on_log_file_toggled would prompt).
            if hasattr(self, "sw_log_file"):
                want = bool(getattr(session, "log_wanted", False))
                base = getattr(session, "log_base_path", "") or ""
                if want and base and hasattr(self, "_open_log_segment"):
                    self._log_base_path = base
                    self._log_seg = int(getattr(session, "log_seg", 0) or 0)
                    self._log_limit = self._parse_log_limit(
                        self.cb_log_split.currentText()) if hasattr(self, "cb_log_split") else 0
                    from datetime import datetime
                    now = datetime.now()
                    real = self._log_segment_path(now)
                    ok = False
                    try:
                        ok = bool(self._open_log_segment(real, when=now))
                    except Exception:
                        _log.debug("restore log failed", exc_info=True)
                    self.sw_log_file.blockSignals(True)
                    self.sw_log_file.setChecked(ok)
                    self.sw_log_file.blockSignals(False)
                    if not ok:
                        session.log_wanted = False
                else:
                    self.sw_log_file.blockSignals(True)
                    self.sw_log_file.setChecked(False)
                    self.sw_log_file.blockSignals(False)
                    if getattr(self, "_log_file", None):
                        try:
                            self._close_log_file()
                        except Exception:
                            pass
            self._sync_open_button_from_session(session)
            if session.is_open():
                self.set_settings_enabled(False)
            else:
                self.set_settings_enabled(True)
            self._update_net_fields()
        finally:
            self._switching_session = False

    def _restore_session_periodic(self, session):
        """Apply one session's periodic-send intent to the window-owned timer."""
        if not hasattr(self, "sw_period"):
            return
        if self.send_timer.isActive():
            self.send_timer.stop()
        want = bool(session and session.period_on and session.is_open())
        self.sw_period.blockSignals(True)
        self.sw_period.setChecked(want)
        self.sw_period.blockSignals(False)
        if want:
            try:
                raw_ms = (session.period_ms if session and session.period_ms
                          else self.ed_period_ms.text())
                ms = max(10, int(raw_ms or "1000"))
            except ValueError:
                ms = 1000
            self.send_timer.start(ms)

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
            except Exception:
                pass

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
        }
        return self._session_resource_key_from_open(proto, fields)

    def _session_resource_key(self, session):
        if session is None or not session.is_open():
            return None
        proto = session._conn_proto
        cfg = session._conn_cfg
        if proto == "Serial" and cfg and len(cfg) > 1:
            return ("serial", str(cfg[1]).upper())
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
        if hasattr(conn, "data_received_from"):
            conn.data_received_from.connect(
                lambda data, target=None, _sid=sid: self._route_session_data(_sid, data, target))
        else:
            conn.data_received.connect(
                lambda data, _sid=sid: self._route_session_data(_sid, data, None))
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

    def _route_session_data(self, session_id, data, reply_target=None):
        s = self.find_session(session_id)
        if s is None:
            return
        with self._with_session(s):
            if s.id == self._active_session_id:
                self.on_data_received(data, reply_target)
            else:
                # Background tabs: update that session's RX view/stats only.
                # Never feed window-level xfer/script/seq/Modbus/AR/macro/recorder.
                self._on_background_session_data(data, reply_target)

    def _on_background_session_data(self, data, reply_target=None):
        """Render with the owning session's options, without feeding tools."""
        s = self._session_ctx()
        if s is None:
            return
        previous = self._display_context
        self._display_context = dict(s.display_opts or {})
        self._display_context["proto_hl_on"] = False
        self._display_context["background"] = True
        try:
            self._on_data_received_impl(data, source=reply_target)
        except Exception:
            self._stat_note_rx_error()
            _log.debug("background session RX failed", exc_info=True)
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
                elif s.conn is not None:
                    # Background drop: tear down without stealing sidebar
                    self.close_conn(update_ui=False)
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
                if (self._rx_pending_cr
                        and self._rx_pending_cr_source not in active):
                    self._rx_pending_cr = False
                    self._rx_pending_cr_source = None
            return
        with self._with_session(s):
            self._on_clients_changed(clients)

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

    def _reset_sessions_runtime(self):
        """Drop the current profile's sessions and create one closed default."""
        self._close_all_sessions(update_active_ui=True)
        for attr in ("_search_bar", "btn_to_bottom"):
            w = getattr(self, attr, None)
            if w is not None:
                w.setParent(self)
        if self.recv_stack is not None:
            for old in list(self._sessions):
                if old.txt_recv is not None:
                    self.recv_stack.removeWidget(old.txt_recv)
                    old.txt_recv.deleteLater()
                    old.txt_recv = None
        for old in self._sessions:
            self._dispose_session_timers(old)
        self._sessions = []
        self._rx_context = None
        self._display_context = None
        fresh = Session(self, title="Session")
        self._sessions.append(fresh)
        self._active_session_id = fresh.id
        self._ensure_session_recv_widget(fresh)
        if self.recv_stack is not None and fresh.txt_recv is not None:
            self.recv_stack.setCurrentWidget(fresh.txt_recv)
            self._reparent_recv_overlays(fresh.txt_recv)
        self._rebuild_session_tabs(select_id=fresh.id)

    def _restore_sessions_settings(self):
        """Replace tabs from settings without auto-opening connections."""
        if not hasattr(self, "settings"):
            return
        raw = self.settings.value("sessions_v1", "")
        if not raw:
            return
        try:
            payload = json.loads(str(raw))
        except Exception:
            return
        if not isinstance(payload, list) or not payload:
            return
        self._reset_sessions_runtime()
        first = payload[0]
        s0 = self._sessions[0]
        s0.conn_fields = dict(first.get("conn_fields") or {})
        s0.send_draft = first.get("send_draft") or ""
        s0.period_ms = first.get("period_ms") or "1000"
        s0.period_on = bool(first.get("period_on", False))
        s0.display_opts = dict(first.get("display_opts") or {})
        s0._freeze_view = bool(s0.display_opts.get("freeze_view", False))
        s0.log_wanted = bool(first.get("log_wanted", False))
        s0.log_base_path = first.get("log_base_path") or ""
        try:
            s0.log_seg = max(0, int(first.get("log_seg", 0) or 0))
        except (TypeError, ValueError):
            s0.log_seg = 0
        if first.get("title"):
            s0.title = first["title"]
        if first.get("id"):
            s0.id = first["id"]
            self._active_session_id = s0.id
            if s0.txt_recv is not None:
                s0.txt_recv.setProperty("session_id", s0.id)
        for item in payload[1:MAX_SESSIONS]:
            self.add_session(activate=False, persist_data=item)
        want = str(self.settings.value("active_session_id", "") or "")
        if want and self.find_session(want):
            self._active_session_id = want
        self._rebuild_session_tabs(select_id=self._active_session_id)
        self._load_session_into_ui(self.active_session())
        if self.recv_stack is not None:
            te = self.active_session().txt_recv
            if te is not None:
                self.recv_stack.setCurrentWidget(te)
                self._reparent_recv_overlays(te)

    def _close_all_sessions(self, update_active_ui=False):
        """Window shutdown: disconnect every session."""
        active_id = self._active_session_id
        for s in list(self._sessions):
            s._user_closing = True
            if s._reconnect_timer.isActive():
                s._reconnect_timer.stop()
            if s._ar_gap_timer.isActive():
                s._ar_gap_timer.stop()
            with self._with_session(s):
                update_ui = bool(update_active_ui and s.id == active_id)
                if s.conn is not None or update_ui:
                    self.close_conn(update_ui=update_ui)
            s._user_closing = False
