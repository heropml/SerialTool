# -*- coding: utf-8 -*-
"""把 icon_src.jpg / png 转成多分辨率 icon.ico（自动抠掉纯色背景）"""
import os
import sys
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))

src = None
# 优先用原图；如果原图不在了，回退到上次生成的预览 (已透明)
for name in ("icon_src.png", "icon_src.jpg", "icon_src.jpeg",
             "icon_src.bmp", "icon_preview.png"):
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        src = p
        break

if not src:
    print("找不到 icon_src.png / icon_src.jpg / icon_preview.png")
    sys.exit(1)


def remove_background(img: Image.Image, threshold: int = 32, feather: int = 1) -> Image.Image:
    """
    从四个角洪水填充，识别和角同色调的连通区域作为背景，把这些像素 alpha 设为 0。
    - threshold: 颜色距离容差，越大抠得越彻底但可能误伤
    - feather: 边缘羽化像素数，让边缘过渡更柔和
    角色内部的白色（如眼睛高光、牙齿）因为不和四角连通，不会被抠掉。
    """
    img = img.convert("RGBA")
    w, h = img.size

    # 在 RGB 拷贝上做 flood fill 找背景区域
    mask_img = img.convert("RGB").copy()
    SENTINEL = (255, 0, 254)  # 不太可能出现在真实图里
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if mask_img.getpixel(corner) != SENTINEL:
            ImageDraw.floodfill(mask_img, corner, SENTINEL, thresh=threshold)

    # 构造 alpha mask（白=保留，黑=透明）
    alpha = Image.new("L", (w, h), 255)
    a_px = alpha.load()
    m_px = mask_img.load()
    for y in range(h):
        for x in range(w):
            if m_px[x, y] == SENTINEL:
                a_px[x, y] = 0

    # 边缘羽化：让 alpha 边缘平滑过渡，避免锯齿
    if feather > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius=feather))

    img.putalpha(alpha)
    return img


img = Image.open(src).convert("RGBA")
w, h = img.size
print(f"源图: {src}, 尺寸 {w}x{h}")

# 居中裁剪成方形，避免 ICO 拉伸变形
side = min(w, h)
left = (w - side) // 2
top = (h - side) // 2
img = img.crop((left, top, left + side, top + side))

# 抠背景
print("正在抠除背景…")
img = remove_background(img, threshold=32, feather=1)

out = os.path.join(HERE, "icon.ico")
sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(out, format="ICO", sizes=sizes)
print(f"已生成: {out}, 包含尺寸 {sizes}")

# 顺便保存一份 PNG 给参考（可用于其他地方）
img.resize((256, 256), Image.LANCZOS).save(
    os.path.join(HERE, "icon_preview.png"), format="PNG")
print(f"预览: {os.path.join(HERE, 'icon_preview.png')}")
