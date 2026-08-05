# -*- coding: utf-8 -*-
"""触发告警的纯逻辑（Qt-free，可单测）。

一条规则 = 「匹配什么」+「命中后干什么」。用途是**无人值守盯梢**：设备半夜复位、
偶发 ERROR、看门狗喂狗超时……长跑时人不可能一直盯着数据区，命中就响铃 / 弹托盘通知 /
在数据区打标，事后还能看每条规则命中了多少次、最后一次在什么时候。

与相邻功能的分工（别做重了）：
- **关键字高亮** 是「看得见」——把命中的行涂色，人得在场；这里是「叫得应」——人不在也知道。
- **自动应答** 是「答」——命中后回一帧，是协议仿真；这里只「报」不「答」，
  故意不做自动发送：两个引擎同时往线路上发会打架（收发任务互斥表也不允许）。

匹配用的都是现成语义（包含 / 相等 / 前缀 / 正则，文本或 HEX），与自动应答一致，
用户不用再学一套。冷却窗口防止刷屏：设备狂刷 ERROR 时不会响铃几千次。
"""
import re
import time

try:  # Python 3.11+；旧版回退 sre_parse（只读语法树，不执行表达式）
    import re._parser as _re_parser
except ImportError:  # pragma: no cover - 由运行 Python 版本决定
    import sre_parse as _re_parser

MAX_RULES = 200          # 规则条数上限：防误导入巨表拖慢每包匹配
MAX_PATTERN = 2000       # 单条匹配内容长度上限
MAX_NAME = 100
DEFAULT_COOLDOWN_MS = 3000   # 默认冷却 3s：告警是给人看的，不是给机器计数的
MAX_WEBHOOK_URL = 2000
MAX_RUN_CMD = 2000
REGEX_LOOKBACK = 256         # 正则图样长度不可知，跨块回看固定窗口
MAX_LOOKBACK = 8192          # 回看上限：再长也没意义，且不该让缓冲无界增长

MODE_CONTAINS, MODE_EQUALS, MODE_PREFIX, MODE_REGEX = 0, 1, 2, 3
SCOPE_RX, SCOPE_TX, SCOPE_BOTH = "rx", "tx", "both"
_SCOPES = (SCOPE_RX, SCOPE_TX, SCOPE_BOTH)


def _to_int(v, default=0):
    try:
        return int(str(v).strip(), 10)
    except (TypeError, ValueError):
        return default


def _as_bool(v, default=False):
    """'false'/'0'/'no'/'off'/'' 都算 False —— 配置往返可能把布尔存成字符串。"""
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0", "no", "off")
    return bool(v)


def normalize(rule):
    """任意来源的一条记录 → 合法规则 dict，字段缺失/类型不对时给安全默认。"""
    if not isinstance(rule, dict):
        rule = {}
    mode = _to_int(rule.get("mode", MODE_CONTAINS))
    if mode not in (MODE_CONTAINS, MODE_EQUALS, MODE_PREFIX, MODE_REGEX):
        mode = MODE_CONTAINS
    scope = str(rule.get("scope", SCOPE_RX) or SCOPE_RX).strip().lower()
    if scope not in _SCOPES:
        scope = SCOPE_RX
    hexmode = _as_bool(rule.get("hex", False))
    if hexmode and mode == MODE_REGEX:
        mode = MODE_CONTAINS      # 正则是文本语义，HEX 模式下无意义 → 退回包含
    cooldown = _to_int(rule.get("cooldown", DEFAULT_COOLDOWN_MS), DEFAULT_COOLDOWN_MS)
    return {
        "name": str(rule.get("name", "") or "")[:MAX_NAME],
        "pattern": str(rule.get("pattern", "") or "")[:MAX_PATTERN],
        "hex": hexmode,
        "mode": mode,
        "scope": scope,
        "on": _as_bool(rule.get("on", True), True),
        # 动作：响铃 / 托盘通知 / 数据区打标。三者可任意组合；全不选就只计数（安静统计）
        "beep": _as_bool(rule.get("beep", True), True),
        "notify": _as_bool(rule.get("notify", True), True),
        "mark": _as_bool(rule.get("mark", False)),
        "webhook": _as_bool(rule.get("webhook", False)),
        "webhook_url": str(rule.get("webhook_url", "") or "")[:MAX_WEBHOOK_URL],
        "run_cmd_on": _as_bool(rule.get("run_cmd_on", False)),
        "run_cmd": str(rule.get("run_cmd", "") or "")[:MAX_RUN_CMD],
        "min_hits": max(1, min(1000000, _to_int(rule.get("min_hits", 1), 1))),
        "every_n": max(1, min(1000000, _to_int(rule.get("every_n", 1), 1))),
        "cooldown": max(0, min(3600000, cooldown)),
    }


