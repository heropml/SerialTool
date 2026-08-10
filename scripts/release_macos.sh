#!/usr/bin/env bash
# macOS 一键发布脚本
# 用法:
#   bash scripts/release_macos.sh <版本号> [发布说明]
#   例:  bash scripts/release_macos.sh 1.1.0 "新增 macOS 支持"
#
# 自动完成:
#   1. 改 src/version.py 版本号
#   2. 打包 .app + 版本号命名的 .dmg
#   3. 提交版本号改动并 git push
#   4. 建 GitHub Release(tag: comm-v<版本>)并上传、校验 .dmg
#        · gh 已登录 → 自动创建/上传
#        · gh 未登录 → 已有资产则继续门禁；否则建 tag 并给出手动步骤
#
# latest.json 是 Win/Mac 共用的：仅当同版本 Windows 清单已存在且 GitHub
# DMG 资产通过门禁时，自动启用 url_mac。

set -e
cd "$(dirname "$0")/.."

VERSION="${1:-}"
NOTES="${2:-CommTool macOS v$VERSION}"
TAG="comm-v$VERSION"
APP_NAME="CommTool"

# ---- 校验版本号 ----
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "用法: bash scripts/release_macos.sh <版本号 如 1.1.0> [发布说明]"
    exit 1
fi

echo "==================================================="
echo " 发布 $APP_NAME macOS v$VERSION  (tag: $TAG)"
echo "==================================================="

# ---- 1. 改版本号 ----
echo "[1/4] 写入 src/version.py → $VERSION"
python3 - "$VERSION" <<'PY'
import re, sys
v = sys.argv[1]
p = "src/version.py"
s = open(p, encoding="utf-8").read()
s = re.sub(r'__version__\s*=\s*"[^"]*"', f'__version__ = "{v}"', s)
open(p, "w", encoding="utf-8").write(s)
PY

# ---- 2. 打包(.app + .dmg) ----
echo "[2/4] 打包 .app + .dmg ..."
bash scripts/build_macos.sh --dmg

[ -f "dist/$APP_NAME.dmg" ] || { echo "❌ 未找到 dist/$APP_NAME.dmg,打包失败"; exit 1; }
REL_DMG="dist/${APP_NAME}_v${VERSION}.dmg"
cp "dist/$APP_NAME.dmg" "$REL_DMG"
echo "  产物: $REL_DMG"

# ---- 3. 提交版本号 + 推送 ----
echo "[3/4] 提交版本号并推送 ..."
git add src/version.py
if git diff --cached --quiet; then
    echo "  (版本号无变化,跳过提交)"
else
    git commit -m "release: macOS v$VERSION"
fi
git push

# ---- 4. GitHub Release + DMG 资产门禁 ----
echo "[4/4] 创建 GitHub Release ..."
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if gh release view "$TAG" >/dev/null 2>&1; then
        gh release upload "$TAG" "$REL_DMG" --clobber
        echo "  ✅ 已向现有 Release $TAG 上传 $REL_DMG"
    else
        gh release create "$TAG" "$REL_DMG" --title "$APP_NAME v$VERSION" --notes "$NOTES"
        echo "  ✅ 已创建 Release $TAG 并上传 $REL_DMG"
    fi
else
    echo "  ⚠️ gh 未安装或未登录，检查 Release 是否已有手工上传的 DMG ..."
    if python3 scripts/check_mac_asset.py "$VERSION"; then
        echo "  ✅ 已找到现有 DMG，继续更新门禁"
    else
        git tag "$TAG" 2>/dev/null && git push origin "$TAG" 2>/dev/null && echo "     · 已推送 tag $TAG" || echo "     · tag $TAG 可能已存在"
        echo "     1) 打开 https://github.com/heropml/SerialTool/releases/new?tag=$TAG"
        echo "     2) 标题填 $APP_NAME v$VERSION"
        echo "     3) 把 $REL_DMG 拖进附件区并 Publish release"
        echo "     4) 上传后重新运行本脚本；无需 gh，也会通过 GitHub API 校验并回写清单"
        echo "❌ DMG 尚未发布，当前未启用 app 内 macOS 下载"
        exit 2
    fi
fi

echo "  校验 GitHub 上确有 ${APP_NAME}_v${VERSION}.dmg ..."
python3 scripts/check_mac_asset.py "$VERSION" || {
    echo "❌ Mac publish gate failed — Release 上找不到 DMG，中止"
    exit 1
}
# 共享清单只在同版本 Windows 清单已经存在时启用 Mac 下载，避免任一平台
# 提前把另一平台导向尚未发布的资产。
python3 - "$VERSION" <<'PY'
import json, sys
from pathlib import Path

version = sys.argv[1]
path = Path("latest.json")
data = json.loads(path.read_text(encoding="utf-8"))
if str(data.get("version", "")) != version:
    print("  ⚠️ latest.json 版本不是 %s，不改 url_mac" % version)
else:
    data["url_mac"] = [
        "https://github.com/heropml/SerialTool/releases/download/"
        "comm-v%s/CommTool_v%s.dmg" % (version, version)
    ]
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  ✅ latest.json 已启用 macOS v%s 下载" % version)
PY
git add latest.json
if git diff --cached --quiet -- latest.json; then
    echo "  (latest.json 无变化)"
else
    git commit -m "release: enable macOS v$VERSION download"
    git push
fi

echo ""
echo "==================================================="
echo " 完成!v$VERSION"
echo "   安装包: $REL_DMG"
echo ""
echo " 📌 app 内 macOS 下载仅在 GitHub DMG 校验通过且 latest.json 已是同版本时自动启用。"
echo "     若上面提示版本不一致，先等 Windows 同版本发布，再重跑本脚本或手动补 url_mac。"
echo "     ⚠️ latest.json 是 Win/Mac 共用 —— 若 Windows 的 v$VERSION .exe 还没发,"
echo "        先别改它,否则 Windows 用户会被导向不存在的安装包。"
echo "     Mac url_mac 只指向已通过门禁的 GitHub DMG（Gitee 标准流程不传 dmg）。"
echo "==================================================="
