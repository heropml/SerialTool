#!/usr/bin/env bash
# Linux 一键发布：打包 .run 并挂到已有 comm-v<版本> GitHub Release，再写入 latest.json url_linux。
# 必须在 Linux 上跑（glibc 下限 = 本机构建环境；建议 Ubuntu 18.04+）。
# 用法: bash scripts/release_linux.sh [版本号]
# 省略版本号时读 src/version.py。不改版本号、不发 Windows/macOS。
set -euo pipefail
cd "$(dirname "$0")/.."

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) ;;
    *)
        echo "Official Linux releases are x86_64 only (this host is $ARCH)."
        exit 1
        ;;
esac

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    VERSION="$(grep -E '^__version__' src/version.py | head -1 | cut -d'"' -f2)"
fi
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "用法: bash scripts/release_linux.sh [版本号 如 1.5.7]"
    exit 1
fi

TAG="comm-v$VERSION"
RUN_NAME="CommTool_Setup_v${VERSION}_linux_x86_64.run"
RUN_PATH="installer/${RUN_NAME}"

echo "==================================================="
echo " 发布 CommTool Linux x86_64 v$VERSION  (tag: $TAG)"
echo "==================================================="

echo "[1/3] 打包 ..."
bash scripts/build.sh
[ -f "$RUN_PATH" ] || { echo "未找到 $RUN_PATH"; exit 1; }

echo "[2/3] 上传 GitHub Release $TAG ..."
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if gh release view "$TAG" >/dev/null 2>&1; then
        gh release upload "$TAG" "$RUN_PATH" --clobber
    else
        echo "Release $TAG 不存在。请先发 Windows 版（release.ps1）再建 tag。"
        exit 1
    fi
else
    echo "gh 未登录。请先上传 $RUN_PATH 到 GitHub Release $TAG 后重跑。"
    python3 scripts/check_linux_asset.py "$VERSION" || exit 2
fi

python3 scripts/check_linux_asset.py "$VERSION"

echo "[3/3] 写入 latest.json url_linux ..."
python3 - "$VERSION" <<'PY'
import json, sys
from pathlib import Path
version = sys.argv[1]
path = Path("latest.json")
data = json.loads(path.read_text(encoding="utf-8"))
if str(data.get("version", "")) != version:
    print("  latest.json 版本不是 %s，不改 url_linux" % version)
else:
    data["url_linux"] = [
        "https://github.com/heropml/SerialTool/releases/download/"
        "comm-v%s/CommTool_Setup_v%s_linux_x86_64.run" % (version, version)
    ]
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  latest.json 已启用 Linux v%s 下载" % version)
PY
git add latest.json
if git diff --cached --quiet -- latest.json; then
    echo "  (latest.json 无变化)"
else
    git commit -m "release: enable Linux v$VERSION download"
    echo "  请 git push github CommTool && git push gitee CommTool"
fi

echo "Linux 发布完成: $RUN_PATH"
