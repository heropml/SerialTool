#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 macOS .dmg / Linux .run 补传到 Gitee 已有的 comm-v<版本> Release。

两站附件规则（RELEASE.md「零」）：GitHub 与 Gitee 都放 Setup.exe + dmg + Linux .run。
Setup.exe 由 Windows 的 release.ps1 → release_gitee.py 传；dmg / .run 在各自平台
传完 GitHub 后用本脚本补到 Gitee。只替换同名附件，其它附件原样保留。

用法：
  python3 scripts/release_gitee_asset.py [--version X.Y.Z] [--skip-existing] <文件>...
  例：python3 scripts/release_gitee_asset.py dist/CommTool_v1.8.3.dmg
      python3 scripts/release_gitee_asset.py installer/CommTool_Setup_v1.8.3_linux_x86_64.run
版本号省略时读 src/version.py；文件名必须带 v<版本>，防止传错 Release。
--skip-existing：Gitee 上已有同名附件就不重传（CI 重跑用）。
令牌来源同 release_gitee.py（GITEE_TOKEN / scripts/.gitee_token / ~/doc/token/gitee_token.txt）。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from release_gitee import (OWNER, REPO, get_token, get_version, find_release,  # noqa: E402
                           replace_asset, die)


def publish(ver, paths, skip_existing=False):
    tag = f"comm-v{ver}"
    for p in paths:
        if not os.path.isfile(p):
            die(f"找不到文件：{p}")
        if f"v{ver}" not in os.path.basename(p):
            die(f"{os.path.basename(p)} 的文件名不含 v{ver}，不往 {tag} 传")
    token = get_token()
    print(f">> Gitee 补传到 {tag}：{', '.join(os.path.basename(p) for p in paths)}")
    rel = find_release(tag, token)
    if not rel:
        die(f"Gitee 上没有 Release {tag}（先在 Windows 上跑 release.ps1 建好该 Release）")
    print(f"  复用 Release id={rel['id']}")
    on_gitee = [p for p in paths
                if replace_asset(rel["id"], p, token, skip_existing=skip_existing) != "too_large"]
    print("\n[OK] 完成。Gitee 下载链接：")
    for p in on_gitee:
        print(f"  https://gitee.com/{OWNER}/{REPO}/releases/download/{tag}/{os.path.basename(p)}")
    if len(on_gitee) < len(paths):
        print("  （超限文件只在 GitHub；跑 release_gitee.py <版本> --notes-only 让 Gitee 正文提示去 GitHub 下载）")


def main():
    ap = argparse.ArgumentParser(description="补传 dmg / .run 到 Gitee Release")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--version")
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()
    ver = a.version.strip().lstrip("vV") if a.version else get_version([])
    publish(ver, a.files, skip_existing=a.skip_existing)


if __name__ == "__main__":
    main()
