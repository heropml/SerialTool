#!/usr/bin/env python3
# Bundle Linux X11/xcb libs into a PyInstaller CommTool folder dist.
# Does not copy glibc / libstdc++ / GPU driver libs.
from __future__ import print_function

import glob
import os
import shutil
import subprocess
import sys

SKIP_PREFIXES = (
    "linux-vdso", "ld-linux", "libc.so", "libm.so", "libpthread", "libdl.so",
    "librt.so", "libresolv", "libutil.so", "libgcc_s", "libstdc++",
    "libgomp", "libglib-2", "libgobject", "libgio-", "libgmodule",
    "libsystemd", "libselinux", "libmount", "libblkid", "libuuid",
    "libpcre", "libffi.so", "libz.so", "liblzma", "libcap.so",
    "libGL.so", "libGLdispatch", "libGLX", "libOpenGL", "libdrm",
    "libgbm", "libEGL", "libwayland", "libatomic", "libnsl",
    "libcrypt.so", "libanl.so", "libBrokenLocale",
)

# Prefer bundling these even if already on the host.
WANT_PREFIXES = (
    "libxcb", "libX11", "libXau", "libXdmcp", "libXext", "libXrender",
    "libxkbcommon", "libbsd", "libmd.so", "libdouble-conversion",
    "libicui18n", "libicuuc", "libicudata", "libpcre2-16",
    "libpng", "libharfbuzz", "libfreetype", "libfontconfig",
    "libgraphite", "libexpat", "libbrotli",
)

DEB_FOR_LIB = {
    "libxcb-xinerama.so.0": "libxcb-xinerama0",
    "libxcb-cursor.so.0": "libxcb-cursor0",
    "libxkbcommon-x11.so.0": "libxkbcommon-x11-0",
    "libxcb-icccm.so.4": "libxcb-icccm4",
    "libxcb-image.so.0": "libxcb-image0",
    "libxcb-keysyms.so.1": "libxcb-keysyms1",
    "libxcb-randr.so.0": "libxcb-randr0",
    "libxcb-render-util.so.0": "libxcb-render-util0",
    "libxcb-shape.so.0": "libxcb-shape0",
    "libxcb-xfixes.so.0": "libxcb-xfixes0",
    "libxcb-sync.so.1": "libxcb-sync1",
    "libxcb-xkb.so.1": "libxcb-xkb1",
    "libxcb-render.so.0": "libxcb-render0",
    "libxcb-shm.so.0": "libxcb-shm0",
    "libxcb-util.so.1": "libxcb-util1",
    "libxcb-dri2.so.0": "libxcb-dri2-0",
    "libxcb-dri3.so.0": "libxcb-dri3-0",
    "libxcb-glx.so.0": "libxcb-glx0",
    "libxcb-present.so.0": "libxcb-present0",
    "libX11-xcb.so.1": "libx11-xcb1",
    "libxkbcommon.so.0": "libxkbcommon0",
    "libX11.so.6": "libx11-6",
    "libXext.so.6": "libxext6",
    "libXrender.so.1": "libxrender1",
    "libxcb.so.1": "libxcb1",
    "libXau.so.6": "libxau6",
    "libXdmcp.so.6": "libxdmcp6",
    "libbsd.so.0": "libbsd0",
    "libmd.so.0": "libmd0",
}


def skipped(name):
    return any(name.startswith(s) for s in SKIP_PREFIXES)


def wanted(name):
    return any(name.startswith(s) for s in WANT_PREFIXES)


def ldd(path):
    try:
        out = subprocess.check_output(["ldd", path], stderr=subprocess.DEVNULL, text=True)
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if "=>" not in line:
            continue
        name, rest = line.split("=>", 1)
        name = name.strip()
        rest = rest.strip()
        if skipped(name):
            continue
        if "not found" in rest:
            rows.append((name, None))
        else:
            lib = rest.split()[0]
            if lib.startswith("/"):
                rows.append((name, lib))
    return rows


def iter_elfs(root):
    for dirpath, _, files in os.walk(root):
        for fname in files:
            path = os.path.join(dirpath, fname)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            yield path


