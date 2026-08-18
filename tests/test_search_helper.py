import re
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from protocol.search_helper import find_last_page, find_spans, parse_hex_term  # noqa: E402


class FindSpansTests(unittest.TestCase):
    def test_plain_substring_and_case(self):
        self.assertEqual(find_spans("Hello hello", "hel"), [(0, 3), (6, 9)])
        # 默认大小写不敏感；显式 case_sensitive=True 只匹配小写
        self.assertEqual(find_spans("Hello hello", "hel", case_sensitive=True), [(6, 9)])
        self.assertEqual(find_spans("abc", ""), [])
        # Unicode lower() may expand a codepoint; spans must still index the
        # original string so QTextCursor receives the correct position.
        self.assertEqual(find_spans("İx", "x"), [(1, 2)])
        self.assertEqual(find_spans("abc", "a", mode="unknown"), [])

    def test_regex_mode(self):
        self.assertEqual(find_spans("a1 b2 c3", r"[a-z]\d", mode="regex"),
                         [(0, 2), (3, 5), (6, 8)])
        # IGNORECASE 默认开：[a-z] 也匹配大写 A
        self.assertEqual(find_spans("A1 b2", r"[a-z]\d", mode="regex"),
                         [(0, 2), (3, 5)])
        self.assertEqual(find_spans("A1 b2", r"[a-z]\d", mode="regex", case_sensitive=True),
                         [(3, 5)])

    def test_regex_catastrophic_backtracking_rejected(self):
        self.assertEqual(find_spans("a" * 30, r"(a+)+$"), [])

    def test_regex_ignorecase_uses_guarded_compiler(self):
        from automation import triggers
        with mock.patch("automation.triggers.compile_regex",
                        wraps=triggers.compile_regex) as compile_regex:
            self.assertEqual(find_spans("A1", r"[a-z]\d", mode="regex"),
                             [(0, 2)])
        compile_regex.assert_called_once_with(r"[a-z]\d", re.IGNORECASE)

    def test_hex_mode_matches_spaced_or_compact(self):
        # 渲染文本 'AA BB CC DD' 里找 b'\xBB\xCC' → 'BB CC' 一段（跨空格）
        self.assertEqual(find_spans("AA BB CC DD", "BBCC", mode="hex"), [(3, 8)])
        self.assertEqual(find_spans("AABBCC", "BBCC", mode="hex"), [(2, 6)])
        # 字节间多空格也兼容（"AA  BB" 共 6 字符）
        self.assertEqual(find_spans("AA  BB  CC", "AABB", mode="hex"), [(0, 6)])

    def test_hex_invalid_term_returns_empty(self):
        self.assertIsNone(parse_hex_term("xyz"))
        self.assertEqual(find_spans("AA BB", "GG", mode="hex"), [])     # 非法字节
        self.assertEqual(find_spans("AA BB", "010", mode="hex"), [])    # 奇数位

    def test_hex_term_matches_trigger_sanitizer(self):
        """Align with triggers.parse_hex_pattern: per-byte 0x and newlines."""
        self.assertEqual(parse_hex_term("0x01,0x03"), b"\x01\x03")
        self.assertEqual(parse_hex_term("0x01 0x03"), b"\x01\x03")
        self.assertEqual(parse_hex_term("01\n03"), b"\x01\x03")
        self.assertEqual(find_spans("01 03 AA", "0x01,0x03", mode="hex"), [(0, 5)])

    def test_spans_are_non_overlapping_and_ordered(self):
        spans = find_spans("aaaa", "aa")
        self.assertEqual(spans, [(0, 2), (2, 4)])

    def test_hexdump_mode_skips_offset_and_ascii_columns(self):
        # hexdump 三列格式：偏移(8hex)+两空格 | hex列 | ASCII列。
        # 搜 '00' 会命中偏移列（00000000）和 ASCII 列，但 hex 模式 hexdump=True 必须只搜 hex 列。
        # 纯 hex 列 '11 22' / '33 44' 不含 00 → 全不命中。
        text = "00000000  11 22 |..|\n00000010  33 44 |..|"
        self.assertEqual(find_spans(text, "00", mode="hex", hexdump=True), [])

        # ASCII 列恰好是字面 '00'（两个 0x30 字节），hex 列是 30 30 → hex 模式不该命中
        self.assertEqual(find_spans("00000000  30 30 |00|", "00", mode="hex", hexdump=True), [])

        # 偏移列本身就是 00000000：非 hexdump 模式会命中，hexdump 模式排除
        self.assertEqual(find_spans("00000000  30 30 |..|", "000000", mode="hex"), [(0, 6)])
        self.assertEqual(find_spans("00000000  30 30 |..|", "000000", mode="hex", hexdump=True), [])

    def test_hexdump_mode_still_matches_hex_bytes(self):
        # 真字节仍命中，且 span 落在 hex 列（偏移列 10 字符之后）
        text = "00000000  00 01 |..|"
        spans = find_spans(text, "0001", mode="hex", hexdump=True)
        self.assertEqual(len(spans), 1)
        start, end = spans[0]
        self.assertGreaterEqual(start, 10)
        # 命中区间对应 '00 01'（含中间空格）
        self.assertEqual(text[start:end], "00 01")
        # 非 hexdump 模式对同文本行为不变（仍命中，但会连带偏移列）
        self.assertGreaterEqual(len(find_spans(text, "0001", mode="hex")), 1)

    def test_hexdump_mode_ignores_timestamp_lines(self):
        # 时间戳/箭头行不以 8hex+双空格 开头 → 自动跳过，不被 hex 搜索误命中
        text = "[2026/08/02 12:00:00.000] ← \n00000000  11 22 |..|"
        self.assertEqual(find_spans(text, "000000", mode="hex", hexdump=True), [])

    def test_hexdump_mode_with_crlf_endings(self):
        # CRLF 占两个码点；第二行 span 必须仍指向原文中的准确位置。
        text = "00000000  00 01 |..|\r\n00000010  02 03 |..|\r\n"
        spans = find_spans(text, "0001", mode="hex", hexdump=True)
        self.assertEqual(len(spans), 1)
        start, end = spans[0]
        self.assertEqual(text[start:end], "00 01")

        spans = find_spans(text, "0203", mode="hex", hexdump=True)
        self.assertEqual(len(spans), 1)
        start, end = spans[0]
        self.assertEqual(start, text.index("02 03"))
        self.assertEqual(text[start:end], "02 03")



    def test_find_spans_respects_start_and_limit(self):
        text = "aa aa aa aa"
        self.assertEqual(find_spans(text, "aa", limit=2), [(0, 2), (3, 5)])
        self.assertEqual(find_spans(text, "aa", limit=2, start=3), [(3, 5), (6, 8)])
        self.assertEqual(find_spans(text, "aa", limit=10, start=9), [(9, 11)])
        self.assertEqual(
            find_spans("a1 b2 c3", r"[a-z]\d", mode="regex", limit=1, start=2),
            [(3, 5)])
        self.assertEqual(
            find_spans("AA BB CC", "BB", mode="hex", limit=1, start=3),
            [(3, 5)])

    def test_find_last_page_scans_once_with_bounded_results(self):
        text = "aa " * 14
        spans, starts = find_last_page(text, "aa", page_size=5)
        self.assertEqual(starts, [0, 15, 30])
        self.assertEqual(spans, [(30, 32), (33, 35), (36, 38), (39, 41)])

        spans, starts = find_last_page("no hits", "aa", page_size=5)
        self.assertEqual(spans, [])
        self.assertEqual(starts, [0])

if __name__ == "__main__":
    unittest.main()
