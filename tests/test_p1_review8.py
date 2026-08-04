import os
import random
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import modbus_master as mm
import modbus_slave as ms
from main_window import CommTool, PortScannerThread
from modbus_master_dialog import ModbusMasterDialog


_APP = QApplication.instance() or QApplication([])


def _patch_window_runtime(monkeypatch, settings_path):
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(settings_path)))
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(
        CommTool, "_info_dlg",
        lambda self, title, body, is_error=False: None)


# --------------------------------------------------------- normalize stability
def test_fc23_invalid_write_addr_stays_invalid():
    """Re-normalizing must not turn a rejected rule into one that writes to the
    read address."""
    rec = {"func": 0x17, "addr": 10, "qty": "2", "write_addr": "", "wvals": "100",
           "unit": 1, "period": 1000}
    a = mm.normalize_poll(rec)
    assert a["write_addr"] is None
    for _ in range(3):
        a = mm.normalize_poll(a)
        assert a["write_addr"] is None
        assert a["rw"]["write_addr"] is None
    # 完全没配 write_addr 的旧配置仍沿用读地址。
    legacy = mm.normalize_poll({"func": 0x17, "addr": 10, "qty": 2,
                                "wvals": "100", "unit": 1, "period": 1000})
    assert legacy["write_addr"] == 10
    assert mm.normalize_poll(legacy)["write_addr"] == 10


def test_fc08_invalid_diag_sub_stays_invalid():
    """An invalid sub-function must not silently become 0 (loopback)."""
    a = mm.normalize_poll({"func": 8, "addr": 0, "unit": 1, "period": 1000,
                           "diag_sub": "q", "wval": 1})
    assert a["diag_sub"] is None
    for _ in range(3):
        a = mm.normalize_poll(a)
        assert a["diag_sub"] is None
    for absent in ({}, {"diag_sub": ""}):
        rec = dict({"func": 8, "addr": 0, "unit": 1, "period": 1000, "wval": 1}, **absent)
        assert mm.normalize_poll(rec)["diag_sub"] == 0
    keep = mm.normalize_poll({"func": 8, "addr": 0, "unit": 1, "period": 1000,
                              "diag_sub": 0x0A, "wval": 1})
    assert keep["diag_sub"] == 0x0A
    assert mm.normalize_poll(keep)["diag_sub"] == 0x0A


# ------------------------------------------------------------- address spans
def test_span_guard_matches_builder():
    """Every rule the span guard passes must be buildable, and vice versa."""
    cases = [
        ({"func": 3, "addr": 0xFFF0, "qty": 16}, False),
        ({"func": 3, "addr": 0xFFF0, "qty": 17}, True),
        ({"func": 2, "addr": 0xFFFF, "qty": 2}, True),
        ({"func": 0x10, "addr": 0xFFFE, "wvals": "1 2"}, False),
        ({"func": 0x10, "addr": 0xFFFE, "wvals": "1 2 3"}, True),
        ({"func": 0x17, "addr": 0xFFFF, "qty": 2, "wvals": "1",
          "write_addr": 0}, True),
        ({"func": 0x17, "addr": 0, "qty": 2, "wvals": "1 2",
          "write_addr": 0xFFFF}, True),
        ({"func": 0x17, "addr": 0, "qty": 2, "wvals": "1 2",
          "write_addr": 0xFFFE}, False),
        ({"func": 6, "addr": 0xFFFF, "wval": 1}, False),
    ]
    for raw, expect_bad in cases:
        rule = mm.normalize_poll(dict(raw, unit=1, period=1000))
        assert CommTool._mbm_span_bad(rule) is expect_bad, raw
        if rule["func"] in mm.READ_FUNCS:
            arg = rule["qty"]
        elif rule["func"] in mm.WRITE_MULTI:
            arg = rule["wvals"]
        elif rule["func"] == 0x17:
            arg = rule["rw"]
        else:
            arg = rule["wval"]
        try:
            mm.build_rtu_request(rule["unit"], rule["func"], rule["addr"], arg)
        except ValueError:
            built = False
        else:
            built = True
        # 守卫判坏 == 构帧失败，两边不能有分歧
        assert built is (not expect_bad), raw


def test_span_bad_rule_reports_badparam(tmp_path, monkeypatch):
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("mbm-span-guard-test")
    try:
        window._mbm_rules = [{"enabled": True, "name": "over", "unit": 1,
                              "func": 3, "addr": 0xFFF0, "qty": 17,
                              "period": 1000}]
        window._mbm_results = {}
        window._mbm_due = {0: 0.0}
        window._mbm_poll(0)
        assert window._mbm_results[0]["status"] == "err"
        assert window._mbm_results[0]["text"] == window._t("mbm_st_badparam")
        assert window._mbm_inflight is None
    finally:
        window.deleteLater()
        _APP.processEvents()


