# -*- coding: utf-8 -*-
"""
SerialTool - iOS 风格串口调试工具
PyQt5 + pyserial
"""
import codecs
import json
import os
import sys
import time
from datetime import datetime

# 单点真源版本号，与 SerialTool.iss / build_installer.bat 同步
try:
    from version import __version__ as APP_VERSION
except Exception:
    APP_VERSION = "0.0.0"

import serial
import serial.tools.list_ports
from PyQt5.QtCore import (Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation,
                          QEasingCurve, QRect, QSize, QPoint, pyqtProperty, QSettings,
                          QEvent)
from PyQt5.QtGui import (QFont, QColor, QPainter, QPen, QBrush, QIcon,
                         QTextCursor, QTextCharFormat, QFontMetrics, QTextFormat)
from PyQt5.QtWidgets import (QApplication, QWidget, QMainWindow, QLabel,
                             QPushButton, QComboBox, QTextEdit, QLineEdit,
                             QCheckBox, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QSplitter, QScrollArea, QFrame, QFileDialog,
                             QMessageBox, QDialog, QGraphicsDropShadowEffect,
                             QSizePolicy, QSpacerItem, QStatusBar,
                             QSystemTrayIcon, QMenu, QAction, QColorDialog, QInputDialog,
                             QListWidget, QListWidgetItem)


# ============== 资源路径 (兼容 PyInstaller) ==============
def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ============== 嵌入式图标 ==============
# base64 数据单独放在 icon_data.py 里。运行时无法通过替换外部 icon.ico 改变运行时图标。
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


# ============== 翻译表 ==============
TR = {
    "zh": {
        "app_title": "串口工具",
        "lang_zh": "中文",
        "lang_en": "English",
        "lang_tw": "繁體中文",
        "data_area": "数据区",
        "legend_rx": "← 收",
        "legend_tx": "→ 发",
        "to_bottom": "↓ 最新",
        "hex_display": "HEX 显示",
        "encoding": "字符编码",
        "encoding_auto": "自动",
        "theme": "主题",
        # 主题名 — 国际通用术语（Solarized/Tango/Campbell/Ubuntu）保留原名，仅翻译 Light/Dark 后缀
        "theme_default": "默认",
        "theme_dark": "暗色",
        "theme_one_half_lt": "One Half 浅色",
        "theme_one_half_dk": "One Half 深色",
        "theme_solar_lt": "Solarized 浅色",
        "theme_solar_dk": "Solarized 深色",
        "theme_tango_dk": "Tango 深色",
        "theme_campbell": "Campbell",
        "theme_ubuntu": "Ubuntu",
        "auto_wrap": "自动换行",
        "show_timestamp": "显示时间戳",
        "packet_split": "时间分包",
        "line_split": "换行分包",
        "nl_auto": "自动",
        "timeout": "超时",
        "real_time_log": "实时记录",
        "log_split_none": "不分包",
        "log_path_idle": "（未记录）",
        "log_split_tip": "实时记录按文件大小分包：写到设定大小就切到新文件(原名加 _001/_002…)。\n可手填自定义，如 3M / 500K；选「不分包」则单文件不限。",
        "max_lines": "最大行数",
        "save": "保存",
        "ctx_copy": "复制",
        "ctx_select_all": "全选",
        "clear": "清空",
        "font_dec": "字号减小",
        "font_inc": "字号增大",
        "serial_settings": "串口设置",
        "port": "端口",
        "baud_rate": "波特率",
        "data_bits": "数据位",
        "parity": "校验",
        "stop_bits": "停止位",
        "open_serial": "打开串口",
        "close_serial": "关闭串口",
        "no_ports": "(无可用串口)",
        "send_area": "发送区",
        "hex_send": "HEX 发送",
        "append_newline": "追加换行",
        "period": "定时",
        "checksum": "校验",
        "ck_none": "无",
        "ck_sum": "和校验",
        "ck_neg_sum": "累加和取反",
        "ck_xor": "异或",
        "ck_crc8": "CRC8",
        "ck_modbus": "ModbusCRC16",
        "ck_ccitt": "CCITT-CRC16",
        "ck_crc32": "CRC32",
        "ck_add16": "ADD16",
        "ck_mobus": "MOBUS",
        "send_placeholder": "在这里输入要发送的内容...   HEX 模式示例: AA BB CC 01 02 (空格可省)",
        "multi_send": "多条发送",
        "multi_send_title": "多条发送",
        "ms_add": "＋ 添加一条",
        "ms_cycle": "▶ 循环",
        "ms_cycle_stop": "■ 停止",
        "ms_send_one": "发送",
        "ms_nl_none": "无",
        "ms_placeholder": "数据（HEX 或文本）",
        "ms_none_checked": "请先勾选要循环发送的条目",
        "ms_hint": "左侧管理分组；每行可独立设 名称 / 延时 / HEX / 换行 / 校验。勾选多条 → 循环发送：发完每条等其「延时」再发下一条，到底再从头。",
        "ms_name_ph": "名称",
        "ms_delay_tip": "延时(ms)：发完本条后等这么久再发下一条",
        "kw_highlight": "关键字高亮",
        "kw_title": "关键字高亮",
        "kw_add": "＋ 添加关键字",
        "kw_mode_bg": "背景",
        "kw_mode_fg": "文字",
        "kw_color": "选择高亮颜色",
        "kw_placeholder": "关键字（区分大小写）",
        "kw_hint": "数据区匹配到关键字就按设定颜色高亮（区分大小写）。每条可限定 收 / 发 / 收发。",
        "kw_scope_both": "收发",
        "kw_scope_rx": "收",
        "kw_scope_tx": "发",
        "filter_highlight": "只显高亮行",
        "kw_default_group": "默认",
        "kw_group_off": "（关闭）",
        "kw_group_label": "分组",
        "kw_new_group": "新建",
        "kw_rename_group": "重命名",
        "kw_del_group": "删除",
        "kw_group_name_prompt": "分组名称：",
        "kw_group_min": "至少保留一个分组",
        "kw_new_group_default": "新分组",
        "kw_group_tip": "双击分组名可改名",
        "read_file": "读取文件",
        "send_btn": "发  送",
        "state_closed": "● 未打开",
        "dlg_save_data": "保存接收数据",
        "dlg_log_path": "选择日志保存路径",
        "dlg_load_file": "读取发送内容",
        "filter_text": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_text_save": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_all": "All Files (*)",
        "log_header": "\n========== 日志开始 {time} ==========\n",
        "log_footer": "\n========== 日志结束 {time} ==========\n",
        "log_started": "实时记录已开启",
        "log_stopped": "实时记录已停止",
        "saved_to": "已保存到 {path}",
        "err_no_port": "请先选择串口",
        "err_bad_baud": "波特率无效",
        "err_open_failed": "打开失败: {e}",
        "err_serial": "串口错误: {e}",
        "err_serial_not_open": "串口未打开",
        "err_hex_odd": "HEX 长度必须为偶数",
        "err_hex_bad": "HEX 格式错误: {e}",
        "err_hex_invalid_chars": "非法字符 {chars}",
        "err_send_failed": "发送失败: {e}",
        "err_checksum": "校验计算失败: {e}",
        "err_save_failed": "保存失败: {e}",
        "err_read_failed": "读取失败: {e}",
        "err_period_bad": "周期错误: {e}",
        "err_min_period": "周期最小 10ms",
        "err_open_log": "打开失败: {e}",
        "err_log_write": "写日志失败: {e}",
        "err_rx": "接收处理出错: {e}",
        "font_size_msg": "字号: {size} pt",
        "close_prompt": "你想怎么关闭程序？",
        "close_minimize": "最小化到托盘",
        "close_quit": "退出程序",
        "close_cancel": "取消",
        "tray_show": "显示窗口",
        "tray_quit": "退出",
        "tray_minimized": "{app} 已最小化到系统托盘",
        # —— 鼠标悬停说明 ——
        "hex_display_tip": "勾选后数据按 16 进制显示\n关闭：按文本/ASCII 显示",
        "encoding_tip": "字符编码（影响 RX 解码 / TX 编码 / 文件加载）\n自动：UTF-8 优先，乱码自动回退 GBK\n指定 UTF-8/GBK/GB2312/Big5 等则严格按选定编码",
        "theme_tip": "数据区配色方案（终端风格）\n切换后仅影响新到的数据，历史不重涂\n想全部刷新点「清空」即可",
        "auto_wrap_tip": "行太长自动折行\n关闭：超出宽度需横向滚动查看",
        "show_timestamp_tip": "每个数据块前显示 [年/月/日 时:分:秒 毫秒] 时间戳和 ←/→ 收发方向箭头",
        "packet_split_tip": "收到数据后超过下方「超时」时间无新数据就开新行\n用于把短时间到达的连续数据合并显示",
        "timeout_tip": "时间分包的间隔阈值（毫秒）\n两次接收间隔超过此值就开新行",
        "line_split_tip": "按换行符自动分行显示\n可选自动识别 / CRLF / LF / CR",
        "real_time_log_tip": "收发数据实时追加保存到日志文件\n显示什么就记什么(含时间戳/箭头/HEX)，关闭后停止写入",
        "max_lines_tip": "数据区最多保留的行数\n超出会丢弃最早的（防止内存涨爆）",
        "hex_send_tip": "把输入框的 16 进制字符串按字节发送（如 AA BB CC）\n关闭：按文本原样发送",
        "append_newline_tip": "每次发送后自动追加换行符\n可选 CRLF / LF / CR",
        "period_tip": "按右侧间隔（毫秒）周期性自动发送当前内容",
        "checksum_tip": "发送前在末尾追加校验字节\n支持 和校验/CRC8/MOBUS/CRC16/CRC32 等多种算法",
    },
    "en": {
        "app_title": "SerialTool",
        "lang_zh": "中文",
        "lang_en": "English",
        "lang_tw": "繁體中文",
        "data_area": "Data",
        "legend_rx": "← RX",
        "legend_tx": "→ TX",
        "to_bottom": "↓ Latest",
        "hex_display": "HEX View",
        "encoding": "Encoding",
        "encoding_auto": "Auto",
        "theme": "Theme",
        # English: keep original recognized theme names
        "theme_default": "Default",
        "theme_dark": "Dark",
        "theme_one_half_lt": "One Half Light",
        "theme_one_half_dk": "One Half Dark",
        "theme_solar_lt": "Solarized Light",
        "theme_solar_dk": "Solarized Dark",
        "theme_tango_dk": "Tango Dark",
        "theme_campbell": "Campbell",
        "theme_ubuntu": "Ubuntu",
        "auto_wrap": "Word Wrap",
        "show_timestamp": "Timestamp",
        "packet_split": "Packet Split",
        "line_split": "Line Split",
        "nl_auto": "Auto",
        "timeout": "Timeout",
        "real_time_log": "Log to File",
        "log_split_none": "No split",
        "log_path_idle": "(not logging)",
        "log_split_tip": "Split the log file by size: when it reaches the set size, a new file is started (original name + _001/_002…).\nType a custom value like 3M / 500K; pick \"No split\" for a single unbounded file.",
        "max_lines": "Max Lines",
        "save": "Save",
        "ctx_copy": "Copy",
        "ctx_select_all": "Select All",
        "clear": "Clear",
        "font_dec": "Decrease Font",
        "font_inc": "Increase Font",
        "serial_settings": "Serial Setup",
        "port": "Port",
        "baud_rate": "Baud Rate",
        "data_bits": "Data Bits",
        "parity": "Parity",
        "stop_bits": "Stop Bits",
        "open_serial": "Open Port",
        "close_serial": "Close Port",
        "no_ports": "(no port available)",
        "send_area": "Send",
        "hex_send": "HEX Send",
        "append_newline": "Append CRLF",
        "period": "Auto",
        "checksum": "Checksum",
        "ck_none": "None",
        "ck_sum": "ADD8",
        "ck_neg_sum": "~ADD8",
        "ck_xor": "XOR8",
        "ck_crc8": "CRC8",
        "ck_modbus": "ModbusCRC16",
        "ck_ccitt": "CCITT-CRC16",
        "ck_crc32": "CRC32",
        "ck_add16": "ADD16",
        "ck_mobus": "MOBUS",
        "send_placeholder": "Type data to send...   HEX example: AA BB CC 01 02 (spaces optional)",
        "multi_send": "Multi-Send",
        "multi_send_title": "Multi-Send",
        "ms_add": "＋ Add Row",
        "ms_cycle": "▶ Cycle",
        "ms_cycle_stop": "■ Stop",
        "ms_send_one": "Send",
        "ms_nl_none": "None",
        "ms_placeholder": "Data (HEX or text)",
        "ms_none_checked": "Check at least one item to cycle-send",
        "ms_hint": "Manage groups on the left; each row has its own name / delay / HEX / newline / checksum. Check items → Cycle Send: after each command waits its delay, then loops.",
        "ms_name_ph": "Name",
        "ms_delay_tip": "Delay (ms): wait this long after this command before the next",
        "kw_highlight": "Highlight",
        "kw_title": "Keyword Highlight",
        "kw_add": "＋ Add Keyword",
        "kw_mode_bg": "Background",
        "kw_mode_fg": "Text",
        "kw_color": "Pick highlight color",
        "kw_placeholder": "Keyword (case-sensitive)",
        "kw_hint": "Matching text in the data area is highlighted (case-sensitive). Each rule can target RX / TX / both.",
        "kw_scope_both": "RX+TX",
        "kw_scope_rx": "RX",
        "kw_scope_tx": "TX",
        "filter_highlight": "Matches only",
        "kw_default_group": "Default",
        "kw_group_off": "(Off)",
        "kw_group_label": "Group",
        "kw_new_group": "New",
        "kw_rename_group": "Rename",
        "kw_del_group": "Delete",
        "kw_group_name_prompt": "Group name:",
        "kw_group_min": "Keep at least one group",
        "kw_new_group_default": "New Group",
        "kw_group_tip": "Double-click a group to rename",
        "read_file": "Load File",
        "send_btn": "Send",
        "state_closed": "● Disconnected",
        "dlg_save_data": "Save received data",
        "dlg_log_path": "Choose log file path",
        "dlg_load_file": "Load file as send content",
        "filter_text": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_text_save": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_all": "All Files (*)",
        "log_header": "\n========== Log started {time} ==========\n",
        "log_footer": "\n========== Log ended {time} ==========\n",
        "log_started": "Logging started",
        "log_stopped": "Logging stopped",
        "saved_to": "Saved to {path}",
        "err_no_port": "Select a port first",
        "err_bad_baud": "Invalid baud rate",
        "err_open_failed": "Open failed: {e}",
        "err_serial": "Serial error: {e}",
        "err_serial_not_open": "Port not opened",
        "err_hex_odd": "HEX length must be even",
        "err_hex_bad": "HEX format error: {e}",
        "err_hex_invalid_chars": "invalid character(s) {chars}",
        "err_send_failed": "Send failed: {e}",
        "err_checksum": "Checksum failed: {e}",
        "err_save_failed": "Save failed: {e}",
        "err_read_failed": "Load failed: {e}",
        "err_period_bad": "Period error: {e}",
        "err_min_period": "Min period 10ms",
        "err_open_log": "Open failed: {e}",
        "err_log_write": "Log write failed: {e}",
        "err_rx": "RX error: {e}",
        "font_size_msg": "Font size: {size} pt",
        "close_prompt": "How do you want to close?",
        "close_minimize": "Minimize to Tray",
        "close_quit": "Quit",
        "close_cancel": "Cancel",
        "tray_show": "Show Window",
        "tray_quit": "Quit",
        "tray_minimized": "{app} minimized to system tray",
        # —— hover tooltips ——
        "hex_display_tip": "Display incoming bytes as hex.\nOff: show as text/ASCII",
        "encoding_tip": "Character encoding for RX decoding / TX encoding / file load.\nAuto: UTF-8 first, fall back to GBK on mojibake.\nOr pick UTF-8 / GBK / GB2312 / Big5 etc. for strict decoding.",
        "theme_tip": "Color scheme for the data area (terminal-style).\nOnly newly received data is recolored; history keeps its colors.\nClear the data area to apply the new theme to everything.",
        "auto_wrap_tip": "Wrap long lines automatically.\nOff: scroll horizontally",
        "show_timestamp_tip": "Prefix each block with [YYYY/MM/DD HH:MM:SS ms] timestamp and ←/→ direction arrow",
        "packet_split_tip": "Start a new block when no data arrives for longer than the timeout below.\nMerges burst data on the same line",
        "timeout_tip": "Time-split threshold (ms).\nNew block when receive gap exceeds this",
        "line_split_tip": "Split on newline characters.\nAuto / CRLF / LF / CR",
        "real_time_log_tip": "Append both RX and TX data to a log file in real time.\nWYSIWYG: timestamp/arrow/HEX preserved. Off to stop writing.",
        "max_lines_tip": "Maximum lines kept in the data area.\nOldest are dropped (prevents memory bloat)",
        "hex_send_tip": "Send input as raw bytes parsed from a hex string (e.g. AA BB CC).\nOff: send as text",
        "append_newline_tip": "Append a newline after each send.\nCRLF / LF / CR",
        "period_tip": "Send the content periodically at the interval (ms) on the right",
        "checksum_tip": "Append a checksum at the end of each send.\nADD8 / XOR8 / CRC8 / MOBUS / CRC16 / CRC32 ...",
    },
    "zh_tw": {
        "app_title": "串口工具",
        "lang_zh": "中文",
        "lang_en": "English",
        "lang_tw": "繁體中文",
        "data_area": "資料區",
        "legend_rx": "← 收",
        "legend_tx": "→ 發",
        "to_bottom": "↓ 最新",
        "hex_display": "HEX 顯示",
        "encoding": "字元編碼",
        "encoding_auto": "自動",
        "theme": "主題",
        "theme_default": "預設",
        "theme_dark": "暗色",
        "theme_one_half_lt": "One Half 淺色",
        "theme_one_half_dk": "One Half 深色",
        "theme_solar_lt": "Solarized 淺色",
        "theme_solar_dk": "Solarized 深色",
        "theme_tango_dk": "Tango 深色",
        "theme_campbell": "Campbell",
        "theme_ubuntu": "Ubuntu",
        "auto_wrap": "自動換行",
        "show_timestamp": "顯示時間戳",
        "packet_split": "時間分包",
        "line_split": "換行分包",
        "nl_auto": "自動",
        "timeout": "超時",
        "real_time_log": "即時記錄",
        "log_split_none": "不分包",
        "log_path_idle": "（未記錄）",
        "log_split_tip": "即時記錄按檔案大小分包：寫到設定大小就切到新檔(原名加 _001/_002…)。\n可手填自訂，如 3M / 500K；選「不分包」則單檔不限。",
        "max_lines": "最大行數",
        "save": "儲存",
        "ctx_copy": "複製",
        "ctx_select_all": "全選",
        "clear": "清空",
        "font_dec": "字號減小",
        "font_inc": "字號增大",
        "serial_settings": "串口設定",
        "port": "連接埠",
        "baud_rate": "鮑率",
        "data_bits": "資料位元",
        "parity": "校驗",
        "stop_bits": "停止位元",
        "open_serial": "開啟串口",
        "close_serial": "關閉串口",
        "no_ports": "(無可用串口)",
        "send_area": "發送區",
        "hex_send": "HEX 發送",
        "append_newline": "追加換行",
        "period": "定時",
        "checksum": "校驗",
        "ck_none": "無",
        "ck_sum": "和校驗",
        "ck_neg_sum": "累加和取反",
        "ck_xor": "異或",
        "ck_crc8": "CRC8",
        "ck_modbus": "ModbusCRC16",
        "ck_ccitt": "CCITT-CRC16",
        "ck_crc32": "CRC32",
        "ck_add16": "ADD16",
        "ck_mobus": "MOBUS",
        "send_placeholder": "在這裡輸入要發送的內容...   HEX 模式範例: AA BB CC 01 02 (空格可省)",
        "multi_send": "多條發送",
        "multi_send_title": "多條發送",
        "ms_add": "＋ 新增一條",
        "ms_cycle": "▶ 迴圈",
        "ms_cycle_stop": "■ 停止",
        "ms_send_one": "發送",
        "ms_nl_none": "無",
        "ms_placeholder": "資料（HEX 或文字）",
        "ms_none_checked": "請先勾選要迴圈發送的條目",
        "ms_hint": "左側管理分組；每行可獨立設 名稱 / 延時 / HEX / 換行 / 校驗。勾選多條 → 迴圈發送：發完每條等其「延時」再發下一條，到底再從頭。",
        "ms_name_ph": "名稱",
        "ms_delay_tip": "延時(ms)：發完本條後等這麼久再發下一條",
        "kw_highlight": "關鍵字高亮",
        "kw_title": "關鍵字高亮",
        "kw_add": "＋ 新增關鍵字",
        "kw_mode_bg": "背景",
        "kw_mode_fg": "文字",
        "kw_color": "選擇高亮顏色",
        "kw_placeholder": "關鍵字（區分大小寫）",
        "kw_hint": "資料區匹配到關鍵字就按設定顏色高亮（區分大小寫）。每條可限定 收 / 發 / 收發。",
        "kw_scope_both": "收發",
        "kw_scope_rx": "收",
        "kw_scope_tx": "發",
        "filter_highlight": "只顯高亮行",
        "kw_default_group": "預設",
        "kw_group_off": "（關閉）",
        "kw_group_label": "分組",
        "kw_new_group": "新增",
        "kw_rename_group": "重新命名",
        "kw_del_group": "刪除",
        "kw_group_name_prompt": "分組名稱：",
        "kw_group_min": "至少保留一個分組",
        "kw_new_group_default": "新分組",
        "kw_group_tip": "雙擊分組名可改名",
        "read_file": "讀取檔案",
        "send_btn": "發  送",
        "state_closed": "● 未開啟",
        "dlg_save_data": "儲存接收資料",
        "dlg_log_path": "選擇日誌儲存路徑",
        "dlg_load_file": "讀取發送內容",
        "filter_text": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_text_save": "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        "filter_all": "All Files (*)",
        "log_header": "\n========== 日誌開始 {time} ==========\n",
        "log_footer": "\n========== 日誌結束 {time} ==========\n",
        "log_started": "即時記錄已開啟",
        "log_stopped": "即時記錄已停止",
        "saved_to": "已儲存到 {path}",
        "err_no_port": "請先選擇串口",
        "err_bad_baud": "鮑率無效",
        "err_open_failed": "開啟失敗: {e}",
        "err_serial": "串口錯誤: {e}",
        "err_serial_not_open": "串口未開啟",
        "err_hex_odd": "HEX 長度必須為偶數",
        "err_hex_bad": "HEX 格式錯誤: {e}",
        "err_hex_invalid_chars": "非法字元 {chars}",
        "err_send_failed": "發送失敗: {e}",
        "err_checksum": "校驗計算失敗: {e}",
        "err_save_failed": "儲存失敗: {e}",
        "err_read_failed": "讀取失敗: {e}",
        "err_period_bad": "週期錯誤: {e}",
        "err_min_period": "週期最小 10ms",
        "err_open_log": "開啟失敗: {e}",
        "err_log_write": "寫日誌失敗: {e}",
        "err_rx": "接收處理出錯: {e}",
        "font_size_msg": "字號: {size} pt",
        "close_prompt": "你想怎麼關閉程式？",
        "close_minimize": "最小化到托盤",
        "close_quit": "退出程式",
        "close_cancel": "取消",
        "tray_show": "顯示視窗",
        "tray_quit": "退出",
        "tray_minimized": "{app} 已最小化到系統托盤",
        # —— 滑鼠懸停說明 ——
        "hex_display_tip": "勾選後資料按 16 進位顯示\n關閉：按文字/ASCII 顯示",
        "encoding_tip": "字元編碼（影響 RX 解碼 / TX 編碼 / 檔案載入）\n自動：UTF-8 優先，亂碼自動回退 GBK\n指定 UTF-8/GBK/GB2312/Big5 等則嚴格按選定編碼",
        "theme_tip": "資料區配色方案（終端風格）\n切換後僅影響新到的資料，歷史不重塗\n想全部重新整理點「清空」即可",
        "auto_wrap_tip": "行太長自動換行\n關閉：超出寬度需橫向捲動檢視",
        "show_timestamp_tip": "每個資料區塊前顯示 [年/月/日 時:分:秒 毫秒] 時間戳和 ←/→ 收發方向箭頭",
        "packet_split_tip": "收到資料後超過下方「超時」時間無新資料就開新行\n用於把短時間到達的連續資料合併顯示",
        "timeout_tip": "時間分包的間隔閾值（毫秒）\n兩次接收間隔超過此值就開新行",
        "line_split_tip": "按換行符自動分行顯示\n可選自動識別 / CRLF / LF / CR",
        "real_time_log_tip": "收發資料即時追加儲存到日誌檔案\n顯示什麼就記什麼(含時間戳/箭頭/HEX)，關閉後停止寫入",
        "max_lines_tip": "資料區最多保留的行數\n超出會丟棄最早的（防止記憶體漲爆）",
        "hex_send_tip": "把輸入框的 16 進位字串按位元組發送（如 AA BB CC）\n關閉：按文字原樣發送",
        "append_newline_tip": "每次發送後自動追加換行符\n可選 CRLF / LF / CR",
        "period_tip": "按右側間隔（毫秒）週期性自動發送目前內容",
        "checksum_tip": "發送前在末尾追加校驗位元組\n支援 和校驗/CRC8/MOBUS/CRC16/CRC32 等多種演算法",
    },
}
CHECKSUM_KEYS = ["ck_none", "ck_sum", "ck_neg_sum", "ck_xor", "ck_crc8",
                 "ck_modbus", "ck_ccitt", "ck_crc32", "ck_add16", "ck_mobus"]


