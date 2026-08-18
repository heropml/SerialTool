# -*- coding: utf-8 -*-
"""Qt-free parse-quality counters for protocol-frame analysis.

Counts live on the Session. UI shows a one-line summary; no send actions.
"""


class ParseDiagnostics:
    """Per-session counters for stream framing + field extract."""

    __slots__ = (
        "rx_chunks", "complete_frames", "matched", "field_ok",
        "waiting", "header_skip", "bad_length", "oversize", "field_oob",
        "last_reason", "last_sample",
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.rx_chunks = 0
        self.complete_frames = 0
        self.matched = 0
        self.field_ok = 0
        self.waiting = 0
        self.header_skip = 0
        self.bad_length = 0
        self.oversize = 0
        self.field_oob = 0
        self.last_reason = ""
        self.last_sample = ""

    def note_chunk(self):
        self.rx_chunks += 1

    def note_assemble(self, n_frames, stats):
        stats = stats or {}
        self.complete_frames += int(n_frames or 0)
        self.waiting = int(stats.get("waiting", 0) or 0)
        self.header_skip += int(stats.get("header_skip", 0) or 0)
        self.bad_length += int(stats.get("bad_length", 0) or 0)
        self.oversize += int(stats.get("oversize", 0) or 0)
        reason = stats.get("last_reason") or ""
        if reason:
            self.last_reason = reason
            self.last_sample = stats.get("last_sample") or ""

    def note_parse(self, matched=False, field_ok=0, field_oob=0):
        if matched:
            self.matched += 1
        self.field_ok += int(field_ok or 0)
        oob = int(field_oob or 0)
        self.field_oob += oob
        if oob and not self.last_reason:
            self.last_reason = "field_oob"

    def snapshot(self):
        return {
            "chunks": self.rx_chunks,
            "frames": self.complete_frames,
            "matched": self.matched,
            "fields": self.field_ok,
            "waiting": self.waiting,
            "skip": self.header_skip,
            "bad_length": self.bad_length,
            "oversize": self.oversize,
            "oob": self.field_oob,
            "last_reason": self.last_reason,
            "last_sample": self.last_sample,
        }
