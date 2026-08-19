# -*- coding: utf-8 -*-
"""In-process event bus + trigger-action consumer (Qt-free)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.event_bus import EventBus, TOPIC_TRIGGER_HIT
from automation.trigger_actions import TriggerActionRunner


def test_event_bus_delivers_to_subscribers():
    bus = EventBus()
    seen = []
    bus.subscribe(TOPIC_TRIGGER_HIT, lambda p: seen.append(p))
    payload = {"hits": 3}
    bus.publish(TOPIC_TRIGGER_HIT, payload)
    assert seen == [payload]


def test_event_bus_isolates_handler_errors():
    bus = EventBus()
    seen = []

    def boom(_payload):
        raise RuntimeError("handler boom")

    bus.subscribe(TOPIC_TRIGGER_HIT, boom)
    bus.subscribe(TOPIC_TRIGGER_HIT, lambda p: seen.append(p.get("name")))
    bus.publish(TOPIC_TRIGGER_HIT, {"name": "ok"})
    assert seen == ["ok"]


def test_event_bus_unsubscribe_and_duplicate_subscribe():
    bus = EventBus()
    seen = []

    def fn(p):
        seen.append(p)

    bus.subscribe("x", fn)
    bus.subscribe("x", fn)
    bus.publish("x", 1)
    assert seen == [1]
    bus.unsubscribe("x", fn)
    bus.publish("x", 2)
    assert seen == [1]


def test_runner_posts_webhook_on_trigger_hit(monkeypatch):
    seen = []

    class _Resp(object):
        def read(self, _n):
            return b"ok"

    def fake_urlopen(req, timeout=5):
        seen.append((req.full_url, req.get_method(), timeout))
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    runner = TriggerActionRunner()
    runner.spawn = lambda worker: (worker(), True)[1]
    runner.on_trigger_hit({
        "rule": {
            "webhook": True,
            "webhook_url": "https://example.com/hook",
            "pattern": "ERROR",
        },
        "name": "n",
        "direction": "rx",
        "hits": 2,
    })
    assert seen == [("https://example.com/hook", "POST", 5)]


def test_runner_skips_private_webhook(monkeypatch):
    called = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: called.append(True))
    runner = TriggerActionRunner()
    runner.spawn = lambda worker: (worker(), True)[1]
    runner.on_trigger_hit({
        "rule": {"webhook": True, "webhook_url": "http://127.0.0.1/hook"},
        "name": "n",
        "direction": "rx",
        "hits": 1,
    })
    assert called == []


def test_runner_run_cmd_uses_spawn():
    runner = TriggerActionRunner()
    spawned = []
    runner.spawn = lambda worker: spawned.append(True) or True
    runner.on_trigger_hit({
        "rule": {"run_cmd_on": True, "run_cmd": "echo x"},
        "name": "n",
        "direction": "rx",
        "hits": 1,
    })
    assert spawned == [True]