def sanitize_list(items):
    """任意列表 → 合法规则列表（逐条 normalize、丢非 dict、整体截到上限）。"""
    if not isinstance(items, list):
        return []
    out = [normalize(x) for x in items if isinstance(x, dict)]
    return out[:MAX_RULES]


def parse_hex_pattern(text):
    """HEX 匹配串 → bytes；允许空格/逗号/0x 前缀分隔。非法 → None（规则整条不生效，
    而不是当成空串匹配一切）。"""
    s = re.sub(r"(?i)0x|[\s,]+", "", str(text or ""))
    if not s or len(s) % 2:
        return None
    try:
        return bytes.fromhex(s)
    except ValueError:
        return None


# 歧义结构被重复放大到多少倍算危险。代价随上界翻倍增长，实测
# `(\\w|\\w\\w){k,k+5}$` 打 50 字符：上界 10 约 0.003s、15 约 0.07s、
# 20 约 1.6s、23 约 11s。
_AMBIGUOUS_BOUND = 12


def compile_regex(pattern):
    """正则 → 已编译对象；非法或明显会灾难性回溯的表达式返回 None。

    触发匹配运行在 GUI 收包线程，`(a+)+$` 这类嵌套不定重复可能指数级回溯、卡死窗口。
    读取语法树拒绝典型危险结构；普通分组、分支和小范围有限重复照常可用。
    """
    try:
        compiled = re.compile(pattern)
        tree = _re_parser.parse(pattern, 0)
    except (re.error, RuntimeError, OverflowError):
        return None

    repeat_ops = {_re_parser.MAX_REPEAT, _re_parser.MIN_REPEAT}
    possessive = getattr(_re_parser, "POSSESSIVE_REPEAT", None)
    if possessive is not None:
        repeat_ops.add(possessive)

    def unsafe(seq, repeated=False, bound=1):
        """bound = 外层各层重复上界的乘积，即内部歧义被放大了多少倍。"""
        for op, arg in seq:
            if op in repeat_ops:
                lo, hi, child = arg
                variable = lo != hi
                if repeated and variable:
                    return True
                inner = (float("inf") if hi == _re_parser.MAXREPEAT else bound * hi)
                # 无界/大范围外层重复才会放大内部歧义；{2,4} 这类常用结构不误伤。
                # 但有界重复也能指数级：(\w|\w\w){10,15} 的 hi-lo 只有 5、hi 也不过 100，
                # 却能在几十字符上跑到秒级，所以累计上界过阀也算放大。
                amplifies = (hi == _re_parser.MAXREPEAT or hi > 100 or hi - lo > 10
                             or inner >= _AMBIGUOUS_BOUND)
                if unsafe(child, repeated or amplifies, inner):
                    return True
            elif op == _re_parser.SUBPATTERN:
                if unsafe(arg[-1], repeated, bound):
                    return True
            elif op == _re_parser.BRANCH:
                alternatives = arg[1]
                # 空选项 = 同一个字符有多条路可走。CPython 会把公共前缀提出来，
                # 所以 (a|ab) 这类歧义写法正是落到这里被拦的。
                if repeated and any(not alt for alt in alternatives):
                    return True
                if any(unsafe(alt, repeated, bound) for alt in alternatives):
                    return True
            elif op in (_re_parser.ASSERT, _re_parser.ASSERT_NOT):
                if unsafe(arg[1], repeated, bound):
                    return True
            elif op == _re_parser.GROUPREF and repeated:
                return True
        return False

    return None if unsafe(tree) else compiled


