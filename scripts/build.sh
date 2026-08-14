#!/usr/bin/env bash
# Linux 打包脚本 — 必须在 Linux 上跑（不支持 Windows 交叉编译）
# 用法: bash build.sh

set -e
cd "$(dirname "$0")/.."

echo "============================================"
echo " Building CommTool (Linux) with PyInstaller"
echo "============================================"
echo

# Prefer a 3.8+ interpreter (Ubuntu 18.04's python3 is 3.6).
if [ -z "${PYTHON:-}" ]; then
    PYTHON=""
    for cand in python3.12 python3.11 python3.10 python3.9 python3.8 python3; do
        if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)'; then
            PYTHON="$cand"
            break
        fi
    done
fi
if [ -z "$PYTHON" ]; then
    echo "Need Python 3.8+ (this host's python3 is too old for PyInstaller 6 / PyQt5 wheels)."
    exit 1
fi
echo "Using $($PYTHON --version 2>&1) [$PYTHON]"

# 优先用 venv，避免污染系统 Python
if [ ! -d ".venv-linux" ]; then
    echo "[1/5] Creating venv .venv-linux ..."
    "$PYTHON" -m venv .venv-linux
fi

# shellcheck disable=SC1091
source .venv-linux/bin/activate

echo "[2/4] Installing deps ..."
# 国内用户可用清华镜像加速；海外/已配 pip.conf 的话删掉 -i 参数即可
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
pip install --upgrade pip -i "$PIP_INDEX"
pip install -i "$PIP_INDEX" -r requirements.txt pyinstaller

echo "[3/4] Running PyInstaller ..."
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

echo "[4/5] Bundling X11/xcb libs into dist (no apt on target) ..."
python3 scripts/bundle_linux_syslibs.py ./dist/CommTool

echo "[5/5] Packaging Linux installer ..."
bash scripts/package_linux.sh

echo
if [ -x "./dist/CommTool/CommTool.bin" ] || [ -x "./dist/CommTool/CommTool" ]; then
    echo "============================================"
    echo " Build OK"
    echo " Output:  ./dist/CommTool/"
    echo " Run:     ./dist/CommTool/CommTool"
    echo " Setup:   ./installer/CommTool_Setup_v*.run"
    echo "============================================"
else
    echo "============================================"
    echo " Build FAILED"
    echo "============================================"
    exit 1
fi
