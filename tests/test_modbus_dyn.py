import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from modbus import modbus_dyn  # noqa: E402


class DynamicEngineTests(unittest.TestCase):
    def test_inc_and_sine(self):
        eng = modbus_dyn.DynamicEngine([
            {"space": "holding", "addr": 0, "mode": "inc",
             "step": 1, "min": 0, "max": 10, "period_ms": 1000},
            {"space": "holding", "addr": 1, "mode": "sine",
             "min": 0, "max": 100, "period_ms": 1000},
        ], now=0.0)
        self.assertEqual(eng.value("holding", 0, now=0.0), 0)
        self.assertEqual(eng.value("holding", 0, now=3.0), 3)
        # 正弦在 min/max 中点起步，1/4 周期到顶，3/4 周期触底：
        # 只断言落在 [0,100] 内的话，sine 模式被整个移除也能过。
        self.assertEqual(eng.value("holding", 1, now=0.0), 50)
        self.assertEqual(eng.value("holding", 1, now=0.25), 100)
        self.assertEqual(eng.value("holding", 1, now=0.75), 0)

    def test_exception_once(self):
        inj = modbus_dyn.ExceptionInjector(
            {"enabled": True, "code": 4, "mode": "once", "funcs": [3]})
        self.assertEqual(inj.should_raise(3, 0), 4)
        self.assertIsNone(inj.should_raise(3, 0))


class ReviewFixTests(unittest.TestCase):
    """Follow-ups from the v1.3.7 review."""

    def test_clamp_u16_clamps_instead_of_wrapping(self):
        # A hand-written min:-5 used to wrap to 65531 and silently invert the range.
        self.assertEqual(modbus_dyn._clamp_u16(-5), 0)
        self.assertEqual(modbus_dyn._clamp_u16(0x1FFFF), 0xFFFF)
        self.assertEqual(modbus_dyn._clamp_u16("nope"), 0)
        rule = modbus_dyn.normalize_dynamic(
            {"space": "holding", "addr": 0, "mode": "inc", "min": -5, "max": 10})
        self.assertEqual((rule["min"], rule["max"]), (0, 10))

    def test_static_rule_honours_its_value(self):
        # {"mode":"static","value":1234} used to read back as the static table value.
        eng = modbus_dyn.DynamicEngine([
            {"space": "holding", "addr": 0, "mode": "static", "value": 1234},
            {"space": "coils", "addr": 1, "mode": "static", "value": 1},
        ], now=0.0)
        self.assertEqual(eng.value("holding", 0, fallback=7, now=0.0), 1234)
        self.assertIs(eng.value("coils", 1, fallback=False, now=0.0), True)

    def test_static_rule_without_value_still_falls_back(self):
        eng = modbus_dyn.DynamicEngine(
            [{"space": "holding", "addr": 0, "mode": "static"}], now=0.0)
        self.assertEqual(eng.value("holding", 0, fallback=7, now=0.0), 7)
        # An unknown mode degrades to static, so it must not shadow the table either.
        eng2 = modbus_dyn.DynamicEngine(
            [{"space": "holding", "addr": 0, "mode": "bogus"}], now=0.0)
        self.assertEqual(eng2.value("holding", 0, fallback=9, now=0.0), 9)

    def test_static_value_survives_normalize(self):
        self.assertIsNone(modbus_dyn.normalize_dynamic({"mode": "static"})["value"])
        self.assertIsNone(modbus_dyn.normalize_dynamic(
            {"mode": "static", "value": ""})["value"])
        self.assertEqual(modbus_dyn.normalize_dynamic(
            {"mode": "static", "value": 1234})["value"], 1234)

    def test_slave_addr_is_clamped_not_masked(self):
        from modbus import modbus_slave
        # addr:300 used to be masked to 44, answering as a completely different slave.
        self.assertEqual(modbus_slave.ModbusSlave(addr=300).addr, 0xFF)
        self.assertEqual(modbus_slave.ModbusSlave(addr=-1).addr, 0)
        self.assertEqual(modbus_slave.ModbusSlave(addr=17).addr, 17)

if __name__ == "__main__":
    unittest.main()
