# -*- coding: utf-8 -*-
"""对话框：CloseDialog / MultiSendDialog / KeywordHighlightDialog + 共享样式 helper。"""
import sys
from PyQt5.QtCore import Qt, QTimer, QUrl, QMimeData, QEvent, QPoint
from PyQt5.QtGui import QColor, QDesktopServices, QDrag, QFont, QFontMetrics, QIntValidator
from PyQt5.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QFrame, QLineEdit,
                             QCheckBox, QComboBox, QHBoxLayout, QVBoxLayout, QScrollArea,
                             QGraphicsDropShadowEffect, QColorDialog,
                             QListWidget, QListWidgetItem, QSplitter,
                             QTableWidget, QHeaderView, QAbstractItemView, QFileDialog, QMenu)
from theme import chrome_for, THEME_DEFAULT
import seq_context
import sequence_dataset
import junit_report
from i18n import CHECKSUM_KEYS
from fonts import ui_font, localize_qss
from updater import UpdateChecker, UpdateDownloader, run_installer
from ui_tips import set_tooltip


# ============== 无边框对话框「按住空白处拖动」混入 ==============
class _DragFramelessMixin:
    """无边框对话框没有标题栏 → 默认拖不动。按住卡片空白处即可拖动（按钮各自吃掉点击，不受影响）。
    注意：只有「会消费鼠标事件」的控件（按钮/输入框/下拉等）点击时不触发拖动；若日后在卡片里放了
    QLabel 等不消费事件的控件，点它也会拖动——届时给该控件设 setAttribute(WA_TransparentForMouseEvents)
    或在此判断 childAt() 排除。当前 CloseDialog/AboutDialog 只有按钮+标签且标签区域可拖动是预期行为。"""
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_off = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and getattr(self, "_drag_off", None) is not None:
            self.move(event.globalPos() - self._drag_off)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_off = None
        super().mouseReleaseEvent(event)


# ============== 关闭确认对话框 (iOS 风格) ==============
class CloseDialog(_DragFramelessMixin, QDialog):
    """无边框 + 圆角白底 + 居中标题 + 3 个并排按钮"""
    RESULT_MIN = 1
    RESULT_QUIT = 2
    RESULT_CANCEL = 0

    def __init__(self, title_text: str, btn_min_text: str,
                 btn_quit_text: str, btn_cancel_text: str,
                 theme_id: str = THEME_DEFAULT, parent=None):
        super().__init__(parent)
        _flags = Qt.Dialog | Qt.FramelessWindowHint
        if sys.platform == "darwin":
            _flags |= Qt.NoDropShadowWindowHint  # 关掉 macOS 给无边框窗口的矩形系统阴影（与圆角卡片冲突）
        self.setWindowFlags(_flags)
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
        self.lbl_title.setFont(ui_font(14, bold=True))
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

        self.setStyleSheet(localize_qss(self._build_qss()))
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
        QCheckBox {{ color: {c['text']}; background: transparent;
            font-family: 'Segoe UI'; font-size: 12px; spacing: 6px; }}
        QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 3px;
            border: 1px solid {c['separator']}; background-color: {c['input_bg']}; }}
        QCheckBox::indicator:hover {{ border: 1px solid {c['accent']}; }}
        QCheckBox::indicator:checked {{ background-color: {c['accent']}; border: 1px solid {c['accent']}; }}
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


# ============== 关于 + 检查更新 对话框 ==============
class AboutDialog(_DragFramelessMixin, QDialog):
    """无边框圆角卡：图标 + 名称 + 版本 + 简介 + 「检查更新」。
    tr: 主窗口翻译函数 _t；app_name/version；icon：QIcon；on_quit：去装更新前退出 app 的回调。"""

    def __init__(self, tr, app_name, version, icon=None,
                 theme_id=THEME_DEFAULT, on_quit=None,
                 auto_check=True, on_auto_check_changed=None, parent=None):
        super().__init__(parent)
        self._tr = tr
        self._version = version
        self._theme_id = theme_id
        self._on_quit = on_quit
        self._on_auto_check_changed = on_auto_check_changed
        self._checker = None
        self._downloader = None
        self._dl_url = ""          # Windows 下载直链(也用于推 releases 页 tag)
        self._dl_cands = []        # 本平台下载候选(逐个试)：Win=[url]，mac=url_mac 列表
        self._dl_idx = 0
        _flags = Qt.Dialog | Qt.FramelessWindowHint
        if sys.platform == "darwin":
            _flags |= Qt.NoDropShadowWindowHint  # 关掉 macOS 给无边框窗口的矩形系统阴影（与圆角卡片冲突）
        self.setWindowFlags(_flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

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
        v.setContentsMargins(28, 22, 28, 20)
        v.setSpacing(12)
        c = chrome_for(theme_id)

        if icon is not None:
            li = QLabel()
            li.setPixmap(icon.pixmap(64, 64))
            li.setAlignment(Qt.AlignCenter)
            v.addWidget(li)

        ln = QLabel(app_name)
        ln.setFont(ui_font(16, bold=True))
        ln.setAlignment(Qt.AlignCenter)
        ln.setStyleSheet(f"color: {c['text']}; background: transparent;")
        v.addWidget(ln)

        lv = QLabel(f"v{version}")
        lv.setAlignment(Qt.AlignCenter)
        lv.setStyleSheet(f"color: {c['text_sec']}; background: transparent; font-size: 12px;")
        v.addWidget(lv)

        ld = QLabel(tr("about_desc"))
        ld.setAlignment(Qt.AlignCenter)
        ld.setWordWrap(True)
        ld.setStyleSheet(f"color: {c['text_sec']}; background: transparent; font-size: 11px;")
        v.addWidget(ld)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setTextInteractionFlags(Qt.TextSelectableByMouse)  # 更新说明可选中复制
        self.lbl_status.setStyleSheet(f"color: {c['text']}; background: transparent; font-size: 11px;")
        # 放进限高滚动区：更新说明很长时(notes 多行)在区内滚动，对话框高度受控、不裁切文字/图标
        self._status_scroll = QScrollArea()
        self._status_scroll.setWidget(self.lbl_status)
        self._status_scroll.setWidgetResizable(True)
        self._status_scroll.setFrameShape(QFrame.NoFrame)
        self._status_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._status_scroll.setMaximumHeight(200)
        self._status_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:0;}"
            "QScrollArea>QWidget>QWidget{background:transparent;}")
        self._status_scroll.viewport().setAutoFillBackground(False)
        self.lbl_status.setAutoFillBackground(False)
        self._status_scroll.hide()
        v.addWidget(self._status_scroll)

        h = QHBoxLayout()
        h.setSpacing(10)
        self.btn_check = QPushButton(tr("check_update"))
        self.btn_check.setObjectName("DialogPrimaryBtn")
        self.btn_check.setMinimumHeight(36)
        self.btn_check.clicked.connect(self._check)
        h.addWidget(self.btn_check, 1)
        self.btn_action = QPushButton(tr("update_download"))
        self.btn_action.setObjectName("DialogPrimaryBtn")
        self.btn_action.setMinimumHeight(36)
        self.btn_action.clicked.connect(self._download)
        self.btn_action.hide()
        h.addWidget(self.btn_action, 1)
        self.btn_close = QPushButton(tr("close_cancel"))
        self.btn_close.setObjectName("DialogGhostBtn")
        self.btn_close.setMinimumHeight(36)
        self.btn_close.clicked.connect(self.reject)
        h.addWidget(self.btn_close, 1)
        v.addLayout(h)

        # 「自动检查更新」开关：勾上则启动后静默查、有新版在主窗右下角版本号亮可点徽标
        self.cb_auto = QCheckBox(tr("auto_check_update"))
        self.cb_auto.setChecked(bool(auto_check))
        self.cb_auto.setCursor(Qt.PointingHandCursor)
        self.cb_auto.toggled.connect(self._on_auto_toggled)
        ha = QHBoxLayout()
        ha.addStretch(1)
        ha.addWidget(self.cb_auto)
        ha.addStretch(1)
        v.addLayout(ha)

        outer.addWidget(self._card)
        self.setStyleSheet(localize_qss(CloseDialog._build_qss(self)))
        self.setMinimumWidth(340)

    def _on_auto_toggled(self, on):
        if self._on_auto_check_changed:
            self._on_auto_check_changed(bool(on))

    def _set_status(self, text):
        self.lbl_status.setText(text)
        self._status_scroll.setVisible(bool(text))
        # 文本变化(尤其长 notes)后让对话框按内容重算高度。滚动区已限高 200px，
        # 不会无限撑高；adjustSize 修了"长说明被裁、图标顶部被挤掉"的问题。
        self.adjustSize()

    # ----- 检查 -----
    def _check(self):
        self.btn_check.setEnabled(False)
        self._set_status(self._tr("update_checking"))
        self._checker = UpdateChecker(self._version, self)
        self._checker.finished.connect(self._on_checked)
        self._checker.start()

    def _on_checked(self, info, err):
        self.btn_check.setEnabled(True)
        if info is None:
            self._set_status(self._tr("update_failed", e=err))
            return
        if not info.get("newer"):
            self._set_status(self._tr("update_latest", ver=info["version"]))
            return
        self._dl_url = info.get("url", "")
        # 本平台下载候选：mac 用 url_mac(可为字符串或多源列表，逐个试)，其余用 url。仅收 https。
        raw = info.get("url_mac", "") if sys.platform == "darwin" else self._dl_url
        raw = [raw] if isinstance(raw, str) else (list(raw) if isinstance(raw, (list, tuple)) else [])
        self._dl_cands = [u for u in raw if isinstance(u, str) and u.lower().startswith("https://")]
        txt = self._tr("update_found", ver=info["version"])
        if info.get("notes"):
            txt += "\n" + info["notes"]
        self._set_status(txt)
        if self._dl_url:
            self.btn_check.hide()
            self.btn_action.show()

    # ----- 下载 + 安装 -----
    def _download(self):
        # Windows: 下载 Setup.exe → 跑安装向导；macOS: 下载 dmg → 打开挂载(拖入应用程序)。
        # 下载地址按候选逐个试(mac 多源：Gitee 优先 + GitHub 兜底)。
        if not self._dl_cands:
            # 无平台专用直链(如老清单缺 url_mac) → 打开 releases 页兜底
            if sys.platform != "win32" and self._dl_url:
                QDesktopServices.openUrl(QUrl(self._releases_page_url()))
                self._set_status(self._tr("update_open_page"))
            return
        self._dl_idx = 0
        self._start_download()

    def _start_download(self):
        self.btn_action.setEnabled(False)
        self._set_status(self._tr("update_downloading", pct=0))
        self._downloader = UpdateDownloader(self._dl_cands[self._dl_idx], self)
        self._downloader.progress.connect(self._on_progress)
        self._downloader.finished.connect(self._on_downloaded)
        self._downloader.start()

    def _releases_page_url(self):
        """打开 GitHub releases 的 tag 页(含各平台包，尤其 mac 的 .dmg —— Gitee 按策略只放
        Setup.exe，故不指 Gitee 页)。从下载直链取 tag，拼固定 GitHub 仓库；取不到则退回原链接。"""
        url = self._dl_url or ""
        marker = "/releases/download/"
        if marker in url:
            tag = url.split(marker, 1)[1].split("/", 1)[0]
            return f"https://github.com/heropml/SerialTool/releases/tag/{tag}"
        return url

    def _on_progress(self, rec, total):
        pct = int(rec * 100 / total) if total > 0 else 0
        self._set_status(self._tr("update_downloading", pct=pct))

    def _on_downloaded(self, path, err):
        if not path:
            self._dl_idx += 1
            if self._dl_idx < len(self._dl_cands):
                self._start_download()          # 换下一个源重试(如 Gitee 失败→GitHub)
                return
            if sys.platform != "win32" and self._dl_url:
                # 所有直链都下载失败 → 打开 releases 页让用户手动下
                QDesktopServices.openUrl(QUrl(self._releases_page_url()))
                self._set_status(self._tr("update_open_page"))
            else:
                self._set_status(self._tr("update_dl_failed", e=err))
            self.btn_action.setEnabled(True)   # 两条失败路径都恢复「更新」按钮，避免卡灰
            return
        if sys.platform == "win32":
            self._set_status(self._tr("update_installing"))
            if run_installer(path):
                if self._on_quit:
                    QTimer.singleShot(500, self._on_quit)
            else:
                self._set_status(self._tr("update_dl_failed", e="installer launch failed"))
                self.btn_action.setEnabled(True)
        else:
            # macOS: 打开下载好的 .dmg(挂载 → 用户拖入「应用程序」)。未公证首次打开需一次
            # xattr 去隔离，这是无法再自动化的部分(见「关于」说明)。
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            self._set_status(self._tr("update_open_dmg"))
            self.btn_action.setEnabled(True)

    def _abort_inflight(self):
        # 中止进行中的检查/下载：避免请求悬挂 + %TEMP% 残留写了一半的安装包。
        chk = getattr(self, "_checker", None)
        if chk is not None:
            chk.abort()
        dl = getattr(self, "_downloader", None)
        if dl is not None:
            dl.abort()

    def reject(self):
        # 「关闭」按钮 / ESC 走的是 reject（不是 closeEvent），这里一并中止在途请求。
        self._abort_inflight()
        super().reject()

    def closeEvent(self, e):
        self._abort_inflight()
        super().closeEvent(e)


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


