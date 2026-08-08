# -*- coding: utf-8 -*-
"""Send-history search picker: filter past TX commands and refill the send box.

Non-modal tool dialog (same pattern as other workbench helpers). Up/Down in
the send box still navigates history; this dialog is for full-text search
when the FIFO is long.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QShortcut,
)

import send_history
from theme import chrome_for
from fonts import localize_qss, mono_font
from dialogs import _dialog_list_qss, _set_win_titlebar_dark


class SendHistoryDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowFlags(
            Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
            | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint
        )
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(420, 360)
        self.resize(520, 440)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        self.ed_search = QLineEdit()
        self.ed_search.setObjectName("SnipSearch")
        self.ed_search.textChanged.connect(self._reload)
        root.addWidget(self.ed_search)

        self.lbl_empty = QLabel()
        self.lbl_empty.setObjectName("HintLabel")
        root.addWidget(self.lbl_empty)

        self.list = QListWidget()
        self.list.setObjectName("SnipList")
        self.list.setFont(mono_font(10))
        self.list.itemDoubleClicked.connect(lambda *_: self._fill())
        self.list.currentItemChanged.connect(lambda *_: self._sync_del_enabled())
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_fill = QPushButton()
        self.btn_fill.setObjectName("MsGhostBtn")
        self.btn_fill.setMinimumHeight(30)
        self.btn_fill.clicked.connect(self._fill)
        row.addWidget(self.btn_fill)
        self.btn_del = QPushButton()
        self.btn_del.setObjectName("MsGhostBtn")
        self.btn_del.setMinimumHeight(30)
        self.btn_del.clicked.connect(self._delete)
        row.addWidget(self.btn_del)
        row.addStretch(1)
        self.btn_close = QPushButton()
        self.btn_close.setObjectName("MsGhostBtn")
        self.btn_close.setMinimumHeight(30)
        self.btn_close.clicked.connect(self.close)
        row.addWidget(self.btn_close)
        root.addLayout(row)

        # Delete / Backspace remove the current row (same as the button).
        for key in (QKeySequence.Delete, QKeySequence(Qt.Key_Backspace)):
            sc = QShortcut(key, self.list)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(self._delete)

        self.retranslate()
        self.refresh_theme()
        self._reload()

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("send_hist_title"))
        self.ed_search.setPlaceholderText(t("send_hist_search_ph"))
        self.btn_fill.setText(t("send_hist_fill"))
        self.btn_del.setText(t("send_hist_del"))
        self.btn_close.setText(t("cancel"))
        # refresh empty-label for current filter state
        self._reload()

    def refresh_theme(self):
        tid = self.app.cb_theme.currentData() if hasattr(self.app, "cb_theme") else None
        c = chrome_for(tid)
        # Match MultiSend / Snippets: MsGhostBtn from _dialog_list_qss + list/search skin.
        qss = _dialog_list_qss(c) + f"""
        QLabel#HintLabel {{ color: {c['text_sec']}; font-size: 11px; }}
        QListWidget#SnipList {{
            background-color: {c['card_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px;
            outline: 0px;
        }}
        QListWidget#SnipList::item {{ padding: 5px 8px; border-radius: 4px; }}
        QListWidget#SnipList::item:selected {{
            background-color: {c['accent']}; color: #FFFFFF;
        }}
        QLineEdit#SnipSearch {{
            background-color: {c['input_bg']}; border: 1px solid {c['separator']};
            border-radius: 6px; padding: 6px 10px; color: {c['text']};
            font-family: 'Segoe UI'; font-size: 12px;
        }}
        QLineEdit#SnipSearch:focus {{
            border: 1px solid {c['accent']}; background-color: {c['input_focus_bg']};
        }}
        QPushButton#MsGhostBtn:disabled {{ color: {c['text_sec']}; }}
        """
        self.setStyleSheet(localize_qss(qss))
        _set_win_titlebar_dark(self, c.get("mode") == "dark")

    def _reload(self, *, prefer_row=None):
        items = getattr(self.app, "_send_hist", []) or []
        query = self.ed_search.text()
        matched = send_history.filter_hist(items, query)
        # newest first
        matched = list(reversed(matched))

        self.list.blockSignals(True)
        self.list.clear()
        for real_idx, text in matched:
            it = QListWidgetItem(send_history.preview_hist(text))
            it.setData(Qt.UserRole, real_idx)
            it.setToolTip(text)
            self.list.addItem(it)
        self.list.blockSignals(False)

        if not items:
            self.lbl_empty.setText(self.app._t("send_hist_empty"))
            self.lbl_empty.show()
        elif not matched:
            self.lbl_empty.setText(self.app._t("send_hist_no_match"))
            self.lbl_empty.show()
        else:
            self.lbl_empty.hide()
            if self.list.count():
                row = 0 if prefer_row is None else max(0, min(prefer_row, self.list.count() - 1))
                if self.list.currentRow() < 0 or prefer_row is not None:
                    self.list.setCurrentRow(row)
        self._sync_del_enabled()

    def _sync_del_enabled(self):
        self.btn_del.setEnabled(self.list.currentItem() is not None)

    def _fill(self):
        it = self.list.currentItem()
        if it is None:
            return
        idx = it.data(Qt.UserRole)
        hist = getattr(self.app, "_send_hist", []) or []
        if not isinstance(idx, int) or not (0 <= idx < len(hist)):
            return
        # Align Up/Down navigation with the filled entry
        self.app._send_hist_idx = idx
        self.app._send_hist_pending = ""
        self.app._show_hist_at(idx)
        self.app.txt_send.setFocus()

    def _delete(self):
        it = self.list.currentItem()
        if it is None:
            return
        idx = it.data(Qt.UserRole)
        row = self.list.currentRow()
        if not getattr(self.app, "_delete_send_hist", None):
            return
        if not self.app._delete_send_hist(idx):
            return
        # Keep the highlight near the deleted row (next item slides up).
        self._reload(prefer_row=row)
