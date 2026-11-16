# -*- coding: utf-8 -*-
"""Serial arrival timing survives polling gaps and delayed GUI delivery."""
import os
import threading
import time
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QObject, Qt, QCoreApplication, QEvent, pyqtSignal
from PyQt5.QtWidgets import QApplication

from transport import serial_io

_APP = QApplication.instance() or QApplication([])


def test_reader_wakes_for_each_arrival_without_polling(monkeypatch):
    class ScheduledSerial:
        is_open = True
        now = 0.0

        def __init__(self):
            self.arrivals = [(0.001, b"A"), (0.007, b"B")]

        @property
        def in_waiting(self):
            return sum(len(data) for at, data in self.arrivals if at <= self.now)

        def read(self, size):
            if not self.arrivals:
                reader._running = False
                return b""
            self.now, data = self.arrivals.pop(0)
            assert size == len(data)
            return data

    port = ScheduledSerial()
    reader = serial_io.SerialReader(port)
    monkeypatch.setattr(serial_io, "time", SimpleNamespace(monotonic=lambda: port.now))
    monkeypatch.setattr(reader, "msleep", lambda ms: pytest.fail("polling sleep"))
    timed, legacy = [], []
    reader.data_received_timed.connect(lambda data, at: timed.append((data, at)))
    reader.data_received.connect(legacy.append)
    reader.run()
    assert timed == [(b"A", 0.001), (b"B", 0.007)]
    assert legacy == [b"A", b"B"]
    assert reader.last_received_at == 0.007


def test_stop_cancels_blocked_read_without_emitting_late_bytes():
    entered, cancelled = threading.Event(), threading.Event()

    class BlockingSerial:
        is_open = True
        in_waiting = 0

        def read(self, size):
            assert size == 1
            entered.set()
            cancelled.wait(1)
            return b"late"

        def cancel_read(self):
            cancelled.set()

    reader = serial_io.SerialReader(BlockingSerial())
    seen = []
    reader.data_received_timed.connect(lambda *args: seen.append(args), Qt.DirectConnection)
    reader.data_received.connect(seen.append, Qt.DirectConnection)
    reader.start()
    try:
        assert entered.wait(1)
        reader.stop()
        assert cancelled.is_set()
        assert not reader.isRunning()
        assert seen == []
    finally:
        reader.stop()


@pytest.mark.parametrize("initial_pending", [0, 1])
def test_reader_delivers_read_bytes_before_next_port_error(initial_pending):
    class DisconnectingSerial:
        is_open = True
        read_done = False

        @property
        def in_waiting(self):
            if self.read_done:
                raise serial_io.serial.SerialException("disconnected")
            return initial_pending

        def read(self, size):
            self.read_done = True
            return b"A"

    reader = serial_io.SerialReader(DisconnectingSerial())
    seen = []
    reader.data_received.connect(lambda data: seen.append(data))
    reader.error_occurred.connect(lambda error: seen.append(error))
    reader.run()
    assert seen == [b"A", "disconnected"]


def test_ready_suffix_joins_wakeup_byte(monkeypatch):
    class PausedSerial:
        is_open = True
        now = 0.001

        def __init__(self):
            self.chunks = [b"A", b"B"]

        @property
        def in_waiting(self):
            if len(self.chunks) == 1:
                self.now = 0.031
                return 1
            return 0

        def read(self, size):
            if not self.chunks:
                reader._running = False
                return b""
            return self.chunks.pop(0)

    port = PausedSerial()
    reader = serial_io.SerialReader(port)
    monkeypatch.setattr(serial_io, "time", SimpleNamespace(monotonic=lambda: port.now))
    seen = []
    reader.data_received_timed.connect(lambda data, at: seen.append((data, at)))
    reader.run()
    assert seen == [(b"AB", 0.031)]


@pytest.mark.parametrize("payload", [b"OK\r\n", bytes(range(256)) * 4])
def test_idle_wakeup_includes_already_buffered_suffix(monkeypatch, payload):
    class BurstSerial:
        is_open = True

        def __init__(self):
            self.buffer = b""
            self.started = False

        @property
        def in_waiting(self):
            return len(self.buffer)

        def read(self, size):
            if not self.started:
                assert size == 1
                self.buffer = payload
                self.started = True
            elif not self.buffer:
                reader._running = False
                return b""
            result, self.buffer = self.buffer[:size], self.buffer[size:]
            return result

    reader = serial_io.SerialReader(BurstSerial())
    monkeypatch.setattr(serial_io, "time", SimpleNamespace(monotonic=lambda: 1.0))
    seen = []
    reader.data_received.connect(seen.append)
    reader.run()
    assert seen == [payload]


