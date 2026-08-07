# -*- coding: utf-8 -*-
"""串口↔网络双向透传桥接 — 对话框。

_BridgeSidePanel — 一侧连接配置面板（类型选择 + 参数 + 连接/断开）
BridgeDialog     — 顶层对话框（两侧面板 + BridgeEngine + 日志）
"""
import codecs
import logging
import os  # noqa: F401  # needed by _dialog_list_qss

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QWidget, QLabel, QPushButton, QComboBox, QLineEdit,
    QPlainTextEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
    QCheckBox, QFrame, QSizePolicy, QSplitter, QScrollArea,
)

import serial
import serial.tools.list_ports

from bridge import BridgeEngine
from serial_io import SerialConn, OneShotPortScanner
from net_io import (
    TcpServerConn, TcpClientConn, UdpConn,
    ERR_CONN_TIMEOUT, local_ipv4_list, is_valid_ip,
)
from theme import chrome_for
from widgets import IOSSwitch
from fonts import localize_qss
from dialogs import _dialog_list_qss, _set_win_titlebar_dark, _style_combo_popups
from ui_tips import set_tooltip

# ── 常量 ─────────────────────────────────────────────────────
_BAUD_LIST = [
    "1200", "2400", "4800", "9600", "19200", "38400", "57600",
    "115200", "230400", "256000", "460800", "500000", "512000",
    "600000", "750000", "921600", "1000000", "1500000", "2000000",
]
_DATABITS_LIST = ["5", "6", "7", "8"]
_PARITY_LIST = ["None", "Even", "Odd", "Mark", "Space"]
_STOPBITS_LIST = ["1", "1.5", "2"]

_PARITY_MAP = {
    "None": serial.PARITY_NONE, "Even": serial.PARITY_EVEN,
    "Odd": serial.PARITY_ODD, "Mark": serial.PARITY_MARK,
    "Space": serial.PARITY_SPACE,
}
_STOPBITS_MAP = {
    "1": serial.STOPBITS_ONE, "1.5": serial.STOPBITS_ONE_POINT_FIVE,
    "2": serial.STOPBITS_TWO,
}
_DATABITS_MAP = {
    "5": serial.FIVEBITS, "6": serial.SIXBITS,
    "7": serial.SEVENBITS, "8": serial.EIGHTBITS,
}

_BRIDGE_PROTO_SERIAL = 0
_BRIDGE_PROTO_TCP_CLIENT = 1
_BRIDGE_PROTO_TCP_SERVER = 2
_BRIDGE_PROTO_UDP = 3

_LBL_W = 60  # 参数标签固定宽度


# ═══════════════════════════════════════════════════════════════
# _BridgeSidePanel — 一侧连接配置面板
# ═══════════════════════════════════════════════════════════════

_log = logging.getLogger(__name__)


