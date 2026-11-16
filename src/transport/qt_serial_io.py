# -*- coding: utf-8 -*-
"""QSerialPort adapter. Its port and all port operations live in one Qt thread."""
import logging
import math
import sys
import time

from PyQt5.QtCore import (QObject, QThread, QTimer, QIODevice, QMetaObject,
                          Q_ARG, Qt, pyqtSignal, pyqtSlot)
from PyQt5.QtSerialPort import QSerialPort

from transport.serial_io import _safe
from transport.net_io import _pending_overflow

_log = logging.getLogger(__name__)


def _validate_format(config):
    # Qt 5 Unix has no 1.5-stop-bit setting. macOS Mark/Space transmission
    # uses per-byte software parity emulation, without native RX support.
    if sys.platform != "win32" and config["stopbits"] == 1.5:
        raise ValueError("QSerialPort does not support 1.5 stop bits on this platform")
    if sys.platform == "darwin" and config["parity"] in ("M", "S"):
        raise ValueError("QSerialPort does not support Mark/Space parity on macOS")


class _SerialWorker(QObject):
    received = pyqtSignal(bytes, float)
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.port = None
        self.opened = False
        self.last_received_at = None
        self._configuring = False
        self._control_active = False
        self._break_timer = None
        self._config = {}

    @pyqtSlot(object)
    def execute(self, request):
        try:
            request["result"] = getattr(self, "_" + request["operation"])(*request["args"])
        except (OSError, ValueError, TypeError, OverflowError, RuntimeError) as exc:
            request["error"] = str(exc)

    def _open(self, name, config):
        config = dict(config, baud=int(config["baud"]))
        self.port = QSerialPort(self)
        self.port.setPortName(name)
        self._break_timer = QTimer(self)
        self._break_timer.setSingleShot(True)
        self._break_timer.setTimerType(Qt.PreciseTimer)
        self._break_timer.timeout.connect(lambda: _safe(self._set_break, False))
        self.port.readyRead.connect(self._receive)
        self.port.errorOccurred.connect(self._error)
        self._configuring = True
        try:
            self._configure(config)
            if not self.port.open(QIODevice.ReadWrite):
                raise OSError(self.port.errorString())
            # Match pyserial's initial output-line state. PTYs and adapters
            # without modem lines may reject these optional operations.
            self.port.setDataTerminalReady(True)
            if config["flow"] != "rtscts":
                self.port.setRequestToSend(True)
            self.opened = True
            self._config = dict(config)
            return True
        finally:
            self._configuring = False

    def _configure(self, config):
        # Validate all enum values before changing any live setting.
        _validate_format(config)
        settings = (
            (self.port.setBaudRate, int(config["baud"])),
            (self.port.setDataBits, {5: QSerialPort.Data5, 6: QSerialPort.Data6,
                                    7: QSerialPort.Data7, 8: QSerialPort.Data8}.get(config["bytesize"])),
            (self.port.setParity, {"N": QSerialPort.NoParity, "E": QSerialPort.EvenParity,
                                  "O": QSerialPort.OddParity, "M": QSerialPort.MarkParity,
                                  "S": QSerialPort.SpaceParity}.get(config["parity"])),
            (self.port.setStopBits, {1: QSerialPort.OneStop, 1.5: QSerialPort.OneAndHalfStop,
                                    2: QSerialPort.TwoStop}.get(config["stopbits"])),
            (self.port.setFlowControl, {"none": QSerialPort.NoFlowControl,
                                       "rtscts": QSerialPort.HardwareControl,
                                       "xonxoff": QSerialPort.SoftwareControl}.get(config["flow"])),
        )
        if (any(value is None for _setter, value in settings)
                or not 0 < settings[0][1] <= 2147483647):
            raise ValueError("Invalid serial parameters")
        for setter, value in settings:
            if not setter(value):
                raise OSError(self.port.errorString())

    def _apply_params(self, changes):
        config = dict(self._config, **changes)
        config["baud"] = int(config["baud"])
        self._configuring = True
        try:
            try:
                self._configure(config)
            except (OSError, ValueError, TypeError):
                try:
                    self._configure(self._config)
                except (OSError, ValueError, TypeError):
                    self._close()
                    raise
                raise
            self._config = config
            return True
        finally:
            self._configuring = False

    def _receive(self):
        data = bytes(self.port.readAll())
        if data and self.opened:
            received_at = time.monotonic()
            self.last_received_at = received_at
            self.received.emit(data, received_at)

    def _error(self, code):
        if (self._configuring or not self.opened
                or (self._control_active and code == QSerialPort.UnknownError)
                or code in (QSerialPort.NoError, QSerialPort.TimeoutError,
                            QSerialPort.UnsupportedOperationError, QSerialPort.NotOpenError,
                            QSerialPort.ParityError, QSerialPort.FramingError,
                            QSerialPort.BreakConditionError)):
            return
        self._fail(self.port.errorString())

    def _fail(self, message):
        if not self.opened:
            return
        # Suppress errors raised by cleanup and discard queued output before
        # notifying callers that a write failed. close also cancels native I/O.
        self.opened = False
        self.port.clear(QSerialPort.Output)
        self._close()
        self.failed.emit(message)

    def _send(self, data):
        # Match the existing Qt network transports' 4 MiB backpressure limit.
        # Rejected data never enters the queue, so callers may safely retry it.
        if _pending_overflow(self.port, data):
            _log.warning("Qt serial send rejected: output buffer limit reached")
            return 0
        try:
            accepted = self.port.write(data)
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            self._fail(str(exc))
            return 0
        if accepted != len(data) or not self.opened:
            self._fail("Serial write failed: " + self.port.errorString())
            return 0
        # The count denotes acceptance by Qt. Its event loop drains the queue
        # asynchronously, including when CTS or XON/XOFF delays transmission.
        return accepted

    def _control_call(self, method, *args):
        # Unsupported modem-line ioctls can synchronously report UnknownError.
        # Limit suppression to this call so data-path/device errors still fail.
        previous = self._control_active
        self._control_active = True
        try:
            return method(*args)
        finally:
            self._control_active = previous

    def _set_dtr(self, on):
        if not self._control_call(self.port.setDataTerminalReady, bool(on)):
            raise OSError(self.port.errorString())

    def _set_rts(self, on):
        if not self._control_call(self.port.setRequestToSend, bool(on)):
            raise OSError(self.port.errorString())

    def _send_break(self, duration):
        interval = max(1, min(2147483647, math.ceil(float(duration) * 1000)))
        self._set_break(True)
        self._break_timer.start(interval)

    def _set_break(self, on):
        if not self._control_call(self.port.setBreakEnabled, bool(on)):
            raise OSError(self.port.errorString())

    def _read_lines(self):
        self.port.clearError()
        pins = self._control_call(self.port.pinoutSignals)
        names = {"cts": QSerialPort.ClearToSendSignal, "dsr": QSerialPort.DataSetReadySignal,
                 "dcd": QSerialPort.DataCarrierDetectSignal, "ri": QSerialPort.RingIndicatorSignal}
        if self.port.error() != QSerialPort.NoError:
            return dict.fromkeys(names)
        return {name: bool(pins & flag) for name, flag in names.items()}

    def _close(self):
        self.opened = False
        if self._break_timer is not None:
            self._break_timer.stop()
        if self.port is not None:
            self.port.close()


