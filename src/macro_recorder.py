# -*- coding: utf-8 -*-
"""宏录制：把用户在主界面的手动收发过程录下来，生成可回放的脚本控制台脚本。

不依赖 Qt，纯逻辑可单测。主窗在发送成功处调 on_tx()、收包处调 on_rx()，
停止后 to_script() 生成 send/expect/check/sleep 代码，丢进脚本库即可重放。

生成策略：
- 每个 TX 出一行 send(...)；其后到下一个 TX 之前的 RX 合并成一条 expect(...) + check(...)
- 事件之间的静默间隔 ≥ gap_ms 时补一行 sleep(ms)，保留原始节奏
- 字节可打印就用字符串字面量（"AT\\r\\n"），否则用 hexs("01 03 ..")
"""
import time

_MAX_EVENTS = 2000        # 录制事件上限，防长时间录制吃内存
_MAX_EXPECT = 32          # expect 模式最多取回包前 N 字节（整包太长会过拟合）
_MAX_CHUNK = 4096         # 单条事件记录的字节上限


def _lit(data: bytes) -> str:
    """bytes → Python 字面量：可打印 ASCII 用字符串，否则用 hexs("..")。"""
    if data and all(32 <= b < 127 or b in (9, 10, 13) for b in data):
        s = data.decode("ascii")
        for a, b in (("\\", "\\\\"), ('"', '\\"'), ("\r", "\\r"),
                     ("\n", "\\n"), ("\t", "\\t")):
            s = s.replace(a, b)
        return '"%s"' % s
    return 'hexs("%s")' % data.hex(" ").upper()


def _label(data: bytes, limit: int = 24) -> str:
    """给 check() 用的可读标签（截断 + 转义引号）。
    先剥掉首尾的 CR/LF/空白再判断可打印性 —— 否则 b"OK\\r\\n" 会因结尾的 \\r\\n 整体
    退化成十六进制，标签变成没法看的 "4F 4B 0D 0A"。"""
    core = data.strip(b"\r\n\t ")
    if core and all(32 <= b < 127 for b in core):
        s = core.decode("ascii")
    else:
        s = data.hex(" ").upper()
    s = s[:limit].replace("\\", "").replace('"', "'")
    return s


class MacroRecorder:
    """录制器。start() 后由主窗喂 on_tx/on_rx，stop() 后 to_script() 出代码。"""

    def __init__(self, max_events=_MAX_EVENTS):
        self._max = max_events
        self._events = []          # [(t, 'tx'|'rx', bytes)]
        self.recording = False
        self.truncated = False     # 是否因超上限丢过事件

    # ---------------- 录制控制 ----------------
    def start(self):
        self._events = []
        self.truncated = False
        self.recording = True

    def stop(self):
        self.recording = False

    def clear(self):
        self._events = []
        self.truncated = False

    @property
    def tx_count(self):
        return sum(1 for _t, k, _d in self._events if k == "tx")

    @property
    def rx_count(self):
        return sum(1 for _t, k, _d in self._events if k == "rx")

    def __len__(self):
        return len(self._events)

    # ---------------- 事件采集 ----------------
    def _add(self, kind, data, t=None):
        if not self.recording:
            return
        if len(self._events) >= self._max:
            self.truncated = True      # 到上限就停止采集（保留最早的流程，不滚动丢头）
            return
        self._events.append((time.monotonic() if t is None else t,
                             kind, bytes(data[:_MAX_CHUNK])))

    def on_tx(self, data, t=None):
        if data:
            self._add("tx", data, t)

    def on_rx(self, data, t=None):
        if data:
            self._add("rx", data, t)

    # ---------------- 生成脚本 ----------------
    def to_script(self, gap_ms=50, header=True, max_chars=None):
        """把录到的事件翻译成脚本代码。

        gap_ms：小于该间隔不补 sleep（忽略手速抖动）。max_chars 用于脚本库上限；
        超限时只在完整行边界截断，保证生成物仍是可编译的 Python。
        """
        evs = self._events
        lines = []
        if header:
            lines += ["# 由「宏录制」自动生成 —— 录制期间的手动收发已翻译成脚本",
                      "# 可自行调整 timeout / 增删 check；API 见「?」",
                      ""]
        if not evs:
            lines.append("log(\"（未录到任何收发）\")")
            return self._limit_script("\n".join(lines) + "\n", max_chars)

        prev_t = None
        i = 0
        while i < len(evs):
            t, kind, data = evs[i]
            if kind != "tx":
                # 没有对应发送的收包（设备主动上报）：只记成注释，不生成 expect
                lines.append("# 收到(无对应发送): %s" % _label(data, 48))
                prev_t = t
                i += 1
                continue

            if prev_t is not None:
                gap = int((t - prev_t) * 1000)
                if gap >= gap_ms:
                    lines.append("sleep(%d)" % gap)
            lines.append("send(%s)" % _lit(data))

            # 合并该次发送之后、下一次发送之前的所有回包
            j = i + 1
            rx = b""
            last_rx_t = None
            while j < len(evs) and evs[j][1] == "rx":
                rx += evs[j][2]
                last_rx_t = evs[j][0]
                j += 1
            if rx:
                latency_ms = int((last_rx_t - t) * 1000)
                # 超时留 3 倍余量并向上取整到 100ms，最少 200ms
                timeout = max(200, ((latency_ms * 3) // 100 + 1) * 100)
                lines.append('r = expect(%s, timeout=%d)' % (_lit(rx[:_MAX_EXPECT]), timeout))
                lines.append('check(r is not None, "%s")' % _label(rx))
                prev_t = last_rx_t
            else:
                prev_t = t
            i = j

        if self.truncated:
            lines.append("")
            lines.append("# ⚠ 录制事件超过上限，后续操作未录入")
        return self._limit_script("\n".join(lines) + "\n", max_chars)

    @staticmethod
    def _limit_script(code, max_chars):
        if max_chars is None or len(code) <= max_chars:
            return code
        marker = "# ⚠ 生成脚本超过脚本库上限，后续操作未保存\n"
        limit = max(0, int(max_chars) - len(marker))
        cut = code.rfind("\n", 0, limit + 1)
        prefix = code[:cut + 1] if cut >= 0 else ""
        return (prefix + marker)[:int(max_chars)]
