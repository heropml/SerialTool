# -*- coding: utf-8 -*-
"""发送框命令 DSL：一行里带时序/重复，不用开脚本控制台就能做轻量自动化。

语法（转义指令写成 \\!(...)，其余内容原样当数据发）：
    AT\\!(Delay500)AT+VER                  发 AT、等 500ms、再发 AT+VER
    \\!(Repeat3)PING\\!(Delay200)          PING+等200ms 整体重复 3 次
    \\!(Hex)01 03 00 00\\!(Text)hello      切换后续片段按 HEX / 文本解释

指令一览（大小写不敏感，可写 \\!(delay 500) 或 \\!(Delay500)）：
    Delay<ms> / Wait<ms>   等待
    Repeat<n>              其后所有内容整体重复 n 次（n≥1，只允许出现一次）
    Hex / Text             切换后续数据片段的解释方式（默认跟随主界面 HEX 发送开关）

编译产物是一串 (op, arg) 指令，由主窗用 QTimer 逐条执行 —— 纯逻辑、可单测，
不依赖 Qt。发送片段本身仍走主窗 _send_text，沿用换行/校验/显示/录制等既有行为。
"""
import re

OP_SEND = "send"      # arg = (text, hex_mode|None)
OP_DELAY = "delay"    # arg = ms

_TOKEN = re.compile(r"\\!\(\s*([A-Za-z]+)\s*(\d*)\s*\)")
_MARKER = r"\!("
_MAX_REPEAT = 10000
_MAX_DELAY_MS = 24 * 3600 * 1000     # 24h，QTimer int32 内
_MAX_OPS = 20000                     # 展开后指令上限，防 Repeat 把内存撑爆

_ESC = "\x01"                        # \\ 的占位符：先换成它再跑正则，flush 时还原为 \


class DslError(Exception):
    """语法/取值错误，附带可直接展示给用户的说明。"""


def has_dsl(text):
    """文本里是否含 DSL 起始标记 —— 含畸形指令也必须进编译器报错，不能原样发给设备。"""
    return _MARKER in (text or "")


def compile_dsl(text, default_hex=False):
    """把发送框文本编译成 [(op, arg), ...]。非法输入抛 DslError。"""
    if not text:
        return []
    # \\ 是转义：\\!(...) 的 \\ 变成字面量 \、后面的 !(...) 不再是指令。
    # 先把 \\ 换成占位符，正则就不会误匹配转义后的序列；flush 时再还原为 \。
    text = text.replace(r"\\", _ESC)
    ops = []
    hex_mode = None            # None = 跟随主界面开关
    repeat = 1
    repeat_at = None           # Repeat 之后的指令才参与重复
    pos = 0
    seen_repeat = False

    def flush(seg):
        seg = seg.replace(_ESC, "\\")        # \\ 转义 → 一个字面量反斜杠
        seg = seg.strip("\r\n") if hex_mode else seg
        if seg:
            ops.append((OP_SEND, (seg, hex_mode)))

    for m in _TOKEN.finditer(text):
        seg = text[pos:m.start()]
        if _MARKER in seg:
            raise DslError("指令格式错误，请使用 \\!(Delay500) 这类写法")
        flush(seg)
        pos = m.end()
        name = m.group(1).lower()
        num = m.group(2)
        if name in ("delay", "wait"):
            if not num:
                raise DslError("%s 需要毫秒数，如 \\!(Delay500)" % m.group(1))
            ms = int(num)
            if ms > _MAX_DELAY_MS:
                raise DslError("延时过大（上限 %d ms）" % _MAX_DELAY_MS)
            ops.append((OP_DELAY, ms))
        elif name == "repeat":
            if seen_repeat:
                raise DslError("Repeat 只能出现一次")
            if not num:
                raise DslError("Repeat 需要次数，如 \\!(Repeat3)")
            repeat = int(num)
            if repeat < 1:
                raise DslError("Repeat 次数至少为 1")
            if repeat > _MAX_REPEAT:
                raise DslError("Repeat 次数过多（上限 %d）" % _MAX_REPEAT)
            seen_repeat = True
            repeat_at = len(ops)
        elif name == "hex":
            if num:
                raise DslError("Hex 不接受参数")
            hex_mode = True
        elif name == "text":
            if num:
                raise DslError("Text 不接受参数")
            hex_mode = False
        else:
            raise DslError("未知指令 \\!(%s)" % m.group(1))
    tail = text[pos:]
    if _MARKER in tail:
        raise DslError("指令格式错误，请使用 \\!(Delay500) 这类写法")
    flush(tail)

    if repeat_at is not None:
        head, body = ops[:repeat_at], ops[repeat_at:]
        if not body:
            raise DslError("Repeat 之后没有可重复的内容")
        if repeat > 1:
            if len(head) + len(body) * repeat > _MAX_OPS:
                raise DslError("展开后指令过多（上限 %d 条）" % _MAX_OPS)
            ops = head + body * repeat
    if len(ops) > _MAX_OPS:
        raise DslError("指令过多（上限 %d 条）" % _MAX_OPS)
    if not any(op == OP_SEND for op, _a in ops):
        raise DslError("没有可发送的内容")
    return ops


def describe(ops):
    """给用户看的执行摘要：几段发送、总延时。"""
    sends = sum(1 for op, _a in ops if op == OP_SEND)
    delay = sum(a for op, a in ops if op == OP_DELAY)
    return sends, delay