def test_suffix_read_error_preserves_first_byte():
    class FailedSuffix:
        is_open = True
        reads = 0

        @property
        def in_waiting(self):
            return self.reads

        def read(self, size):
            self.reads += 1
            if self.reads == 1:
                return b"A"
            raise serial_io.serial.SerialException("suffix failed")

    reader = serial_io.SerialReader(FailedSuffix())
    seen = []
    reader.data_received.connect(seen.append)
    reader.error_occurred.connect(seen.append)
    reader.run()
    assert seen == [b"A", "suffix failed"]


@pytest.mark.skipif(os.name != "posix", reason="PTY requires POSIX")
def test_native_serial_keeps_reader_timestamp_until_gui_delivery():
    master, slave = os.openpty()
    conn = serial_io.SerialConn(os.ttyname(slave), 115200, 8, "N", 1)
    seen, errors = [], []
    conn.data_received_timed.connect(lambda data, at: seen.append(
        (data, at, threading.get_ident())))
    conn.error_occurred.connect(errors.append)
    read_ready = threading.Event()
    reader_bytes = bytearray()

    def note_read(data, _at):
        reader_bytes.extend(data)
        if len(reader_bytes) == 5:
            read_ready.set()

    try:
        assert conn.open()
        conn._reader.data_received_timed.connect(note_read, Qt.DirectConnection)
        os.write(master, b"hello")
        assert read_ready.wait(1)
        reader_timestamp = conn.last_received_at
        before_delivery = time.monotonic()
        assert reader_timestamp <= before_delivery
        assert seen == []
        deadline = time.monotonic() + 1
        while sum(len(data) for data, _at, _thread in seen) < 5 and time.monotonic() < deadline:
            _APP.processEvents()
        assert b"".join(data for data, _at, _thread in seen) == b"hello"
        assert seen[-1][1] == reader_timestamp
        assert all(thread == threading.get_ident() for _data, _at, thread in seen)
        assert errors == []
        reader = conn._reader
        conn.close()
        assert not reader.isRunning()
        assert not conn.is_open
    finally:
        conn.close()
        os.close(master)
        os.close(slave)


class TimedConn(QObject):
    data_received = pyqtSignal(bytes)
    data_received_timed = pyqtSignal(bytes, float)
    error_occurred = pyqtSignal(str)
    state_changed = pyqtSignal(bool)
    is_open = True
    last_received_at = None

    def receive(self, data, at):
        self.last_received_at = at
        self.data_received_timed.emit(data, at)
        self.data_received.emit(data)

    def close(self):
        self.is_open = False


@pytest.fixture
def window(monkeypatch, tmp_path):
    from main_window import CommTool, PortScannerThread

    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "toast", lambda *args, **kwargs: None)
    monkeypatch.setattr(CommTool, "_settings_file", staticmethod(
        lambda profile="": str(tmp_path / "serial-timing.ini")))
    w = CommTool("serial-timing")
    w.sw_hexdump.setChecked(False)
    w.sw_packet_split.setChecked(True)
    w.ed_packet_timeout.setText("20")
    w.sw_line_split.setChecked(False)
    w.sw_show_timestamp.setChecked(False)
    w._ar_rules = [{"on": True, "gap": 20}]
    w._recompute_ar_gap()
    w._ar_frame = {"on": False}
    w._ar_modbus = {"on": False}
    yield w
    w._shutdown()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _bind_timed_conn(w):
    session = w.active_session()
    session.conn = TimedConn()
    session._ar_enabled = True
    w._bind_conn_signals(session.conn, session)
    return session


