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
import ipaddress
import json
import logging
import math
import time

_MAGIC = "ctrec"
_VERSION = 1
_MAX_EVENTS = 200000        # 单次录制事件上限，防长跑吃内存
_MAX_CHUNK = 65536          # 单事件字节上限
_MAX_FILE_BYTES = 64 << 20  # 载入文件上限 64MB，防误选巨型文件卡死
_MAX_TICK_EVENTS = 1000     # 单次 tick 派发上限，防「最快」模式一次排队几十万个 Qt 回调卡死 UI


_log = logging.getLogger(__name__)


class RecordError(Exception):
    pass


def _hex(b):
    return bytes(b).hex(" ").upper()


def _unhex(s):
    return bytes.fromhex(str(s).replace(" ", ""))


class _RecordedEvents(list):
    """Public event tuples plus optional per-event endpoint metadata for PCAP."""

    def __init__(self):
        super().__init__()
        self.pcap_peers = []


class StreamRecorder:
    """录制器：主窗在收/发处调 on_rx / on_tx，停止后 save() 落盘。"""

    def __init__(self, max_events=_MAX_EVENTS):
        self._max = max_events
        self.events = _RecordedEvents()  # [(t_rel, 'rx'|'tx', bytes)]
        self.recording = False
        self.truncated = False
        self._t0 = None
        self._wall_t0 = None
        self.link = None        # optional net endpoint snapshot for PCAP export
        self._mcast_multiple_peers = False
        self._tcp_server_multiple_peers = False

    def start(self, link=None):
        self.events = _RecordedEvents()
        self.truncated = False
        self._t0 = None
        self._wall_t0 = None
        self.link = dict(link) if isinstance(link, dict) else None
        if isinstance(self.link, dict) and isinstance(self.link.get("peers"), list):
            self.link["peers"] = [
                list(p) if isinstance(p, (list, tuple)) else p
                for p in self.link["peers"]]
        self._mcast_multiple_peers = False
        self._tcp_server_multiple_peers = False
        self.recording = True

    def stop(self):
        self.recording = False

    def clear(self):
        self.events = _RecordedEvents()
        self.truncated = False
        self._t0 = None
        self._wall_t0 = None
        self.link = None
        self._mcast_multiple_peers = False
        self._tcp_server_multiple_peers = False

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

    def _add(self, direction, data, t=None, pcap_peer=None):
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
        peers = getattr(self.events, "pcap_peers", None)
        # 大块按同一时间戳拆事件，不能直接截掉尾部；录制的是原始流，静默丢字节会让复现失真。
        for off in range(0, len(payload), _MAX_CHUNK):
            if len(self.events) >= self._max:
                self.truncated = True   # 到上限停止采集（保留最早的现场，不滚动丢头）
                return
            self.events.append((rel, direction, payload[off:off + _MAX_CHUNK]))
            if isinstance(peers, list):
                peers.append(pcap_peer)

    @staticmethod
    def _same_udp_peer(link, source):
        try:
            src_ip, src_port = source
            return (ipaddress.IPv4Address(str(src_ip)) ==
                    ipaddress.IPv4Address(str(link.get("remote_ip")))
                    and int(src_port) == int(link.get("remote_port")))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _multicast_peer(source):
        try:
            src_ip, src_port = source
            port = int(src_port)
            if not 1 <= port <= 65535:
                return None
            return str(ipaddress.IPv4Address(str(src_ip))), port
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _same_tcp_server_peer(link, source):
        """TCP Server client keys are 'ip:port' strings from TcpServerConn._key."""
        try:
            text = str(source or "").strip()
            if ":" not in text:
                return False
            host, _, port_s = text.rpartition(":")
            return (ipaddress.IPv4Address(host.strip().strip("[]")) ==
                    ipaddress.IPv4Address(str(link.get("remote_ip")))
                    and int(port_s) == int(link.get("remote_port")))
        except (TypeError, ValueError):
            return False

    def _note_multicast_rx_peer(self, source):
        """Remember the sender for legacy PCAP metadata and return it for this event."""
        peer = self._multicast_peer(source)
        if peer is None:
            return None
        if not isinstance(self.link, dict):
            return peer
        if self._mcast_multiple_peers:
            return peer
        previous = self._multicast_peer((self.link.get("rx_peer_ip"),
                                         self.link.get("rx_peer_port")))
        if previous is not None and previous != peer:
            # Do not leave a stale header-level fallback that could mislabel a
            # caller which drops the per-event sidecar.
            self._mcast_multiple_peers = True
            self.link.pop("rx_peer_ip", None)
            self.link.pop("rx_peer_port", None)
        else:
            self.link["rx_peer_ip"], self.link["rx_peer_port"] = peer
        return peer

    @staticmethod
    def _tcp_server_peer(source):
        """Parse a TCP Server client key ('ip:port') or broadcast sentinel.

        Returns ``(ip, port)``, ``"__all__"``, or None if unparseable.
        """
        if source == "__all__":
            return "__all__"
        try:
            text = str(source or "").strip()
            if ":" not in text:
                return None
            host, _, port_s = text.rpartition(":")
            port = int(port_s)
            if not 1 <= port <= 65535:
                return None
            ip = str(ipaddress.IPv4Address(host.strip().strip("[]")))
            return ip, port
        except (TypeError, ValueError):
            return None

    def _note_tcp_server_peer(self, peer):
        """Remember a directed TCP Server client; drop stale single-peer header."""
        if peer is None or peer == "__all__":
            return peer
        if not isinstance(self.link, dict):
            return peer
        peers = self.link.setdefault("peers", [])
        item = [peer[0], int(peer[1])]
        if not any(
                isinstance(p, (list, tuple)) and len(p) == 2
                and str(p[0]) == item[0] and int(p[1]) == item[1]
                for p in peers):
            peers.append(item)
        unique = []
        for p in peers:
            parsed = (self._tcp_server_peer("%s:%s" % (p[0], p[1]))
                      if isinstance(p, (list, tuple)) and len(p) == 2
                      else None)
            if parsed not in (None, "__all__") and parsed not in unique:
                unique.append(parsed)
        if len(unique) > 1:
            self._tcp_server_multiple_peers = True
            self.link.pop("remote_ip", None)
            self.link.pop("remote_port", None)
            return peer
        previous = None
        try:
            if (self.link.get("remote_ip")
                    and self.link.get("remote_port") not in (None, "")):
                previous = (
                    str(ipaddress.IPv4Address(str(self.link.get("remote_ip")))),
                    int(self.link.get("remote_port")))
        except (TypeError, ValueError):
            previous = None
        if previous is None:
            self.link["remote_ip"], self.link["remote_port"] = peer
        elif previous != peer:
            self._tcp_server_multiple_peers = True
            self.link.pop("remote_ip", None)
            self.link.pop("remote_port", None)
        return peer

    def on_rx(self, data, t=None, source=None):
        pcap_peer = None
        if self.recording and isinstance(self.link, dict):
            proto = self.link.get("proto")
            if proto == "UDP" and not self._same_udp_peer(self.link, source):
                # A fixed TX destination does not filter inbound UDP. Once another
                # peer contributes bytes, the 3-field recorder events no longer
                # contain enough provenance for a truthful single-peer PCAP.
                # source=None is also untrusted: without peer provenance the
                # exported PCAP could falsely attribute RX bytes to the fixed peer.
                self.link = None
            elif proto == "TCP Server":
                parsed = self._tcp_server_peer(source)
                if parsed is None or parsed == "__all__":
                    # RX without a client key cannot be mapped to a 4-tuple.
                    self.link = None
                else:
                    pcap_peer = self._note_tcp_server_peer(parsed)
            elif proto == "UDP Multicast":
                pcap_peer = self._note_multicast_rx_peer(source)
                if pcap_peer is None:
                    # A multicast RX frame without a sender cannot be represented
                    # truthfully in PCAP; keep the recording but disable export.
                    self.link = None
        self._add("rx", data, t, pcap_peer=pcap_peer)

    def on_tx(self, data, t=None, source=None, peers=None):
        pcap_peer = None
        if self.recording and isinstance(self.link, dict):
            if self.link.get("proto") == "TCP Server":
                parsed = self._tcp_server_peer(source)
                if parsed == "__all__":
                    recipients = []
                    for key in peers or ():
                        extra = self._tcp_server_peer(key)
                        if extra not in (None, "__all__"):
                            self._note_tcp_server_peer(extra)
                            if extra not in recipients:
                                recipients.append(extra)
                    # Persist who was connected at send time so PCAP export
                    # does not invent TX frames for clients that appear later.
                    pcap_peer = recipients if recipients else "__all__"
                elif parsed is not None:
                    pcap_peer = self._note_tcp_server_peer(parsed)
                # source=None keeps header remote (legacy single-peer TX).
        self._add("tx", data, t, pcap_peer=pcap_peer)

    # ---------------- 存盘 / 载入 ----------------
    def save(self, path, note="", link=None):
        header = {"_": _MAGIC, "v": _VERSION, "note": str(note or ""),
                  "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        if self._wall_t0 is not None:
            header["wall_t0"] = float(self._wall_t0)
        link_obj = link if link is not None else self.link
        if isinstance(link_obj, dict) and link_obj:
            # Keep a compact, JSON-friendly snapshot for offline PCAP export.
            clean = {}
            for key in ("proto", "local_ip", "local_port",
                        "remote_ip", "remote_port",
                        "rx_peer_ip", "rx_peer_port", "peers"):
                if key in link_obj and link_obj[key] not in (None, ""):
                    if key == "peers" and not link_obj[key]:
                        continue
                    clean[key] = link_obj[key]
            if clean:
                header["link"] = clean
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(header, ensure_ascii=False) + "\n")
            peers = getattr(self.events, "pcap_peers", ()) or ()
            for i, (t, d, b) in enumerate(self.events):
                event = {"t": round(t, 4), "d": d, "b": _hex(b)}
                peer = peers[i] if i < len(peers) else None
                if peer is not None:
                    event["p"] = peer
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
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
    events, header, bad = _RecordedEvents(), {}, 0
    header_found = False
    with io.open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                bad += 1
                continue
            if not header_found:
                # Keep scanning until _MAGIC; a corrupt first content line must
                # not permanently disable header detection.
                if isinstance(obj, dict) and obj.get("_") == _MAGIC:
                    version = obj.get("v")
                    if type(version) is not int or version != _VERSION:
                        raise RecordError("不支持的录制文件版本：%s" % obj.get("v"))
                    header = obj
                    header_found = True
                else:
                    bad += 1
                continue
            try:
                t = float(obj["t"])
                d = obj["d"]
                b = _unhex(obj["b"])
                peer = obj.get("p") if "p" in obj else None
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
            events.pcap_peers.append(peer)
    if not header:
        raise RecordError("不是有效的录制文件（缺文件头）")
    # 手改后时间戳可能乱序，回放前排好；端点旁路须随事件一起排序。
    ordered = sorted(zip(events, events.pcap_peers), key=lambda item: item[0][0])
    events[:] = [event for event, _peer in ordered]
    events.pcap_peers[:] = [peer for _event, peer in ordered]
    header["bad_lines"] = bad
    return events, header


