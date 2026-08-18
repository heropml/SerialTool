# -*- coding: utf-8 -*-
"""脚本控制台执行核心：把用户 Python 脚本跑在 worker 线程里，用 send/expect/sleep/log/check
编排真实收发流程。

为什么是线程而不是子进程：脚本要 `send(); r = expect(...)` 顺序阻塞地驱动**当前连接**，
子进程碰不到连接对象（脚本应答那套用子进程是因为它只做纯计算、只回传 bytes）。代价是
纯 CPU 死循环（`while True: pass`）杀不掉——停止是协作式的，在 send/expect/sleep/recv
里检查停止标志。

线程安全约定：worker 线程**只**碰 deque / Condition / Event / 信号，绝不直接碰 Qt 控件或连接对象；
发送经 send_requested 信号回主线程执行，收流由主线程 feed() 投进队列。
"""
from collections import deque
import re
import threading
import time
import traceback

from PyQt5.QtCore import QThread, pyqtSignal


class ScriptStopped(Exception):
    """用户点了停止 —— 用异常中断脚本的阻塞调用，run() 里捕获后正常收尾。"""


def parse_hex(text):
    """'AA BB' / 'AABB' / '0xAA,0xBB' → bytes；非法抛 ValueError。"""
    t = re.sub(r"0x|[\s,]", "", str(text), flags=re.I)
    if len(t) % 2:
        raise ValueError("hex 长度必须为偶数: %s" % text)
    return bytes.fromhex(t)


def _to_bytes(data, hex_mode=False):
    """脚本传入的数据 → bytes：bytes/bytearray 原样；hex=True 按 HEX 串解析；否则按 UTF-8 编码。"""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if hex_mode:
        return parse_hex(data)
    return str(data).encode("utf-8")


