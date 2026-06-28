# -*- coding: utf-8 -*-
"""B5 脚本化应答 —— ctx 校验工具 / 脚本执行 / 导入门禁 测试。

覆盖 CommTool._ar_crc（通用可定制 CRC）/ _ar_make_ctx / _ar_script_eval / _ar_gate_imported_scripts。
匹配引擎依赖 GUI 模块(PyQt5/pyserial)；缺则整类跳过（真实代码错误仍抛出）。完整运行：
    .venv/bin/python -m unittest discover -s tests
注意：测试只读不写真实 QSettings（不调 _commit；构造后把 .settings 重定向到临时文件兜底）。
"""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QSettings
    from main_window import CommTool
    _IMPORT_ERR = None
except ModuleNotFoundError as e:
    if (e.name or "").split(".")[0] in {"serial", "PyQt5"}:
        CommTool = None
        _IMPORT_ERR = e
    else:
        raise

_APP = None
_WIN = None


def _win():
    """共享一个 CommTool 实例；把它的 settings 重定向到临时文件，确保测试不写真实配置。"""
    global _APP, _WIN
    _APP = QApplication.instance() or QApplication([])
    if _WIN is None:
        _WIN = CommTool()
        import tempfile
        _WIN.settings = QSettings(tempfile.mktemp(suffix=".ini"), QSettings.IniFormat)
    return _WIN


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class CrcTests(unittest.TestCase):
    C = staticmethod(CommTool._ar_crc) if CommTool else None

    def test_standard_check_values(self):
        d = b"123456789"
        self.assertEqual(self.C(d, 16, 0x8005, 0xFFFF, refin=True, refout=True, byteorder="big"), b"\x4b\x37")  # MODBUS
        self.assertEqual(self.C(d, 16, 0x1021, 0x0000), b"\x31\xc3")                                            # XMODEM
        self.assertEqual(self.C(d, 16, 0x1021, 0xFFFF), b"\x29\xb1")                                            # CCITT-FALSE
        self.assertEqual(self.C(d, 8, 0x07, 0x00), b"\xf4")                                                     # CRC-8/SMBus
        self.assertEqual(self.C(d, 32, 0x04C11DB7, 0xFFFFFFFF, refin=True, refout=True,
                                xorout=0xFFFFFFFF, byteorder="big"), b"\xcb\xf4\x39\x26")                       # CRC-32

    def test_byteorder_and_width(self):
        be = self.C(b"\x01\x03", 16, 0x8005, 0xFFFF, refin=True, refout=True, byteorder="big")
        le = self.C(b"\x01\x03", 16, 0x8005, 0xFFFF, refin=True, refout=True, byteorder="little")
        self.assertEqual(le, be[::-1])
        self.assertEqual(len(self.C(b"x", 8, 0x07)), 1)
        self.assertEqual(len(self.C(b"x", 32, 0x04C11DB7)), 4)


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class ScriptEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = _win()

    def ev(self, script, frame=b"\xAA\x11\x22\x33"):
        return self.w._ar_script_eval({"script": script}, frame)

    def test_return_bytes(self):
        self.assertEqual(self.ev("def reply(f,c):\n return bytes([6])+f[1:3]"), (["06 11 22"], None))

    def test_return_str_utf8(self):
        self.assertEqual(self.ev("def reply(f,c):\n return 'AB'"), (["41 42"], None))

    def test_return_list_multiframe(self):
        self.assertEqual(self.ev("def reply(f,c):\n return [b'\\x06', b'\\x15']"), (["06", "15"], None))

    def test_return_none(self):
        self.assertEqual(self.ev("def reply(f,c):\n return None"), (None, None))

    def test_empty_bytes_means_no_reply(self):
        self.assertEqual(self.ev("def reply(f,c):\n return b''"), (None, None))

    def test_ctx_crc_builds_modbus_response(self):
        parts, err = self.ev("def reply(f,c):\n d=b'\\x01\\x03\\x02\\x00\\x0A'\n return d + c.crc16(d)")
        self.assertIsNone(err)
        self.assertEqual(parts, ["01 03 02 00 0A 38 43"])   # crc16(Modbus,小端) of 01 03 02 00 0A

    def test_runtime_error_caught(self):
        parts, err = self.ev("def reply(f,c):\n return 1/0")
        self.assertIsNone(parts)
        self.assertIn("ZeroDivisionError", err)

    def test_syntax_error_caught(self):
        parts, err = self.ev("def reply(f,c)\n return b''")
        self.assertIsNone(parts)
        self.assertIn("SyntaxError", err)

    def test_missing_reply_func(self):
        parts, err = self.ev("x = 1")
        self.assertIsNone(parts)
        self.assertIn("reply", err)

    def test_bad_return_type(self):
        parts, err = self.ev("def reply(f,c):\n return 123")
        self.assertIsNone(parts)
        self.assertTrue(err)

    def test_script_on_flag_gates_engine(self):
        # script_on=True → 走脚本；False → 跳过脚本回退静态（此处静态空 → 不回）
        self.w._ar_rules = [{"match": "AA", "match_hex": True, "mode": 2, "on": True, "reply": "",
                             "script": "def reply(f,c):\n return b'\\x06'", "script_on": True}]
        self.assertEqual(self.w._ar_preview(b"\xAA").get("replies"), ["06"])
        self.w._ar_rules[0]["script_on"] = False
        self.assertEqual(self.w._ar_preview(b"\xAA").get("replies"), [])

    def test_seq_advances_each_call(self):
        # 评审#3：ctx.seq 每次调用自增（之前一直拿到同一值）
        self.w._ar_seq = 0
        a = self.w._ar_script_eval({"script": "def reply(f,c):\n return bytes([c.seq])"}, b"\x00")[0]
        b = self.w._ar_script_eval({"script": "def reply(f,c):\n return bytes([c.seq])"}, b"\x00")[0]
        self.assertEqual((a, b), (["01"], ["02"]))

    def test_preview_hits_matches_live(self):
        # 评审#3：预览 hits 比 live 少一次 → 现在 preview 下 +1 对齐
        self.assertEqual(self.w._ar_make_ctx({"_hits": 3}, preview=False).hits, 3)
        self.assertEqual(self.w._ar_make_ctx({"_hits": 3}, preview=True).hits, 4)

    def test_fresh_namespace_no_state_leak(self):
        # 评审#2：每次全新命名空间 → 模块级状态不跨调用累积（预览/测试不污染实发）
        sc = "g=[0]\ndef reply(f,c):\n g[0]+=1\n return bytes([g[0]])"
        a = self.w._ar_script_eval({"script": sc}, b"\x00")[0]
        b = self.w._ar_script_eval({"script": sc}, b"\x00")[0]
        self.assertEqual((a, b), (["01"], ["01"]))

    def test_timeout_kills_infinite_loop(self):
        # 评审#1：超时必须真正终止子进程，不能只是主调用返回。
        old = self.w._AR_SCRIPT_TIMEOUT
        self.w._AR_SCRIPT_TIMEOUT = 0.2
        try:
            parts, err = self.w._ar_script_eval({"script": "def reply(f,c):\n while True: pass"}, b"\x00")
        finally:
            self.w._AR_SCRIPT_TIMEOUT = old
        self.assertIsNone(parts)
        self.assertTrue(err)
        self.assertIsNone(self.w._ar_script_proc)
        self.assertIsNone(self.w._ar_script_conn)
        # 超时工作进程被杀后，下一帧应自动重建并恢复正常执行。
        parts, err = self.w._ar_script_eval({"script": "def reply(f,c): return b'\\x06'"}, b"\x00")
        self.assertEqual((parts, err), (["06"], None))
        self.assertTrue(self.w._ar_script_proc.is_alive())

    def test_preview_does_not_consume_seq(self):
        self.w._ar_seq = 10
        parts, err = self.w._ar_script_eval(
            {"script": "def reply(f,c):\n return bytes([c.seq])"}, b"\x00", preview=True)
        self.assertEqual((parts, err), (["0B"], None))
        self.assertEqual(self.w._ar_seq, 10)

    def test_non_string_script_no_crash(self):
        # 评审#3：script 字段非字符串 → str() 容错，不抛 AttributeError
        parts, err = self.w._ar_script_eval({"script": 123}, b"\x00")
        self.assertIsNone(parts)
        self.assertTrue(err)
        self.w._ar_rules = [{"match": "AA", "match_hex": True, "mode": 2, "on": True, "script": 123}]
        self.assertIsInstance(self.w._ar_preview(b"\xAA"), dict)   # 实时/预览路径也不崩

    def test_preview_worker_isolated_from_live(self):
        # 评审#2：预览与实发各用独立进程 → 预览不污染实发的 random/已导入模块等共享态
        self.w._ar_script_eval({"script": "def reply(f,c): return b'\\x01'"}, b"\x00", preview=False)
        self.w._ar_script_eval({"script": "def reply(f,c): return b'\\x01'"}, b"\x00", preview=True)
        self.assertNotEqual(self.w._ar_script_proc.pid, self.w._ar_preview_proc.pid)

    @unittest.skipIf(sys.platform == "win32", "POSIX setsid/pgid handshake")
    def test_worker_ready_means_private_process_group(self):
        self.w._ar_script_eval({"script": "def reply(f,c): return b'\\x01'"}, b"\x00")
        pid = self.w._ar_script_proc.pid
        self.assertEqual(os.getpgid(pid), pid)
        self.assertNotEqual(os.getpgid(pid), os.getpgrp())

    @unittest.skipIf(sys.platform == "win32", "posix killpg path; Windows 走 taskkill /T")
    def test_timeout_kills_spawned_subprocess(self):
        # 评审#1：超时杀整个进程组 → 脚本起的 subprocess 孙子进程也被回收，不 orphan
        import tempfile, time
        marker = tempfile.mktemp()
        sc = ("import subprocess, sys\n"
              "def reply(f, c):\n"
              "    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
              "    with open(%r, 'w') as fh: fh.write(str(p.pid))\n"
              "    while True: pass\n" % marker)
        old = self.w._AR_SCRIPT_TIMEOUT
        self.w._AR_SCRIPT_TIMEOUT = 0.3
        try:
            try:
                self.w._ar_script_eval({"script": sc}, b"\x00")
            finally:
                self.w._AR_SCRIPT_TIMEOUT = old
            time.sleep(0.5)
            with open(marker, encoding="utf-8") as f:
                cpid = int(f.read())
            try:
                os.kill(cpid, 0)
                alive = True
            except OSError:
                alive = False
            self.assertFalse(alive)
        finally:
            try:
                os.unlink(marker)
            except FileNotFoundError:
                pass

    @unittest.skipIf(sys.platform == "win32", "posix killpg path; Windows 走 taskkill /T")
    def test_crashed_worker_still_kills_spawned_subprocess(self):
        # worker 先退出后 is_alive() 已为 False，仍必须按 ready 握手记录的 PGID 回收孙进程。
        import signal, tempfile, time
        marker = tempfile.mktemp()
        child_pid = None
        sc = ("import os, subprocess, sys\n"
              "def reply(f, c):\n"
              "    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
              "    with open(%r, 'w') as fh: fh.write(str(p.pid))\n"
              "    os._exit(7)\n" % marker)
        try:
            parts, err = self.w._ar_script_eval({"script": sc}, b"\x00")
            self.assertIsNone(parts)
            self.assertTrue(err)
            with open(marker, encoding="utf-8") as f:
                child_pid = int(f.read())
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    os.kill(child_pid, 0)
                except OSError:
                    break
                time.sleep(0.05)
            else:
                self.fail("worker 崩溃后子进程未被回收")
        finally:
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except OSError:
                    pass
            try:
                os.unlink(marker)
            except FileNotFoundError:
                pass

    @classmethod
    def tearDownClass(cls):
        cls.w._ar_stop_script_worker()

    def test_ctx_helpers(self):
        ctx = self.w._ar_make_ctx({"_hits": 5})
        self.assertEqual(ctx.crc8(b"123456789"), b"\xf4")
        self.assertEqual(ctx.sum8(bytes([0x10, 0x20, 0x30])), bytes([0x60]))
        self.assertEqual(ctx.xor8(bytes([0x0F, 0xF0])), bytes([0xFF]))
        self.assertEqual(ctx.hexbytes("AA BB,0xCC"), b"\xaa\xbb\xcc")
        self.assertEqual(ctx.tohex(b"\xaa\xbb"), "AA BB")
        self.assertEqual(ctx.hits, 5)


