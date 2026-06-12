# -*- coding: utf-8 -*-
"""主题 / 配色：文本角色标记、THEMES、chrome 派生、COLOR_* 常量。"""
from PyQt5.QtGui import QTextFormat


# 数据区文本段角色标记 — 切主题时据此把历史文字重涂成新主题对应色（否则浅↔深切换看不见）
ROLE_PROP = QTextFormat.UserProperty + 1
ROLE_TS, ROLE_RX, ROLE_TX = 1, 2, 3

# ============== iOS 调色板 ==============
# ============== 主题：整体配色 ==============
# 每个主题指定 mode (light/dark) → 决定 chrome (侧边栏卡片/按钮/输入框等) 用哪套色板；
# bg/fg = 数据区背景 + 默认文字; tx = 发送(→)颜色; ts = 时间戳颜色
THEMES = {
    "default":     {"label": "Default",         "mode": "light", "bg": "#FAFAFC", "fg": "#1C1C1E", "tx": "#007AFF", "ts": "#6E6E73"},
    "dark":        {"label": "Dark",            "mode": "dark",  "bg": "#1E1E1E", "fg": "#D4D4D4", "tx": "#569CD6", "ts": "#808080"},
    "one_half_lt": {"label": "One Half Light",  "mode": "light", "bg": "#FAFAFA", "fg": "#383A42", "tx": "#0184BC", "ts": "#A0A1A7"},
    "one_half_dk": {"label": "One Half Dark",   "mode": "dark",  "bg": "#282C34", "fg": "#DCDFE4", "tx": "#61AFEF", "ts": "#5C6370"},
    "solar_lt":    {"label": "Solarized Light", "mode": "light", "bg": "#FDF6E3", "fg": "#586E75", "tx": "#268BD2", "ts": "#93A1A1"},
    "solar_dk":    {"label": "Solarized Dark",  "mode": "dark",  "bg": "#002B36", "fg": "#839496", "tx": "#268BD2", "ts": "#586E75"},
    "tango_dk":    {"label": "Tango Dark",      "mode": "dark",  "bg": "#2E3436", "fg": "#D3D7CF", "tx": "#729FCF", "ts": "#888A85"},
    "campbell":    {"label": "Campbell",        "mode": "dark",  "bg": "#0C0C0C", "fg": "#CCCCCC", "tx": "#3B78FF", "ts": "#767676"},
    "ubuntu":      {"label": "Ubuntu",          "mode": "dark",  "bg": "#300A24", "fg": "#EEEEEC", "tx": "#3465A4", "ts": "#888A85"},
}
THEME_DEFAULT = "default"

def _mix(c1: str, c2: str, ratio: float) -> str:
    """混色：c1 朝 c2 偏移 ratio (0~1)，返回 #RRGGBB"""
    h1, h2 = c1.lstrip("#"), c2.lstrip("#")
    r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
    r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
    r = round(r1 + (r2 - r1) * ratio)
    g = round(g1 + (g2 - g1) * ratio)
    b = round(b1 + (b2 - b1) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


def chrome_for(theme_id: str) -> dict:
    """根据主题 bg/fg/tx 派生整套 chrome 色 — 每个主题的 chrome 都是自己色调。
    Light 主题: 窗口比卡片稍深 → 卡片浮在背景上的标准 iOS/Material 观感。
    Dark 主题: 窗口 = theme.bg, 卡片比窗口稍亮（lighten）, 营造层次。
    """
    t = THEMES.get(theme_id, THEMES[THEME_DEFAULT])
    is_dark = t.get("mode") == "dark"
    bg = t["bg"]; fg = t["fg"]; accent = t["tx"]

    if is_dark:
        window_bg = bg
        card_bg = _mix(bg, "#FFFFFF", 0.07)
        # ghost / input 系列要比 card 更亮一截 — 否则按钮跟卡片同色, 视觉上"只有字"
        input_bg = _mix(bg, "#FFFFFF", 0.13)
        input_focus_bg = _mix(bg, "#FFFFFF", 0.18)
        ghost_bg = _mix(bg, "#FFFFFF", 0.14)
        ghost_hover = _mix(bg, "#FFFFFF", 0.22)
        ghost_pressed = _mix(bg, "#FFFFFF", 0.30)
        combo_dropdown_bg = _mix(bg, "#FFFFFF", 0.13)
        separator = _mix(bg, "#FFFFFF", 0.18)
        scrollbar = _mix(bg, "#FFFFFF", 0.28)
        scrollbar_hover = _mix(bg, "#FFFFFF", 0.48)
        title_btn_hover = "rgba(255, 255, 255, 24)"
        title_combo_hover = "rgba(255, 255, 255, 18)"
    else:
        # Light 主题：窗口/数据区都用 theme.bg（cream/grey 等主题色），卡片**永远纯白**
        # 这样 cards 在 themed bg 上明显浮起来 — 视觉层次：cards 白 > 窗口 themed > 数据区 themed
        window_bg = bg
        card_bg = "#FFFFFF"
        input_bg = _mix(bg, "#000000", 0.05)
        input_focus_bg = "#FFFFFF"
        ghost_bg = _mix(bg, "#000000", 0.05)
        ghost_hover = _mix(bg, "#000000", 0.11)
        ghost_pressed = _mix(bg, "#000000", 0.18)
        combo_dropdown_bg = "#FFFFFF"
        separator = _mix(bg, "#000000", 0.10)
        scrollbar = _mix(bg, "#000000", 0.20)
        scrollbar_hover = _mix(bg, "#000000", 0.40)
        title_btn_hover = "rgba(0, 0, 0, 18)"
        title_combo_hover = "rgba(0, 0, 0, 14)"

    return {
        "window_bg":         window_bg,
        "card_bg":           card_bg,
        "text":              fg,
        "text_sec":          _mix(fg, bg, 0.40),
        "separator":         separator,
        "input_bg":          input_bg,
        "input_focus_bg":    input_focus_bg,
        "ghost_bg":          ghost_bg,
        "ghost_hover":       ghost_hover,
        "ghost_pressed":     ghost_pressed,
        "combo_dropdown_bg": combo_dropdown_bg,
        "scrollbar":         scrollbar,
        "scrollbar_hover":   scrollbar_hover,
        "accent":            accent,
        "accent_hover":      _mix(accent, "#FFFFFF", 0.20),
        "accent_pressed":    _mix(accent, "#000000", 0.20),
        "danger":            "#FF453A" if is_dark else "#FF3B30",
        "danger_hover":      "#FF6961" if is_dark else "#FF5147",
        "title_btn_hover":   title_btn_hover,
        "title_combo_hover": title_combo_hover,
    }

COLOR_BG = "#F2F2F7"
COLOR_CARD = "#FFFFFF"
COLOR_TEXT = "#1C1C1E"
COLOR_TEXT_SECONDARY = "#6E6E73"
COLOR_BLUE = "#007AFF"
COLOR_BLUE_PRESSED = "#0051D5"
COLOR_GREEN = "#34C759"
COLOR_RED = "#FF3B30"
COLOR_SEPARATOR = "#E5E5EA"
COLOR_GRAY_LIGHT = "#F2F2F7"


