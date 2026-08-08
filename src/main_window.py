# -*- coding: utf-8 -*-
"""主窗口 CommTool（统一串口/网络调试工具）。"""
import atexit
import codecs
import json
import logging
import os
import random
import re
import sys
import threading
import time
import traceback
import types
import multiprocessing
from collections import deque
from datetime import datetime
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QSettings, QEvent
from PyQt5.QtGui import (QColor, QTextCursor, QTextCharFormat, QFont,
                         QFontMetrics, QTextFormat, QPalette, QKeySequence)
from PyQt5.QtWidgets import (QWidget, QMainWindow, QLabel, QPushButton, QComboBox,
                             QTextEdit, QLineEdit, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QSplitter, QScrollArea, QFrame, QFileDialog, QStatusBar,
                             QSystemTrayIcon, QMenu, QApplication, QShortcut, QToolTip, QDialog,
                             QGraphicsOpacityEffect, QStackedLayout, QWidgetAction)
try:
    from version import __version__ as APP_VERSION
except Exception:
    APP_VERSION = "0.0.0"
from theme import (ROLE_PROP, ROLE_TS, ROLE_RX, ROLE_TX, THEMES, THEME_DEFAULT, _mix,
                   chrome_for, COLOR_TEXT, COLOR_TEXT_SECONDARY, COLOR_BLUE)
from i18n import TR, CHECKSUM_KEYS
from app_icon import get_app_icon
from fonts import ui_font, mono_font, localize_qss
from widgets import (make_label, IOSSwitch, TitleBar, Card, CollapsibleSection,
                     SuffixLineEdit)

_log = logging.getLogger(__name__)

# setMaximumBlockCount only caps QTextBlock count. With line/packet split off,
# a newline-free stream stays in one block forever; budget chars as
# max_lines * _RECV_CHARS_PER_LINE.
_RECV_CHARS_PER_LINE = 256
from net_io import (TcpServerConn, TcpClientConn, UdpConn, UdpGroupConn,
                    PROTO_TCP_SERVER, PROTO_TCP_CLIENT, PROTO_UDP, PROTO_UDP_MULTICAST,
                    PROTOCOLS, SEND_NO_TARGET, ERR_CONN_TIMEOUT, local_ipv4_list, is_multicast_ipv4,
                    is_valid_ip, is_local_ipv4)
from serial_io import SerialConn, PortScannerThread, OneShotPortScanner
import conn_error_tips
from virtual_io import VirtualConn, PROTO_VIRTUAL
import send_dsl
import ansi
import binproto
import triggers
import convert
import snippets
import connection_presets
from config_keys import CFG_KEYS as _CFG_KEYS_MOD
from config_io import (
    parse_json_list as _cfg_parse_json_list,
    settings_to_bool as _cfg_to_bool,
    project_fingerprint as _cfg_project_fingerprint,
    snapshot_project_settings as _cfg_snapshot_project,
    clamp_recv_font_size as _cfg_clamp_font,
    profile_cascade_offset as _cfg_profile_offset,
    trigger_external_count as _cfg_trigger_ext_count,
    strip_trigger_externals as _cfg_strip_trigger_ext,
    script_lib_code_count as _cfg_script_lib_count,
    drop_script_lib as _cfg_drop_script_lib,
    ar_script_count as _cfg_ar_script_count,
    strip_ar_scripts as _cfg_strip_ar_scripts,
    collect_export_settings as _cfg_collect_export,
    build_export_payload as _cfg_export_payload,
    coerce_setting_value as _cfg_coerce_value,
    coerce_imported_settings as _cfg_coerce_map,
    dumps_list as _cfg_dumps_list,
    normalize_ts_format as _cfg_norm_ts,
    normalize_encoding as _cfg_norm_enc,
    clamp_combo_index as _cfg_clamp_combo,
    try_combo_index as _cfg_try_combo,
    resolve_view_mutex as _cfg_view_mutex,
    resolve_combo_text as _cfg_resolve_combo,
    parse_json_dict as _cfg_parse_json_dict,
    parse_json_object_list as _cfg_parse_obj_list,
    capture_field_defaults as _cfg_capture_defaults,
    RESET_LINE_EDITS as _CFG_RESET_LINE_EDITS,
    RESET_COMBOS as _CFG_RESET_COMBOS,
    clamp_max_lines as _cfg_clamp_lines,
)
from send_history import (
    push as _hist_push,
    load_list as _hist_load_list,
    dumps as _hist_dumps,
)
from multi_send import (
    load_groups as _ms_load_groups,
    active_items as _ms_active_items_fn,
    build_cycle_seq as _ms_build_cycle_seq,
    groups_json as _ms_groups_json,
)
from connection_presets import parse_port as _conn_parse_port
from connection_presets import parse_baud as _conn_parse_baud
from connection_presets import validate_open as _conn_validate_open
from connection_presets import (
    serial_signature as _conn_serial_sig,
    tcp_client_signature as _conn_tcp_sig,
    proto_only_signature as _conn_proto_sig,
)
import seq_context
import sequence_dataset
import io_stats
from io_stats import (
    fmt_bytes as _io_fmt_bytes,
    fmt_rate as _io_fmt_rate,
    format_stat_bar as _io_format_stat_bar,
)
import log_naming
import modbus_slave
import modbus_master
from dialogs import (CloseDialog, MultiSendDialog, KeywordHighlightDialog,
                     AboutDialog, InfoDialog, _style_one_combo_popup)
from updater import UpdateChecker
from ui_tips import set_tooltip

# 串口作为统一连接层的一种「类型」，排在网络协议之前一起进 cb_proto 下拉。
# 不放进 net_io.PROTOCOLS 是为保持 net_io 纯网络语义；这里组合成完整下拉列表。
# 虚拟连接排最后：它不接硬件，作为一种类型接入后，自动应答 / Modbus / 序列 / 脚本 /
# 波形图 等全部机制都能在离线下直接跑，无需各自改造。
from conn_ui import (
    PROTO_SERIAL,
    CONN_TYPES,
    field_visibility as _conn_field_vis,
)

import send_options_card as _send_options_card
import data_options_card as _data_options_card
import settings_card as _settings_card
import receive_card as _receive_card
import send_card as _send_card
import sidebar as _sidebar
import workspace_ui as _workspace_ui

# Sequence engine limits (S-2: owned by sequence_engine; re-exported for callers).
from sequence_engine import (
    MAX_RETRIES as _SEQ_MAX_RETRIES,
    QTIMER_MAX_MS as _SEQ_QTIMER_MAX_MS,
    RETRY_GUARD_MS as _SEQ_RETRY_GUARD_MS,
    RETRY_MAX_QUIET_MS as _SEQ_RETRY_MAX_QUIET_MS,
    step_match as _seq_engine_step_match,
    capture_vars as _seq_engine_capture_vars,
    apply_capture as _seq_engine_apply_capture,
    round_snapshot as _seq_engine_round_snapshot,
    build_summary as _seq_engine_build_summary,
    clamp_loops as _seq_engine_clamp_loops,
    clamp_timer_ms as _seq_engine_clamp_timer_ms,
    has_runnable_steps as _seq_engine_has_runnable,
    next_enabled_index as _seq_engine_next_enabled,
    prepare_runtime as _seq_engine_prepare_runtime,
    step_kind as _seq_engine_step_kind,
    should_retry as _seq_engine_should_retry,
    plan_retry as _seq_engine_plan_retry,
    retry_remain_s as _seq_engine_retry_remain,
    more_rounds as _seq_engine_more_rounds,
    continue_after_fail as _seq_engine_continue_after_fail,
    clip_rx_hex as _seq_engine_clip_rx_hex,
    detail_from_extracted as _seq_engine_detail_extracted,
    initial_results as _seq_engine_initial_results,
)

from modbus_timing import (
    serial_char_bits as _mbm_timing_char_bits,
    rtu_silent_ms as _mbm_timing_silent_ms,
    rtu_tx_guard_ms as _mbm_timing_tx_guard_ms,
    response_len_budget as _mbm_timing_resp_len,
    timeout_ms as _mbm_timing_timeout_ms,
    span_bad as _mbm_timing_span_bad,
)

from modbus_scheduler import (
    pick_next_due as _mbm_sched_pick_next,
    schedule_delay_ms as _mbm_sched_delay_ms,
    next_due_after as _mbm_sched_next_due,
)

from view_format import (
    bytes_to_hex as _view_bytes_to_hex,
    format_hexdump as _view_format_hexdump,
    with_leading_newline as _view_leading_nl,
    timestamp_prefix as _view_timestamp_prefix,
    view_mode_of_state as _view_mode_of_state,
    view_extra_index as _view_extra_index,
)

from rx_text import (
    decode_auto_chunk as _rx_decode_auto_chunk,
    split_lines_with_offsets as _rx_split_lines,
    ansi_flatten as _rx_ansi_flatten,
    ansi_shift as _rx_ansi_shift,
    ansi_slice as _rx_ansi_slice,
)

from trigger_safe import (
    is_private_url as _trg_is_private_url,
    shell_value as _trg_shell_quote,
)

from keyword_groups import (
    load_groups as _kw_load_groups,
    active_rules as _kw_active_rules,
    save_fields as _kw_save_fields,
)
from project_templates import (
    workspace_tool_entries as _ws_tool_entries,
    workspace_template_options as _ws_template_options,
)

from ui_options import (
    VIEW_MODE_ITEMS as _ui_view_mode_items,
    TS_FORMAT_ITEMS as _ui_ts_format_items,
    SEARCH_MODE_ITEMS as _ui_search_mode_items,
)


# 数据区正文的实际渲染格式。切换视图不会重排历史，所以格式必须跟着字符保存，不能只看当前开关。
VIEW_PROP = QTextFormat.UserProperty + 2
VIEW_TEXT = 1
VIEW_HEX = 2
VIEW_HEXDUMP = 3
VIEW_NUMERIC = 4
VIEW_TERMINAL = 5

# ANSI 着色：存「颜色标识」而非解析好的颜色，切主题时按新主题明暗重解析（见 _recolor_history）。
# 存序号的会跟着主题走，设备指定的精确色(#RRGGBB)不跟着变。
ANSI_FG_PROP = QTextFormat.UserProperty + 3
ANSI_BG_PROP = QTextFormat.UserProperty + 4

from serial_params import (
    resolve_pyserial as _resolve_serial_params,
)


from auto_reply_core import (
    crc_impl as _ar_crc_impl,
    to_int as _ar_core_to_int,
    parse_hex_pat as _ar_core_parse_hex_pat,
    hex_at as _ar_core_hex_at,
    hit_test as _ar_core_hit_test,
    crc as _ar_core_crc,
    parse_delay as _ar_core_parse_delay,
    norm_idx as _ar_core_norm_idx,
    frame_ok as _ar_core_frame_ok,
    compute_checksum as _ar_core_compute_checksum,
    state_tokens as _ar_core_state_tokens,
    norm_frame as _ar_core_norm_frame,
    norm_fault as _ar_core_norm_fault,
    norm_sm as _ar_core_norm_sm,
    norm_modbus as _ar_core_norm_modbus,
    reply_bytes as _ar_core_reply_bytes,
    apply_cs_segs as _ar_core_apply_cs_segs,
    compose_frame as _ar_core_compose_frame,
    apply_fault as _ar_core_apply_fault,
    subst_reply as _ar_core_subst_reply,
    build_parts as _ar_core_build_parts,
    state_ok as _ar_core_state_ok,
    next_state as _ar_core_next_state,
)


def _ar_script_worker(conn):
    """B5 脚本常驻子进程。每个任务用全新 namespace；主进程超时时杀整个进程组，
    脚本若再起子进程(subprocess 等)也会被一并清理、不残留。只回传可 pickle 的 bytes/错误文本。"""
    group_ready = sys.platform == "win32"   # Windows 由 taskkill /T 按 PID 树回收，无 setsid
    if hasattr(os, "setsid"):
        try:
            os.setsid()      # 成为新会话/进程组组长 → 脚本起的子进程同组，父进程可整组 kill
            group_ready = (os.getpgrp() == os.getpid())
        except Exception:
            group_ready = False
    try:
        conn.send(("ready", group_ready))   # 父进程收到后才允许发任务/整组 kill
    except Exception:
        conn.close()
        return

    def _xor8(d):
        value = 0
        for c in bytes(d):
            value ^= c
        return bytes([value])

    def _hexbytes(s):
        clean = re.sub(r"[^0-9A-Fa-f]", "", str(s).replace("0x", "").replace("0X", ""))
        return bytes.fromhex(clean)

    try:
        while True:
            try:
                script, frame, ctx_data, codec = conn.recv()
            except EOFError:
                return
            try:
                ctx = types.SimpleNamespace(
                    state=ctx_data["state"], seq=ctx_data["seq"], hits=ctx_data["hits"],
                    crc=_ar_crc_impl,
                    crc16=lambda d: _ar_crc_impl(d, 16, 0x8005, 0xFFFF,
                                                  refin=True, refout=True, byteorder="little"),
                    crc8=lambda d: _ar_crc_impl(d, 8, 0x07, 0x00),
                    sum8=lambda d: bytes([sum(bytes(d)) & 0xFF]),
                    xor8=_xor8, hexbytes=_hexbytes,
                    tohex=lambda d: " ".join("%02X" % x for x in bytes(d)),
                )
                ns = {}
                exec(compile(script, "<ar-script>", "exec"), ns)
                func = ns.get("reply")
                if not callable(func):
                    raise ValueError("脚本须定义 reply(frame, ctx) 函数")
                result = func(bytes(frame), ctx)
                if result is None:
                    norm = None
                elif isinstance(result, (bytes, bytearray)):
                    norm = [bytes(result)]
                elif isinstance(result, str):
                    norm = [result.encode(codec, errors="replace")]
                elif isinstance(result, (list, tuple)):
                    norm = []
                    for item in result:
                        if isinstance(item, (bytes, bytearray)):
                            norm.append(bytes(item))
                        elif isinstance(item, str):
                            norm.append(item.encode(codec, errors="replace"))
                        else:
                            raise TypeError("reply 返回 list 内含非 bytes / str 元素")
                else:
                    raise TypeError("reply 返回类型须 bytes / str / list / None")
                conn.send(("ok", norm))
            except Exception as e:
                conn.send(("err", "%s: %s" % (type(e).__name__, e)))
    finally:
        conn.close()


class ThemedToolTip(QLabel):
    """不透明主题化 tooltip（仅 macOS 用）。

    macOS 上 Qt 给原生 QToolTip 套样式表后会把它设为半透明窗口，背景不绘制，
    文字直接叠在底层控件上看不清。这里自绘一个：用 autoFillBackground + palette
    上色（基于调色板的填充一定不透明，不走会触发半透明的 QSS 背景），边框用
    QFrame.Box（颜色取前景色）。Windows 仍用原生圆角 tooltip。"""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(True)
        self.setContentsMargins(9, 6, 9, 6)
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setLineWidth(1)
        self.setFont(ui_font(10))
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_text(self, gpos, text, bg, fg):
        if not text:
            self.hide()
            return
        self.setText(text)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(bg))
        pal.setColor(QPalette.WindowText, QColor(fg))
        self.setPalette(pal)
        self.adjustSize()
        self._place(gpos)
        self.show()
        self.raise_()
        self._hide_timer.start(15000)   # 兜底自动隐藏（鼠标点击/移动也会触发隐藏）

    def _place(self, gpos):
        screen = QApplication.screenAt(gpos) or QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QRect(0, 0, 99999, 99999)
        w, h = self.width(), self.height()
        x = gpos.x() + 14
        y = gpos.y() + 18
        if x + w > geo.right():
            x = max(geo.left(), gpos.x() - w - 6)
        if y + h > geo.bottom():
            y = max(geo.top(), gpos.y() - h - 6)
        self.move(x, y)


class ChecksumPopup(QWidget):
    """状态栏选区校验的应用内卡片，规避原生 tooltip 的跨平台样式差异。"""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        self.card = QFrame()
        self.card.setObjectName("ChecksumCard")
        self.card.setFixedWidth(300)
        outer.addWidget(self.card)

        content = QVBoxLayout(self.card)
        content.setContentsMargins(16, 14, 16, 14)
        content.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        self.title = QLabel()
        self.title.setObjectName("ChecksumTitle")
        self.title.setFont(ui_font(11, bold=True))
        header.addWidget(self.title, 1)
        self.meta = QLabel()
        self.meta.setObjectName("ChecksumMeta")
        self.meta.setAlignment(Qt.AlignCenter)
        self.meta.setFont(ui_font(9))
        header.addWidget(self.meta)
        content.addLayout(header)

        divider = QFrame()
        divider.setObjectName("ChecksumDivider")
        divider.setFixedHeight(1)
        content.addWidget(divider)

        self.rows = QWidget()
        self.rows.setObjectName("ChecksumRows")
        self.grid = QGridLayout(self.rows)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(5)
        self.grid.setColumnStretch(1, 1)
        content.addWidget(self.rows)

        self._rows = []          # [(名称 label, 值 label)]，按需增长后复用
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def _row_at(self, i):
        """取第 i 行的两个 label，不够就新建。

        行控件复用而不是每次重建：算法集是固定的 9 行，重建除了白费还会让每次悬停都
        丢下 18 个待销毁的 QLabel —— deleteLater 要等事件循环空闲才真删，连续悬停时
        它们会短暂堆积（实测连刷 10 次不给事件循环，子控件从 20 涨到 200）。
        """
        while len(self._rows) <= i:
            name_label = QLabel()
            name_label.setObjectName("ChecksumName")
            name_label.setFont(ui_font(9))
            value_label = QLabel()
            value_label.setObjectName("ChecksumValue")
            value_label.setFont(mono_font(9))
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setTextInteractionFlags(Qt.NoTextInteraction)
            row = len(self._rows)
            self.grid.addWidget(name_label, row, 0)
            self.grid.addWidget(value_label, row, 1)
            self._rows.append((name_label, value_label))
        return self._rows[i]

    def set_content(self, title, meta, rows, colors):
        self.title.setText(title)
        self.meta.setText(meta)
        for i, (name, value) in enumerate(rows):
            name_label, value_label = self._row_at(i)
            name_label.setText(name)
            value_label.setText(value)
            name_label.show()
            value_label.show()
        for name_label, value_label in self._rows[len(rows):]:   # 多余的行藏起来备用
            name_label.hide()
            value_label.hide()

        self.card.setStyleSheet(localize_qss(f"""
            QFrame#ChecksumCard {{
                background-color: {colors['card_bg']};
                border: 1px solid {colors['separator']};
                border-radius: 12px;
            }}
            QLabel#ChecksumTitle {{
                color: {colors['text']};
                background: transparent;
            }}
            QLabel#ChecksumMeta {{
                color: {colors['accent']};
                background-color: {colors['ghost_bg']};
                border-radius: 8px;
                padding: 3px 8px;
            }}
            QFrame#ChecksumDivider {{
                background-color: {colors['separator']};
                border: 0;
            }}
            QWidget#ChecksumRows, QLabel#ChecksumName {{
                color: {colors['text_sec']};
                background: transparent;
                border: 0;
            }}
            QLabel#ChecksumValue {{
                color: {colors['text']};
                background-color: {colors['input_bg']};
                border: 0;
                border-radius: 6px;
                padding: 3px 8px;
            }}
        """))
        self.adjustSize()

    def show_for(self, anchor):
        """贴着状态栏标签上方显示，并限制在当前屏幕可用区域内。"""
        self.adjustSize()
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        screen = QApplication.screenAt(top_left) or QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else QRect(0, 0, 99999, 99999)
        x = top_left.x() + (anchor.width() - self.width()) // 2
        y = top_left.y() - self.height() - 6
        x = max(geo.left() + 4, min(x, geo.right() - self.width() - 3))
        if y < geo.top() + 4:
            y = min(geo.bottom() - self.height() - 3,
                    top_left.y() + anchor.height() + 6)
        self.move(x, y)
        self.show()
        self.raise_()
        self._hide_timer.start(20000)

    def hideEvent(self, event):
        self._hide_timer.stop()
        super().hideEvent(event)


# ============== 主窗口 ==============
class CommTool(QMainWindow):
    RESIZE_MARGIN = 6
    _AR_SCRIPT_TIMEOUT = 1.0   # B5：脚本执行超时(秒)，超时即放弃本次、防死循环/阻塞冻结 GUI
    _TRG_MAX_ACTIONS = 8       # in-flight webhook / run_cmd workers
    _AR_SCRIPT_START_TIMEOUT = 5.0  # spawn/冻结版首启可较慢；与单次脚本超时分开

    def __init__(self, profile=""):
        super().__init__()
        # 多窗口配置隔离：""=主窗口(settings.ini)，其余用 settings-<profile>.ini；标题加 (N) 区分。
        # 让「开多个窗口 / 新建窗口」各用各的配置、退出不再互相覆盖。
        self._profile = str(profile or "")
        self._title_suffix = "" if not self._profile else " (%s)" % self._profile
        # macOS 用原生窗口边框（红黄绿交通灯 + 系统原生缩放）；Windows/Linux 仍是自定义无边框
        if sys.platform == "darwin":
            self.setWindowFlags(Qt.Window)
        else:
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        # 边缘缩放：Windows 走下面的 nativeEvent(WM_NCHITTEST)；macOS 由原生边框处理；
        # 其它（Linux）无边框又无原生缩放 → 应用级事件过滤器手动实现（悬停光标 + 拖拽改几何）。
        self._manual_resize = sys.platform not in ("win32", "darwin")
        self._resize_edges = Qt.Edges()
        self._resize_start_geo = None
        self._resize_start_mouse = None
        self._hover_cursor_shape = None
        # macOS：原生 QToolTip 加样式后背景透明，改用自绘不透明 tooltip，需 app 级
        # 事件过滤器拦截 ToolTip 事件（Windows/Linux 原生 tooltip 正常，不拦截）。
        self._mac_tooltip = sys.platform == "darwin"
        self._tooltip_popup = None
        self._sel_chk_popup = None
        self._sel_chk_popup_payload = None
        if self._manual_resize or self._mac_tooltip:
            QApplication.instance().installEventFilter(self)

        self.conn = None          # 当前连接：SerialConn / TcpServerConn / TcpClientConn / UdpConn(...)
        self._conn_proto = None   # 实际打开的协议；配置导入可改下拉框，不能拿新值解释旧连接
        self._conn_cfg = None     # 实际打开时的端点/串口参数快照；UI 导入改值后必须重连
        self._conn_engaged = False   # 连接是否已成功建立 → 区分"打开失败"与"运行时断开"的错误文案
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.rx_packets = 0       # 收发包计数：RX=每次到达一块、TX=每次成功发送
        self.tx_packets = 0
        self.rx_errors = 0        # RX 错误：接收处理异常 + 连接/链路错误
        self.tx_errors = 0        # TX 错误：发送失败（无对端 / 写失败 / 异常）
        self._rx_rate = 0         # 当前速率 B/s（每秒采样一次的字节增量）
        self._tx_rate = 0
        self._rx_peak = 0         # 峰值速率 B/s
        self._tx_peak = 0
        self._rx_bytes_mark = 0   # 上次采样时的累计字节，用于算每秒增量
        self._tx_bytes_mark = 0
        self._rate_time_mark = time.monotonic()
        self._io_stats = io_stats.IoStatsAccumulator()

        # 串口端口扫描（仅串口模式用）：后台轮询线程避免 comports() 卡 GUI
        self._last_port_list = []
        self._oneshot_scan = None
        self.port_scanner = None
        self._pending_restore_port = None   # 启动时待恢复的上次串口设备名
        self._serial_empty_selection = False
        self._connection_presets = []

        self.send_timer = QTimer(self)
        self.send_timer.timeout.connect(self.do_send)

        # 收发速率采样：1Hz 取字节增量近似 B/s + 记录峰值，并刷新状态栏统计
        # （start 推迟到 init_ui 之后，确保首个 tick 触发时 lbl_rx_stat 已创建）
        self._rate_timer = QTimer(self)
        self._rate_timer.timeout.connect(self._tick_rate)

        self._reset_recv_state()   # 接收解析状态（方向/缓冲/增量解码器/换行）统一初始化
        self._log_file = None
        self._freeze_view = False
        self._log_file_path = ""
        self._log_ends_with_nl = True  # 日志文件流独立于可见文本区的行尾状态
        self._log_limit = 0       # 分包字节上限，0=不分包
        self._log_base_path = ""  # 用户选的原始路径(可含 %date/%port 等变量)，分包/跨日据此派生
        self._log_seg = 0         # 当前分包序号
        self._log_opened_at = None  # 当前分包的开启时刻，用于跨午夜判定（见 log_naming.should_roll_date）
        self._recv_font_size = 10

        self.settings = QSettings(self._settings_file(self._profile), QSettings.IniFormat)
        self._ar_rules = self._load_ar_rules()       # 自动应答规则
        self._ar_on = self.settings.value("autoreply_on", False, type=bool)
        self._ar_buf = b""                           # 整包组装缓冲（静默超时 / 帧头+长度组帧 共用）
        self._ar_frame = self._load_ar_frame()       # 帧头+长度组帧配置（全局；启用时优先于 gap 静默分帧）
        self._ar_fault = self._load_ar_fault()       # C6 全局故障注入配置（丢包/错CRC/错长度，压测主机）
        self._ar_sm = self._load_ar_sm()             # C8 多步状态机配置（全局；on/init）
        self._ar_state = self._ar_sm.get("init", "")  # 当前状态(运行态，不持久化)；连接/重置时回到 init
        self._ar_generation = 0   # C8：会话代际。reset_state 时 +1，作废在途的延迟应答 singleShot
        self._ar_sm_pending = None  # C8：在途状态转移 token；整条多段应答完成前串行化后续状态帧
        self._ar_sm_queue = deque() # C8：pending 期间收到的完整帧 FIFO（有界，保持收帧顺序）
        self._ar_sm_draining = False # C8：FIFO 同步排空重入保护
        self._ar_modbus = self._load_ar_modbus()     # B4 Modbus RTU 从机配置（全局；on/addr/寄存器表）
        self._modbus = modbus_slave.slave_bank_from_config(self._ar_modbus)  # 运行态从机模型（主机写会改它）
        self._modbus_buffers = {}                    # TCP Server 每客户端独立半包，防止并发连接串流
        # Modbus 主机轮询（master/poll）：规则 + 总开关 + 变体；运行态半双工调度
        self._mbm_rules = self._load_mbm_rules()
        self._mbm_views = self._load_mbm_views()
        self._mbm_on = self.settings.value("modbus_master_on", False, type=bool)
        if self._mbm_on and self._ar_on:
            self._ar_on = False       # 主机/自动应答共用同一收流，启动时主机模式优先，禁止假双开
            self.settings.setValue("autoreply_on", False)
        self._mbm_variant = self.settings.value("modbus_master_variant", "", type=str)  # ""=按连接自动
        self._mbm_echo = self.settings.value("modbus_master_echo", False, type=bool)  # 串口本地回显模式
        self._device_registers = self._load_device_registers()
        self._device_plot_tags = self._load_device_link("device_plot_tags")
        self._device_dash_tags = self._load_device_link("device_dash_tags")
        self._device_scan_state = None
        self._device_scan_timeout_ms = 300
        self._device_center_dlg = None
        # 自动化测试序列：顺序执行每步（发送 → 等回包匹配 → 超时按动作走），出「通过/失败」。
        # 运行态挂在这里，规则(步骤列表)存 settings；运行期抑制自动应答/Modbus（三者共用收流）。
        self._seq_rules = self._load_seq_rules()
        self._seq_on = False          # 是否正在运行
        self._seq_ctx = seq_context.RoundContext()
        self._seq_runtime_step = None
        self._seq_steps = []          # 本次运行的步骤快照
        self._seq_idx = 0             # 当前步
        self._seq_attempt = 1         # 当前步第几次尝试（含首次；步骤级重试用）
        self._seq_buf = b""           # 当前步累积的回包字节（跨块匹配）
        self._seq_results = []        # 每步结果 {status,ms,detail}
        self._seq_summary = None      # 运行结束汇总 {ok,total,ms,pass,loops,rounds,rounds_pass,round_list}
        self._seq_gen = 0             # 代际：start/stop 时 +1，作废在途的延时/超时续跑
        self._seq_dlg = None
        self._frame_builder_dlg = None   # 帧构造器对话框（单实例）
        self._toolbox_dlg = None         # 工具箱对话框（进制转换 + 校验计算，单实例）
        self._xfer_dlg = None            # 文件传输对话框（协议收发 / 原始字节流，单实例）
        self._xfer_worker = None         # 传输后台线程；非 None 且运行中时 on_data_received 接管收流
        self._xfer_target = None         # 传输起始时捕获的发送目标（网络多端用；串口 None）
        self._bridge_dlg = None          # 桥接转发对话框（两端任意 串口/TCP/UDP 组合，单实例）
        self._dash_dlg = None            # 数值仪表盘对话框（大字号实时值 + 阈值告警，单实例）
        self._script_dlg = None          # 脚本控制台对话框（Python 驱动收发，单实例）
        self._script_worker = None       # 脚本运行中的 worker；非 None 时 on_data_received 把 RX 复制给它
        self._script_orphans = []        # 停不下来的脚本 worker（纯计算死循环）：留引用防 QThread running 时被析构
        self._script_quiet_until = 0.0   # 接管前已有 Modbus 请求的迟到响应隔离截止时间
        from macro_recorder import MacroRecorder
        self._macro = MacroRecorder()    # 宏录制：把手动收发录成脚本（脚本控制台里启停）
        from rec_replay import StreamRecorder
        self._recorder = StreamRecorder()  # 数据录制：原始收发流按时序存 .ctrec，可当「设备」回放
        from device_resources import StructuredRecorder
        self._structured_recorder = StructuredRecorder()
        self._structured_dlg = None
        self._replay_on = False            # 回放进行中（占用收发流，计入 _io_task_busy）
        self._rr_dlg = None                # 录制/回放对话框（单实例）
        self._rd_dlg = None                # 会话比较对话框（单实例，纯离线不碰连接）
        self._snip_dlg = None              # 发送模板库对话框（单实例）
        self._send_hist_dlg = None         # 发送历史搜索选择器（单实例）
        self._cpreset_dlg = None
        self._dsl_ops = None               # 命令 DSL 执行中的指令序列（None=空闲）
        self._dsl_idx = 0
        self._dsl_gen = 0                  # 代际：中止后让已排队的 QTimer 回调失效
        self._dsl_record = True
        self._ar_in_flight = False       # 正在发自动应答的回复 → 宏录制跳过（不是用户手动发）
        self._seq_started_at = ""     # 最近一次运行的墙钟起始时间字符串（导出报告用）
        self._seq_finished_at = ""
        self._seq_loops = 1           # 循环次数（整条序列跑几轮）
        self._seq_dataset = None     # CSV dataset dict or None
        self._seq_dataset_row = None # current CSV row meta for this round
        self._seq_round_snapshot_taken = False
        self._seq_loop_i = 0          # 当前第几轮（0 基）
        self._seq_stop_on_fail = False  # 某轮失败即停止后续循环
        self._seq_rounds = []         # 每轮汇总 [{round,ok,total,ms,pass}]（供循环汇总/报告）
        self._seq_round_t0 = 0.0      # 当前轮起始 monotonic
        self._seq_t0 = 0.0
        self._seq_step_total_t0 = 0.0  # 当前步骤总起点（含所有失败尝试 + 重试间隔，用于耗时统计）
        self._seq_retry_not_before = 0.0
        self._seq_retry_quiet_until = 0.0
        self._seq_retry_quiet_deadline = 0.0   # 静默窗最迟等到此刻，防对端不停刷数据卡死重试
        self._seq_waiting_mbm = False  # 启动时先等已有 Modbus 在途请求完成/超时隔离结束
        self._seq_wait_mbm_variant = ""
        self._seq_wait_mbm_until = 0.0
        self._seq_timer = QTimer(self)   # 当前步「等回包」超时（单次）
        self._seq_timer.setSingleShot(True)
        self._seq_timer.timeout.connect(self._seq_on_timeout)
        # 终端模式：发送框逐字符即时发送 + 数据区纯字节流显示（轻量串口终端，不解析 ANSI 转义）
        self._terminal_on = self.settings.value("terminal_mode", False, type=bool)
        self._terminal_echo = self.settings.value("terminal_echo", False, type=bool)   # 本地回显
        self._hexdump_on = self.settings.value("hexdump_view", False, type=bool)        # HEX dump 视图（偏移+HEX+ASCII 三列）
        self._numview_on = self.settings.value("numview", False, type=bool)             # 数值视图（字节流按数值类型解读）
        # ANSI 着色（文本模式）：按设备发的 SGR 转义给日志上色，顺带吃掉光标/擦除等非 SGR 序列
        self._ansi_on = self.settings.value("ansi_color", False, type=bool)
        self._ansi_state = None    # 跨包延续的样式（颜色常常跨包）
        self._ansi_pending = ""    # 跨包未收完的转义序列残片
        self._ansi_states = {}     # TCP Server：每客户端独立样式/残片，防并发来源互相染色
        self._ansi_pendings = {}
        # 触发告警：命中规则就响铃 / 托盘通知 / 数据区打标（无人值守盯梢）
        self._triggers = self._load_triggers()
        self._trigger_engine = triggers.TriggerEngine(self._triggers)
        self._triggers_dlg = None
        self._trg_action_lock = threading.Lock()   # webhook / 运行程序动作的并发闸门
        self._trg_action_busy = 0
        self._trg_action_dropped = 0
        self._trg_procs = set()     # 外部程序动作的活动子进程，退出时靠它回收
        # closeEvent 跑不到的路径（未捕获异常、sys.exit、脚本里直接退）也要把
        # 子进程收掉，否则 POSIX 上成孤儿、Windows 上同样残留。_trg_stop_procs
        # 只碰纯 Python 属性与 subprocess，不碰 Qt，在解释器退出阶段跑是安全的。
        atexit.register(self._trg_stop_procs)
        self._trg_launching = 0     # 已开始、还没登记句柄的 Popen 数
        self._trg_stopping = False  # 竖起后不再放行新动作（单向，只由退出流程置位）
        self._trg_dec_buf = {}      # 触发引擎的增量解码状态，按方向/来源流隔离
        self._trg_dec = {}
        self._trg_dec_codec = None
        self._trg_ansi_pending = {} # 跨块未完成的 ANSI 转义残片，同样按流隔离
        self._trg_tail_bytes = {}   # 跨块回看的尾巴，按流隔离（关键字可能被劈成两半）
        self._trg_tail_text = {}
        # 数值视图余数按来源隔离：TCP Server 多客户端的半个数不能互相拼接；普通串口/单连接用 None 键。
        self._numview_carries = {}
        self._proto_hl_on = self.settings.value("proto_highlight", False, type=bool)     # 协议高亮（HEX 模式按帧解析规则给字段上色）
        self._proto_fields = deque(maxlen=3000)   # [{cursor, color, label}]：已上色字段(带 keepPositionOnInsert 的 QTextCursor)，供高亮+悬浮
        self._proto_rules_raw = None              # frame_rules 上次解析时的原始串（变了才重解析）
        self._proto_rules_cache = []              # 解析后的规则缓存
        self._terminal_enter = self._safe_enter_idx(self.settings.value("terminal_enter", 0))   # 0=CR 1=LF 2=CRLF
        self._term_sgr = None  # 终端渲染：当前 SGR 样式（跨块延续，ANSI 着色开时才上色）
        self._term_esc = ""    # 终端渲染：跨块未完成的 ANSI/CSI 转义序列缓冲
        self._term_discard_csi = False  # 超长 CSI：跨块丢弃到终止字节，避免残片显示
        self._term_discard_osc = False  # 超长 OSC：丢弃到 BEL / ST，避免标题内容漏进正文
        self._term_osc_prev_esc = False
        self._term_streams = {}  # TCP Server：每个客户端独立 SGR/转义残片，防串色/串控制码
        self._term_pos = None  # 终端渲染：跨块延续的光标绝对位置（None=从文末开始）
        self._setting_labels = {}   # 设置项标签引用（i18n key → QLabel），终端模式淡化禁用行用
        self._mbm_inflight = None    # 在途请求 {i,unit,func,qty,tid,variant}；None=空闲可发下一条
        self._mbm_buf = b""          # 响应字节累积（半双工，只对应当前在途请求）
        self._mbm_tid = 0            # Modbus-TCP 事务 ID 自增
        self._mbm_due = {}           # 行 index → 下次到点 monotonic 时刻
        self._mbm_results = {}       # 行 index → {"status","text"}（供对话框读/打开时回填）
        self._mbm_guard_until = 0.0  # RTU 帧间静默/超时隔离：到此刻前不发新请求
        self._mbm_sched = QTimer(self)   # 调度下一条轮询（单次）
        self._mbm_sched.setSingleShot(True)
        self._mbm_sched.timeout.connect(self._mbm_tick)
        self._mbm_to = QTimer(self)      # 当前在途请求的响应超时（单次）
        self._mbm_to.setSingleShot(True)
        self._mbm_to.timeout.connect(self._mbm_on_timeout)
        self._ar_gap_timer = QTimer(self)            # 整包静默超时
        self._ar_gap_timer.setSingleShot(True)
        self._ar_gap_timer.timeout.connect(self._ar_flush)
        self._ar_gap = 0     # 整包静默(ms)：取所有启用规则中的最大值（分帧在匹配前、整条串口共用一个）
        self._ar_script_cache = {}   # B5：脚本文本 → (编译 code, 错误文案)，主进程先做语法校验
        self._ar_script_proc = None  # B5：实发脚本常驻隔离进程（超时整组 kill + 下次重建）
        self._ar_script_conn = None
        self._ar_script_group_ready = False  # ready 握手确认 worker PID 是独立进程组 ID
        self._ar_preview_proc = None # B5：预览/测试专用隔离进程，与实发分开 → 预览不污染实发模块态
        self._ar_preview_conn = None
        self._ar_preview_group_ready = False
        self._ar_seq = 0     # 应答 {seq} 占位符的自增计数（每次替换 +1，wrap 0..255）
        self._send_count = 0 # 发送区 {count} 占位符的自增计数（每次成功 do_send/多条发送 +1，wrap）
        self._send_hist = []         # 发送命令历史(FIFO max 100)，启动从 QSettings 恢复
        self._send_hist_idx = -1     # 当前导航位置：-1=未在导航态，0..len-1=正在看历史第 N 条
        self._send_hist_pending = "" # 进入历史前的草稿，↓ 翻回最新时复原
        # 串口物理移除检测：已连接的口在后台扫描里连续 _serial_missing_limit 次都枚举不到
        # → 判定已拔出/掉驱动 → 主动断开。去抖(连续多次)是为滤掉 USB 串口的瞬时掉枚举
        # (见 _populate_port_combo 注释)，否则适配器抖一下就把正在用的连接误断了。
        # 扫描周期 1500ms → 3 次 ≈ 4.5s 才断。
        self._serial_device = None       # 当前已连接的串口设备名(仅串口连接时非空)
        self._serial_missing_count = 0   # 已连接:当前口在扫描中连续未枚举到的次数(去抖计数)
        self._sel_missing_count = 0      # 未连接:选中口连续缺失次数(占位宽限去抖，超限删占位)
        self._serial_missing_limit = 3
        self._available_serial_devices = set()  # 最近一次后台扫描枚举到的真实设备名
        self._serial_reconnect_cfg = None        # 掉线前的串口签名；重连只允许回到这个设备/参数
        self._serial_reconnect_limit = 10        # 串口退避 0.5s 递增到 5s，第 10 次后停止
        # 自动重连：串口 0.5s 线性递增到 5s；网络指数退避（上限 30s）。主动关闭/退出时跳过。
        self._user_closing = False
        self._reconnect_attempts = 0
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._try_reconnect)
        self._recompute_ar_gap()
        # 自动应答按钮：单击延时打开对话框、双击翻转总开关。Qt 一次双击会发 click→dblclick→click
        # 三个信号，故单击启 timer 延后打开；双击 cancel timer；第二个 click 因距上次过近被忽略。
        self._ar_click_timer = QTimer(self)
        self._ar_click_timer.setSingleShot(True)
        self._ar_click_timer.timeout.connect(self.open_auto_reply)
        self._ar_last_click = 0.0
        saved_lang = self.settings.value("language", "zh")
        self._lang = saved_lang if saved_lang in TR else "zh"
        self._L = TR[self._lang]

        self._closing_real = False
        self._tray = None
        self._project_path = None
        self._project_meta = {}
        self._project_name = ""
        self._project_baseline = None

        self.init_ui()
        self._rate_timer.start(1000)   # init_ui 后再启动统计采样，保证首 tick 时 lbl_rx_stat 已存在
        # 鼠标跟踪：仅手动缩放（Linux）需要——悬停时也产生 MouseMove 以实时切换缩放光标。
        if self._manual_resize:
            self.setMouseTracking(True)
            self.centralWidget().setMouseTracking(True)
            if hasattr(self, "title_bar"):
                self.title_bar.setMouseTracking(True)
        self.refresh_ports()       # 启动即扫一次串口，cb_port 立刻有内容供恢复上次选择
        self.apply_style()
        self._capture_field_defaults()   # 记录字段构建默认值（在 _load_settings 覆盖前）供切换配置复位用
        self._load_settings()
        self._setup_tray()
        # Ctrl+F 全局快捷键：从任何控件按下都打开搜索栏（_open_search 内会自动聚焦输入框）
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._open_search)
        QShortcut(QKeySequence("Ctrl+F2"), self, activated=self._bookmark_toggle)
        QShortcut(QKeySequence("F2"), self, activated=self._bookmark_next)
        QShortcut(QKeySequence("Shift+F2"), self, activated=self._bookmark_prev)
        # 配置导入/导出快捷键（避开 Ctrl+S=保存数据区、Ctrl+O 占用）
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self.export_config)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, activated=self.import_config)

        self.port_scanner = PortScannerThread(interval_ms=1500)
        self.port_scanner.scan_complete.connect(self._on_port_scan_complete)
        self.port_scanner.start()
        # UI 和默认配置全部落定后再恢复工程，避免构造中途应用工程设置覆盖尚未创建的控件。
        QTimer.singleShot(0, self._restore_last_project)

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

    def _is_open(self) -> bool:
        """是否已建立连接并可发送（统一状态判断，替代原 self.ser and self.ser.is_open）。"""
        return bool(self.conn and self.conn.is_open)

    def _label_col_width(self) -> int:
        """网络设置左侧标签列宽：按当前语言下各标签的最大实测文本宽度自适应，
        避免英文单词(如 Remote Port)被输入框遮挡。"""
        keys = ("protocol_type", "cpreset_label", "local_ip", "local_port", "group_addr",
                "remote_ip", "remote_port", "target_client", "use_remote",
                "port", "baud_rate", "data_bits", "parity", "stop_bits")
        fm = QFontMetrics(ui_font(11))
        w = max(fm.horizontalAdvance(self._t(k)) for k in keys)
        return max(44, w + 9)  # +9 右边距；中文下至少 44 保持原观感

    def _tr_label(self, key, size=11, bold=False, color=COLOR_TEXT):
        lbl = make_label(self._t(key), size, bold, color)
        lbl.setProperty("tr_text", key)
        # 自动挂 tooltip：若同名 _tip 键存在则用它，语言切换时由 _apply_language 同步
        tip_key = key + "_tip"
        if tip_key in self._L:
            set_tooltip(lbl, self._L[tip_key])
            lbl.setProperty("tr_tooltip", tip_key)
        return lbl

    # ----- UI 构建 -----
    def init_ui(self):
        self.setWindowTitle(self._t("app_title") + self._title_suffix)
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
        self.title_bar.set_title(self._t("app_title") + self._title_suffix)
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
        set_tooltip(self.cb_theme, self._t("theme_tip"))
        self.cb_theme.currentIndexChanged.connect(lambda _: self._on_theme_changed())

        # 「帮助」下拉按钮：放在 stretch 后、min/max/close 前；点开弹菜单含「关于」
        # （复用 open_about，里面有 检查更新/升级 功能，对应右下角版本号那边的入口）
        self.btn_titlebar_help = QPushButton(self._t("help"))
        self.btn_titlebar_help.setObjectName("TbHelpBtn")
        self.btn_titlebar_help.setProperty("tr_text", "help")
        self.btn_titlebar_help.setCursor(Qt.PointingHandCursor)
        self.btn_titlebar_help.setFixedHeight(26)
        self.btn_titlebar_help.clicked.connect(self._show_titlebar_help_menu)
        self.title_bar.layout().insertWidget(
            self.title_bar.layout().indexOf(self.title_bar.btn_min),
            self.btn_titlebar_help)
        root.addWidget(self.title_bar)
        root.addWidget(self._build_workbench_bar())

        # 工作区内容：终端保留完整收发界面，其余分类使用独立工具入口页。
        self.workspace_host = QWidget()
        self.workspace_host.setObjectName("WorkspaceHost")
        self.workspace_stack = QStackedLayout(self.workspace_host)
        self.workspace_stack.setContentsMargins(0, 0, 0, 0)
        self.workspace_stack.setStackingMode(QStackedLayout.StackOne)
        root.addWidget(self.workspace_host, 1)

        # 终端工作区
        content = QWidget()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 12, 20, 12)
        content_layout.setSpacing(10)
        self.workspace_stack.addWidget(content)
        self._workspace_page_indexes = {"terminal": 0}

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
        # 侧栏默认 300：数据区「显示方式」那行要同时容下 模式下拉 + 彩色开关/附属参数两列
        # （原来那一列只放 40px 的开关），280 会差十几像素、逼出横向滚动条。上限仍 380、可拖。
        self.h_splitter.setSizes([300, 840])

        content_layout.addWidget(self.h_splitter, 1)

        for workspace_key in ("protocol", "simulation", "automation", "data", "bridge"):
            page = self._build_workspace_page(workspace_key)
            self._workspace_page_indexes[workspace_key] = self.workspace_stack.addWidget(page)
        saved_workspace = str(self.settings.value("active_workspace", "terminal") or "terminal")
        self._switch_workspace(saved_workspace, persist=False)

        # 状态栏
        self.status_bar = QStatusBar()
        # 不透明底（不用 transparent）：否则 showMessage(toast) 时 Qt 隐藏 RX/TX 统计标签、
        # 透明底不擦底会残留旧像素与提示重叠。初始用默认主题窗口色，apply_style 再按实际主题刷新。
        self.status_bar.setStyleSheet(
            f"background: {chrome_for(THEME_DEFAULT)['window_bg']}; color: {COLOR_TEXT_SECONDARY};")
        # 左右边距和上面的 content_layout (20px) 对齐
        self.status_bar.setContentsMargins(20, 0, 20, 0)
        self.status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self.status_bar)
        self.lbl_rx_stat = QLabel("RX 0 B")
        self.lbl_tx_stat = QLabel("TX 0 B")
        self.lbl_state = QLabel(self._t("state_closed"))
        self._set_state_color(opened=False)
        for lbl in (self.lbl_state, self.lbl_rx_stat, self.lbl_tx_stat):
            lbl.setFont(ui_font(10))
        for lbl in (self.lbl_rx_stat, self.lbl_tx_stat):
            lbl.installEventFilter(self)
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.setProperty("tr_tooltip", "stat_jump_tip")

        def _sep():
            """竖线分隔符（无自带色 → 跟随状态栏 text_sec，主题自适应）"""
            s = QLabel("│")
            s.setFont(ui_font(10))
            s.setObjectName("StatusSep")
            return s

        # 三个状态项放左下角 — 用 addWidget 而非 addPermanentWidget
        # (addPermanentWidget 会贴右边；addWidget 走左边，缺点是 toast 出现时会被临时遮盖)
        self.status_bar.addWidget(self.lbl_state)
        self.status_bar.addWidget(_sep())
        self.status_bar.addWidget(self.lbl_rx_stat)
        self.status_bar.addWidget(_sep())
        self.status_bar.addWidget(self.lbl_tx_stat)

        # 选中即算校验和 — 数据区选一段就地出结果，省去「复制 → 开工具箱 → 粘贴」三步。
        # 常用的三种(Modbus/XOR/SUM)直接摆出来，9 种全量放 tooltip：状态栏宽度有限，
        # 塞满会和 toast 打架（曾有过统计文字与 toast 重叠的问题）。无选区时连分隔一起隐藏。
        self._sel_chk_sep = _sep()
        self._sel_chk_sep.hide()
        self.lbl_sel_chk = QLabel("")
        self.lbl_sel_chk.setFont(ui_font(10))
        self.lbl_sel_chk.installEventFilter(self)
        self.lbl_sel_chk.hide()
        self.status_bar.addWidget(self._sel_chk_sep)
        self.status_bar.addWidget(self.lbl_sel_chk)

        # 状态栏右键 → 重置统计
        self.status_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.status_bar.customContextMenuRequested.connect(self._stat_context_menu)

        # 实时记录文件路径 — 右下角(版本号左侧)，仅记录时显示，太长中间省略+悬停看全路径
        self.lbl_log_path = QLabel("")
        self.lbl_log_path.setFont(ui_font(9))
        self.lbl_log_path.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self._log_path_elide_w = 560
        self.status_bar.addPermanentWidget(self.lbl_log_path)
        self._log_path_sep = _sep()
        self._log_path_sep.hide()    # 未记录时隐藏这条分隔，避免悬空
        self.status_bar.addPermanentWidget(self._log_path_sep)

        # 版本号 — 右下角 (addPermanentWidget 走右边)
        self.lbl_version = QLabel(f"v{APP_VERSION}")
        self.lbl_version.setFont(ui_font(10))
        self.lbl_version.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self.lbl_version.installEventFilter(self)   # 有新版时整条变可点徽标（见 eventFilter）
        self.status_bar.addPermanentWidget(self.lbl_version)

        # 自动检查更新：启动延迟静默查一次 + 每 6 小时后台再查；发现新版 → 版本号变可点徽标。
        self._update_badge_version = None    # 非空=已发现的新版本号（徽标态）
        self._auto_checker = None            # 在途的后台 UpdateChecker，防并发重复
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(6 * 60 * 60 * 1000)   # 6 小时
        self._update_timer.timeout.connect(self._auto_update_check)
        if self.settings.value("auto_update_check", True, type=bool):
            self._update_timer.start()
            QTimer.singleShot(5000, self._auto_update_check)   # 启动 5s 后静默查（避开启动高峰）

        # 同步最大行数
        self._on_max_lines_changed()
        self._refresh_stat_labels()   # 状态栏 RX/TX 统计初始文案 + tooltip
        self._align_send_card_cols()  # 发送卡片两行三按钮等列宽对齐（语言切换后还要再调）
        self._apply_terminal_ui(self._terminal_on)   # 启动恢复终端模式时，禁用不生效的格式设置

    def _align_send_card_cols(self):
        """对齐发送卡片两行的三列控件：每列取上下两行 sizeHint().width() 的最大值并 setFixedWidth。
        语言切换后必须重新调用——不同语言下文字自然宽度变化，需重算等列宽。
        col 3 设置 floor=110，保证群组下拉再小也不会被压窄到看不清。"""
        if not hasattr(self, "btn_autoreply"):
            return
        triples = [
            (self.btn_multi,    self.btn_load,       0),
            (self.btn_ms_cycle, self.btn_clear_tx,   0),
            (self.cb_ms_group,  self.btn_autoreply, 110),
        ]
        BIG = 16777215
        for top, bot, floor in triples:
            # 撤回先前 fixed（min=max=N）→ 让 sizeHint 反映新文本的自然宽度
            top.setMinimumWidth(0); top.setMaximumWidth(BIG)
            bot.setMinimumWidth(0); bot.setMaximumWidth(BIG)
            w = max(floor, top.sizeHint().width(), bot.sizeHint().width())
            top.setFixedWidth(w)
            bot.setFixedWidth(w)

    def _fit_data_toolbar(self):
        """数据区顶部工具栏按钮按各自内容宽度显示，避免首次显示 / 语言切换时文字被裁：
        初次 apply_style 时 widget 还没 show、QSS 未完全传到子控件，按钮 sizeHint 偏窄、
        布局按此分配后不再重排 → 文字被挤裁。首次显示(样式已生效)后按 sizeHint 定 minimumWidth。"""
        for name in ("btn_keyword", "btn_filter_hl", "btn_font_dec", "btn_font_inc"):
            b = getattr(self, name, None)
            if b is not None:
                b.setMinimumWidth(0)          # 先撤回旧值，让 sizeHint 反映当前文本自然宽度
                b.setMinimumWidth(b.sizeHint().width())

    def _ensure_on_screen(self):
        """确保窗口的『标题栏』落在某个屏幕工作区内、且够宽能抓得住。多显示器/分辨率变化后，
        恢复的旧位置或默认位置可能落到屏幕外 → 表现为『进程在、窗口看不见』。
        注意：不能只用 intersects()（任意 1px 相交就算可见）——窗口只剩一条边/一个角在屏内时，
        顶部标题栏其实已被推出屏幕、鼠标点不到、拖不动。故这里只认『标题栏顶部有连续一段
        (≥MIN_W 宽)真的落在工作区内』，达不到就搬回主屏左上。"""
        try:
            MIN_W, STRIP_H = 120, 8   # 标题栏至少露出 120px 宽、顶部 8px 高，才算抓得住
            fg = self.frameGeometry()
            title_strip = QRect(fg.left(), fg.top(), fg.width(), STRIP_H)
            for scr in QApplication.screens():
                inter = scr.availableGeometry().intersected(title_strip)
                if inter.width() >= MIN_W and inter.height() >= STRIP_H:
                    return   # 标题栏够抓，无需搬动
            avail = QApplication.primaryScreen().availableGeometry()
            self.move(avail.left() + 60, avail.top() + 60)
        except Exception:
            pass

    def build_sidebar(self):
        return _sidebar.build(self)

    def build_settings_card(self):
        return _settings_card.build(self)

    def _update_net_fields(self):
        """Show/hide connection fields and refresh open-button text."""
        proto = self.cb_proto.currentText()
        engaged = self.conn is not None
        has_targets = (
            hasattr(self, "cb_target") and self.cb_target.count() > 0)
        udp_remote_on = (
            hasattr(self, "sw_udp_remote") and self.sw_udp_remote.isChecked())
        vis = _conn_field_vis(
            proto, engaged,
            has_targets=has_targets, udp_remote_on=udp_remote_on)
        if hasattr(self, "box_ctrl"):
            self.box_ctrl.setVisible(vis["ctrl_box"])
        if hasattr(self, "row_vconn_loop"):
            self.row_vconn_loop.setVisible(vis["vconn_loop"])
        for row in (self.row_port, self.row_baud, self.row_databits,
                    self.row_parity, self.row_stopbits, self.row_flow):
            row.setVisible(vis["serial_rows"])
        self.row_local_ip.setVisible(vis["local_ip"])
        self.row_group.setVisible(vis["group"])
        self.row_local_port.setVisible(vis["local_port"])
        self.row_udp_remote.setVisible(vis["udp_remote"])
        self.row_remote_ip.setVisible(vis["remote_ip"])
        self.row_remote_port.setVisible(vis["remote_port"])
        self.row_target.setVisible(vis["target"])
        self.ed_remote_ip.setEnabled(vis["remote_enabled"])
        self.ed_remote_port.setEnabled(vis["remote_enabled"])
        self.btn_open.setText(self._t(vis["open_btn_key"]))

    def build_data_options_card(self):
        return _data_options_card.build(self)

    def build_send_options_card(self):
        return _send_options_card.build(self)

    def build_receive_card(self):
        return _receive_card.build(self)

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
        act_search = menu.addAction(self._t("search"))
        menu.addSeparator()
        act_copy = menu.addAction(self._t("ctx_copy"))
        act_copy.setEnabled(has_sel)
        act_all = menu.addAction(self._t("ctx_select_all"))
        act_all.setEnabled(has_text)
        menu.addSeparator()
        act_clear = menu.addAction(self._t("clear"))
        act_clear.setEnabled(has_text)
        act_save = menu.addAction(self._t("save"))
        act_save.setEnabled(has_text)
        menu.addSeparator()
        act_export = menu.addAction(self._t("cfg_export"))
        act_import = menu.addAction(self._t("cfg_import"))
        chosen = menu.exec_(global_pos)
        if chosen is act_search:
            self._open_search()
        elif chosen is act_export:
            self.export_config()
        elif chosen is act_import:
            self.import_config()
        elif chosen is act_copy:
            self.txt_recv.copy()
        elif chosen is act_all:
            self.txt_recv.selectAll()
        elif chosen is act_clear:
            self.clear_recv()
        elif chosen is act_save:
            self.save_recv()

    # ----- 数据区：滚动锁定 + 单击行高亮 -----
    def eventFilter(self, obj, event):
        # 这是装在 QApplication 上的全局过滤器：窗口销毁之后（deleteLater 已跑、Python 侧属性
        # 已清）Qt 仍可能回调进来，此时在「半个对象」上跑逻辑会直接 AttributeError 崩掉。
        # _mac_tooltip 是 __init__ 里最早设的那批之一（且早于 installEventFilter），
        # 用它当「实例是否可用」的哨兵：没有就直接放行，别处理。
        if not hasattr(self, "_mac_tooltip"):
            return False
        # 选区校验结果使用应用内卡片，不交给各平台样式差异很大的原生 QToolTip。
        if obj is getattr(self, "lbl_sel_chk", None):
            et = event.type()
            if et == QEvent.ToolTip:
                if self._sel_chk_popup_payload:
                    self._show_sel_checksum_popup()
                elif self._sel_chk_popup is not None:
                    self._sel_chk_popup.hide()
                return True
            if (self._sel_chk_popup is not None and self._sel_chk_popup.isVisible()
                    and et in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.Wheel)):
                self._sel_chk_popup.hide()

        # 右下角版本号徽标：有新版时点一下打开「关于」走更新（无新版则普通标签、点击无反应）
        if obj is getattr(self, "lbl_version", None) and event.type() == QEvent.MouseButtonPress:
            if self._update_badge_version:
                self.open_about()
            return False
        if obj in (getattr(self, "lbl_rx_stat", None), getattr(self, "lbl_tx_stat", None)) \
                and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self._jump_from_io_stats()
                return True
            return False
        # 自动应答按钮：双击 → 翻转总开关（吃掉事件，不让 QPushButton 默认处理再发 clicked）
        if obj is getattr(self, "btn_autoreply", None) and event.type() == QEvent.MouseButtonDblClick:
            self._ar_btn_dbl_clicked()
            return True
        # 发送区 tooltip：用 QToolTip.showText + 超长 msecShowTime + widget rect → 鼠标停留时
        # 不超时消失（默认 10s 会消失），移出 rect 时立刻收起，避免长文案没看完就没了。
        # macOS 不走此分支 → 让下面 _show_mac_tooltip 用 ThemedToolTip 自绘（原生 QToolTip
        # 加 QSS 后背景透明看不清，已知 Mac Qt 问题）
        # 终端模式：发送框不弹「动态字段 / 命令历史」提示（逐字符直发，这些都无关）
        if (getattr(self, "_terminal_on", False) and obj is getattr(self, "txt_send", None)
                and event.type() == QEvent.ToolTip):
            return True
        if (obj is getattr(self, "txt_send", None) and event.type() == QEvent.ToolTip
                and not getattr(self, "_mac_tooltip", False)):
            tip = self.txt_send.toolTip()
            if tip:
                QToolTip.showText(event.globalPos(), tip, self.txt_send,
                                  self.txt_send.rect(), 600000)   # 10 min 上限
            return True
        # 终端模式：发送框作键盘捕获 —— 每个按键即时转字节发出、吃掉事件不让它进发送框累积。
        # 放在 ↑↓ 历史导航之前：终端里方向键要发 ESC 序列(shell 历史/编辑)，而非翻命令历史。
        if (getattr(self, "_terminal_on", False) and obj is getattr(self, "txt_send", None)
                and event.type() == QEvent.KeyPress):
            self._terminal_key(event)
            return True
        # 发送区 ↑↓ 历史导航：仅在 cursor 在首行(↑)/末行(↓)时拦截，否则让 QTextEdit 走默认行内移动
        if obj is getattr(self, "txt_send", None) and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Up:
                cur = self.txt_send.textCursor()
                if cur.blockNumber() == 0:
                    self._send_hist_prev()
                    return True
            elif key == Qt.Key_Down:
                cur = self.txt_send.textCursor()
                if cur.blockNumber() == self.txt_send.document().blockCount() - 1:
                    self._send_hist_next()
                    return True
        # macOS：拦截 ToolTip → 自绘不透明 tooltip（原生加样式后背景透明看不清）
        if self._mac_tooltip:
            et0 = event.type()
            if et0 == QEvent.ToolTip:
                return self._show_mac_tooltip(obj, event)
            # 鼠标点击 / 滚轮 → 收起已显示的自绘 tooltip（贴近原生行为）
            elif (self._tooltip_popup is not None and self._tooltip_popup.isVisible()
                  and et0 in (QEvent.MouseButtonPress, QEvent.Wheel)):
                self._tooltip_popup.hide()

        # 无边框窗口的手动缩放（仅 Linux：Windows 用 nativeEvent、macOS 用原生边框）：
        # 边缘左键按下→抓鼠标记起点，拖动→改几何，松开→释放；悬停→切换缩放光标。
        if self._manual_resize:
            et = event.type()
            if (et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton
                    and not self._resize_edges
                    and (obj is self or (isinstance(obj, QWidget) and self.isAncestorOf(obj)))
                    and self.isActiveWindow() and not self.isMaximized() and self.isVisible()):
                pos = self.mapFromGlobal(event.globalPos())
                if self.rect().contains(pos):
                    edges = self._edges_at(pos)
                    if edges:
                        self._resize_edges = edges
                        self._resize_start_geo = self.geometry()
                        self._resize_start_mouse = event.globalPos()
                        # 应用级覆盖光标：整个拖动期间稳定显示缩放光标，不受 setGeometry 影响
                        QApplication.setOverrideCursor(self._resize_cursor(edges))
                        self.grabMouse()
                        return True
            elif et == QEvent.MouseMove and self._resize_edges:
                if QApplication.mouseButtons() & Qt.LeftButton:
                    self._perform_resize(event.globalPos())
                else:
                    # 没收到释放事件（grab 丢失等）→ 主动收尾，避免覆盖光标卡死
                    self._end_resize()
                return True
            elif et == QEvent.MouseButtonRelease and self._resize_edges:
                self._end_resize()
                return True
            elif (et == QEvent.MouseMove and not self._resize_edges
                    and not (event.buttons() & Qt.LeftButton)
                    and (obj is self or (isinstance(obj, QWidget) and self.isAncestorOf(obj)))):
                # 悬停（未按键）在边缘 → 切换缩放光标，让用户一眼看出可拖拽缩放
                if self.isActiveWindow() and not self.isMaximized():
                    pos = self.mapFromGlobal(event.globalPos())
                    self._update_hover_cursor(
                        self._edges_at(pos) if self.rect().contains(pos) else Qt.Edges())

        if hasattr(self, "txt_recv"):
            # 接收区尺寸变化 → 重定位浮动「回到底部」按钮 + 查找栏
            if obj is self.txt_recv and event.type() == QEvent.Resize:
                self._reposition_to_bottom_btn()
                if hasattr(self, "_search_bar"):
                    self._reposition_search_bar()
            # Ctrl+F 打开查找栏 / Esc 关闭（查找栏可见时）
            elif obj is self.txt_recv and event.type() == QEvent.KeyPress:
                if (event.key() == Qt.Key_F
                        and event.modifiers() & Qt.ControlModifier):
                    self._open_search()
                    return True
                if (event.key() == Qt.Key_Escape and hasattr(self, "_search_bar")
                        and self._search_bar.isVisible()):
                    self._close_search()
                    return True
            elif obj is self.txt_recv.viewport():
                # 右键 → 自定义中文菜单（拦截并消费，阻止 Qt 默认菜单）
                if event.type() == QEvent.ContextMenu:
                    self._recv_context_menu(event.globalPos())
                    return True
                # 左键单击 → 整行高亮
                elif (event.type() == QEvent.MouseButtonPress
                      and event.button() == Qt.LeftButton):
                    self._highlight_recv_line(event.pos())
                # 悬浮到协议高亮字段上 → 弹「规则 · 字段=值」解析气泡（仅普通 HEX 模式 + 协议高亮开启 + 有字段时接管）
                elif (event.type() == QEvent.ToolTip and self._proto_hl_on
                      and self.sw_rx_hex.isChecked() and not self._hexdump_on
                      and not self._numview_on and self._proto_fields):
                    pos = self.txt_recv.cursorForPosition(event.pos()).position()
                    label = self._proto_field_at(pos)
                    if label:
                        QToolTip.showText(event.globalPos(), label, self.txt_recv.viewport())
                    else:
                        QToolTip.hideText()
                    return True
        return super().eventFilter(obj, event)

    def _show_mac_tooltip(self, obj, event):
        """macOS：取目标部件 toolTip 文本，按当前主题不透明显示自绘 tooltip。
        有文本则返回 True 消费事件（阻止透明的原生 tooltip）；无文本交还默认。"""
        text = obj.toolTip() if isinstance(obj, QWidget) else ""
        if not text:
            if self._tooltip_popup is not None:
                self._tooltip_popup.hide()
            return False
        tid = self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT
        t = THEMES.get(tid, THEMES[THEME_DEFAULT])
        # 配色刻意与 QSS 里的 QToolTip 一致（见 apply_style 的 tooltip_bg/fg）：dark 模式
        # 用浅底深字、light 用深底白字——这是有意的反差 tooltip（非写反），改这里要同步 QSS。
        bg = "#F2F2F7" if t.get("mode") == "dark" else "#1C1C1E"
        fg = "#1C1C1E" if t.get("mode") == "dark" else "#FFFFFF"
        if self._tooltip_popup is None:
            self._tooltip_popup = ThemedToolTip()
        self._tooltip_popup.show_text(event.globalPos(), text, bg, fg)
        return True

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

    # ----- 数据区：内嵌浮动查找栏（浏览器 Ctrl+F 风格）-----
    def _build_search_bar(self):
        return _receive_card.build_search_bar(self)

    def _style_search_bar(self):
        """按当前主题给查找栏上色（卡片底 + ghost 按钮）。"""
        c = chrome_for(self._theme_id())
        self._search_bar.setStyleSheet(f"""
            QWidget {{ background-color: {c['card_bg']};
                       border: 1px solid {c['separator']}; border-radius: 8px; }}
            QLineEdit {{ background-color: {c['input_bg']}; color: {c['text']};
                         border: 1px solid {c['separator']}; border-radius: 6px;
                         padding: 3px 6px; }}
            QLabel {{ background: transparent; border: none; color: {c['text_sec']};
                      padding: 0 2px; }}
            QPushButton {{ background-color: {c['ghost_bg']}; color: {c['text']};
                           border: none; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {c['ghost_hover']}; }}
        """)


    def _bookmark_toggle(self):
        """Ctrl+F2: toggle a bookmark on the current data-area line."""
        if not hasattr(self, "txt_recv"):
            return
        cur = self.txt_recv.textCursor()
        block = cur.block()
        if not block.isValid():
            return
        bn = block.blockNumber()
        kept = []
        removed = False
        for c in list(self._bookmarks):
            if c.isNull() or not c.block().isValid():
                continue
            if c.block().blockNumber() == bn:
                removed = True
                continue
            kept.append(c)
        if not removed:
            mark = QTextCursor(block)
            mark.setKeepPositionOnInsert(True)
            kept.append(mark)
            kept.sort(key=lambda c: c.block().blockNumber())
        self._bookmarks = kept
        self._bookmark_idx = -1
        self._refresh_extra_selections(rebuild_search=False)

    def _bookmark_goto(self, delta):
        marks = [c for c in self._bookmarks
                 if not c.isNull() and c.block().isValid()]
        self._bookmarks = marks
        if not marks:
            self.toast(self._t("bm_empty"))
            return
        idx = getattr(self, "_bookmark_idx", -1)
        if idx < 0:
            # Start from nearest mark at/after caret when first navigating.
            bn = self.txt_recv.textCursor().block().blockNumber()
            idx = 0
            for i, c in enumerate(marks):
                if c.block().blockNumber() >= bn:
                    idx = i
                    break
            if delta < 0 and marks[idx].block().blockNumber() > bn:
                idx = (idx - 1) % len(marks)
        else:
            idx = (idx + delta) % len(marks)
        self._bookmark_idx = idx
        mark = marks[idx]
        self.txt_recv.setTextCursor(mark)
        self.txt_recv.ensureCursorVisible()
        self._recv_highlight_line = mark.block().blockNumber()
        self._refresh_extra_selections(rebuild_search=False)

    def _bookmark_next(self):
        self._bookmark_goto(1)

    def _bookmark_prev(self):
        self._bookmark_goto(-1)

    def _open_search(self):
        """打开查找栏：定位 + 聚焦，若数据区有选中文本则填入。"""
        if not hasattr(self, "_search_bar"):
            return
        sel = self.txt_recv.textCursor().selectedText()
        if sel and " " not in sel:
            # block 掉 textChanged：否则 setText 先触发一次 _do_search，下面又显式搜一次（双重全文扫描）
            self.ed_search.blockSignals(True)
            self.ed_search.setText(sel)
            self.ed_search.blockSignals(False)
        self._style_search_bar()
        self._search_bar.show()
        self._reposition_search_bar()
        self.ed_search.setFocus()
        self.ed_search.selectAll()
        if self.ed_search.text():
            self._do_search()

    def _do_search(self, text=None):
        """输入变化时：交给 _refresh_extra_selections 统一收集匹配 + 刷新高亮/计数，再定位首个。"""
        self._search_term = self.ed_search.text()
        self._search_idx = 0 if self._search_term else -1
        self._refresh_extra_selections()   # 搜索段会收集匹配、clamp idx、刷新计数
        if not self._search_term:
            self._search_matches = []
            self._search_match_capped = False
            self._update_search_count()
        if self._search_matches:
            self._goto_match(self._search_idx)

    def _on_search_mode_changed(self):
        data = self.cb_search_mode.currentData()
        self._search_mode = data if data in ("plain", "regex", "hex") else "plain"
        self._do_search()

    def _on_search_case_toggled(self, checked):
        self._search_case = bool(checked)
        self._do_search()

    def _update_search_count(self):
        if not hasattr(self, "lbl_search_cnt"):
            return
        if self._search_matches:
            suffix = "+" if getattr(self, "_search_match_capped", False) else ""
            self.lbl_search_cnt.setText(
                f"{self._search_idx + 1}/{len(self._search_matches)}{suffix}")
        elif self._search_term:
            self.lbl_search_cnt.setText(self._t("search_no_match"))
        else:
            self.lbl_search_cnt.setText("")
        # 计数文本变化会改变查找栏所需宽度，重新自适应 + 定位，避免子控件被压缩重叠
        if hasattr(self, "_search_bar"):
            self._reposition_search_bar()

    def _search_next(self):
        if not self._search_matches:
            return
        self._search_idx = (self._search_idx + 1) % len(self._search_matches)
        self._goto_match(self._search_idx)
        # 导航不改变文档，匹配列表不变：只重新着色当前匹配(内部含计数刷新)，免去全文 doc.find 重建
        self._refresh_extra_selections(rebuild_search=False)

    def _search_prev(self):
        if not self._search_matches:
            return
        self._search_idx = (self._search_idx - 1) % len(self._search_matches)
        self._goto_match(self._search_idx)
        self._refresh_extra_selections(rebuild_search=False)

    def _goto_match(self, idx):
        if not (0 <= idx < len(self._search_matches)):
            return
        self.txt_recv.setTextCursor(self._search_matches[idx])
        self.txt_recv.ensureCursorVisible()

    def _close_search(self):
        if hasattr(self, "_search_bar"):
            self._search_bar.hide()
        self._search_term = ""
        self._search_matches = []
        self._search_idx = -1
        self._search_match_capped = False
        if hasattr(self, "lbl_search_cnt"):
            self.lbl_search_cnt.setText("")
        self._refresh_extra_selections()

    def _reposition_search_bar(self):
        if not hasattr(self, "_search_bar"):
            return
        self._search_bar.adjustSize()
        vp = self.txt_recv.viewport()
        if vp is None:   # 极早期(showEvent 之前)viewport 可能尚未就绪，避免 AttributeError
            return
        bw = self._search_bar.width()
        x = vp.width() - bw - 12
        y = 12
        self._search_bar.move(max(0, x), max(0, y))
        self._search_bar.raise_()

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
        """收到新数据时调用：生效分组有规则 或 搜索栏活跃 → 启动节流定时器重扫"""
        if self._kw_timer.isActive():
            return
        if self._active_rules() or getattr(self, "_search_term", "") or self._proto_hl_on:
            self._kw_timer.start()

    _KW_MAX_SELECTIONS = 2000  # 安全上限，避免像 '00' 这种在 HEX 流里匹配出上万条

    # 协议高亮字段调色板：中饱和色，作背景时配亮度自适应黑/白文字，深浅主题下都清晰、彼此可辨
    _PROTO_PALETTE = ("#4C8DFF", "#34C759", "#FF9F0A", "#FF375F",
                      "#AF52DE", "#5AC8FA", "#FFD60A", "#FF6482")

    def _refresh_extra_selections(self, rebuild_search=True):
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
                                    # 背景模式：按背景亮度自动配黑/白文字，避免深色主题下
                                    # 浅色文字落在亮高亮底上看不清（亮底配黑字、暗底配白字）。
                                    lum = (0.299 * col.red() + 0.587 * col.green()
                                           + 0.114 * col.blue())
                                    sel.format.setForeground(
                                        QColor("#1C1C1E") if lum > 140 else QColor("#FFFFFF"))
                                else:
                                    sel.format.setForeground(col)
                                cur = QTextCursor(doc)
                                cur.setPosition(base + idx)
                                cur.setPosition(base + idx + len(pat), QTextCursor.KeepAnchor)
                                cur.setKeepPositionOnInsert(True)   # 防末尾追加新数据时该选区延伸把新行也高亮
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
            # 过滤：开启时只留命中行；关闭时所有行可见（恢复）。纯装饰块（时间戳/箭头行，无 RX/TX 正文，
            # hexdump+时间戳时独占一块）不参与过滤、始终可见——与 _append_block_data 即时判定一致，
            # 否则重扫会把时间戳行隐藏（先闪后消失）。
            if not filter_on:
                want_vis = True
            else:
                want_vis = block_has_match or not self._block_has_body_role(block)
            if block.isVisible() != want_vis:
                block.setVisible(want_vis)
                dirty = True
            block = block.next()
        if dirty:
            doc.markContentsDirty(0, doc.characterCount())
            self.txt_recv.viewport().update()
        # 1.5 协议字段高亮（HEX 模式；复用帧解析规则；每字段调色板背景 + 亮度自适应文字）。
        # 用接收时存下的 QTextCursor（带 keepPositionOnInsert）直接建选区；文档截满被顶掉的帧
        # 其 cursor 会塌缩成空选区，跳过即可。叠在关键字之上、单击行/搜索高亮之下。
        # 必须限定「普通 HEX 显示」模式：字段区间是按 HEX 渲染算的——切到文本模式位置无意义，
        # HEX 转储是另一种排版（偏移+HEX+ASCII）也不适用，两种都不画（切回普通 HEX 自动重现）。
        if (self._proto_hl_on and self.sw_rx_hex.isChecked()
                and not self._hexdump_on and not self._numview_on and not capped):
            for fld in self._proto_fields:
                cur = fld["cursor"]
                if cur.selectionStart() == cur.selectionEnd():
                    continue
                col = QColor(fld["color"])
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(col)
                lum = 0.299 * col.red() + 0.587 * col.green() + 0.114 * col.blue()
                sel.format.setForeground(QColor("#1C1C1E") if lum > 140 else QColor("#FFFFFF"))
                sel.cursor = cur
                sels.append(sel)
                if len(sels) >= self._KW_MAX_SELECTIONS:
                    break
        # 2. 单击行高亮（放最后 → 画在最上层），中性半透明，不跟文字撞色
        is_dark = self._theme().get("mode") == "dark"
        if self._recv_highlight_line >= 0:
            block = doc.findBlockByNumber(self._recv_highlight_line)
            if block.isValid():
                hl = QColor(255, 255, 255, 46) if is_dark else QColor(0, 0, 0, 38)
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(hl)
                sel.format.setProperty(QTextFormat.FullWidthSelection, True)
                sel.cursor = QTextCursor(block)
                sels.append(sel)
            else:
                self._recv_highlight_line = -1
        # 2.5 Bookmarks (session-scoped; appended before search so search paints on top)
        alive = []
        for cur in self._bookmarks:
            if cur.isNull():
                continue
            block = cur.block()
            if not block.isValid():
                continue
            alive.append(cur)
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(
                QColor(255, 149, 0, 90) if is_dark else QColor(255, 149, 0, 70))
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = QTextCursor(block)
            sels.append(sel)
        self._bookmarks = alive
        if not (0 <= getattr(self, "_bookmark_idx", -1) < len(self._bookmarks)):
            self._bookmark_idx = -1 if not self._bookmarks else min(
                max(0, self._bookmark_idx), len(self._bookmarks) - 1)
        # 3. 搜索高亮（叠加在最上层）：所有匹配淡黄，当前匹配橙色
        if getattr(self, "_search_term", ""):
            if rebuild_search:
                # 文档可能已变(实时接收新数据 / 搜索词变化)：全文 doc.find 重建匹配列表。
                # 导航(上一个/下一个)不改文档，走 rebuild_search=False 跳过这段，避免大文档每次点击都全文扫描。
                self._search_matches = []
                self._search_match_capped = False
                # 三模式（纯文本/正则/HEX）匹配由 search_helper 统一算出字符区间，再建选区光标。
                # hexdump 视图下 HEX 搜索只对 hex 列生效（跳过偏移/ASCII 列误匹配）。
                import search_helper
                doc_text = doc.toPlainText()
                spans = search_helper.find_spans(
                    doc_text, self._search_term,
                    getattr(self, "_search_mode", "plain"),
                    getattr(self, "_search_case", False),
                    hexdump=getattr(self, "_hexdump_on", False))
                # search_helper 使用 Python 码点偏移；QTextCursor 使用 UTF-16 单元偏移。
                # 含 emoji 等非 BMP 字符时，两者会在后续位置分叉。
                spans = search_helper.to_utf16_spans(doc_text, spans)
                if len(spans) > self._KW_MAX_SELECTIONS:
                    self._search_match_capped = True
                    spans = spans[:self._KW_MAX_SELECTIONS]
                for start, end in spans:
                    cur = QTextCursor(doc)
                    cur.setPosition(start)
                    cur.setPosition(end, QTextCursor.KeepAnchor)
                    cur.setKeepPositionOnInsert(True)   # 同上：防选区随末尾插入延伸
                    self._search_matches.append(cur)
                if not (0 <= self._search_idx < len(self._search_matches)):
                    self._search_idx = 0 if self._search_matches else -1
            # 用(已缓存或刚重建的)匹配列表着色：当前匹配橙色、其余淡黄
            for i, cur in enumerate(self._search_matches):
                sel = QTextEdit.ExtraSelection()
                col = QColor("#FFA940") if i == self._search_idx else QColor("#FFE58F")
                sel.format.setBackground(col)
                sel.format.setForeground(QColor("#1C1C1E"))  # 深色文字配亮黄/橙底，深色主题也看得清
                sel.cursor = cur
                sels.append(sel)
            self._update_search_count()
        self.txt_recv.setExtraSelections(sels)

    # ----- 关键字高亮：分组模型（多个命名分组，每组多条规则，单个生效分组）-----
    def _load_keyword_groups(self):
        """Load groups + active index; migrate flat keyword_rules if needed."""
        groups, active, loaded_ok = _kw_load_groups(
            self.settings.value("keyword_groups", ""),
            self.settings.value("keyword_rules", ""),
            self.settings.value("keyword_active", ""),
            self._t("kw_default_group"),
        )
        return groups, active, loaded_ok

    def _save_keyword_groups(self):
        payload, name = _kw_save_fields(self._keyword_groups, self._keyword_active)
        self.settings.setValue("keyword_groups", payload)
        self.settings.setValue("keyword_active", name)
        self.settings.remove("keyword_rules")
        self.settings.sync()

    def _active_rules(self):
        """Rules of the active keyword group; off/OOB -> []."""
        return _kw_active_rules(self._keyword_groups, self._keyword_active)

    def _apply_keyword_rules(self):
        """规则内容变更后：持久化 + 立即重扫高亮（绕过节流，立刻见效）"""
        self._save_keyword_groups()
        self._kw_timer.stop()
        self._refresh_extra_selections()
        self._update_sel_checksum()

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

    # ----- 协议高亮：复用「帧解析」规则，HEX 模式下给收到的帧各字段上色 + 悬浮解析 -----
    def _proto_rules(self):
        """Parse frame_rules with cache; share config with frame dialog."""
        raw = self.settings.value("frame_rules", "") or ""
        if raw == self._proto_rules_raw:
            return self._proto_rules_cache
        rules = binproto.parse_frame_rules(raw)
        self._proto_rules_raw = raw
        self._proto_rules_cache = rules
        return rules

    @staticmethod
    def _proto_field_disp(typ, v):
        """Field value -> tooltip/display text."""
        return binproto.field_disp(typ, v)

    def _add_proto_fields(self, data: bytes, body_pos: int):
        """HEX 模式收到一帧后：按 frame_rules 首条命中规则解析，各字段映射成数据区字符区间存起来，
        供 _refresh_extra_selections 上色、eventFilter 悬浮提示。
        body_pos = 正文「AA BB …」在文档中的起始字符位置，字节 i → 字符 [body_pos+3i, body_pos+3i+2)。"""
        rules = self._proto_rules()
        if not rules:
            return
        rule = binproto.first_matching_rule(rules, data)
        if rule is None:
            return
        doc = self.txt_recv.document()
        n = len(data)
        for fi, (name, off, typ) in enumerate(rule["fields"]):
            size = binproto.field_size(typ)
            if size <= 0 or off < 0 or off + size > n:
                continue
            val = binproto.read_field(data, off, typ)
            if val is None:
                continue
            cur = QTextCursor(doc)
            cur.setPosition(body_pos + 3 * off)
            # 末字节只取 2 个 hex 字符、不含其后空格；区间含字段内部各字节间的空格
            cur.setPosition(body_pos + 3 * (off + size) - 1, QTextCursor.KeepAnchor)
            cur.setKeepPositionOnInsert(True)
            self._proto_fields.append({
                "cursor": cur,
                "color": self._PROTO_PALETTE[fi % len(self._PROTO_PALETTE)],
                "label": "%s · %s=%s" % (rule["header_str"], name,
                                         self._proto_field_disp(typ, val)),
            })

    def _proto_field_at(self, pos: int):
        """文档字符位置 pos 落在哪个已上色字段上 → 返回其 label；都不在 → None（供悬浮提示）。"""
        for fld in self._proto_fields:
            cur = fld["cursor"]
            if cur.selectionStart() <= pos < cur.selectionEnd():
                return fld["label"]
        return None

    def set_proto_highlight(self, on: bool):
        """设置「协议高亮」开关（由「帧解析」对话框的 chk_highlight 驱动）：仅 HEX 模式生效、
        需帧解析里有规则，否则给出提示。关闭时清掉已存字段。落盘 + 立即重画 + 同步对话框勾选态。"""
        on = bool(on)
        self._proto_hl_on = on
        if on:
            if not self.sw_rx_hex.isChecked():
                self.toast(self._t("proto_hl_need_hex"))
            elif not self._proto_rules():
                self.toast(self._t("proto_hl_no_rules"))
        else:
            self._proto_fields.clear()
        self.settings.setValue("proto_highlight", on)
        dlg = getattr(self, "_frame_dlg", None)
        if dlg is not None:
            dlg.sync_highlight()      # 配置切换/别处改动时让对话框勾选态跟上
        self._kw_timer.stop()
        self._refresh_extra_selections()

    @staticmethod
    def _block_has_body_role(block) -> bool:
        """block 内是否有 RX/TX 正文片段（非纯时间戳/箭头等装饰）。"""
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            role = frag.charFormat().property(ROLE_PROP) if frag.isValid() else None
            if role in (ROLE_RX, ROLE_TX):
                return True
            it += 1
        return False

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
        is_dark = theme.get("mode") == "dark"      # ANSI 调色板按主题明暗选那一套
        ranges = []  # (start, end, QColor)，相邻同色自动合并
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    fmt = frag.charFormat()
                    # ANSI 着色的正文按存下的颜色标识重解析：调色板序号跟新主题明暗走
                    # （深色配色留在浅色底上会看不见），设备指定的精确色则原样保留。
                    spec = fmt.property(ANSI_FG_PROP)
                    acol = (ansi.color_of_spec(spec, is_dark, theme["fg"], theme["bg"])
                            if spec else None)
                    role = fmt.property(ROLE_PROP)
                    col = QColor(acol) if acol else role_col.get(role, role_col[None])
                    # 背景色同理：ANSI 的 40-47/100-107 也是调色板序号，不跟着重解析的话，
                    # 深色底选的底色留到浅色底上会和文字糊成一片。
                    bspec = fmt.property(ANSI_BG_PROP)
                    bcol = (ansi.color_of_spec(bspec, is_dark, theme["fg"], theme["bg"])
                            if bspec else None)
                    bg = QColor(bcol) if bcol else None
                    start = frag.position()
                    end = start + frag.length()
                    if (ranges and ranges[-1][1] == start and ranges[-1][2] == col
                            and ranges[-1][3] == bg):
                        ranges[-1] = (ranges[-1][0], end, col, bg)   # 合并相邻同色
                    else:
                        ranges.append((start, end, col, bg))
                it += 1
            block = block.next()
        if not ranges:
            return
        self.txt_recv.setUpdatesEnabled(False)
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        try:
            for start, end, col, bg in ranges:
                cur.setPosition(start)
                cur.setPosition(end, QTextCursor.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setForeground(col)
                if bg is not None:
                    fmt.setBackground(bg)
                cur.mergeCharFormat(fmt)
        finally:
            cur.endEditBlock()
            self.txt_recv.setUpdatesEnabled(True)

    def build_send_card(self):
        return _send_card.build(self)

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
        QComboBox:disabled, QLineEdit:disabled {{
            background-color: {c['card_bg']};
            color: {_mix(c['text_sec'], c['card_bg'], 0.45)};
            border: 1px solid {_mix(c['separator'], c['card_bg'], 0.5)};
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
        QPushButton#GhostBtnSm {{
            background-color: {c['ghost_bg']};
            color: {c['accent']};
            border: 0px;
            border-radius: 7px;
            font-family: 'Segoe UI';
            font-size: 12px;
            font-weight: 500;
            padding: 3px 8px;
            min-height: 16px;
        }}
        QPushButton#GhostBtnSm:hover {{ background-color: {c['ghost_hover']}; }}
        QPushButton#GhostBtnSm:pressed {{ background-color: {c['ghost_pressed']}; }}
        QPushButton#GhostBtn:checked {{ background-color: {c['accent']}; color: white; }}
        QPushButton#GhostBtn[arActive="true"] {{ background-color: {c['accent']}; color: white; }}
        QPushButton#GhostBtn[arActive="true"]:hover {{ background-color: {c['accent_hover']}; }}
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
            background: {c['window_bg']};
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
            padding: 5px 9px;
            font-size: 12px;
            font-weight: 500;
        }}
        QWidget#TitleBar {{
            background-color: {c['window_bg']};
            border-bottom: 1px solid {c['separator']};
        }}
        QPushButton#CtrlBtn, QPushButton#CloseBtn {{
            background-color: transparent;
            color: {c['text']};       /* 自绘 paintEvent 读 palette.ButtonText 取此色 */
            border: 0px;              /* 必须两个 objectName 都覆盖，否则 CloseBtn 留默认边框 */
        }}
        QPushButton#CtrlBtn:hover {{ background-color: {c['title_btn_hover']}; }}
        QPushButton#CloseBtn:hover {{
            background-color: {c['danger']};
            color: #FFFFFF;
        }}
        QPushButton#TbHelpBtn {{
            background-color: transparent; color: {c['text']};
            border: 1px solid transparent; border-radius: 4px;
            padding: 1px 10px; font-family: 'Segoe UI'; font-size: 12px;
        }}
        QPushButton#TbHelpBtn:hover {{ background-color: {c['title_combo_hover']};
                                       border: 1px solid {c['separator']}; }}

        QWidget#WorkbenchBar {{
            background-color: {c['window_bg']};
            border-bottom: 1px solid {c['separator']};
        }}
        QLabel#WorkbenchLabel {{
            color: {c['text_sec']};
            background: transparent;
            padding-right: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#WorkbenchBtn {{
            background-color: transparent;
            color: {c['text']};
            border: 1px solid transparent;
            border-radius: 6px;
            padding: 2px 14px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton#WorkbenchBtn:hover {{
            background-color: {c['title_combo_hover']};
            border-color: {c['separator']};
        }}
        QPushButton#WorkbenchBtn:pressed {{
            background-color: {c['accent']};
            color: #FFFFFF;
        }}
        QPushButton#WorkbenchBtn[active="true"] {{
            background-color: {c['accent']}; color: #FFFFFF; font-weight: 600;
        }}
        QWidget#WorkspaceHost, QWidget#WorkspacePage {{ background-color: {c['window_bg']}; }}
        QLabel#WorkspacePageTitle {{
            color: {c['text']}; background: transparent;
            font-family: 'Segoe UI'; font-size: 22px; font-weight: 700;
        }}
        QLabel#WorkspacePageSubtitle {{
            color: {c['text_sec']}; background: transparent;
            font-family: 'Segoe UI'; font-size: 12px;
        }}
        QFrame#WorkspaceToolCard {{
            background-color: {c['card_bg']}; border: 1px solid {c['separator']};
            border-radius: 12px;
        }}
        QFrame#WorkspaceTemplatePanel {{
            background-color: {_mix(c['card_bg'], c['accent'], 0.05)};
            border: 1px solid {_mix(c['separator'], c['accent'], 0.25)};
            border-radius: 12px;
        }}
        QLabel#WorkspaceTemplatePreview {{
            color: {c['text_sec']}; background: transparent; border: 0px;
            font-family: 'Segoe UI'; font-size: 11px;
        }}
        QFrame#WorkspaceToolCard:hover {{
            background-color: {c['title_combo_hover']}; border-color: {c['accent']};
        }}
        QLabel#WorkspaceToolIcon {{
            background-color: {_mix(c['card_bg'], c['accent'], 0.14)};
            color: {c['accent']}; border: 0px; border-radius: 10px;
            font-family: 'Segoe UI Symbol', 'Segoe UI';
            font-size: 17px; font-weight: 700;
        }}
        QLabel#WorkspaceToolTitle {{
            color: {c['text']}; background: transparent; border: 0px;
            font-family: 'Segoe UI'; font-size: 14px; font-weight: 600;
        }}
        QLabel#WorkspaceStatusBadge {{
            background-color: {_mix(c['card_bg'], c['text_sec'], 0.12)};
            color: {c['text_sec']}; border: 0px; border-radius: 8px;
            padding: 2px 8px; font-family: 'Segoe UI'; font-size: 10px;
        }}
        QLabel#WorkspaceStatusBadge[active="true"] {{
            background-color: {_mix(c['card_bg'], '#34C759', 0.16)};
            color: #28A745; font-weight: 600;
        }}
        QPushButton#WorkspaceOpenBtn {{
            background-color: {c['accent']}; color: #FFFFFF; border: 0px;
            border-radius: 6px; padding: 2px 14px;
            font-family: 'Segoe UI'; font-size: 12px; font-weight: 600;
        }}
        QPushButton#WorkspaceOpenBtn:hover {{ background-color: {c['accent_hover']}; }}
        QFrame#WorkbenchSeparator {{
            color: {c['separator']};
            background-color: {c['separator']};
            max-width: 1px;
            margin: 4px 6px;
        }}
        QPushButton#ProjectBtn {{
            background-color: transparent;
            color: {c['text']};
            border: 1px solid {c['separator']};
            border-radius: 6px;
            padding: 2px 10px;
            font-size: 12px;
        }}
        QPushButton#ProjectBtn:hover {{
            background-color: {c['title_combo_hover']};
            border-color: {c['accent']};
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
        self.setStyleSheet(localize_qss(qss))
        # 强制所有子 widget 重新评估样式 —— Qt 有时 setStyleSheet 后旧子组件保留缓存样式
        # 典型表现：重启后从设置里恢复主题，title bar 变了但中间数据区还是旧色
        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)

        # 下拉弹出容器(QComboBoxPrivateContainer)是独立顶层窗口，其底色走系统调色板默认白，
        # 深色主题下圆角/边框处会露白边。这里把每个下拉的弹出容器背景刷成下拉色，彻底消除白边。
        for combo in self.findChildren(QComboBox):
            _style_one_combo_popup(combo, c)

    # ----- 连接 打开/关闭 -----
    def toggle_conn(self):
        if self.conn is not None:
            self._user_closing = True       # 主动断开：跳过自动重连
            self._cancel_reconnect()        # 也取消已排队的重连
            self._serial_reconnect_cfg = None
            self.close_conn()
            self._user_closing = False
        else:
            self._cancel_reconnect()        # 手动重新打开 → 撤销可能在排队的重连
            self._reconnect_attempts = 0
            self._serial_reconnect_cfg = None
            self.open_conn()

    @staticmethod
    def _bytes_to_hex(data):
        """Bytes -> 'AA BB CC' (no trailing space)."""
        return _view_bytes_to_hex(data)

    @staticmethod
    def _format_hexdump(data, per=16):
        """Bytes -> hexdump lines (offset + HEX + |ASCII|)."""
        return _view_format_hexdump(data, per)

    def _hexdump_block(self, data):
        """转储串；时间戳/箭头开启时前置 \\n 让它们单独成行 —— 否则首行被时间戳推右、续行(00000010…)
        在行首，多行帧纵向错位。时间戳关时转储各行本就从行首起、无需前置。"""
        try:
            per = int(self.cb_hexdump_width.currentText())
        except (ValueError, AttributeError):
            per = 16
        dump = self._format_hexdump(data, per)
        return _view_leading_nl(dump, self.sw_show_timestamp.isChecked())

    def _on_hexdump_toggled(self, on):
        if on and getattr(self, "_numview_on", False):
            self._flush_numview_carries()
        self._hexdump_on = bool(on)
        self.settings.setValue("hexdump_view", self._hexdump_on)
        self._refresh_hex_toggle_state()   # hexdump 接管 HEX 显示 → 灰掉 HEX 显示开关，明确优先级
        self._reset_recv_state()   # 切视图 → 下一数据块从干净状态起（新 block、重置增量解码；含清 _proto_fields）
        # 立即重画：_reset_recv_state 已清 _proto_fields，但旧的 ExtraSelection 还挂在视图上，
        # 不刷新则旧协议色块残留到下一包才消失（协议高亮仅普通 HEX、转储不适用）
        self._kw_timer.stop()
        self._refresh_extra_selections()

    def _on_hexdump_width_changed(self, *_):
        self.settings.setValue("hexdump_width", self.cb_hexdump_width.currentText())
        self._reset_recv_state()   # 换每行字节数 → 下一块按新宽度起新 block（不重排已有内容）

    # ----- 数值视图（字节流按 u8/i16/f32… 解读成数值序列）-----
    def _numview_spec(self):
        """当前选中的 (类型, 字节序)；下拉尚未建好或数据异常时回退 ('u16','le')。"""
        cb = getattr(self, "cb_numview_type", None)
        if cb is None:
            return "u16", "le"
        spec = cb.currentData()
        if not (isinstance(spec, tuple) and len(spec) == 2):
            return "u16", "le"
        return spec

    def _numview_block(self, data, carry=True, source=None):
        """字节 → 数值序列块。carry=True 时把凑不满一个数的尾部字节留到下一包（RX 连续流）；
        TCP Server 按 source 分流，避免不同客户端的碎片拼成同一个数。TX 是一次成帧、与 RX 流无关，
        用 carry=False 独立成块，免得两条方向互相污染余数。"""
        typ, endian = self._numview_spec()
        if carry:
            data = self._numview_carries.get(source, b"") + bytes(data)
        text, rest = convert.format_numeric(data, typ, endian)
        if carry:
            if rest:
                self._numview_carries[source] = rest
            else:
                self._numview_carries.pop(source, None)
        elif rest:
            # TX 与 UDP 数据报是独立边界，余数既不能拼到下一帧，也不能静默消失。
            tail = self._t("numview_tail", data=rest.hex(" ").upper())
            text = text + ("\n" if text else "") + tail
        # 同 _hexdump_block：多行块在时间戳/箭头开启时前置换行，避免首行被推右、续行纵向错位
        return _view_leading_nl(text, self.sw_show_timestamp.isChecked())

    def _flush_numview_carries(self, sources=None):
        """连续流结束/换口径时，把未凑整的 RX 尾字节明确显示出来，不让它们随 reset 静默消失。"""
        carries = getattr(self, "_numview_carries", {})
        wanted = set(carries) if sources is None else set(sources)
        tails = []
        for source in list(carries):
            if source in wanted:
                rest = carries.pop(source)
                if rest:
                    tails.append(rest)
        if not tails or not hasattr(self, "txt_recv"):
            return
        for rest in tails:
            text = self._t("numview_tail", data=rest.hex(" ").upper())
            self._append_block_data(text, direction="rx", force_new_block=True,
                                    view_mode=VIEW_NUMERIC)
            self._last_direction = "rx"

    def _on_numview_toggled(self, on):
        if not on:
            self._flush_numview_carries()
        self._numview_on = bool(on)
        self.settings.setValue("numview", self._numview_on)
        self._refresh_hex_toggle_state()   # 数值视图接管显示 → 灰掉 HEX 显示 / HEX 转储，明确优先级
        self._reset_recv_state()           # 切视图 → 下一数据块从干净状态起（含清余数、清协议字段）
        # 同 _on_hexdump_toggled：_reset_recv_state 清了 _proto_fields，但旧 ExtraSelection 还挂在
        # 视图上，不刷新则旧协议色块残留到下一包才消失（协议高亮仅普通 HEX 模式适用）
        self._kw_timer.stop()
        self._refresh_extra_selections()
        self._update_sel_checksum()        # 视图变了 → 选区字节的解读方式也变，重算校验和

    def _view_mode_of_state(self):
        """Toggle state -> view-mode combo id (dump>num>hex>text)."""
        return _view_mode_of_state(
            self._hexdump_on, self._numview_on, self.sw_rx_hex.isChecked())

    def _sync_view_mode_combo(self):
        """状态 → 下拉（导入配置 / 加载会话后调）。只改显示，不再回头触发切换逻辑。"""
        cb = getattr(self, "cb_view_mode", None)
        if cb is None:
            return
        idx = max(0, cb.findData(self._view_mode_of_state()))
        if idx != cb.currentIndex():
            cb.blockSignals(True)
            cb.setCurrentIndex(idx)
            cb.blockSignals(False)
        self._sync_view_extra()

    def _sync_view_extra(self):
        """附属参数页跟着当前模式换（转储→每行字节数，数值→类型，其余→空页）。"""
        stack = getattr(self, "_view_extra", None)
        if stack is None:
            return
        if getattr(self, "_terminal_on", False):
            # 终端模式绕过所有渲染选项，但 ANSI 着色对它仍然生效 → 强制显示那一页，
            # 免得「显示方式」恰好停在 HEX 时开关被藏起来、终端里想关颜色却找不到。
            stack.setCurrentIndex(0)
            return
        mode = self.cb_view_mode.currentData()
        stack.setCurrentIndex(_view_extra_index(mode, terminal_on=False))

    def _on_view_mode_changed(self, *_):
        """下拉 → 状态开关。先关掉不再生效的模式再开新的，避免两个「接管数据区」的
        模式短暂同时为真；各自的 toggled 处理器会做复位/重画，这里不重复那些活。"""
        mode = self.cb_view_mode.currentData() or "text"
        if mode != "dump" and self.sw_hexdump.isChecked():
            self.sw_hexdump.setChecked(False, animate=False)
        if mode != "num" and self.sw_numview.isChecked():
            self.sw_numview.setChecked(False, animate=False)
        self.sw_rx_hex.setChecked(mode == "hex", animate=False)
        if mode == "dump":
            self.sw_hexdump.setChecked(True, animate=False)
        elif mode == "num":
            self.sw_numview.setChecked(True, animate=False)
        self._sync_view_extra()

    def _on_ansi_toggled(self, on):
        self._ansi_on = bool(on)
        self.settings.setValue("ansi_color", self._ansi_on)
        # 切换即从干净状态起：残留的半个转义序列 / 上一段颜色对新模式都没意义
        self._ansi_state = None
        self._ansi_pending = ""
        self._term_sgr = None      # 终端那份也清，免得重新打开时旧颜色复活
        self._term_streams = {}
        self._reset_recv_state()

    def _on_numview_type_changed(self, *_):
        self._flush_numview_carries()
        idx = self.cb_numview_type.currentIndex()
        self.settings.setValue("numview_type", idx)
        self._reset_recv_state()   # 换类型 → 余数按旧宽度攒的已无意义，清掉从下一包重新对齐

    # ----- 选中即算校验和 -----
    # 选区字节数上限。定这个数不是防内存，是防卡界面：9 种算法里多数是纯 Python 逐位
    # 循环，整条链路跑在 GUI 线程上（120ms 节流后）。实测本机：提取 64 KB 只要 ~70ms，
    # 但对它算完 9 种要 ~280ms —— 瓶颈在计算不在提取。按 16 KB 卡到 ~85ms，仍远大于
    # 任何真实帧长（这功能是给「选中一帧看 CRC」用的，不是给大文件算校验的，
    # 那是工具箱的活）。改大前先按上面的数据估一下停顿。
    _SEL_CHK_MAX = 16 * 1024
    # 状态栏直出的三种（覆盖绝大多数嵌入式协议），其余 6 种在 tooltip 里
    _SEL_CHK_BRIEF = ((5, "Modbus"), (3, "XOR"), (1, "SUM"))

    def _selected_hex_bytes(self, cursor, limit=None):
        """按正文 fragment 保存的实际视图类型提取选中的 HEX token。

        返回 bytes；若选区触及文本/数值/终端等不可无损还原的正文，返回 None 并整段拒算。
        视图类型跟内容一起存，所以切换视图后选择历史数据仍按它当时的格式解析。

        limit：取够这么多字节就停。本函数在 120ms 节流后跑在 GUI 线程上，而「最大行数」
        可配到 100 万行；Ctrl+A 全选时逐块扫正则实测 1 万行要 ~190ms，按上限推是十几秒的
        界面卡死。超过上限上层本就只会拒算、不会用这些字节，没必要把整篇文档扫完。
        """
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        if start >= end:
            return b""
        block = self.txt_recv.document().findBlock(start)
        out = bytearray()
        while block.isValid() and block.position() < end:
            line = block.text()
            block_pos = block.position()
            lo = max(0, start - block_pos)
            hi = min(len(line), end - block_pos)
            views = set()
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    frag_start = frag.position()
                    frag_end = frag_start + frag.length()
                    if frag_end > start and frag_start < end:
                        view = frag.charFormat().property(VIEW_PROP)
                        if view is not None:
                            views.add(view)
                it += 1
            if views - {VIEW_HEX, VIEW_HEXDUMP}:
                return None
            if len(views) > 1:   # 同一行格式损坏/混合时不猜
                return None
            if views:
                view = next(iter(views))
                out.extend(convert.hex_line_selection_to_bytes(
                    line, lo, hi, hexdump=(view == VIEW_HEXDUMP),
                    limit=None if limit is None else limit - len(out)))
            if limit is not None and len(out) > limit:
                break      # 已确定超限，多扫无益（返回值只用于 len > limit 的判定）
            block = block.next()
        return bytes(out)

    def _sel_chk_popup_content(self, data: bytes):
        """生成卡片内容；名称复用工具箱的 CHECKSUM_KEYS，避免同一算法两套叫法。"""
        rows = [
            (self._t(CHECKSUM_KEYS[idx]),
             self.compute_checksum(data, idx).hex(" ").upper())
            for idx in range(1, len(CHECKSUM_KEYS))
        ]
        return (
            self._t("sel_chk_popup_title"),
            self._t("sel_chk_popup_meta", n=self.fmt_bytes(len(data)), m=len(rows)),
            rows,
        )

    def _show_sel_checksum_popup(self):
        # isVisible() 在主窗口尚未 show 的离屏测试中也会返回 False；这里只需确认标签
        # 自身没有被业务逻辑隐藏，实际悬停事件只可能来自已显示窗口。
        if not self._sel_chk_popup_payload or self.lbl_sel_chk.isHidden():
            return
        if self._sel_chk_popup is None:
            self._sel_chk_popup = ChecksumPopup()
        title, meta, rows = self._sel_chk_popup_payload
        tid = self._theme_id()
        self._sel_chk_popup.set_content(title, meta, rows, chrome_for(tid))
        self._sel_chk_popup.show_for(self.lbl_sel_chk)

    def _hide_sel_checksum(self):
        """收起状态栏的校验和显示（连同它左边那条分隔，免得悬空）。"""
        self.lbl_sel_chk.setText("")
        set_tooltip(self.lbl_sel_chk, "")
        self._sel_chk_popup_payload = None
        if self._sel_chk_popup is not None:
            self._sel_chk_popup.hide()
        self.lbl_sel_chk.hide()
        self._sel_chk_sep.hide()

    def _update_sel_checksum(self):
        """数据区选区变化 → 状态栏就地显示这段字节的校验和（节流后调用）。"""
        if not hasattr(self, "lbl_sel_chk"):
            return
        cur = self.txt_recv.textCursor()
        if not cur.hasSelection():
            self._hide_sel_checksum()
            return
        data = self._selected_hex_bytes(cur, limit=self._SEL_CHK_MAX)
        if data is None or not data:
            # 选中的全是装饰（时间戳/箭头/纯文本），一个字节也解析不出 → 什么都不显示，
            # 而不是显示"0 字节"的空结果
            self._hide_sel_checksum()
            return

        if len(data) > self._SEL_CHK_MAX:
            # 超限只说明未算，不报字节数 —— 提取在够数时就提前收工了，len(data) 只是
            # 「超过上限」的证据、不是选区实际大小，拿它当数字报出来会是假精确。
            # 也不截断一部分去算：那会给出一个"看着像真的"的错值，比不给结果危险得多。
            self.lbl_sel_chk.setText(self._t("sel_chk_too_big", n=self._SEL_CHK_MAX // 1024))
            set_tooltip(self.lbl_sel_chk, "")
            self._sel_chk_popup_payload = None
            if self._sel_chk_popup is not None:
                self._sel_chk_popup.hide()
        else:
            head = "%s %s" % (self._t("sel_chk"), self.fmt_bytes(len(data)))
            brief = ["%s %s" % (name, self.compute_checksum(data, idx).hex(" ").upper())
                     for idx, name in self._SEL_CHK_BRIEF]
            self.lbl_sel_chk.setText("%s · %s" % (head, "  ".join(brief)))
            self._sel_chk_popup_payload = self._sel_chk_popup_content(data)
            # 非空 tooltip 属性让 Qt 按系统悬停延时派发 QEvent.ToolTip；事件过滤器会
            # 消费事件并显示 ChecksumPopup，因此这个纯文本不会交给原生提示框绘制。
            set_tooltip(self.lbl_sel_chk, self._sel_chk_popup_payload[0])
            if self._sel_chk_popup is not None and self._sel_chk_popup.isVisible():
                self._show_sel_checksum_popup()
        self.lbl_sel_chk.show()
        self._sel_chk_sep.show()

    def _refresh_hex_toggle_state(self):
        """显示方式相关控件的可用性 + 下拉与状态的同步。

        四种渲染方式合成一个下拉后，互斥由类型天然保证（不再需要开关之间互相灰掉）。
        这里只剩两件事：终端模式下整组不可配（终端是纯字节流，绕过所有渲染选项）；
        ANSI 着色仅「按文本渲染」的两种情形有效（普通文本 与 终端模式），其余灰掉，
        避免开了没反应的困惑。"""
        term = getattr(self, "_terminal_on", False)
        num = getattr(self, "_numview_on", False)
        if hasattr(self, "cb_view_mode"):
            self.cb_view_mode.setEnabled(not term)
            self._sync_view_mode_combo()
        if hasattr(self, "cb_hexdump_width"):
            self.cb_hexdump_width.setEnabled(not term)
        if hasattr(self, "cb_numview_type"):
            self.cb_numview_type.setEnabled(not term)
        # ANSI 着色只在它那一页露面（文本 / 终端），不再需要「显示但灰着」这种状态

    @staticmethod
    def _parse_port(text):
        """Parse TCP/UDP port -> int 1..65535, else None."""
        return _conn_parse_port(text)

    def _conn_config_signature(self, proto=None):
        """Current UI connection signature (detect config overwrite)."""
        proto = proto or self.cb_proto.currentText()
        if proto == PROTO_SERIAL:
            try:
                baud = int(self.cb_baud.currentText())
            except (ValueError, TypeError):
                baud = None
            return _conn_serial_sig(
                proto, self.cb_port.currentData(), baud,
                self.cb_databits.currentText(), self.cb_parity.currentText(),
                self.cb_stopbits.currentText(), self.cb_flow.currentText())
        if proto == PROTO_TCP_CLIENT:
            return _conn_tcp_sig(
                proto, self.ed_remote_ip.text().strip(),
                self._parse_port(self.ed_remote_port.text()))
        return _conn_proto_sig(proto)

    def open_conn(self, reconnect_cfg=None):
        """Open the connection described by the current UI (or reconnect_cfg)."""
        proto = reconnect_cfg[0] if reconnect_cfg else self.cb_proto.currentText()
        if proto == PROTO_SERIAL:
            port = reconnect_cfg[1] if reconnect_cfg else self.cb_port.currentData()
            baud_text = reconnect_cfg[2] if reconnect_cfg else self.cb_baud.currentText()
            fields = {"port": port, "baud": baud_text}
        elif proto == PROTO_VIRTUAL:
            fields = {}
        elif proto == PROTO_TCP_CLIENT:
            fields = {
                "remote_ip": self.ed_remote_ip.text(),
                "remote_port": self.ed_remote_port.text(),
            }
        elif proto == PROTO_UDP_MULTICAST:
            fields = {
                "local_ip": self.cb_local_ip.currentText(),
                "local_port": self.ed_local_port.text(),
                "group": self.ed_group.text(),
            }
        elif proto == PROTO_TCP_SERVER:
            fields = {
                "local_ip": self.cb_local_ip.currentText(),
                "local_port": self.ed_local_port.text(),
            }
        else:  # UDP
            fields = {
                "local_ip": self.cb_local_ip.currentText(),
                "local_port": self.ed_local_port.text(),
                "use_remote": self.sw_udp_remote.isChecked(),
                "remote_ip": self.ed_remote_ip.text(),
                "remote_port": self.ed_remote_port.text(),
            }
        checked = _conn_validate_open(
            proto, fields,
            is_valid_ip=is_valid_ip,
            is_local_ipv4=is_local_ipv4,
            is_multicast_ipv4=is_multicast_ipv4)
        if not checked.get("ok"):
            dlg = checked.get("dialog")
            if dlg:
                self._info_dlg(self._t(dlg[0]), self._t(dlg[1]), is_error=True)
            else:
                self.toast(self._t(checked.get("toast", "err_bad_port")), error=True)
            return
        if proto == PROTO_SERIAL:
            databits = reconnect_cfg[3] if reconnect_cfg else self.cb_databits.currentText()
            parity = reconnect_cfg[4] if reconnect_cfg else self.cb_parity.currentText()
            stopbits = reconnect_cfg[5] if reconnect_cfg else self.cb_stopbits.currentText()
            flow = (reconnect_cfg[6] if reconnect_cfg and len(reconnect_cfg) > 6
                    else self.cb_flow.currentText())
            sp = _resolve_serial_params(databits, parity, stopbits, flow)
            conn = SerialConn(
                checked["port"], checked["baud"], sp["bytesize"],
                sp["parity"], sp["stopbits"], flow=sp["flow"])
        elif proto == PROTO_VIRTUAL:
            conn = VirtualConn(loopback=self.sw_vconn_loop.isChecked())
        elif proto == PROTO_TCP_SERVER:
            conn = TcpServerConn(checked["local_ip"], checked["port"])
        elif proto == PROTO_TCP_CLIENT:
            conn = TcpClientConn(checked["ip"], checked["port"])
        elif proto == PROTO_UDP_MULTICAST:
            conn = UdpGroupConn(checked["local_ip"], checked["group"], checked["port"])
        else:
            conn = UdpConn(
                checked["local_ip"], checked["lport"],
                checked["rip"], checked["rport"])

        # TCP Server 额外携带来源客户端 key，让协议自动应答能精确回给请求方；
        # 其余连接仍走原有单参数信号。
        if hasattr(conn, "data_received_from"):
            conn.data_received_from.connect(self.on_data_received)
        else:
            conn.data_received.connect(self.on_data_received)
        conn.error_occurred.connect(self._on_conn_error)
        conn.state_changed.connect(self._on_conn_state_changed)
        # clients_changed / peer_changed 是网络连接专有信号；SerialConn 没有，按需连接
        if hasattr(conn, "clients_changed"):
            conn.clients_changed.connect(self._on_clients_changed)
        if hasattr(conn, "peer_changed"):
            conn.peer_changed.connect(self._on_udp_peer_changed)

        # 先赋值再 open()：TCP Server / UDP / 组播的 open() 会**同步**发出 state_changed(True)，
        # 此时 self.conn 必须已指向 conn，否则 _on_conn_state_changed 看到 None、状态栏先跑一次「未连接」
        self._conn_proto = proto
        self._conn_cfg = tuple(reconnect_cfg) if reconnect_cfg else self._conn_config_signature(proto)
        self._mbm_guard_until = 0.0   # 新物理会话不继承旧连接的迟到响应隔离期
        self.conn = conn
        if not conn.open():   # 同步失败(端口占用/绑定失败)：error_occurred 已触发 _on_conn_error → close_conn 复位
            if self.conn is conn:   # 兜底：万一 _on_conn_error 未清理，这里补清
                self.conn = None
                self._conn_proto = None
                self._conn_cfg = None
                conn.deleteLater()
            return

        self.btn_open.setProperty("state", "open")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        self.set_settings_enabled(False)
        self._update_net_fields()
        self._update_conn_status()
        # 记录已连接的串口设备名 + 复位掉线去抖计数，供后台扫描检测物理移除
        self._serial_device = port if proto == PROTO_SERIAL else None
        self._serial_missing_count = 0
        if proto == PROTO_SERIAL:
            self._select_serial_device(port)  # 重连可能绕过当前下拉选择，界面必须显示实际打开的端口
            self._serial_reconnect_cfg = None
            self._apply_ctrl_lines_on_open()   # 应用持久化 DTR/RTS + 启动状态线轮询

    def _on_vconn_loop_toggled(self, on):
        """回环开关：连接期间也能随时切（虚拟连接无需重开），并刷新状态栏文案。"""
        self.settings.setValue("vconn_loopback", bool(on))
        if isinstance(self.conn, VirtualConn):
            self.conn.loopback = bool(on)
            self._update_conn_status()

    def _apply_ctrl_lines_on_open(self):
        """串口连上：按持久化的 DTR/RTS 状态应用到硬件 + 同步开关 + 启动输入状态线轮询。"""
        dtr = str(self.settings.value("serial_dtr", "true")).lower() in ("1", "true")
        rts = str(self.settings.value("serial_rts", "true")).lower() in ("1", "true")
        for sw, val in ((self.sw_dtr, dtr), (self.sw_rts, rts)):
            sw.blockSignals(True); sw.setChecked(val); sw.blockSignals(False)
        self.conn.set_dtr(dtr)
        self.conn.set_rts(rts)
        self._poll_ctrl_lines()
        self._ctrl_poll_timer.start()

    def _on_dtr_toggled(self, on):
        self.settings.setValue("serial_dtr", bool(on))
        if self._conn_proto == PROTO_SERIAL and self.conn is not None:
            self.conn.set_dtr(on)

    def _on_rts_toggled(self, on):
        self.settings.setValue("serial_rts", bool(on))
        if self._conn_proto == PROTO_SERIAL and self.conn is not None:
            self.conn.set_rts(on)

    def _on_flow_changed(self, *_):
        # RTS/CTS 硬件流控时 RTS 由硬件自动管理，禁用手动 RTS 开关避免误解（软件 / 无流控时可手动控制）
        if hasattr(self, "sw_rts"):
            self.sw_rts.setEnabled(self.cb_flow.currentText() != "RTS/CTS")

    def _apply_serial_params_live(self, *_):
        """串口已连接时改 波特率/数据位/校验位/停止位/流控 → 直接应用到活动连接，不断开。

        只挂在 activated / editingFinished 这类「用户亲手操作」的信号上——切配置、导入配置
        的程序化 setCurrentText 不会触发它们，绝不会把别的配置的参数悄悄打进正在跑的串口。
        应用成功后同步 _conn_cfg（连接签名真源）：Modbus 主机的 RTU t3.5 静默窗、就绪门禁、
        掉线自动重连 全都读它，不同步的话主机轮询会立即因「UI 与实际连接不一致」暂停。
        """
        if (getattr(self, "_conn_proto", None) != PROTO_SERIAL
                or self.conn is None or not getattr(self.conn, "is_open", False)):
            return
        baud = _conn_parse_baud(self.cb_baud.currentText())
        if baud is None:
            self.toast(self._t("err_bad_baud"), error=True)
            return
        sig = self._conn_config_signature(PROTO_SERIAL)
        if sig == self._conn_cfg:
            return      # editingFinished 失焦也会来一次；值没变就不重复应用、不重复提示
        flow = self.cb_flow.currentText()
        sp = _resolve_serial_params(
            self.cb_databits.currentText(), self.cb_parity.currentText(),
            self.cb_stopbits.currentText(), flow)
        ok = self.conn.apply_params(
            baud=baud,
            bytesize=sp["bytesize"],
            parity=sp["parity"],
            stopbits=sp["stopbits"],
            flow=sp["flow"])
        if not ok:
            return      # 失败已由 conn 的 error_occurred 走统一错误提示/掉线路径
        self._conn_cfg = sig
        # 流控切到 RTS/CTS 后手动 RTS 开关要禁用（硬件接管）。目前 _on_flow_changed 靠
        # currentIndexChanged 与本函数的 activated 同帧触发而"顺带"生效，是巧合耦合；
        # 显式调一次，任何绕过 UI 信号直接调本函数的路径（脚本/快捷键）也能正确联动。
        self._on_flow_changed()
        # 状态栏「● COM3 @ 115200」跟着新波特率刷新
        self.lbl_state.setText(f"● {sig[1]} @ {baud}")
        parity_ch = self.cb_parity.currentText()[0]     # None→N / Even→E / Odd→O / Mark→M / Space→S
        self.toast(self._t("live_params_applied",
                           p=f"{baud} {self.cb_databits.currentText()}"
                             f"{parity_ch}{self.cb_stopbits.currentText()}"))

    def _pulse_reset(self):
        """DTR 拉低 ~120ms 再恢复到开关状态，触发 Arduino 等的自动复位电路（不同板子复位方式或异，可用 DTR/RTS 手动控制）。"""
        if self._conn_proto != PROTO_SERIAL or self.conn is None:
            return
        self.conn.set_dtr(False)
        # 用挂在 self 上的单次定时器（非 QTimer.singleShot）：脉冲窗口内若关窗/断连，定时器随 self 销毁、
        # 不会在已析构的 C++ 对象上回调；懒建复用。
        if self._reset_timer is None:
            self._reset_timer = QTimer(self)
            self._reset_timer.setSingleShot(True)
            self._reset_timer.timeout.connect(self._pulse_reset_release)
        self._reset_timer.start(120)

    def _pulse_reset_release(self):
        # 恢复 DTR 到「开关当前状态」而非硬置高：脉冲 120ms 内用户若手动改过 DTR，开关已反映其意图，尊重之、不覆盖。
        if self._conn_proto == PROTO_SERIAL and self.conn is not None:
            self.conn.set_dtr(self.sw_dtr.isChecked())

    def _send_break(self):
        """发送 Break 信号（TX 线拉低约 250ms）：常用于唤醒 / 触发进入 bootloader 等。仅串口 + 已连接。"""
        if self._conn_proto == PROTO_SERIAL and self.conn is not None:
            self.conn.send_break()

    def _poll_ctrl_lines(self):
        """轮询串口输入状态线，刷新 CTS/DSR/DCD/RI 状态灯。"""
        if self._conn_proto != PROTO_SERIAL or self.conn is None:
            return
        lines = self.conn.read_lines()
        for k, dot in self._ctrl_dots.items():
            self._set_dot(dot, lines.get(k))

    def _set_dot(self, dot, state):
        c = chrome_for(self._theme_id())
        col = "#2ecc71" if state is True else c["separator"]   # 绿=有效 / 灰=无效或未知
        dot.setStyleSheet("color: %s; font-size: 13px;" % col)

    def _reset_recv_state(self, reset_dashboard=False):
        """重置主数据区接收状态；断线/清屏这类真正的数据流断点可同时切断仪表盘半行。
        HEX/转储显示设置也会调用本函数，但不应影响与显示区解耦的仪表盘解析。"""
        self._last_recv_time = 0.0
        self._last_direction = None
        self._pending_line_break = False
        self._rx_decode_buffer = b""
        self._rx_decode_buffers = {}   # TCP Server 每客户端独立半字符
        self._rx_pending_cr = False
        self._rx_pending_cr_source = None
        self._inc_decoder = None
        self._inc_decoders = {}
        self._txt_ends_with_nl = True
        self._numview_carries = {}     # 数值视图余数：数据流断点后各来源旧的半个数都已无意义
        self._ansi_state = None        # 同理：断点后旧颜色不该染到新数据上
        self._ansi_pending = ""
        self._ansi_states = {}
        self._ansi_pendings = {}
        self._reset_trigger_decoders() # 触发引擎的半个字符同样作废
        if hasattr(self, "_proto_fields"):
            self._proto_fields.clear()    # 清屏/重连：旧帧的字段高亮 cursor 一并清掉
        if reset_dashboard:
            dash = getattr(self, "_dash_dlg", None)
            if dash is not None:
                dash.reset_stream()       # 不把断线/清屏前的半行与新数据误拼

    def _on_conn_error(self, msg):
        """连接层致命错误：监听/连接/绑定失败 或 连接过程中出错。"""
        # 用 _conn_proto(实际打开的协议)而非下拉框当前值：连接中导入配置可能改了下拉框，
        # 不能拿新值解释旧连接(见 __init__ 处 _conn_proto 注释)。在此处一次性取，早于下面
        # close_conn() 把它清空；失败/无连接时回退读下拉框。
        proto = self._conn_proto or (self.cb_proto.currentText() if hasattr(self, "cb_proto") else "")
        key = {PROTO_SERIAL: "err_open_failed",
               PROTO_TCP_SERVER: "err_listen_failed",
               PROTO_TCP_CLIENT: "err_connect_failed",
               PROTO_UDP: "err_bind_failed",
               PROTO_UDP_MULTICAST: "err_bind_failed"}.get(proto, "err_connect_failed")
        # 串口已打开成功后 reader 运行时报错(拔出/掉线等)：文案用"连接中断"而非"打开失败"
        if proto == PROTO_SERIAL and self._conn_engaged:
            key = "err_serial_runtime"
        was_conn_timeout = (msg == ERR_CONN_TIMEOUT)
        if was_conn_timeout:   # net_io timeout sentinel -> localized text
            msg = self._t("err_conn_timeout")
        else:
            # S-5: map raw OS/Qt strings to actionable tips when recognized
            msg = conn_error_tips.format_conn_error_detail(msg, self._t)
        self._stat_note_rx_error()           # connection/link errors count as RX errors
        if was_conn_timeout:
            _note_to = getattr(self, "_stat_note_timeout", None)
            if callable(_note_to):
                _note_to("conn")
        self._refresh_stat_labels(with_tooltip=False)
        # 串口首次掉线必须提示一次；仅当已经持有重连目标（即后续自动重试）时静默。
        # 不用 attempts 判断，避免残留/边界计数让首次掉线被误判成重试而吞掉提示。
        serial_retrying = proto == PROTO_SERIAL and self._serial_reconnect_cfg is not None
        if not serial_retrying:
            self.toast(self._t(key, e=msg), error=True)
        # 关键：close_conn 会把 _conn_engaged 清零，所以要先捕获状态
        was_engaged = self._conn_engaged
        in_retry = self._reconnect_attempts > 0
        serial_cfg = self._conn_cfg if proto == PROTO_SERIAL else None
        if self.conn is not None:
            self.close_conn()
        # 只在「曾连上又断了」(运行时掉线) 或「正在重连周期内」时自动重连。
        # 手动打开失败（端口占用/服务器离线/绑定失败）不该陷入无限重试。
        # 串口重连保存掉线前的完整签名，不读取可能已回落到其他设备的下拉框。
        if proto == PROTO_SERIAL and serial_cfg and (was_engaged or in_retry):
            self._serial_reconnect_cfg = tuple(serial_cfg)
        if was_engaged or in_retry:
            self._schedule_reconnect()

    def _schedule_reconnect(self):
        """非主动断开后排队重连；串口 0.5s 线性退避，网络指数退避。主动断开/退出时跳过。"""
        if self._user_closing:
            return
        if not self.settings.value("auto_reconnect", True, type=bool):
            return
        if self._reconnect_timer.isActive():
            return     # 已排队 → 同事件被 state_changed 和 error_occurred 同时触发也只算一次，
                       # 否则会跳过本级退避（attempts 多加 1、delay 直接翻倍）
        serial_retry = self._serial_reconnect_cfg is not None
        if serial_retry and self._reconnect_attempts >= self._serial_reconnect_limit:
            self._serial_reconnect_cfg = None
            self._reconnect_attempts = 0
            return     # 第十次仍未恢复：静默放弃，界面已经是断开状态
        n = self._reconnect_attempts
        if serial_retry:
            delay = min(5000, 500 * (n + 1))   # 0.5s→1.0s→...→5.0s，共 10 次
        else:
            delay = min(30000, 1000 * (2 ** n))  # 网络：1s→2s→4s→...→cap 30s
        if not serial_retry:
            self._reconnect_attempts = n + 1
        if not serial_retry:
            self.toast(self._t("auto_reconnect_in", sec=delay // 1000))
        self._reconnect_timer.start(delay)

    def _cancel_reconnect(self):
        if self._reconnect_timer.isActive():
            self._reconnect_timer.stop()

    def _try_reconnect(self):
        if self.conn is not None or self._user_closing:
            return     # 期间已连上 / 用户主动关，撤销
        if not self.settings.value("auto_reconnect", True, type=bool):
            return
        reconnect_cfg = self._serial_reconnect_cfg
        if reconnect_cfg:
            # 每次定时器触发只消耗一个全局重连时隙；端口缺失和真实打开失败共用 10 次上限，
            # 避免两套计数叠加后超过 0.5+1+...+5 = 27.5 秒的承诺窗口。
            self._reconnect_attempts += 1
            device = reconnect_cfg[1]
            if device not in self._available_serial_devices:
                self._schedule_reconnect()  # 原端口还没重新枚举，继续退避等待，绝不尝试其他口
                return
        if not reconnect_cfg:
            self.toast(self._t("auto_reconnect_try", n=self._reconnect_attempts))
        self.open_conn(reconnect_cfg=reconnect_cfg)
        # open_conn 同步失败(端口不存在/baud非法/绑定失败)：conn 仍为 None 且无 state_changed
        # 触发，需手动再排队；若是异步失败(如 TcpClient 连不上)会另走 _on_conn_state_changed 路径
        if self.conn is None and not self._user_closing:
            # 串口第 10 次失败会在 _on_conn_error → _schedule_reconnect 中清掉目标；这里不能
            # 再把 target=None 当成网络重连排队，否则会读取 UI 端口并突破次数上限。
            if reconnect_cfg is None or self._serial_reconnect_cfg is not None:
                self._schedule_reconnect()

    def _on_conn_state_changed(self, up):
        """已连接/监听(up=True) 或 对端断开(up=False)。
        主动 close_conn() 会先 blockSignals，断开的 False 不会回到这里。"""
        if up:
            self._conn_engaged = True   # 已成功建立 → 此后的 error 属"运行时"而非"打开失败"
            self._reconnect_attempts = 0  # 连上 → 重置退避；串口下次从 500ms、网络从 1s 起
            self._cancel_reconnect()
            self._update_conn_status()
            self._update_net_fields()   # TCP Server 连上后显示「目标」行
            self._mbm_restart()         # 连上 → 若 Modbus 主机轮询开启则启动
        elif self.conn is not None:
            self.toast(self._t("net_peer_closed"))
            self.close_conn()
            self._schedule_reconnect()  # 非主动断开 → 走自动重连

    def _on_clients_changed(self, clients):
        """TCP Server 客户端列表变化 → 刷新「目标」下拉（含「全部」）。"""
        active = {key for key, _label in clients}
        self._flush_numview_carries(set(self._numview_carries) - active)
        self._modbus_buffers = {key: buf for key, buf in self._modbus_buffers.items()
                                if key in active}
        self._numview_carries = {key: buf for key, buf in self._numview_carries.items()
                                 if key in active}
        self._rx_decode_buffers = {key: buf for key, buf in self._rx_decode_buffers.items()
                                   if key in active}
        self._inc_decoders = {key: dec for key, dec in self._inc_decoders.items()
                              if key in active}
        self._ansi_states = {key: state for key, state in self._ansi_states.items()
                             if key in active}
        self._ansi_pendings = {key: pending for key, pending in self._ansi_pendings.items()
                               if key in active}
        if self._rx_pending_cr and self._rx_pending_cr_source not in active:
            self._flush_pending_cr()
        self._term_streams = {key: state for key, state in self._term_streams.items()
                              if key in active}
        # 触发匹配的半字符 / ANSI 残片 / 回看尾巴也属于某个客户端的字节流。
        # 客户端离开后立即丢掉，既防重连误拼，也避免长期监听时状态表随历史客户端增长。
        for states in (self._trg_dec_buf, self._trg_dec, self._trg_ansi_pending,
                       self._trg_tail_bytes, self._trg_tail_text):
            for stream_key in list(states):
                if (isinstance(stream_key, tuple) and len(stream_key) == 2
                        and stream_key[1] not in (None, "__all__")
                        and stream_key[1] not in active):
                    states.pop(stream_key, None)
        if not hasattr(self, "cb_target"):
            return
        cur = self.cb_target.currentData()
        self.cb_target.blockSignals(True)
        self.cb_target.clear()
        self.cb_target.addItem(self._t("client_all"), "__all__")
        for key, label in clients:
            self.cb_target.addItem(label, key)
        idx = self.cb_target.findData(cur) if cur else 0
        self.cb_target.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_target.blockSignals(False)
        self._update_net_fields()   # 客户端 0↔有 变化时同步「目标」行的显隐

    def _on_udp_peer_changed(self, ip, port):
        """UDP 收到新对端时，若「指定远程」关闭(回复模式)，把灰显的远程框刷成最近对端地址。
        纯显示——让用户看到当前在跟谁通信、发送会回复给谁；之后打开「指定远程」即预填好该对端。
        「指定远程」打开时不刷(那是用户固定的目标，不能被覆盖)。"""
        if (self.cb_proto.currentText() == PROTO_UDP
                and not self.sw_udp_remote.isChecked()):
            self.ed_remote_ip.setText(ip)
            self.ed_remote_port.setText(str(port))

    def _update_conn_status(self):
        """刷新状态栏左下角的连接状态文本 + 状态点颜色。"""
        if self.conn is None:
            self.lbl_state.setText(self._t("state_closed"))
            self._set_state_color(opened=False)
            return
        proto = self.cb_proto.currentText()
        if proto == PROTO_VIRTUAL:
            key = "vconn_state_loop" if getattr(self.conn, "loopback", False) else "vconn_state"
            self.lbl_state.setText(self._t(key))
            self._set_state_color(opened=True)
            return
        if proto == PROTO_SERIAL:
            port = self.cb_port.currentData() or ""
            self.lbl_state.setText(f"● {port} @ {self.cb_baud.currentText()}")
            self._set_state_color(opened=True)
            return
        if proto == PROTO_TCP_SERVER:
            addr = f"{self.cb_local_ip.currentText().strip()}:{self.ed_local_port.text().strip()}"
            self.lbl_state.setText(self._t("net_listening", proto="TCP", addr=addr))
            self._set_state_color(opened=True)
        elif proto == PROTO_TCP_CLIENT:
            if self.conn.is_open:
                addr = f"{self.ed_remote_ip.text().strip()}:{self.ed_remote_port.text().strip()}"
                self.lbl_state.setText(self._t("net_connected", addr=addr))
                self._set_state_color(opened=True)
            else:
                self.lbl_state.setText(self._t("net_connecting"))
                self._set_state_color(opened=False)
        elif proto == PROTO_UDP_MULTICAST:
            addr = f"{self.ed_group.text().strip()}:{self.ed_local_port.text().strip()}"
            self.lbl_state.setText(self._t("net_group_joined", addr=addr))
            self._set_state_color(opened=True)
        else:  # UDP
            addr = f"{self.cb_local_ip.currentText().strip()}:{self.ed_local_port.text().strip()}"
            self.lbl_state.setText(self._t("net_udp_bound", addr=addr))
            self._set_state_color(opened=True)

    def _send_target(self):
        """TCP Server 模式下，当前选中的发送目标客户端 key（"__all__"=全部）；其余协议返回 None。"""
        if (self.cb_proto.currentText() == PROTO_TCP_SERVER
                and hasattr(self, "cb_target") and self.cb_target.count() > 0):
            return self.cb_target.currentData()
        return None

    def _abort_partial_tcp_stream(self, sent, expected):
        """TCP 短写后流中已留下半帧，不能继续复用；立即断开，交自动重连重建干净流。"""
        if (0 < sent < expected
                and getattr(self, "_conn_proto", None) == PROTO_TCP_CLIENT):
            self.close_conn()
            self._schedule_reconnect()
            return True
        return False

    def _flush_pending_cr(self):
        """把跨包待定的 \\r 输出出来。
        场景：CRLF 模式下对端只发了孤立 \\r 然后没下文，断开连接/切模式时
        如果不冲掉，用户永远看不到那个 \\r。"""
        if not self._rx_pending_cr:
            return
        self._rx_pending_cr = False
        self._rx_pending_cr_source = None
        force_new = (self._last_direction != "rx") or self._pending_line_break
        self._append_block_data("\r", direction="rx", force_new_block=force_new)
        self._last_direction = "rx"

    def close_conn(self):
        # 传输中断连 → 取消传输（连接没了协议无法继续；worker 收到取消会尽快收尾并复位收流）
        if self._xfer_worker is not None and self._xfer_worker.isRunning():
            self._xfer_worker.cancel()
        # 回放的 inject 回调绑定当前虚拟连接；断连后必须同步停掉定时器和占用态，
        # 否则会继续向已关闭的旧连接静默注入，循环模式还会永久占线。
        rr_dlg = getattr(self, "_rr_dlg", None)
        if rr_dlg is not None:
            rr_dlg.stop_replay()
            rr_dlg.stop_recording()
        elif getattr(self, "_replay_on", False):
            self._replay_end()
        if self.sw_period.isChecked():
            self.sw_period.setChecked(False)
        # 停多条发送循环定时器：否则非 closeEvent 路径(点断开/对端断开/连接错误)断连后，
        # 下一 tick 的 _ms_cycle_step 还会再弹一个「未连接」toast，造成双重错误提示
        self._ms_stop_cycle()
        # 断开前先把待定 \r 显示出来，否则数据丢用户视觉
        # 同时要在关闭实时日志前执行，保证日志和屏幕显示一致。
        self._flush_pending_cr()
        if self.sw_log_file.isChecked():
            self.sw_log_file.setChecked(False)
        conn = self.conn
        self.conn = None    # 先置空，避免 close() 触发的 state_changed(False) 回调重入
        self._stop_device_scan(cancelled=True)
        self._conn_proto = None
        self._conn_cfg = None
        self._mbm_guard_until = 0.0   # 物理连接已断，旧响应不可能进入下一会话
        self._conn_engaged = False
        self._serial_device = None    # 已断开 → 清掉串口掉线检测的目标设备
        self._serial_missing_count = 0
        if conn:
            try:
                conn.blockSignals(True)
                conn.close()
            except Exception:
                _log.debug("connection close failed", exc_info=True)
            conn.deleteLater()

        if getattr(self, "_seq_on", False):   # 连接断开 → 中止运行中的序列（保留结果 + 提示，不静默）
            self._seq_abort("seq_aborted_disc")
        # 脚本控制台同理：链路没了就别让脚本对着断掉的连接空跑（send 进虚空、每个 expect
        # 都要等满超时）。协作式停止，脚本会在下一个 send/expect/recv/sleep 处退出并出汇总。
        if self._script_running():
            self._script_worker.stop()
        self._dsl_abort()          # 断连 → 中止 DSL 剩余步骤，别对着断掉的连接空发
        self._flush_numview_carries()
        self._reset_recv_state(reset_dashboard=True)  # 新连接不能消费旧会话的半行
        self._ar_reset_buf()       # 清自动应答半包缓冲：断/重连时旧字节不能被新连接消费
        self._ar_reset_state()     # C8：断开=会话结束 → 状态机回到初始（下次连上从 init 开始握手）
        self._mbm_restart()        # 断开 → 停止 Modbus 主机轮询（_mbm_active 此时为假）
        if hasattr(self, "_ctrl_poll_timer"):
            self._ctrl_poll_timer.stop()   # 断开 → 停止控制线状态轮询

        self.btn_open.setProperty("state", "")
        self.btn_open.style().unpolish(self.btn_open)
        self.btn_open.style().polish(self.btn_open)
        self.lbl_state.setText(self._t("state_closed"))
        self._set_state_color(opened=False)
        self.set_settings_enabled(True)
        if hasattr(self, "cb_target"):
            self.cb_target.clear()
        self._update_net_fields()

    # ----- 串口端口扫描 -----
    def refresh_ports(self):
        """点 ⟳ 时调用 — 用一次性后台线程，避免慢驱动卡 GUI。
        结果通过 _on_port_scan_complete 回 GUI 线程（和后台轮询线程共用处理逻辑）。
        线程**不挂 parent**：万一退出时 wait 超时 comports() 还卡住，线程对象不会跟着
        主窗口一起销毁；finished 后 deleteLater 自清，_clear_oneshot_scan 置 None 避免悬空。
        """
        if getattr(self, "_oneshot_scan", None) and self._oneshot_scan.isRunning():
            return  # 节流：上一次还在跑就忽略
        scan = OneShotPortScanner()  # 故意无 parent
        self._oneshot_scan = scan
        scan.scan_complete.connect(self._on_port_scan_complete)
        scan.finished.connect(lambda: self._clear_oneshot_scan(scan))
        scan.finished.connect(scan.deleteLater)
        scan.start()

    def _clear_oneshot_scan(self, scan):
        """deleteLater 之后清掉 Python 属性引用，避免下次 isRunning() 访问已删 C++ 对象。
        `is scan` 守卫：如果期间已经创建了新 scan，不清新的。"""
        if getattr(self, "_oneshot_scan", None) is scan:
            self._oneshot_scan = None

    def _populate_port_combo(self, port_list, keep_device=None, allow_placeholder=True):
        self.cb_port.blockSignals(True)
        self.cb_port.clear()
        for device, label in port_list:
            self.cb_port.addItem(label, device)
        # keep_device=None -> leave Qt default; keep_device='' -> explicit no-port
        if keep_device is not None:
            if keep_device == "":
                idx = -1
                for i in range(self.cb_port.count()):
                    if self.cb_port.itemData(i) == "":
                        idx = i
                        break
                if idx < 0:
                    self.cb_port.insertItem(0, self._t("no_ports"), "")
                    idx = 0
                self.cb_port.setCurrentIndex(idx)
            else:
                idx = -1
                for i in range(self.cb_port.count()):
                    if self.cb_port.itemData(i) == keep_device:
                        idx = i
                        break
                if idx < 0:
                    if allow_placeholder:
                        # 选中口本次没枚举到、但仍在去抖宽限内（可能只是 USB 串口瞬时掉枚举/
                        # 插拔瞬间）：保留为占位项并选中，**绝不让选择静默落到列表第一个口** ——
                        # 否则「选了串口1，后台扫描时 COM1 短暂消失 → 默认跳第一个口(串口2) →
                        # 用户没察觉就打开成串口2」。口回来后下次扫描选回真实项。
                        self.cb_port.addItem(self._t("port_missing", port=keep_device), keep_device)
                        idx = self.cb_port.count() - 1
                    else:
                        # 已超过宽限、口确实长期不在（拔出/掉驱动）：删掉占位、回落到第一个真实口
                        # （没有则不选），断开/拔出后下拉不再常驻「未检测到」残留项。
                        idx = 0 if self.cb_port.count() else -1
                self.cb_port.setCurrentIndex(idx)
        self.cb_port.blockSignals(False)

    def _select_serial_device(self, device):
        """把串口下拉同步到实际连接设备；扫描列表尚未来得及刷新时补一个临时项。"""
        if not device:
            return
        self.cb_port.blockSignals(True)
        idx = self.cb_port.findData(device)
        if idx < 0:
            self.cb_port.addItem(device, device)
            idx = self.cb_port.count() - 1
        self.cb_port.setCurrentIndex(idx)
        self.cb_port.blockSignals(False)

    def _on_serial_port_selected(self, index):
        """用户显式改选其他真实端口：取消旧口重连并立即移除旧的“未检测到”占位。"""
        device = self.cb_port.itemData(index) if index >= 0 else None
        self._serial_empty_selection = not bool(device)
        reconnect_device = (self._serial_reconnect_cfg[1]
                            if self._serial_reconnect_cfg else None)
        if (not reconnect_device or not device or device == reconnect_device
                or device not in self._available_serial_devices):
            return

        # activated 只由用户操作触发；后台刷新和重连成功的程序选中不会误取消重连。
        self._cancel_reconnect()
        self._serial_reconnect_cfg = None
        self._reconnect_attempts = 0
        self._sel_missing_count = 0
        self._pending_restore_port = None  # 用户选择优先于启动时的旧端口恢复

        # 从当前下拉提取最近扫描到的真实端口，过滤掉旧重连目标的占位项后重建。
        port_list = [(self.cb_port.itemData(i), self.cb_port.itemText(i))
                     for i in range(self.cb_port.count())
                     if self.cb_port.itemData(i) in self._available_serial_devices]
        self._last_port_list = port_list
        self._populate_port_combo(port_list, device, allow_placeholder=False)

    def _on_port_scan_complete(self, port_list):
        self._available_serial_devices = {dev for dev, _ in port_list if dev}
        if not port_list:
            port_list = [("", self._t("no_ports"))]
        # 串口已连接时不动 cb_port（端口占用中、也别打断当前选择）；但要顺带检查正在用的口
        # 是否还在枚举里 —— USB 串口会偶发瞬时掉枚举(见 _populate_port_combo 注释)，故连续
        # _serial_missing_limit 次都检测不到才判定真移除 → 主动断开(单次抖动不误断正在用的连接)。
        if self.conn is not None and self._conn_proto == PROTO_SERIAL:
            if self._serial_device:
                if any(dev == self._serial_device for dev, _ in port_list):
                    self._serial_missing_count = 0
                else:
                    self._serial_missing_count += 1
                    if self._serial_missing_count >= self._serial_missing_limit:
                        dev = self._serial_device
                        reconnect_cfg = self._conn_cfg
                        self._serial_missing_count = 0
                        self.close_conn()
                        if reconnect_cfg:
                            self._serial_reconnect_cfg = tuple(reconnect_cfg)
                        self.toast(self._t("serial_removed", port=dev), error=True)
                        self._schedule_reconnect()
            return
        if self.cb_port.view().isVisible():   # 下拉正展开时不刷，避免选项跳动
            return
        restore_pending = getattr(self, "_pending_restore_port", None)
        reconnect_pending = (self._serial_reconnect_cfg[1]
                             if self._serial_reconnect_cfg else None)
        # 自动重连期间原端口优先级最高：既不让下拉回落到第一个口，也不允许界面显示
        # 与实际重连目标不同的设备。
        pending = reconnect_pending or restore_pending
        # 选中口连续缺失去抖计数 —— **必须在「列表与上次相同就 return」去重之前更新**：
        # 口拔掉后端口列表很快稳定不变(就是少了那个口)，若把计数放在 return 之后，列表稳定
        # 后每次都提前 return、计数停更、占位永远删不掉。这里每次扫描都推进计数。
        # Preserve intentional empty selection (""): `or` would skip it.
        if self._serial_empty_selection:
            sel = ""
        elif reconnect_pending:
            sel = reconnect_pending
        elif self.cb_port.currentIndex() >= 0:
            sel = self.cb_port.currentData()
        else:
            sel = pending
        if sel and not any(dev == sel for dev, _ in port_list):
            self._sel_missing_count += 1
        else:
            self._sel_missing_count = 0
        # 宽限刚走完(计数恰超限)的那一次：即便端口列表没变，也要重建一次把占位删掉、回落真实口。
        need_drop = (not reconnect_pending and bool(sel)
                     and self._sel_missing_count > self._serial_missing_limit)
        # pending(启动恢复的上次端口)已出现在列表里但还没选回时，别因「列表与上次相同」提前返回——
        # 否则启动扫描早于配置恢复(pending 设值)时，pending 设上后端口列表恰好没变，会永远跳过
        # 恢复、选不回上次用的串口。这种情况必须放行一次，让下面的 pending 分支把它选回。
        pending_present = bool(pending) and any(dev == pending for dev, _ in port_list)
        reconnect_mismatch = bool(reconnect_pending) and self.cb_port.currentData() != reconnect_pending
        if (port_list == self._last_port_list and not need_drop
                and not pending_present and not reconnect_mismatch):
            return
        self._last_port_list = port_list
        # ① pending(启动恢复的上次端口)一旦真实出现就选回它，优先于一切——即便此前因长期不在
        #    已回落到别的口，设备插上的那次扫描仍能选回，不丢「恢复上次选择」能力。
        if self._serial_empty_selection:
            keep, hold = "", True
        elif pending and any(dev == pending for dev, _ in port_list):
            keep, hold = pending, True
            if pending == restore_pending:
                self._pending_restore_port = None   # 上次端口已真实出现并将被选回 → 恢复完成
            self._sel_missing_count = 0
        else:
            # ② 否则保持用户当前选择；选中口短暂消失(去抖宽限内)→ 占位保留防漂移；
            #    长期不在(超宽限)→ 删占位、回落第一个真实口，下拉不留「未检测到」残留。
            # Do not use or sel: empty-string selection is falsy.
            keep = reconnect_pending if reconnect_pending else sel
            hold = bool(reconnect_pending) or self._sel_missing_count <= self._serial_missing_limit
        self._populate_port_combo(port_list, keep, allow_placeholder=hold)
        # 原端口一重新枚举就立即唤醒退避定时器；避免 UI 已显示端口但连接仍在等待。
        if reconnect_pending and pending_present and self._reconnect_timer.isActive():
            self._reconnect_timer.start(0)

    def _wait_oneshot_scan(self):
        """退出前确保一次性端口扫描线程结束 — 否则可能 QThread: Destroyed while running。"""
        scan = getattr(self, "_oneshot_scan", None)
        if scan and scan.isRunning():
            scan.wait(2000)

    def set_settings_enabled(self, enabled):
        # 远程框(ed_remote_*)启用由 _update_net_fields 统管(TCP恒开/UDP看开关)；
        # 目标客户端下拉(cb_target)连接期间要可切换发送目标，不锁。
        # 波特率/数据位/校验位/停止位 连接期间不锁：改动即应用到活动串口
        # (_apply_serial_params_live，pyserial 属性赋值即时生效)，试波特率不必断开重连。
        # 换端口/换协议仍必须重开连接，保持锁定。
        for w in (self.cb_proto, self.cb_local_ip, self.ed_local_port,
                  self.ed_group, self.sw_udp_remote,
                  self.cb_port, self.btn_refresh):
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
        self._apply_version_label_style(c)   # 普通色 / 新版徽标强调色，按当前态自适应（复用 c）
        if hasattr(self, "lbl_log_path"):
            self.lbl_log_path.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")
        if hasattr(self, "status_bar"):
            # 用不透明的窗口色而非 transparent：showMessage(toast) 时 Qt 会隐藏 RX/TX 统计标签，
            # 但透明底不擦底 → 隐藏标签的旧像素残留、与提示文字重叠。不透明底每次重绘擦净 → 不重叠。
            # 窗口(QMainWindow)本就是同一 window_bg，故观感不变。
            self.status_bar.setStyleSheet(f"background: {c['window_bg']}; color: {c['text_sec']};")
        if hasattr(self, "lbl_state"):
            self._set_state_color(opened=self._is_open())
        if hasattr(self, "title_bar") and hasattr(self.title_bar, "title_label"):
            self.title_bar.title_label.setStyleSheet(
                f"color: {c['text_sec']}; background: transparent;")
        self._update_legend_label(c)
        # iOS 开关是 custom-paint、不走 QSS，切主题时手动让关态色跟随主题（开态恒用绿）
        for sw in self.findChildren(IOSSwitch):
            sw.set_theme_colors(c["separator"], "#FFFFFF")
        # 数据区历史文字按角色重涂成新主题色 + 行高亮换色（否则浅↔深切换后文字看不见）
        if hasattr(self, "txt_recv"):
            self._recolor_history()
            self._apply_recv_highlight()
        if hasattr(self, "_search_bar"):
            self._style_search_bar()
        # 多条发送/关键字高亮弹窗若开着也跟着换主题
        if getattr(self, "_multi_send_dlg", None) is not None:
            self._multi_send_dlg.refresh_theme()
        if getattr(self, "_keyword_dlg", None) is not None:
            self._keyword_dlg.refresh_theme()
        if getattr(self, "_plot_dlg", None) is not None:
            self._plot_dlg.refresh_theme()
        if getattr(self, "_dash_dlg", None) is not None:
            self._dash_dlg.refresh_theme()
        if getattr(self, "_script_dlg", None) is not None:
            self._script_dlg.refresh_theme()
        if getattr(self, "_rr_dlg", None) is not None:
            self._rr_dlg.refresh_theme()
        if getattr(self, "_rd_dlg", None) is not None:
            self._rd_dlg.refresh_theme()
        if getattr(self, "_snip_dlg", None) is not None:
            self._snip_dlg.refresh_theme()
        if getattr(self, "_send_hist_dlg", None) is not None:
            self._send_hist_dlg.refresh_theme()
        if getattr(self, "_cpreset_dlg", None) is not None:
            self._cpreset_dlg.refresh_theme()
        if getattr(self, "_triggers_dlg", None) is not None:
            self._triggers_dlg.refresh_theme()
        if getattr(self, "_frame_dlg", None) is not None:
            self._frame_dlg.refresh_theme()
        if getattr(self, "_ar_dlg", None) is not None:
            self._ar_dlg.refresh_theme()
        if getattr(self, "_mbm_dlg", None) is not None:
            self._mbm_dlg.refresh_theme()
        if getattr(self, "_seq_dlg", None) is not None:
            self._seq_dlg.refresh_theme()
        if getattr(self, "_frame_builder_dlg", None) is not None:
            self._frame_builder_dlg.refresh_theme()
        if getattr(self, "_toolbox_dlg", None) is not None:
            self._toolbox_dlg.refresh_theme()
        if getattr(self, "_xfer_dlg", None) is not None:
            self._xfer_dlg.refresh_theme()
        if getattr(self, "_bridge_dlg", None) is not None:
            self._bridge_dlg.refresh_theme()
        if getattr(self, "_device_center_dlg", None) is not None:
            self._device_center_dlg.refresh_theme()
        if getattr(self, "_structured_dlg", None) is not None:
            self._structured_dlg.refresh_theme()

    # ----- 接收 -----
    def _get_codec(self) -> str:
        """Current RX/TX/file codec mode -- 'auto' or concrete codec name."""
        if hasattr(self, "cb_encoding"):
            return _cfg_norm_enc(self.cb_encoding.currentData())
        return "auto"

    def _send_codec(self) -> str:
        """TX 用的具体 codec — Auto 模式下默认 utf-8"""
        c = self._get_codec()
        return "utf-8" if c == "auto" else c

    def _on_hex_display_changed(self, _=False):
        """切换 HEX/文本 显示：复位增量解码 + 立即重画叠加高亮。
        协议高亮的字段区间按 HEX 渲染算得，切到文本模式须立刻撤掉旧高亮（refresh 里按当前
        模式判定），否则旧色块残留在已渲染的 HEX 文本上。"""
        self._on_encoding_changed()
        self._refresh_hex_toggle_state()   # HEX 显示不解释转义序列 → 联动 ANSI 着色开关的可用性
        self._kw_timer.stop()
        self._refresh_extra_selections()
        self._update_sel_checksum()

    def _on_encoding_changed(self):
        """切换编码时重置增量解码状态，悬挂字节别用新 codec 错误解码"""
        self._reset_trigger_decoders()   # 触发引擎与显示区共用编码设置，一起复位
        self._rx_decode_buffer = b""
        self._rx_decode_buffers = {}
        self._inc_decoders = {}
        enc = self._get_codec()
        if enc == "auto":
            self._inc_decoder = None
        else:
            try:
                self._inc_decoder = codecs.getincrementaldecoder(enc)(errors="replace")
            except (LookupError, TypeError):
                self._inc_decoder = None  # 罕见的找不到 codec 直接回退 auto

    def _decode_rx(self, data: bytes, source=None) -> str:
        """按选定编码增量解码。Auto 走 UTF-8 优先 / GBK 回退；其他走 Python 标准增量解码器。

        TCP Server 的每个客户端是独立字节流，半个多字节字符必须按 source 隔离；否则 A 的
        UTF-8 前两字节会和 B 的末字节拼成一个线路上从未出现过的字符。
        """
        stream_source = (source if getattr(self, "_conn_proto", None) == PROTO_TCP_SERVER
                         else None)
        if self._get_codec() != "auto":
            if stream_source is not None:
                dec = self._inc_decoders.get(stream_source)
                if dec is None:
                    try:
                        dec = codecs.getincrementaldecoder(self._get_codec())(errors="replace")
                    except (LookupError, TypeError):
                        return data.decode("latin-1")
                    self._inc_decoders[stream_source] = dec
                return dec.decode(data, final=False)
            if self._inc_decoder is None:
                # 第一次调用 / 刚切到具体编码 — 初始化
                self._on_encoding_changed()
            if self._inc_decoder is not None:
                return self._inc_decoder.decode(data, final=False)
            # codec lookup 失败兜底
            return data.decode("latin-1")

        # Auto 模式 — UTF-8 优先, 不完整就缓存, 真乱码回退 GBK
        if stream_source is not None:
            text, self._rx_decode_buffers[stream_source] = self._decode_auto_chunk(
                self._rx_decode_buffers.get(stream_source, b""), data)
            return text
        text, self._rx_decode_buffer = self._decode_auto_chunk(self._rx_decode_buffer, data)
        return text

    @staticmethod
    def _decode_auto_chunk(buf: bytes, data: bytes):
        """Auto decode core: UTF-8 first, partial char kept, GBK fallback."""
        return _rx_decode_auto_chunk(buf, data)

    def _rx_side(self, name, fn):
        """RX side-channel: log failures, never abort the receive path."""
        try:
            fn()
        except Exception:
            _log.debug("rx side-channel %s failed", name, exc_info=True)

    def on_data_received(self, data: bytes, reply_target=None):
        # 文件传输进行中：整段接管收流，不进显示区/自动应答/序列/Modbus。
        # 协议传输(XMODEM/YMODEM)喂给引擎当 getc 源；原始字节流(raw)只发不收，收流直接丢弃。
        w = self._xfer_worker
        if w is not None and w.isRunning():
            if getattr(w, "takes_input", True):
                self._rx_side("xfer.feed", lambda: w.feed(data))
            return
        # 顶层异常保护：解码/插入等意外异常不应静默丢数据(传到事件循环只在 stderr 打印)
        try:
            self._on_data_received_impl(data, source=reply_target)
        except Exception as e:
            self._stat_note_rx_error()
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("err_rx", e=e), error=True)
        # 波形图（若已打开）：用同一份原始数据自行缓冲/解析/绘曲线，与显示区解耦；
        # 自带异常兜底，绘图侧的问题不影响数据接收主流程
        dlg = getattr(self, "_plot_dlg", None)
        if dlg is not None and dlg.isVisible():
            self._rx_side("plot.feed", lambda: dlg.feed(data))
        fdlg = getattr(self, "_frame_dlg", None)
        if fdlg is not None and fdlg.isVisible():
            self._rx_side("frame.feed", lambda: fdlg.feed(data))
        # 宏录制：录回包，供生成 expect(...)（脚本运行期间不录，同 TX 侧）
        if (self._macro.recording and not self._script_running()
                and not self._seq_running()):
            self._rx_side("macro.on_rx", lambda: self._macro.on_rx(data))
        if self._recorder.recording:      # 数据录制：录原始 RX 现场
            self._rx_side("recorder.on_rx", lambda: self._recorder.on_rx(data))
        # 结构化记录：复用 frame_rules 抽取普通协议字段；Modbus 标签在响应解析成功后单独写入。
        def _structured_feed():
            if self._mbm_inflight is None:
                self._structured_feed_protocol(data)
        self._rx_side("structured.feed", _structured_feed)
        # 触发告警：命中就响铃 / 托盘通知 / 数据区打标（自带兜底，不影响收包主流程）
        self._rx_side("triggers.feed",
                      lambda: self._triggers_feed(data, "rx", source=reply_target))
        # 数值仪表盘（若已打开）：同一份原始数据自行解析成命名数值、更新卡片，自带兜底
        ddlg = getattr(self, "_dash_dlg", None)
        if ddlg is not None and ddlg.isVisible():
            self._rx_side("dashboard.feed", lambda: ddlg.feed(data))
        # 自动应答：收到数据匹配规则则自动回复（数据处理之后，自带兜底不影响主流程）。
        # 但 Modbus 主机轮询激活时，收到的都是从机「响应」——绝不能再让自动应答(尤其内置
        # Modbus 从机)把它当请求回发，否则总线互相干扰。主机激活时整体跳过自动应答。
        # 自动化序列运行中：响应喂给序列匹配引擎，并临时抑制自动应答/Modbus 主机（三者共用收流，
        # 序列是主动驱动方；序列结束后自动恢复，不改它们的开关）。
        # 脚本控制台运行中：脚本是主动驱动方，独占收流（expect 从这里拿数据），
        # 同样临时抑制自动应答 / Modbus 主机，结束后由 _script_end 恢复。
        if self._script_running():
            # 脚本接管前若 Modbus 主机已有请求在途，完整超时窗内的字节可能是旧响应；
            # 直接丢弃，避免它被脚本第一个 expect 误认。脚本首个 send 同样会等隔离窗结束。
            if time.monotonic() >= getattr(self, "_script_quiet_until", 0.0):
                self._rx_side("script.feed",
                              lambda: self._script_worker.feed(data))
        elif self._seq_running():
            def _seq_or_mbm():
                # 序列刚启动而 Modbus 尚有在途请求时，先让原请求完整收尾；超时后的迟到响应
                # 隔离期也继续喂 _mbm_feed（RTU 会按最后一个迟到字节重新满足 t3.5）。
                if getattr(self, "_seq_waiting_mbm", False):
                    self._mbm_feed(data)
                else:
                    self._seq_feed(data)
            self._rx_side("seq.feed", _seq_or_mbm)
        else:
            if not self._mbm_active():
                self._rx_side(
                    "auto_reply",
                    lambda: self._auto_reply(data, reply_target=reply_target))
            # Modbus 主机轮询：若有在途请求，把响应喂给轮询引擎切帧/解析（兜底不影响主流程）
            self._rx_side("mbm.feed", lambda: self._mbm_feed(data))

    def _on_data_received_impl(self, data: bytes, source=None):
        self._stat_note_rx(len(data))
        # 标签刷新交给 1Hz 的 _rate_timer：高频收包路径只累加整数计数器，
        # 不每包重建文案 + setText（会触发状态栏重排），高吞吐下避免无谓的 GUI 线程开销。

        # 终端模式：纯字节流直接追加显示，绕过 HEX / 时间戳 / 方向 / 分行 / 分包 等所有装饰。
        if self._terminal_on:
            self._terminal_append(self._decode_rx(data, source=source), source=source)
            return

        # HEX dump 视图：每个收包整段转储为「偏移 + HEX + ASCII」多行块（各块 force_new：独立起行、
        # 可选时间戳/箭头头，偏移按块从 0 起），优先于 HEX/文本/分行/分包 的文本渲染。
        if self._hexdump_on:
            self._append_block_data(self._hexdump_block(data), direction="rx",
                                    force_new_block=True)
            self._last_direction = "rx"
            self._last_recv_time = time.monotonic()
            self._pending_line_break = False
            return

        # 数值视图：整段按选定类型/字节序解读成数值序列（同 hexdump 各块 force_new 独立起行）。
        # 尾部凑不满一个数的字节由 _numview_block 留作余数带到下一包，此时本包可能一个数都凑不出
        # → 文本为空，跳过追加（否则平白多出一个空块 / 一行时间戳）。
        if self._numview_on:
            # 串口/TCP/虚拟连接是连续流，允许跨底层 chunk 补齐一个数；UDP 回调是完整数据报，
            # 报文边界不可跨越，尾字节由 _numview_block 直接以 HEX 标出。
            carry = self._conn_proto not in (PROTO_UDP, PROTO_UDP_MULTICAST)
            block = self._numview_block(data, carry=carry, source=source)
            if block:
                self._append_block_data(block, direction="rx", force_new_block=True)
                self._last_direction = "rx"
            self._last_recv_time = time.monotonic()
            self._pending_line_break = False
            return

        use_hex = self.sw_rx_hex.isChecked()
        use_line_split = self.sw_line_split.isChecked() and not use_hex
        now = time.monotonic()

        ansi_spans = None      # ANSI 着色：[(起, 止, 样式)]，下标相对下面这个 text
        if use_hex:
            text = self._bytes_to_hex(data) + " "
        else:
            text = self._decode_rx(data, source=source)
            if self._ansi_on:
                # 剥掉转义序列（顺带吃掉光标/擦除等非 SGR 的，不再显示成乱码），
                # 留下纯文本给后面的分行/分包逻辑，颜色以字符区间的形式另存。
                stream_source = (source if self._conn_proto == PROTO_TCP_SERVER else None)
                if stream_source is None:
                    st0, pd0 = self._ansi_state, self._ansi_pending
                else:
                    st0 = self._ansi_states.get(stream_source)
                    pd0 = self._ansi_pendings.get(stream_source, "")
                # 快速通道：没有转义符、没有残片、上一包也没留下颜色时，逐字符解析纯属
                # 白跑（每包热路径）。三个条件缺一不可——有残片要拼收尾；上一包颜色
                # 未复位时，本包纯文本也要继续着那个色，跳过解析会掉色。
                if pd0 or "\x1b" in text or (st0 is not None and not st0.is_default()):
                    runs, state, pending = ansi.parse(text, st0, pd0)
                    if stream_source is None:
                        self._ansi_state, self._ansi_pending = state, pending
                    else:
                        self._ansi_states[stream_source] = state
                        if pending:
                            self._ansi_pendings[stream_source] = pending
                        else:
                            self._ansi_pendings.pop(stream_source, None)
                    text, ansi_spans = self._ansi_flatten(runs)

        # 跨 chunk 的 \r\n 处理 — Auto(0) 和 CRLF(1) 都需要
        # （LF/CR 模式因为单字符就是终止符，无歧义，不需要 defer）
        cross_chunk_crlf = False
        nl_mode_for_defer = self.cb_line_nl.currentIndex() if use_line_split else -1
        if nl_mode_for_defer in (0, 1):
            stream_source = source if self._conn_proto == PROTO_TCP_SERVER else None
            # TCP Server 的各客户端不是同一条字节流：A 包尾的 CR 不能与 B 包头的 LF
            # 合成一个虚构 CRLF。来源切换时先按孤立 CR 冲出，再处理当前客户端。
            if (self._rx_pending_cr
                    and self._rx_pending_cr_source != stream_source):
                self._flush_pending_cr()
            if self._rx_pending_cr:
                if text.startswith("\n"):
                    text = text[1:]
                    # 删了首字符 → ANSI 颜色区间要跟着左移一位，否则整段色块错位
                    # （表现为一行的头一个字符没上色、末字符多上了色）
                    ansi_spans = self._ansi_shift(ansi_spans, -1, len(text))
                    cross_chunk_crlf = True
                else:
                    # 没接到 \n —— Auto 模式下 \r 单字符也是换行；
                    # CRLF 模式下 \r 单字符是数据（不是终止符），但 QTextEdit
                    # 渲染时仍会把它当换行显示。两种模式都先把 \r 还回去，
                    # 后续 split 按规则处理（Auto 把它当换行；CRLF 视为数据）
                    text = "\r" + text
                    ansi_spans = self._ansi_shift(ansi_spans, 1, len(text))  # 补了首字符 → 右移
                self._rx_pending_cr = False
                self._rx_pending_cr_source = None
            if text.endswith("\r"):
                self._rx_pending_cr = True
                self._rx_pending_cr_source = stream_source
                text = text[:-1]
                ansi_spans = self._ansi_shift(ansi_spans, 0, len(text))      # 削了尾字符 → 收界

            if cross_chunk_crlf and not text:
                self._pending_line_break = True
                self._last_recv_time = now
                return

        if use_line_split:
            segments, seg_starts = self._split_lines_with_offsets(
                text, self.cb_line_nl.currentIndex())
        else:
            segments, seg_starts = [text], [0]

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

            # ANSI 着色：把整段的颜色区间切出属于本行的部分（分行后下标要换算成行内偏移）
            seg_runs = (self._ansi_slice(ansi_spans, seg_starts[i], seg_starts[i] + len(seg))
                        if ansi_spans else None)
            body_pos = self._append_block_data(seg, direction="rx", force_new_block=force_new_block,
                                               runs=seg_runs)
            self._last_direction = "rx"
            # 协议高亮：HEX 模式下整段=一帧（seg 即 hex(data)），按帧解析规则给字段上色
            if use_hex and self._proto_hl_on and body_pos is not None:
                self._add_proto_fields(data, body_pos)

        if use_line_split:
            self._pending_line_break = (segments[-1] == "" and len(segments) > 1)
        else:
            self._pending_line_break = False
        self._last_recv_time = now

    @staticmethod
    def _split_lines_with_offsets(text, nl_mode):
        """Split by newline mode; return (segments, start_offsets)."""
        return _rx_split_lines(text, nl_mode)

    @staticmethod
    def _ansi_flatten(runs):
        """ansi.parse runs -> (plain_text, style spans)."""
        return _rx_ansi_flatten(runs)

    @staticmethod
    def _ansi_shift(spans, delta, limit):
        """Shift style spans by delta and clip to [0, limit)."""
        return _rx_ansi_shift(spans, delta, limit)

    @staticmethod
    def _ansi_slice(spans, start, end):
        """Keep spans in [start, end); rebase to line-relative offsets."""
        return _rx_ansi_slice(spans, start, end)

    def _apply_sgr_format(self, fmt, st, dark=None):
        """把 ANSI 样式写进字符格式。颜色同时存一份「标识」(ANSI_*_PROP)：切主题时据此按
        新主题明暗重解析，避免深色配色留在浅色底上看不见（见 _recolor_history）。"""
        if dark is None:
            dark = self._theme().get("mode") == "dark"
        theme = self._theme()
        fg, bg = st.fg, st.bg
        if st.reverse:
            # 反显：前后景对调；缺省那侧存「主题正文色 / 底色」的记号（不是当场算好的颜色），
            # 这样切深浅主题时能跟着重解析，不会把为深底选的颜色留在浅底上。
            fg = bg if bg is not None else ansi.SPEC_THEME_BG
            bg = st.fg if st.fg is not None else ansi.SPEC_THEME_FG
        if st.bold and isinstance(fg, int) and fg < 8:
            fg += 8            # 粗体 + 基础色 → 取亮色版，与终端惯例一致
        fg_spec = fg if isinstance(fg, str) else ansi.spec_of(fg)
        bg_spec = bg if isinstance(bg, str) else ansi.spec_of(bg)
        fmt.setProperty(ANSI_FG_PROP, fg_spec)
        fmt.setProperty(ANSI_BG_PROP, bg_spec)
        col = ansi.color_of_spec(fg_spec, dark, theme["fg"], theme["bg"])
        if col:
            fmt.setForeground(QColor(col))
        bcol = ansi.color_of_spec(bg_spec, dark, theme["fg"], theme["bg"])
        if bcol:
            fmt.setBackground(QColor(bcol))
        if st.bold:
            fmt.setFontWeight(QFont.Bold)
        if st.underline:
            fmt.setFontUnderline(True)

    def _insert_ansi_runs(self, cursor, text, runs, body_fmt):
        """按 ANSI 样式区间分段插入正文；区间之外的部分用默认正文格式。"""
        pos = 0
        for off, length, st in runs:
            if off > pos:
                cursor.setCharFormat(body_fmt)
                cursor.insertText(text[pos:off])
            fmt = QTextCharFormat(body_fmt)
            self._apply_sgr_format(fmt, st)
            cursor.setCharFormat(fmt)
            cursor.insertText(text[off:off + length])
            pos = off + length
        if pos < len(text):
            cursor.setCharFormat(body_fmt)
            cursor.insertText(text[pos:])

    def _recv_char_budget(self):
        """Soft character cap for the recv view (complements maximumBlockCount)."""
        doc = self.txt_recv.document()
        max_blocks = doc.maximumBlockCount() or 10000
        return max(100, int(max_blocks)) * _RECV_CHARS_PER_LINE

    def _trim_recv_overflow(self):
        """Drop oldest characters when the recv document exceeds the char budget.

        Needed because setMaximumBlockCount is a no-op while everything stays in
        one QTextBlock (line_split and packet_split both off, no newlines).
        Returns how many characters were removed from the start.
        """
        doc = self.txt_recv.document()
        plain_len = max(0, doc.characterCount() - 1)
        budget = self._recv_char_budget()
        excess = plain_len - budget
        if excess <= 0:
            return 0
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        cur.setPosition(0)
        cur.setPosition(min(excess, plain_len), QTextCursor.KeepAnchor)
        cur.removeSelectedText()
        cur.endEditBlock()
        return excess

    def _append_block_data(self, text: str, direction: str, force_new_block: bool,
                           view_mode=None, runs=None, role=None):
        if getattr(self, "_freeze_view", False):
            # 冻结视图：不追加显示，但「实时记录/Log to File」仍按正常拼接落盘（与 .ctrec 录制/
            # 统计/触发一样独立于视图）。否则冻结期间日志会静默丢一段数据，与"冻结只锁画面"的语义相悖。
            self._write_log_block(text, direction, force_new_block)
            return
        theme = self._theme()
        # TX 用主题里的 tx 色，RX 用 fg 默认色（主题切换后旧文字不会重涂）
        body_color = theme["tx"] if direction == "tx" else theme["fg"]
        # 滚动锁定：插入前先记住是否在底部 + 当前滚动位置；用独立游标插入，避免动可见光标/选区/视图
        was_at_bottom = self._recv_at_bottom()
        scroll_before = self.txt_recv.verticalScrollBar().value()   # 恢复选区时 setTextCursor 会滚到选区，需钉回
        # 记录用户可见选区(绝对偏移)：若选区端点落在文档末尾，末尾 insertText 会把该端点
        # (keepPositionOnInsert=False) 一起后移，导致选区"延伸"覆盖刚追加的新数据。插入后按原
        # 绝对偏移恢复，把选区钉死。无选区时跳过(光标在末尾跟随无所谓)，零开销。
        vis_tc = self.txt_recv.textCursor()
        had_sel = vis_tc.hasSelection()
        sel_anchor = vis_tc.anchor() if had_sel else -1
        sel_pos = vis_tc.position() if had_sel else -1
        cursor = QTextCursor(self.txt_recv.document())
        cursor.movePosition(QTextCursor.End)

        prefix = ""
        if force_new_block:
            if not self._txt_ends_with_nl:
                cursor.insertText("\n")
                self._txt_ends_with_nl = True
            if self.sw_show_timestamp.isChecked():
                # 箭头跟时间戳绑一起：时间戳关掉时也不显示，纯数据更干净
                prefix = self._timestamp_prefix(direction)
            if prefix:
                # 时间戳 + 箭头用 ts 灰色（淡化）
                ts_fmt = QTextCharFormat()
                # 时间戳色朝正文 fg 靠拢 40%，提高对比度（原 ts 偏淡看不清）
                ts_fmt.setForeground(QColor(self._role_color(ROLE_TS, theme)))
                ts_fmt.setProperty(ROLE_PROP, ROLE_TS)
                cursor.setCharFormat(ts_fmt)
                cursor.insertText(prefix)
                self._txt_ends_with_nl = False

        # 正文用 body_color；role 可由调用方指定 —— 告警标记这类「我们自己插的说明行」
        # 要用装饰角色(ROLE_TS)，否则会被当成设备发来的 RX 正文参与关键字过滤与统计。
        body_role = role if role is not None else (ROLE_TX if direction == "tx" else ROLE_RX)
        if role is not None:
            body_color = self._role_color(role, theme)
        body_fmt = QTextCharFormat()
        body_fmt.setForeground(QColor(body_color))
        body_fmt.setProperty(ROLE_PROP, body_role)
        if view_mode is None:
            if self._hexdump_on:
                view_mode = VIEW_HEXDUMP
            elif self._numview_on:
                view_mode = VIEW_NUMERIC
            elif self.sw_rx_hex.isChecked():
                view_mode = VIEW_HEX
            else:
                view_mode = VIEW_TEXT
        body_fmt.setProperty(VIEW_PROP, view_mode)
        cursor.setCharFormat(body_fmt)
        first_body_block = cursor.blockNumber()   # 正文插入前块号；正文含 \n 会跨多块（hexdump 多行）
        body_start_pos = cursor.position()         # 正文起始字符位置（供协议高亮做字节→字符映射）
        if runs:
            self._insert_ansi_runs(cursor, text, runs, body_fmt)   # ANSI 着色：按样式分段插
        else:
            cursor.insertText(text)
        if text:
            self._txt_ends_with_nl = text.endswith("\n")

        reset = QTextCharFormat()
        reset.setForeground(QColor(theme["fg"]))
        cursor.setCharFormat(reset)
        # 只有原本就在底部才跟随到最新；用户往上翻看时保持定住
        # 过滤开启时，立即决定刚追加这行的可见性 —— 在滚动到底之前完成，
        # 避免"先显示→滚到底→150ms后异步隐藏→高度收缩跳动"的抖动
        if self._filter_active():
            # 本次插入可能跨多个 block（hexdump 多行块），逐个立即定可见性——只判最后一行会让前几行
            # 短暂错显、要等 150ms 异步重扫才纠正。普通单行文本时循环只跑一次，与原逻辑等价。
            doc = self.txt_recv.document()
            for bn in range(first_body_block, cursor.blockNumber() + 1):
                blk = doc.findBlockByNumber(bn)
                if not blk.isValid():
                    continue
                # 跳过纯装饰 block（时间戳/箭头等 ROLE_TS），只对含 RX/TX 正文的行做过滤。
                # hexdump+时间戳同时开启时，prefix 独占一个 block，与首行 hexdump 不在同块，
                # 若不跳过会因无正文命中而被错误隐藏。
                if not self._block_has_body_role(blk):
                    continue
                vis = self._block_has_keyword_match(blk)
                if blk.isVisible() != vis:
                    blk.setVisible(vis)
                    doc.markContentsDirty(blk.position(), max(1, blk.length()))

        # 恢复用户选区(防末尾插入把选区端点推后、延伸覆盖新数据)。按原绝对偏移重建，钉在插入前位置。
        trimmed = self._trim_recv_overflow()
        if trimmed:
            body_start_pos = max(0, body_start_pos - trimmed)
            if had_sel:
                sel_anchor = max(0, sel_anchor - trimmed)
                sel_pos = max(0, sel_pos - trimmed)

        if had_sel:
            tc = self.txt_recv.textCursor()
            tc.setPosition(sel_anchor)
            tc.setPosition(sel_pos, QTextCursor.KeepAnchor)
            self.txt_recv.setTextCursor(tc)

        # 滚动定位：贴底则跟随到最新；否则钉回插入前的滚动位置——注意 setTextCursor 恢复选区会把视图
        # 滚到选区处，若用户正往上翻看、且选区在下方，会被拽走(表现为"跳到最下边")，故这里显式钉回。
        sb = self.txt_recv.verticalScrollBar()
        if was_at_bottom:
            sb.setValue(sb.maximum())
        else:
            sb.setValue(scroll_before)

        self._schedule_keyword_rebuild()    # 节流重扫关键字高亮(着色)

        self._write_log_block(text, direction, force_new_block, prefix=prefix)

        return body_start_pos    # 正文起始字符位置，供协议高亮做字节→字符映射

    def _write_log_block(self, text: str, direction: str, force_new_block: bool,
                         prefix=None):
        """把一个显示块写入实时日志；日志行尾状态与可见文本区完全独立。"""
        if not self._log_file:
            return
        try:
            pieces = []
            if force_new_block:
                if not getattr(self, "_log_ends_with_nl", True):
                    pieces.append("\n")
                    self._log_ends_with_nl = True
                if self.sw_show_timestamp.isChecked():
                    if prefix is None:
                        prefix = self._timestamp_prefix(direction)
                    if prefix:
                        pieces.append(prefix)
                        self._log_ends_with_nl = False
            pieces.append(text)
            if text:
                self._log_ends_with_nl = text.endswith("\n")
            self._log_file.write("".join(pieces))
            self._log_file.flush()
            self._maybe_rotate_log()    # 超过分包上限则切到下一个文件
        except Exception as e:
            self.toast(self._t("err_log_write", e=e), error=True)
            self._close_log_file()
            self.sw_log_file.setChecked(False)

    # ----- 多条发送：分组数据 + 主界面快捷栏 + 循环 -----
    def _load_ms_groups(self):
        """Load multi-send groups; migrate flat multi_send_items if needed."""
        return _ms_load_groups(
            self.settings.value("multi_send_groups", ""),
            self.settings.value("multi_send_items", ""),
            self._t("kw_default_group"),
        )

    def _save_ms_groups(self):
        self.settings.setValue("multi_send_groups", _ms_groups_json(self._ms_groups))
        self.settings.setValue("multi_send_group_idx", self._ms_group_idx)
        self.settings.remove("multi_send_items")

    def _load_snippets(self):
        """Load send templates; return (list, loaded_ok)."""
        items = _cfg_parse_json_list(self.settings.value("snippets", ""))
        if items is not None:
            return snippets.sanitize_list(items), True
        return snippets.default_snippets(), False

    def _save_snippets(self):
        self.settings.setValue("snippets",
                               json.dumps(self._snippets, ensure_ascii=False))
        self.settings.sync()
        self.settings.sync()

    def _ms_active_items(self):
        return _ms_active_items_fn(self._ms_groups, self._ms_group_idx)

    def _send_ms_item(self, item):
        hx = bool(item.get("hex", False))
        # 多条发送每条独立 hex_mode；走 _send_with_subst 让 {count} 在失败时回滚
        self._send_with_subst(item.get("data", ""), hex_mode=hx,
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
            set_tooltip(btn, item.get("data", ""))
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
        # 循环运行中编辑了条目：实时刷新发送序列，下一轮即用新数据（序列变空则下一步自停）
        if self._ms_cycle_timer.isActive():
            self._ms_cycle_seq = self._build_ms_cycle_seq()

    # ----- 多条发送：循环（按每行延时）-----
    def _build_ms_cycle_seq(self):
        """Checked non-empty items -> cycle send sequence."""
        return _ms_build_cycle_seq(self._ms_active_items())

    def _ms_toggle_cycle(self):
        if self._ms_cycle_timer.isActive():
            self._ms_stop_cycle()
            return
        if self._io_task_busy(exclude=("multi",)):
            self.toast(self._t("io_exclusive_busy"), error=True)
            return
        seq = self._build_ms_cycle_seq()
        if not seq:
            self.toast(self._t("ms_none_checked"), error=True)
            return
        if not self._is_open():
            self.toast(self._t("net_not_open"), error=True)
            return
        self._ms_cycle_seq = seq
        self._ms_cycle_idx = 0
        self._set_ms_cycle_btn(True)
        self._ms_cycle_step()

    def _ms_cycle_step(self):
        if not self._ms_cycle_seq:
            self._ms_stop_cycle()
            return
        if not self._is_open():
            self.toast(self._t("net_not_open"), error=True)
            self._ms_stop_cycle()
            return
        data, hx, nl, cs, delay = self._ms_cycle_seq[self._ms_cycle_idx % len(self._ms_cycle_seq)]
        # 循环路径走 _send_with_subst：替换 + 失败回滚 {count}
        # 发送失败(坏数据/写异常等)立即停止，避免每轮都刷错误 toast
        # (空命令在 _ms_toggle_cycle 构建序列时已过滤，这里的 False 都是真失败)
        if not self._send_with_subst(data, hex_mode=hx, newline=nl, checksum=cs,
                                     record_macro=False):
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

    def open_plot(self):
        """打开数据波形图（单实例，复用并刷新主题/语言）。
        pyqtgraph 懒导入：缺库时只提示、不影响主程序其余功能。"""
        if getattr(self, "_plot_dlg", None) is None:
            try:
                from plot_dialog import PlotDialog
            except Exception as e:
                self.toast(self._t("plot_need_lib", e=e), error=True)
                return
            self._plot_dlg = PlotDialog(self)
        dlg = self._plot_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_script_console(self):
        """打开脚本控制台（单实例，复用并刷新主题/语言）。"""
        if getattr(self, "_script_dlg", None) is None:
            from script_console_dialog import ScriptConsoleDialog
            self._script_dlg = ScriptConsoleDialog(self)
        dlg = self._script_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ----- 脚本控制台：worker 线程 ↔ 主线程桥接 -----
    def _script_send(self, worker, payload: bytes, done, result):
        """worker 线程经信号请求发送（队列连接，本函数在主线程执行）。
        走 _send_text 的 HEX 直发路径：按脚本给的字节原样发，同时进 TX 显示/记录；
        不追加换行、不加校验（脚本自己拼完整帧）。请求携带 worker 身份和完成事件：
        已停止/关闭/换轮的旧 worker 不能把排队数据发到新会话。"""
        if worker is not self._script_worker or worker.stopping():
            done.set()
            return
        remain = getattr(self, "_script_quiet_until", 0.0) - time.monotonic()
        if remain > 0:
            # 不阻塞 GUI；worker 会在 send() 内等完成，同时可被“停止”打断。
            QTimer.singleShot(max(1, int(remain * 1000) + 1),
                              lambda: self._script_send(worker, payload, done, result))
            return
        try:
            result["ok"] = bool(self._send_text(
                bytes(payload).hex(" ").upper(), hex_mode=True, newline=0, checksum=0,
                record_macro=False, allow_during_exclusive=True))
        except Exception as e:
            self.toast(self._t(
                "err_send_failed",
                e=conn_error_tips.format_conn_error_detail(str(e), self._t)),
                error=True)
        finally:
            done.set()

    def _script_begin(self, worker):
        """脚本开跑：接管收流 + 暂停自动应答/Modbus 主机（同自动化序列的独占策略）。"""
        self._script_worker = worker
        self._ar_reset_buf()
        self._ar_generation = getattr(self, "_ar_generation", 0) + 1
        self._ar_sm_pending = None
        self._ar_sm_queue.clear()
        self._ar_sm_draining = False
        self._mbm_sched.stop()
        # 已发出的 Modbus 请求无法撤回。取消其运行态并隔离一个完整响应超时窗；期间脚本
        # send 会等待、RX 会丢弃，避免旧响应污染脚本。结束后 _mbm_tick 按原开关恢复。
        info = self._mbm_inflight
        self._mbm_to.stop()
        self._mbm_inflight = None
        self._mbm_buf = b""
        guard_ms = int(info.get("timeout_ms", self._MBM_TIMEOUT_MS)) if info else 0
        self._script_quiet_until = time.monotonic() + max(0, guard_ms) / 1000.0
        if info is not None and info.get("variant") == "rtu":
            self._mbm_guard_until = max(self._mbm_guard_until, self._script_quiet_until)

    def _script_end(self):
        """脚本结束：释放收流 + 按原开关恢复 Modbus 主机。"""
        self._script_worker = None
        self._script_quiet_until = 0.0
        self._mbm_tick()

    def _script_running(self) -> bool:
        w = getattr(self, "_script_worker", None)
        return w is not None and w.isRunning()

    def _script_active(self) -> bool:
        """worker 已注册即视为占用收发流（含 start 前/结束信号尚未处理的短窗口）。"""
        return getattr(self, "_script_worker", None) is not None

    def _xfer_active(self) -> bool:
        """文件传输 worker 正在运行时独占收发流。"""
        w = getattr(self, "_xfer_worker", None)
        return w is not None and w.isRunning()

    def _io_task_busy(self, exclude=()) -> bool:
        """统一的主动收发任务占用表；所有任务启动入口必须共用，避免互斥条件各写一套后漏项。"""
        excluded = set(exclude)
        states = {
            "script": self._script_active(),
            "sequence": self._seq_running(),
            "transfer": self._xfer_active(),
            "macro": bool(getattr(getattr(self, "_macro", None), "recording", False)),
            "periodic": self.send_timer.isActive(),
            "multi": self._ms_cycle_timer.isActive(),
            "modbus": bool(self._mbm_inflight is not None or self._mbm_active()),
            "replay": bool(getattr(self, "_replay_on", False)),
            "dsl": bool(getattr(self, "_dsl_ops", None)),
            "recording": bool(getattr(getattr(self, "_recorder", None), "recording", False)),
            "device_scan": getattr(self, "_device_scan_state", None) is not None,
        }
        return any(active for name, active in states.items() if name not in excluded)

    def _manual_send_blocked(self, allow_running_dsl=False) -> bool:
        """脚本/序列/文件传输会独占回包，期间禁止其它手动发送插入线路。"""
        return bool(self._script_active() or self._seq_running() or self._xfer_active()
                    or self._mbm_inflight is not None or self._mbm_active()
                    or self._replay_on
                    or (self._dsl_running() and not allow_running_dsl))

    def _script_start_blocked(self) -> bool:
        """脚本不能与其它会主动收发/独占收流的任务并发。Modbus 主机由 _script_begin 暂停。"""
        return self._io_task_busy(exclude=("script", "modbus"))

    def _macro_start_blocked(self) -> bool:
        """宏只录用户交互；已有后台/独占任务时拒绝开始，避免把自动流量误归因。"""
        return self._io_task_busy(exclude=("macro",))

    def _xfer_start_blocked(self) -> bool:
        """文件传输不能与其它主动任务或 Modbus 在途流量并发。"""
        return self._io_task_busy(exclude=("transfer",))

    def _macro_record_tx(self, data):
        """宏录制的 TX 采集判定（唯一入口）：只录「用户手动发」。三类排除——
        脚本自己 send 的（否则录到脚本自身、循环自指）；自动应答/Modbus 从机的回复
        （也走 _send_text，靠 _ar_in_flight 识别，不是用户动作）；未在录制。
        终端模式在 _terminal_send 成功后也调用本入口。抽成方法是为让测试与生产共用同一判定，
        条件改了测试自动跟着变。"""
        if (self._macro.recording and not self._script_running()
                and not self._seq_running() and not self._ar_in_flight):
            self._macro.on_tx(data)

    def _record_stream_tx(self, data, source=None):
        """数据录制的 TX 采集：录线路上真实发出的字节（含自动应答/Modbus 回复，
        因为录的是「线路现场」而非「用户意图」——这点与宏录制相反）。"""
        if self._recorder.recording:
            self._recorder.on_tx(data)
        self._triggers_feed(data, "tx", source=source)  # TCP Server 按发送目标隔离流尾巴

    # ---------------- 触发告警：命中规则 → 响铃 / 托盘通知 / 数据区打标 ----------------
    def _load_triggers(self):
        items = _cfg_parse_json_list(self.settings.value("triggers", ""))
        return triggers.sanitize_list(items or [])

    def _save_triggers(self):
        """落盘 + 让引擎换上新规则（换规则会清命中统计，故调用方已做编辑去抖）。"""
        self.settings.setValue("triggers", json.dumps(self._triggers, ensure_ascii=False))
        self._trigger_engine.set_rules(self._triggers)
        self._refresh_workspace_statuses()
        # 新规则只观察生效后的数据；不能拿旧规则时期留下的半字符/尾巴与下一块拼接。
        self._reset_trigger_decoders()

    def _triggers_feed(self, data, direction, source=None):
        """把一包数据喂给告警引擎并执行命中动作。收发路径都会调，故先做最省的短路判断。"""
        eng = getattr(self, "_trigger_engine", None)
        if eng is None or not eng.active():
            return
        data = bytes(data)
        # 串口/TCP/虚拟连接是连续字节流，需要跨底层回调拼半字符和关键字；UDP/组播
        # 每次回调就是完整数据报，跨报文拼接会制造线路上从未出现过的假关键字。
        carry = getattr(self, "_conn_proto", None) not in (PROTO_UDP, PROTO_UDP_MULTICAST)
        # TCP Server 的每个客户端都有独立字节流；其余协议 source=None，仍按收/发隔离。
        stream_key = (direction, source if getattr(self, "_conn_proto", None) == PROTO_TCP_SERVER
                      else None)
        text = ""
        if eng.needs_text():       # 全是 HEX 规则时不必解码，省掉每包一次 decode
            try:
                text = self._decode_for_triggers(data, stream_key, carry=carry)
                # 剥掉 ANSI 转义再匹配：彩色日志里一行真正的开头是 "I (123)"，
                # 前面那串 \x1b[0;32m 是显示格式不是内容 —— 不剥的话「前缀」和
                # 「^ 锚定的正则」永远命中不了，用户会以为规则写错了。
                pending = self._trg_ansi_pending.get(stream_key, "") if carry else ""
                # 快速通道：绝大多数包根本没有转义符，逐字符解析纯属白跑（这是每包热路径）。
                # 有上一包的残片时仍必须进解析——残片要与本包拼接收尾。
                if pending or "\x1b" in text:
                    runs, _state, pending = ansi.parse(text, pending=pending)
                    text = "".join(piece for piece, _style in runs)
                    if carry:
                        if pending:
                            self._trg_ansi_pending[stream_key] = pending
                        else:
                            self._trg_ansi_pending.pop(stream_key, None)
            except Exception:
                text = ""
        # 跨块回看：串口是字节流，关键字常被底层读操作劈成两半（"ERR" | "OR"）。
        # 拼上一块的尾巴一起匹配，引擎只认「结束位置落在本块内」的命中，故不会重复计数。
        keep = eng.lookback()
        if keep and carry:
            tb = self._trg_tail_bytes.get(stream_key, b"")
            tt = self._trg_tail_text.get(stream_key, "")
            new_data_at, new_text_at = len(tb), len(tt)
            data_all, text_all = tb + data, tt + text
            self._trg_tail_bytes[stream_key] = data_all[-keep:]
            self._trg_tail_text[stream_key] = text_all[-keep:]
        else:
            data_all, text_all, new_data_at, new_text_at = data, text, 0, 0
        # 命中次数与最后命中时间由引擎在计数时一并记（含冷却期内的命中），这里只管执行动作
        for idx, rule in eng.feed(data_all, direction, text_all,
                                  new_data_at=new_data_at, new_text_at=new_text_at):
            self._fire_trigger(idx, rule, direction)

    def _decode_for_triggers(self, data, stream_key, carry=True):
        """触发引擎的增量解码：与数据区**同一套编码规则**（Auto 走 UTF-8 优先 / GBK 回退），
        但用自己的缓冲。

        为什么不直接复用 _decode_rx：①它的缓冲属于显示路径，共享会互相吃掉对方留存的半个
        多字节字符；②触发要在 HEX / 转储 / 数值 等**任何显示模式**下都能按文本匹配，不能
        绑在文本显示那条路上。每条来源流各持一份状态 —— 混用会让不同客户端或 RX/TX
        的半个字符拼在一起，两边都乱。UDP 数据报 carry=False，每包独立解码。"""
        if not isinstance(stream_key, tuple):  # 兼容内部测试/旧调用传 "rx"、"tx"
            stream_key = (stream_key, None)
        bufs = self._trg_dec_buf
        codec = self._get_codec()
        if not carry:
            if codec == "auto":
                text, _unused = self._decode_auto_chunk(b"", data)
                return text
            try:
                return data.decode(codec, errors="replace")
            except LookupError:
                return data.decode("latin-1")
        if codec != "auto":
            dec = self._trg_dec.get(stream_key)
            if dec is None or self._trg_dec_codec != codec:
                if self._trg_dec_codec != codec:
                    self._trg_dec.clear()          # 换了编码：旧解码器的残留字节按新编码无意义
                    self._trg_dec_codec = codec
                try:
                    dec = codecs.getincrementaldecoder(codec)(errors="replace")
                except LookupError:
                    return data.decode("latin-1")  # 同 _decode_rx 的兜底
                self._trg_dec[stream_key] = dec
            return dec.decode(data, final=False)
        text, bufs[stream_key] = self._decode_auto_chunk(bufs.get(stream_key, b""), data)
        return text

    def _reset_trigger_decoders(self):
        """数据流断点 / 换编码：旧的半个字符与跨块尾巴对新数据都没意义，清掉重来。"""
        self._trg_dec_buf = {}
        self._trg_dec = {}
        self._trg_dec_codec = None
        self._trg_ansi_pending = {}
        self._trg_tail_bytes = {}
        self._trg_tail_text = {}

    def _fire_trigger(self, idx, rule, direction):
        """执行一条命中规则的动作。任一动作出错都不该影响其余动作与收包主流程。"""
        name = rule.get("name") or rule.get("pattern") or self._t("trg_unnamed")
        if rule.get("beep", True):
            try:
                QApplication.beep()
            except Exception:
                _log.debug("trigger beep failed", exc_info=True)
        if rule.get("notify", True):
            msg = self._t("trg_fired", name=name, dir=direction.upper())
            # 托盘通知是「人不在场」的主要送达方式；没有托盘（部分 Linux 桌面）退回状态栏提示
            shown = False
            if self._tray is not None:
                try:
                    self._tray.showMessage(self._t("trg_notify_title"), msg,
                                           QSystemTrayIcon.Warning, 5000)
                    shown = True
                except Exception:
                    shown = False
            if not shown:
                self.toast(msg, error=True)
        if rule.get("mark", False):
            # 数据区打标：单独起一行，用装饰角色(ROLE_TS) —— 这是我们自己插的说明，
            # 不是设备发来的数据，不该参与关键字过滤 / 被当成 RX 正文。
            try:
                marker = "⚠ %s %s" % (self._t("trg_mark_prefix"), name)
                if self._terminal_on:
                    # 终端渲染维护自己的光标，普通 append 不会更新它；直接插标记会让下一包
                    # 回到旧光标覆盖标记。标记独占一行并把终端光标移到其后。
                    shown = self.txt_recv.toPlainText()
                    decorated = ("" if not shown or shown.endswith("\n") else "\n")
                    decorated += marker + "\n"
                    self._append_block_data(decorated, direction="rx",
                                            force_new_block=False,
                                            view_mode=VIEW_TERMINAL, role=ROLE_TS)
                    self._term_pos = self.txt_recv.document().characterCount() - 1
                else:
                    self._append_block_data(marker, direction="rx",
                                            force_new_block=True, role=ROLE_TS)
                self._last_direction = None      # 标记行不属于收发流，别让下一包接着它续行
            except Exception:
                _log.debug("trigger mark failed", exc_info=True)

        hits = 0
        try:
            hits = int(self._trigger_engine.hits(idx))
        except Exception:
            hits = 0
        if rule.get("webhook") and (rule.get("webhook_url") or "").strip():
            self._trg_run_webhook(rule, name, direction, hits)
        if rule.get("run_cmd_on") and (rule.get("run_cmd") or "").strip():
            self._trg_run_cmd(rule, name, direction, hits)

    @staticmethod
    def _is_private_url(url):
        """True if URL host is private/loopback/link-local."""
        return _trg_is_private_url(url)

    def _trg_run_webhook(self, rule, name, direction, hits):
        """POST a small JSON payload; never block the GUI thread."""
        url = (rule.get("webhook_url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return
        # SSRF 防护：拒绝私有/回环地址，避免配置文件被用来探测内网
        if self._is_private_url(url):
            return
        payload = {
            "name": name,
            "direction": direction,
            "hits": hits,
            "pattern": rule.get("pattern") or "",
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        def _worker():
            try:
                import urllib.request
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data, method="POST",
                    headers={"Content-Type": "application/json",
                             "User-Agent": "CommTool-Trigger/1.0"})
                urllib.request.urlopen(req, timeout=5).read(256)
            except Exception:
                _log.debug("trigger webhook failed", exc_info=True)

        self._trg_spawn_action(_worker)

    @staticmethod
    def _trg_shell_value(value):
        """Quote a placeholder value so it stays shell-inert text."""
        return _trg_shell_quote(value)

    def _trg_run_cmd(self, rule, name, direction, hits):
        """Launch an external program with simple placeholder expansion."""
        raw = (rule.get("run_cmd") or "").strip()
        if not raw:
            return
        q = self._trg_shell_value
        cmd = (raw.replace("{name}", q(name))
                  .replace("{hits}", q(hits))
                  .replace("{dir}", q(direction))
                  .replace("{pattern}", q(rule.get("pattern") or "")))

        def _worker():
            with self._trg_action_lock:
                if self._trg_stopping:
                    return              # 正在退出，不再拉新进程
                self._trg_launching += 1
            proc = None
            import subprocess
            try:
                kwargs = {"shell": True}
                if sys.platform == "win32":
                    kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                else:
                    # 自成进程组：shell=True 下真正干活的是孙进程，按组才收得干净
                    kwargs["start_new_session"] = True
                proc = subprocess.Popen(cmd, **kwargs)
            except Exception:
                _log.debug("run_cmd launch failed", exc_info=True)
            finally:
                kill_after_register = False
                with self._trg_action_lock:
                    # 登记必须排在放开占位之前：_trg_stop_procs 等的就是这个次序，
                    # 否则它可能在句柄入表前就扫完走人，把进程漏在系统里。
                    if proc is not None:
                        if self._trg_stopping:
                            # _trg_stop_procs 可能已经扫完并返回；退出态下不能再把
                            # 句柄放进无人回收的集合，登记后由当前 worker 直接收掉。
                            kill_after_register = True
                        else:
                            self._trg_procs.add(proc)
                    self._trg_launching -= 1
            if proc is None:
                return
            if kill_after_register:
                self._trg_kill_proc(proc)
                return
            try:
                # 必须等子进程退出：Popen 启动即返回，不等的话这个线程几微秒就结束并
                # 把名额还回去，_TRG_MAX_ACTIONS 就只限制「同时在启动中的动作数」，
                # 冷却设 0 时子进程仍可无限堆积。顺带回收 POSIX 上的僵尸进程。
                proc.wait(timeout=self._TRG_CMD_TIMEOUT)
            except subprocess.TimeoutExpired:
                # 挂死的命令会永久占着一个并发名额，_TRG_MAX_ACTIONS 个全卡住就等于
                # 这个功能废了。到点按整组收掉：宁可打断也不留死槽——反正退出时
                # 这些子进程也一律被回收，本来就不能活得比 CommTool 长。
                _log.debug("run_cmd exceeded %ss, killing pid %s",
                           self._TRG_CMD_TIMEOUT, proc.pid)
                self._trg_kill_proc(proc)
            except Exception:
                _log.debug("run_cmd wait failed", exc_info=True)
            finally:
                with self._trg_action_lock:
                    self._trg_procs.discard(proc)

        self._trg_spawn_action(_worker)

    @staticmethod
    def _trg_kill_proc(proc):
        """结束一个外部程序动作。

        run_cmd 用 shell=True 启动，句柄指向的是 shell 本身，只 terminate()
        会把真正干活的孙进程留下，所以两边都按整组（树）收：Windows
        走 taskkill /T，POSIX 走 killpg（worker 用 start_new_session 让 shell 成组长）。
        """
        import subprocess
        if sys.platform == "win32":
            if proc.pid:
                try:
                    result = subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True, timeout=5)
                    if result.returncode == 0 or proc.poll() is not None:
                        return
                    _log.debug("taskkill returned %s for pid %s",
                               result.returncode, proc.pid)
                except Exception:
                    _log.debug("taskkill failed for pid %s", proc.pid, exc_info=True)
        else:
            import signal
            if proc.pid:
                # Windows 的 signal 没有 SIGKILL，这段平时不走但不能因此招 AttributeError
                try:
                    # 组长退出后 os.getpgid() 会失败，但后代仍用它的 PID 当 PGID，
                    # 所以直接拿 proc.pid 当组号用。
                    os.killpg(proc.pid, getattr(signal, "SIGTERM", 15))
                except Exception:
                    _log.debug("killpg SIGTERM failed for pid %s", proc.pid,
                               exc_info=True)  # 没成组 → 走通用路径
                else:
                    try:
                        proc.wait(timeout=0.5)
                    except Exception:
                        _log.debug("process group leader did not exit after SIGTERM",
                                   exc_info=True)
                    try:
                        # 父 shell 可能已经退出，但它的后代仍留在同一进程组；
                        # 无条件补 SIGKILL，只有进程组已消失时才算完成。
                        os.killpg(proc.pid, getattr(signal, "SIGKILL", 9))
                    except ProcessLookupError:
                        return
                    except Exception:
                        _log.debug("killpg SIGKILL failed for pid %s", proc.pid,
                                   exc_info=True)
                    else:
                        try:
                            proc.wait(timeout=1)
                        except Exception:
                            _log.debug("process group leader did not exit after SIGKILL",
                                       exc_info=True)
                        return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                _log.debug("cannot kill pid %s", proc.pid, exc_info=True)

    _TRG_CMD_TIMEOUT = 30.0       # 单个外部程序动作的最长存活时间
    _TRG_STOP_WAIT = 2.0          # 等在途启动收尾的上限

    def _trg_stop_procs(self):
        """退出前终止仍在跑的外部程序动作；一旦调用就不再放行新动作。

        动作 worker 是 daemon 线程，解释器退出时会被直接掉掉，但它拉起的
        是独立的 OS 进程：不主动收的话，命令跑得久或卡死时，CommTool 关了
        它们还在系统里。

        Popen 返回到句柄登记之间有个窗口，只扫一遍 _trg_procs 会漏掉正好落在
        窗口里的进程。所以先竖 _trg_stopping 挡住后续动作，再等已在途的启动
        登记完毕。等的只是 Popen 本身，不是命令的执行，所以是有界的。
        """
        deadline = time.monotonic() + self._TRG_STOP_WAIT
        while True:
            with self._trg_action_lock:
                self._trg_stopping = True
                launching = self._trg_launching
                procs, self._trg_procs = list(self._trg_procs), set()
            for proc in procs:
                if proc.poll() is None:
                    self._trg_kill_proc(proc)
            if not launching or time.monotonic() >= deadline:
                return
            time.sleep(0.01)

    def _trg_dropped_actions(self):
        """因并发上限被丢弃的动作次数。计数器由工作线程递增，读写都走锁。"""
        with self._trg_action_lock:
            return self._trg_action_dropped

    def _trg_reset_dropped(self):
        with self._trg_action_lock:
            self._trg_action_dropped = 0

    def _trg_spawn_action(self, worker):
        """Run a trigger action off the GUI thread, capped in flight.

        Cooldown may be set to 0, so a busy link would otherwise spawn one
        thread -- and for run_cmd one process -- per matching packet.

        A slot stays taken for the whole action: the webhook worker blocks on
        the HTTP round-trip and the run_cmd worker waits on the child, so the
        cap bounds live processes rather than just launch calls.
        """
        with self._trg_action_lock:
            if self._trg_stopping:
                return False      # 退出中：不算丢弃，就是不再开新工
            if self._trg_action_busy >= self._TRG_MAX_ACTIONS:
                self._trg_action_dropped += 1
                return False
            self._trg_action_busy += 1

        def _run():
            try:
                worker()
            except Exception:
                _log.debug("trigger action failed", exc_info=True)
            finally:
                with self._trg_action_lock:
                    self._trg_action_busy = max(0, self._trg_action_busy - 1)

        try:
            threading.Thread(target=_run, daemon=True).start()
            return True
        except Exception:
            with self._trg_action_lock:
                self._trg_action_busy = max(0, self._trg_action_busy - 1)
            return False

    def open_triggers(self):
        """打开触发告警对话框（单实例、非模态）。"""
        dlg = getattr(self, "_triggers_dlg", None)
        if dlg is None:
            from triggers_dialog import TriggersDialog
            dlg = TriggersDialog(self)
            self._triggers_dlg = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _replay_inject_target(self):
        """回放的注入落点：只有虚拟连接能接受「收到的数据」注入。
        往真实串口/网络注入 RX 在物理上不成立，返回 None 让调用方明确拒绝。"""
        conn = self.conn
        if isinstance(conn, VirtualConn) and conn.is_open:
            return conn.inject
        return None

    def _replay_begin(self):
        self._replay_on = True

    def _replay_end(self):
        self._replay_on = False

    def open_rec_replay(self):
        """打开数据录制 / 回放（单实例，复用并刷新主题/语言）。"""
        if getattr(self, "_rr_dlg", None) is None:
            from rec_replay_dialog import RecReplayDialog
            self._rr_dlg = RecReplayDialog(self)
        dlg = self._rr_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_rec_diff(self):
        """打开会话比较（单实例，复用并刷新主题/语言）。

        纯离线工具：只读两个 .ctrec 文件、不碰连接，因此不进 _io_task_busy 占用表。
        """
        if getattr(self, "_rd_dlg", None) is None:
            from rec_diff_dialog import RecDiffDialog
            self._rd_dlg = RecDiffDialog(self)
        dlg = self._rd_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_snippets(self):
        """打开发送模板库（单实例，复用并刷新主题/语言）。

        取用时把模板填入发送框、由用户或「发送」按钮走正常发送路径，本身不占收发流，
        故不进 _io_task_busy 占用表。
        """
        if getattr(self, "_snip_dlg", None) is None:
            from snippets_dialog import SnippetsDialog
            self._snip_dlg = SnippetsDialog(self)
        dlg = self._snip_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()


    def open_send_history(self):
        """Open send-history search picker (full-text filter + refill)."""
        if getattr(self, "_send_hist_dlg", None) is None:
            from send_history_dialog import SendHistoryDialog
            self._send_hist_dlg = SendHistoryDialog(self)
        dlg = self._send_hist_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg._reload()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()


    # ----- connection presets -----
    def _load_connection_presets(self):
        raw = self.settings.value("connection_presets", "")
        if isinstance(raw, list):
            return connection_presets.sanitize_list(raw), True
        items = _cfg_parse_json_list(raw)
        if items is not None:
            return connection_presets.sanitize_list(items), True
        return [], False

    def _save_connection_presets(self):
        self.settings.setValue(
            "connection_presets",
            json.dumps(self._connection_presets, ensure_ascii=False))
        self.settings.sync()

    def _rebuild_connection_preset_combo(self, select_id=None):
        if not hasattr(self, "cb_conn_preset"):
            return
        keep = select_id
        if keep is None:
            keep = self.cb_conn_preset.currentData()
        self.cb_conn_preset.blockSignals(True)
        self.cb_conn_preset.clear()
        self.cb_conn_preset.addItem(self._t("cpreset_none"), None)
        for p in connection_presets.sort_by_recent(self._connection_presets):
            self.cb_conn_preset.addItem(connection_presets.display_label(p), p.get("id"))
        idx = 0
        if keep:
            found = self.cb_conn_preset.findData(keep)
            if found >= 0:
                idx = found
        self.cb_conn_preset.setCurrentIndex(idx)
        self.cb_conn_preset.blockSignals(False)

    def _on_connection_preset_activated(self, index):
        pid = self.cb_conn_preset.itemData(index) if index >= 0 else None
        if not pid:
            return
        self.apply_connection_preset(pid)

    def _capture_connection_fields(self):
        return connection_presets.capture_fields({
            "net_proto": self.cb_proto.currentText(),
            "ser_port": self.cb_port.currentData() or "",
            "ser_baud": self.cb_baud.currentText(),
            "ser_databits": self.cb_databits.currentText(),
            "ser_parity": self.cb_parity.currentText(),
            "ser_stopbits": self.cb_stopbits.currentText(),
            "ser_flow": self.cb_flow.currentText(),
            "serial_dtr": self.settings.value("serial_dtr", True, type=bool),
            "serial_rts": self.settings.value("serial_rts", True, type=bool),
            "net_local_ip": self.cb_local_ip.currentText(),
            "net_local_port": self.ed_local_port.text(),
            "net_remote_ip": self.ed_remote_ip.text(),
            "net_remote_port": self.ed_remote_port.text(),
            "net_use_remote": self.sw_udp_remote.isChecked(),
            "net_group_addr": self.ed_group.text(),
            "vconn_loopback": self.sw_vconn_loop.isChecked(),
            "auto_reconnect": self.settings.value("auto_reconnect", True, type=bool),
        })

    def _apply_connection_fields(self, fields):
        fields = connection_presets.capture_fields(fields)
        proto = fields.get("net_proto") or PROTO_SERIAL
        idx = self.cb_proto.findText(proto)
        if idx >= 0:
            self.cb_proto.setCurrentIndex(idx)
        else:
            self.cb_proto.setCurrentText(proto)

        def set_combo_text(cb, value):
            opts = [cb.itemText(i) for i in range(cb.count())]
            decision = _cfg_resolve_combo(value, opts, editable=cb.isEditable())
            if decision is None:
                return
            kind, payload = decision
            if kind == "index":
                cb.setCurrentIndex(payload)
            else:
                cb.setCurrentText(payload)

        set_combo_text(self.cb_baud, fields.get("ser_baud"))
        set_combo_text(self.cb_databits, fields.get("ser_databits"))
        set_combo_text(self.cb_parity, fields.get("ser_parity"))
        set_combo_text(self.cb_stopbits, fields.get("ser_stopbits"))
        set_combo_text(self.cb_flow, fields.get("ser_flow"))
        port = fields.get("ser_port") or ""
        if port:
            self._serial_empty_selection = False
            self._pending_restore_port = port
            self._select_serial_device(port)
        else:
            # Empty ser_port in preset must clear the previous COM selection.
            self._serial_empty_selection = True
            self._pending_restore_port = None
            ports = list(getattr(self, "_last_port_list", None) or [])
            if not ports:
                ports = [(self.cb_port.itemData(i), self.cb_port.itemText(i))
                         for i in range(self.cb_port.count())]
            self._populate_port_combo(ports, keep_device="", allow_placeholder=True)
        self.cb_local_ip.setCurrentText(str(fields.get("net_local_ip") or ""))
        self.ed_local_port.setText(str(fields.get("net_local_port") or ""))
        self.ed_remote_ip.setText(str(fields.get("net_remote_ip") or ""))
        self.ed_remote_port.setText(str(fields.get("net_remote_port") or ""))
        self.sw_udp_remote.setChecked(bool(fields.get("net_use_remote")), animate=False)
        self.ed_group.setText(str(fields.get("net_group_addr") or ""))
        self.sw_vconn_loop.setChecked(bool(fields.get("vconn_loopback")), animate=False)
        self.settings.setValue("serial_dtr", bool(fields.get("serial_dtr", True)))
        self.settings.setValue("serial_rts", bool(fields.get("serial_rts", True)))
        self.settings.setValue("auto_reconnect", bool(fields.get("auto_reconnect", True)))
        if hasattr(self, "sw_dtr"):
            self.sw_dtr.setChecked(bool(fields.get("serial_dtr", True)), animate=False)
        if hasattr(self, "sw_rts"):
            self.sw_rts.setChecked(bool(fields.get("serial_rts", True)), animate=False)
        self._update_net_fields()

    def apply_connection_preset(self, preset_id):
        if self.conn is not None:
            self.toast(self._t("cpreset_need_close"), error=True)
            # Do not keep the rejected item selected; fall back to placeholder.
            if hasattr(self, "cb_conn_preset"):
                self.cb_conn_preset.blockSignals(True)
                self.cb_conn_preset.setCurrentIndex(0)
                self.cb_conn_preset.blockSignals(False)
            return False
        preset = connection_presets.find_by_id(self._connection_presets, preset_id)
        if preset is None:
            self.toast(self._t("cpreset_missing"), error=True)
            return False
        self._apply_connection_fields(preset)
        self._connection_presets, touched = connection_presets.touch_last_used(
            self._connection_presets, preset_id)
        if touched is not None:
            self._save_connection_presets()
        self._rebuild_connection_preset_combo(select_id=preset_id)
        # MRU reorder invalidates dialog list UserRole indices; refresh by id.
        dlg = getattr(self, "_cpreset_dlg", None)
        if dlg is not None:
            dlg._reload_list(keep_id=preset_id)
        self.toast(self._t("cpreset_applied", name=preset.get("name", "")))
        return True

    def save_connection_preset_from_ui(self, prompt_name=True, name=None, note=""):
        from PyQt5.QtWidgets import QInputDialog
        fields = self._capture_connection_fields()
        if prompt_name and not name:
            cur_id = self.cb_conn_preset.currentData() if hasattr(self, "cb_conn_preset") else None
            default_name = ""
            if cur_id:
                cur = connection_presets.find_by_id(self._connection_presets, cur_id)
                if cur:
                    default_name = cur.get("name", "")
            dlg = QInputDialog(self)
            dlg.setWindowTitle(self._t("cpreset_save_title"))
            dlg.setLabelText(self._t("cpreset_save_prompt"))
            dlg.setTextValue(default_name or self._t("cpreset_new_name"))
            dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
            ok = dlg.exec_() == QInputDialog.Accepted
            name = dlg.textValue()
            if not ok:
                return None
            name = (name or "").strip()
            if not name:
                self.toast(self._t("cpreset_name_empty"), error=True)
                return None
        name = (name or self._t("cpreset_new_name")).strip()
        existing = None
        for p in self._connection_presets:
            if p.get("name") == name:
                existing = p
                break
        if existing is not None:
            preset = dict(existing)
            preset.update(fields)
            if note:
                preset["note"] = note
            preset["name"] = name
        else:
            if len(self._connection_presets) >= connection_presets.MAX_PRESETS:
                self.toast(self._t("cpreset_full", n=connection_presets.MAX_PRESETS), error=True)
                return None
            preset = connection_presets.make_preset(name, fields, note=note or "")
        try:
            self._connection_presets, _ = connection_presets.upsert(
                self._connection_presets, preset)
        except ValueError:
            self.toast(self._t("cpreset_full", n=connection_presets.MAX_PRESETS), error=True)
            return None
        self._save_connection_presets()
        self._rebuild_connection_preset_combo(select_id=preset.get("id"))
        if getattr(self, "_cpreset_dlg", None) is not None:
            self._cpreset_dlg.reload_cfg()
        self.toast(self._t("cpreset_saved", name=name))
        return preset

    def open_connection_presets(self):
        if getattr(self, "_cpreset_dlg", None) is None:
            from connection_presets_dialog import ConnectionPresetsDialog
            self._cpreset_dlg = ConnectionPresetsDialog(self)
        dlg = self._cpreset_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.reload_cfg()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_dashboard(self):
        """打开数值仪表盘（单实例，复用并刷新主题/语言）。"""
        if getattr(self, "_dash_dlg", None) is None:
            from dashboard_dialog import DashboardDialog
            self._dash_dlg = DashboardDialog(self)
        dlg = self._dash_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_frame_parse(self):
        """打开协议帧解析表（单实例，复用并刷新主题/语言）。"""
        if getattr(self, "_frame_dlg", None) is None:
            from frame_dialog import FrameParseDialog
            self._frame_dlg = FrameParseDialog(self)
        dlg = self._frame_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.sync_highlight()      # 勾选态跟随主窗当前 _proto_hl_on
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ----- 自动应答 -----
    def open_auto_reply(self):
        """打开自动应答配置（单实例，复用并刷新主题/语言）。"""
        if getattr(self, "_ar_dlg", None) is None:
            from auto_reply_dialog import AutoReplyDialog
            self._ar_dlg = AutoReplyDialog(self)
        dlg = self._ar_dlg
        if dlg._save_timer.isActive():
            dlg._commit()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _ar_btn_clicked(self):
        """自动应答按钮单击：延 doubleClickInterval 后打开对话框；若双击则被取消。
        Qt 双击会发 click→dblclick→click 三个信号，第二个 clicked 距上次过近时忽略，
        避免双击触发后又重启 timer 导致 dialog 还是被打开。"""
        now = time.monotonic()
        iv = QApplication.doubleClickInterval() / 1000.0
        if now - self._ar_last_click < iv:
            return
        self._ar_last_click = now
        self._ar_click_timer.start(QApplication.doubleClickInterval())

    def _ar_btn_dbl_clicked(self):
        """自动应答按钮双击：cancel 延时 timer + 翻转总开关（不打开对话框）。"""
        self._ar_click_timer.stop()
        self._toggle_ar_on()

    def _toggle_ar_on(self):
        """翻转自动应答总开关：落盘 + 按钮高亮刷新 + 同步对话框 checkbox（若开着）+ toast。"""
        new_value = not self._ar_on
        self._set_autoreply_enabled(new_value)
        self.toast(self._t("ar_toast_on" if self._ar_on else "ar_toast_off"))

    def _set_autoreply_enabled(self, enabled):
        """设置自动应答总开关；开启时关闭 Modbus 主机，保证状态与实际执行一致。"""
        enabled = bool(enabled)
        if enabled and getattr(self, "_device_scan_state", None) is not None:
            self.toast(self._t("io_exclusive_busy"), error=True)
            if getattr(self, "_ar_dlg", None) is not None:
                cb = self._ar_dlg.cb_enable
                cb.blockSignals(True)
                cb.setChecked(bool(self._ar_on))
                cb.blockSignals(False)
            return
        if enabled and getattr(self, "_mbm_on", False):
            self._set_mbm_enabled(False)
        self._ar_on = enabled
        self.settings.setValue("autoreply_on", enabled)
        self._ar_reset_buf()        # 切换瞬间清掉半截组装缓冲，防止下次开启时旧字节被新规则吃
        self._ar_reset_state()      # C8：总开关切换=重新开始 → 状态机回到初始
        self._update_autoreply_btn()
        if getattr(self, "_ar_dlg", None) is not None:
            cb = self._ar_dlg.cb_enable
            cb.blockSignals(True)
            cb.setChecked(self._ar_on)
            cb.blockSignals(False)
        self._refresh_workspace_statuses()

    def _set_mbm_enabled(self, enabled):
        """设置主机轮询总开关；开启时关闭自动应答，避免两个引擎争用同一接收流。"""
        enabled = bool(enabled)
        scan_state = getattr(self, "_device_scan_state", None)
        if scan_state is not None:
            self.toast(self._t("io_exclusive_busy"), error=True)
            if getattr(self, "_mbm_dlg", None) is not None:
                cb = self._mbm_dlg.cb_enable
                cb.blockSignals(True)
                cb.setChecked(bool(scan_state["old_on"]))
                cb.blockSignals(False)
            return
        if enabled and (self.send_timer.isActive() or self._ms_cycle_timer.isActive()):
            self.toast(self._t("io_exclusive_busy"), error=True)
            if getattr(self, "_mbm_dlg", None) is not None:
                cb = self._mbm_dlg.cb_enable
                cb.blockSignals(True)
                cb.setChecked(bool(self._mbm_on))
                cb.blockSignals(False)
            return
        if enabled and self._ar_on:
            self._set_autoreply_enabled(False)
        self._mbm_on = enabled
        self.settings.setValue("modbus_master_on", enabled)
        self.settings.sync()
        if getattr(self, "_mbm_dlg", None) is not None:
            cb = self._mbm_dlg.cb_enable
            cb.blockSignals(True)
            cb.setChecked(enabled)
            cb.blockSignals(False)
        self._mbm_restart()
        self._refresh_workspace_statuses()

    def _update_autoreply_btn(self):
        """自动应答开启时高亮「自动应答」按钮（动态属性 arActive + 重新 polish 生效）。"""
        if not hasattr(self, "btn_autoreply"):
            return
        self.btn_autoreply.setProperty("arActive", "true" if self._ar_on else "false")
        self.btn_autoreply.style().unpolish(self.btn_autoreply)
        self.btn_autoreply.style().polish(self.btn_autoreply)

    def _sync_autoreply_ui(self):
        """同步自动应答控件，不修改持久化设置。"""
        self._update_autoreply_btn()
        dlg = getattr(self, "_ar_dlg", None)
        cb = getattr(dlg, "cb_enable", None) if dlg is not None else None
        if cb is not None:
            cb.blockSignals(True)
            cb.setChecked(bool(self._ar_on))
            cb.blockSignals(False)

    # ================= 自动化测试序列（send → 等回包匹配 → 通过/失败） =================
    def _load_seq_rules(self):
        """Load sequence step list from settings."""
        items = _cfg_parse_json_list(self.settings.value("sequence_rules", ""))
        return items if items is not None else []

    def _seq_running(self):
        return getattr(self, "_seq_on", False)

    def _seq_pause_peer_engines(self):
        """序列独占收发流前，作废自动应答旧任务并暂停 Modbus 主机调度；不改持久化开关。"""
        # 已排程的延迟/多段自动应答会在未来直接发送，必须用代际使其永久失效。
        self._ar_reset_buf()
        self._ar_generation = getattr(self, "_ar_generation", 0) + 1
        self._ar_sm_pending = None
        self._ar_sm_queue.clear()
        self._ar_sm_draining = False

        # 已经发出的 Modbus 请求无法撤回。若有在途请求，保留 inflight/超时 timer，并在序列第 0 步
        # 启动前继续把收包交给 Modbus；正常响应后立即释放，RTU 超时则沿用原有迟到响应隔离窗口。
        info = self._mbm_inflight
        self._seq_waiting_mbm = info is not None
        self._seq_wait_mbm_variant = (str(info.get("variant", "")) if info is not None else "")
        self._seq_wait_mbm_until = 0.0
        self._mbm_sched.stop()
        if info is None:
            self._mbm_to.stop()
            self._mbm_buf = b""
        elif not self._mbm_to.isActive():
            # 防御损坏/测试配置：有 inflight 却没有超时 timer 时不能让序列永久等住。
            timeout_ms = max(1, int(info.get("timeout_ms", self._MBM_TIMEOUT_MS)))
            self._mbm_to.start(min(timeout_ms, self._MBM_QTIMER_MAX_MS))

    def _seq_mbm_release_check(self, gen=None):
        """在途 Modbus 已结束后，等迟到响应隔离期彻底结束，再启动序列第 0 步。"""
        if gen is None:
            gen = self._seq_gen
        if (not self._seq_on or gen != self._seq_gen
                or not getattr(self, "_seq_waiting_mbm", False)):
            return
        if self._mbm_inflight is not None:       # 仍在正常等响应/超时，由 Modbus 回调再次触发本检查
            return
        deadline = self._seq_wait_mbm_until
        if self._seq_wait_mbm_variant in ("rtu", "ascii"):
            deadline = max(deadline, self._mbm_guard_until)
        remain = deadline - time.monotonic()
        if remain > 0:
            delay = min(self._MBM_QTIMER_MAX_MS, max(1, int(remain * 1000) + 1))
            QTimer.singleShot(delay, lambda: self._seq_mbm_release_check(gen))
            return
        self._seq_waiting_mbm = False
        self._seq_wait_mbm_variant = ""
        self._seq_wait_mbm_until = 0.0
        self._seq_round_t0 = time.monotonic()   # Modbus 隔离结束、真正开跑：本轮计时从此刻起（不含隔离等待）
        self._seq_run_from(0)

    def _seq_resume_peer_engines(self):
        """序列释放收发流后，按原开关/连接状态恢复 Modbus 主机。"""
        if not self._seq_on:
            self._mbm_tick()

    def open_sequence(self):
        """打开自动化序列对话框（单实例，复用并刷新主题/语言）。"""
        if self._seq_dlg is None:
            from dialogs import SequenceDialog
            self._seq_dlg = SequenceDialog(self)
        dlg = self._seq_dlg
        dlg.reload_rows()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_frame_builder(self):
        """打开帧构造器对话框（单实例，复用并刷新主题/语言）。"""
        if self._frame_builder_dlg is None:
            from frame_builder_dialog import FrameBuilderDialog
            self._frame_builder_dlg = FrameBuilderDialog(self)
        dlg = self._frame_builder_dlg
        dlg.reload_rows()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _fb_fill_send(self, hexs):
        """帧构造器「填入发送框」：把 HEX 填进主发送框并置 HEX 发送态。"""
        self.sw_tx_hex.setChecked(True)
        self.txt_send.setPlainText(hexs)
        self.toast(self._t("fb_filled"))

    def open_toolbox(self):
        """打开工具箱（进制/编码转换 + 校验计算；单实例，复用并刷新主题/语言）。"""
        if self._toolbox_dlg is None:
            from toolbox_dialog import ToolboxDialog
            self._toolbox_dlg = ToolboxDialog(self)
        dlg = self._toolbox_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_bridge(self):
        """打开桥接转发（A/B 两端任意 串口/TCP/UDP 双向透传；单实例，复用并刷新主题/语言）。"""
        if self._bridge_dlg is None:
            from bridge_dialog import BridgeDialog
            self._bridge_dlg = BridgeDialog(self)
        dlg = self._bridge_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_xfer(self):
        """打开文件传输（XMODEM/XMODEM-1K/YMODEM 收发；单实例，复用并刷新主题/语言）。"""
        if self._xfer_dlg is None:
            from xfer_dialog import XferDialog
            self._xfer_dlg = XferDialog(self)
        dlg = self._xfer_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ----- 文件传输 ⇄ 连接层桥接（对话框调） -----
    def _xfer_attach(self, worker):
        """传输开始：主窗接管收流并把 worker 的发送经 GUI 线程转到 conn.send。"""
        if self._xfer_worker is not None:
            self._xfer_detach()                          # 防御：先断掉可能残留的上一个 worker 的发送桥，避免两个 worker 同时发数据
        self._xfer_worker = worker
        self._xfer_target = self._send_target()          # 起始时捕获目标（串口为 None）
        worker.sig_send.connect(self._xfer_send)
        # 暂停 Modbus 定时器：传输期间收流喂协议引擎，Modbus 响应进不来；在途请求的定时器
        # 也会误触发超时——清掉 inflight，待传输结束再恢复。
        if hasattr(self, "_mbm_to"):
            self._mbm_to.stop()
        if hasattr(self, "_mbm_sched"):
            self._mbm_sched.stop()
        self._mbm_inflight = None
        self._mbm_buf = b""

    def _xfer_detach(self):
        """传输结束：断开发送桥、恢复正常收流、恢复 Modbus 轮询（不清结果，只重启调度）。"""
        w = self._xfer_worker
        if w is not None:
            try:
                w.sig_send.disconnect(self._xfer_send)
            except (TypeError, RuntimeError):
                pass
        self._xfer_worker = None
        if hasattr(self, "_mbm_tick"):
            self._mbm_tick()           # 恢复 Modbus 轮询（若已启用）；不调 _mbm_restart 避免清掉已有结果

    def _xfer_send(self, data):
        """worker 线程经队列信号回到 GUI 线程发字节（连接可能已断，兜底不崩）。"""
        if self.conn is not None:
            payload = bytes(data)
            try:
                sent = self.conn.send(payload, self._xfer_target)
            except Exception:
                return
            # 录制与 TX 告警描述的是线路上真实发出的字节；无目标、零写或短写都不能
            # 把整块登记为成功。TCP Client 半帧还要沿用普通发送路径的断流保护。
            if sent == SEND_NO_TARGET or sent != len(payload):
                self._abort_partial_tcp_stream(sent, len(payload))
                return
            # 文件传输同样绕过 _send_text：补上采集入口，否则「发送」范围的触发规则盯不到
            try:
                self._record_stream_tx(payload, source=self._xfer_target)
            except Exception:
                _log.debug("_xfer_send failed", exc_info=True)

    def _seq_start(self, steps, loops=1, stop_on_fail=False, dataset=None):
        """开始运行一段序列（steps=步骤 dict 列表）。loops=循环次数（整条跑几轮），
        stop_on_fail=某轮失败即停后续循环。需已连接；运行期由 on_data_received 抑制
        自动应答/Modbus 主机（三者共用收流，序列是主动驱动方，结束自动恢复、不改它们开关）。"""
        if self._seq_on:
            return
        if self._io_task_busy(exclude=("sequence", "modbus")):
            self.toast(self._t("io_exclusive_busy"), error=True)
            return
        if not self._is_open():
            self.toast(self._t("seq_need_conn"), error=True)
            return
        if not _seq_engine_has_runnable(steps):
            self.toast(self._t("seq_no_steps"), error=True)
            return
        self._seq_steps = [dict(s) for s in steps]
        self._seq_on = True
        self._refresh_workspace_statuses()
        self._seq_gen += 1
        self._seq_pause_peer_engines()
        self._seq_summary = None
        self._seq_dataset = dataset if (dataset and dataset.get("rows")) else None
        self._seq_dataset_row = None
        if self._seq_dataset:
            n_rows = len(self._seq_dataset["rows"])
            self._seq_loops = _seq_engine_clamp_loops(n_rows)
        else:
            self._seq_loops = _seq_engine_clamp_loops(loops)
        self._seq_loop_i = 0
        self._seq_stop_on_fail = bool(stop_on_fail)
        self._seq_rounds = []
        self._seq_t0 = time.monotonic()
        self._seq_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._seq_finished_at = ""  # 墙钟起始时间，供导出报告用
        self.toast(self._t("seq_running_toast"))
        self._seq_begin_round()

    def _seq_begin_round(self):
        """开始新一轮：重置本轮每步结果，从第 0 步跑起（首轮若在等 Modbus 在途则由释放检查触发）。"""
        # Per-round context: CSV row seeds (if any) then extractors may update.
        seed = None
        self._seq_dataset_row = None
        ds = getattr(self, "_seq_dataset", None)
        if ds and ds.get("rows"):
            rows = ds["rows"]
            if 0 <= self._seq_loop_i < len(rows):
                self._seq_dataset_row = rows[self._seq_loop_i]
                seed = self._seq_dataset_row.get("seeds")
        self._seq_ctx = seq_context.RoundContext(seed)
        self._seq_runtime_step = None
        self._seq_results = _seq_engine_initial_results(self._seq_steps)
        self._seq_round_snapshot_taken = False
        self._seq_notify()
        if not self._seq_waiting_mbm:            # 本轮计时从"真正开跑"起；等 Modbus 释放的那段不计入本轮
            self._seq_round_t0 = time.monotonic()
            self._seq_run_from(0)

    def _seq_run_from(self, i):
        """Run from step i: skip disabled, or finish round when exhausted."""
        i = _seq_engine_next_enabled(self._seq_steps, i)
        if i >= len(self._seq_steps):
            self._seq_round_done()
            return
        self._seq_idx = i
        self._seq_attempt = 1
        self._seq_step_total_t0 = time.monotonic()
        self._seq_do_step(i)

    def _seq_do_step(self, i):
        """Run step i: expand ${vars}, send, then wait for expect if any."""
        step = self._seq_steps[i]
        self._seq_buf = b""
        ctx = getattr(self, "_seq_ctx", None)
        ctx_map = ctx.as_dict() if ctx is not None else {}
        runtime, missing = _seq_engine_prepare_runtime(step, ctx_map)
        self._seq_runtime_step = runtime
        if missing:
            self.toast(self._t("seq_var_missing", names=", ".join(missing)), error=True)
            ms = int((time.monotonic() - self._seq_step_total_t0) * 1000)
            self._seq_set_result(i, "fail", ms, self._t("seq_st_var_missing"),
                                "seq_st_var_missing", self._seq_attempt)
            self._seq_after_fail(step)
            return
        kind = _seq_engine_step_kind(runtime)
        send = str(runtime.get("send", "") or "")
        if kind == "skip":
            self._seq_set_result(i, "skip", 0, "")
            self._seq_schedule_next(step)
            return
        if send.strip():
            try:
                ok = self._send_text(send, hex_mode=bool(step.get("send_hex", False)),
                                     checksum=self._ar_to_int(step.get("cs", 0)),
                                     record_macro=False, allow_during_exclusive=True)
            except Exception:
                ok = False
            if not ok:
                self._seq_step_failed("seq_st_send_fail")
                return
            if 0 <= i < len(self._seq_results):
                self._seq_results[i]["tx"] = send
        if kind == "send_only":
            ms = int((time.monotonic() - self._seq_step_total_t0) * 1000)
            self._seq_set_result(i, "sent", ms, "", "", self._seq_attempt)
            self._seq_schedule_next(step)
            return
        self._seq_set_result(i, "waiting", 0, "", "", self._seq_attempt)
        self._seq_timer.stop()
        timeout = _seq_engine_clamp_timer_ms(step.get("timeout", 1000), minimum=1)
        self._seq_timer.start(timeout)

    def _seq_feed(self, data):
        """收到数据（on_data_received 在序列运行时调）：当前步在等回包则累积 + 匹配，命中→通过。"""
        if not self._seq_on:
            return
        i = self._seq_idx
        if not (0 <= i < len(self._seq_results)):
            return
        status = self._seq_results[i].get("status")
        if status == "retry":
            # 上次尝试的迟到响应不参与新尝试匹配；每个迟到数据块都重置安静窗。
            self._seq_retry_quiet_until = time.monotonic() + _SEQ_RETRY_GUARD_MS / 1000.0
            return
        if status != "waiting":
            return
        self._seq_buf += bytes(data)
        match_step = getattr(self, "_seq_runtime_step", None) or self._seq_steps[i]
        if self._seq_step_match(match_step, self._seq_buf):
            self._seq_timer.stop()
            ms = int((time.monotonic() - self._seq_step_total_t0) * 1000)
            extracted = self._seq_capture_vars(self._seq_steps[i], self._seq_buf)
            detail = _seq_engine_detail_extracted(extracted)
            rx_hex = _seq_engine_clip_rx_hex(self._seq_buf)
            self._seq_set_result(i, "pass", ms, detail, "", self._seq_attempt, rx_hex=rx_hex)
            if extracted and 0 <= i < len(self._seq_results):
                self._seq_results[i]["extracted"] = dict(extracted)
            self._seq_schedule_next(self._seq_steps[i])

    def _seq_on_timeout(self):
        """当前步等回包超时：按重试策略处理（还有重试则重发，否则判失败按超时动作走）。"""
        if not self._seq_on:
            return
        i = self._seq_idx
        if not (0 <= i < len(self._seq_results)) or self._seq_results[i].get("status") != "waiting":
            return
        _note_to = getattr(self, "_stat_note_timeout", None)
        if callable(_note_to):
            _note_to("seq")
        self._seq_step_failed("seq_st_fail")

    def _seq_step_failed(self, detail_key):
        """Fail current step: retry if budget remains, else mark fail."""
        i = self._seq_idx
        step = self._seq_steps[i]
        ms = int((time.monotonic() - self._seq_step_total_t0) * 1000)
        if _seq_engine_should_retry(self._seq_attempt, step.get("retry", 0)):
            plan = _seq_engine_plan_retry(
                step, self._seq_attempt,
                guard_ms=_SEQ_RETRY_GUARD_MS,
                max_quiet_ms=_SEQ_RETRY_MAX_QUIET_MS)
            self._seq_attempt = plan["next_attempt"]
            self._seq_set_result(i, "retry", ms, "", detail_key, self._seq_attempt)
            gen = self._seq_gen
            self._seq_retry_not_before = plan["not_before"]
            self._seq_retry_quiet_until = plan["quiet_until"]
            self._seq_retry_quiet_deadline = plan["quiet_deadline"]
            attempt = self._seq_attempt
            QTimer.singleShot(plan["timer_ms"],
                              lambda: self._seq_retry(gen, i, attempt))
            return
        rx_hex = _seq_engine_clip_rx_hex(getattr(self, "_seq_buf", b"") or b"")
        self._seq_set_result(i, "fail", ms, self._t(detail_key), detail_key, self._seq_attempt,
                             rx_hex=rx_hex)
        self._seq_after_fail(step)

    def _seq_retry(self, gen, i, attempt):
        """隔离结束后重发本步；代际/步骤/尝试号/状态任一变化都作废回调。"""
        if not (self._seq_on and gen == self._seq_gen and i == self._seq_idx
                and attempt == self._seq_attempt and 0 <= i < len(self._seq_results)
                and self._seq_results[i].get("status") == "retry"):
            return
        # 静默窗有上限：对端持续刷数据把 quiet_until 一直往后推时，用 deadline 兜底，避免永远卡在重试
        remain = _seq_engine_retry_remain(
            self._seq_retry_not_before, self._seq_retry_quiet_until,
            self._seq_retry_quiet_deadline)
        if remain > 0:
            delay = _seq_engine_clamp_timer_ms(int(remain * 1000) + 1, minimum=1)
            QTimer.singleShot(delay, lambda: self._seq_retry(gen, i, attempt))
            return
        self._seq_do_step(i)

    def _seq_after_fail(self, step):
        """After step fail: continue next step or end the round."""
        if _seq_engine_continue_after_fail(step):
            self._seq_schedule_next(step)
        else:
            self._seq_round_done()


    def _seq_schedule_next(self, step):
        """步间延时后进下一步（用代际作废停止/重启后残留的续跑）。"""
        delay = _seq_engine_clamp_timer_ms(step.get("delay", 0), minimum=0)
        nxt = self._seq_idx + 1
        gen = self._seq_gen
        QTimer.singleShot(delay, lambda: self._seq_continue(gen, nxt))

    def _seq_continue(self, gen, nxt):
        if self._seq_on and gen == self._seq_gen:
            self._seq_run_from(nxt)

    def _seq_append_round_snapshot(self):
        """Record current round aggregate + per-step results into _seq_rounds."""
        if getattr(self, "_seq_round_snapshot_taken", False):
            return
        self._seq_round_snapshot_taken = True
        t0 = getattr(self, "_seq_round_t0", None) or getattr(self, "_seq_t0", time.monotonic())
        self._seq_rounds.append(_seq_engine_round_snapshot(
            self._seq_results, self._seq_steps, self._seq_loop_i, t0,
            dataset_row=getattr(self, "_seq_dataset_row", None)))

    def _seq_round_done(self):
        """本轮所有启用步骤跑完（或失败停止）：记录本轮汇总，再决定跑下一轮还是整体收尾。"""
        self._seq_timer.stop()
        # 只统计「启用且真正执行」的步骤：空步骤(send与expect都空)标记 skip，既不是测试项，也不该
        # 被算作「通过」——从 total 与 passed 里都排除，汇总显示 通过 X/Y 才不会把跳过误显为通过。
        self._seq_append_round_snapshot()
        round_ok = bool(self._seq_rounds and self._seq_rounds[-1].get("pass"))
        self._seq_loop_i += 1
        more = _seq_engine_more_rounds(
            self._seq_loop_i, self._seq_loops, self._seq_stop_on_fail, round_ok)
        if more:
            gen = self._seq_gen                          # 轮间让出事件循环再开下一轮（代际作废停止/断连残留）
            QTimer.singleShot(0, lambda: self._seq_next_round(gen))
        else:
            self._seq_finalize()

    def _seq_next_round(self, gen):
        if self._seq_on and gen == self._seq_gen:
            self._seq_begin_round()

    def _seq_build_summary(self, stopped=False):
        """Aggregate finished rounds (_seq_rounds) into export summary."""
        return _seq_engine_build_summary(
            self._seq_rounds,
            loops=self._seq_loops,
            t0=self._seq_t0,
            stopped=stopped,
            started_at=getattr(self, "_seq_started_at", "") or "",
            finished_at=getattr(self, "_seq_finished_at", "") or "",
            version=APP_VERSION,
            stop_on_fail=bool(getattr(self, "_seq_stop_on_fail", False)),
            step_count=len(getattr(self, "_seq_steps", []) or []),
            dataset=getattr(self, "_seq_dataset", None),
        )

    def _seq_finalize(self):
        """整条序列（全部循环）结束：出聚合汇总 + toast + 恢复对端引擎。"""
        self._seq_on = False
        self._seq_finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._refresh_workspace_statuses()
        self._seq_waiting_mbm = False
        self._seq_wait_mbm_variant = ""
        self._seq_wait_mbm_until = 0.0
        self._seq_timer.stop()
        self._seq_summary = self._seq_build_summary(stopped=False)
        ok = bool(self._seq_summary.get("pass"))
        self._seq_notify()
        self._seq_resume_peer_engines()
        self.toast(self._t("seq_done_pass" if ok else "seq_done_fail"), error=not ok)

    def _seq_stop(self):
        """用户点「停止」：中止运行（保留已跑结果供查看，提示「已停止」）。"""
        self._seq_abort("seq_stopped")

    def _seq_abort(self, toast_key):
        """中止运行中的序列（用户停止 / 连接断开）：**保留已跑结果供查看**（不清 _seq_results，
        对话框据此仍显示各步通过/失败/超时）、当前"等回包/重试中"步标记为「已停止」（否则一直显示
        等回包/↻第N次）、恢复对端引擎、出提示。代际 +1 作废在途续跑。"""
        if not self._seq_on:
            return
        self._seq_on = False
        self._seq_finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._refresh_workspace_statuses()
        self._seq_waiting_mbm = False
        self._seq_wait_mbm_variant = ""
        self._seq_wait_mbm_until = 0.0
        self._seq_timer.stop()
        self._seq_gen += 1
        i = self._seq_idx
        if 0 <= i < len(self._seq_results) and self._seq_results[i].get("status") in ("waiting", "retry"):
            ms = int((time.monotonic() - self._seq_step_total_t0) * 1000)
            prev = self._seq_results[i] if isinstance(self._seq_results[i], dict) else {}
            rec = {"status": "stopped", "ms": ms, "detail": "",
                   "attempt": prev.get("attempt", 1)}
            for k in ("tx", "rx_hex", "extracted"):
                if k in prev:
                    rec[k] = prev[k]
            self._seq_results[i] = rec
        # Snapshot in-progress round so mid-stop still exports.
        if self._seq_results and not getattr(self, "_seq_round_snapshot_taken", False):
            self._seq_append_round_snapshot()
        # 循环运行已完成 ≥1 轮就出汇总，让长时间老化的已跑结果可导出（否则中途停止=白跑，无法导出）。
        self._seq_summary = self._seq_build_summary(stopped=True)
        self._seq_resume_peer_engines()
        self._seq_notify()
        if toast_key:
            self.toast(self._t(toast_key))


    def _seq_capture_vars(self, step, buf):
        """Extract variables from a passed step into the round context."""
        try:
            codec = self._get_codec()
        except Exception:
            codec = "utf-8"
        extracted = _seq_engine_capture_vars(step, buf, codec=codec)
        return _seq_engine_apply_capture(getattr(self, "_seq_ctx", None), extracted)

    def _seq_step_match(self, step, buf):
        """Whether accumulated buf satisfies step expect (AR hit-test rules)."""
        try:
            codec = self._get_codec()
        except Exception:
            codec = "utf-8"
        return _seq_engine_step_match(step, buf, codec=codec)

    def _seq_set_result(self, i, status, ms, detail, detail_key="", attempt=1, **extra):
        if 0 <= i < len(self._seq_results):
            prev = self._seq_results[i] if isinstance(self._seq_results[i], dict) else {}
            rec = {"status": status, "ms": ms, "detail": detail,
                   "detail_key": detail_key, "attempt": attempt}
            for k in ("tx", "rx_hex", "extracted"):
                if k in prev:
                    rec[k] = prev[k]
            if extra:
                rec.update(extra)
            self._seq_results[i] = rec
        self._seq_notify()

    def _seq_notify(self):
        """结果变化 → 通知对话框刷新（对话框没开就算了）。"""
        dlg = getattr(self, "_seq_dlg", None)
        if dlg is not None:
            try:
                dlg.update_results()
            except Exception:
                _log.debug("_seq_notify failed", exc_info=True)

    def _load_ar_rules(self):
        rules = _cfg_parse_obj_list(self.settings.value("autoreply_rules", ""))
        return rules if rules is not None else []

    def _set_ar_rules(self, rules):
        """对话框编辑后回调：更新内存规则并落盘。内存保留 _ 前缀运行态键（_hits/_hit_time/
        _last 命中统计与冷却时刻），但落盘时剥离 —— 不污染配置、也不导出到会话配置档。"""
        self._ar_rules = rules
        self._recompute_ar_gap()
        self._ar_reset_buf()       # 规则变了 → 旧的整包缓冲不能再被新规则吃，必须清掉
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rules]
        self.settings.setValue("autoreply_rules", json.dumps(clean, ensure_ascii=False))
        self.settings.sync()

    def _load_ar_frame(self):
        """Load framing config JSON from QSettings."""
        cfg = _cfg_parse_json_dict(self.settings.value("autoreply_frame", "")) or {}
        return self._norm_ar_frame(cfg)

    def _norm_ar_frame(self, cfg):
        """Normalize framing config + pre-parse header bytes."""
        return _ar_core_norm_frame(cfg)

    def _set_ar_frame(self, cfg):
        """对话框编辑「帧头+长度组帧」后回调：更新内存配置 + 清缓冲 + 落盘（运行态 _header 不存）。"""
        self._ar_frame = self._norm_ar_frame(cfg)
        self._ar_reset_buf()       # 组帧方式变了 → 旧缓冲不能再被新配置吃，必须清
        save = {k: v for k, v in self._ar_frame.items() if not k.startswith("_")}
        self.settings.setValue("autoreply_frame", json.dumps(save, ensure_ascii=False))
        self.settings.sync()

    # ----- C6 全局故障注入（autoreply_fault：丢包/错CRC/错长度 概率，压测主机重传/容错）-----
    def _load_ar_fault(self):
        cfg = _cfg_parse_json_dict(self.settings.value("autoreply_fault", "")) or {}
        return self._norm_ar_fault(cfg)

    def _norm_ar_fault(self, cfg):
        """Normalize fault-injection percentages."""
        return _ar_core_norm_fault(cfg)

    def _set_ar_fault(self, cfg):
        self._ar_fault = self._norm_ar_fault(cfg)
        self.settings.setValue("autoreply_fault", json.dumps(self._ar_fault, ensure_ascii=False))
        self.settings.sync()

    # ----- C8 多步状态机（autoreply_sm：on + init 初始状态。当前状态 _ar_state 是运行态、不持久化）。
    #   会话级复位（连接开/关、总开关切、状态机 on-init 变化、配置导入、手动重置）走 _ar_reset_state：
    #   复位到 init + 代际 +1（作废在途延迟/多段应答）。_ar_reset_buf 只清半包缓冲、不复位状态、不动代际；
    #   『编辑规则/组帧』只调 _ar_reset_buf —— 不打断进行中的握手、在途应答照常发完 -----
    def _load_ar_sm(self):
        cfg = _cfg_parse_json_dict(self.settings.value("autoreply_sm", "")) or {}
        return self._norm_ar_sm(cfg)

    def _norm_ar_sm(self, cfg):
        """Normalize state-machine config."""
        return _ar_core_norm_sm(cfg)

    def _set_ar_sm(self, cfg):
        """对话框编辑「状态机」后回调：更新内存配置 + 落盘。仅当 on/init 真变化时才复位当前状态——
        否则每次去抖落盘（用户改任意无关字段）都会把进行中的握手拉回初始。"""
        new = self._norm_ar_sm(cfg)
        changed = (not getattr(self, "_ar_sm", None)) or new != self._ar_sm
        self._ar_sm = new
        if changed:
            self._ar_reset_state()      # on/init 变了 → 回到（新）初始状态
        self.settings.setValue("autoreply_sm", json.dumps(self._ar_sm, ensure_ascii=False))
        self.settings.sync()

    @staticmethod
    def _ar_state_tokens(when):
        """Rule when-field -> state token list."""
        return _ar_core_state_tokens(when)

    def _ar_state_ok(self, rule):
        """SM gate for a rule against current _ar_state."""
        return _ar_core_state_ok(
            bool(self._ar_sm.get("on")), rule.get("when"), self._ar_state)

    def _ar_apply_goto(self, rule):
        """Advance _ar_state to rule.goto when SM is on."""
        self._ar_state = _ar_core_next_state(
            bool(self._ar_sm.get("on")), rule, self._ar_state)

    def _load_ar_modbus(self):
        cfg = _cfg_parse_json_dict(self.settings.value("autoreply_modbus", "")) or {}
        return self._norm_ar_modbus(cfg)

    def _norm_ar_modbus(self, cfg):
        """Normalize Modbus slave bank config."""
        return _ar_core_norm_modbus(cfg)

    def _set_ar_modbus(self, cfg):
        """对话框编辑「Modbus 从机」后回调：更新内存配置 + 重建运行态从机(回初值) + 落盘。
        Modbus 开关/配置变 = 改变了分帧语义 → 必须清跨模式共用的 _ar_buf 半包缓冲并停 gap timer
        （与 _set_ar_frame / _set_ar_rules 一致），否则切模式时旧字节会被新框架误解析。"""
        self._ar_modbus = self._norm_ar_modbus(cfg)
        self._modbus = modbus_slave.slave_bank_from_config(self._ar_modbus)
        self._ar_reset_buf()
        self.settings.setValue("autoreply_modbus", json.dumps(self._ar_modbus, ensure_ascii=False))
        self.settings.sync()

    def _modbus_feed(self, data: bytes, reply_target=None):
        """B4：Modbus 从机模式收到字节 → 长度感知切整帧 → 逐帧 handle → 有响应就发。
        ASCII 变体（_ar_modbus['variant']=='ascii'）用 ':'..CRLF 切帧 + handle_ascii。"""
        ascii_mode = (self._ar_modbus.get("variant") or "rtu").lower() == "ascii"
        splitter = modbus_slave.iter_ascii_frames if ascii_mode else modbus_slave.iter_frames
        handler = self._modbus.handle_ascii if ascii_mode else self._modbus.handle
        if reply_target is None:
            self._ar_buf += bytes(data)
            frames, self._ar_buf = splitter(self._ar_buf)
            if len(self._ar_buf) > 8192:       # 防御：坏流不无界增长
                self._ar_buf = self._ar_buf[-512:]
        else:
            buf = self._modbus_buffers.get(reply_target, b"") + bytes(data)
            frames, remainder = splitter(buf)
            if len(remainder) > 8192:
                remainder = remainder[-512:]
            if remainder:
                self._modbus_buffers[reply_target] = remainder
            else:
                self._modbus_buffers.pop(reply_target, None)
        for f in frames:
            try:
                resp = handler(f)
            except Exception:
                resp = None
            if resp:
                self._modbus_send(bytes(resp), reply_target=reply_target)

    def _modbus_send(self, frame: bytes, reply_target=None):
        """发 Modbus 响应。响应同样经 C6 全局故障注入（可压测主机的重传/容错）。"""
        if not self._ar_on or not self._is_open():
            return
        # Modbus 从机响应也走 _send_text，同样不是「用户手动发」——置标记让宏录制跳过
        # （与 _ar_schedule_send 一致；这是另一条独立发送路径，各自都要保护）。
        self._ar_in_flight = True
        try:
            out, fault = self._ar_apply_fault(frame)
            if out is None:
                self._ar_fault_note(fault)     # 丢包：不发
            else:
                out = bytes(out)
                # 按从机配置的 variant 路由，不能嗅探首字节——RTU 从机地址 58 = 0x3A = ':' 会被
                # 误判成 ASCII，二进制 RTU 帧被 decode('ascii','replace') 破坏，静默数据损坏。
                if (self._ar_modbus.get("variant") or "rtu").lower() == "ascii":
                    self._send_text(out.decode("ascii", "replace"), hex_mode=False,
                                    newline=0, checksum=0, target=reply_target)
                else:
                    self._send_text(out.hex(" "), hex_mode=True, newline=0, checksum=0,
                                    target=reply_target)
                if fault:
                    self._ar_fault_note(fault)
        except Exception:
            _log.debug("_modbus_send failed", exc_info=True)
        finally:
            self._ar_in_flight = False

    def _ar_reset_buf(self):
        """停整包静默 timer + 清半包缓冲。规则改 / 组帧改 / 总开关切 / 关闭连接 都得调，否则半截
        缓冲会以新状态被当成新帧头匹配（误响应）。
        注意：本函数【既不】复位状态机当前状态、【也不】作废在途延迟/多段应答（代际 +1）—— 两者都
        走 _ar_reset_state（仅会话级）。这样『编辑规则/组帧』这类高频去抖落盘只清缓冲，进行中的握手
        不被打断、在途的延迟/多段应答也照常发完（与 v1.1.5 普通模式行为一致）。"""
        if hasattr(self, "_ar_gap_timer"):
            self._ar_gap_timer.stop()
        self._ar_buf = b""
        if hasattr(self, "_modbus_buffers"):
            self._modbus_buffers.clear()

    def _ar_reset_state(self):
        """复位状态机当前状态到 init + 代际 +1（作废在途延迟应答）。仅会话级复位时调：连接开/关、
        总开关切、状态机 on/init 变化、配置导入、手动重置。【不】绑定到编辑规则/组帧/故障等高频
        去抖落盘路径，否则进行中的握手会因改了个无关字段就被静默拉回初始。"""
        if hasattr(self, "_ar_sm"):
            self._ar_state = self._ar_sm.get("init", "")
        self._ar_sm_pending = None
        if hasattr(self, "_ar_sm_queue"):
            self._ar_sm_queue.clear()
        self._ar_sm_draining = False
        self._ar_generation = getattr(self, "_ar_generation", 0) + 1
        # B4：会话级复位 → Modbus 从机运行态寄存器回到配置初值（清掉主机本次会话的写入）
        if hasattr(self, "_ar_modbus"):
            self._modbus = modbus_slave.slave_bank_from_config(self._ar_modbus)

    @staticmethod
    def _ar_to_int(v, default=0):
        return _ar_core_to_int(v, default)

    def _recompute_ar_gap(self):
        """整包静默取所有启用规则中的最大 gap（分帧在匹配前、整条串口共用一个值）。"""
        self._ar_gap = max((self._ar_to_int(r.get("gap", 0)) for r in self._ar_rules
                            if r.get("on", True)), default=0)

    def _auto_reply(self, data: bytes, reply_target=None):
        """收到数据 → (可选)组帧 → 匹配规则 → (可选延时)自动发应答。仅连接且总开关开时生效。
        三种组帧粒度（互斥，优先级从高到低）：
          1. 帧头+长度组帧（_ar_frame.on）：维护跨包字节流，按「帧头定位 + Length 字段」切整帧，
             正确处理粘包/拆包——有帧头+长度字段的协议（本设备 AA BB…）应优先用这个；
          2. 整包静默超时（_ar_gap>0）：累积字节、静默该时长视作一整帧（Modbus RTU 等无帧头、
             靠帧间静默 T3.5 分帧的协议用）；
          3. 每包即时（默认）：上层一个接收块直接当一帧匹配。
        B4：Modbus 从机模式开启时整条引擎让位给 Modbus（按功能码自动应答，规则/状态机不参与；
        此时即使没有任何规则也生效）。"""
        if not self._ar_on or not self._is_open():
            return
        if self._ar_modbus.get("on"):          # B4 Modbus 从机：独占处理（长度感知组帧）
            self._modbus_feed(bytes(data), reply_target=reply_target)
            return
        if not self._ar_rules:
            return
        fc = self._ar_frame
        if fc.get("on") and fc.get("_header"):
            self._ar_buf += bytes(data)
            frames, self._ar_buf = binproto.iter_length_frames(
                self._ar_buf, fc["_header"], fc["len_off"], fc["len_width"],
                fc["len_extra"], fc["len_be"])
            # 防御：缓冲异常增长（帧头一直不出现 / 全是坏长度）时截断，避免无界吃内存
            if len(self._ar_buf) > 8192:
                self._ar_buf = self._ar_buf[-512:]
            for f in frames:
                self._ar_match(f)
        elif self._ar_gap > 0:
            self._ar_buf += bytes(data)            # 累积；静默 _ar_gap ms 后视作整帧
            self._ar_gap_timer.start(self._ar_gap)
        else:
            self._ar_match(bytes(data))            # 每包即时匹配

    def _ar_flush(self):
        """整包静默超时：把累积缓冲当一整帧匹配。Modbus 模式下不走规则匹配（防止切到 Modbus 后
        在途的 gap timer 仍误用规则匹配一帧）。"""
        buf, self._ar_buf = self._ar_buf, b""
        if buf and self._ar_on and self._is_open() and not self._ar_modbus.get("on"):
            self._ar_match(buf)

    def _ar_match(self, data: bytes):
        # 状态转移的整条多段应答尚未完成时，后续完整帧先入 FIFO。直接继续匹配会让多个随机延迟
        # 任务共享同一旧状态并按定时器先后 goto；直接丢弃又会漏掉同一接收块里的后续合法帧。
        q = self._ar_sm_queue
        busy = (getattr(self, "_ar_sm_pending", None) is not None
                or (q and not getattr(self, "_ar_sm_draining", False)))
        if self._ar_sm.get("on") and busy:
            if len(q) < 256:       # 有界防御：保留最早到达的 256 帧，过载时丢弃最新帧
                q.append(bytes(data))
            if self._ar_sm_pending is None:
                self._ar_drain_sm_queue()
            return
        text_cache = None
        for rule in self._ar_rules:
            if not rule.get("on", True):
                continue
            if not (rule.get("match") or "").strip():
                continue
            if not rule.get("match_hex", True) and text_cache is None:
                codec = self._get_codec()
                try:
                    text_cache = data.decode("utf-8" if codec == "auto" else codec, errors="replace")
                except Exception:
                    text_cache = ""
            if not self._ar_hit_test(rule, data, text_cache or ""):
                continue
            # 长度过滤（⑤）：min_len/max_len 任一>0 时启用；剔除毛刺/超长帧。无 UI、手填 ini/json。0=不限
            min_len = self._ar_to_int(rule.get("min_len", 0))
            max_len = self._ar_to_int(rule.get("max_len", 0))
            if min_len > 0 and len(data) < min_len:
                continue
            if max_len > 0 and len(data) > max_len:
                continue
            if not self._ar_state_ok(rule):
                continue     # C8 状态机：当前状态不满足该规则「仅状态」→ 跳过、试下一条
            if not self._ar_frame_ok(data, self._ar_to_int(rule.get("verify", 0))):
                return       # 命中规则但收包校验不过 → 不应答（命中即停）
            now = time.monotonic()
            # A3 命中统计：匹配 + 收包校验通过即 +1（含被下面冷却抑制的）；运行态、不持久化
            rule["_hits"] = self._ar_to_int(rule.get("_hits", 0)) + 1
            rule["_hit_time"] = now
            # 冷却（rate-limit）：同一规则在冷却窗口内不再触发。delay 是 turnaround 输出延时，
            # 跟冷却是两回事——delay=200 表示「200ms 后回」、cooldown=200 表示「200ms 内不再触发」。
            cooldown = self._ar_to_int(rule.get("cooldown", 0))
            if cooldown > 0 and (now - rule.get("_last", 0.0)) * 1000 < cooldown:
                return
            rule["_last"] = now      # 运行态，不持久化
            # B5：有脚本则跑脚本动态生成应答（脚本拥有整帧、不叠校验段/尾校验）；否则走静态模板
            # （④ 多帧 | 分段、占位符替换、校验段）。两路都经故障注入 + 延时发送、共用 goto 回调。
            script = str(rule.get("script") or "").strip()   # str() 容错：script 非字符串也不崩
            if script and rule.get("script_on", True):
                parts, serr = self._ar_script_eval(rule, data)
                if serr:
                    self._ar_fault_note(self._t("ar_script_err", e=serr))   # 脚本错误：数据区留痕、不崩
                if not parts:
                    return
                hexmode, cs, cs_segs = True, 0, []
            else:
                parts = self._ar_build_parts(rule, data)
                if not parts:
                    return
                hexmode = bool(rule.get("reply_hex", True))
                cs = self._ar_to_int(rule.get("cs", 0))
                cs_segs = rule.get("cs_segs", []) or []    # 内层/额外校验段（在尾部 cs 之前算）
            delay = self._ar_parse_delay(rule.get("delay", 0))   # C7：(min,max)，每次发随机取
            # C8：goto 推进绑定到「首段真正发出」回调，而非排程瞬间 —— 延时未到/连接断/故障丢包
            # 时不推进。带 goto 的规则同时占用 pending 门闩，整条多段应答完成前把后续帧排入 FIFO，
            # 防止延迟不同的任务乱序 goto，也避免 A1|A2 被下一状态的 B1 插队。
            pending = None
            on_sent = None
            on_done = None
            goto = str(rule.get("goto", "") or "").strip()
            if self._ar_sm.get("on") and goto:
                pending = object()
                self._ar_sm_pending = pending

                def on_sent(r=rule, token=pending):
                    if self._ar_sm_pending is token:
                        self._ar_apply_goto(r)

                def on_done(token=pending):
                    if self._ar_sm_pending is token:
                        self._ar_sm_pending = None
                        self._ar_drain_sm_queue()
            try:
                self._ar_schedule_send(parts, hexmode, cs, cs_segs, delay,
                                       on_sent=on_sent, on_done=on_done)
            except Exception:
                if pending is not None and self._ar_sm_pending is pending:
                    self._ar_sm_pending = None
                raise
            return      # 命中即停：一帧最多回一条（按规则顺序取第一条命中的）

    def _ar_drain_sm_queue(self):
        """按收帧顺序消费 pending 期间积压的完整帧；遇到下一条延迟状态转移时自然暂停。"""
        if (self._ar_sm_draining or not self._ar_sm.get("on")
                or not self._ar_on or not self._is_open()):
            return
        self._ar_sm_draining = True
        try:
            q = self._ar_sm_queue
            while q and self._ar_sm_pending is None:
                self._ar_match(q.popleft())
        finally:
            self._ar_sm_draining = False

    def _ar_hit_test(self, rule, data, text):
        return _ar_core_hit_test(rule, data, text)

    def _ar_build_parts(self, rule, data):
        """Split reply on '|', substitute placeholders per segment."""
        parts, self._ar_seq = _ar_core_build_parts(
            rule, data, seq=getattr(self, "_ar_seq", 0))
        return parts

    # ---- B5 脚本化应答：每条规则可选一段 Python，命中时跑 reply(frame, ctx) 动态生成应答 ----
    @staticmethod
    def _ar_crc(data, width=16, poly=0x1021, init=0x0000,
                refin=False, refout=False, xorout=0x0000, byteorder="big"):
        return _ar_core_crc(data, width, poly, init, refin, refout, xorout, byteorder)

    def _ar_make_ctx(self, rule, preview=False):
        """脚本只读上下文 + 校验工具：state / seq / hits + 可定制 crc 及便捷封装。
        seq 每次调用自增（live 持久化；preview 由 _ar_preview 的 save/restore 还原）；
        hits 在 preview 下 +1，与「live 已在 _ar_match 先 +1」对齐，使预览=实发。"""
        crc = CommTool._ar_crc

        def _xor8(d):
            r = 0
            for c in bytes(d):
                r ^= c
            return bytes([r])

        def _hexbytes(s):
            s = re.sub(r"[^0-9A-Fa-f]", "", str(s).replace("0x", "").replace("0X", ""))
            return bytes.fromhex(s)

        next_seq = (self._ar_to_int(getattr(self, "_ar_seq", 0)) + 1) & 0xFF
        if not preview:
            self._ar_seq = next_seq      # 真实执行才写回；编辑器/离线预览无副作用
        return types.SimpleNamespace(
            state=str(getattr(self, "_ar_state", "") or ""),
            seq=next_seq,
            hits=self._ar_to_int(rule.get("_hits", 0)) + (1 if preview else 0),
            crc=crc,                                                      # 通用：自定义 poly/init/refin…
            crc16=lambda d: crc(d, 16, 0x8005, 0xFFFF, refin=True, refout=True, byteorder="little"),  # Modbus
            crc8=lambda d: crc(d, 8, 0x07, 0x00),                        # CRC-8/SMBus
            sum8=lambda d: bytes([sum(bytes(d)) & 0xFF]),
            xor8=_xor8,
            hexbytes=_hexbytes,                                          # "AA BB"/"0xAABB" → bytes
            tohex=lambda d: " ".join("%02X" % x for x in bytes(d)),      # bytes → "AA BB"
        )

    def _ar_script_code(self, script):
        """编译脚本 → (code 对象, None) 或 (None, 错误)，按文本缓存。只缓存编译结果、不缓存运行态/全局：
        每次执行用全新命名空间，避免编辑器测试 / 离线预览污染实发脚本的全局状态。"""
        cached = self._ar_script_cache.get(script)
        if cached is not None:
            return cached
        try:
            res = (compile(script, "<ar-script>", "exec"), None)
        except Exception as e:
            res = (None, "%s: %s" % (type(e).__name__, e))
        self._ar_script_cache[script] = res
        return res

    @staticmethod
    def _ar_kill_worker(proc, conn, group_ready=False):
        """Force-reclaim a script subprocess and its process group.

        Cleanup is stepwise: one failed step must not skip close/join/kill that
        still need to run (same contract as net_io._safe / serial_io._safe).
        """
        if conn is not None:
            try:
                conn.close()
            except Exception:
                _log.debug("ar_kill: conn.close failed", exc_info=True)
        if proc is None:
            return

        alive = False
        try:
            alive = proc.is_alive()
        except Exception:
            _log.debug("ar_kill: is_alive failed", exc_info=True)

        if sys.platform == "win32":
            if (group_ready or alive) and proc.pid:
                try:
                    import subprocess
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except Exception:
                    _log.debug("ar_kill: taskkill failed", exc_info=True)
        else:
            import signal
            killed_group = False
            if group_ready and proc.pid and proc.pid != os.getpgrp():
                try:
                    # After the leader exits, os.getpgid(worker_pid) can fail, but
                    # descendants may still use the original worker PID as PGID.
                    os.killpg(proc.pid, signal.SIGKILL)
                    killed_group = True
                except ProcessLookupError:
                    pass
                except Exception:
                    _log.debug("ar_kill: killpg failed", exc_info=True)
            if alive and not killed_group:
                try:
                    proc.terminate()
                except Exception:
                    _log.debug("ar_kill: terminate failed", exc_info=True)

        try:
            proc.join(0.5)
        except Exception:
            _log.debug("ar_kill: join failed", exc_info=True)

        try:
            still = proc.is_alive()
        except Exception:
            _log.debug("ar_kill: is_alive(after join) failed", exc_info=True)
            still = False
        if still and hasattr(proc, "kill"):
            try:
                proc.kill()
                proc.join(0.5)
            except Exception:
                _log.debug("ar_kill: kill failed", exc_info=True)

        try:
            proc.close()
        except Exception:
            _log.debug("ar_kill: proc.close failed", exc_info=True)

    def _ar_stop_script_worker(self):
        """回收脚本子进程（实发 + 预览两个一起收）。超时、通信故障和应用退出都走这里。"""
        pairs = [(self._ar_script_proc, self._ar_script_conn, self._ar_script_group_ready),
                 (self._ar_preview_proc, self._ar_preview_conn, self._ar_preview_group_ready)]
        self._ar_script_proc = self._ar_script_conn = None
        self._ar_preview_proc = self._ar_preview_conn = None
        self._ar_script_group_ready = self._ar_preview_group_ready = False
        for proc, conn, group_ready in pairs:
            self._ar_kill_worker(proc, conn, group_ready)

    def _ar_get_script_worker(self, preview=False):
        """惰创建 spawn 子进程并常驻复用；预览/测试用独立进程，与实发 worker 隔离 ——
        预览推进的 random / 已导入模块等共享状态不会污染真实执行。"""
        proc_attr = "_ar_preview_proc" if preview else "_ar_script_proc"
        conn_attr = "_ar_preview_conn" if preview else "_ar_script_conn"
        group_attr = "_ar_preview_group_ready" if preview else "_ar_script_group_ready"
        proc, conn = getattr(self, proc_attr), getattr(self, conn_attr)
        if proc is not None and proc.is_alive() and conn is not None:
            return conn
        group_ready = getattr(self, group_attr)
        setattr(self, proc_attr, None)
        setattr(self, conn_attr, None)
        setattr(self, group_attr, False)
        self._ar_kill_worker(proc, conn, group_ready)
        mp = multiprocessing.get_context("spawn")
        parent, child = mp.Pipe(duplex=True)
        proc = mp.Process(target=_ar_script_worker, args=(child,), daemon=True)
        proc.start()
        child.close()
        group_ready = False
        try:
            if not parent.poll(self._AR_SCRIPT_START_TIMEOUT):
                raise TimeoutError("脚本子进程启动超时")
            status, group_ready = parent.recv()
            if status != "ready" or not group_ready:
                raise RuntimeError("脚本子进程隔离初始化失败")
        except Exception:
            self._ar_kill_worker(proc, parent, group_ready)
            raise
        setattr(self, proc_attr, proc)
        setattr(self, conn_attr, parent)
        setattr(self, group_attr, group_ready)
        return parent

    def _ar_script_eval(self, rule, frame, preview=False):
        """跑规则脚本 → (应答 hex 字符串段列表 or None, 错误文案 or None)。无副作用（不发送/不留痕）。
        脚本拥有整帧 → 结果按 hexmode=True 原样发、不叠校验。在常驻隔离子进程中执行；超时整组 kill、
        下次重建；每次任务全新命名空间。预览/测试走独立进程，不污染实发的模块态。"""
        script = str(rule.get("script") or "").strip()      # str() 容错：配置里 script 非字符串也不崩
        code, err = self._ar_script_code(script)
        if code is None:
            return None, err
        ctx = self._ar_make_ctx(rule, preview=preview)
        ctx_data = {"state": ctx.state, "seq": ctx.seq, "hits": ctx.hits}
        try:
            conn = self._ar_get_script_worker(preview=preview)
            conn.send((script, bytes(frame), ctx_data, self._send_codec()))
            if not conn.poll(self._AR_SCRIPT_TIMEOUT):
                self._ar_stop_script_worker()       # 真正杀掉死循环/阻塞任务(连同其子进程)
                return None, self._t("ar_script_timeout", s=self._AR_SCRIPT_TIMEOUT)
            status, result = conn.recv()
        except Exception as e:
            self._ar_stop_script_worker()
            return None, "%s: %s" % (type(e).__name__, e)
        if status == "err":
            return None, result
        parts = [" ".join("%02X" % x for x in b) for b in (result or []) if b]
        return (parts or None), None

    def _ar_schedule_send(self, parts, hexmode, cs, segs, delay, on_sent=None, on_done=None):
        """逐段发送 parts。delay=(min,max) ms（C7 范围延时：每次发独立随机取，模拟 turnaround
        抖动；min==max 即固定）。segs=校验段；每段经 _ar_compose_frame 组装最终字节(段+尾部 cs)，
        与测试器共用、保证预览=实发。发送前经 C6 全局故障注入（丢包/错CRC/错长度）。
        on_sent：首段「真正发出」后调一次（C8 状态机据此推进 goto）—— 延时未到/连接断/故障丢包/
        异常时不调，避免「应答没出去但状态已推进」导致主机重试被新状态拒绝。
        on_done：整条多段应答结束或中止后调一次，用于释放 pending 并继续消费状态帧 FIFO。"""
        gen = getattr(self, "_ar_generation", 0)   # C8：捕获本次会话代际；reset_state/重连会 +1
        dmin, dmax = delay if isinstance(delay, (tuple, list)) else (delay, delay)

        def _delay():
            return random.randint(dmin, dmax) if dmax > dmin else dmin

        def fire(idx):
            def finish_batch():
                if on_done is not None:
                    on_done()

            # 代际已变（手动重置/断重连/配置导入）→ 整批在途任务作废：旧回复不发、旧 goto 不执行
            if gen != getattr(self, "_ar_generation", 0):
                finish_batch()
                return
            if (not self._ar_on or not self._is_open() or self._seq_running()
                    or self._script_running() or idx >= len(parts)):
                finish_batch()
                return
            sent_ok = False
            # 自动应答的回复也走 _send_text，但它不是「用户手动发」——置标记让宏录制跳过，
            # 否则录制期间开着自动应答，设备每次回包触发的自动回复都会被录成一条 send()。
            self._ar_in_flight = True
            try:
                # 组装最终字节（校验段 + 尾部 cs），与测试器共用 _ar_compose_frame，保证预览=实发。
                frame = self._ar_compose_frame(parts[idx], hexmode, segs, cs)
                if frame is None:
                    # 组帧失败（坏 hex）→ 回退原始文本路径（故障注入不介入这条少见分支）。
                    # sent_ok 取 _send_text 真返回：无客户端/底层失败/坏 hex 时为 False → 不推进状态。
                    sent_ok = bool(self._send_text(parts[idx], hex_mode=hexmode, newline=0, checksum=cs))
                else:
                    out, fault = self._ar_apply_fault(bytes(frame))   # C6 全局故障注入
                    if out is None:
                        self._ar_fault_note(fault)                    # 丢包：不发；fault=本地化「丢包」文案
                    else:
                        # 取 _send_text 布尔返回（TCP 无客户端/底层 write 失败=False）→ 失败不推进状态
                        sent_ok = bool(self._send_text(bytes(out).hex(" "), hex_mode=True, newline=0, checksum=0))
                        if fault:
                            self._ar_fault_note(fault)
            except Exception:
                _log.debug("_ar_schedule_send fire failed", exc_info=True)
            finally:
                self._ar_in_flight = False
            if idx == 0:
                try:
                    if on_sent is not None and sent_ok:
                        on_sent()   # 首段确实发出 → 推进状态（失败/丢包则不推进）
                except Exception:
                    _log.debug("_ar_schedule_send on_sent failed", exc_info=True)
            if idx + 1 < len(parts):
                QTimer.singleShot(max(_delay(), 1), lambda: fire(idx + 1))
            else:
                finish_batch()      # 最后一段完成后再释放 pending，保证多段应答不被下一状态插队
        d0 = _delay()
        if d0 > 0:
            QTimer.singleShot(d0, lambda: fire(0))
        else:
            fire(0)

    def _ar_parse_delay(self, v):
        return _ar_core_parse_delay(v)

    @staticmethod
    def _ar_norm_idx(v, n):
        return _ar_core_norm_idx(v, n)

    def _ar_reply_bytes(self, text, hexmode):
        """Reply text -> bytes (hex parse or send codec)."""
        return _ar_core_reply_bytes(
            text, hexmode,
            lambda t: t.encode(self._send_codec(), errors="replace"))

    def _ar_apply_cs_segs(self, buf, segs):
        """Apply checksum segments onto bytearray buf."""
        return _ar_core_apply_cs_segs(buf, segs, self.compute_checksum)

    def _ar_compose_frame(self, text, hexmode, cs_segs, cs):
        """Reply segment -> final TX bytes."""
        return _ar_core_compose_frame(
            text, hexmode, cs_segs, cs,
            lambda t: t.encode(self._send_codec(), errors="replace"),
            self.compute_checksum)

    def _ar_apply_fault(self, frame):
        """Global fault injection; returns (bytes|None, localized note)."""
        out, tags = _ar_core_apply_fault(frame, self._ar_fault)
        if not tags:
            return out, ""
        if tags == ["drop"]:
            return None, self._t("ar_fault_note_drop")
        notes = []
        if "badlen" in tags:
            notes.append(self._t("ar_fault_badlen_short"))
        if "badcrc" in tags:
            notes.append(self._t("ar_fault_badcrc_short"))
        note = self._t("ar_fault_note_corrupt", what=" + ".join(notes)) if notes else ""
        return out, note

    def _ar_fault_note(self, text):
        """故障注入在数据区留痕（让用户看到"这条被故意搞坏/丢了"）。text 已是可读文案。"""
        if not text:
            return
        try:
            self._append_block_data(text + "\n", direction="tx", force_new_block=True,
                                    view_mode=VIEW_TEXT)
        except Exception:
            _log.debug("_ar_fault_note failed", exc_info=True)

    def _ar_preview(self, frame: bytes):
        """A2 离线测试器：给一帧 frame，返回第一条命中规则的索引 + 应答预览。
        不发送、不计数、不冷却，也**不推进 {seq} 实时计数**（存/恢复 _ar_seq）——
        这样预览出的 {seq} 字节与下次真实应答一致，且不污染实时序号。
        ({ts} 取预览时刻的毫秒，与未来实发的时间不同，属固有差异。)
        返回 dict（含 C8 字段）：
          命中：{"index": i, "verify_ok": bool, "replies": [hex|None,...], "sm_on": bool,
                 "state": 当前状态, "goto": 应答后将跳转到的状态}
          无命中：{"index": -1, "verify_ok": False, "replies": [], "sm_on": bool,
                   "state": 当前状态, "state_skip": 内容命中但被状态门拦下的首条规则索引 or None}
        说明：goto 仅在 SM 开、verify_ok 且 replies[0] 可组帧（实发确会发出）时非空；
              state_skip 仅在 SM 开、有规则按内容命中但当前状态不匹配其 when 时为该规则索引（可为 0）。
        预览只读当前 _ar_state、不推进它（实发推进靠真连接的 _ar_match）。"""
        seq_save = self._ar_seq
        try:
            codec = self._get_codec()
            try:
                text = frame.decode("utf-8" if codec == "auto" else codec, errors="replace")
            except Exception:
                text = ""
            sm_on = bool(self._ar_sm.get("on"))
            state_skip = None        # 内容命中但被状态门拦下的第一条索引（仅 SM 开时记，用于提示）
            for i, rule in enumerate(self._ar_rules):
                if not rule.get("on", True):
                    continue
                if not (rule.get("match") or "").strip():
                    continue
                if not self._ar_hit_test(rule, frame, text):
                    continue
                min_len = self._ar_to_int(rule.get("min_len", 0))
                max_len = self._ar_to_int(rule.get("max_len", 0))
                if (min_len > 0 and len(frame) < min_len) or (max_len > 0 and len(frame) > max_len):
                    continue
                if sm_on and not self._ar_state_ok(rule):
                    if state_skip is None:
                        state_skip = i      # 内容命中但当前状态不符 → 记首条供提示，不作为命中
                    continue
                verify_ok = self._ar_frame_ok(frame, self._ar_to_int(rule.get("verify", 0)))
                replies = []
                script_err = None
                if verify_ok:
                    script = str(rule.get("script") or "").strip()      # str() 容错
                    if script and rule.get("script_on", True):          # B5：预览也跑脚本（无副作用变体）
                        parts, script_err = self._ar_script_eval(rule, frame, preview=True)
                        replies = list(parts or [])
                    else:
                        hexmode = bool(rule.get("reply_hex", True))
                        cs = self._ar_to_int(rule.get("cs", 0))
                        cs_segs = rule.get("cs_segs", []) or []
                        for part in self._ar_build_parts(rule, frame):
                            fr = self._ar_compose_frame(part, hexmode, cs_segs, cs)
                            replies.append(bytes(fr).hex(" ").upper() if fr is not None else None)
                # 预览=实发：goto 经 on_sent 在「首段真正发出」后才推进，故仅当首段能组出帧时才报。
                # 校验不过 / 无应答内容(replies 空) / 首段坏 hex(replies[0] is None，回退发送也会因同样坏 hex
                # 失败、sent_ok=False) → 实发都不会跳转，预览也不报 goto。
                goto = ""
                if sm_on and verify_ok and replies and replies[0] is not None:
                    goto = str(rule.get("goto", "") or "").strip()
                return {"index": i, "verify_ok": verify_ok, "replies": replies,
                        "sm_on": sm_on, "state": self._ar_state, "goto": goto,
                        "script_err": script_err}
            return {"index": -1, "verify_ok": False, "replies": [],
                    "sm_on": sm_on, "state": self._ar_state, "state_skip": state_skip}
        finally:
            self._ar_seq = seq_save

    def _ar_reset_stats(self):
        """清零所有规则的 A3 命中统计（运行态）。"""
        for rule in self._ar_rules:
            rule.pop("_hits", None)
            rule.pop("_hit_time", None)

    def _ar_send(self, reply, hexmode, cs):
        """保留：单帧应答（无 | 分段时的快路径不再走这里，但若外部代码或测试直接调仍可用）。"""
        if not self._ar_on or not self._is_open():
            return
        try:
            self._send_text(reply, hex_mode=hexmode, newline=0, checksum=cs,
                            record_macro=False)
        except Exception:
            _log.debug("_ar_send failed", exc_info=True)

    def _ar_frame_ok(self, frame: bytes, idx: int) -> bool:
        return _ar_core_frame_ok(frame, idx)

    @staticmethod
    def _ar_parse_hex_pat(s):
        return _ar_core_parse_hex_pat(s)

    @staticmethod
    def _ar_hex_at(pat, data, off):
        return _ar_core_hex_at(pat, data, off)

    def _ar_subst_reply(self, reply, data, hex_mode):
        """Substitute reply placeholders; advances _ar_seq when {seq} used."""
        out, self._ar_seq = _ar_core_subst_reply(
            reply, data, hex_mode, seq=getattr(self, "_ar_seq", 0))
        return out

    def _info_dlg(self, title, body, is_error=False):
        """与主界面同主题的信息/错误模态对话框（替代风格不一致的 QMessageBox）。
        parent=None：避免 Qt 父子链对无边框主窗 WM_NCHITTEST 的干扰（modal 由 setModal(True)
        ApplicationModal 提供，与 parent 无关）。dialog exec_() 完即弃、不会泄漏。"""
        ok = {"zh": "确定", "en": "OK", "zh_tw": "確定"}.get(self._lang, "OK")
        InfoDialog(title, body, ok_text=ok, is_error=is_error,
                   theme_id=self._theme_id(), parent=None).exec_()

    def _confirm_dlg(self, title, body, ok_text=None, danger=True, cancel_text=None):
        """主题化二选一确认框（替代 QMessageBox.question）；返回 True=确认 / False=取消。
        danger=True 时确认按钮用红色（删除等破坏性操作）。parent=None 理由同 _info_dlg。"""
        cancel = cancel_text or {"zh": "取消", "en": "Cancel", "zh_tw": "取消"}.get(
            self._lang, "Cancel")
        ok = ok_text or {"zh": "确定", "en": "OK", "zh_tw": "確定"}.get(self._lang, "OK")
        dlg = InfoDialog(title, body, ok_text=ok, is_error=danger,
                         theme_id=self._theme_id(), parent=None,
                         confirm=True, cancel_text=cancel, danger=danger)
        return dlg.exec_() == QDialog.Accepted

    # ----- 会话配置档 导入/导出 -----
    # 包含的 QSettings 键（实际 _save_settings 写入的 key 名，已对齐）：
    #   连接（网络/串口）+ 数据区显示 + 发送区 + 主题/语言 + 多条发送/关键字/帧解析/绘图 + 自动应答 + 自动重连
    # 不含：geometry / h_splitter（窗口位置布局不跨机器搬）、send_history（个人命令历史不导出）
    _CFG_KEYS = _CFG_KEYS_MOD

    def export_config(self):
        """导出当前配置为 JSON：QFileDialog 选保存路径，写入 _CFG_KEYS 里所有非空值。"""
        path, _ = QFileDialog.getSaveFileName(self, self._t("cfg_export"), "CommTool_config.json",
                                              "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        # 主界面很多值（发送框文本、HEX 开关、串口/网络字段等）只在退出 _shutdown 时落盘；
        # 用户刚改完立即导出会拿到旧值。先强制落一次盘保证导出是当前最新状态。
        self._save_settings()
        payload = _cfg_export_payload(
            _cfg_collect_export(lambda k: self.settings.value(k, None), self._CFG_KEYS),
            app="CommTool", version=APP_VERSION)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._info_dlg(self._t("cfg_export"), self._t("cfg_exported", path=path))
        except Exception as e:
            self._info_dlg(self._t("cfg_export"), self._t("cfg_export_fail", err=str(e)), is_error=True)

    def _ar_confirm(self, title, body):
        """主题化「是 / 否」确认框，返回 True=用户选「是」。供脚本导入门禁用。"""
        lm = lambda zh, en, tw: {"zh": zh, "en": en, "zh_tw": tw}.get(self._lang, en)
        return self._confirm_dlg(title, body, ok_text=lm("是", "Yes", "是"), danger=False,
                                 cancel_text=lm("否", "No", "否"))

    def _gate_imported_trigger_actions(self, data):
        """Ask before keeping imported trigger external actions."""
        rules = _cfg_parse_json_list(data.get("triggers"))
        if rules is None:
            return data
        n = _cfg_trigger_ext_count(rules)
        if n == 0:
            return data
        if self._ar_confirm(self._t("trg_import_title"),
                            self._t("trg_import_warn", n=n)):
            return data
        new = dict(data)
        new["triggers"] = _cfg_dumps_list(_cfg_strip_trigger_ext(rules))
        return new

    def _gate_imported_script_lib(self, data):
        """Ask before keeping imported script console library."""
        items = _cfg_parse_json_list(data.get("script_lib"))
        if items is None:
            return data
        n = _cfg_script_lib_count(items)
        if n == 0:
            return data
        if self._ar_confirm(self._t("sc_import_title"),
                            self._t("sc_import_warn", n=n)):
            return data
        return _cfg_drop_script_lib(data)

    def _ar_gate_imported_scripts(self, data):
        """Ask before keeping imported autoreply scripts."""
        rules = _cfg_parse_json_list(data.get("autoreply_rules"))
        if rules is None:
            return data
        n = _cfg_ar_script_count(rules)
        if n == 0:
            return data
        if self._ar_confirm(self._t("ar_script_import_title"),
                            self._t("ar_script_import_warn", n=n)):
            return data
        new = dict(data)
        new["autoreply_rules"] = _cfg_dumps_list(_cfg_strip_ar_scripts(rules))
        return new

    def import_config(self):
        """导入 JSON 配置：批量 setValue 到 QSettings + 立刻刷新 UI。
        能即时生效：主题/语言/显示选项/发送框文本/连接字段(UI 显示，未重连)/自动应答规则与状态。
        需手动操作：当前已开的连接（用户得手动断开重连），其它弹窗(多条/关键字/帧解析/绘图)若打开下次重开生效。"""
        path, _ = QFileDialog.getOpenFileName(self, self._t("cfg_import"), "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            data = payload.get("settings", payload)
            if not isinstance(data, dict):
                raise ValueError("invalid format")
        except Exception as e:
            self._info_dlg(self._t("cfg_import"), self._t("cfg_import_fail", err=str(e)), is_error=True)
            return
        data = self._ar_gate_imported_scripts(data)   # B5：含脚本则征求同意，拒绝则清空脚本
        data = self._gate_imported_script_lib(data)   # 脚本控制台库同理：导入的脚本会在本机执行
        data = self._gate_imported_trigger_actions(data)  # 触发器外部动作同样在本机执行
        s = self.settings
        n = 0
        for k, v in data.items():
            if k in self._CFG_KEYS:
                s.setValue(k, _cfg_coerce_value(v))
                n += 1
        s.sync()
        # 立刻刷 UI（兜底 try：刷新失败不该让导入本身报错）
        try:
            self._apply_loaded_settings()
        except Exception:
            _log.debug("import_config failed", exc_info=True)
        self._info_dlg(self._t("cfg_import"), self._t("cfg_imported", n=n))

    def _apply_loaded_settings(self):
        """从 self.settings 重新载入并即时刷新全部 UI/缓存。
        「导入配置」(import_config) 与「切换配置」(_switch_profile) 共用——两者都是把 self.settings
        的内容整体应用到当前窗口。含语言/显示/主题/连接字段/自动应答/Modbus主机/多条发送/关键字/
        绘图/帧解析/终端。Modbus 主机启用态被强制关（安全：加载配置不等于授权写设备，需显式重开）。"""
        s = self.settings
        # 语言不在 _load_settings 里恢复，得单独读 + _set_language 触发完整 retranslate
        new_lang = s.value("language", self._lang)
        if new_lang != self._lang and new_lang in TR:
            self._set_language(new_lang)
        # _load_settings 覆盖：geometry/recv_font/显示开关/编码/主题/发送选项/连接字段...
        # (geometry/h_splitter 不在 _CFG_KEYS 导入集里，原 QSettings 值不变，restore 等于 no-op)
        self._load_settings()
        # _ar_rules 是 __init__ 里读一次的内存缓存 — 不重载会让匹配走老规则
        self._ar_rules = self._load_ar_rules()
        self._ar_frame = self._load_ar_frame()
        self._ar_fault = self._load_ar_fault()
        self._ar_sm = self._load_ar_sm()      # C8：状态机配置随配置档导入
        self._ar_modbus = self._load_ar_modbus()   # B4：Modbus 从机配置随配置档导入（下方 _ar_reset_state 重建运行态）
        self._recompute_ar_gap()
        self._ar_reset_buf()
        self._ar_reset_state()                # C8：导入新配置=新会话 → 状态机复位到（新）初始状态
        # type=bool 让 QSettings 正确把字符串 "true"/"false"/"1"/"0" 解成 bool，
        # 否则手写 JSON 里的 "false" 经 bool() 会变 True（非空字符串）
        self._ar_on = s.value("autoreply_on", False, type=bool)
        self._update_autoreply_btn()
        self._seq_rules = self._load_seq_rules()   # 自动化序列步骤随配置档导入（对话框下方单独刷新）
        # Modbus 主机也是 __init__ 期读入的运行缓存；导入后重载全部配置并重启调度。
        self._mbm_rules = self._load_mbm_rules()
        requested_mbm_on = s.value("modbus_master_on", False, type=bool)
        # 加载配置本身不是“向当前设备发送”的授权动作。连接已打开时必须暂停，避免加载
        # 一个启用的 05/06/0F/10 规则后立刻改写现场设备；用户需显式重新启用。
        self._mbm_on = self._mbm_import_enabled(requested_mbm_on)
        if requested_mbm_on != self._mbm_on:
            s.setValue("modbus_master_on", False)
            s.sync()
        variant = s.value("modbus_master_variant", "", type=str)
        self._mbm_variant = variant if variant in ("", "rtu", "tcp", "ascii") else ""
        self._mbm_echo = s.value("modbus_master_echo", False, type=bool)
        self._device_registers = self._load_device_registers()
        self._device_plot_tags = self._load_device_link("device_plot_tags")
        self._device_dash_tags = self._load_device_link("device_dash_tags")
        if self._mbm_on and self._ar_on:
            # 加载结果也保持互斥（主机优先）。走 _set_autoreply_enabled 而非手设标志，
            # 才能一并复位状态机 + 同步「打开着的」自动应答对话框 checkbox（否则对话框
            # 仍显示启用、与实际关闭不一致）。enabled=False 不会回触发 _set_mbm_enabled。
            self._set_autoreply_enabled(False)
            s.sync()
        self._mbm_restart()
        # 多条发送 / 关键字高亮 的内存模型也是 __init__ 读一次的缓存。不重载会让
        # 后续编辑（commit 走旧内存）把加载的值再覆盖回去。重载 + 刷 UI 让它们立刻生效。
        self._ms_groups, _ = self._load_ms_groups()
        try:
            self._ms_group_idx = int(s.value("multi_send_group_idx", 0))
        except (ValueError, TypeError):
            self._ms_group_idx = 0
        if not (0 <= self._ms_group_idx < len(self._ms_groups)):
            self._ms_group_idx = 0
        self._rebuild_ms_group_combo()
        self._rebuild_ms_quick_bar()
        self._snippets, snippets_ok = self._load_snippets()
        if not snippets_ok:
            self._save_snippets()
        self._connection_presets, cpresets_ok = self._load_connection_presets()
        if not cpresets_ok:
            self._save_connection_presets()
        self._rebuild_connection_preset_combo()
        self._keyword_groups, self._keyword_active, _ = self._load_keyword_groups()
        self._rebuild_kw_group_combo()
        self._refresh_extra_selections()    # 高亮规则变了 → 重画数据区 extra selections
        # 已打开的对话框同步刷新（_ar_rules 改了对话框内 _rows 仍是旧的，会反写覆盖）
        if getattr(self, "_ar_dlg", None) is not None:
            self._ar_dlg.reload_rows()
        if getattr(self, "_multi_send_dlg", None) is not None:
            self._multi_send_dlg._reload_group_list()
            self._multi_send_dlg._reload_rows()
        if getattr(self, "_keyword_dlg", None) is not None:
            self._keyword_dlg._reload_group_list()
            self._keyword_dlg._reload_rows()
        if getattr(self, "_snip_dlg", None) is not None:
            self._snip_dlg.reload_cfg()
        if getattr(self, "_cpreset_dlg", None) is not None:
            self._cpreset_dlg.reload_cfg()
        if getattr(self, "_mbm_dlg", None) is not None:
            self._mbm_dlg.reload_config()
        if getattr(self, "_device_center_dlg", None) is not None:
            self._device_center_dlg.reload_cfg()
        if getattr(self, "_seq_dlg", None) is not None:
            self._seq_dlg.reload_rows()
        if getattr(self, "_frame_builder_dlg", None) is not None:
            # 配置已由导入/切换替换：丢弃旧槽位尚未落盘的草稿，禁止反写覆盖新配置。
            self._frame_builder_dlg.reload_rows(discard_pending=True)
        # 波形图和帧解析：reload_cfg 内部清旧状态(曲线数据/规则行)再读 settings 重建，
        # 避免新配置和老缓冲数据/旧规则混在一起。
        if getattr(self, "_plot_dlg", None) is not None:
            self._plot_dlg.reload_cfg()
        if getattr(self, "_dash_dlg", None) is not None:
            self._dash_dlg.reload_cfg()
        if getattr(self, "_script_dlg", None) is not None:
            self._script_dlg.reload_cfg()
        if getattr(self, "_frame_dlg", None) is not None:
            self._frame_dlg.reload_cfg()
        self._reload_terminal_from_settings()   # 终端模式三项随配置档加载即时生效，无需重启

    def _reload_terminal_from_settings(self):
        """从 settings 重载终端模式三项（模式 / 本地回显 / 回车）并即时同步 UI 与禁用态。
        供配置档导入后调用，让终端设置无需重启即生效（与其它设置「立刻刷新」一致）。"""
        s = self.settings
        self._terminal_enter = self._safe_enter_idx(s.value("terminal_enter", 0))
        self._terminal_echo = s.value("terminal_echo", False, type=bool)
        if hasattr(self, "sw_term_echo"):
            self.sw_term_echo.blockSignals(True)
            self.sw_term_echo.setChecked(self._terminal_echo)
            self.sw_term_echo.blockSignals(False)
        if hasattr(self, "cb_term_enter"):
            self.cb_term_enter.blockSignals(True)
            self.cb_term_enter.setCurrentIndex(self._terminal_enter)
            self.cb_term_enter.blockSignals(False)
        term_on = s.value("terminal_mode", False, type=bool)
        if term_on != self._terminal_on:
            self._set_terminal_enabled(term_on)   # 变了 → 切换 + 同步开关/占位/禁用态
        else:
            self._apply_terminal_ui(term_on)      # 值未变也确保禁用态正确（_load_settings 动过其它开关）
        self._reload_section_states()

    def _send_subst(self, raw, hex_mode):
        """发送区动态字段替换：
          {count}   1B 计数（每次替换 +1，wrap 0..255）
          {ts}      当前 ms 时间戳低 4B BE
          {rand}    1B 随机
          {randN}   N 字节随机（N=1..256；{rand}=={rand1}）
        HEX 模式替成两位十六进制(空格分隔)，文本模式替成原字符。与自动应答的 {seq}/{ts} 独立计数。"""
        import random
        sep = " " if hex_mode else ""
        def bs(b): return f"{b & 0xFF:02X}" if hex_mode else chr(b & 0xFF)
        def bytes_s(bs_list): return sep.join(bs(b) for b in bs_list)
        if "{count}" in raw:
            self._send_count = (self._send_count + 1) & 0xFF
            raw = raw.replace("{count}", bs(self._send_count))
        if "{ts}" in raw:
            ts = int(time.time() * 1000) & 0xFFFFFFFF
            raw = raw.replace("{ts}", bytes_s([(ts >> 24) & 0xFF, (ts >> 16) & 0xFF,
                                               (ts >> 8) & 0xFF, ts & 0xFF]))
        # {randN}/{rand}：N 可省略=1，上限 256（防 {rand9999} 这种）
        def _rand_repl(m):
            n = int(m.group(1)) if m.group(1) else 1
            n = max(1, min(n, 256))
            return bytes_s([random.randint(0, 255) for _ in range(n)])
        raw = re.sub(r"\{rand(\d*)\}", _rand_repl, raw)
        return raw

    # ----- 命令 DSL：发送框里带时序/重复的一行式自动化 -----
    def _dsl_running(self) -> bool:
        return bool(getattr(self, "_dsl_ops", None))

    def _dsl_start(self, raw, record_macro=True) -> bool:
        """编译并启动 DSL 执行。返回 True 表示已接管（无论后续是否中途失败）。"""
        if self._dsl_running():
            # 定时发送间隔短于整条 DSL 时会再次触发；静默跳过本 tick，避免周期性刷提示。
            if record_macro:
                self.toast(self._t("dsl_busy"), error=True)
            return False
        try:
            ops = send_dsl.compile_dsl(raw, default_hex=self.sw_tx_hex.isChecked())
        except send_dsl.DslError as e:
            self.toast(self._t("dsl_bad", e=e), error=True)
            return False
        if not self._is_open():
            self.toast(self._t("net_not_open"), error=True)
            return False
        if self._io_task_busy(exclude=("periodic",)):
            self.toast(self._t("io_exclusive_busy"), error=True)
            return False
        sends, delay = send_dsl.describe(ops)
        self._dsl_ops = ops
        self._dsl_idx = 0
        self._dsl_record = bool(record_macro)
        self._dsl_gen = getattr(self, "_dsl_gen", 0) + 1
        if sends > 1 or delay:
            self.toast(self._t("dsl_started", n=sends, ms=delay))
        self._dsl_step(self._dsl_gen)
        return True

    def _dsl_step(self, gen):
        """执行下一条指令。gen 代际用于让 _dsl_abort 之后的排队回调自动失效。"""
        if gen != getattr(self, "_dsl_gen", 0) or not self._dsl_running():
            return
        if self._dsl_idx >= len(self._dsl_ops):
            self._dsl_finish()
            return
        op, arg = self._dsl_ops[self._dsl_idx]
        self._dsl_idx += 1
        if op == send_dsl.OP_DELAY:
            QTimer.singleShot(max(0, int(arg)), lambda: self._dsl_step(gen))
            return
        seg, hex_mode = arg
        if hex_mode is None:
            hex_mode = self.sw_tx_hex.isChecked()
        ok = self._send_with_subst(seg, hex_mode=hex_mode, record_macro=self._dsl_record,
                                   allow_running_dsl=True)
        if not ok:
            # 发送失败（未连接/格式错/写失败）立即中止：否则后面每段都再失败一次，刷屏
            if self.sw_period.isChecked():
                self.sw_period.setChecked(False)
            self._dsl_abort()
            return
        QTimer.singleShot(0, lambda: self._dsl_step(gen))   # 让出事件循环，界面不卡

    def _dsl_finish(self):
        self._dsl_ops = None
        self._dsl_idx = 0

    def _dsl_abort(self):
        """中止 DSL（发送失败 / 断连 / 关窗）。代际 +1 让已排队的回调作废。"""
        if not self._dsl_running():
            return
        self._dsl_gen = getattr(self, "_dsl_gen", 0) + 1
        self._dsl_ops = None
        self._dsl_idx = 0

    def _send_with_subst(self, raw, hex_mode, newline=None, checksum=None,
                         record_macro=True, allow_during_exclusive=False,
                         allow_running_dsl=False) -> bool:
        """替换动态字段 → 发送 → 失败回滚 {count}（避免未连接/格式错等失败消耗计数）。
        ({ts}/{rand} 是纯函数无副作用，不用回滚；只有 {count} 有持久状态)"""
        prev_count = self._send_count
        subbed = self._send_subst(raw, hex_mode=hex_mode)
        ok = self._send_text(subbed, hex_mode=hex_mode, newline=newline, checksum=checksum,
                             record_macro=record_macro,
                             allow_during_exclusive=allow_during_exclusive,
                             allow_running_dsl=allow_running_dsl)
        if not ok:
            self._send_count = prev_count
        return ok

    def do_send(self):
        raw_orig = self.txt_send.toPlainText()
        if not raw_orig:
            return
        # 动态字段在发送前替换；不在 _send_text 入口替，避免与自动应答(已自行 subst)双重处理
        # QTimer 触发的是后台周期任务，不属于宏录制的“手动发送”；按钮点击/直接调用仍记录。
        record_macro = self.sender() is not self.send_timer
        # 命令 DSL：文本里含 \!(Delay500) / \!(Repeat3) 等指令时走带时序的分步执行。
        # 不含指令则完全走原路径，行为一字不变。
        if send_dsl.has_dsl(raw_orig):
            was_running = self._dsl_running()
            if self._dsl_start(raw_orig, record_macro=record_macro):
                self._push_send_hist(raw_orig)
            elif not was_running and self.sw_period.isChecked():
                # 编译失败/未连接/任务冲突属于确定性失败，定时器继续只会每周期重复报错。
                self.sw_period.setChecked(False)
            return
        ok = self._send_with_subst(raw_orig, hex_mode=self.sw_tx_hex.isChecked(),
                                   record_macro=record_macro)
        if ok:
            self._push_send_hist(raw_orig)   # 存入历史的是「占位符未替换」的原文，重发可保留 {ts} 等语义
        # 定时发送时任何发送失败(数据格式错误/未连接/无目标/写失败)都关掉定时器，
        # 避免格式错误等确定性失败每周期刷一次 toast 形成轰炸
        if not ok and self.sw_period.isChecked():
            self.sw_period.setChecked(False)

    # ----- 发送命令历史 -----
    def _push_send_hist(self, text):
        """Push successful send into FIFO; adjacent-dedupe; cap 100; persist."""
        self._send_hist_idx = -1
        self._send_hist_pending = ""
        if not (text or "").rstrip("\r\n"):
            return
        new_hist, changed = _hist_push(self._send_hist, text)
        self._send_hist = new_hist
        if not changed:
            return
        try:
            self.settings.setValue("send_history", _hist_dumps(self._send_hist))
        except Exception:
            _log.debug("persist send_history failed", exc_info=True)

    def _load_send_hist(self):
        raw = self.settings.value("send_history", "")
        try:
            loaded = _hist_load_list(raw)
        except Exception:
            _log.debug("load send_history failed", exc_info=True)
            return
        if loaded is not None:
            self._send_hist = loaded

    def _show_hist_at(self, idx):
        """加载历史第 idx 条到 txt_send，光标移末尾。idx=-1 时复原 _send_hist_pending（草稿）。"""
        text = self._send_hist_pending if idx < 0 else self._send_hist[idx]
        # blockSignals 防止 textChanged 联动（如果以后挂联动信号）
        self.txt_send.blockSignals(True)
        self.txt_send.setPlainText(text)
        self.txt_send.blockSignals(False)
        cur = self.txt_send.textCursor()
        cur.movePosition(QTextCursor.End)
        self.txt_send.setTextCursor(cur)

    def _send_hist_prev(self):
        """↑：进入历史 / 往前翻。空历史无动作。"""
        if not self._send_hist:
            return
        if self._send_hist_idx == -1:
            # 进入导航：保存当前草稿，跳到最新一条
            self._send_hist_pending = self.txt_send.toPlainText()
            self._send_hist_idx = len(self._send_hist) - 1
        elif self._send_hist_idx > 0:
            self._send_hist_idx -= 1
        else:
            return    # 已到最早一条
        self._show_hist_at(self._send_hist_idx)

    def _send_hist_next(self):
        """↓：往后翻。到末尾后回到原草稿、退出导航态。"""
        if self._send_hist_idx == -1:
            return
        if self._send_hist_idx < len(self._send_hist) - 1:
            self._send_hist_idx += 1
            self._show_hist_at(self._send_hist_idx)
        else:
            self._send_hist_idx = -1
            self._show_hist_at(-1)

    # ==================== Modbus 主机轮询（master / poll）====================
    # 半双工轮询引擎：按每行各自周期，到点发一条请求帧（RTU 含 CRC / Modbus-TCP 含 MBAP），
    # 收到响应或超时后再发下一条；响应在 _mbm_feed 里按「刚发请求」的 unit/func/qty 切帧解析。
    # 持久化：modbus_master（规则）/ modbus_master_on（总开关）/
    # modbus_master_variant（变体）/ modbus_master_echo（本地回显）。
    # 运行态（不持久化）：_mbm_inflight / _mbm_buf / _mbm_tid / _mbm_due / _mbm_results。
    _MBM_TIMEOUT_MS = 1000
    _MBM_MIN_GUARD_MS = 60   # 超时隔离的下限；实际取本请求完整响应超时，低速大帧会自动增长
    _MBM_QTIMER_MAX_MS = 0x7FFFFFFF

    def _load_device_registers(self):
        from device_resources import normalize_registers
        data = _cfg_parse_json_list(self.settings.value("device_registers", "")) or []
        return normalize_registers(data)

    def _load_device_link(self, key):
        """Load device->plot/dash tag set from a JSON list setting."""
        data = _cfg_parse_json_list(self.settings.value(key, "")) or []
        return {str(t) for t in data if t}

    def _save_device_link(self):
        self.settings.setValue("device_plot_tags",
                               json.dumps(sorted(self._device_plot_tags), ensure_ascii=False))
        self.settings.setValue("device_dash_tags",
                               json.dumps(sorted(self._device_dash_tags), ensure_ascii=False))
        self.settings.sync()

    def _load_mbm_views(self):
        raw = self.settings.value("modbus_master_views", "")
        if not raw:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        out = []
        for item in data:
            name = str(item or "")[:40]
            if name and name not in out:
                out.append(name)
        return out[:32]

    def _mbm_save_views(self):
        self.settings.setValue(
            "modbus_master_views",
            json.dumps(list(getattr(self, "_mbm_views", []) or []), ensure_ascii=False))

    def _load_mbm_rules(self):
        raw = self.settings.value("modbus_master", "")
        try:
            data = json.loads(raw) if raw else []
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        out = []
        for r in data:                       # 逐条规范化：单条损坏只跳过它，不清空整张表
            try:
                out.append(modbus_master.normalize_poll(r))
            except Exception:
                _log.debug("_load_mbm_rules failed", exc_info=True)
        return out

    def _mbm_save_rules(self):
        try:
            self.settings.setValue("modbus_master", json.dumps(
                [modbus_master.normalize_poll(r) for r in self._mbm_rules], ensure_ascii=False))
            self.settings.sync()
        except Exception:
            _log.debug("persist mbm_rules failed", exc_info=True)

    def _mbm_variant_eff(self):
        """生效变体：用户显式选优先；否则按连接类型（TCP Client→tcp，其余→rtu）。
        RTU-over-TCP 无需单独变体：在 TCP Client 上显式选 'rtu' 即发 RTU 帧。"""
        if self._mbm_variant in ("rtu", "tcp", "ascii"):
            return self._mbm_variant
        proto = getattr(self, "_conn_proto", None) or self.cb_proto.currentText()
        return "tcp" if proto == PROTO_TCP_CLIENT else "rtu"

    def _mbm_connection_ready(self):
        """当前实际连接与界面配置一致，且属于主机轮询支持的连接类型。"""
        configured = self.cb_proto.currentText()
        actual = getattr(self, "_conn_proto", None) or configured
        return bool(actual in (PROTO_SERIAL, PROTO_TCP_CLIENT)
                    and configured == actual  # 导入改了协议但旧连接未重连：暂停，禁止发错制式
                    and getattr(self, "_conn_cfg", None) == self._conn_config_signature(configured))

    def _mbm_active(self):
        _xw = getattr(self, "_xfer_worker", None)
        return bool(self._mbm_connection_ready()
                    and self._mbm_on and self._is_open()
                    and not getattr(self, "_seq_on", False)
                    and getattr(self, "_script_worker", None) is None
                    and not bool(getattr(getattr(self, "_macro", None), "recording", False))
                    and not (_xw is not None and _xw.isRunning())
                    and any(r.get("enabled") for r in self._mbm_rules))

    def _mbm_import_enabled(self, requested):
        """连接期间导入只加载规则，不继承“启用”状态，避免导入动作直接产生总线写入。"""
        return bool(requested and not self._is_open())

    def _mbm_restart(self):
        """开关/连接/规则/变体变化后：复位运行态并按需启动轮询。"""
        old_info = getattr(self, "_mbm_inflight", None)
        if hasattr(self, "_mbm_to"):
            self._mbm_to.stop()
        if hasattr(self, "_mbm_sched"):
            self._mbm_sched.stop()
        self._mbm_inflight = None
        self._mbm_buf = b""
        self._mbm_due = {}
        self._mbm_results = {}     # 规则增删/重排后清结果，避免旧结果按旧索引错位到新行
        if getattr(self, "_seq_waiting_mbm", False):
            # 序列等待在途请求时若用户切换了 Modbus 配置/开关，restart 会强制取消 inflight；
            # 线路上的旧响应仍可能迟到，按该请求完整超时窗口隔离后再放行序列，避免永久等待或误配。
            if old_info is not None:
                guard_ms = max(self._MBM_MIN_GUARD_MS,
                               int(old_info.get("timeout_ms", self._MBM_TIMEOUT_MS)))
                deadline = time.monotonic() + guard_ms / 1000.0
                if self._seq_wait_mbm_variant in ("rtu", "ascii"):
                    self._mbm_guard_until = max(self._mbm_guard_until, deadline)
                else:
                    self._seq_wait_mbm_until = max(self._seq_wait_mbm_until, deadline)
            self._seq_mbm_release_check()
        if self._mbm_active():
            self._mbm_tick()

    def _mbm_rtu_silent_ms(self):
        """Modbus RTU inter-frame silence (>= 3.5 chars)."""
        return _mbm_timing_silent_ms(self._mbm_serial_baud(), self._mbm_serial_char_bits())

    def _mbm_serial_baud(self):
        """优先使用连接打开时的真实波特率，不用可能已被配置导入改写的界面值。"""
        cfg = getattr(self, "_conn_cfg", None)
        if cfg and cfg[0] == PROTO_SERIAL and len(cfg) > 2 and cfg[2]:
            return max(int(cfg[2]), 300)
        try:
            return max(int(str(self.cb_baud.currentText()).strip()), 300)
        except (ValueError, TypeError):
            return 9600

    def _mbm_serial_char_bits(self):
        """Bits per character from live/open serial config."""
        cfg = getattr(self, "_conn_cfg", None)
        try:
            if cfg and cfg[0] == PROTO_SERIAL and len(cfg) > 5:
                databits, parity, stopbits = (int(cfg[3]), str(cfg[4]), float(cfg[5]))
            else:
                databits = int(self.cb_databits.currentText())
                parity = self.cb_parity.currentText()
                stopbits = float(self.cb_stopbits.currentText())
        except (ValueError, TypeError):
            return 11.0
        return _mbm_timing_char_bits(databits, parity, stopbits)

    def _mbm_rtu_tx_guard_ms(self, frame_len):
        """After broadcast TX: wait full frame time + t3.5."""
        return _mbm_timing_tx_guard_ms(
            frame_len, self._mbm_serial_baud(), self._mbm_serial_char_bits())

    def _mbm_tick(self):
        """Schedule: poll soonest due rule, else arm single-shot timer."""
        if self._mbm_inflight is not None or not self._mbm_active():
            return
        now = time.monotonic()
        best_i, wait = _mbm_sched_pick_next(
            self._mbm_rules, self._mbm_due, now, self._mbm_guard_until)
        if best_i is None:
            return
        if wait <= 0.0:
            self._mbm_poll(best_i)
        else:
            delay_ms = _mbm_sched_delay_ms(wait, self._MBM_QTIMER_MAX_MS)
            self._mbm_sched.start(delay_ms)

    def _mbm_timeout_ms(self, frame, r):
        """Response timeout = base + serial wire time (TCP uses fixed base)."""
        base = (self._device_scan_timeout_ms
                if self._device_scan_state is not None else self._MBM_TIMEOUT_MS)
        proto = getattr(self, "_conn_proto", None) or self.cb_proto.currentText()
        if proto != PROTO_SERIAL:
            return base
        resp_len = _mbm_timing_resp_len(
            r["func"], r["qty"], variant=self._mbm_variant_eff())
        return _mbm_timing_timeout_ms(
            base, len(frame), resp_len,
            self._mbm_serial_baud(), self._mbm_serial_char_bits())

    @staticmethod
    def _mbm_span_bad(r):
        """True when continuous read/write span crosses 0xFFFF."""
        return _mbm_timing_span_bad(r)

    def _mbm_poll(self, i):
        """构造并发出第 i 行的请求帧，登记在途请求 + 启动响应超时。"""
        r = modbus_master.normalize_poll(self._mbm_rules[i])
        variant = self._mbm_variant_eff()
        if (r["unit"] is None or r["addr"] is None or r["period"] is None
                or (r["func"] in modbus_master.READ_FUNCS + (0x17,) and r["qty"] is None)
                or (r["func"] == 0x17 and r.get("write_addr") is None)
                or (variant in ("rtu", "ascii") and r["unit"] > 247)):
            self._mbm_set_result(i, "err", self._t("mbm_st_badparam"))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), 1000)
            self._mbm_sched.start(0)   # 异步排下次：避免大量非法/广播规则同步递归致栈溢出
            return
        # 写值守卫：输入空白/非法/越界 → 报错、不发送（绝不静默截断或写 0）
        if self._mbm_span_bad(r):
            # 连续读写范围不能跨出 16 位地址空间。构帧层 _check_address_span 也会拦，
            # 但那条是未本地化的异常文本，这里统一成「参数非法」。
            self._mbm_set_result(i, "err", self._t("mbm_st_badparam"))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
            self._mbm_sched.start(0)
            return
        if r["func"] == 0x08 and (r.get("diag_sub") is None or r.get("diag_data") is None):
            self._mbm_set_result(i, "err", self._t("mbm_st_badparam"))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
            self._mbm_sched.start(0)
            return
        if r["func"] == 0x16 and (r.get("and_mask") is None or r.get("or_mask") is None):
            self._mbm_set_result(i, "err", self._t("mbm_st_badparam"))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
            self._mbm_sched.start(0)
            return
        if r["func"] == 0x2B and (r.get("read_code") is None or r.get("object_id") is None):
            self._mbm_set_result(i, "err", self._t("mbm_st_badparam"))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
            self._mbm_sched.start(0)
            return
        if ((r["func"] in modbus_master.WRITE_SINGLE and r["wval"] is None)
                or (r["func"] in modbus_master.WRITE_MULTI and not r["wvals"])):
            self._mbm_set_result(i, "err", self._t("mbm_st_noval"))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
            self._mbm_sched.start(0)   # 异步排下次：避免大量非法/广播规则同步递归致栈溢出
            return
        # RTU/ASCII unit 0 = broadcast: only single/multi write allowed (no response).
        # Reject reads and non-broadcastable FCs (08/0B/11/17, etc.).
        if variant in ("rtu", "ascii") and r["unit"] == 0:
            if r["func"] not in (modbus_master.WRITE_SINGLE
                                 + modbus_master.WRITE_MULTI + (0x16,)):
                self._mbm_set_result(i, "err", self._t("mbm_st_broadcast_nowrite"))
                self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
                self._mbm_sched.start(0)
                return
        if r["func"] in modbus_master.READ_FUNCS:
            arg = r["qty"]
        elif r["func"] in modbus_master.WRITE_MULTI:
            arg = r["wvals"]
        elif r["func"] == 0x08:
            arg = (int(r.get("diag_sub") or 0), int(r.get("diag_data")))
        elif r["func"] == 0x16:
            arg = (int(r["and_mask"]), int(r["or_mask"]))
        elif r["func"] == 0x2B:
            arg = {"mei": 0x0E,
                   "read_code": int(r.get("read_code") or 1),
                   "object_id": int(r.get("object_id") or 0)}
        elif r["func"] in (0x0B, 0x11):
            arg = 0
        elif r["func"] == 0x17:
            arg = r.get("rw") or {
                "read_addr": r["addr"], "read_qty": r["qty"],
                "write_addr": r.get("write_addr", r["addr"]),
                "write_vals": r.get("wvals") or [],
            }
            if not arg.get("write_vals"):
                self._mbm_set_result(i, "err", self._t("mbm_st_noval"))
                self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
                self._mbm_sched.start(0)
                return
        else:
            arg = r["wval"]
        try:
            if variant == "tcp":
                self._mbm_tid = (self._mbm_tid + 1) & 0xFFFF
                frame = modbus_master.build_tcp_request(
                    self._mbm_tid, r["unit"], r["func"], r["addr"], arg)
                tid = self._mbm_tid
            elif variant == "ascii":
                frame = modbus_master.build_ascii_request(r["unit"], r["func"], r["addr"], arg)
                tid = None
            else:
                frame = modbus_master.build_rtu_request(r["unit"], r["func"], r["addr"], arg)
                tid = None
        except Exception as e:
            self._mbm_set_result(i, "err", str(e))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
            self._mbm_sched.start(0)   # 异步排下次：避免大量非法/广播规则同步递归致栈溢出
            return
        # RTU/ASCII 广播写：发送成功即完成本轮，不登记 inflight、不启动响应超时。
        if variant in ("rtu", "ascii") and r["unit"] == 0:
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
            sent_ok = self._mbm_send_raw(frame)
            # 广播无响应可作为帧结束锚点，自行覆盖发送时间+t3.5；期间本地回显也会被丢弃。
            self._mbm_guard_until = (time.monotonic()
                                     + self._mbm_rtu_tx_guard_ms(len(frame)) / 1000.0)
            if sent_ok:
                self._mbm_set_result(i, "ok", self._t("mbm_st_broadcast"))
            else:
                self._mbm_set_result(i, "err", self._t("mbm_st_senderr"))
            self._mbm_sched.start(0)   # 异步排下次：避免大量非法/广播规则同步递归致栈溢出
            return
        # 写类预期回显：05 线圈 0/1→0xFF00/0x0000；06 即写入值；0F/10 回显 (起始地址, 数量)
        exp_write = None
        if r["func"] in modbus_master.WRITE_SINGLE:
            ev = (0xFF00 if r["wval"] else 0x0000) if r["func"] == 0x05 else (r["wval"] & 0xFFFF)
            exp_write = (r["addr"], ev)
        elif r["func"] in modbus_master.WRITE_MULTI:
            exp_write = (r["addr"], r["qty"])
        # 08 回环诊断：子功能必须回显；子功能 0 还要求数据原样返回。
        exp_diag = None
        if r["func"] == 0x08:
            exp_diag = (int(r.get("diag_sub") or 0), int(r.get("diag_data")))
        # 先登记在途请求再发送：避免响应在 send() 内被同步投递时（罕见但可能）因 inflight
        # 尚未就绪而被 _mbm_feed 丢弃；发送失败再回滚。echo=刚发出的 RTU/ASCII 帧，用于剥串口本地回显。
        self._mbm_buf = b""
        self._mbm_inflight = {"i": i, "unit": r["unit"], "func": r["func"],
                              "qty": r["qty"], "tid": tid, "variant": variant,
                              "addr": r["addr"], "exp_write": exp_write,
                              "exp_diag": exp_diag,
                              "echo": frame if variant in ("rtu", "ascii") else None}
        self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
        timeout_ms = self._mbm_timeout_ms(frame, r)
        self._mbm_inflight["timeout_ms"] = timeout_ms
        self._mbm_to.start(timeout_ms)
        if not self._mbm_send_raw(frame):
            self._mbm_to.stop()
            self._mbm_inflight = None
            self._mbm_set_result(i, "err", self._t("mbm_st_senderr"))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), max(r["period"], 200))
            self._mbm_sched.start(0)   # 异步排下次：避免大量非法/广播规则同步递归致栈溢出
            return

    def _mbm_send_raw(self, frame) -> bool:
        """整帧直发（不追加换行/校验）+ 显示到数据区(TX)。成功 True。"""
        if not self._is_open():
            return False
        frame = bytes(frame)
        send_target = self._send_target()
        try:
            sent = self.conn.send(frame, send_target)
        except Exception:
            return False
        # 串口 write() 允许返回短写；只有整帧全部交付才可登记为成功并等待响应。
        if sent == SEND_NO_TARGET or sent != len(frame):
            self._abort_partial_tcp_stream(sent, len(frame))
            return False
        self._stat_note_tx(len(frame))
        try:
            if self._hexdump_on:
                disp = self._hexdump_block(frame)
            elif self._numview_on:
                disp = self._numview_block(frame, carry=False)
            elif self.sw_rx_hex.isChecked():
                disp = self._bytes_to_hex(frame) + " "
            else:
                disp = frame.decode(self._send_codec(), errors="replace")
            self._append_block_data(disp, direction="tx", force_new_block=True)
            self._last_direction = "tx"
        except Exception:
            _log.debug("_mbm_send_raw failed", exc_info=True)
        # Modbus 主机也是绕过 _send_text 的直发路径：录制与「发送」范围的触发规则都得盯到
        try:
            self._record_stream_tx(frame, source=send_target)
        except Exception:
            _log.debug("_mbm_send_raw failed", exc_info=True)
        return True

    def _mbm_feed(self, data):
        """收到数据：若有在途轮询请求，累积并尝试切出一帧响应、解析、更新该行结果。
        坏帧/串口本地回显/杂散字节用「丢 1 字节重同步」处理，而非清空整缓冲——避免请求回显
        与合法响应粘包后把响应一并丢掉（RS-485 半双工本地回显常见）。"""
        if self._mbm_inflight is None:
            # 超时隔离期间若迟到字节开始到达：RTU 从最后一字节起重新满足 t3.5 确保整帧排空；
            # ASCII 无 t3.5 概念但同样需要丢掉隔离窗内的迟到字节（无 TID 可辨新旧请求）。
            veff = self._mbm_variant_eff()
            if time.monotonic() < self._mbm_guard_until and veff in ("rtu", "ascii"):
                if veff == "rtu":
                    self._mbm_guard_until = max(
                        self._mbm_guard_until,
                        time.monotonic() + self._mbm_rtu_silent_ms() / 1000.0)
            return
        self._mbm_buf += bytes(data)
        if len(self._mbm_buf) > 4096:                 # 防异常流无界增长
            self._mbm_buf = self._mbm_buf[-4096:]
        info = self._mbm_inflight
        if info["variant"] == "tcp":
            # 按 MBAP 完整帧跳过迟到的旧 TID/Unit，再找当前响应；只对畸形 MBAP/PDU 清缓冲。
            try:
                result, consumed = modbus_master.take_tcp_response_matching(
                    self._mbm_buf, info["tid"], info["func"], info["unit"])
            except modbus_slave.ModbusException as e:
                self._mbm_set_result(info["i"], "exc", self._t("mbm_st_exc", code=e.code))
                self._mbm_finish_inflight()
            except ValueError:
                self._mbm_buf = b""
            else:
                if consumed:
                    self._mbm_buf = self._mbm_buf[consumed:]
                if result is not None:
                    self._mbm_apply(info, result)
            return
        if info["variant"] == "ascii":
            # 本地回显模式（半双工 RS-485 适配器会回显刚发的 ASCII 请求帧）：先剥掉一份与请求
            # 完全相同的前导回显，再解析真正响应。完整回显出现前保留缓冲继续等（与 RTU 分支一致）。
            if self._mbm_echo and info.get("echo") and not info.get("echo_done"):
                rest, found = modbus_master.strip_local_echo(self._mbm_buf, info["echo"])
                if not found:
                    return
                self._mbm_buf = rest
                info["echo_done"] = True
            # 循环重同步：单 chunk 内可能坏帧+好帧粘在一起（串口 readyRead 多帧/TCP Nagle 合包），
            # 或线噪声 ':' 夹在真响应前。坏帧（LRC 错/unit 不符/格式错）丢到本帧 \n 后继续试下一帧，
            # 直到无可解析帧（返回 None 等更多字节）或缓冲空——与 RTU 分支的"丢1字节重同步"对齐。
            while self._mbm_buf:
                try:
                    out = modbus_master.take_ascii_response(
                        self._mbm_buf, info["unit"], info["func"], info["qty"])
                except modbus_slave.ModbusException as e:
                    self._mbm_set_result(info["i"], "exc", self._t("mbm_st_exc", code=e.code))
                    self._mbm_finish_inflight()
                    return
                except ValueError:
                    nl = self._mbm_buf.find(b"\n")
                    self._mbm_buf = self._mbm_buf[nl + 1:] if nl >= 0 else b""
                    continue                       # 丢掉坏帧，继续试后续
                if out is None:
                    return                         # 还需更多字节
                result, consumed = out
                self._mbm_buf = self._mbm_buf[consumed:]
                # 记录响应帧长度（含 ':'、CRLF、LRC）：低速串口下 _mbm_finish_inflight 用它
                # 算出"整帧含帧界完全离线上"的 guard 时长，避免尾字节迟到串到下一请求。
                info["resp_len"] = consumed
                self._mbm_apply(info, result)
                return
        # RTU「本地回显模式」：串口适配器会回显发出的帧时，先剥掉一份与请求完全相同的前导回显，
        # 再解析真正的从机响应。写功能码 05/06 的成功响应与请求同形——仅此法能把回显与
        # 「写成功 / 写异常(86 xx)」区分开（内容判不了，故由用户按硬件实际声明）。
        if self._mbm_echo and info.get("echo") and not info.get("echo_done"):
            # 回显前可能夹有线噪声/上次通信残留，不能只看 startswith；否则下面的通用
            # resync 会落到 05/06 请求回显上，并把它误判成从机写成功。完整回显出现前
            # 保留缓冲继续等（本地回显模式由用户按硬件声明，未见回显则最终按超时处理）。
            rest, found = modbus_master.strip_local_echo(self._mbm_buf, info["echo"])
            if not found:
                return
            self._mbm_buf = rest
            info["echo_done"] = True
        # RTU：每次失败必丢 1 字节，缓冲又有 4096 上限，因此循环天然有限；不另设较小 guard，
        # 避免大量残留字节后已经到达的完整响应被搁在缓冲里、因没有新数据事件而最终超时。
        while self._mbm_buf:
            try:
                out = modbus_master.take_rtu_response(
                    self._mbm_buf, info["unit"], info["func"], info["qty"])
            except modbus_slave.ModbusException as e:
                self._mbm_set_result(info["i"], "exc", self._t("mbm_st_exc", code=e.code))
                self._mbm_finish_inflight()
                return
            except ValueError:
                self._mbm_buf = self._mbm_buf[1:]     # 坏帧/回显/杂散 → 丢 1 字节重同步
                continue
            if out is None:
                return                                # 还需更多字节
            self._mbm_apply(info, out[0])
            return

    def _mbm_apply(self, info, result):
        """对结构合法的响应做语义核对后写入结果行，并结束本次在途请求。"""
        try:
            err = self._mbm_validate(info, result)        # 读数量 / 写回显核对
            if err:
                self._mbm_set_result(info["i"], "err", err)
            else:
                self._structured_feed_modbus(info, result)
                self._mbm_set_result(info["i"], "ok", self._mbm_fmt_result(info, result))
        finally:
            # 无论结果更新/格式化是否异常，都必须释放在途请求，否则 inflight 泄漏到超时。
            self._mbm_finish_inflight()

    def _mbm_validate(self, info, result):
        """对结构合法的响应做语义核对：读回的数量是否够、写回显地址/值是否相符。
        返回错误文案；None=通过。"""
        if "regs" in result:
            if len(result["regs"]) != info["qty"]:
                return self._t("mbm_st_badresp")
        elif "bits" in result:
            expected = ((info["qty"] + 7) // 8) * 8
            if len(result["bits"]) != expected:
                return self._t("mbm_st_badresp")
        elif "echo" in result:
            exp = info.get("exp_write")
            if exp is not None and tuple(result["echo"]) != tuple(exp):
                return self._t("mbm_st_badresp")
        elif "diag" in result:
            exp = info.get("exp_diag")
            if exp is not None:
                sub, data = result["diag"]
                # 非 0 子功能的数据字段按规范是计数值等，不能按请求数据核对。
                if sub != exp[0] or (exp[0] == 0 and data != exp[1]):
                    return self._t("mbm_st_badresp")
        return None

    def _mbm_finish_inflight(self):
        self._mbm_to.stop()
        info = self._mbm_inflight
        self._mbm_inflight = None
        self._mbm_buf = b""
        if info is not None and info.get("variant") in ("rtu", "ascii"):
            # RTU/ASCII 均无事务 ID：正常响应后也必须留出帧间静默，不能刚收完响应立即发下一帧。
            # RTU 无显式帧界，t3.5 是协议要求的帧间最小静默，按规范量级即可。
            # ASCII 有 \r\n 帧界本不需 t3.5，但低速串口下响应尾字节可能还没离线上就发下一帧，
            # 尾部 CRLF 迟到一个字节就会被下一轮轮询当线噪声/残响应吞掉 —— 用响应整帧传输时间
            # （含帧界）量级的 guard，确保整帧含 CRLF 完全离线上再放行下一请求。
            # 非串口（TCP/RTU-over-TCP）无波特率概念，用 t3.5 量级兜底（帧界本身已提供切帧依据）。
            if info["variant"] == "rtu":
                self._mbm_guard_until = time.monotonic() + self._mbm_rtu_silent_ms() / 1000.0
            elif info["variant"] == "ascii":
                resp_len = int(info.get("resp_len") or 0)
                if self._conn_proto == PROTO_SERIAL and resp_len > 0:
                    # 传输时间 + t3.5 余量：低速大帧下确保整帧含 CRLF 离线上。
                    self._mbm_guard_until = (
                        time.monotonic()
                        + self._mbm_rtu_tx_guard_ms(resp_len) / 1000.0)
                else:
                    self._mbm_guard_until = time.monotonic() + self._mbm_rtu_silent_ms() / 1000.0
        self._mbm_tick()
        if getattr(self, "_seq_waiting_mbm", False):
            self._seq_mbm_release_check()

    def _mbm_on_timeout(self):
        info = self._mbm_inflight
        if info is None:
            return
        self._mbm_set_result(info["i"], "timeout", self._t("mbm_st_timeout"))
        _note_to = getattr(self, "_stat_note_timeout", None)
        if callable(_note_to):
            _note_to("mbm")
        self._mbm_inflight = None
        self._mbm_buf = b""
        # RTU/ASCII 无事务 ID：超时后至少再隔离一个"本请求完整超时窗口"。隔离期间收到迟到
        # 字节还会在 _mbm_feed 中延长到最后一字节后的 t3.5(RTU)，显著降低误配到下一请求的风险。
        if info.get("variant") in ("rtu", "ascii"):
            guard_ms = max(self._MBM_MIN_GUARD_MS, int(info.get("timeout_ms", self._MBM_TIMEOUT_MS)))
            self._mbm_guard_until = time.monotonic() + guard_ms / 1000.0
        elif getattr(self, "_seq_waiting_mbm", False):
            # Modbus-TCP 平时可凭 TID 跳过迟到帧；序列匹配没有 TID，因此启动序列前也要留出
            # 一个完整响应超时窗口，把超时后才到的旧 TCP 响应丢干净。
            guard_ms = max(self._MBM_MIN_GUARD_MS, int(info.get("timeout_ms", self._MBM_TIMEOUT_MS)))
            self._seq_wait_mbm_until = time.monotonic() + guard_ms / 1000.0
        self._mbm_tick()
        if getattr(self, "_seq_waiting_mbm", False):
            self._seq_mbm_release_check()

    def _mbm_fmt_result(self, info, result):
        if "regs" in result:
            regs = result["regs"]
            dec = " ".join(str(v) for v in regs)
            hx = " ".join("%04X" % v for v in regs)
            return "%s  (0x %s)" % (dec, hx)
        if "bits" in result:
            bits = result["bits"][:info["qty"]]
            return " ".join("1" if b else "0" for b in bits)
        if "echo" in result:
            a, v = result["echo"]
            if info["func"] in modbus_master.WRITE_MULTI:
                return self._t("mbm_st_written_multi", addr=a, n=v)
            return self._t("mbm_st_written", addr=a, val=v)
        if "diag" in result:
            sub, data = result["diag"]
            # 与读寄存器一致地同时给十进制和十六进制：回环诊断要和发出的值逐位对照，
            # 而请求里的数据通常是按 0x 十六进制填的。
            return self._t("mbm_st_diag", sub=sub, val="%d (0x%04X)" % (data, data))
        if "event_count" in result:
            return self._t("mbm_st_events", status=result.get("status", 0),
                           n=result["event_count"])
        if "server_id" in result:
            sid = result.get("server_id") or b""
            if isinstance(sid, str):
                sid_txt = sid
            else:
                try:
                    sid_txt = bytes(sid).decode("ascii", "replace")
                except Exception:
                    sid_txt = bytes(sid).hex(" ")
            run_key = "mbm_st_run_on" if result.get("run") else "mbm_st_run_off"
            return self._t("mbm_st_serverid", sid=sid_txt, run=self._t(run_key))
        if "mask" in result:
            a, am, om = result["mask"]
            return self._t("mbm_st_mask", addr=a, aand=am, oor=om)
        if "device_id" in result:
            did = result["device_id"]
            parts = []
            for oid, val in sorted((did.get("objects") or {}).items()):
                if isinstance(val, (bytes, bytearray)):
                    txt = bytes(val).decode("utf-8", "replace")
                else:
                    txt = str(val)
                parts.append("%d=%s" % (oid, txt))
            return self._t("mbm_st_devid", code=did.get("read_code", 0),
                           objs="; ".join(parts) if parts else "-")
        return ""

    def _mbm_set_result(self, i, status, text):
        self._mbm_results[i] = {"status": status, "text": text}
        dlg = getattr(self, "_mbm_dlg", None)
        if dlg is not None and dlg.isVisible():
            try:
                dlg.update_result(i, status, text)
            except Exception:
                _log.debug("_mbm_set_result failed", exc_info=True)
        self._device_scan_result(i, status, text)

    def _start_device_scan(self, rules, timeout_ms, on_result, on_done):
        """临时复用 Modbus 半双工调度器执行一次性扫描，结束后恢复原轮询配置。"""
        if self._device_scan_state is not None:
            return False
        if not self._is_open() or not self._mbm_connection_ready():
            self.toast(self._t("device_scan_need_connection"), error=True)
            return False
        if self._io_task_busy(exclude=("modbus",)):
            self.toast(self._t("io_exclusive_busy"), error=True)
            return False
        normalized = [modbus_master.normalize_poll(rule) for rule in rules]
        if not normalized:
            return False
        setting_keys = ("modbus_master", "modbus_master_on",
                        "modbus_master_variant", "modbus_master_echo",
                        "autoreply_on")
        persisted = {
            key: (self.settings.contains(key), self.settings.value(key, None))
            for key in setting_keys
        }
        old_inflight = self._mbm_inflight
        dlg = getattr(self, "_mbm_dlg", None)
        self._device_scan_state = {
            "rules": normalized,
            "completed": set(),
            "on_result": on_result,
            "on_done": on_done,
            "old_rules": self._mbm_rules,
            "old_on": self._mbm_on,
            "old_ar_on": self._ar_on,
            "old_variant": self._mbm_variant,
            "old_echo": self._mbm_echo,
            "old_results": {
                index: dict(result) for index, result in self._mbm_results.items()
            },
            "old_persisted": persisted,
            "old_dlg_enabled": dlg.isEnabled() if dlg is not None else None,
            "old_dlg_dirty": bool(dlg._dirty) if dlg is not None else None,
            "finishing": False,
        }
        # 接管一个已经在轮询的 RTU/ASCII 主机时，旧请求的迟到响应不能误配给扫描首项。
        if old_inflight is not None and self._mbm_variant_eff() in ("rtu", "ascii"):
            guard_ms = max(self._MBM_MIN_GUARD_MS,
                           int(old_inflight.get("timeout_ms", self._MBM_TIMEOUT_MS)))
            self._mbm_guard_until = max(
                self._mbm_guard_until, time.monotonic() + guard_ms / 1000.0)
        self._device_scan_timeout_ms = max(50, min(5000, int(timeout_ms)))
        # 扫描期间与主机互斥：临时关闭自动应答从机，避免 _mbm_on && _ar_on 双开
        # （不变量与 _set_mbm_enabled 的开主机必关从机一致；结束由 _stop_device_scan 恢复）。
        self._ar_on = False
        self._sync_autoreply_ui()
        try:
            self._mbm_rules = normalized
            self._mbm_on = True
            if dlg is not None:
                dlg.setEnabled(False)
            self._mbm_restart()
            self._refresh_workspace_statuses()
        except Exception:
            # 状态变更中途失败：回滚接管，避免 _device_scan_state 残留/对话框禁用/规则被替换。
            self._stop_device_scan(cancelled=True)
            return False
        return True

    def _device_scan_result(self, index, status, text):
        state = self._device_scan_state
        if state is None or index in state["completed"]:
            return
        state["completed"].add(index)
        try:
            state["on_result"](index, status, text)
        except Exception:
            _log.debug("device_scan on_result failed", exc_info=True)
        if len(state["completed"]) >= len(state["rules"]) and not state["finishing"]:
            state["finishing"] = True
            QTimer.singleShot(0, lambda: self._stop_device_scan(cancelled=False))

    def _stop_device_scan(self, cancelled=False):
        state = self._device_scan_state
        if state is None:
            return
        self._device_scan_state = None
        self._mbm_rules = state["old_rules"]
        self._mbm_on = state["old_on"]
        self._ar_on = bool(state.get("old_ar_on", False))   # 扫描期间被临时关掉的从机要恢复
        self._mbm_variant = state["old_variant"]
        self._mbm_echo = state["old_echo"]
        # 即使未来新增了扫描期间可触发的配置入口，也把四个持久化键精确恢复，
        # 避免内存已还原而重启后读到扫描态/临时修改。
        for key, (existed, value) in state["old_persisted"].items():
            if existed:
                self.settings.setValue(key, value)
            else:
                self.settings.remove(key)
        self.settings.sync()
        self._mbm_restart()
        # restart 会按设计清空结果（避免规则重排后错位）；扫描结束恢复的是原规则，
        # 因而要在 restart 之后放回快照，并同步已打开的主机窗口。
        self._mbm_results = state["old_results"]
        dlg = getattr(self, "_mbm_dlg", None)
        if dlg is not None:
            dlg.setEnabled(state["old_dlg_enabled"]
                           if state["old_dlg_enabled"] is not None else True)
            # 扫描期间新打开/原本无草稿的窗口曾显示临时扫描规则，结束后重载原配置；
            # 原本已有未应用草稿则完整保留，不替用户丢弃编辑。
            if state["old_dlg_dirty"] is not True:
                dlg.reload_config()
            else:
                for index, result in self._mbm_results.items():
                    try:
                        dlg.update_result(index, result.get("status", ""),
                                          result.get("text", ""))
                    except Exception:
                        _log.debug("_stop_device_scan failed", exc_info=True)
        self._sync_autoreply_ui()
        try:
            state["on_done"](bool(cancelled))
        except Exception:
            _log.debug("device_scan on_done failed", exc_info=True)
        self._refresh_workspace_statuses()

    def _structured_add(self, samples):
        added = self._structured_recorder.add(samples)
        dlg = getattr(self, "_structured_dlg", None)
        if added and dlg is not None:
            try:
                dlg.on_samples(added)
            except Exception:
                _log.debug("_structured_add failed", exc_info=True)
        return added

    def _structured_feed_modbus(self, info, result):
        # 设备扫描只是发现性请求，不应污染结构化录制或可见联动视图。
        if getattr(self, "_device_scan_state", None) is not None:
            return
        if "regs" not in result:
            return
        try:
            want_record = self._structured_recorder.recording
            plot_tags = self._device_plot_tags
            dash_tags = self._device_dash_tags
            if not want_record and not plot_tags and not dash_tags:
                return
            from device_resources import decode_modbus_samples
            # 17 的读段读的就是保持寄存器，与 03 同语义；寄存器定义只允许 3/4，
            # 不映射的话 FC23 轮询结果永远匹配不上任何标签。
            dec_func = 0x03 if info["func"] == 0x17 else info["func"]
            samples = decode_modbus_samples(
                self._device_registers, info["unit"], dec_func,
                info["addr"], result["regs"])
            if not samples:
                return
            if want_record:
                self._structured_add(samples)
            if plot_tags:
                self._feed_named_view("_plot_dlg", plot_tags, samples)
            if dash_tags:
                self._feed_named_view("_dash_dlg", dash_tags, samples)
        except Exception:
            # Structured/plot side-path must not block Modbus apply / inflight release.
            _log.debug("_mbm_feed_views failed", exc_info=True)

    def _feed_named_view(self, attr, tags, samples):
        """把命中 tags 的样本喂给 plot/dashboard（仅对话框可见时；与各自 feed 同条件）。"""
        dlg = getattr(self, attr, None)
        if dlg is None or not dlg.isVisible():
            return
        picked = [s for s in samples if s.get("tag") in tags]
        if not picked:
            return
        try:
            dlg.feed_named_samples(picked)
        except Exception:
            _log.debug("_feed_named_view failed", exc_info=True)

    def _structured_feed_protocol(self, data):
        if not self._structured_recorder.recording:
            return
        rules = self._proto_rules()
        rule = next((item for item in rules
                     if not item["header"] or bytes(data).startswith(item["header"])), None)
        if rule is None:
            return
        now = time.time()
        samples = []
        for name, offset, typ in rule["fields"]:
            size = binproto.field_size(typ)
            if size <= 0 or offset < 0 or offset + size > len(data):
                continue
            value = binproto.read_field(data, offset, typ)
            if value is None:
                continue
            samples.append({
                "timestamp": now, "source": "protocol", "tag": name,
                "value": value, "unit": "",
                "raw": bytes(data[offset:offset + size]).hex(" ").upper(),
            })
        self._structured_add(samples)

    def _jump_from_io_stats(self):
        """Status-bar RX/TX click: jump to latest stats sample wall time."""
        hist = getattr(getattr(self, "_io_stats", None), "history", None) or []
        if hist:
            wall = hist[-1].get("wall_t")
        else:
            wall = getattr(getattr(self, "_io_stats", None), "session_t0_wall", None)
        if wall is None:
            self.toast(self._t("stat_jump_empty"), error=True)
            return
        self.jump_to_session_time(wall)

    def jump_to_session_time(self, wall_t):
        dlg = getattr(self, "_structured_dlg", None)
        if dlg is None:
            self._open_structured_record()
            dlg = getattr(self, "_structured_dlg", None)
        if dlg is None:
            return
        # 隐藏期间 on_samples 不会刷表，先刷新再定位，否则是在过期行列表上找最近一行。
        dlg.refresh_rows()
        # Table shows only the last 5000 visible rows.
        shown = getattr(dlg, "_replay_rows", None) or []
        if not shown:
            rows = getattr(dlg, "_visible_rows", None) or []
            shown = rows[-5000:]
        best_i, best_dt = None, None
        for i, row in enumerate(shown):
            dt = abs(float(row.get("timestamp", 0)) - float(wall_t))
            if best_dt is None or dt < best_dt:
                best_dt, best_i = dt, i
        if best_i is None:
            return
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if best_i < dlg.table.rowCount():
            dlg.table.selectRow(best_i)
            item = dlg.table.item(best_i, 0)
            if item is not None:
                dlg.table.scrollToItem(item)

    def _structured_replay_sample(self, sample):
        if not isinstance(sample, dict):
            return
        self.status_bar.showMessage(
            "%s = %s %s" % (sample.get("tag", ""), sample.get("value", ""),
                             sample.get("unit", "")), 800)
        samples = [sample]
        plot_tags = getattr(self, "_device_plot_tags", None) or []
        dash_tags = getattr(self, "_device_dash_tags", None) or []
        if plot_tags:
            self._feed_named_view("_plot_dlg", plot_tags, samples)
        if dash_tags:
            self._feed_named_view("_dash_dlg", dash_tags, samples)
        if not plot_tags:
            dlg = getattr(self, "_plot_dlg", None)
            if dlg is not None and dlg.isVisible():
                try:
                    dlg.feed_named_samples(samples)
                except Exception:
                    _log.debug("_structured_replay_sample failed", exc_info=True)
        if not dash_tags:
            dlg = getattr(self, "_dash_dlg", None)
            if dlg is not None and dlg.isVisible():
                try:
                    dlg.feed_named_samples(samples)
                except Exception:
                    _log.debug("_structured_replay_sample failed", exc_info=True)

    def _open_device_center(self):
        if self._device_center_dlg is None:
            from device_center_dialog import DeviceCenterDialog
            self._device_center_dlg = DeviceCenterDialog(self)
        elif not self._device_center_dlg.isVisible():
            self._device_center_dlg.reload_cfg()
        self._device_center_dlg.show()
        self._device_center_dlg.raise_()
        self._device_center_dlg.activateWindow()

    def _open_structured_record(self):
        if self._structured_dlg is None:
            from structured_record_dialog import StructuredRecordDialog
            self._structured_dlg = StructuredRecordDialog(self)
        self._structured_dlg.refresh_rows()
        self._structured_dlg.show()
        self._structured_dlg.raise_()
        self._structured_dlg.activateWindow()

    def _open_modbus_master(self):
        if getattr(self, "_mbm_dlg", None) is None:
            from modbus_master_dialog import ModbusMasterDialog
            self._mbm_dlg = ModbusMasterDialog(self)
        dlg = self._mbm_dlg
        if not dlg._dirty:           # 保留尚未“应用”的界面草稿；已提交时才从运行配置刷新
            dlg.reload_rows()
        dlg.setEnabled(self._device_scan_state is None)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _send_text(self, raw, hex_mode=None, newline=None, checksum=None, target=None,
                   record_macro=True, allow_during_exclusive=False,
                   allow_running_dsl=False) -> bool:
        """解析并发送一段文本(HEX/文本)，复用追加换行+校验+显示。
        hex_mode/newline/checksum 为 None 时用主界面全局设置；多条发送可逐条传入独立值。
          newline: None=全局; 0=无 1=CRLF 2=LF 3=CR
          checksum: None=全局; 否则校验项索引(0=无…)
        成功返回 True"""
        if (not allow_during_exclusive
                and self._manual_send_blocked(allow_running_dsl=allow_running_dsl)):
            self.toast(self._t("io_exclusive_busy"), error=True)
            return False
        if not self._is_open():
            self.toast(self._t("net_not_open"), error=True)
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

        send_target = self._send_target() if target is None else target
        try:
            sent = self.conn.send(data, send_target)
        except Exception as e:
            self._stat_note_tx_error()
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t(
                "err_send_failed",
                e=conn_error_tips.format_conn_error_detail(str(e), self._t)),
                error=True)
            return False
        if sent == SEND_NO_TARGET:   # UDP 无对端 / TCP Server 无客户端
            self._stat_note_tx_error()
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("net_no_target"), error=True)
            return False
        strict_full_write = getattr(self, "_conn_proto", None) in (PROTO_SERIAL, PROTO_TCP_CLIENT)
        if sent <= 0 or (strict_full_write and sent != len(data)):
            # 串口/TCP Client 都是一条字节流，部分写入不能算整包成功；TCP 半帧会污染后续
            # MBAP/应用帧边界，必须断开重建。统计只记底层明确接收的实际字节数。
            if 0 < sent < len(data):
                self.tx_bytes += sent
                acc = getattr(self, "_io_stats", None)
                if acc is not None:
                    acc.note_tx_bytes(sent)
            self._abort_partial_tcp_stream(sent, len(data))
            self._stat_note_tx_error()
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("net_send_failed"), error=True)
            return False

        self._stat_note_tx(len(data))
        # 同收包路径：成功发送只累加计数器，标签刷新交 1Hz 定时器（多帧连发时不每帧重排状态栏）。

        if record_macro:
            self._macro_record_tx(data)
        self._record_stream_tx(data, source=send_target)  # 录线路现场，与 record_macro 无关

        # 显示到数据区 — 只看「HEX 显示」开关(数据区显示格式)，和发送模式无关：
        # 接收按 HEX 显示，发送也按 HEX 显示，RX/TX 统一
        if self._hexdump_on:
            display = self._hexdump_block(data)
        elif self._numview_on:
            display = self._numview_block(data, carry=False)
        elif self.sw_rx_hex.isChecked():
            display = self._bytes_to_hex(data) + " "
        else:
            display = data.decode(self._send_codec(), errors="replace")
        self._append_block_data(display, direction="tx", force_new_block=True)
        self._last_direction = "tx"
        return True

    # ----- 终端模式（轻量串口终端：逐字符即时发送 + 基础 VT 行编辑 / ANSI SGR）-----
    @staticmethod
    def _safe_enter_idx(v):
        """Enter-key mapping index: only 0/1/2, else 0."""
        return log_naming.safe_enter_idx(v)

    def _set_terminal_enabled(self, on):
        on = bool(on)
        self._terminal_on = on
        self._term_esc = ""           # 切换时清掉未完成的转义序列残留
        self._term_discard_csi = False
        self._term_discard_osc = False
        self._term_osc_prev_esc = False
        self._term_streams = {}
        self._term_pos = None         # 光标位置重置（下次从文末开始）
        self._term_sgr = None         # 颜色也归零：上一次会话结尾若停在红色，重进终端
                                      # 不该让新会话的第一行凭空是红的
        self.settings.setValue("terminal_mode", on)
        self.settings.sync()
        # 同步开关控件（程序化调用时）；阻断信号避免 setChecked → toggled → 本函数 递归
        if hasattr(self, "sw_terminal") and self.sw_terminal.isChecked() != on:
            self.sw_terminal.blockSignals(True)
            self.sw_terminal.setChecked(on)
            self.sw_terminal.blockSignals(False)
        if hasattr(self, "txt_send"):
            if on:
                self.txt_send.clear()   # 终端模式发送框作键盘捕获、不累积文本
            ph = "term_send_ph" if on else "send_placeholder"
            self.txt_send.setProperty("tr_placeholder", ph)   # 语言切换时也用对的占位文案
            self.txt_send.setPlaceholderText(self._t(ph))
        if on:
            # 进入终端模式：停掉会在后台按周期发送的功能（定时发送 + 多条发送循环），否则它们
            # 仍在后台周期发（终端模式发送框为空 → 发空内容，且与逐字符直发互相干扰）。
            if hasattr(self, "sw_period") and self.sw_period.isChecked():
                self.sw_period.setChecked(False)   # 触发 on_period_toggled → send_timer.stop()
            self._ms_stop_cycle()
        self._apply_terminal_ui(on)
        self.toast(self._t("term_on") if on else self._t("term_off"))

    def _apply_terminal_ui(self, on):
        """终端模式开启时，把「对终端不生效」的显示 / 发送格式设置禁用（不可配置），避免误以为还
        起作用。终端是纯字节流逐字符直发：HEX 显示 / 时间戳 / 分包 / 超时 / 换行分包，以及
        HEX 发送 / 追加换行 / 定时 / 校验 全被绕过。仍有用的（字符编码 / 自动换行 / 最大行数 /
        实时记录）不动。关闭终端模式后全部恢复可配置。
        冻结视图同样禁用：终端是连续流（回车覆盖 / 光标移动 / 跨块续写），没有块级「追加」这个
        可拦点，冻结会使显示与 _term_* 光标状态机失步。故终端模式下冻结开关不可配。"""
        if on and hasattr(self, "sec_send_term"):
            # 正处在终端模式里却把这组折起来 → 找不到怎么退出，故开启时强制展开
            self.sec_send_term.setExpanded(True)
        if on and hasattr(self, "sw_freeze_view") and self.sw_freeze_view.isChecked():
            # 终端是连续光标流，没有块级冻结语义；进入终端时清除此前冻结状态，
            # 避免开关显示冻结但终端仍继续刷新造成状态欺骗。
            self.sw_freeze_view.setChecked(False)
        for name in ("cb_view_mode", "cb_hexdump_width", "cb_numview_type",
                     "sw_show_timestamp", "sw_packet_split", "ed_packet_timeout",
                     "sw_line_split", "cb_line_nl",
                     "sw_tx_hex", "sw_append_newline", "cb_append_nl",
                     "sw_period", "ed_period_ms", "cb_checksum",
                     "sw_freeze_view"):
            w = getattr(self, name, None)
            if w is not None:
                w.setEnabled(not on)
        self._refresh_hex_toggle_state()   # 退出终端后按 hexdump 状态复算 HEX 显示可用性（否则被上面一律置回可用）
        self._update_sel_checksum()        # 进出终端换了显示口径，旧的选区校验和结果作废
        # 连同标签文字一起淡化，让禁用的整行统一「暗下去」（只灰控件、标签还满色 → 不明显）
        for k in ("view_mode", "show_timestamp", "packet_split", "timeout", "line_split",
                  "hex_send", "append_newline", "period", "checksum", "freeze_view"):
            for lab in self._setting_labels.get(k, ()):
                if on:
                    eff = QGraphicsOpacityEffect(lab)
                    eff.setOpacity(0.4)
                    lab.setGraphicsEffect(eff)
                else:
                    lab.setGraphicsEffect(None)

    def _on_term_echo_changed(self, on):
        self._terminal_echo = bool(on)
        self.settings.setValue("terminal_echo", self._terminal_echo)
        self.settings.sync()

    def _on_term_enter_changed(self, idx):
        self._terminal_enter = int(idx)
        self.settings.setValue("terminal_enter", self._terminal_enter)
        self.settings.sync()

    def _term_key_to_bytes(self, key, mod, text):
        """终端模式：把一次按键(key 码 / 修饰键 / 文本)映射为 (要发字节, 本地回显文本|None)。
        纯函数、不碰 UI，便于单元测试。"""
        enter = {0: b"\r", 1: b"\n", 2: b"\r\n"}.get(self._terminal_enter, b"\r")
        if key in (Qt.Key_Return, Qt.Key_Enter):
            return enter, "\n"
        if key == Qt.Key_Backspace:
            return b"\x7f", None          # DEL：现代 Linux / 多数终端的退格惯例
        if key == Qt.Key_Tab:
            return b"\t", "\t"
        if key == Qt.Key_Escape:
            return b"\x1b", None
        seq = {Qt.Key_Up: b"\x1b[A", Qt.Key_Down: b"\x1b[B",
               Qt.Key_Right: b"\x1b[C", Qt.Key_Left: b"\x1b[D",
               Qt.Key_Home: b"\x1b[H", Qt.Key_End: b"\x1b[F",
               Qt.Key_Delete: b"\x1b[3~"}
        if key in seq:
            return seq[key], None
        if (mod & Qt.ControlModifier) and Qt.Key_A <= key <= Qt.Key_Z:
            return bytes([key - Qt.Key_A + 1]), None   # Ctrl+A=0x01 … Ctrl+C=0x03 … Ctrl+Z=0x1a
        if text:
            try:
                data = text.encode(self._send_codec(), errors="replace")
            except Exception:
                data = text.encode("utf-8", errors="replace")
            return data, text
        return None, None

    def _terminal_key(self, event):
        data, echo = self._term_key_to_bytes(event.key(), event.modifiers(), event.text())
        if data:
            self._terminal_send(data, echo)

    def _terminal_send(self, data, echo=None):
        """终端模式即时发送一小段字节（按键）。统计计数；本地回显开则把回显文本写进数据区。"""
        if self._manual_send_blocked():
            self.toast(self._t("io_exclusive_busy"), error=True)
            return
        if not self._is_open():
            return
        send_target = self._send_target()
        try:
            sent = self.conn.send(data, send_target)
        except Exception as e:
            self._stat_note_tx_error()
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t(
                "err_send_failed",
                e=conn_error_tips.format_conn_error_detail(str(e), self._t)),
                error=True)
            return
        if sent == SEND_NO_TARGET:
            self._stat_note_tx_error()
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("net_no_target"), error=True)
            return
        if sent <= 0:
            self._stat_note_tx_error()
            self._refresh_stat_labels(with_tooltip=False)
            return
        self._stat_note_tx(len(data))
        self._macro_record_tx(data)
        # 终端是绕过 _send_text 的直发路径，采集入口得在这里补一次：数据录制录的是「线路
        # 现场」，终端里敲进去的字节当然算；范围含「发送」的触发规则同样要盯得到，
        # 否则在终端里敲的命令永远不命中。两件事都由 _record_stream_tx 一个入口带上。
        try:
            self._record_stream_tx(data, source=send_target)
        except Exception:
            _log.debug("_terminal_send failed", exc_info=True)
        if self._terminal_echo and echo:
            self._terminal_append(echo)

    def _terminal_append(self, text, source=None):
        r"""把收到的字节流按终端语义渲染到数据区（轻量 VT）：处理 \b(光标左移)、\r(回行首)、
        \n(换行)、覆盖式打印，以及行编辑常用的 CSI 序列 ESC[J/ESC[K(擦除)、ESC[C/ESC[D(光标
        左右)；颜色 ESC[..m、定位 ESC[..H 等其它 CSI 忽略（不显示成乱码）。不解析全屏 TUI。"""
        if not text:
            return
        was_bottom = self._recv_at_bottom()
        doc = self.txt_recv.document()
        cur = QTextCursor(doc)
        # 跨块延续光标位置（终端是连续流）；位置失效（如行数超限被裁剪）则退回文末
        pos, last = self._term_pos, doc.characterCount() - 1
        if pos is not None and 0 <= pos <= last:
            cur.setPosition(pos)
        else:
            cur.movePosition(QTextCursor.End)
        stream_source = source if self._conn_proto == PROTO_TCP_SERVER else None
        if stream_source is None:
            term_sgr = self._term_sgr
            esc = self._term_esc          # 跨块残留的未完成转义序列
            self._term_esc = ""
            discard_csi = self._term_discard_csi
            self._term_discard_csi = False
            discard_osc = self._term_discard_osc
            self._term_discard_osc = False
            osc_prev_esc = self._term_osc_prev_esc
            self._term_osc_prev_esc = False
        else:
            # 多客户端共用一个显示文档，但协议解析状态不能共用：否则 A 的半条 ESC[
            # 会吃掉 B 的正文，A 的红色 SGR 也会把 B 的日志染红。
            stream = self._term_streams.get(stream_source, {})
            term_sgr = stream.get("sgr")
            esc = stream.get("esc", "")
            discard_csi = stream.get("discard_csi", False)
            discard_osc = stream.get("discard_osc", False)
            osc_prev_esc = stream.get("osc_prev_esc", False)
        buf = []
        # 基础格式必须从零构造，不能沿用光标处的格式：光标停在上一段带色文字后面时，
        # 继承来的格式会连 ANSI 的颜色和属性一起带上 —— 关掉 ANSI 着色后新文字仍是红的。
        base_fmt = QTextCharFormat()
        base_fmt.setForeground(QColor(self._theme()["fg"]))
        base_fmt.setProperty(VIEW_PROP, VIEW_TERMINAL)

        def _make_fmt():
            """当前 SGR 样式对应的字符格式；关掉 ANSI 着色时恒为无色的基础格式。"""
            st = term_sgr
            if not self._ansi_on or st is None or st.is_default():
                return base_fmt
            f = QTextCharFormat(base_fmt)
            self._apply_sgr_format(f, st)
            return f

        term_fmt = _make_fmt()

        def _flush():
            if buf:
                cur.insertText("".join(buf), term_fmt)
                del buf[:]

        for ch in text:
            if discard_osc:
                # 超长 OSC（设置标题/超链接等）继续吞到 BEL 或 ST(ESC \)。只丢当前控制序列，
                # 终止后的普通正文仍照常显示。
                if ch == "\x07" or (osc_prev_esc and ch == "\\"):
                    discard_osc = False
                    osc_prev_esc = False
                else:
                    osc_prev_esc = (ch == "\x1b")
                continue
            if discard_csi:
                # 超长 CSI 的剩余部分全部吃掉；遇终止字节后恢复普通解析。
                if "\x40" <= ch <= "\x7e":
                    discard_csi = False
                continue
            if esc:                   # 正在收集转义序列
                esc += ch
                if esc.startswith("\x1b]"):       # OSC：BEL 或 ST(ESC \) 结束
                    if ch == "\x07" or esc.endswith("\x1b\\"):
                        esc = ""
                    elif len(esc) > ansi.MAX_PENDING:
                        osc_prev_esc = (ch == "\x1b")
                        esc = ""
                        discard_osc = True
                elif esc.startswith("\x1b[") and len(esc) > 64:
                    # 异常设备可能一直发 ESC[ + 参数却不给终止字母；限制跨块缓冲长度，
                    # 避免内存持续增长，也避免最终对超长数字执行 int()。
                    esc = ""
                    discard_csi = True
                elif esc.startswith("\x1b[") and len(esc) >= 3 and "\x40" <= ch <= "\x7e":
                    _flush()
                    term_sgr = self._term_handle_csi(cur, esc, term_sgr)
                    term_fmt = _make_fmt()            # SGR 可能改了颜色 → 后续字符用新格式
                    esc = ""
                elif len(esc) == 2:
                    # CSI / OSC 继续收；其它 ESC 序列若第二字节是 intermediate(0x20-0x2F)
                    # 还需再等终止字节，如 ESC(B。ESC7/ESC= 这类两字节序列则已完整吃掉。
                    if ch not in ("[", "]") and not ("\x20" <= ch <= "\x2f"):
                        esc = ""
                elif not esc.startswith(("\x1b[", "\x1b]")):
                    # ESC + intermediate* + final(0x30-0x7E)：整条吃掉，不把 ESC(B 的 B
                    # 或字符集/键盘模式控制码漏进终端正文。
                    if "\x30" <= ch <= "\x7e" or len(esc) > 16:
                        esc = ""
                continue
            if ch == "\x1b":
                _flush()
                esc = "\x1b"
            elif ch == "\b":
                _flush()
                if not cur.atBlockStart():
                    cur.movePosition(QTextCursor.Left)
            elif ch == "\r":
                _flush()
                cur.movePosition(QTextCursor.StartOfLine)
            elif ch == "\n":
                _flush()
                cur.movePosition(QTextCursor.End)
                cur.insertText("\n", term_fmt)
            elif ch == "\t" or (ch >= " " and ch != "�"):
                # 覆盖式打印：行尾→追加（可批量）；行内→替换光标右侧字符。U+FFFD(无效字节)丢弃。
                if cur.atBlockEnd():
                    buf.append(ch)
                else:
                    _flush()
                    cur.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
                    cur.removeSelectedText()
                    cur.insertText(ch, term_fmt)
            # 其它控制符（BEL/NUL 等）丢弃
        _flush()
        if stream_source is None:
            self._term_sgr = term_sgr
            self._term_esc = esc          # 未完成的转义序列留到下次拼接
            self._term_discard_csi = discard_csi
            self._term_discard_osc = discard_osc
            self._term_osc_prev_esc = osc_prev_esc
        else:
            self._term_streams[stream_source] = {
                "sgr": term_sgr,
                "esc": esc,
                "discard_csi": discard_csi,
                "discard_osc": discard_osc,
                "osc_prev_esc": osc_prev_esc,
            }
        self._term_pos = cur.position()
        # Terminal bypasses _append_block_data; apply the same char budget and
        # keep _term_pos valid after a head trim (P1: no-newline growth).
        trimmed = self._trim_recv_overflow()
        if trimmed and self._term_pos is not None:
            self._term_pos = max(0, self._term_pos - trimmed)
            last = self.txt_recv.document().characterCount() - 1
            if self._term_pos > last:
                self._term_pos = max(0, last)
        # Keep line-end flag in sync for non-terminal RX after leaving terminal.
        self._txt_ends_with_nl = self.txt_recv.document().lastBlock().text() == ""
        if was_bottom:
            self._scroll_recv_to_bottom()

    def _term_handle_csi(self, cur, seq, sgr=None):
        """处理一条 CSI 序列 seq = ESC[ <参数> <终止字母>。只管行编辑相关：擦除 J/K + 光标左右
        C/D，以及颜色 m；定位 H/f、上下移 A/B 等其余序列忽略，避免显示成乱码。"""
        final = seq[-1]
        params = seq[2:-1]            # ESC[ 与终止字母之间的参数串，如 ""、"0"、"2"、"5"
        if final == "m":              # SGR：颜色 / 粗体 / 下划线 —— 记进状态，供后续字符取格式
            sgr = ansi.apply_params(sgr or ansi.DEFAULT, params)
        elif final == "J":            # 擦除显示：0/缺省=光标到文末；2=全清
            if params in ("", "0"):
                c2 = QTextCursor(cur)
                c2.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
                c2.removeSelectedText()
            elif params == "2":
                self.txt_recv.clear()
                self._bookmarks = []
                self._bookmark_idx = -1
                self._recv_highlight_line = -1
                cur.movePosition(QTextCursor.End)
        elif final == "K":            # 擦除行：0/缺省=光标到行尾
            if params in ("", "0"):
                c2 = QTextCursor(cur)
                c2.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
                c2.removeSelectedText()
        elif final == "D":            # 光标左移 N（缺省 1）
            n = min(int(params), 100000) if params.isdigit() else 1   # 钳上限防超大 N 空转
            for _ in range(n):
                if cur.atBlockStart():
                    break             # 到行首即停（设备发 ESC[999999999D 也不会冻结界面）
                cur.movePosition(QTextCursor.Left)
        elif final == "C":            # 光标右移 N（缺省 1）
            n = min(int(params), 100000) if params.isdigit() else 1
            for _ in range(n):
                if cur.atBlockEnd():
                    break             # 到行尾即停
                cur.movePosition(QTextCursor.Right)
        return sgr

    @staticmethod
    def compute_checksum(data: bytes, index: int) -> bytes:
        return _ar_core_compute_checksum(data, index)

    def on_period_toggled(self, on):
        if on:
            if self._io_task_busy(exclude=("periodic",)):
                self.toast(self._t("io_exclusive_busy"), error=True)
                self.sw_period.setChecked(False)
                return
            try:
                ms = int(self.ed_period_ms.text())
                if ms < 10:
                    raise ValueError(self._t("err_min_period"))
            except ValueError as e:
                self.toast(self._t("err_period_bad", e=e), error=True)
                self.sw_period.setChecked(False)
                return
            if not self._is_open():
                self.toast(self._t("net_not_open"), error=True)
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
        """Parse split-size combo text -> bytes (0 = unlimited)."""
        return log_naming.parse_size_limit(text)

    def _on_log_split_changed(self, _text=None):
        """改分包大小：实时记录进行中也即时生效。"""
        self._log_limit = self._parse_log_limit(self.cb_log_split.currentText())

    def _log_conn_token(self) -> str:
        """%port expansion: device / IP_port / proto / empty."""
        return log_naming.conn_token(
            getattr(self, "_conn_proto", None),
            getattr(self, "_conn_cfg", None),
            serial_name=PROTO_SERIAL,
            tcp_client_name=PROTO_TCP_CLIENT)

    def _log_segment_path(self, when=None) -> str:
        """当前分包对应的文件名：展开 %date/%time/%port/%n 变量，再按需追加序号。

        when 由调用方传入（跨日轮转要用「新一天的时刻」而不是开始记录时的），
        规则本身在 Qt-free 的 log_naming 里，便于单测。
        """
        return log_naming.segment_path(
            self._log_base_path, when or datetime.now(),
            port=self._log_conn_token(), seg=self._log_seg)

    def _set_log_path_label(self, path):
        """更新状态栏的日志文件路径显示（仅记录时显示，太长中间省略，悬停看全路径）。"""
        if not hasattr(self, "lbl_log_path"):
            return
        if not path:
            self.lbl_log_path.setText("")
            set_tooltip(self.lbl_log_path, "")
            if hasattr(self, "_log_path_sep"):
                self._log_path_sep.hide()
            return
        fm = QFontMetrics(self.lbl_log_path.font())
        w = getattr(self, "_log_path_elide_w", 560)
        self.lbl_log_path.setText("📝 " + fm.elidedText(path, Qt.ElideMiddle, w))
        set_tooltip(self.lbl_log_path, path)
        if hasattr(self, "_log_path_sep"):
            self._log_path_sep.show()

    def _open_log_segment(self, path, when=None) -> bool:
        try:
            # 目录可能来自 %date 之类的变量展开，先建出来再开文件
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._log_file = open(path, "a", encoding="utf-8")
            self._log_file_path = path
            self._log_opened_at = when or datetime.now()
            ts = self._log_opened_at.strftime("%Y-%m-%d %H:%M:%S")
            self._log_file.write(self._t("log_header", time=ts))
            self._log_file.flush()
            self._log_ends_with_nl = True
            self._set_log_path_label(path)
            return True
        except Exception as e:
            self.toast(self._t("err_open_log", e=e), error=True)
            return False

    def _close_log_segment(self, when):
        """Write footer -> flush -> close. Each step is independent so a footer
        failure cannot skip close (same contract as net_io._safe)."""
        if not self._log_file:
            return
        try:
            self._log_file.write(self._t("log_footer",
                                         time=when.strftime("%Y-%m-%d %H:%M:%S")))
            self._log_file.flush()
        except Exception:
            _log.debug("log footer/flush failed", exc_info=True)
        try:
            self._log_file.close()
        except Exception:
            _log.debug("log close failed", exc_info=True)
        self._log_file = None
        self._log_ends_with_nl = True

    def _maybe_rotate_log(self, now=None):
        """写入后判断要不要换文件：跨自然日 或 超过分包上限。

        跨日优先且序号归零 —— 文件名里已经带了新日期，再从 _003 接着数会让人以为
        这天的记录是从第 4 段开始的。跨日轮转只在文件名含日期变量时才有意义
        （否则换日期也是同一个文件名，白白切断），判定在 log_naming 里。
        """
        if not self._log_file:
            return
        now = now or datetime.now()
        if log_naming.should_roll_date(self._log_opened_at, now, self._log_base_path):
            self._close_log_segment(now)
            self._log_seg = 0
            if not self._open_log_segment(self._log_segment_path(now), when=now):
                self.sw_log_file.setChecked(False)
            return
        try:
            cur = self._log_file.tell()
        except Exception:
            _log.debug("log tell() failed", exc_info=True)
            return
        if not log_naming.should_roll_size(cur, self._log_limit):
            return
        self._close_log_segment(now)
        self._log_seg += 1
        if not self._open_log_segment(self._log_segment_path(now), when=now):
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
            # 存模板原文（可能含 %date/%port）：每次开分包时重新展开，跨日才能拿到新日期
            self._log_base_path = path
            self._log_seg = 0
            now = datetime.now()
            real = self._log_segment_path(now)
            if self._open_log_segment(real, when=now):
                self.toast(self._t("log_started", path=real))
            else:
                self.sw_log_file.setChecked(False)
        else:
            self._close_log_file()

    def _close_log_file(self):
        if self._log_file:
            self._close_log_segment(datetime.now())
            self.toast(self._t("log_stopped", path=self._log_file_path))
            self._log_file_path = ""
            self._log_opened_at = None
            self._set_log_path_label("")

    def change_recv_font_size(self, delta):
        new_size = self._recv_font_size + delta
        new_size = _cfg_clamp_font(new_size)
        if new_size == self._recv_font_size:
            return
        self._recv_font_size = new_size
        self.txt_recv.setFont(mono_font(new_size))
        self.toast(self._t("font_size_msg", size=new_size))

    def _on_max_lines_changed(self):
        if not hasattr(self, 'ed_max_lines'):
            return
        try:
            raw_n = int(self.ed_max_lines.text())
        except ValueError:
            raw_n = self.txt_recv.document().maximumBlockCount() or 10000
        n = _cfg_clamp_lines(raw_n)
        self.ed_max_lines.setText(str(n))
        if hasattr(self, 'txt_recv'):
            self.txt_recv.document().setMaximumBlockCount(n)

    def _on_ts_format_changed(self):
        self._ts_format = _cfg_norm_ts(self.cb_ts_format.currentData())
        # 切到相对时间时重置会话锚点，让新格式从此刻起算
        if self._ts_format == "relative":
            self._ts_anchor = None
        self.settings.setValue("ts_format", self._ts_format)
        self.settings.sync()
        self._refresh_project_dirty_label()

    def _on_freeze_view_toggled(self, checked):
        # 冻结视图：新数据仍计入统计/录制/触发，只是不追加到数据区（排查时锁定画面）。
        self._freeze_view = bool(checked)
        self.settings.setValue("freeze_view", self._freeze_view)
        self.settings.sync()
        self._refresh_project_dirty_label()

    def _timestamp_prefix(self, direction):
        """Build block prefix from ts_format + direction arrow; off -> ''."""
        if not self.sw_show_timestamp.isChecked():
            return ""
        fmt = getattr(self, "_ts_format", "absolute")
        text, self._ts_anchor = _view_timestamp_prefix(
            fmt, direction,
            now=datetime.now(), wall_time=time.time(),
            anchor=getattr(self, "_ts_anchor", None))
        return text

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
                self.txt_send.setPlainText(self._bytes_to_hex(data))
            else:
                # 按选定编码读取（默认 utf-8），lossy 容错避免文件偶有坏字节就报错
                self.txt_send.setPlainText(data.decode(self._send_codec(), errors="replace"))
        except Exception as e:
            self.toast(self._t("err_read_failed", e=e), error=True)

    def clear_recv(self):
        self.txt_recv.clear()
        self._recv_highlight_line = -1
        self._bookmarks = []
        self._bookmark_idx = -1
        self.txt_recv.setExtraSelections([])
        self.btn_to_bottom.hide()
        self._reset_stats()
        self._reset_recv_state(reset_dashboard=True)

    # ----- 工具 -----
    @staticmethod
    def fmt_bytes(n):
        return _io_fmt_bytes(n)

    def _stat_note_rx(self, n):
        n = int(n or 0)
        self.rx_bytes += n
        self.rx_packets += 1
        self._io_stats.note_rx(n)

    def _stat_note_tx(self, n):
        n = int(n or 0)
        self.tx_bytes += n
        self.tx_packets += 1
        self._io_stats.note_tx(n)

    def _stat_note_rx_error(self, count=1):
        self.rx_errors += max(0, int(count))
        self._io_stats.note_rx_error(count)

    def _stat_note_tx_error(self, count=1):
        self.tx_errors += max(0, int(count))
        self._io_stats.note_tx_error(count)

    def _stat_note_timeout(self, kind):
        acc = getattr(self, "_io_stats", None)
        if acc is not None:
            acc.note_timeout(kind)

    def _fmt_rate(self, bps):
        return _io_fmt_rate(bps)

    def _tick_rate(self):
        """1Hz sample: B/s + pps + peaks + history via IoStatsAccumulator."""
        now = time.monotonic()
        rates = self._io_stats.tick(now=now)
        self._rx_rate = rates["rx_rate"]
        self._tx_rate = rates["tx_rate"]
        self._rx_peak = self._io_stats.rx_peak
        self._tx_peak = self._io_stats.tx_peak
        self._rx_bytes_mark = self._io_stats._rx_bytes_mark
        self._tx_bytes_mark = self._io_stats._tx_bytes_mark
        self._rate_time_mark = self._io_stats._time_mark
        self._refresh_stat_labels()
        rr_dlg = getattr(self, "_rr_dlg", None)
        if rr_dlg is not None and rr_dlg.isVisible():
            rr_dlg.tick_stat()
        try:
            plot = getattr(self, "_plot_dlg", None)
            if plot is not None and plot.isVisible() and hasattr(plot, "feed_named_samples"):
                plot.feed_named_samples([
                    {"tag": "rx_Bps", "value": float(self._rx_rate)},
                    {"tag": "tx_Bps", "value": float(self._tx_rate)},
                    {"tag": "rx_pps", "value": float(self._io_stats.rx_pps)},
                    {"tag": "tx_pps", "value": float(self._io_stats.tx_pps)},
                ])
        except Exception:
            _log.debug("_tick_rate failed", exc_info=True)

    def _refresh_stat_labels(self, with_tooltip=True):
        """Refresh status-bar RX/TX: bytes, packets, B/s, pps."""
        if not hasattr(self, "lbl_rx_stat"):
            return
        unit = self._t("stat_pkt_unit")
        pps_u = self._t("stat_pps_unit")
        rx = _io_format_stat_bar(
            "RX", self.rx_bytes, self.rx_packets, self._rx_rate,
            self._io_stats.rx_pps, self.rx_errors, unit, pps_u)
        tx = _io_format_stat_bar(
            "TX", self.tx_bytes, self.tx_packets, self._tx_rate,
            self._io_stats.tx_pps, self.tx_errors, unit, pps_u)
        self.lbl_rx_stat.setText(rx)
        self.lbl_tx_stat.setText(tx)
        if with_tooltip:
            tip_rx = self._stat_tooltip("rx") + "\n" + self._t("stat_jump_tip")
            tip_tx = self._stat_tooltip("tx") + "\n" + self._t("stat_jump_tip")
            set_tooltip(self.lbl_rx_stat, tip_rx)
            set_tooltip(self.lbl_tx_stat, tip_tx)

    def _stat_tooltip(self, direction):
        acc = self._io_stats
        if direction == "rx":
            head = self._t("stat_tip_rx")
            b, p, r, pk, e = (self.rx_bytes, self.rx_packets, self._rx_rate,
                              self._rx_peak, self.rx_errors)
            pps, peak_pps = acc.rx_pps, acc.rx_peak_pps
        else:
            head = self._t("stat_tip_tx")
            b, p, r, pk, e = (self.tx_bytes, self.tx_packets, self._tx_rate,
                              self._tx_peak, self.tx_errors)
            pps, peak_pps = acc.tx_pps, acc.tx_peak_pps
        total = self.fmt_bytes(b) + ((" (%s B)" % format(b, ",")) if b >= 1024 else "")
        smin, smax, savg = acc.size_summary(direction)
        lines = [
            head,
            self._t("stat_tip_packet_note"),
            "%s: %s" % (self._t("stat_total"), total),
            "%s: %s" % (self._t("stat_packets"), format(p, ",")),
            "%s: %s" % (self._t("stat_rate"), self._fmt_rate(r)),
            "%s: %s %s" % (self._t("stat_pps"), pps, self._t("stat_pps_unit")),
            "%s: %s" % (self._t("stat_peak"), self._fmt_rate(pk)),
            "%s: %s %s" % (self._t("stat_peak_pps"), peak_pps, self._t("stat_pps_unit")),
            "%s: %s" % (self._t("stat_errors"), format(e, ",")),
        ]
        if smin is not None:
            lines.append("%s: min=%s avg=%.1f max=%s" % (
                self._t("stat_size"), smin, savg, smax))
            lines.append("%s: %s" % (self._t("stat_size_hist"), acc.hist_label(direction)))
        to = acc.timeouts
        lines.append("%s: seq=%s mbm=%s conn=%s" % (
            self._t("stat_timeouts"), to.get("seq", 0), to.get("mbm", 0), to.get("conn", 0)))
        if acc.history:
            n = min(60, len(acc.history))
            recent = acc.history[-n:]
            key = "rx_bps" if direction == "rx" else "tx_bps"
            avg_bps = int(sum(x[key] for x in recent) / n)
            lines.append("%s: %s" % (self._t("stat_avg_rate_1m"), self._fmt_rate(avg_bps)))
        return "\n".join(lines)

    def _reset_stats(self):
        """Clear I/O counters only; does not touch recordings or the receive view."""
        self._io_stats.reset()
        self.rx_bytes = self.tx_bytes = 0
        self.rx_packets = self.tx_packets = 0
        self.rx_errors = self.tx_errors = 0
        self._rx_rate = self._tx_rate = 0
        self._rx_peak = self._tx_peak = 0
        self._rx_bytes_mark = self._tx_bytes_mark = 0
        self._rate_time_mark = time.monotonic()
        self._refresh_stat_labels()

    def _stat_context_menu(self, pos):
        """状态栏右键：重置统计（文字跟随语言、配色跟随主题）。"""
        menu = QMenu(self.status_bar)
        c = chrome_for(self._theme_id())
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['card_bg']}; color: {c['text']};
                     border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
            QMenu::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
        """)
        act_reset = menu.addAction(self._t("stat_reset"))
        chosen = menu.exec_(self.status_bar.mapToGlobal(pos))
        menu.deleteLater()   # 每次右键新建、挂在 status_bar 下；exec_ 后主动回收，避免累积为常驻子对象
        if chosen is act_reset:
            self._reset_stats()

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
        self.setWindowTitle(self._t("app_title") + self._title_suffix)
        if hasattr(self, "title_bar"):
            self.title_bar.set_title(self._t("app_title") + self._title_suffix)

        for w in self.findChildren(QWidget):
            k = w.property("tr_text")
            if k:
                try:
                    w.setText(self._t(k))
                except Exception:
                    _log.debug("_apply_language failed", exc_info=True)
            k = w.property("tr_placeholder")
            if k:
                try:
                    w.setPlaceholderText(self._t(k))
                except Exception:
                    _log.debug("_apply_language failed", exc_info=True)
            k = w.property("tr_tooltip")
            if k:
                try:
                    set_tooltip(w, self._t(k))
                except Exception:
                    _log.debug("_apply_language failed", exc_info=True)
            # 固定宽标签（网络设置左列）随语言调整列宽，避免英文被遮挡
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

        if hasattr(self, "cb_ts_format"):
            data = self.cb_ts_format.currentData()
            self.cb_ts_format.blockSignals(True)
            self.cb_ts_format.clear()
            for d, key in _ui_ts_format_items:
                self.cb_ts_format.addItem(self._t(key), d)
            idx = self.cb_ts_format.findData(data)
            self.cb_ts_format.setCurrentIndex(idx if idx >= 0 else 0)
            self.cb_ts_format.blockSignals(False)
        if hasattr(self, "cb_search_mode"):
            data = self.cb_search_mode.currentData()
            self.cb_search_mode.blockSignals(True)
            self.cb_search_mode.clear()
            for d, key in _ui_search_mode_items:
                self.cb_search_mode.addItem(self._t(key), d)
            idx = self.cb_search_mode.findData(data)
            self.cb_search_mode.setCurrentIndex(idx if idx >= 0 else 0)
            self.cb_search_mode.blockSignals(False)

        if hasattr(self, "cb_line_nl"):
            self.cb_line_nl.setItemText(0, self._t("nl_auto"))
        if hasattr(self, "cb_view_mode"):
            for i, (k, _) in enumerate(_ui_view_mode_items):
                self.cb_view_mode.setItemText(i, self._t(k))
        if hasattr(self, "sec_recv_more"):
            self.sec_recv_more.setTitle(self._t("more_settings"))
        if hasattr(self, "sec_send_term"):
            self.sec_send_term.setTitle(self._t("term_mode"))
        if hasattr(self, "lbl_ansi"):     # 「着色」在下拉那格里，不走 _setting_labels 的统一刷新
            self.lbl_ansi.setText(self._t("ansi_color"))

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

        # 网络设置区：动作按钮文案随协议/状态、字段行随协议显隐重算
        if hasattr(self, "cb_proto"):
            self._update_net_fields()

        # 状态栏连接文本随语言刷新
        if hasattr(self, "lbl_state"):
            if self.conn is not None:
                self._update_conn_status()
            else:
                self.lbl_state.setText(self._t("state_closed"))

        # 状态栏 RX/TX 统计的包单位 + tooltip 随语言刷新
        self._refresh_stat_labels()

        # 「目标」下拉里的「全部」项随语言刷新
        if hasattr(self, "cb_target") and self.cb_target.count() > 0:
            self.cb_target.setItemText(0, self._t("client_all"))

        if self._tray:
            self._tray.setToolTip(self._t("app_title") + self._title_suffix)
            if hasattr(self, "_tray_show_action"):
                self._tray_show_action.setText(self._t("tray_show"))
            if hasattr(self, "_tray_about_action"):
                self._tray_about_action.setText(self._t("about"))
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
        # 发送卡片两行三列等列宽：必须在 btn_ms_cycle 文字更新之后，否则取的是旧语言的 sizeHint
        self._align_send_card_cols()
        self._fit_data_toolbar()   # 数据区工具栏按钮宽度随语言重算，防新语言文字被裁
        self._refresh_project_dirty_label()
        if not (self._project_name or self._project_path):
            self._update_project_label()
        self._refresh_workspace_statuses()
        self._retranslate_workspace_template_panel()
        # 多条发送/关键字高亮弹窗若开着也跟着切语言
        if getattr(self, "_multi_send_dlg", None) is not None:
            self._multi_send_dlg.retranslate()
        if getattr(self, "_keyword_dlg", None) is not None:
            self._keyword_dlg.retranslate()
        if getattr(self, "_plot_dlg", None) is not None:
            self._plot_dlg.retranslate()
        if getattr(self, "_dash_dlg", None) is not None:
            self._dash_dlg.retranslate()
        if getattr(self, "_script_dlg", None) is not None:
            self._script_dlg.retranslate()
        if getattr(self, "_rr_dlg", None) is not None:
            self._rr_dlg.retranslate()
        if getattr(self, "_rd_dlg", None) is not None:
            self._rd_dlg.retranslate()
        if getattr(self, "_snip_dlg", None) is not None:
            self._snip_dlg.retranslate()
        if getattr(self, "_send_hist_dlg", None) is not None:
            self._send_hist_dlg.retranslate()
        if getattr(self, "_cpreset_dlg", None) is not None:
            self._cpreset_dlg.retranslate()
        self._rebuild_connection_preset_combo()
        if getattr(self, "_triggers_dlg", None) is not None:
            self._triggers_dlg.retranslate()
        if getattr(self, "_frame_dlg", None) is not None:
            self._frame_dlg.retranslate()
        if getattr(self, "_ar_dlg", None) is not None:
            self._ar_dlg.retranslate()
        if getattr(self, "_mbm_dlg", None) is not None:
            self._mbm_dlg.retranslate()
        if getattr(self, "_device_center_dlg", None) is not None:
            self._device_center_dlg.retranslate()
        if getattr(self, "_structured_dlg", None) is not None:
            self._structured_dlg.retranslate()
        if getattr(self, "_seq_dlg", None) is not None:
            self._seq_dlg.retranslate()
        if getattr(self, "_frame_builder_dlg", None) is not None:
            self._frame_builder_dlg.retranslate()
        if getattr(self, "_toolbox_dlg", None) is not None:
            self._toolbox_dlg.retranslate()
        if getattr(self, "_xfer_dlg", None) is not None:
            self._xfer_dlg.retranslate()
        if getattr(self, "_bridge_dlg", None) is not None:
            self._bridge_dlg.retranslate()
        # 选中即算校验和的状态栏文案是算出来的（含「选中」「选区过大」等译词），
        # tr_text 机制刷不到 —— 重算一次，让它跟着切语言
        self._update_sel_checksum()

    # ----- 持久化 -----
    @staticmethod
    def _settings_file(profile="") -> str:
        """
        优先 exe 同级目录（绿色版/U 盘携带特性），写不动就回退 %APPDATA%\\CommTool\\。
        场景：用户装到 Program Files（安装时选"为所有用户"），普通用户运行无写权限。
        macOS：不走绿色版逻辑（绝不写进 .app 包内 —— 会破坏签名、重装即丢），
        固定用 ~/Library/Application Support/CommTool/。
        profile：多窗口配置隔离。""=主配置 settings.ini（含旧版路径兼容）；其余=settings-<profile>.ini
        （只放主可写位置，不做旧版兼容——是新开的独立会话，本就该从默认起）。
        """
        name = "settings.ini" if not profile else "settings-%s.ini" % profile
        if sys.platform == "darwin":
            cfg_dir = os.path.join(
                os.path.expanduser("~/Library/Application Support"), "CommTool")
            new_ini = os.path.join(cfg_dir, name)
            # 向后兼容：早期 Mac 版曾回退到 ~/CommTool/，已有则沿用，避免设置丢失（仅主配置）。
            if not profile:
                legacy = os.path.join(os.path.expanduser("~"), "CommTool", "settings.ini")
                if not os.path.exists(new_ini) and os.path.exists(legacy):
                    return legacy
            try:
                os.makedirs(cfg_dir, exist_ok=True)
            except Exception:
                _log.debug("_settings_file failed", exc_info=True)
            return new_ini

        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))

        portable = os.path.join(base, name)

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
            except (OSError, PermissionError):
                return False
            # 写成功 = 目录可写；删测试文件是 best-effort，删不掉(杀软锁等)也不该误判为不可写
            try:
                os.remove(test)
            except OSError:
                pass
            return True

        if _portable_writable():
            return portable

        # 回退用户配置目录
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        cfg_dir = os.path.join(appdata, "CommTool")
        new_ini = os.path.join(cfg_dir, name)
        # 向后兼容：旧版 NetworkTool 的配置在 %APPDATA%\NetworkTool\。新目录尚无配置、
        # 旧目录已有 → 继续沿用旧文件，避免改名后老用户设置全部丢失（仅主配置）。
        if not profile:
            old_ini = os.path.join(appdata, "NetworkTool", "settings.ini")
            if not os.path.exists(new_ini) and os.path.exists(old_ini):
                return old_ini
        try:
            os.makedirs(cfg_dir, exist_ok=True)
        except Exception:
            _log.debug("_settings_file failed", exc_info=True)
        return new_ini

    def _save_settings(self, strict=False):
        """Persist the visible workspace.

        Normal autosave/exit callers keep the historical best-effort behaviour.
        Project operations pass ``strict=True`` because writing a project from a
        partially flushed workspace would silently lose the user's latest edits.
        """
        try:
            # Profile switch replaces self.settings after return; flush debounced edits to the old slot first.
            if getattr(self, "_frame_builder_dlg", None) is not None:
                self._frame_builder_dlg.commit_pending()
            if getattr(self, "_triggers_dlg", None) is not None:
                self._triggers_dlg.flush_pending()   # same: do not lose debounced rule edits
            if getattr(self, "_multi_send_dlg", None) is not None:
                self._multi_send_dlg.flush_pending()
            if getattr(self, "_keyword_dlg", None) is not None:
                self._keyword_dlg.flush_pending()
            if getattr(self, "_snip_dlg", None) is not None:
                self._snip_dlg.flush_pending()
            if getattr(self, "_cpreset_dlg", None) is not None:
                self._cpreset_dlg.flush_pending()
            if getattr(self, "_ar_dlg", None) is not None:
                self._ar_dlg.flush_pending()
            if getattr(self, "_seq_dlg", None) is not None:
                self._seq_dlg.flush_pending()
            if getattr(self, "_device_center_dlg", None) is not None:
                self._device_center_dlg.commit_pending(
                    notify=False, refresh_dirty=False)
            # 联动标签兜底落盘：commit_pending 只在标签变更时调 _save_device_link，
            # 若未来有路径直接改 _device_plot_tags/_device_dash_tags 而未走对话框，退出时仍要存。
            if hasattr(self, "_save_device_link"):
                self._save_device_link()
            s = self.settings
            s.setValue("geometry", self.saveGeometry())
            s.setValue("h_splitter", self.h_splitter.saveState())
            s.setValue("recv_font_size", self._recv_font_size)
            s.setValue("rx_hex", self.sw_rx_hex.isChecked())
            s.setValue("hexdump_view", self.sw_hexdump.isChecked())
            s.setValue("hexdump_width", self.cb_hexdump_width.currentText())
            s.setValue("numview", self.sw_numview.isChecked())
            s.setValue("numview_type", self.cb_numview_type.currentIndex())
            s.setValue("proto_highlight", self._proto_hl_on)
            s.setValue("wrap", self.sw_wrap.isChecked())
            s.setValue("show_timestamp", self.sw_show_timestamp.isChecked())
            s.setValue("packet_split", self.sw_packet_split.isChecked())
            s.setValue("line_split", self.sw_line_split.isChecked())
            s.setValue("line_nl_mode", self.cb_line_nl.currentIndex())
            s.setValue("ts_format", self.cb_ts_format.currentData() or "absolute")
            s.setValue("freeze_view", getattr(self, "_freeze_view", False))
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
            s.setValue("net_proto", self.cb_proto.currentText())
            s.setValue("vconn_loopback", self.sw_vconn_loop.isChecked())
            s.setValue("net_local_ip", self.cb_local_ip.currentText())
            s.setValue("net_local_port", self.ed_local_port.text())
            s.setValue("net_remote_ip", self.ed_remote_ip.text())
            s.setValue("net_remote_port", self.ed_remote_port.text())
            s.setValue("net_use_remote", self.sw_udp_remote.isChecked())
            s.setValue("net_group_addr", self.ed_group.text())
            # 串口设置
            s.setValue("ser_port", self.cb_port.currentData() or "")
            s.setValue("ser_baud", self.cb_baud.currentText())
            s.setValue("ser_databits", self.cb_databits.currentText())
            s.setValue("ser_parity", self.cb_parity.currentText())
            s.setValue("ser_stopbits", self.cb_stopbits.currentText())
            s.setValue("ser_flow", self.cb_flow.currentText())
            s.sync()
            if strict and s.status() != QSettings.NoError:
                raise OSError("QSettings sync failed (status=%s)" % int(s.status()))
            self._refresh_project_dirty_label()
            return True
        except Exception:
            traceback.print_exc()
            if strict:
                raise
            return False

    def _reload_section_states(self):
        """按当前配置槽恢复侧栏折叠状态；终端模式开启时终端组必须保持展开。"""
        s = self.settings
        if hasattr(self, "sec_recv_more"):
            self.sec_recv_more.setExpanded(
                s.value("sec_recv_more", False, type=bool), emit=False)
        if hasattr(self, "sec_send_term"):
            term_on = s.value("terminal_mode", getattr(self, "_terminal_on", False), type=bool)
            expanded = s.value("sec_send_term", False, type=bool) or term_on
            self.sec_send_term.setExpanded(expanded, emit=False)

    def _load_settings(self):
        s = self.settings
        self._load_send_hist()      # 发送命令历史(↑↓ 导航)
        self._reload_section_states()

        to_bool = _cfg_to_bool

        def restore_combo(combo, key):
            opts = [combo.itemText(i) for i in range(combo.count())]
            decision = _cfg_resolve_combo(
                s.value(key, None), opts, editable=combo.isEditable())
            if decision is None:
                return
            kind, payload = decision
            if kind == "index":
                combo.setCurrentIndex(payload)
            else:
                combo.setEditText(payload)

        try:
            geo = s.value("geometry")
            if geo:
                self.restoreGeometry(geo)
            elif self._profile:
                # New profile without saved geometry: cascade by profile index.
                off = _cfg_profile_offset(self._profile)
                self.move(self.x() + off, self.y() + off)
            h_state = s.value("h_splitter")
            if h_state:
                self.h_splitter.restoreState(h_state)
        except Exception:
            _log.debug("_load_settings geometry failed", exc_info=True)

        self._recv_font_size = _cfg_clamp_font(s.value("recv_font_size", 10))
        self.txt_recv.setFont(mono_font(self._recv_font_size))

        legacy_ts = s.value("timestamp", None)
        show_ts_raw = s.value("show_timestamp", legacy_ts if legacy_ts is not None else False)
        pkt_split_raw = s.value("packet_split", False)   # 不继承旧 timestamp 键：分包与时间戳互相独立，老用户升级不该被强制开分包
        self.sw_rx_hex.setChecked(to_bool(s.value("rx_hex", False)), animate=False)
        hexdump_on = to_bool(s.value("hexdump_view", False))
        numview_on = to_bool(s.value("numview", False))
        _h2, _n2 = _cfg_view_mutex(hexdump_on, numview_on)
        if (_h2, _n2) != (hexdump_on, numview_on):
            s.setValue("numview", False)
        hexdump_on, numview_on = _h2, _n2
        self.sw_hexdump.setChecked(hexdump_on, animate=False)
        self._hexdump_on = self.sw_hexdump.isChecked()
        restore_combo(self.cb_hexdump_width, "hexdump_width")
        # 数值视图：先钳好下拉再置开关——setChecked 会触发 _on_numview_toggled 走一遍
        # _refresh_hex_toggle_state / _reset_recv_state，此时类型下拉必须已是本配置的值
        nv_idx = _cfg_clamp_combo(
            s.value("numview_type", 2), self.cb_numview_type.count(), default=2)
        self.cb_numview_type.setCurrentIndex(nv_idx)
        self.sw_numview.setChecked(numview_on, animate=False)
        self._numview_on = self.sw_numview.isChecked()
        self._numview_carries.clear()                # 切配置＝数据流断点，各来源旧余数作废
        self._proto_hl_on = to_bool(s.value("proto_highlight", False))   # 开关在「帧解析」对话框，这里只同步状态
        self._proto_fields.clear()    # 切配置时清掉上一配置遗留的字段高亮
        if getattr(self, "_frame_dlg", None) is not None:
            self._frame_dlg.sync_highlight()
        # ANSI 着色 / 触发告警：同样随配置切换恢复（切配置=换一套工作现场）
        self._ansi_on = to_bool(s.value("ansi_color", False))
        self.sw_ansi.setChecked(self._ansi_on, animate=False)
        self._ansi_state = None
        self._ansi_pending = ""
        self._ansi_states = {}
        self._ansi_pendings = {}
        self._triggers = self._load_triggers()
        self._trigger_engine.set_rules(self._triggers)
        self._refresh_workspace_statuses()
        self._reset_trigger_decoders()
        if getattr(self, "_triggers_dlg", None) is not None:
            self._triggers_dlg._reload_list()
        self._refresh_hex_toggle_state()   # 启动/切配置后同步显示方式下拉与 ANSI 可用性
        self.sw_wrap.setChecked(to_bool(s.value("wrap", True)), animate=False)
        self.sw_show_timestamp.setChecked(to_bool(show_ts_raw), animate=False)
        self.sw_packet_split.setChecked(to_bool(pkt_split_raw), animate=False)
        self.sw_line_split.setChecked(to_bool(s.value("line_split", False)), animate=False)
        self.btn_filter_hl.blockSignals(True)
        self.btn_filter_hl.setChecked(to_bool(s.value("filter_highlight", False)))
        self.btn_filter_hl.blockSignals(False)
        log_split = s.value("log_split", None)
        if log_split is not None:
            self.cb_log_split.setCurrentText(str(log_split))
        nl_idx = _cfg_try_combo(s.value("line_nl_mode", 0), self.cb_line_nl.count())
        if nl_idx is not None:
            self.cb_line_nl.setCurrentIndex(nl_idx)
        ts_fmt = _cfg_norm_ts(s.value("ts_format", "absolute"))
        self._ts_format = ts_fmt
        self._ts_anchor = None      # 相对时间戳的会话起点（首次用时惰性定）
        idx = self.cb_ts_format.findData(ts_fmt)
        self.cb_ts_format.blockSignals(True)
        self.cb_ts_format.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_ts_format.blockSignals(False)
        freeze_saved = s.value("freeze_view", False, type=bool)
        self.sw_freeze_view.setChecked(freeze_saved, animate=False)
        # 字符编码 — 按 codec name 查 itemData 找回上次选项
        enc_saved = _cfg_norm_enc(s.value("encoding", "auto"))
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
        nl_idx = _cfg_try_combo(s.value("append_nl_mode", 0), self.cb_append_nl.count())
        if nl_idx is not None:
            self.cb_append_nl.setCurrentIndex(nl_idx)
        self.on_wrap_toggled(self.sw_wrap.isChecked())

        # 数字字段也用 is not None：导入空串场景下要能清字段（后续编辑/打开走默认逻辑兜底）
        v = s.value("packet_timeout")
        if v is not None:
            self.ed_packet_timeout.setText(str(v))
        v = s.value("max_lines")
        if v is not None:
            self.ed_max_lines.setText(str(v))
            self._on_max_lines_changed()
        v = s.value("period_ms")
        if v is not None:
            self.ed_period_ms.setText(str(v))
        # 用 is not None：空串也写入（清空导入场景）；只 None=未设过该 key 时才跳
        v = s.value("send_text")
        if v is not None:
            self.txt_send.setPlainText(str(v))

        ck_idx = _cfg_try_combo(s.value("checksum_idx", 0), self.cb_checksum.count())
        if ck_idx is not None:
            self.cb_checksum.setCurrentIndex(ck_idx)
        # 连接设置恢复（类型下拉含串口+网络协议）。同样用 is not None 支持空串导入清空
        restore_combo(self.cb_proto, "net_proto")
        v = s.value("net_local_ip", None)
        if v is not None:
            self.cb_local_ip.setCurrentText(str(v))
        v = s.value("net_local_port", None)
        if v is not None:
            self.ed_local_port.setText(str(v))
        v = s.value("net_remote_ip", None)
        if v is not None:
            self.ed_remote_ip.setText(str(v))
        v = s.value("net_remote_port", None)
        if v is not None:
            self.ed_remote_port.setText(str(v))
        self.sw_udp_remote.setChecked(to_bool(s.value("net_use_remote", False)), animate=False)
        self.sw_vconn_loop.setChecked(to_bool(s.value("vconn_loopback", False)), animate=False)
        v = s.value("net_group_addr", None)
        if v is not None:
            self.ed_group.setText(str(v))
        # 串口设置恢复
        restore_combo(self.cb_baud, "ser_baud")
        restore_combo(self.cb_databits, "ser_databits")
        restore_combo(self.cb_parity, "ser_parity")
        restore_combo(self.cb_stopbits, "ser_stopbits")
        restore_combo(self.cb_flow, "ser_flow")
        # cb_port 由后台扫描异步填充，此刻多半还空 → 记下待恢复端口，
        # 首次扫描结果到达时(_on_port_scan_complete)再按设备名选回上次端口。
        self._pending_restore_port = (s.value("ser_port", "") or None)
        self._update_net_fields()   # 按恢复的类型+开关刷新字段显隐/启用 + 按钮文案

    # ----- 系统托盘 -----
    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(get_app_icon(), self)
        self._tray.setToolTip(self._t("app_title") + self._title_suffix)

        menu = QMenu()
        self._tray_show_action = menu.addAction(self._t("tray_show"))
        self._tray_show_action.triggered.connect(self._show_from_tray)
        self._tray_about_action = menu.addAction(self._t("about"))
        self._tray_about_action.triggered.connect(self.open_about)
        menu.addSeparator()
        self._tray_quit_action = menu.addAction(self._t("tray_quit"))
        self._tray_quit_action.triggered.connect(self._real_quit)
        self._tray.setContextMenu(menu)

        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            # 点托盘图标 toggle：窗口正显示就缩小到托盘，已隐藏/最小化就恢复
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _real_quit(self):
        self._closing_real = True
        self.close()


    def _workspace_specs(self, key):
        """Workspace card entries; titles reuse existing i18n keys."""
        bind = {
            "fb_title": self.open_frame_builder,
            "frame_open": self.open_frame_parse,
            "tb_title": self.open_toolbox,
            "mbm_open": self._open_modbus_master,
            "device_title": self._open_device_center,
            "ar_title": self.open_auto_reply,
            "rr_title": self.open_rec_replay,
            "seq_title": self.open_sequence,
            "sc_title": self.open_script_console,
            "trg_title": self.open_triggers,
            "plot_open": self.open_plot,
            "dash_open": self.open_dashboard,
            "rd_title": self.open_rec_diff,
            "structured_title": self._open_structured_record,
            "bg_title": self.open_bridge,
        }
        out = []
        for title_key, icon in _ws_tool_entries(key):
            cb = bind.get(title_key)
            if cb is not None:
                out.append((title_key, icon, cb))
        return tuple(out)

    @staticmethod
    def _workspace_template_options():
        return _ws_template_options()

    def _build_protocol_template_panel(self):
        return _workspace_ui.build_protocol_template_panel(self)

    def _update_workspace_template_preview(self, *_):
        combo = getattr(self, "cb_workspace_template", None)
        label = getattr(self, "lbl_workspace_template_preview", None)
        if combo is None or label is None:
            return
        from project_templates import protocol_template_settings
        cfg = protocol_template_settings(combo.currentData() or "raw")
        yes = self._t("workspace_yes")
        no = self._t("workspace_no")
        framed = bool(cfg.get("packet_split") or cfg.get("line_split"))
        label.setText(self._t(
            "workspace_template_preview",
            connection=cfg.get("net_proto", "Serial"),
            rx=yes if cfg.get("rx_hex") else no,
            tx=yes if cfg.get("tx_hex") else no,
            framed=yes if framed else no,
        ))

    def _retranslate_workspace_template_panel(self):
        combo = getattr(self, "cb_workspace_template", None)
        if combo is None:
            return
        current = combo.currentData()
        combo.blockSignals(True)
        for index, (text_key, _template_id) in enumerate(
                self._workspace_template_options()):
            combo.setItemText(index, self._t(text_key))
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)
        self._update_workspace_template_preview()

    def _apply_workspace_protocol_template(self):
        combo = getattr(self, "cb_workspace_template", None)
        if combo is None:
            return
        template_name = combo.currentText()
        if not self._confirm_dlg(
                self._t("workspace_template_title"),
                self._t("workspace_template_confirm", name=template_name),
                ok_text=self._t("workspace_template_apply"), danger=False):
            return
        if not self._prepare_project_switch():
            return
        from project_templates import protocol_template_settings
        cfg = protocol_template_settings(combo.currentData() or "raw")
        # 旧版单规则配置会在 frame_rules 为空时被迁移；应用无规则模板时
        # 必须同时清理，否则刚清空的规则会在界面重载后被重新写回。
        legacy_frame_keys = ("frame_header", "frame_fields")
        old = {
            key: self.settings.value(key, None)
            for key in (*cfg.keys(), *legacy_frame_keys)
        }
        try:
            for key in legacy_frame_keys:
                self.settings.remove(key)
            for key, value in cfg.items():
                self.settings.setValue(key, value)
            self.settings.sync()
            self._apply_loaded_settings()
        except Exception as exc:
            for key, value in old.items():
                if value is None:
                    self.settings.remove(key)
                else:
                    self.settings.setValue(key, value)
            self.settings.sync()
            try:
                self._apply_loaded_settings()
            except Exception:
                _log.debug("_apply_workspace_protocol_template failed", exc_info=True)
            self._info_dlg(
                self._t("workspace_template_title"),
                self._t("workspace_template_fail", err=str(exc)), is_error=True)
            return
        self._refresh_project_dirty_label()
        self.toast(self._t("workspace_template_applied", name=template_name))

    def _build_workspace_page(self, key):
        return _workspace_ui.build_workspace_page(self, key)

    def _workspace_status_info(self, tool_key):
        """返回 (文案, 是否活跃)；None 表示该工具没有可展示的运行状态。"""
        if tool_key == "ar_title":
            active = bool(getattr(self, "_ar_on", False))
            return self._t("workspace_enabled" if active else "workspace_inactive"), active
        if tool_key == "mbm_open":
            active = bool(getattr(self, "_mbm_on", False))
            return self._t("workspace_enabled" if active else "workspace_inactive"), active
        if tool_key == "trg_title":
            engine = getattr(self, "_trigger_engine", None)
            active = bool(engine is not None and engine.active())
            return self._t("workspace_enabled" if active else "workspace_inactive"), active
        if tool_key == "seq_title":
            active = bool(getattr(self, "_seq_on", False))
            return self._t("workspace_running" if active else "workspace_stopped"), active
        if tool_key == "bg_title":
            dialog = getattr(self, "_bridge_dlg", None)
            engine = getattr(dialog, "engine", None) if dialog is not None else None
            active = bool(engine is not None and engine.is_active())
            return self._t("workspace_running" if active else "workspace_stopped"), active
        if tool_key == "structured_title":
            active = bool(getattr(getattr(self, "_structured_recorder", None),
                                  "recording", False))
            return self._t("workspace_running" if active else "workspace_stopped"), active
        if tool_key == "device_title":
            active = getattr(self, "_device_scan_state", None) is not None
            return self._t("workspace_running" if active else "workspace_stopped"), active
        return None

    def _refresh_workspace_statuses(self):
        for badge in self.findChildren(QLabel, "WorkspaceStatusBadge"):
            info = self._workspace_status_info(str(badge.property("tool_key") or ""))
            badge.setVisible(info is not None)
            if info is None:
                continue
            text, active = info
            badge.setText(text)
            badge.setProperty("active", "true" if active else "false")
            badge.style().unpolish(badge)
            badge.style().polish(badge)

    def _switch_workspace(self, key, persist=True):
        indexes = getattr(self, "_workspace_page_indexes", {})
        if key not in indexes:
            key = "terminal"
        if key not in indexes:
            return
        stack = getattr(self, "workspace_stack", None)
        if stack is None:
            return
        stack.setCurrentIndex(indexes[key])
        self._active_workspace = key
        for button_key, button in getattr(self, "_workbench_buttons", {}).items():
            button.setProperty("active", "true" if button_key == key else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        self._refresh_workspace_statuses()
        if persist:
            self.settings.setValue("active_workspace", key)

    def _build_workbench_bar(self):
        return _workspace_ui.build_workbench_bar(self)

    def _update_project_label(self, dirty=None):
        if not hasattr(self, "btn_project_menu"):
            return
        if not (self._project_name or self._project_path):
            self.btn_project_menu.setText(self._t("project_menu"))
            set_tooltip(self.btn_project_menu, self._t("project_menu"))
            return
        name = self._project_name or os.path.splitext(
            os.path.basename(self._project_path))[0]
        full_text = name + (" *" if dirty is True else "") + " ▾"
        # Elide long names so the project button stays compact beside workbench groups.
        shown = QFontMetrics(self.btn_project_menu.font()).elidedText(
            full_text, Qt.ElideMiddle, 172)
        self.btn_project_menu.setText(shown)
        set_tooltip(self.btn_project_menu, self._project_path or name)

    def _build_project_menu(self):
        return _workspace_ui.build_project_menu(self)

    def _show_project_menu(self):
        dirty = self._project_is_dirty()
        self._update_project_label(dirty)
        menu = self._build_project_menu()
        from PyQt5.QtCore import QPoint
        self._exec_transient_menu(
            menu, self.btn_project_menu.mapToGlobal(
                QPoint(0, self.btn_project_menu.height())))

    def _recent_projects(self):
        raw = self.settings.value("recent_projects", "[]")
        try:
            paths = json.loads(raw) if isinstance(raw, str) else list(raw or [])
        except Exception:
            paths = []
        valid = [str(p) for p in paths if p and os.path.isfile(str(p))][:8]
        if valid != paths:
            self.settings.setValue("recent_projects", json.dumps(valid, ensure_ascii=False))
        return valid

    def _clear_recent_projects(self):
        self.settings.setValue("recent_projects", "[]")
        self.settings.sync()

    def _set_restore_last_project(self, enabled):
        self.settings.setValue("restore_last_project", bool(enabled))
        self.settings.sync()

    def _restore_last_project(self):
        """启动后静默恢复上次工程；不存在的路径直接清理，不弹错误框。"""
        if self._project_name or self._project_path:
            return
        if not self.settings.value("restore_last_project", True, type=bool):
            return
        path = str(self.settings.value("last_project_path", "") or "")
        if not path:
            return
        if not os.path.isfile(path):
            self.settings.remove("last_project_path")
            self._recent_projects()
            self.settings.sync()
            return
        if not self._open_project_path(
                path, confirm=False, notify=False, notify_errors=False):
            # 文件存在但已损坏/版本不兼容/应用失败时也要忘掉，否则每次启动都会重复失败。
            self.settings.remove("last_project_path")
            self._remove_recent_project(path)
            self.settings.sync()

    def _remove_recent_project(self, path):
        raw = self.settings.value("recent_projects", "[]")
        try:
            paths = json.loads(raw) if isinstance(raw, str) else list(raw or [])
        except Exception:
            paths = []
        target = os.path.normcase(os.path.abspath(str(path)))
        kept = [str(item) for item in paths if item and
                os.path.normcase(os.path.abspath(str(item))) != target]
        self.settings.setValue("recent_projects", json.dumps(kept[:8], ensure_ascii=False))

    def _add_recent_project(self, path):
        path = os.path.abspath(path)
        paths = [p for p in self._recent_projects()
                 if os.path.normcase(os.path.abspath(p)) != os.path.normcase(path)]
        paths.insert(0, path)
        self.settings.setValue("recent_projects", json.dumps(paths[:8], ensure_ascii=False))
        self.settings.sync()

    @staticmethod
    def _project_fingerprint(settings):
        return _cfg_project_fingerprint(settings)

    def _snapshot_project_settings(self):
        """Read project keys already in QSettings (no flush / no UI write-back)."""
        return _cfg_snapshot_project(
            lambda k: self.settings.value(k, None), self._CFG_KEYS)

    def _refresh_project_dirty_label(self):
        if not (self._project_name or self._project_path):
            return
        if self._project_baseline is None:
            self._update_project_label(True)
            return
        dirty = (self._project_fingerprint(self._snapshot_project_settings())
                 != self._project_baseline)
        self._update_project_label(dirty)

    def _project_is_dirty(self):
        if not (self._project_name or self._project_path):
            return False
        if self._project_baseline is None:
            return True
        current = self._collect_project_settings()
        return self._project_fingerprint(current) != self._project_baseline

    def _confirm_project_reset(self):
        """Warn that new-project template replaces the whole workspace config."""
        return self._confirm_dlg(
            self._t("project_reset_title"),
            self._t("project_reset_body"),
            ok_text=self._t("project_reset_ok"),
            danger=False)

    def _confirm_project_switch(self):
        try:
            dirty = self._project_is_dirty()
        except Exception as e:
            self._info_dlg(
                self._t("project_save"),
                self._t("project_save_fail", err=str(e)),
                is_error=True)
            return False
        if not dirty:
            return True
        dlg = InfoDialog(
            self._t("project_unsaved_title"),
            self._t("project_unsaved_body",
                    name=self._project_name or self._t("project_untitled")),
            ok_text=self._t("project_save"),
            is_error=True,
            theme_id=self._theme_id(),
            parent=None,
            confirm=True,
            cancel_text=self._t("cancel"),
            danger=False,
            third_text=self._t("project_discard"),
        )
        result = dlg.exec_()
        if result == QDialog.Rejected:
            return False
        if result == QDialog.Accepted:
            return self.save_project()
        return result == InfoDialog.ThirdAction

    def _project_wizard_texts(self):
        keys = (
            "title", "default_name", "name", "device", "connection", "protocol",
            "step_device", "step_device_tip", "step_connection", "step_connection_tip",
            "step_protocol", "step_protocol_tip", "step_display", "step_display_tip",
            "step_save", "step_save_tip", "view_terminal", "view_hex", "view_timestamp",
            "view_plot", "view_dashboard", "summary", "back", "next", "finish",
        )
        out = {k: self._t("project_wizard_" + k) for k in keys}
        out["cancel"] = self._t("cancel")
        out["device_types"] = [
            self._t("project_device_generic"), self._t("project_device_modbus"),
            self._t("project_device_at"), self._t("project_device_sensor"),
            self._t("project_device_network"), self._t("project_device_custom"),
        ]
        out["protocol_types"] = [
            self._t("project_proto_raw"), self._t("project_proto_modbus_rtu"),
            self._t("project_proto_modbus_tcp"), self._t("project_proto_nmea"),
            self._t("project_proto_at"), self._t("project_proto_header"),
            self._t("project_proto_delimiter"), self._t("project_proto_custom"),
        ]
        return out

    def _collect_project_settings(self):
        self._save_settings(strict=True)
        return self._snapshot_project_settings()

    def _apply_project_settings(self, data, gate_scripts=True):
        """Replace QSettings/UI with project settings; restore previous on failure."""
        data = dict(data or {})
        if gate_scripts:
            data = self._ar_gate_imported_scripts(data)
            data = self._gate_imported_script_lib(data)
            data = self._gate_imported_trigger_actions(data)
        converted = _cfg_coerce_map(data, self._CFG_KEYS)

        old = {key: self.settings.value(key, None) for key in self._CFG_KEYS}
        from project_model import prepare_project_settings
        incoming = prepare_project_settings(converted, old, self._CFG_KEYS)

        def replace(values):
            for cfg_key in self._CFG_KEYS:
                self.settings.remove(cfg_key)
            for cfg_key, cfg_value in values.items():
                if cfg_value is not None:
                    self.settings.setValue(cfg_key, cfg_value)
            self.settings.sync()
            if self.settings.status() != QSettings.NoError:
                raise OSError(
                    "QSettings sync failed (status=%s)" % int(self.settings.status()))
            self._restore_field_defaults()
            self._apply_loaded_settings()

        try:
            replace(incoming)
        except Exception:
            # Roll back QSettings + UI so a partial apply cannot leave a mixed state.
            try:
                replace(old)
            except Exception:
                _log.debug("import_config rollback failed", exc_info=True)
            raise
        return len(incoming)

    def _prepare_project_switch(self):
        """Disconnect (or cancel reconnect) before switching projects."""
        if self.conn is None:
            # Clear a queued auto-reconnect so it cannot reopen against the new project.
            self._cancel_reconnect()
            self._serial_reconnect_cfg = None
            return True
        if not self._confirm_dlg(
                self._t("project_disconnect_title"),
                self._t("project_disconnect_body"),
                ok_text=self._t("project_disconnect"),
                danger=False):
            return False
        self.toggle_conn()
        return self.conn is None

    def new_project(self):
        from project_wizard import ProjectWizard
        wizard = ProjectWizard(
            self._project_wizard_texts(), CONN_TYPES, self,
            theme_id=self._theme_id())
        if wizard.exec_() != QDialog.Accepted:
            return
        data = wizard.result_data()
        if not self._confirm_project_switch():
            return
        # Template replace clears multi-send / scripts / keywords / etc.
        if not self._confirm_project_reset():
            return
        # Choose save path BEFORE wiping workspace so Cancel keeps current config.
        default_name = (data["name"] or "CommTool_project") + ".ctproj"
        path, _ = QFileDialog.getSaveFileName(
            self, self._t("project_save"), default_name, self._t("project_filter"))
        if not path:
            return
        if not path.lower().endswith(".ctproj"):
            path += ".ctproj"
        if not self._prepare_project_switch():
            return
        views = data["views"]
        from project_templates import protocol_template_settings
        template_cfg = protocol_template_settings(
            data["protocol_template"], data["connection_type"])
        # Display choices from the wizard override template recommendations.
        template_cfg["rx_hex"] = views["hex"]
        template_cfg["show_timestamp"] = views["timestamp"]
        # Keep the connection the user confirmed in step 2.
        template_cfg["net_proto"] = data["connection_type"]

        # Snapshot so a later save failure can restore the previous workspace.
        old_cfg = {key: self.settings.value(key, None) for key in self._CFG_KEYS}
        old_path = self._project_path
        old_name = self._project_name
        old_meta = dict(self._project_meta)
        old_baseline = self._project_baseline
        try:
            self._apply_project_settings(template_cfg, gate_scripts=False)
        except Exception as e:
            self._info_dlg(self._t("project_new"),
                           self._t("project_apply_fail", err=str(e)), is_error=True)
            return

        self._project_path = os.path.abspath(path)
        self._project_name = data["name"]
        self._project_meta = {
            "device_type": data["device_type"],
            "device_label": data["device_label"],
            "connection_type": template_cfg["net_proto"],
            "protocol_template": data["protocol_template"],
            "protocol_label": data["protocol_label"],
            "views": views,
        }
        self._project_baseline = None
        self._update_project_label(True)
        if not self.save_project():
            # Disk/save failed after apply: put back previous QSettings + project state.
            try:
                for cfg_key in self._CFG_KEYS:
                    self.settings.remove(cfg_key)
                for cfg_key, cfg_value in old_cfg.items():
                    if cfg_value is not None:
                        self.settings.setValue(cfg_key, cfg_value)
                self.settings.sync()
                self._restore_field_defaults()
                self._apply_loaded_settings()
            except Exception:
                traceback.print_exc()
                self._info_dlg(
                    self._t("project_new"),
                    self._t("project_restore_fail"),
                    is_error=True)
            self._project_path = old_path
            self._project_name = old_name
            self._project_meta = old_meta
            self._project_baseline = old_baseline
            self._refresh_project_dirty_label()
            if not (self._project_name or self._project_path):
                self._update_project_label()
            return
        # Open optional views only after save finishes.
        if views["plot"]:
            QTimer.singleShot(0, self.open_plot)
        if views["dashboard"]:
            QTimer.singleShot(0, self.open_dashboard)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._t("project_open"), "", self._t("project_filter"))
        if not path:
            return
        self._open_project_path(path)

    def _open_project_path(self, path, confirm=True, notify=True, notify_errors=True):
        try:
            from project_model import load_project
            payload = load_project(path)
        except Exception as e:
            if notify_errors:
                self._info_dlg(self._t("project_open"),
                               self._t("project_open_fail", err=str(e)), is_error=True)
            return False
        if confirm and not self._confirm_project_switch():
            return False
        if not self._prepare_project_switch():
            return False
        try:
            from project_model import merge_project_resources
            project_settings = merge_project_resources(
                payload["settings"], payload.get("resources", {}))
            self._apply_project_settings(project_settings)
        except Exception as e:
            if notify_errors:
                self._info_dlg(self._t("project_open"),
                               self._t("project_open_fail", err=str(e)), is_error=True)
            return False
        self._project_path = os.path.abspath(path)
        self._project_name = str(payload.get("name") or "")
        self._project_meta = dict(payload.get("metadata") or {})
        self._project_baseline = self._project_fingerprint(
            self._collect_project_settings())
        self.settings.setValue("last_project_path", self._project_path)
        self._add_recent_project(self._project_path)
        self._update_project_label()
        if notify:
            self._info_dlg(self._t("project_open"),
                           self._t("project_opened", path=self._project_path))
        return True

    def save_project(self, save_as=False):
        path = None if save_as else self._project_path
        if not path:
            default_name = (self._project_name or "CommTool_project") + ".ctproj"
            path, _ = QFileDialog.getSaveFileName(
                self, self._t("project_save"), default_name, self._t("project_filter"))
            if not path:
                return False
            if not path.lower().endswith(".ctproj"):
                path += ".ctproj"
        try:
            from project_model import collect_project_resources, make_project, save_project
            settings = self._collect_project_settings()
            metadata = dict(self._project_meta)
            metadata["connection_type"] = settings.get(
                "net_proto", metadata.get("connection_type", "Serial"))
            views = dict(metadata.get("views") or {})
            views.update({
                "terminal": True,
                "hex": bool(self.sw_rx_hex.isChecked()),
                "timestamp": bool(self.sw_show_timestamp.isChecked()),
            })
            metadata["views"] = views
            payload = make_project(
                self._project_name or self._t("project_untitled"),
                metadata,
                settings,
                APP_VERSION,
                resources=collect_project_resources(settings),
            )
            save_project(path, payload)
        except Exception as e:
            self._info_dlg(self._t("project_save"),
                           self._t("project_save_fail", err=str(e)), is_error=True)
            return False
        self._project_path = os.path.abspath(path)
        self._project_name = str(payload["name"])
        self._project_meta = dict(payload["metadata"])
        self._project_baseline = self._project_fingerprint(payload["settings"])
        self.settings.setValue("last_project_path", self._project_path)
        self._add_recent_project(self._project_path)
        self._update_project_label()
        self._info_dlg(self._t("project_save"),
                       self._t("project_saved", path=self._project_path))
        return True

    def close_project(self):
        if not self._confirm_project_switch():
            return False
        self._project_path = None
        self._project_meta = {}
        self._project_name = ""
        self._project_baseline = None
        self.settings.remove("last_project_path")
        self.settings.sync()
        self._update_project_label()
        return True

    @staticmethod
    def _exec_transient_menu(menu, pos):
        """执行一次性菜单并确保释放；带 parent 的 QMenu 不主动删会在主窗口下持续累积。"""
        try:
            return menu.exec_(pos)
        finally:
            try:
                menu.deleteLater()
            except RuntimeError:
                pass       # 菜单动作若已销毁 parent，Qt 可能已先删除菜单

    def _show_titlebar_help_menu(self):
        """标题栏「帮助」按钮下拉：当前含「关于」一项（含检查更新），后续可继续加文档链接等。
        菜单使用项目主题色，弹在按钮正下方。"""
        menu = QMenu(self)
        c = chrome_for(self._theme_id())
        qss = f"""
            QMenu {{ background-color: {c['card_bg']}; color: {c['text']};
                     border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
            QMenu::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
            QMenu::item:disabled {{ color: {c['text_sec']}; }}
        """
        menu.setStyleSheet(qss)
        # 「打开配置」子菜单：列出已保存的配置（主/2/3…）。点空闲的 → 把【当前窗口】就地切到该
        # 配置（不新开窗口）；「当前窗口」/「使用中」标注并禁用。末尾「新建窗口（自动分配）」= 另开
        # 一个独立窗口占下一个空闲槽位。解决「全部关掉后想用回以前第 3 个配置」——数据一直在磁盘。
        sub = menu.addMenu(self._t("open_profile"))
        sub.setStyleSheet(qss)
        for p in [""] + [str(n) for n in range(2, 9)]:
            try:
                if not os.path.exists(CommTool._settings_file(p)):
                    continue
            except Exception:
                continue
            name = self._t("profile_main") if p == "" else self._t("profile_n", n=p)
            if p == self._profile:
                sub.addAction(self._t("profile_current", name=name)).setEnabled(False)
            elif self._profile_in_use(p):
                sub.addAction(self._t("profile_busy", name=name)).setEnabled(False)
            else:
                sub.addAction(name).triggered.connect(
                    lambda *_a, prof=p: self._switch_profile(prof))   # 就地切换到该配置
        sub.addSeparator()
        sub.addAction(self._t("new_window_auto")).triggered.connect(
            lambda *_a: self._open_new_window())                      # 另开一个独立窗口
        # 「删除配置」子菜单：仅列可删的编号配置(存在、非当前、空闲；主配置不可删)。有才显示。
        deletable = []
        for _n in range(2, 9):
            _p = str(_n)
            try:
                _ex = os.path.exists(CommTool._settings_file(_p))
            except Exception:
                _ex = False
            if _ex and _p != self._profile and not self._profile_in_use(_p):
                deletable.append(_p)
        if deletable:
            sub_del = menu.addMenu(self._t("delete_profile"))
            sub_del.setStyleSheet(qss)
            for _p in deletable:
                sub_del.addAction(self._t("profile_n", n=_p)).triggered.connect(
                    lambda *_a, prof=_p: self._delete_profile(prof))
        menu.addSeparator()
        act = menu.addAction(self._t("about") + "…")
        act.triggered.connect(self.open_about)
        # 弹在按钮正下方
        from PyQt5.QtCore import QPoint
        self._exec_transient_menu(menu, self.btn_titlebar_help.mapToGlobal(
            QPoint(0, self.btn_titlebar_help.height())))

    @staticmethod
    def _profile_in_use(profile):
        """探测某配置槽位是否被活着的窗口占用：能拿到 .mwlock=空闲(立即释放)，拿不到=使用中。
        陈旧锁(持有进程已死)会被 tryLock 判为可夺 → 视为空闲，符合预期；当前窗口自持的槽位
        因锁被本进程占着 → 判为使用中（菜单里单独标「当前窗口」）。"""
        from PyQt5.QtCore import QLockFile
        lf = QLockFile(CommTool._settings_file(profile) + ".mwlock")
        if lf.tryLock(0):
            lf.unlock()
            return False
        return True

    def _open_new_window(self, profile=None):
        """再开一个独立窗口（新进程）。profile=None → 自动占下一个空闲槽位（settings-N.ini）；
        指定 profile（""=主配置 / "2".."8"）→ 以该已保存配置打开（供「打开指定配置」子菜单用）。
        若目标配置在启动瞬间恰被别人占用，新进程会回落到自动分配，仍能开出窗口。"""
        import subprocess
        try:
            if getattr(sys, "frozen", False):
                args = [sys.executable]                                  # 冻结版：exe 自身
            else:
                args = [sys.executable, os.path.abspath(sys.argv[0])]    # 源码运行：python + main.py
            if profile is not None:
                args.append("--profile=%s" % profile)                    # main() 解析后优先占该槽位
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(args, **kwargs)
        except Exception as e:
            self.toast(self._t("err_new_window", e=e), error=True)

    def _switch_profile(self, profile):
        """把【当前窗口】就地切换到另一个已保存配置（不新开窗口）。
        流程：抢目标配置的槽位锁(被别的窗口占用则拒绝) → 存当前配置 + 断开当前连接(切配置=新会话)
        → 交换 profile 锁(释放旧的、持有新的) → 改 settings 指向 + 标题 → 从新配置重载全部 UI。
        窗口位置/大小保持不变(不跳到目标配置上次的几何)，减少视觉突兀。"""
        profile = str(profile)
        if profile == self._profile:
            return
        # A project is bound to the current profile's QSettings.  Keeping that
        # binding after swapping self.settings would make a later Save overwrite
        # the old .ctproj with the new profile's unrelated workspace.
        if not self._confirm_project_switch():
            return
        from PyQt5.QtCore import QLockFile
        # 1) 先抢目标槽位锁；被占（别的窗口正用该配置）→ 拒绝，避免两个窗口写同一文件
        new_lock = QLockFile(self._settings_file(profile) + ".mwlock")
        if not new_lock.tryLock(100):
            self.toast(self._t("profile_switch_busy"), error=True)
            return
        # 2) 存当前配置 + 停自动重连 + 断开当前连接（切配置=新会话）。旧连接/排队的重连都属旧配置，
        #    留着会在新配置下误发起连接：故无条件取消重连、并且只要 conn 非空就拆
        #    （TCP Client "连接中" 时 is_open=False，只判 is_open 会漏掉、旧连接稍后可能在新配置下连上）。
        try:
            self._save_settings(strict=True)
        except Exception as e:
            new_lock.unlock()
            self._info_dlg(
                self._t("profile_save_fail_title"),
                self._t("profile_save_fail", err=str(e)),
                is_error=True)
            return
        self._cancel_reconnect()
        self._reconnect_attempts = 0
        if self.conn is not None:
            self.close_conn()
        # 3) 交换 profile 锁：新锁挂 app 保活、释放旧锁（旧配置槽位随即空出，可被别的窗口用）
        app = QApplication.instance()
        old_lock = getattr(app, "_profile_lock", None)
        app._profile_lock = new_lock
        if old_lock is not None:
            try:
                old_lock.unlock()
            except Exception:
                _log.debug("_switch_profile failed", exc_info=True)
        # 4) 切换身份 + settings 指向新配置文件
        self._profile = profile
        self._title_suffix = "" if not profile else " (%s)" % profile
        self.settings = QSettings(self._settings_file(profile), QSettings.IniFormat)
        self._project_path = None
        self._project_meta = {}
        self._project_name = ""
        self._project_baseline = None
        self._update_project_label()
        # 5) 保住当前窗口几何（下面 _load_settings 会按新配置的存档几何挪窗，切换时不希望窗口跳走）
        geo = self.saveGeometry()
        try:
            # 先复位「缺失键则不改控件」的字段（发送文本/地址/串口参数等）到构建默认值，
            # 否则目标配置缺某键时会残留上一配置的值、之后保存还会污染目标配置。
            self._restore_field_defaults()
            self._apply_loaded_settings()   # 与「导入配置」共用：整体重载新配置到 UI
        except Exception:
            _log.debug("_switch_profile failed", exc_info=True)
        self.restoreGeometry(geo)
        # 6) 刷新标题栏 / 任务栏 / 托盘的窗口名后缀
        self.setWindowTitle(self._t("app_title") + self._title_suffix)
        if hasattr(self, "title_bar"):
            self.title_bar.set_title(self._t("app_title") + self._title_suffix)
        if self._tray:
            self._tray.setToolTip(self._t("app_title") + self._title_suffix)
        name = self._t("profile_main") if not profile else self._t("profile_n", n=profile)
        self.toast(self._t("profile_switched", name=name))

    # 「缺失键则不改控件」的字段（见 _load_settings：这些用 is not None/restore_combo，缺失就不动）。
    # 切换配置到不完整配置前先复位它们，避免残留上一配置的值。line edit→.text；combo→.currentText。
    _RESET_LINE_EDITS = _CFG_RESET_LINE_EDITS
    _RESET_COMBOS = _CFG_RESET_COMBOS

    def _capture_field_defaults(self):
        """Snapshot build-time defaults before _load_settings overwrites."""
        values = {"txt_send": self.txt_send.toPlainText()}
        for n in self._RESET_LINE_EDITS:
            w = getattr(self, n, None)
            if w is not None:
                values[n] = w.text()
        for n in self._RESET_COMBOS:
            w = getattr(self, n, None)
            if w is not None:
                values[n] = w.currentText()
        self._field_defaults = _cfg_capture_defaults(values)

    def _restore_field_defaults(self):
        """把 _capture_field_defaults 记录的默认值写回控件（切换配置前调用）。"""
        d = getattr(self, "_field_defaults", None)
        if not d:
            return
        if "txt_send" in d:
            self.txt_send.setPlainText(d["txt_send"])
        for n in self._RESET_LINE_EDITS:
            w = getattr(self, n, None)
            if w is not None and n in d:
                w.setText(d[n])
        for n in self._RESET_COMBOS:
            w = getattr(self, n, None)
            if w is not None and n in d:
                w.setCurrentText(d[n])
        if hasattr(self, "cb_port") and self.cb_port.count() > 0:
            self.cb_port.setCurrentIndex(0)   # 串口选择复位到第一个（ser_port 缺失时不残留旧口）

    def _delete_profile(self, profile):
        """删除一个已保存的编号配置（settings-<N>.ini + QSettings 内部锁）。二次确认后删除。
        只删 2..8 的编号配置：主配置("")不可删、当前窗口在用的不可删、别的窗口开着的不可删。
        用 QLockFile 独占目标槽位=确认无人在用后再删；unlock() 会移除 .mwlock（Qt 负责删文件，
        勿再手工删——否则可能删掉另一窗口刚抢到该槽位新建的锁，导致两窗口同写一配置）。"""
        profile = str(profile)
        if profile not in {"2", "3", "4", "5", "6", "7", "8"} or profile == self._profile:
            return   # 非 2..8 / 主配置 / 当前窗口：菜单本不给入口，双保险
        name = self._t("profile_n", n=profile)
        if not self._confirm_dlg(self._t("profile_delete_title"),
                                 self._t("profile_delete_body", name=name),
                                 ok_text=self._t("delete")):
            return
        from PyQt5.QtCore import QLockFile
        base = self._settings_file(profile)
        lk = QLockFile(base + ".mwlock")
        if not lk.tryLock(0):        # 拿不到锁 = 正被别的窗口用 → 不能删
            self.toast(self._t("profile_delete_busy"), error=True)
            return
        removed = False
        try:
            if os.path.exists(base):
                os.remove(base)
                removed = True
            p_qlock = base + ".lock"   # QSettings 可能残留的内部锁
            if os.path.exists(p_qlock):
                try:
                    os.remove(p_qlock)
                except OSError:
                    pass
        except OSError:
            pass
        finally:
            lk.unlock()   # 释放并移除 .mwlock（不手工再删，避免与刚抢到该槽位的新窗口竞态）
        if removed:
            self.toast(self._t("profile_deleted", name=name))
        else:
            self._info_dlg(self._t("profile_delete_title"),
                           self._t("profile_delete_fail", name=name), is_error=True)

    # ----- 自动检查更新（启动 + 每 6 小时静默查；有新版 → 右下角版本号亮可点徽标）-----
    def _auto_update_check(self):
        """后台静默检查新版本：拿到清单后若有新版就在右下角版本号显示可点徽标；出错不打扰用户。"""
        if not self.settings.value("auto_update_check", True, type=bool):
            return
        if self._auto_checker is not None:     # 上一次还在跑就不重复发
            return
        chk = UpdateChecker(APP_VERSION, self)
        chk.finished.connect(self._on_auto_update_checked)
        self._auto_checker = chk
        chk.start()

    def _on_auto_update_checked(self, info, err):
        self._auto_checker = None
        ver = info.get("version", "") if info else ""
        if info and info.get("newer") and ver:   # 防御：version 缺失/为空就不挂空白徽标
            self._show_update_badge(ver)

    def _show_update_badge(self, ver):
        """把右下角版本号变成「● 可更新 vX」高亮可点徽标，点击打开「关于」走下载更新。"""
        if not hasattr(self, "lbl_version"):
            return
        self._update_badge_version = ver
        self.lbl_version.setText(self._t("update_badge", ver=ver))
        set_tooltip(self.lbl_version, self._t("update_badge_tip", ver=ver))
        self.lbl_version.setCursor(Qt.PointingHandCursor)
        self._apply_version_label_style()

    def _apply_version_label_style(self, c=None):
        """按是否有新版徽标给右下角版本号上色（普通=次要色；徽标=强调色加粗）。主题切换时复用。
        c：调用方已算好的 chrome palette，传入可省一次 chrome_for（如 refresh_theme）。"""
        if not hasattr(self, "lbl_version"):
            return
        if c is None:
            c = chrome_for(self._theme_id())
        if getattr(self, "_update_badge_version", None):
            self.lbl_version.setStyleSheet(
                f"color: {c['accent']}; background: transparent; font-weight: 600;")
        else:
            self.lbl_version.setStyleSheet(f"color: {c['text_sec']}; background: transparent;")

    def _set_auto_update_check(self, enabled):
        """「自动检查更新」开关：写盘 + 起停 6h 定时器；刚打开则立即静默查一次。"""
        self.settings.setValue("auto_update_check", bool(enabled))
        self.settings.sync()
        if enabled:
            if not self._update_timer.isActive():
                self._update_timer.start()
            QTimer.singleShot(0, self._auto_update_check)
        else:
            self._update_timer.stop()

    def open_about(self):
        """打开「关于 + 检查更新」对话框（托盘菜单触发）。
        parent=None：与其它子对话框一致，避免干扰主窗 WM_NCHITTEST。modal 由 setModal(True) 保证。"""
        dlg = AboutDialog(
            tr=self._t,
            app_name=self._t("app_title"),
            version=APP_VERSION,
            icon=get_app_icon(),
            theme_id=self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT,
            on_quit=self._real_quit,
            auto_check=self.settings.value("auto_update_check", True, type=bool),
            on_auto_check_changed=self._set_auto_update_check,
            parent=None,
        )
        dlg.exec_()

    def showEvent(self, event):
        super().showEvent(event)
        # 第一次显示后做一次：把右侧发送区卡片的高度上限设为左侧发送区卡片的实际高度
        # 这样右侧发送区不会因为 QTextEdit 的 Expanding 策略吃掉过多空间，顶底都和左侧对齐
        if not getattr(self, "_height_synced", False):
            self._height_synced = True
            QTimer.singleShot(0, self._sync_right_send_height)
            # 数据区顶部工具栏按钮：样式生效后按内容宽度定宽，避免首次显示时文字被裁
            QTimer.singleShot(0, self._fit_data_toolbar)
            # 兜底：窗口若落在屏幕外(多显示器/旧位置)则搬回主屏，避免"进程在、窗口看不见"
            QTimer.singleShot(0, self._ensure_on_screen)
        # 跨显示器后状态栏等区域不重绘的修复（多屏 backing store 刷新）：监听屏幕切换（只连一次）
        if not getattr(self, "_screen_sig_connected", False):
            wh = self.windowHandle()
            if wh is not None:
                wh.screenChanged.connect(self._on_screen_changed)
                self._screen_sig_connected = True
        # 无边框窗口默认丢了 WS_MINIMIZEBOX 样式，任务栏图标 / Aero 无法最小化；
        # 用 Windows API 把最小化 + 最大化框样式加回去（只做一次）。
        if sys.platform == "win32" and not getattr(self, "_minbox_set", False):
            self._minbox_set = True
            try:
                import ctypes
                hwnd = int(self.winId())
                GWL_STYLE = -16
                WS_MINIMIZEBOX = 0x00020000
                WS_MAXIMIZEBOX = 0x00010000
                cur = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                ctypes.windll.user32.SetWindowLongW(
                    hwnd, GWL_STYLE, cur | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
            except Exception:
                pass

    def _on_screen_changed(self, _screen):
        # 窗口移到另一个显示器后强制重绘（含底部状态栏），
        # 修复多屏 backing store 不刷新导致状态栏显示空白的问题。
        self.repaint()
        if hasattr(self, "status_bar"):
            self.status_bar.repaint()

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
            # 最大化/还原后底部状态栏可能不重绘（尤其副屏），延迟一拍强制刷新
            if hasattr(self, "status_bar"):
                QTimer.singleShot(0, self.status_bar.repaint)
        super().changeEvent(e)

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0024:  # WM_GETMINMAXINFO
                    # 无边框窗口最大化时限制到当前显示器的「工作区」，否则会覆盖任务栏 /
                    # 超出屏幕底部，导致状态栏被挤出看不到（尤其副屏没有任务栏时整屏覆盖）。
                    class _PT(ctypes.Structure):
                        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

                    class _RC(ctypes.Structure):
                        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                                    ("r", ctypes.c_long), ("b", ctypes.c_long)]

                    class _MI(ctypes.Structure):
                        _fields_ = [("cb", ctypes.c_ulong), ("rcMon", _RC),
                                    ("rcWork", _RC), ("flags", ctypes.c_ulong)]

                    class _MMI(ctypes.Structure):
                        _fields_ = [("ptRes", _PT), ("ptMaxSize", _PT), ("ptMaxPos", _PT),
                                    ("ptMinTrack", _PT), ("ptMaxTrack", _PT)]

                    hmon = ctypes.windll.user32.MonitorFromWindow(int(self.winId()), 2)
                    if hmon:
                        mi = _MI()
                        mi.cb = ctypes.sizeof(_MI)
                        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
                        w = mi.rcWork
                        mon = mi.rcMon
                        mmi = _MMI.from_address(int(msg.lParam))
                        mmi.ptMaxPos.x = w.l - mon.l       # 最大化位置（相对显示器左上）
                        mmi.ptMaxPos.y = w.t - mon.t
                        mmi.ptMaxSize.x = w.r - w.l        # 最大化尺寸 = 工作区尺寸
                        mmi.ptMaxSize.y = w.b - w.t
                        mmi.ptMaxTrack.x = w.r - w.l
                        mmi.ptMaxTrack.y = w.b - w.t
                    return True, 0
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

    # ----- 无边框窗口缩放（macOS / Linux：手动实现，不依赖 startSystemResize）-----
    def _edges_at(self, pos):
        """鼠标点相对窗口的边缘命中，返回 Qt.Edges（无命中则为 0）。"""
        m = self.RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        edges = Qt.Edges()
        if x <= m:
            edges |= Qt.LeftEdge
        elif x >= w - m:
            edges |= Qt.RightEdge
        if y <= m:
            edges |= Qt.TopEdge
        elif y >= h - m:
            edges |= Qt.BottomEdge
        return edges

    def _resize_cursor(self, edges):
        """命中边缘对应的缩放光标（仅在拖拽期间用 grabMouse 设置）。"""
        if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            return Qt.SizeFDiagCursor
        if edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            return Qt.SizeBDiagCursor
        if edges & (Qt.LeftEdge | Qt.RightEdge):
            return Qt.SizeHorCursor
        if edges & (Qt.TopEdge | Qt.BottomEdge):
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def _perform_resize(self, gpos):
        """按拖拽位移调整窗口几何，遵守最小尺寸。"""
        g = QRect(self._resize_start_geo)
        dx = gpos.x() - self._resize_start_mouse.x()
        dy = gpos.y() - self._resize_start_mouse.y()
        minw, minh = self.minimumWidth(), self.minimumHeight()
        e = self._resize_edges
        if e & Qt.LeftEdge:
            g.setLeft(min(g.left() + dx, g.right() - minw + 1))
        elif e & Qt.RightEdge:
            g.setRight(max(g.right() + dx, g.left() + minw - 1))
        if e & Qt.TopEdge:
            g.setTop(min(g.top() + dy, g.bottom() - minh + 1))
        elif e & Qt.BottomEdge:
            g.setBottom(max(g.bottom() + dy, g.top() + minh - 1))
        self.setGeometry(g)

    def _end_resize(self):
        """结束缩放：清状态、释放鼠标、还原覆盖光标。"""
        self._resize_edges = Qt.Edges()
        self.releaseMouse()
        QApplication.restoreOverrideCursor()

    def _update_hover_cursor(self, edges):
        """悬停边缘时设置/复位缩放光标（带状态去抖，避免反复 set/unset）。"""
        shape = self._resize_cursor(edges) if edges else None
        if shape == self._hover_cursor_shape:
            return
        self._hover_cursor_shape = shape
        if shape is not None:
            self.setCursor(shape)
        else:
            self.unsetCursor()

    def leaveEvent(self, e):
        # 鼠标离开窗口 → 复位悬停缩放光标；缩放进行中不动，避免拖拽时光标被清成箭头
        if not self._resize_edges and self._hover_cursor_shape is not None:
            self._hover_cursor_shape = None
            self.unsetCursor()
        super().leaveEvent(e)

    def _shutdown(self):
        """退出前统一清理。closeEvent 的两条退出路径（直接退出 / 选「退出」）共用：
        以前两段逐行复制，加清理步骤极易漏改其中一条导致线程/定时器泄漏，故抽成一处。"""
        self._user_closing = True             # 退出 → 跳过自动重连
        self._cancel_reconnect()
        if hasattr(self, "_ms_cycle_timer"):
            self._ms_cycle_timer.stop()   # 先停循环定时器，避免销毁中触发 toast
        if hasattr(self, "_rate_timer"):
            self._rate_timer.stop()       # 同停 1Hz 统计采样：避免 accept 后、窗口析构前残余 tick 去 setText 已销毁的标签
        self._ar_stop_script_worker()      # B5：回收常驻脚本子进程
        self._trg_stop_procs()             # 同收触发器外部程序动作的子进程
        # 正常退出已经收完，注销兵底：否则每开一个窗口就累积一个句柄（测试里
        # 会建很多个），那些句柄还会把已销毁的窗口一直拉着不放。
        atexit.unregister(self._trg_stop_procs)
        self._save_settings()
        self.close_conn()
        self._close_log_file()
        if self.port_scanner:
            self.port_scanner.stop()
        self._wait_oneshot_scan()
        if self._tooltip_popup is not None:   # macOS 自绘 tooltip 是独立顶层窗，主动收掉避免退出瞬间残留屏上
            self._tooltip_popup.hide()
            self._tooltip_popup.deleteLater()
            self._tooltip_popup = None
        if self._sel_chk_popup is not None:
            self._sel_chk_popup.hide()
            self._sel_chk_popup.deleteLater()
            self._sel_chk_popup = None
        # 子对话框统一 parent=None（避开 Qt 父子链对主窗 WM_NCHITTEST 的干扰），
        # 主窗关闭时必须显式收掉，否则进程退不干净（独立顶层窗会留着）。
        for attr in ("_ar_dlg", "_multi_send_dlg", "_keyword_dlg", "_plot_dlg", "_frame_dlg",
                     "_mbm_dlg", "_seq_dlg", "_frame_builder_dlg", "_toolbox_dlg", "_xfer_dlg",
                     "_bridge_dlg", "_dash_dlg", "_script_dlg", "_rr_dlg", "_rd_dlg",
                     "_snip_dlg", "_send_hist_dlg", "_cpreset_dlg", "_triggers_dlg", "_device_center_dlg", "_structured_dlg"):
            dlg = getattr(self, attr, None)
            if dlg is not None:
                try:
                    dlg.close(); dlg.deleteLater()
                except Exception:
                    pass
                setattr(self, attr, None)
        if self._tray:
            self._tray.hide()

    def closeEvent(self, e):
        if self._closing_real or not self._tray:
            if not self._confirm_project_switch():
                self._closing_real = False
                e.ignore()
                return
            self._shutdown()
            e.accept()
            return

        dlg = CloseDialog(
            self._t("close_prompt"),
            self._t("close_minimize"),
            self._t("close_quit"),
            self._t("close_cancel"),
            theme_id=self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT,
            parent=None,    # 与其它对话框一致，避免干扰主窗 WM_NCHITTEST
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
            if not self._confirm_project_switch():
                e.ignore()
                return
            self._closing_real = True
            self._shutdown()
            e.accept()
        else:
            e.ignore()
