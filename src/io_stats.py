# -*- coding: utf-8 -*-
"""I/O statistics accumulator (Qt-free).

Tracks transport-level packets (OS read chunks / successful sends), not
protocol frames. Provides B/s, pps, size distribution, peaks, timeouts,
and a short throughput history ring for diagnostics.
"""
from __future__ import print_function

import time

# Packet size histogram bins (upper bounds, inclusive); last is open-ended.
SIZE_BINS = (16, 64, 256, 1024, 4096)  # + overflow
HISTORY_LEN = 180  # ~3 min at 1Hz


def _bin_index(n):
    for i, upper in enumerate(SIZE_BINS):
        if n <= upper:
            return i
    return len(SIZE_BINS)


class IoStatsAccumulator(object):
    def __init__(self, history_len=HISTORY_LEN):
        self.history_len = max(10, int(history_len))
        self.reset()

    def reset(self):
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.rx_packets = 0
        self.tx_packets = 0
        self.rx_errors = 0
        self.tx_errors = 0
        self.rx_rate = 0
        self.tx_rate = 0
        self.rx_pps = 0
        self.tx_pps = 0
        self.rx_peak = 0
        self.tx_peak = 0
        self.rx_peak_pps = 0
        self.tx_peak_pps = 0
        self._rx_bytes_mark = 0
        self._tx_bytes_mark = 0
        self._rx_pkts_mark = 0
        self._tx_pkts_mark = 0
        self._time_mark = time.monotonic()
        self.rx_size_min = None
        self.rx_size_max = 0
        self.rx_size_sum = 0
        self.tx_size_min = None
        self.tx_size_max = 0
        self.tx_size_sum = 0
        self.rx_hist = [0] * (len(SIZE_BINS) + 1)
        self.tx_hist = [0] * (len(SIZE_BINS) + 1)
        self.timeouts = {"seq": 0, "mbm": 0, "conn": 0}
        self.history = []  # [{t, rx_bps, tx_bps, rx_pps, tx_pps}, ...]

    def note_rx(self, n):
        n = int(n or 0)
        if n < 0:
            n = 0
        self.rx_bytes += n
        self.rx_packets += 1
        self._note_size("rx", n)

    def note_tx_bytes(self, n):
        """Add TX bytes without counting a packet (partial write)."""
        n = int(n or 0)
        if n > 0:
            self.tx_bytes += n

    def note_tx(self, n):
        n = int(n or 0)
        if n < 0:
            n = 0
        self.tx_bytes += n
        self.tx_packets += 1
        self._note_size("tx", n)

    def note_rx_error(self, count=1):
        self.rx_errors += max(0, int(count))

    def note_tx_error(self, count=1):
        self.tx_errors += max(0, int(count))

    def note_timeout(self, kind):
        kind = str(kind or "")
        if kind not in self.timeouts:
            self.timeouts[kind] = 0
        self.timeouts[kind] += 1

    def _note_size(self, direction, n):
        if direction == "rx":
            if self.rx_size_min is None or n < self.rx_size_min:
                self.rx_size_min = n
            if n > self.rx_size_max:
                self.rx_size_max = n
            self.rx_size_sum += n
            self.rx_hist[_bin_index(n)] += 1
        else:
            if self.tx_size_min is None or n < self.tx_size_min:
                self.tx_size_min = n
            if n > self.tx_size_max:
                self.tx_size_max = n
            self.tx_size_sum += n
            self.tx_hist[_bin_index(n)] += 1

    def avg_size(self, direction):
        if direction == "rx":
            if self.rx_packets <= 0:
                return 0.0
            return float(self.rx_size_sum) / float(self.rx_packets)
        if self.tx_packets <= 0:
            return 0.0
        return float(self.tx_size_sum) / float(self.tx_packets)

    def tick(self, now=None):
        """1Hz (or any) sample: update B/s, pps, peaks, history."""
        now = time.monotonic() if now is None else float(now)
        elapsed = max(0.001, now - self._time_mark)
        self.rx_rate = max(0, int((self.rx_bytes - self._rx_bytes_mark) / elapsed))
        self.tx_rate = max(0, int((self.tx_bytes - self._tx_bytes_mark) / elapsed))
        self.rx_pps = max(0, int((self.rx_packets - self._rx_pkts_mark) / elapsed))
        self.tx_pps = max(0, int((self.tx_packets - self._tx_pkts_mark) / elapsed))
        self._rx_bytes_mark = self.rx_bytes
        self._tx_bytes_mark = self.tx_bytes
        self._rx_pkts_mark = self.rx_packets
        self._tx_pkts_mark = self.tx_packets
        self._time_mark = now
        if self.rx_rate > self.rx_peak:
            self.rx_peak = self.rx_rate
        if self.tx_rate > self.tx_peak:
            self.tx_peak = self.tx_rate
        if self.rx_pps > self.rx_peak_pps:
            self.rx_peak_pps = self.rx_pps
        if self.tx_pps > self.tx_peak_pps:
            self.tx_peak_pps = self.tx_pps
        self.history.append({
            "t": now,
            "rx_bps": self.rx_rate,
            "tx_bps": self.tx_rate,
            "rx_pps": self.rx_pps,
            "tx_pps": self.tx_pps,
        })
        if len(self.history) > self.history_len:
            self.history = self.history[-self.history_len:]
        return {
            "rx_rate": self.rx_rate,
            "tx_rate": self.tx_rate,
            "rx_pps": self.rx_pps,
            "tx_pps": self.tx_pps,
        }

    def hist_label(self, direction):
        """Compact histogram: '<=16:a <=64:b ... >4096:z'."""
        hist = self.rx_hist if direction == "rx" else self.tx_hist
        parts = []
        for i, upper in enumerate(SIZE_BINS):
            parts.append("<=%d:%d" % (upper, hist[i]))
        parts.append(">%d:%d" % (SIZE_BINS[-1], hist[-1]))
        return " ".join(parts)

    def size_summary(self, direction):
        if direction == "rx":
            if self.rx_packets <= 0:
                return None, None, 0.0
            return self.rx_size_min, self.rx_size_max, self.avg_size("rx")
        if self.tx_packets <= 0:
            return None, None, 0.0
        return self.tx_size_min, self.tx_size_max, self.avg_size("tx")

    def timeout_total(self):
        return sum(int(v) for v in self.timeouts.values())

    def snapshot(self):
        return {
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "rx_packets": self.rx_packets,
            "tx_packets": self.tx_packets,
            "rx_errors": self.rx_errors,
            "tx_errors": self.tx_errors,
            "rx_rate": self.rx_rate,
            "tx_rate": self.tx_rate,
            "rx_pps": self.rx_pps,
            "tx_pps": self.tx_pps,
            "rx_peak": self.rx_peak,
            "tx_peak": self.tx_peak,
            "rx_peak_pps": self.rx_peak_pps,
            "tx_peak_pps": self.tx_peak_pps,
            "rx_size_min": self.rx_size_min,
            "rx_size_max": self.rx_size_max,
            "rx_size_avg": self.avg_size("rx"),
            "tx_size_min": self.tx_size_min,
            "tx_size_max": self.tx_size_max,
            "tx_size_avg": self.avg_size("tx"),
            "rx_hist": list(self.rx_hist),
            "tx_hist": list(self.tx_hist),
            "timeouts": dict(self.timeouts),
            "history_len": len(self.history),
        }
