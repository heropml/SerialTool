#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gitee 发版脚本 —— 建/复用 Release + 传 Setup.exe，让国内用户能下载/在线升级。

为什么单独一个脚本：Gitee 没有 gh 这种 CLI，发 Release 只能走 Open API v5（需令牌）。
本脚本把「建 release / 删旧附件 / 传新 exe / 验证」都封好，配合长期令牌即可一键发，
不用每次手动生成临时令牌+粘贴。

令牌来源（按顺序）：
  1. 环境变量 GITEE_TOKEN
  2. scripts/.gitee_token 文件（已在 .gitignore，不会提交）
  3. ~/doc/token/gitee_token.txt（Mac 上的存放位置）
令牌在 Gitee → 设置 → 私人令牌生成，勾 projects 权限即可。

用法（在项目根或 scripts 下都行）：
  py -3 scripts/release_gitee.py            # 版本号自动从 src/version.py 读
  py -3 scripts/release_gitee.py 1.1.3      # 指定版本号
  py -3 scripts/release_gitee.py 1.1.3 --notes-only  # 只同步标题/正文，不动附件（不需要本地安装包）
前置（非 --notes-only）：installer/CommTool_Setup_v<版本>.exe 已打好。
附件规则（RELEASE.md「零」）：两站都传 Setup.exe + dmg，不再发 onefile；Linux .run
超过 Gitee 单文件 100MB 上限，只在 GitHub（变小后 release_gitee_asset.py 会自动补传）。
本脚本只替换同名 Setup.exe；dmg / .run 由 release_gitee_asset.py 追加，互不删除。
Gitee 正文下载表里 Gitee 上没有的文件，会自动加一句「请到 GitHub 下载」。
Gitee 附件配额 1GB，不自动清理旧版。

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
# Gitee 单个附件上限 100MB（超了 API 回 400「文件大小已超出限制：100 MB」）；Linux .run 约 130MB 传不上
GITEE_MAX_ASSET = 100 * 1024 * 1024
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def die(msg):
    print("[X] " + msg)
    sys.exit(1)


