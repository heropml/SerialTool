# -*- coding: utf-8 -*-
"""实时记录的文件名变量展开与按日轮转判定（Qt-free，可单测）。

主窗只负责在写入后问一句「该换文件了吗」，命名与判定规则全在这里。

支持的变量（大小写不敏感）：
    %date  → 20260723        %time  → 143005
    %datetime → 20260723_143005
    %port  → COM3 / 192.168.1.10_8080（连接标识，已清理成合法文件名）
    %n     → 分包序号 001（不带此变量时序号按老规矩追加在扩展名前）
未知的 %x 原样保留——用户文件名里真有个百分号时不至于被吃掉。
"""
import os
import re

# 变量名按长度降序匹配，"%datetime" 必须排在 "%date" 前面，否则前缀会被先吃掉
_VAR_RE = re.compile(r"%(datetime|date|time|port|n)", re.IGNORECASE)

# Windows 文件名非法字符 + 控制字符；连接标识里的 : / \ 都要换掉
_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_token(text, fallback="unknown"):
    """把连接标识（COM3 / 192.168.1.10:8080）清成能进文件名的片段。"""
    cleaned = _ILLEGAL_RE.sub("_", str(text or "")).strip(" .")
    return cleaned or fallback


def expand(template, when, port="", seg=0):
    """展开文件名模板。when=datetime（调用方传，便于测试注入固定时刻）。

    seg 只在模板含 %n 时用得上；不含 %n 时序号由 segment_path 追加到扩展名前，
    保持与旧版「xxx_001.log」一致的观感。
    """
    port_token = sanitize_token(port, "conn")

    def _sub(m):
        key = m.group(1).lower()
        if key == "datetime":
            return when.strftime("%Y%m%d_%H%M%S")
        if key == "date":
            return when.strftime("%Y%m%d")
        if key == "time":
            return when.strftime("%H%M%S")
        if key == "port":
            return port_token
        return "%03d" % seg          # %n
    return _VAR_RE.sub(_sub, template or "")


def segment_path(template, when, port="", seg=0):
    """模板 + 当前时刻/连接/分包序号 → 最终完整路径。

    含 %n：序号由用户决定位置。不含 %n：第 0 包用原名，之后追加 _001（老规矩）。
    """
    path = expand(template, when, port=port, seg=seg)
    if seg > 0 and not re.search(r"%n", template or "", re.IGNORECASE):
        root, ext = os.path.splitext(path)
        path = "%s_%03d%s" % (root, seg, ext)
    return path


def should_roll_date(opened_at, now, template):
    """跨自然日了吗——只有文件名含日期类变量时才需要，否则换日期也是同一个文件名。

    比的是日期而不是「距开始满 24 小时」：挂机记录要的是按天归档，
    下午 3 点开始记录，次日 0 点就该换新文件，而不是次日下午 3 点。
    """
    if not (opened_at and now):
        return False
    if not re.search(r"%(datetime|date|time)", template or "", re.IGNORECASE):
        return False
    return opened_at.date() != now.date()


def parse_size_limit(text):
    """Parse a human size like '2M' / '512K' / '1.5G' into bytes.

    No digits (e.g. 'none' / empty) -> 0 (unlimited). Bare number defaults to MB,
    matching the UI combo convention used by CommTool.
    """
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KkMmGg]?)", text or "")
    if not m:
        return 0
    val = float(m.group(1))
    mult = {"K": 1024, "M": 1024 * 1024, "G": 1024 ** 3}.get(
        m.group(2).upper(), 1024 * 1024)
    return int(val * mult)


def should_roll_size(current_bytes, limit_bytes):
    """True when the open segment has reached/exceeded the size limit.

    limit_bytes <= 0 means unlimited (never roll for size). current_bytes None
    or negative is treated as unknown -> do not roll (caller keeps writing /
    retries later) so a failed tell() cannot cascade into a spurious rotate.
    Non-numeric limits are treated as unlimited (do not raise).
    """
    try:
        limit = int(limit_bytes)
    except (TypeError, ValueError):
        return False
    if limit <= 0:
        return False
    try:
        cur = int(current_bytes)
    except (TypeError, ValueError):
        return False
    if cur < 0:
        return False
    return cur >= limit


def conn_token(proto, cfg, serial_name="Serial", tcp_client_name="TCP Client"):
    """%port expansion value from connection signature tuple.

    serial_name / tcp_client_name must match PROTO_* display strings used by UI.
    """
    if proto == serial_name and cfg and len(cfg) > 1 and cfg[1]:
        return str(cfg[1])
    if proto == tcp_client_name and cfg and len(cfg) > 2:
        return "%s_%s" % (cfg[1], cfg[2])
    if proto == "BLE" and cfg and len(cfg) > 1 and cfg[1]:
        return str(cfg[1])
    if proto:
        return str(proto)
    return ""


def safe_enter_idx(v):
    """Enter-key mapping index: only 0/1/2 accepted, else 0."""
    try:
        n = int(v)
    except (ValueError, TypeError):
        return 0
    return n if n in (0, 1, 2) else 0
