# -*- coding: utf-8 -*-
"""数据录制 / 回放对话框 RecReplayDialog。

录制：把当前连接上的原始收发流按时序录下来，存成 .ctrec（JSON Lines，可读可手改）。
回放：载入 .ctrec，按原始时间间隔把 RX 注入当前连接 —— 无硬件复现问题、离线调试。

回放落点是 VirtualConn.inject（虚拟连接），因为往真实串口/网络「注入收到的数据」在
物理上不成立。未连虚拟连接时会明确提示，而不是假装成功。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QCheckBox, QFileDialog, QProgressBar,
                             QPlainTextEdit, QLineEdit, QScrollArea, QFrame)

import rec_replay
from theme import chrome_for
from fonts import localize_qss, mono_font
from dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from ui_tips import set_tooltip

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
        rec.addWidget(self.lbl_rec)
        rec.addWidget(self.btn_rec)
        rec.addWidget(self.lbl_rec_stat, 1)
        rec.addWidget(self.btn_save)
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
        r.start()
        self._log(self.app._t("rr_rec_started"))
        self._refresh_stat()

    def stop_recording(self):
        """停止并接管本次录制，确保之后即使关闭窗口也仍可重新打开保存。"""
        r = self.app._recorder
        if not r.recording:
            return
        r.stop()
        self._events = list(r.events)
        self._src_name = self.app._t("rr_src_live")
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
            rec.events = list(self._events)
            n = rec.save(path)
            self.app.toast(self.app._t("saved_to", path=path))
            self._log(self.app._t("rr_saved", n=n))
        except Exception as e:
            self.app.toast(self.app._t("err_save_failed", e=e), error=True)

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
        bad = header.get("bad_lines") or 0
        self._log(self.app._t("rr_loaded", name=self._src_name, n=len(events)))
        if bad:
            self._log(self.app._t("rr_load_skipped", n=bad))
        self._refresh_stat()

    def is_playing(self):
        return self._player is not None and not self._player.finished

    def _on_play(self):
        if self.is_playing():
            return
        if not self._events:
            self.app.toast(self.app._t("rr_nothing"), error=True)
            return
        inject = self.app._replay_inject_target()
        if inject is None:
            # 往真实串口/网络「注入收到的数据」物理上不成立，明确拒绝而不是假装成功
            self.app.toast(self.app._t("rr_need_virtual"), error=True)
            return
        if self.app._io_task_busy():
            self.app.toast_io_exclusive_busy()
            return
        speed = _SPEEDS[max(0, self.cb_speed.currentIndex())][1]
        self._player = rec_replay.Player(self._events, inject, speed=speed,
                                         include_tx=self.chk_tx.isChecked(),
                                         loop=self.chk_loop.isChecked())
        if len(self._player) == 0:
            self.app.toast(self.app._t("rr_no_rx"), error=True)
            self._player = None
            return
        import time
        self._player.start(time.monotonic())
        self.app._replay_begin()
        self._set_playing_ui(True)
        self._log(self.app._t("rr_play_started", n=len(self._player),
                              sec=round(self._player.duration, 1)))
        self._timer.start()

    def _on_stop(self):
        self.stop_replay()

    def stop_replay(self):
        """停止当前回放；也供主窗在连接断开时同步清理回放占用状态。"""
        if self._player is None:
            self._timer.stop()
            self.app._replay_end()
            return
        self._timer.stop()
        done = self._player.idx
        self._player = None
        self.app._replay_end()
        self._set_playing_ui(False)
        self._log(self.app._t("rr_play_stopped", n=done))

    def _tick(self):
        p = self._player
        if p is None:
            self._timer.stop()
            return
        import time
        p.tick(time.monotonic())
        self.bar.setValue(int(p.progress * 100))
        if p.finished:
            self._timer.stop()
            n = len(p)
            self._player = None
            self.app._replay_end()
            self._set_playing_ui(False)
            self._log(self.app._t("rr_play_done", n=n))

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
            self._timer.stop()
        p.step(now)
        self.bar.setValue(int(p.progress * 100))
        if p.finished:
            self._timer.stop()
            self._player = None
            self.app._replay_end()
            self._set_playing_ui(False)
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
            self._timer.stop()
            self._player = None
            self.app._replay_end()
            self._set_playing_ui(False)

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
        for w in (self.btn_load, self.btn_save, self.cb_speed, self.chk_loop, self.chk_tx):
            w.setEnabled(not recording and not playing)
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
        self.btn_play.setText(t("rr_play"))
        self.btn_stop.setText(t("rr_stop"))
        set_tooltip(self.btn_help, t("rr_help_btn"))
        self.lbl_hint.setText(t("rr_hint"))
        self.cb_speed.setItemText(len(_SPEEDS) - 1, t("rr_speed_max"))
        self._refresh_stat()

    # ---------------- 生命周期 ----------------
    def closeEvent(self, e):
        if self._player is not None:
            self.stop_replay()
        if self.app._recorder.recording:
            self.stop_recording()
        super().closeEvent(e)
