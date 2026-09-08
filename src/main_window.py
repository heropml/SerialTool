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
import zipfile
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
except ImportError:
    APP_VERSION = "0.0.0"
from ui import app_style
from ui import i18n_ui
from ui.theme import (ROLE_PROP, ROLE_TS, ROLE_RX, ROLE_TX, THEMES, THEME_DEFAULT, _mix,
                   chrome_for, COLOR_TEXT, COLOR_TEXT_SECONDARY, COLOR_BLUE)
from ui.i18n import TR, CHECKSUM_KEYS
from app_icon import get_app_icon
from ui.fonts import ui_font, mono_font, localize_qss
from ui.widgets import (make_label, IOSSwitch, TitleBar, Card, CollapsibleSection,
                     SuffixLineEdit, find_combo_ancestor, should_block_combo_wheel)
from diagnostics import create_diagnostic_bundle

_log = logging.getLogger(__name__)

# 目录枚举是 daemon Python 线程。窗口关闭时若它仍卡在第三方 DLL 中，不能
# 继续让 QObject 挂在窗口父子树上；保留到 worker 自己结束，再延迟销毁。
_RTT_CATALOG_REAPERS = set()


def _reap_rtt_catalog(catalog):
    _RTT_CATALOG_REAPERS.discard(catalog)
    try:
        catalog.deleteLater()
    except RuntimeError:
        pass

# Connect/send/live-log: OS and runtime IO. Do not use bare Exception here —
# unexpected bugs should still surface rather than look like a wire failure.
_TX_IO_ERRORS = (OSError, RuntimeError, TypeError, ValueError)
# RuntimeError: deleted Qt widgets (toPlainText / setPlainText) still toast.
_LOG_IO_ERRORS = (OSError, RuntimeError, ValueError, TypeError)
_CHECKSUM_ERRORS = (TypeError, ValueError, OverflowError)
_RX_SIDE_LABELS = {
    "auto_reply": "ar_title",
    "automation.triggers.feed": "trg_title",
    "automation.xfer.feed": "xfer_title",
    "plot.feed": "plot_title",
    "frame.feed": "frame_title",
    "dashboard.feed": "dash_title",
    "macro.on_rx": "io_task_macro",
    "recorder.on_rx": "rr_title",
    "structured.feed": "structured_title",
    "script.feed": "sc_title",
    "seq.feed": "seq_title",
    "mbm.feed": "mbm_title",
}

# setMaximumBlockCount only caps QTextBlock count. With line/packet split off,
# a newline-free stream stays in one block forever; budget chars as
# max_lines * _RECV_CHARS_PER_LINE.
_RECV_CHARS_PER_LINE = 256
from transport.net_io import (TcpServerConn, TcpClientConn, UdpConn, UdpGroupConn,
                    PROTO_TCP_SERVER, PROTO_TCP_CLIENT, PROTO_UDP, PROTO_UDP_MULTICAST,
                    PROTOCOLS, SEND_NO_TARGET, ERR_CONN_TIMEOUT, ERR_SEND_BACKPRESSURE,
                    local_ipv4_list, is_multicast_ipv4,
                    is_valid_ip, is_local_ipv4, resolve_export_local_ipv4)
from transport.serial_io import SerialConn, PortScannerThread, OneShotPortScanner
from transport import conn_error_tips
from transport.virtual_io import VirtualConn, PROTO_VIRTUAL
from transport.ble_io import BleConn, BleScanner, ERROR_I18N as _BLE_ERROR_I18N
from transport import rtt_io as rtt_io_mod
from transport.rtt_io import (
    RttConn, RttCatalog,
    ERROR_I18N as _RTT_ERROR_I18N, NOTICE_I18N as _RTT_NOTICE_I18N,
)
from sessions.session_host import SessionHostMixin, _install_session_proxies
from automation import send_dsl
from protocol import ansi
from protocol import binproto
from automation import triggers
from protocol import convert
from automation import snippets
from project import connection_presets
from project.config_keys import CFG_KEYS as _CFG_KEYS_MOD
from project.config_io import (
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
    clamp_group_idx as _cfg_clamp_group_idx,
    normalize_mbm_variant as _cfg_normalize_mbm_variant,
    mbm_import_enabled as _cfg_mbm_import_enabled,
    ar_mbm_mutex_disable_ar as _cfg_ar_mbm_mutex_disable_ar,
    resolve_settings_file as _cfg_resolve_settings_file,
)
from automation.send_history import (
    push as _hist_push,
    load_list as _hist_load_list,
    dumps as _hist_dumps,
    remove_at as _hist_remove_at,
    nav_idx_after_remove as _hist_nav_after_remove,
)
from automation.multi_send import (
    load_groups as _ms_load_groups,
    active_items as _ms_active_items_fn,
    build_cycle_seq as _ms_build_cycle_seq,
    groups_json as _ms_groups_json,
)
from project.connection_presets import parse_port as _conn_parse_port
from project.connection_presets import parse_baud as _conn_parse_baud
from project.connection_presets import validate_open as _conn_validate_open
from project.connection_presets import open_fields_from_ui as _conn_open_fields_from_ui
from project.connection_presets import open_fields_from_reconnect as _conn_open_fields_from_reconnect
from project.connection_presets import serial_extras_from_reconnect as _conn_serial_extras
from project.connection_presets import (
    serial_signature as _conn_serial_sig,
    tcp_client_signature as _conn_tcp_sig,
    ble_signature as _conn_ble_sig,
    rtt_signature as _conn_rtt_sig,
    proto_only_signature as _conn_proto_sig,
)
from automation import seq_context
from automation import sequence_dataset
from transport import io_stats
from transport.io_stats import (
    fmt_bytes as _io_fmt_bytes,
    fmt_rate as _io_fmt_rate,
    format_stat_bar as _io_format_stat_bar,
)
from record import log_naming
from modbus import modbus_slave
from modbus import modbus_master
from ui.dialogs import (CloseDialog, MultiSendDialog, KeywordHighlightDialog,
                     AboutDialog, InfoDialog, _set_win_titlebar_dark,
                     _style_one_combo_popup)
from updater import UpdateChecker
from ui.ui_tips import set_tooltip

# 串口作为统一连接层的一种「类型」，排在网络协议之前一起进 cb_proto 下拉。
# 不放进 net_io.PROTOCOLS 是为保持 net_io 纯网络语义；这里组合成完整下拉列表。
# 虚拟连接排最后：它不接硬件，作为一种类型接入后，自动应答 / Modbus / 序列 / 脚本 /
# 波形图 等全部机制都能在离线下直接跑，无需各自改造。
from ui.conn_ui import (
    PROTO_SERIAL,
    PROTO_BLE,
    PROTO_RTT,
    visible_conn_types,
    field_visibility as _conn_field_vis,
)

from ui import send_options_card as _send_options_card
from ui import data_options_card as _data_options_card
from ui import settings_card as _settings_card
from ui import receive_card as _receive_card
from ui import send_card as _send_card
from ui import sidebar as _sidebar
from ui import workspace_ui as _workspace_ui
# Sequence engine limits (S-2: owned by sequence_engine; re-exported for callers).
from automation.sequence_engine import (
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
    feed_action as _seq_engine_feed_action,
    mbm_release_plan as _seq_engine_mbm_release_plan,
    fail_outcome as _seq_engine_fail_outcome,
)


from modbus.modbus_timing import (
    serial_char_bits as _mbm_timing_char_bits,
    rtu_silent_ms as _mbm_timing_silent_ms,
    rtu_tx_guard_ms as _mbm_timing_tx_guard_ms,
    response_len_budget as _mbm_timing_resp_len,
    timeout_ms as _mbm_timing_timeout_ms,
    span_bad as _mbm_timing_span_bad,
)

from transport import reconnect_policy as _reconnect_policy
from automation import auto_reply_gate as _ar_gate
from sessions import rx_dispatch as _rx_dispatch
from protocol import term_vt as _term_vt
from modbus import modbus_feed as _mbm_feed_plan
from modbus.modbus_poll_plan import (
    poll_reject_reason as _mbm_poll_reject_reason,
    build_poll_arg as _mbm_build_poll_arg,
    validate_response as _mbm_validate_response,
)
from modbus.modbus_scheduler import (
    pick_next_due as _mbm_sched_pick_next,
    schedule_delay_ms as _mbm_sched_delay_ms,
    next_due_after as _mbm_sched_next_due,
)

from protocol.view_format import (
    bytes_to_hex as _view_bytes_to_hex,
    format_hexdump as _view_format_hexdump,
    with_leading_newline as _view_leading_nl,
    timestamp_prefix as _view_timestamp_prefix,
    view_mode_of_state as _view_mode_of_state,
    view_extra_index as _view_extra_index,
    recv_view_prop as _view_recv_prop,
    force_block_prefix_plan as _view_force_prefix,
    log_block_pieces as _view_log_pieces,
    offsets_after_trim as _view_offsets_after_trim,
)

from protocol.rx_text import (
    decode_auto_chunk as _rx_decode_auto_chunk,
    split_lines_with_offsets as _rx_split_lines,
    ansi_flatten as _rx_ansi_flatten,
    ansi_shift as _rx_ansi_shift,
    ansi_slice as _rx_ansi_slice,
)

from automation.trigger_safe import (
    is_private_url as _trg_is_private_url,
    shell_value as _trg_shell_quote,
)
from automation.event_bus import EventBus, TOPIC_TRIGGER_HIT
from automation.trigger_actions import (
    TriggerActionRunner,
    kill_proc as _trg_kill_proc_impl,
)

from protocol.keyword_groups import (
    load_groups as _kw_load_groups,
    active_rules as _kw_active_rules,
    save_fields as _kw_save_fields,
    normalize_match as _kw_normalize_match,
    rule_spans as _kw_rule_spans,
    rule_matches as _kw_rule_matches,
)
from project.project_templates import (
    workspace_tool_entries as _ws_tool_entries,
    workspace_template_options as _ws_template_options,
)