# ============== iOS 风格滑动开关 ==============
class IOSSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 24)
        self._checked = checked
        self._circle_pos = 18 if checked else 2
        self.setCursor(Qt.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"circle_pos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def isChecked(self):
        return self._checked

    def setChecked(self, value, animate=True):
        if self._checked == value:
            return
        self._checked = value
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._circle_pos)
            self._anim.setEndValue(18 if value else 2)
            self._anim.start()
        else:
            self._circle_pos = 18 if value else 2
            self.update()
        self.toggled.emit(value)

    def get_circle_pos(self):
        return self._circle_pos

    def set_circle_pos(self, v):
        self._circle_pos = v
        self.update()

    circle_pos = pyqtProperty(int, get_circle_pos, set_circle_pos)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track_color = QColor(COLOR_GREEN) if self._checked else QColor("#E5E5EA")
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(0, 0, 40, 24, 12, 12)
        shadow = QColor(0, 0, 0, 40)
        p.setBrush(QBrush(shadow))
        p.drawEllipse(self._circle_pos, 3, 20, 20)
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(self._circle_pos, 2, 20, 20)


# ============== 自定义标题栏 ==============
class TitleBar(QWidget):
    HEIGHT = 36

    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self._win = parent
        self._drag_pos = None
        self.setObjectName("TitleBar")
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(6)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        layout.addWidget(self.icon_label)

        self.title_label = QLabel("")
        self.title_label.setFont(QFont("Segoe UI", 10))
        self.title_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(self.title_label)

        # 语言 + 主题切换全部左侧 — 紧挨标题（旧版语言在右上现挪到左上）
        layout.addSpacing(12)
        self.cb_language = QComboBox()
        self.cb_language.setMinimumWidth(96)
        self.cb_language.setFixedHeight(26)
        layout.addWidget(self.cb_language)

        self.cb_theme = QComboBox()
        self.cb_theme.setMinimumWidth(120)
        self.cb_theme.setFixedHeight(26)
        layout.addWidget(self.cb_theme)

        layout.addStretch(1)

        # 用 Segoe UI 里可靠的 Unicode 字符
        self._ch_min = "−"
        self._ch_max = "□"
        self._ch_restore = "❐"
        self._ch_close = "×"

        self.btn_min = self._mk_btn(self._ch_min)
        self.btn_max = self._mk_btn(self._ch_max)
        self.btn_close = self._mk_btn(self._ch_close)
        self.btn_close.setObjectName("CloseBtn")
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

        self.btn_min.clicked.connect(self._win.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self._win.close)

    def _mk_btn(self, text):
        btn = QPushButton(text)
        btn.setFixedSize(46, self.HEIGHT)
        btn.setObjectName("CtrlBtn")
        btn.setFocusPolicy(Qt.NoFocus)
        return btn

    def set_app_icon(self, qicon: QIcon):
        if qicon and not qicon.isNull():
            self.icon_label.setPixmap(qicon.pixmap(16, 16))

    def set_title(self, text: str):
        self.title_label.setText(text)

    def update_max_icon(self):
        self.btn_max.setText(self._ch_restore if self._win.isMaximized() else self._ch_max)

    def _toggle_max(self):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()
        self.update_max_icon()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._win.isMaximized():
                self._drag_pos = None
            else:
                self._drag_pos = event.globalPos() - self._win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            if self._win.isMaximized():
                ratio = event.x() / max(self.width(), 1)
                self._win.showNormal()
                self.update_max_icon()
                new_w = self._win.width()
                self._drag_pos = QPoint(int(new_w * ratio), event.y())
                self._win.move(event.globalPos() - self._drag_pos)
            elif self._drag_pos is not None:
                self._win.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_max()
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


# ============== 带阴影的卡片 ==============
class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)


# ============== 标签 ==============
def make_label(text, size=11, bold=False, color=COLOR_TEXT):
    lbl = QLabel(text)
    f = QFont("Segoe UI", size)
    if bold:
        f.setWeight(QFont.DemiBold)
    lbl.setFont(f)
    if color == COLOR_TEXT_SECONDARY:
        lbl.setProperty("theme_color_role", "secondary")
    elif color == COLOR_TEXT:
        lbl.setProperty("theme_color_role", "primary")
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


# ============== 串口读取线程 ==============
class SerialReader(QThread):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)

    def __init__(self, ser):
        super().__init__()
        self.ser = ser
        self._running = True

    def run(self):
        while self._running:
            try:
                if self.ser and self.ser.is_open:
                    n = self.ser.in_waiting
                    if n > 0:
                        data = self.ser.read(n)
                        if data:
                            self.data_received.emit(data)
                    else:
                        self.msleep(10)
                else:
                    self.msleep(50)
            except Exception as e:
                self.error_occurred.emit(str(e))
                break

    def stop(self):
        self._running = False
        self.wait(1000)


# ============== 后台串口扫描线程 ==============
class PortScannerThread(QThread):
    """后台轮询可用串口，避免在 GUI 线程调用 comports() 偶发卡顿"""
    scan_complete = pyqtSignal(list)

    def __init__(self, interval_ms: int = 1500, parent=None):
        super().__init__(parent)
        self._running = True
        self._interval = interval_ms

    def run(self):
        while self._running:
            try:
                ports = list(serial.tools.list_ports.comports())
                result = []
                for p in ports:
                    desc = p.description.replace(p.device, "").strip(" ()-")
                    label = f"{p.device}  {desc}" if desc else p.device
                    result.append((p.device, label))
                self.scan_complete.emit(result)
            except Exception:
                pass
            self.msleep(self._interval)

    def stop(self):
        self._running = False
        self.wait(2000)


class OneShotPortScanner(QThread):
    """点 ⟳ 手动刷新端口时用的一次性扫描线程，避免在 GUI 线程跑 comports() 卡顿"""
    scan_complete = pyqtSignal(list)

    def run(self):
        try:
            ports = list(serial.tools.list_ports.comports())
            result = []
            for p in ports:
                desc = p.description.replace(p.device, "").strip(" ()-")
                label = f"{p.device}  {desc}" if desc else p.device
                result.append((p.device, label))
            self.scan_complete.emit(result)
        except Exception:
            self.scan_complete.emit([])


