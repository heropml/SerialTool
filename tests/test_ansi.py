# -*- coding: utf-8 -*-
"""ANSI SGR 解析单测：着色 / 跨包续传 / 非 SGR 序列吞掉 / 调色板与主题解析。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ansi  # noqa: E402


def texts(runs):
    return [t for t, _ in runs]


class ParseTests(unittest.TestCase):
    def test_plain_text_untouched(self):
        """没有转义序列时原样返回，样式为默认。"""
        runs, st, pend = ansi.parse("hello world")
        self.assertEqual(runs, [("hello world", ansi.DEFAULT)])
        self.assertTrue(st.is_default())
        self.assertEqual(pend, "")

    def test_basic_color_splits_runs(self):
        """ESP-IDF 风格日志：颜色段与复位段分开着色，转义符本身不进文本。"""
        runs, st, _ = ansi.parse("\x1b[0;32mI (123) boot\x1b[0m done")
        self.assertEqual(texts(runs), ["I (123) boot", " done"])
        self.assertEqual(runs[0][1].fg, 2)          # 32 → 绿
        self.assertIsNone(runs[1][1].fg)            # 0 → 复位
        self.assertTrue(st.is_default())

    def test_bright_and_bg_and_default(self):
        runs, _, _ = ansi.parse("\x1b[91mA\x1b[44mB\x1b[39mC\x1b[49mD")
        self.assertEqual(texts(runs), ["A", "B", "C", "D"])
        self.assertEqual(runs[0][1].fg, 9)          # 91 → 亮红
        self.assertEqual((runs[1][1].fg, runs[1][1].bg), (9, 4))
        self.assertIsNone(runs[2][1].fg)            # 39 → 默认前景，背景保留
        self.assertEqual(runs[2][1].bg, 4)
        self.assertIsNone(runs[3][1].bg)            # 49 → 默认背景

    def test_attributes(self):
        runs, _, _ = ansi.parse("\x1b[1mB\x1b[4mU\x1b[22mN\x1b[24mP\x1b[7mR")
        st = dict(zip(texts(runs), [s for _, s in runs]))
        self.assertTrue(st["B"].bold)
        self.assertTrue(st["U"].bold and st["U"].underline)
        self.assertFalse(st["N"].bold)
        self.assertFalse(st["P"].underline)
        self.assertTrue(st["R"].reverse)

    def test_256_and_truecolor(self):
        runs, _, _ = ansi.parse("\x1b[38;5;196mA\x1b[38;2;10;20;30mB\x1b[38;5;9mC")
        self.assertEqual(runs[0][1].fg, (255, 0, 0))     # 196 = 色立方纯红
        self.assertEqual(runs[1][1].fg, (10, 20, 30))    # 真彩原样
        self.assertEqual(runs[2][1].fg, 9)               # 256 色的前 16 个仍走调色板
        gray, _, _ = ansi.parse("\x1b[38;5;232mX")
        self.assertEqual(gray[0][1].fg, (8, 8, 8))       # 灰阶起点

    def test_empty_params_is_reset(self):
        """ESC[m 等价 ESC[0m。"""
        runs, _, _ = ansi.parse("\x1b[31mA\x1b[mB")
        self.assertEqual(runs[0][1].fg, 1)
        self.assertIsNone(runs[1][1].fg)

    def test_non_sgr_csi_swallowed(self):
        """光标移动 / 擦除 / 定位等非 SGR 序列吃掉，不留乱码也不影响样式。"""
        runs, st, _ = ansi.parse("\x1b[2J\x1b[10;20HA\x1b[KB\x1b[?25lC")
        self.assertEqual("".join(texts(runs)), "ABC")
        self.assertTrue(st.is_default())

    def test_osc_and_other_escapes_swallowed(self):
        """OSC 设置标题（BEL 或 ESC\\ 终止）与 ESC+单字节序列都吃掉。"""
        runs, _, _ = ansi.parse("\x1b]0;title\x07A\x1b(BB")
        self.assertEqual("".join(texts(runs)), "AB")
        runs2, _, _ = ansi.parse("\x1b]0;t\x1b\\Z")
        self.assertEqual("".join(texts(runs2)), "Z")

    def test_control_chars_preserved(self):
        r"""\r \n \t 必须留给分行/分包逻辑，不能被当转义符吃掉。"""
        runs, _, _ = ansi.parse("\x1b[32ma\r\nb\tc")
        self.assertEqual("".join(texts(runs)), "a\r\nb\tc")

    def test_state_carries_across_packets(self):
        """颜色跨包延续：上一包设的绿色对下一包仍有效。"""
        runs1, st1, pend1 = ansi.parse("\x1b[32mfirst")
        runs2, st2, _ = ansi.parse("second", st1, pend1)
        self.assertEqual(runs2[0][1].fg, 2)
        self.assertEqual(st2.fg, 2)

    def test_split_escape_across_packets(self):
        """转义序列被切成两半：残片留到下一包拼回，不吐乱码。"""
        runs1, st1, pend1 = ansi.parse("A\x1b[3")
        self.assertEqual(texts(runs1), ["A"])
        self.assertEqual(pend1, "\x1b[3")
        runs2, st2, pend2 = ansi.parse("2mB", st1, pend1)
        self.assertEqual(texts(runs2), ["B"])
        self.assertEqual(runs2[0][1].fg, 2)
        self.assertEqual(pend2, "")

    def test_lone_esc_at_end(self):
        runs, _, pend = ansi.parse("A\x1b")
        self.assertEqual(texts(runs), ["A"])
        self.assertEqual(pend, "\x1b")

    def test_runaway_escape_bounded(self):
        """设备一直发参数不给终止字节：缓冲保持有界，后续参数也不能漏成正文。"""
        runs, st, pend = ansi.parse("\x1b[" + "1;" * 200)
        self.assertLessEqual(len(pend), ansi.MAX_PENDING)
        self.assertEqual(texts(runs), [])
        runs, st, pend = ansi.parse("1;2;3;4;", st, pend)
        self.assertEqual(texts(runs), [])
        runs, _, pend = ansi.parse("mVISIBLE", st, pend)
        self.assertEqual(texts(runs), ["VISIBLE"])
        self.assertEqual(pend, "")

    def test_runaway_osc_discards_until_bel_or_split_st(self):
        """超长 OSC 只丢控制串；终止后的正文恢复，跨包 ST 也能识别。"""
        runs, st, pend = ansi.parse("\x1b]0;" + "x" * 200)
        self.assertEqual(texts(runs), [])
        self.assertLessEqual(len(pend), ansi.MAX_PENDING)
        runs, st, pend = ansi.parse("more-title\x07VISIBLE", st, pend)
        self.assertEqual(texts(runs), ["VISIBLE"])
        self.assertEqual(pend, "")

        _, st, pend = ansi.parse("\x1b]8;;" + "x" * 200 + "\x1b")
        runs, _, pend = ansi.parse("\\LINK", st, pend)
        self.assertEqual(texts(runs), ["LINK"])
        self.assertEqual(pend, "")

    def test_adjacent_same_style_merged(self):
        """同样式相邻段合并，减少插入次数。"""
        runs, _, _ = ansi.parse("A\x1b[0mB")     # 复位到本来就是默认 → 应并成一段
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0][0], "AB")

    def test_malformed_params_ignored(self):
        """含非数字参数的私有序列整条忽略，不改样式也不崩。"""
        runs, st, _ = ansi.parse("\x1b[31m\x1b[>1mA")
        self.assertEqual(st.fg, 1)               # 私有序列没把红色冲掉
        self.assertEqual(texts(runs), ["A"])

    def test_strip(self):
        self.assertEqual(ansi.strip("\x1b[32mok\x1b[0m\r\n"), "ok\r\n")


class ColorResolveTests(unittest.TestCase):
    def test_palette_differs_by_theme(self):
        """同一序号在深/浅底取不同色：白在白底、黑在黑底都要可读。"""
        self.assertNotEqual(ansi.resolve(7, dark=True), ansi.resolve(7, dark=False))
        self.assertNotEqual(ansi.resolve(0, dark=True), ansi.resolve(0, dark=False))
        for i in range(16):
            for dark in (True, False):
                self.assertRegex(ansi.resolve(i, dark), r"^#[0-9A-F]{6}$")

    def test_truecolor_theme_independent(self):
        self.assertEqual(ansi.resolve((1, 2, 3), True), "#010203")
        self.assertEqual(ansi.resolve((1, 2, 3), False), "#010203")

    def test_none_is_default(self):
        self.assertIsNone(ansi.resolve(None))

    def test_spec_roundtrip(self):
        """存进 QTextCharFormat 的标识能还原成当前主题的颜色。"""
        self.assertEqual(ansi.color_of_spec(ansi.spec_of(2), dark=True),
                         ansi.resolve(2, dark=True))
        self.assertEqual(ansi.color_of_spec(ansi.spec_of(2), dark=False),
                         ansi.resolve(2, dark=False))
        self.assertEqual(ansi.color_of_spec(ansi.spec_of((9, 8, 7))), "#090807")
        self.assertIsNone(ansi.color_of_spec(""))
        self.assertIsNone(ansi.color_of_spec("garbage"))


if __name__ == "__main__":
    unittest.main()