# ---------------------------------------------------------- dialog round-trip
def test_dialog_keeps_diag_sub(tmp_path, monkeypatch):
    """The dialog has no sub-function widget, so it must carry the value through
    instead of resetting it to 0 on apply."""
    _patch_window_runtime(monkeypatch, tmp_path / "settings.ini")
    window = CommTool("mbm-diag-sub-test")
    try:
        window._mbm_rules = [{
            "enabled": True, "name": "diag", "unit": 1, "func": 0x08,
            "addr": 0, "period": 1000, "wval": 0x1234, "diag_sub": 0x0A,
        }]
        dlg = ModbusMasterDialog(window)
        try:
            rule = mm.normalize_poll(dlg._collect()[0])
            assert rule["diag_sub"] == 0x0A
            assert rule["diag_data"] == 0x1234
        finally:
            dlg.deleteLater()
    finally:
        window.deleteLater()
        _APP.processEvents()


# ------------------------------------------------------------------- fuzzing
def test_slave_survives_random_frames():
    """No exception other than ModbusException may escape the slave."""
    rng = random.Random(20260804)
    slave = ms.ModbusSlave(
        addr=1, holding={i: i for i in range(32)}, coils={i: i % 2 for i in range(32)},
        input_regs={i: i for i in range(32)}, discrete={i: 1 for i in range(32)},
        server_id=b"CommTool",
        dynamics=[{"space": "holding", "addr": 3, "mode": "inc",
                   "min": 0, "max": 500, "period_ms": 10}],
        exception_policy={"enabled": True, "code": 4, "mode": "n", "n": 3,
                          "funcs": [3, 0x17], "addrs": []},
    )
    funcs = [1, 2, 3, 4, 5, 6, 8, 0x0B, 0x0F, 0x10, 0x11, 0x17, 0x2B, 0x63]
    for _ in range(1500):
        body = bytes([rng.choice((0, 1, 2, 247)), rng.choice(funcs)])
        body += bytes(rng.randrange(256) for _ in range(rng.randrange(0, 30)))
        frame = body + bytes(ms.crc16(body)) if rng.random() < 0.7 else body
        try:
            slave.handle(frame)
        except ms.ModbusException:
            pass
        frames, _rest = ms.iter_frames(frame)
        for fr in frames:
            try:
                slave.handle(fr)
            except ms.ModbusException:
                pass


def test_normalize_poll_idempotent_and_buildable():
    """normalize(normalize(x)) == normalize(x), and anything the poller's guards
    accept must actually build on the wire."""
    rng = random.Random(4321)
    pools = {
        "func": [1, 2, 3, 4, 5, 6, 8, 0x0B, 0x0F, 0x10, 0x11, 0x17, 99, "3", None],
        "unit": [0, 1, 247, 248, -1, "1", "0x0A", None, "abc"],
        "addr": [0, 5, 0xFFF0, 0xFFFF, 0x10000, -1, "0x10", None, ""],
        "qty": [0, 1, 17, 125, 126, 2000, "7", None, "x"],
        "period": [0, 20, 1000, -5, "500", None],
        "wval": [0, 1, 0xFFFF, 0x10000, "0x20", None, ""],
        "wvals": [[], [1, 2], "1,2,3", "1 x 3", None, list(range(200))],
        "write_addr": [None, 0, 10, 0xFFFF, 0x10000, "0x0A", "zz", ""],
        "diag_sub": [None, 0, 1, "0x00", "q", ""],
        "diag_data": [None, 0, 0x1234, "0xFFFF", "q"],
    }
    for _ in range(1200):
        rec = {k: rng.choice(v) for k, v in pools.items()}
        a = mm.normalize_poll(rec)
        assert mm.normalize_poll(a) == a, rec

        guards_ok = (a["unit"] is not None and a["addr"] is not None
                     and a["period"] is not None and 0 <= a["unit"] <= 247
                     and not CommTool._mbm_span_bad(a))
        if a["func"] in mm.READ_FUNCS + (0x17,) and a["qty"] is None:
            guards_ok = False
        if a["func"] == 0x17 and a.get("write_addr") is None:
            guards_ok = False
        if a["func"] == 0x08 and (a["diag_sub"] is None or a["diag_data"] is None):
            guards_ok = False
        if a["func"] in mm.WRITE_SINGLE and a["wval"] is None:
            guards_ok = False
        if a["func"] in mm.WRITE_MULTI and not a["wvals"]:
            guards_ok = False
        if a["func"] == 0x17 and not (a.get("rw") or {}).get("write_vals"):
            guards_ok = False
        if a["func"] not in (mm.READ_FUNCS + mm.WRITE_SINGLE + mm.WRITE_MULTI
                             + (0x08, 0x0B, 0x11, 0x17)):
            guards_ok = False
        if not guards_ok:
            continue

        if a["func"] in mm.READ_FUNCS:
            arg = a["qty"]
        elif a["func"] in mm.WRITE_MULTI:
            arg = a["wvals"]
        elif a["func"] == 0x08:
            arg = (a["diag_sub"], a["diag_data"])
        elif a["func"] in (0x0B, 0x11):
            arg = 0
        elif a["func"] == 0x17:
            arg = a["rw"]
        else:
            arg = a["wval"]
        for build in (mm.build_rtu_request, mm.build_ascii_request):
            build(a["unit"], a["func"], a["addr"], arg)


