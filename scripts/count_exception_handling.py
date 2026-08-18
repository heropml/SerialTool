# -*- coding: utf-8 -*-
"""统计 src/ 里的宽泛异常捕获与静默吞异常，供 docs/TODO.md 的 S-1 进度使用。

手工数出来的数字很快就会漂移（改一处 except 就得记得改文档），所以固定用这个
脚本重算：

    python scripts/count_exception_handling.py           # 汇总 + 明细
    python scripts/count_exception_handling.py --md      # 直接贴进 TODO 的一行

口径说明（重要，换算法数字就对不上了）：

* **宽泛捕获**：``except Exception`` 或裸 ``except:``；写明具体异常类型的不算。
* **静默吞**：宽泛捕获的处理体只有一句 ``pass``。带 ``return`` / 日志 / 兜底动作
  的不算静默——它们仍可能吞信息，但至少是有意为之的控制流。

注释和空行会跳过；用 AST 而不是正则，避免把字符串里的 ``except`` 数进来。
"""
import argparse
import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def iter_src_py():
    """All application modules under src/, including domain packages."""
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        yield path


def src_label(path):
    return path.relative_to(SRC).as_posix()


def is_broad(handler):
    """裸 except 或 except Exception（含 as e）。"""
    if handler.type is None:
        return True
    node = handler.type
    return isinstance(node, ast.Name) and node.id == "Exception"


def is_silent(handler):
    """处理体只有一句 pass。"""
    return len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)


def iter_silent_handlers(path):
    """Yield ``(lineno, end_lineno)`` for each silent broad ``except`` in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.ExceptHandler)
                and is_broad(node) and is_silent(node)):
            end = getattr(node, "end_lineno", None) or node.lineno
            yield node.lineno, end


def scan(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    broad = silent = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not is_broad(node):
            continue
        broad += 1
        silent += is_silent(node)
    return broad, silent


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--md", action="store_true", help="只输出可贴进文档的一行")
    args = ap.parse_args()

    rows = []
    for path in iter_src_py():
        broad, silent = scan(path)
        if broad:
            rows.append((src_label(path), broad, silent))
    total_broad = sum(r[1] for r in rows)
    total_silent = sum(r[2] for r in rows)

    if args.md:
        top = ", ".join("`%s`（%d/%d）" % r for r in
                        sorted(rows, key=lambda r: -r[2])[:3] if r[2])
        print("全量 %d 处宽泛 `except`、其中 %d 处静默 `pass`；静默集中在 %s"
              % (total_broad, total_silent, top))
        return 0

    print("%-40s %8s %8s" % ("module", "broad", "silent"))
    for name, broad, silent in sorted(rows, key=lambda r: (-r[2], -r[1])):
        print("%-40s %8d %8d" % (name, broad, silent))
    print("%-40s %8d %8d" % ("TOTAL", total_broad, total_silent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
