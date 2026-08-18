# -*- coding: utf-8 -*-
"""Tooltip helpers: make Qt word-wrap long plain-text tips.

Qt only auto-wraps tooltips it treats as rich text. A long plain Chinese tip
renders as one ultra-wide line. Wrap every tip we set so wrapping works without
hand-editing every locale string.
"""
from __future__ import print_function

from html import escape


def tip_html(text):
    """Turn plain tip text into rich HTML Qt will wrap."""
    if text is None:
        return ""
    s = str(text)
    if not s:
        return ""
    # Already marked rich: leave alone (callers may pass pre-built HTML).
    low = s.lstrip().lower()
    if low.startswith("<html") or low.startswith("<!doctype"):
        return s
    return "<html><body>%s</body></html>" % escape(s).replace("\n", "<br>")


def set_tooltip(widget, text):
    """Drop-in for widget.setToolTip that always enables wrapping."""
    if widget is None:
        return
    widget.setToolTip(tip_html(text) if text else "")
