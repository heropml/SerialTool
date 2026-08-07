# -*- coding: utf-8 -*-
"""Qt-free unit tests for seq_report (S-2)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import seq_report as sr


def test_csv_safe_formula_prefix():
    assert sr.csv_safe("=1+1").startswith("'")
    assert sr.csv_safe("+cmd").startswith("'")
    assert sr.csv_safe("  @x").startswith("'")
    assert sr.csv_safe("ok") == "ok"
    assert sr.csv_safe(12) == 12


def test_report_fmt_extension_and_filter():
    assert sr.report_fmt("a.csv") == ("csv", "a.csv")
    assert sr.report_fmt("a.xml") == ("junit", "a.xml")
    assert sr.report_fmt("a.html") == ("html", "a.html")
    assert sr.report_fmt("out", "CSV (*.csv)") == ("csv", "out.csv")
    assert sr.report_fmt("out", "JUnit XML (*.xml)") == ("junit", "out.xml")
    assert sr.report_fmt("out", "HTML (*.html)") == ("html", "out.html")


def test_build_html_contains_verdict_and_rows():
    html = sr.build_html(
        "Report",
        [("Version", "1.0")],
        "PASS 1/1",
        True,
        ["#", "Name"],
        [{"cells": [1, "step"], "cls": "ok"}],
    )
    assert "PASS 1/1" in html
    assert "step" in html
    assert "#2f9e44" in html
    assert "<th>#</th>" in html


def test_build_csv_roundtrip_safe():
    text = sr.build_csv(
        "Report",
        [("K", "V")],
        "ok",
        ["A", "B"],
        [{"cells": ["=1", "x"], "cls": "fail"}],
    )
    assert "Report" in text
    assert "'=1" in text
    assert "K,V" in text.replace(" ", "")