def get_token():
    t = os.environ.get("GITEE_TOKEN")
    if t and t.strip():
        return t.strip()
    for p in (os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gitee_token"),
              os.path.expanduser("~/doc/token/gitee_token.txt")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                t = f.read().strip()
            if t:
                return t
    die("找不到 Gitee 令牌：设环境变量 GITEE_TOKEN，或把令牌写进 scripts/.gitee_token")


def get_version(argv=None):
    """版本号取 argv 里第一个非 -- 参数（默认 sys.argv[1:]），没有就读 src/version.py。"""
    args = [a for a in (sys.argv[1:] if argv is None else argv)
            if a.strip() and not a.startswith("--")]
    if args:
        return args[0].strip().lstrip("vV")
    vp = os.path.join(ROOT, "src", "version.py")
    with open(vp, encoding="utf-8") as f:
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
    if not m:
        die("src/version.py 里读不到 __version__")
    return m.group(1)


def get_release_body(ver, gitee_files=None):
    """读取完整发布说明，并把下载区适配成 Gitee 实际提供的附件。

    功能说明与 GitHub 共用同一真源。下载表里列出、但 Gitee 上没有的安装包（Linux .run
    超 100MB、尚未补传的 dmg，以及 v1.8.3 及更早只在 GitHub 的 onefile），在表后统一
    提示去 GitHub Release 下载。gitee_files 是 Gitee 上（即将）有的附件名集合；
    为 None 时只做 onefile 的旧版适配。
    """
    path = os.path.join(ROOT, "docs", "RELEASE_NOTES.md")
    try:
        with open(path, encoding="utf-8") as f:
            body = f.read().strip()
    except OSError as e:
        die(f"读取发布说明失败：{e}")
    if not body:
        die("docs/RELEASE_NOTES.md 为空，拒绝发布无说明的 Release")
    if f"v{ver}" not in body:
        die(f"docs/RELEASE_NOTES.md 里没出现 v{ver}，像是别的版本的文案，拒绝覆盖 Release 正文")
    rows = list(re.finditer(r"^\|[^|\n]*\|\s*`(CommTool[^`]*)`[^\n]*$", body, re.MULTILINE))
    if not rows:
        return body
    table_start, table_end = rows[0].start(), rows[0].end()
    while True:  # 提示放在整张下载表之后，插在中间会把表格截断
        nxt = re.match(r"\n\|[^\n]*", body[table_end:])
        if not nxt:
            break
        table_end += nxt.end()
    table = body[table_start:table_end]
    missing = []
    # onefile（v1.8.3 及更早）只在 GitHub：整行去掉，放进提示
    onefile = re.search(r"^\| Windows 单文件版 \|[^`\n]*`([^`]+)`.*\n?", table, re.MULTILINE)
    if onefile:
        missing.append(onefile.group(1))
        table = table[:onefile.start()] + table[onefile.end():]
        table = table.rstrip("\n")
    if gitee_files is not None:
        for m in rows:
            name = m.group(1)
            if name not in gitee_files and name not in missing and name in table:
                missing.append(name)
    if not missing:
        return body[:table_start] + table + body[table_end:]
    github_url = f"https://github.com/{OWNER}/{REPO}/releases/tag/comm-v{ver}"
    names = "、".join(f"`{n}`" for n in missing)
    note = (f"\n\n> 以下文件只在 GitHub 提供（Gitee 单文件上限 100MB，或尚未补传），请到\n"
            f"> [GitHub Release]({github_url}) 下载：{names}")
    return body[:table_start] + table + note + body[table_end:]


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


def find_release(tag, token):
    """按 tag 精确查 Release（列表接口有分页，版本多后只扫首页会误判不存在）。没有返回 None。"""
    st, rel = api("GET", f"/releases/tags/{urllib.parse.quote(tag, safe='')}",
                  {"access_token": token})
    if st == 404 or (st == 200 and rel is None):
        return None
    if st != 200 or not isinstance(rel, dict):
        die(f"按 tag 查询 release 失败：HTTP {st} {rel}")
    return rel


def replace_asset(rid, filepath, token, skip_existing=False):
    """传一个附件：同名旧附件先删（Gitee 无 clobber），其它附件原样保留。

    skip_existing=True 时已有同名附件就不重传（CI 重跑时省配额和流量）。
    超过 Gitee 单文件上限的直接跳过。返回 "uploaded" / "exists" / "too_large"。
    """
    fname = os.path.basename(filepath)
    size = os.path.getsize(filepath)
    if size > GITEE_MAX_ASSET:
        print(f"  [!] {fname} 有 {size / 1024 / 1024:.0f}MB，超过 Gitee 单文件 100MB 上限，"
              f"跳过（只在 GitHub 提供）")
        return "too_large"
    st, atts = api("GET", f"/releases/{rid}/attach_files", {"access_token": token})
    if st != 200 or not isinstance(atts, list):
        die(f"读取附件列表失败：HTTP {st} {atts}")
    same = [a for a in atts if a.get("name") == fname]
    if same and skip_existing:
        print(f"  已有 {fname}，跳过")
        return "exists"
    for a in same:
        st, res = api("DELETE", f"/releases/{rid}/attach_files/{a['id']}",
                      {"access_token": token})
        if st not in (200, 204):
            die(f"删同名旧附件失败 {fname}：HTTP {st} {res}")
        print(f"  删同名旧附件 {fname}")
    st, res = upload(rid, filepath, token)
    if st not in (200, 201) or not isinstance(res, dict):
        die(f"传附件失败 {fname}：HTTP {st} {res}")
    print(f"  [OK] 传 {res.get('name')}")
    return "uploaded"


def main():
    token = get_token()
    ver = get_version()
    tag = f"comm-v{ver}"
    notes_only = "--notes-only" in sys.argv[1:]
    setup = os.path.join(ROOT, "installer", f"CommTool_Setup_v{ver}.exe")
    if not notes_only and not os.path.exists(setup):
        die(f"找不到安装包：{setup}\n  先打包：build.bat + ISCC")

    print(f">> Gitee 发版 {tag}")

    # 1. 建 / 复用 Release；复用时同步标题与完整正文（补发附件/修复文案时不能保留旧占位文本）
    rel = find_release(tag, token)
    gitee_files = {a.get("name") for a in (rel or {}).get("assets", [])}
    if not notes_only:
        gitee_files.add(os.path.basename(setup))  # 本次就会传上去
    body = get_release_body(ver, gitee_files)
    if rel:
        rid = rel["id"]
        print(f"  复用已有 Release id={rid}")
        st, updated = api("PATCH", f"/releases/{rid}", {
            "access_token": token, "tag_name": tag, "name": f"CommTool v{ver}",
            "body": body, "target_commitish": BRANCH,
        })
        if st != 200 or not isinstance(updated, dict):
            die(f"更新 release 文案失败：HTTP {st} {updated}")
        print("  [OK] 同步完整 Release Notes")
    elif notes_only:
        die(f"Gitee 上没有 Release {tag}，--notes-only 无从同步（先跑完整发版）")
    else:
        st, rel = api("POST", "/releases", {
            "access_token": token, "tag_name": tag, "name": f"CommTool v{ver}",
            "body": body,
            "target_commitish": BRANCH,
        })
        if st not in (200, 201) or not isinstance(rel, dict) or not rel.get("id"):
            die(f"建 release 失败：HTTP {st} {rel}")
        rid = rel["id"]
        print(f"  新建 Release id={rid}")

    if notes_only:
        print(f"\n[OK] 已同步 Gitee Release {tag} 的标题与完整正文（未改附件）")
        return

    # 2. 只替换同名 Setup.exe；已补传的 dmg / .run 保留（两站附件规则见 RELEASE.md「零」）
    replace_asset(rid, setup, token)

    # 3. 验证下载链接
    dl = f"https://gitee.com/{OWNER}/{REPO}/releases/download/{tag}/CommTool_Setup_v{ver}.exe"
    print(f"\n[OK] 完成。下载链接（latest.json 的 url 应为此）：\n  {dl}")
    print("  提醒：latest.json 的 url 用 Gitee 链接、代码记得 git push gitee CommTool")


if __name__ == "__main__":
    main()
