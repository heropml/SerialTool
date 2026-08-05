# -*- coding: utf-8 -*-
"""数据录制 / 回放：把一段真实收发流按原始时序录下来存盘，之后可当「设备」重放。

与「宏录制」的分工：
- 宏录制录的是**你发了什么**，产出可编辑的脚本（TX 侧、语义化）
- 本模块录的是**线路上的原始字节流**（RX 为主、含 TX 便于对照），产出 .ctrec 数据文件，
  回放时按原时间间隔把 RX 注入连接 —— 用于无硬件复现问题、离线调试、把现场发给同事

文件格式：JSON Lines（首行 header，其后每行一个事件），文本可读、可 diff、易手改：
    {"_": "ctrec", "v": 1, "created": "...", "note": "..."}
    {"t": 0.0,   "d": "rx", "b": "41 42"}
    {"t": 0.153, "d": "tx", "b": "4F 4B"}
t = 相对录制开始的秒数；b = 空格分隔 HEX（可读性优先，比 base64 好手改）。

Player 只依赖一个 `inject(bytes)` 回调，不碰 Qt 控件；定时由调用方（对话框）用 QTimer 驱动，
便于单测。
"""
import io
import json
import math
import time

_MAGIC = "ctrec"
_VERSION = 1
_MAX_EVENTS = 200000        # 单次录制事件上限，防长跑吃内存
_MAX_CHUNK = 65536          # 单事件字节上限
_MAX_FILE_BYTES = 64 << 20  # 载入文件上限 64MB，防误选巨型文件卡死
_MAX_TICK_EVENTS = 1000     # 单次 tick 派发上限，防「最快」模式一次排队几十万个 Qt 回调卡死 UI


class RecordError(Exception):
    pass


def _hex(b):
    return bytes(b).hex(" ").upper()


def _unhex(s):
    return bytes.fromhex(str(s).replace(" ", ""))


class StreamRecorder:
    """录制器：主窗在收/发处调 on_rx / on_tx，停止后 save() 落盘。"""

    def __init__(self, max_events=_MAX_EVENTS):
        self._max = max_events
        self.events = []        # [(t_rel, 'rx'|'tx', bytes)]
        self.recording = False
        self.truncated = False
        self._t0 = None
        self._wall_t0 = None

    def start(self):
        self.events = []
        self.truncated = False
        self._t0 = None
        self._wall_t0 = None
        self.recording = True

    def stop(self):
        self.recording = False

    def clear(self):
        self.events = []
        self.truncated = False
        self._t0 = None
        self._wall_t0 = None

    def __len__(self):
        return len(self.events)

    @property
    def rx_count(self):
        return sum(1 for _t, d, _b in self.events if d == "rx")

    @property
    def tx_count(self):
        return sum(1 for _t, d, _b in self.events if d == "tx")

    @property
    def duration(self):
        return self.events[-1][0] if self.events else 0.0

    @property
    def total_bytes(self):
        return sum(len(b) for _t, _d, b in self.events)

    def _add(self, direction, data, t=None):
        if not self.recording or not data:
            return
        now = time.monotonic() if t is None else t
        if self._t0 is None:
            self._t0 = now
            # Wall-clock anchor so session-diff / tools can map relative t
            # back to absolute time for jump_to_session_time.
            self._wall_t0 = time.time()
        rel = max(0.0, now - self._t0)
        payload = bytes(data)
        # 大块按同一时间戳拆事件，不能直接截掉尾部；录制的是原始流，静默丢字节会让复现失真。
        for off in range(0, len(payload), _MAX_CHUNK):
            if len(self.events) >= self._max:
                self.truncated = True   # 到上限停止采集（保留最早的现场，不滚动丢头）
                return
            self.events.append((rel, direction, payload[off:off + _MAX_CHUNK]))

    def on_rx(self, data, t=None):
        self._add("rx", data, t)

    def on_tx(self, data, t=None):
        self._add("tx", data, t)

    # ---------------- 存盘 / 载入 ----------------
    def save(self, path, note=""):
        header = {"_": _MAGIC, "v": _VERSION, "note": str(note or ""),
                  "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        if self._wall_t0 is not None:
            header["wall_t0"] = float(self._wall_t0)
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(header, ensure_ascii=False) + "\n")
            for t, d, b in self.events:
                f.write(json.dumps({"t": round(t, 4), "d": d, "b": _hex(b)},
                                   ensure_ascii=False) + "\n")
        return len(self.events)