def needle_len(rule):
    """这条规则要跨块回看多少字节/字符才不会漏 —— 图样长度 - 1 就够（再长的重叠没意义）。
    正则长度不可知，给一个固定窗口。"""
    pat = rule.get("pattern") or ""
    if rule.get("hex"):
        n = parse_hex_pattern(pat)
        return max(0, len(n) - 1) if n else 0
    if rule.get("mode") == MODE_REGEX:
        return REGEX_LOOKBACK
    return max(0, len(pat) - 1)


def match_stream(rule, data, text, new_data_at=0, new_text_at=0, regex_cache=None):
    """流式匹配：data/text 是「上一块的尾巴 + 本块」，new_*_at 是本块数据的起点。

    串口是字节流，一个关键字常被底层读操作劈成两半（"ERR" | "OR: boom"）—— 只看单块必漏。
    但拼上尾巴后又不能整段重算，否则上一块已经命中过的内容会被反复计数：故只认
    **结束位置落在本块之内** 的匹配，既补上跨块的，也不重复老的。

    「相等 / 前缀」是「这一块(行)是不是 X」的语义，跨块拼接反而会失真 → 只看本块。
    """
    pat = rule.get("pattern") or ""
    if not pat:
        return False
    mode = rule.get("mode", MODE_CONTAINS)
    if mode in (MODE_EQUALS, MODE_PREFIX):
        return match(rule, data[new_data_at:], text[new_text_at:], regex_cache)
    if rule.get("hex"):
        needle = parse_hex_pattern(pat)
        if not needle:
            return False
        i = data.find(needle)
        while i != -1:
            if i + len(needle) > new_data_at:      # 命中结束于本块 → 是新的
                return True
            i = data.find(needle, i + 1)
        return False
    if mode == MODE_REGEX:
        rx = regex_cache.get(pat) if regex_cache is not None else None
        if rx is None:
            rx = compile_regex(pat)
            if regex_cache is not None:
                regex_cache[pat] = rx or False
        if not rx:
            return False
        # 先按原有「本块」语义匹配：^ / \A 应锚定本次收到的数据开头，不能因为前置了
        # 回看尾巴而从第二块起永久失效。随后再查拼接流，只补跨边界的匹配。
        if rx.search(text[new_text_at:]):
            return True
        return any(m.end() > new_text_at for m in rx.finditer(text))
    i = text.find(pat)
    while i != -1:
        if i + len(pat) > new_text_at:
            return True
        i = text.find(pat, i + 1)
    return False


def match(rule, data, text, regex_cache=None):
    """规则是否命中这一包。data=原始字节，text=已解码文本（文本模式用）。

    regex_cache: 可选 dict，避免每包重编译正则（引擎内部用）。
    """
    pat = rule.get("pattern") or ""
    if not pat:
        return False                     # 空模式不匹配任何东西（否则每包都告警）
    mode = rule.get("mode", MODE_CONTAINS)
    if rule.get("hex"):
        needle = parse_hex_pattern(pat)
        if not needle:
            return False
        if mode == MODE_EQUALS:
            return data == needle
        if mode == MODE_PREFIX:
            return data.startswith(needle)
        return needle in data
    if mode == MODE_REGEX:
        rx = regex_cache.get(pat) if regex_cache is not None else None
        if rx is None:
            rx = compile_regex(pat)
            if regex_cache is not None:
                regex_cache[pat] = rx or False
        if not rx:
            return False
        return bool(rx.search(text))
    # 收到的这一块首尾的空白/换行属于「分帧」而不是内容（日志行常常是 "  ERROR: x\r\n"），
    # 故「相等」「前缀」都先剥掉再比 —— 否则用户写 ERROR 却匹配不上缩进行或带 \r\n 的行。
    # 「包含」保持字面：剥了反而会让「想匹配带空格的模式」失效，而包含本身不受首尾空白影响。
    if mode == MODE_EQUALS:
        return text.strip() == pat
    if mode == MODE_PREFIX:
        return text.strip().startswith(pat)
    return pat in text


def scope_ok(rule, direction):
    """规则的收发范围是否覆盖这个方向。direction: 'rx' | 'tx'。"""
    scope = rule.get("scope", SCOPE_RX)
    return scope == SCOPE_BOTH or scope == direction