@pytest.mark.skipif(os.name != "posix", reason="PTY requires POSIX")
@pytest.mark.parametrize("combo_name,value", [
    ("cb_stopbits", "1.5"),
    pytest.param("cb_parity", "Mark", marks=pytest.mark.skipif(
        os.sys.platform != "darwin", reason="macOS parity restriction")),
    pytest.param("cb_parity", "Space", marks=pytest.mark.skipif(
        os.sys.platform != "darwin", reason="macOS parity restriction")),
    ("cb_baud", "driver-reject"),
])
def test_unsupported_live_format_keeps_connection_and_restores_controls(
        window, monkeypatch, combo_name, value):
    import termios
    w = window
    master, slave = os.openpty()
    monkeypatch.setenv("COMMTOOL_SERIAL_BACKEND", "qserialport")
    name = os.ttyname(slave)
    w.cb_port.addItem(name, name)
    w.cb_port.setCurrentIndex(w.cb_port.count() - 1)
    w.cb_baud.setCurrentText("115200")
    w.cb_parity.setCurrentText("None")
    w.cb_stopbits.setCurrentText("1")
    w.cb_flow.setCurrentText("None")
    try:
        w.open_conn()
        conn = w.conn
        assert conn is not None and conn.is_open
        worker, thread = conn._worker, conn._thread
        signature = w._conn_cfg
        config = dict(conn._config)
        native_format = termios.tcgetattr(master)
        errors, notices, states, toasts = [], [], [], []
        conn.error_occurred.connect(errors.append)
        conn.notice_occurred.connect(notices.append)
        conn.state_changed.connect(states.append)
        monkeypatch.setattr(w, "toast", lambda message, **_kw: toasts.append(message))
        if value == "driver-reject":
            configure = worker._configure
            attempts = []

            def reject_first(proposed):
                attempts.append(dict(proposed))
                if len(attempts) == 1:
                    assert worker.port.setBaudRate(proposed["baud"])
                    raise OSError("driver rejected parameters")
                return configure(proposed)

            monkeypatch.setattr(worker, "_configure", reject_first)
        else:
            getattr(w, combo_name).setCurrentText(value)
        w.cb_baud.setCurrentText("9600")
        w.cb_flow.setCurrentText("RTS/CTS")
        w._apply_serial_params_live()
        _APP.processEvents()
        assert w.conn is conn and conn.is_open
        assert conn._worker is worker and conn._thread is thread
        assert errors == [] and states == []
        assert len(notices) == 1 and toasts == notices
        assert w._conn_cfg == signature
        assert w._conn_config_signature() == signature
        assert conn._config == config
        assert termios.tcgetattr(master) == native_format
        assert not w._reconnect_timer.isActive()
        assert w._mbm_connection_ready()
        assert w.sw_rts.isEnabled()
        assert w._capture_connection_fields()["ser_baud"] == "115200"
        received = w.rx_bytes
        os.write(master, b"still connected")
        deadline = time.monotonic() + 2
        while w.rx_bytes == received and time.monotonic() < deadline:
            _APP.processEvents()
            time.sleep(0.001)
        assert w.rx_bytes == received + len(b"still connected")
    finally:
        w.close_conn()
        os.close(master)
        os.close(slave)


def test_live_parameter_rejection_without_connection_signature(window):
    from main_window import PROTO_SERIAL
    w = window
    conn = SimpleNamespace(is_open=True, apply_params=lambda **_kwargs: False)
    w.conn = conn
    w._conn_proto = PROTO_SERIAL
    w._conn_cfg = None
    try:
        w._apply_serial_params_live()
        assert w.conn is conn and conn.is_open
        assert w._conn_cfg is None
    finally:
        w.conn = None


@pytest.mark.skipif(os.name != "posix", reason="PTY requires POSIX")
@pytest.mark.parametrize("backend", ["qserialport", "pyserial"])
def test_selected_backend_uses_existing_20ms_framing(window, monkeypatch, backend):
    w = window
    master, slave = os.openpty()
    monkeypatch.setenv("COMMTOOL_SERIAL_BACKEND", backend)
    name = os.ttyname(slave)
    w.cb_port.addItem(name, name)
    w.cb_port.setCurrentIndex(w.cb_port.count() - 1)
    w.cb_baud.setCurrentText("115200")
    frames = []
    monkeypatch.setattr(w, "_ar_match", lambda data: frames.append(
        (data, time.monotonic(), w.conn.last_received_at)))
    try:
        w.open_conn()
        assert w.conn is not None and w.conn.is_open
        assert w.conn.backend_name == backend
        w.active_session()._ar_enabled = True
        for expected in (b"OK\r\n", b"next"):
            for byte in expected:
                os.write(master, bytes([byte]))
                time.sleep(0.002)
            target = len(frames) + 1
            deadline = time.monotonic() + 2
            while len(frames) < target and time.monotonic() < deadline:
                _APP.processEvents()
                time.sleep(0.001)
            assert len(frames) == target
            data, flushed_at, received_at = frames[-1]
            assert data == expected
            assert flushed_at - received_at >= 0.020
            assert flushed_at - received_at < 0.5
    finally:
        w.close_conn()
        os.close(master)
        os.close(slave)