def download_deb(pkg, work):
    subprocess.check_call(
        ["apt-get", "download", pkg],
        cwd=work,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    debs = glob.glob(os.path.join(work, pkg + "_*.deb"))
    if not debs:
        raise RuntimeError("no deb for " + pkg)
    dest = os.path.join(work, "extracted-" + pkg)
    os.makedirs(dest, exist_ok=True)
    subprocess.check_call(["dpkg-deb", "-x", debs[0], dest])
    found = []
    for dirpath, _, files in os.walk(dest):
        for fname in files:
            if ".so" in fname:
                found.append(os.path.join(dirpath, fname))
    return found


def copy_lib(src, internal):
    base = os.path.basename(src)
    dest = os.path.join(internal, base)
    if os.path.lexists(dest):
        return dest
    if os.path.islink(src):
        target = os.path.realpath(src)
        tbase = os.path.basename(target)
        tdest = os.path.join(internal, tbase)
        if not os.path.exists(tdest):
            shutil.copy2(target, tdest)
        os.symlink(tbase, dest)
        print("link", base, "->", tbase)
        return dest
    shutil.copy2(src, dest)
    print("copy", src, "->", dest)
    return dest


def write_launcher(app_dir):
    elf = os.path.join(app_dir, "CommTool")
    real = os.path.join(app_dir, "CommTool.bin")
    if os.path.isfile(elf):
        with open(elf, "rb") as f:
            magic = f.read(4)
        if magic == b"\x7fELF":
            os.replace(elf, real)
            os.chmod(real, 0o755)
    script = os.path.join(app_dir, "CommTool")
    body = """#!/usr/bin/env bash
HERE="$(cd "$(dirname "$0")" && pwd)"
export LD_LIBRARY_PATH="$HERE/_internal${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
  if [ -S /tmp/.X11-unix/X0 ]; then
    export DISPLAY=:0
  fi
fi
exec "$HERE/CommTool.bin" "$@"
"""
    with open(script, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    os.chmod(script, 0o755)
    print("launcher", script)
    old_wrap = os.path.join(app_dir, "run.sh")
    if os.path.lexists(old_wrap):
        if os.path.islink(old_wrap) or os.path.isfile(old_wrap):
            os.remove(old_wrap)
        os.symlink("CommTool", old_wrap)


def main():
    app_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/kylin/Desktop/SerialTool/dist/CommTool"
    internal = os.path.join(app_dir, "_internal")
    work = "/tmp/commtool-syslibs"
    os.makedirs(work, exist_ok=True)

    pending = {}
    for elf in iter_elfs(app_dir):
        for name, path in ldd(elf):
            if path is None or wanted(name):
                pending.setdefault(name, path)

    for name, path in sorted(pending.items()):
        if path:
            copy_lib(path, internal)
            continue
        pkg = DEB_FOR_LIB.get(name)
        if not pkg:
            print("MISSING no package map:", name)
            continue
        print("download", pkg, "for", name)
        try:
            files = download_deb(pkg, work)
        except Exception as e:
            print("download failed", pkg, e)
            continue
        for src in files:
            if os.path.basename(src).startswith(name.split(".so")[0]):
                copy_lib(src, internal)

    # Second pass: new copies may pull more deps
    for _ in range(3):
        extra = {}
        for elf in iter_elfs(internal):
            for name, path in ldd(elf):
                dest = os.path.join(internal, os.path.basename(name))
                if os.path.lexists(dest):
                    continue
                if path is None or wanted(name):
                    extra[name] = path
        if not extra:
            break
        for name, path in extra.items():
            if path:
                copy_lib(path, internal)
            elif name in DEB_FOR_LIB:
                try:
                    files = download_deb(DEB_FOR_LIB[name], work)
                    for src in files:
                        if os.path.basename(src).startswith(name.split(".so")[0]):
                            copy_lib(src, internal)
                except Exception as e:
                    print("download failed", name, e)
            else:
                print("STILL MISSING", name)

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = internal + ((":" + env["LD_LIBRARY_PATH"]) if env.get("LD_LIBRARY_PATH") else "")
    plugin = os.path.join(internal, "PyQt5/Qt5/plugins/platforms/libqxcb.so")
    print("--- libqxcb after bundle ---")
    out = subprocess.check_output(["ldd", plugin], env=env, text=True)
    missing = [ln for ln in out.splitlines() if "not found" in ln]
    print(out)
    if missing:
        print("UNRESOLVED:")
        print("\n".join(missing))
        sys.exit(1)
    write_launcher(app_dir)
    print("OK")


if __name__ == "__main__":
    main()
