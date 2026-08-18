# -*- coding: utf-8 -*-
"""数据录制 / 回放对话框 RecReplayDialog。

录制：把当前连接上的原始收发流按时序录下来，存成 .ctrec（JSON Lines，可读可手改）。
回放两种模式：
  - 默认：注入 VirtualConn.inject（RX），未连虚拟连接会明确拒绝；
  - 驱动真实 TX：经当前打开连接原样发出录制的 TX（危险确认，非默认）。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QCheckBox, QFileDialog, QProgressBar,
                             QPlainTextEdit, QLineEdit, QScrollArea, QFrame)

from record import rec_replay
from record import pcap_export
from ui.theme import chrome_for
from ui.fonts import localize_qss, mono_font
from ui.dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from ui.ui_tips import set_tooltip

_SPEEDS = [("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("5x", 5.0), ("最快", 1000.0)]
_TICK_MS = 20                # 回放派发间隔；20ms 足够贴合原时序又不吃 CPU
_MAX_LOG_BLOCKS = 2000


class RecReplayDialog(QDialog):
    def __init__(self, app):
        # parent=None：避免干扰主窗 WM_NCHITTEST（同其它工具对话框）。主窗 _shutdown 显式收。
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(560, 380)
        self.resize(760, 480)

        self._events = []            # 已载入/已录制的事件，供回放
        self._src_name = ""          # 数据来源描述（文件名 / 「本次录制」）
        self._player = None
        self._link = None            # TCP/UDP 端点快照（PCAP 导出用）
        self._wall_t0 = None         # 录制墙钟锚点（写入 pcap 时间戳）

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ===== 录制行 =====
        rec = QHBoxLayout()
        rec.setSpacing(8)
        self.lbl_rec = QLabel()
        self.btn_rec = QPushButton()
        self.btn_rec.setObjectName("PlotGhostBtn")
        self.btn_rec.clicked.connect(self._on_rec)
        self.lbl_rec_stat = QLabel()
        self.lbl_rec_stat.setObjectName("MsHint")
        self.btn_save = QPushButton()
        self.btn_save.setObjectName("PlotGhostBtn")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_pcap = QPushButton()
        self.btn_pcap.setObjectName("PlotGhostBtn")
        self.btn_pcap.clicked.connect(self._on_export_pcap)
        rec.addWidget(self.lbl_rec)
        rec.addWidget(self.btn_rec)
        rec.addWidget(self.lbl_rec_stat, 1)
        rec.addWidget(self.btn_save)
        rec.addWidget(self.btn_pcap)
        root.addLayout(rec)

        # ===== 回放行 =====
        rep = QHBoxLayout()
        rep.setSpacing(8)
        self.lbl_rep = QLabel()
        self.btn_load = QPushButton()
        self.btn_load.setObjectName("PlotGhostBtn")
        self.btn_load.clicked.connect(self._on_load)
        self.lbl_speed = QLabel()
        self.cb_speed = QComboBox()
        self.cb_speed.setFocusPolicy(Qt.NoFocus)
        self.cb_speed.setFixedHeight(28)
        for name, _v in _SPEEDS:
            self.cb_speed.addItem(name)
        self.cb_speed.setCurrentIndex(1)          # 默认 1x
        self.chk_loop = QCheckBox()
        self.btn_pause = QPushButton()
        self.btn_pause.setObjectName("PlotGhostBtn")
        self.btn_pause.setFixedHeight(28)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_step = QPushButton()
        self.btn_step.setObjectName("PlotGhostBtn")
        self.btn_step.setFixedHeight(28)
        self.btn_step.clicked.connect(self._on_step)
        self.ed_seek = QLineEdit("0")
        self.ed_seek.setFixedWidth(64)
        self.btn_seek = QPushButton()
        self.btn_seek.setObjectName("PlotGhostBtn")
        self.btn_seek.setFixedHeight(28)
        self.btn_seek.clicked.connect(self._on_seek)
        self.chk_tx = QCheckBox()
        self.chk_drive_tx = QCheckBox()
        self.chk_drive_tx.toggled.connect(self._on_drive_tx_toggled)
        self.btn_play = QPushButton()
        self.btn_play.setObjectName("PlotPrimaryBtn")
        self.btn_play.setMinimumSize(68, 34)
        self.btn_play.clicked.connect(self._on_play)
        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("PlotDangerBtn")
        self.btn_stop.setMinimumSize(68, 34)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setVisible(False)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("PlotHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help_dlg)
        rep.addWidget(self.lbl_rep)
        rep.addWidget(self.btn_load)
        rep.addWidget(self.lbl_speed)
        rep.addWidget(self.cb_speed)
        rep.addWidget(self.chk_loop)
        rep.addWidget(self.btn_pause)
        rep.addWidget(self.btn_step)
        rep.addWidget(self.ed_seek)
        rep.addWidget(self.btn_seek)
        rep.addWidget(self.chk_tx)
        rep.addWidget(self.chk_drive_tx)
        rep.addStretch(1)
        rep.addWidget(self.btn_play)
        rep.addWidget(self.btn_stop)
        rep.addWidget(self.btn_help)
        root.addLayout(rep)

        self.bar = QProgressBar()
        self.bar.setObjectName("RrBar")
        self.bar.setTextVisible(True)
        self.bar.setRange(0, 100)
        root.addWidget(self.bar)

        self.txt_info = QPlainTextEdit()
        self.txt_info.setObjectName("RrInfo")
        self.txt_info.setReadOnly(True)
        self.txt_info.setFont(mono_font(11))
        self.txt_info.document().setMaximumBlockCount(_MAX_LOG_BLOCKS)
        root.addWidget(self.txt_info, 1)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("MsHint")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

        self.retranslate()
        self.refresh_theme()
        self._refresh_stat()

    def _visible_session(self):
        finder = getattr(self.app, "active_session", None)
        return finder() if callable(finder) else None

    def sync_session(self):
        """Bind Play/Stop/progress and capture events to the visible tab."""
        session = self._visible_session()
        self._apply_rr_capture(session)
        self._player = getattr(session, "_replay_player", None) if session else None
        playing = self.is_playing()
        self._set_playing_ui(playing)
        if playing and self._player is not None:
            self.bar.setValue(int(self._player.progress * 100))
        else:
            self.bar.setValue(0)
        self._refresh_stat()
        if self._any_player():
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()

    def _apply_rr_capture(self, session):
        cap = getattr(session, "_rr_capture", None) if session is not None else None
        if not isinstance(cap, dict):
            self._events = []
            self._src_name = ""
            self._link = None
            self._wall_t0 = None
            return
        self._events = cap.get("events") or []
        self._src_name = cap.get("src_name") or ""
        link = cap.get("link")
        self._link = dict(link) if isinstance(link, dict) else link
        self._wall_t0 = cap.get("wall_t0")

    def _store_rr_capture(self, session=None):
        session = session or self._visible_session()
        if session is None:
            return
        session._rr_capture = {
            "events": self._events,
            "src_name": self._src_name,
            "link": dict(self._link) if isinstance(self._link, dict) else self._link,
            "wall_t0": self._wall_t0,
        }

    def _any_player(self):
        return any(getattr(s, "_replay_player", None) is not None
                   for s in getattr(self.app, "_sessions", ()) or ())

    # ---------------- 录制 ----------------
    def _on_rec(self):
        r = self.app._recorder
        if r.recording:
            self.stop_recording()
            return
        if self.app._io_task_busy():
            # 录制本身不发数据，但与主动任务并行录到的流会混入对方流量，语义不清
            self.app.toast_io_exclusive_busy()
            return
        if not self.app._is_open():
            self.app.toast(self.app._t("net_not_open"), error=True)
            return
        r.clear()
        link = None
        if hasattr(self.app, "_recorder_link_snapshot"):
            link = self.app._recorder_link_snapshot()
        r.start(link=link)
        bind = getattr(self.app, "bind_recording_owner", None)
        if callable(bind):
            bind(True)
        self._link = dict(link) if isinstance(link, dict) else None
        self._wall_t0 = None
        self._log(self.app._t("rr_rec_started"))
        self._refresh_stat()

    def stop_recording(self):
        """停止并接管本次录制，确保之后即使关闭窗口也仍可重新打开保存。"""
        r = self.app._recorder
        if not r.recording:
            return
        r.stop()
        bind = getattr(self.app, "bind_recording_owner", None)
        if callable(bind):
            bind(False)
        ctx = getattr(self.app, "_session_ctx", None)
        session = ctx() if callable(ctx) else None
        session = session or self._visible_session()
        events = r.events
        src_name = self.app._t("rr_src_live")
        link = dict(r.link) if isinstance(getattr(r, "link", None), dict) else None
        wall_t0 = getattr(r, "_wall_t0", None)
        if session is not None:
            session._rr_capture = {
                "events": events,
                "src_name": src_name,
                "link": link,
                "wall_t0": wall_t0,
            }
        if session is None or session is self._visible_session():
            self._events = events
            self._src_name = src_name
            self._link = link
            self._wall_t0 = wall_t0
            self._log(self.app._t("rr_rec_stopped", n=len(r), sec=round(r.duration, 1)))
            self._refresh_stat()

    def _on_save(self):
        if not self._events:
            self.app.toast(self.app._t("rr_nothing"), error=True)
            return
        path, _ = QFileDialog.getSaveFileName(self, self.app._t("rr_save"),
                                              "capture.ctrec",
                                              "CommTool 录制 (*.ctrec);;All Files (*)")
        if not path:
            return
        try:
            rec = rec_replay.StreamRecorder()
            rec.events = self._events
            rec._wall_t0 = self._wall_t0
            rec.link = dict(self._link) if isinstance(self._link, dict) else None
            n = rec.save(path)
            self.app.toast(self.app._t("saved_to", path=path))
            self._log(self.app._t("rr_saved", n=n))
        except Exception as e:
            self.app.toast(self.app._t("err_save_failed", e=e), error=True)

    def _on_export_pcap(self):
        if not self._events:
            self.app.toast(self.app._t("rr_nothing"), error=True)
            return
        link = self._link
        if not pcap_export.can_export_link(link):
            self.app.toast(self.app._t("rr_pcap_unsupported"), error=True)
            return
        peers = pcap_export.list_export_peers(self._events, link)
        if (str((link or {}).get("proto") or "") == "TCP Server"
                and len(peers) > 1):
            listing = "\n".join("%s:%s" % (ip, port) for ip, port in peers)
            if not self.app._confirm_dlg(
                    self.app._t("rr_pcap_peers_title"),
                    self.app._t("rr_pcap_peers_confirm",
                                n=len(peers), peers=listing),
                    danger=False):
                return
        path, _ = QFileDialog.getSaveFileName(
            self, self.app._t("rr_export_pcap"), "capture.pcap",
            "Wireshark PCAP (*.pcap);;Wireshark PCAPNG (*.pcapng);;All Files (*)")
        if not path:
            return
        try:
            n = pcap_export.export_pcap_file(
                path, self._events, link, wall_t0=self._wall_t0)
            self.app.toast(self.app._t("rr_pcap_exported", path=path, n=n))
            self._log(self.app._t("rr_pcap_exported", path=path, n=n))
        except Exception as e:
            self.app.toast(self.app._t("rr_pcap_failed", e=e), error=True)

    # ---------------- 回放 ----------------
    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(self, self.app._t("rr_load"), "",
                                              "CommTool 录制 (*.ctrec);;All Files (*)")
        if not path:
            return
        try:
            events, header = rec_replay.load(path)
        except Exception as e:
            self.app.toast(self.app._t("rr_load_bad", e=e), error=True)
            return
        if not events:
            self.app.toast(self.app._t("rr_nothing"), error=True)
            return
        self._events = events
        import os
        self._src_name = os.path.basename(path)
        self._link = dict(header["link"]) if isinstance(header.get("link"), dict) else None
        self._wall_t0 = header.get("wall_t0")
        self._store_rr_capture()
        bad = header.get("bad_lines") or 0
        self._log(self.app._t("rr_loaded", name=self._src_name, n=len(events)))
        if bad:
            self._log(self.app._t("rr_load_skipped", n=bad))
        self._refresh_stat()

    def is_playing(self):
        p = self._player
        return p is not None and not p.finished

    def _on_drive_tx_toggled(self, on):
        # Drive-TX ignores Virtual inject-TX; keep the old checkbox for inject mode only.
        self.chk_tx.setEnabled(not bool(on))
        if on:
            self.chk_tx.setChecked(False)

    def _on_play(self):
        if self.is_playing():
            return
        if not self._events:
            self.app.toast(self.app._t("rr_nothing"), error=True)
            return
        if self.app._io_task_busy():
            self.app.toast_io_exclusive_busy()
            return
        drive_tx = bool(self.chk_drive_tx.isChecked())
        speed = _SPEEDS[max(0, self.cb_speed.currentIndex())][1]
        if drive_tx:
            if self.app._replay_send_target() is None:
                self.app.toast(self.app._t("rr_need_open_conn"), error=True)
                return
            tx_n = sum(1 for _t, d, _b in self._events if d == "tx")
            if tx_n <= 0:
                self.app.toast(self.app._t("rr_no_tx"), error=True)
                return
            conn_label = self.app._replay_conn_summary()
            tx_dur = 0.0
            for t_rel, d, _b in self._events:
                if d == "tx":
                    tx_dur = float(t_rel)
            loop_on = bool(self.chk_loop.isChecked())
            ok = self.app._confirm_dlg(
                self.app._t("rr_drive_tx_confirm_title"),
                self.app._t("rr_drive_tx_confirm",
                            n=tx_n,
                            conn=conn_label,
                            sec=round(tx_dur, 1)),
                danger=True)
            if not ok:
                return
            # Loop / Max speed can flood hardware; require a second explicit confirm.
            if loop_on or speed >= 1000.0:
                ok2 = self.app._confirm_dlg(
                    self.app._t("rr_drive_tx_loop_title"),
                    self.app._t("rr_drive_tx_loop_confirm",
                                loop=("ON" if loop_on else "OFF"),
                                speed=("Max" if speed >= 1000.0 else ("%gx" % speed))),
                    danger=True)
                if not ok2:
                    return
            # TOCTOU: confirm dialog can block; connection may close/switch.
            send_tx = self.app._replay_send_target()
            if send_tx is None:
                self.app.toast(self.app._t("rr_need_open_conn"), error=True)
                return
            self._player = rec_replay.Player(
                self._events, None, speed=speed, loop=loop_on,
                mode="drive_tx", send_tx=send_tx)
            empty_toast = "rr_no_tx"
        else:
            inject = self.app._replay_inject_target()
            if inject is None:
                # 往真实串口/网络「注入收到的数据」物理上不成立，明确拒绝而不是假装成功
                self.app.toast(self.app._t("rr_need_virtual"), error=True)
                return
            self._player = rec_replay.Player(
                self._events, inject, speed=speed,
                include_tx=self.chk_tx.isChecked(),
                loop=self.chk_loop.isChecked())
            empty_toast = "rr_no_rx"
        if len(self._player) == 0:
            self.app.toast(self.app._t(empty_toast), error=True)
            self._player = None
            return
        import time
        self._player.start(time.monotonic())
        session = self._visible_session()
        if session is not None:
            session._replay_player = self._player
        self.app._replay_begin(drive_tx=drive_tx)
        self._set_playing_ui(True)
        self._log(self.app._t("rr_play_started", n=len(self._player),
                              sec=round(self._player.duration, 1)))
        self._timer.start()

    def _on_stop(self):
        self.stop_replay()

    def stop_replay(self, session=None):
        """停止指定（默认当前上下文）会话的回放；也供主窗在连接断开时同步清理。"""
        session = session or self.app._session_ctx() or self._visible_session()
        player = getattr(session, "_replay_player", None) if session is not None else self._player
        if player is None:
            if session is not None:
                with self.app._with_session(session):
                    self.app._replay_end()
            else:
                self.app._replay_end()
            if not self._any_player():
                self._timer.stop()
            return
        done = player.idx
        fails = int(getattr(player, "send_fail_count", 0) or 0)
        if session is not None:
            session._replay_player = None
        if self._player is player:
            self._player = None
            self._set_playing_ui(False)
        if not self._any_player():
            self._timer.stop()
        if session is not None:
            with self.app._with_session(session):
                self.app._replay_end()
        else:
            self.app._replay_end()
        self._log(self.app._t("rr_play_stopped", n=done))
        self._toast_drive_tx_fails(fails)

    def _toast_drive_tx_fails(self, fails, toast=True):
        if toast and fails > 0:
            self.app.toast(self.app._t("rr_drive_tx_fails", n=fails), error=True)

    def _tick(self):
        import time
        now = time.monotonic()
        visible = self._visible_session()
        any_live = False
        for session in list(getattr(self.app, "_sessions", ()) or ()):
            p = getattr(session, "_replay_player", None)
            if p is None:
                continue
            # drive-tx 发送失败达到阈值：暂停回放并提示。后台标签不弹 toast，
            # 但必须收尾清 _replay_on，否则该标签被判定忙且无法关闭。
            if getattr(p, "send_aborted", False) and p.paused:
                if session is visible:
                    self.retranslate()
                    fails = int(getattr(p, "send_fail_count", 0) or 0)
                    self._log(self.app._t("rr_drive_tx_paused", n=fails))
                    self.app.toast(self.app._t("rr_drive_tx_paused", n=fails), error=True)
                    p.send_aborted = False
                    # 该 player 仍处于暂停态，resume 由 _on_pause 重启定时器。
                else:
                    self._finish_player(session, p)
                continue
            p.tick(now)
            if session is visible:
                self.bar.setValue(int(p.progress * 100))
            if p.finished:
                self._finish_player(session, p)
                continue
            if p.paused:
                # 暂停的 player 不需要再 tick；resume 时由 _on_pause 重启定时器。
                continue
            any_live = True
        if not any_live:
            self._timer.stop()

    def _finish_player(self, session, p):
        n = len(p)
        fails = int(getattr(p, "send_fail_count", 0) or 0)
        aborted = bool(getattr(p, "send_aborted", False))
        visible = session is not None and session is self._visible_session()
        if session is not None:
            session._replay_player = None
        if self._player is p:
            self._player = None
            self._set_playing_ui(False)
        if session is not None:
            with self.app._with_session(session):
                self.app._replay_end()
        else:
            self.app._replay_end()
        if aborted and fails > 0:
            self._log(self.app._t("rr_drive_tx_paused", n=fails))
            if visible:
                self.app.toast(self.app._t("rr_drive_tx_paused", n=fails), error=True)
        else:
            self._log(self.app._t("rr_play_done", n=n))
            self._toast_drive_tx_fails(fails, toast=visible)

    def _on_pause(self):
        import time
        p = self._player
        if p is None:
            return
        now = time.monotonic()
        if p.paused:
            p.resume(now)
            self._timer.start()
        else:
            p.pause(now)
            if not self._any_player():
                self._timer.stop()
        self.retranslate()

    def _on_step(self):
        import time
        p = self._player
        if p is None:
            return
        now = time.monotonic()
        # 先暂停再走一格：否则 step 会在事件到点前就把它注入，并把媒体时钟
        # 前推到该事件时刻——那是「跳到下一事件」而不是单步。
        if not p.paused:
            p.pause(now)
        p.step(now)
        self.bar.setValue(int(p.progress * 100))
        if p.finished:
            self._finish_player(self._visible_session(), p)
            if not self._any_player():
                self._timer.stop()
        else:
            self.retranslate()          # 暂停按钮改显「继续」

    def _on_seek(self):
        import time
        p = self._player
        if p is None:
            return
        try:
            t_rel = float(self.ed_seek.text().strip() or "0")
        except ValueError:
            return
        p.seek(t_rel, time.monotonic())
        self.bar.setValue(int(p.progress * 100))
        if p.finished:
            self._finish_player(self._visible_session(), p)
            if not self._any_player():
                self._timer.stop()

    def _set_playing_ui(self, playing):
        self.btn_play.setVisible(not playing)
        self.btn_stop.setVisible(playing)
        self._sync_controls()
        if not playing:
            self.bar.setValue(0)

    def _sync_controls(self):
        """录制与回放互斥时同步控件；录制中仍保留停止录制按钮可用。"""
        recording = self.app._recorder.recording
        playing = self.is_playing()
        self.btn_rec.setEnabled(not playing)
        for w in (self.btn_load, self.btn_save, self.btn_pcap,
                  self.cb_speed, self.chk_loop, self.chk_tx, self.chk_drive_tx):
            w.setEnabled(not recording and not playing)
        if (not recording and not playing) and self.chk_drive_tx.isChecked():
            self.chk_tx.setEnabled(False)
        self.btn_play.setEnabled(not recording and not playing)
        # 暂停/单步/定位 只在回放中有意义（无 player 时点了也不会有反应）。
        for w in (self.btn_pause, self.btn_step, self.ed_seek, self.btn_seek):
            w.setEnabled(playing)

    # ---------------- 显示 ----------------
    def _refresh_stat(self):
        r = self.app._recorder
        if r.recording:
            self.btn_rec.setText(self.app._t("rr_rec_stop"))
            self.btn_rec.setObjectName("PlotDangerBtn")
        else:
            self.btn_rec.setText(self.app._t("rr_rec"))
            self.btn_rec.setObjectName("PlotGhostBtn")
        self._sync_controls()
        self.btn_rec.style().unpolish(self.btn_rec)
        self.btn_rec.style().polish(self.btn_rec)
        if r.recording:
            self.lbl_rec_stat.setText(self.app._t("rr_recording", n=len(r)))
        elif self._events:
            rx = sum(1 for _t, d, _b in self._events if d == "rx")
            nbytes = sum(len(b) for _t, _d, b in self._events)
            dur = self._events[-1][0] if self._events else 0
            self.lbl_rec_stat.setText(self.app._t(
                "rr_loaded_stat", name=self._src_name, n=len(self._events),
                rx=rx, bytes=nbytes, sec=round(dur, 1)))
        else:
            self.lbl_rec_stat.setText(self.app._t("rr_empty"))

    def _log(self, line):
        self.txt_info.appendPlainText(line)
        sb = self.txt_info.verticalScrollBar()
        sb.setValue(sb.maximum())

    def tick_stat(self):
        """录制中由主窗每秒调一次，刷新计数。"""
        if self.app._recorder.recording:
            self._refresh_stat()

    # ---------------- 主题 / 语言 ----------------
    def _show_help_dlg(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("rr_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(720, 480)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("rr_help"))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setAlignment(Qt.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        btn_close = QPushButton(
            {"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(self.app._lang, "Close"))
        btn_close.setObjectName("PlotGhostBtn")
        btn_close.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn_close)
        v.addLayout(row)
        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(f"""
            QDialog {{ background-color: {c['window_bg']}; }}
            QLabel {{ color: {c['text']}; background: transparent;
                      font-family: 'Segoe UI'; font-size: 12px; }}
            QScrollArea {{ background: transparent; border: 1px solid {c['separator']}; border-radius: 6px; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QPushButton#PlotGhostBtn {{
                background-color: {c['input_bg']}; color: {c['text']};
                border: 1px solid {c['separator']}; border-radius: 6px;
                font-family: 'Segoe UI'; font-size: 12px; padding: 5px 16px;
            }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        """))
        _set_win_titlebar_dark(dlg, self.app._theme().get("mode") == "dark")
        dlg.exec_()

    def refresh_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")
        c = chrome_for(self.app._theme_id())
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
        QPushButton#PlotGhostBtn {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
            font-family: 'Segoe UI'; font-size: 12px; padding: 4px 12px;
        }}
        QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#PlotPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 12px;
            font-weight: 500; padding: 4px 16px;
        }}
        QPushButton#PlotPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#PlotDangerBtn {{
            background-color: {c['danger']}; color: white; border: 0px;
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 12px;
            font-weight: 500; padding: 4px 16px;
        }}
        QPushButton#PlotDangerBtn:hover {{ background-color: {c['danger_hover']}; }}
        QPushButton#PlotHelpBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 13px;
            font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
        }}
        QPushButton#PlotHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        QPlainTextEdit#RrInfo {{
            background-color: {c['card_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
        }}
        QProgressBar#RrBar {{
            background-color: {c['input_bg']}; border: 1px solid {c['separator']};
            border-radius: 6px; height: 16px; text-align: center;
            font-family: 'Segoe UI'; font-size: 10px; color: {c['text']};
        }}
        QProgressBar#RrBar::chunk {{ background-color: {c['accent']}; border-radius: 5px; }}
        """))
        _style_combo_popups(self, c)

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("rr_title"))
        self.lbl_rec.setText(t("rr_record"))
        self.btn_save.setText(t("rr_save"))
        self.btn_pcap.setText(t("rr_export_pcap"))
        set_tooltip(self.btn_pcap, t("rr_export_pcap_tip"))
        self.lbl_rep.setText(t("rr_replay"))
        self.btn_load.setText(t("rr_load"))
        self.lbl_speed.setText(t("rr_speed"))
        self.chk_loop.setText(t("rr_loop"))
        paused = bool(self._player and getattr(self._player, "paused", False))
        self.btn_pause.setText(t("rr_resume" if paused else "rr_pause"))
        self.btn_step.setText(t("rr_step"))
        self.btn_seek.setText(t("rr_seek"))
        self.ed_seek.setPlaceholderText(t("rr_seek_ph"))
        self.chk_tx.setText(t("rr_include_tx"))
        self.chk_drive_tx.setText(t("rr_drive_tx"))
        set_tooltip(self.chk_drive_tx, t("rr_drive_tx_tip"))
        if self.chk_drive_tx.isChecked():
            self.chk_tx.setEnabled(False)
        self.btn_play.setText(t("rr_play"))
        self.btn_stop.setText(t("rr_stop"))
        set_tooltip(self.btn_help, t("rr_help_btn"))
        self.lbl_hint.setText(t("rr_hint"))
        self.cb_speed.setItemText(len(_SPEEDS) - 1, t("rr_speed_max"))
        self._refresh_stat()

    # ---------------- 生命周期 ----------------
    def closeEvent(self, e):
        # Stop the visible player first, then any remaining per-session players.
        # After stop_replay(session) the matching self._player is already None.
        if self._player is not None:
            self.stop_replay()
        for session in list(getattr(self.app, "_sessions", ()) or ()):
            if getattr(session, "_replay_player", None) is not None:
                self.stop_replay(session)
        for session in list(getattr(self.app, "_sessions", ()) or ()):
            rec = getattr(session, "_recorder", None)
            if rec is not None and rec.recording:
                with self.app._with_session(session):
                    self.stop_recording()
        super().closeEvent(e)
