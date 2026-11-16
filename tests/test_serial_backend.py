"""Backend contract and native Qt serial I/O exercised through real PTYs."""
import os
import select
import threading
import time
from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtSerialPort import QSerialPort
from PyQt5.QtWidgets import QApplication

from transport.serial_backend import BACKENDS, create_serial_connection
from transport.qt_serial_io import QSerialPortConn, _SerialWorker
from transport import qt_serial_io

_APP = QApplication.instance() or QApplication([])


def _until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        _APP.processEvents()
        time.sleep(0.001)
    assert predicate()


@pytest.fixture
def pty_pair():
    if os.name != "posix":
        pytest.skip("PTY requires POSIX")
    master, slave = os.openpty()
    try:
        yield master, os.ttyname(slave)
    finally:
        os.close(master)
        os.close(slave)


@pytest.fixture
def qt_conn(pty_pair):
    master, name = pty_pair
    conn = create_serial_connection(name, 115200, 8, "N", 1, backend="qserialport")
    assert conn.open()
    try:
        yield conn, master
    finally:
        conn.close()
        _APP.processEvents()


@pytest.mark.parametrize("backend", list(BACKENDS))
def test_factory_selects_backend(monkeypatch, backend):
    monkeypatch.setenv("COMMTOOL_SERIAL_BACKEND", backend)
    conn = create_serial_connection("unused", 9600, 8, "N", 1)
    assert conn.backend_name == backend
    assert not conn.is_open
    assert conn.send(b"closed") == 0
    assert conn.last_received_at is None
    assert conn.read_lines() == dict.fromkeys(("cts", "dsr", "dcd", "ri"))
    assert not conn.apply_params(baud=19200)
    conn.close()


def test_factory_default_and_explicit_selection(monkeypatch):
    monkeypatch.delenv("COMMTOOL_SERIAL_BACKEND", raising=False)
    assert isinstance(create_serial_connection("unused", 9600, 8, "N", 1), QSerialPortConn)
    monkeypatch.setenv("COMMTOOL_SERIAL_BACKEND", "pyserial")
    assert isinstance(create_serial_connection(
        "unused", 9600, 8, "N", 1, backend="qserialport"), QSerialPortConn)
    with pytest.raises(ValueError, match="Unknown serial backend"):
        create_serial_connection("unused", 9600, 8, "N", 1, backend="unknown")


@pytest.mark.parametrize("backend", list(BACKENDS))
def test_contract_receive_send_and_reopen(pty_pair, backend):
    master, name = pty_pair
    conn = create_serial_connection(name, 115200, 8, "N", 1, backend=backend)
    timed, raw, errors, states = [], [], [], []
    conn.data_received_timed.connect(lambda data, at: timed.append((data, at)))
    conn.data_received.connect(raw.append)
    conn.error_occurred.connect(errors.append)
    conn.state_changed.connect(states.append)
    try:
        for payload in (b"OK\r\n", bytes(range(256)) * 16):
            assert conn.open()
            start = time.monotonic()
            os.write(master, payload)
            _until(lambda: sum(len(data) for data in raw) == len(payload))
            assert b"".join(raw) == payload
            assert b"".join(data for data, _at in timed) == payload
            assert all(start <= at <= time.monotonic() for _data, at in timed)
            assert conn.last_received_at == timed[-1][1]
            response = bytearray()

            def read_response():
                while len(response) < len(payload):
                    if not select.select([master], [], [], 2)[0]:
                        return
                    response.extend(os.read(master, len(payload) - len(response)))

            receiver = threading.Thread(target=read_response)
            receiver.start()
            try:
                assert conn.send(payload) == len(payload)
            finally:
                receiver.join(3)
            assert not receiver.is_alive()
            assert response == payload
            conn.close()
            assert not conn.is_open
            timed.clear()
            raw.clear()
        assert states == [True, False, True, False]
        assert errors == []
    finally:
        conn.close()


def test_worker_timestamp_precedes_gui_delivery_and_late_rx_is_dropped(qt_conn):
    conn, master = qt_conn
    ready = threading.Event()
    seen = []
    conn._worker.received.connect(lambda *_args: ready.set(), Qt.DirectConnection)
    conn.data_received_timed.connect(lambda data, at: seen.append(
        (data, at, threading.get_ident())))
    os.write(master, b"queued")
    assert ready.wait(2)
    assert seen == []
    timestamp = conn.last_received_at
    assert timestamp <= time.monotonic()
    _until(lambda: len(seen) == 1)
    assert seen == [(b"queued", timestamp, threading.get_ident())]

    ready.clear()
    os.write(master, b"stale")
    assert ready.wait(2)
    conn.close()
    conn.close()
    assert conn.open()
    _APP.processEvents()
    assert len(seen) == 1
    os.write(master, b"fresh")
    _until(lambda: len(seen) == 2)
    assert seen[-1][0] == b"fresh"