@pytest.mark.skipif(os.name != "posix", reason="PTY requires POSIX")
@pytest.mark.parametrize("payload", [b"OK\r\n", bytes(range(128))])
def test_native_idle_burst_matches_immediate_equal_rule(window, monkeypatch, payload):
    w = window
    master, slave = os.openpty()
    idle_read = threading.Event()
    serial_factory = serial_io.serial.Serial

    def open_serial(**kwargs):
        port = serial_factory(**kwargs)
        native_read = port.read

        def read(size):
            if size == 1:
                idle_read.set()
            return native_read(size)

        port.read = read
        return port

    monkeypatch.setattr(serial_io.serial, "Serial", open_serial)
    conn = serial_io.SerialConn(os.ttyname(slave), 115200, 8, "N", 1)
    session = w.active_session()
    session.conn = conn
    session._ar_enabled = True
    rule = {"on": True, "gap": 0, "match_hex": True,
            "match": payload.hex(), "mode": 1}
    w._ar_rules = [rule]
    w._recompute_ar_gap()
    w._bind_conn_signals(conn, session)
    chunks = []
    conn.data_received.connect(chunks.append)
    try:
        assert conn.open()
        assert idle_read.wait(1)
        os.write(master, payload)
        deadline = time.monotonic() + 1
        while session.rx_bytes < len(payload) and time.monotonic() < deadline:
            _APP.processEvents()
            time.sleep(0.001)
        assert chunks == [payload]
        assert rule.get("_hits") == 1
        assert session._ar_buf == b""
    finally:
        conn.close()
        os.close(master)
        os.close(slave)


@pytest.mark.parametrize("background", [False, True])
def test_delayed_delivery_preserves_display_and_auto_reply_frames(
        window, monkeypatch, background):
    w = window
    session = _bind_timed_conn(w)
    matched = []
    monkeypatch.setattr(w, "_ar_match", lambda data: matched.append(
        (w._session_ctx().id, data)))
    if background:
        w.add_session(activate=True)
    start = time.monotonic() - 1
    session.conn.receive(b"A", start)
    session.conn.receive(b"B", start + 0.004)
    session.conn.receive(b"C", start + 0.030)
    with w._with_session(session):
        w._ar_flush()
    assert matched == [(session.id, b"AB"), (session.id, b"C")]
    assert session.txt_recv.toPlainText().splitlines() == ["AB", "C"]
    assert session.rx_bytes == 3
    assert session._last_recv_time == start + 0.030
    assert session._rx_received_at is None
    assert session._ar_last_received_at is None
    assert session._ar_gap_timer.timerType() == Qt.PreciseTimer


def test_silence_waits_for_rx_still_queued_for_gui(window, monkeypatch):
    w = window
    session = _bind_timed_conn(w)
    matched = []
    monkeypatch.setattr(w, "_ar_match", matched.append)
    start = time.monotonic() - 1
    session.conn.receive(b"A", start)
    session.conn.last_received_at = start + 0.005
    w._ar_flush()
    assert matched == []
    assert session._ar_buf == b"A"
    session.conn.receive(b"B", start + 0.005)
    w._ar_flush()
    assert matched == [b"AB"]


def test_silence_rechecks_deadline_and_reset_clears_timestamp(window, monkeypatch):
    w = window
    session = _bind_timed_conn(w)
    matched = []
    monkeypatch.setattr(w, "_ar_match", matched.append)
    received_at = time.monotonic()
    session.conn.receive(b"A", received_at)
    with monkeypatch.context() as clock:
        clock.setattr("main_window.time.monotonic", lambda: received_at + 0.010)
        w._ar_flush()
    assert matched == []
    assert session._ar_buf == b"A"
    assert session._ar_gap_timer.isActive()
    w._ar_reset_buf()
    assert session._ar_last_received_at is None
    assert session._ar_buf == b""
    assert not session._ar_gap_timer.isActive()


def test_silence_does_not_wait_for_rx_already_consumed_by_another_engine(
        window, monkeypatch):
    w = window
    session = _bind_timed_conn(w)
    matched = []
    monkeypatch.setattr(w, "_ar_match", matched.append)
    start = time.monotonic() - 1
    session.conn.receive(b"A", start)
    monkeypatch.setattr(w, "_feed_session_engines", lambda *_args, **_kwargs: None)
    session.conn.receive(b"B", start + 0.005)
    w._ar_flush()
    assert matched == [b"A"]
    assert not session._ar_gap_timer.isActive()


def test_timed_rx_from_replaced_connection_is_dropped(window):
    w = window
    session = _bind_timed_conn(w)
    old_conn = session.conn
    session.conn = TimedConn()
    w._bind_conn_signals(session.conn, session)
    old_conn.receive(b"old", time.monotonic())
    assert session.rx_bytes == 0
    assert session._rx_processed_at is None
    session.conn.receive(b"new", time.monotonic())
    assert session.rx_bytes == 3
    assert session._ar_buf == b"new"


