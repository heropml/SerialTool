#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gitee 发版脚本 —— 建/复用 Release + 覆盖附件，让国内用户能下载/在线升级。

为什么单独一个脚本：Gitee 没有 gh 这种 CLI，发 Release 只能走 Open API v5（需令牌）。
本脚本把「建 release / 删旧附件 / 传新 exe / 验证」都封好，配合长期令牌即可一键发，
不用每次手动生成临时令牌+粘贴。

令牌来源（按顺序）：
  1. 环境变量 GITEE_TOKEN
  2. scripts/.gitee_token 文件（已在 .gitignore，不会提交）
令牌在 Gitee → 设置 → 私人令牌生成，勾 projects 权限即可。

用法（在项目根或 scripts 下都行）：
  py -3 scripts/release_gitee.py            # 版本号自动从 src/version.py 读
  py -3 scripts/release_gitee.py 1.1.3      # 指定版本号
前置：installer/CommTool_Setup_v<版本>.exe 已打好。
（Gitee 仓库附件配额仅 1GB → 本脚本只往 Gitee 传 Setup.exe：在线更新只依赖它；
  免安装版 onefile.exe 与 macOS .dmg 只发到 GitHub，不占 Gitee 配额。）

推代码到 Gitee 不归本脚本管（走 SSH）：git push gitee CommTool
"""
import os
import re
import sys
import json
import uuid
import urllib.request
import urllib.parse

OWNER = "heropml"
REPO = "SerialTool"
BRANCH = "CommTool"
API = f"https://gitee.com/api/v5/repos/{OWNER}/{REPO}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def die(msg):
    print("[X] " + msg)
    sys.exit(1)


def get_token():
    t = os.environ.get("GITEE_TOKEN")
    if t and t.strip():
        return t.strip()
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gitee_token")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            t = f.read().strip()
        if t:
            return t
    die("找不到 Gitee 令牌：设环境变量 GITEE_TOKEN，或把令牌写进 scripts/.gitee_token")


def get_version():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip().lstrip("vV")
    vp = os.path.join(ROOT, "src", "version.py")
    with open(vp, encoding="utf-8") as f:
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
    if not m:
        die("src/version.py 里读不到 __version__")
    return m.group(1)


def api(method, path, fields=None):
    """urlencode 表单（UTF-8），GET/POST/DELETE 通用。返回 (status, json|text)。"""
    url = API + path
    data = None
    if method == "GET":
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(fields or {})
    else:
        data = urllib.parse.urlencode(fields or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        body = r.read().decode("utf-8", "replace")
        return r.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def upload(rid, filepath, token):
    """multipart 传单个附件。文件名 ASCII，无编码坑。"""
    fname = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        content = f.read()
    boundary = "----GiteeRel" + uuid.uuid4().hex
    pre = (f"--{boundary}\r\n"
           f'Content-Disposition: form-data; name="access_token"\r\n\r\n{token}\r\n'
           f"--{boundary}\r\n"
           f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
           f"Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
    body = pre + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(f"{API}/releases/{rid}/attach_files",
                                 data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        r = urllib.request.urlopen(req, timeout=300)
        return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    token = get_token()
    ver = get_version()
    tag = f"comm-v{ver}"
    # Gitee 附件配额仅 1GB（免费版）：每版 3 资产 ~131MB，约 8 版就撑满（HTTP 400「超出配额」）。
    # 在线更新只依赖 Setup.exe（latest.json 的 url 指它），故 Gitee 只放 Setup.exe；
    # 免安装版 onefile.exe 与 macOS .dmg 只发到 GitHub（无配额限制）。
    setup = os.path.join(ROOT, "installer", f"CommTool_Setup_v{ver}.exe")
    if not os.path.exists(setup):
        die(f"找不到安装包：{setup}\n  先打包：build.bat + ISCC")

    print(f">> Gitee 发版 {tag}")

    # 1. 找已有 release（同 tag 复用，不重复建）
    st, rels = api("GET", "/releases", {"access_token": token})
    if st != 200 or not isinstance(rels, list):
        die(f"查 release 列表失败：HTTP {st} {rels}")
    rel = next((r for r in rels if r.get("tag_name") == tag), None)

    if rel:
        rid = rel["id"]
        print(f"  复用已有 Release id={rid}")
    else:
        st, rel = api("POST", "/releases", {
            "access_token": token, "tag_name": tag, "name": f"CommTool v{ver}",
            "body": f"国内镜像版（功能与 GitHub Release 一致）。\n安装版 CommTool_Setup_v{ver}.exe（免安装版 / macOS dmg 请到 GitHub Release 下载）",
            "target_commitish": BRANCH,
        })
        if st not in (200, 201) or not isinstance(rel, dict) or not rel.get("id"):
            die(f"建 release 失败：HTTP {st} {rel}")
        rid = rel["id"]
        print(f"  新建 Release id={rid}")

    # 2. 删旧附件（Gitee 无 clobber，先删后传）
    st, atts = api("GET", f"/releases/{rid}/attach_files", {"access_token": token})
    if st == 200 and isinstance(atts, list):
        for a in atts:
            api("DELETE", f"/releases/{rid}/attach_files/{a['id']}",
                {"access_token": token})
            print(f"  删旧附件 {a.get('name')}")

    # 3. 传新附件（仅 Setup.exe；onefile / dmg 走 GitHub，不占 Gitee 配额）
    st, res = upload(rid, setup, token)
    if st in (200, 201) and isinstance(res, dict):
        print(f"  [OK] 传 {res.get('name')}")
    else:
        die(f"传附件失败 {os.path.basename(setup)}：HTTP {st} {res}")

    # 4. 验证下载链接
    dl = f"https://gitee.com/{OWNER}/{REPO}/releases/download/{tag}/CommTool_Setup_v{ver}.exe"
    print(f"\n[OK] 完成。下载链接（latest.json 的 url 应为此）：\n  {dl}")
    print("  提醒：latest.json 的 url 用 Gitee 链接、代码记得 git push gitee CommTool")


if __name__ == "__main__":
    main()
