# -*- coding: utf-8 -*-
"""跨平台字体统一入口。

历史上各处硬编码了 Windows 字体（Segoe UI / Microsoft YaHei / Consolas），
这些在 macOS / Linux 上并不存在，会触发 Qt 字体告警并回退到不理想的字体。
本模块按平台给出等价字体，并提供：

- ``ui_font(size, bold)`` / ``mono_font(size)``：替换代码里的 ``QFont("Segoe UI", ...)``；
- ``install_font_substitutions()``：注册 QFont 替换表，让样式表里 ``font-family: 'Segoe UI'``
  这类字符串也自动重映射到本平台字体（无需逐条改样式表）。
"""
import sys

from PyQt5.QtGui import QFont

if sys.platform == "darwin":          # macOS
    UI_FAMILY = "PingFang SC"         # 系统中文字体，西文字形也干净；Qt 能可靠按名解析
    MONO_FAMILY = "Menlo"             # 系统等宽字体
elif sys.platform == "win32":         # Windows —— 保持原观感不变
    UI_FAMILY = "Segoe UI"
    MONO_FAMILY = "Consolas"
else:                                  # Linux / 其它
    UI_FAMILY = "Noto Sans CJK SC"
    MONO_FAMILY = "DejaVu Sans Mono"

# 代码里出现过的、需要被重映射到本平台字体的 Windows 字体名
_UI_ALIASES = ("Segoe UI", "Microsoft YaHei", "Microsoft YaHei UI", "SF Pro Display")
_MONO_ALIASES = ("Consolas",)


def ui_font(size: int = 10, bold: bool = False) -> QFont:
    """界面文本字体。"""
    f = QFont(UI_FAMILY, size)
    if bold:
        f.setWeight(QFont.DemiBold)
    return f


def mono_font(size: int = 10) -> QFont:
    """等宽字体（接收/发送数据区用）。"""
    return QFont(MONO_FAMILY, size)


def localize_qss(qss: str) -> str:
    """把样式表里硬编码的 Windows 字体名换成本平台字体。

    字体替换表（``install_font_substitutions``）能让 'Segoe UI' 最终落到正确字体，
    但 Qt 解析样式表时仍会因「找不到 Segoe UI」打印一次告警。在样式表入口跑一遍
    本函数，直接把字符串改掉，告警也随之消除。Windows 上原样返回。
    """
    if sys.platform == "win32":
        return qss
    return (qss.replace("'Segoe UI'", f"'{UI_FAMILY}'")
               .replace("'Consolas'", f"'{MONO_FAMILY}'"))


def install_font_substitutions() -> None:
    """注册字体替换：Windows 字体名 → 本平台字体。

    必须在 QApplication 创建后、加载样式表前调用一次。Qt 在解析样式表的
    ``font-family`` 或构造找不到的 ``QFont`` 时，会查这张替换表，从而把
    残留的 'Segoe UI' / 'Consolas' 自动落到 PingFang SC / Menlo 等。
    """
    if sys.platform == "win32":
        return  # Windows 上这些字体本就存在，无需替换
    for alias in _UI_ALIASES:
        QFont.insertSubstitution(alias, UI_FAMILY)
    for alias in _MONO_ALIASES:
        QFont.insertSubstitution(alias, MONO_FAMILY)