# ============== 关闭确认对话框 (iOS 风格) ==============
class CloseDialog(QDialog):
    """无边框 + 圆角白底 + 居中标题 + 3 个并排按钮"""
    RESULT_MIN = 1
    RESULT_QUIT = 2
    RESULT_CANCEL = 0

    def __init__(self, title_text: str, btn_min_text: str,
                 btn_quit_text: str, btn_cancel_text: str,
                 theme_id: str = THEME_DEFAULT, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self._result_val = self.RESULT_CANCEL
        self._theme_id = theme_id

        # 外层透明容器，里面放圆角白卡
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        self._card = QFrame()
        self._card.setObjectName("DialogCard")
        sh = QGraphicsDropShadowEffect(self._card)
        sh.setBlurRadius(30)
        sh.setColor(QColor(0, 0, 0, 60))
        sh.setOffset(0, 4)
        self._card.setGraphicsEffect(sh)

        v = QVBoxLayout(self._card)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(20)

        # 标题文本 (居中) — 颜色按主题来
        c = chrome_for(theme_id)
        self.lbl_title = QLabel(title_text)
        f = QFont("Segoe UI", 14)
        f.setWeight(QFont.DemiBold)
        self.lbl_title.setFont(f)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet(f"color: {c['text']}; background: transparent;")
        v.addWidget(self.lbl_title)

        # 3 个按钮一行
        h = QHBoxLayout()
        h.setSpacing(10)

        self.btn_min = QPushButton(btn_min_text)
        self.btn_min.setObjectName("DialogPrimaryBtn")
        self.btn_min.setMinimumHeight(36)
        self.btn_min.clicked.connect(self._on_min)
        h.addWidget(self.btn_min, 1)

        self.btn_quit = QPushButton(btn_quit_text)
        self.btn_quit.setObjectName("DialogDangerBtn")
        self.btn_quit.setMinimumHeight(36)
        self.btn_quit.clicked.connect(self._on_quit)
        h.addWidget(self.btn_quit, 1)

        self.btn_cancel = QPushButton(btn_cancel_text)
        self.btn_cancel.setObjectName("DialogGhostBtn")
        self.btn_cancel.setMinimumHeight(36)
        self.btn_cancel.clicked.connect(self._on_cancel)
        h.addWidget(self.btn_cancel, 1)

        v.addLayout(h)
        outer.addWidget(self._card)

        self.setStyleSheet(self._build_qss())
        self.setMinimumWidth(380)

    def _build_qss(self):
        c = chrome_for(self._theme_id)
        return f"""
        QFrame#DialogCard {{
            background-color: {c['card_bg']};
            border-radius: 14px;
        }}
        QPushButton#DialogPrimaryBtn {{
            background-color: {c['accent']};
            color: white;
            border: 0px;
            border-radius: 9px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 600;
            padding: 6px 12px;
        }}
        QPushButton#DialogPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#DialogPrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#DialogDangerBtn {{
            background-color: {c['danger']};
            color: white;
            border: 0px;
            border-radius: 9px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 600;
            padding: 6px 12px;
        }}
        QPushButton#DialogDangerBtn:hover {{ background-color: {c['danger_hover']}; }}
        QPushButton#DialogGhostBtn {{
            background-color: {c['ghost_bg']};
            color: {c['text']};
            border: 0px;
            border-radius: 9px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 500;
            padding: 6px 12px;
        }}
        QPushButton#DialogGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#DialogGhostBtn:pressed {{ background-color: {c['ghost_pressed']}; }}
        """

    def _on_min(self):
        self._result_val = self.RESULT_MIN
        self.accept()

    def _on_quit(self):
        self._result_val = self.RESULT_QUIT
        self.accept()

    def _on_cancel(self):
        self._result_val = self.RESULT_CANCEL
        self.reject()

    def result_value(self):
        return self._result_val


def _set_win_titlebar_dark(widget, is_dark):
    """Windows DWM 沉浸式深/浅标题栏；非 Windows 静默跳过。
    供 MultiSendDialog / KeywordHighlightDialog 共用，避免重复+标志不一致。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        val = ctypes.c_int(1 if is_dark else 0)
        # 属性号 20 = Win10 20H1+/Win11；失败(HRESULT≠0)才回退老版本的 19
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        if hr != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
        if widget.isVisible():
            # SWP_NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED — 仅重绘非客户区，不动大小/位置/层级
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
    except Exception:
        pass


def _make_list_scroll():
    """列表型弹窗共用：建滚动区 + 内部容器(底栏 stretch)，并关掉 viewport/host 的
    autoFillBackground(否则深色主题下默认白底盖住对话框)。返回 (scroll, host, vbox)。"""
    host = QWidget()
    host.setObjectName("MsListHost")
    vbox = QVBoxLayout(host)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(6)
    vbox.addStretch(1)
    scroll = QScrollArea()
    scroll.setObjectName("MsScroll")
    scroll.setWidget(host)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    host.setAutoFillBackground(False)
    scroll.viewport().setAutoFillBackground(False)
    return scroll, host, vbox


def _dialog_list_qss(c):
    """MultiSendDialog / KeywordHighlightDialog 共用的列表型弹窗基础样式表。
    各自再拼接自己特有的按钮样式(MsPrimaryBtn/MsSendBtn 等)。"""
    return f"""
    QDialog {{ background-color: {c['window_bg']}; }}
    QLabel {{ color: {c['text']}; background: transparent; font-family: 'Segoe UI'; font-size: 12px; }}
    QLabel#MsHint {{ color: {c['text_sec']}; font-size: 11px; }}
    QScrollArea#MsScroll {{ background: transparent; border: 0px; }}
    QScrollArea#MsScroll > QWidget > QWidget {{ background: transparent; }}
    QWidget#MsListHost {{ background: transparent; }}
    QFrame#MsRow {{ background-color: {c['card_bg']}; border-radius: 8px; }}
    QLineEdit {{
        background-color: {c['input_bg']}; border: 1px solid {c['separator']};
        border-radius: 6px; padding: 4px 8px; color: {c['text']};
        font-family: 'Consolas'; font-size: 12px;
        selection-background-color: {c['accent']};
    }}
    QLineEdit:focus {{ border: 1px solid {c['accent']}; background-color: {c['input_focus_bg']}; }}
    QCheckBox {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 11px; spacing: 4px; }}
    QComboBox {{
        background-color: {c['input_bg']}; border: 1px solid {c['separator']};
        border-radius: 6px; padding: 3px 6px; color: {c['text']};
        font-family: 'Segoe UI'; font-size: 11px;
        selection-background-color: {c['accent']};
    }}
    QComboBox:focus {{ border: 1px solid {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 16px; }}
    QComboBox QAbstractItemView {{
        background-color: {c['combo_dropdown_bg']}; color: {c['text']};
        border: 1px solid {c['separator']}; border-radius: 0px; padding: 2px;
        outline: 0px; selection-background-color: {c['accent']}; selection-color: #FFFFFF;
    }}
    QPushButton#MsGhostBtn {{
        background-color: {c['ghost_bg']}; color: {c['text']}; border: 0px;
        border-radius: 8px; font-family: 'Segoe UI'; font-size: 12px; padding: 5px 10px;
    }}
    QPushButton#MsGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
    QPushButton#MsDelBtn {{
        background-color: transparent; color: {c['text_sec']}; border: 0px;
        font-size: 13px; font-weight: bold;
    }}
    QPushButton#MsDelBtn:hover {{ color: {c['danger']}; }}
    """


# ============== 多条发送弹窗 ==============
class MultiSendDialog(QDialog):
    """多条自定义发送，支持分组(左侧列表)：每行一条命令 + 名称 + 独立延时 + HEX/换行/校验。
    可逐条点「发送」，也可勾选多条后「循环发送」按每行延时依次轮发。分组与命令持久化。"""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(app._t("multi_send_title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(900, 400)
        self.resize(1040, 480)
        self._rows = []
        self._populating = False
        self._edit_idx = 0      # 编辑哪个分组（数据存于 app._ms_groups，循环在主界面）
        # 去抖：连敲键时合并存盘+重建，避免每个字符都 sync 磁盘/重建快捷栏卡顿
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._commit_now)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ===== 左侧：分组列表 =====
        left = QVBoxLayout()
        left.setSpacing(6)
        grp_btns = QHBoxLayout()
        grp_btns.setSpacing(6)
        self.btn_new_group = QPushButton(app._t("kw_new_group"))
        self.btn_new_group.setObjectName("MsGhostBtn")
        self.btn_new_group.setMinimumHeight(30)
        self.btn_new_group.clicked.connect(self._new_group)
        grp_btns.addWidget(self.btn_new_group, 1)
        self.btn_del_group = QPushButton(app._t("kw_del_group"))
        self.btn_del_group.setObjectName("MsGhostBtn")
        self.btn_del_group.setMinimumHeight(30)
        self.btn_del_group.clicked.connect(self._delete_group)
        grp_btns.addWidget(self.btn_del_group, 1)
        left.addLayout(grp_btns)
        self.list_groups = QListWidget()
        self.list_groups.setObjectName("KwGroupList")
        self.list_groups.currentRowChanged.connect(self._on_group_row_changed)
        self.list_groups.itemChanged.connect(self._on_group_renamed)
        self.list_groups.itemDoubleClicked.connect(self.list_groups.editItem)
        left.addWidget(self.list_groups, 1)
        self.lbl_group_tip = QLabel(app._t("kw_group_tip"))
        self.lbl_group_tip.setObjectName("MsHint")
        self.lbl_group_tip.setWordWrap(True)
        left.addWidget(self.lbl_group_tip)
        left_host = QWidget()
        left_host.setLayout(left)
        left_host.setFixedWidth(180)
        root.addWidget(left_host)

        # ===== 右侧：当前分组的命令 =====
        right = QVBoxLayout()
        right.setSpacing(10)
        scroll, self._list_host, self._list_v = _make_list_scroll()
        right.addWidget(scroll, 1)

        self.btn_add = QPushButton(app._t("ms_add"))
        self.btn_add.setObjectName("MsGhostBtn")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.clicked.connect(lambda *_: (self._add_row(), self._commit_now()))
        right.addWidget(self.btn_add)

        self.lbl_hint = QLabel(app._t("ms_hint"))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setObjectName("MsHint")
        right.addWidget(self.lbl_hint)
        root.addLayout(right, 1)

        self.refresh_theme()
        self._reload_group_list()
        self._reload_rows()

    # ----- 分组管理（左侧列表）-----
    @property
    def _groups(self):
        """分组数据存于主窗口(与发送区快捷栏共享)，弹窗只是编辑器。"""
        return self.app._ms_groups

    def _reload_group_list(self):
        self._populating = True
        self.list_groups.clear()
        for i, g in enumerate(self._groups):
            item = QListWidgetItem(g.get("name", f"组{i + 1}"))
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.list_groups.addItem(item)
        if not (0 <= self._edit_idx < len(self._groups)):
            self._edit_idx = 0
        self.list_groups.setCurrentRow(self._edit_idx)
        self._populating = False
        self.btn_del_group.setEnabled(len(self._groups) > 1)

    def _on_group_row_changed(self, row):
        if self._populating or row < 0:
            return
        if self._save_timer.isActive():     # 切组前把上一组未提交的编辑落盘，避免丢失
            self._commit_now()
        self._edit_idx = row
        self._reload_rows()

    def _on_group_renamed(self, item):
        if self._populating:
            return
        row = self.list_groups.row(item)
        if not (0 <= row < len(self._groups)):
            return
        name = item.text().strip()
        if not name:
            self._populating = True
            item.setText(self._groups[row].get("name", ""))
            self._populating = False
            return
        self._groups[row]["name"] = name
        self.app._ms_groups_changed()

    def _new_group(self):
        if self._save_timer.isActive():   # 先把当前组未提交编辑落盘
            self._commit_now()
        base = self.app._t("kw_new_group_default")
        existing = {g.get("name") for g in self._groups}
        name, n = base, 1
        while name in existing:
            n += 1
            name = f"{base}{n}"
        self._groups.append({"name": name, "items": []})
        self._edit_idx = len(self._groups) - 1
        self.app._ms_groups_changed()
        self._reload_group_list()
        self._reload_rows()
        item = self.list_groups.item(self._edit_idx)
        if item:
            self.list_groups.editItem(item)

    def _delete_group(self):
        if len(self._groups) <= 1:
            self.app.toast(self.app._t("kw_group_min"), error=True)
            return
        self._save_timer.stop()    # 当前组将被删，丢弃其待提交编辑
        d = self._edit_idx
        self._groups.pop(d)
        # 同步主窗口选中分组索引的偏移（删除项在其之前/即其本身时）
        if self.app._ms_group_idx == d:
            self.app._ms_group_idx = min(d, len(self._groups) - 1)
        elif self.app._ms_group_idx > d:
            self.app._ms_group_idx -= 1
        self._edit_idx = min(d, len(self._groups) - 1)
        self.app._ms_groups_changed()
        self._reload_group_list()
        self._reload_rows()

    # ----- 命令行管理 -----
    def _add_row(self, data="", checked=False, hex_on=False, nl=0, cs=0,
                 name="", delay=1000):
        frame = QFrame()
        frame.setObjectName("MsRow")
        h = QHBoxLayout(frame)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)
        chk = QCheckBox()
        chk.setChecked(checked)
        chk.stateChanged.connect(self._save)
        h.addWidget(chk)
        ed_name = QLineEdit(name)
        ed_name.setPlaceholderText(self.app._t("ms_name_ph"))
        ed_name.setFixedWidth(82)
        ed_name.textChanged.connect(self._save)
        h.addWidget(ed_name)
        edit = QLineEdit(data)
        edit.setPlaceholderText(self.app._t("ms_placeholder"))
        edit.textChanged.connect(self._save)
        h.addWidget(edit, 1)
        ed_delay = QLineEdit(str(delay))
        ed_delay.setFixedWidth(58)
        ed_delay.setToolTip(self.app._t("ms_delay_tip"))
        ed_delay.setPlaceholderText("ms")
        ed_delay.textChanged.connect(self._save)
        h.addWidget(ed_delay)
        cb_hex = QCheckBox("HEX")
        cb_hex.setChecked(hex_on)
        cb_hex.stateChanged.connect(self._save)
        h.addWidget(cb_hex)
        cb_nl = QComboBox()
        cb_nl.addItems([self.app._t("ms_nl_none"), "CRLF", "LF", "CR"])
        cb_nl.setCurrentIndex(nl)
        cb_nl.setFixedWidth(66)
        cb_nl.currentIndexChanged.connect(self._save)
        h.addWidget(cb_nl)
        cb_cs = QComboBox()
        cb_cs.addItems([self.app._t(k) for k in CHECKSUM_KEYS])
        cb_cs.setCurrentIndex(cs)
        cb_cs.setFixedWidth(104)
        cb_cs.currentIndexChanged.connect(self._save)
        h.addWidget(cb_cs)
        btn_send = QPushButton(self.app._t("ms_send_one"))
        btn_send.setObjectName("MsSendBtn")
        row = {"frame": frame, "chk": chk, "name": ed_name, "edit": edit,
               "delay": ed_delay, "hex": cb_hex, "nl": cb_nl, "cs": cb_cs}
        btn_send.clicked.connect(lambda _=False, r=row: self._send_row(r))
        h.addWidget(btn_send)
        btn_del = QPushButton("✕")
        btn_del.setObjectName("MsDelBtn")
        btn_del.setFixedWidth(28)
        btn_del.clicked.connect(lambda _=False, r=row: self._del_row(r))
        h.addWidget(btn_del)
        self._list_v.insertWidget(self._list_v.count() - 1, frame)
        self._rows.append(row)

    def _row_delay(self, row):
        try:
            return max(0, int(row["delay"].text()))
        except (ValueError, TypeError):
            return 1000

    def _row_params(self, row):
        """(数据, hex_mode, newline 0-3, checksum 索引, 延时 ms)"""
        return (row["edit"].text(), row["hex"].isChecked(),
                row["nl"].currentIndex(), row["cs"].currentIndex(),
                self._row_delay(row))

    def _send_row(self, row):
        data, hx, nl, cs, _d = self._row_params(row)
        self.app._send_text(data, hex_mode=hx, newline=nl, checksum=cs)

    def _del_row(self, row):
        row["frame"].setParent(None)
        row["frame"].deleteLater()
        if row in self._rows:
            self._rows.remove(row)
        self._commit_now()

    # ----- 持久化（写回主窗口分组 + 同步快捷栏）-----
    def _row_dict(self, r):
        return {"name": r["name"].text(), "data": r["edit"].text(),
                "checked": r["chk"].isChecked(), "delay": self._row_delay(r),
                "hex": r["hex"].isChecked(), "nl": r["nl"].currentIndex(),
                "cs": r["cs"].currentIndex()}

    def _save(self):
        """行内编辑触发：去抖，300ms 内合并多次按键为一次落盘+重建。"""
        self._save_timer.start()

    def _commit_now(self):
        """把当前行写回编辑分组，并刷新主界面快捷栏/下拉（去抖后或结构性操作时立即调用）。"""
        self._save_timer.stop()
        if 0 <= self._edit_idx < len(self._groups):
            self._groups[self._edit_idx]["items"] = [self._row_dict(r) for r in self._rows]
        self.app._ms_groups_changed()

    def _reload_rows(self):
        for r in self._rows:
            r["frame"].setParent(None)
            r["frame"].deleteLater()
        self._rows = []
        items = []
        if 0 <= self._edit_idx < len(self._groups):
            items = self._groups[self._edit_idx]["items"]
        if not items:
            items = [{"data": "", "checked": False}]
        for it in items:
            self._add_row(str(it.get("data", "")), bool(it.get("checked", False)),
                          bool(it.get("hex", False)), int(it.get("nl", 0)),
                          int(it.get("cs", 0)), str(it.get("name", "")),
                          int(it.get("delay", 1000)))
        self.refresh_theme()

    def closeEvent(self, e):
        self._commit_now()    # 关窗时立即落盘待提交编辑
        super().closeEvent(e)

    # ----- 主题 / 语言 -----
    def retranslate(self):
        self.setWindowTitle(self.app._t("multi_send_title"))
        self.btn_add.setText(self.app._t("ms_add"))
        self.lbl_hint.setText(self.app._t("ms_hint"))
        self.btn_new_group.setText(self.app._t("kw_new_group"))
        self.btn_del_group.setText(self.app._t("kw_del_group"))
        self.lbl_group_tip.setText(self.app._t("kw_group_tip"))
        for r in self._rows:
            r["edit"].setPlaceholderText(self.app._t("ms_placeholder"))
            r["name"].setPlaceholderText(self.app._t("ms_name_ph"))
            r["delay"].setToolTip(self.app._t("ms_delay_tip"))
            r["nl"].setItemText(0, self.app._t("ms_nl_none"))
            cs_idx = r["cs"].currentIndex()
            r["cs"].blockSignals(True)
            for i, k in enumerate(CHECKSUM_KEYS):
                r["cs"].setItemText(i, self.app._t(k))
            r["cs"].setCurrentIndex(cs_idx)
            r["cs"].blockSignals(False)

    def _apply_titlebar_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")

    def refresh_theme(self):
        self._apply_titlebar_theme()
        c = chrome_for(self.app._theme_id())
        self.setStyleSheet(_dialog_list_qss(c) + f"""
        QPushButton#MsPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 13px; font-weight: 600;
            padding: 6px 14px;
        }}
        QPushButton#MsPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#MsPrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#MsSendBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 12px; padding: 4px 12px;
        }}
        QPushButton#MsSendBtn:hover {{ background-color: {c['accent_hover']}; }}
        QListWidget#KwGroupList {{
            background-color: {c['input_bg']}; border: 1px solid {c['separator']};
            border-radius: 8px; color: {c['text']};
            font-family: 'Segoe UI'; font-size: 12px; outline: 0px; padding: 3px;
        }}
        QListWidget#KwGroupList::item {{ padding: 5px 6px; border-radius: 5px; }}
        QListWidget#KwGroupList::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
        QListWidget#KwGroupList::item:hover {{ background-color: {c['ghost_hover']}; }}
        QListWidget#KwGroupList QLineEdit {{
            background-color: {c['input_focus_bg']}; color: {c['text']};
            border: 1px solid {c['accent']}; border-radius: 4px; padding: 1px 4px;
            selection-background-color: {c['accent']}; selection-color: #FFFFFF;
        }}
        """)
        for r in getattr(self, "_rows", []):
            for key in ("nl", "cs"):
                popup = r[key].view().window()
                popup.setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")


# ============== 关键字高亮配置弹窗 ==============
class KeywordHighlightDialog(QDialog):
    """配置多条关键字高亮：每条选 背景/文字 着色 + 颜色。
    区分大小写子串匹配，RX/TX 都高亮；规则持久化、即时生效。"""
    PRESET_COLORS = ["#FFD60A", "#FF453A", "#32D74B", "#0A84FF", "#BF5AF2", "#FF9F0A"]

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle(app._t("kw_title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(720, 380)
        self.resize(860, 460)
        self._rows = []
        self._populating = False    # 编程填充分组列表时忽略 itemChanged(重命名)
        # 去抖：连敲键时合并落盘+全量重扫高亮，避免每个字符都 sync+重扫卡顿
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(300)
        self._commit_timer.timeout.connect(self._commit_now)
        # 编辑目标分组（与主界面「生效分组」独立）：默认编辑当前生效分组，关闭时编辑第一个
        self._edit_idx = (app._keyword_active
                          if 0 <= app._keyword_active < len(app._keyword_groups) else 0)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ===== 左侧：分组列表（仿 SuperCom）=====
        left = QVBoxLayout()
        left.setSpacing(6)
        # 新建 / 删除 并排一行
        grp_btns = QHBoxLayout()
        grp_btns.setSpacing(6)
        self.btn_new_group = QPushButton(app._t("kw_new_group"))
        self.btn_new_group.setObjectName("MsGhostBtn")
        self.btn_new_group.setMinimumHeight(30)
        self.btn_new_group.clicked.connect(self._new_group)
        grp_btns.addWidget(self.btn_new_group, 1)
        self.btn_del_group = QPushButton(app._t("kw_del_group"))
        self.btn_del_group.setObjectName("MsGhostBtn")
        self.btn_del_group.setMinimumHeight(30)
        self.btn_del_group.clicked.connect(self._delete_group)
        grp_btns.addWidget(self.btn_del_group, 1)
        left.addLayout(grp_btns)
        self.list_groups = QListWidget()
        self.list_groups.setObjectName("KwGroupList")
        self.list_groups.currentRowChanged.connect(self._on_group_row_changed)
        self.list_groups.itemChanged.connect(self._on_group_renamed)
        self.list_groups.itemDoubleClicked.connect(self.list_groups.editItem)
        left.addWidget(self.list_groups, 1)
        self.lbl_group_tip = QLabel(app._t("kw_group_tip"))
        self.lbl_group_tip.setObjectName("MsHint")
        self.lbl_group_tip.setWordWrap(True)
        left.addWidget(self.lbl_group_tip)
        left_host = QWidget()
        left_host.setLayout(left)
        left_host.setFixedWidth(180)
        root.addWidget(left_host)

        # ===== 右侧：当前分组的规则 =====
        right = QVBoxLayout()
        right.setSpacing(10)
        scroll, self._list_host, self._list_v = _make_list_scroll()
        right.addWidget(scroll, 1)
        self.btn_add = QPushButton(app._t("kw_add"))
        self.btn_add.setObjectName("MsGhostBtn")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.clicked.connect(lambda *_: self._on_add())
        right.addWidget(self.btn_add)
        self.lbl_hint = QLabel(app._t("kw_hint"))
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setObjectName("MsHint")
        right.addWidget(self.lbl_hint)
        root.addLayout(right, 1)

        self.refresh_theme()
        self._reload_group_list()
        self._reload_rows()

    # ----- 行管理 -----
    def _on_add(self):
        # 新加行默认不勾选(与首次默认行一致)：用户填好关键字后再手动启用
        color = self.PRESET_COLORS[len(self._rows) % len(self.PRESET_COLORS)]
        self._add_row("", "bg", color, False)
        self._commit_now()

    _SCOPES = ("both", "rx", "tx")

    def _add_row(self, pattern="", mode="bg", color="#FFD60A", enabled=True, scope="both"):
        frame = QFrame()
        frame.setObjectName("MsRow")
        h = QHBoxLayout(frame)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(6)
        chk = QCheckBox()
        chk.setChecked(enabled)
        chk.stateChanged.connect(self._commit)
        h.addWidget(chk)
        edit = QLineEdit(pattern)
        edit.setPlaceholderText(self.app._t("kw_placeholder"))
        edit.textChanged.connect(self._commit)
        h.addWidget(edit, 1)
        cb_scope = QComboBox()
        cb_scope.addItems([self.app._t("kw_scope_both"), self.app._t("kw_scope_rx"),
                           self.app._t("kw_scope_tx")])
        cb_scope.setCurrentIndex(self._SCOPES.index(scope) if scope in self._SCOPES else 0)
        cb_scope.setFixedWidth(74)
        cb_scope.currentIndexChanged.connect(self._commit)
        h.addWidget(cb_scope)
        cb_mode = QComboBox()
        cb_mode.addItems([self.app._t("kw_mode_bg"), self.app._t("kw_mode_fg")])
        cb_mode.setCurrentIndex(0 if mode == "bg" else 1)
        cb_mode.setFixedWidth(78)
        cb_mode.currentIndexChanged.connect(self._commit)
        h.addWidget(cb_mode)
        btn_color = QPushButton()
        btn_color.setObjectName("KwColorBtn")
        btn_color.setFixedSize(40, 24)
        btn_color.setCursor(Qt.PointingHandCursor)
        row = {"frame": frame, "chk": chk, "edit": edit, "scope": cb_scope,
               "mode": cb_mode, "color": color, "colorbtn": btn_color}
        self._paint_color_btn(row)
        btn_color.clicked.connect(lambda _=False, r=row: self._pick_color(r))
        h.addWidget(btn_color)
        btn_del = QPushButton("✕")
        btn_del.setObjectName("MsDelBtn")
        btn_del.setFixedWidth(28)
        btn_del.clicked.connect(lambda _=False, r=row: self._del_row(r))
        h.addWidget(btn_del)
        self._list_v.insertWidget(self._list_v.count() - 1, frame)
        self._rows.append(row)

    def _paint_color_btn(self, row):
        row["colorbtn"].setStyleSheet(
            f"QPushButton#KwColorBtn {{ background-color: {row['color']};"
            f" border: 1px solid rgba(128,128,128,0.5); border-radius: 5px; }}")

    def _pick_color(self, row):
        col = QColorDialog.getColor(QColor(row["color"]), self, self.app._t("kw_color"))
        if col.isValid():
            row["color"] = col.name()
            self._paint_color_btn(row)
            self._commit_now()

    def _del_row(self, row):
        row["frame"].setParent(None)
        row["frame"].deleteLater()
        if row in self._rows:
            self._rows.remove(row)
        self._commit_now()

    # ----- 分组管理（左侧列表）-----
    def _reload_group_list(self):
        """用各分组名重建左侧列表，选中当前编辑分组。双击列表项可改名。"""
        self._populating = True
        self.list_groups.clear()
        for i, g in enumerate(self.app._keyword_groups):
            item = QListWidgetItem(g.get("name", f"组{i + 1}"))
            item.setFlags(item.flags() | Qt.ItemIsEditable)   # 双击改名
            self.list_groups.addItem(item)
        if not (0 <= self._edit_idx < len(self.app._keyword_groups)):
            self._edit_idx = 0
        self.list_groups.setCurrentRow(self._edit_idx)
        self._populating = False
        self.btn_del_group.setEnabled(len(self.app._keyword_groups) > 1)  # 至少保留一个

    def _on_group_row_changed(self, row):
        if self._populating or row < 0:
            return
        if self._commit_timer.isActive():   # 切组前把上一组未提交的编辑落盘
            self._commit_now()
        self._edit_idx = row
        self._reload_rows()

    def _on_group_renamed(self, item):
        """双击改名提交：写回分组名并同步主下拉。"""
        if self._populating:
            return
        row = self.list_groups.row(item)
        if not (0 <= row < len(self.app._keyword_groups)):
            return
        name = item.text().strip()
        if not name:   # 空名还原
            self._populating = True
            item.setText(self.app._keyword_groups[row].get("name", ""))
            self._populating = False
            return
        self.app._keyword_groups[row]["name"] = name
        self.app._kw_groups_changed()   # 存盘 + 重建主界面分组下拉

    def _new_group(self):
        if self._commit_timer.isActive():   # 先把当前组未提交编辑落盘
            self._commit_now()
        # 起个不重复的默认名，加进列表并进入改名状态(贴近 SuperCom 流程)
        base = self.app._t("kw_new_group_default")
        existing = {g.get("name") for g in self.app._keyword_groups}
        name, n = base, 1
        while name in existing:
            n += 1
            name = f"{base}{n}"
        self.app._keyword_groups.append({"name": name, "rules": []})
        self._edit_idx = len(self.app._keyword_groups) - 1
        self.app._kw_groups_changed()
        self._reload_group_list()
        self._reload_rows()
        item = self.list_groups.item(self._edit_idx)
        if item:
            self.list_groups.editItem(item)   # 直接改名

    def _delete_group(self):
        if len(self.app._keyword_groups) <= 1:
            self.app.toast(self.app._t("kw_group_min"), error=True)
            return
        self._commit_timer.stop()   # 当前组将被删，丢弃其待提交编辑
        d = self._edit_idx
        self.app._keyword_groups.pop(d)
        # 调整生效分组索引
        if self.app._keyword_active == d:
            self.app._keyword_active = -1
        elif self.app._keyword_active > d:
            self.app._keyword_active -= 1
        self._edit_idx = min(d, len(self.app._keyword_groups) - 1)
        self.app._kw_groups_changed()
        self._reload_group_list()
        self._reload_rows()

    # ----- 规则行 应用 / 加载 -----
    def _commit(self):
        """行内编辑触发：去抖，300ms 内合并多次按键为一次落盘+全量重扫高亮。"""
        self._commit_timer.start()

    def _commit_now(self):
        self._commit_timer.stop()
        rules = [
            {"pattern": r["edit"].text(),
             "mode": "bg" if r["mode"].currentIndex() == 0 else "fg",
             "scope": self._SCOPES[r["scope"].currentIndex()],
             "color": r["color"],
             "enabled": r["chk"].isChecked()}
            for r in self._rows]
        if 0 <= self._edit_idx < len(self.app._keyword_groups):
            self.app._keyword_groups[self._edit_idx]["rules"] = rules
        self.app._apply_keyword_rules()   # 存盘 + 刷新(若编辑的是生效分组即时见效)

    def _reload_rows(self):
        """清掉现有行，载入当前编辑分组的规则。"""
        for r in self._rows:
            r["frame"].setParent(None)
            r["frame"].deleteLater()
        self._rows = []
        rules = []
        if 0 <= self._edit_idx < len(self.app._keyword_groups):
            rules = self.app._keyword_groups[self._edit_idx]["rules"]
        if not rules:
            # 空分组给一条占位行(不勾选、不写回，等用户填了再 commit)
            rules = [{"pattern": "", "mode": "bg",
                      "color": self.PRESET_COLORS[0], "enabled": False, "scope": "both"}]
        for r in rules:
            self._add_row(str(r.get("pattern", "")), r.get("mode", "bg"),
                          r.get("color", "#FFD60A"), bool(r.get("enabled", True)),
                          r.get("scope", "both"))
        # 给新行的下拉弹出容器/颜色块刷主题色
        self.refresh_theme()

    def closeEvent(self, e):
        if self._commit_timer.isActive():   # 关窗时立即落盘待提交编辑
            self._commit_now()
        super().closeEvent(e)

    # ----- 主题 / 语言 -----
    def retranslate(self):
        self.setWindowTitle(self.app._t("kw_title"))
        self.btn_add.setText(self.app._t("kw_add"))
        self.lbl_hint.setText(self.app._t("kw_hint"))
        self.btn_new_group.setText(self.app._t("kw_new_group"))
        self.btn_del_group.setText(self.app._t("kw_del_group"))
        self.lbl_group_tip.setText(self.app._t("kw_group_tip"))
        for r in self._rows:
            r["edit"].setPlaceholderText(self.app._t("kw_placeholder"))
            idx = r["mode"].currentIndex()
            r["mode"].blockSignals(True)
            r["mode"].setItemText(0, self.app._t("kw_mode_bg"))
            r["mode"].setItemText(1, self.app._t("kw_mode_fg"))
            r["mode"].setCurrentIndex(idx)
            r["mode"].blockSignals(False)
            sidx = r["scope"].currentIndex()
            r["scope"].blockSignals(True)
            r["scope"].setItemText(0, self.app._t("kw_scope_both"))
            r["scope"].setItemText(1, self.app._t("kw_scope_rx"))
            r["scope"].setItemText(2, self.app._t("kw_scope_tx"))
            r["scope"].setCurrentIndex(sidx)
            r["scope"].blockSignals(False)

    def _apply_titlebar_theme(self):
        _set_win_titlebar_dark(self, self.app._theme().get("mode") == "dark")

    def refresh_theme(self):
        self._apply_titlebar_theme()
        c = chrome_for(self.app._theme_id())
        # 公共列表样式 + 左侧分组列表(QListWidget)样式
        self.setStyleSheet(_dialog_list_qss(c) + f"""
        QListWidget#KwGroupList {{
            background-color: {c['input_bg']};
            border: 1px solid {c['separator']};
            border-radius: 8px;
            color: {c['text']};
            font-family: 'Segoe UI'; font-size: 12px;
            outline: 0px;
            padding: 3px;
        }}
        QListWidget#KwGroupList::item {{ padding: 5px 6px; border-radius: 5px; }}
        QListWidget#KwGroupList::item:selected {{
            background-color: {c['accent']}; color: #FFFFFF;
        }}
        QListWidget#KwGroupList::item:hover {{ background-color: {c['ghost_hover']}; }}
        QListWidget#KwGroupList QLineEdit {{
            background-color: {c['input_focus_bg']};
            color: {c['text']};
            border: 1px solid {c['accent']};
            border-radius: 4px;
            padding: 1px 4px;
            selection-background-color: {c['accent']};
            selection-color: #FFFFFF;
        }}
        """)
        for r in self._rows:                       # 颜色按钮保持各自底色
            self._paint_color_btn(r)
            for key in ("mode", "scope"):
                popup = r[key].view().window()
                popup.setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")


# ============== 主窗口 ==============
class SerialTool(QMainWindow):
    RESIZE_MARGIN = 6

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        self.ser = None
        self.reader = None
        self.rx_bytes = 0
        self.tx_bytes = 0

        self.send_timer = QTimer(self)
        self.send_timer.timeout.connect(self.do_send)

        self._last_port_list = []
        self.port_scanner = None

        self._last_recv_time = 0.0
        self._last_direction = None
        self._pending_line_break = False
        self._rx_decode_buffer = b""
        self._rx_pending_cr = False
        self._inc_decoder = None  # 重置增量解码器（None → _decode_rx 首次调用时按当前 codec 重建）
        self._txt_ends_with_nl = True
        self._log_file = None
        self._log_file_path = ""
        self._log_limit = 0       # 分包字节上限，0=不分包
        self._log_base_path = ""  # 用户选的原始路径，分包时据此派生 _001/_002...
        self._log_seg = 0         # 当前分包序号
        self._recv_font_size = 10

        self.settings = QSettings(self._settings_file(), QSettings.IniFormat)
        saved_lang = self.settings.value("language", "zh")
        self._lang = saved_lang if saved_lang in TR else "zh"
        self._L = TR[self._lang]

        self._closing_real = False
        self._tray = None

        self.init_ui()
        self.refresh_ports()
        self.apply_style()
        self._load_settings()
        self._setup_tray()

        self.port_scanner = PortScannerThread(interval_ms=1500)
        self.port_scanner.scan_complete.connect(self._on_port_scan_complete)
        self.port_scanner.start()

    def _t(self, key, **kwargs) -> str:
        s = self._L.get(key, key)
        return s.format(**kwargs) if kwargs else s

    def _theme_label(self, theme_id: str) -> str:
        """主题显示名 — 优先用翻译 key (theme_<id>)，缺失就回退到 THEMES['label'] 英文名"""
        key = f"theme_{theme_id}"
        s = self._L.get(key)
        if s:
            return s
        return THEMES.get(theme_id, {}).get("label", theme_id)

    def _theme_id(self) -> str:
        if not hasattr(self, "cb_theme"):
            return THEME_DEFAULT
        return self.cb_theme.currentData() or THEME_DEFAULT

    def _set_state_color(self, opened: bool):
        """状态点色：打开 = 通用绿（任何主题都看得清）；关闭 = 主题 danger 红"""
        color = "#34C759" if opened else chrome_for(self._theme_id())["danger"]
        self.lbl_state.setStyleSheet(f"color: {color};")

    def _label_col_width(self) -> int:
        """串口设置左侧标签列宽：按当前语言下 5 个标签的最大实测文本宽度自适应，
        避免英文单词(如 Baud Rate)被输入框遮挡。"""
        keys = ("port", "baud_rate", "data_bits", "parity", "stop_bits")
        fm = QFontMetrics(QFont("Segoe UI", 11))
        w = max(fm.horizontalAdvance(self._t(k)) for k in keys)
        return max(44, w + 9)  # +9 右边距；中文下至少 44 保持原观感

    def _tr_label(self, key, size=11, bold=False, color=COLOR_TEXT):
        lbl = make_label(self._t(key), size, bold, color)
        lbl.setProperty("tr_text", key)
        # 自动挂 tooltip：若同名 _tip 键存在则用它，语言切换时由 _apply_language 同步
        tip_key = key + "_tip"
        if tip_key in self._L:
            lbl.setToolTip(self._L[tip_key])
            lbl.setProperty("tr_tooltip", tip_key)
        return lbl

    # ----- UI 构建 -----
    def init_ui(self):
        self.setWindowTitle(self._t("app_title"))
        self.resize(1140, 740)
        self.setMinimumSize(960, 600)

        central = QWidget()
        central.setObjectName("Central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏
        self.title_bar = TitleBar(self)
        self.title_bar.set_title(self._t("app_title"))
        self.title_bar.set_app_icon(get_app_icon())

        self.cb_language = self.title_bar.cb_language
        self.cb_language.addItem(TR["zh"]["lang_zh"], "zh")
        self.cb_language.addItem(TR["en"]["lang_en"], "en")
        self.cb_language.addItem(TR["zh_tw"]["lang_tw"], "zh_tw")
        lang_idx = {"zh": 0, "en": 1, "zh_tw": 2}.get(self._lang, 0)
        self.cb_language.setCurrentIndex(lang_idx)
        self.cb_language.currentIndexChanged.connect(
            lambda i: self._set_language(self.cb_language.itemData(i)))

        # 主题下拉 — 也在标题栏左侧
        self.cb_theme = self.title_bar.cb_theme
        for theme_id in THEMES.keys():
            self.cb_theme.addItem(self._theme_label(theme_id), theme_id)
        self.cb_theme.setProperty("tr_tooltip", "theme_tip")
        self.cb_theme.setToolTip(self._t("theme_tip"))
        self.cb_theme.currentIndexChanged.connect(lambda _: self._on_theme_changed())

        root.addWidget(self.title_bar)

        # 内容
        content = QWidget()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 12, 20, 12)
        content_layout.setSpacing(10)
        root.addWidget(content, 1)

        # 右侧改用 QVBoxLayout（去掉 v_splitter）：数据区拉伸，发送区自然高度贴底
        # 这样和左侧 sidebar 的结构一致（左侧 3 张卡也是数据区拉伸 + 发送区贴底）
        right_container = QWidget()
        right_v = QVBoxLayout(right_container)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(10)
        right_v.addWidget(self.build_receive_card(), 1)   # 数据区：拉伸吃多余空间
        self._right_send_card = self.build_send_card()
        right_v.addWidget(self._right_send_card)           # 发送区：自然高度，贴底

        # 主水平分隔条：左侧 sidebar | 右侧 container
        self.h_splitter = QSplitter(Qt.Horizontal)
        self.h_splitter.setChildrenCollapsible(False)
        self.h_splitter.setHandleWidth(8)
        self.h_splitter.addWidget(self.build_sidebar())
        self.h_splitter.addWidget(right_container)
        self.h_splitter.setStretchFactor(0, 0)
        self.h_splitter.setStretchFactor(1, 1)
        self.h_splitter.setSizes([280, 860])

        content_layout.addWidget(self.h_splitter, 1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(f"background: transparent; color: {COLOR_TEXT_SECONDARY};")
        # 左右边距和上面的 content_layout (20px) 对齐
        self.status_bar.setContentsMargins(20, 0, 20, 0)
        self.status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self.status_bar)
        self.lbl_rx_stat = QLabel("RX: 0 B")
        self.lbl_tx_stat = QLabel("TX: 0 B")
        self.lbl_state = QLabel(self._t("state_closed"))
        self._set_state_color(opened=False)
        for lbl in (self.lbl_state, self.lbl_rx_stat, self.lbl_tx_stat):
            lbl.setFont(QFont("Segoe UI", 10))

        def _sep():
            """竖线分隔符（无自带色 → 跟随状态栏 text_sec，主题自适应）"""
            s = QLabel("│")
            s.setFont(QFont("Segoe UI", 10))
            s.setObjectName("StatusSep")
            return s

        # 三个状态项放左下角 — 用 addWidget 而非 addPermanentWidget
        # (addPermanentWidget 会贴右边；addWidget 走左边，缺点是 toast 出现时会被临时遮盖)
        self.status_bar.addWidget(self.lbl_state)
        self.status_bar.addWidget(_sep())
        self.status_bar.addWidget(self.lbl_rx_stat)
        self.status_bar.addWidget(_sep())
        self.status_bar.addWidget(self.lbl_tx_stat)

        # 实时记录文件路径 — 右下角(版本号左侧)，仅记录时显示，太长中间省略+悬停看全路径
        self.lbl_log_path = QLabel("")
        self.lbl_log_path.setFont(QFont("Segoe UI", 9))
        self.lbl_log_path.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self._log_path_elide_w = 560
        self.status_bar.addPermanentWidget(self.lbl_log_path)
        self._log_path_sep = _sep()
        self._log_path_sep.hide()    # 未记录时隐藏这条分隔，避免悬空
        self.status_bar.addPermanentWidget(self._log_path_sep)

        # 版本号 — 右下角 (addPermanentWidget 走右边)
        self.lbl_version = QLabel(f"v{APP_VERSION}")
        self.lbl_version.setFont(QFont("Segoe UI", 10))
        self.lbl_version.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self.status_bar.addPermanentWidget(self.lbl_version)

        # 同步最大行数
        self._on_max_lines_changed()

    def build_sidebar(self):
        host = QWidget()
        host.setObjectName("SidebarHost")
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(self.build_settings_card())
        # 数据区 options 卡片 stretch=1，吃多余高度（保存/清空按钮始终贴卡片底部）
        v.addWidget(self.build_data_options_card(), 1)
        # 发送区卡片：自然高度，贴侧边栏底部
        self._left_send_card = self.build_send_options_card()
        v.addWidget(self._left_send_card)
        # 不加底部 stretch — 让发送区和右侧 send_card 同样贴底

        scroll = QScrollArea()
        scroll.setWidget(host)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("Sidebar")
        scroll.setMinimumWidth(260)
        scroll.setMaximumWidth(380)
        return scroll

    def build_settings_card(self):
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(self._tr_label("serial_settings", 12, bold=True))

        # 端口
        r = QHBoxLayout(); r.setSpacing(6)
        lbl = self._tr_label("port", color=COLOR_TEXT_SECONDARY); lbl.setFixedWidth(self._label_col_width()); lbl.setProperty("tr_fixedw", True)
        r.addWidget(lbl)
        self.cb_port = QComboBox()
        self.cb_port.setMinimumWidth(100)
        r.addWidget(self.cb_port, 1)
        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setObjectName("IconBtn")
        self.btn_refresh.setFixedSize(30, 26)
        self.btn_refresh.clicked.connect(self.refresh_ports)
        r.addWidget(self.btn_refresh)
        layout.addLayout(r)

        # 波特率
        r = QHBoxLayout(); r.setSpacing(6)
        lbl = self._tr_label("baud_rate", color=COLOR_TEXT_SECONDARY); lbl.setFixedWidth(self._label_col_width()); lbl.setProperty("tr_fixedw", True)
        r.addWidget(lbl)
        self.cb_baud = QComboBox()
        self.cb_baud.setEditable(True)
        for b in ["1200", "2400", "4800", "9600", "19200", "38400", "57600",
                  "115200", "230400", "256000", "460800", "500000", "512000",
                  "600000", "750000", "921600", "1000000", "1500000", "2000000"]:
            self.cb_baud.addItem(b)
        self.cb_baud.setCurrentText("115200")
        r.addWidget(self.cb_baud, 1)
        layout.addLayout(r)

        # 数据位
        r = QHBoxLayout(); r.setSpacing(6)
        lbl = self._tr_label("data_bits", color=COLOR_TEXT_SECONDARY); lbl.setFixedWidth(self._label_col_width()); lbl.setProperty("tr_fixedw", True)
        r.addWidget(lbl)
        self.cb_databits = QComboBox()
        self.cb_databits.addItems(["5", "6", "7", "8"])
        self.cb_databits.setCurrentText("8")
        r.addWidget(self.cb_databits, 1)
        layout.addLayout(r)

        # 校验
        r = QHBoxLayout(); r.setSpacing(6)
        lbl = self._tr_label("parity", color=COLOR_TEXT_SECONDARY); lbl.setFixedWidth(self._label_col_width()); lbl.setProperty("tr_fixedw", True)
        r.addWidget(lbl)
        self.cb_parity = QComboBox()
        self.cb_parity.addItems(["None", "Even", "Odd", "Mark", "Space"])
        r.addWidget(self.cb_parity, 1)
        layout.addLayout(r)

        # 停止位
        r = QHBoxLayout(); r.setSpacing(6)
        lbl = self._tr_label("stop_bits", color=COLOR_TEXT_SECONDARY); lbl.setFixedWidth(self._label_col_width()); lbl.setProperty("tr_fixedw", True)
        r.addWidget(lbl)
        self.cb_stopbits = QComboBox()
        self.cb_stopbits.addItems(["1", "1.5", "2"])
        self.cb_stopbits.setCurrentText("1")
        r.addWidget(self.cb_stopbits, 1)
        layout.addLayout(r)

        # 打开按钮
        self.btn_open = QPushButton(self._t("open_serial"))
        self.btn_open.setObjectName("PrimaryBtn")
        self.btn_open.setMinimumHeight(34)
        self.btn_open.clicked.connect(self.toggle_serial)
        layout.addWidget(self.btn_open)

        return card

    def build_data_options_card(self):
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(self._tr_label("data_area", 12, bold=True))

        MAIN_W = 90
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        def lbl(key):
            return self._tr_label(key, color=COLOR_TEXT_SECONDARY)

        def sw_row(row, key, sw):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(sw, row, 2, alignment=Qt.AlignRight)

        def sw_extra_row(row, key, sw, extra):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(sw, row, 1, alignment=Qt.AlignRight)
            grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

        def extra_row(row, key, extra):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

        def input_with_ms(input_widget):
            input_widget.setAlignment(Qt.AlignRight)
            box = QWidget()
            box.setFixedWidth(MAIN_W)
            h = QHBoxLayout(box); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
            h.addWidget(input_widget, 1)
            h.addWidget(make_label("ms", color=COLOR_TEXT_SECONDARY))
            return box

        row = 0
        self.sw_rx_hex = IOSSwitch(False)
        # 切 HEX/文本 显示时复位增量解码状态：否则文本模式残留的半个多字节
        # 在切回文本时会和新数据拼接错误解码 → 乱码
        self.sw_rx_hex.toggled.connect(lambda _=False: self._on_encoding_changed())
        sw_row(row, "hex_display", self.sw_rx_hex); row += 1

        # 字符编码 — 影响 RX 解码、TX 编码、文件加载
        self.cb_encoding = QComboBox()
        self.cb_encoding.addItem(self._t("encoding_auto"), "auto")
        for codec_name in ("UTF-8", "GBK", "GB2312", "GB18030", "Big5", "ASCII", "Latin-1"):
            self.cb_encoding.addItem(codec_name, codec_name.lower())
        self.cb_encoding.setFixedWidth(MAIN_W)
        self.cb_encoding.currentIndexChanged.connect(lambda _: self._on_encoding_changed())
        extra_row(row, "encoding", self.cb_encoding); row += 1

        self.sw_wrap = IOSSwitch(True)
        self.sw_wrap.toggled.connect(self.on_wrap_toggled)
        sw_row(row, "auto_wrap", self.sw_wrap); row += 1

        self.sw_show_timestamp = IOSSwitch(False)
        sw_row(row, "show_timestamp", self.sw_show_timestamp); row += 1

        self.sw_packet_split = IOSSwitch(False)
        sw_row(row, "packet_split", self.sw_packet_split); row += 1

        self.ed_packet_timeout = QLineEdit("20")
        extra_row(row, "timeout", input_with_ms(self.ed_packet_timeout)); row += 1

        self.sw_line_split = IOSSwitch(False)
        self.cb_line_nl = QComboBox()
        self.cb_line_nl.addItem(self._t("nl_auto"))
        self.cb_line_nl.addItem("CRLF")
        self.cb_line_nl.addItem("LF")
        self.cb_line_nl.addItem("CR")
        self.cb_line_nl.setFixedWidth(MAIN_W)
        # 切换换行模式时把待定 \r 冲出来（防止从 CRLF 切到 LF/CR 后旧 \r 永远见不到）
        self.cb_line_nl.currentIndexChanged.connect(lambda _: self._flush_pending_cr())
        sw_extra_row(row, "line_split", self.sw_line_split, self.cb_line_nl); row += 1

        self.sw_log_file = IOSSwitch(False)
        self.sw_log_file.toggled.connect(self.on_log_file_toggled)
        # 实时记录按文件大小分包：到设定大小切到新文件（可编辑自定义，如 3M）
        self.cb_log_split = QComboBox()
        self.cb_log_split.setEditable(True)
        self.cb_log_split.addItem(self._t("log_split_none"))   # 不分包
        for s in ("1M", "2M", "5M", "10M", "20M", "50M", "100M"):
            self.cb_log_split.addItem(s)
        self.cb_log_split.setCurrentIndex(0)
        self.cb_log_split.setFixedWidth(MAIN_W)
        self.cb_log_split.setToolTip(self._t("log_split_tip"))
        self.cb_log_split.setProperty("tr_tooltip", "log_split_tip")
        self.cb_log_split.currentTextChanged.connect(self._on_log_split_changed)
        sw_extra_row(row, "real_time_log", self.sw_log_file, self.cb_log_split); row += 1


        self.ed_max_lines = QLineEdit("10000")
        self.ed_max_lines.setAlignment(Qt.AlignRight)
        self.ed_max_lines.setFixedWidth(MAIN_W)
        self.ed_max_lines.editingFinished.connect(self._on_max_lines_changed)
        extra_row(row, "max_lines", self.ed_max_lines); row += 1

        layout.addLayout(grid)
        layout.addStretch(1)  # 卡片被拉伸时吃掉多余空间，让按钮始终贴卡片底部

        # 保存 / 清空：保存贴左，清空贴右
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(6)

        self.btn_save = QPushButton(self._t("save"))
        self.btn_save.setObjectName("GhostBtn")
        self.btn_save.setFixedWidth(MAIN_W)
        self.btn_save.setProperty("tr_text", "save")
        self.btn_save.clicked.connect(self.save_recv)
        btns.addWidget(self.btn_save)

        btns.addStretch(1)

        self.btn_clear_rx = QPushButton(self._t("clear"))
        self.btn_clear_rx.setObjectName("GhostBtn")
        self.btn_clear_rx.setFixedWidth(MAIN_W)
        self.btn_clear_rx.setProperty("tr_text", "clear")
        self.btn_clear_rx.clicked.connect(self.clear_recv)
        btns.addWidget(self.btn_clear_rx)

        layout.addLayout(btns)
        return card

    def build_send_options_card(self):
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(self._tr_label("send_area", 12, bold=True))

        MAIN_W = 90
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        def lbl(key):
            return self._tr_label(key, color=COLOR_TEXT_SECONDARY)

        def sw_row(row, key, sw):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(sw, row, 2, alignment=Qt.AlignRight)

        def sw_extra_row(row, key, sw, extra):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(sw, row, 1, alignment=Qt.AlignRight)
            grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

        def extra_row(row, key, extra):
            grid.addWidget(lbl(key), row, 0)
            grid.addWidget(extra, row, 2, alignment=Qt.AlignRight)

        def input_with_ms(input_widget):
            input_widget.setAlignment(Qt.AlignRight)
            box = QWidget()
            box.setFixedWidth(MAIN_W)
            h = QHBoxLayout(box); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
            h.addWidget(input_widget, 1)
            h.addWidget(make_label("ms", color=COLOR_TEXT_SECONDARY))
            return box

        row = 0
        self.sw_tx_hex = IOSSwitch(False)
        sw_row(row, "hex_send", self.sw_tx_hex); row += 1

        self.sw_append_newline = IOSSwitch(False)
        self.cb_append_nl = QComboBox()
        self.cb_append_nl.addItem("CRLF")
        self.cb_append_nl.addItem("LF")
        self.cb_append_nl.addItem("CR")
        self.cb_append_nl.setFixedWidth(MAIN_W)
        sw_extra_row(row, "append_newline", self.sw_append_newline, self.cb_append_nl); row += 1

        self.sw_period = IOSSwitch(False)
        self.sw_period.toggled.connect(self.on_period_toggled)
        self.ed_period_ms = QLineEdit("1000")
        sw_extra_row(row, "period", self.sw_period,
                     input_with_ms(self.ed_period_ms)); row += 1

        self.cb_checksum = QComboBox()
        for ck_key in CHECKSUM_KEYS:
            self.cb_checksum.addItem(self._t(ck_key))
        self.cb_checksum.setFixedWidth(MAIN_W)
        extra_row(row, "checksum", self.cb_checksum); row += 1

        layout.addLayout(grid)
        return card

    def build_receive_card(self):
        """右侧主区域：数据区"""
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.addWidget(self._tr_label("data_area", 13, bold=True))
        title_row.addSpacing(10)
        self.legend_label = QLabel(
            f'<span style="color:{COLOR_TEXT_SECONDARY};">{self._t("legend_rx")}</span>'
            f'&nbsp;&nbsp;'
            f'<span style="color:{COLOR_BLUE};">{self._t("legend_tx")}</span>'
        )
        self.legend_label.setFont(QFont("Segoe UI", 10))
        self.legend_label.setStyleSheet("background: transparent;")
        title_row.addWidget(self.legend_label)
        title_row.addStretch(1)

        # 生效分组下拉（顶部「（关闭）」+ 各分组）—— 选哪个分组就按哪个分组高亮
        self.cb_kw_group = QComboBox()
        self.cb_kw_group.setMinimumWidth(96)
        self.cb_kw_group.currentIndexChanged.connect(self._on_kw_group_changed)
        title_row.addWidget(self.cb_kw_group)
        title_row.addSpacing(6)

        self.btn_keyword = QPushButton(self._t("kw_highlight"))
        self.btn_keyword.setObjectName("GhostBtn")
        self.btn_keyword.setProperty("tr_text", "kw_highlight")
        self.btn_keyword.clicked.connect(self.open_keyword_highlight)
        title_row.addWidget(self.btn_keyword)
        title_row.addSpacing(6)

        # 只显高亮行：可切换按钮，开启后数据区只保留命中关键字的行（折叠其余）
        self.btn_filter_hl = QPushButton(self._t("filter_highlight"))
        self.btn_filter_hl.setObjectName("GhostBtn")
        self.btn_filter_hl.setCheckable(True)
        self.btn_filter_hl.setProperty("tr_text", "filter_highlight")
        self.btn_filter_hl.toggled.connect(self._on_filter_hl_toggled)
        title_row.addWidget(self.btn_filter_hl)
        title_row.addSpacing(8)

        self.btn_font_dec = QPushButton("A−")
        self.btn_font_dec.setObjectName("IconBtn")
        self.btn_font_dec.setFixedSize(34, 30)
        self.btn_font_dec.setProperty("tr_tooltip", "font_dec")
        self.btn_font_dec.setToolTip(self._t("font_dec"))
        self.btn_font_dec.clicked.connect(lambda: self.change_recv_font_size(-1))
        title_row.addWidget(self.btn_font_dec)

        self.btn_font_inc = QPushButton("A+")
        self.btn_font_inc.setObjectName("IconBtn")
        self.btn_font_inc.setFixedSize(34, 30)
        self.btn_font_inc.setProperty("tr_tooltip", "font_inc")
        self.btn_font_inc.setToolTip(self._t("font_inc"))
        self.btn_font_inc.clicked.connect(lambda: self.change_recv_font_size(+1))
        title_row.addWidget(self.btn_font_inc)

        layout.addLayout(title_row)

        self.txt_recv = QTextEdit()
        self.txt_recv.setReadOnly(True)
        self.txt_recv.setObjectName("RecvBox")
        self.txt_recv.setFont(QFont("Consolas", self._recv_font_size))
        self.txt_recv.setLineWrapMode(QTextEdit.WidgetWidth)
        self.txt_recv.document().setMaximumBlockCount(10000)
        layout.addWidget(self.txt_recv, 1)

        # ----- 单击行高亮 + 滚动锁定/回到底部（仿 SuperCom）-----
        self._recv_highlight_line = -1          # 当前高亮的块号，-1 表示无
        # 关键字高亮分组: [{name, rules:[{pattern,mode,scope,color,enabled}]}]，_keyword_active=生效分组(-1关闭)
        self._keyword_groups, self._keyword_active, _kw_ok = self._load_keyword_groups()
        if not _kw_ok:      # 迁移/首次/损坏 → 落盘，避免每次启动重复迁移
            self._save_keyword_groups()
        self._rebuild_kw_group_combo()      # 填充标题栏分组下拉
        # 节流定时器：收数据高频，关键字重扫合并到 ~150ms 一次，避免卡顿
        self._kw_timer = QTimer(self)
        self._kw_timer.setSingleShot(True)
        self._kw_timer.setInterval(150)
        self._kw_timer.timeout.connect(self._refresh_extra_selections)
        # 浮动「回到底部」按钮：做成 txt_recv 子控件，悬在右下角；翻到上面才显示
        self.btn_to_bottom = QPushButton(self._t("to_bottom"), self.txt_recv)
        self.btn_to_bottom.setObjectName("ToBottomBtn")
        self.btn_to_bottom.setProperty("tr_text", "to_bottom")
        self.btn_to_bottom.setCursor(Qt.PointingHandCursor)
        self.btn_to_bottom.clicked.connect(self._scroll_recv_to_bottom)
        self.btn_to_bottom.hide()
        # 滚动条变化时判断是否在底部，决定按钮显隐
        self.txt_recv.verticalScrollBar().valueChanged.connect(self._on_recv_scroll)
        # 监听 viewport 点击(行高亮) 和 txt_recv 尺寸变化(重定位按钮)
        self.txt_recv.viewport().installEventFilter(self)
        self.txt_recv.installEventFilter(self)
        # 自定义右键菜单（跟随程序语言）：在 eventFilter 拦截 ContextMenu 事件弹出
        # （QTextEdit 的右键事件发往 viewport，CustomContextMenu 信号路由不稳，故走 eventFilter）
        self.txt_recv.setContextMenuPolicy(Qt.PreventContextMenu)

        return card

    def _recv_context_menu(self, global_pos):
        """数据区右键菜单：复制 / 全选 / 清空 / 保存，文字跟随程序语言。"""
        menu = QMenu(self.txt_recv)
        c = chrome_for(self._theme_id())
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['card_bg']}; color: {c['text']};
                     border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
            QMenu::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
            QMenu::item:disabled {{ color: {c['text_sec']}; }}
            QMenu::separator {{ height: 1px; background: {c['separator']}; margin: 4px 8px; }}
        """)
        has_sel = self.txt_recv.textCursor().hasSelection()
        has_text = bool(self.txt_recv.document().characterCount() > 1)
        act_copy = menu.addAction(self._t("ctx_copy"))
        act_copy.setEnabled(has_sel)
        act_all = menu.addAction(self._t("ctx_select_all"))
        act_all.setEnabled(has_text)
        menu.addSeparator()
        act_clear = menu.addAction(self._t("clear"))
        act_clear.setEnabled(has_text)
        act_save = menu.addAction(self._t("save"))
        act_save.setEnabled(has_text)
        chosen = menu.exec_(global_pos)
        if chosen is act_copy:
            self.txt_recv.copy()
        elif chosen is act_all:
            self.txt_recv.selectAll()
        elif chosen is act_clear:
            self.clear_recv()
        elif chosen is act_save:
            self.save_recv()

    # ----- 数据区：滚动锁定 + 单击行高亮 -----
    def eventFilter(self, obj, event):
        if hasattr(self, "txt_recv"):
            # 接收区尺寸变化 → 重定位浮动「回到底部」按钮
            if obj is self.txt_recv and event.type() == QEvent.Resize:
                self._reposition_to_bottom_btn()
            elif obj is self.txt_recv.viewport():
                # 右键 → 自定义中文菜单（拦截并消费，阻止 Qt 默认菜单）
                if event.type() == QEvent.ContextMenu:
                    self._recv_context_menu(event.globalPos())
                    return True
                # 左键单击 → 整行高亮
                elif (event.type() == QEvent.MouseButtonPress
                      and event.button() == Qt.LeftButton):
                    self._highlight_recv_line(event.pos())
        return super().eventFilter(obj, event)

    def _recv_at_bottom(self, slack: int = 4) -> bool:
        sb = self.txt_recv.verticalScrollBar()
        return sb.value() >= sb.maximum() - slack

    def _scroll_recv_to_bottom(self):
        sb = self.txt_recv.verticalScrollBar()
        sb.setValue(sb.maximum())
        self.btn_to_bottom.hide()

    def _on_recv_scroll(self, _value=None):
        """用户往上翻 → 显示「回到底部」；回到底部 → 隐藏并恢复跟随"""
        self.btn_to_bottom.setVisible(not self._recv_at_bottom())
        self._reposition_to_bottom_btn()

    def _reposition_to_bottom_btn(self):
        if not hasattr(self, "btn_to_bottom"):
            return
        self.btn_to_bottom.adjustSize()
        vp = self.txt_recv.viewport()
        bw = self.btn_to_bottom.width()
        bh = self.btn_to_bottom.height()
        # 右下角，留 12px 边距（基于 viewport 尺寸，避开滚动条）
        x = vp.width() - bw - 12
        y = vp.height() - bh - 12
        self.btn_to_bottom.move(max(0, x), max(0, y))
        self.btn_to_bottom.raise_()

    def _highlight_recv_line(self, pos):
        """单击数据区某一行 → 整行高亮；点已高亮行则取消"""
        cur = self.txt_recv.cursorForPosition(pos)
        block_no = cur.blockNumber()
        if block_no == self._recv_highlight_line:
            self._recv_highlight_line = -1
        else:
            self._recv_highlight_line = block_no
        self._refresh_extra_selections()

    def _apply_recv_highlight(self):
        """兼容旧调用名：刷新所有叠加高亮(行高亮 + 关键字高亮)"""
        self._refresh_extra_selections()

    def _schedule_keyword_rebuild(self):
        """收到新数据时调用：生效分组有规则才启动节流定时器重扫"""
        if self._active_rules() and not self._kw_timer.isActive():
            self._kw_timer.start()

    _KW_MAX_SELECTIONS = 2000  # 安全上限，避免像 '00' 这种在 HEX 流里匹配出上万条

    def _refresh_extra_selections(self):
        """统一构建数据区叠加高亮：关键字着色(背景/文字，分收/发范围) + 单击行高亮(最上层)；
        若开启「只显高亮行」过滤，则隐藏未命中关键字的行(块可见性折叠)。"""
        if not hasattr(self, "txt_recv"):
            return
        doc = self.txt_recv.document()
        sels = []
        # 1. 关键字高亮（生效分组；区分大小写子串匹配；按规则 scope 限定 收/发/收发）
        rules = [r for r in self._active_rules()
                 if r.get("enabled", True) and r.get("pattern")]
        # (pattern, QColor, is_bg, scope) — scope: 'both'/'rx'/'tx'
        parsed = [(r["pattern"], QColor(r.get("color", "#FFD60A")),
                   r.get("mode", "bg") == "bg", r.get("scope", "both")) for r in rules]
        # 过滤仅在有 启用+非空 规则时才生效，避免"开了过滤却没规则 → 全空"
        filter_on = self._filter_active()
        capped = False
        dirty = False
        block = doc.begin()
        while block.isValid():
            block_has_match = False
            if parsed and not capped:
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    role = frag.charFormat().property(ROLE_PROP) if frag.isValid() else None
                    if role in (ROLE_RX, ROLE_TX):
                        ftext = frag.text()
                        base = frag.position()
                        for pat, col, is_bg, scope in parsed:
                            if scope == "rx" and role != ROLE_RX:
                                continue
                            if scope == "tx" and role != ROLE_TX:
                                continue
                            start = 0
                            while True:
                                idx = ftext.find(pat, start)
                                if idx < 0:
                                    break
                                block_has_match = True
                                sel = QTextEdit.ExtraSelection()
                                if is_bg:
                                    sel.format.setBackground(col)
                                else:
                                    sel.format.setForeground(col)
                                cur = QTextCursor(doc)
                                cur.setPosition(base + idx)
                                cur.setPosition(base + idx + len(pat), QTextCursor.KeepAnchor)
                                sel.cursor = cur
                                sels.append(sel)
                                start = idx + len(pat)
                                if len(sels) >= self._KW_MAX_SELECTIONS:
                                    capped = True
                                    break
                            if capped:
                                break
                    it += 1
                    if capped:
                        break
            # 过滤：开启时只留命中行；关闭时所有行可见（恢复）
            want_vis = block_has_match if filter_on else True
            if block.isVisible() != want_vis:
                block.setVisible(want_vis)
                dirty = True
            block = block.next()
        if dirty:
            doc.markContentsDirty(0, doc.characterCount())
            self.txt_recv.viewport().update()
        # 2. 单击行高亮（放最后 → 画在最上层），中性半透明，不跟文字撞色
        if self._recv_highlight_line >= 0:
            block = doc.findBlockByNumber(self._recv_highlight_line)
            if block.isValid():
                is_dark = self._theme().get("mode") == "dark"
                hl = QColor(255, 255, 255, 46) if is_dark else QColor(0, 0, 0, 38)
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(hl)
                sel.format.setProperty(QTextFormat.FullWidthSelection, True)
                sel.cursor = QTextCursor(block)
                sels.append(sel)
            else:
                self._recv_highlight_line = -1
        self.txt_recv.setExtraSelections(sels)

    # ----- 关键字高亮：分组模型（多个命名分组，每组多条规则，单个生效分组）-----
    def _load_keyword_groups(self):
        """加载分组 + 生效分组名。兼容旧版扁平 keyword_rules → 迁移成「默认」分组。
        返回 (groups, active_index, loaded_ok)；loaded_ok=False 表示走了迁移/默认(损坏或缺失)，
        调用方据此落盘，避免每次启动重复迁移。active=-1 表示关闭。"""
        groups = []
        raw = self.settings.value("keyword_groups", "")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    groups = [g for g in data
                              if isinstance(g, dict) and isinstance(g.get("rules"), list)]
            except Exception:
                groups = []
        loaded_ok = bool(groups)
        if not groups:
            # 迁移旧扁平规则(若有)到「默认」分组
            old_rules = []
            old = self.settings.value("keyword_rules", "")
            if old:
                try:
                    parsed = json.loads(old)
                    if isinstance(parsed, list):
                        old_rules = parsed
                except Exception:
                    pass
            groups = [{"name": self._t("kw_default_group"), "rules": old_rules}]
        # 生效分组按名称记忆(索引会因增删变动)
        active = -1
        active_name = self.settings.value("keyword_active", "")
        if active_name:
            for i, g in enumerate(groups):
                if g.get("name") == active_name:
                    active = i
                    break
        return groups, active, loaded_ok

    def _save_keyword_groups(self):
        self.settings.setValue("keyword_groups",
                               json.dumps(self._keyword_groups, ensure_ascii=False))
        name = (self._keyword_groups[self._keyword_active]["name"]
                if 0 <= self._keyword_active < len(self._keyword_groups) else "")
        self.settings.setValue("keyword_active", name)
        self.settings.remove("keyword_rules")    # 清理已迁移的旧扁平键
        self.settings.sync()

    def _active_rules(self):
        """当前生效分组的规则列表；关闭(-1)或越界时返回空列表。"""
        if 0 <= self._keyword_active < len(self._keyword_groups):
            return self._keyword_groups[self._keyword_active]["rules"]
        return []

    def _apply_keyword_rules(self):
        """规则内容变更后：持久化 + 立即重扫高亮（绕过节流，立刻见效）"""
        self._save_keyword_groups()
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _rebuild_kw_group_combo(self):
        """重建数据区标题栏的分组下拉：顶部「（关闭）」+ 各分组名，选中当前生效分组。"""
        if not hasattr(self, "cb_kw_group"):
            return
        self.cb_kw_group.blockSignals(True)
        self.cb_kw_group.clear()
        self.cb_kw_group.addItem(self._t("kw_group_off"), -1)
        for i, g in enumerate(self._keyword_groups):
            self.cb_kw_group.addItem(g.get("name", f"组{i + 1}"), i)
        sel = 0
        for k in range(self.cb_kw_group.count()):
            if self.cb_kw_group.itemData(k) == self._keyword_active:
                sel = k
                break
        self.cb_kw_group.setCurrentIndex(sel)
        self.cb_kw_group.blockSignals(False)

    def _on_kw_group_changed(self, _i=None):
        """主界面切换生效分组：按哪个分组高亮。"""
        data = self.cb_kw_group.currentData()
        self._keyword_active = data if data is not None else -1
        self._save_keyword_groups()
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _kw_groups_changed(self):
        """弹窗里增/删/重命名分组后：钳制生效索引、存盘、重建主下拉、刷新高亮。"""
        if self._keyword_active >= len(self._keyword_groups):
            self._keyword_active = -1
        self._save_keyword_groups()
        self._rebuild_kw_group_combo()
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _on_filter_hl_toggled(self, _on=None):
        """切换「只显高亮行」：立即重算可见性"""
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _filter_active(self) -> bool:
        """「只显高亮行」是否真正生效：开关开 且 至少有一条 启用+非空 的规则。
        _append_block_data 与 _refresh_extra_selections 共用，避免判断不一致导致闪烁。"""
        if not (hasattr(self, "btn_filter_hl") and self.btn_filter_hl.isChecked()):
            return False
        return any(r.get("enabled", True) and r.get("pattern")
                   for r in self._active_rules())

    def _block_has_keyword_match(self, block) -> bool:
        """单个块的 RX/TX 正文是否命中生效分组里任一启用规则(按 scope 限定 收/发)"""
        rules = [r for r in self._active_rules()
                 if r.get("enabled", True) and r.get("pattern")]
        if not rules:
            return False
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            role = frag.charFormat().property(ROLE_PROP) if frag.isValid() else None
            if role in (ROLE_RX, ROLE_TX):
                ftext = frag.text()
                for r in rules:
                    scope = r.get("scope", "both")
                    if scope == "rx" and role != ROLE_RX:
                        continue
                    if scope == "tx" and role != ROLE_TX:
                        continue
                    if r["pattern"] in ftext:
                        return True
            it += 1
        return False

    def _role_color(self, role, theme=None):
        """数据区某角色(时间戳/RX/TX)在指定主题下的文字色"""
        theme = theme or self._theme()
        if role == ROLE_TS:
            return _mix(theme["ts"], theme["fg"], 0.40)
        if role == ROLE_TX:
            return theme["tx"]
        return theme["fg"]          # ROLE_RX 及兜底

    def _recolor_history(self):
        """切主题时把数据区已有文字按角色重涂成新主题色，避免浅↔深切换后看不见。
        遍历所有 fragment 读 ROLE_PROP，先收集区间再统一改(改格式会让迭代器失效)。
        大文档优化：合并相邻同色区间 + beginEditBlock 批处理 + 关刷新，避免逐片段重排卡死。"""
        theme = self._theme()
        doc = self.txt_recv.document()
        # 每个角色的目标色只算一次(原来每片段都建 QColor + 调 _role_color)
        role_col = {r: QColor(self._role_color(r, theme))
                    for r in (None, ROLE_TS, ROLE_RX, ROLE_TX)}
        ranges = []  # (start, end, QColor)，相邻同色自动合并
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    role = frag.charFormat().property(ROLE_PROP)
                    col = role_col.get(role, role_col[None])
                    start = frag.position()
                    end = start + frag.length()
                    if ranges and ranges[-1][1] == start and ranges[-1][2] == col:
                        ranges[-1] = (ranges[-1][0], end, col)   # 合并相邻同色
                    else:
                        ranges.append((start, end, col))
                it += 1
            block = block.next()
        if not ranges:
            return
        self.txt_recv.setUpdatesEnabled(False)
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        try:
            for start, end, col in ranges:
                cur.setPosition(start)
                cur.setPosition(end, QTextCursor.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setForeground(col)
                cur.mergeCharFormat(fmt)
        finally:
            cur.endEditBlock()
            self.txt_recv.setUpdatesEnabled(True)

    def build_send_card(self):
        """右侧主区域：发送区"""
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._tr_label("send_area", 13, bold=True))

        # ---- 多条发送快捷栏：选分组 + ▶/■ 循环 + 命令平铺直接发 ----
        self._ms_groups, _ms_ok = self._load_ms_groups()
        try:
            self._ms_group_idx = int(self.settings.value("multi_send_group_idx", 0))
        except (ValueError, TypeError):
            self._ms_group_idx = 0
        if not (0 <= self._ms_group_idx < len(self._ms_groups)):
            self._ms_group_idx = 0
        if not _ms_ok:    # 迁移/首次/损坏 → 落盘，避免每次启动重复迁移
            self._save_ms_groups()
        self._ms_cycle_seq = []
        self._ms_cycle_idx = 0
        self._ms_cycle_timer = QTimer(self)
        self._ms_cycle_timer.setSingleShot(True)
        self._ms_cycle_timer.timeout.connect(self._ms_cycle_step)

        ms_bar = QHBoxLayout()
        ms_bar.setSpacing(6)
        self.btn_multi = QPushButton(self._t("multi_send"))
        self.btn_multi.setObjectName("GhostBtn")
        self.btn_multi.setProperty("tr_text", "multi_send")
        self.btn_multi.clicked.connect(self.open_multi_send)
        ms_bar.addWidget(self.btn_multi)
        self.btn_ms_cycle = QPushButton(self._t("ms_cycle"))
        self.btn_ms_cycle.setObjectName("GhostBtn")
        self.btn_ms_cycle.clicked.connect(self._ms_toggle_cycle)
        ms_bar.addWidget(self.btn_ms_cycle)
        self.cb_ms_group = QComboBox()
        self.cb_ms_group.setMinimumWidth(110)
        self.cb_ms_group.currentIndexChanged.connect(self._on_ms_group_changed)
        ms_bar.addWidget(self.cb_ms_group)
        self._ms_quick_host = QWidget()
        self._ms_quick_host.setObjectName("MsQuickHost")
        self._ms_quick_h = QHBoxLayout(self._ms_quick_host)
        self._ms_quick_h.setContentsMargins(0, 0, 0, 0)
        self._ms_quick_h.setSpacing(6)
        self._ms_quick_host.setAutoFillBackground(False)
        ms_qscroll = QScrollArea()
        ms_qscroll.setObjectName("MsQuickScroll")
        ms_qscroll.setWidget(self._ms_quick_host)
        ms_qscroll.setWidgetResizable(True)
        ms_qscroll.setFrameShape(QFrame.NoFrame)
        ms_qscroll.setFixedHeight(38)
        ms_qscroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ms_qscroll.viewport().setAutoFillBackground(False)
        ms_bar.addWidget(ms_qscroll, 1)
        layout.addLayout(ms_bar)
        self._rebuild_ms_group_combo()
        self._rebuild_ms_quick_bar()

        self.txt_send = QTextEdit()
        self.txt_send.setObjectName("SendBox")
        self.txt_send.setFont(QFont("Consolas", 10))
        # 固定高度、不拉伸：否则与接收区(数据区)抢垂直空间，发送卡片被压缩导致按钮和发送框重叠
        self.txt_send.setFixedHeight(64)
        self.txt_send.setProperty("tr_placeholder", "send_placeholder")
        self.txt_send.setPlaceholderText(self._t("send_placeholder"))
        layout.addWidget(self.txt_send)

        btn_row = QHBoxLayout()
        self.btn_load = QPushButton(self._t("read_file"))
        self.btn_load.setObjectName("GhostBtn")
        self.btn_load.setProperty("tr_text", "read_file")
        self.btn_load.clicked.connect(self.load_file_to_send)
        btn_row.addWidget(self.btn_load)

        self.btn_clear_tx = QPushButton(self._t("clear"))
        self.btn_clear_tx.setObjectName("GhostBtn")
        self.btn_clear_tx.setProperty("tr_text", "clear")
        self.btn_clear_tx.clicked.connect(lambda: self.txt_send.clear())
        btn_row.addWidget(self.btn_clear_tx)

        btn_row.addStretch(1)

        self.btn_send = QPushButton(self._t("send_btn"))
        self.btn_send.setObjectName("PrimaryBtn")
        self.btn_send.setMinimumHeight(36)
        self.btn_send.setMinimumWidth(120)
        self.btn_send.setProperty("tr_text", "send_btn")
        self.btn_send.clicked.connect(self.do_send)
        btn_row.addWidget(self.btn_send)

        layout.addLayout(btn_row)
        return card

    def apply_style(self):
        """根据当前主题构建全局 QSS — light/dark 模式整体切换"""
        tid = self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT
        c = chrome_for(tid)
        t = THEMES.get(tid, THEMES[THEME_DEFAULT])

        # Tooltip 在 dark mode 用浅色 (反差)，light 用深色
        tooltip_bg = "#F2F2F7" if t.get("mode") == "dark" else "#1C1C1E"
        tooltip_fg = "#1C1C1E" if t.get("mode") == "dark" else "#FFFFFF"

        qss = f"""
        QMainWindow, QWidget#Central, QWidget#Content {{
            background-color: {c['window_bg']};
        }}
        QFrame#Card {{
            background-color: {c['card_bg']};
            border-radius: 14px;
            border: 0px;
        }}
        QLabel {{ color: {c['text']}; background: transparent; }}
        QComboBox, QLineEdit {{
            background-color: {c['input_bg']};
            border: 1px solid {c['separator']};
            border-radius: 6px;
            padding: 2px 7px;
            min-height: 16px;
            font-family: 'Segoe UI';
            font-size: 11px;
            color: {c['text']};
            selection-background-color: {c['accent']};
        }}
        QComboBox:focus, QLineEdit:focus {{
            border: 1px solid {c['accent']};
            background-color: {c['input_focus_bg']};
        }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {c['text_sec']};
            margin-right: 8px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['combo_dropdown_bg']};
            color: {c['text']};
            border: 1px solid {c['separator']};
            border-radius: 0px;
            padding: 4px;
            outline: 0px;
            selection-background-color: {c['accent']};
            selection-color: #FFFFFF;
        }}
        QPushButton#PrimaryBtn {{
            background-color: {c['accent']};
            color: white;
            border: 0px;
            border-radius: 9px;
            font-family: 'Segoe UI';
            font-size: 12px;
            font-weight: 600;
            padding: 5px 16px;
        }}
        QPushButton#PrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#PrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#PrimaryBtn[state="open"] {{ background-color: {c['danger']}; }}
        QPushButton#PrimaryBtn[state="open"]:hover {{ background-color: {c['danger_hover']}; }}
        QPushButton#GhostBtn {{
            background-color: {c['ghost_bg']};
            color: {c['accent']};
            border: 0px;
            border-radius: 7px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 500;
            padding: 5px 12px;
            min-height: 18px;
        }}
        QPushButton#GhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#GhostBtn:pressed {{ background-color: {c['ghost_pressed']}; }}
        QPushButton#GhostBtn:checked {{ background-color: {c['accent']}; color: white; }}
        QPushButton#IconBtn {{
            background-color: {c['ghost_bg']};
            color: {c['text_sec']};
            border: 0px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton#IconBtn:hover {{
            background-color: {c['ghost_hover']};
            color: {c['accent']};
        }}
        QScrollArea#MsQuickScroll, QWidget#MsQuickHost {{ background: transparent; border: 0px; }}
        QPushButton#MsQuickBtn {{
            background-color: {c['ghost_bg']}; color: {c['text']}; border: 1px solid {c['separator']};
            border-radius: 6px; font-family: 'Segoe UI'; font-size: 11px; padding: 2px 10px;
        }}
        QPushButton#MsQuickBtn:hover {{ background-color: {c['ghost_hover']}; color: {c['accent']}; }}
        QPushButton#MsQuickBtn:pressed {{ background-color: {c['ghost_pressed']}; }}
        QPushButton#ToBottomBtn {{
            background-color: {c['accent']};
            color: white;
            border: 0px;
            border-radius: 13px;
            padding: 4px 14px;
            font-family: 'Segoe UI';
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#ToBottomBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#ToBottomBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QTextEdit#RecvBox {{
            background-color: {t['bg']};
            border: 1px solid {c['separator']};
            border-radius: 10px;
            padding: 10px;
            color: {t['fg']};
            selection-background-color: {c['accent']};
        }}
        QTextEdit#SendBox {{
            background-color: {c['input_bg']};
            border: 1px solid {c['separator']};
            border-radius: 10px;
            padding: 10px;
            color: {c['text']};
            selection-background-color: {c['accent']};
        }}
        QTextEdit#RecvBox:focus, QTextEdit#SendBox:focus {{
            border: 1px solid {c['accent']};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {c['scrollbar']};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_hover']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QStatusBar {{
            background: transparent;
            color: {c['text_sec']};
            border-top: 1px solid {c['separator']};
        }}
        QStatusBar QLabel {{ color: {c['text_sec']}; background: transparent; }}
        QStatusBar::item {{ border: 0px; }}
        QToolTip {{
            background-color: {tooltip_bg};
            color: {tooltip_fg};
            border: 0px;
            border-radius: 6px;
            padding: 4px 8px;
        }}
        QWidget#TitleBar {{
            background-color: {c['window_bg']};
            border-bottom: 1px solid {c['separator']};
        }}
        QPushButton#CtrlBtn {{
            background-color: transparent;
            color: {c['text']};
            border: 0px;
            font-size: 14px;
            font-family: 'Segoe UI';
        }}
        QPushButton#CtrlBtn:hover {{ background-color: {c['title_btn_hover']}; }}
        QPushButton#CloseBtn:hover {{
            background-color: {c['danger']};
            color: #FFFFFF;
        }}
        QWidget#TitleBar QComboBox {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 1px 8px;
            min-height: 22px;
            font-size: 12px;
            color: {c['text']};
        }}
        QWidget#TitleBar QComboBox:hover {{
            background-color: {c['title_combo_hover']};
        }}
        QWidget#TitleBar QComboBox::drop-down {{
            border: none;
            width: 18px;
        }}
        QScrollArea#Sidebar {{
            background: transparent;
            border: 0px;
        }}
        QScrollArea#Sidebar > QWidget > QWidget {{
            background: transparent;
        }}
        QWidget#SidebarHost {{
            background: transparent;
        }}
        """
        self.setStyleSheet(qss)
        # 强制所有子 widget 重新评估样式 —— Qt 有时 setStyleSheet 后旧子组件保留缓存样式
        # 典型表现：重启后从设置里恢复主题，title bar 变了但中间数据区还是旧色
        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)

        # 下拉弹出容器(QComboBoxPrivateContainer)是独立顶层窗口，其底色走系统调色板默认白，
        # 深色主题下圆角/边框处会露白边。这里把每个下拉的弹出容器背景刷成下拉色，彻底消除白边。
        for combo in self.findChildren(QComboBox):
            popup = combo.view().window()
            popup.setStyleSheet(f"background-color: {c['combo_dropdown_bg']};")

    # ----- 端口扫描 -----
    def _clear_oneshot_scan(self, scan):
        """deleteLater 之后清掉 Python 属性引用，避免下次 isRunning() 访问已删 C++ 对象。
        `is scan` 守卫：如果期间已经创建了新 scan，不清新的"""
        if getattr(self, "_oneshot_scan", None) is scan:
            self._oneshot_scan = None

    def refresh_ports(self):
        """点 ⟳ 时调用 — 用一次性后台线程，避免慢驱动卡 GUI。
        扫描结果通过 _on_port_scan_complete 回 GUI 线程（和后台轮询线程共用同一处理逻辑）

        线程**不挂 parent**：万一退出时 wait(2000) 超时 comports() 还卡住，
        线程对象不会跟着主窗口一起销毁；finished 后 deleteLater() 自己清，
        同时 _clear_oneshot_scan 把 Python 属性置 None 避免悬空引用。
        """
        if getattr(self, "_oneshot_scan", None) and self._oneshot_scan.isRunning():
            return  # 节流：上一次还在跑就忽略
        scan = OneShotPortScanner()  # 故意无 parent
        self._oneshot_scan = scan
        scan.scan_complete.connect(self._on_port_scan_complete)
        scan.finished.connect(lambda: self._clear_oneshot_scan(scan))
        scan.finished.connect(scan.deleteLater)
        scan.start()

    def _populate_port_combo(self, port_list, keep_device=None):
        self.cb_port.blockSignals(True)
        self.cb_port.clear()
        for device, label in port_list:
            self.cb_port.addItem(label, device)
        if keep_device:
            for i in range(self.cb_port.count()):
                if self.cb_port.itemData(i) == keep_device:
                    self.cb_port.setCurrentIndex(i)
                    break
        self.cb_port.blockSignals(False)

    def _on_port_scan_complete(self, port_list):
        if not port_list:
            port_list = [("", self._t("no_ports"))]
        if self.cb_port.view().isVisible():
            return
        if self.ser and self.ser.is_open:
            return
        if port_list == self._last_port_list:
            return
        keep = self.cb_port.currentData()
        self._last_port_list = port_list
        self._populate_port_combo(port_list, keep)

    # ----- 串口打开/关闭 -----
    def toggle_serial(self):
        if self.ser and self.ser.is_open:
            self.close_serial()
        else:
            self.open_serial()

    def open_serial(self):
        port = self.cb_port.currentData() or self.cb_port.currentText().split(" ")[0]
        if not port or port.startswith("("):
            self.toast(self._t("err_no_port"), error=True)
            return
        try:
            baud = int(self.cb_baud.currentText())
        except ValueError:
            self.toast(self._t("err_bad_baud"), error=True)
            return

        parity_map = {"None": serial.PARITY_NONE, "Even": serial.PARITY_EVEN,
                      "Odd": serial.PARITY_ODD, "Mark": serial.PARITY_MARK,
                      "Space": serial.PARITY_SPACE}
        stopbits_map = {"1": serial.STOPBITS_ONE, "1.5": serial.STOPBITS_ONE_POINT_FIVE,
                        "2": serial.STOPBITS_TWO}
        databits_map = {"5": serial.FIVEBITS, "6": serial.SIXBITS,
                        "7": serial.SEVENBITS, "8": serial.EIGHTBITS}

        try:
            self.ser = serial.Serial(
                port=port, baudrate=baud,
                bytesize=databits_map[self.cb_databits.currentText()],
                parity=parity_map[self.cb_parity.currentText()],
                stopbits=stopbits_map[self.cb_stopbits.currentText()],
                timeout=0,
            )
        except Exception as e:
            self.toast(self._t("err_open_failed", e=e), error=True)
            self.ser = None
            return

        self.reader = SerialReader(self.ser)
        self.reader.data_received.connect(self.on_data_received)
        self.reader.error_occurred.connect(self.on_reader_error)
        self.reader.start()

        self.btn_open.setText(self._t("close_serial"))
        self.btn_open.setProperty("state", "open")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        self.lbl_state.setText(f"● {port} @ {baud}")
        self._set_state_color(opened=True)
        self.set_settings_enabled(False)

    def _flush_pending_cr(self):
        """把跨包待定的 \\r 输出出来。
        场景：CRLF 模式下设备只发了孤立 \\r 然后没下文，关串口/切模式时
        如果不冲掉，用户永远看不到那个 \\r。"""
        if not self._rx_pending_cr:
            return
        self._rx_pending_cr = False
        force_new = (self._last_direction != "rx") or self._pending_line_break
        self._append_block_data("\r", direction="rx", force_new_block=force_new)
        self._last_direction = "rx"

    def close_serial(self):
        if self.sw_period.isChecked():
            self.sw_period.setChecked(False)
        # 串口关之前先把待定 \r 显示出来，否则数据丢用户视觉
        # 同时要在关闭实时日志前执行，保证日志和屏幕显示一致。
        self._flush_pending_cr()
        if self.sw_log_file.isChecked():
            self.sw_log_file.setChecked(False)
        if self.reader:
            self.reader.stop()
            self.reader = None
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

        self._last_recv_time = 0.0
        self._last_direction = None
        self._pending_line_break = False
        self._rx_decode_buffer = b""
        self._rx_pending_cr = False

        self.btn_open.setText(self._t("open_serial"))
        self.btn_open.setProperty("state", "")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        self.lbl_state.setText(self._t("state_closed"))
        self._set_state_color(opened=False)
        self.set_settings_enabled(True)

    def set_settings_enabled(self, enabled):
        for w in (self.cb_port, self.cb_baud, self.cb_databits,
                  self.cb_parity, self.cb_stopbits, self.btn_refresh):
            w.setEnabled(enabled)

    # ----- 主题 -----
    def _theme(self) -> dict:
        return THEMES.get(self._theme_id(), THEMES[THEME_DEFAULT])

    def _apply_theme_label_styles(self, chrome: dict = None):
        c = chrome or chrome_for(self._theme_id())
        for lbl in self.findChildren(QLabel):
            role = lbl.property("theme_color_role")
            if role == "primary":
                lbl.setStyleSheet(f"color: {c['text']}; background: transparent;")
            elif role == "secondary":
                lbl.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")

    def _update_legend_label(self, chrome: dict = None):
        if not hasattr(self, "legend_label"):
            return
        c = chrome or chrome_for(self._theme_id())
        t = self._theme()
        self.legend_label.setText(
            f'<span style="color:{c["text_sec"]};">{self._t("legend_rx")}</span>'
            f'&nbsp;&nbsp;'
            f'<span style="color:{t["tx"]};">{self._t("legend_tx")}</span>'
        )

    def _on_theme_changed(self):
        """切换主题：整体重建 QSS — 侧边栏卡片/按钮/输入框/标题栏/数据区都跟着 light/dark 切换。
        数据区历史文字按角色(时间戳/RX/TX)重涂成新主题色，避免浅↔深切换后看不见。"""
        # 1. 重建全局 QSS，apply_style 会读 cb_theme 当前选项自适应
        self.apply_style()
        # 2. 内联 setStyleSheet 的几处也跟着 chrome palette 刷
        c = chrome_for(self._theme_id())
        self._apply_theme_label_styles(c)
        if hasattr(self, "lbl_version"):
            self.lbl_version.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")
        if hasattr(self, "lbl_log_path"):
            self.lbl_log_path.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")
        if hasattr(self, "status_bar"):
            self.status_bar.setStyleSheet(f"background: transparent; color: {c['text_sec']};")
        if hasattr(self, "lbl_state"):
            self._set_state_color(opened=bool(self.ser and self.ser.is_open))
        if hasattr(self, "title_bar") and hasattr(self.title_bar, "title_label"):
            self.title_bar.title_label.setStyleSheet(
                f"color: {c['text_sec']}; background: transparent;")
        self._update_legend_label(c)
        # 数据区历史文字按角色重涂成新主题色 + 行高亮换色（否则浅↔深切换后文字看不见）
        if hasattr(self, "txt_recv"):
            self._recolor_history()
            self._apply_recv_highlight()
        # 多条发送/关键字高亮弹窗若开着也跟着换主题
        if getattr(self, "_multi_send_dlg", None) is not None:
            self._multi_send_dlg.refresh_theme()
        if getattr(self, "_keyword_dlg", None) is not None:
            self._keyword_dlg.refresh_theme()

    # ----- 接收 -----
    def _get_codec(self) -> str:
        """当前 RX/TX/文件 编码模式 — 'auto' 或具体 codec 名"""
        if hasattr(self, "cb_encoding"):
            return self.cb_encoding.currentData() or "auto"
        return "auto"

    def _send_codec(self) -> str:
        """TX 用的具体 codec — Auto 模式下默认 utf-8"""
        c = self._get_codec()
        return "utf-8" if c == "auto" else c

    def _on_encoding_changed(self):
        """切换编码时重置增量解码状态，悬挂字节别用新 codec 错误解码"""
        self._rx_decode_buffer = b""
        enc = self._get_codec()
        if enc == "auto":
            self._inc_decoder = None
        else:
            try:
                self._inc_decoder = codecs.getincrementaldecoder(enc)(errors="replace")
            except (LookupError, TypeError):
                self._inc_decoder = None  # 罕见的找不到 codec 直接回退 auto

    def _decode_rx(self, data: bytes) -> str:
        """按选定编码增量解码。Auto 走 UTF-8 优先 / GBK 回退；其他走 Python 标准增量解码器"""
        if self._get_codec() != "auto":
            if self._inc_decoder is None:
                # 第一次调用 / 刚切到具体编码 — 初始化
                self._on_encoding_changed()
            if self._inc_decoder is not None:
                return self._inc_decoder.decode(data, final=False)
            # codec lookup 失败兜底
            return data.decode("latin-1")

        # Auto 模式 — 原 UTF-8 优先, 不完整就缓存, 真乱码回退 GBK
        self._rx_decode_buffer += data
        if not self._rx_decode_buffer:
            return ""
        try:
            text = self._rx_decode_buffer.decode("utf-8")
            self._rx_decode_buffer = b""
            return text
        except UnicodeDecodeError as e:
            if (e.end == len(self._rx_decode_buffer)
                    and "unexpected end of data" in str(e.reason)):
                try:
                    text = self._rx_decode_buffer[:e.start].decode("utf-8")
                    self._rx_decode_buffer = self._rx_decode_buffer[e.start:]
                    return text
                except UnicodeDecodeError:
                    pass
            text = self._rx_decode_buffer.decode("gbk", errors="replace")
            self._rx_decode_buffer = b""
            return text

    def on_data_received(self, data: bytes):
        # 顶层异常保护：解码/插入等意外异常不应静默丢数据(传到事件循环只在 stderr 打印)
        try:
            self._on_data_received_impl(data)
        except Exception as e:
            self.toast(self._t("err_rx", e=e), error=True)

    def _on_data_received_impl(self, data: bytes):
        self.rx_bytes += len(data)
        self.lbl_rx_stat.setText(f"RX: {self.fmt_bytes(self.rx_bytes)}")

        use_hex = self.sw_rx_hex.isChecked()
        use_line_split = self.sw_line_split.isChecked() and not use_hex
        now = time.monotonic()

        if use_hex:
            text = " ".join(f"{b:02X}" for b in data) + " "
        else:
            text = self._decode_rx(data)

        # 跨 chunk 的 \r\n 处理 — Auto(0) 和 CRLF(1) 都需要
        # （LF/CR 模式因为单字符就是终止符，无歧义，不需要 defer）
        cross_chunk_crlf = False
        nl_mode_for_defer = self.cb_line_nl.currentIndex() if use_line_split else -1
        if nl_mode_for_defer in (0, 1):
            if self._rx_pending_cr:
                if text.startswith("\n"):
                    text = text[1:]
                    cross_chunk_crlf = True
                else:
                    # 没接到 \n —— Auto 模式下 \r 单字符也是换行；
                    # CRLF 模式下 \r 单字符是数据（不是终止符），但 QTextEdit
                    # 渲染时仍会把它当换行显示。两种模式都先把 \r 还回去，
                    # 后续 split 按规则处理（Auto 把它当换行；CRLF 视为数据）
                    text = "\r" + text
                self._rx_pending_cr = False
            if text.endswith("\r"):
                self._rx_pending_cr = True
                text = text[:-1]

            if cross_chunk_crlf and not text:
                self._pending_line_break = True
                self._last_recv_time = now
                return

        if use_line_split:
            nl_mode = self.cb_line_nl.currentIndex()
            if nl_mode == 1:
                segments = text.split("\r\n")
            elif nl_mode == 2:
                segments = text.split("\n")
            elif nl_mode == 3:
                segments = text.split("\r")
            else:
                normalized = text.replace("\r\n", "\n").replace("\r", "\n")
                segments = normalized.split("\n")
        else:
            segments = [text]

        for i, seg in enumerate(segments):
            is_first = (i == 0)
            is_last = (i == len(segments) - 1)

            if is_first:
                force_new_block = (
                    (self._last_direction != "rx")
                    or self._pending_line_break
                    or cross_chunk_crlf  # 跨包 CRLF 也算上一次换行
                )
                if not force_new_block and self.sw_packet_split.isChecked():
                    try:
                        timeout_ms = max(1, int(self.ed_packet_timeout.text()))
                    except ValueError:
                        timeout_ms = 20
                    gap_ms = (now - self._last_recv_time) * 1000.0
                    if gap_ms > timeout_ms:
                        force_new_block = True
            else:
                force_new_block = True

            if is_last and seg == "" and use_line_split and len(segments) > 1:
                continue

            self._append_block_data(seg, direction="rx", force_new_block=force_new_block)
            self._last_direction = "rx"

        if use_line_split:
            self._pending_line_break = (segments[-1] == "" and len(segments) > 1)
        else:
            self._pending_line_break = False
        self._last_recv_time = now

    def _append_block_data(self, text: str, direction: str, force_new_block: bool):
        theme = self._theme()
        # TX 用主题里的 tx 色，RX 用 fg 默认色（主题切换后旧文字不会重涂）
        body_color = theme["tx"] if direction == "tx" else theme["fg"]
        # 滚动锁定：插入前先记住是否在底部；用独立游标插入，避免动可见光标/选区/视图
        was_at_bottom = self._recv_at_bottom()
        cursor = QTextCursor(self.txt_recv.document())
        cursor.movePosition(QTextCursor.End)

        log_pieces = []

        if force_new_block:
            if not self._txt_ends_with_nl:
                cursor.insertText("\n")
                log_pieces.append("\n")
                self._txt_ends_with_nl = True
            prefix = ""
            if self.sw_show_timestamp.isChecked():
                now = datetime.now()
                prefix = (f"[{now.year}/{now.month:02d}/{now.day:02d} "
                          f"{now.hour:02d}:{now.minute:02d}:{now.second:02d} "
                          f"{now.microsecond // 1000:03d}] ")
                # 箭头跟时间戳绑一起：时间戳关掉时也不显示，纯数据更干净
                prefix += "→ " if direction == "tx" else "← "
            if prefix:
                # 时间戳 + 箭头用 ts 灰色（淡化）
                ts_fmt = QTextCharFormat()
                # 时间戳色朝正文 fg 靠拢 40%，提高对比度（原 ts 偏淡看不清）
                ts_fmt.setForeground(QColor(self._role_color(ROLE_TS, theme)))
                ts_fmt.setProperty(ROLE_PROP, ROLE_TS)
                cursor.setCharFormat(ts_fmt)
                cursor.insertText(prefix)
                log_pieces.append(prefix)
                self._txt_ends_with_nl = False

        # 正文用 body_color
        body_role = ROLE_TX if direction == "tx" else ROLE_RX
        body_fmt = QTextCharFormat()
        body_fmt.setForeground(QColor(body_color))
        body_fmt.setProperty(ROLE_PROP, body_role)
        cursor.setCharFormat(body_fmt)
        cursor.insertText(text)
        log_pieces.append(text)
        if text:
            self._txt_ends_with_nl = text.endswith("\n")

        reset = QTextCharFormat()
        reset.setForeground(QColor(theme["fg"]))
        cursor.setCharFormat(reset)
        # 只有原本就在底部才跟随到最新；用户往上翻看时保持定住
        # 过滤开启时，立即决定刚追加这行的可见性 —— 在滚动到底之前完成，
        # 避免"先显示→滚到底→150ms后异步隐藏→高度收缩跳动"的抖动
        if self._filter_active():
            blk = cursor.block()
            vis = self._block_has_keyword_match(blk)
            if blk.isVisible() != vis:
                blk.setVisible(vis)
                self.txt_recv.document().markContentsDirty(
                    blk.position(), max(1, blk.length()))

        if was_at_bottom:
            sb = self.txt_recv.verticalScrollBar()
            sb.setValue(sb.maximum())

        self._schedule_keyword_rebuild()    # 节流重扫关键字高亮(着色)

        if self._log_file:
            try:
                self._log_file.write("".join(log_pieces))
                self._log_file.flush()
                self._maybe_rotate_log()    # 超过分包上限则切到下一个文件
            except Exception as e:
                self.toast(self._t("err_log_write", e=e), error=True)
                self._close_log_file()
                self.sw_log_file.setChecked(False)

    def on_reader_error(self, msg):
        self.toast(self._t("err_serial", e=msg), error=True)
        self.close_serial()

    # ----- 多条发送：分组数据 + 主界面快捷栏 + 循环 -----
    def _load_ms_groups(self):
        """加载多条发送分组；兼容旧版扁平 multi_send_items → 迁移成「默认」分组。
        返回 (groups, loaded_ok)；loaded_ok=False 表示走了迁移/默认(损坏或缺失)，调用方据此落盘。"""
        groups = []
        raw = self.settings.value("multi_send_groups", "")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    groups = [g for g in data
                              if isinstance(g, dict) and isinstance(g.get("items"), list)]
            except Exception:
                groups = []
        loaded_ok = bool(groups)
        if not groups:
            old_items = []
            old = self.settings.value("multi_send_items", "")
            if old:
                try:
                    parsed = json.loads(old)
                    if isinstance(parsed, list):
                        old_items = parsed
                except Exception:
                    pass
            groups = [{"name": self._t("kw_default_group"), "items": old_items}]
        return groups, loaded_ok

    def _save_ms_groups(self):
        self.settings.setValue("multi_send_groups",
                               json.dumps(self._ms_groups, ensure_ascii=False))
        self.settings.setValue("multi_send_group_idx", self._ms_group_idx)
        self.settings.remove("multi_send_items")    # 清理已迁移的旧扁平键
        self.settings.sync()

    def _ms_active_items(self):
        if 0 <= self._ms_group_idx < len(self._ms_groups):
            return self._ms_groups[self._ms_group_idx]["items"]
        return []

    def _send_ms_item(self, item):
        self._send_text(item.get("data", ""),
                        hex_mode=bool(item.get("hex", False)),
                        newline=int(item.get("nl", 0)),
                        checksum=int(item.get("cs", 0)))

    def _rebuild_ms_group_combo(self):
        if not hasattr(self, "cb_ms_group"):
            return
        self.cb_ms_group.blockSignals(True)
        self.cb_ms_group.clear()
        for i, g in enumerate(self._ms_groups):
            self.cb_ms_group.addItem(g.get("name", f"组{i + 1}"), i)
        if not (0 <= self._ms_group_idx < len(self._ms_groups)):
            self._ms_group_idx = 0
        self.cb_ms_group.setCurrentIndex(self._ms_group_idx)
        self.cb_ms_group.blockSignals(False)

    def _on_ms_group_changed(self, _i=None):
        data = self.cb_ms_group.currentData()
        self._ms_group_idx = data if data is not None else 0
        self._ms_stop_cycle()
        self._save_ms_groups()
        self._rebuild_ms_quick_bar()

    def _rebuild_ms_quick_bar(self):
        """重建快捷发送按钮：选中分组里每条非空命令一个按钮，点击立即发。"""
        if not hasattr(self, "_ms_quick_h"):
            return
        while self._ms_quick_h.count():
            it = self._ms_quick_h.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for item in self._ms_active_items():
            if not str(item.get("data", "")).strip():
                continue
            label = (item.get("name") or "").strip() or item.get("data", "")
            if len(label) > 16:
                label = label[:15] + "…"
            btn = QPushButton(label)
            btn.setObjectName("MsQuickBtn")
            btn.setToolTip(item.get("data", ""))
            btn.clicked.connect(lambda _=False, it=item: self._send_ms_item(it))
            self._ms_quick_h.addWidget(btn)
        self._ms_quick_h.addStretch(1)

    def _ms_groups_changed(self):
        """弹窗编辑分组后回调：钳制索引、存盘、重建主界面下拉与快捷栏。"""
        if self._ms_group_idx >= len(self._ms_groups):
            self._ms_group_idx = max(0, len(self._ms_groups) - 1)
        self._save_ms_groups()
        self._rebuild_ms_group_combo()
        self._rebuild_ms_quick_bar()

    # ----- 多条发送：循环（按每行延时）-----
    def _ms_toggle_cycle(self):
        if self._ms_cycle_timer.isActive():
            self._ms_stop_cycle()
            return
        seq = [(it.get("data", ""), bool(it.get("hex", False)), int(it.get("nl", 0)),
                int(it.get("cs", 0)), max(1, int(it.get("delay", 1000))))
               for it in self._ms_active_items()
               if it.get("checked") and str(it.get("data", "")).strip()]
        if not seq:
            self.toast(self._t("ms_none_checked"), error=True)
            return
        if not (self.ser and self.ser.is_open):
            self.toast(self._t("err_serial_not_open"), error=True)
            return
        self._ms_cycle_seq = seq
        self._ms_cycle_idx = 0
        self._set_ms_cycle_btn(True)
        self._ms_cycle_step()

    def _ms_cycle_step(self):
        if not self._ms_cycle_seq:
            self._ms_stop_cycle()
            return
        if not (self.ser and self.ser.is_open):
            self.toast(self._t("err_serial_not_open"), error=True)
            self._ms_stop_cycle()
            return
        data, hx, nl, cs, delay = self._ms_cycle_seq[self._ms_cycle_idx % len(self._ms_cycle_seq)]
        # 发送失败(坏数据/串口写异常等)立即停止，避免每轮都刷错误 toast
        # (空命令在 _ms_toggle_cycle 构建序列时已过滤，这里的 False 都是真失败)
        if not self._send_text(data, hex_mode=hx, newline=nl, checksum=cs):
            self._ms_stop_cycle()
            return
        self._ms_cycle_idx += 1
        self._ms_cycle_timer.start(delay)

    def _ms_stop_cycle(self):
        if hasattr(self, "_ms_cycle_timer"):
            self._ms_cycle_timer.stop()
        self._set_ms_cycle_btn(False)

    def _set_ms_cycle_btn(self, running):
        if hasattr(self, "btn_ms_cycle"):
            self.btn_ms_cycle.setText(self._t("ms_cycle_stop" if running else "ms_cycle"))

    # ----- 发送 -----
    def open_multi_send(self):
        """打开多条发送弹窗（单实例，复用并刷新主题/语言）"""
        if getattr(self, "_multi_send_dlg", None) is None:
            self._multi_send_dlg = MultiSendDialog(self)
        dlg = self._multi_send_dlg
        if dlg._save_timer.isActive():   # 重复打开前先落盘待提交编辑，避免 _reload_rows 清掉
            dlg._commit_now()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg._reload_group_list()
        dlg._reload_rows()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_keyword_highlight(self):
        """打开关键字高亮配置弹窗（单实例，复用并刷新主题/语言）"""
        if getattr(self, "_keyword_dlg", None) is None:
            self._keyword_dlg = KeywordHighlightDialog(self)
        dlg = self._keyword_dlg
        if dlg._commit_timer.isActive():   # 重复打开前先落盘待提交编辑
            dlg._commit_now()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg._reload_group_list()    # 复用时同步最新分组
        dlg._reload_rows()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def do_send(self):
        raw = self.txt_send.toPlainText()
        if not raw:
            return
        ok = self._send_text(raw)
        # 串口没开导致发送失败时，顺手关掉定时发送开关
        if not ok and self.sw_period.isChecked() and not (self.ser and self.ser.is_open):
            self.sw_period.setChecked(False)

    def _send_text(self, raw, hex_mode=None, newline=None, checksum=None) -> bool:
        """解析并发送一段文本(HEX/文本)，复用追加换行+校验+显示。
        hex_mode/newline/checksum 为 None 时用主界面全局设置；多条发送可逐条传入独立值。
          newline: None=全局; 0=无 1=CRLF 2=LF 3=CR
          checksum: None=全局; 否则校验项索引(0=无…)
        成功返回 True"""
        if not (self.ser and self.ser.is_open):
            self.toast(self._t("err_serial_not_open"), error=True)
            return False
        if not raw:
            return False
        use_hex = self.sw_tx_hex.isChecked() if hex_mode is None else hex_mode

        try:
            if use_hex:
                import re as _re
                # 1. 先剥掉注释 — 否则注释里 "face" "dead" "beef" 这些 a-f 字符会被当数据
                cleaned = _re.sub(r'/\*.*?\*/', '', raw, flags=_re.DOTALL)   # 块注释
                cleaned = _re.sub(r'//[^\n]*', '', cleaned)                    # 行注释 //
                cleaned = _re.sub(r'#[^\n]*', '', cleaned)                     # 行注释 #
                # 2. 去掉 0x/0X 前缀
                cleaned = cleaned.replace("0x", "").replace("0X", "")
                # 3. 移除允许的分隔符（空白、- : , ;）
                allowed_seps = set(" \t\r\n-:,;")
                filtered = "".join(c for c in cleaned if c not in allowed_seps)
                if not filtered:
                    return False
                # 4. 检查剩下的必须全是 hex —— 出现 ZZ / G 这种就报错，不再静默丢弃
                bad_chars = sorted(set(c for c in filtered
                                       if c not in "0123456789abcdefABCDEF"))
                if bad_chars:
                    err = self._t(
                        "err_hex_invalid_chars",
                        chars=" ".join(repr(c) for c in bad_chars),
                    )
                    self.toast(
                        self._t("err_hex_bad", e=err),
                        error=True,
                    )
                    return False
                if len(filtered) % 2 != 0:
                    self.toast(self._t("err_hex_odd"), error=True)
                    return False
                data = bytes.fromhex(filtered)
            else:
                # 按选定编码发送（默认 UTF-8）— 让用户能给 GBK 设备发中文
                data = raw.encode(self._send_codec(), errors="replace")
        except ValueError as e:
            self.toast(self._t("err_hex_bad", e=e), error=True)
            return False

        # 追加换行 - HEX 和 ASCII 模式都生效
        if newline is None:
            if self.sw_append_newline.isChecked():
                nl_idx = self.cb_append_nl.currentIndex()  # 0=CRLF,1=LF,2=CR
                data += {0: b"\r\n", 1: b"\n", 2: b"\r"}.get(nl_idx, b"\r\n")
        else:
            data += {1: b"\r\n", 2: b"\n", 3: b"\r"}.get(newline, b"")  # 0=无

        # 追加校验
        cs_idx = self.cb_checksum.currentIndex() if checksum is None else checksum
        try:
            data = data + self.compute_checksum(data, cs_idx)
        except Exception as e:
            self.toast(self._t("err_checksum", e=e), error=True)
            return False

        try:
            self.ser.write(data)
        except Exception as e:
            self.toast(self._t("err_send_failed", e=e), error=True)
            return False

        self.tx_bytes += len(data)
        self.lbl_tx_stat.setText(f"TX: {self.fmt_bytes(self.tx_bytes)}")

        # 显示到数据区 — 只看「HEX 显示」开关(数据区显示格式)，和发送模式无关：
        # 接收按 HEX 显示，发送也按 HEX 显示，RX/TX 统一
        if self.sw_rx_hex.isChecked():
            display = " ".join(f"{b:02X}" for b in data) + " "
        else:
            display = data.decode(self._send_codec(), errors="replace")
        self._append_block_data(display, direction="tx", force_new_block=True)
        self._last_direction = "tx"
        return True

    @staticmethod
    def compute_checksum(data: bytes, index: int) -> bytes:
        if not data or index <= 0:
            return b""
        if index == 1:  # ADD8
            return bytes([sum(data) & 0xFF])
        if index == 2:  # ~ADD8
            return bytes([(~sum(data)) & 0xFF])
        if index == 3:  # XOR8
            x = 0
            for b in data:
                x ^= b
            return bytes([x])
        if index == 4:  # CRC8 (poly 0x07)
            crc = 0
            for b in data:
                crc ^= b
                for _ in range(8):
                    crc = ((crc << 1) ^ 0x07) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
            return bytes([crc])
        if index == 5:  # ModbusCRC16
            crc = 0xFFFF
            for b in data:
                crc ^= b
                for _ in range(8):
                    crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
            return bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        if index == 6:  # CCITT-CRC16
            crc = 0xFFFF
            for b in data:
                crc ^= (b << 8)
                for _ in range(8):
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
            return bytes([(crc >> 8) & 0xFF, crc & 0xFF])
        if index == 7:  # CRC32
            import zlib
            crc = zlib.crc32(data) & 0xFFFFFFFF
            return bytes([(crc >> 24) & 0xFF, (crc >> 16) & 0xFF,
                          (crc >> 8) & 0xFF, crc & 0xFF])
        if index == 8:  # ADD16
            s = sum(data) & 0xFFFF
            return bytes([(s >> 8) & 0xFF, s & 0xFF])
        if index == 9:  # MOBUS: CRC8 with poly 0x31
            crc = 0
            for b in data:
                crc ^= b
                for _ in range(8):
                    crc = ((crc << 1) ^ 0x31) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
            return bytes([crc])
        return b""

    def on_period_toggled(self, on):
        if on:
            try:
                ms = int(self.ed_period_ms.text())
                if ms < 10:
                    raise ValueError(self._t("err_min_period"))
            except ValueError as e:
                self.toast(self._t("err_period_bad", e=e), error=True)
                self.sw_period.setChecked(False)
                return
            if not (self.ser and self.ser.is_open):
                self.toast(self._t("err_serial_not_open"), error=True)
                self.sw_period.setChecked(False)
                return
            self.send_timer.start(ms)
        else:
            self.send_timer.stop()

    def on_wrap_toggled(self, on):
        self.txt_recv.setLineWrapMode(
            QTextEdit.WidgetWidth if on else QTextEdit.NoWrap)

    # ----- 日志记录 -----
    def _parse_log_limit(self, text) -> int:
        """把分包大小文本解析成字节；无数字(如「不分包」)返回 0。无单位默认 MB。"""
        import re
        m = re.search(r'(\d+(?:\.\d+)?)\s*([KkMmGg]?)', text or "")
        if not m:
            return 0
        val = float(m.group(1))
        mult = {"K": 1024, "M": 1024 * 1024, "G": 1024 ** 3}.get(m.group(2).upper(), 1024 * 1024)
        return int(val * mult)

    def _on_log_split_changed(self, _text=None):
        """改分包大小：实时记录进行中也即时生效。"""
        self._log_limit = self._parse_log_limit(self.cb_log_split.currentText())

    def _log_segment_path(self) -> str:
        """当前分包序号对应的文件名：第 0 包用原始路径，之后加 _001/_002…后缀。"""
        if self._log_seg <= 0:
            return self._log_base_path
        root, ext = os.path.splitext(self._log_base_path)
        return f"{root}_{self._log_seg:03d}{ext}"

    def _set_log_path_label(self, path):
        """更新状态栏的日志文件路径显示（仅记录时显示，太长中间省略，悬停看全路径）。"""
        if not hasattr(self, "lbl_log_path"):
            return
        if not path:
            self.lbl_log_path.setText("")
            self.lbl_log_path.setToolTip("")
            if hasattr(self, "_log_path_sep"):
                self._log_path_sep.hide()
            return
        fm = QFontMetrics(self.lbl_log_path.font())
        w = getattr(self, "_log_path_elide_w", 560)
        self.lbl_log_path.setText("📝 " + fm.elidedText(path, Qt.ElideMiddle, w))
        self.lbl_log_path.setToolTip(path)
        if hasattr(self, "_log_path_sep"):
            self._log_path_sep.show()

    def _open_log_segment(self, path) -> bool:
        try:
            self._log_file = open(path, "a", encoding="utf-8")
            self._log_file_path = path
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._log_file.write(self._t("log_header", time=ts))
            self._log_file.flush()
            self._set_log_path_label(path)
            return True
        except Exception as e:
            self.toast(self._t("err_open_log", e=e), error=True)
            return False

    def _maybe_rotate_log(self):
        """写入后若超过分包上限，切到下一个分包文件。"""
        if not (self._log_file and self._log_limit > 0):
            return
        try:
            if self._log_file.tell() < self._log_limit:
                return
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._log_file.write(self._t("log_footer", time=ts))
            self._log_file.flush()    # close 前先刷盘，避免 close 失败时尾部缓冲丢失
            self._log_file.close()
        except Exception:
            pass
        self._log_seg += 1
        self._log_file = None
        if not self._open_log_segment(self._log_segment_path()):
            self.sw_log_file.setChecked(False)

    def on_log_file_toggled(self, on):
        if on:
            path, _ = QFileDialog.getSaveFileName(
                self, self._t("dlg_log_path"),
                f"data_log_{datetime.now():%Y%m%d_%H%M%S}.log",
                self._t("filter_text"))
            if not path:
                self.sw_log_file.blockSignals(True)   # 取消选择 → 关开关但别递归回调本函数
                self.sw_log_file.setChecked(False)
                self.sw_log_file.blockSignals(False)
                return
            self._log_limit = self._parse_log_limit(self.cb_log_split.currentText())
            self._log_base_path = path
            self._log_seg = 0
            if self._open_log_segment(path):
                self.toast(self._t("log_started", path=path))
            else:
                self.sw_log_file.setChecked(False)
        else:
            self._close_log_file()

    def _close_log_file(self):
        if self._log_file:
            try:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._log_file.write(self._t("log_footer", time=ts))
                self._log_file.flush()
                self._log_file.close()
            except Exception:
                pass
            self.toast(self._t("log_stopped", path=self._log_file_path))
            self._log_file = None
            self._log_file_path = ""
            self._set_log_path_label("")

    def change_recv_font_size(self, delta):
        new_size = self._recv_font_size + delta
        new_size = max(7, min(28, new_size))
        if new_size == self._recv_font_size:
            return
        self._recv_font_size = new_size
        self.txt_recv.setFont(QFont("Consolas", new_size))
        self.toast(self._t("font_size_msg", size=new_size))

    def _on_max_lines_changed(self):
        if not hasattr(self, 'ed_max_lines'):
            return
        try:
            n = int(self.ed_max_lines.text())
        except ValueError:
            n = self.txt_recv.document().maximumBlockCount() or 10000
        n = max(100, min(1_000_000, n))
        self.ed_max_lines.setText(str(n))
        if hasattr(self, 'txt_recv'):
            self.txt_recv.document().setMaximumBlockCount(n)

    # ----- 文件 -----
    def save_recv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self._t("dlg_save_data"),
            f"save_log_{datetime.now():%Y%m%d_%H%M%S}.log",
            self._t("filter_text_save"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt_recv.toPlainText())
            self.toast(self._t("saved_to", path=path))
        except Exception as e:
            self.toast(self._t("err_save_failed", e=e), error=True)

    def load_file_to_send(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._t("dlg_load_file"), "", self._t("filter_all"))
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            if self.sw_tx_hex.isChecked():
                self.txt_send.setPlainText(" ".join(f"{b:02X}" for b in data))
            else:
                # 按选定编码读取（默认 utf-8），lossy 容错避免文件偶有坏字节就报错
                self.txt_send.setPlainText(data.decode(self._send_codec(), errors="replace"))
        except Exception as e:
            self.toast(self._t("err_read_failed", e=e), error=True)

    def clear_recv(self):
        self.txt_recv.clear()
        self._recv_highlight_line = -1
        self.txt_recv.setExtraSelections([])
        self.btn_to_bottom.hide()
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.lbl_rx_stat.setText("RX: 0 B")
        self.lbl_tx_stat.setText("TX: 0 B")
        self._last_direction = None
        self._pending_line_break = False
        self._rx_decode_buffer = b""
        self._rx_pending_cr = False
        self._inc_decoder = None  # 重置增量解码器（None → _decode_rx 首次调用时按当前 codec 重建）
        self._txt_ends_with_nl = True

    # ----- 工具 -----
    @staticmethod
    def fmt_bytes(n):
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n/1024:.1f} KB"
        return f"{n/1024/1024:.2f} MB"

    def toast(self, msg, error=False):
        if error:
            self.status_bar.showMessage("⚠ " + msg, 3500)
        else:
            self.status_bar.showMessage("✓ " + msg, 2500)

    # ----- 多语言 -----
    def _set_language(self, lang: str):
        if lang not in TR or lang == self._lang:
            return
        self._lang = lang
        self._L = TR[lang]
        self.settings.setValue("language", lang)
        self.settings.sync()
        self._apply_language()

    def _apply_language(self):
        self.setWindowTitle(self._t("app_title"))
        if hasattr(self, "title_bar"):
            self.title_bar.set_title(self._t("app_title"))

        for w in self.findChildren(QWidget):
            k = w.property("tr_text")
            if k:
                try:
                    w.setText(self._t(k))
                except Exception:
                    pass
            k = w.property("tr_placeholder")
            if k:
                try:
                    w.setPlaceholderText(self._t(k))
                except Exception:
                    pass
            k = w.property("tr_tooltip")
            if k:
                try:
                    w.setToolTip(self._t(k))
                except Exception:
                    pass
            # 固定宽标签（串口设置左列）随语言调整列宽，避免英文被遮挡
            if w.property("tr_fixedw"):
                w.setFixedWidth(self._label_col_width())

        self._apply_theme_label_styles()
        self._update_legend_label()

        if hasattr(self, "cb_checksum"):
            idx = self.cb_checksum.currentIndex()
            self.cb_checksum.blockSignals(True)
            self.cb_checksum.clear()
            for ck_key in CHECKSUM_KEYS:
                self.cb_checksum.addItem(self._t(ck_key))
            if 0 <= idx < self.cb_checksum.count():
                self.cb_checksum.setCurrentIndex(idx)
            self.cb_checksum.blockSignals(False)

        if hasattr(self, "cb_line_nl"):
            self.cb_line_nl.setItemText(0, self._t("nl_auto"))

        if hasattr(self, "cb_encoding"):
            self.cb_encoding.setItemText(0, self._t("encoding_auto"))

        # 主题下拉的 9 项也跟着语言切换
        if hasattr(self, "cb_theme"):
            self.cb_theme.blockSignals(True)
            for i in range(self.cb_theme.count()):
                tid = self.cb_theme.itemData(i)
                if tid:
                    self.cb_theme.setItemText(i, self._theme_label(tid))
            self.cb_theme.blockSignals(False)

        if hasattr(self, "btn_open"):
            opened = bool(self.ser and self.ser.is_open)
            self.btn_open.setText(self._t("close_serial" if opened else "open_serial"))

        if hasattr(self, "lbl_state"):
            if not (self.ser and self.ser.is_open):
                self.lbl_state.setText(self._t("state_closed"))

        if hasattr(self, "cb_port") and self.cb_port.count() == 1:
            data = self.cb_port.itemData(0)
            if not data:
                self.cb_port.setItemText(0, self._t("no_ports"))

        if self._tray:
            self._tray.setToolTip(self._t("app_title"))
            if hasattr(self, "_tray_show_action"):
                self._tray_show_action.setText(self._t("tray_show"))
            if hasattr(self, "_tray_quit_action"):
                self._tray_quit_action.setText(self._t("tray_quit"))

        # 数据区分组下拉的「（关闭）」项随语言变
        if hasattr(self, "cb_kw_group"):
            self._rebuild_kw_group_combo()
        # 日志分包下拉的「不分包」项随语言变
        if hasattr(self, "cb_log_split"):
            self.cb_log_split.blockSignals(True)
            self.cb_log_split.setItemText(0, self._t("log_split_none"))
            self.cb_log_split.blockSignals(False)
        # 多条发送循环按钮文字随语言变
        if hasattr(self, "btn_ms_cycle"):
            self._set_ms_cycle_btn(self._ms_cycle_timer.isActive())
        # 多条发送/关键字高亮弹窗若开着也跟着切语言
        if getattr(self, "_multi_send_dlg", None) is not None:
            self._multi_send_dlg.retranslate()
        if getattr(self, "_keyword_dlg", None) is not None:
            self._keyword_dlg.retranslate()

    # ----- 持久化 -----
    @staticmethod
    def _settings_file() -> str:
        """
        优先 exe 同级目录（绿色版/U 盘携带特性），写不动就回退 %APPDATA%\\SerialTool\\。
        场景：用户装到 Program Files（安装时选"为所有用户"），普通用户运行无写权限。
        """
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))

        portable = os.path.join(base, "settings.ini")

        # 判定 portable 路径可不可用：
        # - 文件已存在 → 测试能否打开追加写（覆盖只读文件场景）
        # - 文件不存在 → 在目录里试写一个临时文件
        def _portable_writable():
            if os.path.exists(portable):
                try:
                    with open(portable, "a"):
                        pass
                    return True
                except (OSError, PermissionError):
                    return False
            test = os.path.join(base, ".write_test")
            try:
                with open(test, "w"):
                    pass
                os.remove(test)
                return True
            except (OSError, PermissionError):
                return False

        if _portable_writable():
            return portable

        # 回退用户配置目录
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        cfg_dir = os.path.join(appdata, "SerialTool")
        try:
            os.makedirs(cfg_dir, exist_ok=True)
        except Exception:
            pass
        return os.path.join(cfg_dir, "settings.ini")

    def _save_settings(self):
        try:
            s = self.settings
            s.setValue("geometry", self.saveGeometry())
            s.setValue("h_splitter", self.h_splitter.saveState())
            s.setValue("recv_font_size", self._recv_font_size)
            s.setValue("rx_hex", self.sw_rx_hex.isChecked())
            s.setValue("wrap", self.sw_wrap.isChecked())
            s.setValue("show_timestamp", self.sw_show_timestamp.isChecked())
            s.setValue("packet_split", self.sw_packet_split.isChecked())
            s.setValue("line_split", self.sw_line_split.isChecked())
            s.setValue("line_nl_mode", self.cb_line_nl.currentIndex())
            s.setValue("encoding", self.cb_encoding.currentData())
            s.setValue("theme", self.cb_theme.currentData())
            s.setValue("packet_timeout", self.ed_packet_timeout.text())
            s.setValue("max_lines", self.ed_max_lines.text())
            s.setValue("filter_highlight", self.btn_filter_hl.isChecked())
            s.setValue("log_split", self.cb_log_split.currentText())
            s.setValue("tx_hex", self.sw_tx_hex.isChecked())
            s.setValue("append_newline", self.sw_append_newline.isChecked())
            s.setValue("append_nl_mode", self.cb_append_nl.currentIndex())
            s.setValue("period_ms", self.ed_period_ms.text())
            s.setValue("checksum_idx", self.cb_checksum.currentIndex())
            s.setValue("send_text", self.txt_send.toPlainText())
            s.setValue("port", self.cb_port.currentData() or "")
            s.setValue("baud", self.cb_baud.currentText())
            s.setValue("databits", self.cb_databits.currentText())
            s.setValue("parity", self.cb_parity.currentText())
            s.setValue("stopbits", self.cb_stopbits.currentText())
            s.sync()
        except Exception:
            pass

    def _load_settings(self):
        s = self.settings

        def to_bool(v, default=False):
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.lower() in ("true", "1", "yes")
            return default

        def restore_combo(combo, key):
            v = s.value(key, None)
            if v is None or v == "":
                return
            v = str(v)
            idx = combo.findText(v)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif combo.isEditable():
                combo.setEditText(v)

        try:
            geo = s.value("geometry")
            if geo:
                self.restoreGeometry(geo)
            h_state = s.value("h_splitter")
            if h_state:
                self.h_splitter.restoreState(h_state)
        except Exception:
            pass

        try:
            size = int(s.value("recv_font_size", 10))
            self._recv_font_size = max(7, min(28, size))
            self.txt_recv.setFont(QFont("Consolas", self._recv_font_size))
        except (ValueError, TypeError):
            pass

        legacy_ts = s.value("timestamp", None)
        show_ts_raw = s.value("show_timestamp", legacy_ts if legacy_ts is not None else False)
        pkt_split_raw = s.value("packet_split", legacy_ts if legacy_ts is not None else False)
        self.sw_rx_hex.setChecked(to_bool(s.value("rx_hex", False)), animate=False)
        self.sw_wrap.setChecked(to_bool(s.value("wrap", True)), animate=False)
        self.sw_show_timestamp.setChecked(to_bool(show_ts_raw), animate=False)
        self.sw_packet_split.setChecked(to_bool(pkt_split_raw), animate=False)
        self.sw_line_split.setChecked(to_bool(s.value("line_split", False)), animate=False)
        self.btn_filter_hl.blockSignals(True)
        self.btn_filter_hl.setChecked(to_bool(s.value("filter_highlight", False)))
        self.btn_filter_hl.blockSignals(False)
        log_split = s.value("log_split", "")
        if log_split:
            self.cb_log_split.setCurrentText(str(log_split))
        try:
            nl_idx = int(s.value("line_nl_mode", 0))
            if 0 <= nl_idx < self.cb_line_nl.count():
                self.cb_line_nl.setCurrentIndex(nl_idx)
        except (ValueError, TypeError):
            pass
        # 字符编码 — 按 codec name 查 itemData 找回上次选项
        enc_saved = s.value("encoding", "auto") or "auto"
        for i in range(self.cb_encoding.count()):
            if self.cb_encoding.itemData(i) == enc_saved:
                self.cb_encoding.setCurrentIndex(i)
                break
        # 触发一次 _on_encoding_changed 初始化增量解码器
        self._on_encoding_changed()

        # 主题 — 按 theme_id 查 itemData
        theme_saved = s.value("theme", THEME_DEFAULT) or THEME_DEFAULT
        # 静默切到目标 idx — 不让 setCurrentIndex 在 __init__ 阶段触发 _on_theme_changed
        # （此时 widget 还没完成首次 show，Qt setStyleSheet 不会完全 propagate 到子组件）
        self.cb_theme.blockSignals(True)
        for i in range(self.cb_theme.count()):
            if self.cb_theme.itemData(i) == theme_saved:
                self.cb_theme.setCurrentIndex(i)
                break
        self.cb_theme.blockSignals(False)
        # 推迟到 event loop 启动后再应用 — 此时所有 widget 已 show，setStyleSheet 全部生效
        QTimer.singleShot(0, self._on_theme_changed)
        self.sw_tx_hex.setChecked(to_bool(s.value("tx_hex", False)), animate=False)
        self.sw_append_newline.setChecked(to_bool(s.value("append_newline", False)), animate=False)
        try:
            nl_idx = int(s.value("append_nl_mode", 0))
            if 0 <= nl_idx < self.cb_append_nl.count():
                self.cb_append_nl.setCurrentIndex(nl_idx)
        except (ValueError, TypeError):
            pass
        self.on_wrap_toggled(self.sw_wrap.isChecked())

        v = s.value("packet_timeout")
        if v:
            self.ed_packet_timeout.setText(str(v))
        v = s.value("max_lines")
        if v:
            self.ed_max_lines.setText(str(v))
            self._on_max_lines_changed()
        v = s.value("period_ms")
        if v:
            self.ed_period_ms.setText(str(v))
        v = s.value("send_text")
        if v:
            self.txt_send.setPlainText(str(v))

        try:
            ck_idx = int(s.value("checksum_idx", 0))
            if 0 <= ck_idx < self.cb_checksum.count():
                self.cb_checksum.setCurrentIndex(ck_idx)
        except (ValueError, TypeError):
            pass
        restore_combo(self.cb_baud, "baud")
        restore_combo(self.cb_databits, "databits")
        restore_combo(self.cb_parity, "parity")
        restore_combo(self.cb_stopbits, "stopbits")

        saved_port = s.value("port", "")
        if saved_port:
            for i in range(self.cb_port.count()):
                if self.cb_port.itemData(i) == saved_port:
                    self.cb_port.setCurrentIndex(i)
                    break

    # ----- 系统托盘 -----
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(get_app_icon(), self)
        self._tray.setToolTip(self._t("app_title"))

        menu = QMenu()
        self._tray_show_action = menu.addAction(self._t("tray_show"))
        self._tray_show_action.triggered.connect(self._show_from_tray)
        menu.addSeparator()
        self._tray_quit_action = menu.addAction(self._t("tray_quit"))
        self._tray_quit_action.triggered.connect(self._real_quit)
        self._tray.setContextMenu(menu)

        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _real_quit(self):
        self._closing_real = True
        self.close()

    def showEvent(self, event):
        super().showEvent(event)
        # 第一次显示后做一次：把右侧发送区卡片的高度上限设为左侧发送区卡片的实际高度
        # 这样右侧发送区不会因为 QTextEdit 的 Expanding 策略吃掉过多空间，顶底都和左侧对齐
        if not getattr(self, "_height_synced", False):
            self._height_synced = True
            QTimer.singleShot(0, self._sync_right_send_height)

    def _sync_right_send_height(self):
        try:
            if hasattr(self, "_left_send_card") and hasattr(self, "_right_send_card"):
                h = self._left_send_card.height()
                # 上限取「左侧高度」与「右侧内容最小高度」的较大值：
                # 否则左侧卡片变矮(字号/间距缩小)时，会把内容更多的右侧(含多条发送快捷栏)压到重叠
                need = self._right_send_card.minimumSizeHint().height()
                if h > 60:
                    self._right_send_card.setMaximumHeight(max(h, need))
        except Exception:
            pass

    def changeEvent(self, e):
        if e.type() == e.WindowStateChange and hasattr(self, "title_bar"):
            self.title_bar.update_max_icon()
        super().changeEvent(e)

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    lparam = msg.lParam
                    x = ctypes.c_short(lparam & 0xFFFF).value
                    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                    # lParam 是物理像素；开 HiDPI 缩放后 Qt 用逻辑像素，需按设备像素比换算，
                    # 否则缩放热区与实际边缘错位、拖不动窗口
                    dpr = self.devicePixelRatioF() or 1.0
                    pt = self.mapFromGlobal(QPoint(int(x / dpr), int(y / dpr)))
                    if self.isMaximized():
                        return False, 0
                    m = self.RESIZE_MARGIN
                    on_left = pt.x() < m
                    on_right = pt.x() >= self.width() - m
                    on_top = pt.y() < m
                    on_bottom = pt.y() >= self.height() - m
                    if on_top and on_left:
                        return True, 13
                    if on_top and on_right:
                        return True, 14
                    if on_bottom and on_left:
                        return True, 16
                    if on_bottom and on_right:
                        return True, 17
                    if on_left:
                        return True, 10
                    if on_right:
                        return True, 11
                    if on_top:
                        return True, 12
                    if on_bottom:
                        return True, 15
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _wait_oneshot_scan(self):
        """退出前确保一次性端口扫描线程结束 — 否则可能 QThread: Destroyed while running"""
        scan = getattr(self, "_oneshot_scan", None)
        if scan and scan.isRunning():
            scan.wait(2000)

    def closeEvent(self, e):
        if self._closing_real or not self._tray:
            if hasattr(self, "_ms_cycle_timer"):
                self._ms_cycle_timer.stop()   # 先停循环定时器，避免销毁中触发 toast
            self._save_settings()
            self.close_serial()
            self._close_log_file()
            if self.port_scanner:
                self.port_scanner.stop()
            self._wait_oneshot_scan()
            if self._tray:
                self._tray.hide()
            e.accept()
            return

        dlg = CloseDialog(
            self._t("close_prompt"),
            self._t("close_minimize"),
            self._t("close_quit"),
            self._t("close_cancel"),
            theme_id=self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT,
            parent=self,
        )
        dlg.exec_()
        choice = dlg.result_value()

        if choice == CloseDialog.RESULT_MIN:
            e.ignore()
            self.hide()
            self._tray.showMessage(
                self._t("app_title"),
                self._t("tray_minimized", app=self._t("app_title")),
                QSystemTrayIcon.Information,
                2000
            )
        elif choice == CloseDialog.RESULT_QUIT:
            self._closing_real = True
            if hasattr(self, "_ms_cycle_timer"):
                self._ms_cycle_timer.stop()   # 与直接退出路径一致，避免销毁中触发 toast
            self._save_settings()
            self.close_serial()
            self._close_log_file()
            if self.port_scanner:
                self.port_scanner.stop()
            self._wait_oneshot_scan()
            self._tray.hide()
            e.accept()
        else:
            e.ignore()


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Tools.SerialTool.1.0")
        except Exception:
            pass

    # 高分屏(HiDPI)缩放：必须在 QApplication 创建前设置，否则 2560x1600 等高分屏上
    # Qt 按物理像素渲染，字号/下拉框都显得很小。PassThrough 让 150% 等分数缩放也平滑。
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(get_app_icon())

    for family in ("SF Pro Display", "PingFang SC", "Segoe UI", "Microsoft YaHei UI"):
        f = QFont(family, 10)
        if QFont(family).exactMatch() or family in ("Segoe UI", "Microsoft YaHei UI"):
            app.setFont(f)
            break

    w = SerialTool()
    w.setWindowIcon(get_app_icon())
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