class _BridgeSidePanel(QWidget):
    """一侧连接配置面板：类型选择 + QStackedWidget(4 页参数) + 连接/断开按钮 + 状态。

    不直接连接 data_received —— 由 BridgeEngine.start() 统一连接。
    """

    state_changed = pyqtSignal(bool)  # True=已连接, False=已断开

    def __init__(self, side: int, app, parent=None):
        super().__init__(parent)
        self._side = side          # 0=A, 1=B
        self._side_label = "A" if side == 0 else "B"
        self.app = app
        self._conn = None
        self._connecting = False
        self._scanner = None       # OneShotPortScanner

        self._build_ui()

    # ── UI 构建 ────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # 标题行
        self.lbl_title = QLabel("Side " + self._side_label)
        self.lbl_title.setObjectName("BgSideLabel")

        # 类型下拉
        self.lbl_type = QLabel()
        self.lbl_type.setFixedWidth(_LBL_W)
        self.cb_type = QComboBox()
        self.cb_type.addItems(["Serial", "TCP Client", "TCP Server", "UDP"])
        self.cb_type.currentIndexChanged.connect(self._on_type_changed)

        row_type = QHBoxLayout()
        row_type.setSpacing(6)
        row_type.addWidget(self.lbl_type)
        row_type.addWidget(self.cb_type, 1)
        root.addWidget(self.lbl_title)
        root.addLayout(row_type)

        # ── QStackedWidget：4 页参数面板 ──
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_serial_page())       # 0
        self.stack.addWidget(self._build_tcp_client_page())    # 1
        self.stack.addWidget(self._build_tcp_server_page())    # 2
        self.stack.addWidget(self._build_udp_page())           # 3
        self.stack.setCurrentIndex(0)
        root.addWidget(self.stack)

        # ── 状态 + 连接按钮 ──
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("BgStatus")
        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("BgToggleBtn")
        self.btn_toggle.clicked.connect(self._on_toggle)

        row_btn = QHBoxLayout()
        row_btn.setSpacing(8)
        row_btn.addWidget(self.lbl_status, 1)
        row_btn.addWidget(self.btn_toggle)
        root.addLayout(row_btn)

        # ── 字节统计 ──
        self.lbl_rx = QLabel("RX: 0")
        self.lbl_tx = QLabel("TX: 0")
        self.lbl_rx.setObjectName("BgStat")
        self.lbl_tx.setObjectName("BgStat")
        row_stats = QHBoxLayout()
        row_stats.setSpacing(12)
        row_stats.addWidget(self.lbl_rx)
        row_stats.addWidget(self.lbl_tx)
        row_stats.addStretch()
        root.addLayout(row_stats)

        root.addStretch()

    # ── 各类型参数页 ────────────────────────────────────────

    def _build_serial_page(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 4, 0, 4)
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(6)

        lbl = QLabel(); lbl.setFixedWidth(_LBL_W)
        g.addWidget(lbl, 0, 0)
        self.cb_port = QComboBox()
        self.cb_port.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_scan = QPushButton("⟳")
        self.btn_scan.setObjectName("BgScanBtn")
        self.btn_scan.setFixedSize(30, 26)
        set_tooltip(self.btn_scan, "")
        self.btn_scan.clicked.connect(self._scan_ports_now)
        g.addWidget(self.cb_port, 0, 1)
        g.addWidget(self.btn_scan, 0, 2)

        lbl2 = QLabel(); lbl2.setFixedWidth(_LBL_W)
        g.addWidget(lbl2, 1, 0)
        self.cb_baud = QComboBox()
        self.cb_baud.setEditable(True)
        self.cb_baud.addItems(_BAUD_LIST)
        self.cb_baud.setCurrentText("115200")
        g.addWidget(self.cb_baud, 1, 1, 1, 2)

        lbl3 = QLabel(); lbl3.setFixedWidth(_LBL_W)
        g.addWidget(lbl3, 2, 0)
        self.cb_databits = QComboBox()
        self.cb_databits.addItems(_DATABITS_LIST)
        self.cb_databits.setCurrentText("8")
        g.addWidget(self.cb_databits, 2, 1, 1, 2)

        lbl4 = QLabel(); lbl4.setFixedWidth(_LBL_W)
        g.addWidget(lbl4, 3, 0)
        self.cb_parity = QComboBox()
        self.cb_parity.addItems(_PARITY_LIST)
        self.cb_parity.setCurrentText("None")
        g.addWidget(self.cb_parity, 3, 1, 1, 2)

        lbl5 = QLabel(); lbl5.setFixedWidth(_LBL_W)
        g.addWidget(lbl5, 4, 0)
        self.cb_stopbits = QComboBox()
        self.cb_stopbits.addItems(_STOPBITS_LIST)
        self.cb_stopbits.setCurrentText("1")
        g.addWidget(self.cb_stopbits, 4, 1, 1, 2)

        self._serial_labels = [lbl, lbl2, lbl3, lbl4, lbl5]
        return page

    def _build_tcp_client_page(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 4, 0, 4)
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(6)

        lbl1 = QLabel(); lbl1.setFixedWidth(_LBL_W)
        g.addWidget(lbl1, 0, 0)
        self.ed_remote_ip = QLineEdit("127.0.0.1")
        g.addWidget(self.ed_remote_ip, 0, 1)

        lbl2 = QLabel(); lbl2.setFixedWidth(_LBL_W)
        g.addWidget(lbl2, 1, 0)
        self.ed_remote_port = QLineEdit("8888")
        g.addWidget(self.ed_remote_port, 1, 1)

        self._tcp_client_labels = [lbl1, lbl2]
        return page

    def _build_tcp_server_page(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 4, 0, 4)
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(6)

        lbl1 = QLabel(); lbl1.setFixedWidth(_LBL_W)
        g.addWidget(lbl1, 0, 0)
        self.cb_local_ip_srv = QComboBox()
        self.cb_local_ip_srv.setEditable(True)
        g.addWidget(self.cb_local_ip_srv, 0, 1)

        lbl2 = QLabel(); lbl2.setFixedWidth(_LBL_W)
        g.addWidget(lbl2, 1, 0)
        self.ed_local_port_srv = QLineEdit("8888")
        g.addWidget(self.ed_local_port_srv, 1, 1)

        self._tcp_server_labels = [lbl1, lbl2]
        return page

    def _build_udp_page(self):
        page = QWidget()
        g = QGridLayout(page)
        g.setContentsMargins(0, 4, 0, 4)
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(6)

        lbl1 = QLabel(); lbl1.setFixedWidth(_LBL_W)
        g.addWidget(lbl1, 0, 0)
        self.cb_local_ip_udp = QComboBox()
        self.cb_local_ip_udp.setEditable(True)
        g.addWidget(self.cb_local_ip_udp, 0, 1)

        lbl2 = QLabel(); lbl2.setFixedWidth(_LBL_W)
        g.addWidget(lbl2, 1, 0)
        self.ed_local_port_udp = QLineEdit("9999")
        g.addWidget(self.ed_local_port_udp, 1, 1)

        self.lbl_spec_remote = QLabel()
        self.lbl_spec_remote.setFixedWidth(_LBL_W)
        g.addWidget(self.lbl_spec_remote, 2, 0)
        self.sw_spec_remote = IOSSwitch(False)   # 与主窗口「指定远程」一致的 iOS 拨动开关
        self.sw_spec_remote.toggled.connect(self._on_spec_remote_toggled)
        g.addWidget(self.sw_spec_remote, 2, 1, Qt.AlignLeft | Qt.AlignVCenter)

        lbl3 = QLabel(); lbl3.setFixedWidth(_LBL_W)
        g.addWidget(lbl3, 3, 0)
        self.ed_remote_ip_udp = QLineEdit("127.0.0.1")
        self.ed_remote_ip_udp.setEnabled(False)
        g.addWidget(self.ed_remote_ip_udp, 3, 1)

        lbl4 = QLabel(); lbl4.setFixedWidth(_LBL_W)
        g.addWidget(lbl4, 4, 0)
        self.ed_remote_port_udp = QLineEdit("0")
        self.ed_remote_port_udp.setEnabled(False)
        g.addWidget(self.ed_remote_port_udp, 4, 1)

        self._udp_labels = [lbl1, lbl2, lbl3, lbl4]
        return page

    # ── 端口扫描 ────────────────────────────────────────────

    def _scan_ports_now(self):
        if self._scanner and self._scanner.isRunning():
            return
        self._scanner = OneShotPortScanner()
        self._scanner.scan_complete.connect(self._on_ports_scanned)
        self._scanner.start()

    def _on_ports_scanned(self, port_list):
        prev = self.cb_port.currentData()
        self.cb_port.blockSignals(True)
        self.cb_port.clear()
        for device, label in port_list:
            self.cb_port.addItem(label, device)
        if prev and self.cb_port.findData(prev) >= 0:
            self.cb_port.setCurrentIndex(self.cb_port.findData(prev))
        self.cb_port.blockSignals(False)

    def _refresh_local_ips(self):
        ips = local_ipv4_list()
        for cb in (self.cb_local_ip_srv, self.cb_local_ip_udp):
            prev = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(ips)
            if prev in ips:
                cb.setCurrentText(prev)
            cb.blockSignals(False)

    # ── 类型切换 ────────────────────────────────────────────

    def _on_type_changed(self, idx):
        self.stack.setCurrentIndex(idx)

    def _on_spec_remote_toggled(self, checked):
        self.ed_remote_ip_udp.setEnabled(checked)
        self.ed_remote_port_udp.setEnabled(checked)

    # ── 连接/断开 ────────────────────────────────────────────

    def _on_toggle(self):
        if self._conn:
            self.close_conn()
        else:
            self.open_conn()

    def open_conn(self):
        idx = self.cb_type.currentIndex()
        try:
            if idx == _BRIDGE_PROTO_SERIAL:
                conn = self._open_serial()
            elif idx == _BRIDGE_PROTO_TCP_CLIENT:
                conn = self._open_tcp_client()
            elif idx == _BRIDGE_PROTO_TCP_SERVER:
                conn = self._open_tcp_server()
            else:
                conn = self._open_udp()
        except Exception as e:
            self.app.toast(str(e))
            return None

        if conn is None:
            return None

        self._conn = conn
        self._connecting = True
        conn.state_changed.connect(self._on_conn_state)
        conn.error_occurred.connect(self._on_conn_error)
        if not conn.open():
            self._conn = None
            self._connecting = False
            conn.deleteLater()
            # 现有 Serial/TCP Server/UDP 均已通过 error_occurred 给出具体原因，
            # 不再追加一个无信息量的 "Open failed" 重复提示。
            return None

        # Serial/TCP Server/UDP 会在 open() 内同步发 state_changed(True)；
        # TCP Client 则等异步 connected 信号，不能提前显示为已连接。
        if not conn.is_open:
            self._update_ui_state(False, connecting=True)
        return conn

    def close_conn(self):
        self._connecting = False
        if self._conn:
            try:
                self._conn.state_changed.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._conn.error_occurred.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._conn.data_received.disconnect()
            except (TypeError, RuntimeError):
                pass
            # TCP Client 处于 ConnectingState 时 is_open=False，也必须 close/abort，
            # 不能只依赖 deleteLater 延迟取消底层连接。
            try:
                self._conn.close()
            except Exception:
                _log.debug("bridge_dialog close_conn failed", exc_info=True)
            self._conn.deleteLater()
            self._conn = None
        self._update_ui_state(False)
        self.state_changed.emit(False)

    def _open_serial(self):
        port = self.cb_port.currentData()
        if not port:
            self.app.toast(self.app._t("bg_need_port"))
            return None
        baud = int(self.cb_baud.currentText())
        return SerialConn(
            port, baud,
            _DATABITS_MAP[self.cb_databits.currentText()],
            _PARITY_MAP[self.cb_parity.currentText()],
            _STOPBITS_MAP[self.cb_stopbits.currentText()],
            flow="none",
        )

    def _open_tcp_client(self):
        ip = self.ed_remote_ip.text().strip()
        port = int(self.ed_remote_port.text() or "0")
        if not is_valid_ip(ip) or not 1 <= port <= 65535:
            self.app.toast(self.app._t("bg_bad_addr"))
            return None
        return TcpClientConn(ip, port)

    def _open_tcp_server(self):
        ip = self.cb_local_ip_srv.currentText().strip()
        port = int(self.ed_local_port_srv.text() or "0")
        if (ip not in ("", "0.0.0.0") and not is_valid_ip(ip)):
            self.app.toast(self.app._t("bg_bad_addr"))
            return None
        if not 1 <= port <= 65535:
            self.app.toast(self.app._t("bg_bad_port"))
            return None
        return TcpServerConn(ip, port)

    def _open_udp(self):
        lip = self.cb_local_ip_udp.currentText().strip()
        lport = int(self.ed_local_port_udp.text() or "0")
        if (lip not in ("", "0.0.0.0") and not is_valid_ip(lip)):
            self.app.toast(self.app._t("bg_bad_addr"))
            return None
        if not 1 <= lport <= 65535:
            self.app.toast(self.app._t("bg_bad_port"))
            return None
        if self.sw_spec_remote.isChecked():
            rip = self.ed_remote_ip_udp.text().strip()
            rport = int(self.ed_remote_port_udp.text() or "0")
            if not is_valid_ip(rip) or not 1 <= rport <= 65535:
                self.app.toast(self.app._t("bg_bad_addr"))
                return None
        else:
            rip, rport = "", 0
        return UdpConn(lip, lport, rip, rport)

    # ── 连接状态回调 ────────────────────────────────────────

    def _on_conn_state(self, opened):
        if opened:
            self._connecting = False
            self._update_ui_state(True)
            self.state_changed.emit(True)
        else:
            # 让同一 state_changed(False) 上的 BridgeEngine 槽先完成自动停桥，
            # 再清理连接；否则 close_conn() 立即 disconnect() 会令引擎漏掉断线。
            conn = self._conn
            if conn is not None:
                QTimer.singleShot(0, lambda c=conn: self._close_if_current(c))

    def _on_conn_error(self, msg):
        if msg == ERR_CONN_TIMEOUT:
            msg = self.app._t("err_conn_timeout")
        self.app.toast(f"Side {self._side_label}: {msg}")
        # 连接层错误均为致命错误。延后清理，让 BridgeEngine 的同一错误槽先自动停桥；
        # 同时绑定当前对象，防止旧连接的迟到错误误关用户刚建立的新连接。
        conn = self._conn
        if conn is not None:
            QTimer.singleShot(0, lambda c=conn: self._close_if_current(c))

    def _close_if_current(self, conn):
        if self._conn is conn:
            self.close_conn()

    # ── UI 状态 ──────────────────────────────────────────────

    def _update_ui_state(self, connected, connecting=False):
        t = self.app._t
        if connected:
            self.btn_toggle.setText(t("bg_close"))
            self.lbl_status.setText(t("bg_connected"))
        elif connecting:
            self.btn_toggle.setText(t("bg_cancel"))
            self.lbl_status.setText(t("bg_connecting"))
        else:
            self.btn_toggle.setText(t("bg_open"))
            self.lbl_status.setText(t("bg_disconnected"))
        # 同主窗打开按钮：连接后 state="open" → 变红（关闭），未连接 → 蓝（打开）
        self.btn_toggle.setProperty("state", "open" if connected else "")
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)

    def update_stats(self, rx, tx):
        self.lbl_rx.setText(f"RX: {rx:,}")
        self.lbl_tx.setText(f"TX: {tx:,}")

    def set_settings_enabled(self, enabled):
        self.cb_type.setEnabled(enabled)
        self.stack.setEnabled(enabled)
        self.btn_toggle.setEnabled(enabled)

    def connection(self):
        if self._conn and self._conn.is_open:
            return self._conn
        return None

    def is_connected(self):
        return self._conn is not None and self._conn.is_open

    def shutdown(self):
        if self._scanner and self._scanner.isRunning():
            self._scanner.scan_complete.disconnect()
            self._scanner.quit()
            self._scanner.wait(2000)
        self.close_conn()

    # ── 配置持久化 ──────────────────────────────────────────

    def _prefix(self) -> str:
        return f"bridge/side_{'a' if self._side == 0 else 'b'}"

    def save_config(self):
        pfx = self._prefix()
        s = self.app.settings
        s.setValue(f"{pfx}_type", self.cb_type.currentIndex())
        s.setValue(f"{pfx}_serial_port", self.cb_port.currentData() or "")
        s.setValue(f"{pfx}_serial_baud", self.cb_baud.currentText())
        s.setValue(f"{pfx}_serial_databits", self.cb_databits.currentText())
        s.setValue(f"{pfx}_serial_parity", self.cb_parity.currentText())
        s.setValue(f"{pfx}_serial_stopbits", self.cb_stopbits.currentText())
        s.setValue(f"{pfx}_tc_remote_ip", self.ed_remote_ip.text())
        s.setValue(f"{pfx}_tc_remote_port", self.ed_remote_port.text())
        s.setValue(f"{pfx}_ts_local_ip", self.cb_local_ip_srv.currentText())
        s.setValue(f"{pfx}_ts_local_port", self.ed_local_port_srv.text())
        s.setValue(f"{pfx}_udp_local_ip", self.cb_local_ip_udp.currentText())
        s.setValue(f"{pfx}_udp_local_port", self.ed_local_port_udp.text())
        s.setValue(f"{pfx}_udp_spec_remote", self.sw_spec_remote.isChecked())
        s.setValue(f"{pfx}_udp_remote_ip", self.ed_remote_ip_udp.text())
        s.setValue(f"{pfx}_udp_remote_port", self.ed_remote_port_udp.text())

    def load_config(self):
        pfx = self._prefix()
        s = self.app.settings
        try:
            idx = int(s.value(f"{pfx}_type", 0))
        except (TypeError, ValueError):
            idx = 0
        idx = max(0, min(3, idx))
        self.cb_type.setCurrentIndex(idx)
        port_data = s.value(f"{pfx}_serial_port", "")
        if port_data:
            self.cb_port.addItem(str(port_data), port_data)
        self.cb_baud.setCurrentText(s.value(f"{pfx}_serial_baud", "115200"))
        self.cb_databits.setCurrentText(s.value(f"{pfx}_serial_databits", "8"))
        self.cb_parity.setCurrentText(s.value(f"{pfx}_serial_parity", "None"))
        self.cb_stopbits.setCurrentText(s.value(f"{pfx}_serial_stopbits", "1"))
        self.ed_remote_ip.setText(s.value(f"{pfx}_tc_remote_ip", "127.0.0.1"))
        self.ed_remote_port.setText(s.value(f"{pfx}_tc_remote_port", "8888"))
        self.cb_local_ip_srv.setCurrentText(
            s.value(f"{pfx}_ts_local_ip", "0.0.0.0"))
        self.ed_local_port_srv.setText(s.value(f"{pfx}_ts_local_port", "8888"))
        self.cb_local_ip_udp.setCurrentText(
            s.value(f"{pfx}_udp_local_ip", "0.0.0.0"))
        self.ed_local_port_udp.setText(s.value(f"{pfx}_udp_local_port", "9999"))
        self.sw_spec_remote.setChecked(
            s.value(f"{pfx}_udp_spec_remote", False, bool))
        self.ed_remote_ip_udp.setText(
            s.value(f"{pfx}_udp_remote_ip", "127.0.0.1"))
        self.ed_remote_port_udp.setText(
            s.value(f"{pfx}_udp_remote_port", "0"))

    def refresh_theme(self):
        # 大部分样式在 BridgeDialog.setStyleSheet 统一处理；IOSSwitch 是自绘控件、需单独上主题色
        c = chrome_for(self.app._theme_id())
        self.sw_spec_remote.set_theme_colors(c["separator"], "#FFFFFF")

    def retranslate(self):
        t = self.app._t
        self.lbl_type.setText(t("bg_type"))
        self._update_ui_state(self.is_connected(), self._connecting)
        port_lbl, baud_lbl, dbits_lbl, parity_lbl, sbits_lbl = self._serial_labels
        port_lbl.setText(t("bg_port"))
        baud_lbl.setText(t("bg_baud"))
        dbits_lbl.setText(t("bg_databits"))
        parity_lbl.setText(t("bg_parity"))
        sbits_lbl.setText(t("bg_stopbits"))
        rip_lbl, rport_lbl = self._tcp_client_labels
        rip_lbl.setText(t("bg_remote_ip"))
        rport_lbl.setText(t("bg_remote_port"))
        lip_lbl, lport_lbl = self._tcp_server_labels
        lip_lbl.setText(t("bg_local_ip"))
        lport_lbl.setText(t("bg_local_port"))
        ulip_lbl, ulport_lbl, urip_lbl, urport_lbl = self._udp_labels
        ulip_lbl.setText(t("bg_local_ip"))
        ulport_lbl.setText(t("bg_local_port"))
        urip_lbl.setText(t("bg_remote_ip"))
        urport_lbl.setText(t("bg_remote_port"))
        self.lbl_spec_remote.setText(t("bg_spec_remote"))
        set_tooltip(self.btn_scan, t("bg_refresh_ports"))