from ui.ui_options import (
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

from transport.serial_params import (
    resolve_pyserial as _resolve_serial_params,
)


from automation.auto_reply_core import (
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
    parse_tx_hex as _ar_core_parse_tx_hex,
    append_tx_newline as _ar_core_append_tx_newline,
    send_preflight as _ar_core_send_preflight,
    classify_send_result as _ar_core_classify_send,
    tx_display_mode as _ar_core_tx_display_mode,
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
            except SystemExit as e:
                # User scripts may call sys.exit(); report it like any other
                # script error instead of silently killing the reusable worker.
                conn.send(("err", "%s: %s" % (type(e).__name__, e)))
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
class CommTool(SessionHostMixin, QMainWindow):
    RESIZE_MARGIN = 6
    _AR_SCRIPT_TIMEOUT = 1.0   # B5：脚本执行超时(秒)，超时即放弃本次、防死循环/阻塞冻结 GUI
    _TRG_MAX_ACTIONS = 8       # in-flight webhook / run_cmd workers
    _TRG_CMD_TIMEOUT = 30.0    # 单个外部程序动作的最长存活时间
    _TRG_STOP_WAIT = 2.0       # 等在途启动收尾的上限
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
        # 全平台装 app 级过滤器：主界面 QComboBox 禁滚轮误触；Linux 缩放 / macOS tooltip 复用同一入口。
        QApplication.instance().installEventFilter(self)
        self._app_filter_installed = True

        # Multi-session host must exist before proxy attribute assigns.
        self._init_session_host()

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

        self._send_timer_fallback = QTimer(self)
        # Period TX uses per-session _period_timer (send_timer property).

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
        self._stream_frame = self._load_stream_frame()  # 分析层协议帧模式（独立于自动应答；默认关）
        self._ar_fault = self._load_ar_fault()       # C6 全局故障注入配置（丢包/错CRC/错长度，压测主机）
        self._ar_sm = self._load_ar_sm()             # C8 多步状态机配置（全局；on/init）
        self._ar_state = self._ar_sm.get("init", "")  # 当前状态(运行态，不持久化)；连接/重置时回到 init
        self._ar_generation = 0   # C8：会话代际。reset_state 时 +1，作废在途的延迟应答 singleShot
        self._ar_sm_pending = None  # C8：在途状态转移 token；整条多段应答完成前串行化后续状态帧
        self._ar_sm_queue = deque() # C8：pending 期间收到的完整帧 FIFO（有界，保持收帧顺序）
        self._ar_sm_draining = False # C8：FIFO 同步排空重入保护
        self._ar_modbus = self._load_ar_modbus()     # B4 Modbus 从机配置（窗口共享；运行态 bank 每会话一份）
        self._modbus_rebuild_all_sessions()
        self._modbus_buffers = {}                    # TCP Server 每客户端独立半包，防止并发连接串流
        # Modbus 主机轮询（master/poll）：规则 + 总开关 + 变体；运行态半双工调度
        self._mbm_rules = self._load_mbm_rules()
        self._mbm_views = self._load_mbm_views()
        self._mbm_on = self.settings.value("modbus_master_on", False, type=bool)
        if _cfg_ar_mbm_mutex_disable_ar(self._ar_on, self._mbm_on):
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
        # 自动化测试序列：规则(步骤列表)在窗口；运行态在 Session（双标签可各跑一套）。
        self._seq_rules = self._load_seq_rules()
        self._seq_dlg = None
        self._frame_builder_dlg = None   # 帧构造器对话框（单实例）
        self._toolbox_dlg = None         # 工具箱对话框（进制转换 + 校验计算，单实例）
        self._xfer_dlg = None            # 文件传输对话框（协议收发 / 原始字节流，单实例）
        self._xfer_worker = None         # 传输后台线程；非 None 且运行中时 on_data_received 接管收流
        self._xfer_send_bridge = None    # 只断开主窗自己挂上的桥，不误删 worker 的其它订阅者
        self._xfer_orphans = []          # 极端底层阻塞时续命，避免运行中的 QThread 被析构
        self._xfer_conn = None           # 传输启动时的连接；断线重连后旧 worker 不得碰新连接
        self._xfer_target = None         # 传输起始时捕获的发送目标（网络多端用；串口 None）
        self._bridge_dlg = None          # 桥接转发对话框（两端任意 串口/TCP/UDP 组合，单实例）
        self._dash_dlg = None            # 数值仪表盘对话框（大字号实时值 + 阈值告警，单实例）
        self._script_dlg = None          # 脚本控制台对话框（Python 驱动收发，单实例）
        self._script_orphans = []        # 停不下来的脚本 worker（纯计算死循环）：留引用防 QThread running 时被析构
        # 引擎占用均为 per-session：transfer/replay/script/MBM/recording/macro/DSL/scan
        # 都在各标签独立运行；_io_owner_sid 只在需要定位 owner 的兜底路径使用。
        self._io_owner_sid = {
            "script": None, "sequence": None, "transfer": None, "macro": None,
            "modbus": None, "replay": None, "dsl": None, "recording": None,
            "device_scan": None,
        }
        from project.device_resources import StructuredRecorder
        self._structured_recorder = StructuredRecorder()
        self._structured_dlg = None
        self._replay_on = False            # 回放进行中（占用收发流，计入 _io_task_busy）
        self._replay_drive_tx = False      # 驱动真实 TX：额外压制 Modbus 主机 / 自动应答发送
        self._rr_dlg = None                # 录制/回放对话框（单实例）
        self._rd_dlg = None                # 会话比较对话框（单实例，纯离线不碰连接）
        self._snip_dlg = None              # 发送模板库对话框（单实例）
        self._send_hist_dlg = None         # 发送历史搜索选择器（单实例）
        self._cpreset_dlg = None
        self._ble_scan_dlg = None
        self._ar_in_flight = False       # 正在发自动应答的回复 → 宏录制跳过（不是用户手动发）
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
        # 触发器只产事件；webhook / run_cmd 走总线消费端（并发上限与杀进程都在 runner）。
        self._event_bus = EventBus()
        self._trg_actions = TriggerActionRunner(host=self)
        self._event_bus.subscribe(TOPIC_TRIGGER_HIT, self._trg_actions.on_trigger_hit)
        # closeEvent 跑不到的路径（未捕获异常、sys.exit、脚本里直接退）也要把
        # 子进程收掉，否则 POSIX 上成孤儿、Windows 上同样残留。_trg_stop_procs
        # 只碰纯 Python 属性与 subprocess，不碰 Qt，在解释器退出阶段跑是安全的。
        atexit.register(self._trg_stop_procs)
        self._trg_dec_buf = {}      # 触发引擎的增量解码状态，按会话/方向/来源流隔离
        self._trg_dec = {}
        self._trg_dec_codec = {}    # stream_key → codec；两会话编码可以不同
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
        # Per-session via proxy: each tab has its own serial target and attempt budget.
        self._serial_reconnect_cfg = None        # 掉线前的串口签名；重连只允许回到这个设备/参数
        self._serial_reconnect_limit = _reconnect_policy.SERIAL_RECONNECT_LIMIT        # 串口退避 0.5s 递增到 5s，第 10 次后停止
        # 自动重连：串口 0.5s 线性递增到 5s；网络指数退避（上限 30s）。主动关闭/退出时跳过。
        self._user_closing = False
        self._reconnect_attempts = 0
        # Fallback only; SessionHost proxies _reconnect_timer to context session.
        self._reconnect_timer_fallback = QTimer(self)
        self._reconnect_timer_fallback.setSingleShot(True)
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
        self._refresh_session_tab_styles()
        _workspace_ui.refresh_top_bar_icons(self)
        self._capture_field_defaults()   # 记录字段构建默认值（在 _load_settings 覆盖前）供切换配置复位用
        self._theme_apply_timer = QTimer(self)
        self._theme_apply_timer.setSingleShot(True)
        self._theme_apply_timer.timeout.connect(self._on_theme_changed)
        self._load_settings()
        self._restore_sessions_settings()
        self._io_reconcile_session_owners()
        if getattr(self, "_mbm_on", False):
            self._io_bind_owner("modbus")
        self._autosave_suppress = 0
        self._autosave_resume_pending = False
        self._autosave_ready = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(1500)
        self._autosave_timer.timeout.connect(self._flush_workspace_autosave)
        self._wire_workspace_autosave()
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
        self._restore_project_timer = QTimer(self)
        self._restore_project_timer.setSingleShot(True)
        self._restore_project_timer.timeout.connect(self._restore_last_project)
        self._restore_project_timer.start(0)

    def _t(self, key, **kwargs) -> str:
        s = self._L.get(key, key)
        try:
            return s.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return s

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
                "port", "baud_rate", "data_bits", "parity", "stop_bits",
                # 每种连接类型的字段标签都要算进来，否则新标签一长就被
                # setFixedWidth 裁掉半个字（RTT 的「速率 (kHz)」「连接时复位」
                # 就这么被裁过）。文案本身仍应尽量短，说明放 tooltip。
                "vconn_loopback", "ble_profile", "ble_write_mode",
                "rtt_device", "rtt_probe", "rtt_interface", "rtt_speed",
                "rtt_address", "rtt_channel", "rtt_reset")
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
        self._update_start_timer = QTimer(self)
        self._update_start_timer.setSingleShot(True)
        self._update_start_timer.timeout.connect(self._auto_update_check)
        if self.settings.value("auto_update_check", True, type=bool):
            self._update_timer.start()
            # Window-owned so close/deleteLater cancels it. A static
            # QTimer.singleShot would retain a dead bound method for 5s and
            # could start an updater after the window had been destroyed.
            self._update_start_timer.start(5000)

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
        ble_on = vis.get("ble_rows", False)
        for row in (
                getattr(self, "row_ble_scan", None),
                getattr(self, "row_ble_name", None),
                getattr(self, "row_ble_address", None),
                getattr(self, "row_ble_profile", None),
                getattr(self, "row_ble_service", None),
                getattr(self, "row_ble_write", None),
                getattr(self, "row_ble_notify", None),
                getattr(self, "row_ble_write_mode", None)):
            if row is not None:
                row.setVisible(ble_on)
        if (not ble_on) and getattr(self, "_ble_scanner", None) is not None:
            self._stop_ble_scan("leave")
        rtt_on = vis.get("rtt_rows", False)
        for row in (
                getattr(self, "row_rtt_device", None),
                getattr(self, "row_rtt_probe", None),
                getattr(self, "row_rtt_interface", None),
                getattr(self, "row_rtt_speed", None),
                getattr(self, "row_rtt_address", None),
                getattr(self, "row_rtt_channel", None),
                getattr(self, "row_rtt_reset", None)):
            if row is not None:
                row.setVisible(rtt_on)
        if rtt_on:
            self._ensure_rtt_catalog()
        self.btn_open.setText(self._t(vis["open_btn_key"]))

    # ---- RTT：器件表 / 调试器发现 ----

    def _rtt_speed_text(self):
        """速率下拉 -> 纯数字文本（下拉项显示带 kHz，存盘/签名不带）。"""
        cb = getattr(self, "cb_rtt_speed", None)
        if cb is None:
            return ""
        from transport import rtt_io
        return rtt_io.strip_speed_unit(cb.currentText())

    def _set_rtt_speed_text(self, value):
        cb = getattr(self, "cb_rtt_speed", None)
        if cb is None:
            return
        from transport import rtt_io
        text = rtt_io.strip_speed_unit(value)
        cb.blockSignals(True)
        try:
            idx = cb.findText(rtt_io.format_speed(int(text)))
        except (TypeError, ValueError):
            idx = -1
        if idx >= 0:
            cb.setCurrentIndex(idx)      # 命中档位就选中它
        else:
            cb.setCurrentText(text)      # 手填的非档位值原样留着
        cb.blockSignals(False)

    def _rtt_probe_text(self):
        """调试器下拉 -> 序列号字符串（第 0 项「自动」= 空串）。"""
        cb = getattr(self, "cb_rtt_probe", None)
        if cb is None:
            return ""
        if cb.currentIndex() == 0 and cb.currentText() == self._t("rtt_probe_auto"):
            return ""
        from transport import rtt_io
        return rtt_io.normalize_probe(cb.currentText())

    def _set_rtt_probe_text(self, value):
        cb = getattr(self, "cb_rtt_probe", None)
        if cb is None:
            return
        from transport import rtt_io
        sn = rtt_io.normalize_probe(value)
        cb.blockSignals(True)
        if not sn:
            cb.setCurrentIndex(0)
        else:
            idx = cb.findText(sn)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            else:
                cb.setCurrentText(sn)
        cb.blockSignals(False)

    def _ensure_rtt_catalog(self):
        """首次进 RTT 页时后台取一次器件表 + 已插调试器。

        枚举走 JLinkARM DLL（数千项，几百 ms 到数秒），必须离开 UI 线程；
        没装驱动时线程内部退回内置候选，界面照常可用。
        """
        if getattr(self, "_rtt_catalog_thread", None) is not None:
            return
        if getattr(self, "_rtt_catalog_done", False):
            return
        if not hasattr(self, "cb_rtt_device"):
            return
        th = RttCatalog()
        th.ready.connect(self._on_rtt_catalog)
        th.finished.connect(self._on_rtt_catalog_finished)
        self._rtt_catalog_thread = th
        th.start()

    def _on_rtt_catalog(self, devices, probes):
        self._rtt_catalog_done = True
        self._rtt_devices = list(devices or [])
        cb = getattr(self, "cb_rtt_device", None)
        th = getattr(self, "_rtt_catalog_thread", None)
        self._rtt_driver_path = getattr(th, "driver_path", "") if th else ""
        dlg = getattr(self, "_rtt_dev_dlg", None)
        if dlg is not None:
            dlg.set_devices(self._rtt_devices)
            dlg.set_driver(self._rtt_driver_path)
            dlg.select_device(cb.currentText() if cb is not None else "")
        pcb = getattr(self, "cb_rtt_probe", None)
        if pcb is not None:
            keep = self._rtt_probe_text()
            pcb.blockSignals(True)
            while pcb.count() > 1:
                pcb.removeItem(1)
            for sn in probes:
                pcb.addItem(str(sn), str(sn))
            pcb.blockSignals(False)
            self._set_rtt_probe_text(keep)

    def _on_rtt_catalog_finished(self):
        current = getattr(self, "_rtt_catalog_thread", None)
        th = self.sender() or current
        if th is current:
            self._rtt_catalog_thread = None
        if th is not None:
            th.deleteLater()

    def _stop_rtt_catalog(self):
        th = getattr(self, "_rtt_catalog_thread", None)
        if th is None:
            return
        try:
            th.ready.disconnect()
            th.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        stopped = True
        if th.isRunning():
            # DLL 枚举不可中断，只能短暂等它自己跑完。
            stopped = bool(th.wait(5000))
        if not stopped:
            # 仍在 DLL 内：脱离窗口所有权，daemon worker 结束后自行销毁。
            _RTT_CATALOG_REAPERS.add(th)
            th.finished.connect(lambda _th=th: _reap_rtt_catalog(_th))
            self._rtt_catalog_thread = None
            return
        self._rtt_catalog_thread = None
        th.deleteLater()

    def _rtt_device_dialog(self):
        dlg = getattr(self, "_rtt_dev_dlg", None)
        if dlg is None:
            from ui.rtt_device_dialog import RttDeviceDialog
            dlg = RttDeviceDialog(self)
            self._rtt_dev_dlg = dlg
        return dlg

    def _on_rtt_device_pick(self):
        """「…」：在驱动的完整器件表里搜着选（下拉塞不下上万项）。"""
        self._ensure_rtt_catalog()
        dlg = self._rtt_device_dialog()
        dlg.set_devices(getattr(self, "_rtt_devices", None) or [])
        dlg.set_driver(getattr(self, "_rtt_driver_path", ""))
        dlg.retranslate()
        dlg.refresh_theme()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if hasattr(self, "cb_rtt_device"):
            dlg.select_device(self.cb_rtt_device.currentText())

    def _apply_rtt_device(self, name):
        cb = getattr(self, "cb_rtt_device", None)
        if cb is None or not name:
            return
        if self.conn is not None:
            # 连接期间其它连接字段都被禁用了，弹窗是独立顶层窗禁不到
            self.toast(self._t("rtt_dev_need_close"), error=True)
            return
        cb.setCurrentText(str(name))
        self.settings.setValue("rtt_device", str(name))

    def _reload_rtt_catalog(self, dll_hint=None):
        """换 J-Link 驱动目录后重新枚举（pylink 自己只会扫 C 盘）。"""
        if dll_hint is not None:
            hint = str(dll_hint or "").strip()
            # 目录里确实有 DLL 才落地：选错了不能把原来能用的配置顶掉，
            # 也不能被全盘兜底搜到的另一份驱动掩盖成「看起来成功了」。
            if hint and not rtt_io_mod.dll_in_directory(hint):
                self.toast(self._t("rtt_dev_driver_bad"), error=True)
                return
            rtt_io_mod.set_dll_hint(hint)
            self.settings.setValue("rtt_dll_path", hint)
        previous = getattr(self, "_rtt_catalog_thread", None)
        if previous is not None:
            # 用户可能在首次枚举尚未完成时换驱动。旧结果必须丢弃；新 worker
            # 会在 DLL 互斥锁后排队，旧 worker 结束后自动回收。
            try:
                previous.ready.disconnect()
                previous.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            if previous.isRunning():
                _RTT_CATALOG_REAPERS.add(previous)
                previous.finished.connect(
                    lambda _th=previous: _reap_rtt_catalog(_th))
            else:
                previous.deleteLater()
            self._rtt_catalog_thread = None
        rtt_io_mod.clear_device_cache()
        self._rtt_catalog_done = False
        self._rtt_devices = []
        self._rtt_driver_path = ""
        self._ensure_rtt_catalog()

    def _route_session_notice(self, session_id, msg):
        """连接层的非致命提示（如 RTT 控制块还没出现）：只 toast，不断连。"""
        session = self.find_session(session_id)
        if session is None or session.id != self._active_session_id:
            return
        key = _RTT_NOTICE_I18N.get(msg)
        self.toast(self._t(key) if key else str(msg))

    def _route_session_rtt_ready(self, session_id, source_conn):
        """控制块首次命中后，把活动 RTT 会话从“等待”刷新为“已连接”。"""
        session = self.find_session(session_id)
        if (session is None or session.conn is not source_conn
                or session.id != self._active_session_id):
            return
        self._update_conn_status()

    def _ensure_ble_scanner(self):
        scanner = getattr(self, "_ble_scanner", None)
        if scanner is not None:
            return scanner
        scanner = BleScanner(self)
        scanner.device_found.connect(self._on_ble_device_found)
        scanner.scan_finished.connect(self._on_ble_scan_finished)
        scanner.scan_error.connect(self._on_ble_scan_error)
        self._ble_scanner = scanner
        return scanner

    def _ble_scan_dialog(self):
        dlg = getattr(self, "_ble_scan_dlg", None)
        if dlg is None:
            from ui.ble_scan_dialog import BleScanDialog
            dlg = BleScanDialog(self)
            self._ble_scan_dlg = dlg
        return dlg

    def _sync_ble_scan_buttons(self):
        scanning = bool(
            getattr(getattr(self, "_ble_scanner", None), "is_scanning", False))
        dlg = getattr(self, "_ble_scan_dlg", None)
        if dlg is not None:
            dlg.set_scanning(scanning)
        btn = getattr(self, "btn_ble_scan", None)
        if btn is not None:
            btn.setEnabled((not scanning) and self.conn is None)

    def _hide_ble_scan_dialog(self):
        dlg = getattr(self, "_ble_scan_dlg", None)
        if dlg is not None and dlg.isVisible():
            dlg.hide()

    def _stop_ble_scan(self, reason=None):
        scanner = getattr(self, "_ble_scanner", None)
        was = bool(scanner is not None and scanner.is_scanning)
        if scanner is not None and scanner.is_scanning:
            scanner.stop()
        self._sync_ble_scan_buttons()
        if reason == "leave":
            self._hide_ble_scan_dialog()
        if was and reason == "user":
            self.toast(self._t("ble_scan_stopped"))
        elif was and reason == "leave":
            self.toast(self._t("ble_scan_left_page"))

    def _start_ble_scan(self):
        if self.conn is not None:
            return False
        scanner = self._ensure_ble_scanner()
        if scanner.is_scanning:
            self._sync_ble_scan_buttons()
            return True
        dlg = self._ble_scan_dialog()
        dlg.clear_devices()
        if not scanner.start():
            self._sync_ble_scan_buttons()
            return False
        self._sync_ble_scan_buttons()
        return True

    def _on_ble_scan_clicked(self):
        if self.conn is not None:
            return
        dlg = self._ble_scan_dialog()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self._start_ble_scan()

    def _on_ble_scan_error(self, token):
        self._sync_ble_scan_buttons()
        key = _BLE_ERROR_I18N.get(token, "ble_err_bt_off")
        self.toast(self._t(key), error=True)

    def _on_ble_scan_finished(self):
        self._sync_ble_scan_buttons()

    def _on_ble_device_found(self, address, name, rssi, uuids, adv=None):
        dlg = getattr(self, "_ble_scan_dlg", None)
        if dlg is not None:
            dlg.upsert(address, name, rssi, uuids, adv)

    def _apply_ble_device(self, address, name):
        if hasattr(self, "ed_ble_address"):
            self.ed_ble_address.setText(address or "")
        if hasattr(self, "ed_ble_name"):
            self.ed_ble_name.setText(name or "")

    def _on_ble_profile_changed(self, *_a):
        from transport import ble_uuid
        pid = self.cb_ble_profile.currentData() if hasattr(self, "cb_ble_profile") else ""
        if ble_uuid.normalize_profile(pid) == ble_uuid.PROFILE_CUSTOM:
            return
        filled = ble_uuid.apply_preset(pid)
        self.ed_ble_service.setText(ble_uuid.short_uuid(filled["service_uuid"]))
        self.ed_ble_write.setText(ble_uuid.short_uuid(filled["write_uuid"]))
        self.ed_ble_notify.setText(ble_uuid.short_uuid(filled["notify_uuid"]))

    def _on_ble_swap_clicked(self):
        from transport import ble_uuid
        w, n = ble_uuid.swap_write_notify(
            self.ed_ble_write.text(), self.ed_ble_notify.text())
        self.ed_ble_write.setText(w)
        self.ed_ble_notify.setText(n)
        idx = self.cb_ble_profile.findData(ble_uuid.PROFILE_CUSTOM)
        if idx >= 0:
            self.cb_ble_profile.blockSignals(True)
            self.cb_ble_profile.setCurrentIndex(idx)
            self.cb_ble_profile.blockSignals(False)

    def build_data_options_card(self):
        return _data_options_card.build(self)

    def build_send_options_card(self):
        return _send_options_card.build(self)

    def build_receive_card(self):
        return _receive_card.build(self)

    _CTX_CONVERT_MAX = 64 * 1024

    def _recv_context_menu(self, global_pos):
        """数据区右键菜单：复制 / 转换 / 全选 / 清空 / 保存，文字跟随程序语言。"""
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
        act_to_text = menu.addAction(self._t("ctx_to_text"))
        act_to_text.setEnabled(has_sel)
        act_to_hex = menu.addAction(self._t("ctx_to_hex"))
        act_to_hex.setEnabled(has_sel)
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
        elif chosen is act_to_text:
            self._ctx_convert_selection(to_hex=False)
        elif chosen is act_to_hex:
            self._ctx_convert_selection(to_hex=True)
        elif chosen is act_all:
            self.txt_recv.selectAll()
        elif chosen is act_clear:
            self.clear_recv()
        elif chosen is act_save:
            self.save_recv()

    def _ctx_convert_selection(self, to_hex):
        """选区 → 文本或 HEX，结果写入剪贴板（不改写数据区历史）。"""
        cur = self.txt_recv.textCursor()
        if not cur.hasSelection():
            return
        raw = cur.selectedText()
        # 文本→HEX 会走整段 encode：先按字符数卡上限，避免 Ctrl+A 巨选区卡 GUI。
        raw_norm = convert.normalize_qtext_selection(raw)
        if len(raw_norm) > self._CTX_CONVERT_MAX:
            self.toast(self._t("sel_chk_too_big",
                               n=self._CTX_CONVERT_MAX // 1024), error=True)
            return
        extracted = self._selected_hex_bytes(cur, limit=self._CTX_CONVERT_MAX)
        if extracted is not None and len(extracted) > self._CTX_CONVERT_MAX:
            self.toast(self._t("sel_chk_too_big",
                               n=self._CTX_CONVERT_MAX // 1024), error=True)
            return
        try:
            if to_hex:
                data = convert.selection_bytes_for_hex_convert(
                    extracted, raw, encoding=self._send_codec())
                kind = self._t("ctx_to_hex")
            else:
                data = convert.selection_bytes_for_text_convert(extracted, raw)
                kind = self._t("ctx_to_text")
            if not data:
                self.toast(self._t("ctx_convert_empty"), error=True)
                return
            # 两路统一：编码/提取后的字节数也不得超过上限（再生成 HEX 文本会再膨胀）。
            if len(data) > self._CTX_CONVERT_MAX:
                self.toast(self._t("sel_chk_too_big",
                                   n=self._CTX_CONVERT_MAX // 1024), error=True)
                return
            out = (convert.bytes_to_hex(data) if to_hex
                   else convert.bytes_to_text(data, self._send_codec()))
        except (ValueError, UnicodeError) as e:
            self.toast(self._t("ctx_convert_fail", e=e), error=True)
            return
        QApplication.clipboard().setText(out)
        # 弹窗展示完整转换结果，同时已写入剪贴板，方便接着粘贴/核对。
        self._info_dlg(kind, out)
        self.toast(self._t("ctx_convert_copied", kind=kind))

    # ----- 数据区：滚动锁定 + 单击行高亮 -----
    def eventFilter(self, obj, event):
        # 这是装在 QApplication 上的全局过滤器：窗口销毁之后（deleteLater 已跑、Python 侧属性
        # 已清）Qt 仍可能回调进来，此时在「半个对象」上跑逻辑会直接 AttributeError 崩掉。
        # _mac_tooltip 是 __init__ 里最早设的那批之一（且早于 installEventFilter），
        # 用它当「实例是否可用」的哨兵：没有就直接放行，别处理。
        if not hasattr(self, "_mac_tooltip"):
            return False
        # 主界面下拉框：未展开时吞滚轮，防止侧栏/发送区悬停滚动误改波特率等。
        if event.type() == QEvent.Wheel:
            combo = find_combo_ancestor(obj)
            if (combo is not None and self.isAncestorOf(combo)
                    and should_block_combo_wheel(combo)):
                return True
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
        if obj is getattr(self, "txt_send", None) and event.type() in (
                QEvent.KeyPress, QEvent.ShortcutOverride):
            key = event.key()
            if (key in (Qt.Key_Return, Qt.Key_Enter)
                    and (event.modifiers() & Qt.ControlModifier)):
                # Ctrl+Enter（macOS 上 Qt 把 ⌘ 映射为 ControlModifier）发送；
                # 裸 Enter 仍交给 QTextEdit 换行。终端模式已在上面整键拦截。
                # ShortcutOverride 先认领，避免 QTextEdit 再插入换行；长按 auto-repeat 不连发。
                if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
                    # 先提交 IME 组合：中文/日文输入法下 Ctrl+Enter 通常不提交组合，
                    # 组词未上屏就发送会漏掉正在输入的内容。
                    self._commit_ime_composition()
                    self.do_send()
                return True
            if event.type() == QEvent.KeyPress:
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

        # SessionHostMixin 把 txt_recv 实现为属性：即使接收视图尚未创建（或当前
        # session 正在销毁），hasattr(self, "txt_recv") 仍会为真，但取值是 None。
        # macOS 的应用级 event filter 在 __init__ 期间就会收到事件，此时不能访问
        # None.viewport()；PyQt 回调里的未处理异常会升级为 Qt qFatal 并终止进程。
        recv_view = self.txt_recv
        if recv_view is not None:
            # 接收区尺寸变化 → 重定位浮动「回到底部」按钮 + 查找栏
            if obj is recv_view and event.type() == QEvent.Resize:
                self._reposition_to_bottom_btn()
                if hasattr(self, "_search_bar"):
                    self._reposition_search_bar()
            # Ctrl+F 打开查找栏 / Esc 关闭（查找栏可见时）
            elif obj is recv_view and event.type() == QEvent.KeyPress:
                if (event.key() == Qt.Key_F
                        and event.modifiers() & Qt.ControlModifier):
                    self._open_search()
                    return True
                if (event.key() == Qt.Key_Escape and hasattr(self, "_search_bar")
                        and self._search_bar.isVisible()):
                    self._close_search()
                    return True
            elif obj is recv_view.viewport():
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
        # 词/模式/大小写变化：清掉旧 query key，下一个 refresh 从第一页重建
        # （避免被「query 未变」分支当成文档增量、只刷新当前页）。
        self._search_page_key = None
        self._refresh_extra_selections()   # 搜索段会收集匹配、clamp idx、刷新计数
        if not self._search_term:
            self._search_matches = []
            self._search_match_capped = False
            self._update_search_count()
        if self._search_matches:
            self._goto_match(self._search_idx)

    def _schedule_search_debounce(self):
        """打字防抖：停止敲击 ~150ms 后真正执行全量搜索，避免大缓冲区下每键一次全文扫描。"""
        if getattr(self, "_search_debounce", None) is None:
            return
        self._search_debounce.start()

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
            page = max(0, len(getattr(self, "_search_page_starts", [0])) - 1)
            base = page * self._KW_MAX_SELECTIONS
            suffix = "+" if getattr(self, "_search_match_capped", False) else ""
            self.lbl_search_cnt.setText(
                f"{base + self._search_idx + 1}/{base + len(self._search_matches)}{suffix}")
        elif self._search_term:
            self.lbl_search_cnt.setText(self._t("search_no_match"))
        else:
            self.lbl_search_cnt.setText("")
        # 计数文本变化会改变查找栏所需宽度，重新自适应 + 定位，避免子控件被压缩重叠
        if hasattr(self, "_search_bar"):
            self._reposition_search_bar()

    def _search_find_kwargs(self):
        return dict(
            mode=getattr(self, "_search_mode", "plain"),
            case_sensitive=getattr(self, "_search_case", False),
            hexdump=getattr(self, "_hexdump_on", False),
        )

    def _search_page_key_tuple(self):
        """搜索 query 键：词/模式/大小写/hexdump。文档 revision 另见 ``_search_page_rev``。"""
        kw = self._search_find_kwargs()
        return (self._search_term, kw["mode"], kw["case_sensitive"], kw["hexdump"])

    def _reload_search_page(self, reset=False):
        """Rebuild the current search page from the live document.

        ``reset=True`` (query changed, or head truncation) starts at page 0.
        Otherwise keep the current page start so ▼ pagination is not yanked
        back while new hits arrive at the end.
        """
        if reset:
            self._search_page_starts = [0]
            self._search_scan_end = 0
            start = 0
        else:
            starts = getattr(self, "_search_page_starts", None) or [0]
            start = int(starts[-1] if starts else 0)
            chars = max(0, self.txt_recv.document().characterCount() - 1)
            if start >= chars:
                self._search_page_starts = [0]
                self._search_scan_end = 0
                start = 0
        self._load_search_page(start)

    def _load_search_page(self, start=0):
        """Load one page of matches from codepoint ``start`` (lazy pagination)."""
        from protocol import search_helper
        doc = self.txt_recv.document()
        doc_text = doc.toPlainText()
        page = self._KW_MAX_SELECTIONS
        spans = search_helper.find_spans(
            doc_text, self._search_term,
            limit=page + 1, start=start, **self._search_find_kwargs())
        capped = len(spans) > page
        spans = spans[:page]
        return self._set_search_page(doc_text, spans, capped, start)

    def _set_search_page(self, doc_text, spans, capped, start=0):
        """Install codepoint spans as the current QTextCursor search page."""
        from protocol import search_helper
        doc = self.txt_recv.document()
        self._search_page_rev = doc.revision()
        self._search_page_chars = max(0, doc.characterCount() - 1)
        self._search_match_capped = capped
        if spans:
            last_start, last_end = spans[-1]
            # Zero-width regex matches must still advance the next-page scan.
            self._search_scan_end = (
                last_end if last_end > last_start else min(len(doc_text), last_end + 1))
        else:
            self._search_scan_end = int(start or 0)
        spans = search_helper.to_utf16_spans(doc_text, spans)
        self._search_matches = []
        for a, b in spans:
            cur = QTextCursor(doc)
            cur.setPosition(a)
            cur.setPosition(b, QTextCursor.KeepAnchor)
            cur.setKeepPositionOnInsert(True)
            self._search_matches.append(cur)
        return bool(self._search_matches)

    def _extend_search_next_page(self):
        """▼ past the end of a capped page → fetch the next chunk."""
        start = int(getattr(self, "_search_scan_end", 0) or 0)
        pages = list(getattr(self, "_search_page_starts", None) or [0])
        if not self._load_search_page(start):
            self._search_match_capped = False
            return False
        pages.append(start)
        self._search_page_starts = pages
        return True

    def _load_search_prev_page(self):
        """▲ before the first match of page N → reload page N-1."""
        pages = list(getattr(self, "_search_page_starts", None) or [0])
        if len(pages) <= 1:
            return False
        pages.pop()
        start = pages[-1]
        self._search_page_starts = pages
        return self._load_search_page(start)

    def _load_search_last_page(self):
        """Find the final page in one bounded scan for global ▲ wrap."""
        from protocol import search_helper
        doc_text = self.txt_recv.document().toPlainText()
        spans, starts = search_helper.find_last_page(
            doc_text, self._search_term, page_size=self._KW_MAX_SELECTIONS,
            **self._search_find_kwargs())
        self._search_page_starts = starts
        return self._set_search_page(
            doc_text, spans, False, starts[-1] if starts else 0)

    def _search_next(self):
        if not self._search_matches:
            return
        if self._search_idx + 1 < len(self._search_matches):
            self._search_idx += 1
        elif getattr(self, "_search_match_capped", False):
            if self._extend_search_next_page():
                self._search_idx = 0
            elif len(getattr(self, "_search_page_starts", [0])) > 1:
                # No further hits: wrap to the first global page.
                self._search_page_starts = [0]
                self._load_search_page(0)
                self._search_idx = 0
            else:
                self._search_idx = 0
        else:
            if len(getattr(self, "_search_page_starts", [0])) > 1:
                self._search_page_starts = [0]
                self._load_search_page(0)
            self._search_idx = 0
        self._goto_match(self._search_idx)
        # 导航不改变文档：只重新着色当前匹配(内部含计数刷新)，免去全文重建
        self._refresh_extra_selections(rebuild_search=False)

    def _search_prev(self):
        if not self._search_matches:
            return
        if self._search_idx > 0:
            self._search_idx -= 1
        elif len(getattr(self, "_search_page_starts", [0])) > 1:
            if self._load_search_prev_page() and self._search_matches:
                self._search_idx = len(self._search_matches) - 1
            else:
                self._search_idx = 0
        elif getattr(self, "_search_match_capped", False):
            if self._load_search_last_page() and self._search_matches:
                self._search_idx = len(self._search_matches) - 1
            else:
                self._search_idx = 0
        else:
            self._search_idx = len(self._search_matches) - 1
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
        self._search_scan_end = 0
        self._search_page_starts = [0]
        self._search_page_key = None
        self._search_page_rev = None
        self._search_page_chars = None
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

    def _kw_inc_state(self):
        """Per-recv-widget incremental keyword state (follows the session tab)."""
        te = getattr(self, "txt_recv", None)
        if te is None:
            return None
        st = getattr(te, "_kw_inc", None)
        if not isinstance(st, dict):
            st = {
                "sels": [],
                "rev": None,
                "key": None,
                "tail": 0,     # 自上次扫描起追加的字符数（见 _kw_mark_dirty）
                "blocks": 0,
                "full": True,
                "capped": False,
            }
            te._kw_inc = st
        return st

    def _kw_reset_inc(self):
        te = getattr(self, "txt_recv", None)
        if te is not None and hasattr(te, "_kw_inc"):
            delattr(te, "_kw_inc")

    def _kw_mark_full(self):
        st = self._kw_inc_state()
        if st is not None:
            st["full"] = True
            st["tail"] = 0

    def _kw_mark_dirty(self, added_chars=0):
        """Register appended characters changed since the last keyword scan.

        Accumulates the length of the *appended tail*, not block numbers or
        absolute positions: ``maximumBlockCount`` drops head blocks on overflow,
        which shifts both, while appended text always lands at the end of the
        document (head trims remove from the front only). At scan time the dirty
        range is recovered as ``[last_char - tail, last_char]`` — correct under
        any amount of head truncation (``_kw_scan_incremental``).
        """
        st = self._kw_inc_state()
        if st is None or st["full"]:
            return
        try:
            n = max(0, int(added_chars or 0))
        except (TypeError, ValueError):
            n = 0
        st["tail"] = int(st.get("tail") or 0) + n

    def _kw_rules_key(self, parsed):
        hex_on = bool(self.sw_rx_hex.isChecked()) if hasattr(self, "sw_rx_hex") else False
        return (
            tuple((pat, col.name(), is_bg, scope, match)
                  for pat, col, is_bg, scope, match in parsed),
            bool(getattr(self, "_hexdump_on", False)),
            bool(getattr(self, "_numview_on", False)),
            hex_on,
            bool(getattr(self, "_terminal_on", False)),
        )

    @staticmethod
    def _kw_sel_block_no(sel):
        cur = getattr(sel, "cursor", None)
        if cur is None or cur.isNull():
            return None
        if cur.selectionStart() == cur.selectionEnd():
            return None
        block = cur.block()
        if not block.isValid():
            return None
        return block.blockNumber()

    def _append_kw_sels_for_block(self, doc, block, parsed, hexdump_view,
                                  sels, capped):
        """Scan one block's RX/TX runs into ``sels``. Returns (capped, had_match)."""
        block_has_match = False
        if not parsed or capped:
            return capped, False
        for role, ftext, base in self._block_body_runs(block):
            for pat, col, is_bg, scope, match_mode in parsed:
                if scope == "rx" and role != ROLE_RX:
                    continue
                if scope == "tx" and role != ROLE_TX:
                    continue
                rule = {"pattern": pat, "match": match_mode}
                spans = _kw_rule_spans(
                    ftext, rule, hexdump=hexdump_view,
                    limit=max(0, self._KW_MAX_SELECTIONS - len(sels)))
                for a, b in spans:
                    if a >= b:
                        continue
                    block_has_match = True
                    sel = QTextEdit.ExtraSelection()
                    if is_bg:
                        sel.format.setBackground(col)
                        lum = (0.299 * col.red() + 0.587 * col.green()
                               + 0.114 * col.blue())
                        sel.format.setForeground(
                            QColor("#1C1C1E") if lum > 140 else QColor("#FFFFFF"))
                    else:
                        sel.format.setForeground(col)
                    cur = QTextCursor(doc)
                    cur.setPosition(base + a)
                    cur.setPosition(base + b, QTextCursor.KeepAnchor)
                    cur.setKeepPositionOnInsert(True)
                    sel.cursor = cur
                    sels.append(sel)
                    if len(sels) >= self._KW_MAX_SELECTIONS:
                        return True, True
        return capped, block_has_match

    def _kw_commit_state(self, st, sels, capped, key, doc):
        st["sels"] = list(sels)
        st["capped"] = bool(capped)
        st["key"] = key
        st["rev"] = doc.revision()
        st["blocks"] = doc.blockCount()
        st["tail"] = 0
        st["full"] = False
        return list(sels), bool(capped)

    def _collect_keyword_highlights(self, doc, parsed, filter_on):
        """Keyword ExtraSelections: incremental tail scan, or full walk.

        Filter mode needs every block's visibility, so it always full-scans.
        A document revision bump without a registered appended tail (setPlainText,
        theme recolor, missed edit) also falls back to a full walk.
        """
        self._kw_scan_blocks = 0
        self._kw_scan_mode = "full"
        st = self._kw_inc_state()
        key = (self._kw_rules_key(parsed), bool(filter_on))
        hexdump_view = bool(getattr(self, "_hexdump_on", False))
        if st is None:
            return self._kw_scan_full(doc, parsed, filter_on, hexdump_view,
                                      {"sels": []}, key)

        need_full = (
            filter_on or st["full"] or st["key"] != key or st["rev"] is None)
        if not need_full and st["rev"] == doc.revision():
            self._kw_scan_mode = "skip"
            return list(st["sels"]), st["capped"], False
        if not need_full:
            if doc.blockCount() < int(st.get("blocks") or 0):
                need_full = True
            elif not int(st.get("tail") or 0):
                # Edited, but no writer registered appended chars.
                need_full = True
        if need_full:
            return self._kw_scan_full(doc, parsed, filter_on, hexdump_view, st, key)
        self._kw_scan_mode = "incr"
        return self._kw_scan_incremental(doc, parsed, hexdump_view, st, key)

    def _kw_scan_full(self, doc, parsed, filter_on, hexdump_view, st, key):
        sels = []
        capped = False
        dirty = False
        block = doc.begin()
        while block.isValid():
            self._kw_scan_blocks += 1
            capped, block_has_match = self._append_kw_sels_for_block(
                doc, block, parsed, hexdump_view, sels, capped)
            if not filter_on:
                want_vis = True
            else:
                want_vis = block_has_match or not self._block_has_body_role(block)
            if block.isVisible() != want_vis:
                block.setVisible(want_vis)
                dirty = True
            block = block.next()
        self._kw_commit_state(st, sels, capped, key, doc)
        return list(sels), capped, dirty

    def _kw_scan_incremental(self, doc, parsed, hexdump_view, st, key):
        last_bn = max(0, doc.blockCount() - 1)
        plain_len = max(0, doc.characterCount() - 1)
        tail = max(0, int(st.get("tail") or 0))
        from_pos = max(0, plain_len - tail)
        from_block = doc.findBlock(from_pos)
        if not from_block.isValid():
            # 尾部长度超过当前文档（头部被大量截掉）——增量定位失效，回退全量。
            self._kw_scan_mode = "full"
            return self._kw_scan_full(doc, parsed, False, hexdump_view, st, key)
        from_bn = from_block.blockNumber()
        to_bn = last_bn   # 正文只追加到文末，脏区间的上界就是当前末块
        prefix, suffix = [], []
        for sel in st["sels"]:
            bn = self._kw_sel_block_no(sel)
            if bn is None:
                continue
            if bn < from_bn:
                prefix.append(sel)
            elif bn > to_bn:
                suffix.append(sel)
        sels = list(prefix)
        capped = len(sels) >= self._KW_MAX_SELECTIONS
        if not capped:
            block = doc.findBlockByNumber(from_bn)
            while block.isValid() and block.blockNumber() <= to_bn:
                self._kw_scan_blocks += 1
                capped, _had = self._append_kw_sels_for_block(
                    doc, block, parsed, hexdump_view, sels, capped)
                if capped:
                    break
                block = block.next()
        if not capped:
            sels.extend(suffix)
            if len(sels) > self._KW_MAX_SELECTIONS:
                sels = sels[:self._KW_MAX_SELECTIONS]
                capped = True
        self._kw_commit_state(st, sels, capped, key, doc)
        return list(sels), capped, False

    def _refresh_extra_selections(self, rebuild_search=True):
        """统一构建数据区叠加高亮：关键字着色(背景/文字，分收/发范围) + 单击行高亮(最上层)；
        若开启「只显高亮行」过滤，则隐藏未命中关键字的行(块可见性折叠)。"""
        if not hasattr(self, "txt_recv"):
            return
        doc = self.txt_recv.document()
        # 1. 关键字高亮（生效分组；区分大小写子串匹配；按规则 scope 限定 收/发/收发）
        rules = [r for r in self._active_rules()
                 if r.get("enabled", True) and r.get("pattern")]
        # (pattern, QColor, is_bg, scope) — scope: 'both'/'rx'/'tx'
        parsed = [(r["pattern"], QColor(r.get("color", "#FFD60A")),
                   r.get("mode", "bg") == "bg", r.get("scope", "both"),
                   _kw_normalize_match(r.get("match"))) for r in rules]
        # 过滤仅在有 启用+非空 规则时才生效，避免"开了过滤却没规则 → 全空"
        filter_on = self._filter_active()
        sels, capped, dirty = self._collect_keyword_highlights(doc, parsed, filter_on)
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
                new_key = self._search_page_key_tuple()
                old_key = getattr(self, "_search_page_key", None)
                rev = doc.revision()
                old_rev = getattr(self, "_search_page_rev", None)
                chars = max(0, doc.characterCount() - 1)
                old_chars = getattr(self, "_search_page_chars", None)
                if new_key != old_key:
                    # 词/模式/大小写/hexdump 变了：重置到第一页。硬上限在 find_spans
                    # 内止损；更多匹配靠 ▼ 惰性加载下一页（_extend_search_next_page）。
                    self._reload_search_page(reset=True)
                    self._search_page_key = new_key
                    self._search_idx = 0 if self._search_matches else -1
                elif rev != old_rev:
                    # 词未变、文档变了：重建当前页，让新追加的命中出现在搜索高亮里。
                    # 头部截断会让页起点码点失真 → 回第一页。词+revision 都未变才
                    # 跳过 toPlainText+find_spans（关键字/行高亮刷新不必连带全扫搜索）。
                    truncated = old_chars is not None and chars < old_chars
                    self._reload_search_page(reset=truncated)
                    if truncated:
                        self._search_idx = 0 if self._search_matches else -1
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
        self._kw_mark_full()
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
    def _block_body_runs(block):
        """Contiguous RX/TX text runs, merging fragments split only by formatting."""
        runs = []
        run_role = None
        run_text = []
        run_base = 0

        def flush():
            nonlocal run_role, run_text, run_base
            if run_role in (ROLE_RX, ROLE_TX) and run_text:
                runs.append((run_role, "".join(run_text), run_base))
            run_role = None
            run_text = []
            run_base = 0

        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            role = frag.charFormat().property(ROLE_PROP) if frag.isValid() else None
            if role not in (ROLE_RX, ROLE_TX):
                flush()
            elif role == run_role:
                run_text.append(frag.text())
            else:
                flush()
                run_role = role
                run_base = frag.position()
                run_text = [frag.text()]
            it += 1
        flush()
        return runs

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
        for role, ftext, _base in self._block_body_runs(block):
            for r in rules:
                scope = r.get("scope", "both")
                if scope == "rx" and role != ROLE_RX:
                    continue
                if scope == "tx" and role != ROLE_TX:
                    continue
                if _kw_rule_matches(
                        ftext, r,
                        hexdump=bool(getattr(self, "_hexdump_on", False))):
                    return True
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
        views = [s.txt_recv for s in self.sessions()
                 if s.txt_recv is not None]
        # 每个角色的目标色只算一次(原来每片段都建 QColor + 调 _role_color)
        role_col = {r: QColor(self._role_color(r, theme))
                    for r in (None, ROLE_TS, ROLE_RX, ROLE_TX)}
        is_dark = theme.get("mode") == "dark"      # ANSI 调色板按主题明暗选那一套
        for txt in views:
            doc = txt.document()
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
                        acol = (ansi.color_of_spec(
                            spec, is_dark, theme["fg"], theme["bg"])
                            if spec else None)
                        role = fmt.property(ROLE_PROP)
                        col = (QColor(acol) if acol
                               else role_col.get(role, role_col[None]))
                        # 背景色同理：ANSI 的 40-47/100-107 也是调色板序号。
                        bspec = fmt.property(ANSI_BG_PROP)
                        bcol = (ansi.color_of_spec(
                            bspec, is_dark, theme["fg"], theme["bg"])
                            if bspec else None)
                        bg = QColor(bcol) if bcol else None
                        start = frag.position()
                        end = start + frag.length()
                        if (ranges and ranges[-1][1] == start
                                and ranges[-1][2] == col
                                and ranges[-1][3] == bg):
                            ranges[-1] = (ranges[-1][0], end, col, bg)
                        else:
                            ranges.append((start, end, col, bg))
                    it += 1
                block = block.next()
            if not ranges:
                continue
            txt.setUpdatesEnabled(False)
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
                txt.setUpdatesEnabled(True)

    def build_send_card(self):
        return _send_card.build(self)

    def apply_style(self):
        """根据当前主题构建全局 QSS — light/dark 模式整体切换"""
        tid = self.cb_theme.currentData() if hasattr(self, "cb_theme") else THEME_DEFAULT
        c = chrome_for(tid)
        t = THEMES.get(tid, THEMES[THEME_DEFAULT])

        # Tooltip 在 dark mode 用浅色 (反差)，light 用深色
        tooltip_bg, tooltip_fg = _term_vt.tooltip_colors(t.get("mode"))
        qss = app_style.build_app_qss(c, t, tooltip_bg, tooltip_fg)
        self.setStyleSheet(localize_qss(qss))
        # 强制所有子 widget 重新评估样式 —— Qt 有时 setStyleSheet 后旧子组件保留缓存样式
        # 典型表现：重启后从设置里恢复主题，title bar 变了但中间数据区还是旧色
        app_style.polish_widget_tree(self)

        # 下拉弹出容器(QComboBoxPrivateContainer)是独立顶层窗口，其底色走系统调色板默认白，
        # 深色主题下圆角/边框处会露白边。这里把每个下拉的弹出容器背景刷成下拉色，彻底消除白边。
        for combo in self.findChildren(QComboBox):
            _style_one_combo_popup(combo, c)

    # ----- 连接 打开/关闭 -----
    def toggle_conn(self):
        if self.conn is not None:
            session = self._session_ctx()
            if session is not None:
                session._user_closing = True
                session.period_on = False
            else:
                self._user_closing = True
            try:
                _closing_proto = getattr(self, "_conn_proto", None)
                cancelling_async = (
                    _closing_proto in (PROTO_BLE, PROTO_RTT)
                    and self.conn is not None
                    and not getattr(self.conn, "is_open", False)
                    and not getattr(self, "_conn_engaged", False))
                self._cancel_reconnect()        # 也取消已排队的重连
                self._serial_reconnect_cfg = None
                self.close_conn()
                if cancelling_async:
                    self.toast(self._t(
                        "rtt_cancelled" if _closing_proto == PROTO_RTT
                        else "ble_cancelled"))
            finally:
                if session is not None:
                    session._user_closing = False
                else:
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
            per = int(self._display_value(
                "hexdump_width", self.cb_hexdump_width.currentText()))
        except (ValueError, AttributeError):
            per = 16
        dump = self._format_hexdump(data, per)
        show_ts = self._session_display_flag(
            "show_timestamp",
            self.sw_show_timestamp.isChecked()
            if hasattr(self, "sw_show_timestamp") else False)
        return _view_leading_nl(dump, bool(show_ts))

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
        ctx = getattr(self, "_display_context", None)
        if ctx is not None:
            spec = ctx.get("numview_spec")
            if isinstance(spec, (tuple, list)) and len(spec) == 2:
                return tuple(spec)
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
        return _view_leading_nl(text, bool(self._display_value(
            "show_timestamp", self.sw_show_timestamp.isChecked())))

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
        if proto == PROTO_BLE:
            return _conn_ble_sig(
                proto,
                self.ed_ble_address.text() if hasattr(self, "ed_ble_address") else "",
                self.ed_ble_service.text() if hasattr(self, "ed_ble_service") else "",
                self.ed_ble_write.text() if hasattr(self, "ed_ble_write") else "",
                self.ed_ble_notify.text() if hasattr(self, "ed_ble_notify") else "",
                self.cb_ble_write_mode.currentData()
                if hasattr(self, "cb_ble_write_mode") else "auto")
        if proto == PROTO_RTT:
            return _conn_rtt_sig(
                proto,
                self.cb_rtt_device.currentText()
                if hasattr(self, "cb_rtt_device") else "",
                self._rtt_speed_text(),
                self.cb_rtt_interface.currentText()
                if hasattr(self, "cb_rtt_interface") else "",
                self.ed_rtt_address.text() if hasattr(self, "ed_rtt_address") else "",
                self.cb_rtt_channel.currentData()
                if hasattr(self, "cb_rtt_channel") else 0,
                self._rtt_probe_text(),
                self.sw_rtt_reset.isChecked()
                if hasattr(self, "sw_rtt_reset") else False)
        return _conn_proto_sig(proto)

    def open_conn(self, reconnect_cfg=None, reconnect_snapshot=None):
        """Open the connection described by the current UI (or reconnect_cfg)."""
        manual_open = reconnect_cfg is None and reconnect_snapshot is None
        if reconnect_snapshot is not None:
            proto = str(reconnect_snapshot.get("proto") or "")
            fields = dict(reconnect_snapshot.get("fields") or {})
        else:
            ui_fields = {
                "port": self.cb_port.currentData(),
                "baud": self.cb_baud.currentText(),
                "remote_ip": self.ed_remote_ip.text(),
                "remote_port": self.ed_remote_port.text(),
                "local_ip": self.cb_local_ip.currentText(),
                "local_port": self.ed_local_port.text(),
                "group": self.ed_group.text(),
                "use_remote": self.sw_udp_remote.isChecked(),
                "ble_address": (self.ed_ble_address.text()
                                if hasattr(self, "ed_ble_address") else ""),
                "ble_service_uuid": (self.ed_ble_service.text()
                                     if hasattr(self, "ed_ble_service") else ""),
                "ble_write_uuid": (self.ed_ble_write.text()
                                   if hasattr(self, "ed_ble_write") else ""),
                "ble_notify_uuid": (self.ed_ble_notify.text()
                                    if hasattr(self, "ed_ble_notify") else ""),
                "ble_write_mode": (
                    self.cb_ble_write_mode.currentData() or "auto"
                    if hasattr(self, "cb_ble_write_mode") else "auto"),
                "rtt_device": (self.cb_rtt_device.currentText()
                               if hasattr(self, "cb_rtt_device") else ""),
                "rtt_interface": (self.cb_rtt_interface.currentText()
                                  if hasattr(self, "cb_rtt_interface") else ""),
                "rtt_speed": self._rtt_speed_text(),
                "rtt_address": (self.ed_rtt_address.text()
                                if hasattr(self, "ed_rtt_address") else ""),
                "rtt_channel": (self.cb_rtt_channel.currentData()
                                if hasattr(self, "cb_rtt_channel") else 0),
                "rtt_probe": self._rtt_probe_text(),
                "rtt_reset": (self.sw_rtt_reset.isChecked()
                              if hasattr(self, "sw_rtt_reset") else False),
            }
            if reconnect_cfg:
                proto, fields = _conn_open_fields_from_reconnect(reconnect_cfg)
                if not fields:
                    fields = _conn_open_fields_from_ui(proto, ui_fields)
            else:
                proto = self.cb_proto.currentText()
                fields = _conn_open_fields_from_ui(proto, ui_fields)
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
        session = self._session_ctx() or self.active_session()
        period_intent = bool(session.period_on) if session is not None else False
        resource_key = self._session_resource_key_from_open(proto, fields)
        conflict = self.check_session_resource_conflict(resource_key, session)
        if conflict is not None:
            if manual_open and session is self.active_session():
                self.toast(self._t(
                    "session_conflict", name=conflict.tab_label()))
            return "resource-conflict"
        # Defense-in-depth: never orphan a live conn when open_conn is called
        # again (UI toggle normally closes first; this covers racy/programmatic paths).
        if self.conn is not None:
            self.close_conn(
                update_ui=(session is self.active_session()),
                preserve_session_intent=True)
        port = checked.get("port") if proto == PROTO_SERIAL else None
        serial_extras = None
        if proto == PROTO_SERIAL:
            extras = (tuple(reconnect_snapshot.get("serial_extras") or ())
                      if reconnect_snapshot is not None else
                      (_conn_serial_extras(reconnect_cfg) if reconnect_cfg else None))
            if not extras:
                extras = None
            if extras is not None:
                databits, parity, stopbits, flow = extras
                if flow is None:
                    flow = self.cb_flow.currentText()
            else:
                databits = self.cb_databits.currentText()
                parity = self.cb_parity.currentText()
                stopbits = self.cb_stopbits.currentText()
                flow = self.cb_flow.currentText()
            serial_extras = (databits, parity, stopbits, flow)
            sp = _resolve_serial_params(databits, parity, stopbits, flow)
            conn = SerialConn(
                port, checked["baud"], sp["bytesize"],
                sp["parity"], sp["stopbits"], flow=sp["flow"])
        elif proto == PROTO_VIRTUAL:
            loopback = (bool(reconnect_snapshot.get("virtual_loopback", False))
                        if reconnect_snapshot is not None
                        else self.sw_vconn_loop.isChecked())
            conn = VirtualConn(loopback=loopback)
        elif proto == PROTO_TCP_SERVER:
            conn = TcpServerConn(checked["local_ip"], checked["port"])
        elif proto == PROTO_TCP_CLIENT:
            conn = TcpClientConn(checked["ip"], checked["port"])
        elif proto == PROTO_UDP_MULTICAST:
            conn = UdpGroupConn(checked["local_ip"], checked["group"], checked["port"])
        elif proto == PROTO_BLE:
            self._stop_ble_scan()
            self._hide_ble_scan_dialog()
            conn = BleConn(
                checked["address"], checked.get("service_uuid", ""),
                checked["write_uuid"], checked["notify_uuid"],
                write_mode=checked.get("write_mode", "auto"))
        elif proto == PROTO_RTT:
            conn = RttConn(
                checked["device"], checked.get("speed", 4000),
                checked.get("interface", "SWD"),
                checked.get("address", 0), checked.get("channel", 0),
                serial_no=checked.get("probe", ""),
                reset_on_open=checked.get("reset", False),
                search_size=checked.get("search_size", 0))
        else:
            conn = UdpConn(
                checked["local_ip"], checked["lport"],
                checked["rip"], checked["rport"])

        # TCP Server 额外携带来源客户端 key，让协议自动应答能精确回给请求方；
        # 其余连接仍走原有单参数信号。
        # Bind to the session that is opening (context), not the visible tab.
        self._bind_conn_signals(conn, session)

        # Assign before open(): sync listeners may emit state_changed(True) immediately.
        if reconnect_snapshot is not None:
            conn_cfg = tuple(reconnect_snapshot.get("conn_cfg") or (proto,))
        elif reconnect_cfg:
            conn_cfg = tuple(reconnect_cfg)
        else:
            conn_cfg = self._conn_config_signature(proto)
        if reconnect_snapshot is None:
            session._reconnect_snapshot = {
                "proto": proto,
                "fields": dict(fields),
                "serial_extras": serial_extras,
                "virtual_loopback": bool(getattr(conn, "loopback", False)),
                "conn_cfg": tuple(conn_cfg),
            }
        self._conn_proto = proto
        self._conn_cfg = conn_cfg
        if session is self.active_session():
            self._mbm_guard_until = 0.0
        self.conn = conn
        if not conn.open():
            if self.conn is conn:
                self.conn = None
                self._conn_proto = None
                self._conn_cfg = None
                conn.deleteLater()
            return

        cur = self.active_session()
        ctx = self._session_ctx()
        if ctx is cur:
            self.btn_open.setProperty("state", "open")
            self.btn_open.style().unpolish(self.btn_open)
            self.btn_open.style().polish(self.btn_open)
            self.set_settings_enabled(False)
            self._update_net_fields()
            self._update_conn_status()
            if cur is not None and manual_open:
                self._save_ui_into_session(cur)
                cur.period_on = period_intent
            if cur is not None:
                self._restore_session_periodic(cur)
        elif session is not None:
            self._sync_session_period_timer(session)
        if session is not None:
            self._restore_session_log_intent(session)
        self._refresh_session_tab_styles()
        self._serial_device = port if proto == PROTO_SERIAL else None
        self._serial_missing_count = 0
        if proto == PROTO_SERIAL:
            self._serial_reconnect_cfg = None
            if ctx is cur:
                self._select_serial_device(port)
                self._apply_ctrl_lines_on_open()
            else:
                self._apply_ctrl_lines_to_conn(conn, session)

    def _on_vconn_loop_toggled(self, on):
        """回环开关：连接期间也能随时切（虚拟连接无需重开），并刷新状态栏文案。"""
        self.settings.setValue("vconn_loopback", bool(on))
        if isinstance(self.conn, VirtualConn):
            self.conn.loopback = bool(on)
            self._update_conn_status()

    def _session_ctrl_line_values(self, session=None):
        """Resolve DTR/RTS from one session, falling back to profile defaults."""
        session = session or self._session_ctx() or self.active_session()
        fields = getattr(session, "conn_fields", None)
        fields = fields if isinstance(fields, dict) else {}
        dtr = bool(fields.get(
            "serial_dtr", self.settings.value("serial_dtr", True, type=bool)))
        rts = bool(fields.get(
            "serial_rts", self.settings.value("serial_rts", True, type=bool)))
        return dtr, rts

    def _apply_ctrl_lines_to_conn(self, conn, session=None):
        """Apply one session's output control lines without touching active UI."""
        dtr, rts = self._session_ctrl_line_values(session)
        conn.set_dtr(dtr)
        conn.set_rts(rts)
        return dtr, rts

    def _apply_ctrl_lines_on_open(self):
        """串口连上：按持久化的 DTR/RTS 状态应用到硬件 + 同步开关 + 启动输入状态线轮询。"""
        session = self._session_ctx() or self.active_session()
        dtr, rts = self._apply_ctrl_lines_to_conn(self.conn, session)
        for sw, val in ((self.sw_dtr, dtr), (self.sw_rts, rts)):
            sw.blockSignals(True); sw.setChecked(val); sw.blockSignals(False)
        self._poll_ctrl_lines()
        self._ctrl_poll_timer.start()

    def _sync_ctrl_poll_for_active_session(self):
        """Start modem-line polling exactly when the active tab is an open serial link."""
        timer = getattr(self, "_ctrl_poll_timer", None)
        if timer is None:
            return
        session = self.active_session()
        serial_open = bool(
            session is not None
            and session._conn_proto == PROTO_SERIAL
            and session.conn is not None
            and getattr(session.conn, "is_open", False))
        if not serial_open:
            timer.stop()
            return
        with self._with_session(session):
            self._poll_ctrl_lines()
        timer.start()

    def _on_dtr_toggled(self, on):
        self.settings.setValue("serial_dtr", bool(on))
        session = self.active_session()
        if session is not None:
            session.conn_fields = dict(session.conn_fields or {})
            session.conn_fields["serial_dtr"] = bool(on)
        if self._conn_proto == PROTO_SERIAL and self.conn is not None:
            self.conn.set_dtr(on)

    def _on_rts_toggled(self, on):
        self.settings.setValue("serial_rts", bool(on))
        session = self.active_session()
        if session is not None:
            session.conn_fields = dict(session.conn_fields or {})
            session.conn_fields["serial_rts"] = bool(on)
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
        # Timer belongs to the owning Session.  Switching tabs during the pulse
        # must still release this connection, never the newly active one.
        self._reset_timer.start(120)

    def _pulse_reset_release_for(self, session_id):
        session = self.find_session(session_id)
        if session is None:
            return
        with self._with_session(session):
            self._pulse_reset_release()

    def _pulse_reset_release(self):
        # The active owner can honor the live switch (including a change during
        # the 120 ms pulse).  A hidden owner must use its captured session field,
        # never the newly active tab's shared UI.
        if self._conn_proto == PROTO_SERIAL and self.conn is not None:
            owner = self._session_ctx() or self.active_session()
            if owner is self.active_session() and hasattr(self, "sw_dtr"):
                dtr = bool(self.sw_dtr.isChecked())
            else:
                dtr, _rts = self._session_ctrl_line_values(owner)
            self.conn.set_dtr(dtr)

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
        ctx = self._session_ctx() or self.active_session()
        self._reset_trigger_decoders(session=ctx)  # this session only; keep other tabs
        if ctx is self.active_session():
            if hasattr(self, "_proto_fields"):
                self._proto_fields.clear()
            if reset_dashboard:
                dash = getattr(self, "_dash_dlg", None)
                if dash is not None:
                    dash.reset_stream()

    def _on_conn_error(self, msg, update_ui=True):
        """连接层致命错误：监听/连接/绑定失败 或 连接过程中出错。"""
        if msg == ERR_SEND_BACKPRESSURE:
            # 写缓冲积压：已经丢弃这一帧，连接仍可用，不能走 close_conn。
            _log.warning("TCP send backpressure: dropped a write, link kept")
            return
        # 用 _conn_proto(实际打开的协议)而非下拉框当前值：连接中导入配置可能改了下拉框，
        # 不能拿新值解释旧连接(见 __init__ 处 _conn_proto 注释)。在此处一次性取，早于下面
        # close_conn() 把它清空；失败/无连接时回退读下拉框。
        proto = self._conn_proto or (self.cb_proto.currentText() if hasattr(self, "cb_proto") else "")
        ble_key = _BLE_ERROR_I18N.get(msg) or _RTT_ERROR_I18N.get(msg)
        key = {PROTO_SERIAL: "err_open_failed",
               PROTO_TCP_SERVER: "err_listen_failed",
               PROTO_TCP_CLIENT: "err_connect_failed",
               PROTO_UDP: "err_bind_failed",
               PROTO_UDP_MULTICAST: "err_bind_failed",
               PROTO_BLE: "err_connect_failed",
               PROTO_RTT: "err_connect_failed"}.get(proto, "err_connect_failed")
        # 串口已打开成功后 reader 运行时报错(拔出/掉线等)：文案用"连接中断"而非"打开失败"
        if proto == PROTO_SERIAL and self._conn_engaged:
            key = "err_serial_runtime"
        was_conn_timeout = (msg == ERR_CONN_TIMEOUT)
        if ble_key:
            pass
        elif was_conn_timeout:   # net_io timeout sentinel -> localized text
            msg = self._t("err_conn_timeout")
        else:
            # S-5: map raw OS/Qt strings to actionable tips when recognized
            msg = conn_error_tips.format_conn_error_detail(msg, self._t)
        self._stat_note_rx_error()           # connection/link errors count as RX errors
        if was_conn_timeout:
            _note_to = getattr(self, "_stat_note_timeout", None)
            if callable(_note_to):
                _note_to("conn")
        if update_ui:
            self._refresh_stat_labels(with_tooltip=False)
        # 串口首次掉线必须提示一次；仅当已经持有重连目标（即后续自动重试）时静默。
        # 不用 attempts 判断，避免残留/边界计数让首次掉线被误判成重试而吞掉提示。
        serial_retrying = proto == PROTO_SERIAL and self._serial_reconnect_cfg is not None
        if update_ui and not serial_retrying:
            if ble_key:
                self.toast(self._t(ble_key), error=True)
            else:
                self.toast(self._t(key, e=msg), error=True)
        # 关键：close_conn 会把 _conn_engaged 清零，所以要先捕获状态
        was_engaged = self._conn_engaged
        in_retry = self._reconnect_attempts > 0
        serial_cfg = self._conn_cfg if proto == PROTO_SERIAL else None
        if self.conn is not None:
            self.close_conn(
                update_ui=(self._session_ctx() is self.active_session()),
                preserve_session_intent=True)
        # 只在「曾连上又断了」(运行时掉线) 或「正在重连周期内」时自动重连。
        # 手动打开失败（端口占用/服务器离线/绑定失败）不该陷入无限重试。
        # 串口重连保存掉线前的完整签名，不读取可能已回落到其他设备的下拉框。
        if proto == PROTO_SERIAL and serial_cfg and (was_engaged or in_retry):
            self._serial_reconnect_cfg = tuple(serial_cfg)
        if was_engaged or in_retry:
            self._schedule_reconnect()

    @staticmethod
    def _session_auto_reconnect_enabled(host, session=None):
        """Resolve reconnect policy from the owning session, then defaults."""
        fields = getattr(session, "conn_fields", None)
        if isinstance(fields, dict) and "auto_reconnect" in fields:
            return bool(fields["auto_reconnect"])
        settings = getattr(host, "settings", None)
        if settings is not None:
            return settings.value("auto_reconnect", True, type=bool)
        return True

    def _schedule_reconnect(self):
        """Non-user disconnect -> queue reconnect; policy in reconnect_policy."""
        _ctx = getattr(self, "_session_ctx", None)
        sess = _ctx() if callable(_ctx) else None
        timer = None
        if sess is not None and hasattr(sess, "_reconnect_timer"):
            timer = sess._reconnect_timer
        else:
            timer = getattr(self, "_reconnect_timer_fallback", None)
            if timer is None:
                timer = getattr(self, "_reconnect_timer", None)
        user_closing = (bool(getattr(self, "_user_closing", False))
                        or bool(getattr(sess, "_user_closing", False)))
        visible = sess is None or sess is self.active_session()
        auto = CommTool._session_auto_reconnect_enabled(self, sess)
        proto = getattr(self, "_conn_proto", None)
        if not proto and sess is not None:
            proto = (getattr(sess, "conn_fields", None) or {}).get("net_proto")
        if not proto and hasattr(self, "cb_proto"):
            proto = self.cb_proto.currentText()
        plan = _reconnect_policy.plan_schedule(
            user_closing=user_closing,
            auto_reconnect=auto,
            timer_active=(timer.isActive() if timer is not None else False),
            serial_retry=self._serial_reconnect_cfg is not None,
            attempts=self._reconnect_attempts,
            serial_limit=self._serial_reconnect_limit,
            attempt_limit=(
                _reconnect_policy.BLE_RECONNECT_LIMIT
                if proto == PROTO_BLE else (
                    _reconnect_policy.RTT_RECONNECT_LIMIT
                    if proto == PROTO_RTT else None)),
        )
        action = plan.get("action")
        if action == "skip":
            return
        if action == "exhausted":
            if plan.get("clear_serial_target"):
                self._serial_reconnect_cfg = None
            if plan.get("reset_attempts"):
                self._reconnect_attempts = 0
            refresh_tabs = getattr(self, "_refresh_session_tab_styles", None)
            if callable(refresh_tabs):
                refresh_tabs()
            return
        delay = int(plan.get("delay_ms") or 0)
        if plan.get("bump_attempts"):
            self._reconnect_attempts = int(self._reconnect_attempts or 0) + 1
            if visible:
                self.toast(self._t("auto_reconnect_in", sec=delay // 1000))
        if timer is not None:
            timer.start(delay)
            refresh_tabs = getattr(self, "_refresh_session_tab_styles", None)
            if callable(refresh_tabs):
                refresh_tabs()

    def _cancel_reconnect(self):
        _ctx = getattr(self, "_session_ctx", None)
        sess = _ctx() if callable(_ctx) else None
        stopped = False
        # The property may currently route to a test/embedder override, the
        # context session timer, or the early-init fallback.  Cancel every
        # distinct live candidate so callers never have to know that detail.
        candidates = [getattr(self, "_reconnect_timer", None)]
        if sess is not None:
            candidates.append(getattr(sess, "_reconnect_timer", None))
        candidates.append(getattr(self, "_reconnect_timer_fallback", None))
        seen = set()
        for timer in candidates:
            if timer is None or id(timer) in seen:
                continue
            seen.add(id(timer))
            try:
                if timer.isActive():
                    timer.stop()
                    stopped = True
            except RuntimeError:
                # A deferred session deletion may already have destroyed the
                # native QTimer.  Cancellation is already satisfied in that
                # case; shutdown must continue and join background threads.
                pass
        if stopped:
            refresh_tabs = getattr(self, "_refresh_session_tab_styles", None)
            if callable(refresh_tabs):
                refresh_tabs()

    def _try_reconnect(self):
        reconnect_cfg = self._serial_reconnect_cfg
        _ctx = getattr(self, "_session_ctx", None)
        sess = _ctx() if callable(_ctx) else None
        reconnect_snapshot = (getattr(sess, "_reconnect_snapshot", None)
                              if reconnect_cfg is None else None)
        user_closing = (bool(getattr(self, "_user_closing", False))
                        or bool(getattr(sess, "_user_closing", False)))
        visible = sess is None or sess is self.active_session()
        auto = CommTool._session_auto_reconnect_enabled(self, sess)
        plan = _reconnect_policy.plan_try(
            conn_open=self.conn is not None,
            user_closing=user_closing,
            auto_reconnect=auto,
            serial_cfg=reconnect_cfg,
            device_available=self._available_serial_devices,
        )
        action = plan.get("action")
        if action == "noop":
            return
        if plan.get("bump_attempts"):
            # One global budget tick per timer fire (missing port + failed open).
            self._reconnect_attempts += 1
        if action == "wait_device":
            self._schedule_reconnect()
            return
        if plan.get("toast_try") and visible:
            self.toast(self._t("auto_reconnect_try", n=self._reconnect_attempts))
        if reconnect_snapshot is None:
            open_result = self.open_conn(reconnect_cfg=reconnect_cfg)
        else:
            open_result = self.open_conn(reconnect_snapshot=reconnect_snapshot)
        if open_result == "resource-conflict":
            # Another tab owns this exclusive resource. More retries cannot
            # change that and network retries otherwise continue forever.
            self._cancel_reconnect()
            self._serial_reconnect_cfg = None
            self._reconnect_attempts = 0
            return
        if self.conn is None and not user_closing:
            if _reconnect_policy.should_reschedule_after_open_fail(
                    serial_cfg=reconnect_cfg,
                    serial_target_still_set=self._serial_reconnect_cfg is not None):
                self._schedule_reconnect()

    def _on_conn_state_changed(self, up):
        """已连接/监听(up=True) 或 对端断开(up=False)。
        主动 close_conn() 会先 blockSignals，断开的 False 不会回到这里。"""
        if up:
            if self.conn is None:
                return
            sender = self.sender()
            if sender is not None and sender is not self.conn:
                return
            self._conn_engaged = True   # 已成功建立 → 此后的 error 属"运行时"而非"打开失败"
            self._reconnect_attempts = 0  # 连上 → 重置退避；串口下次从 500ms、网络从 1s 起
            self._cancel_reconnect()
            self._update_conn_status()
            self._update_net_fields()   # TCP Server 连上后显示「目标」行
            if getattr(self, "_conn_proto", None) == PROTO_BLE:
                addr = getattr(self.conn, "address", None) or ""
                if not addr and hasattr(self, "ed_ble_address"):
                    addr = self.ed_ble_address.text().strip()
                dlg = getattr(self, "_ble_scan_dlg", None)
                if dlg is not None:
                    dlg.remember_last_connect(addr)
                else:
                    from ui.ble_scan_dialog import remember_ble_connect
                    remember_ble_connect(getattr(self, "settings", None), addr)
            if self._io_session_owns("modbus") or (
                    self._io_owner_session("modbus") is self._session_ctx()):
                self._mbm_resume_after_link_up()     # 连上 → 若本会话拥有 Modbus 主机则启动
        elif self.conn is not None:
            self.toast(self._t("net_peer_closed"))
            self.close_conn(
                update_ui=(self._session_ctx() is self.active_session()),
                preserve_session_intent=True)
            self._schedule_reconnect()  # 非主动断开 → 走自动重连

    def _drop_stale_tcp_client_framers(self, active):
        """Drop protocol-frame / AR length buffers for TCP Server clients that left."""
        active = set(active)
        ctx = self._session_ctx() or self.active_session()
        assemblers = getattr(ctx, "_frame_assemblers", None) if ctx is not None else None
        retain = getattr(assemblers, "retain_sources", None)
        if callable(retain):
            retain(active)
        bufs = getattr(self, "_ar_stream_buffers", None)
        if isinstance(bufs, dict):
            for key in list(bufs):
                if key not in active:
                    bufs.pop(key, None)

    def _on_clients_changed(self, clients):
        """TCP Server 客户端列表变化 → 刷新「目标」下拉（含「全部」）。"""
        active = {key for key, _label in clients}
        self._flush_numview_carries(set(self._numview_carries) - active)
        self._modbus_buffers = {key: buf for key, buf in self._modbus_buffers.items()
                                if key in active}
        self._drop_stale_tcp_client_framers(active)
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
                       self._trg_tail_bytes, self._trg_tail_text, self._trg_dec_codec):
            if not isinstance(states, dict):
                continue
            sid = getattr(self._session_ctx() or self.active_session(), "id", None)
            for stream_key in list(states):
                peer = None
                if isinstance(stream_key, tuple) and len(stream_key) == 3:
                    if stream_key[0] != sid:
                        continue
                    peer = stream_key[2]
                elif isinstance(stream_key, tuple) and len(stream_key) == 2:
                    peer = stream_key[1]
                if peer not in (None, "__all__") and peer not in active:
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
        session = self._session_ctx() or self.active_session()
        if session is not None:
            session.send_target = self.cb_target.currentData()
        self._update_net_fields()   # 客户端 0?有 变化时同步「目标」行的显隐

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
        elif proto == PROTO_BLE:
            name = (self.ed_ble_name.text().strip()
                    if hasattr(self, "ed_ble_name") else "")
            addr = (self.ed_ble_address.text().strip()
                    if hasattr(self, "ed_ble_address") else "")
            label = name or addr or "BLE"
            if getattr(self.conn, "is_open", False):
                mtu = getattr(self.conn, "mtu", None) or 23
                self.lbl_state.setText(self._t(
                    "ble_connected", name=label, addr=addr, mtu=mtu))
                self._set_state_color(opened=True)
            else:
                self.lbl_state.setText(self._t("net_connecting"))
                self._set_state_color(opened=False)
        elif proto == PROTO_RTT:
            dev = (self.cb_rtt_device.currentText().strip()
                   if hasattr(self, "cb_rtt_device") else "")
            ch = (self.cb_rtt_channel.currentData()
                  if hasattr(self, "cb_rtt_channel") else 0)
            if getattr(self.conn, "is_open", False):
                # 链路已通但控制块还没出现时说清楚在等什么，别让用户
                # 对着「已连接 + 一直没数据」猜。
                key = ("rtt_connected"
                       if getattr(self.conn, "control_block_seen", True)
                       else "rtt_waiting_cb")
                self.lbl_state.setText(self._t(
                    key, dev=dev or "RTT", ch=ch))
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
        """TCP Server send target key ("__all__"=all); other protocols None.

        Background sessions use their own send_target, not the active tab combo.
        """
        session = self._session_ctx()
        if session is not None and session is not self.active_session():
            return (session.send_target
                    if "Server" in str(session._conn_proto or "") else None)
        if (self.cb_proto.currentText() == PROTO_TCP_SERVER
                and hasattr(self, "cb_target") and self.cb_target.count() > 0):
            data = self.cb_target.currentData()
            if session is not None:
                session.send_target = data
            return data
        return None

    def _abort_partial_tcp_stream(self, sent, expected, update_ui=True):
        """TCP 短写后流中已留下半帧，不能继续复用；立即断开，交自动重连重建干净流。"""
        if (0 < sent < expected
                and getattr(self, "_conn_proto", None) == PROTO_TCP_CLIENT):
            self.close_conn(
                update_ui=update_ui, preserve_session_intent=True)
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

    def close_conn(self, update_ui=True, preserve_session_intent=False):
        session = self._session_ctx()
        if session is not None:
            if not preserve_session_intent:
                session.period_on = False
            if session._period_timer.isActive():
                session._period_timer.stop()
            if session._log_file is not None:
                if preserve_session_intent:
                    session.log_wanted = True
                try:
                    self._close_log_file(session=session, toast=False)
                except (OSError, RuntimeError, TypeError):
                    _log.debug("close_conn log failed", exc_info=True)
                if not preserve_session_intent:
                    session.log_wanted = False

        # Detach first: stopping replay/transfer/script may synchronously resume
        # a paused Modbus schedule.  With conn already absent, that cleanup can
        # never emit one last frame on a link being torn down.
        conn = self.conn
        self.conn = None
        owns = {
            key: self._io_session_owns(key, session)
            for key in ("transfer", "replay", "macro", "recording",
                        "device_scan", "script", "dsl", "modbus")
        }

        if (owns["transfer"] and self._xfer_worker is not None
                and self._xfer_worker.isRunning()):
            self._xfer_worker.cancel()
        rr_dlg = getattr(self, "_rr_dlg", None)
        if owns["replay"] and getattr(self, "_replay_on", False):
            if rr_dlg is not None:
                rr_dlg.stop_replay()
            else:
                self._replay_end()
        macro = getattr(self, "_macro", None)
        if owns["macro"] and macro is not None and macro.recording:
            script_dlg = getattr(self, "_script_dlg", None)
            stop_macro = getattr(script_dlg, "_on_record", None)
            if callable(stop_macro):
                try:
                    stop_macro()  # stop + preserve the captured macro in the script library
                except RuntimeError:
                    _log.debug("close_conn macro dialog cleanup failed", exc_info=True)
            if macro.recording:
                # A deleted/missing dialog must not leave a dead session pinned.
                macro.stop()
                self._io_clear_owner("macro")
        recorder = getattr(self, "_recorder", None)
        if (owns["recording"] and recorder is not None
                and recorder.recording):
            if rr_dlg is not None:
                rr_dlg.stop_recording()
            else:
                recorder.stop()
                self._io_clear_owner("recording")
        if (owns["device_scan"]
                and getattr(self, "_device_scan_state", None) is not None):
            # The shared Modbus engine belongs to the same scan.  Its restore
            # path owns the timer/inflight cleanup; do not restart it again
            # later with the just-closed connection.
            owns["modbus"] = False
            self._stop_device_scan(cancelled=True)
        elif update_ui and getattr(self, "_device_scan_state", None) is None:
            # Preserve the active-close/project-switch cleanup hook.  The real
            # implementation is a no-op here; tests/plugins may observe it.
            self._stop_device_scan(cancelled=True)
        if owns["script"] and self._script_running():
            stop_script = getattr(self._script_worker, "stop", None)
            if callable(stop_script):
                stop_script()
        if owns["dsl"]:
            self._dsl_abort()

        if update_ui:
            if not preserve_session_intent and self.sw_period.isChecked():
                self.sw_period.blockSignals(True)
                self.sw_period.setChecked(False)
                self.sw_period.blockSignals(False)
        self._ms_stop_cycle(session)
        self._flush_pending_cr()
        if (update_ui and not preserve_session_intent
                and self.sw_log_file.isChecked()):
            self.sw_log_file.blockSignals(True)
            self.sw_log_file.setChecked(False)
            self.sw_log_file.blockSignals(False)
            if hasattr(self, "_set_log_path_label"):
                self._set_log_path_label("")
        self._conn_proto = None
        self._conn_cfg = None
        self._mbm_guard_until = 0.0   # 此会话物理连接已断，旧响应不可能进入下一连接
        self._conn_engaged = False
        self._serial_device = None    # 已断开 → 清掉串口掉线检测的目标设备
        self._serial_missing_count = 0
        if self._reset_timer.isActive():
            self._reset_timer.stop()
        if conn:
            try:
                conn.blockSignals(True)
                conn.close()
            except (RuntimeError, OSError, TypeError, AttributeError):
                _log.debug("connection close failed", exc_info=True)
            try:
                conn.deleteLater()
            except (RuntimeError, AttributeError):
                _log.debug("connection deleteLater failed", exc_info=True)

        # Sequence is per-session — abort the context session's run on disconnect.
        if getattr(self, "_seq_on", False):
            self._seq_abort("seq_aborted_disc")
        self._flush_numview_carries()
        self._reset_recv_state(reset_dashboard=True)  # 新连接不能消费旧会话的半行
        # AR framing / Modbus slave bank are session-owned — always reset this session.
        self._ar_reset_buf()
        self._ar_reset_state(reset_modbus=True)
        ctx = self._session_ctx()
        if ctx is not None:
            ctx.reset_stream_frames(reset_diag=True)
        if owns["modbus"]:
            if session is not None:
                session._mbm_enabled = False  # runtime occupancy; pin keeps reconnect intent
            self._mbm_restart()
        if hasattr(self, "_ctrl_poll_timer") and update_ui:
            self._ctrl_poll_timer.stop()

        if update_ui:
            self.btn_open.setProperty("state", "")
            self.btn_open.style().unpolish(self.btn_open)
            self.btn_open.style().polish(self.btn_open)
            self.lbl_state.setText(self._t("state_closed"))
            self._set_state_color(opened=False)
            self.set_settings_enabled(True)
            if hasattr(self, "cb_target"):
                self.cb_target.clear()
            self._update_net_fields()
        self._refresh_session_tab_styles()

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
        # QObject-bound receiver: deleting the window auto-disconnects it.
        # A context-free lambda capturing ``self`` could remain queued after
        # the window's DeferredDelete and crash on the next event-loop turn.
        scan.finished.connect(self._clear_oneshot_scan)
        scan.finished.connect(scan.deleteLater)
        scan.start()

    def _clear_oneshot_scan(self, scan=None):
        """deleteLater 之后清掉 Python 属性引用，避免下次 isRunning() 访问已删 C++ 对象。
        `is scan` 守卫：如果期间已经创建了新 scan，不清新的。"""
        scan = scan or self.sender()
        if getattr(self, "_oneshot_scan", None) is scan:
            self._oneshot_scan = None

    def _populate_port_combo(self, port_list, keep_device=None, allow_placeholder=True):
        self.cb_port.blockSignals(True)
        self.cb_port.clear()
        for device, label in port_list:
            self.cb_port.addItem(label, device)
        # keep_device=None -> leave Qt default; keep_device='' -> explicit no-port
        if keep_device is not None:
            self._serial_empty_selection = (keep_device == "")
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
        active = self.active_session()
        active_id = active.id if active is not None else None
        # Check every live serial session. Hidden tabs own their missing counter and
        # reconnect timer; only the active tab is allowed to update window UI.
        for session in list(self._sessions):
            if session.conn is None or session._conn_proto != PROTO_SERIAL:
                continue
            dev = session._serial_device
            if not dev:
                continue
            if dev in self._available_serial_devices:
                session._serial_missing_count = 0
                continue
            session._serial_missing_count += 1
            if session._serial_missing_count < self._serial_missing_limit:
                continue
            reconnect_cfg = session._conn_cfg
            session._serial_missing_count = 0
            with self._with_session(session):
                if session.id == active_id:
                    self.close_conn(preserve_session_intent=True)
                else:
                    self.close_conn(
                        update_ui=False, preserve_session_intent=True)
                if reconnect_cfg:
                    session._serial_reconnect_cfg = tuple(reconnect_cfg)
                if session.id == active_id:
                    self.toast(self._t("serial_removed", port=dev), error=True)
                self._schedule_reconnect()

        # A reappearing device wakes the matching timer even when its tab is hidden.
        for session in self._sessions:
            cfg = session._serial_reconnect_cfg
            target = cfg[1] if cfg and len(cfg) > 1 else None
            if (target in self._available_serial_devices
                    and session._reconnect_timer.isActive()):
                session._reconnect_timer.start(0)

        # Keep the active serial selector stable while its connection remains open.
        if (active is not None and active.conn is not None
                and active._conn_proto == PROTO_SERIAL):
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
        if scan is None:
            return
        # Do this before waiting: a result/finished signal may already be
        # queued in the GUI thread while shutdown is synchronously deleting
        # the receiver window.
        for signal, slot in (
                (scan.scan_complete, self._on_port_scan_complete),
                (scan.finished, self._clear_oneshot_scan)):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        if scan.isRunning():
            scan.wait(2000)
        if not scan.isRunning():
            try:
                scan.finished.disconnect(scan.deleteLater)
            except (TypeError, RuntimeError):
                pass
            scan.deleteLater()
            self._oneshot_scan = None

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
        for w in (
                getattr(self, "btn_ble_scan", None),
                getattr(self, "ed_ble_name", None),
                getattr(self, "ed_ble_address", None),
                getattr(self, "cb_ble_profile", None),
                getattr(self, "ed_ble_service", None),
                getattr(self, "ed_ble_write", None),
                getattr(self, "ed_ble_notify", None),
                getattr(self, "cb_ble_write_mode", None),
                getattr(self, "btn_ble_swap", None),
                getattr(self, "cb_rtt_device", None),
                getattr(self, "cb_rtt_interface", None),
                getattr(self, "cb_rtt_speed", None),
                getattr(self, "ed_rtt_address", None),
                getattr(self, "cb_rtt_channel", None),
                getattr(self, "cb_rtt_probe", None),
                getattr(self, "sw_rtt_reset", None),
                getattr(self, "btn_rtt_device_pick", None)):
            if w is not None:
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
        self._refresh_session_tab_styles()
        _workspace_ui.refresh_top_bar_icons(self)
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
        if getattr(self, "_ble_scan_dlg", None) is not None:
            self._ble_scan_dlg.refresh_theme()
        if getattr(self, "_rtt_dev_dlg", None) is not None:
            self._rtt_dev_dlg.refresh_theme()
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
    def _display_value(self, key, default=None):
        ctx = getattr(self, "_display_context", None)
        return ctx.get(key, default) if ctx is not None else default

    def _session_display_flag(self, key, ui_default=False, session=None):
        """Boolean display option for the owning session (no active-tab leak).

        Order: ``_display_context`` (explicit background/override) → live UI for
        the active/unknown session → ``session.display_opts`` for background tabs
        → False.  Active-tab toggles must not be masked by a stale snapshot that
        was last saved on tab switch.
        """
        session = session or self._session_ctx()
        ctx = getattr(self, "_display_context", None)
        if ctx is not None and key in ctx:
            return bool(ctx[key])
        if session is None or session is self.active_session():
            return bool(ui_default)
        opts = session.display_opts or {}
        if key in opts:
            return bool(opts[key])
        return False

    def _get_codec(self) -> str:
        """Current RX/TX/file codec mode -- 'auto' or concrete codec name."""
        ctx = getattr(self, "_display_context", None)
        if ctx is not None and "encoding" in ctx:
            return _cfg_norm_enc(ctx.get("encoding"))
        session = self._session_ctx() if hasattr(self, "_session_ctx") else None
        if (session is not None
                and session is not self.active_session()):
            opts = session.display_opts or {}
            if "encoding" in opts:
                return _cfg_norm_enc(opts.get("encoding"))
            # Background without a snapshot must not inherit the active combo.
            return "auto"
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
        ctx = self._session_ctx() or self.active_session()
        self._reset_trigger_decoders(session=ctx)
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
        codec = self._get_codec()
        if codec != "auto":
            if stream_source is not None:
                dec = self._inc_decoders.get(stream_source)
                if dec is None:
                    try:
                        dec = codecs.getincrementaldecoder(codec)(errors="replace")
                    except (LookupError, TypeError):
                        return data.decode("latin-1")
                    self._inc_decoders[stream_source] = dec
                return dec.decode(data, final=False)
            if self._inc_decoder is None:
                # Initialize only this session's decoder.  Calling the UI
                # change handler here would also clear window-owned trigger
                # decoder state when a background tab receives its first byte.
                try:
                    self._inc_decoder = codecs.getincrementaldecoder(codec)(
                        errors="replace")
                except (LookupError, TypeError):
                    self._inc_decoder = None
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
            _log.warning("rx side-channel %s failed", name, exc_info=True)
            # Device-response paths: one throttled toast so silent failures are visible.
            if name in ("auto_reply", "automation.triggers.feed"):
                self._toast_rx_side_throttled(name)

    def _rx_side_display_name(self, name):
        key = _RX_SIDE_LABELS.get(name)
        if key:
            return self._t(key)
        return self._t("err_rx", e="").rstrip(": ").rstrip()

    def _toast_rx_side_throttled(self, name):
        now = time.monotonic()
        last = getattr(self, "_rx_side_toast_at", None)
        if last is None:
            last = {}
            self._rx_side_toast_at = last
        if now - float(last.get(name, 0.0) or 0.0) < 5.0:
            return
        last[name] = now
        self.toast(self._t("err_rx_side", name=self._rx_side_display_name(name)),
                   error=True)

    def on_data_received(self, data: bytes, reply_target=None):
        # Stale post-close / post-reconnect chunks are dropped in
        # _route_session_data via source_conn identity (not here): tests and
        # inject paths may call this without a live conn.
        # 文件传输进行中：整段接管收流，不进显示区/自动应答/序列/Modbus。
        # 协议传输(XMODEM/YMODEM)喂给引擎当 getc 源；原始字节流(raw)只发不收，收流直接丢弃。
        if self._feed_xfer_if_owned(data):
            return
        # 顶层异常保护：解码/插入等意外异常不应静默丢数据(传到事件循环只在 stderr 打印)
        try:
            self._on_data_received_impl(data, source=reply_target)
        except Exception as e:
            self._stat_note_rx_error()
            self._refresh_stat_labels(with_tooltip=False)
            self.toast(self._t("err_rx", e=e), error=True)
        # Analysis consumers: complete protocol frames when stream mode is on;
        # display / engines still see the original chunk.
        units = self._analysis_rx_units(data, source=reply_target)
        # Active-tab UI dialogs only (plot/frame/dash bind to the visible session).
        dlg = getattr(self, "_plot_dlg", None)
        if dlg is not None and dlg.isVisible():
            for unit in units:
                self._rx_side("plot.feed", lambda u=unit: dlg.feed(u))
        fdlg = getattr(self, "_frame_dlg", None)
        if fdlg is not None and fdlg.isVisible():
            for unit in units:
                self._rx_side("frame.feed", lambda u=unit: fdlg.feed(u))
        ddlg = getattr(self, "_dash_dlg", None)
        if ddlg is not None and ddlg.isVisible():
            for unit in units:
                self._rx_side("dashboard.feed", lambda u=unit: ddlg.feed(u))
        # Triggers keep per-session decoders so background tabs can match too.
        self._rx_side("automation.triggers.feed",
                      lambda: self._triggers_feed(data, "rx", source=reply_target))
        self._feed_session_engines(
            data, reply_target=reply_target, analysis_units=units)

    def _feed_xfer_if_owned(self, data):
        """If transfer owns this context session's RX, feed worker and consume."""
        w = self._xfer_worker
        if not _rx_dispatch.xfer_owns(
                xfer_running=(w is not None and w.isRunning())):
            return False
        if not self._io_session_owns("transfer"):
            return False
        if (self._xfer_conn is not None
                and self.conn is not self._xfer_conn):
            # close_conn cancels asynchronously. A replacement connection may
            # already be open before sig_done detaches the old worker.
            return False
        if getattr(w, "takes_input", True):
            self._rx_side("automation.xfer.feed", lambda: w.feed(data))
        return True

    def _feed_session_engines(self, data, reply_target=None, analysis_units=None):
        """Feed this context session's engines (AR/MBM/seq/script/macro/recorder/…).

        Called for both active and background RX under ``_with_session``.
        Script / sequence / MBM / recording / macro / DSL / transfer / replay
        are per-session. ``analysis_units`` is the framed (or chunk) list for
        structured protocol extract; engines themselves still consume ``data``.
        """
        units = analysis_units if analysis_units is not None else [bytes(data)]
        # 宏录制：录回包，供生成 expect(...)（脚本运行期间不录，同 TX 侧）
        script_here = (self._script_running()
                       and self._io_session_owns("script")
                       and (self._script_conn is None
                            or self.conn is self._script_conn))
        if (self._macro.recording and not script_here
                and not self._seq_running()
                and self._io_session_owns("macro")):
            self._rx_side("macro.on_rx", lambda: self._macro.on_rx(data))
        if self._recorder.recording and self._io_session_owns("recording"):
            peer = None
            proto = getattr(self, "_conn_proto", None)
            if proto in (PROTO_UDP, PROTO_UDP_MULTICAST) and hasattr(
                    self.conn, "peer_endpoint"):
                peer = self.conn.peer_endpoint()
            elif proto == PROTO_TCP_SERVER:
                peer = reply_target
            self._rx_side(
                "recorder.on_rx",
                lambda peer=peer: self._recorder.on_rx(data, source=peer))
        # 结构化记录：复用 frame_rules 抽取普通协议字段；Modbus 标签在响应解析成功后单独写入。
        def _structured_feed():
            if _rx_dispatch.structured_feed_ok(
                    mbm_inflight=self._mbm_inflight is not None):
                for unit in units:
                    self._structured_feed_protocol(unit)
        is_active_context = self._session_ctx() is self.active_session()
        if (is_active_context
                and (self._io_session_owns("modbus") or not self._mbm_active())):
            # Avoid structured parse fighting another session's in-flight MBM.
            if (self._mbm_inflight is None
                    or self._io_session_owns("modbus")):
                self._rx_side("structured.feed", _structured_feed)
        # Route uses THIS session's sequence flag; script only if pinned here.
        route = _rx_dispatch.engine_route(
            script_running=script_here,
            script_quiet_until=getattr(self, "_script_quiet_until", 0.0),
            now=time.monotonic(),
            seq_running=self._seq_running(),
            seq_waiting_mbm=bool(getattr(self, "_seq_waiting_mbm", False)),
        )
        if route == "script":
            if _rx_dispatch.should_feed_script(
                    route=route, now=time.monotonic(),
                    quiet_until=getattr(self, "_script_quiet_until", 0.0)):
                self._rx_side("script.feed",
                              lambda: self._script_worker.feed(data))
        elif route == "seq_mbm":
            # Sequence is paused on a Modbus reply; the consumer is still MBM.
            self._rx_side("mbm.feed", lambda: self._mbm_feed(data))
        elif route == "seq":
            self._rx_side("seq.feed", lambda: self._seq_feed(data))
        else:
            # AR: per-session buffers + bank; skip only when THIS session's MBM is active.
            mbm_here = (self._mbm_active()
                        and self._io_session_owns("modbus"))
            if _rx_dispatch.should_feed_auto_reply(
                    route=route, mbm_active=mbm_here):
                self._rx_side(
                    "auto_reply",
                    lambda: self._auto_reply(data, reply_target=reply_target))
            if (_rx_dispatch.should_feed_mbm(route=route)
                    and self._io_session_owns("modbus")):
                self._rx_side("mbm.feed", lambda: self._mbm_feed(data))

    def _on_data_received_impl(self, data: bytes, source=None):
        self._stat_note_rx(len(data))
        # 标签刷新交给 1Hz 的 _rate_timer：高频收包路径只累加整数计数器，
        # 不每包重建文案 + setText（会触发状态栏重排），高吞吐下避免无谓的 GUI 线程开销。

        # 终端模式：纯字节流直接追加显示，绕过 HEX / 时间戳 / 方向 / 分行 / 分包 等所有装饰。
        mode = _rx_dispatch.rx_display_mode(
            terminal_on=bool(self._display_value("terminal_on", self._terminal_on)),
            hexdump_on=bool(self._display_value("hexdump_on", self._hexdump_on)),
            numview_on=bool(self._display_value("numview_on", self._numview_on)),
        )
        if mode == "terminal":
            self._terminal_append(self._decode_rx(data, source=source), source=source)
            return

        if mode == "hexdump":
            self._append_block_data(self._hexdump_block(data), direction="rx",
                                    force_new_block=True)
            self._last_direction = "rx"
            self._last_recv_time = time.monotonic()
            self._pending_line_break = False
            return

        if mode == "numview":
            carry = _rx_dispatch.numview_carry(conn_proto=self._conn_proto)
            block = self._numview_block(data, carry=carry, source=source)
            if block:
                self._append_block_data(block, direction="rx", force_new_block=True)
                self._last_direction = "rx"
            self._last_recv_time = time.monotonic()
            self._pending_line_break = False
            return

        use_hex, use_line_split = _rx_dispatch.stream_flags(
            rx_hex=bool(self._display_value("rx_hex", self.sw_rx_hex.isChecked())),
            line_split=bool(self._display_value(
                "line_split", self.sw_line_split.isChecked())))
        now = time.monotonic()

        ansi_spans = None      # ANSI 着色：[(起, 止, 样式)]，下标相对下面这个 text
        if use_hex:
            text = self._bytes_to_hex(data) + " "
        else:
            text = self._decode_rx(data, source=source)
            if bool(self._display_value("ansi_on", self._ansi_on)):
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
                if _rx_dispatch.ansi_needs_parse(
                        pending=pd0, text=text,
                        state_is_default=(st0 is None or st0.is_default())):
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
        line_nl = int(self._display_value(
            "line_nl", self.cb_line_nl.currentIndex()))
        nl_mode_for_defer = line_nl if use_line_split else -1
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
                text, line_nl)
        else:
            segments, seg_starts = [text], [0]

        for i, seg in enumerate(segments):
            is_first = (i == 0)
            is_last = (i == len(segments) - 1)

            if is_first:
                packet_split = bool(self._display_value(
                    "packet_split", self.sw_packet_split.isChecked()))
                timeout_ms = (
                    _rx_dispatch.packet_timeout_ms(self._display_value(
                        "packet_timeout", self.ed_packet_timeout.text()))
                    if packet_split else 0)
                force_new_block = _rx_dispatch.force_new_block_first(
                    last_direction=self._last_direction,
                    pending_line_break=self._pending_line_break,
                    cross_chunk_crlf=cross_chunk_crlf,
                    packet_split=packet_split,
                    gap_ms=(now - self._last_recv_time) * 1000.0,
                    timeout_ms=timeout_ms)
            else:
                force_new_block = True

            if _rx_dispatch.skip_empty_trailing_seg(
                    is_last=is_last, seg=seg, use_line_split=use_line_split,
                    n_segments=len(segments)):
                continue

            # ANSI 着色：把整段的颜色区间切出属于本行的部分（分行后下标要换算成行内偏移）
            seg_runs = (self._ansi_slice(ansi_spans, seg_starts[i], seg_starts[i] + len(seg))
                        if ansi_spans else None)
            body_pos = self._append_block_data(seg, direction="rx", force_new_block=force_new_block,
                                               runs=seg_runs)
            self._last_direction = "rx"
            # 协议高亮：HEX 模式下整段=一帧（seg 即 hex(data)），按帧解析规则给字段上色
            proto_hl = bool(self._display_value(
                "proto_hl_on", self._proto_hl_on))
            if use_hex and proto_hl and body_pos is not None:
                self._add_proto_fields(data, body_pos)

        self._pending_line_break = _rx_dispatch.next_pending_line_break(
            use_line_split=use_line_split, segments=segments)
        self._last_recv_time = now

    @staticmethod
    def _split_lines_with_offsets(text, nl_mode):
        """Split by newline mode; return (segments, start_offsets)."""
        return _rx_split_lines(text, nl_mode)

    @staticmethod
    def _ansi_flatten(runs):
        """protocol.ansi.parse runs -> (plain_text, style spans)."""
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
        # Prefer explicit display context (background tab opts) over the
        # session proxy, so freeze_view in display_opts cannot desync from UI.
        freeze = bool(getattr(self, "_freeze_view", False))
        ctx = getattr(self, "_display_context", None)
        if ctx is not None and "freeze_view" in ctx:
            freeze = bool(ctx["freeze_view"])
        if freeze:
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
        show_ts = self._session_display_flag(
            "show_timestamp",
            self.sw_show_timestamp.isChecked()
            if hasattr(self, "sw_show_timestamp") else False)
        plan = _view_force_prefix(
            force_new_block=force_new_block,
            ends_with_nl=self._txt_ends_with_nl,
            show_timestamp=show_ts)
        if plan["need_leading_nl"]:
            cursor.insertText("\n")
            self._txt_ends_with_nl = True
        if plan["want_ts"]:
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
            view_mode = _view_recv_prop(
                bool(self._display_value("hexdump_on", self._hexdump_on)),
                bool(self._display_value("numview_on", self._numview_on)),
                bool(self._display_value("rx_hex", self.sw_rx_hex.isChecked())))
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
        background = bool(self._display_value("background", False))
        if not background and self._filter_active():
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
            body_start_pos, = _view_offsets_after_trim(trimmed, body_start_pos)
            if had_sel:
                sel_anchor, sel_pos = _view_offsets_after_trim(
                    trimmed, sel_anchor, sel_pos)

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

        last = self.txt_recv.document().lastBlock()
        if trimmed:
            self._kw_mark_full()
        elif last.isValid():
            # 尾部锚定：累积本次追加的字符数（用源文本长度——截断会把 cursor/位置一起
            # 平移，算差值会失真；ANSI 下此值略高，只会向前多扫、不会漏）。maximumBlockCount
            # 头部截断只删文档前面，已追加内容始终留在文末——扫描时 [末字符-tail, 末字符]
            # 即脏区间（见 _kw_mark_dirty / _kw_scan_incremental）。
            self._kw_mark_dirty(len(text))
        if not background:
            self._schedule_keyword_rebuild()    # 节流重扫关键字高亮(着色)

        self._write_log_block(text, direction, force_new_block, prefix=prefix)

        return body_start_pos    # 正文起始字符位置，供协议高亮做字节→字符映射

    def _flush_log_file(self, session=None, to_disk=False):
        """Push the live-log Python buffer to the OS; optionally fsync to disk.

        Per-write uses flush only (other editors see new lines; cheap). Close /
        idle-sync pass ``to_disk=True`` so a crash loses at most ~1s. StringIO
        test doubles have no fileno — skip fsync there.
        """
        session = self._log_session(session)
        if session is None or not session._log_file:
            return
        fp = session._log_file
        try:
            fp.flush()
        except (OSError, ValueError):
            _log.debug("log flush failed", exc_info=True)
            raise
        if not to_disk:
            self._schedule_log_disk_sync()
            return
        fileno = getattr(fp, "fileno", None)
        if not callable(fileno):
            return
        try:
            os.fsync(fileno())
        except (OSError, ValueError, AttributeError):
            _log.debug("log fsync failed", exc_info=True)

    def _schedule_log_disk_sync(self):
        """Coalesce fsync: high-rate writes share one ~1s disk sync."""
        timer = getattr(self, "_log_sync_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(1000)
            timer.timeout.connect(self._sync_open_log_files)
            self._log_sync_timer = timer
        if not timer.isActive():
            timer.start()

    def _sync_open_log_files(self):
        for session in getattr(self, "_sessions", None) or []:
            if getattr(session, "_log_file", None) is None:
                continue
            try:
                self._flush_log_file(session=session, to_disk=True)
            except (OSError, ValueError):
                _log.debug("idle log fsync failed", exc_info=True)

    def _write_log_block(self, text: str, direction: str, force_new_block: bool,
                         prefix=None):
        """Write one display block into the context session's live log."""
        session = self._session_ctx()
        if session is None or not session._log_file:
            return
        show_ts = self._session_display_flag(
            "show_timestamp",
            self.sw_show_timestamp.isChecked()
            if hasattr(self, "sw_show_timestamp") else False,
            session=session)
        try:
            if force_new_block and show_ts and prefix is None:
                prefix = self._timestamp_prefix(direction)
            pieces, session._log_ends_with_nl = _view_log_pieces(
                text=text, force_new_block=force_new_block,
                log_ends_with_nl=bool(session._log_ends_with_nl),
                prefix=prefix,
                show_timestamp=show_ts)
            session._log_file.write("".join(pieces))
            self._flush_log_file(session=session)
            # _write_log_block already runs in the owning session context.
            # Keep the legacy no-argument call contract used by integrations.
            self._maybe_rotate_log()
        except _LOG_IO_ERRORS as e:
            _log.debug("live log write failed", exc_info=True)
            self.toast(self._t("err_log_write", e=e), error=True)
            self._close_log_file(session=session, toast=False)
            session.log_wanted = False
            if session is self.active_session() and hasattr(self, "sw_log_file"):
                self.sw_log_file.blockSignals(True)
                self.sw_log_file.setChecked(False)
                self.sw_log_file.blockSignals(False)
                if hasattr(self, "_set_log_path_label"):
                    self._set_log_path_label("")


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
        self._save_ms_groups()
        self._rebuild_ms_quick_bar()
        # 分组是整窗共享：所有正在循环的会话同步到新分组序列（空则停）
        self._ms_refresh_running_cycles()

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
        # 分组整窗共享：所有正在循环的会话同步刷新（含后台；空序列则停）
        self._ms_refresh_running_cycles()

    # ----- 多条发送：循环（按每行延时，per-session）-----
    def _build_ms_cycle_seq(self):
        """Checked non-empty items -> cycle send sequence."""
        return _ms_build_cycle_seq(self._ms_active_items())

    def _ms_refresh_running_cycles(self):
        """Rebuild cycle seq for every session currently cycling; stop if empty."""
        seq = self._build_ms_cycle_seq()
        for session in getattr(self, "_sessions", []) or []:
            timer = getattr(session, "_ms_cycle_timer", None)
            if timer is None or not timer.isActive():
                continue
            if not seq:
                self._ms_stop_cycle(session)
            else:
                session._ms_cycle_seq = list(seq)

    def _session_ms_cycle_active(self, session=None) -> bool:
        """True if the given (or context/active) session's multi-send cycle is running."""
        session = session or self._session_ctx() or self.active_session()
        timer = getattr(session, "_ms_cycle_timer", None) if session is not None else None
        return bool(timer is not None and timer.isActive())

    def _ms_toggle_cycle(self):
        session = self.active_session()
        if session is None:
            return
        timer = session._ms_cycle_timer
        if timer.isActive():
            self._ms_stop_cycle(session)
            return
        if self._io_task_busy(exclude=("multi",)):
            self.toast_io_exclusive_busy(exclude=("multi",))
            return
        seq = self._build_ms_cycle_seq()
        if not seq:
            self.toast(self._t("ms_none_checked"), error=True)
            return
        if not self._is_open():
            self.toast(self._t("net_not_open"), error=True)
            return
        session._ms_cycle_seq = seq
        session._ms_cycle_idx = 0
        self._set_ms_cycle_btn(True)
        self._ms_cycle_step_for(session.id)

    def _ms_cycle_step_for(self, sid):
        """Timer callback: TX one multi-send item on the owning session."""
        session = self.find_session(sid)
        if session is None:
            return
        seq = session._ms_cycle_seq or []
        if not seq:
            self._ms_stop_cycle(session)
            return
        if not session.is_open():
            if session is self.active_session():
                self.toast(self._t("net_not_open"), error=True)
            self._ms_stop_cycle(session)
            return
        data, hx, nl, cs, delay = seq[session._ms_cycle_idx % len(seq)]
        delay_ms = max(1, int(delay))
        is_active = session is self.active_session()
        target = None
        if "Server" in str(session._conn_proto or ""):
            target = session.send_target
        with self._with_session(session):
            # Only the engine-owning session pauses its own cycle tick.
            if self._period_tx_blocked(session):
                session._ms_cycle_timer.start(max(50, delay_ms))
                return
            opts = None
            previous_ctx = getattr(self, "_display_context", None)
            if not is_active:
                opts = self._background_display_opts(session)
                self._display_context = dict(opts)
                self._display_context["background"] = True
            try:
                # 循环路径走 _send_with_subst：替换 + 失败回滚 {count}
                # 发送失败(坏数据/写异常等)立即停止，避免每轮都刷错误 toast
                ok = self._send_with_subst(
                    data, hex_mode=hx, newline=nl, checksum=cs,
                    target=target,
                    encoding=(opts or {}).get("encoding") if opts else None,
                    record_macro=False, notify_ui=is_active,
                    feed_window_engines=True)
            finally:
                if not is_active:
                    self._display_context = previous_ctx
        if not ok:
            self._ms_stop_cycle(session)
            return
        session._ms_cycle_idx += 1
        session._ms_cycle_timer.start(delay_ms)

    def _ms_stop_cycle(self, session=None):
        session = session or self._session_ctx() or self.active_session()
        if session is not None:
            timer = getattr(session, "_ms_cycle_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
            session._ms_cycle_seq = []
            session._ms_cycle_idx = 0
        if session is None or session is self.active_session():
            self._set_ms_cycle_btn(False)

    def _ms_stop_all_cycles(self):
        for session in getattr(self, "_sessions", []) or []:
            self._ms_stop_cycle(session)

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

    def open_plot(self, io_graph=False):
        """打开数据波形图（单实例，复用并刷新主题/语言）。
        pyqtgraph 懒导入：缺库时只提示、不影响主程序其余功能。"""
        if getattr(self, "_plot_dlg", None) is None:
            try:
                from ui.plot_dialog import PlotDialog
            except Exception as e:
                self.toast(self._t("plot_need_lib", e=e), error=True)
                return
            self._plot_dlg = PlotDialog(self)
        dlg = self._plot_dlg
        if io_graph and hasattr(dlg, "apply_io_graph_preset"):
            dlg.apply_io_graph_preset()
        elif hasattr(dlg, "leave_io_graph_preset"):
            dlg.leave_io_graph_preset()
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_io_graph(self):
        """Open the plot dialog preset to RX/TX throughput channels (I/O Graph)."""
        self.open_plot(io_graph=True)
        dlg = getattr(self, "_plot_dlg", None)
        if dlg is None:
            return
        try:
            if hasattr(dlg, "feed_named_samples"):
                acc = getattr(self, "_io_stats", None)
                dlg.feed_named_samples([
                    {"tag": "rx_Bps", "value": float(getattr(self, "_rx_rate", 0) or 0)},
                    {"tag": "tx_Bps", "value": float(getattr(self, "_tx_rate", 0) or 0)},
                    {"tag": "rx_pps", "value": float(getattr(acc, "rx_pps", 0) or 0)},
                    {"tag": "tx_pps", "value": float(getattr(acc, "tx_pps", 0) or 0)},
                ])
        except (TypeError, ValueError, RuntimeError, AttributeError):
            _log.debug("open_io_graph seed failed", exc_info=True)

    def _on_active_session_plot_changed(self):
        """Keep the I/O Graph from joining samples from different tabs."""
        dlg = getattr(self, "_plot_dlg", None)
        if (dlg is not None
                and getattr(dlg, "_io_graph_mode", False)
                and hasattr(dlg, "restart_io_graph_series")):
            dlg.restart_io_graph_series()

    def open_script_console(self):
        """打开脚本控制台（单实例，复用并刷新主题/语言）。"""
        if getattr(self, "_script_dlg", None) is None:
            from ui.script_console_dialog import ScriptConsoleDialog
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
        owner = None
        for session in getattr(self, "_sessions", ()):
            if getattr(session, "_script_worker", None) is worker:
                owner = session
                break
        if owner is None or worker.stopping():
            done.set()
            return
        if self._session_ctx() is not owner:
            with self._with_session(owner):
                self._script_send(worker, payload, done, result)
            return
        if (self._script_conn is not None
                and self.conn is not self._script_conn):
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
        except _TX_IO_ERRORS as e:
            _log.debug("script send failed", exc_info=True)
            self.toast(self._t(
                "err_send_failed",
                e=conn_error_tips.format_conn_error_detail(str(e), self._t)),
                error=True)
        finally:
            done.set()

    def _script_begin(self, worker):
        """脚本开跑：接管收流 + 暂停自动应答/Modbus 主机（同自动化序列的独占策略）。"""
        self._script_worker = worker
        self._script_conn = self.conn
        self._io_bind_owner("script")
        # Script owns only this session's wire.  Do not cancel another tab's
        # delayed auto-replies or its window-pinned Modbus master.
        self._ar_reset_buf()
        self._ar_cancel_pending()
        owns_mbm = self._io_session_owns("modbus")
        sched = getattr(self, "_mbm_sched", None)
        if owns_mbm and sched is not None:
            sched.stop()
        # 已发出的 Modbus 请求无法撤回。取消其运行态并隔离一个完整响应超时窗；期间脚本
        # send 会等待、RX 会丢弃，避免旧响应污染脚本。结束后 _mbm_tick 按原开关恢复。
        info = self._mbm_inflight if owns_mbm else None
        to = getattr(self, "_mbm_to", None)
        if owns_mbm and to is not None:
            to.stop()
            self._mbm_inflight = None
            self._mbm_buf = b""
        guard_ms = int(info.get("timeout_ms", self._MBM_TIMEOUT_MS)) if info else 0
        self._script_quiet_until = time.monotonic() + max(0, guard_ms) / 1000.0
        if info is not None and info.get("variant") == "rtu":
            self._mbm_guard_until = max(self._mbm_guard_until, self._script_quiet_until)
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def _script_end(self, worker=None):
        """脚本结束：释放该 worker 所在会话的收流 + 按原开关恢复 Modbus 主机。"""
        if worker is not None:
            owner = None
            for session in getattr(self, "_sessions", ()):
                if getattr(session, "_script_worker", None) is worker:
                    owner = session
                    break
            if owner is None:
                return
            if self._session_ctx() is not owner:
                with self._with_session(owner):
                    self._script_end(worker)
                return
        resume_mbm = bool(getattr(
            self._session_ctx(), "_mbm_enabled", False)) if self._session_ctx() else False
        self._script_worker = None
        self._script_conn = None
        # Window pin is one slot; another tab may still own a running script.
        owners = getattr(self, "_io_owner_sid", None) or {}
        ctx = self._session_ctx()
        if ctx is None or owners.get("script") in (None, getattr(ctx, "id", None)):
            self._io_clear_owner("script")
        self._script_quiet_until = 0.0
        if resume_mbm:
            self._mbm_tick()
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def _script_running(self, session=None) -> bool:
        session = session or self._session_ctx() or self.active_session()
        w = getattr(session, "_script_worker", None) if session is not None else None
        return w is not None and w.isRunning()

    def _script_active(self, session=None) -> bool:
        """worker 已注册即视为占用收发流（含 start 前/结束信号尚未处理的短窗口）。"""
        session = session or self._session_ctx() or self.active_session()
        return getattr(session, "_script_worker", None) is not None if session else False

    def _xfer_active(self, session=None) -> bool:
        """A registered transfer owns its session until GUI-side finalization.

        ``QThread.isRunning()`` may become false before its queued ``sig_done``
        reaches the dialog.  Treating that gap as idle lets project/profile
        replacement delete the captured owner before ``_on_done`` detaches it.
        RX routing still checks ``isRunning()`` separately in
        ``_feed_xfer_if_owned``.
        """
        session = session or self._session_ctx() or self.active_session()
        return getattr(session, "_xfer_worker", None) is not None if session else False

    def _session_period_active(self, session=None) -> bool:
        """True if the given (or context/active) session's period timer is running."""
        session = session or self._session_ctx() or self.active_session()
        timer = getattr(session, "_period_timer", None) if session is not None else None
        if timer is not None:
            return bool(timer.isActive())
        st = getattr(self, "send_timer", None)
        return bool(st is not None and st.isActive())

    def _period_tx_blocked(self, session=None) -> bool:
        """Pause period/cycle TX only on sessions that own a hard engine."""
        session = session or self._session_ctx() or self.active_session()
        if self._seq_running(session):
            return True
        if self._script_active(session):
            return True
        if self._dsl_running(session):
            return True
        if getattr(session, "_device_scan_state", None) is not None:
            return True
        if getattr(session, "_mbm_enabled", False) or getattr(session, "_mbm_inflight", None) is not None:
            return True
        hard = (
            ("transfer", self._xfer_active(session)),
            ("replay", bool(getattr(session, "_replay_on", False))),
        )
        for key, active in hard:
            if active:
                return True
        return False

    _IO_BUSY_ORDER = (
        "script", "sequence", "transfer", "macro", "periodic", "multi",
        "modbus", "replay", "dsl", "recording", "device_scan",
    )
    _IO_HARD_OWNER_KEYS = (
        "script", "sequence", "transfer", "macro", "modbus", "replay",
        "dsl", "recording", "device_scan",
    )

    def _io_bind_owner(self, key, session=None):
        """Pin an exclusive engine to the session that started it."""
        owners = getattr(self, "_io_owner_sid", None)
        if owners is None:
            return
        session = session or self._session_ctx() or self.active_session()
        owners[key] = session.id if session is not None else None

    def _io_clear_owner(self, key):
        owners = getattr(self, "_io_owner_sid", None)
        if owners is not None:
            owners[key] = None

    def _io_reconcile_session_owners(self):
        """Drop pins to replaced tabs and rebind enabled persistent engines."""
        owners = getattr(self, "_io_owner_sid", None)
        if owners is None:
            return
        live_ids = {session.id for session in getattr(self, "_sessions", ())}
        for key, owner_id in tuple(owners.items()):
            if owner_id is not None and owner_id not in live_ids:
                owners[key] = None
        # Restore settings-backed Modbus enable onto the active tab when no
        # session is polling yet (session restore can replace the first tab).
        if getattr(self, "_mbm_on", False) and not any(
                getattr(session, "_mbm_enabled", False)
                for session in getattr(self, "_sessions", ())):
            session = self.active_session()
            if session is not None:
                session._mbm_enabled = True
                session._mbm_wanted = True
                self._io_bind_owner("modbus", session)
        if getattr(self, "_ar_on", False) and not any(
                getattr(session, "_ar_enabled", False)
                for session in getattr(self, "_sessions", ())):
            session = self.active_session()
            if session is not None:
                session._ar_enabled = True

    def _io_owner_session(self, key):
        """Return the concrete pinned owner, never the unbound→active fallback."""
        owners = getattr(self, "_io_owner_sid", None) or {}
        owner_id = owners.get(key)
        if owner_id is None:
            return None
        finder = getattr(self, "find_session", None)
        if callable(finder):
            return finder(owner_id)
        session = self._session_ctx() or self.active_session()
        return session if getattr(session, "id", None) == owner_id else None

    def _io_session_owns(self, key, session=None) -> bool:
        """True if ``session`` currently runs this engine (or owns a window pin)."""
        session = session or self._session_ctx() or self.active_session()
        if session is None:
            return False
        if key == "script":
            return getattr(session, "_script_worker", None) is not None
        if key == "sequence":
            return bool(getattr(session, "_seq_on", False))
        if key == "macro":
            rec = getattr(session, "_macro", None)
            return bool(rec is not None and rec.recording)
        if key == "modbus":
            return bool(getattr(session, "_mbm_enabled", False)
                        or getattr(session, "_mbm_inflight", None) is not None)
        if key == "dsl":
            return bool(getattr(session, "_dsl_ops", None))
        if key == "recording":
            rec = getattr(session, "_recorder", None)
            return bool(rec is not None and rec.recording)
        if key == "device_scan":
            return getattr(session, "_device_scan_state", None) is not None
        if key == "transfer":
            return getattr(session, "_xfer_worker", None) is not None
        if key == "replay":
            return bool(getattr(session, "_replay_on", False))
        owners = getattr(self, "_io_owner_sid", None) or {}
        owner = owners.get(key)
        if owner is None:
            return session.id == getattr(self, "_active_session_id", None)
        return owner == session.id

    def _hard_busy_owned_by(self, session) -> bool:
        """True if ``session`` owns any hard-busy engine (close guard / tab tip).

        Avoids ``_mbm_active()`` so tab styling can run before ``cb_proto`` exists.
        Sequence is session-local; other per-session engines use session runtime.
        """
        if session is None:
            return False
        if bool(getattr(session, "_seq_on", False)):
            return True
        if getattr(session, "_script_worker", None) is not None:
            return True
        macro = getattr(session, "_macro", None)
        if macro is not None and macro.recording:
            return True
        if (getattr(session, "_mbm_enabled", False)
                or getattr(session, "_mbm_inflight", None) is not None):
            return True
        if getattr(session, "_dsl_ops", None):
            return True
        recorder = getattr(session, "_recorder", None)
        if recorder is not None and recorder.recording:
            return True
        if getattr(session, "_device_scan_state", None) is not None:
            return True
        if getattr(session, "_xfer_worker", None) is not None:
            return True
        if bool(getattr(session, "_replay_on", False)):
            return True
        return False

    def _session_mbm_busy(self, session) -> bool:
        """True if ``session`` has Modbus master occupancy (enabled, in-flight, or active)."""
        if session is None:
            return False
        if (getattr(session, "_mbm_enabled", False)
                or getattr(session, "_mbm_inflight", None) is not None):
            return True
        ctx = self._session_ctx() or self.active_session()
        if session is not ctx:
            return False
        fn = getattr(self, "_mbm_active", None)
        if not callable(fn):
            return False
        try:
            return bool(fn())
        except (TypeError, AttributeError):
            return False

    def _io_busy_states(self, exclude=(), session=None):
        """Named exclusive I/O occupancy for ``session`` (default: context/active).

        Per-session engines (script / sequence / MBM / recording / macro / DSL /
        scan / transfer / replay) read that session's fields, so another tab's
        script does not block a sequence here.
        """
        excluded = set(exclude)
        session = session or self._session_ctx() or self.active_session()
        states = {
            "script": self._script_active(session),
            "sequence": bool(getattr(session, "_seq_on", False)) if session else False,
            "transfer": self._xfer_active(session),
            "macro": bool(getattr(getattr(session, "_macro", None), "recording", False)) if session else False,
            "periodic": self._session_period_active(session),
            "multi": self._session_ms_cycle_active(session),
            "modbus": self._session_mbm_busy(session),
            "replay": bool(getattr(session, "_replay_on", False)) if session else False,
            "dsl": self._dsl_running(session),
            "recording": bool(getattr(getattr(session, "_recorder", None), "recording", False)) if session else False,
            "device_scan": getattr(session, "_device_scan_state", None) is not None,
        }
        return {name: active for name, active in states.items()
                if name not in excluded}

    def _io_task_busy(self, exclude=()) -> bool:
        """Shared active I/O task table used by exclusive start gates."""
        return any(self._io_busy_states(exclude).values())

    def _io_busy_task_names(self, exclude=()):
        states = self._io_busy_states(exclude)
        return [name for name in self._IO_BUSY_ORDER if states.get(name)]

    def _io_busy_message(self, key, exclude=()):
        """Localize exclusive-busy toast with the concrete occupying task list."""
        names = self._io_busy_task_names(exclude=exclude)
        if names:
            sep = self._t("io_task_sep")
            tasks = sep.join(self._t("io_task_%s" % name) for name in names)
        else:
            tasks = self._t("io_task_unknown")
        return self._t(key, tasks=tasks)

    def toast_io_exclusive_busy(self, exclude=()):
        self.toast(self._io_busy_message("io_exclusive_busy", exclude=exclude),
                   error=True)

    def toast_session_busy(self, exclude=("periodic", "multi")):
        self.toast(self._io_busy_message("session_busy", exclude=exclude),
                   error=True)

    def toast_session_leave_stopped(self, stopped):
        """Informational toast after leave-safe window tasks were auto-stopped."""
        if not stopped:
            return
        sep = self._t("io_task_sep")
        tasks = sep.join(self._t("io_task_%s" % name) for name in stopped)
        self.toast(self._t("session_leave_stopped", tasks=tasks))

    def _manual_send_blocked(self, allow_running_dsl=False, session=None) -> bool:
        """Block manual TX on sessions that own an exclusive engine."""
        session = session or self._session_ctx() or self.active_session()
        if self._seq_running(session):
            return True
        if self._script_active(session):
            return True
        if self._dsl_running(session) and not allow_running_dsl:
            return True
        if getattr(session, "_device_scan_state", None) is not None:
            return True
        if getattr(session, "_mbm_enabled", False) or getattr(session, "_mbm_inflight", None) is not None:
            return True
        if self._xfer_active(session):
            return True
        if bool(getattr(session, "_replay_on", False)):
            return True
        return False

    def _script_start_blocked(self) -> bool:
        """Script cannot start alongside other exclusive RX/TX tasks; Modbus is paused by _script_begin."""
        return self._io_task_busy(exclude=("script", "modbus"))

    def _macro_start_blocked(self) -> bool:
        """Reject macro start while other exclusive tasks are active."""
        return self._io_task_busy(exclude=("macro",))

    def _xfer_start_blocked(self) -> bool:
        """File transfer is one worker per session; another tab may start its own.

        Occupancy for *starting* transfer only sees this session, matching
        script / sequence / Modbus.  A live worker on this tab still blocks a
        second Start so it cannot detach mid-flight.
        """
        if self._xfer_active():
            return True
        return self._io_task_busy(exclude=("transfer",))

    def bind_macro_owner(self, active=True):
        """Script console calls this when macro record starts/stops."""
        if active:
            self._io_bind_owner("macro")
        else:
            self._io_clear_owner("macro")
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def bind_recording_owner(self, active=True):
        """Rec/replay dialog calls this when stream recording starts/stops."""
        if active:
            self._io_bind_owner("recording")
        else:
            self._io_clear_owner("recording")
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def _macro_record_tx(self, data):
        """宏录制的 TX 采集判定（唯一入口）：只录「用户手动发」。三类排除——
        脚本自己 send 的（否则录到脚本自身、循环自指）；自动应答/Modbus 从机的回复
        （也走 _send_text，靠 _ar_in_flight 识别，不是用户动作）；未在录制。
        终端模式在 _terminal_send 成功后也调用本入口。抽成方法是为让测试与生产共用同一判定，
        条件改了测试自动跟着变。"""
        script_here = (self._script_running()
                       and self._io_session_owns("script")
                       and (self._script_conn is None
                            or self.conn is self._script_conn))
        if (self._macro.recording and not script_here
                and not self._seq_running() and not self._ar_in_flight
                and self._io_session_owns("macro")):
            self._macro.on_tx(data)

    def _record_stream_tx(self, data, source=None):
        """数据录制的 TX 采集：录线路上真实发出的字节（含自动应答/Modbus 回复，
        因为录的是「线路现场」而非「用户意图」——这点与宏录制相反）。"""
        if (self._recorder.recording
                and self._io_session_owns("recording")):
            extra = None
            if (source == "__all__"
                    and getattr(self, "_conn_proto", None) == PROTO_TCP_SERVER
                    and self.conn is not None):
                successful = getattr(self.conn, "last_send_client_keys", None)
                if callable(successful):
                    extra = successful()
                elif hasattr(self.conn, "client_keys"):
                    extra = self.conn.client_keys()
            self._recorder.on_tx(data, source=source, peers=extra)
        self._triggers_feed(data, "tx", source=source)  # TCP Server 按发送目标隔离流尾巴

    def _triggers_stream_key(self, direction, source=None):
        """Isolate trigger decoder/tail state per session + direction + peer."""
        session = self._session_ctx() or self.active_session()
        sid = getattr(session, "id", None)
        peer = (source if getattr(self, "_conn_proto", None) == PROTO_TCP_SERVER
                else None)
        return (sid, direction, peer)

    # ---------------- 触发告警：命中规则 → 响铃 / 托盘通知 / 数据区打标 ----------------
    def _load_triggers(self):
        items = _cfg_parse_json_list(self.settings.value("triggers", ""))
        items, migrated = triggers.migrate_legacy_webhook_permissions(items or [])
        clean = triggers.sanitize_list(items)
        if migrated:
            # 旧版允许 HTTP / 局域网 webhook，升级后不能静默停发。只迁移本机已有配置；
            # 当前版新建规则始终显式写入 False，仍保持“公网 HTTPS”安全默认。
            self.settings.setValue("triggers", json.dumps(clean, ensure_ascii=False))
            self.settings.sync()
        return clean

    def _save_triggers(self):
        """落盘 + 让引擎换上新规则（换规则会清命中统计，故调用方已做编辑去抖）。"""
        self.settings.setValue("triggers", json.dumps(self._triggers, ensure_ascii=False))
        self._trigger_engine.set_rules(self._triggers)
        self._refresh_workspace_statuses()
        # 新规则只观察生效后的数据；不能拿旧规则时期留下的半字符/尾巴与下一块拼接。
        self._reset_trigger_decoders()

    def _triggers_feed(self, data, direction, source=None, session=None):
        """把一包数据喂给告警引擎并执行命中动作。收发路径都会调，故先做最省的短路判断。"""
        eng = getattr(self, "_trigger_engine", None)
        if eng is None or not eng.active():
            return
        data = bytes(data)
        # 串口/TCP/虚拟连接是连续字节流，需要跨底层回调拼半字符和关键字；UDP/组播
        # 每次回调就是完整数据报，跨报文拼接会制造线路上从未出现过的假关键字。
        carry = getattr(self, "_conn_proto", None) not in (PROTO_UDP, PROTO_UDP_MULTICAST)
        stream_key = self._triggers_stream_key(direction, source)
        session = session or self._session_ctx() or self.active_session()
        sid = getattr(session, "id", None) if session is not None else None
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
                                  new_data_at=new_data_at, new_text_at=new_text_at,
                                  sid=sid):
            self._fire_trigger(idx, rule, direction, session=session)

    def _decode_for_triggers(self, data, stream_key, carry=True):
        """触发引擎的增量解码：与数据区**同一套编码规则**（Auto 走 UTF-8 优先 / GBK 回退），
        但用自己的缓冲。

        为什么不直接复用 _decode_rx：①它的缓冲属于显示路径，共享会互相吃掉对方留存的半个
        多字节字符；②触发要在 HEX / 转储 / 数值 等**任何显示模式**下都能按文本匹配，不能
        绑在文本显示那条路上。每条来源流各持一份状态 —— 混用会让不同客户端或 RX/TX
        的半个字符拼在一起，两边都乱。UDP 数据报 carry=False，每包独立解码。"""
        if not isinstance(stream_key, tuple):  # 兼容内部测试/旧调用传 "rx"、"tx"
            stream_key = self._triggers_stream_key(stream_key, None)
        elif len(stream_key) == 2:
            stream_key = (getattr(self._session_ctx() or self.active_session(),
                                  "id", None),) + stream_key
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
        codec_by_key = self._trg_dec_codec
        if not isinstance(codec_by_key, dict):
            codec_by_key = {}
            self._trg_dec_codec = codec_by_key
        if codec != "auto":
            dec = self._trg_dec.get(stream_key)
            if dec is None or codec_by_key.get(stream_key) != codec:
                codec_by_key[stream_key] = codec
                try:
                    dec = codecs.getincrementaldecoder(codec)(errors="replace")
                except LookupError:
                    return data.decode("latin-1")  # 同 _decode_rx 的兜底
                self._trg_dec[stream_key] = dec
            return dec.decode(data, final=False)
        text, bufs[stream_key] = self._decode_auto_chunk(bufs.get(stream_key, b""), data)
        return text

    def _reset_trigger_decoders(self, session=None):
        """数据流断点 / 换编码：旧的半个字符与跨块尾巴对新数据都没意义，清掉重来。

        ``session=None`` 清全部流（换规则 / 切配置）。传入会话时只清该标签，
        避免清接收区或改编码时把后台标签的半字符拼掉。
        """
        names = ("_trg_dec_buf", "_trg_dec", "_trg_dec_codec",
                 "_trg_ansi_pending", "_trg_tail_bytes", "_trg_tail_text")
        if session is None:
            for name in names:
                setattr(self, name, {})
            return
        sid = getattr(session, "id", None)
        for name in names:
            states = getattr(self, name, None)
            if not isinstance(states, dict):
                continue
            for key in list(states):
                if isinstance(key, tuple) and key and key[0] == sid:
                    states.pop(key, None)

    # webhook / run_cmd 状态挂在 TriggerActionRunner 上；测试仍读窗口上的旧名字。
    @property
    def _trg_action_lock(self):
        return self._trg_actions.lock

    @property
    def _trg_action_busy(self):
        return self._trg_actions.busy

    @_trg_action_busy.setter
    def _trg_action_busy(self, value):
        self._trg_actions.busy = value

    @property
    def _trg_action_dropped(self):
        return self._trg_actions.dropped

    @_trg_action_dropped.setter
    def _trg_action_dropped(self, value):
        self._trg_actions.dropped = value

    @property
    def _trg_procs(self):
        return self._trg_actions.procs

    @_trg_procs.setter
    def _trg_procs(self, value):
        self._trg_actions.procs = value

    @property
    def _trg_launching(self):
        return self._trg_actions.launching

    @_trg_launching.setter
    def _trg_launching(self, value):
        self._trg_actions.launching = value

    @property
    def _trg_stopping(self):
        return self._trg_actions.stopping

    @_trg_stopping.setter
    def _trg_stopping(self, value):
        self._trg_actions.stopping = value

    def _fire_trigger(self, idx, rule, direction, session=None):
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
                owner = session or self._session_ctx() or self.active_session()
                term_on = self._session_display_flag(
                    "terminal_on",
                    bool(getattr(self, "_terminal_on", False)),
                    session=owner)
                if term_on:
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
            owner = session or self._session_ctx() or self.active_session()
            sid = getattr(owner, "id", None) if owner is not None else None
            hits = int(self._trigger_engine.hits(idx, sid=sid))
        except Exception:
            hits = 0
        bus = getattr(self, "_event_bus", None)
        if bus is not None:
            bus.publish(TOPIC_TRIGGER_HIT, {
                "rule": rule,
                "name": name,
                "direction": direction,
                "hits": hits,
            })

    @staticmethod
    def _is_private_url(url):
        """True if URL host is private/loopback/link-local."""
        return _trg_is_private_url(url)

    def _trg_run_webhook(self, rule, name, direction, hits):
        """测试兼容入口；生产路径是 EventBus → TriggerActionRunner。"""
        return self._trg_actions.run_webhook(rule, name, direction, hits)

    @staticmethod
    def _trg_shell_value(value):
        """Quote a placeholder value so it stays shell-inert text."""
        return _trg_shell_quote(value)

    def _trg_run_cmd(self, rule, name, direction, hits):
        """测试兼容入口；生产路径是 EventBus → TriggerActionRunner。"""
        return self._trg_actions.run_cmd(rule, name, direction, hits)

    @staticmethod
    def _trg_kill_proc(proc):
        return _trg_kill_proc_impl(proc)

    def _trg_stop_procs(self):
        """退出前终止仍在跑的外部程序动作；一旦调用就不再放行新动作。"""
        return self._trg_actions.stop_procs()

    def _trg_dropped_actions(self):
        """因并发上限被丢弃的动作次数。计数器由工作线程递增，读写都走锁。"""
        return self._trg_actions.dropped_actions()

    def _trg_reset_dropped(self):
        return self._trg_actions.reset_dropped()

    def _trg_spawn_action(self, worker):
        """Run a trigger action off the GUI thread, capped in flight."""
        return self._trg_actions.spawn(worker)

    def open_triggers(self):
        """打开触发告警对话框（单实例、非模态）。"""
        dlg = getattr(self, "_triggers_dlg", None)
        if dlg is None:
            from ui.triggers_dialog import TriggersDialog
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

    def _replay_send_target(self):
        """回放「驱动真实 TX」：把录制的 TX 字节原样经当前连接发出。

        不走发送框的 HEX/换行/校验和编码，避免二次加工。TCP Server 无单客户端时返回 None。
        回调每次发送时重新取 self.conn，避免确认框期间连接被关掉后仍持有旧引用。
        """
        session = self._session_ctx() or self.active_session()
        conn = self.conn
        if conn is None or not getattr(conn, "is_open", False):
            return None
        if isinstance(conn, TcpServerConn):
            target = self._send_target()
            if not target or target == "__all__":
                return None

        owner_id = getattr(session, "id", None)

        def _send(data):
            owner = self.find_session(owner_id) if owner_id is not None else session
            if owner is None:
                raise RuntimeError("connection closed")
            with self._with_session(owner):
                live = self.conn
                if live is None or not getattr(live, "is_open", False):
                    raise RuntimeError("connection closed")
                payload = bytes(data or b"")
                if not payload:
                    return 0
                target = None
                if isinstance(live, TcpServerConn):
                    target = self._send_target()
                    if not target or target == "__all__":
                        raise RuntimeError("tcp server needs a single client target")
                n = live.send(payload, target) if target is not None else live.send(payload)
                if n is None:
                    return 0
                sent = int(n)
                # Partial serial/TCP writes must not count as "sent as-is".
                if sent < len(payload):
                    return 0
                return sent

        return _send

    def _replay_conn_summary(self):
        """Short connection label for the drive-TX confirm dialog."""
        proto = getattr(self, "_conn_proto", None) or (
            self.cb_proto.currentText() if hasattr(self, "cb_proto") else "")
        if proto == PROTO_SERIAL:
            port = ""
            if hasattr(self, "cb_port"):
                port = (self.cb_port.currentText() or "").strip()
            return ("%s %s" % (proto, port or "?")).strip()
        if proto == PROTO_TCP_CLIENT:
            return "%s %s:%s" % (
                proto,
                (self.ed_remote_ip.text() or "").strip(),
                (self.ed_remote_port.text() or "").strip())
        if proto == PROTO_TCP_SERVER:
            return "%s :%s → %s" % (
                proto,
                (self.ed_local_port.text() or "").strip(),
                self._send_target() or "?")
        if proto == PROTO_UDP:
            return "%s %s:%s" % (
                proto,
                (self.ed_remote_ip.text() or "").strip(),
                (self.ed_remote_port.text() or "").strip())
        if proto == PROTO_UDP_MULTICAST:
            return "%s %s:%s" % (
                proto,
                (self.ed_group.text() or "").strip(),
                (self.ed_local_port.text() or "").strip())
        if proto == PROTO_VIRTUAL:
            return str(proto)
        if proto == PROTO_BLE:
            name = ""
            addr = ""
            if hasattr(self, "ed_ble_name"):
                name = (self.ed_ble_name.text() or "").strip()
            if hasattr(self, "ed_ble_address"):
                addr = (self.ed_ble_address.text() or "").strip()
            return ("%s %s" % (proto, name or addr or "?")).strip()
        if proto == PROTO_RTT:
            dev = ""
            if hasattr(self, "cb_rtt_device"):
                dev = (self.cb_rtt_device.currentText() or "").strip()
            return ("%s %s" % (proto, dev or "?")).strip()
        return str(proto or "?")

    def _recorder_link_snapshot(self):
        """Capture TCP/UDP endpoints for PCAP export.

        Supports TCP Client, TCP Server (one flow per client, including
        broadcast), UDP with a fixed remote, and UDP Multicast (group as
        remote). Returns None when out of scope (serial, UDP without remote, …).
        Wildcard bind addresses (0.0.0.0 / ::) are resolved to a concrete host
        IPv4 via route table / local NIC list; failure refuses export.
        """
        from record.pcap_export import can_export_link, as_unicast_peer
        proto = getattr(self, "_conn_proto", None) or self.cb_proto.currentText()
        remote_ip = ""
        remote_port = None
        local_ip = ""
        local_port = None
        peers = []

        if proto == PROTO_TCP_CLIENT:
            remote_ip = (self.ed_remote_ip.text() or "").strip()
            remote_port = self._parse_port(self.ed_remote_port.text())
            conn = self.conn
            ep = conn.local_endpoint() if hasattr(conn, "local_endpoint") else None
            if ep:
                local_ip, local_port = ep
        elif proto == PROTO_TCP_SERVER:
            local_ip = (self.cb_local_ip.currentText() or "").strip()
            local_port = self._parse_port(self.ed_local_port.text())
            conn = self.conn
            if conn is not None:
                bp = getattr(conn, "bound_port", None)
                if callable(bp):
                    bp = bp()
                if isinstance(bp, int) and bp:
                    local_port = bp
                keys = conn.client_keys() if hasattr(conn, "client_keys") else ()
                for key in keys or ():
                    peer = as_unicast_peer(key)
                    if peer is not None and peer not in peers:
                        peers.append(peer)
            target = self._send_target()
            if target and target != "__all__":
                peer = as_unicast_peer(target)
                if peer is not None:
                    remote_ip, remote_port = peer
                    if peer not in peers:
                        peers.append(peer)
            elif len(peers) == 1:
                remote_ip, remote_port = peers[0]
        elif proto == PROTO_UDP:
            # Single-peer only: require "指定远程" with a concrete peer.
            if not self.sw_udp_remote.isChecked():
                return None
            remote_ip = (self.ed_remote_ip.text() or "").strip()
            remote_port = self._parse_port(self.ed_remote_port.text())
            local_ip = (self.cb_local_ip.currentText() or "").strip()
            local_port = self._parse_port(self.ed_local_port.text())
            conn = self.conn
            ep = conn.local_endpoint() if hasattr(conn, "local_endpoint") else None
            if ep:
                # Prefer OS-bound port (port 0) over the UI placeholder.
                lip, lport = ep
                if lip and lip not in ("0.0.0.0", "::"):
                    local_ip = lip
                if lport:
                    local_port = lport
        elif proto == PROTO_UDP_MULTICAST:
            remote_ip = (self.ed_group.text() or "").strip()
            remote_port = self._parse_port(self.ed_local_port.text())
            local_ip = (self.cb_local_ip.currentText() or "").strip()
            local_port = remote_port
        else:
            return None

        local_ip = resolve_export_local_ipv4(
            local_ip, remote_ip=remote_ip, remote_port=remote_port)
        if not local_ip:
            return None

        link = {
            "proto": proto,
            "local_ip": local_ip,
            "local_port": local_port,
            "remote_ip": remote_ip or None,
            "remote_port": remote_port,
        }
        if peers:
            link["peers"] = [[ip, port] for ip, port in peers]
        return link if can_export_link(link) else None

    def _replay_begin(self, *, drive_tx=False):
        """Mark replay busy on this session. drive_tx also suppresses Modbus master + auto-reply TX."""
        self._replay_on = True
        self._io_bind_owner("replay")
        self._replay_drive_tx = bool(drive_tx)
        # Stop any in-flight Modbus poll schedule so it cannot race with replay TX/RX.
        if (hasattr(self, "_mbm_restart")
                and self._io_session_owns("modbus")):
            self._mbm_restart()
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def _replay_end(self):
        resume_mbm = self._io_session_owns("modbus")
        self._replay_on = False
        self._replay_drive_tx = False
        if not any(getattr(s, "_replay_on", False)
                   for s in getattr(self, "_sessions", ()) or ()):
            self._io_clear_owner("replay")
        # Resume Modbus schedule if it was still enabled.
        if hasattr(self, "_mbm_restart") and resume_mbm:
            self._mbm_restart()
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def open_rec_replay(self):
        """打开数据录制 / 回放（单实例，复用并刷新主题/语言）。"""
        if getattr(self, "_rr_dlg", None) is None:
            from ui.rec_replay_dialog import RecReplayDialog
            self._rr_dlg = RecReplayDialog(self)
        dlg = self._rr_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        sync = getattr(dlg, "sync_session", None)
        if callable(sync):
            sync()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_rec_diff(self):
        """打开会话比较（单实例，复用并刷新主题/语言）。

        纯离线工具：只读两个 .ctrec 文件、不碰连接，因此不进 _io_task_busy 占用表。
        """
        if getattr(self, "_rd_dlg", None) is None:
            from ui.rec_diff_dialog import RecDiffDialog
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
            from ui.snippets_dialog import SnippetsDialog
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
            from ui.send_history_dialog import SendHistoryDialog
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
            "serial_dtr": self.sw_dtr.isChecked() if hasattr(self, "sw_dtr")
            else self.settings.value("serial_dtr", True, type=bool),
            "serial_rts": self.sw_rts.isChecked() if hasattr(self, "sw_rts")
            else self.settings.value("serial_rts", True, type=bool),
            "net_local_ip": self.cb_local_ip.currentText(),
            "net_local_port": self.ed_local_port.text(),
            "net_remote_ip": self.ed_remote_ip.text(),
            "net_remote_port": self.ed_remote_port.text(),
            "net_use_remote": self.sw_udp_remote.isChecked(),
            "net_group_addr": self.ed_group.text(),
            "vconn_loopback": self.sw_vconn_loop.isChecked(),
            "auto_reconnect": getattr(
                self, "_ui_auto_reconnect",
                self.settings.value("auto_reconnect", True, type=bool)),
            "ble_address": (self.ed_ble_address.text()
                            if hasattr(self, "ed_ble_address") else ""),
            "ble_name": (self.ed_ble_name.text()
                         if hasattr(self, "ed_ble_name") else ""),
            "ble_profile": (self.cb_ble_profile.currentData() or "custom"
                            if hasattr(self, "cb_ble_profile") else "fff0"),
            "ble_service_uuid": (self.ed_ble_service.text()
                                 if hasattr(self, "ed_ble_service") else ""),
            "ble_write_uuid": (self.ed_ble_write.text()
                               if hasattr(self, "ed_ble_write") else ""),
            "ble_notify_uuid": (self.ed_ble_notify.text()
                                if hasattr(self, "ed_ble_notify") else ""),
            "ble_write_mode": (
                self.cb_ble_write_mode.currentData() or "auto"
                if hasattr(self, "cb_ble_write_mode") else "auto"),
            "rtt_device": (self.cb_rtt_device.currentText()
                           if hasattr(self, "cb_rtt_device") else ""),
            "rtt_interface": (self.cb_rtt_interface.currentText()
                              if hasattr(self, "cb_rtt_interface") else ""),
            "rtt_speed": self._rtt_speed_text(),
            "rtt_address": (self.ed_rtt_address.text()
                            if hasattr(self, "ed_rtt_address") else ""),
            "rtt_channel": (self.cb_rtt_channel.currentData()
                            if hasattr(self, "cb_rtt_channel") else 0),
            "rtt_probe": self._rtt_probe_text(),
            "rtt_reset": (self.sw_rtt_reset.isChecked()
                          if hasattr(self, "sw_rtt_reset") else False),
        })

    def _apply_connection_fields(self, fields, persist_defaults=False):
        provided_fields = fields if isinstance(fields, dict) else {}
        fields = connection_presets.capture_fields(provided_fields)
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
        if hasattr(self, "ed_ble_address"):
            from transport import ble_uuid
            self.ed_ble_address.setText(str(fields.get("ble_address") or ""))
            self.ed_ble_name.setText(str(fields.get("ble_name") or ""))
            self.ed_ble_service.setText(str(fields.get("ble_service_uuid") or ""))
            self.ed_ble_write.setText(str(fields.get("ble_write_uuid") or ""))
            self.ed_ble_notify.setText(str(fields.get("ble_notify_uuid") or ""))
            if hasattr(self, "cb_ble_write_mode"):
                mode = ble_uuid.normalize_write_mode(fields.get("ble_write_mode"))
                midx = self.cb_ble_write_mode.findData(mode)
                self.cb_ble_write_mode.blockSignals(True)
                self.cb_ble_write_mode.setCurrentIndex(midx if midx >= 0 else 0)
                self.cb_ble_write_mode.blockSignals(False)
            pid = ble_uuid.normalize_profile(fields.get("ble_profile"))
            idx = self.cb_ble_profile.findData(pid)
            self.cb_ble_profile.blockSignals(True)
            self.cb_ble_profile.setCurrentIndex(idx if idx >= 0 else self.cb_ble_profile.findData(
                ble_uuid.PROFILE_CUSTOM))
            self.cb_ble_profile.blockSignals(False)
        if hasattr(self, "cb_rtt_device"):
            from transport import rtt_io
            self.cb_rtt_device.blockSignals(True)
            self.cb_rtt_device.setCurrentText(str(fields.get("rtt_device") or ""))
            self.cb_rtt_device.blockSignals(False)
            if hasattr(self, "cb_rtt_interface"):
                self.cb_rtt_interface.setCurrentText(rtt_io.normalize_interface(
                    fields.get("rtt_interface")))
            speed = rtt_io.parse_speed(fields.get("rtt_speed"))
            if speed is not None:
                self._set_rtt_speed_text(speed)
            if hasattr(self, "ed_rtt_address"):
                # 地址框支持“起点+范围”；预设回填必须保留完整表达式。
                self.ed_rtt_address.setText(str(fields.get("rtt_address") or ""))
            if hasattr(self, "cb_rtt_channel"):
                ch = rtt_io.normalize_channel(fields.get("rtt_channel"))
                cidx = self.cb_rtt_channel.findData(ch if ch is not None else 0)
                self.cb_rtt_channel.blockSignals(True)
                self.cb_rtt_channel.setCurrentIndex(cidx if cidx >= 0 else 0)
                self.cb_rtt_channel.blockSignals(False)
            if hasattr(self, "cb_rtt_probe"):
                self._set_rtt_probe_text(fields.get("rtt_probe"))
            if hasattr(self, "sw_rtt_reset"):
                self.sw_rtt_reset.blockSignals(True)
                self.sw_rtt_reset.setChecked(
                    str(fields.get("rtt_reset", "")).lower()
                    not in ("", "0", "false", "no", "none"))
                self.sw_rtt_reset.blockSignals(False)
        dtr = bool(fields["serial_dtr"] if "serial_dtr" in provided_fields else
                   self.settings.value("serial_dtr", True, type=bool))
        rts = bool(fields["serial_rts"] if "serial_rts" in provided_fields else
                   self.settings.value("serial_rts", True, type=bool))
        auto_reconnect = bool(
            fields["auto_reconnect"] if "auto_reconnect" in provided_fields else
            self.settings.value("auto_reconnect", True, type=bool))
        self._ui_auto_reconnect = auto_reconnect
        if persist_defaults:
            self.settings.setValue("serial_dtr", dtr)
            self.settings.setValue("serial_rts", rts)
            self.settings.setValue("auto_reconnect", auto_reconnect)
            session = self.active_session()
            if session is not None:
                session.conn_fields = dict(session.conn_fields or {})
                session.conn_fields.update({
                    "serial_dtr": dtr,
                    "serial_rts": rts,
                    "auto_reconnect": auto_reconnect,
                })
        if hasattr(self, "sw_dtr"):
            self.sw_dtr.blockSignals(True)
            self.sw_dtr.setChecked(dtr, animate=False)
            self.sw_dtr.blockSignals(False)
        if hasattr(self, "sw_rts"):
            self.sw_rts.blockSignals(True)
            self.sw_rts.setChecked(rts, animate=False)
            self.sw_rts.blockSignals(False)
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
        self._apply_connection_fields(preset, persist_defaults=True)
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

    def _build_themed_text_input_dialog(self, title, prompt, default_text=""):
        """Build the shared themed single-line text prompt.

        Avoid QInputDialog: on Windows its QDialogButtonBox often keeps the
        native chrome, so OK/Cancel look unlike MsPrimaryBtn / MsGhostBtn.
        """
        ok_text = {"zh": "确定", "en": "OK", "zh_tw": "確定"}.get(
            self._lang, "OK")
        cancel_text = {"zh": "取消", "en": "Cancel", "zh_tw": "取消"}.get(
            self._lang, "Cancel")
        c = chrome_for(self._theme_id())

        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        dlg.setMinimumWidth(380)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        lbl = QLabel(prompt)
        lbl.setWordWrap(True)
        root.addWidget(lbl)

        ed = QLineEdit(default_text or "")
        ed.setObjectName("ThemedTextInput")
        root.addWidget(ed)
        dlg._ed = ed

        def _text_value():
            return dlg._ed.text()

        dlg.textValue = _text_value  # same API as former QInputDialog

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        btn_ok = QPushButton(ok_text)
        btn_ok.setObjectName("MsPrimaryBtn")
        btn_ok.setMinimumHeight(32)
        btn_ok.setMinimumWidth(88)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel = QPushButton(cancel_text)
        btn_cancel.setObjectName("MsGhostBtn")
        btn_cancel.setMinimumHeight(32)
        btn_cancel.setMinimumWidth(88)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        root.addLayout(btn_row)

        ed.returnPressed.connect(dlg.accept)
        dlg.setStyleSheet(localize_qss(f"""
        QDialog {{
            background-color: {c['window_bg']};
            color: {c['text']};
        }}
        QLabel {{
            color: {c['text']}; background: transparent;
            font-family: 'Segoe UI'; font-size: 12px; font-weight: 500;
        }}
        QLineEdit#ThemedTextInput {{
            background-color: {c['input_bg']}; color: {c['text']};
            border: 1px solid {c['separator']}; border-radius: 7px;
            min-height: 22px; padding: 5px 9px;
            selection-background-color: {c['accent']};
        }}
        QLineEdit#ThemedTextInput:focus {{
            background-color: {c['input_focus_bg']};
            border-color: {c['accent']};
        }}
        QPushButton#MsPrimaryBtn {{
            background-color: {c['accent']}; color: white; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 13px;
            font-weight: 600; padding: 6px 14px;
        }}
        QPushButton#MsPrimaryBtn:hover {{ background-color: {c['accent_hover']}; }}
        QPushButton#MsPrimaryBtn:pressed {{ background-color: {c['accent_pressed']}; }}
        QPushButton#MsGhostBtn {{
            background-color: {c['ghost_bg']}; color: {c['text']}; border: 0px;
            border-radius: 9px; font-family: 'Segoe UI'; font-size: 13px;
            font-weight: 500; padding: 6px 14px;
        }}
        QPushButton#MsGhostBtn:hover {{ background-color: {c['ghost_hover']}; }}
        """))
        QTimer.singleShot(
            0, lambda d=dlg: _set_win_titlebar_dark(
                d, self._theme().get("mode") == "dark"))
        return dlg

    def _build_connection_preset_name_dialog(self, default_name=""):
        return self._build_themed_text_input_dialog(
            self._t("cpreset_save_title"), self._t("cpreset_save_prompt"),
            default_name or self._t("cpreset_new_name"))

    def save_connection_preset_from_ui(self, prompt_name=True, name=None, note=""):
        fields = self._capture_connection_fields()
        if prompt_name and not name:
            cur_id = self.cb_conn_preset.currentData() if hasattr(self, "cb_conn_preset") else None
            default_name = ""
            if cur_id:
                cur = connection_presets.find_by_id(self._connection_presets, cur_id)
                if cur:
                    default_name = cur.get("name", "")
            dlg = self._build_connection_preset_name_dialog(default_name)
            ok = dlg.exec_() == QDialog.Accepted
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
            from ui.connection_presets_dialog import ConnectionPresetsDialog
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
            from ui.dashboard_dialog import DashboardDialog
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
            from ui.frame_dialog import FrameParseDialog
            self._frame_dlg = FrameParseDialog(self)
        dlg = self._frame_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        dlg.sync_highlight()      # 勾选态跟随主窗当前 _proto_hl_on
        dlg._load_stream_widgets()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ----- 自动应答 -----
    def open_auto_reply(self):
        """打开自动应答配置（单实例，复用并刷新主题/语言）。"""
        if getattr(self, "_ar_dlg", None) is None:
            from ui.auto_reply_dialog import AutoReplyDialog
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
        """翻转当前会话的自动应答开关：落盘 + 按钮高亮刷新 + 同步对话框 checkbox（若开着）+ toast。"""
        new_value = not self._session_ar_on()
        self._set_autoreply_enabled(new_value)
        self.toast(self._t("ar_toast_on" if self._session_ar_on() else "ar_toast_off"))

    def _session_ar_on(self, session=None) -> bool:
        """True if this (or the given) session's auto-reply switch is on."""
        session = session or self._session_ctx() or self.active_session()
        return bool(getattr(session, "_ar_enabled", False)) if session else False

    def _set_autoreply_enabled(self, enabled):
        """设置当前会话的自动应答开关；开启时关闭本会话 Modbus 主机。"""
        enabled = bool(enabled)
        if enabled and getattr(self, "_device_scan_state", None) is not None:
            self.toast_io_exclusive_busy()
            if getattr(self, "_ar_dlg", None) is not None:
                cb = self._ar_dlg.cb_enable
                cb.blockSignals(True)
                cb.setChecked(bool(self._session_ar_on()))
                cb.blockSignals(False)
            return
        session = self._session_ctx() or self.active_session()
        if enabled and (getattr(session, "_mbm_enabled", False) if session is not None
                        else getattr(self, "_mbm_on", False)):
            self._set_mbm_enabled(False)
        if session is not None:
            session._ar_enabled = enabled
        self._ar_on = enabled
        self.settings.setValue("autoreply_on", enabled)
        # Per-session switch: only this tab's half-packet / SM pending is stale.
        self._ar_reset_buf()
        self._ar_reset_state()
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
            self.toast_io_exclusive_busy()
            if getattr(self, "_mbm_dlg", None) is not None:
                cb = self._mbm_dlg.cb_enable
                cb.blockSignals(True)
                cb.setChecked(bool(scan_state.get("old_on", False)))
                cb.blockSignals(False)
            return
        if enabled and (self.send_timer.isActive() or self._session_ms_cycle_active()):
            self.toast_io_exclusive_busy()
            if getattr(self, "_mbm_dlg", None) is not None:
                cb = self._mbm_dlg.cb_enable
                cb.blockSignals(True)
                cb.setChecked(bool(self._mbm_on))
                cb.blockSignals(False)
            return
        session = self._session_ctx() or self.active_session()
        if enabled and self._session_ar_on(session):
            self._set_autoreply_enabled(False)
        self._mbm_on = enabled
        if session is not None:
            session._mbm_enabled = enabled
            session._mbm_wanted = enabled
        if enabled:
            self._io_bind_owner("modbus")
        self.settings.setValue("modbus_master_on", enabled)
        self.settings.sync()
        if getattr(self, "_mbm_dlg", None) is not None:
            cb = self._mbm_dlg.cb_enable
            cb.blockSignals(True)
            cb.setChecked(enabled)
            cb.blockSignals(False)
        self._mbm_restart()
        if not enabled:
            other = next((s for s in getattr(self, "_sessions", ()) or ()
                          if s is not session
                          and getattr(s, "_mbm_wanted", False)), None)
            if other is not None:
                self._io_bind_owner("modbus", other)
            else:
                self._io_clear_owner("modbus")
        self._refresh_workspace_statuses()
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

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

    def _seq_running(self, session=None):
        if session is not None:
            return bool(getattr(session, "_seq_on", False))
        return bool(getattr(self, "_seq_on", False))

    def _seq_ctx_id(self):
        """Session id for deferred sequence callbacks (survive tab switch)."""
        session = self._session_ctx() or self.active_session()
        return session.id if session is not None else None

    def _seq_call_for(self, sid, fn, *args):
        """Run ``fn(*args)`` under the sequence-owning session context."""
        if sid is None or not hasattr(self, "find_session"):
            return
        session = self.find_session(sid)
        if session is None:
            return
        with self._with_session(session):
            fn(*args)

    def _seq_pause_peer_engines(self):
        """序列独占本会话收发流前，作废本会话自动应答旧任务；若本会话钉住 MBM 则暂停主机。"""
        # Only this session — other tabs may keep their own AR / sequence.
        self._ar_reset_buf()
        self._ar_generation = getattr(self, "_ar_generation", 0) + 1
        self._ar_sm_pending = None
        if hasattr(self, "_ar_sm_queue"):
            self._ar_sm_queue.clear()
        self._ar_sm_draining = False

        owns_mbm = self._io_session_owns("modbus")
        info = self._mbm_inflight if owns_mbm else None
        self._seq_waiting_mbm = info is not None
        self._seq_wait_mbm_variant = (str(info.get("variant", "")) if info is not None else "")
        self._seq_wait_mbm_until = 0.0
        if not owns_mbm:
            return
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
        deadline = self._seq_wait_mbm_until
        if self._seq_wait_mbm_variant in ("rtu", "ascii"):
            deadline = max(deadline, self._mbm_guard_until)
        plan = _seq_engine_mbm_release_plan(
            seq_on=self._seq_on,
            gen_ok=(gen == self._seq_gen),
            waiting_mbm=bool(getattr(self, "_seq_waiting_mbm", False)),
            inflight=self._mbm_inflight,
            deadline=deadline,
            qtimer_max_ms=self._MBM_QTIMER_MAX_MS,
        )
        action = plan.get("action")
        if action in ("noop", "still_inflight"):
            return
        if action == "wait":
            ctx_id = getattr(self, "_seq_ctx_id", None)
            call_for = getattr(self, "_seq_call_for", None)
            if callable(ctx_id) and callable(call_for):
                sid = ctx_id()
                QTimer.singleShot(
                    int(plan["delay_ms"]),
                    lambda: call_for(
                        sid, self._seq_mbm_release_check, gen))
            else:
                # Lightweight direct-call tests/embedders without SessionHost.
                QTimer.singleShot(
                    int(plan["delay_ms"]),
                    lambda: self._seq_mbm_release_check(gen))
            return
        self._seq_waiting_mbm = False
        self._seq_wait_mbm_variant = ""
        self._seq_wait_mbm_until = 0.0
        self._seq_round_t0 = time.monotonic()
        self._seq_run_from(0)

    def _seq_resume_peer_engines(self):
        """序列释放本会话收发流后，若本会话钉住 MBM 则按原开关恢复主机。"""
        if not self._seq_on and self._io_session_owns("modbus"):
            self._mbm_tick()

    def open_sequence(self):
        """打开自动化序列对话框（单实例，复用并刷新主题/语言）。"""
        if self._seq_dlg is None:
            from ui.dialogs import SequenceDialog
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
            from ui.frame_builder_dialog import FrameBuilderDialog
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
            from ui.toolbox_dialog import ToolboxDialog
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
            from ui.bridge_dialog import BridgeDialog
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
            from ui.xfer_dialog import XferDialog
            self._xfer_dlg = XferDialog(self)
        dlg = self._xfer_dlg
        dlg.refresh_theme()
        dlg.retranslate()
        sync = getattr(dlg, "sync_session", None)
        if callable(sync):
            sync()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ----- 文件传输 ⇄ 连接层桥接（对话框调） -----
    def _xfer_attach(self, worker):
        """传输开始：主窗接管收流并把 worker 的发送经 GUI 线程转到 conn.send。"""
        if self._xfer_worker is not None:
            old = self._xfer_worker
            self._xfer_detach()  # 本会话残留的上一个 worker；不影响其它标签
            # 正常路径被 _xfer_start_blocked 拦截，这里仅防御极端竞态：
            # 断桥后若旧线程仍在跑，取消它避免悬挂线程（孤儿由对话框收尾）。
            if getattr(old, "isRunning", lambda: False)():
                stop = getattr(old, "cancel", None)
                if callable(stop):
                    stop()
        self._xfer_worker = worker
        self._io_bind_owner("transfer")
        self._xfer_conn = self.conn
        self._xfer_target = self._send_target()          # 起始时捕获目标（串口为 None）
        owner_id = getattr(self._session_ctx() or self.active_session(), "id", None)
        def bridge(data, _worker=worker, _owner_id=owner_id):
            self._xfer_send_for(_worker, _owner_id, data)
        self._xfer_send_bridge = bridge
        worker.sig_send.connect(bridge)
        # 传输即将独占本会话线路：作废已经排队的延迟自动应答，避免它在
        # X/YMODEM 握手中途插入普通业务帧。只动当前 owner，不影响其它标签。
        self._ar_reset_buf()
        self._ar_cancel_pending()
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()
        # 暂停 Modbus 定时器：传输期间收流喂协议引擎，Modbus 响应进不来；在途请求的定时器
        # 也会误触发超时——清掉 inflight，待传输结束再恢复。
        if self._io_session_owns("modbus"):
            if hasattr(self, "_mbm_to"):
                self._mbm_to.stop()
            if hasattr(self, "_mbm_sched"):
                self._mbm_sched.stop()
            self._mbm_inflight = None
            self._mbm_buf = b""

    def _xfer_detach(self):
        """传输结束：断开发送桥、恢复正常收流、恢复 Modbus 轮询（不清结果，只重启调度）。"""
        resume_mbm = self._io_session_owns("modbus")
        w = self._xfer_worker
        bridge = self._xfer_send_bridge
        if w is not None and bridge is not None:
            try:
                w.sig_send.disconnect(bridge)
            except (TypeError, RuntimeError):
                pass
        self._xfer_worker = None
        self._xfer_send_bridge = None
        self._xfer_conn = None
        self._xfer_target = None
        if not any(getattr(s, "_xfer_worker", None)
                   for s in getattr(self, "_sessions", ()) or ()):
            self._io_clear_owner("transfer")
        if hasattr(self, "_mbm_tick") and resume_mbm:
            self._mbm_tick()           # 恢复 Modbus 轮询（若已启用）；不调 _mbm_restart 避免清掉已有结果
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def _xfer_send_for(self, worker, owner_id, data):
        """Send one queued chunk only for the worker/owner captured at attach."""
        owner = self.find_session(owner_id) if owner_id is not None else None
        if owner is None:
            return
        if self._session_ctx() is not owner:
            with self._with_session(owner):
                self._xfer_send_for(worker, owner_id, data)
            return
        if worker is not self._xfer_worker:
            return
        if (self._xfer_conn is not None
                and self.conn is not self._xfer_conn):
            return
        self._xfer_send_owned(data)

    def _xfer_send(self, data):
        """Compatibility entry; attached workers use _xfer_send_for."""
        owner = self._io_owner_session("transfer")
        if owner is None:
            # Compatibility for direct bridge callers/tests that invoke this
            # without _xfer_attach.  A real active transfer is always bound.
            if self._xfer_worker is not None:
                return
            owner = self._session_ctx() or self.active_session()
            if owner is None:
                return
        if self._session_ctx() is not owner:
            with self._with_session(owner):
                self._xfer_send(data)
            return
        self._xfer_send_owned(data)

    def _xfer_send_owned(self, data):
        if self.conn is not None:
            payload = bytes(data)
            try:
                sent = self.conn.send(payload, self._xfer_target)
            except (OSError, RuntimeError, TypeError, ValueError):
                return
            # 录制与 TX 告警描述的是线路上真实发出的字节；无目标、零写或短写都不能
            # 把整块登记为成功。TCP Client 半帧还要沿用普通发送路径的断流保护。
            if sent == SEND_NO_TARGET or sent != len(payload):
                self._abort_partial_tcp_stream(sent, len(payload))
                return
            # 文件传输同样绕过 _send_text：补上采集入口，否则「发送」范围的触发规则盯不到
            try:
                self._record_stream_tx(payload, source=self._xfer_target)
            except (TypeError, ValueError, RuntimeError, OSError):
                _log.debug("_xfer_send failed", exc_info=True)

    def _seq_start(self, steps, loops=1, stop_on_fail=False, dataset=None):
        """开始运行一段序列（steps=步骤 dict 列表）。loops=循环次数（整条跑几轮），
        stop_on_fail=某轮失败即停后续循环。需已连接；运行期由 on_data_received 抑制
        自动应答/Modbus 主机（三者共用收流，序列是主动驱动方，结束自动恢复、不改它们开关）。"""
        if self._seq_on:
            return
        # Busy is per-session: another tab's sequence/script must not block this one
        # (script/xfer remain one-per-window and only block their owner session).
        if self._io_task_busy(exclude=("sequence", "modbus")):
            self.toast_io_exclusive_busy(exclude=("sequence", "modbus"))
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
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()
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
            self._toast_if_active_session(
                self._t("seq_var_missing", names=", ".join(missing)), error=True)
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
        action = _seq_engine_feed_action(status)
        if action == "extend_quiet":
            self._seq_retry_quiet_until = (
                time.monotonic() + _SEQ_RETRY_GUARD_MS / 1000.0)
            return
        if action != "accumulate":
            return
        self._seq_buf += bytes(data)
        match_step = getattr(self, "_seq_runtime_step", None) or self._seq_steps[i]
        if self._seq_step_match(match_step, self._seq_buf):
            self._seq_timer.stop()
            ms = int((time.monotonic() - self._seq_step_total_t0) * 1000)
            extracted = self._seq_capture_vars(self._seq_steps[i], self._seq_buf)
            detail = _seq_engine_detail_extracted(extracted)
            rx_hex = _seq_engine_clip_rx_hex(self._seq_buf)
            self._seq_set_result(
                i, "pass", ms, detail, "", self._seq_attempt, rx_hex=rx_hex)
            if extracted and 0 <= i < len(self._seq_results):
                self._seq_results[i]["extracted"] = dict(extracted)
            self._seq_schedule_next(self._seq_steps[i])

    def _seq_on_timeout_for(self, sid):
        """Per-session sequence wait timer callback."""
        session = self.find_session(sid) if hasattr(self, "find_session") else None
        if session is None:
            return
        with self._with_session(session):
            self._seq_on_timeout()

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
        if _seq_engine_fail_outcome(
                attempt=self._seq_attempt,
                retry_limit=step.get("retry", 0)) == "retry":
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
            sid = self._seq_ctx_id()
            QTimer.singleShot(
                plan["timer_ms"],
                lambda: self._seq_call_for(
                    sid, self._seq_retry, gen, i, attempt))
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
            sid = self._seq_ctx_id()
            QTimer.singleShot(
                delay,
                lambda: self._seq_call_for(
                    sid, self._seq_retry, gen, i, attempt))
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
        sid = self._seq_ctx_id()
        QTimer.singleShot(
            delay,
            lambda: self._seq_call_for(sid, self._seq_continue, gen, nxt))

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
            sid = self._seq_ctx_id()
            QTimer.singleShot(
                0,
                lambda: self._seq_call_for(sid, self._seq_next_round, gen))
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
        self._toast_if_active_session(
            self._t("seq_done_pass" if ok else "seq_done_fail"), error=not ok)
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

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
            self._toast_if_active_session(self._t(toast_key))
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()


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
        # Row results always follow the visible tab. Background runs still
        # refresh the summary so other sessions' progress stays visible.
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
        self._ar_reset_all_buffers()  # 全局规则变更不能留下后台标签的旧半包
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
        self._ar_reset_all_buffers()  # 全局组帧方式变更需清每个标签的旧缓冲
        save = {k: v for k, v in self._ar_frame.items() if not k.startswith("_")}
        self.settings.setValue("autoreply_frame", json.dumps(save, ensure_ascii=False))
        self.settings.sync()

    def _load_stream_frame(self):
        """Analysis-layer stream framing (independent of auto-reply). Missing = off."""
        cfg = _cfg_parse_json_dict(self.settings.value("stream_frame", "")) or {}
        return binproto.norm_stream_frame(cfg)

    def _set_stream_frame(self, cfg):
        """Frame-parse dialog: persist protocol-frame mode and drop half-frames."""
        self._stream_frame = binproto.norm_stream_frame(cfg)
        save = {k: v for k, v in self._stream_frame.items() if not k.startswith("_")}
        self.settings.setValue("stream_frame", json.dumps(save, ensure_ascii=False))
        self.settings.sync()
        self._reset_stream_frames_all(reset_diag=False)

    def _reset_stream_frames_all(self, reset_diag=False):
        for session in self._ar_sessions_snapshot():
            session.reset_stream_frames(reset_diag=reset_diag)

    def _analysis_rx_units(self, data, source=None):
        """Raw chunk → analysis units (compat: one chunk; protocol mode: frames)."""
        s = self._session_ctx()
        if s is None or not hasattr(s, "feed_analysis_frames"):
            return [bytes(data)]
        cfg = getattr(self, "_stream_frame", None) or binproto.norm_stream_frame({})
        proto = getattr(self, "_conn_proto", None)
        return s.feed_analysis_frames(data, source, cfg, proto)

    def _note_parse_diag(self, matched=False, field_ok=0, field_oob=0):
        s = self._session_ctx()
        if s is not None and hasattr(s, "_parse_diag"):
            s._parse_diag.note_parse(matched, field_ok, field_oob)

    def parse_diag_snapshot(self):
        s = self._session_ctx() or self.active_session()
        if s is None or not hasattr(s, "_parse_diag"):
            return {}
        return s._parse_diag.snapshot()

    def reset_parse_diag(self):
        s = self._session_ctx() or self.active_session()
        if s is not None and hasattr(s, "_parse_diag"):
            s._parse_diag.reset()

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
            self._ar_reset_all_states()  # on/init 是全局配置，所有会话回到新初态
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

    def _modbus_rebuild_all_sessions(self):
        """Rebuild every session's slave register bank from window ``_ar_modbus``."""
        cfg = getattr(self, "_ar_modbus", None) or {}
        sessions = self._ar_sessions_snapshot()
        if not sessions:
            return
        for session in sessions:
            session._modbus = modbus_slave.slave_bank_from_config(cfg)

    def _set_ar_modbus(self, cfg):
        """对话框编辑「Modbus 从机」后回调：更新内存配置 + 重建各会话运行态从机(回初值) + 落盘。
        Modbus 开关/配置变 = 改变了分帧语义 → 必须清跨模式共用的 _ar_buf 半包缓冲并停 gap timer
        （与 _set_ar_frame / _set_ar_rules 一致），否则切模式时旧字节会被新框架误解析。"""
        self._ar_modbus = self._norm_ar_modbus(cfg)
        self._modbus_rebuild_all_sessions()
        self._ar_reset_all_buffers()
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
        if (not self._session_ar_on() or not self._is_open()
                or (getattr(self, "_replay_drive_tx", False)
                    and self._io_session_owns("replay"))):
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
        except (ValueError, TypeError, UnicodeError, OSError, RuntimeError):
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
        if hasattr(self, "_ar_stream_buffers"):
            self._ar_stream_buffers.clear()
        if hasattr(self, "_modbus_buffers"):
            self._modbus_buffers.clear()

    def _ar_sessions_snapshot(self):
        """Return concrete sessions for a window-wide auto-reply runtime reset."""
        getter = getattr(self, "sessions", None)
        sessions = list(getter()) if callable(getter) else []
        if sessions:
            return sessions
        current = self._session_ctx() or self.active_session()
        return [current] if current is not None else []

    def _ar_reset_all_buffers(self):
        """Clear framing/client buffers and gap timers in every session."""
        sessions = self._ar_sessions_snapshot()
        if not sessions:
            self._ar_reset_buf()
            return
        for session in sessions:
            with self._with_session(session):
                self._ar_reset_buf()

    def _ar_cancel_pending(self):
        """Cancel delayed/state-machine work in the context session only."""
        self._ar_generation = getattr(self, "_ar_generation", 0) + 1
        self._ar_sm_pending = None
        if hasattr(self, "_ar_sm_queue"):
            self._ar_sm_queue.clear()
        self._ar_sm_draining = False

    def _ar_cancel_all_pending(self):
        """Cancel delayed/state-machine work in every session without changing state."""
        for session in self._ar_sessions_snapshot():
            with self._with_session(session):
                self._ar_cancel_pending()

    def _ar_reset_all_states(self):
        """Reset every session to the current window-level state-machine config."""
        sessions = self._ar_sessions_snapshot()
        if not sessions:
            self._ar_reset_state()
            return
        for session in sessions:
            with self._with_session(session):
                self._ar_reset_state()

    def _ar_reset_state(self, reset_modbus=True):
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
        if reset_modbus and hasattr(self, "_ar_modbus"):
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
        # Drive-TX replay owns the wire; do not let AR / Modbus-slave TX race it.
        if (getattr(self, "_replay_drive_tx", False)
                and self._io_session_owns("replay")):
            return
        mode = _ar_gate.ingress_mode(
            ar_on=self._session_ar_on(),
            is_open=self._is_open(),
            modbus_on=bool(self._ar_modbus.get("on")),
            has_rules=bool(self._ar_rules),
            frame_on=bool(self._ar_frame.get("on")),
            has_header=bool(self._ar_frame.get("_header")),
            gap_ms=self._ar_gap,
        )
        if mode == "noop":
            return
        if mode == "modbus":
            self._modbus_feed(bytes(data), reply_target=reply_target)
            return
        if mode == "no_rules":
            return
        if mode == "length_frame":
            fc = self._ar_frame
            key = reply_target
            bufs = getattr(self, "_ar_stream_buffers", None)
            if key is None or not isinstance(bufs, dict):
                self._ar_buf += bytes(data)
                frames, self._ar_buf = binproto.iter_length_frames(
                    self._ar_buf, fc["_header"], fc["len_off"], fc["len_width"],
                    fc["len_extra"], fc["len_be"])
                self._ar_buf, _ = _ar_gate.trim_length_buf(self._ar_buf)
            else:
                buf = bufs.get(key, b"") + bytes(data)
                frames, rem = binproto.iter_length_frames(
                    buf, fc["_header"], fc["len_off"], fc["len_width"],
                    fc["len_extra"], fc["len_be"])
                rem, _ = _ar_gate.trim_length_buf(rem)
                if rem:
                    bufs[key] = rem
                else:
                    bufs.pop(key, None)
            for f in frames:
                self._ar_match(f)
        elif mode == "gap":
            self._ar_buf += bytes(data)
            self._ar_gap_timer.start(self._ar_gap)
        else:
            self._ar_match(bytes(data))

    def _ar_flush(self):
        """整包静默超时：把累积缓冲当一整帧匹配。Modbus 模式下不走规则匹配（防止切到 Modbus 后
        在途的 gap timer 仍误用规则匹配一帧）。"""
        buf, self._ar_buf = self._ar_buf, b""
        if buf and self._session_ar_on() and self._is_open() and not self._ar_modbus.get("on"):
            self._ar_match(buf)

    def _ar_match(self, data: bytes):
        # 状态转移的整条多段应答尚未完成时，后续完整帧先入 FIFO。直接继续匹配会让多个随机延迟
        # 任务共享同一旧状态并按定时器先后 goto；直接丢弃又会漏掉同一接收块里的后续合法帧。
        q = self._ar_sm_queue
        if _ar_gate.sm_busy(
                sm_on=bool(self._ar_sm.get("on")),
                pending=getattr(self, "_ar_sm_pending", None),
                queue_len=len(q),
                draining=bool(getattr(self, "_ar_sm_draining", False))):
            _ar_gate.enqueue_sm_frame(q, data)
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
            if not _ar_gate.len_filter_ok(
                    len(data),
                    self._ar_to_int(rule.get("min_len", 0)),
                    self._ar_to_int(rule.get("max_len", 0))):
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
            session = self._session_ctx() or self.active_session()
            sid = getattr(session, "id", None)
            last_by_session = rule.get("_last_by_session")
            if not isinstance(last_by_session, dict):
                last_by_session = {}
            last = (last_by_session.get(sid, 0.0) if sid is not None
                    else rule.get("_last", 0.0))
            if _ar_gate.cooldown_blocks(
                    now, last,
                    self._ar_to_int(rule.get("cooldown", 0))):
                return
            if sid is not None:
                last_by_session[sid] = now
                rule["_last_by_session"] = last_by_session
            else:
                rule["_last"] = now
            # B5：有脚本则跑脚本动态生成应答（脚本拥有整帧、不叠校验段/尾校验）；否则走静态模板
            # （④ 多帧 | 分段、占位符替换、校验段）。两路都经故障注入 + 延时发送、共用 goto 回调。
            path = _ar_gate.reply_path(rule)
            script_err = None
            if path == "script":
                parts, script_err = self._ar_script_eval(rule, data)
            else:
                parts = self._ar_build_parts(rule, data)
            plan = _ar_gate.post_hit_plan(
                rule, sm_on=bool(self._ar_sm.get("on")),
                parts=parts, from_script=(path == "script"),
                script_err=script_err)
            if plan["note_script_err"]:
                self._ar_fault_note(self._t("ar_script_err", e=script_err))
            if plan["action"] != "schedule":
                return
            hexmode, cs, cs_segs = plan["hexmode"], plan["cs"], plan["cs_segs"]
            delay = self._ar_parse_delay(rule.get("delay", 0))
            pending = None
            on_sent = None
            on_done = None
            if plan["arm_goto"]:
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
                if _ar_gate.clear_pending_on_schedule_error(
                        pending=pending, current_pending=self._ar_sm_pending):
                    self._ar_sm_pending = None
                raise
            return


    def _ar_drain_sm_queue(self):
        """按收帧顺序消费 pending 期间积压的完整帧；遇到下一条延迟状态转移时自然暂停。"""
        if (self._ar_sm_draining or not self._ar_sm.get("on")
                or not self._session_ar_on() or not self._is_open()):
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
        owner = self._session_ctx() or self.active_session()
        owner_id = owner.id if owner is not None else None
        dmin, dmax = delay if isinstance(delay, (tuple, list)) else (delay, delay)

        def _delay():
            return random.randint(dmin, dmax) if dmax > dmin else dmin

        def fire(idx):
            target = self.find_session(owner_id) if owner_id is not None else owner
            if owner_id is not None and target is None:
                if on_done is not None:
                    with self._with_session(owner):
                        on_done()
                return
            if target is not None:
                with self._with_session(target):
                    fire_owned(idx)
            else:
                fire_owned(idx)

        def fire_owned(idx):
            def finish_batch():
                if on_done is not None:
                    on_done()

            # 代际已变（手动重置/断重连/配置导入）→ 整批在途任务作废：旧回复不发、旧 goto 不执行
            if gen != getattr(self, "_ar_generation", 0):
                finish_batch()
                return
            script_here = (self._script_running()
                           and self._io_session_owns("script")
                           and (self._script_conn is None
                                or self.conn is self._script_conn))
            replay_here = (getattr(self, "_replay_drive_tx", False)
                           and self._io_session_owns("replay"))
            if (not self._session_ar_on() or not self._is_open() or self._seq_running()
                    or script_here or replay_here or idx >= len(parts)):
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
        if not self._session_ar_on() or not self._is_open():
            return
        try:
            self._send_text(reply, hex_mode=hexmode, newline=0, checksum=cs,
                            record_macro=False)
        except (ValueError, TypeError, UnicodeError, OSError, RuntimeError):
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
            # 用户已明确选择保留外部动作：兼容旧版中尚无权限字段的 webhook。
            # 显式的 False 必须保留，不能把新版安全选择改回去。
            rules, migrated = triggers.migrate_legacy_webhook_permissions(rules)
            if not migrated:
                return data
            new = dict(data)
            new["triggers"] = _cfg_dumps_list(rules)
            return new
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
        """导入 JSON 配置并用一个新会话替换当前工作区运行态。"""
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
        old = {key: self.settings.value(key, None) for key in self._CFG_KEYS}
        with self._workspace_autosave_paused():
            if not self._prepare_project_switch():
                return
            s = self.settings
            n = 0
            try:
                for k, v in data.items():
                    if k in self._CFG_KEYS:
                        s.setValue(k, _cfg_coerce_value(v))
                        n += 1
                s.sync()
                self._apply_loaded_settings()
            except Exception as exc:
                _log.debug("import_config failed", exc_info=True)
                for key, value in old.items():
                    if value is None:
                        s.remove(key)
                    else:
                        s.setValue(key, value)
                s.sync()
                try:
                    self._apply_loaded_settings()
                except Exception:
                    _log.debug("import_config rollback failed", exc_info=True)
                self._rollback_project_switch_sessions()
                self._info_dlg(
                    self._t("cfg_import"),
                    self._t("cfg_import_fail", err=str(exc)), is_error=True)
                return
            self._commit_project_switch_sessions()
            # Persist the new single-tab snapshot now so a crash before normal
            # shutdown cannot resurrect the imported profile's stale sessions_v1.
            self._save_sessions_settings()
            self.settings.sync()
        self._info_dlg(self._t("cfg_import"), self._t("cfg_imported", n=n))

    def _apply_loaded_settings(self):
        self._begin_workspace_autosave_pause()
        try:
            self._apply_loaded_settings_unlocked()
        finally:
            self._end_workspace_autosave_pause()

    def _apply_loaded_settings_unlocked(self):
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
        self._stream_frame = self._load_stream_frame()
        self._ar_fault = self._load_ar_fault()
        self._ar_sm = self._load_ar_sm()      # C8：状态机配置随配置档导入
        self._ar_modbus = self._load_ar_modbus()   # B4：Modbus 从机配置随配置档导入
        self._modbus_rebuild_all_sessions()
        self._recompute_ar_gap()
        self._ar_reset_all_buffers()
        self._reset_stream_frames_all(reset_diag=True)
        self._ar_reset_all_states()           # C8：导入新配置=新会话 → 所有会话复位到新初态
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
        self._mbm_variant = _cfg_normalize_mbm_variant(
            s.value("modbus_master_variant", "", type=str))
        self._mbm_echo = s.value("modbus_master_echo", False, type=bool)
        self._device_registers = self._load_device_registers()
        self._device_plot_tags = self._load_device_link("device_plot_tags")
        self._device_dash_tags = self._load_device_link("device_dash_tags")
        if _cfg_ar_mbm_mutex_disable_ar(self._ar_on, self._mbm_on):
            # 加载结果也保持互斥（主机优先）。走 _set_autoreply_enabled 而非手设标志，
            # 才能一并复位状态机 + 同步「打开着的」自动应答对话框 checkbox（否则对话框
            # 仍显示启用、与实际关闭不一致）。enabled=False 不会回触发 _set_mbm_enabled。
            self._set_autoreply_enabled(False)
            s.sync()
        else:
            session = self.active_session()
            if session is not None:
                session._ar_enabled = bool(self._ar_on)
        if self._mbm_on:
            self._io_bind_owner("modbus")
        self._mbm_restart()
        if not self._mbm_on:
            self._io_clear_owner("modbus")
        # 多条发送 / 关键字高亮 的内存模型也是 __init__ 读一次的缓存。不重载会让
        # 后续编辑（commit 走旧内存）把加载的值再覆盖回去。重载 + 刷 UI 让它们立刻生效。
        self._ms_groups, _ = self._load_ms_groups()
        self._ms_group_idx = _cfg_clamp_group_idx(
            s.value("multi_send_group_idx", 0), len(self._ms_groups))
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
    def _dsl_running(self, session=None) -> bool:
        session = session or self._session_ctx() or self.active_session()
        return bool(getattr(session, "_dsl_ops", None)) if session else False

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
            self.toast_io_exclusive_busy(exclude=("periodic",))
            return False
        sends, delay = send_dsl.describe(ops)
        session = self._session_ctx() or self.active_session()
        sid = session.id if session is not None else None
        self._dsl_ops = ops
        self._io_bind_owner("dsl")
        self._dsl_idx = 0
        self._dsl_record = bool(record_macro)
        self._dsl_gen = getattr(self, "_dsl_gen", 0) + 1
        if sends > 1 or delay:
            self.toast(self._t("dsl_started", n=sends, ms=delay))
        self._dsl_step(self._dsl_gen, sid)
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()
        return True

    def _dsl_step(self, gen, sid=None):
        """执行下一条指令。gen 代际用于让 _dsl_abort 之后的排队回调自动失效。"""
        if sid is None:
            session = self._session_ctx() or self.active_session()
            sid = getattr(session, "id", None)
        session = self.find_session(sid) if sid is not None else None
        if session is None:
            return
        if self._session_ctx() is not session:
            with self._with_session(session):
                self._dsl_step(gen, sid)
            return
        if gen != getattr(self, "_dsl_gen", 0) or not self._dsl_running():
            return
        if self._dsl_idx >= len(self._dsl_ops):
            self._dsl_finish()
            return
        op, arg = self._dsl_ops[self._dsl_idx]
        self._dsl_idx += 1
        if op == send_dsl.OP_DELAY:
            QTimer.singleShot(max(0, int(arg)), lambda: self._dsl_step(gen, sid))
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
        QTimer.singleShot(0, lambda: self._dsl_step(gen, sid))   # 让出事件循环，界面不卡

    def _dsl_finish(self):
        self._dsl_ops = None
        self._io_clear_owner("dsl")
        self._dsl_idx = 0
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def _dsl_abort(self):
        """中止 DSL（发送失败 / 断连 / 关窗）。代际 +1 让已排队的回调作废。"""
        if not self._dsl_running():
            return
        self._dsl_gen = getattr(self, "_dsl_gen", 0) + 1
        self._dsl_ops = None
        self._io_clear_owner("dsl")
        self._dsl_idx = 0
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

    def _send_with_subst(self, raw, hex_mode, newline=None, checksum=None,
                         target=None, encoding=None, record_macro=True,
                         allow_during_exclusive=False,
                         allow_running_dsl=False, notify_ui=True,
                         feed_window_engines=True) -> bool:
        """替换动态字段 → 发送 → 失败回滚 {count}（避免未连接/格式错等失败消耗计数）。
        ({ts}/{rand} 是纯函数无副作用，不用回滚；只有 {count} 有持久状态)"""
        prev_count = self._send_count
        subbed = self._send_subst(raw, hex_mode=hex_mode)
        ok = self._send_text(subbed, hex_mode=hex_mode, newline=newline, checksum=checksum,
                             target=target, encoding=encoding,
                             record_macro=record_macro,
                             allow_during_exclusive=allow_during_exclusive,
                             allow_running_dsl=allow_running_dsl,
                             notify_ui=notify_ui,
                             feed_window_engines=feed_window_engines)
        if not ok:
            self._send_count = prev_count
        return ok

    def _commit_ime_composition(self):
        """发送前提交 IME 组合文本。

        中文/日文输入法下 Ctrl+Enter 通常只透传按键、不提交组合；若组词未上屏就
        发送，组合中的文字会从发送内容里漏掉。先 commit() 让 QTextEdit 收到完整
        文本，再走 do_send。无活动组合时为空操作；异常只记 debug 不阻塞发送。
        """
        try:
            from PyQt5.QtGui import QGuiApplication
            im = QGuiApplication.inputMethod()
            if im is not None:
                im.commit()
        except Exception:
            _log.debug("IME commit failed", exc_info=True)

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
        except (TypeError, ValueError, RuntimeError, OSError):
            _log.debug("persist send_history failed", exc_info=True)

    def _delete_send_hist(self, idx):
        """Remove one send-history entry and persist; adjust Up/Down cursor."""
        new_hist, changed = _hist_remove_at(self._send_hist, idx)
        if not changed:
            return False
        self._send_hist_idx = _hist_nav_after_remove(self._send_hist_idx, idx)
        if self._send_hist_idx < 0:
            self._send_hist_pending = ""
        self._send_hist = new_hist
        try:
            self.settings.setValue("send_history", _hist_dumps(self._send_hist))
        except (TypeError, ValueError, RuntimeError, OSError):
            _log.debug("persist send_history failed", exc_info=True)
        return True

    def _load_send_hist(self):
        raw = self.settings.value("send_history", "")
        try:
            loaded = _hist_load_list(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
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
        from project.device_resources import normalize_registers
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
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        out = []
        for r in data:                       # 逐条规范化：单条损坏只跳过它，不清空整张表
            try:
                out.append(modbus_master.normalize_poll(r))
            except (TypeError, ValueError, KeyError, AttributeError):
                _log.debug("_load_mbm_rules failed", exc_info=True)
        return out

    def _mbm_save_rules(self):
        try:
            self.settings.setValue("modbus_master", json.dumps(
                [modbus_master.normalize_poll(r) for r in self._mbm_rules], ensure_ascii=False))
            self.settings.sync()
        except (TypeError, ValueError, AttributeError, RuntimeError, OSError):
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
        session_ctx = getattr(self, "_session_ctx", None)
        active_session = getattr(self, "active_session", None)
        session = ((session_ctx() if callable(session_ctx) else None)
                   or (active_session() if callable(active_session) else None))
        actual = getattr(self, "_conn_proto", None)
        active = active_session() if callable(active_session) else None
        if session is None or session is active:
            configured = self.cb_proto.currentText()
            actual = actual or configured
            signature = getattr(self, "_conn_config_signature", None)
            expected = (signature(configured) if callable(signature)
                        else getattr(self, "_conn_cfg", None))
        else:
            # Sidebar widgets describe the visible tab, not this background
            # owner.  Rebuild the desired signature from its saved fields.
            fields = session.conn_fields or {}
            configured = str(fields.get("net_proto") or actual or "")
            if not fields:
                expected = getattr(session, "_conn_cfg", None)
            elif configured == PROTO_SERIAL:
                try:
                    baud = int(fields.get("ser_baud"))
                except (TypeError, ValueError):
                    baud = None
                expected = _conn_serial_sig(
                    configured, fields.get("ser_port"), baud,
                    fields.get("ser_databits"), fields.get("ser_parity"),
                    fields.get("ser_stopbits"), fields.get("ser_flow"))
            elif configured == PROTO_TCP_CLIENT:
                expected = _conn_tcp_sig(
                    configured, str(fields.get("net_remote_ip") or "").strip(),
                    self._parse_port(fields.get("net_remote_port")))
            elif configured == PROTO_BLE:
                expected = _conn_ble_sig(
                    configured,
                    fields.get("ble_address"),
                    fields.get("ble_service_uuid"),
                    fields.get("ble_write_uuid"),
                    fields.get("ble_notify_uuid"),
                    fields.get("ble_write_mode"))
            elif configured == PROTO_RTT:
                expected = _conn_rtt_sig(
                    configured,
                    fields.get("rtt_device"),
                    fields.get("rtt_speed"),
                    fields.get("rtt_interface"),
                    fields.get("rtt_address"),
                    fields.get("rtt_channel"),
                    fields.get("rtt_probe"),
                    fields.get("rtt_reset"))
            else:
                expected = _conn_proto_sig(configured)
        return bool(actual in (PROTO_SERIAL, PROTO_TCP_CLIENT, PROTO_BLE, PROTO_RTT)
                    and configured == actual  # 导入改了协议但旧连接未重连：暂停，禁止发错制式
                    and getattr(self, "_conn_cfg", None) == expected)

    def _mbm_poll_rules(self):
        """Rules the scheduler is currently driving (scan snapshot or editor list)."""
        session = self._session_ctx() or self.active_session()
        state = getattr(session, "_device_scan_state", None) if session else None
        if isinstance(state, dict) and state.get("rules"):
            return state["rules"]
        return getattr(self, "_mbm_rules", None) or []

    def _mbm_active(self):
        _xw = getattr(self, "_xfer_worker", None)
        session_ctx = getattr(self, "_session_ctx", None)
        active_session = getattr(self, "active_session", None)
        session = ((session_ctx() if callable(session_ctx) else None)
                   or (active_session() if callable(active_session) else None))
        owns = getattr(self, "_io_session_owns", None)
        owns = owns if callable(owns) else (lambda _key, _session=None: True)
        current_conn = getattr(self, "conn", None)
        script_conn = getattr(self, "_script_conn", None)
        script_here = (getattr(self, "_script_worker", None) is not None
                       and owns("script", session)
                       and (script_conn is None or current_conn is script_conn))
        replay_here = (getattr(self, "_replay_on", False)
                       and owns("replay", session))
        macro_here = (bool(getattr(getattr(self, "_macro", None), "recording", False))
                      and owns("macro", session))
        xfer_conn = getattr(self, "_xfer_conn", None)
        xfer_here = (_xw is not None and _xw.isRunning()
                     and owns("transfer", session)
                     and (xfer_conn is None or current_conn is xfer_conn))
        return bool(self._mbm_connection_ready()
                    and (bool(getattr(session, "_mbm_enabled", False))
                         if session is not None else bool(self._mbm_on))
                    and self._is_open()
                    and not getattr(self, "_seq_on", False)
                    and not replay_here
                    and not script_here
                    and not macro_here
                    and not xfer_here
                    and any(r.get("enabled") for r in self._mbm_poll_rules()))

    def _mbm_import_enabled(self, requested):
        """连接期间导入只加载规则，不继承“启用”状态，避免导入动作直接产生总线写入。"""
        return _cfg_mbm_import_enabled(requested, self._is_open())

    def _mbm_restart(self):
        """开关/连接/规则/变体变化后：复位当前会话运行态并按需启动轮询。"""
        old_info = getattr(self, "_mbm_inflight", None)
        sched = getattr(self, "_mbm_sched", None)
        to = getattr(self, "_mbm_to", None)
        if sched is not None:
            sched.stop()
        if to is not None:
            to.stop()
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

    def _mbm_resume_after_link_up(self):
        """Restore this session's master after reconnect if it still owns the pin."""
        session = self._session_ctx() or self.active_session()
        if session is None or not hasattr(self, "_mbm_restart"):
            return
        owner = (self._io_owner_session("modbus")
                 if hasattr(self, "_io_owner_session") else None)
        wanted = bool(getattr(session, "_mbm_wanted", False))
        if owner is session or wanted:
            session._mbm_enabled = True
            if session is self.active_session():
                self._mbm_on = True
                dlg = getattr(self, "_mbm_dlg", None)
                cb = getattr(dlg, "cb_enable", None) if dlg is not None else None
                if cb is not None:
                    cb.blockSignals(True)
                    cb.setChecked(True)
                    cb.blockSignals(False)
            self._mbm_restart()
        elif owner is None and getattr(session, "_mbm_enabled", False):
            self._mbm_restart()

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

    def _mbm_tick_for(self, sid):
        session = self.find_session(sid) if hasattr(self, "find_session") else None
        if session is None:
            return
        with self._with_session(session):
            self._mbm_tick()

    def _mbm_on_timeout_for(self, sid):
        session = self.find_session(sid) if hasattr(self, "find_session") else None
        if session is None:
            return
        with self._with_session(session):
            self._mbm_on_timeout()

    def _mbm_tick(self):
        """Schedule: poll soonest due rule, else arm single-shot timer."""
        if self._mbm_inflight is not None or not self._mbm_active():
            return
        now = time.monotonic()
        poll_rules = getattr(self, "_mbm_poll_rules", None)
        rules = (poll_rules() if callable(poll_rules)
                 else (getattr(self, "_mbm_rules", None) or []))
        best_i, wait = _mbm_sched_pick_next(
            rules, self._mbm_due, now, self._mbm_guard_until)
        if best_i is None:
            return
        if wait <= 0.0:
            self._mbm_poll(best_i)
        else:
            delay_ms = _mbm_sched_delay_ms(wait, self._MBM_QTIMER_MAX_MS)
            sched = getattr(self, "_mbm_sched", None)
            if sched is not None:
                sched.start(delay_ms)

    def _mbm_timeout_ms(self, frame, r):
        """Response timeout = base + serial wire time (TCP uses fixed base)."""
        state = getattr(self, "_device_scan_state", None)
        if isinstance(state, dict):
            base = int(state.get("timeout_ms", self._MBM_TIMEOUT_MS))
        else:
            base = self._MBM_TIMEOUT_MS
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
        rules = self._mbm_poll_rules()
        if i < 0 or i >= len(rules):
            return
        r = modbus_master.normalize_poll(rules[i])
        variant = self._mbm_variant_eff()
        reject = _mbm_poll_reject_reason(r, variant)
        if reject:
            self._mbm_set_result(i, "err", self._t(reject))
            period = r.get("period") or 1000
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), period)
            self._mbm_sched.start(0)
            return
        arg, reject = _mbm_build_poll_arg(r)
        if reject:
            self._mbm_set_result(i, "err", self._t(reject))
            self._mbm_due[i] = _mbm_sched_next_due(time.monotonic(), r["period"])
            self._mbm_sched.start(0)
            return
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
        except _TX_IO_ERRORS:
            _log.debug("modbus master send failed", exc_info=True)
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
        except (UnicodeError, LookupError, ValueError, TypeError, RuntimeError,
                OSError):
            _log.debug("_mbm_send_raw failed", exc_info=True)
        # Modbus 主机也是绕过 _send_text 的直发路径：录制与「发送」范围的触发规则都得盯到
        try:
            self._record_stream_tx(frame, source=send_target)
        except (TypeError, ValueError, RuntimeError, OSError):
            _log.debug("_mbm_send_raw failed", exc_info=True)
        return True

    def _mbm_feed(self, data):
        """收到数据：若有在途轮询请求，累积并尝试切出一帧响应、解析、更新该行结果。
        坏帧/串口本地回显/杂散字节用「丢 1 字节重同步」处理，而非清空整缓冲——避免请求回显
        与合法响应粘包后把响应一并丢掉（RS-485 半双工本地回显常见）。"""
        plan = _mbm_feed_plan.idle_guard_plan(
            has_inflight=self._mbm_inflight is not None,
            now=time.monotonic(),
            guard_until=self._mbm_guard_until,
            variant_eff=self._mbm_variant_eff(),
            rtu_silent_s=self._mbm_rtu_silent_ms() / 1000.0,
        )
        self._mbm_guard_until = plan["guard_until"]
        if plan["action"] == "idle_return":
            return
        self._mbm_buf += bytes(data)
        self._mbm_buf = _mbm_feed_plan.clamp_rx_buf(self._mbm_buf)
        info = self._mbm_inflight
        variant = _mbm_feed_plan.feed_variant(info)
        if variant == "tcp":
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
        if variant == "ascii":
            if _mbm_feed_plan.echo_needed(info, echo_enabled=self._mbm_echo):
                rest, found = modbus_master.strip_local_echo(self._mbm_buf, info["echo"])
                if _mbm_feed_plan.after_echo_strip(found) == "wait":
                    return
                self._mbm_buf = rest
                info["echo_done"] = True
            while self._mbm_buf:
                try:
                    out = modbus_master.take_ascii_response(
                        self._mbm_buf, info["unit"], info["func"], info["qty"])
                except modbus_slave.ModbusException as e:
                    self._mbm_set_result(info["i"], "exc", self._t("mbm_st_exc", code=e.code))
                    self._mbm_finish_inflight()
                    return
                except ValueError:
                    self._mbm_buf = _mbm_feed_plan.ascii_resync_on_value_error(self._mbm_buf)
                    continue
                if out is None:
                    return
                result, consumed = out
                self._mbm_buf = self._mbm_buf[consumed:]
                info["resp_len"] = consumed
                self._mbm_apply(info, result)
                return
            return
        if _mbm_feed_plan.echo_needed(info, echo_enabled=self._mbm_echo):
            rest, found = modbus_master.strip_local_echo(self._mbm_buf, info["echo"])
            if _mbm_feed_plan.after_echo_strip(found) == "wait":
                return
            self._mbm_buf = rest
            info["echo_done"] = True
        while self._mbm_buf:
            try:
                out = modbus_master.take_rtu_response(
                    self._mbm_buf, info["unit"], info["func"], info["qty"])
            except modbus_slave.ModbusException as e:
                self._mbm_set_result(info["i"], "exc", self._t("mbm_st_exc", code=e.code))
                self._mbm_finish_inflight()
                return
            except ValueError:
                self._mbm_buf = _mbm_feed_plan.rtu_resync_on_value_error(self._mbm_buf)
                continue
            if out is None:
                return
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
        """Semantic response check; returns localized error or None."""
        key = _mbm_validate_response(info, result)
        return self._t(key) if key else None

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
            ctx = self._session_ctx() if hasattr(self, "_session_ctx") else None
            active = self.active_session() if hasattr(self, "active_session") else None
            # Visible dialog shows the active tab; background sessions keep
            # their own _mbm_results and are applied on switch_session reload.
            if ctx is None or active is None or ctx is active:
                try:
                    dlg.update_result(i, status, text)
                except Exception:
                    _log.debug("_mbm_set_result failed", exc_info=True)
        self._device_scan_result(i, status, text)

    def _start_device_scan(self, rules, timeout_ms, on_result, on_done):
        """Reuse this session's Modbus half-duplex scheduler for a one-shot scan."""
        if self._device_scan_state is not None:
            return False
        if not self._is_open() or not self._mbm_connection_ready():
            self.toast(self._t("device_scan_need_connection"), error=True)
            return False
        if self._io_task_busy(exclude=("modbus",)):
            self.toast_io_exclusive_busy(exclude=("modbus",))
            return False
        session = self._session_ctx() or self.active_session()
        normalized = [modbus_master.normalize_poll(rule) for rule in rules]
        if not normalized:
            return False
        old_inflight = self._mbm_inflight
        old_ar = bool(getattr(session, "_ar_enabled", False)) if session else False
        self._device_scan_state = {
            "rules": normalized,
            "completed": set(),
            "on_result": on_result,
            "on_done": on_done,
            "old_on": bool(getattr(session, "_mbm_enabled", False)) if session else bool(self._mbm_on),
            "old_mbm_enabled": bool(getattr(session, "_mbm_enabled", False)) if session else False,
            "old_ar_enabled": old_ar,
            "old_results": {
                index: dict(result) for index, result in (self._mbm_results or {}).items()
            },
            "timeout_ms": max(50, min(5000, int(timeout_ms))),
            "finishing": False,
        }
        # 允许多标签并发扫描：若已有其它会话持有 device_scan pin，本扫描不抢。
        # 全局 pin 仅服务 close_conn 兜底定位 owner；per-session state 已独立，
        # 后结束的扫描在 _stop_device_scan 里只清属于自己的 pin。
        if self._io_owner_session("device_scan") is None:
            self._io_bind_owner("device_scan", session)
        self._io_bind_owner("modbus", session)
        # 接管一个已经在轮询的 RTU/ASCII 主机时，旧请求的迟到响应不能误配给扫描首项。
        if old_inflight is not None and self._mbm_variant_eff() in ("rtu", "ascii"):
            guard_ms = max(self._MBM_MIN_GUARD_MS,
                           int(old_inflight.get("timeout_ms", self._MBM_TIMEOUT_MS)))
            self._mbm_guard_until = max(
                self._mbm_guard_until, time.monotonic() + guard_ms / 1000.0)
        self._device_scan_timeout_ms = max(50, min(5000, int(timeout_ms)))
        # 本会话扫描期间关掉本会话自动应答从机（不改其它标签、不改窗口规则）。
        if session is not None:
            session._ar_enabled = False
        if session is self.active_session():
            self._ar_on = False
            self._sync_autoreply_ui()
        try:
            if session is self.active_session():
                self._mbm_on = True
            if session is not None:
                session._mbm_enabled = True
            self._mbm_restart()
            self._refresh_workspace_statuses()
            refresh = getattr(self, "_refresh_session_tab_styles", None)
            if callable(refresh):
                refresh()
        except Exception:
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
            sid = getattr(self._session_ctx() or self.active_session(), "id", None)
            QTimer.singleShot(
                0, lambda _sid=sid: self._stop_device_scan_for(_sid, cancelled=False))

    def _stop_device_scan_for(self, session_id, cancelled=False):
        session = self.find_session(session_id) if session_id else None
        if session is None:
            return
        with self._with_session(session):
            self._stop_device_scan(cancelled=cancelled)

    def _stop_device_scan(self, cancelled=False):
        ctx = self._session_ctx()
        state = getattr(ctx, "_device_scan_state", None) if ctx is not None else None
        if state is None:
            owner = self._io_owner_session("device_scan")
            if owner is not None and owner is not ctx:
                with self._with_session(owner):
                    self._stop_device_scan(cancelled=cancelled)
            return
        self._device_scan_state = None
        owner = self._io_owner_session("device_scan")
        if owner is None or owner is ctx:
            self._io_clear_owner("device_scan")
        restored_mbm = bool(state.get("old_mbm_enabled", state.get("old_on", False)))
        if ctx is not None:
            ctx._mbm_enabled = restored_mbm
            ctx._ar_enabled = bool(state.get("old_ar_enabled", False))
        if ctx is self.active_session():
            self._mbm_on = restored_mbm
            self._ar_on = bool(state.get("old_ar_enabled", False))
        if restored_mbm:
            self._io_bind_owner("modbus", ctx)
        else:
            self._io_clear_owner("modbus")
        self._mbm_restart()
        self._mbm_results = state.get("old_results") or {}
        dlg = getattr(self, "_mbm_dlg", None)
        if dlg is not None and ctx is self.active_session():
            for index, result in self._mbm_results.items():
                try:
                    dlg.update_result(index, result.get("status", ""),
                                      result.get("text", ""))
                except Exception:
                    _log.debug("_stop_device_scan failed", exc_info=True)
        if ctx is self.active_session():
            self._sync_autoreply_ui()
        try:
            state["on_done"](bool(cancelled))
        except Exception:
            _log.debug("device_scan on_done failed", exc_info=True)
        self._refresh_workspace_statuses()
        refresh = getattr(self, "_refresh_session_tab_styles", None)
        if callable(refresh):
            refresh()

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
        # This window-wide recorder and the plot/dashboard dialogs have no
        # session column. Background MBM must not mix another tab into them.
        if self._session_ctx() is not self.active_session():
            return
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
            from project.device_resources import decode_modbus_samples
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
        if self._session_ctx() is not self.active_session():
            return
        if not self._structured_recorder.recording:
            return
        rules = self._proto_rules()
        frame = bytes(data)
        rule = binproto.first_matching_rule(rules, frame)
        if rule is None:
            self._note_parse_diag(matched=False)
            return
        now = time.time()
        samples = []
        pairs, ok, oob = binproto.extract_rule_fields(rule, frame)
        self._note_parse_diag(matched=True, field_ok=ok, field_oob=oob)
        for name, offset, typ, value in pairs:
            size = binproto.field_size(typ)
            samples.append({
                "timestamp": now, "source": "protocol", "tag": name,
                "value": value, "unit": "",
                "raw": bytes(frame[offset:offset + size]).hex(" ").upper(),
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
            from ui.device_center_dialog import DeviceCenterDialog
            self._device_center_dlg = DeviceCenterDialog(self)
        elif not self._device_center_dlg.isVisible():
            self._device_center_dlg.reload_cfg()
        self._device_center_dlg.show()
        self._device_center_dlg.raise_()
        self._device_center_dlg.activateWindow()
        sync = getattr(self._device_center_dlg, "sync_session", None)
        if callable(sync):
            sync()

    def _open_structured_record(self):
        if self._structured_dlg is None:
            from ui.structured_record_dialog import StructuredRecordDialog
            self._structured_dlg = StructuredRecordDialog(self)
        self._structured_dlg.refresh_rows()
        self._structured_dlg.show()
        self._structured_dlg.raise_()
        self._structured_dlg.activateWindow()

    def _open_modbus_master(self):
        if getattr(self, "_mbm_dlg", None) is None:
            from ui.modbus_master_dialog import ModbusMasterDialog
            self._mbm_dlg = ModbusMasterDialog(self)
        dlg = self._mbm_dlg
        if not dlg._dirty:           # 保留尚未“应用”的界面草稿；已提交时才从运行配置刷新
            dlg.reload_rows()
        dlg.setEnabled(self._device_scan_state is None)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()


    def _tx_format_from_session(self, session=None):
        """Resolve append-newline / checksum for the context session.

        Active tab uses live sidebar widgets; background uses display_opts.
        Returns (append_on, append_idx, checksum_idx).
        """
        session = session or self._session_ctx()
        if session is None or session is self.active_session():
            append_on = (self.sw_append_newline.isChecked()
                         if hasattr(self, "sw_append_newline") else False)
            append_idx = (self.cb_append_nl.currentIndex()
                          if hasattr(self, "cb_append_nl") else 0)
            cs_idx = (self.cb_checksum.currentIndex()
                      if hasattr(self, "cb_checksum") else 0)
            return bool(append_on), int(append_idx), int(cs_idx)
        opts = session.display_opts or {}
        append_on = bool(opts.get("append_nl_on", False))
        try:
            append_idx = int(opts.get("append_nl", 0) or 0)
        except (TypeError, ValueError):
            append_idx = 0
        try:
            cs_idx = int(opts.get("checksum", 0) or 0)
        except (TypeError, ValueError):
            cs_idx = 0
        return append_on, append_idx, cs_idx

    def _send_text(self, raw, hex_mode=None, newline=None, checksum=None, target=None,
                   encoding=None, record_macro=True, allow_during_exclusive=False,
                   allow_running_dsl=False, notify_ui=True,
                   feed_window_engines=True) -> bool:
        """解析并发送一段文本(HEX/文本)，复用追加换行+校验+显示。
        hex_mode/newline/checksum/encoding 为 None 时用主界面当前设置；调用方可传入独立值。
          newline: None=全局; 0=无 1=CRLF 2=LF 3=CR
          checksum: None=全局; 否则校验项索引(0=无…)
        成功返回 True"""
        blocked = (not allow_during_exclusive
                   and self._manual_send_blocked(allow_running_dsl=allow_running_dsl))
        pre = _ar_core_send_preflight(
            exclusive_blocked=blocked,
            is_open=self._is_open(),
            raw_empty=not raw,
        )
        if pre == "exclusive":
            if notify_ui:
                self.toast_io_exclusive_busy()
            return False
        if pre == "not_open":
            if notify_ui:
                self.toast(self._t("net_not_open"), error=True)
            return False
        if pre == "empty":
            return False
        use_hex = self.sw_tx_hex.isChecked() if hex_mode is None else hex_mode

        try:
            if use_hex:
                parsed = _ar_core_parse_tx_hex(raw)
                if parsed["error"] == "empty":
                    return False
                if parsed["error"] == "bad_chars":
                    err = self._t(
                        "err_hex_invalid_chars",
                        chars=" ".join(repr(c) for c in parsed["bad_chars"]),
                    )
                    if notify_ui:
                        self.toast(self._t("err_hex_bad", e=err), error=True)
                    return False
                if parsed["error"] == "odd_length":
                    if notify_ui:
                        self.toast(self._t("err_hex_odd"), error=True)
                    return False
                if not parsed["ok"]:
                    if notify_ui:
                        self.toast(self._t("err_hex_bad", e="value_error"), error=True)
                    return False
                data = parsed["data"]
            else:
                codec = self._send_codec()
                if encoding is not None:
                    codec = _cfg_norm_enc(encoding)
                    if codec == "auto":
                        codec = "utf-8"
                data = raw.encode(codec, errors="replace")
        except ValueError as e:
            if notify_ui:
                self.toast(self._t("err_hex_bad", e=e), error=True)
            return False

        append_on, append_idx, default_cs = self._tx_format_from_session()
        data = _ar_core_append_tx_newline(
            data,
            newline=newline,
            global_on=append_on,
            global_idx=append_idx,
        )

        cs_idx = default_cs if checksum is None else checksum
        try:
            data = data + self.compute_checksum(data, cs_idx)
        except _CHECKSUM_ERRORS as e:
            _log.debug("checksum append failed", exc_info=True)
            if notify_ui:
                self.toast(self._t("err_checksum", e=e), error=True)
            return False

        send_target = self._send_target() if target is None else target
        try:
            sent = self.conn.send(data, send_target)
        except _TX_IO_ERRORS as e:
            _log.debug("send failed", exc_info=True)
            self._stat_note_tx_error()
            if notify_ui:
                self._refresh_stat_labels(with_tooltip=False)
                self.toast(self._t(
                    "err_send_failed",
                    e=conn_error_tips.format_conn_error_detail(str(e), self._t)),
                    error=True)
            return False
        strict_full_write = getattr(self, "_conn_proto", None) in (
            PROTO_SERIAL, PROTO_TCP_CLIENT, PROTO_BLE, PROTO_RTT)
        outcome = _ar_core_classify_send(
            sent=sent, payload_len=len(data),
            no_target_sentinel=SEND_NO_TARGET,
            strict_full_write=strict_full_write,
        )
        if outcome == "no_target":
            self._stat_note_tx_error()
            if notify_ui:
                self._refresh_stat_labels(with_tooltip=False)
                self.toast(self._t("net_no_target"), error=True)
            return False
        if outcome != "ok":
            if outcome == "fail_partial":
                self.tx_bytes += sent
                acc = getattr(self, "_io_stats", None)
                if acc is not None:
                    acc.note_tx_bytes(sent)
            self._abort_partial_tcp_stream(
                sent, len(data), update_ui=notify_ui)
            self._stat_note_tx_error()
            if notify_ui:
                self._refresh_stat_labels(with_tooltip=False)
                self.toast(self._t("net_send_failed"), error=True)
            return False

        self._stat_note_tx(len(data))

        if record_macro:
            self._macro_record_tx(data)
        if feed_window_engines:
            self._record_stream_tx(data, source=send_target)

        disp = _ar_core_tx_display_mode(
            hexdump_on=self._session_display_flag(
                "hexdump_on", bool(getattr(self, "_hexdump_on", False))),
            numview_on=self._session_display_flag(
                "numview_on", bool(getattr(self, "_numview_on", False))),
            rx_hex=self._session_display_flag(
                "rx_hex",
                self.sw_rx_hex.isChecked() if hasattr(self, "sw_rx_hex") else False),
        )
        if disp == "hexdump":
            display = self._hexdump_block(data)
        elif disp == "numview":
            display = self._numview_block(data, carry=False)
        elif disp == "hex":
            display = self._bytes_to_hex(data) + " "
        else:
            display = data.decode(self._send_codec(), errors="replace")
        self._append_block_data(display, direction="tx", force_new_block=True)
        self._last_direction = "tx"
        return True

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
            # Entering terminal mode stops ALL sessions' period timers and
            # multi-send cycles (not only the active tab).
            if hasattr(self, "sw_period") and self.sw_period.isChecked():
                self.sw_period.setChecked(False)
            for session in getattr(self, "_sessions", []) or []:
                session.period_on = False
                timer = getattr(session, "_period_timer", None)
                if timer is not None and timer.isActive():
                    timer.stop()
            self._ms_stop_all_cycles()
        self._apply_terminal_ui(on)
        # 终端模式改变正文块的角色/可匹配性：key 含 terminal_on，开关即触发全量重扫，
        # 清掉切换时残留在旧 RX 文本上的高亮（终端块无 ROLE_PROP，规则本就不匹配）。
        if hasattr(self, "_kw_timer"):
            self._kw_timer.stop()
            self._kw_mark_full()
            self._refresh_extra_selections()
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
            self.toast_io_exclusive_busy()
            return
        if not self._is_open():
            return
        send_target = self._send_target()
        try:
            sent = self.conn.send(data, send_target)
        except _TX_IO_ERRORS as e:
            _log.debug("terminal send failed", exc_info=True)
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
        strict_full_write = getattr(self, "_conn_proto", None) in (
            PROTO_SERIAL, PROTO_TCP_CLIENT, PROTO_BLE, PROTO_RTT)
        if strict_full_write and sent != len(data):
            # 与普通发送/文件传输保持一致：短写只统计实际交付的前缀，不能把
            # 整块登记到宏录制、数据录制或 PCAP。TCP 流还需断开重建。
            if sent < len(data):
                self.tx_bytes += sent
                acc = getattr(self, "_io_stats", None)
                if acc is not None:
                    acc.note_tx_bytes(sent)
            self._abort_partial_tcp_stream(sent, len(data))
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
        except (TypeError, ValueError, RuntimeError, OSError):
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
        st = _term_vt.resolve_stream_state(
            getattr(self, "_term_streams", {}), stream_source,
            global_sgr=self._term_sgr, global_esc=self._term_esc,
            global_discard_csi=self._term_discard_csi,
            global_discard_osc=self._term_discard_osc,
            global_osc_prev_esc=self._term_osc_prev_esc)
        term_sgr = st["sgr"]
        esc = st["esc"]
        discard_csi = st["discard_csi"]
        discard_osc = st["discard_osc"]
        osc_prev_esc = st["osc_prev_esc"]
        if st["use_global"]:
            self._term_esc = ""
            self._term_discard_csi = False
            self._term_discard_osc = False
            self._term_osc_prev_esc = False
        buf = []
        # 基础格式必须从零构造，不能沿用光标处的格式：光标停在上一段带色文字后面时，
        # 继承来的格式会连 ANSI 的颜色和属性一起带上 —— 关掉 ANSI 着色后新文字仍是红的。
        base_fmt = QTextCharFormat()
        base_fmt.setForeground(QColor(self._theme()["fg"]))
        base_fmt.setProperty(VIEW_PROP, VIEW_TERMINAL)

        def _make_fmt():
            """当前 SGR 样式对应的字符格式；关掉 ANSI 着色时恒为无色的基础格式。"""
            st = term_sgr
            if (not bool(self._display_value("ansi_on", self._ansi_on))
                    or st is None or st.is_default()):
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
            self._term_esc = esc
            self._term_discard_csi = discard_csi
            self._term_discard_osc = discard_osc
            self._term_osc_prev_esc = osc_prev_esc
        else:
            self._term_streams = _term_vt.store_stream_state(
                self._term_streams, stream_source,
                sgr=term_sgr, esc=esc, discard_csi=discard_csi,
                discard_osc=discard_osc, osc_prev_esc=osc_prev_esc)
        self._term_pos = cur.position()
        # Terminal bypasses _append_block_data; apply the same char budget and
        # keep _term_pos valid after a head trim (P1: no-newline growth).
        trimmed = self._trim_recv_overflow()
        if trimmed:
            self._kw_mark_full()
        if trimmed and self._term_pos is not None:
            last = self.txt_recv.document().characterCount() - 1
            self._term_pos = _term_vt.term_pos_after_trim(
                self._term_pos, trimmed, last)
        # Keep line-end flag in sync for non-terminal RX after leaving terminal.
        self._txt_ends_with_nl = self.txt_recv.document().lastBlock().text() == ""
        if was_bottom:
            sb = self.txt_recv.verticalScrollBar()
            sb.setValue(sb.maximum())
            if self._session_ctx() is self.active_session():
                self.btn_to_bottom.hide()

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
                self._kw_reset_inc()
                self.txt_recv.setExtraSelections([])
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
        session = self._session_ctx() or self.active_session()
        if session is not None:
            session.period_on = bool(on)
            if hasattr(self, "ed_period_ms"):
                session.period_ms = self.ed_period_ms.text()
        if on:
            if self._io_task_busy(exclude=("periodic",)):
                self.toast_io_exclusive_busy(exclude=("periodic",))
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
            if session is not None:
                session.period_ms = str(ms)
                session.period_on = True
                self._sync_session_period_timer(session)
            else:
                self.send_timer.start(ms)
        else:
            if session is not None:
                session.period_on = False
                if session._period_timer.isActive():
                    session._period_timer.stop()
            else:
                self.send_timer.stop()
        self._refresh_session_tab_styles()


    def on_wrap_toggled(self, on):
        mode = QTextEdit.WidgetWidth if on else QTextEdit.NoWrap
        for session in self.sessions():
            if session.txt_recv is not None:
                session.txt_recv.setLineWrapMode(mode)

    # ----- 日志记录 -----
    def _parse_log_limit(self, text) -> int:
        """Parse split-size combo text -> bytes (0 = unlimited)."""
        return log_naming.parse_size_limit(text)

    def _on_log_split_changed(self, _text=None):
        """Change split size: apply immediately to the active session's log."""
        session = self._session_ctx() or self.active_session()
        limit = self._parse_log_limit(self.cb_log_split.currentText())
        if session is not None:
            session._log_limit = limit
            opts = dict(session.display_opts or {})
            opts["log_split"] = self.cb_log_split.currentText()
            session.display_opts = opts

    def _log_session(self, session=None):
        return session or self._session_ctx() or self.active_session()

    def _restore_session_log_intent(self, session):
        """Reopen one session's live log after an automatic reconnect."""
        if (session is None or not session.log_wanted
                or not session.log_base_path):
            return False
        if session._log_file is not None:
            return True
        now = datetime.now()
        ok = self._open_log_segment(
            self._log_segment_path(now, session=session),
            when=now, session=session)
        if not ok:
            session.log_wanted = False
            if session is self.active_session() and hasattr(self, "sw_log_file"):
                self.sw_log_file.blockSignals(True)
                self.sw_log_file.setChecked(False)
                self.sw_log_file.blockSignals(False)
        return bool(ok)

    def _log_conn_token(self, session=None) -> str:
        """%port expansion: device / IP_port / proto / empty."""
        session = self._log_session(session)
        if session is not None:
            proto = session._conn_proto
            cfg = session._conn_cfg
        else:
            proto = getattr(self, "_conn_proto", None)
            cfg = getattr(self, "_conn_cfg", None)
        return log_naming.conn_token(
            proto, cfg,
            serial_name=PROTO_SERIAL,
            tcp_client_name=PROTO_TCP_CLIENT)

    def _log_segment_path(self, when=None, session=None, seg=None) -> str:
        session = self._log_session(session)
        base = (session.log_base_path if session is not None
                else getattr(self, "_log_base_path", "")) or ""
        if seg is None:
            seg = int(session.log_seg if session is not None
                      else getattr(self, "_log_seg", 0) or 0)
        return log_naming.segment_path(
            base, when or datetime.now(),
            port=self._log_conn_token(session), seg=int(seg or 0))

    def _set_log_path_label(self, path):
        """Update status-bar log path (only while recording)."""
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
        self.lbl_log_path.setText("\U0001f4dd " + fm.elidedText(path, Qt.ElideMiddle, w))
        set_tooltip(self.lbl_log_path, path)
        if hasattr(self, "_log_path_sep"):
            self._log_path_sep.show()

    def _log_path_owned_by_other(self, path, except_session=None):
        path = os.path.normcase(os.path.abspath(path)) if path else ""
        if not path:
            return None
        for s in getattr(self, "_sessions", []) or []:
            if except_session is not None and s is except_session:
                continue
            other = s._log_file_path or ""
            if other and os.path.normcase(os.path.abspath(other)) == path:
                return s
        return None

    def _open_log_segment(self, path, when=None, session=None) -> bool:
        session = self._log_session(session)
        if session is None:
            return False
        conflict = self._log_path_owned_by_other(path, except_session=session)
        if conflict is not None:
            self.toast(self._t("err_log_path_busy", path=path), error=True)
            return False
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            if session._log_file is not None:
                self._close_log_segment(datetime.now(), session=session)
            session._log_file = open(path, "a", encoding="utf-8")
            session._log_file_path = path
            session._log_opened_at = when or datetime.now()
            ts = session._log_opened_at.strftime("%Y-%m-%d %H:%M:%S")
            session._log_file.write(self._t("log_header", time=ts))
            self._flush_log_file(session=session, to_disk=True)
            session._log_ends_with_nl = True
            session.log_wanted = True
            if session is self.active_session():
                self._set_log_path_label(path)
            return True
        except _LOG_IO_ERRORS as e:
            _log.debug("open log segment failed", exc_info=True)
            self.toast(self._t("err_open_log", e=e), error=True)
            return False

    def _close_log_segment(self, when, session=None):
        """Write footer -> flush -> close for one session."""
        session = self._log_session(session)
        if session is None or not session._log_file:
            return
        try:
            session._log_file.write(self._t(
                "log_footer", time=when.strftime("%Y-%m-%d %H:%M:%S")))
            self._flush_log_file(session=session, to_disk=True)
        except (OSError, TypeError, ValueError, KeyError):
            _log.debug("log footer/flush failed", exc_info=True)
        try:
            session._log_file.close()
        except OSError:
            _log.debug("log close failed", exc_info=True)
        session._log_file = None
        session._log_ends_with_nl = True

    def _toast_log_rotate_failed(self, err):
        """Throttle: size/date rolls can retry every write if the new path stays bad."""
        now = time.monotonic()
        last = float(getattr(self, "_log_rotate_fail_at", 0.0) or 0.0)
        if now - last < 5.0:
            return
        self._log_rotate_fail_at = now
        self.toast(self._t("err_log_rotate", e=err), error=True)

    def _rotate_log_to(self, path, when, session, next_seg):
        """Open the new segment first; only then close the old one.

        If the new path cannot be created, the current file stays open and
        logging continues. Returns True when the switch committed.
        """
        old = session._log_file
        if old is None:
            session.log_seg = next_seg
            return self._open_log_segment(path, when=when, session=session)
        conflict = self._log_path_owned_by_other(path, except_session=session)
        if conflict is not None:
            self._toast_log_rotate_failed(self._t("err_log_path_busy", path=path))
            return False
        new_f = None
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            new_f = open(path, "a", encoding="utf-8")
            ts = when.strftime("%Y-%m-%d %H:%M:%S")
            new_f.write(self._t("log_header", time=ts))
            new_f.flush()
        except _LOG_IO_ERRORS as e:
            if new_f is not None:
                try:
                    new_f.close()
                except OSError:
                    _log.debug("log rotate: close failed new segment", exc_info=True)
            _log.debug("log rotate: open new segment failed", exc_info=True)
            self._toast_log_rotate_failed(e)
            return False
        try:
            old.write(self._t("log_footer", time=when.strftime("%Y-%m-%d %H:%M:%S")))
            self._flush_log_file(session=session, to_disk=True)
        except (OSError, TypeError, ValueError, KeyError):
            _log.debug("log rotate: old footer/flush failed", exc_info=True)
        try:
            old.close()
        except OSError:
            _log.debug("log rotate: old close failed", exc_info=True)
        session._log_file = new_f
        session._log_file_path = path
        session._log_opened_at = when
        session.log_seg = next_seg
        session._log_ends_with_nl = True
        session.log_wanted = True
        if session is self.active_session():
            self._set_log_path_label(path)
        return True

    def _maybe_rotate_log(self, now=None, session=None):
        session = self._log_session(session)
        if session is None or not session._log_file:
            return
        now = now or datetime.now()
        if log_naming.should_roll_date(
                session._log_opened_at, now, session.log_base_path):
            path = self._log_segment_path(now, session=session, seg=0)
            self._rotate_log_to(path, now, session, next_seg=0)
            return
        try:
            cur = session._log_file.tell()
        except (OSError, ValueError):
            _log.debug("log tell() failed", exc_info=True)
            return
        if not log_naming.should_roll_size(cur, session._log_limit):
            return
        next_seg = int(session.log_seg or 0) + 1
        path = self._log_segment_path(now, session=session, seg=next_seg)
        self._rotate_log_to(path, now, session, next_seg=next_seg)

    def on_log_file_toggled(self, on):
        session = self._log_session()
        if on:
            path, _ = QFileDialog.getSaveFileName(
                self, self._t("dlg_log_path"),
                "data_log_%s.log" % datetime.now().strftime("%Y%m%d_%H%M%S"),
                self._t("filter_text"))
            if not path:
                self.sw_log_file.blockSignals(True)
                self.sw_log_file.setChecked(False)
                self.sw_log_file.blockSignals(False)
                self._refresh_session_tab_styles()
                return
            if session is None:
                self.sw_log_file.setChecked(False)
                self._refresh_session_tab_styles()
                return
            session.log_base_path = path
            session.log_seg = 0
            if hasattr(self, "cb_log_split"):
                session._log_limit = self._parse_log_limit(
                    self.cb_log_split.currentText())
            now = datetime.now()
            real = self._log_segment_path(now, session=session)
            if self._open_log_segment(real, when=now, session=session):
                self.toast(self._t("log_started", path=real))
            else:
                self.sw_log_file.setChecked(False)
        else:
            if session is not None:
                session.log_wanted = False
            self._close_log_file(session=session)
        self._refresh_session_tab_styles()

    def _close_log_file(self, session=None, toast=True):
        session = self._log_session(session)
        if session is None or not session._log_file:
            if session is not None:
                session._log_file_path = ""
                session._log_opened_at = None
            return
        path = session._log_file_path
        self._close_log_segment(datetime.now(), session=session)
        if toast:
            self.toast(self._t("log_stopped", path=path))
        session._log_file_path = ""
        session._log_opened_at = None
        if session is self.active_session():
            self._set_log_path_label("")


    def change_recv_font_size(self, delta):
        new_size = self._recv_font_size + delta
        new_size = _cfg_clamp_font(new_size)
        if new_size == self._recv_font_size:
            return
        self._recv_font_size = new_size
        for session in self.sessions():
            if session.txt_recv is not None:
                session.txt_recv.setFont(mono_font(new_size))
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
        for session in self.sessions():
            if session.txt_recv is not None:
                session.txt_recv.document().setMaximumBlockCount(n)

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
        show_ts = self._session_display_flag(
            "show_timestamp",
            self.sw_show_timestamp.isChecked()
            if hasattr(self, "sw_show_timestamp") else False)
        if not show_ts:
            return ""
        fmt = self._display_value(
            "ts_format", getattr(self, "_ts_format", "absolute"))
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
        except _LOG_IO_ERRORS as e:
            _log.debug("save recv failed", exc_info=True)
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
        except _LOG_IO_ERRORS as e:
            _log.debug("load file to send failed", exc_info=True)
            self.toast(self._t("err_read_failed", e=e), error=True)

    def clear_recv(self):
        self.txt_recv.clear()
        self._recv_highlight_line = -1
        self._bookmarks = []
        self._bookmark_idx = -1
        self.txt_recv.setExtraSelections([])
        self._kw_reset_inc()
        self.btn_to_bottom.hide()
        self._reset_stats()
        self._reset_recv_state(reset_dashboard=True)
        self._refresh_quick_start()

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
        sessions = list(getattr(self, "_sessions", ()) or ())
        for session in sessions:
            with self._with_session(session):
                rates = self._io_stats.tick(now=now)
                self._rx_rate = rates["rx_rate"]
                self._tx_rate = rates["tx_rate"]
                self._rx_peak = self._io_stats.rx_peak
                self._tx_peak = self._io_stats.tx_peak
                self._rx_bytes_mark = self._io_stats._rx_bytes_mark
                self._tx_bytes_mark = self._io_stats._tx_bytes_mark
                self._rate_time_mark = self._io_stats._time_mark
        active = self.active_session()
        if active is None:
            return
        with self._with_session(active):
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
        """状态栏右键：I/O Graph / 重置统计（文字跟随语言、配色跟随主题）。"""
        menu = QMenu(self.status_bar)
        c = chrome_for(self._theme_id())
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['card_bg']}; color: {c['text']};
                     border: 1px solid {c['separator']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
            QMenu::item:selected {{ background-color: {c['accent']}; color: #FFFFFF; }}
        """)
        act_io = menu.addAction(self._t("plot_io_graph"))
        act_reset = menu.addAction(self._t("stat_reset"))
        chosen = menu.exec_(self.status_bar.mapToGlobal(pos))
        menu.deleteLater()   # 每次右键新建、挂在 status_bar 下；exec_ 后主动回收，避免累积为常驻子对象
        if chosen is act_io:
            self.open_io_graph()
        elif chosen is act_reset:
            self._reset_stats()

    def toast(self, msg, error=False):
        if error:
            self.status_bar.showMessage("⚠ " + msg, 3500)
        else:
            self.status_bar.showMessage("✓ " + msg, 2500)

    def _toast_if_active_session(self, msg, error=False):
        """Skip toasts originating from a background session's engine."""
        ctx_fn = getattr(self, "_session_ctx", None)
        act_fn = getattr(self, "active_session", None)
        if callable(ctx_fn) and callable(act_fn):
            ctx = ctx_fn()
            act = act_fn()
            if ctx is not None and act is not None and ctx is not act:
                return
        self.toast(msg, error=error)

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

        i18n_ui.apply_tr_properties(
            self.findChildren(QWidget), self._t, set_tooltip,
            label_col_width=self._label_col_width, log=_log)

        self._apply_theme_label_styles()
        self._update_legend_label()
        if hasattr(self, "_refresh_session_tab_styles"):
            try:
                from sessions.session import format_default_title
                for s in self.sessions():
                    if getattr(s, "title_index", None) is not None:
                        s.title = format_default_title(self, s.title_index)
                self._refresh_session_tab_styles()
            except Exception:
                _log.debug("retranslate session tabs failed", exc_info=True)

        if hasattr(self, "cb_checksum"):
            i18n_ui.refill_combo_keys(
                self.cb_checksum, CHECKSUM_KEYS, self._t)

        if hasattr(self, "cb_ts_format"):
            i18n_ui.refill_combo_data_items(
                self.cb_ts_format, _ui_ts_format_items, self._t)
        if hasattr(self, "cb_search_mode"):
            i18n_ui.refill_combo_data_items(
                self.cb_search_mode, _ui_search_mode_items, self._t)

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
        # RTT 调试器下拉的「自动」项随语言刷新
        if hasattr(self, "cb_rtt_probe") and self.cb_rtt_probe.count() > 0:
            was_auto = not self._rtt_probe_text()
            self.cb_rtt_probe.blockSignals(True)
            self.cb_rtt_probe.setItemText(0, self._t("rtt_probe_auto"))
            if was_auto:
                self.cb_rtt_probe.setCurrentIndex(0)
            self.cb_rtt_probe.blockSignals(False)

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
            self._set_ms_cycle_btn(self._session_ms_cycle_active())
        # 发送卡片两行三列等列宽：必须在 btn_ms_cycle 文字更新之后，否则取的是旧语言的 sizeHint
        self._align_send_card_cols()
        self._fit_data_toolbar()   # 数据区工具栏按钮宽度随语言重算，防新语言文字被裁
        self._refresh_project_dirty_label()
        if not (self._project_name or self._project_path):
            self._update_project_label()
        self._refresh_workspace_statuses()
        self._retranslate_workspace_template_panel()
        # _ble_scan_dlg 是顶层非模态窗（QDialog(None)），findChildren 刷不到。
        i18n_ui.retranslate_dialogs(self)
        if getattr(self, "_ble_scan_dlg", None) is not None:
            self._ble_scan_dlg.retranslate()
        if getattr(self, "_rtt_dev_dlg", None) is not None:
            self._rtt_dev_dlg.retranslate()
        self._rebuild_connection_preset_combo()
        # 选中即算校验和的状态栏文案是算出来的（含「选中」「选区过大」等译词），
        # tr_text 机制刷不到 —— 重算一次，让它跟着切语言
        self._update_sel_checksum()

    # ----- 持久化 -----
    @staticmethod
    def _settings_file(profile="") -> str:
        """
        配置落在 ``<基目录>/config/settings.ini``（多窗口为 settings-N.ini）。
        优先 exe / 源码同级（绿色版可连 config 一起拷走）；写不动就回退
        %APPDATA%\\CommTool\\config\\。首次启动会把旧版同级的 settings*.ini 迁进 config/。
        macOS：不写进 .app 包内，固定 ~/Library/Application Support/CommTool/config/。
        profile：""=主配置；其余=settings-<profile>.ini。
        """
        if sys.platform == "darwin":
            support = os.path.join(
                os.path.expanduser("~/Library/Application Support"), "CommTool")
            home_legacy = os.path.join(os.path.expanduser("~"), "CommTool")
            legacy = [support]
            if not profile:
                legacy.append(home_legacy)
            return _cfg_resolve_settings_file(profile, [(support, legacy)])

        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))

        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        appdata_root = os.path.join(appdata, "CommTool")
        appdata_legacy = [appdata_root, base]
        if not profile:
            appdata_legacy.append(os.path.join(appdata, "NetworkTool"))
        return _cfg_resolve_settings_file(profile, [
            (base, [base]),
            (appdata_root, appdata_legacy),
        ])


    def _begin_workspace_autosave_pause(self):
        depth = int(getattr(self, "_autosave_suppress", 0))
        timer = getattr(self, "_autosave_timer", None)
        if depth == 0:
            self._autosave_resume_pending = bool(
                timer is not None and timer.isActive())
        if timer is not None:
            timer.stop()
        self._autosave_suppress = depth + 1

    def _end_workspace_autosave_pause(self):
        depth = max(0, int(getattr(self, "_autosave_suppress", 0)) - 1)
        self._autosave_suppress = depth
        if depth != 0:
            return
        resume = bool(getattr(self, "_autosave_resume_pending", False))
        self._autosave_resume_pending = False
        timer = getattr(self, "_autosave_timer", None)
        if (resume and timer is not None
                and getattr(self, "_autosave_ready", False)
                and not getattr(self, "_user_closing", False)):
            timer.start()

    def _workspace_autosave_paused(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            self._begin_workspace_autosave_pause()
            try:
                yield
            finally:
                self._end_workspace_autosave_pause()
        return _cm()

    def _schedule_workspace_autosave(self, *_args):
        """Debounce user edits into a workspace draft; ignore timer/engine ticks."""
        if not getattr(self, "_autosave_ready", False):
            return
        if int(getattr(self, "_autosave_suppress", 0)) > 0:
            return
        if getattr(self, "_user_closing", False):
            return
        timer = getattr(self, "_autosave_timer", None)
        if timer is None:
            return
        timer.start()

    def _flush_workspace_autosave(self):
        if int(getattr(self, "_autosave_suppress", 0)) > 0:
            return
        if getattr(self, "_user_closing", False):
            return
        self._save_settings()

    def _wire_workspace_autosave(self):
        kick = self._schedule_workspace_autosave
        if hasattr(self, "txt_send"):
            self.txt_send.textChanged.connect(kick)
        for name in getattr(self, "_RESET_LINE_EDITS", ()) or ():
            w = getattr(self, name, None)
            if w is not None and hasattr(w, "textChanged"):
                w.textChanged.connect(kick)
        for name in getattr(self, "_RESET_COMBOS", ()) or ():
            w = getattr(self, name, None)
            if w is not None and hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(kick)
                if w.isEditable() and w.lineEdit() is not None:
                    w.lineEdit().editingFinished.connect(kick)
        if hasattr(self, "cb_port"):
            self.cb_port.activated.connect(kick)
        for name in (
            "sw_tx_hex", "sw_append_newline", "sw_rx_hex", "sw_wrap",
            "sw_show_timestamp", "sw_packet_split", "sw_line_split",
            "sw_vconn_loop", "sw_udp_remote", "cb_checksum", "cb_append_nl",
            "cb_encoding", "cb_theme", "cb_log_split", "cb_ts_format",
            "cb_line_nl", "cb_hexdump_width", "cb_numview_type", "ed_period_ms",
            "sw_hexdump", "sw_numview", "sw_freeze_view", "sw_terminal",
            "sw_period", "sw_log_file", "btn_filter_hl", "cb_view_mode",
            "cb_target", "cb_flow", "sw_dtr", "sw_rts",
        ):
            w = getattr(self, name, None)
            if w is None:
                continue
            if hasattr(w, "toggled"):
                w.toggled.connect(kick)
            elif hasattr(w, "textChanged"):
                w.textChanged.connect(kick)
            elif hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(kick)
        self._autosave_ready = True

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
            if hasattr(self, "ed_ble_address"):
                s.setValue("ble_address", self.ed_ble_address.text())
                s.setValue("ble_name", self.ed_ble_name.text())
                s.setValue("ble_profile", self.cb_ble_profile.currentData() or "fff0")
                s.setValue("ble_service_uuid", self.ed_ble_service.text())
                s.setValue("ble_write_uuid", self.ed_ble_write.text())
                s.setValue("ble_notify_uuid", self.ed_ble_notify.text())
                s.setValue(
                    "ble_write_mode",
                    self.cb_ble_write_mode.currentData() or "auto")
            if hasattr(self, "cb_rtt_device"):
                s.setValue("rtt_device", self.cb_rtt_device.currentText())
                s.setValue("rtt_interface", self.cb_rtt_interface.currentText())
                s.setValue("rtt_speed", self._rtt_speed_text())
                s.setValue("rtt_address", self.ed_rtt_address.text())
                s.setValue("rtt_channel", self.cb_rtt_channel.currentData()
                           if self.cb_rtt_channel.currentData() is not None else 0)
                s.setValue("rtt_probe", self._rtt_probe_text())
                s.setValue("rtt_reset", bool(
                    self.sw_rtt_reset.isChecked()
                    if hasattr(self, "sw_rtt_reset") else False))
            # 串口设置
            s.setValue("ser_port", self.cb_port.currentData() or "")
            s.setValue("ser_baud", self.cb_baud.currentText())
            s.setValue("ser_databits", self.cb_databits.currentText())
            s.setValue("ser_parity", self.cb_parity.currentText())
            s.setValue("ser_stopbits", self.cb_stopbits.currentText())
            s.setValue("ser_flow", self.cb_flow.currentText())
            self._save_sessions_settings()
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
            expanded = _send_options_card.term_section_expanded(
                s.value("sec_send_term", False, type=bool), term_on)
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
        except (TypeError, ValueError, RuntimeError):
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
        # 推迟到 event loop 启动后再应用 — 此时所有 widget 已 show，setStyleSheet 全部生效。
        # Window-owned timer is cancelled automatically if a short-lived test/
        # host deletes the window before its first event-loop turn.
        self._theme_apply_timer.start(0)
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
        if hasattr(self, "ed_ble_address"):
            from transport import ble_uuid
            v = s.value("ble_address", None)
            if v is not None:
                self.ed_ble_address.setText(str(v))
            v = s.value("ble_name", None)
            if v is not None:
                self.ed_ble_name.setText(str(v))
            v = s.value("ble_service_uuid", None)
            if v is not None:
                self.ed_ble_service.setText(str(v))
            v = s.value("ble_write_uuid", None)
            if v is not None:
                self.ed_ble_write.setText(str(v))
            v = s.value("ble_notify_uuid", None)
            if v is not None:
                self.ed_ble_notify.setText(str(v))
            v = s.value("ble_write_mode", None)
            if v is not None and hasattr(self, "cb_ble_write_mode"):
                midx = self.cb_ble_write_mode.findData(
                    ble_uuid.normalize_write_mode(v))
                if midx >= 0:
                    self.cb_ble_write_mode.blockSignals(True)
                    self.cb_ble_write_mode.setCurrentIndex(midx)
                    self.cb_ble_write_mode.blockSignals(False)
            pid = ble_uuid.normalize_profile(s.value("ble_profile", "fff0"))
            idx = self.cb_ble_profile.findData(pid)
            if idx >= 0:
                self.cb_ble_profile.blockSignals(True)
                self.cb_ble_profile.setCurrentIndex(idx)
                self.cb_ble_profile.blockSignals(False)
        if hasattr(self, "cb_rtt_device"):
            from transport import rtt_io
            v = s.value("rtt_device", None)
            if v is not None:
                self.cb_rtt_device.setCurrentText(str(v))
            v = s.value("rtt_interface", None)
            if v is not None:
                self.cb_rtt_interface.setCurrentText(rtt_io.normalize_interface(v))
            v = s.value("rtt_speed", None)
            if v is not None and rtt_io.parse_speed(v) is not None:
                self._set_rtt_speed_text(v)
            v = s.value("rtt_address", None)
            if v is not None:
                self.ed_rtt_address.setText(str(v))
            v = s.value("rtt_channel", None)
            ch = rtt_io.normalize_channel(v)
            if ch is not None:
                cidx = self.cb_rtt_channel.findData(ch)
                if cidx >= 0:
                    self.cb_rtt_channel.blockSignals(True)
                    self.cb_rtt_channel.setCurrentIndex(cidx)
                    self.cb_rtt_channel.blockSignals(False)
            v = s.value("rtt_dll_path", None)
            if v is not None:
                rtt_io_mod.set_dll_hint(str(v))
            v = s.value("rtt_probe", None)
            if v is not None:
                self._set_rtt_probe_text(v)
            if hasattr(self, "sw_rtt_reset"):
                self.sw_rtt_reset.blockSignals(True)
                self.sw_rtt_reset.setChecked(
                    s.value("rtt_reset", False, type=bool))
                self.sw_rtt_reset.blockSignals(False)
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

    @staticmethod
    def _bundled_example_path(name="fixed_header_demo.ctproj"):
        roots = []
        bundle = getattr(sys, "_MEIPASS", "")
        if bundle:
            roots.append(bundle)
        roots.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for root in roots:
            path = os.path.join(root, "examples", name)
            if os.path.isfile(path):
                return path
        return ""

    def _refresh_quick_start(self):
        bar = getattr(self, "quick_start_bar", None)
        if bar is None:
            return
        # 常显：数据刷出来也不收起（此前是「空页面才显示、有数据即隐藏」，
        # 用户反馈数据一来按钮就没了，改回一直可见）。空态才计算最近/示例按钮
        # 的可见性，数据态提前返回，保证高频 RX 下这个 textChanged 槽足够轻。
        if not bar.isVisible():
            bar.setVisible(True)
        view = getattr(self, "txt_recv", None)
        empty = bool(view is not None and view.document().characterCount() <= 1)
        if not empty:
            return
        recent = self._recent_projects() if hasattr(self, "settings") else []
        button = getattr(self, "btn_quick_recent", None)
        if button is not None:
            button.setVisible(bool(recent))
            if recent:
                button.setToolTip(recent[0])
        example = getattr(self, "btn_quick_example", None)
        if example is not None:
            example.setVisible(bool(self._bundled_example_path()))
        virtual = getattr(self, "btn_quick_virtual", None)
        if virtual is not None:
            virtual.setEnabled(not self._is_open())

    def _quick_start_virtual(self):
        # Never overwrite the visible connection fields while a real link is
        # active; doing so would make the form say Virtual while the session
        # still owns its original serial/network connection.
        if self._is_open():
            return False
        self._switch_workspace("terminal")
        self.cb_proto.setCurrentText(PROTO_VIRTUAL)
        self.sw_vconn_loop.setChecked(True, animate=False)
        self._update_net_fields()
        if not self._is_open():
            self.open_conn()
        self.txt_send.setFocus()
        self._refresh_quick_start()
        return True

    def _quick_start_example(self):
        path = self._bundled_example_path()
        if path:
            # Bundled files live in the read-only app bundle. Load one as an
            # unsaved template so Ctrl+S asks for a user path instead of trying
            # to overwrite _MEIPASS / the source-tree example.
            return self._open_project_path(
                path, notify=False, as_template=True)
        return False

    def _quick_start_recent(self):
        recent = self._recent_projects()
        if recent:
            self._open_project_path(recent[0])


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
            "plot_io_graph": self.open_io_graph,
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
        from project.project_templates import protocol_template_settings
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
        from project.project_templates import protocol_template_settings
        cfg = protocol_template_settings(combo.currentData() or "raw")
        with self._workspace_autosave_paused():
            if not self._prepare_project_switch():
                return
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
                self._rollback_project_switch_sessions()
                self._info_dlg(
                    self._t("workspace_template_title"),
                    self._t("workspace_template_fail", err=str(exc)), is_error=True)
                return
            self._commit_project_switch_sessions()
            # The template switch already replaced the runtime tab set. Persist the
            # new single-session snapshot now so an abnormal exit cannot restore
            # the previous sessions_v1 / active_session_id on the next launch.
            self._save_sessions_settings()
            self.settings.sync()
        self._refresh_project_dirty_label()
        self.toast(self._t("workspace_template_applied", name=template_name))

    def _build_workspace_page(self, key):
        return _workspace_ui.build_workspace_page(self, key)

    def _workspace_status_info(self, tool_key):
        """返回 (文案, 是否活跃)；None 表示该工具没有可展示的运行状态。"""
        if tool_key == "ar_title":
            sessions = getattr(self, "_sessions", ()) or ()
            active = any(getattr(s, "_ar_enabled", False) for s in sessions)
            return self._t("workspace_enabled" if active else "workspace_inactive"), active
        if tool_key == "mbm_open":
            sessions = getattr(self, "_sessions", ()) or ()
            active = (any(getattr(s, "_mbm_enabled", False) for s in sessions)
                      or bool(getattr(self, "_mbm_on", False)))
            return self._t("workspace_enabled" if active else "workspace_inactive"), active
        if tool_key == "trg_title":
            engine = getattr(self, "_trigger_engine", None)
            active = bool(engine is not None and engine.active())
            return self._t("workspace_enabled" if active else "workspace_inactive"), active
        if tool_key == "seq_title":
            sessions = getattr(self, "_sessions", ()) or ()
            active = any(getattr(s, "_seq_on", False) for s in sessions)
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
            sessions = getattr(self, "_sessions", ()) or ()
            active = any(getattr(s, "_device_scan_state", None) is not None
                         for s in sessions)
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
        # Session chips only on terminal workspace.
        show_sessions = (key == "terminal")
        for attr in ("_session_sep", "_session_tab_strip"):
            w = getattr(self, attr, None)
            if w is not None:
                w.setVisible(show_sessions)
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
        full_text = name + (" *" if dirty is True else "")
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
            dlg = InfoDialog(
                self._t("project_save"),
                self._t("project_save_fail", err=str(e)),
                ok_text=self._t("cancel"),
                is_error=True,
                theme_id=self._theme_id(),
                parent=None,
                third_text=self._t("project_force_continue"),
            )
            return dlg.exec_() == InfoDialog.ThirdAction
        if not dirty:
            return True
        dlg = InfoDialog(
            self._t("project_unsaved_title"),
            self._t("project_unsaved_body",
                    name=self._project_name or self._t("project_untitled")),
            ok_text=self._t("project_save"),
            is_warning=True,
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
            if self.save_project():
                return True
            if getattr(self, "_project_save_cancelled", False):
                self._info_dlg(
                    self._t("project_save"),
                    self._t("project_save_cancelled"))
            return False
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
        from project.project_model import prepare_project_settings
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
        """Stop every old-project session before replacing workspace settings."""
        # Project replacement destroys every Session object.  Window-level
        # workers/timers are pinned by session id and may finish asynchronously;
        # removing their owner underneath them would orphan callbacks (and a
        # running QThread in the transfer/script dialogs).  Use the same hard
        # busy guard as tab close and require the user to stop the task first.
        if any(self._hard_busy_owned_by(s) for s in self._sessions):
            self.toast_session_busy()
            return False
        if any(s.conn is not None for s in self._sessions):
            if not self._confirm_dlg(
                    self._t("project_disconnect_title"),
                    self._t("project_disconnect_body"),
                    ok_text=self._t("project_disconnect"),
                    danger=False):
                return False
        # Keep the disconnected old tabs/views alive until the caller confirms
        # that applying the new workspace succeeded.  Failure can then restore
        # drafts/history instead of leaving an unrelated empty tab behind.
        self._commit_project_switch_sessions()
        self._project_switch_session_snapshot = self._begin_sessions_runtime_reset()
        return (len(self._sessions) == 1
                and self.active_session() is not None
                and self.active_session().conn is None)

    def _commit_project_switch_sessions(self):
        snapshot = getattr(self, "_project_switch_session_snapshot", None)
        self._project_switch_session_snapshot = None
        if snapshot is not None:
            self._commit_sessions_runtime_reset(snapshot)

    def _rollback_project_switch_sessions(self):
        snapshot = getattr(self, "_project_switch_session_snapshot", None)
        self._project_switch_session_snapshot = None
        if snapshot is not None:
            self._rollback_sessions_runtime_reset(snapshot)

    def new_project(self):
        from project.project_wizard import ProjectWizard
        wizard = ProjectWizard(
            self._project_wizard_texts(), visible_conn_types(), self,
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
        views = data["views"]
        from project.project_templates import protocol_template_settings
        template_cfg = protocol_template_settings(
            data["protocol_template"], data["connection_type"])
        # Display choices from the wizard override template recommendations.
        template_cfg["rx_hex"] = views["hex"]
        template_cfg["show_timestamp"] = views["timestamp"]
        # Keep the connection the user confirmed in step 2.
        template_cfg["net_proto"] = data["connection_type"]
        old_cfg = {key: self.settings.value(key, None) for key in self._CFG_KEYS}
        old_path = self._project_path
        old_name = self._project_name
        old_meta = dict(self._project_meta)
        old_baseline = self._project_baseline
        with self._workspace_autosave_paused():
            if not self._prepare_project_switch():
                return
            try:
                self._apply_project_settings(template_cfg, gate_scripts=False)
            except Exception as e:
                self._rollback_project_switch_sessions()
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
                self._rollback_project_switch_sessions()
                self._save_sessions_settings()
                self.settings.sync()
                return
            self._commit_project_switch_sessions()
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

    def _open_project_path(self, path, confirm=True, notify=True, notify_errors=True,
                           as_template=False):
        try:
            from project.project_model import load_project
            payload = load_project(path)
        except Exception as e:
            if notify_errors:
                self._info_dlg(self._t("project_open"),
                               self._t("project_open_fail", err=str(e)), is_error=True)
            return False
        if confirm and not self._confirm_project_switch():
            return False
        with self._workspace_autosave_paused():
            if not self._prepare_project_switch():
                return False
            try:
                from project.project_model import merge_project_resources
                project_settings = merge_project_resources(
                    payload["settings"], payload.get("resources", {}))
                self._apply_project_settings(project_settings)
            except Exception as e:
                self._rollback_project_switch_sessions()
                if notify_errors:
                    self._info_dlg(self._t("project_open"),
                                   self._t("project_open_fail", err=str(e)), is_error=True)
                return False
            self._commit_project_switch_sessions()
            self._project_name = str(payload.get("name") or "")
            self._project_meta = dict(payload.get("metadata") or {})
            if as_template:
                self._project_path = None
                self._project_baseline = None
                self._update_project_label(True)
            else:
                self._project_path = os.path.abspath(path)
                self._project_baseline = self._project_fingerprint(
                    self._collect_project_settings())
                self.settings.setValue("last_project_path", self._project_path)
                self._add_recent_project(self._project_path)
                self._update_project_label()
        if notify:
            self._info_dlg(self._t("project_open"),
                           self._t("project_opened", path=(
                               self._project_path or os.path.abspath(path))))
        return True

    def save_project(self, save_as=False):
        self._project_save_cancelled = False
        path = None if save_as else self._project_path
        if not path:
            default_name = (self._project_name or "CommTool_project") + ".ctproj"
            path, _ = QFileDialog.getSaveFileName(
                self, self._t("project_save"), default_name, self._t("project_filter"))
            if not path:
                self._project_save_cancelled = True
                return False
            if not path.lower().endswith(".ctproj"):
                path += ".ctproj"
        try:
            from project.project_model import collect_project_resources, make_project, save_project
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
        diag = menu.addAction(self._t("diagnostics_export") + "…")
        diag.triggered.connect(self.export_diagnostics)
        act = menu.addAction(self._t("about") + "…")
        act.triggered.connect(self.open_about)
        # 弹在按钮正下方
        from PyQt5.QtCore import QPoint
        self._exec_transient_menu(menu, self.btn_titlebar_help.mapToGlobal(
            QPoint(0, self.btn_titlebar_help.height())))

    def export_diagnostics(self):
        """Export redacted environment/settings plus rolling application logs."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = "CommTool_diagnostics_%s.zip" % stamp
        path, _ = QFileDialog.getSaveFileName(
            self, self._t("diagnostics_export"), name, "ZIP (*.zip)")
        if not path:
            return False
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            log_dir = getattr(QApplication.instance(), "_diagnostics_log_dir", "")
            if not log_dir:
                log_dir = os.path.join(
                    os.path.dirname(self._settings_file(self._profile)), "logs")
            log_name = getattr(
                QApplication.instance(), "_diagnostics_log_name", "commtool.log")
            create_diagnostic_bundle(
                path, APP_VERSION, log_dir, settings=self.settings,
                log_name=log_name)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            _log.debug("diagnostic bundle export failed", exc_info=True)
            self.toast(self._t("diagnostics_failed", e=exc), error=True)
            return False
        self.toast(self._t("diagnostics_exported", path=path))
        return True

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
        # Switching profiles replaces every Session object.  Do not orphan a
        # window-level worker/timer that is still pinned to one of them.
        if any(self._hard_busy_owned_by(s) for s in self._sessions):
            self.toast_session_busy()
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
        with self._workspace_autosave_paused():
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
            self._reset_sessions_runtime()
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
                self._restore_sessions_settings()
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
        self._begin_workspace_autosave_pause()
        try:
            self._restore_field_defaults_unlocked()
        finally:
            self._end_workspace_autosave_pause()

    def _restore_field_defaults_unlocked(self):
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
        if getattr(self, "_user_closing", False):
            return
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
            self._update_start_timer.start(0)
        else:
            self._update_timer.stop()
            self._update_start_timer.stop()
            checker = self._auto_checker
            if checker is not None:
                checker.abort()
                self._auto_checker = None

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
        # This object is installed on QApplication, not merely on its child
        # widgets. Remove it before deferred deletion can interleave with the
        # next global event dispatch (notably in multi-window/test hosts).
        if getattr(self, "_app_filter_installed", False):
            app = QApplication.instance()
            if app is not None:
                try:
                    app.removeEventFilter(self)
                except RuntimeError:
                    pass
            self._app_filter_installed = False
        self._begin_workspace_autosave_pause()
        self._cancel_reconnect()
        self._ms_stop_all_cycles()       # 先停各会话循环定时器，避免销毁中触发 toast
        for timer_name in ("_theme_apply_timer", "_restore_project_timer",
                           "_update_start_timer", "_update_timer",
                           "_log_sync_timer"):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()
        checker = getattr(self, "_auto_checker", None)
        if checker is not None:
            checker.abort()
            self._auto_checker = None
        if hasattr(self, "_rate_timer"):
            self._rate_timer.stop()       # 同停 1Hz 统计采样：避免 accept 后、窗口析构前残余 tick 去 setText 已销毁的标签
        self._ar_stop_script_worker()      # B5：回收常驻脚本子进程
        self._trg_stop_procs()             # 同收触发器外部程序动作的子进程
        # 正常退出已经收完，注销兵底：否则每开一个窗口就累积一个句柄（测试里
        # 会建很多个），那些句柄还会把已销毁的窗口一直拉着不放。
        atexit.unregister(self._trg_stop_procs)
        self._save_settings()
        self._close_all_sessions(update_active_ui=True)
        self._stop_ble_scan()
        self._stop_rtt_catalog()
        try:
            from transport import ble_io
            ble_io.shutdown_loop()
        except Exception:
            _log.debug("BLE loop shutdown failed", exc_info=True)
        scanner = self.port_scanner
        if scanner:
            scanner.stop()
            # PortScannerThread has no QObject parent. Leaving a stopped
            # scanner referenced by a deleted window accumulates native QThread
            # wrappers in multi-window/test hosts; delete only after stop/wait
            # has positively completed.
            if not scanner.isRunning():
                scanner.deleteLater()
                self.port_scanner = None
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
                     "_snip_dlg", "_send_hist_dlg", "_cpreset_dlg", "_ble_scan_dlg", "_triggers_dlg", "_device_center_dlg", "_structured_dlg", "_rtt_dev_dlg"):
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

_install_session_proxies(CommTool)