def test_parameter_changes_and_validation_leave_port_usable(qt_conn):
    conn, master = qt_conn
    errors, notices, seen = [], [], []
    conn.error_occurred.connect(errors.append)
    conn.notice_occurred.connect(notices.append)
    conn.data_received.connect(seen.append)
    assert conn.apply_params(baud=19200, stopbits=2, flow="none")
    config = dict(conn._config)
    assert not conn.apply_params(baud=9600, bytesize=9)
    assert not conn.apply_params(baud=2**40)
    assert not conn.apply_params(baud=float("inf"))
    assert conn._config == config
    assert conn._worker._config == config
    assert errors == []
    assert len(notices) == 3
    os.write(master, b"still usable")
    _until(lambda: bool(seen))
    assert b"".join(seen) == b"still usable"


def test_partial_configuration_failure_restores_all_settings():
    worker = _SerialWorker()
    worker.port = Mock()
    worker.port.errorString.return_value = "unsupported parity"
    worker._config = {"baud": 115200, "bytesize": 8, "parity": "N",
                      "stopbits": 1, "flow": "none"}
    worker.port.setParity.side_effect = [False, True]
    with pytest.raises(OSError, match="unsupported parity"):
        worker._apply_params({"baud": 9600, "parity": "E"})
    assert [call.args[0] for call in worker.port.setBaudRate.call_args_list] == [9600, 115200]
    assert worker._config["baud"] == 115200
    assert not worker._configuring


def test_failed_rollback_closes_port_with_uncertain_settings():
    worker = _SerialWorker()
    worker.port = Mock()
    worker.opened = True
    worker.port.errorString.return_value = "device lost"
    worker._config = {"baud": 115200, "bytesize": 8, "parity": "N",
                      "stopbits": 1, "flow": "none"}
    worker.port.setParity.return_value = False
    with pytest.raises(OSError, match="device lost"):
        worker._apply_params({"baud": 9600, "parity": "E"})
    assert not worker.opened
    worker.port.close.assert_called_once()
    assert not worker._configuring


def test_failed_open_stops_worker_and_can_be_retried(pty_pair):
    _master, name = pty_pair
    conn = QSerialPortConn(name + "-missing", 115200, 8, "N", 1)
    errors = []
    conn.error_occurred.connect(errors.append)
    try:
        assert not conn.open()
        assert not conn.is_open
        assert conn._thread is None
        assert errors
        conn._port_name = name
        assert conn.open()
        assert conn.is_open
    finally:
        conn.close()


def test_missing_device_always_releases_worker():
    conn = QSerialPortConn("commtool-missing-device", 115200, 8, "N", 1)
    errors = []
    conn.error_occurred.connect(errors.append)
    for _attempt in range(3):
        assert not conn.open()
        assert not conn.is_open
        assert conn._thread is None
        assert conn._worker is None
    assert len(errors) == 3
    conn.close()


def test_close_stops_worker_and_break_timer(qt_conn):
    conn, _master = qt_conn
    thread = conn._thread
    conn.send_break(1)
    conn.read_lines()
    conn.set_dtr(False)
    conn.set_rts(False)
    conn.close()
    assert not thread.isRunning()
    assert conn._worker is None
    assert not conn.is_open


def test_fatal_native_error_closes_port_once(qt_conn):
    conn, _master = qt_conn
    worker = conn._worker
    errors = []
    conn.error_occurred.connect(errors.append)
    # Invoke the native error handler in its owning thread. PTY hangup does
    # not generate a portable USB-removal error across host drivers.
    conn._call("error", QSerialPort.ResourceError)
    _until(lambda: bool(errors))
    assert not conn.is_open
    assert conn._thread is None
    assert not conn._engaged
    conn._error_from(worker, "late duplicate")
    _APP.processEvents()
    assert len(errors) == 1


@pytest.mark.parametrize("code", [QSerialPort.ParityError, QSerialPort.FramingError,
                                  QSerialPort.BreakConditionError])
