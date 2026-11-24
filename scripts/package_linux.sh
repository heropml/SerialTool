#!/usr/bin/env bash
# Pack dist/CommTool into a per-user Linux installer (.run) and a portable .tar.gz.
# Must run on Linux after scripts/build.sh (or an equivalent PyInstaller + syslib bundle).
set -euo pipefail
cd "$(dirname "$0")/.."

DIST="./dist/CommTool"
if [ ! -x "$DIST/CommTool" ] && [ ! -x "$DIST/CommTool.bin" ]; then
    echo "No Linux dist at $DIST — run bash scripts/build.sh first."
    exit 1
fi

VERSION="$(grep -E '^__version__' src/version.py | head -1 | cut -d'"' -f2)"
if [ -z "$VERSION" ]; then
    echo "Could not read src/version.py"
    exit 1
fi
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) ARCH=x86_64 ;;
    *)
        echo "Official Linux packages are x86_64 only (this host is $ARCH)."
        echo "PyInstaller does not cross-compile; build on an x86_64 machine."
        exit 1
        ;;
esac

OUT_DIR="./installer"
mkdir -p "$OUT_DIR"
STAGE="$(mktemp -d /tmp/commtool-linux-pkg.XXXXXX)"
PAYLOAD="$STAGE/CommTool-linux"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$PAYLOAD/CommTool"
cp -a "$DIST"/. "$PAYLOAD/CommTool/"
# Drop leftover wrapper symlink from the build VM; installer has its own entry.
rm -f "$PAYLOAD/CommTool/run.sh"

python3 - <<'PY'
import base64, pathlib, sys
sys.path.insert(0, "src")
from icon_data import ICON_B64
pathlib.Path("installer").mkdir(exist_ok=True)
png = pathlib.Path("/tmp/commtool-icon.png")
# written into payload below via env
open("/tmp/commtool-icon.png", "wb").write(base64.b64decode(ICON_B64))
PY
cp /tmp/commtool-icon.png "$PAYLOAD/CommTool/commtool.png"
rm -f /tmp/commtool-icon.png

cat > "$PAYLOAD/install.sh" <<'INSTALL'
#!/usr/bin/env bash
# Per-user CommTool install (no sudo). Override with COMMTOOL_PREFIX=/path
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${COMMTOOL_PREFIX:-$HOME/.local/opt/CommTool}"
BIN_DIR="${COMMTOOL_BIN_DIR:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/128x128/apps"
DESKTOP_DIR="$HOME/Desktop"

check_payload() {
    local bundle=$1
    if [[ ! -f "$bundle/CommTool" ]]; then
        echo "Installer payload is missing the CommTool launcher" >&2
        return 1
    fi
    # A plain PyInstaller ELF is also supported. The shell launcher needs both
    # the renamed binary and the runtime that was built alongside it.
    if [[ $(LC_ALL=C head -c 4 -- "$bundle/CommTool") != $'\x7fELF' ]]; then
        if [[ ! -f "$bundle/CommTool.bin" || ! -d "$bundle/_internal" ]]; then
            echo "Installer payload requires CommTool.bin and _internal" >&2
            return 1
        fi
    fi
}
if [[ ${1:-} == --check-payload ]]; then
    check_payload "$HERE/CommTool"
    exit 0
fi

echo "Installing CommTool to: $PREFIX"
mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR" "$PREFIX"
# Different prefixes can share the same menu and command. Hold the directory
# locks through rollback, taking just one lock for aliased destinations.
declare -A locked_dirs=()
for dir in "$PREFIX" "$BIN_DIR" "$APP_DIR" "$ICON_DIR" "$DESKTOP_DIR"; do
    [[ -d "$dir" ]] || continue
    key=$(stat -Lc '%d:%i' -- "$dir")
    [[ ${locked_dirs[$key]+held} ]] && continue
    exec {lock_fd}<"$dir"
    flock -n "$lock_fd" || { echo "Another installation is using $dir" >&2; exit 1; }
    locked_dirs[$key]=$lock_fd
