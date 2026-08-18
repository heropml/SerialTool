# -*- coding: utf-8 -*-
"""ANSI SGR 着色的纯逻辑（Qt-free，可单测）。

把带 ESC 转义的文本拆成「文本段 + 样式」，供数据区按设备本来的配色显示 ——
ESP-IDF / Zephyr / NuttX / U-Boot 这些固件的日志天生带颜色（错误红、警告黄、信息绿），
以前在数据区要么是 `^[[0;32m` 乱码、要么被当普通字符糊成一片。

**只做 SGR**（颜色 / 粗体 / 下划线 / 反显）：完整 VT 仿真（光标定位、滚动区、字符集、
备用屏）是 PuTTY / SecureCRT 那个品类的核心，做全套等于变成残血终端；这里只取
「设备日志按原色显示」这 80% 的收益。非 SGR 的 CSI 与其它转义序列一律**吃掉不显示**，
不再留下乱码。

跨包状态：一次收包可能把 ESC 序列切成两半、颜色也常常跨包延续，故 parse() 同时
返回「未完成的转义残片」和「当前样式」，由调用方带到下一包。
"""

# 16 色基础调色板。深色底 / 浅色底各一套：ANSI 原色在相反底色上常常看不清
# （白字白底、黑字黑底、纯黄在白底几乎不可读），故按主题明暗各自取可读的近似色。
PALETTE_DARK = (
    "#6B6B6B", "#F14C4C", "#23D18B", "#F5F543",   # 黑(提亮成灰否则不可见) 红 绿 黄
    "#3B8EEA", "#D670D6", "#29B8DB", "#E5E5E5",   # 蓝 品红 青 白
    "#808080", "#FF6B6B", "#4EE39A", "#FFFF7A",   # 亮黑(灰) 亮红 亮绿 亮黄
    "#6BB1FF", "#E68FE6", "#5FD7E8", "#FFFFFF",   # 亮蓝 亮品红 亮青 亮白
)
PALETTE_LIGHT = (
    "#1C1C1E", "#C41A16", "#007400", "#8A6D00",   # 黄在白底要压暗才看得清
    "#0B5FCE", "#A626A4", "#007D85", "#6E6E6E",   # 白(压暗成灰否则不可见)
    "#5A5A5A", "#E0453A", "#1A8A1A", "#A67C00",
    "#2A7FE8", "#B944B7", "#0F9BA5", "#3A3A3A",
)

MAX_PENDING = 128    # 未完成转义序列的缓冲上限：异常设备可能一直发参数不给终止字节
# 超长控制串不能继续保存原文（否则缓冲无界），但也不能简单忘掉「仍在控制串里」：
# 下一包的参数会被当正文漏出来。用固定长度哨兵只记丢弃状态，直到真正终止。
_DISCARD_CSI = "\x00ansi:csi"
_DISCARD_OSC = "\x00ansi:osc"
_DISCARD_OSC_ESC = "\x00ansi:osc-esc"   # 上一包最后一个字节是 ESC，下一包 "\" 可组成 ST


class SgrState:
    """一段文本的显示样式。fg / bg 为 None(默认色) | int 0..15(调色板序号) | (r,g,b)。

    调色板序号不在这里解析成具体颜色 —— 留到显示层按当前主题明暗解析，
    这样切换深浅主题时旧文字能跟着重解析，不会出现「深色配色留在浅色底上看不见」。
    """

    __slots__ = ("fg", "bg", "bold", "underline", "reverse")

    def __init__(self, fg=None, bg=None, bold=False, underline=False, reverse=False):
        self.fg = fg
        self.bg = bg
        self.bold = bold
        self.underline = underline
        self.reverse = reverse

    def copy(self):
        return SgrState(self.fg, self.bg, self.bold, self.underline, self.reverse)

    def is_default(self):
        return (self.fg is None and self.bg is None
                and not self.bold and not self.underline and not self.reverse)

    def key(self):
        """可哈希的样式标识：相邻文本样式相同则可合并成一段。"""
        return (self.fg, self.bg, self.bold, self.underline, self.reverse)

    def __eq__(self, other):
        return isinstance(other, SgrState) and self.key() == other.key()

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        return "SgrState(fg=%r, bg=%r, bold=%r, underline=%r, reverse=%r)" % (
            self.fg, self.bg, self.bold, self.underline, self.reverse)


DEFAULT = SgrState()