def load(path):
    """读 .ctrec → (events, header)。格式非法抛 RecordError。
    坏行整行跳过而不是整体失败 —— 录制文件常被手改，容忍一两行笔误更实用。"""
    import os
    try:
        if os.path.getsize(path) > _MAX_FILE_BYTES:
            raise RecordError("文件过大（上限 %d MB）" % (_MAX_FILE_BYTES >> 20))
    except OSError as e:
        raise RecordError(str(e))
    events, header, bad = [], {}, 0
    first_content = True
    with io.open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                bad += 1
                first_content = False
                continue
            if first_content:
                first_content = False
                if not isinstance(obj, dict) or obj.get("_") != _MAGIC:
                    bad += 1
                    continue
                if obj.get("v") != _VERSION:
                    raise RecordError("不支持的录制文件版本：%s" % obj.get("v"))
                header = obj
                continue
            try:
                t = float(obj["t"])
                d = obj["d"]
                b = _unhex(obj["b"])
            except Exception:
                bad += 1
                continue
            if (not math.isfinite(t)) or len(b) > _MAX_CHUNK:
                bad += 1
                continue
            if d not in ("rx", "tx") or not b:
                bad += 1
                continue
            if len(events) >= _MAX_EVENTS:
                raise RecordError("事件过多（上限 %d 条）" % _MAX_EVENTS)
            events.append((max(0.0, t), d, b))
    if not header:
        raise RecordError("不是有效的录制文件（缺文件头）")
    events.sort(key=lambda e: e[0])     # 手改后时间戳可能乱序，回放前排好
    header["bad_lines"] = bad
    return events, header


class Player:
    """回放器：按原始时序把 rx 事件交给 inject 回调。

    调用方每隔一小段调 tick(now)，本类返回这段时间内到期的事件。这样定时精度、
    暂停/停止都由调用方（QTimer）控制，本类保持纯逻辑、可单测。
    """

    def __init__(self, events, inject, speed=1.0, include_tx=False, loop=False):
        self.events = [e for e in events if include_tx or e[1] == "rx"]
        self.inject = inject
        self.speed = max(0.01, float(speed))
        self.loop = bool(loop)
        self.idx = 0
        self.started_at = None
        self.finished = False
        self.loops_done = 0
        self.paused = False
        self._pause_elapsed = 0.0

    def __len__(self):
        return len(self.events)

    @property
    def duration(self):
        return self.events[-1][0] if self.events else 0.0

    def start(self, now):
        self.idx = 0
        self.finished = False
        self.loops_done = 0
        self.started_at = now
        self.paused = False
        self._pause_elapsed = 0.0

    def pause(self, now):
        """暂停并记下已播进度。now 必须与 start()/tick() 同一时钟（调用方显式传），
        不在这里自己取 monotonic：合成时钟（如 start(0.0)）与真实开机时长无法区分。"""
        if self.started_at is None or self.finished:
            self.paused = True
            return
        if not self.paused:
            self._pause_elapsed = max(0.0, (now - self.started_at) * self.speed)
        self.paused = True

    def resume(self, now):
        if self.started_at is not None and self.paused and not self.finished:
            self.started_at = now - (self._pause_elapsed / self.speed)
            self.paused = False

    def _emit_one(self):
        if self.idx >= len(self.events):
            return 0
        _t, _d, b = self.events[self.idx]
        self.idx += 1
        try:
            self.inject(b)
        except Exception:
            pass
        if self.idx >= len(self.events):
            self.loops_done += 1
            if self.loop:
                self.idx = 0
                self.finished = False
            else:
                self.finished = True
        return 1

    def step(self, now):
        if self.finished or not self.events or self.started_at is None:
            if not self.events:
                self.finished = True
            return 0
        if self.idx >= len(self.events):
            self.finished = True
            return 0
        t_ev = self.events[self.idx][0]
        looped = False
        n = self._emit_one()
        if self.loop and self.idx == 0 and self.loops_done:
            self.started_at = now
            self._pause_elapsed = 0.0
            looped = True
        if not looped and not self.finished:
            self._pause_elapsed = t_ev + 1e-9
            self.started_at = now - (self._pause_elapsed / self.speed)
        return n

    def seek(self, t_rel, now):
        was_paused = self.paused
        t_rel = max(0.0, float(t_rel))
        if not self.events:
            self.finished = True
            return 0.0
        self.idx = 0
        while self.idx < len(self.events) and self.events[self.idx][0] < t_rel:
            self.idx += 1
        self.finished = self.idx >= len(self.events)
        self._pause_elapsed = t_rel if not self.finished else self.duration
        self.started_at = now - (self._pause_elapsed / self.speed)
        self.paused = was_paused and not self.finished
        return self.position

    def tick(self, now):
        if self.finished or self.started_at is None or not self.events:
            if not self.events:
                self.finished = True
            return 0
        if self.paused:
            return 0
        elapsed = (now - self.started_at) * self.speed
        self._pause_elapsed = elapsed
        n = 0
        while (self.idx < len(self.events) and n < _MAX_TICK_EVENTS
               and self.events[self.idx][0] <= elapsed):
            just = self._emit_one()
            n += just
            if self.finished:
                break
            if just and self.loop and self.idx == 0 and self.loops_done:
                self.started_at = now
                self._pause_elapsed = 0.0
                break
        return n

    @property
    def position(self):
        if not self.events:
            return 0.0
        if self.finished:
            return self.duration
        if self.idx < len(self.events):
            return float(self.events[self.idx][0])
        return self.duration

    @property
    def progress(self):
        return (1.0 if self.finished
                else (self.idx / len(self.events) if self.events else 1.0))