done
# Stage on the target filesystem so switching even a running ELF uses rename.
work=$(mktemp -d -- "$PREFIX/.commtool-install.XXXXXX")
new="$work/new"
old="$work/old"
installing=()
entries=()
entry_count=0
entry_tmp=
finish_install() {
    status=$?
    trap - EXIT
    trap '' HUP INT TERM
    set +e
    local restored=1 i entry backup
    if (( status != 0 )); then
        echo "Installation failed; restoring the previous runtime from $work" >&2
        for name in ${installing[@]+"${installing[@]}"}; do
            if [[ ! -e "$new/$name" && ! -L "$new/$name" ]]; then
                mv -T -- "$PREFIX/$name" "$new/$name" || restored=0
            fi
        done
        for backup in "$old"/*; do
            [[ -e "$backup" || -L "$backup" ]] || continue
            mv -T -- "$backup" "$PREFIX/${backup##*/}" || restored=0
        done
        for ((i=entry_count-1; i>=0; i--)); do
            entry=${entries[i]}
            backup="$work/entries/$i"
            if [[ -e "$backup" || -L "$backup" ]]; then
                mv -fT -- "$backup" "$entry" || restored=0
            else
                rm -f -- "$entry" || restored=0
            fi
        done
    fi
    if [[ -n "$entry_tmp" ]]; then rm -rf -- "$entry_tmp"; fi
    if (( restored )); then
        rm -rf -- "$work" || echo "Could not remove installation backup: $work" >&2
    else
        echo "Rollback incomplete. Installation backup retained at $work" >&2
    fi
    exit "$status"
}
trap finish_install EXIT
trap 'exit 1' HUP INT TERM
mkdir -- "$old" "$work/entries"
cp -a -- "$HERE/CommTool" "$new"
check_payload "$new"
chmod +x -- "$new/CommTool"
if [[ -f "$new/CommTool.bin" ]]; then
    chmod +x -- "$new/CommTool.bin"
fi

for name in _internal CommTool.bin CommTool; do
    if [[ ! -e "$new/$name" && ! -L "$new/$name" ]]; then
        continue
    fi
    if [[ -e "$PREFIX/$name" || -L "$PREFIX/$name" ]]; then
        mv -T -- "$PREFIX/$name" "$old/$name"
    fi
    installing+=("$name")
    mv -T -- "$new/$name" "$PREFIX/$name"
done
# Merge other package files while keeping the user's profile and prefix permissions.
find "$new" -mindepth 1 -maxdepth 1 -exec cp -a -t "$PREFIX" -- {} +

# Shortcuts can belong to an installation in another prefix. Save their actual
# contents/targets and publish each replacement by rename on its own filesystem.
publish_entry() {
    local src=$1 dest=$2
    if [[ -d "$dest" && ! -L "$dest" ]]; then
        echo "Cannot replace directory: $dest" >&2
        return 1
    fi
    entry_tmp=$(mktemp -d -- "$(dirname -- "$dest")/.commtool-entry.XXXXXX")
    cp -aT -- "$src" "$entry_tmp/new"
    if [[ -e "$dest" || -L "$dest" ]]; then
        cp -aT -- "$dest" "$work/entries/$entry_count"
    fi
    entries[entry_count]=$dest
    ((entry_count+=1))
    mv -fT -- "$entry_tmp/new" "$dest"
    rmdir -- "$entry_tmp"
    entry_tmp=
}
if [ -f "$PREFIX/commtool.png" ]; then
    publish_entry "$PREFIX/commtool.png" "$ICON_DIR/commtool.png"
fi

ln -s -- "$PREFIX/CommTool" "$work/cli"
publish_entry "$work/cli" "$BIN_DIR/CommTool"

DESKTOP_FILE="$APP_DIR/commtool.desktop"
cat > "$work/commtool.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=CommTool
Name[zh_CN]=通信调试工具
Name[zh_TW]=通訊除錯工具
GenericName=Serial / Network Debugger
Comment=UART serial terminal and TCP/UDP debugger
Comment[zh_CN]=串口调试助手 / 网络调试工具
Exec=$PREFIX/CommTool
Icon=commtool
Terminal=false
Categories=Development;Utility;
StartupNotify=true
StartupWMClass=CommTool
EOF
chmod 755 -- "$work/commtool.desktop"
publish_entry "$work/commtool.desktop" "$DESKTOP_FILE"

if [ -d "$DESKTOP_DIR" ]; then
    publish_entry "$work/commtool.desktop" "$DESKTOP_DIR/commtool.desktop"
    if command -v gio >/dev/null 2>&1; then
        gio set "$DESKTOP_DIR/commtool.desktop" metadata::trusted true >/dev/null 2>&1 || true
    fi
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" >/dev/null 2>&1 || true
fi