# ============== 通用信息/错误提示框 (iOS 风格，无边框圆角) ==============
class InfoDialog(_DragFramelessMixin, QDialog):
    """themed info/error popup —— 替代 QMessageBox，与 CloseDialog/AboutDialog 风格统一。
    icon=✓(accent) 信息 / icon=✕(danger) 错误；标题 + 正文 + 单 OK 按钮，点击或 Esc 关闭。"""

    ThirdAction = 2

    def __init__(self, title_text: str, body_text: str, ok_text: str = "OK",
                 is_error: bool = False, theme_id: str = THEME_DEFAULT, parent=None,
                 confirm: bool = False, cancel_text: str = "Cancel", danger: bool = False,
                 third_text: str = None):
        super().__init__(parent)
        _flags = Qt.Dialog | Qt.FramelessWindowHint
        if sys.platform == "darwin":
            _flags |= Qt.NoDropShadowWindowHint
        self.setWindowFlags(_flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._theme_id = theme_id

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        self._card = QFrame()
        self._card.setObjectName("DialogCard")
        sh = QGraphicsDropShadowEffect(self._card)
        sh.setBlurRadius(28)
        sh.setColor(QColor(0, 0, 0, 80))
        sh.setOffset(0, 4)
        self._card.setGraphicsEffect(sh)

        v = QVBoxLayout(self._card)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(14)

        c = chrome_for(theme_id)
        # 大圆形图标（居中、视觉锚点）
        ic = QLabel("✕" if is_error else "✓")
        ic_bg = c['danger'] if is_error else c['accent']
        ic.setFixedSize(44, 44)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(
            f"background-color: {ic_bg}; color: white; border-radius: 22px;"
            f"font-family: 'Segoe UI'; font-size: 22px; font-weight: bold;")
        ic_row = QHBoxLayout()
        ic_row.addStretch(1); ic_row.addWidget(ic); ic_row.addStretch(1)
        v.addLayout(ic_row)

        # 标题（居中）
        self.lbl_title = QLabel(title_text)
        self.lbl_title.setFont(ui_font(14, bold=True))
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet(f"color: {c['text']}; background: transparent;")
        v.addWidget(self.lbl_title)

        # 正文（居中、可选中复制；长路径换行）
        self.lbl_body = QLabel(body_text)
        self.lbl_body.setWordWrap(True)
        self.lbl_body.setAlignment(Qt.AlignCenter)
        self.lbl_body.setStyleSheet(
            f"color: {c['text_sec']}; background: transparent;"
            f"font-family: 'Segoe UI'; font-size: 12px;")
        self.lbl_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.lbl_body)

        # 按钮行：默认单 OK（信息/错误）；confirm=True 时前面再加一个「取消」(ghost)，构成二选一
        # 确认框（exec_() 返回 Accepted/Rejected）。danger=True 时 OK 用红色(危险动作如删除)。
        self.btn_ok = QPushButton(ok_text)
        self.btn_ok.setObjectName("DialogDangerBtn" if danger else "DialogPrimaryBtn")
        self.btn_ok.setMinimumHeight(36)
        self.btn_ok.setMinimumWidth(120)
        self.btn_ok.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        if confirm:
            self.btn_cancel = QPushButton(cancel_text)
            self.btn_cancel.setObjectName("DialogGhostBtn")
            self.btn_cancel.setMinimumHeight(36)
            self.btn_cancel.setMinimumWidth(120)
            self.btn_cancel.clicked.connect(self.reject)
            btn_row.addWidget(self.btn_cancel)
        if third_text:
            self.btn_third = QPushButton(third_text)
            # Discard / tertiary action is not a destructive confirm; keep it neutral.
            self.btn_third.setObjectName("DialogGhostBtn")
            self.btn_third.setMinimumHeight(36)
            self.btn_third.setMinimumWidth(120)
            self.btn_third.clicked.connect(lambda: self.done(self.ThirdAction))
            btn_row.addWidget(self.btn_third)
        btn_row.addWidget(self.btn_ok)
        btn_row.addStretch(1)
        # 默认按钮 / Enter 目标：危险确认（如删除）给「取消」并令其获焦，避免弹框后一按 Enter
        # 就执行了破坏性操作；其它（信息/普通确认）仍以 OK 为默认。
        if confirm and danger:
            self.btn_ok.setAutoDefault(False)
            self.btn_ok.setDefault(False)
            self.btn_cancel.setAutoDefault(True)
            self.btn_cancel.setDefault(True)
            self.btn_cancel.setFocus()
        else:
            self.btn_ok.setDefault(True)
        v.addLayout(btn_row)

        outer.addWidget(self._card)
        self.setStyleSheet(localize_qss(self._build_qss()))
        self.setMinimumWidth(360)
        self.setMaximumWidth(620 if third_text else 520)

    def _build_qss(self):
        c = chrome_for(self._theme_id)
        return f"""
        QFrame#DialogCard {{ background-color: {c['card_bg']}; border-radius: 14px; }}
        QPushButton#DialogPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 13px;
            font-weight: 600; padding: 6px 14px;
        }}
        QPushButton#DialogPrimaryBtn:hover  {{ background-color: {c['accent_hover']}; }}
        QPushButton#DialogPrimaryBtn:pressed{{ background-color: {c['accent_pressed']}; }}
        QPushButton#DialogDangerBtn {{
            background-color: {c['danger']}; color: white; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 13px;
            font-weight: 600; padding: 6px 14px;
        }}
        QPushButton#DialogDangerBtn:hover {{ background-color: {c['danger_hover']}; }}
        QPushButton#DialogGhostBtn {{
            background-color: {c['ghost_bg']}; color: {c['text']}; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 13px;
            font-weight: 500; padding: 6px 14px;
        }}
        QPushButton#DialogGhostBtn:hover  {{ background-color: {c['ghost_hover']}; }}
        QPushButton#DialogGhostBtn:pressed{{ background-color: {c['ghost_pressed']}; }}
        """


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


class _DragHandle(QLabel):
    """多条发送的行拖拽手柄：按住左键发起 QDrag，由列表容器(host)接收 drop 重排行顺序。"""
    def __init__(self, dialog, frame):
        super().__init__("☰")          # ☰ 三横，拖拽手柄惯例图标
        self.setObjectName("MsDragGrip")
        self.setFixedWidth(18)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.OpenHandCursor)
        set_tooltip(self, {"zh": "按住拖动改变顺序", "en": "Drag to reorder",
                         "zh_tw": "按住拖動改變順序"}.get(getattr(dialog.app, "_lang", "zh"),
                                                          "Drag to reorder"))
        self._dialog = dialog
        self._frame = frame

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dialog._begin_row_drag(self._frame)
        super().mousePressEvent(e)   # 无论左右键都让基类感知，保持 Qt 内部按下状态一致


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
    QComboBox:disabled, QLineEdit:disabled {{
        background-color: {c['window_bg']}; color: {c['text_sec']};
        border: 1px solid {c['separator']};
    }}
    QCheckBox {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 11px; spacing: 4px; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px; border-radius: 3px;
        border: 1px solid {c['separator']}; background-color: {c['input_bg']};
    }}
    QCheckBox::indicator:hover {{ border: 1px solid {c['accent']}; }}
    QCheckBox::indicator:checked {{ background-color: {c['accent']}; border: 1px solid {c['accent']}; }}
    QCheckBox::indicator:disabled {{ border: 1px solid {c['separator']}; background-color: {c['window_bg']}; }}
    /* 与主界面（main_window 全局样式表）的 QComboBox 规则保持一致：padding / min-height /
       下拉按钮宽度 / 箭头边距 逐项对齐。此前对话框这几项与主界面不同，下拉框在按钮行里会被
       拉伸、原生样式再在内部按自然尺寸补画一层，观感与主界面不一致。 */
    QComboBox {{
        background-color: {c['input_bg']}; border: 1px solid {c['separator']};
        border-radius: 6px; padding: 2px 7px; min-height: 16px; color: {c['text']};
        font-family: 'Segoe UI'; font-size: 11px;
        selection-background-color: {c['accent']};
    }}
    QComboBox:focus {{
        border: 1px solid {c['accent']}; background-color: {c['input_bg']};
        selection-background-color: {c['input_bg']}; selection-color: {c['text']};
    }}
    /* Windows 会在下拉列表展开时给 QComboBox:on 套系统强调色；显式恢复中性底色/边框。
       弹出列表中真正的当前项仍由下方 QAbstractItemView 规则保持蓝色。 */
    QComboBox:on {{
        border: 1px solid {c['separator']}; background-color: {c['input_bg']};
        selection-background-color: {c['input_bg']}; selection-color: {c['text']};
    }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {c['text_sec']};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['combo_dropdown_bg']}; color: {c['text']};
        border: 1px solid {c['separator']}; border-radius: 0px; padding: 4px;
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


def _style_combo_popups(root, c):
    """按主窗口相同方式给 QComboBoxPrivateContainer 显式刷底色。

    下拉弹出容器是独立顶层窗口，只给 QAbstractItemView 写 QSS 时 Windows 原生 palette
    仍可能在外框透出青绿色系统强调色。
    """
    for combo in root.findChildren(QComboBox):
        try:
            combo.view().window().setStyleSheet(
                f"background-color: {c['combo_dropdown_bg']};")
        except (AttributeError, RuntimeError):
            pass


