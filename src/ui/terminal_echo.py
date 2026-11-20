"""Editable terminal echo and reconciliation of the next device echo."""
from collections import deque
import math
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QTextCursor


class TerminalEcho:
    def __init__(self, parent):
        self.input_start = None
        self.preview = None
        self.expected = deque()
        self.buffered = ""
        self.timer = QTimer(parent)
        self.timer.setSingleShot(True)

    def begin(self, doc):
        if self.input_start is None:
            self.input_start = QTextCursor(doc)
            self.input_start.movePosition(QTextCursor.End)
            self.input_start.setKeepPositionOnInsert(True)

    def received_part(self, line):
        """Return the echoed prefix and whether that line already has a newline."""
        if self.input_start is None:
            return "", False
        cur = QTextCursor(self.input_start)
        cur.clearSelection()  # Qt keeps the position pinned, but moves the anchor on insert.
        block = cur.block()
        if block.position() + block.length() - 1 - cur.position() > 2 * len(line):
            return "", False
        cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        tail = cur.selectedText()
        if block != cur.document().lastBlock():
            return (line, True) if tail == line else ("", False)
        return (tail, False) if line.startswith(tail) else ("", False)

    def hide_preview(self):
        if self.preview is None:
            return
        cur, length, text = self.preview
        self.preview = None
        end = cur.position() + length
        if end < cur.document().characterCount():
            cur.clearSelection()
            cur.setPosition(end, QTextCursor.KeepAnchor)
            if cur.selectedText() == text:
                cur.removeSelectedText()

    def show_preview(self, doc, line):
        self.hide_preview()
        prefix, _ = self.received_part(line)
        suffix = line[len(prefix):]
        if suffix:
            start = QTextCursor(doc)
            start.movePosition(QTextCursor.End)
            start.setKeepPositionOnInsert(True)
            writer = QTextCursor(start)
            writer.setKeepPositionOnInsert(False)
            writer.insertText(suffix)
            self.preview = (start, writer.position() - start.position(), suffix)

    def expect(self, suffix):
        self.expected.append((suffix, time.monotonic() + 1.5))
        if len(self.expected) == 1:
            self._schedule_timeout()

    def _schedule_timeout(self):
        if self.expected:
            self.timer.start(max(1, math.ceil((self.expected[0][1] - time.monotonic()) * 1000)))
        else:
            self.timer.stop()

    def expire(self):
        text = ""
        now = time.monotonic()
        while self.expected and self.expected[0][1] <= now:
            suffix, _ = self.expected.popleft()
            if self.buffered != suffix + "\r":
                text += self.buffered
            self.buffered = ""
        self._schedule_timeout()
        return text

    def receive(self, text):
        """Match a submitted line only when its terminator arrives. Return other RX intact."""
        if not self.expected or not text:
            return text
        expired = self.expire()
        text = self.buffered + text
        self.buffered = ""
        while self.expected and text:
            suffix = self.expected[0][0]
            if suffix.startswith(text) or text == suffix + "\r":
                self.buffered = text
                return expired
            rest = text[len(suffix):]
            if not text.startswith(suffix) or not rest.startswith(("\r", "\n")):
                self.finish()
                return expired + text
            text = rest[2:] if rest.startswith("\r\n") else rest[1:]
            self.expected.popleft()
        self._schedule_timeout()
        return expired + text

    def finish(self):
        self.timer.stop()
        text = self.buffered
        if self.expected and text == self.expected[0][0] + "\r":
            text = ""
        self.buffered = ""
        self.expected.clear()
        return text