def test_line_error_handler_does_not_close_native_port(code):
    worker = _write_worker()
    errors = []
    worker.failed.connect(errors.append)
    worker._error(code)
    assert worker.opened
    assert worker.port.mock_calls == []
    assert errors == []


@pytest.mark.parametrize("code", [QSerialPort.ParityError, QSerialPort.FramingError,
                                  QSerialPort.BreakConditionError])
def test_line_errors_preserve_connection_and_receive(qt_conn, code):
    conn, master = qt_conn
    worker, thread = conn._worker, conn._thread
    errors, states, seen = [], [], []
    conn.error_occurred.connect(errors.append)
    conn.state_changed.connect(states.append)
    conn.data_received.connect(seen.append)
    conn._call("error", code)
    _APP.processEvents()
    assert conn.is_open and conn._engaged
    assert conn._worker is worker and conn._thread is thread
    assert errors == [] and states == []
    os.write(master, b"after line error")
    _until(lambda: bool(seen))
    assert b"".join(seen) == b"after line error"


@pytest.mark.parametrize("platform,parity,stopbits", [
    ("darwin", "M", 1), ("darwin", "S", 1), ("darwin", "N", 1.5),
    ("linux", "N", 1.5),
])
def test_unsupported_formats_rejected_before_any_setter(monkeypatch, platform, parity, stopbits):
    worker = _SerialWorker()
    worker.port = Mock()
    monkeypatch.setattr(qt_serial_io.sys, "platform", platform)
    with pytest.raises(ValueError, match="does not support"):
        worker._configure({"baud": 115200, "bytesize": 8, "parity": parity,
                           "stopbits": stopbits, "flow": "none"})
    assert worker.port.mock_calls == []


@pytest.mark.parametrize("parity,stopbits", [("M", 1), ("S", 1), ("N", 1.5)])
def test_windows_formats_reach_native_configuration(monkeypatch, parity, stopbits):
    worker = _SerialWorker()
    worker.port = Mock()
    monkeypatch.setattr(qt_serial_io.sys, "platform", "win32")
    worker._configure({"baud": 9600, "bytesize": 5, "parity": parity,
                       "stopbits": stopbits, "flow": "none"})
    worker.port.setParity.assert_called_once_with({
        "M": QSerialPort.MarkParity, "S": QSerialPort.SpaceParity,
        "N": QSerialPort.NoParity}[parity])
    worker.port.setStopBits.assert_called_once_with(
        QSerialPort.OneAndHalfStop if stopbits == 1.5 else QSerialPort.OneStop)


@pytest.mark.parametrize("platform,changes", [
    ("darwin", {"parity": "M"}), ("darwin", {"parity": "S"}),
    ("darwin", {"stopbits": 1.5}), ("linux", {"stopbits": 1.5}),
])
def test_known_unsupported_live_format_only_emits_notice(monkeypatch, platform, changes):
    conn = QSerialPortConn("unused", 115200, 8, "N", 1)
    conn._worker = SimpleNamespace(opened=True)
    native_call = Mock(side_effect=AssertionError("rejected parameters reached worker"))
    monkeypatch.setattr(conn, "_call", native_call)
    monkeypatch.setattr(qt_serial_io.sys, "platform", platform)
    errors, notices = [], []
    conn.error_occurred.connect(errors.append)
    conn.notice_occurred.connect(notices.append)
    config = dict(conn._config)
    assert not conn.apply_params(**changes)
    assert conn.is_open
    assert conn._config == config
    assert errors == []
    assert len(notices) == 1 and "does not support" in notices[0]
    native_call.assert_not_called()


def test_hardware_parameter_failure_still_emits_error(monkeypatch):
    conn = QSerialPortConn("unused", 115200, 8, "N", 1)
    conn._worker = SimpleNamespace(opened=True)
    conn._engaged = True
    conn._thread = Mock()

    def call(operation, *_args):
        if operation == "apply_params":
            conn._worker.opened = False
            raise OSError("device lost")

    monkeypatch.setattr(conn, "_call", call)
    errors, notices = [], []
    conn.error_occurred.connect(errors.append)
    conn.notice_occurred.connect(notices.append)
    assert not conn.apply_params(baud=9600)
    assert errors == ["device lost"]
    assert notices == []
    assert conn._worker is None and conn._thread is None
    assert not conn._engaged


