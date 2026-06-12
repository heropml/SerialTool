# -*- coding: utf-8 -*-
"""串口后台线程：SerialReader / PortScannerThread / OneShotPortScanner。"""
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, pyqtSignal


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
        self.wait(1000)


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
                ports = list(serial.tools.list_ports.comports())
                result = []
                for p in ports:
                    desc = p.description.replace(p.device, "").strip(" ()-")
                    label = f"{p.device}  {desc}" if desc else p.device
                    result.append((p.device, label))
                self.scan_complete.emit(result)
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
            ports = list(serial.tools.list_ports.comports())
            result = []
            for p in ports:
                desc = p.description.replace(p.device, "").strip(" ()-")
                label = f"{p.device}  {desc}" if desc else p.device
                result.append((p.device, label))
            self.scan_complete.emit(result)
        except Exception:
            self.scan_complete.emit([])


