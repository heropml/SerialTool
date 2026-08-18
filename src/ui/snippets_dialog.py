# -*- coding: utf-8 -*-
"""发送模板库对话框 SnippetsDialog：存常用命令，双击填入发送框或直接发送。

与「多条发送」分工：多条发送把一组命令按序循环发（自动化节奏），本库是单条常用命令
随手取用（手动）。故这里没有延时 / 校验 / 循环，只有 名称 / 内容 / HEX 三列。

数据存在主窗 app._snippets（与持久化共享），本对话框只是编辑器 + 取用入口。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QListWidget, QListWidgetItem, QCheckBox,
                             QPlainTextEdit, QFileDialog, QWidget)

from automation import snippets
from ui.theme import chrome_for
from ui.fonts import localize_qss, mono_font
from ui.dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups


class SnippetsDialog(QDialog):
    def __init__(self, app):
        # parent=None：同其它工具对话框，避免干扰主窗 WM_NCHITTEST。主窗 _shutdown 显式收。
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(720, 420)
        self.resize(860, 520)

        self._cur = -1            # 当前编辑的模板在 app._snippets 里的真实下标；-1=无选中
        self._loading = False     # 填充编辑区时抑制 textChanged 回写
        self._reloading = False   # 重建列表时抑制 currentRowChanged 的「切走落盘」逻辑
        # 编辑去抖：连敲不每字符落盘 / 重建列表
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._commit_edit)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # ===== 左：搜索 + 列表 + 增删 =====
        left = QVBoxLayout()
        left.setSpacing(8)
        self.ed_search = QLineEdit()
        self.ed_search.setObjectName("SnipSearch")
        self.ed_search.textChanged.connect(self._reload_list)
        left.addWidget(self.ed_search)

        self.list = QListWidget()
        self.list.setObjectName("SnipList")
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.itemDoubleClicked.connect(lambda *_: self._fill(send=False))
        left.addWidget(self.list, 1)

        ops = QHBoxLayout()
        ops.setSpacing(6)
        self.btn_add = QPushButton()
        self.btn_add.setObjectName("PlotGhostBtn")
        self.btn_add.clicked.connect(self._add)
        self.btn_del = QPushButton()
        self.btn_del.setObjectName("PlotGhostBtn")
        self.btn_del.clicked.connect(self._delete)
        ops.addWidget(self.btn_add)
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
        left_host.setFixedWidth(280)
        root.addWidget(left_host)

        # ===== 右：编辑区 + 取用按钮 =====
        right = QVBoxLayout()
        right.setSpacing(8)
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("MsHint")
        right.addWidget(self.lbl_name)
        self.ed_name = QLineEdit()
        self.ed_name.setObjectName("SnipName")
        self.ed_name.textChanged.connect(self._on_edit)
        right.addWidget(self.ed_name)

        self.lbl_body = QLabel()
        self.lbl_body.setObjectName("MsHint")
        right.addWidget(self.lbl_body)
        self.ed_body = QPlainTextEdit()
        self.ed_body.setObjectName("SnipBody")
        self.ed_body.setFont(mono_font(10))
        self.ed_body.textChanged.connect(self._on_edit)
        right.addWidget(self.ed_body, 1)

        self.chk_hex = QCheckBox()
        self.chk_hex.setObjectName("SnipHex")
        self.chk_hex.toggled.connect(self._on_edit)
        right.addWidget(self.chk_hex)

        act = QHBoxLayout()
        act.setSpacing(8)
        self.btn_fill = QPushButton()
        self.btn_fill.setObjectName("PlotGhostBtn")
        self.btn_fill.clicked.connect(lambda *_: self._fill(send=False))
        self.btn_send = QPushButton()
        self.btn_send.setObjectName("PlotPrimaryBtn")
        self.btn_send.clicked.connect(lambda *_: self._fill(send=True))
        act.addStretch(1)
        act.addWidget(self.btn_fill)
        act.addWidget(self.btn_send)
        right.addLayout(act)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("MsHint")
        self.lbl_hint.setWordWrap(True)
        right.addWidget(self.lbl_hint)

        root.addLayout(right, 1)

        self.refresh_theme()
        self.retranslate()
        self._reload_list()

    # ---------------- 数据（存主窗，本对话框只是编辑器）----------------
    @property
    def _items(self):
        return self.app._snippets

    def _save(self):
        self.app._save_snippets()

    # ---------------- 列表 ----------------
    def _reload_list(self, *_):
        """按搜索框过滤重建列表；每个 item 用 UserRole 记住它在 _items 里的真实下标。"""
        # 搜索、语言切换等也会直接重建列表。若编辑仍在 300ms 去抖窗口里，必须先写回
        # 模型，否则下面的 _load_editor 会拿旧值覆盖输入框，刚敲的内容永久丢失。
        self.flush_pending()
        # 整个重建期间挡住 currentRowChanged 的副作用：clear / setCurrentRow 都会发信号，
        # 若不挡会触发 _on_row_changed 的「切走落盘」再回来重建，形成递归。
        self._reloading = True
        try:
            self.list.clear()
            for real_idx, s in snippets.filter_snippets(self._items, self.ed_search.text()):
                label = s.get("name") or self._preview(s.get("text", ""))
                item = QListWidgetItem(("HEX  " if s.get("hex") else "TXT  ") + label)
                item.setData(Qt.UserRole, real_idx)
                self.list.addItem(item)
            # 尽量把选中恢复到 _cur 对应的行（编辑 / 增删后列表重建仍停在当前条）
            target = None
            for row in range(self.list.count()):
                if self.list.item(row).data(Qt.UserRole) == self._cur:
                    target = row
                    break
            if target is not None:
                self.list.setCurrentRow(target)
            elif self.list.count():
                self.list.setCurrentRow(0)
                self._cur = self.list.item(0).data(Qt.UserRole)
            else:
                self._cur = -1
        finally:
            self._reloading = False
        self._load_editor()          # 用最终的 _cur 同步编辑区（重建后统一刷一次）

    @staticmethod
    def _preview(text):
        one = " ".join(text.split())
        return (one[:40] + "…") if len(one) > 40 else (one or "(空)")

    def _on_row_changed(self, row):
        if self._reloading or row < 0:      # 重建列表触发的选中变化不算「用户切走」，_reload_list 会统一收尾
            return
        idx = self.list.item(row).data(Qt.UserRole)
        idx = idx if isinstance(idx, int) else -1
        if self._save_timer.isActive():      # 切走前先把上一条未提交的编辑落盘
            # 先只写模型，不在 currentRowChanged 回调中按旧 _cur 重建列表；否则重建会把
            # 高亮拉回旧条目，随后编辑区却载入新条目，造成“选中 A、实际编辑 B”。
            self._commit_edit(reload=False)
            self._cur = idx
            self._reload_list()
            return
        self._cur = idx
        self._load_editor()

    # ---------------- 编辑区 ----------------
    def _load_editor(self):
        self._loading = True
        if 0 <= self._cur < len(self._items):
            s = self._items[self._cur]
            self.ed_name.setText(s.get("name", ""))
            self.ed_body.setPlainText(s.get("text", ""))
            self.chk_hex.setChecked(bool(s.get("hex")))
            for w in (self.ed_name, self.ed_body, self.chk_hex,
                      self.btn_fill, self.btn_send, self.btn_del):
                w.setEnabled(True)
        else:
            self.ed_name.clear()
            self.ed_body.clear()
            self.chk_hex.setChecked(False)
            for w in (self.ed_name, self.ed_body, self.chk_hex,
                      self.btn_fill, self.btn_send, self.btn_del):
                w.setEnabled(False)
        self._loading = False

    def _on_edit(self, *_):
        if self._loading or not (0 <= self._cur < len(self._items)):
            return
        self._save_timer.start()     # 去抖：连敲合并成一次落盘 + 列表刷新

    def flush_pending(self):
        """把去抖窗口里的编辑立即写回模型；重建/导出/关闭前统一调用。"""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._commit_edit(reload=False)

    def reload_cfg(self):
        """工程/配置切换后按主窗口的新模板库重建列表，丢弃旧工程选中索引。"""
        self._save_timer.stop()
        self._cur = -1
        self._reload_list()

    def _commit_edit(self, reload=True):
        if not (0 <= self._cur < len(self._items)):
            return
        self._save_timer.stop()      # 防重入：_reload_list 的 setCurrentRow 会回调 _on_row_changed，
                                     # 若 timer 仍 active 会再次 _commit_edit → _reload_list 无限递归
        self._items[self._cur] = snippets.normalize({
            "name": self.ed_name.text(),
            "text": self.ed_body.toPlainText(),
            "hex": self.chk_hex.isChecked(),
        })
        self._save()
        if reload:
            self._reload_list()      # 名称 / HEX 变了要刷新列表标签

    # ---------------- 增删 ----------------
    def _add(self):
        self.flush_pending()
        if len(self._items) >= snippets.MAX_SNIPPETS:
            self.app.toast(self.app._t("snip_full", n=snippets.MAX_SNIPPETS), error=True)
            return
        self._items.append({"name": self.app._t("snip_new_name"), "text": "", "hex": False})
        self._cur = len(self._items) - 1
        self._save()
        self.ed_search.clear()       # 清搜索确保新条可见
        self._reload_list()
        self.ed_name.setFocus()
        self.ed_name.selectAll()

    def _delete(self):
        if not (0 <= self._cur < len(self._items)):
            return
        # 当前条即将删除，不必提交它，但必须取消定时器，避免删除后回调误写下一条。
        self._save_timer.stop()
        del self._items[self._cur]
        self._cur = min(self._cur, len(self._items) - 1)
        self._save()
        self._reload_list()

    # ---------------- 取用：填入发送框 / 直接发送 ----------------
    def _fill(self, send):
        """把当前模板填入主发送框，按其 HEX 标记设发送格式；send=True 时随即发送。
        直接发送复用主窗 do_send，遵循主界面的换行 / 校验 / 目标设置，与手动发一致。"""
        if not (0 <= self._cur < len(self._items)):
            return
        self._commit_edit()          # 填入的是「当前编辑框的最新内容」，先落盘再取
        s = self._items[self._cur]
        self.app.sw_tx_hex.setChecked(bool(s.get("hex")))
        self.app.txt_send.setPlainText(s.get("text", ""))
        if send:
            self.app.do_send()
        else:
            self.app.toast(self.app._t("snip_filled"))

    # ---------------- 导入 / 导出 ----------------
    def _import(self):
        t = self.app._t
        path, _ = QFileDialog.getOpenFileName(self, t("snip_import"), "",
                                              "JSON (*.json);;All Files (*)")
        if not path:
            return
        self.flush_pending()
        try:
            with open(path, encoding="utf-8") as f:
                incoming = snippets.from_json(f.read())
        except Exception as e:
            self.app.toast(t("snip_import_failed", e=e), error=True)
            return
        if not incoming:
            self.app.toast(t("snip_import_empty"), error=True)
            return
        # 追加到现有库（不覆盖，用户手上的不丢），整体截到上限
        merged = snippets.sanitize_list(self._items + incoming)
        added = len(merged) - len(self._items)
        self._items[:] = merged
        self._cur = -1
        self._save()
        self.ed_search.clear()
        self._reload_list()
        self.app.toast(t("snip_imported", n=added))

    def _export(self):
        t = self.app._t
        self.flush_pending()
        if not self._items:
            self.app.toast(t("snip_export_empty"), error=True)
            return
        path, _ = QFileDialog.getSaveFileName(self, t("snip_export"), "snippets.json",
                                              "JSON (*.json);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(snippets.to_json(self._items))
            self.app.toast(t("snip_exported", path=path))
        except Exception as e:
            self.app.toast(t("snip_export_failed", e=e), error=True)

    # ---------------- 主题 / 语言 ----------------
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

    def retranslate(self):
        self.flush_pending()
        t = self.app._t
        self.setWindowTitle(t("snip_title"))
        self.ed_search.setPlaceholderText(t("snip_search_ph"))
        self.btn_add.setText(t("snip_add"))
        self.btn_del.setText(t("snip_del"))
        self.btn_import.setText(t("snip_import"))
        self.btn_export.setText(t("snip_export"))
        self.lbl_name.setText(t("snip_name_label"))
        self.lbl_body.setText(t("snip_body_label"))
        self.chk_hex.setText(t("snip_hex"))
        self.btn_fill.setText(t("snip_fill"))
        self.btn_send.setText(t("snip_send"))
        self.lbl_hint.setText(t("snip_hint"))
        self._reload_list()

    def hideEvent(self, e):
        self.flush_pending()
        super().hideEvent(e)

    def closeEvent(self, e):
        self.flush_pending()
        super().closeEvent(e)
