# -*- coding: utf-8 -*-
"""串口后台线程：SerialReader / PortScannerThread / OneShotPortScanner。"""
import logging
import threading
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QObject, QThread, pyqtSignal

_log = logging.getLogger(__name__)


def _safe(func, *args):
    """Run one cleanup/side-effect step; log failures without aborting the caller.

    Same contract as net_io._safe: default debug level stays quiet unless logging is enabled.
    """
    try:
        func(*args)
        return True
    except Exception:
        _log.debug("serial_io step %s failed",
                   getattr(func, "__name__", func), exc_info=True)
        return False


# USB-UART 转换芯片 VID/PID → 芯片型号。系统描述常是泛化的 "USB Serial Port"，
# 在其后补上精确型号（FT232R/CH340…），插着多个同类转接头时更好认。
_USB_UART_CHIPS = {
    (0x1A86, 0x7523): "CH340",       # WCH CH340（最常见）
    (0x1A86, 0x7522): "CH340K",
    (0x1A86, 0x5523): "CH341",
    (0x1A86, 0x5512): "CH341",
    (0x1A86, 0x55D3): "CH343",
    (0x1A86, 0x55D4): "CH9102",
    (0x1A86, 0x55D2): "CH9102",
    (0x1A86, 0x55D5): "CH9103",
    (0x10C4, 0xEA60): "CP2102",      # Silicon Labs
    (0x10C4, 0xEA61): "CP2102N",
    (0x10C4, 0xEA63): "CP2102N",
    (0x10C4, 0xEA70): "CP2105",
    (0x10C4, 0xEA71): "CP2108",
    (0x0403, 0x6001): "FT232R",      # FTDI
    (0x0403, 0x6010): "FT2232",
    (0x0403, 0x6011): "FT4232",
    (0x0403, 0x6014): "FT232H",
    (0x0403, 0x6015): "FT-X",
    (0x067B, 0x2303): "PL2303",      # Prolific
    (0x067B, 0x23A3): "PL2303GC",
    (0x067B, 0x23C3): "PL2303GT",
    (0x067B, 0x23D3): "PL2303GS",
}

# VID → 厂商名，作为未收录 PID 时的退路（至少认出厂家/芯片系）。
_USB_UART_VENDORS = {
    0x1A86: "WCH",
    0x10C4: "Silicon Labs",
    0x0403: "FTDI",
    0x067B: "Prolific",
    0x2341: "Arduino",
    0x239A: "Adafruit",
    0x1B4F: "SparkFun",
    0x303A: "Espressif",
    0x2E8A: "Raspberry Pi",
    0x1FC9: "NXP",
    0x0483: "STMicro",
}


def _chip_ident(vid, pid):
    """VID/PID → 芯片型号（精确）或厂商名（退路）；认不出返回 ''。虚拟/蓝牙口 vid=None→''。"""
    if vid is None:
        return ""
    return _USB_UART_CHIPS.get((vid, pid)) or _USB_UART_VENDORS.get(vid, "")


def _scan_ports():
    """枚举可用串口 → [(device, label), ...]，label 形如 'COM29  USB Serial Port  FT232R'；
    系统描述已含芯片名则不重复补，描述为空时只显示设备名（如 'COM1'）。后台轮询
    (PortScannerThread)与手动一次性扫描(OneShotPortScanner)共用，避免两处各写一份拼接逻辑。"""
    result = []
    for p in serial.tools.list_ports.comports():
        desc = p.description.replace(p.device, "").strip(" ()-")
        chip = _chip_ident(getattr(p, "vid", None), getattr(p, "pid", None))
        # 在系统描述后补精确型号；desc 里已含该型号（如 "USB-SERIAL CH340"）就不重复。
        parts = [desc] if desc else []
        if chip and chip.lower() not in desc.lower():
            parts.append(chip)
        label = f"{p.device}  " + "  ".join(parts) if parts else p.device
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
        self._reconfig_lock = threading.Lock()
        self._reconfiguring = False

    def set_reconfiguring(self, on):
        with self._reconfig_lock:
            self._reconfiguring = bool(on)

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
            except serial.SerialException as e:
                # Live baud/parity reconfigure races the reader; ignore while flagged.
                with self._reconfig_lock:
                    if self._reconfiguring and self._running:
                        continue
                self.error_occurred.emit(str(e))
                break
            except Exception as e:
                self.error_occurred.emit(str(e))
                break

    def stop(self):
        self._running = False
        # Short wait keeps the GUI responsive.  If the OS read is stuck, continue;
        # close() disconnects signals first and _running stops further work.
        if self.isRunning() and not self.wait(200):
            _log.warning("SerialReader still running after 200ms stop timeout")

