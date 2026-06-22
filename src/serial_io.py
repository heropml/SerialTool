# -*- coding: utf-8 -*-
"""串口后台线程：SerialReader / PortScannerThread / OneShotPortScanner。"""
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QObject, QThread, pyqtSignal


def _scan_ports():
    """枚举可用串口 → [(device, label), ...]，label 形如 'COM3  USB-SERIAL CH340'。
    后台轮询(PortScannerThread)与手动一次性扫描(OneShotPortScanner)共用，
    避免两处各写一份 label 拼接逻辑、改一处漏另一处导致显示格式漂移。"""
    result = []
    for p in serial.tools.list_ports.comports():
        desc = p.description.replace(p.device, "").strip(" ()-")
        label = f"{p.device}  {desc}" if desc else p.device
        result.append((p.device, label))
    return result


# ============== 串口读取线程 ==============
class SerialReader(QThread):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)

    def __init__(self, ser):
        super().__init__()
        self.ser = ser
        self._running = True

    def run(self):
        while self._running:
            try:
                if self.ser and self.ser.is_open:
                    n = self.ser.in_waiting
                    if n > 0:
                        data = self.ser.read(n)
                        if data:
                            self.data_received.emit(data)
                    else:
                        self.msleep(10)
                else:
                    self.msleep(50)
            except Exception as e:
                self.error_occurred.emit(str(e))
                break

    def stop(self):
        self._running = False
        # in_waiting 不阻塞、read 仅在有数据时调用，run 循环最多 50ms 就检查一次
        # _running，正常 1s 内必退出；给足 3s 余量应对设备异常时底层调用偶发卡顿。
        # 万一仍未退出，此后 ser 已被上层 close()，run 里 is_open=False 只会空转
        # msleep 并在下一轮 _running=False 自行结束，不会再访问已关闭的串口句柄。
        self.wait(3000)

# ============== 串口连接（接口对齐 net_io 的 NetConn，供统一连接层用）==============
class SerialConn(QObject):
    """把串口包成和 NetConn 一样的接口：open()/close()/send()/is_open + 信号，
    让 main_window 用 self.conn 统一处理串口/网络，不关心底层。
    参数 bytesize/parity/stopbits 传 pyserial 常量（由 main_window 从下拉项解析后给）。"""
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    state_changed = pyqtSignal(bool)

    def __init__(self, port, baud, bytesize, parity, stopbits, parent=None):
        super().__init__(parent)
        self._port = port
        self._baud = baud
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits
        self._ser = None
        self._reader = None

    def open(self):
        try:
            self._ser = serial.Serial(
                port=self._port, baudrate=self._baud, bytesize=self._bytesize,
                parity=self._parity, stopbits=self._stopbits, timeout=0,
            )
        except Exception as e:
            self.error_occurred.emit(str(e))
            self._ser = None
            return False
        self._reader = SerialReader(self._ser)
        self._reader.data_received.connect(self.data_received)
        self._reader.error_occurred.connect(self._on_reader_error)
        self._reader.start()
        self.state_changed.emit(True)
        return True

    def _on_reader_error(self, msg):
        self.error_occurred.emit(msg)

    def send(self, data, target=None):
        if self._ser and self._ser.is_open:
            try:
                n = self._ser.write(data)
                return n if n is not None else len(data)
            except Exception:
                return 0
        return 0

    def close(self):
        # 已关闭则直接返回：避免重复 close 再次 emit state_changed(False)
        # （当前由 close_conn 的 blockSignals 兜着，这里加守卫让 SerialConn 被直接复用时也不会虚假"对端已断开"）
        if self._reader is None and self._ser is None:
            return
        if self._reader:
            # 先断信号再 stop：避免 stop 期间排队的 error_occurred 在 reader 置 None 后重入
            try:
                self._reader.data_received.disconnect(self.data_received)
                self._reader.error_occurred.disconnect(self._on_reader_error)
            except (TypeError, RuntimeError):
                pass
            self._reader.stop()
            self._reader = None
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self.state_changed.emit(False)

    @property
    def is_open(self):
        return self._ser is not None and self._ser.is_open


# ============== 后台串口扫描线程 ==============
class PortScannerThread(QThread):
    """后台轮询可用串口，避免在 GUI 线程调用 comports() 偶发卡顿"""
    scan_complete = pyqtSignal(list)

    def __init__(self, interval_ms: int = 1500, parent=None):
        super().__init__(parent)
        self._running = True
        self._interval = interval_ms

    def run(self):
        while self._running:
            try:
                self.scan_complete.emit(_scan_ports())
            except Exception:
                pass
            self.msleep(self._interval)

    def stop(self):
        self._running = False
        self.wait(2000)


class OneShotPortScanner(QThread):
    """点 ⟳ 手动刷新端口时用的一次性扫描线程，避免在 GUI 线程跑 comports() 卡顿"""
    scan_complete = pyqtSignal(list)

    def run(self):
        try:
            self.scan_complete.emit(_scan_ports())
        except Exception:
            self.scan_complete.emit([])


