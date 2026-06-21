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
#   4. 建 GitHub Release(tag: comm-v<版本>)并上传 .dmg
#        · gh 已登录 → 自动创建/上传
#        · gh 未登录 → 自动建 tag 并给出网页手动上传步骤
#
# 刻意不动 latest.json:它是 Win/Mac 共用的。等对应平台安装包都齐了,
# 再手动把 latest.json 的 version 改成新版,app 内「检查更新」才会提示用户。

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

# ---- 4. GitHub Release ----
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
    echo "  ⚠️ gh 未安装或未登录 —— 已自动建好 tag,请到网页手动建 Release:"
    git tag "$TAG" 2>/dev/null && git push origin "$TAG" 2>/dev/null && echo "     · 已推送 tag $TAG" || echo "     · tag $TAG 可能已存在"
    echo "     1) 打开 https://github.com/heropml/SerialTool/releases/new?tag=$TAG"
    echo "     2) 标题填 $APP_NAME v$VERSION"
    echo "     3) 把 $REL_DMG 拖进附件区,点 Publish release"
fi

echo ""
echo "==================================================="
echo " 完成!v$VERSION"
echo "   安装包: $REL_DMG"
echo ""
echo " 📌 想让 app 内「检查更新」提示用户升级,再手动改 latest.json:"
echo "     把 \"version\" 改成 \"$VERSION\" 并 git push。"
echo "     ⚠️ latest.json 是 Win/Mac 共用 —— 若 Windows 的 v$VERSION .exe 还没发,"
echo "        先别改它,否则 Windows 用户会被导向不存在的安装包。"
echo "==================================================="
