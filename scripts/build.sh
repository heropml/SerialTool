#!/usr/bin/env bash
# Linux 打包脚本 — 必须在 Linux 上跑（不支持 Windows 交叉编译）
# 用法: bash build.sh

set -e
cd "$(dirname "$0")/.."

echo "============================================"
echo " Building CommTool (Linux) with PyInstaller"
echo "============================================"
echo

# 优先用 venv，避免污染系统 Python
if [ ! -d ".venv-linux" ]; then
    echo "[1/3] Creating venv .venv-linux ..."
    python3 -m venv .venv-linux
fi

# shellcheck disable=SC1091
source .venv-linux/bin/activate

echo "[2/3] Installing deps ..."
# 国内用户可用清华镜像加速；海外/已配 pip.conf 的话删掉 -i 参数即可
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
pip install --upgrade pip -i "$PIP_INDEX"
pip install -i "$PIP_INDEX" PyQt5 pyserial pyinstaller

echo "[3/3] Running PyInstaller ..."
pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name CommTool \
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

echo
if [ -x "./dist/CommTool/CommTool" ]; then
    echo "============================================"
    echo " Build OK"
    echo " Output:  ./dist/CommTool/"
    echo " Run:     ./dist/CommTool/CommTool"
    echo "============================================"
else
    echo "============================================"
    echo " Build FAILED"
    echo "============================================"
    exit 1
fi
