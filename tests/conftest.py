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


def pytest_sessionfinish(session, exitstatus):
    """在解释器静态析构前正常释放测试创建的原生事件循环和 Qt 窗口。

    全套 GUI 测试会跨模块复用同一个 QApplication；若把清理留到 Python
    finalize，Windows 的 Qt/IOCP 静态析构顺序不确定。这里不改 exitstatus、
    不调用 os._exit，断言失败和 teardown 失败仍由 pytest 原样返回。
    """
    if sys.platform != "win32":
        return
    try:
        from transport import ble_io
        ble_io.shutdown_loop()
        ble_io._stop_all_loops_at_exit()
    except Exception:
        pass
    try:
        from PyQt5.QtCore import QCoreApplication, QEvent
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.closeAllWindows()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
    except Exception:
        pass