UNINST="$PREFIX/uninstall.sh"
cat > "$work/uninstall.sh" <<UN
#!/usr/bin/env bash
set -euo pipefail
PREFIX="$PREFIX"
BIN_DIR="$BIN_DIR"
APP_DIR="$APP_DIR"
ICON_DIR="$ICON_DIR"
DESKTOP_DIR="$DESKTOP_DIR"
rm -f "\$BIN_DIR/CommTool"
rm -f "\$APP_DIR/commtool.desktop"
rm -f "\$DESKTOP_DIR/commtool.desktop"
rm -f "\$ICON_DIR/commtool.png"
rm -rf "\$PREFIX"
echo "CommTool uninstalled."
UN
chmod +x "$work/uninstall.sh"
publish_entry "$work/uninstall.sh" "$UNINST"

echo
echo "Install OK."
echo "  Launch:  CommTool"
echo "  Or:      $PREFIX/CommTool"
echo "  Menu:    application menu → CommTool"
echo "  Desktop: ~/Desktop/commtool.desktop  (if the folder exists)"
echo "  Remove:  $UNINST"

MSG="CommTool 已安装到
$PREFIX

可从应用菜单或桌面图标启动。
卸载：$UNINST"

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    if command -v zenity >/dev/null 2>&1; then
        zenity --info --title="CommTool" --width=420 --text="$MSG" >/dev/null 2>&1 || true
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --title "CommTool" --msgbox "$MSG" >/dev/null 2>&1 || true
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send "CommTool" "已安装到 $PREFIX" >/dev/null 2>&1 || true
    fi
fi
INSTALL
chmod +x "$PAYLOAD/install.sh"
bash "$PAYLOAD/install.sh" --check-payload

cat > "$PAYLOAD/README.txt" <<EOF
CommTool v${VERSION}  (Linux ${ARCH})

图形界面安装（推荐）
  1. 给安装器执行权限：  chmod +x CommTool_Setup_v${VERSION}_linux_${ARCH}.run
  2. 双击该文件，或在终端运行：  ./CommTool_Setup_v${VERSION}_linux_${ARCH}.run
  3. 默认装到 ~/.local/opt/CommTool ，并创建应用菜单项和桌面图标（无需 sudo）

便携包
  tar -xzf CommTool_v${VERSION}_linux_${ARCH}.tar.gz
  cd CommTool-linux && ./install.sh

指定安装目录
  COMMTOOL_PREFIX=\$HOME/Apps/CommTool ./install.sh

启动
  CommTool
  或 ~/.local/opt/CommTool/CommTool

卸载
  ~/.local/opt/CommTool/uninstall.sh

说明
  已打包 Qt xcb / X11 库，一般不必再 apt 安装依赖。
  串口设备可能需要把当前用户加入 dialout 组（需管理员，与本安装包无关）。
EOF

TAR_NAME="CommTool_v${VERSION}_linux_${ARCH}.tar.gz"
RUN_NAME="CommTool_Setup_v${VERSION}_linux_${ARCH}.run"
TAR_PATH="$OUT_DIR/$TAR_NAME"
RUN_PATH="$OUT_DIR/$RUN_NAME"

echo "Creating $TAR_PATH ..."
tar -C "$STAGE" -czf "$TAR_PATH" CommTool-linux

HEADER="$STAGE/header.sh"
cat > "$HEADER" <<'HEADER'
#!/usr/bin/env bash
# Self-extracting CommTool installer. Does not need sudo.
set -euo pipefail
if ! command -v tar >/dev/null 2>&1; then
    echo "tar is required to install CommTool."
    exit 1
fi
WORKDIR="$(mktemp -d /tmp/commtool-setup.XXXXXX)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT
ARCHIVE_LINE="$(awk '/^__ARCHIVE_BELOW__/ { print NR + 1; exit 0 }' "$0")"
tail -n +"$ARCHIVE_LINE" "$0" | tar -xzf - -C "$WORKDIR"
if [ ! -x "$WORKDIR/CommTool-linux/install.sh" ]; then
    echo "Installer payload is incomplete."
    exit 1
fi
bash "$WORKDIR/CommTool-linux/install.sh"
exit 0
__ARCHIVE_BELOW__
HEADER

echo "Creating $RUN_PATH ..."
cat "$HEADER" "$TAR_PATH" > "$RUN_PATH"
chmod +x "$RUN_PATH"

echo
echo "============================================"
echo " Linux package OK  v${VERSION}  ${ARCH}"
echo " Portable:  $TAR_PATH"
echo " Setup:     $RUN_PATH"
ls -lh "$TAR_PATH" "$RUN_PATH"
echo "============================================"
