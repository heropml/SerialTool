# -*- coding: utf-8 -*-
"""CommTool 入口。"""
import sys
import multiprocessing
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from app_icon import get_app_icon
from fonts import install_font_substitutions, ui_font
from main_window import CommTool
from updater import cleanup_temp_installers, set_translator


def main():
    # PyInstaller/Windows 下脚本应答使用 multiprocessing 隔离执行；必须在创建
    # QApplication 前调用，否则冻结版子进程会递归重启整个 GUI。
    multiprocessing.freeze_support()
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Tools.CommTool.1.0")
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

    # 注册字体替换（让样式表里残留的 'Segoe UI'/'Consolas' 落到本平台字体），
    # 再把全局默认字体设为本平台界面字体。
    install_font_substitutions()
    app.setFont(ui_font(10))

    cleanup_temp_installers()   # 清理上次更新残留在 %TEMP% 的安装包
    w = CommTool()
    set_translator(w._t)   # 把 updater 的用户可见错误文案接入主窗口多语言
    w.setWindowIcon(get_app_icon())
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
