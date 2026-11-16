# -*- coding: utf-8 -*-
"""Selectable serial transport contract shared by terminal and bridge."""
import logging
import os
from typing import Any, Protocol

from transport.serial_io import SerialConn as PySerialConn
from transport.qt_serial_io import QSerialPortConn

_log = logging.getLogger(__name__)
BACKENDS = {"qserialport": QSerialPortConn, "pyserial": PySerialConn}


class SerialConnection(Protocol):
    """Backend-neutral API. Signals are Qt signals emitted with these payloads.

    data_received(bytes), data_received_timed(bytes, monotonic_seconds),
    error_occurred(str), state_changed(bool). RX chunks are arbitrary byte
    sequences; silence/length framing belongs to the session consumers.
    send returns the accepted byte count. close stops I/O before returning.
    Failed parameter updates attempt to restore the previous configuration.

    A backend may expose notice_occurred(str) for rejected parameters when
    validation or successful rollback preserves the current connection.
    In that case apply_params returns False and retains the current settings.
    """
    backend_name: str
    data_received: Any
    data_received_timed: Any
    error_occurred: Any
    state_changed: Any

    @property
    def is_open(self) -> bool: ...
    @property
    def last_received_at(self): ...
    def open(self) -> bool: ...
    def close(self) -> None: ...
    def send(self, data, target=None) -> int: ...
    def apply_params(self, baud=None, bytesize=None, parity=None,
                     stopbits=None, flow=None) -> bool: ...
    def set_dtr(self, on) -> None: ...
    def set_rts(self, on) -> None: ...
    def send_break(self, duration=0.25) -> None: ...
    def read_lines(self) -> dict: ...


def create_serial_connection(port, baud, bytesize, parity, stopbits,
                             parent=None, flow="none", *, backend=None) -> SerialConnection:
    name = (backend or os.environ.get("COMMTOOL_SERIAL_BACKEND", "qserialport")).strip().lower()
    if name not in BACKENDS:
        raise ValueError("Unknown serial backend %r; choose %s" % (name, ", ".join(BACKENDS)))
    _log.info("serial backend=%s port=%s", name, port)
    return BACKENDS[name](port, baud, bytesize, parity, stopbits, parent=parent, flow=flow)