class QSerialPortConn(QObject):
    """Same connection contract as SerialConn, backed by native Qt serial I/O."""
    backend_name = "qserialport"
    data_received = pyqtSignal(bytes)
    data_received_timed = pyqtSignal(bytes, float)
    error_occurred = pyqtSignal(str)
    notice_occurred = pyqtSignal(str)
    state_changed = pyqtSignal(bool)

    def __init__(self, port, baud, bytesize, parity, stopbits, parent=None, flow="none"):
        super().__init__(parent)
        self._port_name = port
        self._config = {"baud": baud, "bytesize": bytesize, "parity": parity,
                        "stopbits": stopbits, "flow": flow}
        self._worker = None
        self._thread = None
        self._engaged = False

    def _call(self, operation, *args):
        if self._worker is None or not self._thread.isRunning():
            raise OSError("Serial port is closed")
        request = {"operation": operation, "args": args}
        if QThread.currentThread() == self._worker.thread():
            self._worker.execute(request)
        else:
            QMetaObject.invokeMethod(self._worker, "execute", Qt.BlockingQueuedConnection,
                                     Q_ARG(object, request))
        if "error" in request:
            raise OSError(request["error"])
        return request.get("result")

    def open(self):
        if self.is_open:
            return True
        self.close()
        self._thread = QThread(self)
        worker = _SerialWorker()
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.finished.connect(worker.deleteLater)
        worker.received.connect(lambda data, at: self._receive_from(worker, data, at))
        worker.failed.connect(lambda message: self._error_from(worker, message))
        self._thread.start()
        try:
            self._call("open", self._port_name, self._config)
        except OSError as exc:
            self.close()
            self.error_occurred.emit(str(exc))
            return False
        self._engaged = True
        self.state_changed.emit(True)
        return True

    def _receive_from(self, worker, data, received_at):
        if self._worker is worker and self._engaged:
            self.data_received_timed.emit(data, received_at)
            self.data_received.emit(data)

    def _error_from(self, worker, message):
        if self._worker is worker and self._engaged:
            try:
                self.error_occurred.emit(message)
            finally:
                if self._worker is worker:
                    self.close()

    @property
    def is_open(self):
        return self._worker is not None and self._worker.opened

    @property
    def last_received_at(self):
        return self._worker.last_received_at if self._worker is not None else None

    def send(self, data, target=None):
        if not self.is_open:
            return 0
        try:
            return self._call("send", bytes(data))
        except (OSError, TypeError):
            _log.debug("Qt serial write failed", exc_info=True)
            return 0

    def apply_params(self, baud=None, bytesize=None, parity=None, stopbits=None, flow=None):
        if not self.is_open:
            return False
        changes = {name: value for name, value in (
            ("baud", baud), ("bytesize", bytesize), ("parity", parity),
            ("stopbits", stopbits), ("flow", flow)) if value is not None}
        try:
            _validate_format(dict(self._config, **changes))
        except ValueError as exc:
            self.notice_occurred.emit(str(exc))
            return False
        try:
            worker = self._worker
            result = self._call("apply_params", changes)
        except OSError as exc:
            if self.is_open:
                self.notice_occurred.emit(str(exc))
            else:
                self._error_from(worker, str(exc))
            return False
        self._config.update(changes)
        return result

    def set_dtr(self, on):
        if self.is_open:
            _safe(self._call, "set_dtr", on)

    def set_rts(self, on):
        if self.is_open:
            _safe(self._call, "set_rts", on)

    def send_break(self, duration=0.25):
        if self.is_open:
            _safe(self._call, "send_break", duration)

    def read_lines(self):
        if self.is_open:
            return self._call("read_lines")
        return dict.fromkeys(("cts", "dsr", "dcd", "ri"))

    def close(self):
        if self._thread is None:
            return
        thread = self._thread
        try:
            self._call("close")
        finally:
            self._worker = None
            self._thread = None
            thread.quit()
            thread.wait()
            thread.deleteLater()
        was_engaged, self._engaged = self._engaged, False
        if was_engaged:
            self.state_changed.emit(False)
