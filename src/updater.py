# -*- coding: utf-8 -*-
"""在线更新：检查最新版本（GitHub raw）+ 下载安装包并运行。

更新源是一份「版本清单」JSON：
    {"version": "1.0.5", "url": "<安装包下载地址>", "notes": "本次更新内容…"}
按 UPDATE_MANIFEST_URLS 的顺序逐个尝试，第一个成功拿到的为准。
基于 Qt 自带 QtNetwork，无需额外依赖。

发版流程：打好安装包传到下载地址 → 更新各源上的 latest.json 的 version/url/notes。
注意：清单 URL 必须能**免登录**访问（开放的内网 HTTP，或公开仓库的 raw / Releases）。
"""
import os
import re
import sys
import json
import glob
import tempfile
import ssl
import urllib.request
import urllib.error
from PyQt5.QtCore import QObject, pyqtSignal, QUrl, QThread

# 版本清单地址，按顺序逐个尝试，第一个成功的为准。
# Gitee 在前（用户绝大多数是国内嵌入式开发者，gitee.com 国内直连、秒回）；GitHub 在后做回退
# （海外/能直连 GitHub 的环境，Gitee 万一抽风时兜底）。两源 latest.json 内容一致，url 都指向
# Gitee Release 下载（Gitee 全球可达，国内国外都下得到）。
UPDATE_MANIFEST_URLS = [
    "https://gitee.com/heropml/SerialTool/raw/CommTool/latest.json",              # Gitee raw（国内优先）
    "https://raw.githubusercontent.com/heropml/SerialTool/CommTool/latest.json",  # GitHub raw（回退）
]

# 超时（毫秒）：每个更新源连不上就尽快轮到下一个。
_CHECK_TIMEOUT_MS = 8000      # 单个更新源的响应超时
_DOWNLOAD_STALL_MS = 30000    # 下载“停滞”超时：这么久没有新数据就判失败

# i18n 翻译钩子：main 启动时用 set_translator(主窗口._t) 注入；未注入时回退返回 key 本身。
# updater 是独立模块、不持有语言状态，故用此钩子把少量用户可见错误文案接入多语言。
_translate = lambda key: key


def set_translator(fn):
    global _translate
    _translate = fn


def _parse_version(v):
    """'v1.0.5' / '1.0.5' / '1.0.5-rc1' -> 可比较元组；非法返回 (0,)。
    主版本补齐到 3 段(避免 '1.0' 与 '1.0.0' 因长度不同误判)，末位附加预发布标记
    (正式版 1 > 预发布 0)，于是 1.0.5 > 1.0.5-rc1，不再把 '-rc1' 整段截断成等同正式版。"""
    try:
        s = str(v).strip().lstrip("vV")
        main, _, pre = s.partition("-")   # 拆出主版本与可选预发布后缀(-rc1/-beta…)
        nums = []
        for part in main.split("."):
            m = re.match(r"\d+", part)
            if not m:
                break
            nums.append(int(m.group()))
        if not nums:
            return (0,)
        while len(nums) < 3:              # 补齐 3 段：1.0 → (1,0,0)
            nums.append(0)
        nums.append(0 if pre else 1)      # 预发布排在同号正式版之前
        return tuple(nums)
    except (ValueError, AttributeError, TypeError):
        return (0,)


def is_newer(remote, local):
    """remote 版本是否比 local 新"""
    return _parse_version(remote) > _parse_version(local)


def cleanup_temp_installers():
    """清理上次更新残留在 %TEMP% 的安装包（CommTool_Setup_*.exe）。
    启动时调用一次；删不掉（可能仍被占用）就跳过，不影响启动。"""
    try:
        pattern = os.path.join(tempfile.gettempdir(), "CommTool_Setup_*.exe")
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass
    except Exception:
        pass


# 程序化请求的 User-Agent + 系统证书：Qt 的 QNetworkAccessManager 走 OpenSSL，而 OpenSSL
# 在 Windows 默认不读系统证书存储 → 某些机器验证 Gitee/GitHub 证书失败、所有更新源「连不上」
# （浏览器/Python ssl 用系统证书则正常，表现为「网页能开但程序连不上」）。故清单与下载都改用
# Python urllib（系统证书）+ 浏览器 UA，放子线程跑、不阻塞 UI。
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 CommTool")
_running_workers = set()   # 保活在跑的 worker，防 Checker/Downloader 先销毁导致 QThread 被回收


def _ssl_context():
    """Windows 上 ssl 默认 context 用系统证书存储（与浏览器一致），避免 OpenSSL 找不到根 CA。"""
    try:
        return ssl.create_default_context()
    except Exception:
        return None


class _ManifestWorker(QThread):
    """子线程逐个试 UPDATE_MANIFEST_URLS（urllib + 系统证书 + UA），拿到清单即停。"""
    got = pyqtSignal(object, str)        # (info|None, err)

    def __init__(self, current_version):
        super().__init__()               # 无 parent：生命周期独立、由 _running_workers 保活
        self._cur = current_version
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        ctx = _ssl_context()
        last_err = ""
        for url in UPDATE_MANIFEST_URLS:
            if self._stop:
                return
            host = url.split("/")[2] if "//" in url else url
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": _UA,
                                  "Accept": "application/json, text/plain, */*"})
                with urllib.request.urlopen(req, timeout=_CHECK_TIMEOUT_MS / 1000.0,
                                            context=ctx) as resp:
                    data = resp.read(1 << 20)        # 清单很小，限 1MB 防异常超大响应
                m = json.loads(data.decode("utf-8"))
                ver = str(m["version"])
            except Exception as e:
                last_err = "%s: %s" % (host, e)      # 记最后一个源的错误，全失败时回传
                continue
            if self._stop:
                return
            self.got.emit({
                "version": ver,
                "url": str(m.get("url", "")),
                "notes": str(m.get("notes", "")),
                "newer": is_newer(ver, self._cur),
                "source": url,
            }, "")
            return
        if not self._stop:
            self.got.emit(None, last_err or _translate("updater_no_source"))


