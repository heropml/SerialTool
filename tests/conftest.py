# -*- coding: utf-8 -*-
"""Shared pytest bootstrap for CommTool.

Force Qt offscreen before any test imports create QApplication, so local and
CI runs share the same headless path.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