@unittest.skipIf(CommTool is None, "GUI deps unavailable: %s" % (_IMPORT_ERR,))
class ImportGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = _win()

    @staticmethod
    def _cfg():
        import json
        return {"autoreply_rules": json.dumps(
            [{"match": "AA", "script": "def reply(f,c):\n return b'\\x99'"},
             {"match": "BB"}], ensure_ascii=False)}

    def test_trust_keeps_scripts(self):
        self.w._ar_confirm = lambda *a: True
        out = self.w._ar_gate_imported_scripts(self._cfg())
        self.assertIn("reply", out["autoreply_rules"])

    def test_decline_strips_scripts_but_keeps_rules(self):
        import json
        self.w._ar_confirm = lambda *a: False
        out = self.w._ar_gate_imported_scripts(self._cfg())
        rules = json.loads(out["autoreply_rules"])
        self.assertEqual(len(rules), 2)
        self.assertTrue(all(not (r.get("script") or "") for r in rules))

    def test_no_script_no_prompt(self):
        import json
        called = {"n": 0}
        self.w._ar_confirm = lambda *a: called.__setitem__("n", 1) or True
        self.w._ar_gate_imported_scripts({"autoreply_rules": json.dumps([{"match": "AA"}])})
        self.assertEqual(called["n"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