def test_last_frame_flushes_through_actual_timer(window, monkeypatch):
    w = window
    session = _bind_timed_conn(w)
    matched = []
    monkeypatch.setattr(w, "_ar_match", lambda data: matched.append(
        (data, time.monotonic())))
    received_at = time.monotonic()
    session.conn.receive(b"last", received_at)
    deadline = received_at + 1
    while not matched and time.monotonic() < deadline:
        _APP.processEvents()
        time.sleep(0.001)
    assert len(matched) == 1
    assert matched[0][0] == b"last"
    assert matched[0][1] >= received_at + 0.020
    assert session._ar_buf == b""


def test_pending_suffix_does_not_flush_previous_frame(window, monkeypatch):
    w = window
    entered, release = threading.Event(), threading.Event()

    class PausedPort:
        is_open = True
        reads = 0

        @property
        def in_waiting(self):
            if self.reads == 1:
                entered.set()
                release.wait(1)
            return 0

        def read(self, size):
            self.reads += 1
            if self.reads == 1:
                return b"B"
            reader._running = False
            return b""

        def cancel_read(self):
            release.set()

        def close(self):
            self.is_open = False

    port = PausedPort()
    reader = serial_io.SerialReader(port)
    conn = serial_io.SerialConn("fake", 115200, 8, "N", 1)
    conn._ser, conn._reader = port, reader
    reader.data_received.connect(conn.data_received)
    reader.data_received_timed.connect(conn.data_received_timed)
    reader.error_occurred.connect(conn._on_reader_error)
    session = w.active_session()
    session.conn = conn
    session._ar_enabled = True
    w._bind_conn_signals(conn, session)
    matched = []
    monkeypatch.setattr(w, "_ar_match", matched.append)
    # Deterministic arrival times with the GUI already past the deadline.
    start = time.monotonic() - 1
    monkeypatch.setattr(serial_io, "time", SimpleNamespace(monotonic=lambda: start + 0.005))
    try:
        reader._emit_received(b"A", start)
        reader.start()
        assert entered.wait(1)
        w._ar_flush()
        assert matched == []
        release.set()
        assert reader.wait(1000)
        deadline = time.monotonic() + 1
        while not matched and time.monotonic() < deadline:
            _APP.processEvents()
            time.sleep(0.001)
        assert matched == [b"AB"]
    finally:
        release.set()
        conn.close()


@pytest.mark.parametrize("single_chunk", [False, True])
@pytest.mark.parametrize("timer_flush", [False, True])
def test_oversized_silence_frame_discards_until_boundary(
        window, monkeypatch, single_chunk, timer_flush):
    from automation.auto_reply_gate import GAP_BUF_MAX
    w = window
    session = _bind_timed_conn(w)
    matched, notices = [], []
    monkeypatch.setattr(w, "_ar_match", matched.append)
    monkeypatch.setattr(w, "toast", lambda *args, **kwargs: notices.append(args))
    # Feed through session routing while skipping expensive rendering of 1MiB.
    monkeypatch.setattr(w, "on_data_received", lambda data, target=None: w._auto_reply(data))
    start = time.monotonic() - 1
    if single_chunk:
        session.conn.receive(b"A" * (GAP_BUF_MAX + 1), start)
    else:
        session.conn.receive(b"A" * GAP_BUF_MAX, start)
        assert len(session._ar_buf) == GAP_BUF_MAX
        assert not session._ar_gap_overflow
        session.conn.receive(b"B", start + 0.005)
    assert session._ar_buf == b""
    assert session._ar_gap_overflow
    for i in range(1, 21):
        session.conn.receive(b"tail", start + 0.005 + i * 0.005)
        assert session._ar_buf == b""
    assert len(notices) == 1
    assert matched == []
    if timer_flush:
        w._ar_flush()
        assert not session._ar_gap_overflow
    session.conn.receive(b"OK", start + 0.150)
    w._ar_flush()
    assert matched == [b"OK"]
    assert not session._ar_gap_overflow


def test_overflow_reset_and_session_isolation(window, monkeypatch):
    from automation.auto_reply_gate import GAP_BUF_MAX
    w = window
    first = _bind_timed_conn(w)
    monkeypatch.setattr(w, "on_data_received", lambda data, target=None: w._auto_reply(data))
    first.conn.receive(b"A" * (GAP_BUF_MAX + 1), time.monotonic())
    second = w.add_session(activate=True)
    assert not second._ar_gap_overflow
    with w._with_session(first):
        w._ar_reset_buf()
    assert not first._ar_gap_overflow
    assert not first._ar_gap_timer.isActive()