class TriggerEngine:
    """规则集 + 命中判定 + 冷却 + 计数。不碰 Qt，动作由调用方按返回结果执行。

    命中统计（hits / last_ts）是运行态，不持久化 —— 关掉软件重开就该从零数起。
    """

    def __init__(self, rules=None):
        self._rules = []
        self._regex_cache = {}
        self.stats = {}          # id(规则序号) → {"hits": n, "last": monotonic, "last_wall": 墙钟串}
        self.set_rules(rules or [])

    # ---------------- 规则 ----------------
    def set_rules(self, rules):
        """换一套规则。按「序号」记的统计会重置 —— 编辑过的规则再沿用旧计数会误导。"""
        self._rules = sanitize_list(rules)
        self._regex_cache = {}
        self.stats = {}
        self._cool_until = {}
        # 回看长度只随规则集变，缓存住 —— lookback() 在每包热路径上被调
        enabled = self.enabled_rules()
        self._lookback = min(MAX_LOOKBACK,
                             max([needle_len(r) for r in enabled], default=0))

    def rules(self):
        return self._rules

    def enabled_rules(self):
        return [r for r in self._rules if r.get("on", True) and (r.get("pattern") or "")]

    def bad_patterns(self):
        """返回配置有问题的规则序号与原因，供对话框标红提示（正则写错 / HEX 串非法）。"""
        bad = []
        for i, r in enumerate(self._rules):
            pat = r.get("pattern") or ""
            if not pat:
                continue
            if r.get("hex"):
                if parse_hex_pattern(pat) is None:
                    bad.append((i, "hex"))
            elif r.get("mode") == MODE_REGEX and compile_regex(pat) is None:
                bad.append((i, "regex"))
        return bad

    # ---------------- 判定 ----------------
    def lookback(self):
        """跨块回看需要保留多少字节/字符（取所有启用规则里最长的那个，带上限）。
        set_rules 时算好缓存——这是每包热路径，不该每次重扫全部规则。"""
        return self._lookback

    def feed(self, data, direction="rx", text="", now=None, wall=None,
             new_data_at=0, new_text_at=0):
        """喂一包数据，返回本次触发的 [(序号, 规则), ...]（已过冷却窗口）。

        冷却只压制「动作」，命中计数**和最后命中时间**照常更新 —— 否则「这条到底命中了
        多少次、最近一次什么时候」都会失真（冷却期的命中同样是命中）。

        wall: 墙钟时间串，缺省取当前时刻；显式传入便于测试。
        """
        if now is None:
            now = time.monotonic()
        fired = []
        for i, rule in enumerate(self._rules):
            if not rule.get("on", True):
                continue
            if not scope_ok(rule, direction):
                continue
            if not match_stream(rule, data, text, new_data_at, new_text_at,
                                self._regex_cache):
                continue
            if wall is None:
                wall = time.strftime("%H:%M:%S")   # 懒取：绝大多数包无命中，别每包都格式化墙钟
            st = self.stats.setdefault(i, {"hits": 0, "last": 0.0, "last_wall": ""})
            st["hits"] += 1
            st["last"] = now
            st["last_wall"] = wall
            hits = st["hits"]
            min_hits = int(rule.get("min_hits", 1) or 1)
            every_n = int(rule.get("every_n", 1) or 1)
            if hits < min_hits:
                continue                     # count only until threshold
            if every_n > 1 and (hits % every_n) != 0:
                continue                     # fire every Nth hit
            cd = rule.get("cooldown", 0)
            if cd > 0 and now < self._cool_until.get(i, 0.0):
                continue                     # 冷却中：只计数、不再重复告警（防刷屏）
            self._cool_until[i] = now + cd / 1000.0
            fired.append((i, rule))
        return fired

    def hits(self, index):
        return self.stats.get(index, {}).get("hits", 0)

    def total_hits(self):
        return sum(s.get("hits", 0) for s in self.stats.values())

    def reset_stats(self):
        self.stats = {}
        self._cool_until = {}

    def needs_text(self):
        """是否有启用的文本模式规则 —— 没有就不必为每包解码，省掉收包路径的无谓开销。"""
        return any(not r.get("hex") for r in self.enabled_rules())

    def active(self):
        return bool(self.enabled_rules())
