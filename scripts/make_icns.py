#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 assets/icon.ico 生成 macOS 用的 .icns 图标。

用法: python3 scripts/make_icns.py [输出路径]
默认输出 build_macos/CommTool.icns。依赖 Pillow + 系统自带 iconutil（macOS）。
"""
import os
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "icon.ico")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build_macos", "CommTool.icns")


def _load_largest(path: str) -> Image.Image:
    """载入 .ico 中最大的一帧（icon.ico 最大 256×256）。"""
    img = Image.open(path)
    try:
        img.size = max(img.ico.sizes())  # type: ignore[attr-defined]
    except Exception:
        pass
    return img.convert("RGBA")


def main():
    if not os.path.exists(SRC):
        sys.exit(f"找不到图标源: {SRC}")
    base = _load_largest(SRC)

    iconset = os.path.join(os.path.dirname(OUT) or ".", "CommTool.iconset")
    os.makedirs(iconset, exist_ok=True)
    # macOS 标准 iconset：每个尺寸提供 1x 与 @2x（高分屏）
    for size in (16, 32, 128, 256, 512):
        base.resize((size, size), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{size}x{size}.png"))
        base.resize((size * 2, size * 2), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{size}x{size}@2x.png"))

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", OUT], check=True)
    print(f"✅ 生成图标: {OUT}")


if __name__ == "__main__":
    main()