def test_native_parameter_rollback_failure_cleans_facade_without_error_handler(qt_conn, monkeypatch):
    conn, _master = qt_conn
    thread = conn._thread
    monkeypatch.setattr(conn._worker, "_configure", Mock(side_effect=OSError("device lost")))
    errors, states, notices = [], [], []
    conn.error_occurred.connect(errors.append)
    conn.state_changed.connect(states.append)
    conn.notice_occurred.connect(notices.append)
    assert not conn.apply_params(baud=9600)
    assert not conn.is_open and not conn._engaged
    assert conn._worker is None and conn._thread is None
    assert not thread.isRunning()
    assert errors == ["device lost"] and states == [False] and notices == []


def test_driver_rejection_after_partial_change_rolls_back_without_disconnect(qt_conn, monkeypatch):
    conn, master = qt_conn
    worker = conn._worker
    config = dict(conn._config)
    configure = worker._configure
    attempts = []

    def reject_first(proposed):
        attempts.append(dict(proposed))
        if len(attempts) == 1:
            assert worker.port.setBaudRate(proposed["baud"])
            raise OSError("driver rejected parameters")
        return configure(proposed)

    monkeypatch.setattr(worker, "_configure", reject_first)
    errors, states, notices, seen = [], [], [], []
    conn.error_occurred.connect(errors.append)
    conn.state_changed.connect(states.append)
    conn.notice_occurred.connect(notices.append)
    conn.data_received.connect(seen.append)
    assert not conn.apply_params(baud=9600)
    assert conn.is_open and conn._engaged and conn._worker is worker
    assert conn._config == config and worker._config == config
    assert attempts[-1] == config
    assert errors == [] and states == [] and notices == ["driver rejected parameters"]
    os.write(master, b"RX after rollback")
    _until(lambda: bool(seen))
    assert b"".join(seen) == b"RX after rollback"


@pytest.mark.skipif(os.sys.platform != "darwin", reason="macOS format restrictions")
@pytest.mark.parametrize("changes", [{"parity": "M"}, {"parity": "S"}, {"stopbits": 1.5}])
def test_macos_unsupported_open_fails_and_live_update_keeps_termios(pty_pair, changes):
    import termios
    master, name = pty_pair
    config = dict(baud=115200, bytesize=8, parity="N", stopbits=1)
    config.update(changes)
    rejected = QSerialPortConn(name, **config)
    try:
        assert not rejected.open()
        assert rejected._thread is None
    finally:
        rejected.close()
    conn = QSerialPortConn(name, 115200, 8, "N", 1)
    try:
        assert conn.open()
        errors, notices = [], []
        conn.error_occurred.connect(errors.append)
        conn.notice_occurred.connect(notices.append)
        before = termios.tcgetattr(master)
        assert not conn.apply_params(**changes)
        assert conn.is_open
        assert errors == []
        assert len(notices) == 1
        assert termios.tcgetattr(master) == before
        assert conn._config == {"baud": 115200, "bytesize": 8, "parity": "N",
                                "stopbits": 1, "flow": "none"}
    finally:
        conn.close()


def _write_worker():
    worker = _SerialWorker()
    worker.opened = True
    worker.port = Mock()
    worker.port.bytesToWrite.return_value = 128
    worker.port.errorString.return_value = "write failed"
    return worker


@pytest.mark.parametrize("operation,args,native_method", [
    ("_set_dtr", (True,), "setDataTerminalReady"),
    ("_set_rts", (False,), "setRequestToSend"),
    ("_send_break", (0.01,), "setBreakEnabled"),
    ("_set_break", (False,), "setBreakEnabled"),
    ("_read_lines", (), "pinoutSignals"),
])
def test_optional_control_unknown_error_keeps_data_port(operation, args, native_method):
    worker = _write_worker()
    worker.port.error.return_value = QSerialPort.UnknownError
    errors = []
    worker.failed.connect(errors.append)

    def reject(*_args):
        worker._error(QSerialPort.UnknownError)
        return False

    getattr(worker.port, native_method).side_effect = reject
    if operation == "_read_lines":
        assert worker._read_lines() == dict.fromkeys(("cts", "dsr", "dcd", "ri"))
    else:
        with pytest.raises(OSError):
            getattr(worker, operation)(*args)
    assert worker.opened and not worker._control_active
    assert errors == []
    worker.port.close.assert_not_called()


@pytest.mark.parametrize("code", [QSerialPort.ResourceError, QSerialPort.ReadError,
                                  QSerialPort.WriteError])
