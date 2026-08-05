# -*- coding: utf-8 -*-
"""结构化数据记录、CSV 历史查询与时间轴回放。"""

import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from fonts import localize_qss
from theme import chrome_for
from ui_tips import set_tooltip


class StructuredRecordDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.recorder = app._structured_recorder
        self._visible_rows = []
        self._replay_rows = []
        self._replay_index = 0
        self._replay_started = 0.0
        self._replay_base = 0.0
        self._timer = QTimer(self)
        self._replay_speed = 1.0
        self._replay_paused = False
        self._replay_elapsed = 0.0
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._replay_tick)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(760, 440)
        self.resize(1050, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        top = QHBoxLayout()
        self.btn_record = self._button("structured_start", self._toggle_recording)
        self.btn_clear = self._button("structured_clear", self._clear)
        self.btn_open = self._button("structured_open", self._open_csv)
        self.btn_save = self._button("structured_save", self._save_csv)
        self.cb_replay_speed = QComboBox()
        for label, val in (("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("5x", 5.0)):
            self.cb_replay_speed.addItem(label, val)
        self.cb_replay_speed.setCurrentIndex(1)
        self.cb_replay_speed.currentIndexChanged.connect(self._on_replay_speed)
        self.btn_replay_pause = QPushButton()
        self.btn_replay_pause.setObjectName("PlotGhostBtn")
        self.btn_replay_pause.clicked.connect(self._toggle_replay_pause)
        self.btn_replay = self._button("structured_replay", self._toggle_replay)
        self.ed_search = QLineEdit()
        self.ed_search.textChanged.connect(self.refresh_rows)
        self.cb_source = QComboBox()
        self.cb_source.addItem("", "")
        self.cb_source.addItem("Modbus", "modbus")
        self.cb_source.addItem("Protocol", "protocol")
        self.cb_source.currentIndexChanged.connect(self.refresh_rows)
        for button in (self.btn_record, self.btn_clear, self.btn_open,
                       self.btn_save, self.cb_replay_speed,
                       self.btn_replay_pause, self.btn_replay):
            top.addWidget(button)
        top.addStretch(1)
        top.addWidget(self.cb_source)
        top.addWidget(self.ed_search)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("PlotHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help_dlg)
        top.addWidget(self.btn_help)
        root.addLayout(top)

        self.table = QTableWidget(0, 7)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)
        self.lbl_status = QLabel()
        root.addWidget(self.lbl_status)
        self.retranslate()
        self.refresh_theme()
        self.refresh_rows()

    def _button(self, key, callback):
        button = QPushButton()
        button.setObjectName("PlotGhostBtn")
        button.setProperty("tr_text", key)
        button.clicked.connect(callback)
        return button

    def _toggle_recording(self):
        if self.recorder.recording:
            self.recorder.stop()
        else:
            self.recorder.start(clear=False)
        self._sync_state()
        self.app._refresh_workspace_statuses()

    def _clear(self):
        self._timer.stop()
        self.recorder.clear()
        self.refresh_rows()

    def _open_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.app._t("structured_open"), "", "CSV (*.csv)")
        if not path:
            return
        try:
            self.recorder.stop()
            self.recorder.load_csv(path)
        except Exception as exc:
            self.app.toast(str(exc), error=True)
            return
        self.app._refresh_workspace_statuses()
        self.refresh_rows()

    def _save_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self.app._t("structured_save"), "structured.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            count = self.recorder.save_csv(path, self._visible_rows)
        except Exception as exc:
            self.app.toast(str(exc), error=True)
            return
        self.app.toast(self.app._t("structured_saved", count=count))

    def _on_replay_speed(self, *_):
        import time
        new_speed = float(self.cb_replay_speed.currentData() or 1.0)
        new_speed = max(0.01, new_speed)
        if self._timer.isActive() or self._replay_paused:
            now = time.monotonic()
            # Keep media elapsed stable across speed changes.
            self._replay_started = now - (self._replay_elapsed / new_speed)
        self._replay_speed = new_speed

    def _toggle_replay_pause(self):
        import time
        if not self._timer.isActive() and not self._replay_paused:
            return
        if self._replay_paused:
            self._replay_speed = max(0.01, float(self.cb_replay_speed.currentData() or 1.0))
            self._replay_started = time.monotonic() - (self._replay_elapsed / self._replay_speed)
            self._replay_paused = False
            self._timer.start()
        else:
            self._replay_paused = True
            self._timer.stop()
        self._sync_state()

    def _toggle_replay(self):
        # Active or paused: stop (do not restart from zero while paused).
        if self._timer.isActive() or self._replay_paused:
            self._timer.stop()
            self._replay_paused = False
            self._sync_state()
            return
        if not self._replay_rows:
            return
        import time
        self._replay_index = 0
        self._replay_paused = False
        self._replay_elapsed = 0.0
        self._replay_speed = float(self.cb_replay_speed.currentData() or 1.0)
        self._replay_started = time.monotonic()
        self._replay_base = self._replay_rows[0]["timestamp"]
        self._timer.start()
        self._sync_state()

    def _replay_tick(self):
        import time
        if self._replay_paused:
            return
        elapsed = (time.monotonic() - self._replay_started) * self._replay_speed
        self._replay_elapsed = elapsed
        while self._replay_index < len(self._replay_rows):
            row = self._replay_rows[self._replay_index]
            if row["timestamp"] - self._replay_base > elapsed:
                break
            table_row = self._replay_index
            if table_row < self.table.rowCount():
                self.table.selectRow(table_row)
                self.table.scrollToItem(self.table.item(table_row, 0))
            self.app._structured_replay_sample(row)
            self._replay_index += 1
        if self._replay_index >= len(self._replay_rows):
            self._timer.stop()
            self._sync_state()

    @staticmethod
    def _format_value(value):
        if isinstance(value, float):
            return "%.9g" % value
        return str(value)

    def refresh_rows(self, *_):
        source = self.cb_source.currentData() if hasattr(self, "cb_source") else ""
        text = self.ed_search.text() if hasattr(self, "ed_search") else ""
        self._visible_rows = self.recorder.query(text, source)
        # GUI 只展示最后 5000 条，CSV 保存仍使用完整筛选结果。
        shown = self._visible_rows[-5000:]
        self._replay_rows = shown
        self.table.setRowCount(len(shown))
        for row_index, row in enumerate(shown):
            dt = datetime.datetime.fromtimestamp(row["timestamp"])
            values = (
                dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], row["source"], row["tag"],
                self._format_value(row["value"]), row["unit"],
                self._level_text(row.get("level", "")), row["raw"],
            )
            for column, value in enumerate(values):
                self.table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self._sync_state()

    def _level_text(self, level):
        """寄存器阈值命中的结果；未配阈值的行为空。"""
        key = {"warn": "structured_level_warn",
               "alarm": "structured_level_alarm"}.get(str(level or ""))
        return self.app._t(key) if key else ""

    def on_samples(self, count):
        if count and self.isVisible() and not self._timer.isActive():
            self.refresh_rows()

    def _sync_state(self):
        self.btn_record.setText(self.app._t(
            "structured_stop" if self.recorder.recording else "structured_start"))
        self.btn_replay_pause.setText(self.app._t(
            "structured_replay_resume" if self._replay_paused else "structured_replay_pause"))
        replaying = self._timer.isActive() or self._replay_paused
        self.btn_replay.setText(self.app._t(
            "structured_replay_stop" if replaying else "structured_replay"))
        self.lbl_status.setText(self.app._t(
            "structured_status", count=len(self.recorder.rows),
            shown=len(self._visible_rows)))

    # ---------------- 主题 / 语言 ----------------
    def _show_help_dlg(self):
        """弹独立窗口看用法 + 例子（同波形图/仪表盘形制：富文本+滚动+可复制）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("structured_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                           | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                           | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(720, 500)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("structured_help"))
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
            {"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(getattr(self.app, "_lang", "en"), "Close"))
        btn_close.setObjectName("PlotGhostBtn")
        btn_close.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1); row.addWidget(btn_close)
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
        c = chrome_for(self.app._theme_id())
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
        QDialog {{ background-color: {c['window_bg']}; color: {c['text']}; }}
        QTableWidget {{ background-color: {c['card_bg']}; color: {c['text']};
            alternate-background-color: {c['input_bg']}; border: 1px solid {c['separator']}; }}
        QHeaderView::section {{ background-color: {c['input_bg']}; color: {c['text']};
            border: 0; border-right: 1px solid {c['separator']}; padding: 6px; }}
        QPushButton#PlotGhostBtn {{ background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px; padding: 5px 12px; }}
        QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#PlotHelpBtn {{
            background-color: transparent; color: {c['text_sec']};
            border: 1px solid {c['separator']}; border-radius: 13px;
            font-family: 'Segoe UI'; font-size: 13px; font-weight: bold;
        }}
        QPushButton#PlotHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        """))
        _style_combo_popups(self, c)
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("structured_title"))
        self.ed_search.setPlaceholderText(t("structured_search"))
        self.cb_source.setItemText(0, t("structured_all_sources"))
        for button in (self.btn_clear, self.btn_open, self.btn_save):
            button.setText(t(button.property("tr_text")))
        set_tooltip(self.btn_help, t("structured_help_btn"))
        self.table.setHorizontalHeaderLabels([
            t("structured_col_time"), t("structured_col_source"),
            t("structured_col_tag"), t("structured_col_value"),
            t("structured_col_unit"), t("structured_col_level"),
            t("structured_col_raw"),
        ])
        self._sync_state()

    def closeEvent(self, event):
        self._timer.stop()
        # 对话框是单实例，关闭即结束回放会话；不清暂停标志的话，
        # 重开后按钮会显示成「继续/停止回放」的假活动态。
        self._replay_paused = False
        self._replay_elapsed = 0.0
        super().closeEvent(event)