# ============== 多条发送弹窗 ==============
class MultiSendDialog(QDialog):
    """多条自定义发送，支持分组(左侧列表)：每行一条命令 + 名称 + 独立延时 + HEX/换行/校验。
    可逐条点「发送」，也可勾选多条后「循环发送」按每行延时依次轮发。分组与命令持久化。"""

    def __init__(self, app):
        # parent=None：与主窗 Qt 父子链断开，避免 Qt 在 Windows 上和无边框主窗的 WM_NCHITTEST
        # 处理产生干扰（症状：打开此弹窗后主窗边缘 resize 失效，关掉也不恢复）。生命周期改在
        # 主窗 _shutdown 显式收（同 AutoReplyDialog）。
        super().__init__(None)
        self.app = app
        self.setWindowTitle(app._t("multi_send_title"))
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(900, 400)
        self.resize(1040, 480)
        self._rows = []
        self._populating = False
        # 名称/数据列的共享拖动比例（所有行同步）；从 settings 恢复上次拖好的列宽，
        # 没存过则 None → 用默认 [90, 460]。拖动后在 _sync_splits 里写回 settings 持久化。
        self._name_split_sizes = self._load_split_sizes()
        self._syncing_split = False      # 防止同步分隔条时递归
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
        # 表头：全选/全不选。左边距 8 与行 frame 的左 contentsMargins 一致 → 全选框对齐行首勾选框
        header = QHBoxLayout()
        header.setContentsMargins(8, 0, 8, 0)
        self.cb_all = QCheckBox(app._t("ms_select_all"))
        self.cb_all.setObjectName("MsSelectAll")
        self.cb_all.setTristate(True)        # 全选=√ / 全不选=空 / 部分=▣
        self.cb_all.clicked.connect(self._toggle_all)
        header.addWidget(self.cb_all)
        header.addStretch(1)
        # 模板库入口：多条发送与模板库都在管理「发什么」——多条发送把一组命令按序循环发，
        # 模板库存单条常用命令随手取用。从这里一键打开，两个发送辅助工具就近串起来。
        self.btn_snippets = QPushButton(app._t("ms_snip_btn"))
        self.btn_snippets.setObjectName("MsGhostBtn")
        self.btn_snippets.setMinimumHeight(28)
        set_tooltip(self.btn_snippets, app._t("ms_snip_btn_tip"))
        self.btn_snippets.clicked.connect(lambda *_: self.app.open_snippets())
        header.addWidget(self.btn_snippets)
        right.addLayout(header)
        scroll, self._list_host, self._list_v = _make_list_scroll()
        # 行拖拽排序：手柄发起 QDrag、容器(host)接收 drop 按落点重排
        self._list_host.setAcceptDrops(True)
        self._list_host.installEventFilter(self)
        self._drag_frame = None
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
        chk.stateChanged.connect(self._on_chk_changed)
        h.addWidget(chk)
        h.addWidget(_DragHandle(self, frame))   # 行拖拽手柄（拖它改变顺序）
        ed_name = QLineEdit(name)
        ed_name.setPlaceholderText(self.app._t("ms_name_ph"))
        ed_name.setMinimumWidth(40)
        ed_name.textChanged.connect(self._save)
        edit = QLineEdit(data)
        edit.setPlaceholderText(self.app._t("ms_placeholder"))
        edit.textChanged.connect(self._save)
        # 名称框 + 数据框放进可拖 QSplitter：拖动调名称列宽(长名称显示不全时)，所有行同步
        split = QSplitter(Qt.Horizontal)
        split.setObjectName("MsNameSplit")
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        split.addWidget(ed_name)
        split.addWidget(edit)
        split.setSizes(self._name_split_sizes or [90, 460])
        split.splitterMoved.connect(lambda *_: self._sync_splits(split))
        h.addWidget(split, 1)
        ed_delay = QLineEdit(str(delay))
        ed_delay.setFixedWidth(58)
        set_tooltip(ed_delay, self.app._t("ms_delay_tip"))
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
               "delay": ed_delay, "hex": cb_hex, "nl": cb_nl, "cs": cb_cs, "split": split}
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

    # ----- 拖拽排序 -----
    def eventFilter(self, obj, event):
        if obj is self._list_host:
            et = event.type()
            if et in (QEvent.DragEnter, QEvent.DragMove):
                if event.mimeData().hasFormat("application/x-mssend-row"):
                    event.acceptProposedAction()
                    return True
            elif et == QEvent.Drop:
                if event.mimeData().hasFormat("application/x-mssend-row"):
                    self._on_row_drop(event.pos().y())
                    event.acceptProposedAction()
                    return True
            elif et == QEvent.DragLeave:
                # 拖到列表区外：接掉事件即可（拖拽影像跟随鼠标，无悬停高亮需清理）
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def _begin_row_drag(self, frame):
        """行手柄按下：发起 QDrag，用整行截图作拖拽影像。"""
        self._drag_frame = frame
        drag = QDrag(frame)
        mime = QMimeData()
        mime.setData("application/x-mssend-row", b"1")
        drag.setMimeData(mime)
        pm = frame.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(12, pm.height() // 2))
        drag.exec_(Qt.MoveAction)
        self._drag_frame = None

    def _on_row_drop(self, y):
        """按落点 y 把被拖的行插到目标位置，重排 _rows + 布局并落盘。"""
        src = self._drag_frame
        if src is None:
            return
        frames = [r["frame"] for r in self._rows]
        if src not in frames:
            return
        src_idx = frames.index(src)
        target = len(frames)
        for i, f in enumerate(frames):
            if y < f.y() + f.height() / 2:     # 落点在某行上半 → 插到它之前
                target = i
                break
        if target > src_idx:                   # 源行移除后其后目标索引前移 1
            target -= 1
        if target < 0 or target == src_idx:
            return
        row = self._rows.pop(src_idx)
        self._rows.insert(target, row)
        self._list_v.removeWidget(src)
        self._list_v.insertWidget(target, src)
        self._commit_now()

    def _load_split_sizes(self):
        """从 settings 读上次拖好的名称/数据列宽 "w_name,w_data"；无效则 None（用默认）。"""
        raw = self.app.settings.value("multi_send_split", "")
        try:
            parts = [int(x) for x in str(raw).split(",")]
            if len(parts) == 2 and all(p > 0 for p in parts):
                return parts
        except (ValueError, TypeError):
            pass
        return None

    def _sync_splits(self, src):
        """一行拖动名称/数据分隔条 → 所有行同步到相同比例（列对齐），并持久化列宽。"""
        if self._syncing_split:
            return
        sizes = src.sizes()
        if len(sizes) != 2 or sum(sizes) <= 0:
            return
        self._name_split_sizes = sizes
        # 写回 settings：下次开窗 / 重启后列宽保持现状（sync 放在 closeEvent，避免拖动时频繁刷盘）
        self.app.settings.setValue("multi_send_split", "%d,%d" % (sizes[0], sizes[1]))
        self._syncing_split = True
        try:
            for r in self._rows:
                sp = r.get("split")
                if sp is not None and sp is not src:
                    sp.setSizes(sizes)
        finally:
            self._syncing_split = False

    def _on_chk_changed(self, *_):
        """某行勾选变化：落盘(去抖) + 刷新顶部全选三态。"""
        self._save()
        self._refresh_select_all()

    def _toggle_all(self, checked):
        """顶部全选框：一键勾选/取消所有行（block 行信号，最后统一落盘+刷新）。"""
        on = bool(checked)
        for r in self._rows:
            r["chk"].blockSignals(True)
            r["chk"].setChecked(on)
            r["chk"].blockSignals(False)
        self._refresh_select_all()
        self._save()

    def _refresh_select_all(self):
        """顶部全选框(左/右)反映当前勾选：全选=√ / 全不选=空 / 部分=▣。"""
        if not hasattr(self, "cb_all"):
            return
        n = sum(1 for r in self._rows if r["chk"].isChecked())
        st = (Qt.Checked if n and n == len(self._rows)
              else Qt.Unchecked if n == 0 else Qt.PartiallyChecked)
        self.cb_all.blockSignals(True)
        self.cb_all.setCheckState(st)
        self.cb_all.blockSignals(False)

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

    def flush_pending(self):
        """工程/配置保存前提交仍处于防抖窗口内的编辑。"""
        if self._save_timer.isActive():
            self._commit_now()

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
        self._refresh_select_all()

    def closeEvent(self, e):
        self._commit_now()    # 关窗时立即落盘待提交编辑
        self.app.settings.sync()   # 把拖动列宽等设置刷到磁盘
        super().closeEvent(e)

    # ----- 主题 / 语言 -----
    def retranslate(self):
        self.setWindowTitle(self.app._t("multi_send_title"))
        self.btn_add.setText(self.app._t("ms_add"))
        self.cb_all.setText(self.app._t("ms_select_all"))
        self.btn_snippets.setText(self.app._t("ms_snip_btn"))
        set_tooltip(self.btn_snippets, self.app._t("ms_snip_btn_tip"))
        self.lbl_hint.setText(self.app._t("ms_hint"))
        self.btn_new_group.setText(self.app._t("kw_new_group"))
        self.btn_del_group.setText(self.app._t("kw_del_group"))
        self.lbl_group_tip.setText(self.app._t("kw_group_tip"))
        for r in self._rows:
            r["edit"].setPlaceholderText(self.app._t("ms_placeholder"))
            r["name"].setPlaceholderText(self.app._t("ms_name_ph"))
            set_tooltip(r["delay"], self.app._t("ms_delay_tip"))
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
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
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
        QSplitter#MsNameSplit::handle {{ background: {c['separator']}; margin: 4px 1px; border-radius: 2px; }}
        QSplitter#MsNameSplit::handle:hover {{ background: {c['accent']}; }}
        QLabel#MsDragGrip {{ color: {c['text_sec']}; font-size: 13px; }}
        QLabel#MsDragGrip:hover {{ color: {c['accent']}; }}
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
        """))
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
        # parent=None：避免干扰主窗 WM_NCHITTEST（详见 MultiSendDialog 同位置注释）。
        # 用户报告过：开关此弹窗后主窗边缘 resize 失效。
        super().__init__(None)
        self.app = app
        self.setWindowTitle(app._t("kw_title"))
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint
                            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
                            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
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

    def flush_pending(self):
        """工程/配置保存前提交仍处于防抖窗口内的编辑。"""
        if self._commit_timer.isActive():
            self._commit_now()

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
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
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
        """))
        for r in self._rows:                       # 颜色按钮保持各自底色
            self._paint_color_btn(r)
            for key in ("mode", "scope"):
                popup = r[key].view().window()
                popup.setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")