def _cube256(n):
    """xterm 256 色 → (r,g,b)。16-231 是 6×6×6 色立方，232-255 是 24 级灰阶。"""
    if n < 16:
        return n                       # 前 16 个就是基础调色板，交给主题解析
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n % 36) // 6, n % 6
        return tuple(0 if v == 0 else 55 + 40 * v for v in (r, g, b))
    v = 8 + 10 * (n - 232)
    return (v, v, v)


def _take_ext_color(params, i):
    """解析 38/48 的扩展色参数，返回 (颜色, 消费到的下标)。
    38;5;N = 256 色；38;2;R;G;B = 真彩。参数不全 → 颜色 None（忽略这段）。"""
    if i + 1 < len(params):
        kind = params[i + 1]
        if kind == 5 and i + 2 < len(params):
            return _cube256(max(0, min(255, params[i + 2]))), i + 2
        if kind == 2 and i + 4 < len(params):
            return tuple(max(0, min(255, params[i + j])) for j in (2, 3, 4)), i + 4
    return None, len(params)           # 参数残缺：整段丢弃，不猜


def apply_params(state, params_str):
    """把一条 SGR 参数串（ESC[ 与 m 之间的部分）应用到 state，返回新 state。

    空参数串等价于 `0`（ESC[m = 复位），与终端一致。无法识别的参数忽略而不是报错 ——
    设备可能发任意扩展码，忽略比中断整段着色好。
    """
    parts = params_str.split(";") if params_str else [""]
    params = []
    for p in parts:
        p = p.strip()
        if p == "":
            params.append(0)           # 空段按 0 处理（ESC[;m、ESC[m）
        elif p.isdigit():
            params.append(int(p[:6]))  # 截断超长数字，防病态输入
        else:
            return state.copy()        # 含非数字（如 ESC[?25m 的私有序列）→ 整条忽略
    st = state.copy()
    i = 0
    while i < len(params):
        p = params[i]
        if p == 0:
            st = SgrState()
        elif p == 1:
            st.bold = True
        elif p == 22:
            st.bold = False
        elif p == 4:
            st.underline = True
        elif p == 24:
            st.underline = False
        elif p == 7:
            st.reverse = True
        elif p == 27:
            st.reverse = False
        elif 30 <= p <= 37:
            st.fg = p - 30
        elif p == 38:
            col, i = _take_ext_color(params, i)
            if col is not None:
                st.fg = col
        elif p == 39:
            st.fg = None
        elif 40 <= p <= 47:
            st.bg = p - 40
        elif p == 48:
            col, i = _take_ext_color(params, i)
            if col is not None:
                st.bg = col
        elif p == 49:
            st.bg = None
        elif 90 <= p <= 97:
            st.fg = p - 90 + 8
        elif 100 <= p <= 107:
            st.bg = p - 100 + 8
        # 其余（斜体 3、闪烁 5、隐藏 8…）忽略：数据区不做这些效果
        i += 1
    return st


