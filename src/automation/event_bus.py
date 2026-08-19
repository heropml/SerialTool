# -*- coding: utf-8 -*-
"""In-process pub/sub for CommTool (Qt-free).

Trigger matching publishes ``trigger.hit``; webhook / run_cmd subscribe as
consumers so new external actions do not keep growing inside the GUI.
Handlers run synchronously on the publisher's thread. A failing handler is
logged and does not abort the rest.
"""
import logging

_log = logging.getLogger("commtool.event_bus")

TOPIC_TRIGGER_HIT = "trigger.hit"


class EventBus:
    def __init__(self):
        self._subs = {}

    def subscribe(self, topic, fn):
        if not callable(fn):
            return
        bucket = self._subs.setdefault(topic, [])
        if fn not in bucket:
            bucket.append(fn)

    def unsubscribe(self, topic, fn):
        bucket = self._subs.get(topic)
        if not bucket:
            return
        try:
            bucket.remove(fn)
        except ValueError:
            pass
        if not bucket:
            self._subs.pop(topic, None)

    def publish(self, topic, payload=None):
        for fn in list(self._subs.get(topic) or ()):
            try:
                fn(payload)
            except Exception:
                _log.debug("handler for %s failed", topic, exc_info=True)

    def clear(self):
        self._subs.clear()
