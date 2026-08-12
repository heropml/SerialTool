# -*- coding: utf-8 -*-
"""QSplitter 列宽持久化：settings 读写 + 多行同步（对话框共用）。"""


def load_split_sizes(settings, key, n_cols, max_size=None):
    """从 settings 读 ``'w1,w2,...'``；列数不符 / 非法则 ``None``（调用方用默认）。"""
    raw = settings.value(key, "")
    try:
        parts = [int(x) for x in str(raw).split(",")]
    except (ValueError, TypeError):
        return None
    if len(parts) != int(n_cols):
        return None
    if not all(p > 0 for p in parts):
        return None
    if max_size is not None and not all(p <= int(max_size) for p in parts):
        return None
    return parts


def save_split_sizes(settings, key, sizes):
    """把列宽列表写成 ``'w1,w2,...'``。"""
    settings.setValue(key, ",".join(str(int(s)) for s in sizes))


def sync_splitter_group(src, peers, *, get_busy, set_busy, on_sizes=None,
                        expected_len=None, guard_runtime=False):
    """任一分隔条拖动 → 同组其余 splitter 对齐，并回调 ``on_sizes(sizes)`` 做持久化。

    ``get_busy`` / ``set_busy`` 防止同步时 ``setSizes`` 再触发 ``splitterMoved`` 递归。
    ``guard_runtime``：对话框已 ``deleteLater`` 后 singleShot 仍可能触发，吞 ``RuntimeError``。
    成功返回 sizes 列表；跳过时返回 ``None``。
    """
    if get_busy():
        return None
    try:
        sizes = src.sizes()
    except RuntimeError:
        if guard_runtime:
            return None
        raise
    if not sizes or sum(sizes) <= 0:
        return None
    if expected_len is not None and len(sizes) != int(expected_len):
        return None
    # 先回调持久化、再 busy：与抽取前各对话框一致。on_sizes 不得再触发
    # splitterMoved（否则会在 busy 置位前重入）；peer setSizes 失败时 settings
    # 可能已写入（guard_runtime 下吞 RuntimeError，同旧行为）。
    if on_sizes is not None:
        on_sizes(sizes)
    set_busy(True)
    try:
        for sp in peers:
            if sp is None or sp is src:
                continue
            try:
                sp.setSizes(sizes)
            except RuntimeError:
                if not guard_runtime:
                    raise
    finally:
        set_busy(False)
    return sizes
