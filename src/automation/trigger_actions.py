# -*- coding: utf-8 -*-
"""Trigger external actions (webhook / run_cmd) as an event-bus consumer.

Qt-free: the GUI publishes ``trigger.hit``; this runner owns concurrency,
subprocess tracking, and HTTP POST. Beep / tray / mark stay in the GUI.
"""
import json
import http.client
import logging
import os
import socket
import ssl
import sys
import threading
import time
from automation.trigger_safe import resolve_webhook_target, shell_value

_log = logging.getLogger("commtool.trigger_actions")

MAX_ACTIONS = 8
CMD_TIMEOUT = 30.0
STOP_WAIT = 2.0


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Connect to a validated IP while retaining the original Host header."""

    def __init__(self, host, port, pinned_address, timeout=5):
        self._pinned_address = pinned_address
        super().__init__(host, port=port, timeout=timeout)

    def connect(self):
        self.sock = socket.create_connection(
            (self._pinned_address, self.port), self.timeout, self.source_address)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Pinned TCP destination + original hostname for certificate/SNI checks."""

    def __init__(self, host, port, pinned_address, timeout=5):
        self._pinned_address = pinned_address
        super().__init__(host, port=port, timeout=timeout,
                         context=ssl.create_default_context())

    def connect(self):
        sock = socket.create_connection(
            (self._pinned_address, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _send_pinned(target, address, data, timeout=5):
    cls = (_PinnedHTTPSConnection if target["scheme"] == "https"
           else _PinnedHTTPConnection)
    conn = cls(target["host"], target["port"], address, timeout=timeout)
    try:
        conn.request(
            "POST", target["path"], body=data,
            headers={"Content-Type": "application/json",
                     "User-Agent": "CommTool-Trigger/1.0"})
        response = conn.getresponse()
        response.read(256)
        # http.client never follows redirects; a 3xx is just a failed action.
        return 200 <= int(response.status) < 300
    finally:
        conn.close()


def _post_webhook(url, data, allow_insecure=False, timeout=5):
    target = resolve_webhook_target(url, allow_insecure=allow_insecure)
    if target is None:
        return False
    for address in target["addresses"]:
        try:
            if _send_pinned(target, address, data, timeout=timeout):
                return True
        except (OSError, ssl.SSLError, http.client.HTTPException, ValueError):
            continue
    return False


def kill_proc(proc):
    """End one run_cmd child (process group on POSIX, taskkill /T on Windows).

    run_cmd uses shell=True, so the handle is the shell. terminate() alone
    would leave grandchildren; both platforms reap the whole tree.
    """
    import subprocess
    if sys.platform == "win32":
        if proc.pid:
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True, timeout=5)
                if result.returncode == 0 or proc.poll() is not None:
                    return
                _log.debug("taskkill returned %s for pid %s",
                           result.returncode, proc.pid)
            except Exception:
                _log.debug("taskkill failed for pid %s", proc.pid, exc_info=True)
    else:
        import signal
        if proc.pid:
            try:
                os.killpg(proc.pid, getattr(signal, "SIGTERM", 15))
            except Exception:
                _log.debug("killpg SIGTERM failed for pid %s", proc.pid,
                           exc_info=True)
            else:
                try:
                    proc.wait(timeout=0.5)
                except Exception:
                    _log.debug("process group leader did not exit after SIGTERM",
                               exc_info=True)
                try:
                    os.killpg(proc.pid, getattr(signal, "SIGKILL", 9))
                except ProcessLookupError:
                    return
                except Exception:
                    _log.debug("killpg SIGKILL failed for pid %s", proc.pid,
                               exc_info=True)
                else:
                    try:
                        proc.wait(timeout=1)
                    except Exception:
                        _log.debug("process group leader did not exit after SIGKILL",
                                   exc_info=True)
                    return
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            _log.debug("cannot kill pid %s", proc.pid, exc_info=True)


class TriggerActionRunner:
    """In-flight cap + webhook POST + run_cmd. Host is optional (timeouts / kill)."""

    def __init__(self, host=None):
        self.host = host
        self.lock = threading.Lock()
        self.busy = 0
        self.dropped = 0
        self.procs = set()
        self.launching = 0
        self.stopping = False

    def on_trigger_hit(self, payload):
        event = payload or {}
        rule = event.get("rule") or {}
        name = event.get("name") or ""
        direction = event.get("direction") or ""
        hits = event.get("hits") or 0
        if rule.get("webhook") and (rule.get("webhook_url") or "").strip():
            self.run_webhook(rule, name, direction, hits)
        if rule.get("run_cmd_on") and (rule.get("run_cmd") or "").strip():
            self.run_cmd(rule, name, direction, hits)

    def run_webhook(self, rule, name, direction, hits):
        url = (rule.get("webhook_url") or "").strip()
        allow_insecure = bool(rule.get("webhook_allow_insecure"))
        lower = url.lower()
        if not (lower.startswith("https://")
                or (allow_insecure and lower.startswith("http://"))):
            return
        payload = {
            "name": name,
            "direction": direction,
            "hits": hits,
            "pattern": rule.get("pattern") or "",
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        def _worker():
            try:
                data = json.dumps(payload).encode("utf-8")
                _post_webhook(
                    url, data, allow_insecure=allow_insecure, timeout=5)
            except Exception:
                _log.debug("trigger webhook failed", exc_info=True)

        self.spawn(_worker)

    def run_cmd(self, rule, name, direction, hits):
        raw = (rule.get("run_cmd") or "").strip()
        if not raw:
            return
        q = shell_value
        cmd = (raw.replace("{name}", q(name))
                  .replace("{hits}", q(hits))
                  .replace("{dir}", q(direction))
                  .replace("{pattern}", q(rule.get("pattern") or "")))

        def _worker():
            with self.lock:
                if self.stopping:
                    return
                self.launching += 1
            proc = None
            import subprocess
            try:
                kwargs = {"shell": True}
                if sys.platform == "win32":
                    kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                else:
                    kwargs["start_new_session"] = True
                proc = subprocess.Popen(cmd, **kwargs)
            except Exception:
                _log.debug("run_cmd launch failed", exc_info=True)
            finally:
                kill_after_register = False
                with self.lock:
                    if proc is not None:
                        if self.stopping:
                            kill_after_register = True
                        else:
                            self.procs.add(proc)
                    self.launching -= 1
            if proc is None:
                return
            if kill_after_register:
                self._kill(proc)
                return
            try:
                proc.wait(timeout=self._cmd_timeout())
            except subprocess.TimeoutExpired:
                _log.debug("run_cmd exceeded %ss, killing pid %s",
                           self._cmd_timeout(), proc.pid)
                self._kill(proc)
            except Exception:
                _log.debug("run_cmd wait failed", exc_info=True)
            finally:
                with self.lock:
                    self.procs.discard(proc)

        self.spawn(_worker)

    def spawn(self, worker):
        with self.lock:
            if self.stopping:
                return False
            if self.busy >= self._max_actions():
                self.dropped += 1
                return False
            self.busy += 1

        def _run():
            try:
                worker()
            except Exception:
                _log.debug("trigger action failed", exc_info=True)
            finally:
                with self.lock:
                    self.busy = max(0, self.busy - 1)

        try:
            threading.Thread(target=_run, daemon=True).start()
            return True
        except Exception:
            with self.lock:
                self.busy = max(0, self.busy - 1)
            return False

    def stop_procs(self):
        deadline = time.monotonic() + self._stop_wait()
        while True:
            with self.lock:
                self.stopping = True
                launching = self.launching
                procs, self.procs = list(self.procs), set()
            for proc in procs:
                if proc.poll() is None:
                    self._kill(proc)
            if not launching or time.monotonic() >= deadline:
                return
            time.sleep(0.01)

    def dropped_actions(self):
        with self.lock:
            return self.dropped

    def reset_dropped(self):
        with self.lock:
            self.dropped = 0

    def _kill(self, proc):
        host = self.host
        if host is not None:
            return host._trg_kill_proc(proc)
        return kill_proc(proc)

    def _max_actions(self):
        host = self.host
        if host is not None:
            return int(getattr(host, "_TRG_MAX_ACTIONS", MAX_ACTIONS))
        return MAX_ACTIONS

    def _cmd_timeout(self):
        host = self.host
        if host is not None:
            return float(getattr(host, "_TRG_CMD_TIMEOUT", CMD_TIMEOUT))
        return CMD_TIMEOUT

    def _stop_wait(self):
        host = self.host
        if host is not None:
            return float(getattr(host, "_TRG_STOP_WAIT", STOP_WAIT))
        return STOP_WAIT
