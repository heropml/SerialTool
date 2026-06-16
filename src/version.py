# -*- coding: utf-8 -*-
"""
NetworkTool 版本号 — 单点真源 (Single Source of Truth)。

main.py            → import version, 状态栏右下角显示
build_installer.bat → findstr 解析此文件, 传给 ISCC /DMyAppVersion=...

只在这里改版本号，重新打包即可全部同步。
"""
__version__ = "1.0.5"
