# -*- coding: utf-8 -*-
"""触发告警单测：匹配语义 / 冷却 / 计数 / 收发范围 / 坏配置容错。"""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import triggers as tg  # noqa: E402


def rule(**kw):
    return tg.normalize(kw)


class NormalizeTests(unittest.TestCase):
    def test_defaults(self):
        r = tg.normalize({})
        self.assertEqual((r["mode"], r["scope"], r["hex"]), (tg.MODE_CONTAINS, "rx", False))
        self.assertTrue(r["on"] and r["beep"] and r["notify"])
        self.assertEqual(r["cooldown"], tg.DEFAULT_COOLDOWN_MS)

    def test_bad_types_are_safe(self):
        r = tg.normalize({"mode": "x", "scope": "sideways", "cooldown": "abc", "on": "false"})
        self.assertEqual(r["mode"], tg.MODE_CONTAINS)
        self.assertEqual(r["scope"], "rx")
        self.assertEqual(r["cooldown"], tg.DEFAULT_COOLDOWN_MS)
        self.assertFalse(r["on"])            # 字符串 "false" 必须识别成停用
        self.assertEqual(tg.normalize("not a dict")["pattern"], "")

    def test_regex_with_hex_falls_back(self):
        """正则是文本语义，HEX 模式下没意义 → 退回包含，而不是留个跑不通的组合。"""
        r = rule(hex=True, mode=tg.MODE_REGEX, pattern="AA")
        self.assertEqual(r["mode"], tg.MODE_CONTAINS)

    def test_limits(self):
        r = rule(name="n" * 500, pattern="p" * 5000, cooldown=10 ** 9)
        self.assertLessEqual(len(r["name"]), tg.MAX_NAME)
        self.assertLessEqual(len(r["pattern"]), tg.MAX_PATTERN)
        self.assertLessEqual(r["cooldown"], 3600000)
        self.assertEqual(len(tg.sanitize_list([{}] * (tg.MAX_RULES + 50))), tg.MAX_RULES)
        self.assertEqual(tg.sanitize_list("nope"), [])


