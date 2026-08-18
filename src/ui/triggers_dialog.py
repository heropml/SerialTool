# -*- coding: utf-8 -*-
"""触发告警对话框 TriggersDialog：配「命中什么」+「怎么叫」，并实时显示各条命中次数。

无人值守盯梢用：设备半夜复位、偶发 ERROR、看门狗超时……人不可能一直盯着数据区，
命中就响铃 / 弹托盘通知 / 在数据区打标，回来还能看每条命中了多少次、最后一次是几点。

数据存在主窗 app._triggers（与持久化、引擎共享），本对话框只是编辑器 + 统计视图。
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QListWidget, QListWidgetItem, QCheckBox,
                             QComboBox, QWidget, QGridLayout)

from automation import triggers
from ui.theme import chrome_for
from ui.fonts import localize_qss
from ui.dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from ui.ui_tips import set_tooltip


class TriggersDialog(QDialog):
    def __init__(self, app):
        # parent=None：同其它工具对话框，避免干扰主窗 WM_NCHITTEST。主窗 _shutdown 显式收。
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(760, 460)
        self.resize(880, 540)

        self._cur = -1          # 当前编辑的规则下标；-1=无选中
        self._loading = False   # 填充编辑区时抑制回写
        self._reloading = False # 重建列表时抑制 currentRowChanged

        # 编辑去抖：连敲不每字符落盘 / 重建引擎（引擎重建会清命中统计，更不能每字符来一次）
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._commit_edit)

        # 命中统计是运行态、由收包路径累加，这里 1Hz 轮询刷新显示（仅窗口可见时）
        self._stat_timer = QTimer(self)
        self._stat_timer.setInterval(1000)
        self._stat_timer.timeout.connect(self._refresh_stats)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # ===== 左：规则列表 + 增删 + 重置统计 =====
        left = QVBoxLayout()
        left.setSpacing(8)
        self.lbl_list = QLabel()
        self.lbl_list.setObjectName("MsHint")
        left.addWidget(self.lbl_list)

        self.list = QListWidget()
        self.list.setObjectName("TrgList")
        self.list.currentRowChanged.connect(self._on_row_changed)
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

        self.btn_reset = QPushButton()
        self.btn_reset.setObjectName("PlotGhostBtn")
        self.btn_reset.clicked.connect(self._reset_stats)
        left.addWidget(self.btn_reset)

        left_host = QWidget()
        left_host.setLayout(left)
        left_host.setFixedWidth(300)
        root.addWidget(left_host)

        # ===== 右：编辑区 =====
        right = QVBoxLayout()
        right.setSpacing(8)

        self.chk_on = QCheckBox()
        self.chk_on.toggled.connect(self._on_edit)
        right.addWidget(self.chk_on)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        r = 0
        self.lbl_name = QLabel(); self.lbl_name.setObjectName("MsHint")
        self.ed_name = QLineEdit(); self.ed_name.setObjectName("TrgInput")
        self.ed_name.textChanged.connect(self._on_edit)
        grid.addWidget(self.lbl_name, r, 0); grid.addWidget(self.ed_name, r, 1, 1, 3); r += 1

        self.lbl_pat = QLabel(); self.lbl_pat.setObjectName("MsHint")
        self.ed_pat = QLineEdit(); self.ed_pat.setObjectName("TrgInput")
        self.ed_pat.textChanged.connect(self._on_edit)
        grid.addWidget(self.lbl_pat, r, 0); grid.addWidget(self.ed_pat, r, 1, 1, 3); r += 1

        self.lbl_mode = QLabel(); self.lbl_mode.setObjectName("MsHint")
        self.cb_mode = QComboBox()
        self.cb_mode.currentIndexChanged.connect(self._on_edit)
        self.chk_hex = QCheckBox()
        self.chk_hex.toggled.connect(self._on_hex_toggled)
        grid.addWidget(self.lbl_mode, r, 0)
        grid.addWidget(self.cb_mode, r, 1)
        grid.addWidget(self.chk_hex, r, 2, 1, 2); r += 1

        self.lbl_scope = QLabel(); self.lbl_scope.setObjectName("MsHint")
        self.cb_scope = QComboBox()
        self.cb_scope.currentIndexChanged.connect(self._on_edit)
        self.lbl_cd = QLabel(); self.lbl_cd.setObjectName("MsHint")
        self.ed_cd = QLineEdit(); self.ed_cd.setObjectName("TrgInput")
        self.ed_cd.setFixedWidth(90)
        self.ed_cd.textChanged.connect(self._on_edit)
        grid.addWidget(self.lbl_scope, r, 0)
        grid.addWidget(self.cb_scope, r, 1)
        grid.addWidget(self.lbl_cd, r, 2)
        grid.addWidget(self.ed_cd, r, 3); r += 1
        grid.setColumnStretch(1, 1)
        right.addLayout(grid)

        self.lbl_act = QLabel(); self.lbl_act.setObjectName("MsHint")
        right.addWidget(self.lbl_act)
        acts = QHBoxLayout()
        acts.setSpacing(12)
        self.chk_beep = QCheckBox(); self.chk_beep.toggled.connect(self._on_edit)
        self.chk_notify = QCheckBox(); self.chk_notify.toggled.connect(self._on_edit)
        self.chk_mark = QCheckBox(); self.chk_mark.toggled.connect(self._on_edit)
        for w_ in (self.chk_beep, self.chk_notify, self.chk_mark):
            acts.addWidget(w_)
        acts.addStretch(1)
        right.addLayout(acts)

        acts2 = QHBoxLayout()
        acts2.setSpacing(8)
        self.chk_webhook = QCheckBox(); self.chk_webhook.toggled.connect(self._on_edit)
        self.ed_webhook = QLineEdit(); self.ed_webhook.setObjectName("TrgInput")
        self.ed_webhook.textChanged.connect(self._on_edit)
        acts2.addWidget(self.chk_webhook)
        acts2.addWidget(self.ed_webhook, 1)
        right.addLayout(acts2)

        acts3 = QHBoxLayout()
        acts3.setSpacing(8)
        self.chk_run = QCheckBox(); self.chk_run.toggled.connect(self._on_edit)
        self.ed_run = QLineEdit(); self.ed_run.setObjectName("TrgInput")
        self.ed_run.textChanged.connect(self._on_edit)
        acts3.addWidget(self.chk_run)
        acts3.addWidget(self.ed_run, 1)
        right.addLayout(acts3)

        gate = QHBoxLayout()
        gate.setSpacing(8)
        self.lbl_min = QLabel(); self.lbl_min.setObjectName("MsHint")
        self.ed_min = QLineEdit(); self.ed_min.setObjectName("TrgInput")
        self.ed_min.setFixedWidth(56)
        self.ed_min.textChanged.connect(self._on_edit)
        self.lbl_every = QLabel(); self.lbl_every.setObjectName("MsHint")
        self.ed_every = QLineEdit(); self.ed_every.setObjectName("TrgInput")
        self.ed_every.setFixedWidth(56)
        self.ed_every.textChanged.connect(self._on_edit)
        gate.addWidget(self.lbl_min)
        gate.addWidget(self.ed_min)
        gate.addWidget(self.lbl_every)
        gate.addWidget(self.ed_every)
        gate.addStretch(1)
        right.addLayout(gate)

        self.lbl_hits = QLabel()
        self.lbl_hits.setObjectName("TrgHits")
        right.addWidget(self.lbl_hits)

        self.lbl_err = QLabel()
        self.lbl_err.setObjectName("TrgErr")
        self.lbl_err.setWordWrap(True)
        right.addWidget(self.lbl_err)

        # 全局（不分规则）：动作被并发上限丢掉时，命中数照涨但 webhook /
        # 外部程序没跑，不说一声只能靠猜。只在 >0 时占位。
        self.lbl_dropped = QLabel()
        self.lbl_dropped.setObjectName("TrgDropped")
        self.lbl_dropped.setWordWrap(True)
        right.addWidget(self.lbl_dropped)

        right.addStretch(1)
        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("MsHint")
        self.lbl_hint.setWordWrap(True)
        right.addWidget(self.lbl_hint)
        root.addLayout(right, 1)

        self.refresh_theme()
        self.retranslate()
        self._reload_list()

    # ---------------- 数据（存主窗）----------------
    @property
    def _items(self):
        return self.app._triggers

    def _save(self):
        """落盘 + 让引擎换上新规则。引擎换规则会清统计，故只在去抖后调一次。"""
        self.app._save_triggers()

    def _reload_list(self, keep=None):
        self._reloading = True
        try:
            self.list.clear()
            for i, rule in enumerate(self._items):
                self.list.addItem(QListWidgetItem(self._label(i, rule)))
            row = keep if keep is not None else self._cur
            if not (0 <= row < self.list.count()):
                row = 0 if self.list.count() else -1
            # _cur 必须在这里显式赋值：setCurrentRow 触发的 _on_row_changed 被 _reloading
            # 挡掉了（那是为了不在重建列表时误触发「切走落盘」），若不赋值，打开对话框时
            # _cur 会一直停在 -1 → 编辑区全灰，已有规则点不动。
            self._cur = row
            if row >= 0:
                self.list.setCurrentRow(row)
        finally:
            self._reloading = False
        self._load_editor()

    def _label(self, i, rule):
        """列表项文案：启用标记 + 名称(或匹配内容) + 命中次数。"""
        name = rule.get("name") or rule.get("pattern") or self.app._t("trg_unnamed")
        mark = "●" if rule.get("on", True) else "○"
        hits = self.app._trigger_engine.hits(i)
        return "%s %s    ×%d" % (mark, name[:28], hits)

    # ---------------- 选中 / 编辑 ----------------
    def _on_row_changed(self, row):
        if self._reloading:
            return
        if self._save_timer.isActive():      # 切走前先把未落盘的编辑提交
            self._save_timer.stop()
            self._commit_edit(reload=False)
        self._cur = row
        self._load_editor()

    def _load_editor(self):
        self._loading = True
        try:
            ok = 0 <= self._cur < len(self._items)
            rule = self._items[self._cur] if ok else triggers.normalize({})
            for w_ in (self.chk_on, self.ed_name, self.ed_pat, self.cb_mode, self.chk_hex,
                       self.cb_scope, self.ed_cd, self.chk_beep, self.chk_notify,
                       self.chk_mark, self.chk_webhook, self.ed_webhook,
                       self.chk_run, self.ed_run, self.ed_min, self.ed_every):
                w_.setEnabled(ok)
            self.chk_on.setChecked(rule.get("on", True))
            self.ed_name.setText(rule.get("name", ""))
            self.ed_pat.setText(rule.get("pattern", ""))
            self.chk_hex.setChecked(rule.get("hex", False))
            self.cb_mode.setCurrentIndex(min(rule.get("mode", 0), self.cb_mode.count() - 1))
            idx = {"rx": 0, "tx": 1, "both": 2}.get(rule.get("scope", "rx"), 0)
            self.cb_scope.setCurrentIndex(idx)
            self.ed_cd.setText(str(rule.get("cooldown", triggers.DEFAULT_COOLDOWN_MS)))
            self.chk_beep.setChecked(rule.get("beep", True))
            self.chk_notify.setChecked(rule.get("notify", True))
            self.chk_mark.setChecked(rule.get("mark", False))
            self.chk_webhook.setChecked(rule.get("webhook", False))
            self.ed_webhook.setText(rule.get("webhook_url", ""))
            self.chk_run.setChecked(rule.get("run_cmd_on", False))
            self.ed_run.setText(rule.get("run_cmd", ""))
            self.ed_min.setText(str(rule.get("min_hits", 1)))
            self.ed_every.setText(str(rule.get("every_n", 1)))
            self._sync_mode_items()
        finally:
            self._loading = False
        self._refresh_stats()

    def _sync_mode_items(self):
        """HEX 模式下「正则」不可选：正则是文本语义，对字节串没意义。"""
        hexmode = self.chk_hex.isChecked()
        if self.cb_mode.count() <= triggers.MODE_REGEX:
            return          # 下拉还没填充（retranslate 之前）：没有项可禁用，直接跳过
        item = self.cb_mode.model().item(triggers.MODE_REGEX)
        if item is not None:
            item.setEnabled(not hexmode)
        if hexmode and self.cb_mode.currentIndex() == triggers.MODE_REGEX:
            self.cb_mode.setCurrentIndex(triggers.MODE_CONTAINS)

    def _on_hex_toggled(self, *_):
        self._sync_mode_items()
        self._on_edit()

    def _on_edit(self, *_):
        if self._loading:
            return
        self._save_timer.start()

    def flush_pending(self):
        """把还在防抖窗口里的编辑立刻落盘。

        编辑有 400ms 去抖（连敲不每字符重建引擎），但「保存配置 / 导出 / 退出」可能正好
        发生在这 400ms 内 —— 不冲一次的话，用户刚敲进去的规则就丢了。主窗保存路径会调。"""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._commit_edit(reload=False)

    def _commit_edit(self, reload=True):
        if not (0 <= self._cur < len(self._items)):
            return
        rule = triggers.normalize({
            "name": self.ed_name.text(),
            "pattern": self.ed_pat.text(),
            "hex": self.chk_hex.isChecked(),
            "mode": self.cb_mode.currentIndex(),
            "scope": ("rx", "tx", "both")[min(2, max(0, self.cb_scope.currentIndex()))],
            "on": self.chk_on.isChecked(),
            "beep": self.chk_beep.isChecked(),
            "notify": self.chk_notify.isChecked(),
            "mark": self.chk_mark.isChecked(),
            "webhook": self.chk_webhook.isChecked(),
            "webhook_url": self.ed_webhook.text(),
            "run_cmd_on": self.chk_run.isChecked(),
            "run_cmd": self.ed_run.text(),
            "min_hits": self.ed_min.text(),
            "every_n": self.ed_every.text(),
            "cooldown": self.ed_cd.text(),
        })
        self._items[self._cur] = rule
        self._save()
        if reload:
            self._reload_list(keep=self._cur)

    # ---------------- 增删 / 统计 ----------------
    def _add(self):
        # 新增会重建列表/编辑区；先保存当前行去抖中的草稿，否则刚输入的内容会被旧模型覆盖。
        self.flush_pending()
        if len(self._items) >= triggers.MAX_RULES:
            self.app.toast(self.app._t("trg_full", n=triggers.MAX_RULES), error=True)
            return
        self._items.append(triggers.normalize({"name": self.app._t("trg_new"),
                                               "pattern": "ERROR"}))
        self._save()
        self._cur = len(self._items) - 1
        self._reload_list(keep=self._cur)

    def _delete(self):
        if not (0 <= self._cur < len(self._items)):
            return
        # 删规则当场落盘、无 undo；外部动作规则尤其危险，普通规则也不可逆，
        # 所以一律先确认。文案用 trg_*，不能复用 mbm_view_del_body（那句说
        # 「规则本身不删」，语义正好相反）。
        rule = self._items[self._cur]
        if not self.app._confirm_dlg(
                self.app._t("trg_del_title"),
                self.app._t("trg_del_body", name=rule.get("name") or ""),
                ok_text=self.app._t("trg_del")):
            return
        self._save_timer.stop()
        del self._items[self._cur]
        self._save()
        self._cur = min(self._cur, len(self._items) - 1)
        self._reload_list(keep=self._cur)

    def _reset_stats(self):
        # 重置后会 _reload_list；未提交的编辑必须先落模型，不能被重载覆盖。
        self.flush_pending()
        self.app._trigger_engine.reset_stats()
        self.app._trg_reset_dropped()
        self._refresh_stats()
        self._reload_list(keep=self._cur)

    def _refresh_stats(self):
        """刷命中次数 + 最后命中时间 + 坏配置提示。1Hz 调用，只改文案不重建列表。"""
        t = self.app._t
        eng = self.app._trigger_engine
        if 0 <= self._cur < len(self._items):
            st = eng.stat_for(self._cur)
            hits = st.get("hits", 0)
            wall = st.get("last_wall", "")
            self.lbl_hits.setText(t("trg_hits", n=hits, when=wall) if wall
                                  else t("trg_hits_none", n=hits))
        else:
            self.lbl_hits.setText("")
        bad = dict(eng.bad_patterns())
        why = bad.get(self._cur)
        self.lbl_err.setText(t("trg_bad_regex") if why == "regex"
                             else t("trg_bad_hex") if why == "hex" else "")
        dropped = self.app._trg_dropped_actions()
        self.lbl_dropped.setText(t("trg_dropped", n=dropped) if dropped else "")
        # 列表里的次数也跟着走（不重建列表，直接改文案，避免抢用户选中）
        for i in range(min(self.list.count(), len(self._items))):
            item = self.list.item(i)
            new = self._label(i, self._items[i])
            if item.text() != new:
                item.setText(new)

    # ---------------- 生命周期 ----------------
    def showEvent(self, e):
        super().showEvent(e)
        self._reload_list(keep=self._cur)
        self._stat_timer.start()

    def hideEvent(self, e):
        # 非 close 的隐藏路径同样可能随后 showEvent 重建编辑区，先冲掉草稿。
        self.flush_pending()
        self._stat_timer.stop()
        super().hideEvent(e)

    def closeEvent(self, e):
        if self._save_timer.isActive():      # 关窗前把未落盘的编辑提交，别丢用户刚敲的
            self._save_timer.stop()
            self._commit_edit(reload=False)
        self._stat_timer.stop()
        super().closeEvent(e)

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
        QListWidget#TrgList {{
            background-color: {c['card_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px; outline: 0;
        }}
        QListWidget#TrgList::item {{ padding: 5px 8px; border-radius: 4px; }}
        QListWidget#TrgList::item:selected {{ background-color: {c['accent']}; color: white; }}
        QLineEdit#TrgInput {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 6px; padding: 5px 8px;
        }}
        QLineEdit#TrgInput:disabled {{ color: {c['text_sec']}; }}
        QLabel#TrgHits {{ color: {c['accent']}; font-size: 12px; font-weight: 600; }}
        QLabel#TrgErr {{ color: {c['danger']}; font-size: 11px; }}
        QLabel#TrgDropped {{ color: {c['danger']}; font-size: 11px; }}
        """))
        _style_combo_popups(self, c)

    def retranslate(self):
        # 语言切换会重建下拉和编辑区；先保存 400ms 去抖窗口里的当前输入。
        self.flush_pending()
        t = self.app._t
        self.setWindowTitle(t("trg_title"))
        self.lbl_list.setText(t("trg_list"))
        self.btn_add.setText(t("trg_add"))
        self.btn_del.setText(t("trg_del"))
        self.btn_reset.setText(t("trg_reset"))
        self.chk_on.setText(t("trg_enabled"))
        self.lbl_name.setText(t("trg_name"))
        self.lbl_pat.setText(t("trg_pattern"))
        self.ed_pat.setPlaceholderText(t("trg_pattern_ph"))
        self.lbl_mode.setText(t("trg_mode"))
        self.chk_hex.setText(t("trg_hex"))
        self.lbl_scope.setText(t("trg_scope"))
        self.lbl_cd.setText(t("trg_cooldown"))
        set_tooltip(self.ed_cd, t("trg_cooldown_tip"))
        self.lbl_act.setText(t("trg_actions"))
        self.chk_beep.setText(t("trg_beep"))
        self.chk_webhook.setText(t("trg_webhook"))
        set_tooltip(self.ed_webhook, t("trg_webhook_tip"))
        self.ed_webhook.setPlaceholderText(t("trg_webhook_ph"))
        self.chk_run.setText(t("trg_run"))
        set_tooltip(self.ed_run, t("trg_run_tip"))
        self.ed_run.setPlaceholderText(t("trg_run_ph"))
        self.lbl_min.setText(t("trg_min_hits"))
        set_tooltip(self.ed_min, t("trg_min_hits_tip"))
        self.lbl_every.setText(t("trg_every_n"))
        set_tooltip(self.ed_every, t("trg_every_n_tip"))
        self.chk_notify.setText(t("trg_notify"))
        self.chk_mark.setText(t("trg_mark"))
        self.lbl_hint.setText(t("trg_hint"))
        cur_mode, cur_scope = self.cb_mode.currentIndex(), self.cb_scope.currentIndex()
        self._loading = True
        try:
            self.cb_mode.clear()
            self.cb_mode.addItems([t("trg_m_contains"), t("trg_m_equals"),
                                   t("trg_m_prefix"), t("trg_m_regex")])
            self.cb_scope.clear()
            self.cb_scope.addItems([t("trg_s_rx"), t("trg_s_tx"), t("trg_s_both")])
            self.cb_mode.setCurrentIndex(max(0, cur_mode))
            self.cb_scope.setCurrentIndex(max(0, cur_scope))
            self._sync_mode_items()
        finally:
            self._loading = False
        self._reload_list(keep=self._cur)
