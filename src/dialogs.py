# -*- coding: utf-8 -*-
"""对话框：CloseDialog / MultiSendDialog / KeywordHighlightDialog + 共享样式 helper。"""
import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QFrame, QLineEdit,
                             QCheckBox, QComboBox, QHBoxLayout, QVBoxLayout, QScrollArea,
                             QGraphicsDropShadowEffect, QColorDialog,
                             QListWidget, QListWidgetItem)
from theme import chrome_for, THEME_DEFAULT
from i18n import CHECKSUM_KEYS


# ============== 关闭确认对话框 (iOS 风格) ==============
class CloseDialog(QDialog):
    """无边框 + 圆角白底 + 居中标题 + 3 个并排按钮"""
    RESULT_MIN = 1
    RESULT_QUIT = 2
    RESULT_CANCEL = 0

    def __init__(self, title_text: str, btn_min_text: str,
                 btn_quit_text: str, btn_cancel_text: str,
                 theme_id: str = THEME_DEFAULT, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._result_val = self.RESULT_CANCEL
        self._theme_id = theme_id

        # 外层透明容器，里面放圆角白卡
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        self._card = QFrame()
        self._card.setObjectName("DialogCard")
        sh = QGraphicsDropShadowEffect(self._card)
        sh.setBlurRadius(30)
        sh.setColor(QColor(0, 0, 0, 60))
        sh.setOffset(0, 4)
        self._card.setGraphicsEffect(sh)

        v = QVBoxLayout(self._card)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(20)

        # 标题文本 (居中) — 颜色按主题来
        c = chrome_for(theme_id)
        self.lbl_title = QLabel(title_text)
        f = QFont("Segoe UI", 14)
        f.setWeight(QFont.DemiBold)
        self.lbl_title.setFont(f)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet(f"color: {c['text']}; background: transparent;")
        v.addWidget(self.lbl_title)

        # 3 个按钮一行
        h = QHBoxLayout()
        h.setSpacing(10)

        self.btn_min = QPushButton(btn_min_text)
        self.btn_min.setObjectName("DialogPrimaryBtn")
        self.btn_min.setMinimumHeight(36)
        self.btn_min.clicked.connect(self._on_min)
        h.addWidget(self.btn_min, 1)

        self.btn_quit = QPushButton(btn_quit_text)
        self.btn_quit.setObjectName("DialogDangerBtn")
        self.btn_quit.setMinimumHeight(36)
        self.btn_quit.clicked.connect(self._on_quit)
        h.addWidget(self.btn_quit, 1)

        self.btn_cancel = QPushButton(btn_cancel_text)
        self.btn_cancel.setObjectName("DialogGhostBtn")
        self.btn_cancel.setMinimumHeight(36)
        self.btn_cancel.clicked.connect(self._on_cancel)
        h.addWidget(self.btn_cancel, 1)

        v.addLayout(h)
        outer.addWidget(self._card)

        self.setStyleSheet(self._build_qss())
        self.setMinimumWidth(380)

    def _build_qss(self):
        c = chrome_for(self._theme_id)
        return f"""
        QFrame#DialogCard {{
            background-color: {c['card_bg']};
            border-radius: 14px;
        }}
        QPushButton#DialogPrimaryBtn {{
            background-color: {c['accent']};
            color: white;
            border: 0px;
            border-radius: 9px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 600;
            padding: 6px 12px;
        }}
        QPushButton#DialogPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#DialogPrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#DialogDangerBtn {{
            background-color: {c['danger']};
            color: white;
            border: 0px;
            border-radius: 9px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 600;
            padding: 6px 12px;
        }}
        QPushButton#DialogDangerBtn:hover {{ background-color: {c['danger_hover']}; }}
        QPushButton#DialogGhostBtn {{
            background-color: {c['ghost_bg']};
            color: {c['text']};
            border: 0px;
            border-radius: 9px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 500;
            padding: 6px 12px;
        }}
        QPushButton#DialogGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#DialogGhostBtn:pressed {{ background-color: {c['ghost_pressed']}; }}
        """

    def _on_min(self):
        self._result_val = self.RESULT_MIN
        self.accept()

    def _on_quit(self):
        self._result_val = self.RESULT_QUIT
        self.accept()

    def _on_cancel(self):
        self._result_val = self.RESULT_CANCEL
        self.reject()

    def result_value(self):
        return self._result_val


def _set_win_titlebar_dark(widget, is_dark):
    """Windows DWM 沉浸式深/浅标题栏；非 Windows 静默跳过。
    供 MultiSendDialog / KeywordHighlightDialog 共用，避免重复+标志不一致。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        val = ctypes.c_int(1 if is_dark else 0)
        # 属性号 20 = Win10 20H1+/Win11；失败(HRESULT≠0)才回退老版本的 19
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        if hr != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
        if widget.isVisible():
            # SWP_NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED — 仅重绘非客户区，不动大小/位置/层级
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
    except Exception:
        pass


def _make_list_scroll():
    """列表型弹窗共用：建滚动区 + 内部容器(底栏 stretch)，并关掉 viewport/host 的
    autoFillBackground(否则深色主题下默认白底盖住对话框)。返回 (scroll, host, vbox)。"""
    host = QWidget()
    host.setObjectName("MsListHost")
    vbox = QVBoxLayout(host)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(6)
    vbox.addStretch(1)
    scroll = QScrollArea()
    scroll.setObjectName("MsScroll")
    scroll.setWidget(host)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    host.setAutoFillBackground(False)
    scroll.viewport().setAutoFillBackground(False)
    return scroll, host, vbox


def _dialog_list_qss(c):
    """MultiSendDialog / KeywordHighlightDialog 共用的列表型弹窗基础样式表。
    各自再拼接自己特有的按钮样式(MsPrimaryBtn/MsSendBtn 等)。"""
    return f"""
    QDialog {{ background-color: {c['window_bg']}; }}
    QLabel {{ color: {c['text']}; background: transparent; font-family: 'Segoe UI'; font-size: 12px; }}
    QLabel#MsHint {{ color: {c['text_sec']}; font-size: 11px; }}
    QScrollArea#MsScroll {{ background: transparent; border: 0px; }}
    QScrollArea#MsScroll > QWidget > QWidget {{ background: transparent; }}
    QWidget#MsListHost {{ background: transparent; }}
    QFrame#MsRow {{ background-color: {c['card_bg']}; border-radius: 8px; }}
    QLineEdit {{
        background-color: {c['input_bg']}; border: 1px solid {c['separator']};
        border-radius: 6px; padding: 4px 8px; color: {c['text']};
        font-family: 'Consolas'; font-size: 12px;
        selection-background-color: {c['accent']};
    }}
    QLineEdit:focus {{ border: 1px solid {c['accent']}; background-color: {c['input_focus_bg']}; }}
    QCheckBox {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 11px; spacing: 4px; }}
    QComboBox {{
        background-color: {c['input_bg']}; border: 1px solid {c['separator']};
        border-radius: 6px; padding: 3px 6px; color: {c['text']};
        font-family: 'Segoe UI'; font-size: 11px;
        selection-background-color: {c['accent']};
    }}
    QComboBox:focus {{ border: 1px solid {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 16px; }}
    QComboBox QAbstractItemView {{
        background-color: {c['combo_dropdown_bg']}; color: {c['text']};
        border: 1px solid {c['separator']}; border-radius: 0px; padding: 2px;
        outline: 0px; selection-background-color: {c['accent']}; selection-color: #FFFFFF;
    }}
    QPushButton#MsGhostBtn {{
        background-color: {c['ghost_bg']}; color: {c['text']}; border: 0px;
        border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px; padding: 5px 10px;
    }}
    QPushButton#MsGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
    QPushButton#MsDelBtn {{
        background-color: transparent; color: {c['text_sec']}; border: 0px;
        font-size: 13px; font-weight: bold;
    }}
    QPushButton#MsDelBtn:hover {{ color: {c['danger']}; }}
    """


# ============== 多条发送弹窗 ==============
class MultiSendDialog(QDialog):
    """多条自定义发送，支持分组(左侧列表)：每行一条命令 + 名称 + 独立延时 + HEX/换行/校验。
    可逐条点「发送」，也可勾选多条后「循环发送」按每行延时依次轮发。分组与命令持久化。"""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(app._t("multi_send_title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(900, 400)
        self.resize(1040, 480)
        self._rows = []
        self._populating = False
        self._edit_idx = 0      # 编辑哪个分组（数据存于 app._ms_groups，循环在主界面）
        # 去抖：连敲键时合并存盘+重建，避免每个字符都 sync 磁盘/重建快捷栏卡顿
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._commit_now)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ===== 左侧：分组列表 =====
        left = QVBoxLayout()
        left.setSpacing(6)
        grp_btns = QHBoxLayout()
        grp_btns.setSpacing(6)
        self.btn_new_group = QPushButton(app._t("kw_new_group"))
        self.btn_new_group.setObjectName("MsGhostBtn")
        self.btn_new_group.setMinimumHeight(30)
        self.btn_new_group.clicked.connect(self._new_group)
        grp_btns.addWidget(self.btn_new_group, 1)
        self.btn_del_group = QPushButton(app._t("kw_del_group"))
        self.btn_del_group.setObjectName("MsGhostBtn")
        self.btn_del_group.setMinimumHeight(30)
        self.btn_del_group.clicked.connect(self._delete_group)
        grp_btns.addWidget(self.btn_del_group, 1)
        left.addLayout(grp_btns)
        self.list_groups = QListWidget()
        self.list_groups.setObjectName("KwGroupList")
        self.list_groups.currentRowChanged.connect(self._on_group_row_changed)
        self.list_groups.itemChanged.connect(self._on_group_renamed)
        self.list_groups.itemDoubleClicked.connect(self.list_groups.editItem)
        left.addWidget(self.list_groups, 1)
        self.lbl_group_tip = QLabel(app._t("kw_group_tip"))
        self.lbl_group_tip.setObjectName("MsHint")
        self.lbl_group_tip.setWordWrap(True)
        left.addWidget(self.lbl_group_tip)
        left_host = QWidget()
        left_host.setLayout(left)
        left_host.setFixedWidth(180)
        root.addWidget(left_host)

        # ===== 右侧：当前分组的命令 =====
        right = QVBoxLayout()
        right.setSpacing(10)
        scroll, self._list_host, self._list_v = _make_list_scroll()
        right.addWidget(scroll, 1)

        self.btn_add = QPushButton(app._t("ms_add"))
        self.btn_add.setObjectName("MsGhostBtn")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.clicked.connect(lambda *_: (self._add_row(), self._commit_now()))
        right.addWidget(self.btn_add)

        self.lbl_hint = QLabel(app._t("ms_hint"))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setObjectName("MsHint")
        right.addWidget(self.lbl_hint)
        root.addLayout(right, 1)

        self.refresh_theme()
        self._reload_group_list()
        self._reload_rows()

    # ----- 分组管理（左侧列表）-----
    @property
    def _groups(self):
        """分组数据存于主窗口(与发送区快捷栏共享)，弹窗只是编辑器。"""
        return self.app._ms_groups

    def _reload_group_list(self):
        self._populating = True
        self.list_groups.clear()
        for i, g in enumerate(self._groups):
            item = QListWidgetItem(g.get("name", f"组{i + 1}"))
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.list_groups.addItem(item)
        if not (0 <= self._edit_idx < len(self._groups)):
            self._edit_idx = 0
        self.list_groups.setCurrentRow(self._edit_idx)
        self._populating = False
        self.btn_del_group.setEnabled(len(self._groups) > 1)

    def _on_group_row_changed(self, row):
        if self._populating or row < 0:
            return
        if self._save_timer.isActive():     # 切组前把上一组未提交的编辑落盘，避免丢失
            self._commit_now()
        self._edit_idx = row
        self._reload_rows()

    def _on_group_renamed(self, item):
        if self._populating:
            return
        row = self.list_groups.row(item)
        if not (0 <= row < len(self._groups)):
            return
        name = item.text().strip()
        if not name:
            self._populating = True
            item.setText(self._groups[row].get("name", ""))
            self._populating = False
            return
        self._groups[row]["name"] = name
        self.app._ms_groups_changed()

    def _new_group(self):
        if self._save_timer.isActive():   # 先把当前组未提交编辑落盘
            self._commit_now()
        base = self.app._t("kw_new_group_default")
        existing = {g.get("name") for g in self._groups}
        name, n = base, 1
        while name in existing:
            n += 1
            name = f"{base}{n}"
        self._groups.append({"name": name, "items": []})
        self._edit_idx = len(self._groups) - 1
        self.app._ms_groups_changed()
        self._reload_group_list()
        self._reload_rows()
        item = self.list_groups.item(self._edit_idx)
        if item:
            self.list_groups.editItem(item)

    def _delete_group(self):
        if len(self._groups) <= 1:
            self.app.toast(self.app._t("kw_group_min"), error=True)
            return
        self._save_timer.stop()    # 当前组将被删，丢弃其待提交编辑
        d = self._edit_idx
        self._groups.pop(d)
        # 同步主窗口选中分组索引的偏移（删除项在其之前/即其本身时）
        if self.app._ms_group_idx == d:
            self.app._ms_group_idx = min(d, len(self._groups) - 1)
        elif self.app._ms_group_idx > d:
            self.app._ms_group_idx -= 1
        self._edit_idx = min(d, len(self._groups) - 1)
        self.app._ms_groups_changed()
        self._reload_group_list()
        self._reload_rows()

    # ----- 命令行管理 -----
    def _add_row(self, data="", checked=False, hex_on=False, nl=0, cs=0,
                 name="", delay=1000):
        frame = QFrame()
        frame.setObjectName("MsRow")
        h = QHBoxLayout(frame)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)
        chk = QCheckBox()
        chk.setChecked(checked)
        chk.stateChanged.connect(self._save)
        h.addWidget(chk)
        ed_name = QLineEdit(name)
        ed_name.setPlaceholderText(self.app._t("ms_name_ph"))
        ed_name.setFixedWidth(82)
        ed_name.textChanged.connect(self._save)
        h.addWidget(ed_name)
        edit = QLineEdit(data)
        edit.setPlaceholderText(self.app._t("ms_placeholder"))
        edit.textChanged.connect(self._save)
        h.addWidget(edit, 1)
        ed_delay = QLineEdit(str(delay))
        ed_delay.setFixedWidth(58)
        ed_delay.setToolTip(self.app._t("ms_delay_tip"))
        ed_delay.setPlaceholderText("ms")
        ed_delay.textChanged.connect(self._save)
        h.addWidget(ed_delay)
        cb_hex = QCheckBox("HEX")
        cb_hex.setChecked(hex_on)
        cb_hex.stateChanged.connect(self._save)
        h.addWidget(cb_hex)
        cb_nl = QComboBox()
        cb_nl.addItems([self.app._t("ms_nl_none"), "CRLF", "LF", "CR"])
        cb_nl.setCurrentIndex(nl)
        cb_nl.setFixedWidth(66)
        cb_nl.currentIndexChanged.connect(self._save)
        h.addWidget(cb_nl)
        cb_cs = QComboBox()
        cb_cs.addItems([self.app._t(k) for k in CHECKSUM_KEYS])
        cb_cs.setCurrentIndex(cs)
        cb_cs.setFixedWidth(104)
        cb_cs.currentIndexChanged.connect(self._save)
        h.addWidget(cb_cs)
        btn_send = QPushButton(self.app._t("ms_send_one"))
        btn_send.setObjectName("MsSendBtn")
        row = {"frame": frame, "chk": chk, "name": ed_name, "edit": edit,
               "delay": ed_delay, "hex": cb_hex, "nl": cb_nl, "cs": cb_cs}
        btn_send.clicked.connect(lambda _=False, r=row: self._send_row(r))
        h.addWidget(btn_send)
        btn_del = QPushButton("✕")
        btn_del.setObjectName("MsDelBtn")
        btn_del.setFixedWidth(28)
        btn_del.clicked.connect(lambda _=False, r=row: self._del_row(r))
        h.addWidget(btn_del)
        self._list_v.insertWidget(self._list_v.count() - 1, frame)
        self._rows.append(row)

    def _row_delay(self, row):
        try:
            return max(0, int(row["delay"].text()))
        except (ValueError, TypeError):
            return 1000

    def _row_params(self, row):
        """(数据, hex_mode, newline 0-3, checksum 索引, 延时 ms)"""
        return (row["edit"].text(), row["hex"].isChecked(),
                row["nl"].currentIndex(), row["cs"].currentIndex(),
                self._row_delay(row))

    def _send_row(self, row):
        data, hx, nl, cs, _d = self._row_params(row)
        self.app._send_text(data, hex_mode=hx, newline=nl, checksum=cs)

    def _del_row(self, row):
        row["frame"].setParent(None)
        row["frame"].deleteLater()
        if row in self._rows:
            self._rows.remove(row)
        self._commit_now()

    # ----- 持久化（写回主窗口分组 + 同步快捷栏）-----
    def _row_dict(self, r):
        return {"name": r["name"].text(), "data": r["edit"].text(),
                "checked": r["chk"].isChecked(), "delay": self._row_delay(r),
                "hex": r["hex"].isChecked(), "nl": r["nl"].currentIndex(),
                "cs": r["cs"].currentIndex()}

    def _save(self):
        """行内编辑触发：去抖，300ms 内合并多次按键为一次落盘+重建。"""
        self._save_timer.start()

    def _commit_now(self):
        """把当前行写回编辑分组，并刷新主界面快捷栏/下拉（去抖后或结构性操作时立即调用）。"""
        self._save_timer.stop()
        if 0 <= self._edit_idx < len(self._groups):
            self._groups[self._edit_idx]["items"] = [self._row_dict(r) for r in self._rows]
        self.app._ms_groups_changed()

    def _reload_rows(self):
        for r in self._rows:
            r["frame"].setParent(None)
            r["frame"].deleteLater()
        self._rows = []
        items = []
        if 0 <= self._edit_idx < len(self._groups):
            items = self._groups[self._edit_idx]["items"]
        if not items:
            items = [{"data": "", "checked": False}]
        for it in items:
            self._add_row(str(it.get("data", "")), bool(it.get("checked", False)),
                          bool(it.get("hex", False)), int(it.get("nl", 0)),
                          int(it.get("cs", 0)), str(it.get("name", "")),
                          int(it.get("delay", 1000)))
        self.refresh_theme()

    def closeEvent(self, e):
        self._commit_now()    # 关窗时立即落盘待提交编辑
        super().closeEvent(e)

    # ----- 主题 / 语言 -----
    def retranslate(self):
        self.setWindowTitle(self.app._t("multi_send_title"))
        self.btn_add.setText(self.app._t("ms_add"))
        self.lbl_hint.setText(self.app._t("ms_hint"))
        self.btn_new_group.setText(self.app._t("kw_new_group"))
        self.btn_del_group.setText(self.app._t("kw_del_group"))
        self.lbl_group_tip.setText(self.app._t("kw_group_tip"))
        for r in self._rows:
            r["edit"].setPlaceholderText(self.app._t("ms_placeholder"))
            r["name"].setPlaceholderText(self.app._t("ms_name_ph"))
            r["delay"].setToolTip(self.app._t("ms_delay_tip"))
            r["nl"].setItemText(0, self.app._t("ms_nl_none"))
            cs_idx = r["cs"].currentIndex()
            r["cs"].blockSignals(True)
            for i, k in enumerate(CHECKSUM_KEYS):
                r["cs"].setItemText(i, self.app._t(k))
            r["cs"].setCurrentIndex(cs_idx)
            r["cs"].blockSignals(False)

    def _apply_titlebar_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")

    def refresh_theme(self):
        self._apply_titlebar_theme()
        c = chrome_for(self.app._theme_id())
        self.setStyleSheet(_dialog_list_qss(c) + f"""
        QPushButton#MsPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 13px; font-weight: 600;
            padding: 6px 14px;
        }}
        QPushButton#MsPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#MsPrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#MsSendBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 12px; padding: 4px 12px;
        }}
        QPushButton#MsSendBtn:hover {{ background-color: {c['accent_hover']}; }}
        QListWidget#KwGroupList {{
            background-color: {c['input_bg']}; border: 1px solid {c['separator']};
            border-radius: 8px; color: {c['text']};
            font-family: 'Segoe UI'; font-size: 12px; outline: 0px; padding: 3px;
        }}
        QListWidget#KwGroupList::item {{ padding: 5px 6px; border-radius: 5px; }}
        QListWidget#KwGroupList::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
        QListWidget#KwGroupList::item:hover {{ background-color: {c['ghost_hover']}; }}
        QListWidget#KwGroupList QLineEdit {{
            background-color: {c['input_focus_bg']}; color: {c['text']};
            border: 1px solid {c['accent']}; border-radius: 4px; padding: 1px 4px;
            selection-background-color: {c['accent']}; selection-color: #FFFFFF;
        }}
        """)
        for r in getattr(self, "_rows", []):
            for key in ("nl", "cs"):
                popup = r[key].view().window()
                popup.setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")


# ============== 关键字高亮配置弹窗 ==============
class KeywordHighlightDialog(QDialog):
    """配置多条关键字高亮：每条选 背景/文字 着色 + 颜色。
    区分大小写子串匹配，RX/TX 都高亮；规则持久化、即时生效。"""
    PRESET_COLORS = ["#FFD60A", "#FF453A", "#32D74B", "#0A84FF", "#BF5AF2", "#FF9F0A"]

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(app._t("kw_title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(720, 380)
        self.resize(860, 460)
        self._rows = []
        self._populating = False    # 编程填充分组列表时忽略 itemChanged(重命名)
        # 去抖：连敲键时合并落盘+全量重扫高亮，避免每个字符都 sync+重扫卡顿
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(300)
        self._commit_timer.timeout.connect(self._commit_now)
        # 编辑目标分组（与主界面「生效分组」独立）：默认编辑当前生效分组，关闭时编辑第一个
        self._edit_idx = (app._keyword_active
                          if 0 <= app._keyword_active < len(app._keyword_groups) else 0)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ===== 左侧：分组列表（仿 SuperCom）=====
        left = QVBoxLayout()
        left.setSpacing(6)
        # 新建 / 删除 并排一行
        grp_btns = QHBoxLayout()
        grp_btns.setSpacing(6)
        self.btn_new_group = QPushButton(app._t("kw_new_group"))
        self.btn_new_group.setObjectName("MsGhostBtn")
        self.btn_new_group.setMinimumHeight(30)
        self.btn_new_group.clicked.connect(self._new_group)
        grp_btns.addWidget(self.btn_new_group, 1)
        self.btn_del_group = QPushButton(app._t("kw_del_group"))
        self.btn_del_group.setObjectName("MsGhostBtn")
        self.btn_del_group.setMinimumHeight(30)
        self.btn_del_group.clicked.connect(self._delete_group)
        grp_btns.addWidget(self.btn_del_group, 1)
        left.addLayout(grp_btns)
        self.list_groups = QListWidget()
        self.list_groups.setObjectName("KwGroupList")
        self.list_groups.currentRowChanged.connect(self._on_group_row_changed)
        self.list_groups.itemChanged.connect(self._on_group_renamed)
        self.list_groups.itemDoubleClicked.connect(self.list_groups.editItem)
        left.addWidget(self.list_groups, 1)
        self.lbl_group_tip = QLabel(app._t("kw_group_tip"))
        self.lbl_group_tip.setObjectName("MsHint")
        self.lbl_group_tip.setWordWrap(True)
        left.addWidget(self.lbl_group_tip)
        left_host = QWidget()
        left_host.setLayout(left)
        left_host.setFixedWidth(180)
        root.addWidget(left_host)

        # ===== 右侧：当前分组的规则 =====
        right = QVBoxLayout()
        right.setSpacing(10)
        scroll, self._list_host, self._list_v = _make_list_scroll()
        right.addWidget(scroll, 1)
        self.btn_add = QPushButton(app._t("kw_add"))
        self.btn_add.setObjectName("MsGhostBtn")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.clicked.connect(lambda *_: self._on_add())
        right.addWidget(self.btn_add)
        self.lbl_hint = QLabel(app._t("kw_hint"))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setObjectName("MsHint")
        right.addWidget(self.lbl_hint)
        root.addLayout(right, 1)

        self.refresh_theme()
        self._reload_group_list()
        self._reload_rows()

    # ----- 行管理 -----
    def _on_add(self):
        # 新加行默认不勾选(与首次默认行一致)：用户填好关键字后再手动启用
        color = self.PRESET_COLORS[len(self._rows) % len(self.PRESET_COLORS)]
        self._add_row("", "bg", color, False)
        self._commit_now()

    _SCOPES = ("both", "rx", "tx")

    def _add_row(self, pattern="", mode="bg", color="#FFD60A", enabled=True, scope="both"):
        frame = QFrame()
        frame.setObjectName("MsRow")
        h = QHBoxLayout(frame)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)
        chk = QCheckBox()
        chk.setChecked(enabled)
        chk.stateChanged.connect(self._commit)
        h.addWidget(chk)
        edit = QLineEdit(pattern)
        edit.setPlaceholderText(self.app._t("kw_placeholder"))
        edit.textChanged.connect(self._commit)
        h.addWidget(edit, 1)
        cb_scope = QComboBox()
        cb_scope.addItems([self.app._t("kw_scope_both"), self.app._t("kw_scope_rx"),
                           self.app._t("kw_scope_tx")])
        cb_scope.setCurrentIndex(self._SCOPES.index(scope) if scope in self._SCOPES else 0)
        cb_scope.setFixedWidth(74)
        cb_scope.currentIndexChanged.connect(self._commit)
        h.addWidget(cb_scope)
        cb_mode = QComboBox()
        cb_mode.addItems([self.app._t("kw_mode_bg"), self.app._t("kw_mode_fg")])
        cb_mode.setCurrentIndex(0 if mode == "bg" else 1)
        cb_mode.setFixedWidth(78)
        cb_mode.currentIndexChanged.connect(self._commit)
        h.addWidget(cb_mode)
        btn_color = QPushButton()
        btn_color.setObjectName("KwColorBtn")
        btn_color.setFixedSize(40, 24)
        btn_color.setCursor(Qt.PointingHandCursor)
        row = {"frame": frame, "chk": chk, "edit": edit, "scope": cb_scope,
               "mode": cb_mode, "color": color, "colorbtn": btn_color}
        self._paint_color_btn(row)
        btn_color.clicked.connect(lambda _=False, r=row: self._pick_color(r))
        h.addWidget(btn_color)
        btn_del = QPushButton("✕")
        btn_del.setObjectName("MsDelBtn")
        btn_del.setFixedWidth(28)
        btn_del.clicked.connect(lambda _=False, r=row: self._del_row(r))
        h.addWidget(btn_del)
        self._list_v.insertWidget(self._list_v.count() - 1, frame)
        self._rows.append(row)

    def _paint_color_btn(self, row):
        row["colorbtn"].setStyleSheet(
            f"QPushButton#KwColorBtn {{ background-color: {row['color']};"
            f" border: 1px solid rgba(128,128,128,0.5); border-radius: 5px; }}")

    def _pick_color(self, row):
        col = QColorDialog.getColor(QColor(row["color"]), self, self.app._t("kw_color"))
        if col.isValid():
            row["color"] = col.name()
            self._paint_color_btn(row)
            self._commit_now()

    def _del_row(self, row):
        row["frame"].setParent(None)
        row["frame"].deleteLater()
        if row in self._rows:
            self._rows.remove(row)
        self._commit_now()

    # ----- 分组管理（左侧列表）-----
    def _reload_group_list(self):
        """用各分组名重建左侧列表，选中当前编辑分组。双击列表项可改名。"""
        self._populating = True
        self.list_groups.clear()
        for i, g in enumerate(self.app._keyword_groups):
            item = QListWidgetItem(g.get("name", f"组{i + 1}"))
            item.setFlags(item.flags() | Qt.ItemIsEditable)   # 双击改名
            self.list_groups.addItem(item)
        if not (0 <= self._edit_idx < len(self.app._keyword_groups)):
            self._edit_idx = 0
        self.list_groups.setCurrentRow(self._edit_idx)
        self._populating = False
        self.btn_del_group.setEnabled(len(self.app._keyword_groups) > 1)  # 至少保留一个

    def _on_group_row_changed(self, row):
        if self._populating or row < 0:
            return
        if self._commit_timer.isActive():   # 切组前把上一组未提交的编辑落盘
            self._commit_now()
        self._edit_idx = row
        self._reload_rows()

    def _on_group_renamed(self, item):
        """双击改名提交：写回分组名并同步主下拉。"""
        if self._populating:
            return
        row = self.list_groups.row(item)
        if not (0 <= row < len(self.app._keyword_groups)):
            return
        name = item.text().strip()
        if not name:   # 空名还原
            self._populating = True
            item.setText(self.app._keyword_groups[row].get("name", ""))
            self._populating = False
            return
        self.app._keyword_groups[row]["name"] = name
        self.app._kw_groups_changed()   # 存盘 + 重建主界面分组下拉

    def _new_group(self):
        if self._commit_timer.isActive():   # 先把当前组未提交编辑落盘
            self._commit_now()
        # 起个不重复的默认名，加进列表并进入改名状态(贴近 SuperCom 流程)
        base = self.app._t("kw_new_group_default")
        existing = {g.get("name") for g in self.app._keyword_groups}
        name, n = base, 1
        while name in existing:
            n += 1
            name = f"{base}{n}"
        self.app._keyword_groups.append({"name": name, "rules": []})
        self._edit_idx = len(self.app._keyword_groups) - 1
        self.app._kw_groups_changed()
        self._reload_group_list()
        self._reload_rows()
        item = self.list_groups.item(self._edit_idx)
        if item:
            self.list_groups.editItem(item)   # 直接改名

    def _delete_group(self):
        if len(self.app._keyword_groups) <= 1:
            self.app.toast(self.app._t("kw_group_min"), error=True)
            return
        self._commit_timer.stop()   # 当前组将被删，丢弃其待提交编辑
        d = self._edit_idx
        self.app._keyword_groups.pop(d)
        # 调整生效分组索引
        if self.app._keyword_active == d:
            self.app._keyword_active = -1
        elif self.app._keyword_active > d:
            self.app._keyword_active -= 1
        self._edit_idx = min(d, len(self.app._keyword_groups) - 1)
        self.app._kw_groups_changed()
        self._reload_group_list()
        self._reload_rows()

    # ----- 规则行 应用 / 加载 -----
    def _commit(self):
        """行内编辑触发：去抖，300ms 内合并多次按键为一次落盘+全量重扫高亮。"""
        self._commit_timer.start()

    def _commit_now(self):
        self._commit_timer.stop()
        rules = [
            {"pattern": r["edit"].text(),
             "mode": "bg" if r["mode"].currentIndex() == 0 else "fg",
             "scope": self._SCOPES[r["scope"].currentIndex()],
             "color": r["color"],
             "enabled": r["chk"].isChecked()}
            for r in self._rows]
        if 0 <= self._edit_idx < len(self.app._keyword_groups):
            self.app._keyword_groups[self._edit_idx]["rules"] = rules
        self.app._apply_keyword_rules()   # 存盘 + 刷新(若编辑的是生效分组即时见效)

    def _reload_rows(self):
        """清掉现有行，载入当前编辑分组的规则。"""
        for r in self._rows:
            r["frame"].setParent(None)
            r["frame"].deleteLater()
        self._rows = []
        rules = []
        if 0 <= self._edit_idx < len(self.app._keyword_groups):
            rules = self.app._keyword_groups[self._edit_idx]["rules"]
        if not rules:
            # 空分组给一条占位行(不勾选、不写回，等用户填了再 commit)
            rules = [{"pattern": "", "mode": "bg",
                      "color": self.PRESET_COLORS[0], "enabled": False, "scope": "both"}]
        for r in rules:
            self._add_row(str(r.get("pattern", "")), r.get("mode", "bg"),
                          r.get("color", "#FFD60A"), bool(r.get("enabled", True)),
                          r.get("scope", "both"))
        # 给新行的下拉弹出容器/颜色块刷主题色
        self.refresh_theme()

    def closeEvent(self, e):
        if self._commit_timer.isActive():   # 关窗时立即落盘待提交编辑
            self._commit_now()
        super().closeEvent(e)

    # ----- 主题 / 语言 -----
    def retranslate(self):
        self.setWindowTitle(self.app._t("kw_title"))
        self.btn_add.setText(self.app._t("kw_add"))
        self.lbl_hint.setText(self.app._t("kw_hint"))
        self.btn_new_group.setText(self.app._t("kw_new_group"))
        self.btn_del_group.setText(self.app._t("kw_del_group"))
        self.lbl_group_tip.setText(self.app._t("kw_group_tip"))
        for r in self._rows:
            r["edit"].setPlaceholderText(self.app._t("kw_placeholder"))
            idx = r["mode"].currentIndex()
            r["mode"].blockSignals(True)
            r["mode"].setItemText(0, self.app._t("kw_mode_bg"))
            r["mode"].setItemText(1, self.app._t("kw_mode_fg"))
            r["mode"].setCurrentIndex(idx)
            r["mode"].blockSignals(False)
            sidx = r["scope"].currentIndex()
            r["scope"].blockSignals(True)
            r["scope"].setItemText(0, self.app._t("kw_scope_both"))
            r["scope"].setItemText(1, self.app._t("kw_scope_rx"))
            r["scope"].setItemText(2, self.app._t("kw_scope_tx"))
            r["scope"].setCurrentIndex(sidx)
            r["scope"].blockSignals(False)

    def _apply_titlebar_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")

    def refresh_theme(self):
        self._apply_titlebar_theme()
        c = chrome_for(self.app._theme_id())
        # 公共列表样式 + 左侧分组列表(QListWidget)样式
        self.setStyleSheet(_dialog_list_qss(c) + f"""
        QListWidget#KwGroupList {{
            background-color: {c['input_bg']};
            border: 1px solid {c['separator']};
            border-radius: 8px;
            color: {c['text']};
            font-family: 'Segoe UI'; font-size: 12px;
            outline: 0px;
            padding: 3px;
        }}
        QListWidget#KwGroupList::item {{ padding: 5px 6px; border-radius: 5px; }}
        QListWidget#KwGroupList::item:selected {{
            background-color: {c['accent']}; color: #FFFFFF;
        }}
        QListWidget#KwGroupList::item:hover {{ background-color: {c['ghost_hover']}; }}
        QListWidget#KwGroupList QLineEdit {{
            background-color: {c['input_focus_bg']};
            color: {c['text']};
            border: 1px solid {c['accent']};
            border-radius: 4px;
            padding: 1px 4px;
            selection-background-color: {c['accent']};
            selection-color: #FFFFFF;
        }}
        """)
        for r in self._rows:                       # 颜色按钮保持各自底色
            self._paint_color_btn(r)
            for key in ("mode", "scope"):
                popup = r[key].view().window()
                popup.setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")


