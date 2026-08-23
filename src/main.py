# -*- coding: utf-8 -*-
"""CommTool 入口。"""
import sys
import os
import logging
import multiprocessing
from PyQt5.QtCore import Qt, QLockFile, QSettings
from PyQt5.QtNetwork import QNetworkProxy
from PyQt5.QtWidgets import QApplication, QMessageBox
from app_icon import get_app_icon
from ui.fonts import install_font_substitutions, ui_font
from ui.i18n import TR
from main_window import CommTool
from sessions.session import MAX_SESSIONS
from updater import cleanup_temp_installers, set_translator
from diagnostics import configure_logging, install_exception_logging


_VALID_PROFILES = {""} | {str(n) for n in range(2, MAX_SESSIONS + 1)}  # ""=主配置 / "2"..MAX_SESSIONS


def _parse_profile_arg(argv):
    """从命令行取 `--profile=<值>`（「打开配置」子菜单启动新进程时带上）；没有则返回 None。
    值须在合法槽位集内（""=主配置 / "2".."8"）；越界或乱填（如 `--profile=9`/`--profile=abc`）
    按「未指定」处理返回 None → 回落自动分配，避免建出菜单里选不到的孤儿 settings-9.ini。"""
    for a in argv:
        if a.startswith("--profile="):
            v = a[len("--profile="):]
            return v if v in _VALID_PROFILES else None
    return None


def _acquire_profile(settings_path=None, preferred=None):
    """为本窗口挑一个空闲配置槽位并加锁；返回 (profile, QLockFile)。
    ""=主配置(settings.ini)，其余 2..8=settings-<N>.ini。QLockFile 记录持有进程 PID，
    异常退出留下的陈旧锁会被自动回收。**锁对象须由调用方持有到进程结束**，否则被 GC 释放、
    槽位会被下一个窗口抢占。
    settings_path：计算配置文件路径的函数（默认 CommTool._settings_file）；测试可注入临时目录版以隔离。
    preferred：「打开指定配置」时用户选定的槽位，优先尝试；被占则回落到正常的「第一个空闲」扫描。
    8 个槽位全被占（已开满 8 个窗口）→ 返回 (None, None)，调用方据此提示「已达最大窗口数」并退出
    （不再用 PID 建标题难看又进不了菜单管理的 settings-<PID>.ini 孤儿配置）。

    ⚠️ 锁文件后缀必须用 `.mwlock`，**不能**用 `.lock`：QSettings 写盘(sync())时内部会对
    `<ini文件>.lock` 加自己的 QLockFile；若本函数也占用同名 `.lock`，同进程里 QSettings 一 sync
    就会死等自己持有的锁 → 死锁（表现：新配置窗口构造时卡住只剩进程没界面、关窗保存时卡死）。"""
    if settings_path is None:
        settings_path = CommTool._settings_file
    order = [""] + [str(n) for n in range(2, MAX_SESSIONS + 1)]
    if preferred is not None and str(preferred) in order:   # 仅合法槽位可优先；越界 preferred 忽略、走正常扫描
        preferred = str(preferred)
        order = [preferred] + [p for p in order if p != preferred]
    for p in order:
        lock = QLockFile(settings_path(p) + ".mwlock")   # 见上：勿改回 .lock（会与 QSettings 撞锁死锁）
        if lock.tryLock(100):
            return p, lock
    return None, None    # 槽位占满（8 个窗口都开着）→ 交调用方提示已达上限并退出


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

    # 调试工具的 TCP/UDP 都是直连——强制 Qt socket 不走代理。否则开着系统代理时，
    # QTcpSocket 连非回环地址会被套进 HTTP 代理（不支持裸 TCP → "The proxy type is invalid for
    # this operation"），表现为连本机/局域网 TCP 服务器失败（连 127.0.0.1 因绕过代理反而正常）。
    # 更新检查走 urllib、自带代理逻辑，不受这里影响。
    QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.NoProxy))

    # 注册字体替换（让样式表里残留的 'Segoe UI'/'Consolas' 落到本平台字体），
    # 再把全局默认字体设为本平台界面字体。
    install_font_substitutions()
    app.setFont(ui_font(10))

    cleanup_temp_installers()   # 清理上次更新残留在系统临时目录的安装包
    # 多窗口配置隔离：挑一个空闲配置槽位（主/2/3…）并加锁——双击开多个 / 「新建窗口」
    # 都各用各的配置、退出不互相覆盖。锁必须留到进程退出，否则被释放、槽位会被下一个窗口抢占；
    # 挂到 app（生命周期=整个进程）上保活，比裸局部变量更稳（不依赖 CPython 引用计数细节）。
    # `--profile=<N>`（「打开指定配置」子菜单传入）优先占该槽位；被占或未指定则自动分配。
    preferred = _parse_profile_arg(sys.argv)
    profile, profile_lock = _acquire_profile(preferred=preferred)
    if profile is None:
        # 8 个配置槽位都被占用（已开满 8 个窗口）→ 提示并退出，不再开第 9 个
        try:
            lang = QSettings(CommTool._settings_file(""), QSettings.IniFormat).value("language", "zh")
            tr = TR.get(lang if lang in TR else "zh", TR["zh"])
        except Exception:
            tr = TR["zh"]
        QMessageBox.information(None, tr.get("app_title", "CommTool"),
                                tr.get("max_windows", "最多同时打开 8 个窗口。"))
        return
    app._profile_lock = profile_lock
    settings_path = CommTool._settings_file(profile)
    log_dir = os.path.join(os.path.dirname(settings_path), "logs")
    log_name = "commtool.log" if not profile else "commtool-profile-%s.log" % profile
    app._diagnostics_log_dir = log_dir
    app._diagnostics_log_name = log_name
    configure_logging(log_dir, log_name=log_name)
    install_exception_logging()
    logging.getLogger(__name__).info(
        "CommTool starting (profile=%s)", profile or "main")
    w = CommTool(profile)
    set_translator(w._t)   # 把 updater 的用户可见错误文案接入主窗口多语言
    w.setWindowIcon(get_app_icon())
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
