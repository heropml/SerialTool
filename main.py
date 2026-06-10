# -*- coding: utf-8 -*-
"""
SerialTool - iOS 风格串口调试工具
PyQt5 + pyserial
"""
import codecs
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
                          QEasingCurve, QRect, QSize, QPoint, pyqtProperty, QSettings)
from PyQt5.QtGui import (QFont, QColor, QPainter, QPen, QBrush, QIcon,
                         QTextCursor, QTextCharFormat, QFontMetrics)
from PyQt5.QtWidgets import (QApplication, QWidget, QMainWindow, QLabel,
                             QPushButton, QComboBox, QTextEdit, QLineEdit,
                             QCheckBox, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QSplitter, QScrollArea, QFrame, QFileDialog,
                             QMessageBox, QDialog, QGraphicsDropShadowEffect,
                             QSizePolicy, QSpacerItem, QStatusBar,
                             QSystemTrayIcon, QMenu, QAction)


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
        "max_lines": "最大行数",
        "save": "保存",
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
        "log_started": "日志保存到 {path}",
        "log_stopped": "已停止记录: {path}",
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
        "max_lines": "Max Lines",
        "save": "Save",
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
        "log_started": "Logging to {path}",
        "log_stopped": "Stopped logging: {path}",
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
        "max_lines": "最大行數",
        "save": "儲存",
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
        "log_started": "日誌儲存到 {path}",
        "log_stopped": "已停止記錄: {path}",
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
        self.setFixedSize(46, 28)
        self._checked = checked
        self._circle_pos = 22 if checked else 2
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
            self._anim.setEndValue(22 if value else 2)
            self._anim.start()
        else:
            self._circle_pos = 22 if value else 2
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
        p.drawRoundedRect(0, 0, 46, 28, 14, 14)
        shadow = QColor(0, 0, 0, 40)
        p.setBrush(QBrush(shadow))
        p.drawEllipse(self._circle_pos, 3, 24, 24)
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(self._circle_pos, 2, 24, 24)


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
        layout.setSpacing(8)

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
def make_label(text, size=13, bold=False, color=COLOR_TEXT):
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
        fm = QFontMetrics(QFont("Segoe UI", 13))
        w = max(fm.horizontalAdvance(self._t(k)) for k in keys)
        return max(50, w + 10)  # +10 右边距；中文下至少 50 保持原观感

    def _tr_label(self, key, size=13, bold=False, color=COLOR_TEXT):
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
        # 三个状态项放左下角 — 用 addWidget 而非 addPermanentWidget
        # (addPermanentWidget 会贴右边；addWidget 走左边，缺点是 toast 出现时会被临时遮盖)
        self.status_bar.addWidget(self.lbl_state)
        self.status_bar.addWidget(QLabel("    "))
        self.status_bar.addWidget(self.lbl_rx_stat)
        self.status_bar.addWidget(QLabel("    "))
        self.status_bar.addWidget(self.lbl_tx_stat)

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
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._tr_label("serial_settings", 13, bold=True))

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
                  "115200", "230400", "460800", "921600"]:
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
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._tr_label("data_area", 13, bold=True))

        MAIN_W = 90
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(8)

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
        sw_row(row, "real_time_log", self.sw_log_file); row += 1

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
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(self._tr_label("send_area", 13, bold=True))

        MAIN_W = 90
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(8)

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
        title_row.addWidget(self._tr_label("data_area", 14, bold=True))
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

        return card

    def build_send_card(self):
        """右侧主区域：发送区"""
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._tr_label("send_area", 14, bold=True))

        self.txt_send = QTextEdit()
        self.txt_send.setObjectName("SendBox")
        self.txt_send.setFont(QFont("Consolas", 10))
        self.txt_send.setMinimumHeight(60)
        self.txt_send.setProperty("tr_placeholder", "send_placeholder")
        self.txt_send.setPlaceholderText(self._t("send_placeholder"))
        layout.addWidget(self.txt_send, 1)

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
            border-radius: 8px;
            padding: 5px 10px;
            min-height: 22px;
            font-family: 'Segoe UI';
            font-size: 13px;
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
            border-radius: 10px;
            font-family: 'Segoe UI';
            font-size: 13px;
            font-weight: 600;
            padding: 6px 18px;
        }}
        QPushButton#PrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#PrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#PrimaryBtn[state="open"] {{ background-color: {c['danger']}; }}
        QPushButton#PrimaryBtn[state="open"]:hover {{ background-color: {c['danger_hover']}; }}
        QPushButton#GhostBtn {{
            background-color: {c['ghost_bg']};
            color: {c['accent']};
            border: 0px;
            border-radius: 8px;
            font-family: 'Segoe UI';
            font-size: 12px;
            font-weight: 500;
            padding: 6px 14px;
            min-height: 22px;
        }}
        QPushButton#GhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#GhostBtn:pressed {{ background-color: {c['ghost_pressed']}; }}
        QPushButton#IconBtn {{
            background-color: {c['ghost_bg']};
            color: {c['text_sec']};
            border: 0px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton#IconBtn:hover {{
            background-color: {c['ghost_hover']};
            color: {c['accent']};
        }}
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
        历史文字不重涂（旧 TX 蓝、旧 RX 文字保留各自原色）"""
        # 1. 重建全局 QSS，apply_style 会读 cb_theme 当前选项自适应
        self.apply_style()
        # 2. 内联 setStyleSheet 的几处也跟着 chrome palette 刷
        c = chrome_for(self._theme_id())
        self._apply_theme_label_styles(c)
        if hasattr(self, "lbl_version"):
            self.lbl_version.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")
        if hasattr(self, "status_bar"):
            self.status_bar.setStyleSheet(f"background: transparent; color: {c['text_sec']};")
        if hasattr(self, "lbl_state"):
            self._set_state_color(opened=bool(self.ser and self.ser.is_open))
        if hasattr(self, "title_bar") and hasattr(self.title_bar, "title_label"):
            self.title_bar.title_label.setStyleSheet(
                f"color: {c['text_sec']}; background: transparent;")
        self._update_legend_label(c)

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
        cursor = self.txt_recv.textCursor()
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
                ts_fmt.setForeground(QColor(theme["ts"]))
                cursor.setCharFormat(ts_fmt)
                cursor.insertText(prefix)
                log_pieces.append(prefix)
                self._txt_ends_with_nl = False

        # 正文用 body_color
        body_fmt = QTextCharFormat()
        body_fmt.setForeground(QColor(body_color))
        cursor.setCharFormat(body_fmt)
        cursor.insertText(text)
        log_pieces.append(text)
        if text:
            self._txt_ends_with_nl = text.endswith("\n")

        reset = QTextCharFormat()
        reset.setForeground(QColor(theme["fg"]))
        cursor.setCharFormat(reset)
        self.txt_recv.setTextCursor(cursor)

        if self._log_file:
            try:
                self._log_file.write("".join(log_pieces))
                self._log_file.flush()
            except Exception as e:
                self.toast(self._t("err_log_write", e=e), error=True)
                self._close_log_file()
                self.sw_log_file.setChecked(False)

    def on_reader_error(self, msg):
        self.toast(self._t("err_serial", e=msg), error=True)
        self.close_serial()

    # ----- 发送 -----
    def do_send(self):
        if not (self.ser and self.ser.is_open):
            self.toast(self._t("err_serial_not_open"), error=True)
            if self.sw_period.isChecked():
                self.sw_period.setChecked(False)
            return

        raw = self.txt_send.toPlainText()
        if not raw:
            return

        try:
            if self.sw_tx_hex.isChecked():
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
                    return
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
                    return
                if len(filtered) % 2 != 0:
                    self.toast(self._t("err_hex_odd"), error=True)
                    return
                data = bytes.fromhex(filtered)
            else:
                # 按选定编码发送（默认 UTF-8）— 让用户能给 GBK 设备发中文
                data = raw.encode(self._send_codec(), errors="replace")
        except ValueError as e:
            self.toast(self._t("err_hex_bad", e=e), error=True)
            return

        # 追加换行 - HEX 和 ASCII 模式都生效
        if self.sw_append_newline.isChecked():
            nl_idx = self.cb_append_nl.currentIndex()
            if nl_idx == 1:
                data += b"\n"
            elif nl_idx == 2:
                data += b"\r"
            else:
                data += b"\r\n"

        # 追加校验
        try:
            data = data + self.compute_checksum(data, self.cb_checksum.currentIndex())
        except Exception as e:
            self.toast(self._t("err_checksum", e=e), error=True)
            return

        try:
            self.ser.write(data)
        except Exception as e:
            self.toast(self._t("err_send_failed", e=e), error=True)
            return

        self.tx_bytes += len(data)
        self.lbl_tx_stat.setText(f"TX: {self.fmt_bytes(self.tx_bytes)}")

        # 显示到数据区 — 文本模式按当前 codec 解（默认 utf-8），lossy 但仅用于显示
        if self.sw_tx_hex.isChecked():
            display = " ".join(f"{b:02X}" for b in data) + " "
        else:
            display = data.decode(self._send_codec(), errors="replace")
        self._append_block_data(display, direction="tx", force_new_block=True)
        self._last_direction = "tx"

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
    def on_log_file_toggled(self, on):
        if on:
            path, _ = QFileDialog.getSaveFileName(
                self, self._t("dlg_log_path"),
                f"data_log_{datetime.now():%Y%m%d_%H%M%S}.log",
                self._t("filter_text"))
            if not path:
                self.sw_log_file.setChecked(False)
                return
            try:
                self._log_file = open(path, "a", encoding="utf-8")
                self._log_file_path = path
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._log_file.write(self._t("log_header", time=ts))
                self._log_file.flush()
                self.toast(self._t("log_started", path=path))
            except Exception as e:
                self.toast(self._t("err_open_log", e=e), error=True)
                self.sw_log_file.setChecked(False)
        else:
            self._close_log_file()

    def _close_log_file(self):
        if self._log_file:
            try:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._log_file.write(self._t("log_footer", time=ts))
                self._log_file.close()
            except Exception:
                pass
            self.toast(self._t("log_stopped", path=self._log_file_path))
            self._log_file = None
            self._log_file_path = ""

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
                if h > 60:
                    self._right_send_card.setMaximumHeight(h)
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
                    pt = self.mapFromGlobal(QPoint(x, y))
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
