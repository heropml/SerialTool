# -*- coding: utf-8 -*-
"""静默 ``except Exception: pass`` 预算门禁（AST）。

口径与 ``scripts/count_exception_handling.py`` 一致：宽泛捕获体只有一句 ``pass``。
新增静默必须先改本文件白名单并写明理由；收掉静默则同步下调预算。
"""
from __future__ import print_function

import importlib.util
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
_SCRIPT = ROOT / "scripts" / "count_exception_handling.py"

# 故意保留的静默（窗口几何 / nativeEvent / DPI / AppUserModelID / shutdown 等）。
# 值 = 该文件允许的静默条数；总预算 = 各值之和。
ALLOWED_SILENT = {
    "dialogs.py": 1,       # Win 标题栏 SetWindowPos 失败可忽略
    "main.py": 2,          # AppUserModelID + HiDPI roundingPolicy（旧 Qt 无属性）
    "main_window.py": 5,   # 几何搬移 / 原生边框 / nativeEvent / 关机关对话框
    "session.py": 1,       # 默认会话名 i18n 回退
}


def _load_counter():
    spec = importlib.util.spec_from_file_location(
        "count_exception_handling", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _silent_by_file(mod):
    counts = Counter()
    sites = []
    for path in sorted(SRC.glob("*.py")):
        for lineno, _end in mod.iter_silent_handlers(path):
            counts[path.name] += 1
            sites.append("%s:%d" % (path.name, lineno))
    return counts, sites


def test_silent_except_budget_not_increased():
    mod = _load_counter()
    counts, sites = _silent_by_file(mod)
    actual = {name: n for name, n in counts.items() if n}
    allowed_total = sum(ALLOWED_SILENT.values())
    actual_total = sum(actual.values())

    extra_files = sorted(set(actual) - set(ALLOWED_SILENT))
    assert not extra_files, (
        "new silent except:pass in unexpected modules %s; sites=%s"
        % (extra_files, sites))

    over = {name: (actual.get(name, 0), ALLOWED_SILENT[name])
            for name in ALLOWED_SILENT
            if actual.get(name, 0) > ALLOWED_SILENT[name]}
    assert not over, (
        "silent except:pass budget exceeded %s; all sites=%s"
        % (over, sites))

    # Exact freeze: fixing a silent requires lowering ALLOWED_SILENT in this file
    # (deliberate workflow — see module docstring). Do not weaken to "<=".
    under = {name: (actual.get(name, 0), ALLOWED_SILENT[name])
             for name in ALLOWED_SILENT
             if actual.get(name, 0) != ALLOWED_SILENT[name]}
    assert not under, (
        "silent budget drift %s — edit ALLOWED_SILENT in "
        "tests/test_silent_except_budget.py if intentional; sites=%s"
        % (under, sites))
    assert actual_total == allowed_total


def test_count_script_scan_matches_budget():
    """脚本 TOTAL与白名单一致，避免脚本/门禁口径分叉。"""
    mod = _load_counter()
    total_silent = sum(mod.scan(p)[1] for p in SRC.glob("*.py"))
    assert total_silent == sum(ALLOWED_SILENT.values())


if __name__ == "__main__":
    # 便于本地一眼看清当前静默位点
    mod = _load_counter()
    _counts, sites = _silent_by_file(mod)
    for s in sites:
        print(s)
    sys.exit(0)
