# -*- coding: utf-8 -*-
"""Windows 打包入口必须 --collect-all bleak（定制头像脚本曾漏过，exe 会报未安装 BLE）。"""
from __future__ import print_function

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 正式 / 单文件 / 定制头像 / 发版。Linux/macOS 不提供 BLE I/O，不要求收集 bleak。
_WIN_PACK_SCRIPTS = (
    "scripts/build.bat",
    "scripts/build_onefile.bat",
    "scripts/build_custom.py",
    "scripts/release.ps1",
)

# 覆盖 bat 的 `--collect-all bleak`、Python 的 "--collect-all", "bleak"、
# PowerShell 的 $args += '--collect-all'; $args += 'bleak'。
_COLLECT_BLEAK = re.compile(r"--collect-all.{0,80}bleak", re.IGNORECASE | re.DOTALL)


def test_windows_pack_scripts_collect_all_bleak():
    missing = []
    for rel in _WIN_PACK_SCRIPTS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if _COLLECT_BLEAK.search(text) is None:
            missing.append(rel)
    assert not missing, (
        "PyInstaller entry points missing --collect-all bleak: %s"
        % missing)
