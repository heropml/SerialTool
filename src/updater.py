# -*- coding: utf-8 -*-
"""在线更新：检查最新版本（GitHub raw）+ 下载安装包并运行。

更新源是一份「版本清单」JSON：
    {"version": "1.0.5", "url": "<安装包下载地址>",
     "sha256": "<64位摘要>", "size": 123456, "notes": "本次更新内容…"}
按 UPDATE_MANIFEST_URLS 的顺序逐个尝试，第一个成功拿到的为准。
基于 Qt 自带 QtNetwork，无需额外依赖。

发版流程：打好安装包 → update_manifest_integrity.py 写摘要/大小 → 上传并发布清单。
注意：清单 URL 必须能**免登录**访问（开放的内网 HTTP，或公开仓库的 raw / Releases）。
"""
import glob
import hashlib
import http.client
import json
import logging
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
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


_log = logging.getLogger(__name__)


def set_translator(fn):
    global _translate
    _translate = fn


def _parse_version(v):
    """'v1.0.5' / '1.0.5' / '1.0.5-rc1' -> 可比较元组；非法返回 None。
    主版本补齐到 3 段(避免 '1.0' 与 '1.0.0' 因长度不同误判)，末位附加预发布标记
    (正式版 1 > 预发布 0)，于是 1.0.5 > 1.0.5-rc1，不再把 '-rc1' 整段截断成等同正式版。
    预发布后缀拆为 (名称, 序号) 使 rc1 < rc2 可区分。"""
    try:
        s = str(v).strip().lstrip("vV")
        main, sep, pre = s.partition("-")  # 拆出主版本与可选预发布后缀(-rc1/-beta…)
        pre = pre.strip()
        parts = main.split(".")
        if (not parts or any(not part.isdigit() for part in parts)
                or (sep and not pre)):
            return None
        nums = [int(part) for part in parts]
        while len(nums) < 3:              # 补齐 3 段：1.0 → (1,0,0)
            nums.append(0)
        # 1.0.0.0 与 1.0.0 等价；保留额外的非零段，且把主版本整体放在
        # 固定位置，避免 3/4 段版本比较时拿 int 与预发布 tuple 相比。
        while len(nums) > 3 and nums[-1] == 0:
            nums.pop()
        base = tuple(nums)
        if pre:
            # 拆预发布后缀为 (名称, 序号)：rc1 → ("rc", 1)，beta → ("beta", 0)
            m = re.fullmatch(r"([a-zA-Z]+)(\d*)", pre)
            if m:
                name, number = m.group(1).lower(), int(m.group(2) or 0)
            else:
                name, number = pre.lower(), 0
            return (base, 0, name, number)  # 预发布 < 正式版
        return (base, 1, "", 0)
    except (ValueError, AttributeError, TypeError):
        return None


def is_newer(remote, local):
    """remote 版本是否比 local 新"""
    remote_v = _parse_version(remote)
    local_v = _parse_version(local)
    return bool(remote_v is not None and local_v is not None
                and remote_v > local_v)


def https_download_candidates(raw):
    """Normalize a manifest URL field into an ordered HTTPS list (GitHub first).

    Gitee Releases do not host the .dmg / Linux .run in the standard publish
    flow; listing Gitee first causes a guaranteed 404 before the GitHub
    fallback.  Older manifests may still put Gitee first — reorder at runtime.
    """
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = []
    https = []
    seen = set()
    for u in items:
        if not isinstance(u, str):
            continue
        u = u.strip()
        key = u.lower()
        if not key.startswith("https://") or key in seen:
            continue
        seen.add(key)
        https.append(u)

    def _rank(url):
        host = url.lower()
        if "github.com" in host or "githubusercontent.com" in host:
            return 0
        if "gitee.com" in host:
            return 2
        return 1

    https.sort(key=_rank)
    return https


def mac_download_candidates(raw):
    """Normalize url_mac into an ordered HTTPS list (GitHub before Gitee)."""
    return https_download_candidates(raw)


def linux_download_candidates(raw):
    """Normalize url_linux into an ordered HTTPS list (GitHub before Gitee)."""
    return https_download_candidates(raw)


