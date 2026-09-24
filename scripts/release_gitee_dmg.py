#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 dist/CommTool_v<版本>.dmg 补传到 Gitee 的 comm-v<版本> Release（只替换同名 dmg）。

两站都要放 dmg（RELEASE.md「零」）。本脚本是 release_gitee_asset.py 的快捷方式，
.run 等其它文件直接用 release_gitee_asset.py。

用法：python3 scripts/release_gitee_dmg.py [版本号]
前置：dist/CommTool_v<版本>.dmg 已就绪（release_macos.sh / build_macos.sh --dmg，
或云端打包后 gh release download 下来）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from release_gitee import get_version, die  # noqa: E402
from release_gitee_asset import publish  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ver = get_version()
    dmg = os.path.join(ROOT, "dist", f"CommTool_v{ver}.dmg")
    if not os.path.exists(dmg):
        die(f"找不到 {dmg}\n  先打包：bash scripts/build_macos.sh --dmg")
    publish(ver, [dmg])


if __name__ == "__main__":
    main()
