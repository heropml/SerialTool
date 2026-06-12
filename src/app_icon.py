# -*- coding: utf-8 -*-
"""资源路径（兼容 PyInstaller）+ 内嵌应用图标。"""
import os
import sys
from PyQt5.QtGui import QIcon


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


from icon_data import ICON_B64 as _APP_ICON_B64


def get_app_icon():
    """从嵌入的 base64 数据加载 QIcon（缓存一次）"""
    cache = globals().get("_APP_ICON_CACHE")
    if cache is not None:
        return cache
    import base64 as _b64
    from PyQt5.QtGui import QPixmap
    px = QPixmap()
    px.loadFromData(_b64.b64decode(_APP_ICON_B64), b"PNG")
    icon = QIcon(px)
    globals()["_APP_ICON_CACHE"] = icon
    return icon
