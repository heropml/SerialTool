# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import io_stats as st


def test_note_and_size_stats():
    a = st.IoStatsAccumulator()
    a.note_rx(10)
    a.note_rx(100)
    a.note_tx(5)
    assert a.rx_bytes == 110
    assert a.rx_packets == 2
    assert a.tx_packets == 1
    assert a.rx_size_min == 10
    assert a.rx_size_max == 100
    assert abs(a.avg_size("rx") - 55.0) < 1e-6
    assert a.rx_hist[0] == 1   # <=16
    assert a.rx_hist[2] == 1   # <=256


def test_tick_rates_and_peaks():
    a = st.IoStatsAccumulator()
    t0 = 1000.0
    a._time_mark = t0
    a.note_rx(1000)
    a.note_rx(1000)
    a.tick(now=t0 + 1.0)
    assert a.rx_rate == 2000
    assert a.rx_pps == 2
    assert a.rx_peak == 2000
    assert a.rx_peak_pps == 2
    a.note_rx(5000)
    a.tick(now=t0 + 2.0)
    assert a.rx_rate == 5000
    assert a.rx_peak == 5000
    assert len(a.history) == 2


def test_reset_clears_all():
    a = st.IoStatsAccumulator()
    a.note_rx(20)
    a.note_tx(30)
    a.note_timeout("seq")
    a.note_rx_error()
    a.tick()
    a.reset()
    s = a.snapshot()
    assert s["rx_bytes"] == 0 and s["tx_packets"] == 0
    assert s["rx_peak"] == 0 and s["timeouts"]["seq"] == 0
    assert s["history_len"] == 0
    assert a.rx_size_min is None


def test_timeouts_independent():
    a = st.IoStatsAccumulator()
    a.note_timeout("seq")
    a.note_timeout("seq")
    a.note_timeout("mbm")
    a.note_timeout("conn")
    assert a.timeouts == {"seq": 2, "mbm": 1, "conn": 1}
    assert a.timeout_total() == 4


def test_hist_overflow_bin():
    a = st.IoStatsAccumulator()
    a.note_rx(10000)
    assert a.rx_hist[-1] == 1
    assert " >4096:1" in (" " + a.hist_label("rx"))


def test_note_tx_bytes_no_packet():
    a = st.IoStatsAccumulator()
    a.note_tx_bytes(7)
    assert a.tx_bytes == 7
    assert a.tx_packets == 0
    assert a.tx_size_min is None