class Player:
    """回放器：按原始时序派发事件。

    mode=\"inject\"（默认）：把 RX（可选含 TX）交给 inject，仅适合虚拟连接注入。
    mode=\"drive_tx\"：只回放 TX，交给 send_tx 经真实/虚拟连接发出原始字节。

    调用方每隔一小段调 tick(now)，本类返回这段时间内到期的事件。这样定时精度、
    暂停/停止都由调用方（QTimer）控制，本类保持纯逻辑、可单测。
    """

    # drive_tx: pause after this many consecutive send failures
    _DRIVE_TX_FAIL_PAUSE = 3

    def __init__(self, events, inject, speed=1.0, include_tx=False, loop=False,
                 mode="inject", send_tx=None):
        self.mode = "drive_tx" if str(mode or "").strip() == "drive_tx" else "inject"
        if self.mode == "drive_tx":
            self.events = [e for e in events if e[1] == "tx"]
            self.inject = None
            self.send_tx = send_tx
        else:
            self.events = [e for e in events if include_tx or e[1] == "rx"]
            self.inject = inject
            self.send_tx = None
        self.speed = max(0.01, float(speed))
        self.loop = bool(loop)
        self.idx = 0
        self.started_at = None
        self.finished = False
        self.loops_done = 0
        self.paused = False
        self._pause_elapsed = 0.0
        self.send_fail_count = 0
        self.send_ok_count = 0
        self._consec_fail = 0
        self.send_aborted = False

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
        self.send_fail_count = 0
        self.send_ok_count = 0
        self._consec_fail = 0
        self.send_aborted = False

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
            if self.mode == "drive_tx":
                # Allow retry after user resumes; consecutive streak resets.
                self._consec_fail = 0
                self.send_aborted = False

    def _emit_one(self):
        if self.idx >= len(self.events):
            return 0
        _t, _d, b = self.events[self.idx]
        self.idx += 1
        try:
            if self.mode == "drive_tx":
                if self.send_tx is None:
                    raise RuntimeError("drive_tx mode requires send_tx callback")
                n = self.send_tx(b)
                # None = success for callbacks that don't return a count (tests).
                # Must deliver the full payload; partial / SEND_NO_TARGET / 0 → fail.
                if n is not None:
                    sent = int(n)
                    if sent < len(b):
                        raise RuntimeError(
                            "send failed/partial: %r of %d" % (sent, len(b)))
                self.send_ok_count += 1
                self._consec_fail = 0
            else:
                self.inject(b)
        except Exception:
            _log.debug("rec_replay emit failed (mode=%s)", self.mode, exc_info=True)
            if self.mode == "drive_tx":
                self.send_fail_count += 1
                self._consec_fail += 1
                if self._consec_fail >= self._DRIVE_TX_FAIL_PAUSE:
                    self.paused = True
                    self.send_aborted = True
        if self.idx >= len(self.events):
            self.loops_done += 1
            if self.loop and not self.paused:
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
            # Stop the same tick immediately after a drive_tx abort (or finish).
            if self.paused or self.finished:
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