# ============== 串口连接（接口对齐 net_io 的 NetConn，供统一连接层用）==============
class SerialConn(QObject):
    """把串口包成和 NetConn 一样的接口：open()/close()/send()/is_open + 信号，
    让 main_window 用 self.conn 统一处理串口/网络，不关心底层。
    参数 bytesize/parity/stopbits 传 pyserial 常量（由 main_window 从下拉项解析后给）。"""
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    state_changed = pyqtSignal(bool)

    def __init__(self, port, baud, bytesize, parity, stopbits, parent=None, flow="none"):
        super().__init__(parent)
        self._port = port
        self._baud = baud
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits
        self._flow = flow          # "none" / "rtscts"（硬件 RTS/CTS）/ "xonxoff"（软件 XON/XOFF）
        self._ser = None
        self._reader = None

    def open(self):
        try:
            self._ser = serial.Serial(
                port=self._port, baudrate=self._baud, bytesize=self._bytesize,
                parity=self._parity, stopbits=self._stopbits, timeout=0,
                rtscts=(self._flow == "rtscts"), xonxoff=(self._flow == "xonxoff"),
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
                _log.debug("serial write failed on %s", self._port, exc_info=True)
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
            # Prefer closing the port only after the reader loop has noticed
            # _running=False; if still alive, close anyway (signals already cut).
            if self._reader.isRunning() and not self._reader.wait(100):
                _log.debug("closing serial port while reader still alive")
            self._reader = None
        if self._ser:
            _safe(self._ser.close)
            self._ser = None
        self.state_changed.emit(False)

    @property
    def is_open(self):
        return self._ser is not None and self._ser.is_open

    def apply_params(self, baud=None, bytesize=None, parity=None, stopbits=None, flow=None):
        """不断开连接，把新参数一次性应用到已打开的串口（None=该项不动）。

        pyserial 对已打开端口每次属性赋值都会立即 reconfigure。为避免「baud 改成功、
        parity 改失败」留下硬件跑混合参数、而函数却返回 False 的半应用状态，这里先快照
        调用前的全部属性；任一项赋值抛错就把已改的属性逐一回滚回快照，让硬件与内部记录
        都退回一致的旧状态，再发 error_occurred 让上层掉线路径接管。要么整体生效、要么
        整体不变，绝不留中间态。

        接收线程持有的是同一个 Serial 对象、无需重启；试波特率不用断开重连，接收缓冲也不丢。
        全部成功返回 True 并同步内部记录（掉线重连按新参数）。
        """
        if not (self._ser and self._ser.is_open):
            return False
        # (Serial 属性名, 目标值, 内部记录属性名)；None 的项跳过
        steps = []
        if baud is not None:
            steps.append(("baudrate", int(baud), "_baud"))
        if bytesize is not None:
            steps.append(("bytesize", bytesize, "_bytesize"))
        if parity is not None:
            steps.append(("parity", parity, "_parity"))
        if stopbits is not None:
            steps.append(("stopbits", stopbits, "_stopbits"))
        if flow is not None:
            steps.append(("rtscts", flow == "rtscts", None))
            steps.append(("xonxoff", flow == "xonxoff", None))
        snapshot = {attr: getattr(self._ser, attr) for attr, _v, _rec in steps}
        done = []
        reader = self._reader
        if reader is not None:
            reader.set_reconfiguring(True)
        try:
            try:
                for attr, val, _rec in steps:
                    setattr(self._ser, attr, val)     # 每次赋值即 reconfigure，可能抛
                    done.append(attr)
            except Exception as e:
                for attr in reversed(done):           # 回滚已改的，退回快照
                    if not _safe(setattr, self._ser, attr, snapshot[attr]):
                        # 回滚都失败 → 端口确已坏，交给掉线路径
                        pass
                self.error_occurred.emit(str(e))
                return False
        finally:
            if reader is not None:
                reader.set_reconfiguring(False)
        # 全部硬件赋值成功，再同步内部记录（重连真源）；flow 单独记
        for _attr, val, rec in steps:
            if rec is not None:
                setattr(self, rec, val)
        if flow is not None:
            self._flow = flow
        return True

    # ----- 控制线（仅串口有；NetConn 无这些方法，上层按类型调用）-----
    def set_dtr(self, on):
        """设 DTR 输出线（高=True/低=False）。未连接则忽略。"""
        if self._ser and self._ser.is_open:
            _safe(setattr, self._ser, "dtr", bool(on))

    def set_rts(self, on):
        """设 RTS 输出线（高=True/低=False）。未连接则忽略。"""
        if self._ser and self._ser.is_open:
            _safe(setattr, self._ser, "rts", bool(on))

    def send_break(self, duration=0.25):
        """发送 Break 信号（TX 线保持间隔电平 duration 秒）。未连接则忽略。"""
        if self._ser and self._ser.is_open:
            _safe(self._ser.send_break, duration)

    def read_lines(self):
        """读输入状态线 → {'cts','dsr','dcd','ri'}: bool；未连接/读失败该项为 None。
        键用显示惯例 dcd（Data Carrier Detect），底层读 pyserial 的 cd 属性。"""
        attr = {"cts": "cts", "dsr": "dsr", "dcd": "cd", "ri": "ri"}
        out = {k: None for k in attr}
        if self._ser and self._ser.is_open:
            for k, a in attr.items():
                try:
                    out[k] = bool(getattr(self._ser, a))
                except Exception:
                    _log.debug("read line %s failed", k, exc_info=True)
                    out[k] = None
        return out


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
                ports = _scan_ports()
                # Skip emit after stop()/teardown — emitting into a dying GUI
                # thread is a common Windows access-violation source in CI.
                if self._running:
                    self.scan_complete.emit(ports)
            except Exception:
                _log.debug("port scan failed", exc_info=True)
            if self._running:
                self.msleep(self._interval)

    def stop(self):
        self._running = False
        try:
            self.scan_complete.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.wait(2000)


class OneShotPortScanner(QThread):
    """点 ⟳ 手动刷新端口时用的一次性扫描线程，避免在 GUI 线程跑 comports() 卡顿"""
    scan_complete = pyqtSignal(list)

    def run(self):
        try:
            self.scan_complete.emit(_scan_ports())
        except Exception:
            _log.debug("one-shot port scan failed", exc_info=True)
            self.scan_complete.emit([])


