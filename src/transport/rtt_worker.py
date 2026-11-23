# -*- coding: utf-8 -*-
"""Isolate each active J-Link DLL in its own process."""

import functools
import logging
import multiprocessing

_log = logging.getLogger(__name__)

_METHODS = (
    "num_connected_emulators", "open", "exec_command", "set_tif", "connect",
    "reset", "target_connected", "connected", "swo_flush", "memory_read32",
    "rtt_start", "rtt_read", "rtt_write", "rtt_get_num_down_buffers",
    "rtt_get_buf_descriptor",
)


class JLinkProcessExited(ConnectionError):
    """The native driver process closed the connection unexpectedly."""


def _serve_jlink(pipe, jlink, driver_error):
    methods = {name: getattr(jlink, name) for name in _METHODS
               if callable(getattr(jlink, name, None))}
    pipe.send(("ok", tuple(methods)))
    while True:
        name, args, kwargs = pipe.recv()
        try:
            if name == "serial_number":
                result = jlink.serial_number
            else:
                result = methods[name](*args, **kwargs)
            if name == "rtt_read":
                result = bytes(result or b"")
            reply = ("ok", result)
        except driver_error as exc:
            reply = ("driver_error", str(exc))
        except Exception as exc:
            reply = ("error", str(exc) or type(exc).__name__)
        pipe.send(reply)


def _run_jlink_worker(pipe, dll_hint):
    from transport import rtt_io

    with pipe:
        try:
            pylink = rtt_io._import_pylink()
            jlink = rtt_io.make_jlink(pylink, hint=dll_hint)
        except Exception as exc:
            pipe.send(("error", str(exc) or type(exc).__name__))
            return
        try:
            _serve_jlink(pipe, jlink, pylink.errors.JLinkException)
        except (EOFError, BrokenPipeError, ConnectionResetError):
            return  # The parent closed its end of the pipe.
        finally:
            for name in ("rtt_stop", "close"):
                try:
                    getattr(jlink, name)()
                except Exception:
                    _log.debug("rtt %s cleanup failed", name, exc_info=True)


class JLinkProcess:
    """Send synchronous DLL calls from an RTT worker thread over a private pipe."""

    def __init__(self, dll_hint, cancelled, driver_error):
        self._dll_hint = dll_hint
        self._cancelled = cancelled
        self._driver_error = driver_error
        self._pipe = None
        self._process = None
        self._methods = ()

    def start(self):
        context = multiprocessing.get_context("spawn")
        self._pipe, worker_pipe = context.Pipe()
        process = context.Process(target=_run_jlink_worker,
                                  args=(worker_pipe, self._dll_hint),
                                  name="CommToolJLink", daemon=True)
        try:
            process.start()
        finally:
            worker_pipe.close()
        self._process = process
        self._methods = self._receive()

    def __getattr__(self, name):
        if name in self._methods:
            return functools.partial(self._call, name)
        raise AttributeError(name)

    @property
    def serial_number(self):
        return self._call("serial_number")

    def _call(self, name, *args, **kwargs):
        if self._cancelled():
            raise InterruptedError()
        try:
            self._pipe.send((name, args, kwargs))
        except OSError as exc:
            raise JLinkProcessExited() from exc
        return self._receive()

    def _receive(self):
        try:
            while not self._cancelled():
                if self._pipe.poll(0.05):
                    status, result = self._pipe.recv()
                    break
            else:
                raise InterruptedError()
        except (EOFError, BrokenPipeError, ConnectionResetError) as exc:
            raise JLinkProcessExited() from exc
        if status == "driver_error":
            raise self._driver_error(result)
        if status == "error":
            raise RuntimeError(result)
        return result

    def close(self):
        if self._pipe is not None:
            self._pipe.close()
            self._pipe = None
        process = self._process
        if process is None:
            return
        # EOF gives the child a chance to stop RTT and close the probe. A stuck
        # DLL may never return, so reap that child without touching other links.
        process.join(0.25)
        if process.is_alive():
            process.terminate()
            process.join(0.5)
        if process.is_alive():
            process.kill()
            process.join()
        process.close()
        self._process = None
