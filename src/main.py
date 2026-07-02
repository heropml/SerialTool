# -*- coding: utf-8 -*-
"""CommTool 入口。"""
import os
import sys
import multiprocessing
from PyQt5.QtCore import Qt, QLockFile
from PyQt5.QtWidgets import QApplication
from app_icon import get_app_icon
from fonts import install_font_substitutions, ui_font
from main_window import CommTool
from updater import cleanup_temp_installers, set_translator


def _acquire_profile(settings_path=None):
    """为本窗口挑第一个空闲配置槽位并加锁；返回 (profile, QLockFile)。
    ""=主配置(settings.ini)，其余 2..8=settings-<N>.ini。QLockFile 记录持有进程 PID，
    异常退出留下的陈旧锁会被自动回收。**锁对象须由调用方持有到进程结束**，否则被 GC 释放、
    槽位会被下一个窗口抢占。都占满(≥8 窗口)则用 PID 作唯一 profile（不加锁，仍保证配置独立）。
    settings_path：计算配置文件路径的函数（默认 CommTool._settings_file）；测试可注入临时目录版以隔离。"""
    if settings_path is None:
        settings_path = CommTool._settings_file
    for p in [""] + [str(n) for n in range(2, 9)]:
        lock = QLockFile(settings_path(p) + ".lock")
        if lock.tryLock(100):
            return p, lock
    return str(os.getpid()), None


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
    # 多窗口配置隔离：挑一个空闲配置槽位（主/2/3…）并加锁——双击开多个 / 「新建窗口」
    # 都各用各的配置、退出不互相覆盖。_profile_lock 必须留到退出（勿删），否则锁提前释放。
    profile, _profile_lock = _acquire_profile()
    w = CommTool(profile)
    set_translator(w._t)   # 把 updater 的用户可见错误文案接入主窗口多语言
    w.setWindowIcon(get_app_icon())
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
