# -*- coding: utf-8 -*-
"""发送模板库的纯数据逻辑（Qt-free，可单测）。

一条模板 = {name, text, hex}：名称、发送内容、是否按 HEX 发送。用户随手存下常用命令
（复位帧 / AT 查版本 / Modbus 读某寄存器…），之后在库里双击即填入发送框或直接发送。

与「多条发送」的分工：多条发送是一组命令按序循环发（自动化节奏），模板库是单条常用
命令随手取用（手动点发）。故这里不带延时 / 校验 / 循环，只保留发一条所需的最小字段。

对话框只管展示 / 编辑，增删改、搜索过滤、导入导出的规则全在这里，便于单元测试。
"""
import json

MAX_SNIPPETS = 500        # 库容量上限：防手滑导入巨表把配置撑爆 / 列表卡顿
MAX_NAME = 200            # 单条名称字符上限
MAX_TEXT = 20000         # 单条内容字符上限（HEX 长帧也够）


def _bool(v):
    """宽进解析布尔值：配置/手写 JSON 里的 "false" 不能被 bool(str) 误判为 True。"""
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0", "no", "off")
    return bool(v)


def normalize(snip):
    """把任意来源的一条记录规整成 {name:str, text:str, hex:bool}，字段缺失 / 类型不对时给安全默认。
    名称 / 内容按上限截断——宁可截短也不让超长串进配置。返回规整后的新 dict。"""
    if not isinstance(snip, dict):
        return {"name": "", "text": "", "hex": False}
    name = snip.get("name", "")
    text = snip.get("text", "")
    name = str(name) if name is not None else ""
    text = str(text) if text is not None else ""
    return {
        "name": name[:MAX_NAME],
        "text": text[:MAX_TEXT],
        "hex": _bool(snip.get("hex", False)),
    }


def sanitize_list(items):
    """把任意列表规整成合法模板列表：逐条 normalize，丢弃非 dict，整体截到 MAX_SNIPPETS。
    非列表输入 → 空列表。用于加载配置 / 导入文件后的统一入口。"""
    if not isinstance(items, list):
        return []
    out = [normalize(x) for x in items if isinstance(x, dict)]
    return out[:MAX_SNIPPETS]


def default_snippets():
    """首次使用给几条示例，只为说明「这里能存什么」，用户可直接删。故意跨用途各一条。"""
    return [
        {"name": "AT 查版本", "text": "AT+VERSION?\r\n", "hex": False},
        {"name": "Modbus 读保持寄存器", "text": "01 03 00 00 00 02 C4 0B", "hex": True},
        {"name": "复位帧示例", "text": "AA 55 00 FF", "hex": True},
    ]


def match(snip, query):
    """模糊搜索：query（不分大小写）命中名称或内容即算匹配。空 query 全通过。"""
    q = (query or "").strip().lower()
    if not q:
        return True
    return q in snip.get("name", "").lower() or q in snip.get("text", "").lower()


def filter_snippets(items, query):
    """返回 [(原始下标, 模板), ...]：保留原下标，供 UI 过滤显示后仍能定位回真实数据。"""
    return [(i, s) for i, s in enumerate(items) if match(s, query)]


def to_json(items):
    """导出为带版本头的 JSON 文本（缩进易读、可手改）。"""
    return json.dumps({"type": "commtool-snippets", "version": 1,
                       "snippets": sanitize_list(items)},
                      ensure_ascii=False, indent=2)


def from_json(text):
    """解析导入文本 → 合法模板列表。兼容三种形态，宽进：
       - {"snippets": [...]}（本程序导出格式）
       - 直接是一个列表 [...]（用户手写 / 别处拷来）
       - {"items": [...]}（与多条发送同构，方便互转）
    解析失败 raise ValueError（调用方转成用户可见的错误提示）。"""
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as e:
        raise ValueError("bad json: %s" % e)
    if isinstance(data, list):
        return sanitize_list(data)
    if isinstance(data, dict):
        for key in ("snippets", "items"):
            if isinstance(data.get(key), list):
                return sanitize_list(data[key])
    raise ValueError("no snippet list found")
