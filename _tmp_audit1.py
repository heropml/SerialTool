# -*- coding: gbk -*-
"""机械体检：编码 / 语法 / i18n 一致性 / 静默异常 / 死属性。"""
import ast
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SRC = sorted(Path("src").rglob("*.py"))
TESTS = sorted(Path("tests").rglob("*.py"))
ALL = SRC + TESTS
problems = []

# ---------------------------------------------------------- 1 编码与语法 ----
print("=" * 68)
print("1  \u7f16\u7801\u4e0e\u8bed\u6cd5")
bad_enc = []
for f in ALL:
    data = f.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        bad_enc.append((f, str(e)))
        continue
    try:
        ast.parse(text)
    except SyntaxError as e:
        bad_enc.append((f, "SyntaxError: %s" % e))
    if data.startswith(b"\xef\xbb\xbf"):
        bad_enc.append((f, "\u5e26 UTF-8 BOM"))
print("  %d \u4e2a\u6587\u4ef6\uff0c%s" % (len(ALL), "\u5168\u90e8\u5408\u6cd5 UTF-8 \u4e14\u53ef\u89e3\u6790"
                                        if not bad_enc else "\u95ee\u9898\uff1a"))
for f, why in bad_enc:
    print("  !! %s  %s" % (f, why))
    problems.append("\u7f16\u7801/\u8bed\u6cd5: %s" % f)

# ------------------------------------------------------------ 2 i18n 一致 ----
print("=" * 68)
print("2  i18n \u4e09\u8bed\u4e00\u81f4\u6027")
sys.path.insert(0, "src")
import i18n

langs = list(i18n.TR)
base = langs[0]
keysets = {l: set(i18n.TR[l]) for l in langs}
for l in langs[1:]:
    miss = keysets[base] - keysets[l]
    extra = keysets[l] - keysets[base]
    if miss or extra:
        problems.append("i18n \u952e\u4e0d\u9f50: %s" % l)
        print("  !! %s \u7f3a %d\uff1a%s" % (l, len(miss), sorted(miss)[:6]))
        print("     %s \u591a %d\uff1a%s" % (l, len(extra), sorted(extra)[:6]))
print("  \u952e\u96c6\u5408\uff1a%s" % ("\u4e09\u8bed\u4e00\u81f4 (%d \u952e)" % len(keysets[base])
                              if all(keysets[l] == keysets[base] for l in langs) else "\u4e0d\u4e00\u81f4"))

# 占位符一致
ph_bad = []
for key in sorted(keysets[base]):
    sets = {}
    for l in langs:
        v = i18n.TR[l].get(key)
        sets[l] = set(re.findall(r"\{(\w+)\}", v)) if isinstance(v, str) else None
    ref = sets[base]
    for l in langs[1:]:
        if sets[l] is not None and ref is not None and sets[l] != ref:
            ph_bad.append((key, base, sorted(ref), l, sorted(sets[l])))
print("  \u5360\u4f4d\u7b26\uff1a%s" % ("\u5168\u90e8\u5bf9\u5e94" if not ph_bad else "%d \u5904\u4e0d\u5bf9" % len(ph_bad)))
for row in ph_bad[:10]:
    print("  !! %s  %s=%s  %s=%s" % row)
    problems.append("i18n \u5360\u4f4d\u7b26: %s" % row[0])

# 疑似未翻译（zh_tw 与 en 完全相同且含 ASCII 字母）
if "zh_tw" in langs and "en" in langs:
    untranslated = [k for k in keysets[base]
                    if isinstance(i18n.TR["zh_tw"].get(k), str)
                    and i18n.TR["zh_tw"][k] == i18n.TR["en"].get(k)
                    and re.search(r"[A-Za-z]{4,}", i18n.TR["zh_tw"][k])
                    and i18n.TR["zh"].get(k) != i18n.TR["en"].get(k)]
    print("  zh_tw \u7591\u4f3c\u672a\u8bd1\uff1a%d \u6761" % len(untranslated))
    for k in sorted(untranslated)[:12]:
        print("     - %s = %r" % (k, i18n.TR["zh_tw"][k][:56]))
    if untranslated:
        problems.append("zh_tw \u672a\u8bd1 %d \u6761" % len(untranslated))

# ------------------------------------------------------ 3 静默吞异常统计 ----
print("=" * 68)
print("3  \u5f02\u5e38\u5904\u7406")


class H(ast.NodeVisitor):
    def __init__(self):
        self.silent = []      # except ...: pass（什么都不做）
        self.broad = 0

    def visit_ExceptHandler(self, node):
        body = [n for n in node.body if not isinstance(n, ast.Expr)
                or not isinstance(n.value, ast.Constant)]
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            self.silent.append(node.lineno)
        if node.type is None or (isinstance(node.type, ast.Name)
                                 and node.type.id in ("Exception", "BaseException")):
            self.broad += 1
        self.generic_visit(node)


tot_silent = tot_broad = 0
for f in SRC:
    h = H()
    h.visit(ast.parse(f.read_text(encoding="utf-8")))
    tot_silent += len(h.silent)
    tot_broad += h.broad
    if h.silent:
        print("  %s: \u9759\u9ed8 pass \u00d7%d \u884c %s" % (f.name, len(h.silent), h.silent[:8]))
print("  src \u5408\u8ba1\uff1a\u5bbd\u6cdb\u6355\u83b7 %d\uff0c\u5176\u4e2d\u9759\u9ed8 pass %d" % (tot_broad, tot_silent))

# ------------------------------------------------------------ 4 死属性 ----
print("=" * 68)
print("4  \u53ea\u5199\u4e0d\u8bfb\u7684 self.\u5c5e\u6027\uff08\u53ef\u80fd\u662f\u6b7b\u4ee3\u7801\uff09")
stored, loaded = defaultdict(set), set()
for f in ALL:
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.ctx, ast.Store):
                stored[node.attr].add(f.name)
            else:
                loaded.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            loaded.add(node.value)          # getattr("x") 之类
dead = sorted(a for a in stored
              if a not in loaded and a.startswith("_") and not a.startswith("__"))
print("  %d \u4e2a\uff1a%s" % (len(dead), dead[:20] if dead else "\u65e0"))
for a in dead[:20]:
    problems.append("\u53ea\u5199\u4e0d\u8bfb: %s (%s)" % (a, ",".join(sorted(stored[a]))))

print("=" * 68)
print("\u5c0f\u7ed3\uff1a%d \u6761\u5f85\u786e\u8ba4" % len(problems))
for p in problems:
    print("  - %s" % p)