class MatchTests(unittest.TestCase):
    def test_text_modes(self):
        data, text = b"ERROR: boom", "ERROR: boom"
        self.assertTrue(tg.match(rule(pattern="ERROR"), data, text))
        self.assertFalse(tg.match(rule(pattern="WARN"), data, text))
        self.assertTrue(tg.match(rule(pattern="ERROR: boom", mode=tg.MODE_EQUALS), data, text))
        self.assertFalse(tg.match(rule(pattern="ERROR", mode=tg.MODE_EQUALS), data, text))
        self.assertTrue(tg.match(rule(pattern="ERR", mode=tg.MODE_PREFIX), data, text))
        self.assertFalse(tg.match(rule(pattern="boom", mode=tg.MODE_PREFIX), data, text))

    def test_regex(self):
        r = rule(pattern=r"E \(\d+\)", mode=tg.MODE_REGEX)
        self.assertTrue(tg.match(r, b"", "E (1234) app: x"))
        self.assertFalse(tg.match(r, b"", "I (1234) app: x"))

    def test_bad_regex_never_raises(self):
        """写错的正则不能把收包路径打断，只是这条规则不生效。"""
        r = rule(pattern="([unclosed", mode=tg.MODE_REGEX)
        self.assertFalse(tg.match(r, b"", "anything"))

    def test_catastrophic_regex_is_rejected(self):
        """触发匹配跑在 GUI 线程，明显的嵌套量词不能有机会指数回溯卡死窗口。"""
        self.assertIsNone(tg.compile_regex(r"(a+)+$"))
        self.assertIsNone(tg.compile_regex(r"(\w+\s?)*$"))
        # 常用而有界的分组、分支、重复仍可用，防护不能把正常正则一刀切。
        self.assertIsNotNone(tg.compile_regex(r"^(ERROR|WARN)-\d{1,3}$"))
        self.assertIsNotNone(tg.compile_regex(r"^(ab){2,4}$"))

    def test_ambiguous_branch_in_a_bounded_repeat_is_rejected(self):
        """有界重复里的歧义分支同样指数级回溯。

        CPython 会把交替分支的公共前缀提出来，`(\\w|\\w\\w)` 变成「一个 \\w，
        后跟 空|\\w」——歧义就落在「分支带空选项」上。这类写法 hi-lo 很小、
        hi 也不超 100，光看单层上界看不出危险，但打 50 字符要跑十几秒。
        """
        for pat in (r"(\w|\w\w){10,15}$", r"(\w|\w\w){20,25}$",
                    r"(a|ab){12,16}c", r"((a|ab){5,8}){5,8}c", r"(\d?){5,12}$"):
            self.assertIsNone(tg.compile_regex(pat), pat)

    def test_mutually_exclusive_branches_stay_usable(self):
        """首字符互斥的分支没有歧义，别因为重复次数多就误伤。"""
        for pat in (r"(ERR|WARN|INFO){1,20}", r"(a|b|c){1,50}$",
                    r"(\d|[a-f]){1,30}$", r"(\w|\w\w){2,8}$"):
            compiled = tg.compile_regex(pat)
            self.assertIsNotNone(compiled, pat)
            # 顺带确认放行的确实不慢（歧义那几条在这个输入上要秒级）
            t0 = time.perf_counter()
            compiled.search("a" * 60 + "!")
            self.assertLess(time.perf_counter() - t0, 0.05, pat)

    def test_hex_modes(self):
        data = bytes.fromhex("01 03 00 6B 00 03")
        self.assertTrue(tg.match(rule(pattern="03 00 6B", hex=True), data, ""))
        self.assertTrue(tg.match(rule(pattern="0x01,0x03", hex=True, mode=tg.MODE_PREFIX), data, ""))
        self.assertFalse(tg.match(rule(pattern="AA BB", hex=True), data, ""))
        self.assertTrue(tg.match(rule(pattern="0103006B0003", hex=True, mode=tg.MODE_EQUALS), data, ""))

    def test_bad_hex_pattern_inert(self):
        """HEX 串非法（奇数位/含非法字符）→ 规则不生效，绝不退化成「匹配一切」。"""
        for bad in ("ZZ", "010", "", "   "):
            self.assertFalse(tg.match(rule(pattern=bad, hex=True), b"\x01\x02", "x"))
        self.assertIsNone(tg.parse_hex_pattern("ZZ"))

    def test_empty_pattern_never_matches(self):
        self.assertFalse(tg.match(rule(pattern=""), b"data", "data"))

    def test_prefix_and_equals_ignore_framing_whitespace(self):
        """回归：日志行常带缩进与 \\r\\n，那是分帧不是内容 —— 相等与前缀都要先剥掉，
        否则用户写 ERROR 匹配不上 "  ERROR: x\\r\\n"。包含保持字面（不受首尾空白影响）。"""
        line = "  ERROR: boom\r\n"
        self.assertTrue(tg.match(rule(pattern="ERROR", mode=tg.MODE_PREFIX), b"", line))
        self.assertTrue(tg.match(rule(pattern="ERROR", mode=tg.MODE_CONTAINS), b"", line))
        self.assertTrue(tg.match(rule(pattern="ERROR", mode=tg.MODE_EQUALS), b"", "  ERROR \r\n"))
        # 前缀仍然是前缀：中间出现不算
        self.assertFalse(tg.match(rule(pattern="boom", mode=tg.MODE_PREFIX), b"", line))
        # 「包含」保持字面：带空格的模式仍能匹配到
        self.assertTrue(tg.match(rule(pattern=" ERROR", mode=tg.MODE_CONTAINS), b"", line))

    def test_scope(self):
        self.assertTrue(tg.scope_ok(rule(scope="rx"), "rx"))
        self.assertFalse(tg.scope_ok(rule(scope="rx"), "tx"))
        self.assertTrue(tg.scope_ok(rule(scope="both"), "tx"))


