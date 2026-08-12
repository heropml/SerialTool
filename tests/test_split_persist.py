# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from split_persist import load_split_sizes, save_split_sizes, sync_splitter_group


class _FakeSettings(object):
    def __init__(self, data=None):
        self.data = dict(data or {})

    def value(self, key, default=""):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value


class _FakeSplit(object):
    def __init__(self, sizes, boom=False):
        self._sizes = list(sizes)
        self.boom = boom
        self.set_calls = []

    def sizes(self):
        if self.boom:
            raise RuntimeError("deleted")
        return list(self._sizes)

    def setSizes(self, sizes):
        if self.boom:
            raise RuntimeError("deleted")
        self._sizes = list(sizes)
        self.set_calls.append(list(sizes))


def test_load_split_sizes_ok_and_rejects():
    s = _FakeSettings({"k": "10,20,30"})
    assert load_split_sizes(s, "k", 3) == [10, 20, 30]
    assert load_split_sizes(s, "k", 2) is None
    assert load_split_sizes(_FakeSettings({"k": "0,20"}), "k", 2) is None
    assert load_split_sizes(_FakeSettings({"k": "10,999"}), "k", 2, max_size=100) is None
    assert load_split_sizes(_FakeSettings({"k": "a,b"}), "k", 2) is None


def test_save_and_reload_roundtrip():
    s = _FakeSettings()
    save_split_sizes(s, "ms", [90, 460])
    assert s.data["ms"] == "90,460"
    assert load_split_sizes(s, "ms", 2) == [90, 460]


def test_sync_splitter_group_aligns_peers_and_persists():
    src = _FakeSplit([100, 200])
    peer = _FakeSplit([50, 50])
    busy = {"v": False}
    saved = []

    out = sync_splitter_group(
        src, [peer],
        get_busy=lambda: busy["v"],
        set_busy=lambda v: busy.__setitem__("v", v),
        on_sizes=saved.append,
        expected_len=2,
    )
    assert out == [100, 200]
    assert peer.set_calls == [[100, 200]]
    assert saved == [[100, 200]]
    assert busy["v"] is False


def test_sync_splitter_group_guards_runtime_and_busy():
    src = _FakeSplit([1, 2], boom=True)
    assert sync_splitter_group(
        src, [],
        get_busy=lambda: False,
        set_busy=lambda _v: None,
        guard_runtime=True,
    ) is None

    busy = {"v": True}
    src2 = _FakeSplit([3, 4])
    assert sync_splitter_group(
        src2, [],
        get_busy=lambda: busy["v"],
        set_busy=lambda v: busy.__setitem__("v", v),
    ) is None


def test_load_max_size_inclusive_boundary():
    s = _FakeSettings({"k": "10,100"})
    assert load_split_sizes(s, "k", 2, max_size=100) == [10, 100]
    assert load_split_sizes(s, "k", 2, max_size=99) is None


def test_sync_expected_len_mismatch_skips():
    src = _FakeSplit([1, 2, 3])
    peer = _FakeSplit([9, 9])
    out = sync_splitter_group(
        src, [peer],
        get_busy=lambda: False,
        set_busy=lambda _v: None,
        expected_len=2,
    )
    assert out is None
    assert peer.set_calls == []


def test_sync_runtime_error_propagates_without_guard():
    src = _FakeSplit([1, 2], boom=True)
    try:
        sync_splitter_group(
            src, [],
            get_busy=lambda: False,
            set_busy=lambda _v: None,
            guard_runtime=False,
        )
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_sync_peer_runtime_error_propagates_without_guard():
    src = _FakeSplit([10, 20])
    peer = _FakeSplit([1, 1], boom=True)
    try:
        sync_splitter_group(
            src, [peer],
            get_busy=lambda: False,
            set_busy=lambda _v: None,
            guard_runtime=False,
        )
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
