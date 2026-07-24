# -*- coding: utf-8 -*-
"""会话比较：把两个 .ctrec 录制按事件序列对齐，逐条判「相同 / 内容不同 / 只有一边有」。

典型用途：新旧固件各录一次，比出「哪一帧不一样、谁多发了、时序差多少」。

对齐用 LCS（最长公共子序列），不是简单的按下标并排——设备少答一帧时，按下标比会让
**之后每一条**都错位报差异，噪声淹没真正的那一处。LCS 能把多出来的一条识别成
「只有 A 有」，后续继续对齐。

LCS 用 Hirschberg 分治（线性空间）实现：内存 O(min(n,m)) 而非朴素 DP 的 O(n*m)——
3000×3000 的朴素 DP 表是 900 万个 Python int（约 70MB），Hirschberg 只需两行滚动数组。
时间仍是 O(n*m)，且整条比较跑在点「比较」后的 GUI 线程上，所以另设格子数上限 MAX_CELLS：
超过就退化成按下标并排（线性、瞬时），在结果里标明 degraded，绝不悄悄截断数据。

相等的判定：方向相同 且 字节完全相同。时间戳**不参与**是否相等的判定，只在配对成功后
报告偏差（同一条帧早 30ms 到达仍是同一条帧；把时序算进相等性会让所有条目都不相等）。

Qt-free，纯数据进出，便于单测；对话框只负责展示。
"""

# 走完整 LCS 的格子数（n*m）上限。LCS 跑在点「比较」后的 GUI 线程上，实测本机方阵
# 边界（~50 万格 ≈ 707² 条）最坏 ~120ms，是可接受的同步停顿；超过退化成按下标并排
# （线性、瞬时）。用格子数而非条数：一边 5 条 × 另一边 50000 条只有 25 万格、瞬时算完，
# 没必要因为「有一边条数多」就退化。会话比较通常几百条帧，够用且有余量。
MAX_CELLS = 500_000
# 兼容旧调用/测试：仍暴露一个条数意义的 MAX_ALIGN（≈ sqrt(MAX_CELLS)），
# compare(max_align=N) 传进来时按 N*N 格换算成格子上限。
MAX_ALIGN = 707       # int(500_000 ** 0.5)

SAME = "same"          # 方向与字节都一致
DIFF = "diff"          # 配上了，但字节不同
ONLY_A = "only_a"      # 只有 A 有（B 少了这条）
ONLY_B = "only_b"      # 只有 B 有（B 多了这条）


def _key(ev):
    """参与对齐的等价键：方向 + 字节。时间不进键，见模块注释。"""
    return (ev[1], ev[2])


