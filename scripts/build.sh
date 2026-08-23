#!/usr/bin/env bash
# Linux 打包脚本 — 必须在 Linux 上跑（不支持 Windows 交叉编译）
# 用法: bash build.sh

set -e
cd "$(dirname "$0")/.."

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) ;;
    *)
        echo "Official Linux builds are x86_64 only (this host is $ARCH)."
        echo "PyInstaller does not cross-compile; build on an x86_64 machine."
        exit 1
        ;;
esac

echo "============================================"
echo " Building CommTool (Linux) with PyInstaller"
echo "============================================"
echo

# Tested source builds support Python 3.11..3.13; prefer the release target first.
python_supported() {
    command -v "$1" >/dev/null 2>&1 \
        && "$1" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)'
}
if [ -n "${PYTHON:-}" ]; then
    if ! python_supported "$PYTHON"; then
        echo "Unsupported PYTHON=$PYTHON; need Python 3.11..3.13."
        exit 1
    fi
elif [ -x ".venv-linux/bin/python" ] && python_supported ".venv-linux/bin/python"; then
    PYTHON=".venv-linux/bin/python"
else
    PYTHON=""
    for cand in python3.13 python3.12 python3.11; do
        if python_supported "$cand"; then
            PYTHON="$cand"
            break
        fi
    done
fi
if [ -z "$PYTHON" ]; then
    echo "Need Python 3.11..3.13 (3.13 is the release target)."
    exit 1
fi
echo "Using $($PYTHON --version 2>&1) [$PYTHON]"
SELECTED_PYTHON_MM="$($PYTHON -c 'import sys; print("%d.%d" % sys.version_info[:2])')"

# 优先用 venv，避免污染系统 Python
if [ ! -d ".venv-linux" ]; then
    echo "[1/5] Creating venv .venv-linux ..."
    "$PYTHON" -m venv .venv-linux
fi

# shellcheck disable=SC1091
source .venv-linux/bin/activate
if ! python -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)'; then
    echo ".venv-linux uses an unsupported Python; recreate it with Python 3.11..3.13."
    exit 1
fi
VENV_PYTHON_MM="$(python -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ "$VENV_PYTHON_MM" != "$SELECTED_PYTHON_MM" ]; then
    echo ".venv-linux uses Python $VENV_PYTHON_MM but this build selected $SELECTED_PYTHON_MM; recreate it."
    exit 1
fi

echo "[2/4] Installing deps ..."
# 国内用户可用清华镜像加速；海外/已配 pip.conf 的话删掉 -i 参数即可
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
pip install --upgrade pip -i "$PIP_INDEX"
pip install -i "$PIP_INDEX" -r requirements.txt -c constraints-runtime.txt pyinstaller

echo "[3/4] Running PyInstaller ..."
pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name CommTool \
    --add-data "examples:examples" \
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
python scripts/bundle_linux_syslibs.py ./dist/CommTool

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
