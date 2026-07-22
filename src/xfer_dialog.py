# -*- coding: utf-8 -*-
"""文件传输对话框 XferDialog + 后台线程 XferWorker —— 协议收发 / 原始字节流发送。

协议纯逻辑在 xfer.py（可单测）；本模块做 GUI 与串口/网络连接的桥接：
- XferWorker(QThread) 跑 xfer.send_file/recv_file 或 raw 分块发送，协议 getc 从 ByteInbox 取（主窗把收到的数据 feed 进来），
  putc 经 sig_send 信号回到 GUI 线程由主窗 conn.send 发出（连接生命周期只在 GUI 线程动，避免竞态）。
- 传输期间主窗 on_data_received 整段接管收流喂 worker、不进显示区/自动应答/序列/Modbus。
单实例非模态，随主窗刷新主题/语言。
"""
import os

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QDialog, QWidget, QLabel, QLineEdit, QComboBox,
                             QRadioButton, QButtonGroup, QPushButton, QProgressBar, QSpinBox,
                             QTextEdit, QScrollArea, QFileDialog, QHBoxLayout, QVBoxLayout)

import xfer
from theme import chrome_for
from fonts import localize_qss
from dialogs import _dialog_list_qss, _set_win_titlebar_dark

MODE_RAW = "raw"            # 原始字节流：无协议、按分块 + 块间延时直接发送（只发不收）

# 协议下拉项 → xfer 模式
_PROTOS = (
    ("xfer_proto_xmodem", xfer.MODE_XMODEM),
    ("xfer_proto_xmodem_crc", xfer.MODE_XMODEM_CRC),
    ("xfer_proto_1k", xfer.MODE_XMODEM_1K),
    ("xfer_proto_ymodem", xfer.MODE_YMODEM),
    ("xfer_proto_raw", MODE_RAW),
)


class XferWorker(QThread):
    """后台跑一次传输。feed()/cancel() 由 GUI 线程调；sig_send 回 GUI 线程发字节。"""
    sig_progress = pyqtSignal(int, int)          # done, total（-1=未知）
    sig_done = pyqtSignal(bool, str, object)     # ok, msg, (data,meta)|None
    sig_send = pyqtSignal(bytes)

    def __init__(self, direction, mode, payload=b"", name="", chunk=1024, delay=0):
        super().__init__()
        self.direction = direction               # "send" / "recv"
        self.mode = mode
        self.payload = bytes(payload)
        self.name = name
        self.chunk = max(1, int(chunk))          # raw 分块字节数
        self.delay = max(0, int(delay))          # raw 块间延时 ms
        self.takes_input = (mode != MODE_RAW)    # 协议传输接管收流喂 getc；raw 只发不收、不接管
        self.inbox = xfer.ByteInbox()
        self._cancel = False

    def feed(self, data):
        self.inbox.put(data)

    def cancel(self):
        self._cancel = True
        self.inbox.close()                       # 唤醒阻塞的 getc，让协议尽快看到取消

    def run(self):
        if self.mode == MODE_RAW:
            self._run_raw()
            return
        getc = self.inbox.read
        putc = lambda d: self.sig_send.emit(bytes(d))
        cancel = lambda: self._cancel
        prog = lambda done, total: self.sig_progress.emit(done, -1 if total is None else total)
        try:
            if self.direction == "send":
                xfer.send_file(getc, putc, self.payload, mode=self.mode, name=self.name,
                               cancel=cancel, progress=prog)
                self.sig_done.emit(True, "", None)
            else:
                data, meta = xfer.recv_file(getc, putc, mode=self.mode, cancel=cancel, progress=prog)
                self.sig_done.emit(True, "", (data, meta))
        except xfer.XferCancelled:
            self.sig_done.emit(False, "__cancelled__", None)
        except Exception as e:                   # 协议/IO 异常 → 失败收尾（不崩 GUI）
            self.sig_done.emit(False, str(e), None)

    def _run_raw(self):
        """原始字节流：无协议、按 chunk 分块 sig_send，块间延时 delay ms（可取消）。"""
        total, off = len(self.payload), 0
        try:
            while off < total:
                if self._cancel:
                    self.sig_done.emit(False, "__cancelled__", None)
                    return
                piece = self.payload[off:off + self.chunk]
                self.sig_send.emit(bytes(piece))
                off += len(piece)
                self.sig_progress.emit(off, total)
                if self.delay and off < total:
                    self._sleep_cancellable(self.delay)
            self.sig_done.emit(True, "", None)
        except Exception as e:
            self.sig_done.emit(False, str(e), None)

    def _sleep_cancellable(self, ms):
        left = ms
        while left > 0 and not self._cancel:     # 分段睡，最多 20ms 内响应取消
            self.msleep(min(20, left))
            left -= 20


class XferDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                            | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(520, 440)
        self.resize(560, 480)
        self._worker = None
        self._path = ""            # 发送=源文件；接收=保存路径

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        # 顶部：标题占位 + 「?」
        top = QHBoxLayout()
        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("XferHint")
        self.lbl_hint.setWordWrap(True)
        top.addWidget(self.lbl_hint, 1)
        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("ArHelpBtn")
        self.btn_help.setFixedSize(24, 24)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(lambda *_: self._show_help_dlg())
        top.addWidget(self.btn_help, 0, Qt.AlignTop)
        root.addLayout(top)

        # 方向
        r_dir = QHBoxLayout()
        self.lbl_dir = QLabel()
        self.rb_send = QRadioButton()
        self.rb_recv = QRadioButton()
        self.rb_send.setChecked(True)
        self._dir_grp = QButtonGroup(self)
        self._dir_grp.addButton(self.rb_send, 0)
        self._dir_grp.addButton(self.rb_recv, 1)
        self.rb_send.toggled.connect(self._on_dir_changed)
        r_dir.addWidget(self.lbl_dir)
        r_dir.addSpacing(8)
        r_dir.addWidget(self.rb_send)
        r_dir.addSpacing(6)
        r_dir.addWidget(self.rb_recv)
        r_dir.addStretch(1)
        root.addLayout(r_dir)

        # 协议
        r_proto = QHBoxLayout()
        self.lbl_proto = QLabel()
        self.cb_proto = QComboBox()
        for _key, _mode in _PROTOS:
            self.cb_proto.addItem("", _mode)
        self.cb_proto.setCurrentIndex(1)        # 默认 XMODEM(CRC)
        r_proto.addWidget(self.lbl_proto)
        r_proto.addSpacing(8)
        r_proto.addWidget(self.cb_proto, 1)
        root.addLayout(r_proto)

        # 原始字节流参数（仅「原始字节流」协议显示）：分块大小 + 块间延时
        self.row_raw = QWidget()
        rr = QHBoxLayout(self.row_raw)
        rr.setContentsMargins(0, 0, 0, 0)
        self.lbl_chunk = QLabel()
        self.sp_chunk = QSpinBox()
        self.sp_chunk.setRange(1, 65535)
        self.sp_chunk.setValue(1024)
        self.sp_chunk.setSuffix(" B")
        self.lbl_delay = QLabel()
        self.sp_delay = QSpinBox()
        self.sp_delay.setRange(0, 10000)
        self.sp_delay.setValue(0)
        self.sp_delay.setSuffix(" ms")
        rr.addWidget(self.lbl_chunk); rr.addSpacing(6); rr.addWidget(self.sp_chunk)
        rr.addSpacing(16)
        rr.addWidget(self.lbl_delay); rr.addSpacing(6); rr.addWidget(self.sp_delay)
        rr.addStretch(1)
        root.addWidget(self.row_raw)
        self.row_raw.setVisible(False)

        # 文件 / 保存路径
        r_file = QHBoxLayout()
        self.lbl_file = QLabel()
        self.ed_path = QLineEdit()
        self.ed_path.setReadOnly(True)
        self.btn_browse = QPushButton()
        self.btn_browse.setObjectName("PlotGhostBtn")
        self.btn_browse.clicked.connect(self._browse)
        r_file.addWidget(self.lbl_file)
        r_file.addSpacing(8)
        r_file.addWidget(self.ed_path, 1)
        r_file.addWidget(self.btn_browse)
        root.addLayout(r_file)

        # 进度条
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.setValue(0)
        root.addWidget(self.bar)

        # 日志
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("XferLog")
        root.addWidget(self.log, 1)

        # 操作按钮
        r_btn = QHBoxLayout()
        r_btn.addStretch(1)
        self.btn_start = QPushButton()
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.setMinimumHeight(32)
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton()
        self.btn_cancel.setObjectName("PlotGhostBtn")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cancel.setEnabled(False)
        r_btn.addWidget(self.btn_start)
        r_btn.addWidget(self.btn_cancel)
        root.addLayout(r_btn)

        self.cb_proto.currentIndexChanged.connect(self._on_proto_changed)
        self.retranslate()
        self.refresh_theme()
        self._on_dir_changed()
        self._on_proto_changed()

    # ---------- 交互 ----------
    def _is_send(self):
        return self.rb_send.isChecked()

    def _on_proto_changed(self, *_):
        # 原始字节流：只发不收 → 显示分块/延时行、强制发送方向、禁用接收
        raw = self.cb_proto.currentData() == MODE_RAW
        self.row_raw.setVisible(raw)
        if raw:
            self.rb_send.setChecked(True)
            self.rb_recv.setEnabled(False)
        else:
            self.rb_recv.setEnabled(True)

    def _on_dir_changed(self, *_):
        t = self.app._t
        send = self._is_send()
        self.lbl_file.setText(t("xfer_file") if send else t("xfer_save"))
        self._path = ""
        self.ed_path.setText("")
        self.bar.setValue(0)

    def _browse(self):
        if self._is_send():
            path, _ = QFileDialog.getOpenFileName(self, self.app._t("xfer_pick_send"))
        else:
            path, _ = QFileDialog.getSaveFileName(self, self.app._t("xfer_pick_recv"))
        if path:
            self._path = path
            self.ed_path.setText(path)
            if self._is_send():
                try:
                    self.ed_path.setText("%s  (%d B)" % (path, os.path.getsize(path)))
                except OSError:
                    pass

    def _log(self, msg):
        self.log.append(msg)

    def _set_busy(self, busy):
        raw = self.cb_proto.currentData() == MODE_RAW
        self.rb_send.setEnabled(not busy)
        self.rb_recv.setEnabled((not busy) and (not raw))
        if raw:
            self.rb_send.setChecked(True)
        for w in (self.cb_proto, self.btn_browse, self.btn_start):
            w.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)

    def _start(self):
        t = self.app._t
        if not self.app._is_open():
            self.app.toast(t("xfer_need_conn"), error=True)
            return
        if self.app._xfer_start_blocked():
            self.app.toast(t("io_exclusive_busy"), error=True)
            return
        if not self._path:
            self.app.toast(t("xfer_need_file" if self._is_send() else "xfer_need_save"), error=True)
            return
        mode = self.cb_proto.currentData()
        if self._is_send():
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    with open(self._path, "rb") as f:
                        payload = f.read()
                finally:
                    QApplication.restoreOverrideCursor()
            except OSError as e:
                self.app.toast(t("xfer_read_err", msg=e), error=True)
                return
            worker = XferWorker("send", mode, payload=payload, name=os.path.basename(self._path),
                                chunk=self.sp_chunk.value(), delay=self.sp_delay.value())
            self.bar.setFormat("%p%")                  # 切回百分比（上次若为接收则可能残留字节格式）
            self.bar.setRange(0, max(1, len(payload)))
            self._log(t("xfer_log_send", name=os.path.basename(self._path), n=len(payload),
                        proto=self.cb_proto.currentText()))
        else:
            worker = XferWorker("recv", mode)
            self.bar.setRange(0, 0)              # 未知总量 → 忙碌态
            self._log(t("xfer_log_recv", proto=self.cb_proto.currentText()))

        worker.sig_progress.connect(self._on_progress)
        worker.sig_done.connect(self._on_done)
        self._worker = worker
        self.app._xfer_attach(worker)           # 主窗接管收流 + 提供发送桥
        self._set_busy(True)
        worker.start()

    def _cancel(self):
        if self._worker is not None and self._worker.isRunning():
            self._log(self.app._t("xfer_cancelling"))
            self._worker.cancel()

    def _on_progress(self, done, total):
        if total > 0:
            if self.bar.maximum() != total:
                self.bar.setRange(0, total)
            self.bar.setValue(done)
        else:
            self.bar.setFormat("%d B" % done)   # 未知总量：显示已传字节

    def _on_done(self, ok, msg, result):
        t = self.app._t
        self.app._xfer_detach()
        if self.bar.maximum() == 0:             # 结束忙碌态
            self.bar.setRange(0, 1)
            self.bar.setFormat("%p%")           # 还原百分比格式（接收过程中设了字节格式）
        if ok:
            if self._is_send():
                self.bar.setValue(self.bar.maximum())
                self._log(t("xfer_done_send"))
                self.app.toast(t("xfer_toast_send"))
            else:
                data, meta = result
                out = self._path
                # YMODEM 若带文件名，且用户选的是目录/沿用名，仍写用户选定路径；文件名记进日志
                if meta.get("name"):
                    self._log(t("xfer_log_meta", name=meta.get("name", ""), n=meta.get("size", len(data))))
                try:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    try:
                        with open(out, "wb") as f:
                            f.write(data)
                    finally:
                        QApplication.restoreOverrideCursor()
                    self.bar.setRange(0, max(1, len(data)))
                    self.bar.setValue(len(data))
                    self._log(t("xfer_done_recv", path=out, n=len(data)))
                    self.app.toast(t("xfer_toast_recv", n=len(data)))
                except OSError as e:
                    self._log(t("xfer_write_err", msg=e))
                    self.app.toast(t("xfer_write_err", msg=e), error=True)
        elif msg == "__cancelled__":
            self._log(t("xfer_cancelled"))
            self.app.toast(t("xfer_cancelled"), error=True)
        else:
            self._log(t("xfer_failed", msg=msg))
            self.app.toast(t("xfer_failed", msg=msg), error=True)
        if self._worker is not None:
            self._worker.wait(2000)
        self._worker = None
        self._set_busy(False)

    # ---------- 帮助 / 主题 / 语言 ----------
    def _show_help_dlg(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("xfer_help_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                           | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(640, 440)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("xfer_help"))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setAlignment(Qt.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        v.addWidget(scroll, 1)
        btn = QPushButton(self.app._t("dlg_close"))
        btn.setObjectName("PlotGhostBtn")
        btn.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btn)
        v.addLayout(row)
        c = chrome_for(self.app._theme_id())
        dlg.setStyleSheet(localize_qss(
            "QDialog {{ background-color: {bg}; }}"
            "QLabel {{ color: {txt}; background: transparent; font-family: 'Segoe UI'; font-size: 12px; }}"
            "QScrollArea {{ background: transparent; border: 1px solid {sep}; border-radius: 6px; }}"
            "QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            "QPushButton#PlotGhostBtn {{ background-color: {gb}; color: {txt}; border: 0px;"
            " border-radius: 8px; font-size: 12px; padding: 6px 16px; }}"
            "QPushButton#PlotGhostBtn:hover {{ background-color: {gh}; }}".format(
                bg=c["window_bg"], txt=c["text"], sep=c["separator"], gb=c["ghost_bg"], gh=c["ghost_hover"])))
        _set_win_titlebar_dark(dlg, c)
        dlg.exec_()

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("xfer_title"))
        self.lbl_hint.setText(t("xfer_hint"))
        self.btn_help.setToolTip(t("xfer_help_btn"))
        self.lbl_dir.setText(t("xfer_dir"))
        self.rb_send.setText(t("xfer_dir_send"))
        self.rb_recv.setText(t("xfer_dir_recv"))
        self.lbl_proto.setText(t("xfer_proto"))
        for i, (key, _mode) in enumerate(_PROTOS):
            self.cb_proto.setItemText(i, t(key))
        self.lbl_chunk.setText(t("xfer_chunk"))
        self.lbl_delay.setText(t("xfer_delay"))
        self.lbl_file.setText(t("xfer_file") if self._is_send() else t("xfer_save"))
        self.btn_browse.setText(t("xfer_browse"))
        self.btn_start.setText(t("xfer_start"))
        self.btn_cancel.setText(t("xfer_cancel"))
        # 方向 / 协议 / 文件(保存) 行标签定宽成一列 → 输入框在发送 / 接收、各语言下都对齐
        fm = self.lbl_dir.fontMetrics()
        wmax = max(fm.horizontalAdvance(t(k)) for k in ("xfer_dir", "xfer_proto", "xfer_file", "xfer_save")) + 2
        for lb in (self.lbl_dir, self.lbl_proto, self.lbl_file):
            lb.setFixedWidth(wmax)

    def refresh_theme(self):
        c = chrome_for(self.app._theme_id())
        _set_win_titlebar_dark(self, c)
        self.setStyleSheet(localize_qss(_dialog_list_qss(c) + """
            QLabel#XferHint {{ color: {sub}; font-size: 11px; }}
            QTextEdit#XferLog {{ background-color: {panel}; color: {txt}; border: 1px solid {sep};
                border-radius: 6px; font-family: 'Consolas','Courier New',monospace; font-size: 11px; }}
            QProgressBar {{ border: 1px solid {sep}; border-radius: 6px; background-color: {panel};
                height: 16px; text-align: center; color: {txt}; }}
            QProgressBar::chunk {{ background-color: {acc}; border-radius: 5px; }}
            QPushButton#ArHelpBtn {{ background-color: {gb}; color: {sub}; border: 0px;
                border-radius: 12px; font-family: 'Segoe UI'; font-size: 14px; font-weight: 600; }}
            QPushButton#ArHelpBtn:hover {{ background-color: {gh}; color: {txt}; }}
        """.format(sub=c["text_sec"], panel=c["card_bg"], txt=c["text"], sep=c["separator"],
                   acc=c["accent"], gb=c["ghost_bg"], gh=c["ghost_hover"])))
        for cb in self.findChildren(QComboBox):
            if cb.view() and cb.view().window():
                cb.view().window().setStyleSheet("background-color: %s;" % c["combo_dropdown_bg"])

    def closeEvent(self, e):
        # 关窗时若还挂着 worker（运行中、或刚结束 sig_done 尚未处理）：先断桥——putc 的 sig_send 之后落空、
        # 不再碰连接，也不会在已关闭对话框上触发桥回调；再断开 dialog 侧的回调防 sig_done/progress 在已关闭
        # 对话框上执行；运行中的再取消并等它退出，避免悬挂线程。
        w = self._worker
        if w is not None:
            self.app._xfer_detach()
            try:
                w.sig_done.disconnect(self._on_done)
            except (TypeError, RuntimeError):
                pass
            try:
                w.sig_progress.disconnect(self._on_progress)
            except (TypeError, RuntimeError):
                pass
            if w.isRunning():
                w.cancel()
                w.wait(3000)
        self.app.settings.sync()
        super().closeEvent(e)