def test_fatal_error_during_control_operation_still_closes(code):
    worker = _write_worker()
    errors = []
    worker.failed.connect(errors.append)

    def fail(_on):
        worker._error(code)
        return False

    worker.port.setDataTerminalReady.side_effect = fail
    with pytest.raises(OSError):
        worker._set_dtr(True)
    assert not worker.opened and not worker._control_active
    assert len(errors) == 1
    worker.port.close.assert_called_once()


def test_control_call_exception_restores_error_handling():
    worker = _write_worker()
    worker.port.setRequestToSend.side_effect = OSError("optional ioctl failed")
    with pytest.raises(OSError):
        worker._set_rts(False)
    assert not worker._control_active
    worker._error(QSerialPort.UnknownError)
    assert not worker.opened


def test_break_timer_reset_unknown_error_keeps_native_connection(qt_conn, monkeypatch):
    conn, master = qt_conn
    worker = conn._worker
    reset = threading.Event()
    errors, seen = [], []
    conn.error_occurred.connect(errors.append)
    conn.data_received.connect(seen.append)

    def set_break(on):
        if on:
            return True
        worker._error(QSerialPort.UnknownError)
        reset.set()
        return False

    monkeypatch.setattr(worker.port, "setBreakEnabled", set_break)
    conn.send_break(0.001)
    assert reset.wait(2)
    _APP.processEvents()
    assert conn.is_open and conn._engaged
    assert errors == [] and not worker._control_active
    os.write(master, b"RX after break reset failure")
    _until(lambda: bool(seen))
    assert b"".join(seen) == b"RX after break reset failure"


def test_send_accepts_queued_bytes_without_waiting_for_cts():
    worker = _write_worker()
    worker.port.write.return_value = 3
    assert worker._send(b"new") == 3
    worker.port.waitForBytesWritten.assert_not_called()
    worker.port.clear.assert_not_called()
    assert worker.opened


@pytest.mark.parametrize("result", [-1, 0, 2])
@pytest.mark.parametrize("clear_ok", [True, False])
def test_failed_or_partial_write_discards_output_and_closes(result, clear_ok):
    worker = _write_worker()
    worker.port.write.return_value = result
    worker.port.clear.return_value = clear_ok
    errors = []
    worker.failed.connect(errors.append)
    assert worker._send(b"new") == 0
    worker.port.clear.assert_called_once_with(QSerialPort.Output)
    worker.port.close.assert_called_once()
    worker.port.waitForBytesWritten.assert_not_called()
    assert not worker.opened
    assert len(errors) == 1


def test_write_exception_discards_output_and_closes():
    worker = _write_worker()
    worker.port.write.side_effect = OSError("write failed")
    assert worker._send(b"new") == 0
    worker.port.clear.assert_called_once_with(QSerialPort.Output)
    worker.port.close.assert_called_once()
    assert not worker.opened


def test_backpressure_rejects_new_frame_without_touching_accepted_queue():
    worker = _write_worker()
    worker.port.bytesToWrite.return_value = 4 * 1024 * 1024 - 2
    assert worker._send(b"new") == 0
    worker.port.write.assert_not_called()
    worker.port.clear.assert_not_called()
    worker.port.close.assert_not_called()
    assert worker.opened


def test_blocked_native_output_keeps_reader_and_gui_available(qt_conn):
    conn, master = qt_conn
    ready = threading.Event()
    pending = []
    worker = conn._worker

    def note_receive(_data, _at):
        pending.append(worker.port.bytesToWrite())
        ready.set()

    worker.received.connect(note_receive, Qt.DirectConnection)
    started = time.monotonic()
    assert conn.send(b"A" * (128 * 1024)) == 128 * 1024
    assert time.monotonic() - started < 0.5
    # Leave the PTY peer unread to fill the native output buffer, then prove
    # incoming data still runs through the worker and queued GUI delivery.
    seen = []
    conn.data_received.connect(seen.append)
    os.write(master, b"RX during blocked TX")
    assert ready.wait(2)
    assert pending[-1] > 0
    _until(lambda: bool(seen))
    assert b"".join(seen) == b"RX during blocked TX"
    conn._call("error", QSerialPort.WriteError)
    _until(lambda: conn._thread is None)
    assert not conn.is_open and not conn._engaged


def test_both_application_entry_points_use_common_factory():
    from main_window import SerialConn as terminal_factory
    from ui.bridge_dialog import SerialConn as bridge_factory
    assert terminal_factory is create_serial_connection
    assert bridge_factory is create_serial_connection