class EngineTests(unittest.TestCase):
    def test_fires_and_counts(self):
        eng = tg.TriggerEngine([rule(name="err", pattern="ERR", cooldown=0)])
        fired = eng.feed(b"ERR", "rx", "ERR", now=1.0)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0][1]["name"], "err")
        self.assertEqual(eng.hits(0), 1)
        eng.feed(b"ERR", "rx", "ERR", now=2.0)
        self.assertEqual(eng.hits(0), 2)
        self.assertEqual(eng.total_hits(), 2)

    def test_cooldown_suppresses_action_but_still_counts(self):
        """冷却只压制告警动作；命中次数照数，否则「命中多少次」会失真。"""
        eng = tg.TriggerEngine([rule(pattern="E", cooldown=1000)])
        self.assertEqual(len(eng.feed(b"E", "rx", "E", now=10.0)), 1)
        self.assertEqual(len(eng.feed(b"E", "rx", "E", now=10.5)), 0)   # 冷却中：不再告警
        self.assertEqual(eng.hits(0), 2)                                # 但仍计数
        self.assertEqual(len(eng.feed(b"E", "rx", "E", now=11.5)), 1)   # 过了冷却又告警

    def test_disabled_and_scope_filtered(self):
        eng = tg.TriggerEngine([rule(pattern="X", on=False, cooldown=0),
                                rule(pattern="X", scope="tx", cooldown=0)])
        self.assertEqual(eng.feed(b"X", "rx", "X", now=1.0), [])        # 停用 + 范围不符
        fired = eng.feed(b"X", "tx", "X", now=1.0)
        self.assertEqual([i for i, _ in fired], [1])

    def test_multiple_rules_all_fire(self):
        """一包可同时命中多条规则，互不吞没。"""
        eng = tg.TriggerEngine([rule(pattern="A", cooldown=0), rule(pattern="B", cooldown=0)])
        self.assertEqual(len(eng.feed(b"AB", "rx", "AB", now=1.0)), 2)

    def test_set_rules_resets_stats(self):
        eng = tg.TriggerEngine([rule(pattern="A", cooldown=0)])
        eng.feed(b"A", "rx", "A", now=1.0)
        eng.set_rules([rule(pattern="A", cooldown=0)])
        self.assertEqual(eng.hits(0), 0)

    def test_reset_stats(self):
        eng = tg.TriggerEngine([rule(pattern="A", cooldown=5000)])
        eng.feed(b"A", "rx", "A", now=1.0)
        eng.reset_stats()
        self.assertEqual(eng.hits(0), 0)
        self.assertEqual(len(eng.feed(b"A", "rx", "A", now=1.1)), 1)   # 冷却也一并清

    def test_bad_patterns_reported(self):
        eng = tg.TriggerEngine([rule(pattern="([x", mode=tg.MODE_REGEX),
                                rule(pattern="ZZ", hex=True),
                                rule(pattern="ok")])
        self.assertEqual(eng.bad_patterns(), [(0, "regex"), (1, "hex")])

    def test_needs_text_and_active(self):
        """全是 HEX 规则时不必为每包解码 —— 收包路径省一次 decode。"""
        eng = tg.TriggerEngine([rule(pattern="AA", hex=True)])
        self.assertTrue(eng.active())
        self.assertFalse(eng.needs_text())
        eng.set_rules([rule(pattern="AA", hex=True), rule(pattern="err")])
        self.assertTrue(eng.needs_text())
        eng.set_rules([rule(pattern="err", on=False)])
        self.assertFalse(eng.active())

    def test_stream_match_across_chunk_boundary(self):
        """回归：串口是字节流，关键字常被底层读操作劈成两半 —— 拼上一块的尾巴才不漏。"""
        eng = tg.TriggerEngine([rule(pattern="ERROR", cooldown=0)])
        # 模拟调用方：保留 lookback 长度的尾巴，new_*_at 指向本块起点
        keep = eng.lookback()
        self.assertEqual(keep, len("ERROR") - 1)
        tail = "ERR"[-keep:]
        fired = eng.feed(b"", "rx", tail + "OR: boom", now=1.0, new_text_at=len(tail))
        self.assertEqual(len(fired), 1)

    def test_stream_match_not_double_counted(self):
        """跨块回看不能把上一块已经命中过的内容再数一遍：只认结束于本块内的命中。"""
        eng = tg.TriggerEngine([rule(pattern="AB", cooldown=0)])
        self.assertEqual(len(eng.feed(b"", "rx", "AB", now=1.0, new_text_at=0)), 1)
        # 下一块把 "AB" 留在尾巴里，本块是 "C" —— 老命中不该再算
        self.assertEqual(len(eng.feed(b"", "rx", "ABC", now=2.0, new_text_at=2)), 0)
        self.assertEqual(eng.hits(0), 1)

    def test_stream_hex_across_boundary(self):
        eng = tg.TriggerEngine([rule(pattern="AA BB", hex=True, cooldown=0)])
        self.assertEqual(eng.lookback(), 1)
        fired = eng.feed(b"\xaa\xbb\x01", "rx", "", now=1.0, new_data_at=1)
        self.assertEqual(len(fired), 1)

    def test_equals_prefix_stay_per_chunk(self):
        """「相等 / 前缀」是「这一块是不是 X」的语义，跨块拼接会失真 → 只看本块。"""
        eng = tg.TriggerEngine([rule(pattern="OK", mode=tg.MODE_EQUALS, cooldown=0)])
        # 尾巴 "junk" + 本块 "OK"：相等应按本块判定，仍然命中
        self.assertEqual(len(eng.feed(b"", "rx", "junkOK", now=1.0, new_text_at=4)), 1)

    def test_lookback_bounded(self):
        eng = tg.TriggerEngine([rule(pattern="x" * 99999, cooldown=0)])
        self.assertLessEqual(eng.lookback(), tg.MAX_LOOKBACK)
        eng.set_rules([rule(pattern="a+", mode=tg.MODE_REGEX)])
        self.assertEqual(eng.lookback(), tg.REGEX_LOOKBACK)   # 正则长度不可知 → 固定窗口

    def test_cooldown_still_updates_last_time(self):
        """回归：冷却期内的命中同样是命中 —— 次数和「最后命中时间」都要更新，
        否则「最近一次什么时候」会停在很久以前，误导排查。"""
        eng = tg.TriggerEngine([rule(pattern="E", cooldown=60000)])
        eng.feed(b"E", "rx", "E", now=1.0, wall="10:00:00")
        eng.feed(b"E", "rx", "E", now=2.0, wall="10:00:01")   # 冷却中
        self.assertEqual(eng.hits(0), 2)
        self.assertEqual(eng.stats[0]["last_wall"], "10:00:01")

    def test_regex_compiled_once(self):
        """正则缓存：同一模式反复喂包不重复编译。"""
        eng = tg.TriggerEngine([rule(pattern=r"\d+", mode=tg.MODE_REGEX, cooldown=0)])
        for i in range(5):
            eng.feed(b"", "rx", "n=%d" % i, now=float(i))
        self.assertEqual(eng.hits(0), 5)
        self.assertIn(r"\d+", eng._regex_cache)


class ActionGateTests(unittest.TestCase):
    def test_min_hits_and_every_n(self):
        eng = tg.TriggerEngine([rule(pattern="ERR", min_hits=3, every_n=2, cooldown=0)])
        fired = []
        for _ in range(6):
            fired.append(eng.feed(b"ERR", text="ERR"))
        # hits 1,2 suppressed by min_hits; 3 odd skipped by every_n; 4 fire; 5 skip; 6 fire
        self.assertEqual([bool(x) for x in fired], [False, False, False, True, False, True])
        self.assertEqual(eng.hits(0), 6)

    def test_normalize_action_fields(self):
        r = tg.normalize({"webhook": True, "webhook_url": "https://x", "run_cmd_on": 1,
                          "run_cmd": "echo {name}", "min_hits": 0, "every_n": -3})
        self.assertTrue(r["webhook"] and r["run_cmd_on"])
        self.assertEqual(r["webhook_url"], "https://x")
        self.assertEqual(r["min_hits"], 1)
        self.assertEqual(r["every_n"], 1)


if __name__ == "__main__":
    unittest.main()
