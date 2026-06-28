# -*- coding: utf-8 -*-
"""D 位掩码/字段级匹配 —— 自动应答 HEX 匹配的解析与命中测试。

覆盖 CommTool._ar_parse_hex_pat / _ar_hex_at / _ar_hit_test：
  整字节精确 / 整字节通配(??·XX) / 半字节通配(A?·?5·X) / 位级掩码(b:+8位[01x]) /
  跨空格 HEX 拼接(向后兼容 `A B`=0xAB) / 旧语法优先(零回归) / 坏格式 / 三种匹配模式。

匹配引擎依赖 GUI 模块(PyQt5/pyserial)。仅当这些 GUI 依赖缺失时整类跳过——真实代码
错误(语法/名称/其它缺模块)会照常抛出使测试失败，不被误判为“缺依赖”。完整运行用项目 venv：
    .venv/bin/python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from main_window import CommTool
    _IMPORT_ERR = None
except ModuleNotFoundError as e:            # 仅 GUI 依赖缺失才跳过；其余照常抛出
    if (e.name or "").split(".")[0] in {"serial", "PyQt5"}:
        CommTool = None
        _IMPORT_ERR = e
    else:
        raise


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class ParseHexPatTests(unittest.TestCase):
    P = staticmethod(CommTool._ar_parse_hex_pat) if CommTool else None

    def test_exact_byte(self):
        self.assertEqual(self.P("AB"), [(0xAB, 0xFF)])
        self.assertEqual(self.P("ab"), [(0xAB, 0xFF)])        # 大小写不敏感
        self.assertEqual(self.P("0B"), [(0x0B, 0xFF)])        # 0B 单字节仍是 hex 0x0B

    def test_byte_wildcard(self):
        self.assertEqual(self.P("??"), [(0x00, 0x00)])
        self.assertEqual(self.P("XX"), [(0x00, 0x00)])
        self.assertEqual(self.P("xx"), [(0x00, 0x00)])

    def test_nibble_wildcard(self):
        self.assertEqual(self.P("A?"), [(0xA0, 0xF0)])        # 高半字节固定
        self.assertEqual(self.P("?5"), [(0x05, 0x0F)])        # 低半字节固定
        self.assertEqual(self.P("X5"), [(0x05, 0x0F)])        # X 同 ?
        self.assertEqual(self.P("5X"), [(0x50, 0xF0)])

    def test_bit_mask(self):
        self.assertEqual(self.P("b:1xxxxxx1"), [(0x81, 0x81)])  # 仅看最高+最低位
        self.assertEqual(self.P("b:00000000"), [(0x00, 0xFF)])  # 全 0 = 精确 0x00
        self.assertEqual(self.P("b:11111111"), [(0xFF, 0xFF)])  # 全 1 = 精确 0xFF
        self.assertEqual(self.P("b:xxxxxxxx"), [(0x00, 0x00)])  # 全 x = 整字节通配
        self.assertEqual(self.P("B:1001XXXX"), [(0x90, 0xF0)])  # 大写 + 高半字节
        self.assertEqual(self.P("b:xxxxxxx1"), [(0x01, 0x01)])  # 仅最低位=1（字段级常用）

    def test_multiple_bit_masks_are_unambiguous(self):
        self.assertEqual(self.P("b:10000000 b:00000000"),
                         [(0x80, 0xFF), (0x00, 0xFF)])
        self.assertEqual(self.P("b:1xx00001 b:xx000000"),
                         [(0x81, 0x9F), (0x00, 0x3F)])

    def test_legacy_syntax_takes_precedence(self):
        # 只要整串能被旧解析器接受，必须保留原字节语义。
        self.assertEqual(self.P("0B01010101"),
                         [(0x0B, 0xFF), (0x01, 0xFF), (0x01, 0xFF), (0x01, 0xFF), (0x01, 0xFF)])
        self.assertEqual(self.P("0BXXXXXXXX"),
                         [(0x0B, 0xFF), (0x00, 0x00), (0x00, 0x00), (0x00, 0x00), (0x00, 0x00)])
        self.assertEqual(self.P("A b10000000"),
                         [(0xAB, 0xFF), (0x10, 0xFF), (0x00, 0xFF), (0x00, 0xFF), (0x00, 0xFF)])
        self.assertEqual(self.P("1 b00000000"),
                         [(0x1B, 0xFF), (0x00, 0xFF), (0x00, 0xFF), (0x00, 0xFF), (0x00, 0xFF)])
        self.assertEqual(self.P("b10000000 A"),
                         [(0xB1, 0xFF), (0x00, 0xFF), (0x00, 0xFF), (0x00, 0xFF), (0x0A, 0xFF)])

    def test_mixed_tokens(self):
        self.assertEqual(
            self.P("AA b:1001xxxx ?5"),
            [(0xAA, 0xFF), (0x90, 0xF0), (0x05, 0x0F)],
        )

    def test_cross_space_hex_backcompat(self):
        # 空格仅作分隔：`A B` 仍拼成 0xAB（与旧行为一致）
        self.assertEqual(self.P("A B"), [(0xAB, 0xFF)])
        self.assertEqual(self.P("54 ?? 03"),
                         [(0x54, 0xFF), (0x00, 0x00), (0x03, 0xFF)])
        self.assertEqual(self.P("AABBCC"),
                         [(0xAA, 0xFF), (0xBB, 0xFF), (0xCC, 0xFF)])

    def test_bad_formats_return_none(self):
        self.assertIsNone(self.P(""))            # 空
        self.assertIsNone(self.P("   "))         # 全空白
        self.assertIsNone(self.P("ZZ"))          # 非法 hex 字符
        self.assertIsNone(self.P("AAB"))         # 奇数 nibble
        self.assertIsNone(self.P("b:1001"))      # b: 后不足 8 位
        self.assertIsNone(self.P("b:1002xxxx"))  # b: 后含非 0/1/x


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class HexAtTests(unittest.TestCase):
    P = staticmethod(CommTool._ar_parse_hex_pat) if CommTool else None
    A = staticmethod(CommTool._ar_hex_at) if CommTool else None

    def test_bitmask_hit_miss(self):
        pat = self.P("b:1xxxxxx1")               # 最高位=1 且 最低位=1
        self.assertTrue(self.A(pat, bytes([0x81]), 0))
        self.assertTrue(self.A(pat, bytes([0xFF]), 0))
        self.assertTrue(self.A(pat, bytes([0x83]), 0))
        self.assertFalse(self.A(pat, bytes([0x01]), 0))  # 最高位=0
        self.assertFalse(self.A(pat, bytes([0x80]), 0))  # 最低位=0

    def test_exact_and_wildcard(self):
        self.assertTrue(self.A(self.P("AB"), bytes([0xAB]), 0))
        self.assertFalse(self.A(self.P("AB"), bytes([0xAC]), 0))
        self.assertTrue(self.A(self.P("??"), bytes([0x00]), 0))
        self.assertTrue(self.A(self.P("??"), bytes([0xFF]), 0))

    def test_offset_and_bounds(self):
        pat = self.P("?5")
        self.assertTrue(self.A(pat, bytes([0x00, 0x35]), 1))
        self.assertFalse(self.A(pat, bytes([0x00, 0x36]), 1))
        self.assertFalse(self.A(pat, bytes([0x35]), 1))   # 越界
        self.assertFalse(self.A(pat, bytes([0x35]), -1))  # 负偏移


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class HitTestModesTests(unittest.TestCase):
    def _hit(self, match, data, mode):
        rule = {"match": match, "match_hex": True, "mode": mode}
        inst = CommTool.__new__(CommTool)     # 不跑 __init__、不需 QApplication
        return CommTool._ar_hit_test(inst, rule, data, "")

    def test_contains(self):
        self.assertTrue(self._hit("?5", bytes([0x00, 0x35, 0x99]), 0))   # 滑窗命中
        self.assertFalse(self._hit("?5", bytes([0x31, 0x32]), 0))

    def test_equals(self):
        self.assertTrue(self._hit("b:1xxxxxx1", bytes([0xC1]), 1))       # 单字节相等
        self.assertFalse(self._hit("AA BB", bytes([0xAA, 0xBB, 0xCC]), 1))  # 长度不等

    def test_prefix(self):
        self.assertTrue(self._hit("AA ?5", bytes([0xAA, 0x15, 0x77]), 2))
        self.assertFalse(self._hit("AA ?5", bytes([0xAB, 0x15]), 2))

    def test_field_level_bit_at_offset(self):
        # 「第 3 字节 bit0 须为 1」= 通配填充到偏移 + 前缀模式
        self.assertTrue(self._hit("?? ?? ?? b:xxxxxxx1", bytes([0, 0, 0, 0x01]), 2))
        self.assertFalse(self._hit("?? ?? ?? b:xxxxxxx1", bytes([0, 0, 0, 0x00]), 2))

    def test_backcompat_exact(self):
        # 老规则零行为变化
        self.assertTrue(self._hit("54 ?? 03", bytes([0x54, 0x99, 0x03]), 0))
        self.assertFalse(self._hit("54 ?? 03", bytes([0x55, 0x99, 0x03]), 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