class ScriptWorker(QThread):
    """跑一段用户脚本。收流由主线程 feed() 投队列；发送经 send_requested 回主线程。"""

    # worker, payload, done_event, result_dict。等待 GUI 完成后才让脚本继续，提供发送背压。
    send_requested = pyqtSignal(object, bytes, object, object)
    log_line = pyqtSignal(str)
    run_finished = pyqtSignal(bool, str)     # ok, 汇总文案

    _MAX_BUF = 1 << 20        # expect/recv 各级待处理缓冲上限 1MB，防设备狂刷吃内存

    def __init__(self, code, parent=None):
        super().__init__(parent)
        self._code = code
        # 收包可能发生在脚本 sleep/纯计算期间，必须在 feed 入口就限流；只限制 expect 的
        # self._buf 挡不住尚未被 worker 取出的 Queue 无限增长。deque + Condition 同时提供
        # 总字节上限和可中断等待。
        self._rx = deque()
        self._rx_bytes = 0
        self._rx_cv = threading.Condition()
        self._stop = threading.Event()
        self._buf = b""           # expect 跨调用保留的未匹配残段
        self._warned_trunc = False    # 缓冲截断只告警一次，不刷屏
        self.checks_passed = 0
        self.checks_failed = 0

    @staticmethod
    def _chk_timeout(timeout):
        """超时值校验：负数是调用方笔误（会被静默当成 0=不等待），直接报错早暴露。"""
        if timeout is None or timeout < 0:
            raise ValueError("timeout 不能为负：%r" % (timeout,))
        return timeout

    # ---------------- 主线程侧 ----------------
    def feed(self, data):
        """主线程收到 RX 时调用，把数据投给脚本。"""
        chunk = bytes(data)
        if not chunk:
            return
        truncated = False
        with self._rx_cv:
            if len(chunk) > self._MAX_BUF:
                # 单块就超限：保留最新尾部，并清掉更早的待处理块。
                chunk = chunk[-self._MAX_BUF:]
                self._rx.clear()
                self._rx_bytes = 0
                truncated = True
            while self._rx and self._rx_bytes + len(chunk) > self._MAX_BUF:
                self._rx_bytes -= len(self._rx.popleft())
                truncated = True
            self._rx.append(chunk)
            self._rx_bytes += len(chunk)
            self._rx_cv.notify()
        if truncated:
            self._warn_truncated()

    def stop(self):
        self._stop.set()
        # 唤醒正在 recv/expect 或等待主线程完成发送的 worker，使停止立即生效。
        with self._rx_cv:
            self._rx_cv.notify_all()

    def stopping(self):
        return self._stop.is_set()

    # ---------------- 脚本 API（worker 线程内执行）----------------
    def _api_send(self, data, hex=False):
        """发送。data 为 bytes 原样发；hex=True 时按 HEX 串解析；否则 UTF-8 编码。"""
        self._check_stop()
        payload = _to_bytes(data, hex)
        if not payload:
            return 0
        # 一次只允许一个发送在途，并等待 GUI 线程给出完成结果。这样不会因脚本紧密循环
        # 无界堆积 Qt 队列事件；关闭/停止后，主窗口也能按 worker 身份丢弃旧发送。
        done = threading.Event()
        result = {"ok": False}
        self.send_requested.emit(self, payload, done, result)
        while not done.wait(0.05):
            self._check_stop()
        self._check_stop()
        return len(payload) if result["ok"] else 0

    def _api_recv(self, timeout=1000):
        """等任意数据，返回本次收到的 bytes（超时返回 b""）。先吐 expect 残留的缓冲。"""
        self._check_stop()
        self._chk_timeout(timeout)
        if self._buf:
            out, self._buf = self._buf, b""
            return out
        chunk = self._wait_chunk(time.monotonic() + timeout / 1000.0)
        return chunk or b""

    def _api_expect(self, pattern, timeout=1000, hex=False):
        """等到收到的数据里出现 pattern 为止，返回**匹配点之前(含匹配)**的全部字节；
        超时返回 None。未消费的尾部留给下次 expect/recv。"""
        self._check_stop()
        self._chk_timeout(timeout)
        pat = _to_bytes(pattern, hex)
        if not pat:
            raise ValueError("expect 的 pattern 不能为空")
        deadline = time.monotonic() + timeout / 1000.0
        while True:
            idx = self._buf.find(pat)
            if idx >= 0:
                end = idx + len(pat)
                out, self._buf = self._buf[:end], self._buf[end:]
                return out
            chunk = self._wait_chunk(deadline)
            if chunk is None:                 # 超时
                return None
            self._buf += chunk
            if len(self._buf) > self._MAX_BUF:
                # 只保留尾部够继续匹配。**告警一次**：设备狂刷时，若模式前半截落在被丢弃的
                # 部分里，这个 expect 就再也匹配不上了，不提示的话现象很难懂。
                self._buf = self._buf[-self._MAX_BUF:]
                self._warn_truncated()

    def _api_sleep(self, ms):
        """睡 ms 毫秒；期间可被停止打断。"""
        self._check_stop()
        self._chk_timeout(ms)
        deadline = time.monotonic() + ms / 1000.0
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                return
            if self._stop.wait(min(remain, 0.05)):
                raise ScriptStopped()

    def _api_log(self, *args):
        self.log_line.emit(" ".join(str(a) for a in args))

    def _api_check(self, cond, msg=""):
        """断言：真→计通过，假→计失败并记一行。返回 bool，脚本可据此分支。"""
        ok = bool(cond)
        if ok:
            self.checks_passed += 1
            self.log_line.emit("  ✓ %s" % (msg or "check"))
        else:
            self.checks_failed += 1
            self.log_line.emit("  ✗ %s" % (msg or "check"))
        return ok

    # ---------------- 内部 ----------------
    def _check_stop(self):
        if self._stop.is_set():
            raise ScriptStopped()

    def _wait_chunk(self, deadline):
        """阻塞等一块数据；超时返回 None；停止时抛 ScriptStopped。"""
        with self._rx_cv:
            while True:
                if self._stop.is_set():
                    raise ScriptStopped()
                # 先查队列再看 deadline，使 recv(timeout=0) 真正成为一次非阻塞读取。
                if self._rx:
                    chunk = self._rx.popleft()
                    self._rx_bytes -= len(chunk)
                    return chunk
                remain = deadline - time.monotonic()
                if remain <= 0:
                    return None
                self._rx_cv.wait(min(remain, 0.05))

    def _warn_truncated(self):
        """接收截断只告警一次；可能由 GUI feed 或 worker expect 两个线程调用。"""
        with self._rx_cv:
            if self._warned_trunc:
                return
            self._warned_trunc = True
        self.log_line.emit(
            "⚠ 接收缓冲超过 %d KB 已截断最旧数据，若匹配模式恰好跨越截断点将匹配不到"
            % (self._MAX_BUF // 1024))

    def _globals(self):
        return {
            "__name__": "__commtool_script__",
            "send": self._api_send,
            "recv": self._api_recv,
            "expect": self._api_expect,
            "sleep": self._api_sleep,
            "log": self._api_log,
            "check": self._api_check,
            "hexs": parse_hex,          # 'AA BB' → b'\xaa\xbb'，方便手搓帧
        }

    # ---------------- 线程主体 ----------------
    def run(self):
        ok = True
        summary = ""
        try:
            exec(compile(self._code, "<script>", "exec"), self._globals())
        except ScriptStopped:
            ok = False
            summary = "stopped"
        except SyntaxError as e:
            ok = False
            summary = "syntax"
            self.log_line.emit("语法错误 第 %s 行: %s" % (e.lineno, e.msg))
        except Exception:
            ok = False
            summary = "error"
            self.log_line.emit(traceback.format_exc(limit=6).rstrip())
        if summary == "" and self.checks_failed:
            ok = False
            summary = "checks"
        self.run_finished.emit(ok, summary)
