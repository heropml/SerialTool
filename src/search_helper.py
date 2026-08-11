# -*- coding: utf-8 -*-
"""数据区搜索匹配核心（纯逻辑，无 Qt 依赖）。

三种匹配模式：
- plain：纯文本子串（可选大小写敏感）
- regex：正则（复用 triggers.compile_regex 拒掉灾难性回溯结构）
- hex：把搜索词按十六进制字节解析，在渲染文本里按「每字节 + 可选空白分隔」匹配
  （适配 HEX 视图的 ``AA BB CC`` 排版，也兼容无分隔写法）

返回 ``[(start, end), ...]`` 字符区间列表（左闭右开），调用方据此建 QTextCursor。

hexdump 视图：渲染是三列格式（``%08X  <hex列> |ASCII|``），只有 hex 列才是真正的字节，
偏移列与 ASCII 列会误匹配。hex 模式下传 ``hexdump=True`` 则逐行只搜 hex 列。
"""

import re


def parse_hex_term(term):
    """``"01 03" / "0103" / "0x01,0x03"`` → bytes 或 None（非法 hex）。

    清洗规则与 ``triggers.parse_hex_pattern`` 对齐：去掉每段 ``0x`` 前缀及空白/逗号。
    """
    t = re.sub(r"(?i)0x|[\s,]+", "", str(term or ""))
    if not t or len(t) % 2 != 0:
        return None
    try:
        return bytes.fromhex(t)
    except ValueError:
        return None


def _hex_regex(bytes_):
    """bytes → 匹配其 HEX 渲染（字节间允许空白）的正则。如 b"\\x01\\x03" → ``01\\s*03``。"""
    return "\\s*".join("%02X" % b for b in bytes_)


def to_utf16_spans(text, spans):
    """把 Python 字符串码点区间转换为 QTextDocument 使用的 UTF-16 区间。

    BMP 字符在两种索引中一致；仅在文本含非 BMP 字符时建立映射，避免普通串口日志
    搜索引入额外开销。
    """
    spans = list(spans or ())
    if not spans or not any(ord(ch) > 0xFFFF for ch in (text or "")):
        return spans
    offsets = [0] * (len(text) + 1)
    units = 0
    for i, ch in enumerate(text):
        offsets[i] = units
        units += 2 if ord(ch) > 0xFFFF else 1
    offsets[-1] = units
    return [(offsets[max(0, min(start, len(text)))],
             offsets[max(0, min(end, len(text)))])
            for start, end in spans]


# hexdump 行 = 8 位 hex 偏移 + 两空格 + hex 列；ASCII 列以 " |" 分隔。
# 时间戳/箭头行不以 8 位 hex + 双空格开头，天然被此模式排除。
_HEXDUMP_LINE = re.compile(r"^[0-9A-Fa-f]{8} {2}")


def _iter_hex_spans_in_hexdump(text, pat, flags, start=0):
    """在 hexdump 转储文本里只搜 hex 列（跳过每行开头的偏移列与结尾的 |ASCII| 列），
    产出全文字符区间。逐行处理：字节序列跨 hexdump 每行边界（如 per=16 换行处）不匹配，
    属可接受的极罕见取舍。"""
    try:
        start = max(0, int(start or 0))
    except (TypeError, ValueError):
        start = 0
    rx = re.compile(pat, flags)
    # 惰性翻页从包含 start 的行开始，避免每翻一页都重新遍历此前所有行。
    off = text.rfind("\n", 0, min(start, len(text))) + 1
    for line in text[off:].splitlines(keepends=True):
        if _HEXDUMP_LINE.match(line):
            ascii_idx = line.find(" |", 10)
            if ascii_idx > 10:
                for m in rx.finditer(line[10:ascii_idx]):   # 只搜 hex 列
                    a = off + 10 + m.start()
                    if a < start:
                        continue
                    yield a, off + 10 + m.end()
        # 保留原始行尾，CRLF 的两个码点也必须计入全文偏移。
        off += len(line)


def _iter_spans(text, term, mode="plain", case_sensitive=False,
                hexdump=False, start=0):
    """Yield matching codepoint spans without materializing the full result."""
    if not term:
        return
    try:
        start = max(0, int(start or 0))
    except (TypeError, ValueError):
        start = 0
    text = text or ""
    if mode not in {"plain", "regex", "hex"}:
        return
    if mode == "regex":
        import triggers
        flags = 0 if case_sensitive else re.IGNORECASE
        rx = triggers.compile_regex(term, flags)
        if rx is None:
            return
        for m in rx.finditer(text, start):
            if m.end() > m.start():
                yield m.start(), m.end()
        return
    if mode == "hex":
        bytes_ = parse_hex_term(term)
        if not bytes_:
            return
        pat = _hex_regex(bytes_)
        flags = 0 if case_sensitive else re.IGNORECASE
        if hexdump:
            yield from _iter_hex_spans_in_hexdump(text, pat, flags, start=start)
            return
        rx = re.compile(pat, flags)
        for m in rx.finditer(text, start):
            yield m.start(), m.end()
        return
    if not case_sensitive:
        # lower()/casefold() can change string length (for example "İ" -> "i̇"),
        # making the returned offsets invalid for QTextCursor. Regex spans always
        # refer to the original text while preserving non-overlapping matching.
        rx = re.compile(re.escape(term), re.IGNORECASE)
        for m in rx.finditer(text, start):
            yield m.start(), m.end()
        return
    pos = start
    while True:
        i = text.find(term, pos)
        if i < 0:
            return
        yield i, i + len(term)
        pos = i + len(term)


def find_spans(text, term, mode="plain", case_sensitive=False, hexdump=False,
               limit=None, start=0):
    """在 text 里找 term 的所有匹配，返回 [(start, end), ...]。

    mode ∈ ``plain / regex / hex``。空 term 或非法模式返回 []。
    区间按起始位置升序、互不重叠。
    ``start``：从该码点偏移起继续扫描（惰性分页用）。
    hexdump=True 仅对 hex 模式生效：逐行跳过偏移列/ASCII 列，只搜 hex 字节列。"""
    if not term:
        return []
    if limit is not None:
        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 0
        if limit == 0:
            return []
    spans = []
    for span in _iter_spans(
            text, term, mode, case_sensitive, hexdump, start=start):
        spans.append(span)
        if limit is not None and len(spans) >= limit:
            break
    return spans


def find_last_page(text, term, mode="plain", case_sensitive=False,
                   hexdump=False, page_size=2000):
    """Return the final bounded match page and every page's scan start.

    The document is scanned once. Only the current page plus one integer per
    earlier page is retained, so global ▲ wrap cannot become repeated full-text
    scans on dense streams.
    """
    try:
        page_size = max(0, int(page_size))
    except (TypeError, ValueError):
        page_size = 0
    if page_size == 0 or not term:
        return [], [0]
    page = []
    page_starts = [0]
    count = 0
    for span in _iter_spans(text, term, mode, case_sensitive, hexdump, start=0):
        if count and count % page_size == 0:
            page_starts.append(span[0])
            page = []
        page.append(span)
        count += 1
    return page, page_starts
