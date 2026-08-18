# -*- coding: utf-8 -*-
"""虚拟连接（离线模式）：不接任何硬件/网络，只在进程内环回。

接口与 serial_io.SerialConn / net_io.NetConn 完全一致（open/close/send/is_open +
data_received/error_occurred/state_changed），因此作为一种连接「类型」接入后，
自动应答、Modbus 从机、自动化序列、脚本控制台、波形图、仪表盘等全部现有机制
都能直接在离线状态下跑，不需要各自改造。

用途：
- 没带设备时先把自动应答规则 / 序列用例 / 脚本写好并验证
- 数据回放的落点（回放器把录到的 RX 注入这里）
- 自发自收演示：开「回环」后 send 的数据会原样当成 RX 回来

注意：send() 里不能直接 emit data_received —— 那样会在主窗 _send_text 尚未返回时
重入收包路径。统一用 0ms QTimer 派发到下一轮事件循环。
"""
import logging

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

PROTO_VIRTUAL = "Virtual"

_MAX_INJECT = 1 << 20        # 单次注入字节上限，防脚本/回放一次灌爆界面
_log = logging.getLogger(__name__)


class VirtualConn(QObject):
    """进程内环回连接。loopback=True 时把发出去的数据当成收到的数据回灌。"""

    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    state_changed = pyqtSignal(bool)

    def __init__(self, loopback=False, parent=None):
        super().__init__(parent)
        self.loopback = bool(loopback)
        self._open = False
        self.tx_log = []          # 供测试/回放核对：本连接发出过的数据

    # ---------------- 连接层接口 ----------------
    def open(self):
        if self._open:
            return True
        self._open = True
        # 与 TCP Server / UDP 一致：open() 内同步发 state_changed(True)。主窗已先赋值
        # self.conn 再调 open()，故此处回调看得到连接对象。
        self.state_changed.emit(True)
        return True

    def close(self):
        if not self._open:
            return
        self._open = False
        self.state_changed.emit(False)

    def simulate_link_drop(self, reason="device disconnected"):
        """Inject a mid-session link drop for soak / offline demos.

        Emits error_occurred then closes (state_changed False), matching how
        serial/network backends report sudden disconnects.
        """
        if not self._open:
            return False
        msg = str(reason or "device disconnected")
        self.error_occurred.emit(msg)
        self.close()
        return True

    def send(self, data, target=None):
        """「发出」数据：无硬件，直接算全部写成功。开了回环则异步回灌成 RX。"""
        if not self._open:
            return 0
        payload = bytes(data)
        self.tx_log.append(payload)
        if len(self.tx_log) > 1000:            # 只留最近的，防长跑吃内存
            del self.tx_log[:-1000]
        if self.loopback and payload:
            # 必须延到下一轮事件循环：send() 是在 _send_text 中途被调用的，
            # 同步 emit 会让收包路径在发送尚未收尾时重入。
            QTimer.singleShot(0, lambda d=payload: self._emit_rx(d))
        return len(payload)

    @property
    def is_open(self):
        return self._open

    @property
    def bridge_ready(self):
        return self._open

    # ---------------- 注入（回放 / 手动喂数据）----------------
    def inject(self, data):
        """把 data 当作「设备发来的数据」投进来。回放器与「喂数据」按钮用。"""
        if not self._open:
            return 0
        raw = bytes(data)
        payload = raw[:_MAX_INJECT]
        if len(raw) > _MAX_INJECT:
            _log.warning(
                "VirtualConn.inject truncated %d bytes to %d bytes",
                len(raw), _MAX_INJECT)
        if payload:
            QTimer.singleShot(0, lambda d=payload: self._emit_rx(d))
        return len(payload)

    def _emit_rx(self, data):
        if self._open:                          # 期间可能已关闭，关了就丢弃
            self.data_received.emit(data)
