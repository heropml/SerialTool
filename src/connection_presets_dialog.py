# -*- coding: utf-8 -*-
"""Connection presets manager dialog: list/edit, note, copy/delete, import/export, apply.

Data lives in app._connection_presets; this dialog is only the editor UI.
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QListWidget, QListWidgetItem, QCheckBox,
                             QPlainTextEdit, QFileDialog, QWidget, QMessageBox)

import connection_presets as cp
from theme import chrome_for
from fonts import localize_qss
from dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups


class ConnectionPresetsDialog(QDialog):
    def __init__(self, app):
        # parent=None like other tool dialogs; avoid main-window WM_NCHITTEST during shutdown.
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(720, 420)
        self.resize(860, 520)

        self._cur = -1            # real index into app._connection_presets; -1 = none
        self._loading = False     # suppress textChanged while loading editor
        self._reloading = False   # suppress row-change side effects while rebuilding list
        # Debounce edits: merge rapid keystrokes into one model write
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._commit_edit)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # ===== Left: search + list + actions =====
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        # Mirror right's "Name" label so search lines up with the name field.
        self.lbl_list = QLabel()
        self.lbl_list.setObjectName("MsHint")
        left.addWidget(self.lbl_list)
        self.ed_search = QLineEdit()
        self.ed_search.setObjectName("SnipSearch")
        self.ed_search.textChanged.connect(self._reload_list)
        left.addWidget(self.ed_search)

        self.list = QListWidget()
        self.list.setObjectName("SnipList")
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.itemDoubleClicked.connect(lambda *_: self._apply())
        left.addWidget(self.list, 1)

        ops = QHBoxLayout()
        ops.setSpacing(6)
        self.btn_save_cur = QPushButton()
        self.btn_save_cur.setObjectName("PlotGhostBtn")
        self.btn_save_cur.clicked.connect(self._save_current)
        self.btn_copy = QPushButton()
        self.btn_copy.setObjectName("PlotGhostBtn")
        self.btn_copy.clicked.connect(self._copy)
        self.btn_del = QPushButton()
        self.btn_del.setObjectName("PlotGhostBtn")
        self.btn_del.clicked.connect(self._delete)
        ops.addWidget(self.btn_save_cur)
        ops.addWidget(self.btn_copy)
        ops.addWidget(self.btn_del)
        left.addLayout(ops)

        io_row = QHBoxLayout()
        io_row.setSpacing(6)
        self.btn_import = QPushButton()
        self.btn_import.setObjectName("PlotGhostBtn")
        self.btn_import.clicked.connect(self._import)
        self.btn_export = QPushButton()
        self.btn_export.setObjectName("PlotGhostBtn")
        self.btn_export.clicked.connect(self._export)
        io_row.addWidget(self.btn_import)
        io_row.addWidget(self.btn_export)
        left.addLayout(io_row)

        left_host = QWidget()
        left_host.setLayout(left)
        left_host.setFixedWidth(300)
        root.addWidget(left_host)

        # ===== Right: editor + apply =====
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("MsHint")
        right.addWidget(self.lbl_name)
        self.ed_name = QLineEdit()
        self.ed_name.setObjectName("SnipName")
        self.ed_name.textChanged.connect(self._on_edit)
        right.addWidget(self.ed_name)

        self.lbl_note = QLabel()
        self.lbl_note.setObjectName("MsHint")
        right.addWidget(self.lbl_note)
        self.ed_note = QPlainTextEdit()
        self.ed_note.setObjectName("SnipBody")
        self.ed_note.setMaximumHeight(90)
        self.ed_note.textChanged.connect(self._on_edit)
        right.addWidget(self.ed_note)

        self.lbl_summary = QLabel()
        self.lbl_summary.setObjectName("MsHint")
        self.lbl_summary.setWordWrap(True)
        right.addWidget(self.lbl_summary)

        self.chk_reconnect = QCheckBox()
        self.chk_reconnect.setObjectName("SnipHex")
        self.chk_reconnect.toggled.connect(self._on_edit)
        right.addWidget(self.chk_reconnect)

        act = QHBoxLayout()
        act.setSpacing(8)
        self.btn_update_fields = QPushButton()
        self.btn_update_fields.setObjectName("PlotGhostBtn")
        self.btn_update_fields.clicked.connect(self._update_from_ui)
        self.btn_apply = QPushButton()
        self.btn_apply.setObjectName("PlotPrimaryBtn")
        self.btn_apply.clicked.connect(self._apply)
        act.addStretch(1)
        act.addWidget(self.btn_update_fields)
        act.addWidget(self.btn_apply)
        right.addLayout(act)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("MsHint")
        self.lbl_hint.setWordWrap(True)
        right.addWidget(self.lbl_hint)
        right.addStretch(1)
        root.addLayout(right, 1)

        self.refresh_theme()
        self.retranslate()
        self._reload_list()

    # ---------------- data: dialog only edits ----------------
    @property
    def _items(self):
        return self.app._connection_presets

    def _save(self):
        self.app._save_connection_presets()
        self.app._rebuild_connection_preset_combo()

    def flush_pending(self):
        """Flush debounced editor changes into the model."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._commit_edit()

    def _reload_list(self, *args, **kwargs):
        """Rebuild list from filter; each item UserRole stores real _items index.

        keep_id=... forces selection by preset id (needed after touch_last_used
        reorders the underlying list and invalidates self._cur).
        """
        self.flush_pending()
        # Block row-change handlers while clear/setCurrentRow emit signals
        self._reloading = True
        try:
            keep_id = kwargs.get("keep_id")
            if keep_id is None and 0 <= self._cur < len(self._items):
                keep_id = self._items[self._cur].get("id")
            self.list.clear()
            select_row = -1
            for row, (real_idx, p) in enumerate(
                    cp.filter_presets(self._items, self.ed_search.text())):
                item = QListWidgetItem(cp.display_label(p))
                item.setData(Qt.UserRole, real_idx)
                self.list.addItem(item)
                if keep_id and p.get("id") == keep_id:
                    select_row = row
            if select_row >= 0:
                self.list.setCurrentRow(select_row)
                self._cur = self.list.item(select_row).data(Qt.UserRole)
            elif self.list.count():
                self.list.setCurrentRow(0)
                self._cur = self.list.item(0).data(Qt.UserRole)
            else:
                self._cur = -1
        finally:
            self._reloading = False
        if 0 <= self._cur < len(self._items):
            self._load_editor(self._items[self._cur])
        else:
            self._load_editor(None)

    def _on_row_changed(self, row):
        if self._reloading:
            return
        self.flush_pending()
        if row < 0:
            self._cur = -1
            self._load_editor(None)
            return
        item = self.list.item(row)
        if item is None:
            self._cur = -1
            self._load_editor(None)
            return
        self._cur = int(item.data(Qt.UserRole))
        if 0 <= self._cur < len(self._items):
            self._load_editor(self._items[self._cur])
        else:
            self._cur = -1
            self._load_editor(None)

    def _load_editor(self, preset):
        self._loading = True
        try:
            if preset is None:
                self.ed_name.clear()
                self.ed_note.clear()
                self.lbl_summary.setText("")
                self.chk_reconnect.setChecked(True)
                self.ed_name.setEnabled(False)
                self.ed_note.setEnabled(False)
                self.chk_reconnect.setEnabled(False)
                self.btn_apply.setEnabled(False)
                self.btn_copy.setEnabled(False)
                self.btn_del.setEnabled(False)
                self.btn_update_fields.setEnabled(False)
            else:
                self.ed_name.setText(preset.get("name", ""))
                self.ed_note.setPlainText(preset.get("note", ""))
                self.lbl_summary.setText(cp.summary(preset))
                self.chk_reconnect.setChecked(bool(preset.get("auto_reconnect", True)))
                self.ed_name.setEnabled(True)
                self.ed_note.setEnabled(True)
                self.chk_reconnect.setEnabled(True)
                self.btn_apply.setEnabled(True)
                self.btn_copy.setEnabled(True)
                self.btn_del.setEnabled(True)
                self.btn_update_fields.setEnabled(True)
        finally:
            self._loading = False

    def _on_edit(self, *_):
        if self._loading or self._cur < 0:
            return
        self._save_timer.start()

    def _commit_edit(self):
        if self._cur < 0 or self._cur >= len(self._items):
            return
        self._save_timer.stop()
        cur = dict(self._items[self._cur])
        cur["name"] = self.ed_name.text()
        cur["note"] = self.ed_note.toPlainText()
        cur["auto_reconnect"] = self.chk_reconnect.isChecked()
        self._items[self._cur] = cp.normalize(cur)
        self._save()
        # Update list label / summary without a full rebuild
        self._reloading = True
        try:
            row = self.list.currentRow()
            if 0 <= row < self.list.count():
                self.list.item(row).setText(cp.display_label(self._items[self._cur]))
            self.lbl_summary.setText(cp.summary(self._items[self._cur]))
        finally:
            self._reloading = False

    def _save_current(self):
        self.app.save_connection_preset_from_ui(prompt_name=True)

    def _update_from_ui(self):
        if self._cur < 0 or self._cur >= len(self._items):
            return
        self.flush_pending()
        fields = self.app._capture_connection_fields()
        cur = dict(self._items[self._cur])
        cur.update(fields)
        cur["name"] = self.ed_name.text()
        cur["note"] = self.ed_note.toPlainText()
        cur["auto_reconnect"] = self.chk_reconnect.isChecked()
        self._items[self._cur] = cp.normalize(cur)
        self._save()
        self._load_editor(self._items[self._cur])
        self._reload_list()
        self.app.toast(self.app._t("cpreset_updated"))

    def _apply(self):
        if self._cur < 0 or self._cur >= len(self._items):
            return
        self.flush_pending()
        # Capture id before apply: touch_last_used moves the preset to index 0.
        pid = self._items[self._cur]["id"]
        self.app.apply_connection_preset(pid)
        # apply_connection_preset also refreshes us; keep selection by id.
        self._reload_list(keep_id=pid)

    def _copy(self):
        if self._cur < 0 or self._cur >= len(self._items):
            return
        self.flush_pending()
        try:
            items, clone = cp.duplicate(
                self._items, self._items[self._cur]["id"],
                name_suffix=self.app._t("cpreset_copy_suffix"))
        except ValueError:
            self.app.toast(self.app._t("cpreset_full", n=cp.MAX_PRESETS), error=True)
            return
        self.app._connection_presets = items
        self._save()
        self._cur = len(items) - 1
        self._reload_list()
        if clone:
            self.app.toast(self.app._t("cpreset_copied", name=clone["name"]))

    def _delete(self):
        if self._cur < 0 or self._cur >= len(self._items):
            return
        self.flush_pending()
        name = self._items[self._cur].get("name", "")
        reply = QMessageBox.question(
            self, self.app._t("cpreset_del_title"),
            self.app._t("cpreset_del_confirm", name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        items, _ = cp.delete_by_id(self._items, self._items[self._cur]["id"])
        self.app._connection_presets = items
        self._cur = -1
        self._save()
        self._reload_list()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.app._t("cpreset_import"), "", "JSON (*.json)")
        if not path:
            return
        self.flush_pending()
        try:
            with open(path, "r", encoding="utf-8") as f:
                incoming = cp.from_json(f.read())
        except Exception as e:
            self.app.toast(self.app._t("cpreset_import_failed", e=e), error=True)
            return
        if not incoming:
            self.app.toast(self.app._t("cpreset_import_empty"), error=True)
            return
        # Assign fresh ids so imports never collide with existing presets
        for item in incoming:
            item["id"] = cp._new_id()
        before = len(self._items)
        merged = cp.sanitize_list(self._items + incoming)
        added = max(0, len(merged) - before)
        self.app._connection_presets = merged
        self._cur = -1
        self._save()
        self.ed_search.clear()
        self._reload_list()
        if added < len(incoming):
            self.app.toast(
                self.app._t("cpreset_imported_truncated",
                            n=added, dropped=len(incoming) - added, max=cp.MAX_PRESETS),
                error=True)
        else:
            self.app.toast(self.app._t("cpreset_imported", n=added))

    def _export(self):
        self.flush_pending()
        if not self._items:
            self.app.toast(self.app._t("cpreset_export_empty"), error=True)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.app._t("cpreset_export"), "connection_presets.json",
            "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(cp.to_json(self._items))
            self.app.toast(self.app._t("cpreset_exported", path=path))
        except Exception as e:
            self.app.toast(self.app._t("cpreset_export_failed", e=e), error=True)

    def reload_cfg(self):
        """Reload list after profile / config switch."""
        self._save_timer.stop()
        self._cur = -1
        self._reload_list()

    def retranslate(self):
        self.flush_pending()
        t = self.app._t
        self.setWindowTitle(t("cpreset_title"))
        self.lbl_list.setText(t("cpreset_list_label"))
        self.ed_search.setPlaceholderText(t("cpreset_search_ph"))
        self.btn_save_cur.setText(t("cpreset_save_current"))
        self.btn_copy.setText(t("cpreset_copy"))
        self.btn_del.setText(t("cpreset_del"))
        self.btn_import.setText(t("cpreset_import"))
        self.btn_export.setText(t("cpreset_export"))
        self.lbl_name.setText(t("cpreset_name_label"))
        self.lbl_note.setText(t("cpreset_note_label"))
        self.chk_reconnect.setText(t("cpreset_auto_reconnect"))
        self.btn_update_fields.setText(t("cpreset_update_fields"))
        self.btn_apply.setText(t("cpreset_apply"))
        self.lbl_hint.setText(t("cpreset_hint"))
        self._reload_list()

    def refresh_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")
        c = chrome_for(self.app._theme_id())
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
        QPushButton#PlotGhostBtn {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
            font-family: 'Segoe UI'; font-size: 12px; padding: 5px 12px;
        }}
        QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#PlotGhostBtn:disabled {{ color: {c['text_sec']}; }}
        QPushButton#PlotPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 12px;
            font-weight: 500; padding: 5px 16px;
        }}
        QPushButton#PlotPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#PlotPrimaryBtn:disabled {{
            background-color: {c['input_bg']}; color: {c['text_sec']};
        }}
        QListWidget#SnipList {{
            background-color: {c['card_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
            outline: 0;
        }}
        QListWidget#SnipList::item {{ padding: 5px 8px; border-radius: 4px; }}
        QListWidget#SnipList::item:selected {{
            background-color: {c['accent']}; color: white;
        }}
        QLineEdit#SnipSearch, QLineEdit#SnipName {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px; padding: 5px 8px;
        }}
        QPlainTextEdit#SnipBody {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px;
        }}
        """))
        _style_combo_popups(self, c)

    def hideEvent(self, e):
        self.flush_pending()
        super().hideEvent(e)

    def closeEvent(self, e):
        self.flush_pending()
        super().closeEvent(e)