def test_all_function_codes_roundtrip_on_every_variant():
    """Master -> slave -> master for each supported code on RTU / ASCII / TCP."""
    cases = [
        (1, 0, 5, lambda r: len(r["bits"]) >= 5),
        (2, 0, 5, lambda r: len(r["bits"]) >= 5),
        (3, 0, 4, lambda r: r["regs"] == [0, 1, 2, 3]),
        (4, 0, 4, lambda r: r["regs"] == [0, 1, 2, 3]),
        (5, 2, 1, lambda r: r["echo"] == (2, 0xFF00)),
        (6, 2, 0x1234, lambda r: r["echo"] == (2, 0x1234)),
        (8, 0, (0, 0xBEEF), lambda r: r["diag"] == (0, 0xBEEF)),
        (0x0B, 0, 0, lambda r: "event_count" in r),
        (0x0F, 0, [1, 0, 1], lambda r: r["echo"] == (0, 3)),
        (0x10, 0, [7, 8], lambda r: r["echo"] == (0, 2)),
        (0x11, 0, 0, lambda r: r["server_id"].startswith(b"CommTool")),
        (0x17, 0, {"read_addr": 0, "read_qty": 2, "write_addr": 6,
                   "write_vals": [11, 12]}, lambda r: r["regs"] == [0, 1]),
    ]

    def fresh():
        return ms.ModbusSlave(
            addr=7, holding={i: i for i in range(16)},
            input_regs={i: i for i in range(16)},
            coils={i: 1 for i in range(16)}, discrete={i: 1 for i in range(16)},
            server_id=b"CommTool")

    for func, addr, arg, check in cases:
        qty = arg if isinstance(arg, int) else (
            arg.get("read_qty") if isinstance(arg, dict) else len(arg))

        resp = fresh().handle(mm.build_rtu_request(7, func, addr, arg))
        out = mm.take_rtu_response(resp, 7, func, qty)
        assert out is not None and out[1] == len(resp), hex(func)
        assert check(out[0]), (hex(func), out[0])

        aresp = fresh().handle_ascii(mm.build_ascii_request(7, func, addr, arg))
        out = mm.take_ascii_response(aresp, 7, func, qty)
        assert out is not None and out[1] == len(aresp), hex(func)
        assert check(out[0]), (hex(func), out[0])

        pdu = fresh().handle(mm.build_rtu_request(7, func, addr, arg))[1:-2]
        mbap = (0x1234).to_bytes(2, "big") + b"\x00\x00" \
            + (len(pdu) + 1).to_bytes(2, "big") + bytes([7])
        out = mm.take_tcp_response(mbap + pdu, 0x1234, func, 7)
        assert out is not None and out[1] == len(mbap) + len(pdu), hex(func)
        assert check(out[0]), (hex(func), out[0])


def test_parse_pdu_rejects_truncated_and_overlong_cleanly():
    """Malformed response PDUs must raise ValueError, never IndexError."""
    cases = [(1, 0, 5), (2, 0, 5), (3, 0, 4), (4, 0, 4), (5, 2, 1), (6, 2, 0x1234),
             (8, 0, (0, 0xBEEF)), (0x0B, 0, 0), (0x0F, 0, [1, 0, 1]),
             (0x10, 0, [7, 8]), (0x11, 0, 0),
             (0x17, 0, {"read_addr": 0, "read_qty": 2, "write_addr": 6,
                        "write_vals": [11, 12]})]
    for func, addr, arg in cases:
        slave = ms.ModbusSlave(
            addr=7, holding={i: i for i in range(16)},
            input_regs={i: i for i in range(16)},
            coils={i: 1 for i in range(16)}, discrete={i: 1 for i in range(16)},
            server_id=b"CommTool")
        full = slave.handle(mm.build_rtu_request(7, func, addr, arg))[1:-2]
        for cut in list(range(len(full))) + [None]:
            frag = full[:cut] if cut is not None else full + b"\x00" * 300
            try:
                mm.parse_pdu(func, frag)
            except (ValueError, ms.ModbusException):
                pass
def test_qty_tooltip_stays_wrapped():
    """mbm_qty_tip is plain text, and Qt only word-wraps tooltips it thinks are
    rich text -- so every locale has to bring its own line breaks."""
    import i18n

    for lang in ("zh", "en", "zh_tw"):
        tip = i18n.TR[lang]["mbm_qty_tip"]
        assert "\r" not in tip, "%s: tooltip carries a stray CR" % lang
        lines = tip.split("\n")
        assert len(lines) > 1, "%s: tooltip must be broken into lines" % lang
        worst = max(len(l) for l in lines)
        assert worst <= 90, "%s: longest line is %d chars: %r" % (lang, worst, tip)


def test_no_i18n_value_carries_a_carriage_return():
    """A CR inside a translation is invisible to a byte-level CRLF check, because
    it is written as the two-character escape, and it shows up as a stray glyph
    in Qt widgets."""
    import i18n

    offenders = []
    for lang, table in i18n.TR.items():
        for key, val in table.items():
            if isinstance(val, str) and "\r" in val:
                offenders.append("%s/%s" % (lang, key))
    assert not offenders, "values containing CR: %s" % ", ".join(sorted(offenders))