# ============== 自动化测试序列对话框 ==============
class SequenceDialog(_DragFramelessMixin, QDialog):
    """自动化测试序列：表头 + 圆角卡片行（形制同多条发送/自动应答，复用 _dialog_list_qss）。
    顺序执行 发送 → 等回包匹配 → 通过/失败。步骤存 app._seq_rules / settings['sequence_rules']；
    运行引擎在 main_window（_seq_* 系列）。单实例非模态，复用主窗刷新主题/语言。
    每行控件引用存 self._rows[i]（dict），读写走 _row_to_step。"""
    _MODE_KEYS = ("seq_mode_contains", "seq_mode_equals", "seq_mode_prefix")
    _ONFAIL_KEYS = ("seq_onfail_stop", "seq_onfail_continue")
    # 只有「发送」「期望回包」两个数据框可拖宽：分别装进 2 面板 splitter 的左/右两组，组内数据框伸展、
    # 其余控件固定宽度（拖它们没意义）。整行只有一个分隔条(两组之间)——拖它调两个数据框的相对宽。
    # 形制同自动应答对话框。行布局：启用 | [ 名称 发送↔ HEX 校验 | 期望↔ HEX 模式 超时 超时动作 延时 ] | 结果 删除
    _LEAD_W, _RESULT_W, _DEL_W = 22, 170, 24
    # 定宽列。下拉列(校验/模式/超时动作)只给「最小宽」，实际宽在 __init__ 按各自选项文案自动算(见
    # _combo_w)——以后往选项列表加更长的项，列宽自动跟着变，不用改代码。
    _NAME_W, _HEX_W, _TO_W, _DL_W, _RETRY_W = 90, 34, 58, 54, 46
    _CS_MIN_W, _MODE_MIN_W, _OF_MIN_W = 60, 56, 56
    _DATA_MIN_W = 60                # 发送/期望数据框最小宽（表头标签与行控件取同值 → 任何宽度都对齐）
    _MAX_IMPORT_STEPS = 500          # 导入会为每步创建整行 Qt 控件，限量防止误导入卡死 UI
    _MAX_IMPORT_BYTES = 5 * 1024 * 1024  # json.load 前先限制文件大小，避免大文件占满内存
    _MAX_RETRY = 999                 # 与重试输入框/引擎安全上限一致
    _MAX_TIMER_MS = 2147483647        # QTimer 的 int 毫秒上限
    _DEFAULT_SPLIT = [300, 440]     # 左组(名称+发送)/右组(期望+模式…) 初始宽；拖分隔条调二者、持久化

    def __init__(self, app):
        super().__init__(None)      # 不传 parent：与其它子对话框一致，避免干扰无边框主窗
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                            | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(880, 320)
        self.resize(1140, 460)
        self._loading = False
        self._rows = []              # 每行控件引用 dict 列表（on/name/send/…/res/frame/split）
        # 中间列的共享拖动比例，所有行 + 表头同步；从 settings 恢复上次拖好的列宽，没存过用默认
        self._split_sizes = self._load_split_sizes()
        self._syncing_split = False  # 防止同步分隔条递归
        # 循环运行配置：循环次数 + 某轮失败即停（持久化，关窗 sync）
        self._loops_cfg = max(1, self._to_int(app.settings.value("sequence_loops", 1), 1))
        self._stopfail_cfg = str(app.settings.value("sequence_stop_on_fail", "")).lower() in ("1", "true")
        self._csv_path = str(app.settings.value("sequence_csv_path", "") or "").strip()
        self._csv_dataset = None
        if self._csv_path:
            try:
                self._csv_dataset = sequence_dataset.load_dataset(self._csv_path)
            except Exception:
                # Keep path so UI can show stale hint and enable Clear.
                self._csv_dataset = None
        # 下拉列宽按各自选项文案自动算（含最长项，避免像 ModbusCRC16 被截断；日后加更长的项也自适应）
        self._cs_w = self._combo_w(CHECKSUM_KEYS, self._CS_MIN_W)
        self._mode_w = self._combo_w(self._MODE_KEYS, self._MODE_MIN_W)
        self._of_w = self._combo_w(self._ONFAIL_KEYS, self._OF_MIN_W)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._commit)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)                       # 顶栏控件统一间距，避免个别处大小不一
        self.btn_run = QPushButton()
        self.btn_run.setObjectName("PlotGhostBtn")   # 普通灰按钮：空闲时不高亮，避免被误读成"运行中"
        self.btn_run.setMinimumHeight(30)
        self.btn_run.clicked.connect(self._on_run)
        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("PlotGhostBtn")
        self.btn_stop.clicked.connect(lambda *_: self.app._seq_stop())
        self.btn_add = QPushButton()
        self.btn_add.setObjectName("PlotGhostBtn")
        self.btn_add.clicked.connect(lambda *_: (self._add_row(), self._schedule()))
        self.btn_steps = QPushButton()          # 步骤 ▾：导入 / 导出整条序列(JSON)，便于分享/版本管理
        self.btn_steps.setObjectName("PlotGhostBtn")
        self.btn_steps.clicked.connect(self._show_steps_menu)
        self.btn_export = QPushButton()         # 导出报告（跑完后可用，出 HTML/CSV 测试报告）
        self.btn_export.setObjectName("PlotGhostBtn")
        self.btn_export.clicked.connect(self._on_export)
        self.btn_help = QPushButton("?")        # 「?」→ 带例子的用法说明（形制同自动应答对话框）
        self.btn_help.setObjectName("ArHelpBtn")
        self.btn_help.setFixedSize(26, 26)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(lambda *_: self._show_help_dlg())
        self.lbl_loops = QLabel()               # 循环次数：整条序列跑几轮
        self.ed_loops = QLineEdit(str(self._loops_cfg))
        self.ed_loops.setFixedWidth(46)
        self.ed_loops.setValidator(QIntValidator(1, 100000, self))   # 1..10万(与引擎 _SEQ_MAX_LOOPS 一致)，挡字母/负号
        self.ed_loops.editingFinished.connect(self._save_loop_cfg)
        self.cb_stopfail = QCheckBox()          # 某轮失败即停止后续循环
        self.cb_stopfail.setChecked(self._stopfail_cfg)
        self.cb_stopfail.toggled.connect(lambda *_: self._save_loop_cfg())
        self.btn_csv = QPushButton()
        self.btn_csv.setObjectName("PlotGhostBtn")
        self.btn_csv.clicked.connect(self._on_pick_csv)
        self.btn_csv_clear = QPushButton()
        self.btn_csv_clear.setObjectName("PlotGhostBtn")
        self.btn_csv_clear.clicked.connect(self._on_clear_csv)
        self.lbl_csv = QLabel("")
        self.lbl_csv.setObjectName("MsHint")
        self.lbl_csv.setMaximumWidth(260)
        self._refresh_csv_ui()
        top.addWidget(self.btn_run)             # 左侧：操作序列的按钮 + 循环配置，统一间距
        top.addWidget(self.btn_stop)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_steps)
        top.addWidget(self.lbl_loops)
        top.addWidget(self.ed_loops)
        top.addWidget(self.cb_stopfail)
        top.addWidget(self.btn_csv)
        top.addWidget(self.btn_csv_clear)
        top.addWidget(self.lbl_csv)
        top.addStretch(1)
        self.lbl_summary = QLabel("")           # 运行状态/汇总
        self.lbl_summary.setObjectName("SeqSummary")
        self.lbl_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top.addWidget(self.lbl_summary)
        top.addWidget(self.btn_export)          # 右侧：导出报告 + 帮助
        top.addWidget(self.btn_help)
        root.addLayout(top)

        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("ArDesc")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        # 表头：启用占位(固定) + [左组 | 右组](splitter，仅两数据列可拖) + 结果(固定) + 删除占位(固定)
        self.hdr = QWidget()
        self._hdr_layout = QHBoxLayout(self.hdr)
        self._hdr_layout.setContentsMargins(10, 2, 10, 2)
        self._hdr_layout.setSpacing(6)
        self._hdr_labels = []
        lead = QLabel()                     # 启用勾选列占位
        lead.setFixedWidth(self._LEAD_W)
        self._hdr_layout.addWidget(lead)
        # 左组标签：名称(固定) 发送(伸展) HEX(固定) 校验(固定)；右组：期望(伸展) HEX 模式 超时 超时动作 延时(均固定)
        hleft = self._mk_hdr_group([("seq_col_name", self._NAME_W), ("seq_col_send", None),
                                    ("seq_col_extract", None),
                                    ("HEX", self._HEX_W), ("seq_col_cs", self._cs_w)])
        hright = self._mk_hdr_group([("seq_col_expect", None), ("HEX", self._HEX_W),
                                     ("seq_col_mode", self._mode_w), ("seq_col_timeout", self._TO_W),
                                     ("seq_col_onfail", self._of_w), ("seq_col_delay", self._DL_W),
                                     ("seq_col_retry", self._RETRY_W)])
        self._hdr_split = self._make_split()
        self._hdr_split.addWidget(hleft)
        self._hdr_split.addWidget(hright)
        self._hdr_split.setStretchFactor(0, 1)
        self._hdr_split.setStretchFactor(1, 1)
        self._hdr_split.setSizes(self._split_sizes or self._DEFAULT_SPLIT)
        self._hdr_split.splitterMoved.connect(lambda *_: self._sync_splits(self._hdr_split))
        self._hdr_layout.addWidget(self._hdr_split, 1)
        lb_res = QLabel()                   # 结果：固定列，不在 splitter 内
        lb_res.setObjectName("SeqHdr")
        lb_res.setProperty("k", "seq_col_result")
        lb_res.setFixedWidth(self._RESULT_W)
        lb_res.setAlignment(Qt.AlignCenter)
        self._hdr_layout.addWidget(lb_res)
        self._hdr_labels.append(lb_res)
        hdel = QWidget()                    # 删除按钮列占位
        hdel.setFixedWidth(self._DEL_W)
        self._hdr_layout.addWidget(hdel)
        root.addWidget(self.hdr)

        # 卡片行滚动区（形制同 多条发送/自动应答）
        host = QWidget()
        host.setObjectName("MsListHost")
        self.rows_v = QVBoxLayout(host)
        self.rows_v.setContentsMargins(0, 0, 0, 0)
        self.rows_v.setSpacing(5)
        self.rows_v.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("MsScroll")
        self.scroll.setWidget(host)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._update_header_scroll_margin)
        root.addWidget(self.scroll, 1)

        self.reload_rows()
        self.retranslate()
        self.refresh_theme()
        QTimer.singleShot(0, self._update_header_scroll_margin)

    def _combo_w(self, keys, min_w):
        """按下拉选项里最长文案算列宽：最长项像素宽 + 下拉箭头/内边距余量，不小于 min_w。
        选项列表加更长的项时列宽自动跟着变，无需手改常量。"""
        f = QFont("Segoe UI")
        f.setPixelSize(11)                             # 与 QComboBox 的 QSS 字号一致
        fm = QFontMetrics(f)
        need = max((fm.horizontalAdvance(self.app._t(k)) for k in keys), default=0)
        return max(min_w, need + 32)                   # +32 = 下拉箭头(16)+内边距(12)+边框(~4)，刚好不截断

    def _make_split(self):
        sp = QSplitter(Qt.Horizontal)
        sp.setObjectName("MsColSplit")
        sp.setChildrenCollapsible(False)
        sp.setHandleWidth(8)
        return sp

    def _mk_hdr_group(self, cols):
        """建一个表头分组容器（放进 2 面板 splitter 的一侧）：cols=[(表头键, 固定宽或 None)]，
        宽=None 的列(数据框)伸展、其余固定，与每行同组的控件逐列对齐。标签登记进 _hdr_labels 供翻译。"""
        box = QWidget()
        hb = QHBoxLayout(box)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(6)
        for key, w in cols:
            lb = QLabel()
            lb.setObjectName("SeqHdr")
            lb.setProperty("k", key)
            if w is None:
                lb.setMinimumWidth(self._DATA_MIN_W)   # 与行数据框同最小宽 → 表头/行始终对齐
                hb.addWidget(lb, 1)         # 数据列：伸展，占满该组剩余宽
            else:
                lb.setFixedWidth(w)
                hb.addWidget(lb)
            self._hdr_labels.append(lb)
        return box

    def _mk_row_group(self, cells):
        """建一行的分组容器（放进 2 面板 splitter 一侧）：cells=[(控件, 固定宽或 None)]，宽=None(数据框)
        伸展、其余固定，与表头同组逐列对齐。"""
        box = QWidget()
        hb = QHBoxLayout(box)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(6)
        for w, wd in cells:
            if wd is None:
                w.setMinimumWidth(self._DATA_MIN_W)    # 与表头数据标签同最小宽 → 表头/行始终对齐
                hb.addWidget(w, 1)
            else:
                w.setFixedWidth(wd)
                hb.addWidget(w)
        return box

    def _load_split_sizes(self):
        """从 settings 读上次拖好的列宽 'w1,...,wN'；列数不符/非法则 None（用默认）。"""
        raw = self.app.settings.value("sequence_split", "")
        try:
            parts = [int(x) for x in str(raw).split(",")]
            if len(parts) == len(self._DEFAULT_SPLIT) and all(p > 0 for p in parts):
                return parts
        except (ValueError, TypeError):
            pass
        return None

    def _sync_splits(self, src):
        """任一行(或表头)拖动分隔条 → 所有行 + 表头同步到相同比例（列对齐），并持久化列宽。"""
        if self._syncing_split:
            return
        try:                       # 对话框已关(deleteLater)后 singleShot 仍可能触发 → C++ 已删，忽略
            sizes = src.sizes()
        except RuntimeError:
            return
        if not sizes or sum(sizes) <= 0:
            return
        self._split_sizes = sizes
        self.app.settings.setValue("sequence_split", ",".join(str(s) for s in sizes))
        self._syncing_split = True
        try:
            targets = [getattr(self, "_hdr_split", None)] + [r.get("split") for r in self._rows]
            for sp in targets:
                if sp is not None and sp is not src:
                    try:
                        sp.setSizes(sizes)
                    except RuntimeError:
                        pass
        finally:
            self._syncing_split = False

    def _update_header_scroll_margin(self, *_args):
        """数据区出现垂直滚动条时，表头右侧预留同宽空间，保持 splitter 像素对齐。"""
        try:                       # 同上：延迟触发时对话框可能已析构，静默跳过防止 PyQt 槽内异常 abort
            bar = self.scroll.verticalScrollBar()
            extra = bar.sizeHint().width() if bar.maximum() > bar.minimum() else 0
            self._hdr_layout.setContentsMargins(10, 2, 10 + extra, 2)
        except RuntimeError:
            return
        QTimer.singleShot(0, lambda: self._sync_splits(self._hdr_split))

    # ---------------- 行读写 ----------------
    @staticmethod
    def _to_int(s, default):
        try:
            return max(0, int(str(s).strip()))
        except (ValueError, TypeError):
            return default

    def _add_row(self, step=None):
        step = step or {}
        d = {}
        frame = QFrame()
        frame.setObjectName("MsRow")
        d["frame"] = frame
        h = QHBoxLayout(frame)
        h.setContentsMargins(10, 5, 10, 5)
        h.setSpacing(6)

        d["on"] = QCheckBox()                       # 启用：固定列，不在 splitter 内
        d["on"].setFixedWidth(self._LEAD_W)
        d["on"].setChecked(bool(step.get("on", True)))
        d["on"].toggled.connect(self._schedule)
        h.addWidget(d["on"])

        d["name"] = QLineEdit(str(step.get("name", "") or ""))
        d["name"].textChanged.connect(self._schedule)

        d["send"] = QLineEdit(str(step.get("send", "") or ""))
        d["send"].setPlaceholderText(self.app._t("seq_send_ph"))
        d["send"].textChanged.connect(self._schedule)

        d["shex"] = QCheckBox()
        d["shex"].setChecked(bool(step.get("send_hex", False)))
        d["shex"].toggled.connect(self._schedule)

        cb_cs = QComboBox()
        for k in CHECKSUM_KEYS:
            cb_cs.addItem(self.app._t(k))
        cs = self._to_int(step.get("cs", 0), 0)
        cb_cs.setCurrentIndex(cs if 0 <= cs < cb_cs.count() else 0)
        cb_cs.currentIndexChanged.connect(self._schedule)
        d["cs"] = cb_cs

        d["exp"] = QLineEdit(str(step.get("expect", "") or ""))
        d["exp"].setPlaceholderText(self.app._t("seq_expect_ph"))
        d["exp"].textChanged.connect(self._schedule)

        d["ehex"] = QCheckBox()
        d["ehex"].setChecked(bool(step.get("expect_hex", False)))
        d["ehex"].toggled.connect(self._schedule)

        cb_mode = QComboBox()
        for k in self._MODE_KEYS:
            cb_mode.addItem(self.app._t(k))
        md = self._to_int(step.get("mode", 0), 0)
        cb_mode.setCurrentIndex(md if 0 <= md < 3 else 0)
        cb_mode.currentIndexChanged.connect(self._schedule)
        d["mode"] = cb_mode

        d["to"] = QLineEdit(str(step.get("timeout", 1000)))
        d["to"].setValidator(QIntValidator(0, self._MAX_TIMER_MS, self))
        d["to"].textChanged.connect(self._schedule)

        cb_of = QComboBox()
        for k in self._ONFAIL_KEYS:
            cb_of.addItem(self.app._t(k))
        cb_of.setCurrentIndex(1 if str(step.get("on_timeout", "stop")) == "continue" else 0)
        cb_of.currentIndexChanged.connect(self._schedule)
        d["of"] = cb_of

        d["dl"] = QLineEdit(str(step.get("delay", 0)))
        d["dl"].setValidator(QIntValidator(0, self._MAX_TIMER_MS, self))
        d["dl"].textChanged.connect(self._schedule)

        d["retry"] = QLineEdit(str(self._to_int(step.get("retry", 0), 0)))   # 失败重试次数（0=不重试）
        d["retry"].setValidator(QIntValidator(0, self._MAX_RETRY, self))
        set_tooltip(d["retry"], self.app._t("seq_retry_tip"))
        d["retry"].textChanged.connect(self._schedule)

        d["extract"] = QLineEdit(str(step.get("extract_dsl") or "") or seq_context.extractors_to_dsl(step.get("extract") or []))
        d["extract"].setPlaceholderText(self.app._t("seq_extract_ph"))
        set_tooltip(d["extract"], self.app._t("seq_extract_tip"))
        d["extract"].textChanged.connect(self._schedule)

        # 只把两个数据框放进可拖：左组[名称 发送↔ HEX 校验] / 右组[期望↔ HEX 模式 超时 超时动作 延时 重试]，
        # 组内数据框伸展、其余固定；两组装进 2 面板 splitter，拖中间分隔条即调发送/期望相对宽（各行+表头同步）。
        left = self._mk_row_group([(d["name"], self._NAME_W), (d["send"], None),
                                   (d["extract"], None),
                                   (d["shex"], self._HEX_W), (cb_cs, self._cs_w)])
        right = self._mk_row_group([(d["exp"], None), (d["ehex"], self._HEX_W),
                                    (cb_mode, self._mode_w), (d["to"], self._TO_W),
                                    (cb_of, self._of_w), (d["dl"], self._DL_W),
                                    (d["retry"], self._RETRY_W)])
        split = self._make_split()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        split.setSizes(self._split_sizes or self._DEFAULT_SPLIT)
        split.splitterMoved.connect(lambda *_: self._sync_splits(split))
        d["split"] = split
        h.addWidget(split, 1)

        res = QLabel("—")                           # 结果：固定列，不在 splitter 内
        res.setFixedWidth(self._RESULT_W)
        res.setAlignment(Qt.AlignCenter)
        d["res"] = res
        h.addWidget(res)

        btn_del = QPushButton("✕")                  # 删除：固定列
        btn_del.setObjectName("MsDelBtn")
        btn_del.setFixedWidth(self._DEL_W)
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(lambda *_, dd=d: self._del_row(dd))
        d["del"] = btn_del
        h.addWidget(btn_del)

        self.rows_v.insertWidget(self.rows_v.count() - 1, frame)   # 插在末尾 stretch 之前
        self._rows.append(d)
        c = chrome_for(self.app._theme_id())      # 下拉弹出窗上色（QSS 罩不到弹窗框；新增行也覆盖）
        for combo in (cb_cs, cb_mode, cb_of):
            combo.view().window().setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")

    def _del_row(self, d):
        if d in self._rows:
            self._rows.remove(d)
        d["frame"].setParent(None)
        d["frame"].deleteLater()
        self._schedule()

    def _row_to_step(self, d):
        return {
            "on": d["on"].isChecked(),
            "name": d["name"].text(),
            "send": d["send"].text(),
            "send_hex": d["shex"].isChecked(),
            "cs": d["cs"].currentIndex(),
            "expect": d["exp"].text(),
            "expect_hex": d["ehex"].isChecked(),
            "mode": d["mode"].currentIndex(),
            "timeout": min(self._MAX_TIMER_MS, self._to_int(d["to"].text(), 1000)),
            "on_timeout": "continue" if d["of"].currentIndex() == 1 else "stop",
            "delay": min(self._MAX_TIMER_MS, self._to_int(d["dl"].text(), 0)),
            "retry": self._to_int(d["retry"].text(), 0),
            "extract_dsl": d["extract"].text().strip(),
            "extract": seq_context.parse_extract_dsl(d["extract"].text()),
        }

    def _all_steps(self):
        return [self._row_to_step(d) for d in self._rows]

    # ---------------- 持久化 ----------------
    def _schedule(self):
        if self._loading:
            return
        # 编辑步骤后，上一次运行的结果/汇总不再对应当前步骤 → 清掉，避免「改了却仍显示旧的通过/失败」
        # 或删行后结果按索引错位。运行中允许改字段但绝不能清在跑的实时结果，故仅非运行态清。
        if not self.app._seq_running() and (getattr(self.app, "_seq_results", None)
                                            or getattr(self.app, "_seq_summary", None)):
            self.app._seq_results = []
            self.app._seq_summary = None
            self.update_results()
        self._save_timer.start(400)

    def _commit(self):
        import json
        steps = self._all_steps()
        self.app._seq_rules = steps
        self.app.settings.setValue("sequence_rules", json.dumps(steps, ensure_ascii=False))
        self.app.settings.sync()

    def flush_pending(self):
        """Flush debounced step edits before project/config save.

        Loop count is synced silently only when valid; invalid/empty values are
        left for editingFinished / run paths so opening the project menu alone
        does not toast a validation error.
        """
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._commit()
        self.app.settings.setValue("sequence_stop_on_fail", self.cb_stopfail.isChecked())
        # CSV-bound: ed_loops shows row count -- never persist that as manual loops.
        if self._csv_dataset and self._csv_dataset.get("rows"):
            return
        loops = self._to_int(self.ed_loops.text(), 0)
        if loops < 1:
            return
        self._loops_cfg = loops
        self.app.settings.setValue("sequence_loops", loops)

    def reload_rows(self):
        self._loading = True
        for d in list(self._rows):    # 清掉现有卡片行
            d["frame"].setParent(None)
            d["frame"].deleteLater()
        self._rows = []
        for step in getattr(self.app, "_seq_rules", []) or []:
            if isinstance(step, dict):
                self._add_row(step)
        if not self._rows:
            self._add_row()           # 空则给一行空模板，方便直接填
        self._loading = False
        self.update_results()

    # ---------------- 运行 / 结果 ----------------
    def _save_loop_cfg(self):
        """Persist loop count / stop-on-fail. CSV-bound keeps unbound loop preference."""
        self.app.settings.setValue("sequence_stop_on_fail", self.cb_stopfail.isChecked())
        self._stopfail_cfg = self.cb_stopfail.isChecked()
        if self._csv_dataset and self._csv_dataset.get("rows"):
            return
        loops = self._to_int(self.ed_loops.text(), 0)
        if loops < 1:
            loops = 1
            self.app.toast(self.app._t("seq_loops_invalid"))
        self.ed_loops.setText(str(loops))
        self._loops_cfg = loops
        self.app.settings.setValue("sequence_loops", loops)

    def _refresh_csv_ui(self):
        bound = bool(self._csv_dataset and self._csv_dataset.get("rows"))
        running = bool(getattr(self.app, "_seq_on", False))
        self.ed_loops.setEnabled((not bound) and (not running))
        self.lbl_loops.setEnabled((not bound) and (not running))
        if bound:
            n = len(self._csv_dataset["rows"])
            self.ed_loops.setText(str(n))
            self.lbl_csv.setText(sequence_dataset.dataset_status(self._csv_dataset))
            set_tooltip(self.lbl_csv, self._csv_dataset.get("path") or "")
            self.btn_csv_clear.setEnabled(not running)
        else:
            self.ed_loops.setText(str(max(1, getattr(self, "_loops_cfg", 1))))
            stale = bool(getattr(self, "_csv_path", "") or "")
            self.lbl_csv.setText(self.app._t("seq_csv_stale") if stale else "")
            set_tooltip(self.lbl_csv, self._csv_path if stale else "")
            self.btn_csv_clear.setEnabled(stale and (not running))

    def _save_csv_cfg(self):
        self.app.settings.setValue("sequence_csv_path", self._csv_path or "")

    def _on_pick_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.app._t("seq_csv_pick_title"), self._csv_path or "",
            "CSV (*.csv);;All (*.*)")
        if not path:
            return
        try:
            ds = sequence_dataset.load_dataset(path)
        except sequence_dataset.DatasetError as e:
            self.app.toast(self.app._t(e.code, **e.kwargs), error=True)
            return
        except Exception as e:
            self.app.toast(self.app._t("seq_csv_load_failed", e=e), error=True)
            return
        self._csv_path = ds["path"]
        self._csv_dataset = ds
        self._save_csv_cfg()
        self._refresh_csv_ui()
        msg = self.app._t("seq_csv_loaded", n=len(ds["rows"]))
        if ds.get("truncated"):
            msg += " " + self.app._t("seq_csv_truncated", n=sequence_dataset.MAX_ROWS)
        self.app.toast(msg)

    def _on_clear_csv(self):
        self._csv_path = ""
        self._csv_dataset = None
        self._save_csv_cfg()
        self._refresh_csv_ui()
        self.app.toast(self.app._t("seq_csv_cleared"))

    def _on_run(self):
        self._commit()
        ds = self._csv_dataset
        # Always re-read when a path is bound so external CSV edits take effect.
        if self._csv_path:
            try:
                ds = sequence_dataset.load_dataset(self._csv_path)
                self._csv_dataset = ds
                self._refresh_csv_ui()
            except sequence_dataset.DatasetError as e:
                self.app.toast(self.app._t(e.code, **e.kwargs), error=True)
                self._csv_dataset = None
                self._refresh_csv_ui()
                return
            except Exception as e:
                self.app.toast(self.app._t("seq_csv_load_failed", e=e), error=True)
                self._csv_dataset = None
                self._refresh_csv_ui()
                return
        if ds and ds.get("rows"):
            loops = len(ds["rows"])
            self.ed_loops.setText(str(loops))
            self.app._seq_start(self._all_steps(), loops=loops,
                                stop_on_fail=self.cb_stopfail.isChecked(),
                                dataset=ds)
        else:
            loops = max(1, self._to_int(self.ed_loops.text(), 1))
            self.ed_loops.setText(str(loops))
            self.app._seq_start(self._all_steps(), loops=loops,
                                stop_on_fail=self.cb_stopfail.isChecked(),
                                dataset=None)

    def _result_detail(self, res):
        """返回当前语言的结果详情。新结果保存 detail_key 以支持运行后切换语言；
        detail 作为旧结果/外部构造数据的兼容回退。"""
        key = str(res.get("detail_key", "") or "")
        return self.app._t(key) if key else str(res.get("detail", "") or "")

    def _attempt_suffix(self, res):
        """通过/已发送若经过重试(第2次起) → 附「(第N次)」，让人看出这步是重试后才成的。"""
        a = int(res.get("attempt", 1) or 1)
        return (" " + self.app._t("seq_attempt", n=a)) if a > 1 else ""

    def _status_display(self, st, res, c):
        if st == "pass":
            return "✓ %dms%s" % (int(res.get("ms", 0)), self._attempt_suffix(res)), c["accent"]
        if st == "sent":
            return self.app._t("seq_st_sent") + self._attempt_suffix(res), c["accent"]
        if st == "retry":
            return self.app._t("seq_st_retry", n=int(res.get("attempt", 2) or 2)), c["text_sec"]
        if st == "fail":
            return ("✗ " + (self._result_detail(res) or self.app._t("seq_st_fail"))
                    + self._attempt_suffix(res)), c["danger"]
        if st == "waiting":
            return self.app._t("seq_st_waiting"), c["text_sec"]
        if st == "skip":
            return self.app._t("seq_st_skip"), c["text_sec"]
        if st == "stopped":
            return self.app._t("seq_st_stopped"), c["text_sec"]
        return self.app._t("seq_st_pending"), c["text_sec"]

    def update_results(self):
        """从 app._seq_results / _seq_summary 刷新结果列 + 汇总 + 运行按钮态（运行引擎回调）。"""
        c = chrome_for(self.app._theme_id())
        results = getattr(self.app, "_seq_results", []) or []
        running = self.app._seq_running()
        # 有已跑结果就一直显示（停止/断连后 _seq_summary 可能为空，但 _seq_results 仍在 → 结果不该丢）
        show = running or bool(results)
        for i, d in enumerate(self._rows):
            res = results[i] if i < len(results) else {}
            st = res.get("status", "pending") if show else "pending"
            text, color = self._status_display(st, res, c)
            d["res"].setText(text)
            set_tooltip(d["res"], text)
            d["res"].setStyleSheet("color: %s; background: transparent;" % color)
        summ = getattr(self.app, "_seq_summary", None)
        if running:
            n = len(getattr(self.app, "_seq_steps", []) or []) or len(results) or 1
            i = min(max(1, getattr(self.app, "_seq_idx", 0) + 1), n)   # 当前第 i/n 步（随步进实时更新）
            loops = max(1, getattr(self.app, "_seq_loops", 1))
            if loops > 1:                        # 循环运行：显示当前第 R/N 轮
                r = min(max(1, getattr(self.app, "_seq_loop_i", 0) + 1), loops)
                self.lbl_summary.setText(self.app._t("seq_running_round", r=r, n_loops=loops, i=i, n=n))
            else:
                self.lbl_summary.setText(self.app._t("seq_running_at", i=i, n=n))
            self.lbl_summary.setStyleSheet("color: %s; font-weight: 600;" % c["accent"])
        elif summ:
            verdict = self.app._t("seq_pass" if summ.get("pass") else "seq_fail")
            if summ.get("loops", 1) > 1:         # 循环汇总：通过轮 R/N（提前停止标计划总数）· 累计步 X/Y
                text = self._loop_summary_text(summ, verdict)
            else:
                text = self.app._t("seq_summary", ok=summ.get("ok", 0), total=summ.get("total", 0),
                                   ms=summ.get("ms", 0), verdict=verdict)
            self.lbl_summary.setText(text)
            self.lbl_summary.setStyleSheet("color: %s; font-weight: 600;"
                                           % (c["accent"] if summ.get("pass") else c["danger"]))
        else:
            self.lbl_summary.setText("")
        self.btn_run.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        csv_bound = bool(self._csv_dataset and self._csv_dataset.get("rows"))
        self.ed_loops.setEnabled((not running) and (not csv_bound))
        self.lbl_loops.setEnabled((not running) and (not csv_bound))
        self.cb_stopfail.setEnabled(not running)
        self.btn_steps.setEnabled(not running)  # 运行中不导入步骤（结构性变更会与在跑快照错位）
        # 只有正常收尾并产生汇总才是完整报告；用户停止/断连时保留的部分结果
        # 仍可在界面查看，但不应导出成缺少结论的测试报告。
        self.btn_export.setEnabled(not running and bool(results)
                                   and bool(getattr(self.app, "_seq_summary", None)))
        # 运行中把「运行」点亮成绿色作「正在运行」指示（仍禁用防重复启动，故 :disabled 也显绿）；
        # 空闲/结束回落普通灰按钮（清空内联样式 → 回到对话框级 PlotGhostBtn 样式）。
        if running:
            self.btn_run.setStyleSheet(
                "QPushButton, QPushButton:disabled { background-color: %s; color: #fff;"
                " border: 0px; border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px;"
                " font-weight: 600; padding: 5px 14px; }" % c["accent"])
        else:
            self.btn_run.setStyleSheet("")
        self._set_editing_enabled(not running)   # 运行中锁住步骤编辑，避免改表/增删行与在跑的快照错位

    def _set_editing_enabled(self, enabled):
        """运行中只禁止「结构性改动」——增行 / 删行会改变行数、让结果按索引错位。步骤字段本身不锁：
        运行用的是启动时的快照，改字段不影响在跑的步骤，也不会错位；且禁用勾选框会丢失选中蓝色渲染，
        看着像被取消，反而误导。"""
        self.btn_add.setEnabled(enabled)
        self.btn_csv.setEnabled(enabled)
        stale = bool(getattr(self, "_csv_path", "") or "") and not (
            self._csv_dataset and self._csv_dataset.get("rows"))
        bound = bool(self._csv_dataset and self._csv_dataset.get("rows"))
        self.btn_csv_clear.setEnabled(enabled and (bound or stale))
        for d in self._rows:
            btn = d.get("del")
            if btn is not None:
                btn.setEnabled(enabled)

    # ---------------- 导出测试报告 ----------------
    def _status_report_text(self, res):
        """结果状态 → 报告用的纯文本（无颜色）。"""
        st = res.get("status", "pending")
        t = self.app._t
        if st == "pass":    return t("seq_st_pass") + self._attempt_suffix(res)   # 通过(第N次)
        if st == "sent":    return t("seq_st_sent") + self._attempt_suffix(res)   # 已发送(第N次)
        if st == "retry":   return t("seq_st_retry", n=int(res.get("attempt", 2) or 2))
        if st == "fail":    return t("seq_report_fail") + self._attempt_suffix(res)  # 失败(第N次)
        if st == "skip":    return t("seq_report_skip")                   # 跳过
        if st == "stopped": return t("seq_st_stopped")                    # 已停止
        if st == "waiting": return t("seq_st_waiting")                    # 等回包…
        return t("seq_st_pending")                                        # 待运行

    def _report_rows(self, steps, results):
        """把运行快照(app._seq_steps) + 结果(app._seq_results) 整理成报告行 dict 列表。"""
        t = self.app._t
        rows = []
        for i, s in enumerate(steps):
            res = results[i] if i < len(results) else {}
            send = str(s.get("send", "") or "")
            if s.get("send_hex"):
                send += " (HEX)"
            exp = str(s.get("expect", "") or "").strip()
            exp_disp = (exp + (" (HEX)" if s.get("expect_hex") else "")) if exp else "—"
            cs = self._to_int(s.get("cs", 0), 0)
            cs_name = t(CHECKSUM_KEYS[cs]) if 0 <= cs < len(CHECKSUM_KEYS) else ""
            md = self._to_int(s.get("mode", 0), 0)
            mode_name = t(self._MODE_KEYS[md]) if (exp and 0 <= md < len(self._MODE_KEYS)) else "—"
            status = res.get("status", "pending")
            detail = self._result_detail(res)
            frames = []
            if res.get("tx"):
                frames.append("TX=%s" % res.get("tx"))
            if res.get("rx_hex"):
                frames.append("RX=%s" % res.get("rx_hex"))
            if frames:
                detail = (detail + " | " if detail else "") + " ".join(frames)
            rows.append({
                "no": i + 1, "name": str(s.get("name", "") or ""),
                "send": send, "cs": cs_name, "expect": exp_disp, "mode": mode_name,
                "timeout": "%dms" % self._to_int(s.get("timeout", 1000), 1000),
                "status": self._status_report_text(res),
                "elapsed": "%dms" % int(res.get("ms", 0)),
                "detail": detail,
                "enabled": bool(s.get("on", True)),
                "ok": status in ("pass", "sent", "skip"), "fail": status == "fail",
            })
        return rows

    def _report_header(self):
        """报告表头列名（HTML/CSV 共用）。"""
        t = self.app._t
        return ["#", t("seq_col_name"), t("seq_col_send"), t("seq_col_cs"), t("seq_col_expect"),
                t("seq_col_mode"), t("seq_col_timeout"), t("seq_col_result"),
                t("seq_report_elapsed"), t("seq_report_detail")]

    def _report_is_csv(self):
        """True when the last run was CSV-driven (any row count)."""
        summ = getattr(self.app, "_seq_summary", None) or {}
        if summ.get("csv_path"):
            return True
        return any(("csv_row" in r) for r in (summ.get("round_list") or []))

    def _report_is_loop(self):
        # Multi-round OR CSV-driven (incl. single-row) so reports keep csv_row/label.
        if self._report_is_csv():
            return True
        return int((getattr(self.app, "_seq_summary", None) or {}).get("loops", 1) or 1) > 1

    def _report_by_round(self):
        """轮次表要有轮次数据才成立；一轮都没跑完时回退到逐步骤表（否则表是空的）。"""
        if not self._report_is_loop():
            return False
        summ = getattr(self.app, "_seq_summary", None) or {}
        return bool(summ.get("round_list"))

    def _loop_summary_text(self, summ, verdict):
        """循环汇总文案：通过轮 R/N；实际跑过轮数 < 计划(失败即停/中途停止)时标出「计划 M 轮」，避免误读。"""
        rp, rt = summ.get("rounds_pass", 0), summ.get("rounds", 0)
        loops = summ.get("loops", rt) or rt
        frac = (self.app._t("seq_rounds_partial", rp=rp, rt=rt, loops=loops) if rt < loops
                else self.app._t("seq_rounds_frac", rp=rp, rt=rt))
        return self.app._t("seq_summary_loops", rounds=frac, ok=summ.get("ok", 0),
                           total=summ.get("total", 0), ms=summ.get("ms", 0), verdict=verdict)

    def _report_summary_line(self):
        summ = getattr(self.app, "_seq_summary", None) or {}
        if not summ:
            return "", False
        passed = bool(summ.get("pass"))
        verdict = self.app._t("seq_pass" if passed else "seq_fail")
        if int(summ.get("loops", 1) or 1) > 1:
            line = self._loop_summary_text(summ, verdict)
        else:
            line = self.app._t("seq_summary", ok=summ.get("ok", 0), total=summ.get("total", 0),
                               ms=summ.get("ms", 0), verdict=verdict)
        csv_path = summ.get("csv_path") or ""
        if csv_path:
            line = line + " | " + self.app._t("seq_report_csv_src", path=csv_path)
        return line, passed

    def _report_meta_rows(self):
        """Extra metadata lines for HTML/CSV/JUnit."""
        from version import __version__ as _ver
        t = self.app._t
        summ = getattr(self.app, "_seq_summary", None) or {}
        started = summ.get("started_at") or getattr(self.app, "_seq_started_at", "") or ""
        finished = summ.get("finished_at") or getattr(self.app, "_seq_finished_at", "") or ""
        ver = summ.get("version") or _ver
        rows = [
            (t("seq_report_time"), started),
            (t("seq_report_finished"), finished),
            (t("seq_report_version"), "CommTool %s" % ver),
            (t("seq_report_params"), t(
                "seq_report_params_val",
                loops=summ.get("loops", 1),
                steps=summ.get("step_count", len(getattr(self.app, "_seq_steps", []) or [])),
                stop=t("seq_stop_on_fail") if summ.get("stop_on_fail") else "-",
            )),
        ]
        if summ.get("csv_path"):
            rows.append((t("seq_report_csv_file"), summ.get("csv_path")))
        return [(k, v) for k, v in rows if v not in ("", None)]

    def _report_table(self, rows):
        """Return (header, body[{cells,cls}]). Loop/CSV uses per-step rows when snapshots exist."""
        t = self.app._t
        if self._report_by_round():
            summ = getattr(self.app, "_seq_summary", None) or {}
            rounds = list(summ.get("round_list") or [])
            has_csv = bool(summ.get("csv_path")) or any(("csv_row" in rr) for rr in rounds)
            has_steps = any(rr.get("steps") for rr in rounds)
            if has_steps:
                header = [t("seq_report_round")]
                if has_csv:
                    header += [t("seq_report_csv_row"), t("seq_report_csv_label")]
                header += ["#", t("seq_col_name"), t("seq_col_send"), t("seq_col_expect"),
                           t("seq_col_result"), t("seq_report_elapsed"), t("seq_report_detail")]
                body = []
                for r in rounds:
                    defs = r.get("step_defs") or []
                    results = r.get("steps") or []
                    for i, step in enumerate(defs):
                        if not step.get("on", True):
                            continue
                        res = results[i] if i < len(results) else {}
                        st = res.get("status", "pending")
                        detail = self._result_detail(res)
                        frames = []
                        if res.get("tx"):
                            frames.append("TX=%s" % res.get("tx"))
                        if res.get("rx_hex"):
                            frames.append("RX=%s" % res.get("rx_hex"))
                        if frames:
                            detail = (detail + " | " if detail else "") + " ".join(frames)
                        send = str(step.get("send", "") or "")
                        if step.get("send_hex"):
                            send += " (HEX)"
                        exp = str(step.get("expect", "") or "").strip() or "-"
                        cells = [r.get("round", "")]
                        if has_csv:
                            cells += [r.get("csv_row", ""), r.get("csv_label", "") or ""]
                        cells += [i + 1, str(step.get("name", "") or ""), send, exp,
                                  self._status_report_text(res),
                                  "%dms" % int(res.get("ms", 0)), detail]
                        cls = ("ok" if st in ("pass", "sent", "skip")
                               else ("fail" if st == "fail" else ""))
                        body.append({"cells": cells, "cls": cls})
                return header, body
            if has_csv:
                header = [t("seq_report_round"), t("seq_report_csv_row"),
                          t("seq_report_csv_label"), t("seq_report_round_steps"),
                          t("seq_report_verdict"), t("seq_report_elapsed")]
            else:
                header = [t("seq_report_round"), t("seq_report_round_steps"),
                          t("seq_report_verdict"), t("seq_report_elapsed")]
            body = []
            for r in rounds:
                rp = bool(r.get("pass"))
                if has_csv:
                    cells = [r.get("round", ""),
                             r.get("csv_row", ""),
                             r.get("csv_label", "") or "",
                             "%d/%d" % (r.get("ok", 0), r.get("total", 0)),
                             t("seq_pass" if rp else "seq_fail"),
                             "%dms" % int(r.get("ms", 0))]
                else:
                    cells = [r.get("round", ""),
                             "%d/%d" % (r.get("ok", 0), r.get("total", 0)),
                             t("seq_pass" if rp else "seq_fail"),
                             "%dms" % int(r.get("ms", 0))]
                body.append({"cells": cells, "cls": "ok" if rp else "fail"})
            return header, body
        header = self._report_header()
        body = []
        for r in rows:
            cls = ("ok" if r["ok"] else ("fail" if r["fail"] else "")) if r["enabled"] else ""
            body.append({"cells": [r["no"], r["name"], r["send"], r["cs"], r["expect"], r["mode"],
                                   r["timeout"], r["status"], r["elapsed"], r["detail"]], "cls": cls})
        return header, body

    def _build_report_html(self, rows):
        import html as _h
        t = self.app._t
        summ_line, passed = self._report_summary_line()
        header, body = self._report_table(rows)
        th = "".join("<th>%s</th>" % _h.escape(str(x)) for x in header)
        trs = []
        for b in body:
            tds = "".join("<td>%s</td>" % _h.escape(str(x)) for x in b["cells"])
            trs.append('<tr class="%s">%s</tr>' % (b["cls"], tds))
        meta_html = "".join(
            "<div class='meta'>%s: %s</div>" % (_h.escape(str(k)), _h.escape(str(v)))
            for k, v in self._report_meta_rows()
        )
        return (
            "<!doctype html><html><head><meta charset='utf-8'><title>%(title)s</title><style>"
            "body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;margin:24px;color:#222;}"
            "h1{font-size:20px;margin:0 0 6px;}"
            ".meta{color:#666;font-size:13px;margin-bottom:6px;}"
            ".verdict{display:inline-block;padding:3px 12px;border-radius:6px;color:#fff;"
            "font-weight:600;background:%(accent)s;}"
            "table{border-collapse:collapse;width:100%%;font-size:13px;margin-top:12px;}"
            "th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top;"
            "word-break:break-all;}"
            "th{background:#f4f5f7;font-weight:600;}"
            "tr.ok td{background:#ebfbee;}tr.fail td{background:#fff0f0;}"
            "td:first-child,th:first-child{text-align:center;width:36px;}"
            ".foot{color:#aaa;font-size:11px;margin-top:16px;}"
            "</style></head><body>"
            "<h1>%(title)s</h1>"
            "%(meta)s"
            "%(verdict_html)s"
            "<table><thead><tr>%(th)s</tr></thead><tbody>%(rows)s</tbody></table>"
            "<div class='foot'>CommTool · %(title)s</div></body></html>"
        ) % {
            "title": _h.escape(t("seq_report_title")),
            "meta": meta_html,
            "verdict_html": ("<div><span class='verdict'>%s</span></div>" % _h.escape(summ_line))
                            if summ_line else "",
            "accent": "#2f9e44" if passed else "#e03131",
            "th": th, "rows": "".join(trs),
        }

    def _build_report_csv(self, rows):
        import csv, io
        t = self.app._t
        summ_line, _passed = self._report_summary_line()
        header, body = self._report_table(rows)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([self._csv_safe(t("seq_report_title"))])
        for k, v in self._report_meta_rows():
            w.writerow([self._csv_safe(k), self._csv_safe(v)])
        if summ_line:
            w.writerow([self._csv_safe(summ_line)])
        w.writerow([])
        w.writerow([self._csv_safe(x) for x in header])
        for b in body:
            w.writerow([self._csv_safe(x) for x in b["cells"]])
        return buf.getvalue()

    @staticmethod
    def _csv_safe(value):
        """Excel 会把危险前缀的 CSV 单元格当作公式；前置单引号强制按文本打开。"""
        if not isinstance(value, str):
            return value
        probe = value.lstrip()
        if value and (value[0] in "=+-@\t\r\n" or (probe and probe[0] in "=+-@")):
            return "'" + value
        return value

    @staticmethod
    def _report_fmt(path, sel):
        """决定导出格式 + 补扩展名：先看路径扩展名；扩展名不明时按对话框选中的过滤器(sel)决定
        （部分平台/Qt 不会自动追加扩展名，避免选了 CSV 却写成 .html）。返回 (fmt, path)。"""
        low = path.lower()
        if low.endswith(".csv"):
            return "csv", path
        if low.endswith(".xml"):
            return "junit", path
        if low.endswith(".html") or low.endswith(".htm"):
            return "html", path
        sel_l = (sel or "").lower()
        if "csv" in sel_l:
            return "csv", path + ".csv"
        if "xml" in sel_l or "junit" in sel_l:
            return "junit", path + ".xml"
        return "html", path + ".html"

    def _build_report_junit(self, rows):
        """Build JUnit XML from the latest sequence snapshot."""
        from version import __version__ as _ver
        steps = getattr(self.app, "_seq_steps", []) or []
        results = getattr(self.app, "_seq_results", []) or []
        summ = getattr(self.app, "_seq_summary", None) or {}
        cases = junit_report.cases_from_snapshot(
            steps, results, summ, detail_resolver=self._result_detail)
        meta = {
            "app": "CommTool",
            "version": summ.get("version") or _ver,
            "started_at": summ.get("started_at") or getattr(self.app, "_seq_started_at", "") or "",
            "finished_at": summ.get("finished_at") or getattr(self.app, "_seq_finished_at", "") or "",
            "loops": summ.get("loops"),
            "stop_on_fail": summ.get("stop_on_fail"),
            "csv_path": summ.get("csv_path"),
            "csv_rows": summ.get("csv_rows"),
            "pass": summ.get("pass"),
            "stopped": summ.get("stopped"),
        }
        return junit_report.build_junit_xml("CommTool.Sequence", cases, meta)

    def _on_export(self):
        """导出上一次运行的测试报告（按保存对话框选的扩展名/过滤器出 HTML 或 CSV）。"""
        steps = getattr(self.app, "_seq_steps", []) or []
        results = getattr(self.app, "_seq_results", []) or []
        summary = getattr(self.app, "_seq_summary", None)
        if not steps or not results or not summary:
            self.app.toast(self.app._t("seq_export_none"), error=True)
            return
        ts = (getattr(self.app, "_seq_started_at", "") or "").translate(str.maketrans("", "", "-: "))
        # 默认名不预绑定 .html：切换到 CSV 过滤器时，某些平台不会替换已有扩展名。
        # 留给 _report_fmt 根据过滤器补全，用户手动输入的扩展名仍优先。
        default = "CommTool_seq_report_%s" % (ts or "report")
        path, _sel = QFileDialog.getSaveFileName(self, self.app._t("seq_export"), default,
                                                 "HTML (*.html);;CSV (*.csv);;JUnit XML (*.xml)")
        if not path:
            return
        try:
            # 循环模式按轮次出表(_report_table 直接读 round_list)，逐步骤 rows 用不上，不白算
            rows = [] if self._report_by_round() else self._report_rows(steps, results)
            fmt, path = self._report_fmt(path, _sel)
            if fmt == "csv":
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    f.write(self._build_report_csv(rows))
            elif fmt == "junit":
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(self._build_report_junit(rows))
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._build_report_html(rows))
        except Exception as e:
            self.app.toast(self.app._t("seq_export_fail", e=e), error=True)
            return
        self.app.toast(self.app._t("seq_export_ok", path=path))

    # ---------------- 步骤 导入 / 导出（JSON，便于分享/版本管理测试用例） ----------------
    def _show_steps_menu(self):
        menu = QMenu(self)
        c = chrome_for(self.app._theme_id())
        menu.setStyleSheet(
            "QMenu { background: %s; color: %s; border: 1px solid %s; }"
            " QMenu::item:selected { background: %s; color: #fff; }"
            % (c["combo_dropdown_bg"], c["text"], c["separator"], c["accent"]))
        menu.addAction(self.app._t("seq_steps_export")).triggered.connect(
            lambda *_: self._export_steps())
        menu.addAction(self.app._t("seq_steps_import")).triggered.connect(
            lambda *_: self._import_steps())
        menu.exec_(self.btn_steps.mapToGlobal(QPoint(0, self.btn_steps.height())))

    def _export_steps(self):
        import json
        path, _sel = QFileDialog.getSaveFileName(self, self.app._t("seq_steps_export"),
                                                 "CommTool_sequence.json", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._all_steps(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.app.toast(self.app._t("seq_steps_export_fail", e=e), error=True)
            return
        self.app.toast(self.app._t("seq_steps_export_ok", path=path))

    def _import_steps(self):
        import json
        if self.app._seq_running():                  # 运行中不改步骤（结构性变更会与在跑快照错位）
            return
        path, _sel = QFileDialog.getOpenFileName(self, self.app._t("seq_steps_import"),
                                                 "", "JSON (*.json)")
        if not path:
            return
        try:
            import os
            if os.path.getsize(path) > self._MAX_IMPORT_BYTES:
                self.app.toast(self.app._t("seq_steps_import_large"), error=True)
                return
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            self.app.toast(self.app._t("seq_steps_import_fail", e=e), error=True)
            return
        steps = self._validate_import_steps(data)
        if steps is None:
            self.app.toast(self.app._t("seq_steps_import_bad"), error=True)
            return
        # 覆盖当前所有步骤前确认（防误导入丢失现有用例）
        if not self.app._confirm_dlg(self.app._t("seq_steps_import"),
                                     self.app._t("seq_steps_import_confirm", n=len(steps)), danger=False):
            return
        self._apply_imported_steps(steps)
        self.app.toast(self.app._t("seq_steps_imported", n=len(steps)))

    def _validate_import_steps(self, data):
        """校验并归一化导入数据。空列表会被 reload_rows 自动变成一个空步骤，
        因此直接拒绝，避免「导入 0 步」与实际结果不一致。"""
        if (not isinstance(data, list) or not data or len(data) > self._MAX_IMPORT_STEPS
                or not all(isinstance(x, dict) for x in data)):
            return None
        out = []
        for raw in data:
            step = dict(raw)
            # 严格校验已出现的字段；缺失字段仍由旧版兼容默认值补齐。
            if any(k in step and not isinstance(step[k], bool)
                   for k in ("on", "send_hex", "expect_hex")):
                return None
            if any(k in step and not isinstance(step[k], str)
                   for k in ("name", "send", "expect", "extract_dsl")):
                return None
            if "on_timeout" in step and step["on_timeout"] not in ("stop", "continue"):
                return None
            int_ranges = {
                "cs": (0, len(CHECKSUM_KEYS) - 1), "mode": (0, len(self._MODE_KEYS) - 1),
                "timeout": (0, self._MAX_TIMER_MS), "delay": (0, self._MAX_TIMER_MS),
                "retry": (0, self._MAX_RETRY),
            }
            for key, (lo, hi) in int_ranges.items():
                if key not in step:
                    continue
                value = step[key]
                if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
                    return None
            retry = step.get("retry", 0)
            if not 0 <= retry <= self._MAX_RETRY:
                return None
            step["retry"] = retry
            if "extract" in step and not isinstance(step["extract"], list):
                return None
            if "extract" in step:
                step["extract"] = seq_context.sanitize_extractors(step["extract"])
            dsl = step.get("extract_dsl")
            if isinstance(dsl, str) and dsl.strip():
                step["extract"] = seq_context.parse_extract_dsl(dsl)
                step["extract_dsl"] = dsl.strip()
            out.append(step)
        return out

    def _apply_imported_steps(self, steps):
        """覆盖当前步骤并清除已不对应的旧运行结果/汇总。"""
        self.app._seq_rules = [dict(x) for x in steps]
        self.app._seq_results = []
        self.app._seq_summary = None
        self.reload_rows()
        self._commit()

    # ---------------- 语言 / 主题 ----------------
    def retranslate(self):
        self.setWindowTitle(self.app._t("seq_title"))
        self.btn_run.setText(self.app._t("seq_run"))
        self.btn_stop.setText(self.app._t("seq_stop"))
        self.btn_add.setText(self.app._t("seq_add"))
        self.btn_steps.setText(self.app._t("seq_steps_menu"))
        self.btn_export.setText(self.app._t("seq_export"))
        self.lbl_loops.setText(self.app._t("seq_loops"))
        set_tooltip(self.ed_loops, self.app._t("seq_loops_tip"))
        self.cb_stopfail.setText(self.app._t("seq_stop_on_fail"))
        self.btn_csv.setText(self.app._t("seq_csv_btn"))
        set_tooltip(self.btn_csv, self.app._t("seq_csv_tip"))
        self.btn_csv_clear.setText(self.app._t("seq_csv_clear"))
        set_tooltip(self.btn_csv_clear, self.app._t("seq_csv_clear_tip"))
        self._refresh_csv_ui()
        set_tooltip(self.btn_help, self.app._t("seq_help_btn"))   # 按钮固定 "?"，悬停/点开看完整说明
        self.lbl_hint.setText(self.app._t("seq_hint"))
        for lb in self._hdr_labels:                 # 表头列名（HEX 列不翻译）
            k = lb.property("k")
            lb.setText("" if not k else (k if k == "HEX" else self.app._t(k)))
        for d in self._rows:                        # 下拉项/占位随语言刷新（保留选中项）
            d["send"].setPlaceholderText(self.app._t("seq_send_ph"))
            d["exp"].setPlaceholderText(self.app._t("seq_expect_ph"))
            if "extract" in d:
                d["extract"].setPlaceholderText(self.app._t("seq_extract_ph"))
                set_tooltip(d["extract"], self.app._t("seq_extract_tip"))
            set_tooltip(d["retry"], self.app._t("seq_retry_tip"))
            for i, k in enumerate(CHECKSUM_KEYS):
                if i < d["cs"].count():
                    d["cs"].setItemText(i, self.app._t(k))
            for i, k in enumerate(self._MODE_KEYS):
                d["mode"].setItemText(i, self.app._t(k))
            for i, k in enumerate(self._ONFAIL_KEYS):
                d["of"].setItemText(i, self.app._t(k))
        self.update_results()

    def _show_help_dlg(self):
        """弹独立窗口展示「自动化序列」用法说明（富文本 + 举例，可滚动、可复制）。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("seq_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                           | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(780, 560)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("seq_help"))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setAlignment(Qt.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)   # 让用户复制例子
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        btn_close = QPushButton({"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(self.app._lang, "Close"))
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
            QPushButton#PlotGhostBtn {{ background-color: {c['ghost_bg']}; color: {c['text']}; border: 0px;
                border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px; padding: 6px 16px; }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        """))
        _set_win_titlebar_dark(dlg, c)
        dlg.exec_()

    def refresh_theme(self):
        c = chrome_for(self.app._theme_id())
        _set_win_titlebar_dark(self, c)
        # 复用列表型弹窗基础样式（卡片行 MsRow / 蓝勾选 / 主题化输入下拉 / MsDelBtn），再补本弹窗特有按钮
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + f"""
            QLabel#ArDesc {{ color: {c['text_sec']}; font-size: 11px; }}
            QLabel#SeqHdr {{ color: {c['text_sec']}; font-size: 11px; font-weight: 600; }}
            QLabel#SeqSummary {{ font-size: 12px; }}
            QPushButton#PlotGhostBtn {{ background-color: {c['ghost_bg']}; color: {c['text']}; border: 0px;
                border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px; padding: 5px 14px; }}
            QPushButton#PlotGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
            QPushButton#PlotGhostBtn:disabled {{ color: {c['text_sec']}; }}
            QPushButton#ArHelpBtn {{ background-color: {c['ghost_bg']}; color: {c['text_sec']}; border: 0px;
                border-radius: 13px; font-family: 'Segoe UI'; font-size: 14px; font-weight: 600; }}
            QPushButton#ArHelpBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['text']}; }}
            QSplitter#MsColSplit {{ background: transparent; }}
            QSplitter#MsColSplit::handle {{ background: {c['separator']}; margin: 5px 3px; border-radius: 1px; }}
            QSplitter#MsColSplit::handle:hover {{ background: {c['accent']}; margin: 3px 3px; }}
        """))
        # 下拉弹出是独立顶层窗，QSS 罩不到弹窗边框 → 单独上色，避免深色主题露白边
        for d in self._rows:
            for combo in (d["cs"], d["mode"], d["of"]):
                combo.view().window().setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")
        self.update_results()   # 结果列颜色/运行绿按钮是内联样式，换主题后需按新强调色重刷

    def closeEvent(self, e):
        if self._save_timer.isActive():
            self._commit()
        self.app.settings.sync()
        super().closeEvent(e)