def _lcs_lengths(ka, kb):
    """一行滚动数组求 LCS 长度向量：返回 len(kb)+1 的列表，
    curr[j] = LCS(ka, kb[:j])。这是 Hirschberg 的核心子过程，空间 O(len(kb))。"""
    prev = [0] * (len(kb) + 1)
    for x in ka:
        curr = [0] * (len(kb) + 1)
        for j in range(1, len(kb) + 1):
            if x == kb[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = prev[j] if prev[j] >= curr[j - 1] else curr[j - 1]
        prev = curr
    return prev


def _hirschberg(ka, kb, oa, ob):
    """线性空间 LCS，返回对齐操作 [('=',i,j) | ('-',i,None) | ('+',None,j)]。
    ka/kb 是等价键序列，oa/ob 是它们在原始 a/b 中的绝对下标（分治时要还原真实位置）。"""
    n, m = len(ka), len(kb)
    if n == 0:
        return [("+", None, ob[j]) for j in range(m)]
    if m == 0:
        return [("-", oa[i], None) for i in range(n)]
    if n == 1:
        # 单行：在 kb 里找第一个等于 ka[0] 的位置配成 '='，其余全是 '+'
        hit = kb.index(ka[0]) if ka[0] in kb else -1
        ops = []
        for j in range(m):
            if j == hit:
                ops.append(("=", oa[0], ob[j]))
            else:
                ops.append(("+", None, ob[j]))
        if hit < 0:
            ops.append(("-", oa[0], None))   # ka[0] 无处可配 → 删除
        return ops
    # 分治：在 a 的中线切开，用「前缀 LCS 长度」+「后缀 LCS 长度」找 b 的最佳切点
    mid = n // 2
    l1 = _lcs_lengths(ka[:mid], kb)
    l2 = _lcs_lengths(ka[mid:][::-1], kb[::-1])
    best_j, best = 0, -1
    for j in range(m + 1):
        s = l1[j] + l2[m - j]
        if s > best:
            best, best_j = s, j
    return (_hirschberg(ka[:mid], kb[:best_j], oa[:mid], ob[:best_j])
            + _hirschberg(ka[mid:], kb[best_j:], oa[mid:], ob[best_j:]))


def _lcs_ops(a, b):
    """LCS 对齐编辑脚本：[('=', i, j) | ('-', i, None) | ('+', None, j)]。
    线性空间（Hirschberg），下标为在 a/b 中的绝对位置。

    出口做一次规范化：把每段连续的删/增重排成「先所有删、后所有增」。Hirschberg 分治在
    不同切点会输出 '+' 在 '-' 前的顺序，而下游 _pair_ops 靠「相邻的 - 紧跟 +」识别内容变更；
    不归一的话同一处改动一会儿合并、一会儿散成 only_a+only_b，结果不稳定。删增各自内部
    保持原下标序，不影响 SAME 的位置。"""
    ka = [_key(x) for x in a]
    kb = [_key(x) for x in b]
    ops = _hirschberg(ka, kb, list(range(len(a))), list(range(len(b))))
    out = []
    i = 0
    while i < len(ops):
        if ops[i][0] in ("-", "+"):
            j = i
            while j < len(ops) and ops[j][0] in ("-", "+"):
                j += 1
            block = ops[i:j]
            out.extend(o for o in block if o[0] == "-")
            out.extend(o for o in block if o[0] == "+")
            i = j
        else:
            out.append(ops[i]); i += 1
    return out


def _pair_ops(a, b):
    """把「同一处的删+增」合并成一条 diff：同一位置的帧内容变了，报成「改了」比报成
    「删一条又加一条」更贴近用户心里的模型。方向不同的不合并（RX 变 TX 是两件事）。

    _lcs_ops 出口已把每段连续删增归一成「先全部删、后全部增」。这里对每个这样的块，
    按顺序把删项与增项两两配对：方向相同 → 合并成 diff（'~'）；方向不同或一侧配完 →
    原样保留为 only_a/only_b。逐条配对（而非只看相邻一对）才能处理「连续多帧都改了」，
    否则 N 删 N 增只会合并第一对、其余散成单边缺失。

    配对只查方向不查字节：方向+字节都相同的早被 LCS 配成 '='、不会进这里，所以一对
    方向相同的删增，字节必然不同。"""
    ops = _lcs_ops(a, b)
    out = []
    i = 0
    while i < len(ops):
        if ops[i][0] in ("-", "+"):
            k = i
            while k < len(ops) and ops[k][0] in ("-", "+"):
                k += 1
            dels = [o for o in ops[i:k] if o[0] == "-"]
            adds = [o for o in ops[i:k] if o[0] == "+"]
            di = ai = 0
            while di < len(dels) and ai < len(adds):
                d, ad = dels[di], adds[ai]
                if a[d[1]][1] == b[ad[2]][1]:      # 同方向 → 内容变更
                    out.append(("~", d[1], ad[2]))
                    di += 1; ai += 1
                else:                               # 方向不同：删的先落地，增的等下一轮
                    out.append(d)
                    di += 1
            out.extend(dels[di:])                   # 剩余未配对的删/增原样保留
            out.extend(adds[ai:])
            i = k
        else:
            out.append(ops[i]); i += 1
    return out


def _linear_ops(a, b):
    """超规模时的退化对齐：按下标并排。不做 LCS，仅保证不卡死。"""
    ops = []
    for i in range(max(len(a), len(b))):
        if i < len(a) and i < len(b):
            ops.append(("=" if _key(a[i]) == _key(b[i]) else "~", i, i))
        elif i < len(a):
            ops.append(("-", i, None))
        else:
            ops.append(("+", None, i))
    return ops


def compare(events_a, events_b, max_align=None, max_cells=MAX_CELLS):
    """比较两个事件序列 → {"rows": [...], "stats": {...}, "degraded": bool}。

    每行 dict：
        kind      SAME / DIFF / ONLY_A / ONLY_B
        ia, ib    在各自序列中的下标（缺席侧为 None）
        dir_a/b   'rx' / 'tx'
        bytes_a/b bytes
        t_a/t_b   相对秒
        dt        配对成功时 t_b - t_a（秒，正=B 更晚），否则 None
        first_diff 内容不同时第一个不同字节的偏移，便于定位

    退化判定按「格子数」n*m：LCS 时间是 O(n*m) 且跑在 GUI 线程上，超过 max_cells
    就退化成按下标并排比较（线性、瞬时）并标 degraded。老接口 max_align（条数）仍兼容：
    传了就按 max_align² 换算成格子上限，与旧「各 N 条即退化」语义等价。
    """
    a = list(events_a or [])
    b = list(events_b or [])
    if max_align is not None:
        max_cells = max_align * max_align       # 兼容旧「条数」阈值：N*N 格
    degraded = len(a) * len(b) >= max_cells
    ops = _linear_ops(a, b) if degraded else _pair_ops(a, b)

    rows = []
    stats = {"same": 0, "diff": 0, "only_a": 0, "only_b": 0,
             "total_a": len(a), "total_b": len(b), "max_dt": 0.0}
    for tag, ia, ib in ops:
        ea = a[ia] if ia is not None else None
        eb = b[ib] if ib is not None else None
        if tag == "=":
            kind = SAME
        elif tag == "~":
            kind = DIFF
        elif tag == "-":
            kind = ONLY_A
        else:
            kind = ONLY_B
        # 退化模式下 '=' 可能其实字节相同但方向不同？不会：_key 含方向，'=' 已保证两者都同。
        dt = None
        if ea is not None and eb is not None:
            dt = round(eb[0] - ea[0], 4)
            if abs(dt) > abs(stats["max_dt"]):
                stats["max_dt"] = dt
        first_diff = None
        if kind == DIFF:
            ba, bb = ea[2], eb[2]
            lim = min(len(ba), len(bb))
            first_diff = next((k for k in range(lim) if ba[k] != bb[k]), lim)
        rows.append({
            "kind": kind, "ia": ia, "ib": ib,
            "dir_a": ea[1] if ea else None, "dir_b": eb[1] if eb else None,
            "bytes_a": ea[2] if ea else b"", "bytes_b": eb[2] if eb else b"",
            "t_a": ea[0] if ea else None, "t_b": eb[0] if eb else None,
            "dt": dt, "first_diff": first_diff,
        })
        stats[kind] += 1
    stats["identical"] = (stats["diff"] == 0 and stats["only_a"] == 0
                          and stats["only_b"] == 0)
    return {"rows": rows, "stats": stats, "degraded": degraded}


def rows_to_csv(rows):
    """差异表 → CSV 文本（供导出）。首列做防公式注入处理，同报告导出的既有做法。"""
    def _cell(v):
        s = "" if v is None else str(v)
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    out = ["kind,index_a,index_b,dir,time_a,time_b,dt,first_diff,bytes_a,bytes_b"]
    for r in rows:
        out.append(",".join([
            _cell(r["kind"]),
            "" if r["ia"] is None else str(r["ia"]),
            "" if r["ib"] is None else str(r["ib"]),
            _cell(r["dir_a"] or r["dir_b"] or ""),
            "" if r["t_a"] is None else "%.4f" % r["t_a"],
            "" if r["t_b"] is None else "%.4f" % r["t_b"],
            "" if r["dt"] is None else "%.4f" % r["dt"],
            "" if r["first_diff"] is None else str(r["first_diff"]),
            _cell(r["bytes_a"].hex(" ").upper()),
            _cell(r["bytes_b"].hex(" ").upper()),
        ]))
    return "\n".join(out)