def normalize_sha256(value):
    """Return a canonical 64-char SHA-256 digest, or an empty string."""
    digest = str(value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", digest):
        return digest
    return ""


def normalize_artifact_size(value):
    """Return a positive expected byte size, or 0 when omitted/invalid."""
    try:
        size = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return size if size > 0 else 0


def cleanup_temp_installers():
    """清理上次更新残留在临时目录的 Windows/macOS 安装包。启动时调用一次；
    删不掉（可能仍被占用）就跳过，不影响启动。多窗口下**跳过最近 10 分钟内改动的文件**——
    避免删掉另一个窗口正在下载 / 刚下载完还没启动安装的更新包。"""
    try:
        now = time.time()
        patterns = ("CommTool_Setup_*.exe", "CommTool_v*.dmg", "CommTool_Setup_*.run")
        for name in patterns:
            pattern = os.path.join(tempfile.gettempdir(), name)
            for f in glob.glob(pattern):
                try:
                    if now - os.path.getmtime(f) < 600:  # 近 10 分钟改动 → 可能别的窗口在用
                        continue
                    os.remove(f)
                except OSError:
                    pass
    except (OSError, TypeError, ValueError):
        _log.debug("cleanup_temp_installers failed", exc_info=True)


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
    except (OSError, ValueError, ssl.SSLError):
        return None


def _is_windows():
    """Keep platform checks mockable without mutating process-global sys.platform."""
    return sys.platform == "win32"


def _is_linux():
    return sys.platform.startswith("linux")


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
            except (urllib.error.URLError, TimeoutError, OSError,
                    http.client.HTTPException, ValueError, TypeError,
                    KeyError, UnicodeError) as e:
                last_err = "%s: %s" % (host, e)      # 记最后一个源的错误，全失败时回传
                continue
            if self._stop:
                return
            self.got.emit({
                "version": ver,
                "url": str(m.get("url", "")),
                "url_mac": m.get("url_mac", ""),      # macOS 专用下载(dmg)；可为字符串或多源列表
                "url_linux": m.get("url_linux", ""),  # Linux 专用下载(.run)；可为字符串或多源列表
                "sha256": normalize_sha256(m.get("sha256", "")),
                "size": normalize_artifact_size(m.get("size", 0)),
                "sha256_mac": normalize_sha256(m.get("sha256_mac", "")),
                "size_mac": normalize_artifact_size(m.get("size_mac", 0)),
                "sha256_linux": normalize_sha256(m.get("sha256_linux", "")),
                "size_linux": normalize_artifact_size(m.get("size_linux", 0)),
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
    """Download one artifact, verify expected SHA-256/size, then its file signature."""
    progressed = pyqtSignal(int, int)    # 已下载, 总大小
    done = pyqtSignal(str, str)          # 保存路径|'', 错误

    def __init__(self, url, path, expected_sha256="", expected_size=0):
        super().__init__()
        self._url = url
        self._path = path
        self._expected_sha256 = normalize_sha256(expected_sha256)
        self._expected_size = normalize_artifact_size(expected_size)
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
                digest = hashlib.sha256()
                while not self._stop:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fp.write(chunk)
                    digest.update(chunk)
                    got += len(chunk)
                    self.progressed.emit(got, total)
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException, ValueError, TypeError) as e:
            self._remove()
            self.done.emit("", str(e))
            return
        if self._stop:
            self._remove()                        # 中止：删半成品
            self.done.emit("", _translate("updater_cancelled"))
            return
        if self._expected_size and got != self._expected_size:
            self._remove()
            self.done.emit("", _translate("updater_bad_size"))
            return
        if self._expected_sha256 and digest.hexdigest() != self._expected_sha256:
            self._remove()
            self.done.emit("", _translate("updater_bad_hash"))
            return
        # 校验下载到的是不是真正的安装包（防 404/错误页被当成功）。
        # Windows：MZ/PE；Linux：shell 安装器以 #! 开头；mac .dmg 跳过（错误页走 HTTP 404）。
        if _is_windows() or _is_linux():
            try:
                with open(self._path, "rb") as f:
                    head = f.read(2)
            except OSError as e:
                self._remove()
                self.done.emit("", str(e))
                return
            expect = b"MZ" if _is_windows() else b"#!"
            if head != expect:
                self._remove()
                self.done.emit("", _translate("updater_bad_installer"))
                return
        self.done.emit(self._path, "")


class UpdateDownloader(QObject):
    """下载安装包到 %TEMP%（urllib + 系统证书 + UA，子线程），带进度。finished(saved_path|'', error)"""
    progress = pyqtSignal(int, int)   # 已下载, 总大小
    finished = pyqtSignal(str, str)   # 保存路径, 错误

    def __init__(self, url, parent=None, expected_sha256="", expected_size=0):
        super().__init__(parent)
        self._url = url
        self._expected_sha256 = normalize_sha256(expected_sha256)
        self._expected_size = normalize_artifact_size(expected_size)
        self._worker = None
        self._stopped = False

    def start(self):
        # 只允许 https 下载源：防清单被改成 http/file 等降级或本地路径
        if not str(self._url).lower().startswith("https://"):
            self.finished.emit("", _translate("updater_bad_url"))
            return
        # 没有可信摘要的旧清单只允许 UI 打开人工下载页，绝不自动执行产物。
        if not self._expected_sha256:
            self.finished.emit("", _translate("updater_unverified"))
            return
        name = os.path.basename(QUrl(self._url).path()) or "Setup.exe"
        # 文件名插入 PID：多窗口同时下载各写各的文件、不会互相踩（清理仍按 CommTool_Setup_* 匹配）
        stem, ext = os.path.splitext(name)
        name = "%s_%d%s" % (stem, os.getpid(), ext)
        path = os.path.join(tempfile.gettempdir(), name)
        w = _DownloadWorker(
            self._url, path, self._expected_sha256, self._expected_size)
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
    if not _is_windows():
        return False
    try:
        # 不加 /SILENT —— 弹出正常安装向导，用户手动点「下一步/安装」。
        # CREATE_NEW_PROCESS_GROUP：让安装向导独立成组，不受本 app 退出影响。
        # getattr fallback also keeps this path safely testable on non-Windows
        # Python builds, where the Windows-only constant is absent.
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([path], creationflags=flags)
        return True
    except OSError:
        _log.debug("run_installer failed for %s", path, exc_info=True)
        return False


LINUX_INSTALL_WAIT_SEC = 60
# $1 = .run path, $2 = CommTool pid, $3 = max wait seconds.
# Do not use sleep-and-hope: wait until the old process is actually gone.
LINUX_INSTALLER_WAIT_SH = """
path="$1"
pid="$2"
wait_sec="$3"
i=0
while kill -0 "$pid" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -ge "$wait_sec" ]; then
    msg="CommTool (pid $pid) did not exit within ${wait_sec}s; update aborted."
    if command -v notify-send >/dev/null 2>&1; then
      notify-send "CommTool" "$msg" || true
    fi
    logger -t commtool-update "$msg" 2>/dev/null || true
    echo "$msg" >&2
    exit 1
  fi
  sleep 1
done
exec "$path"
"""


def run_linux_installer(path, pid=None, wait_sec=None):
    """Launch the downloaded .run after this process has actually exited.

    ``pid`` defaults to the current process. The waiter polls ``kill -0``
    until that pid is gone (or ``wait_sec`` elapses) before exec'ing the
    installer, so PREFIX is not overwritten while the old binary is still
    mapped.
    """
    if not _is_linux():
        return False
    try:
        os.chmod(path, 0o755)
        wait_sec = int(LINUX_INSTALL_WAIT_SEC if wait_sec is None else wait_sec)
        if wait_sec < 1:
            wait_sec = 1
        child_pid = int(os.getpid() if pid is None else pid)
        subprocess.Popen(
            ["bash", "-c", LINUX_INSTALLER_WAIT_SH, "commtool-update",
             path, str(child_pid), str(wait_sec)],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError:
        _log.debug("run_linux_installer failed for %s", path, exc_info=True)
        return False
