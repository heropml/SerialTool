#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 macOS .dmg 补传到 Gitee 的 comm-v<版本> Release（只动 .dmg，不碰已有 .exe）。

为什么单独一个：release_gitee.py 会「删光所有附件再传两个 .exe」，在 Mac 上跑会把
Windows 的 .exe 删掉、且本机补不回。本脚本只针对 dist/CommTool_v<版本>.dmg —— 同名旧
附件先删再传（Gitee 无 clobber），其余附件（.exe / 源码包）原样保留，行为与
release_macos.sh 往 GitHub Release 追加 .dmg 一致。

令牌 / 版本号来源同 release_gitee.py（环境变量 GITEE_TOKEN 或 scripts/.gitee_token；
版本号取 argv，否则读 src/version.py）。
用法：python3 scripts/release_gitee_dmg.py [版本号]
前置：dist/CommTool_v<版本>.dmg 已打好（bash scripts/release_macos.sh 或 build_macos.sh --dmg）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from release_gitee import OWNER, REPO, get_token, get_version, api, upload, die  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    token = get_token()
    ver = get_version()
    tag = f"comm-v{ver}"
    dmg = os.path.join(ROOT, "dist", f"CommTool_v{ver}.dmg")
    if not os.path.exists(dmg):
        die(f"找不到 {dmg}\n  先打包：bash scripts/build_macos.sh --dmg")
    fname = os.path.basename(dmg)
    print(f">> Gitee 补传 macOS 包到 {tag}：{fname}")

    # 1. 找已有 release（不新建：Windows 版应已建好；找不到就报错，避免发出没有 .exe 的残缺 release）
    st, rels = api("GET", "/releases", {"access_token": token})
    if st != 200 or not isinstance(rels, list):
        die(f"查 release 列表失败：HTTP {st} {rels}")
    rel = next((r for r in rels if r.get("tag_name") == tag), None)
    if not rel:
        die(f"Gitee 上没有 Release {tag}（请先发 Windows 版 / 建好该 Release）")
    rid = rel["id"]
    print(f"  复用 Release id={rid}")

    # 2. 只删同名旧 .dmg（保留 .exe / 源码包等其它附件）
    st, atts = api("GET", f"/releases/{rid}/attach_files", {"access_token": token})
    if st == 200 and isinstance(atts, list):
        for a in atts:
            if a.get("name") == fname:
                api("DELETE", f"/releases/{rid}/attach_files/{a['id']}",
                    {"access_token": token})
                print(f"  删同名旧附件 {fname}")

    # 3. 传 .dmg
    st, res = upload(rid, dmg, token)
    if st in (200, 201) and isinstance(res, dict):
        print(f"  [OK] 已传 {res.get('name')}")
    else:
        die(f"传 .dmg 失败：HTTP {st} {res}")

    dl = f"https://gitee.com/{OWNER}/{REPO}/releases/download/{tag}/{fname}"
    print(f"\n[OK] 完成。下载链接：\n  {dl}")


if __name__ == "__main__":
    main()
