# -*- coding: utf-8 -*-
"""NetworkTool 入口。"""
import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication
from app_icon import get_app_icon
from main_window import NetworkTool


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Tools.NetworkTool.1.0")
        except Exception:
            pass

    # 高分屏(HiDPI)缩放：必须在 QApplication 创建前设置，否则 2560x1600 等高分屏上
    # Qt 按物理像素渲染，字号/下拉框都显得很小。PassThrough 让 150% 等分数缩放也平滑。
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(get_app_icon())

    for family in ("SF Pro Display", "PingFang SC", "Segoe UI", "Microsoft YaHei UI"):
        f = QFont(family, 10)
        if QFont(family).exactMatch() or family in ("Segoe UI", "Microsoft YaHei UI"):
            app.setFont(f)
            break

    w = NetworkTool()
    w.setWindowIcon(get_app_icon())
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