# ═══════════════════════════════════════════════════════════════
# BridgeDialog — 顶层对话框
# ═══════════════════════════════════════════════════════════════

class BridgeDialog(QDialog):
    """串口↔网络双向透传桥接对话框。"""

    _MAX_LOG_LINES = 5000
    _MAX_LOG_BYTES_PER_ENTRY = 4096

    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
            | Qt.WindowSystemMenuHint | Qt.WindowTitleHint
        )
        self.setWindowModality(Qt.NonModal)
        self.setMinimumSize(820, 560)
        self.resize(860, 600)

        self.engine = BridgeEngine(self)
        self._reset_log_decoders()
        self._build_ui()
        self._connect_engine()
        self._load_config()
        self._scan_ports_both()

    # ── UI 构建 ────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        # ── 左右 Side Panel（直接放入 QSplitter，用简约框架包裹）──
        self.panel_a = _BridgeSidePanel(0, self.app)
        self.panel_b = _BridgeSidePanel(1, self.app)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("BgPanelsSplitter")
        splitter.addWidget(self._wrap_side(self.panel_a, "A"))
        splitter.addWidget(self._wrap_side(self.panel_b, "B"))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # ── 桥接控制条（统计 + 按钮 + 帮助）──
        self.lbl_ab = QLabel("A→B: 0 B")
        self.lbl_ba = QLabel("B→A: 0 B")
        self.lbl_ab.setObjectName("BgCount")
        self.lbl_ba.setObjectName("BgCount")

        self.btn_start = QPushButton()
        self.btn_start.setObjectName("DialogPrimaryBtn")
        self.btn_start.setMinimumHeight(28)
        self.btn_start.clicked.connect(self._on_start)
        # placed in retranslate/layout if present

        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("DialogDangerBtn")
        self.btn_stop.setMinimumHeight(28)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setVisible(False)

        self.lbl_bridge_status = QLabel()
        self.lbl_bridge_status.setObjectName("BgBridgeStatus")

        self.btn_help = QPushButton("?")
        self.btn_help.setObjectName("ArHelpBtn")
        self.btn_help.setFixedSize(24, 24)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self._show_help)

        self.chk_modbus_gw = QCheckBox()
        self.chk_modbus_gw.setObjectName('BgGwCheck')

        row_ctrl = QHBoxLayout()
        row_ctrl.setSpacing(10)
        row_ctrl.addWidget(self.lbl_ab)
        row_ctrl.addWidget(self.lbl_ba)
        row_ctrl.addStretch()
        row_ctrl.addWidget(self.lbl_bridge_status)
        row_ctrl.addWidget(self.chk_modbus_gw)
        row_ctrl.addWidget(self.btn_start)
        row_ctrl.addWidget(self.btn_stop)
        row_ctrl.addWidget(self.btn_help)
        root.addLayout(row_ctrl)

        # ── 流量日志（section 标签 + 工具栏 + 文本框）──
        self.lbl_log_section = QLabel()
        self.lbl_log_section.setObjectName("TbSection")
        root.addWidget(self.lbl_log_section)

        self.sw_log = QCheckBox()
        self.sw_log.toggled.connect(self._on_log_toggled)
        self.sw_log_hex = QCheckBox()
        self.sw_log_hex.setChecked(True)
        self.sw_log_hex.toggled.connect(self._reset_log_decoders)
        self.btn_clear_log = QPushButton()
        self.btn_clear_log.setObjectName("PlotGhostBtn")
        self.btn_clear_log.clicked.connect(self._clear_log)
        self.lbl_max_lines = QLabel("Max:")
        self.ed_max_lines = QLineEdit(str(self._MAX_LOG_LINES))
        self.ed_max_lines.setFixedWidth(50)
        self.ed_max_lines.setObjectName("BgMaxLines")
        self.ed_max_lines.editingFinished.connect(self._apply_max_log_lines)

        row_log_tools = QHBoxLayout()
        row_log_tools.setSpacing(8)
        row_log_tools.addWidget(self.sw_log)
        row_log_tools.addWidget(self.sw_log_hex)
        row_log_tools.addWidget(self.btn_clear_log)
        row_log_tools.addStretch()
        row_log_tools.addWidget(self.lbl_max_lines)
        row_log_tools.addWidget(self.ed_max_lines)
        root.addLayout(row_log_tools)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setObjectName("BgLogText")
        self.txt_log.setMaximumBlockCount(self._MAX_LOG_LINES)
        root.addWidget(self.txt_log, 1)

    def _wrap_side(self, panel: _BridgeSidePanel, label: str) -> QFrame:
        """用简约 QFrame 包裹一侧面板。"""
        frame = QFrame()
        frame.setObjectName("BgSideFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        title = QLabel(label)
        title.setObjectName("BgSideLabel")
        lay.addWidget(title)
        lay.addWidget(panel, 1)
        return frame

    # ── 引擎信号 ─────────────────────────────────────────────

    def _connect_engine(self):
        eng = self.engine
        eng.started.connect(self._on_bridge_started)
        eng.stopped.connect(self._on_bridge_stopped)
        eng.stats_updated.connect(self._on_stats)
        eng.side_state.connect(self._on_side_state)
        eng.error_occurred.connect(self._on_side_error)
        eng.forwarded.connect(self._on_forwarded)

    # ── 开始/停止桥接 ────────────────────────────────────────

    def _on_start(self):
        if self.engine.is_active():
            return
        c_a = self.panel_a.connection()
        c_b = self.panel_b.connection()
        if not c_a or not c_b:
            self.app.toast(self.app._t("bg_need_both"))
            return
        if self._same_port(c_a, c_b):
            self.app.toast(self.app._t("bg_same_port"))
            return
        waiting = [label for label, conn in (("A", c_a), ("B", c_b))
                   if not getattr(conn, "bridge_ready", True)]
        if waiting:
            self.app.toast(self.app._t("bg_wait_target", side="/".join(waiting)))
            return

        self.engine.set_connection(0, c_a)
        self.engine.set_connection(1, c_b)
        self.engine.set_modbus_gateway(
            bool(getattr(self, "chk_modbus_gw", None) and self.chk_modbus_gw.isChecked()))
        if self.engine.start():
            self._log_to_view("Bridge started")
        else:
            self.app.toast("Bridge start failed")

    def _on_stop(self):
        if self.engine.is_active():
            self.engine.stop("User stopped")

    def _on_bridge_started(self):
        self.btn_start.setVisible(False)
        self.btn_stop.setVisible(True)
        self.lbl_bridge_status.setText(self.app._t("bg_bridging"))
        self.panel_a.set_settings_enabled(False)
        self.panel_b.set_settings_enabled(False)
        refresh = getattr(self.app, "_refresh_workspace_statuses", None)
        if refresh is not None:
            refresh()

    def _on_bridge_stopped(self, reason):
        self.btn_start.setVisible(True)
        self.btn_stop.setVisible(False)
        self.lbl_bridge_status.setText(self.app._t("bg_stopped_status"))
        self.panel_a.set_settings_enabled(True)
        self.panel_b.set_settings_enabled(True)
        refresh = getattr(self.app, "_refresh_workspace_statuses", None)
        if refresh is not None:
            refresh()
        self._reset_log_decoders()
        self._log_to_view(f"Bridge stopped{f': {reason}' if reason else ''}")
        if reason and reason != "User stopped" and " error:" not in reason:
            self.app.toast(self.app._t("bg_stopped_reason", reason=reason))

    # ── 统计 ─────────────────────────────────────────────────

    def _on_stats(self, a_rx, a_tx, b_rx, b_tx, a_rate, b_rate):
        self.panel_a.update_stats(a_rx, a_tx)
        self.panel_b.update_stats(b_rx, b_tx)

        def fmt(n):
            if n >= 1_000_000:
                return f"{n/1_000_000:.1f} MB"
            elif n >= 1_000:
                return f"{n/1_000:.1f} KB"
            return f"{n} B"

        def rate_fmt(r):
            if r >= 1_000_000:
                return f"{r/1_000_000:.1f} MB/s"
            elif r >= 1_000:
                return f"{r/1_000:.1f} KB/s"
            return f"{r} B/s"

        self.lbl_ab.setText(f"A→B: {fmt(b_tx)} ({rate_fmt(a_rate)})")
        self.lbl_ba.setText(f"B→A: {fmt(a_tx)} ({rate_fmt(b_rate)})")

    def _on_side_state(self, side, opened):
        label = "A" if side == 0 else "B"
        self._log_to_view(f"Side {label} {'connected' if opened else 'disconnected'}")

    def _on_side_error(self, side, msg):
        label = "A" if side == 0 else "B"
        self._log_to_view(f"Side {label} error: {msg}")

    # ── 日志 ─────────────────────────────────────────────────

    def _on_log_toggled(self, enabled):
        self._reset_log_decoders()

    def _disconnect_log_signals(self):
        # 日志改由 BridgeEngine.forwarded（仅成功转发）驱动，无连接层槽需要摘除。
        self._reset_log_decoders()

    def _on_forwarded(self, direction, data):
        self._append_log(direction, "A→B" if direction == 0 else "B→A", data)

    def _reset_log_decoders(self, *_args):
        self._log_decoders = [
            codecs.getincrementaldecoder("utf-8")(errors="replace"),
            codecs.getincrementaldecoder("utf-8")(errors="replace"),
        ]

    def _append_log(self, direction_idx, direction, data):
        if not self.sw_log.isChecked():
            return
        from datetime import datetime
        now = datetime.now()
        ts = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
        raw = bytes(data)
        omitted = max(0, len(raw) - self._MAX_LOG_BYTES_PER_ENTRY)
        preview = raw[:self._MAX_LOG_BYTES_PER_ENTRY]
        suffix = f" … (+{omitted} bytes)" if omitted else ""
        if self.sw_log_hex.isChecked():
            hex_str = " ".join(f"{b:02X}" for b in preview)
            line = f"[{ts}] {direction}: {hex_str}{suffix}"
        else:
            if omitted:
                text = preview.decode("utf-8", errors="replace")
                self._reset_log_decoders()
            else:
                text = self._log_decoders[direction_idx].decode(preview, final=False)
            text = text.replace("\r", "\\r").replace("\n", "\\n")
            line = f"[{ts}] {direction}: {text}{suffix}"
        self.txt_log.appendPlainText(line)

    def _log_to_view(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt_log.appendPlainText(f"[{ts}] {msg}")

    def _clear_log(self):
        self.txt_log.clear()

    # ── 主题 / 翻译 ──────────────────────────────────────────

    def retranslate(self):
        t = self.app._t
        self.setWindowTitle(t("bg_title"))
        self.lbl_log_section.setText(t("bg_log_title"))
        set_tooltip(self.btn_help, t("bg_help"))
        self.btn_start.setText(t("bg_start"))
        if hasattr(self, "chk_modbus_gw"):
            self.chk_modbus_gw.setText(t("bg_modbus_gw"))
            set_tooltip(self.chk_modbus_gw, t("bg_modbus_gw_tip"))
        self.btn_stop.setText(t("bg_stop"))
        self.sw_log.setText(t("bg_log_enable"))
        self.sw_log_hex.setText(t("bg_log_hex"))
        self.btn_clear_log.setText(t("bg_log_clear"))
        self.lbl_max_lines.setText(t("bg_max_lines"))
        if not self.engine.is_active():
            self.lbl_bridge_status.setText(t("bg_stopped_status"))
        else:
            self.lbl_bridge_status.setText(t("bg_bridging"))
        self.panel_a.retranslate()
        self.panel_b.retranslate()

    def refresh_theme(self):
        c = chrome_for(self.app._theme_id())
        _set_win_titlebar_dark(self, c)
        qss = localize_qss(_dialog_list_qss(c) + """
            QLabel#BgSideLabel {{
                font-size: 12px; font-weight: 600; color: {text};
            }}
            QLabel#BgStatus {{
                font-size: 11px; color: {text};
            }}
            QLabel#BgCount {{
                font-size: 11px; color: {text_sec}; font-family: monospace;
            }}
            QLabel#BgBridgeStatus {{
                font-size: 11px; color: {accent}; font-weight: 600;
            }}
            QLabel#BgStat {{
                font-size: 10px; color: {text_sec}; font-family: monospace;
            }}
            QPushButton#ArHelpBtn {{
                background-color: {ghost_bg}; color: {text_sec}; border: 0px;
                border-radius: 12px; font-family: 'Segoe UI'; font-size: 14px;
                font-weight: 600;
            }}
            QPushButton#ArHelpBtn:hover {{
                background-color: {ghost_hover}; color: {text};
            }}
            QPushButton#BgToggleBtn {{
                background-color: {accent}; color: white; border: 0px;
                border-radius: 9px; font-family: 'Segoe UI'; font-size: 12px;
                font-weight: 600; padding: 5px 18px;
            }}
            QPushButton#BgToggleBtn:hover {{ background-color: {accent_hover}; }}
            QPushButton#BgToggleBtn:pressed {{ background-color: {accent_pressed}; }}
            QPushButton#BgToggleBtn[state="open"] {{ background-color: {danger}; }}
            QPushButton#BgToggleBtn[state="open"]:hover {{ background-color: {danger_hover}; }}
            QPushButton#BgScanBtn {{
                background-color: {ghost_bg}; color: {text_sec};
                border: 0px; border-radius: 8px; font-size: 13px;
            }}
            QPushButton#BgScanBtn:hover {{
                background-color: {ghost_hover}; color: {accent};
            }}
            QPushButton#DialogPrimaryBtn {{
                background-color: {accent}; color: white; border: 0px; border-radius: 9px;
                font-family: 'Segoe UI'; font-size: 13px; font-weight: 600; padding: 6px 14px;
            }}
            QPushButton#DialogPrimaryBtn:hover {{ background-color: {accent_hover}; }}
            QPushButton#DialogPrimaryBtn:pressed {{ background-color: {accent_pressed}; }}
            QPushButton#DialogDangerBtn {{
                background-color: {danger}; color: white; border: 0px; border-radius: 9px;
                font-family: 'Segoe UI'; font-size: 13px; font-weight: 600; padding: 6px 14px;
            }}
            QPushButton#DialogDangerBtn:hover {{ background-color: {danger_hover}; }}
            QFrame#BgSideFrame {{
                background-color: {card_bg}; border: 1px solid {separator};
                border-radius: 6px;
            }}
            QPlainTextEdit#BgLogText {{
                background-color: {input_bg}; color: {text};
                border: 1px solid {separator}; border-radius: 4px;
                font-family: monospace; font-size: 11px;
            }}
            QLineEdit#BgMaxLines {{
                background-color: {input_bg}; color: {text};
                border: 1px solid {separator}; border-radius: 3px;
                padding: 2px 4px; font-family: monospace; font-size: 11px;
            }}
        """.format(**c))
        self.setStyleSheet(qss)
        _style_combo_popups(self, c)
        self.panel_a.refresh_theme()
        self.panel_b.refresh_theme()

    # ── 工具方法 ─────────────────────────────────────────────

    def _same_port(self, conn_a, conn_b) -> bool:
        if hasattr(conn_a, "_port") and hasattr(conn_b, "_port"):
            return conn_a._port == conn_b._port
        return False

    def _scan_ports_both(self):
        self.panel_a._scan_ports_now()
        self.panel_b._scan_ports_now()
        self.panel_a._refresh_local_ips()
        self.panel_b._refresh_local_ips()

    def _show_help(self):
        # 主题化帮助窗（同 工具箱 / 文件传输 的 _show_help_dlg），不用原生 QMessageBox
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app._t("bg_title"))
        dlg.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                           | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint | Qt.WindowTitleHint)
        dlg.resize(560, 380)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        lbl = QLabel(self.app._t("bg_help"))
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.PlainText)        # bg_help 是带换行的纯文本
        lbl.setAlignment(Qt.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        v.addWidget(scroll, 1)
        btn = QPushButton({"zh": "关闭", "en": "Close", "zh_tw": "關閉"}.get(self.app._lang, "Close"))
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

    # ── 配置持久化 ──────────────────────────────────────────

    def _load_config(self):
        self.panel_a.load_config()
        self.panel_b.load_config()
        s = self.app.settings
        self.sw_log.setChecked(s.value("bridge/log_enabled", False, bool))
        self.sw_log_hex.setChecked(s.value("bridge/log_hex", True, bool))
        try:
            max_lines = int(s.value("bridge/log_max_lines", self._MAX_LOG_LINES))
        except (TypeError, ValueError):
            max_lines = self._MAX_LOG_LINES
        max_lines = max(1, min(100000, max_lines))
        self.ed_max_lines.setText(str(max_lines))
        self.txt_log.setMaximumBlockCount(max_lines)
        geo = s.value("bridge/geometry")
        if geo:
            self.restoreGeometry(geo)

    def _save_config(self):
        self._apply_max_log_lines()
        self.panel_a.save_config()
        self.panel_b.save_config()
        s = self.app.settings
        s.setValue("bridge/log_enabled", self.sw_log.isChecked())
        s.setValue("bridge/log_hex", self.sw_log_hex.isChecked())
        s.setValue("bridge/log_max_lines", int(self.ed_max_lines.text()))
        s.setValue("bridge/geometry", self.saveGeometry())

    def _apply_max_log_lines(self):
        """即时应用并规范化日志行数，防坏配置导致无限日志或异常值。"""
        try:
            value = int(self.ed_max_lines.text())
        except ValueError:
            value = self._MAX_LOG_LINES
        value = max(1, min(100000, value))
        self.ed_max_lines.setText(str(value))
        self.txt_log.setMaximumBlockCount(value)

    # ── 生命周期 ─────────────────────────────────────────────

    def closeEvent(self, e):
        if self.engine.is_active():
            self.engine.stop("Dialog closed")
        self._disconnect_log_signals()
        self.panel_a.shutdown()
        self.panel_b.shutdown()
        self._save_config()
        self.app.settings.sync()
        super().closeEvent(e)
