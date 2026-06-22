#!/usr/bin/env bash
# macOS 打包脚本 —— 必须在 macOS 上运行（不支持交叉编译）
# 用法:
#   bash scripts/build_macos.sh          # 仅产出 dist/CommTool.app
#   bash scripts/build_macos.sh --dmg    # 额外打一个 dist/CommTool.dmg（拖拽安装）

set -e
cd "$(dirname "$0")/.."

APP_NAME="CommTool"
BUNDLE_ID="com.heropml.commtool"
BUILD_DIR="build_macos"
ICNS="$BUILD_DIR/$APP_NAME.icns"

echo "============================================"
echo " Building $APP_NAME.app (macOS) with PyInstaller"
echo "============================================"
echo

# [1/4] 选虚拟环境：优先复用已有 .venv，否则建独立的 .venv-macos
if [ -d ".venv" ]; then
    VENV=".venv"
else
    VENV=".venv-macos"
    [ -d "$VENV" ] || { echo "[1/4] 创建 venv $VENV ..."; python3 -m venv "$VENV"; }
fi
echo "[1/4] 使用虚拟环境: $VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# [2/4] 安装依赖（从 requirements.txt 装，避免漏装运行时依赖如 pyqtgraph/numpy）
#       国内可用清华镜像加速；海外可 export PIP_INDEX=https://pypi.org/simple
echo "[2/4] 安装依赖 ..."
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
python -m pip install --upgrade pip -i "$PIP_INDEX" >/dev/null
python -m pip install -i "$PIP_INDEX" -r requirements.txt >/dev/null

# [3/4] 生成 .icns 图标
echo "[3/4] 生成 .icns 图标 ..."
python scripts/make_icns.py "$ICNS"

# [4/4] PyInstaller 打包成 .app（--windowed 在 macOS 上产出 .app bundle）
echo "[4/4] 运行 PyInstaller ..."
pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --icon "$ICNS" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    --paths src \
    --exclude-module PyQt5.QtBluetooth \
    --exclude-module PyQt5.QtDBus \
    --exclude-module PyQt5.QtDesigner \
    --exclude-module PyQt5.QtHelp \
    --exclude-module PyQt5.QtLocation \
    --exclude-module PyQt5.QtMultimedia \
    --exclude-module PyQt5.QtMultimediaWidgets \
    --exclude-module PyQt5.QtNfc \
    --exclude-module PyQt5.QtOpenGL \
    --exclude-module PyQt5.QtPositioning \
    --exclude-module PyQt5.QtQml \
    --exclude-module PyQt5.QtQuick \
    --exclude-module PyQt5.QtQuickWidgets \
    --exclude-module PyQt5.QtRemoteObjects \
    --exclude-module PyQt5.QtSensors \
    --exclude-module PyQt5.QtSerialPort \
    --exclude-module PyQt5.QtSql \
    --exclude-module PyQt5.QtTest \
    --exclude-module PyQt5.QtWebChannel \
    --exclude-module PyQt5.QtWebEngine \
    --exclude-module PyQt5.QtWebEngineCore \
    --exclude-module PyQt5.QtWebEngineWidgets \
    --exclude-module PyQt5.QtWebSockets \
    --exclude-module PyQt5.QtXmlPatterns \
    src/main.py

APP="dist/$APP_NAME.app"
if [ ! -d "$APP" ]; then
    echo "============================================"
    echo " Build FAILED（未生成 $APP）"
    echo "============================================"
    exit 1
fi

# 把 src/version.py 的版本号写进 .app 的 Info.plist（Finder「显示简介」会看到）
VER=$(python3 -c "import re;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('src/version.py',encoding='utf-8').read()).group(1))" 2>/dev/null || echo "")
if [ -n "$VER" ]; then
    plutil -replace CFBundleShortVersionString -string "$VER" "$APP/Contents/Info.plist"
    plutil -replace CFBundleVersion -string "$VER" "$APP/Contents/Info.plist"
    echo " 版本号写入 Info.plist: $VER"
fi

# 不跟随 macOS 系统暗色：本 app 用自带 QSS 主题统一上色。若跟随系统暗色，QTableWidget /
# QHeaderView / QScrollArea 视口等原生控件在暗色下不认 QSS 背景，会变黑底，叠上浅色主题的
# 深色文字 → 帧解析 / 波形图等弹窗黑底看不清（主窗口不用这些控件所以正常）。强制 Aqua(浅)
# 系统外观后，原生控件回到浅底，9 套 QSS 主题(浅/深)照常生效。
plutil -replace NSRequiresAquaSystemAppearance -bool true "$APP/Contents/Info.plist" 2>/dev/null \
    || plutil -insert NSRequiresAquaSystemAppearance -bool true "$APP/Contents/Info.plist"
echo " 禁用系统暗色外观跟随: NSRequiresAquaSystemAppearance=true"

echo
echo "============================================"
echo " Build OK"
echo " App:  $APP"
echo " Run:  open \"$APP\""
echo "============================================"

# 可选：打 .dmg（含 /Applications 软链，方便拖拽安装）
if [ "${1:-}" = "--dmg" ]; then
    echo
    echo "打包 .dmg ..."
    DMG="dist/$APP_NAME.dmg"
    STAGE="$BUILD_DIR/dmg"
    rm -rf "$STAGE"; mkdir -p "$STAGE"
    cp -R "$APP" "$STAGE/"
    ln -s /Applications "$STAGE/Applications"
    rm -f "$DMG"
    hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
    rm -rf "$STAGE"
    echo "✅ DMG: $DMG"
fi
