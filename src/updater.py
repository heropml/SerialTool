# -*- coding: utf-8 -*-
"""在线更新：检查最新版本（内网优先，回退 GitHub）+ 下载安装包并运行。

更新源是一份「版本清单」JSON：
    {"version": "1.0.5", "url": "<安装包下载地址>", "notes": "本次更新内容…"}
按 UPDATE_MANIFEST_URLS 的顺序逐个尝试，第一个成功拿到的为准（所以把内网放前面）。
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
from PyQt5.QtCore import QObject, pyqtSignal, QUrl, QTimer
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

# 版本清单地址（内网优先，回退 GitHub）。按需改成你实际托管 latest.json 的地址。
UPDATE_MANIFEST_URLS = [
    "http://192.168.50.40/pengml/SerialTool/-/raw/NetworkTool/latest.json",          # 内网 GitLab raw
    "https://raw.githubusercontent.com/heropml/SerialTool/NetworkTool/latest.json",  # GitHub raw 回退
]

# 超时（毫秒）：每个更新源连不上就尽快轮到下一个，避免外网用户卡在内网 IP 上。
_CHECK_TIMEOUT_MS = 8000      # 单个更新源的响应超时
_DOWNLOAD_STALL_MS = 30000    # 下载“停滞”超时：这么久没有新数据就判失败


def _parse_version(v):
    """'v1.0.5' / '1.0.5' / '1.0.5-beta' -> (1,0,5)；非法返回 (0,)。
    遇到非数字段（如 -beta / rc）就截断，不抛异常。"""
    try:
        nums = []
        for part in str(v).strip().lstrip("vV").split("."):
            m = re.match(r"\d+", part)
            if not m:
                break
            nums.append(int(m.group()))
        return tuple(nums) if nums else (0,)
    except (ValueError, AttributeError, TypeError):
        return (0,)


def is_newer(remote, local):
    """remote 版本是否比 local 新"""
    return _parse_version(remote) > _parse_version(local)


def cleanup_temp_installers():
    """清理上次更新残留在 %TEMP% 的安装包（NetworkTool_Setup_*.exe）。
    启动时调用一次；删不掉（可能仍被占用）就跳过，不影响启动。"""
    try:
        pattern = os.path.join(tempfile.gettempdir(), "NetworkTool_Setup_*.exe")
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass
    except Exception:
        pass


class UpdateChecker(QObject):
    """逐个尝试 UPDATE_MANIFEST_URLS，拿到清单后和当前版本比较。
    finished(info|None, error): info = {version, url, notes, newer, source}"""
    finished = pyqtSignal(object, str)

    def __init__(self, current_version, parent=None):
        super().__init__(parent)
        self._cur = current_version
        self._nam = QNetworkAccessManager(self)
        self._urls = list(UPDATE_MANIFEST_URLS)
        self._idx = 0
        self._reply = None
        self._stopped = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def start(self):
        self._try_next()

    def _try_next(self):
        if self._stopped:
            return
        if self._idx >= len(self._urls):
            self.finished.emit(None, "所有更新源都连不上")
            return
        url = self._urls[self._idx]
        self._idx += 1
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        self._reply = self._nam.get(req)
        self._reply.finished.connect(lambda r=self._reply: self._on_reply(r))
        self._timer.start(_CHECK_TIMEOUT_MS)

    def _on_timeout(self):
        # 当前源超时：abort 当前请求 → 触发 _on_reply（error≠NoError）→ 试下一个源
        if self._reply is not None:
            self._reply.abort()

    def _on_reply(self, reply):
        self._timer.stop()
        if self._reply is reply:
            self._reply = None
        if self._stopped:
            reply.deleteLater()
            return
        err = reply.error()
        data = bytes(reply.readAll())
        url = reply.request().url().toString()
        reply.deleteLater()
        if err != QNetworkReply.NoError or not data:
            self._try_next()    # 这个源不通，试下一个
            return
        try:
            m = json.loads(data.decode("utf-8"))
            ver = str(m["version"])
        except Exception:
            self._try_next()
            return
        info = {
            "version": ver,
            "url": str(m.get("url", "")),
            "notes": str(m.get("notes", "")),
            "newer": is_newer(ver, self._cur),
            "source": url,
        }
        self.finished.emit(info, "")

    def abort(self):
        """供调用方（如关闭对话框时）中止进行中的检查。"""
        self._stopped = True
        self._timer.stop()
        if self._reply is not None:
            try:
                self._reply.abort()
            except Exception:
                pass


class UpdateDownloader(QObject):
    """下载安装包到 %TEMP%，带进度。finished(saved_path|'', error)"""
    progress = pyqtSignal(int, int)   # 已下载, 总大小
    finished = pyqtSignal(str, str)   # 保存路径, 错误

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self._url = url
        self._nam = QNetworkAccessManager(self)
        self._fp = None
        self._path = ""
        self._reply = None
        self._stopped = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def start(self):
        name = os.path.basename(QUrl(self._url).path()) or "Setup.exe"
        self._path = os.path.join(tempfile.gettempdir(), name)
        try:
            self._fp = open(self._path, "wb")
        except OSError as e:
            self.finished.emit("", str(e))
            return
        req = QNetworkRequest(QUrl(self._url))
        req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        self._reply = self._nam.get(req)
        self._reply.downloadProgress.connect(self._emit_progress)
        self._reply.readyRead.connect(self._on_read)
        self._reply.finished.connect(self._on_done)
        self._timer.start(_DOWNLOAD_STALL_MS)

    def _emit_progress(self, rec, total):
        # downloadProgress 参数是 qint64，不能直接 signal→signal 转发到
        # progress(int,int)，否则 connect() 抛 TypeError（点下载即闪退）。
        # 必须经一个槽显式转成 int 再发出。
        self._timer.start(_DOWNLOAD_STALL_MS)   # 有进度就重置“停滞”超时
        self.progress.emit(int(rec), int(total))

    def _on_timeout(self):
        # 下载停滞太久：abort → 触发 _on_done（error≠NoError）
        if self._reply is not None:
            self._reply.abort()

    def _on_read(self):
        if self._fp and self._reply:
            self._fp.write(bytes(self._reply.readAll()))

    def _on_done(self):
        self._timer.stop()
        reply = self._reply
        self._reply = None
        err = reply.error() if reply is not None else QNetworkReply.OperationCanceledError
        msg = reply.errorString() if reply is not None else "已取消"
        if reply is not None:
            reply.deleteLater()
        if self._fp:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None
        if self._stopped:
            self._remove_path()        # 关闭中止：删掉写了一半的文件
            return
        if err != QNetworkReply.NoError:
            self._remove_path()
            self.finished.emit("", msg)
            return
        # 校验下载到的是不是真正的 Windows 可执行文件（防 404/错误页被当成功）。
        try:
            with open(self._path, "rb") as f:
                head = f.read(2)
        except OSError as e:
            self.finished.emit("", str(e))
            return
        if head != b"MZ":
            self._remove_path()
            self.finished.emit("", "下载内容不是有效安装包（可能是错误页面）")
            return
        self.finished.emit(self._path, "")

    def _remove_path(self):
        try:
            if self._path:
                os.remove(self._path)
        except OSError:
            pass

    def abort(self):
        """供调用方（如关闭对话框时）中止下载：停请求、关句柄、删半成品。"""
        self._stopped = True
        self._timer.stop()
        if self._fp:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None
        if self._reply is not None:
            try:
                self._reply.abort()    # 触发 _on_done（_stopped 分支收尾删文件）
            except Exception:
                pass
        else:
            self._remove_path()


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