def parse(text, state=None, pending=""):
    """把 text 拆成 [(文本段, 样式), ...]，并返回延续到下一包的 (样式, 未完成残片)。

    Args:
        text: 本次要显示的文本（已解码）。
        state: 上一包结束时的样式（跨包延续），None = 默认样式。
        pending: 上一包末尾未收完的转义序列残片。

    Returns:
        (runs, state, pending)。runs 里相邻同样式已合并；控制字符（\\r \\n \\t）
        原样保留在文本里 —— 分行 / 分包逻辑还要靠它们，这里只负责剥转义序列。
    """
    st = (state or DEFAULT).copy()
    incoming = text or ""

    # 上一包的控制串已超过 MAX_PENDING：原参数已丢弃，只扫描终止符。这样内存有界，
    # 同时不会把后续包里的标题/参数内容误显示或拿去做触发匹配。
    if pending == _DISCARD_CSI:
        end = next((i for i, ch in enumerate(incoming) if "\x40" <= ch <= "\x7e"), None)
        if end is None:
            return [], st, _DISCARD_CSI
        incoming = incoming[end + 1:]
        pending = ""
    elif pending in (_DISCARD_OSC, _DISCARD_OSC_ESC):
        prev_esc = pending == _DISCARD_OSC_ESC
        end = None
        for i, ch in enumerate(incoming):
            if ch == "\x07" or (prev_esc and ch == "\\"):
                end = i
                break
            prev_esc = ch == "\x1b"
        if end is None:
            return [], st, _DISCARD_OSC_ESC if prev_esc else _DISCARD_OSC
        incoming = incoming[end + 1:]
        pending = ""

    buf = pending + incoming
    runs = []
    cur = []                                   # 当前样式下累积的字符
    i, n = 0, len(buf)

    def flush():
        if cur:
            if runs and runs[-1][1] == st:     # 与上一段同样式 → 合并，减少插入次数
                runs[-1] = (runs[-1][0] + "".join(cur), runs[-1][1])
            else:
                runs.append(("".join(cur), st.copy()))
            del cur[:]

    while i < n:
        ch = buf[i]
        if ch != "\x1b":
            cur.append(ch)
            i += 1
            continue
        # --- 遇到 ESC：先把已累积的文本按旧样式定下来 ---
        flush()
        rest = buf[i + 1:]
        if not rest:                           # ESC 在末尾，序列还没收完
            return runs, st, "\x1b"
        kind = rest[0]
        if kind == "[":                        # CSI：ESC[ <参数> <终止字节 0x40-0x7E>
            j = i + 2
            while j < n and not ("\x40" <= buf[j] <= "\x7e"):
                j += 1
            if j >= n:                         # 终止字节还没到
                if n - i > MAX_PENDING:        # 病态输入：丢弃这段，别无限缓冲
                    return runs, st, _DISCARD_CSI
                return runs, st, buf[i:]
            if buf[j] == "m":                  # 只有 SGR 影响显示，其余 CSI 吃掉
                st = apply_params(st, buf[i + 2:j])
            i = j + 1
        elif kind == "]":                      # OSC：ESC] ... BEL 或 ESC\ 终止（设置标题等）
            j = i + 2
            while j < n and buf[j] != "\x07" and not (buf[j] == "\x1b" and j + 1 < n
                                                     and buf[j + 1] == "\\"):
                j += 1
            if j >= n:
                if n - i > MAX_PENDING:
                    return runs, st, (_DISCARD_OSC_ESC if buf.endswith("\x1b")
                                      else _DISCARD_OSC)
                return runs, st, buf[i:]
            i = j + (2 if buf[j] == "\x1b" else 1)
        else:
            # 其它转义序列：ESC + 若干中间字节(0x20-0x2F) + 一个终止字节(0x30-0x7E)。
            # 如 ESC(B(选字符集，3 字节)、ESC=(2 字节)、ESC7/ESC8 —— 按长度精确吃掉，
            # 否则会把序列末字节当成正文吐出来（ESC(B 少吃一字节就会多显示一个 B）。
            j = i + 1
            while j < n and "\x20" <= buf[j] <= "\x2f":
                j += 1
            if j >= n:                         # 中间字节收完但终止字节还没到
                if n - i > MAX_PENDING:
                    return runs, st, ""
                return runs, st, buf[i:]
            i = j + 1
    flush()
    return runs, st, ""


def resolve(color, dark=True):
    """样式里的颜色 → "#RRGGBB"。None → None（用数据区默认色）。

    调色板序号按主题明暗取对应那套；(r,g,b) 是设备指定的精确色，不随主题变。
    """
    if color is None:
        return None
    if isinstance(color, tuple):
        return "#%02X%02X%02X" % color
    pal = PALETTE_DARK if dark else PALETTE_LIGHT
    return pal[max(0, min(15, int(color)))]


def spec_of(color):
    """颜色 → 可存进 QTextCharFormat 的字符串标识（主题切换时据此重解析）。
    序号存 "i<N>"（跟主题走），精确色直接存 "#RRGGBB"（不跟主题变）。"""
    if color is None:
        return ""
    if isinstance(color, tuple):
        return "#%02X%02X%02X" % color
    return "i%d" % int(color)


SPEC_THEME_FG = "!fg"    # 反显用：取当前主题的正文色
SPEC_THEME_BG = "!bg"    # 反显用：取当前主题的底色


def color_of_spec(spec, dark=True, theme_fg=None, theme_bg=None):
    """spec_of 的逆操作：存进格式里的标识 → 当前主题下的 "#RRGGBB"。

    反显(SGR 7)把前后景对调，缺省那一侧要用「主题的正文色 / 底色」。这里存的是记号
    而不是当时算好的具体颜色 —— 存死了切主题就不会变，浅底上会留着为深底选的颜色。
    """
    if not spec:
        return None
    spec = str(spec)
    if spec == SPEC_THEME_FG:
        return theme_fg
    if spec == SPEC_THEME_BG:
        return theme_bg
    if spec.startswith("i"):
        try:
            return resolve(int(spec[1:]), dark)
        except ValueError:
            return None
    return spec if spec.startswith("#") else None


def strip(text):
    """剥掉所有转义序列，只留纯文本（日志落盘、关键字匹配用）。"""
    runs, _, _ = parse(text)
    return "".join(t for t, _ in runs)