class UpdateChecker(QObject):
    """逐个尝试 UPDATE_MANIFEST_URLS（urllib + 系统证书 + UA，子线程），拿到清单后与当前版本比较。
    finished(info|None, error): info = {version, url, notes, newer, source}"""
    finished = pyqtSignal(object, str)

    def __init__(self, current_version, parent=None):
        super().__init__(parent)
        self._cur = current_version
        self._worker = None
        self._stopped = False

    def start(self):
        w = _ManifestWorker(self._cur)
        w.got.connect(self._on_got)
        w.finished.connect(lambda: (_running_workers.discard(w), w.deleteLater()))
        _running_workers.add(w)
        self._worker = w
        w.start()

    def _on_got(self, info, err):
        if not self._stopped:
            self.finished.emit(info, err)

    def abort(self):
        """供调用方（如关闭对话框时）中止：置位后 worker 结果被丢弃（urllib 不可异步 abort，
        但每源至多等 _CHECK_TIMEOUT_MS，worker 跑完自行回收）。"""
        self._stopped = True
        if self._worker is not None:
            self._worker.stop()


class _DownloadWorker(QThread):
    """子线程用 urllib（系统证书 + UA）下载到 path：分块写、报进度、可中止、校验 MZ 头。"""
    progressed = pyqtSignal(int, int)    # 已下载, 总大小
    done = pyqtSignal(str, str)          # 保存路径|'', 错误

    def __init__(self, url, path):
        super().__init__()
        self._url = url
        self._path = path
        self._stop = False

    def stop(self):
        self._stop = True

    def _remove(self):
        try:
            os.remove(self._path)
        except OSError:
            pass

    def run(self):
        ctx = _ssl_context()
        try:
            req = urllib.request.Request(self._url, headers={"User-Agent": _UA})
            # timeout 既是连接超时、也是每次 read 的 socket 超时：停滞超过它即抛、判失败。
            with urllib.request.urlopen(req, timeout=_DOWNLOAD_STALL_MS / 1000.0,
                                        context=ctx) as resp, open(self._path, "wb") as fp:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                while not self._stop:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fp.write(chunk)
                    got += len(chunk)
                    self.progressed.emit(got, total)
        except Exception as e:
            self._remove()
            self.done.emit("", str(e))
            return
        if self._stop:
            self._remove()                        # 中止：删半成品
            self.done.emit("", _translate("updater_cancelled"))
            return
        # 校验下载到的是不是真正的 Windows 可执行文件（防 404/错误页被当成功）
        try:
            with open(self._path, "rb") as f:
                head = f.read(2)
        except OSError as e:
            self.done.emit("", str(e))
            return
        if head != b"MZ":
            self._remove()
            self.done.emit("", _translate("updater_bad_installer"))
            return
        self.done.emit(self._path, "")


class UpdateDownloader(QObject):
    """下载安装包到 %TEMP%（urllib + 系统证书 + UA，子线程），带进度。finished(saved_path|'', error)"""
    progress = pyqtSignal(int, int)   # 已下载, 总大小
    finished = pyqtSignal(str, str)   # 保存路径, 错误

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self._url = url
        self._worker = None
        self._stopped = False

    def start(self):
        # 只允许 https 下载源：防清单被改成 http/file 等降级或本地路径
        if not str(self._url).lower().startswith("https://"):
            self.finished.emit("", _translate("updater_bad_url"))
            return
        name = os.path.basename(QUrl(self._url).path()) or "Setup.exe"
        path = os.path.join(tempfile.gettempdir(), name)
        w = _DownloadWorker(self._url, path)
        w.progressed.connect(self._on_progress)
        w.done.connect(self._on_done)
        w.finished.connect(lambda: (_running_workers.discard(w), w.deleteLater()))
        _running_workers.add(w)
        self._worker = w
        w.start()

    def _on_progress(self, got, total):
        if not self._stopped:
            self.progress.emit(got, total)

    def _on_done(self, path, err):
        if not self._stopped:
            self.finished.emit(path, err)

    def abort(self):
        """供调用方（如关闭对话框时）中止下载：worker 停止 + 删半成品，结果被丢弃。"""
        self._stopped = True
        if self._worker is not None:
            self._worker.stop()


def run_installer(path):
    """启动下载好的安装程序（正常向导，由用户手动点击完成安装）。
    返回 True 表示已拉起安装程序；随后本 app 会退出，让安装程序能覆盖文件。"""
    if sys.platform != "win32":
        return False
    try:
        import subprocess
        # 不加 /SILENT —— 弹出正常安装向导，用户手动点「下一步/安装」。
        # CREATE_NEW_PROCESS_GROUP：让安装向导独立成组，不受本 app 退出影响。
        subprocess.Popen([path], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        return True
    except Exception:
        return False
