# -*- coding: utf-8 -*-
"""SEGGER RTT target pipe over a J-Link probe (pylink), matching SerialConn.

Open/scan/RTT I/O run on a dedicated worker thread so a slow DLL call can
never stall the UI. RTT bytes, connection state and errors are emitted on
the Qt thread that owns the QObject. pylink-square is a pure-Python ctypes
wrapper; the SEGGER J-Link driver package (JLinkARM DLL) is required at
runtime and discovered by pylink itself.

Connect semantics follow the reference RTT tools (J-Link RTT Viewer and
gitee bds123/rtt_t2): a successful ``rtt_start`` already means "the probe
is talking to the target", so the link goes up right there. The RTT
control block may only show up later (the DLL scans target RAM, and the
firmware may not have reached ``SEGGER_RTT_Init`` yet) — that is a
*waiting* state that raises a one-shot notice, never a failed connect and
never a drop.

Error contract: ``error_occurred`` carries either a stable ``rtt:*`` token
(see ERROR_I18N) or the raw probe error text — the raw text flows into the
generic ``err_connect_failed {e}`` toast in main_window. ``notice_occurred``
carries a ``rtt:*`` token from NOTICE_I18N and is informational only.
"""
from __future__ import annotations

import glob
import logging
import os
import struct
import sys
import threading
import time

from PyQt5.QtCore import QObject, pyqtSignal

_log = logging.getLogger(__name__)

# JLinkARM carries process-global state. Keep one RTT worker in the DLL at a
# time, including the interval after close() timed out while a DLL call remains
# blocked. The worker releases this claim only from its own finally block.
_ACTIVE_WORKER_LOCK = threading.Lock()
_ACTIVE_WORKER = None
# JLinkARM 内部状态是进程级的；器件/探针枚举与实际 RTT 收发也不能并发
# 进入同一份 DLL。RLock 允许目录线程在持锁期间调用 list_devices/probes。
_JLINK_DLL_LOCK = threading.RLock()
# “自动”探针模式记住最近一次真正连通的 J-Link。RttConn 每次连接都会新建，
# 所以缓存必须放在模块级，才能复现参考 rtt_t2 跨连接优先重试原探针的语义。
_LAST_SUCCESSFUL_PROBE_LOCK = threading.Lock()
_LAST_SUCCESSFUL_PROBE = ""


def _claim_worker(thread):
    global _ACTIVE_WORKER
    with _ACTIVE_WORKER_LOCK:
        if _ACTIVE_WORKER is not None:
            return False
        _ACTIVE_WORKER = thread
        return True


def _release_worker(thread):
    global _ACTIVE_WORKER
    with _ACTIVE_WORKER_LOCK:
        if _ACTIVE_WORKER is thread:
            _ACTIVE_WORKER = None


def _last_successful_probe():
    with _LAST_SUCCESSFUL_PROBE_LOCK:
        return _LAST_SUCCESSFUL_PROBE


def _remember_successful_probe(jlink):
    """缓存当前 J-Link 的实际序列号；老 pylink / 测试替身无此属性就跳过。"""
    global _LAST_SUCCESSFUL_PROBE
    try:
        value = getattr(jlink, "serial_number", "")
        if callable(value):
            value = value()
        value = normalize_probe(value)
    except Exception:
        return
    if value:
        with _LAST_SUCCESSFUL_PROBE_LOCK:
            _LAST_SUCCESSFUL_PROBE = value


def _clear_probe_history():
    """清掉自动探针历史（供隔离测试及进程内完整状态重置使用）。"""
    global _LAST_SUCCESSFUL_PROBE
    with _LAST_SUCCESSFUL_PROBE_LOCK:
        _LAST_SUCCESSFUL_PROBE = ""

ERR_NO_PYLINK = "rtt:no-pylink"     # pylink-square 未安装
ERR_NO_JLINK = "rtt:no-jlink"       # SEGGER J-Link 驱动 (DLL) 未安装
ERR_NO_PROBE = "rtt:no-probe"       # 调试器没插 / 被其它程序占用
ERR_BAD_DEVICE = "rtt:bad-device"   # 器件名 J-Link 不认识
ERR_NO_TARGET = "rtt:no-target"     # 调试器在，但目标没上电 / 接口不通 / 核选错
ERR_BAD_SPEED = "rtt:bad-speed"     # 速率被 DLL 拒绝（越界）
ERR_NO_RTT = "rtt:no-rtt"           # RTT 控制块没找到
ERR_GONE = "rtt:gone"               # 运行中调试器 / 目标掉线
ERR_NO_DEVICE = "rtt:no-device"     # 未填器件名
ERR_TIMEOUT = "rtt:timeout"         # 打开阶段长时间无响应（调试器被占用/目标无应答）
ERR_BUSY = "rtt:busy"               # 上一个连接还在收尾（JLinkARM 是进程级单例）
ERR_CONNECT = "rtt:connect"         # 其它连接失败（原文走 {e}）

ERROR_I18N = {
    ERR_NO_PYLINK: "rtt_err_no_pylink",
    ERR_NO_JLINK: "rtt_err_no_jlink",
    ERR_NO_PROBE: "rtt_err_no_probe",
    ERR_BAD_DEVICE: "rtt_err_bad_device",
    ERR_NO_TARGET: "rtt_err_no_target",
    ERR_BAD_SPEED: "rtt_err_bad_speed",
    ERR_NO_RTT: "rtt_err_no_rtt",
    ERR_GONE: "rtt_err_gone",
    ERR_NO_DEVICE: "rtt_err_no_device",
    ERR_TIMEOUT: "rtt_err_timeout",
    ERR_BUSY: "rtt_err_busy",
    # ERR_CONNECT 不映射：原文由主窗口 err_connect_failed {e} 展示
}

NOTICE_WAIT_CB = "rtt:waiting-cb"   # 已连上目标，控制块还没出现（继续等，不断线）

NOTICE_I18N = {
    NOTICE_WAIT_CB: "rtt_notice_waiting_cb",
}

INTERFACES = ("SWD", "JTAG")
_INTERFACE_SET = frozenset(INTERFACES)
DEFAULT_INTERFACE = "SWD"
DEFAULT_SPEED_KHZ = 4000
# 与 pylink 的 JLink.MIN_JTAG_SPEED / MAX_JTAG_SPEED 对齐：越界会被 DLL 侧
# 抛 ValueError，本地先拦住才能给中文提示而不是透传英文。
MIN_SPEED_KHZ = 5
MAX_SPEED_KHZ = 50000
MAX_CHANNEL = 15
DEFAULT_CHANNEL = 0

# J-Link 的接口速率是 48000 kHz 的整数分频，只有这些离散档位真正生效
# （48000/80=600、/64=750、/48=1000、/36=1334、/12=4000 …），与 J-Link
# RTT Viewer 的速率下拉同一组。下拉可编辑，手填任意 5~50000 仍然接受。
SPEED_PRESETS_KHZ = (
    5, 10, 20, 30, 50, 100, 200, 300, 400, 500,
    600, 750, 900, 1000, 1200, 1334, 1600, 2000, 2667, 3200,
    4000, 4800, 6000, 8000, 12000, 15000, 20000, 25000, 30000,
    40000, 50000,
)

RTT_HINT_S = 10.0           # 连上后一直没见控制块多久提示一次（只提示一次）
POLL_IDLE_S = 0.02
READ_BURST = 16
READ_CHUNK = 8192
WRITE_CHUNK = 512           # 下行缓冲目标侧常见 16~1024，交给 DLL 分批落
MAX_QUEUED_BYTES = 256 * 1024
JOIN_TIMEOUT_S = 3.0
# 运行期读失败宽限：DLL 忙 / 目标复位的瞬间会抛「未知」错误，参考实现直接
# 吞掉继续读。只有持续这么久都读不动才判定掉线。
READ_FAIL_GRACE_S = 5.0
RESET_MS = 10               # reset(ms=, halt=False)：与 rtt_t2 一致
# JLinkARM 在这些情况下会自己弹 GUI 窗（器件名不认识的选择框、固件升级
# 询问、下载信息窗）。弹窗顶在后台无人点，worker 就一直卡在那次 DLL 调用
# 里，表现成「连接中」直到看门狗超时。开连接后立刻关掉它们。
SILENT_COMMANDS = (
    "SilentUpdateFW",           # 固件升级不询问
    "SuppressInfoUpdateFW",     # 升级完不弹信息窗
    "HideDeviceSelection",      # 器件名不认识时不弹选择框（改为报错返回）
    "SuppressControlPanel",     # 不起控制面板窗
    "DisableInfoWinFlashDL",    # 下载信息窗
)
# 打开看门狗：DLL 在「调试器被占用 / 目标无应答」时可能阻塞几十秒甚至永远
# （USB 重试、共享协商、固件升级询问），没有它用户只会看到无声的「连接中」。
CONNECT_TIMEOUT_S = 20.0

# 控制块字符串搜索（地址栏用「起点+范围」写法时）
RTT_MAGIC = b"SEGGER RTT"
SEARCH_CHUNK_BYTES = 4096
MIN_SEARCH_BYTES = 16
MAX_SEARCH_BYTES = 4 * 1024 * 1024

# 器件名下拉的兜底候选。装了 J-Link 驱动时 list_supported_devices() 会从
# DLL 里取到完整器件表（数千项，与 J-Link RTT Viewer 的选择框同源），
# 这张表只在取不到时用。
COMMON_DEVICES = (
    "Cortex-M0", "Cortex-M3", "Cortex-M4", "Cortex-M7",
    "Cortex-M23", "Cortex-M33", "Cortex-M55",
    "nRF52840_xxAA", "nRF5340_xxAA_APP",
    "STM32F103C8", "STM32F407VG", "STM32H743VI", "STM32L432KC",
    "GD32F303CC", "AT32F403ACGT7",
)

PROBE_AUTO = ""             # 调试器序列号：空 = 自动选第一个

# J-Link 驱动（JLinkARM DLL）发现。pylink 自带的 find_library_windows()
# 把根目录写死成 "C:\\"，只扫 C:\Program Files*\SEGGER\JLink*；装到 D 盘
# （或任何别的盘）就永远找不到，表现是「未检测到 J-Link 驱动」+ 器件表
# 退回内置候选。这里自己按 提示路径 → 环境变量 → 注册表 → 全盘 的顺序找。
JLINK_ENV_VARS = ("JLINK_PATH", "SEGGER_JLINK_PATH", "JLINK_HOME")
_NIX_JLINK_GLOBS = (
    "/opt/SEGGER/JLink*", "/usr/lib/JLink*",
    "/Applications/SEGGER/JLink*",
)
_dll_hint = ""              # UI 里手动指定的驱动目录 / DLL 路径


def _parse_uint(text):
    s = str(text or "").strip()
    if not s or s.startswith("-"):
        return None
    try:
        val = int(s, 0)
    except ValueError:
        return None
    return val if val >= 0 else None


def parse_address_spec(text):
    """地址栏文本 -> ``(start, size)``；非法 -> None。

    四种写法（size == 0 表示「不搜索」）::

        ""  / "AUTO"                -> (0, 0)           DLL 自动搜索
        "0x20000000"                -> (0x20000000, 0)  控制块精确地址
        "0x20000000+0x40000"        -> (0x20000000, 0x40000)
        "0x20000000..0x20040000"    -> (0x20000000, 0x40000)
        "0x20000000 0x40000"        -> (0x20000000, 0x40000)

    带范围的写法是为了对齐 rtt_t2 等工具的习惯：那里填的地址是 RAM 搜索
    起点而不是控制块本身，直接当精确地址喂给 ``rtt_start`` 必然找不到。
    """
    if text is None:
        return (0, 0)
    s = str(text).strip()
    if not s or s.upper() == "AUTO":
        return (0, 0)
    sep = None
    for cand in ("..", "+"):
        if cand in s:
            sep = cand
            break
    if sep is None and " " in s:
        sep = " "
    if sep is None:
        val = _parse_uint(s)
        return None if val is None else (val, 0)
    head, _, tail = s.partition(sep)
    start = _parse_uint(head)
    second = _parse_uint(tail)
    if start is None or second is None:
        return None
    if sep == "..":
        if second <= start:
            return None
        size = second - start
    else:
        size = second
    if size <= 0:
        return None
    if start % 4 or size < MIN_SEARCH_BYTES:
        return None
    return (start, min(size, MAX_SEARCH_BYTES))


def parse_address(text):
    """RTT 控制块地址文本 -> 非负 int；空/AUTO -> 0(自动)；非法 -> None。

    接受 0x 十六进制与十进制（``int(s, 0)`` 语义）。「起点+范围」写法只取
    起点，完整解析见 :func:`parse_address_spec`。
    """
    spec = parse_address_spec(text)
    return None if spec is None else spec[0]


def parse_search_size(text):
    """地址栏文本 -> 搜索范围字节数（0 = 不搜索）；非法 -> None。"""
    spec = parse_address_spec(text)
    return None if spec is None else spec[1]


def strip_speed_unit(text):
    """去掉速率文本的单位后缀：``"4000 kHz"`` / ``"4000k"`` -> ``"4000"``。

    下拉项带着单位显示（标签列窄，"速率 (kHz)" 放不下），取值时得剥掉；
    顺带也认用户手打的 "4000kHz"。认不出的原样返回，交给校验去报错。
    """
    s = str(text or "").strip()
    low = s.lower()
    for suffix in ("khz", "k hz", "hz", "k"):
        if low.endswith(suffix):
            s = s[:len(s) - len(suffix)].strip()
            break
    return s


def parse_speed(text, default=DEFAULT_SPEED_KHZ):
    """速率文本 -> kHz int (5..50000)；空串 -> default；非法/越界 -> None。"""
    if text is None or strip_speed_unit(text) == "":
        return int(default)
    try:
        val = int(strip_speed_unit(text))
    except (TypeError, ValueError):
        return None
    return val if MIN_SPEED_KHZ <= val <= MAX_SPEED_KHZ else None


def format_speed(value):
    """kHz int -> 下拉里显示的带单位文本。"""
    return "%d kHz" % int(value)


def clamp_speed(value):
    """构造期兜底：任何输入都收敛成合法 kHz int。"""
    try:
        val = int(strip_speed_unit(value) if isinstance(value, str) else value)
    except (TypeError, ValueError):
        return DEFAULT_SPEED_KHZ
    return min(MAX_SPEED_KHZ, max(MIN_SPEED_KHZ, val))


def normalize_channel(value):
    """RTT 通道号 -> 0..15 int；非法 -> None。"""
    try:
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return DEFAULT_CHANNEL
            val = int(s, 0)
        else:
            val = int(value)
    except (TypeError, ValueError):
        return None
    return val if 0 <= val <= MAX_CHANNEL else None


def normalize_interface(text):
    text = str(text or "").strip().upper()
    return text if text in _INTERFACE_SET else DEFAULT_INTERFACE


def normalize_probe(value):
    """调试器序列号 -> 字符串（空 = 自动选第一个）。"""
    s = str(value or "").strip()
    if not s or s.upper() in ("AUTO", "-"):
        return PROBE_AUTO
    return s


def split_write(data, chunk=WRITE_CHUNK):
    """下行数据按 chunk 切块（空 -> []）。"""
    size = chunk if isinstance(chunk, int) and chunk > 0 else WRITE_CHUNK
    raw = bytes(data or b"")
    if not raw:
        return []
    return [raw[i:i + size] for i in range(0, len(raw), size)]


def _contains(low, *subs):
    return any(s in low for s in subs)


def classify_error(text):
    """Raw probe/exception text -> ``rtt:*`` token，未知 -> ""(原文透传)。

    ``rtt:*`` 开头的输入原样返回：内部哨兵不经过字符串猜测。匹配表覆盖
    pylink 自己抛的文案（``errors.JLinkException`` 把 DLL 错误码翻成
    ``enums.JLinkGlobalErrors.to_string`` 的固定英文句）与 DLL 直出的常见
    提示 —— 漏一条用户就会看到一句生英文。
    """
    s = str(text or "").strip()
    if s.startswith("rtt:"):
        return s
    low = s.lower()
    # 缺 DLL：pylink 构造期 TypeError('Expected to be given a valid DLL.')
    if _contains(low, "unable to load", "jlinkarm", ".dll", "valid dll",
                 "could not load", "load library", "dll has not been opened"):
        return ERR_NO_JLINK
    # 调试器不在 / 被占用：'No connection to emulator.'、'Emulator connection error.'
    if _contains(low, "no emulator", "no j-link", "emulator not found",
                 "cannot connect to j-link", "failed to open j-link",
                 "j-link is busy", "already in use", "emulator is busy",
                 "no connection to emulator", "emulator connection error",
                 "no device found", "usb communication"):
        return ERR_NO_PROBE
    # 器件名不认识：pylink get_device_index -> 'Unsupported device selected.'
    if _contains(low, "unknown device", "does not match any",
                 "unknown target", "device name", "unsupported device",
                 "user did not specify core", "no target device selected"):
        return ERR_BAD_DEVICE
    # 速率越界：set_speed -> ValueError('Given speed exceeds…/is too slow…')
    if _contains(low, "given speed", "speed is invalid"):
        return ERR_BAD_SPEED
    # 控制块还没出现：JLinkRTTException(-2) ->
    # 'The RTT Control Block has not yet been found (wait?)'
    if _contains(low, "control block", "no rtt", "rtt not"):
        return ERR_NO_RTT
    # 目标侧不通：没上电 / 接口选错 / 核睡死
    if _contains(low, "no power", "supported cpu", "target interface error",
                 "target is not connected", "low power mode",
                 "cannot connect to target", "could not connect to target",
                 "no cpu found", "tif status"):
        return ERR_NO_TARGET
    return ""


# 运行期读到这些 = 链路真断了，立刻收尾；其余（含控制块未找到）继续等。
FATAL_READ_TOKENS = frozenset((ERR_NO_PROBE, ERR_NO_JLINK, ERR_NO_TARGET,
                               ERR_GONE, ERR_NO_PYLINK))


def set_dll_hint(path):
    """记下用户手动指定的 J-Link 驱动目录（或 DLL 文件），空串 = 清除。"""
    global _dll_hint
    _dll_hint = str(path or "").strip()
    return _dll_hint


def get_dll_hint():
    return _dll_hint


def windows_dll_name(pylink_mod=None):
    """当前解释器位数对应的 DLL 名（64 位 JLink_x64.dll / 32 位 JLinkARM.dll）。"""
    lib = getattr(pylink_mod, "Library", None) if pylink_mod is not None else None
    fn = getattr(lib, "get_appropriate_windows_sdk_name", None)
    if callable(fn):
        try:
            return str(fn()) + ".dll"
        except Exception:
            _log.debug("rtt: pylink sdk name lookup failed", exc_info=True)
    return ("JLink_x64.dll" if struct.calcsize("P") == 8 else "JLinkARM.dll")


def _dll_in_dir(directory, names):
    for name in names:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None


def _registry_jlink_dirs():
    """SEGGER 安装时写的注册表项（装在哪个盘都记得住）。"""
    if not sys.platform.startswith("win"):
        return []
    try:
        import winreg
    except ImportError:
        return []
    out = []
    roots = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
    keys = (r"SOFTWARE\SEGGER\J-Link", r"SOFTWARE\WOW6432Node\SEGGER\J-Link")
    for root in roots:
        for key in keys:
            try:
                with winreg.OpenKey(root, key) as handle:
                    value, _ = winreg.QueryValueEx(handle, "InstallPath")
            except OSError:
                continue
            value = str(value or "").strip()
            if value:
                out.append(value)
    return out


def _scan_roots_under(drive):
    r"""一个盘符下的 SEGGER JLink* 目录。

    官方安装器落在 <盘>:\Program Files*\SEGGER\JLink*；绿色版 / 手动解压
    常见在 <盘>:\SEGGER\JLink* 或 <盘>:\Tools\SEGGER\JLink*，这类没有
    注册表项，只能靠扫。
    """
    roots = [os.path.join(drive, "SEGGER"),
             os.path.join(drive, "Tools", "SEGGER")]
    roots.extend(os.path.join(prog, "SEGGER")
                 for prog in glob.glob(os.path.join(drive, "Program Files*")))
    found = []
    for seg in roots:
        if os.path.isdir(seg):
            found.extend(glob.glob(os.path.join(seg, "JLink*")))
    return [d for d in found if os.path.isdir(d)]


def _scan_jlink_dirs():
    """所有盘符 / 平台默认位置下的 SEGGER JLink* 安装目录，新版本在前。"""
    found = []
    if sys.platform.startswith("win"):
        drives = ["%s:\\" % chr(c) for c in range(ord("A"), ord("Z") + 1)]
        for drive in drives:
            if os.path.isdir(drive):
                found.extend(_scan_roots_under(drive))
    else:
        for pattern in _NIX_JLINK_GLOBS:
            found.extend(glob.glob(pattern))
    dirs = [d for d in found if os.path.isdir(d)]
    # JLink_V926 > JLink_V794 > JLink：名字降序即版本降序（同前缀等长数字）
    dirs.sort(key=lambda d: os.path.basename(d), reverse=True)
    return dirs


def find_jlink_dll(hint=None, pylink_mod=None):
    """返回可用的 JLinkARM DLL 绝对路径；找不到 -> None（交给 pylink 自己找）。"""
    names = [windows_dll_name(pylink_mod)]
    if sys.platform.startswith("win"):
        for extra in ("JLink_x64.dll", "JLinkARM.dll"):
            if extra not in names:
                names.append(extra)
    else:
        names = ["libjlinkarm.so", "libjlinkarm.dylib"]
    candidates = []
    for raw in (hint, _dll_hint) + tuple(os.environ.get(v) for v in JLINK_ENV_VARS):
        raw = str(raw or "").strip().strip('"')
        if not raw:
            continue
        if os.path.isfile(raw):
            return raw
        if os.path.isdir(raw):
            candidates.append(raw)
    candidates.extend(_registry_jlink_dirs())
    candidates.extend(_scan_jlink_dirs())
    seen = set()
    for directory in candidates:
        key = os.path.normcase(os.path.abspath(directory))
        if key in seen:
            continue
        seen.add(key)
        path = _dll_in_dir(directory, names)
        if path:
            return path
    return None


def dll_in_directory(path, pylink_mod=None):
    """这个目录（或 DLL 文件）本身是否就是一个可用的 J-Link 驱动。

    与 find_jlink_dll 不同：**不做兜底搜索**。用户手动指了个目录，就得能
    如实回答「这里没有」，否则会被全盘扫到的另一份驱动掩盖掉。
    """
    raw = str(path or "").strip().strip('"')
    if not raw:
        return None
    if os.path.isfile(raw):
        return raw
    if not os.path.isdir(raw):
        return None
    names = [windows_dll_name(pylink_mod)]
    if sys.platform.startswith("win"):
        for extra in ("JLink_x64.dll", "JLinkARM.dll"):
            if extra not in names:
                names.append(extra)
    else:
        names = ["libjlinkarm.so", "libjlinkarm.dylib"]
    return _dll_in_dir(raw, names)


def _shared_library(mod, path):
    """按 DLL 路径复用 pylink.Library（见 _LIBRARY_CACHE 上的说明）。"""
    key = os.path.normcase(os.path.abspath(path)) if path else ""
    with _LIBRARY_LOCK:
        lib = _LIBRARY_CACHE.get(key)
        if lib is None:
            lib = mod.Library(dllpath=path) if path else mod.Library()
            _LIBRARY_CACHE[key] = lib
        return lib


def make_jlink(pylink_mod=None, hint=None):
    """建一个 pylink.JLink，优先用我们找到的 DLL（pylink 自己找不到 C 盘外的）。"""
    mod = pylink_mod if pylink_mod is not None else _import_pylink()
    path = find_jlink_dll(hint=hint, pylink_mod=mod)
    if path:
        try:
            return mod.JLink(lib=_shared_library(mod, path))
        except Exception:
            _log.debug("rtt: loading J-Link DLL %s failed", path, exc_info=True)
    return mod.JLink()


def _import_pylink():
    try:
        import pylink
    except ImportError as exc:
        raise RuntimeError(ERR_NO_PYLINK) from exc
    return pylink


def resolve_interface(pylink_mod, name):
    """UI 文本 -> pylink 枚举值；枚举不可用时退回原始字符串。"""
    want = normalize_interface(name)
    enums = getattr(pylink_mod, "enums", None)
    table = getattr(enums, "JLinkInterfaces", None) if enums is not None else None
    val = getattr(table, want, None) if table is not None else None
    return want if val is None else val


# ---- 器件 / 调试器发现（下拉框用；都不需要插着调试器） ----

_DEVICE_CACHE = None
_DISCOVERY_LOCK = threading.Lock()
# 每个 DLL 路径只建一个 pylink.Library 并一直留着。
# pylink.Library 在析构时 FreeLibrary(JLinkARM)，而 JLinkARM 自带全局状态和
# 后台线程；反复 Load/FreeLibrary 同一份 DLL 会在退出时段错误（实测：只要
# 进程里真的加载得到驱动，多次建 Library 的测试进程必崩）。JLinkARM 本来就
# 是进程级单例，共享一份才是它期望的用法，顺带省掉每次几十 MB 的加载开销。
_LIBRARY_CACHE = {}
_LIBRARY_LOCK = threading.Lock()


def _new_jlink(pylink_mod=None):
    return make_jlink(pylink_mod)


def _internal_flash_size(info):
    """片内 Flash 字节数。

    ``FlashSize`` 是所有 flash 区之和，**外扩 QSPI/OSPI 也算在内** —— 拿它
    当片内容量会离谱（STM32H743VI 会报 258MB、nRF52840 报 65MB）。改成从
    第一块起累加地址连续的区：H743 的 0x08000000+0x08100000 合出 2MB，
    后面 0x90000000 的外部区自然断开。
    """
    try:
        areas = sorted((int(a.Addr), int(a.Size))
                       for a in info.aFlashArea if int(a.Size) > 0)
    except Exception:
        _log.debug("rtt: flash areas unreadable", exc_info=True)
        return 0
    if not areas:
        return 0
    total = areas[0][1]
    end = areas[0][0] + areas[0][1]
    for addr, size in areas[1:]:
        if addr != end:
            break
        total += size
        end = addr + size
    return total


def _device_row(info):
    """JLinkDeviceInfo -> 选择对话框用的一行（取不到的字段留空/0）。"""
    def _get(attr, default=""):
        try:
            value = getattr(info, attr)
        except Exception:
            return default
        return default if value is None else value

    return {
        "name": str(_get("name") or "").strip(),
        "manufacturer": str(_get("manufacturer") or "").strip(),
        "core_id": int(_get("Core", 0) or 0),
        "core": "",
        "flash": _internal_flash_size(info),
        "ram": int(_get("RAMSize", 0) or 0),
    }


def _pretty_core(attr):
    if attr.startswith("CORTEX_"):
        return "Cortex-" + attr[len("CORTEX_"):].replace("_", "-")
    return attr.replace("_", "-")


def _pylink_core_names(pylink_mod=None):
    """pylink 的 JLinkCore 枚举 -> {core_id: 名字}，用于驱动表没给通用条目的
    老内核（ARM7TDMI-S / ARM926EJ-S / RX610 …）。"""
    try:
        mod = pylink_mod if pylink_mod is not None else _import_pylink()
        table = mod.enums.JLinkCore
    except Exception:
        _log.debug("rtt: JLinkCore enum unavailable", exc_info=True)
        return {}
    out = {}
    for attr in dir(table):
        if attr.startswith("_") or attr in ("NONE", "ANY"):
            continue
        value = getattr(table, attr, None)
        if isinstance(value, int) and value not in out:
            out[value] = _pretty_core(attr)
    return out


def _fill_core_names(rows, pylink_mod=None):
    """给每行填内核名。

    驱动的器件表里，每个 Core id 都带一条厂商为 Unspecified 的「通用内核」
    条目，它的器件名就是内核名（Cortex-M4 / Cortex-M23 / ARM7 …）——
    这正是 RTT Viewer 的 Core 列显示的东西，比按 id 猜准。取不到的退回
    十六进制 id。
    """
    generic = {}
    for row in rows:
        cid = row.get("core_id") or 0
        if not cid or cid in generic:
            continue
        if str(row.get("manufacturer") or "").strip().lower() in ("", "unspecified"):
            generic[cid] = row.get("name") or ""
    fallback = None
    for row in rows:
        cid = row.get("core_id") or 0
        name = generic.get(cid)
        if not name and cid:
            if fallback is None:
                fallback = _pylink_core_names(pylink_mod)
            name = fallback.get(cid) or ("%#010X" % cid)
        row["core"] = name or ""
    return rows


def clear_device_cache():
    """丢掉缓存的器件表（换了驱动路径后重新枚举）。"""
    global _DEVICE_CACHE
    with _DISCOVERY_LOCK:
        _DEVICE_CACHE = None


def list_devices(pylink_mod=None, refresh=False):
    """J-Link DLL 支持的全部器件（名称 / 厂商 / Flash / RAM），数千项。

    与 J-Link RTT Viewer 的 Target Device 选择框同一份数据。只要装了驱动
    就能取，**不需要插调试器**；取不到（没装驱动 / 老 DLL）时返回内置的
    COMMON_DEVICES 兜底。结果缓存，UI 在后台线程取一次即可。
    """
    global _DEVICE_CACHE
    if _DEVICE_CACHE is not None and not refresh:
        return _DEVICE_CACHE
    with _JLINK_DLL_LOCK:
        with _DISCOVERY_LOCK:
            if _DEVICE_CACHE is not None and not refresh:
                return _DEVICE_CACHE
            rows = []
            try:
                jlink = _new_jlink(pylink_mod)
                total = int(jlink.num_supported_devices() or 0)
                seen = set()
                for idx in range(total):
                    try:
                        row = _device_row(jlink.supported_device(idx))
                    except Exception:
                        continue
                    name = row["name"]
                    if name and name not in seen:
                        seen.add(name)
                        rows.append(row)
            except Exception:
                _log.debug("rtt device enumeration failed", exc_info=True)
                rows = []
            if not rows:
                rows = [{"name": n, "manufacturer": "", "core_id": 0,
                         "core": "", "flash": 0, "ram": 0}
                        for n in COMMON_DEVICES]
            _fill_core_names(rows, pylink_mod)
            _DEVICE_CACHE = rows
            return _DEVICE_CACHE


def list_supported_devices(pylink_mod=None, refresh=False):
    """器件名列表（下拉与补全用）。明细见 :func:`list_devices`。"""
    return [row["name"] for row in list_devices(pylink_mod, refresh=refresh)]


def list_probes(pylink_mod=None):
    """已插上的 J-Link 调试器序列号（字符串列表，可能为空）。"""
    with _JLINK_DLL_LOCK:
        out = []
        try:
            jlink = _new_jlink(pylink_mod)
            for info in jlink.connected_emulators() or ():
                sn = getattr(info, "SerialNumber", None)
                if sn:
                    out.append(str(sn))
        except Exception:
            _log.debug("rtt probe enumeration failed", exc_info=True)
        return out


def search_control_block(jlink, start, size, cancelled=None):
    """在 [start, start+size) 里找 "SEGGER RTT" 串，返回绝对地址或 None。

    对齐 rtt_t2 的 find_rtt_address：那里填的是 RAM 搜索起点。分块读且相邻
    块重叠 magic-1 字节，magic 跨块也能命中。
    """
    if not size or size <= 0:
        return None
    magic = RTT_MAGIC
    overlap = len(magic) - 1
    addr = int(start)
    end = addr + min(int(size), MAX_SEARCH_BYTES)
    tail = b""
    tail_addr = addr
    while addr < end:
        if cancelled is not None and cancelled():
            return None
        want = min(SEARCH_CHUNK_BYTES, end - addr)
        words = max(1, (want + 3) // 4)
        try:
            data = jlink.memory_read32(addr, words)
        except Exception:
            _log.debug("rtt block search read failed @%#x", addr, exc_info=True)
            return None
        chunk = b"".join(int(w & 0xFFFFFFFF).to_bytes(4, "little")
                         for w in (data or ()))[:want]
        if not chunk:
            return None
        hay = tail + chunk
        pos = hay.find(magic)
        if pos >= 0:
            return tail_addr + pos
        tail = hay[-overlap:] if overlap else b""
        tail_addr = addr + len(chunk) - len(tail)
        addr += len(chunk)
    return None


class RttCatalog(QObject):
    """后台枚举 J-Link 器件表 + 已插调试器（DLL 调用会花几百 ms 到数秒）。

    器件表来自 JLinkARM DLL 本身，和 J-Link RTT Viewer 的 Target Device
    选择框同一份数据；没装驱动时返回 COMMON_DEVICES 兜底，UI 照样能用。
    """

    ready = pyqtSignal(list, list)      # device rows, probes
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.driver_path = ""
        self._thread = None

    def start(self):
        if self.isRunning():
            return
        self._thread = threading.Thread(
            target=self._worker, name="CommToolRttCatalog", daemon=True)
        self._thread.start()

    def isRunning(self):
        return bool(self._thread is not None and self._thread.is_alive())

    def wait(self, msecs=-1):
        thread = self._thread
        if thread is None:
            return True
        timeout = None if msecs is None or int(msecs) < 0 else int(msecs) / 1000.0
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _worker(self):
        try:
            self.run()
        finally:
            try:
                self.finished.emit()
            except RuntimeError:
                pass

    def run(self):
        # 活跃 RTT 会话会独占 JLinkARM。目录线程在后台等它释放，不把“DLL
        # 正忙”误报成一次成功的兜底枚举；线程是 daemon，应用退出也不会被拖住。
        with _JLINK_DLL_LOCK:
            self.driver_path = find_jlink_dll() or ""
            try:
                devices = list(list_devices())
            except Exception:
                _log.debug("rtt catalog: device list failed", exc_info=True)
                devices = [{"name": n, "manufacturer": "", "core_id": 0,
                            "core": "", "flash": 0, "ram": 0}
                           for n in COMMON_DEVICES]
            try:
                probes = list(list_probes())
            except Exception:
                _log.debug("rtt catalog: probe list failed", exc_info=True)
                probes = []
            self.ready.emit(devices, probes)


class RttConn(QObject):
    """SEGGER RTT 连接：经 J-Link 读写目标 MCU 内存中的 RTT 缓冲。

    一个 worker 线程串行化全部 DLL 调用（连接、轮询读、下行写），与 Qt 侧
    只通过信号交互 —— 契约与 BleConn 一致，另加一个可选的
    ``notice_occurred``（非致命提示，主窗口只 toast，不断连）。
    """

    data_received = pyqtSignal(bytes)
    state_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    notice_occurred = pyqtSignal(str)
    control_block_found = pyqtSignal()

    # 测试注入点：jlink_factory() -> jlink-like；pylink_module -> 命名空间
    jlink_factory = None
    pylink_module = None

    def __init__(self, device, speed_khz=DEFAULT_SPEED_KHZ,
                 interface=DEFAULT_INTERFACE, rtt_address=0,
                 channel=DEFAULT_CHANNEL, parent=None,
                 serial_no=PROBE_AUTO, reset_on_open=False, search_size=0):
        super().__init__(parent)
        self._device = str(device or "").strip()
        self._speed = clamp_speed(speed_khz)
        self._interface = normalize_interface(interface)
        self._address = (rtt_address
                         if isinstance(rtt_address, int) and rtt_address > 0 else 0)
        self._search_size = (int(search_size)
                             if isinstance(search_size, int) and search_size > 0 else 0)
        self._serial_no = normalize_probe(serial_no)
        self._reset = bool(reset_on_open)
        ch = normalize_channel(channel)
        self._channel = DEFAULT_CHANNEL if ch is None else ch
        self._gen = 0
        self._ready = False
        self._was_open = False
        self._closing = False
        self._cb_seen = False
        self._thread = None
        self._watchdog = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending = []
        self._queued = 0

    @property
    def is_open(self):
        return bool(self._ready)

    @property
    def device(self):
        return self._device

    @property
    def channel(self):
        return self._channel

    @property
    def control_block_seen(self):
        """控制块是否命中过（连上但一直 False = 固件侧没有 RTT 输出）。"""
        return bool(self._cb_seen)

    @property
    def queued_bytes(self):
        with self._lock:
            return self._queued

    def open(self):
        thread = self._thread
        if thread is not None and thread.is_alive():
            if self._stop.is_set() or self._closing:
                # 上一轮还卡在某个 DLL 调用里没退出。JLinkARM 是进程级单例，
                # 再起一个 worker 就是两个线程同时进 DLL —— 宁可让用户重试。
                self.error_occurred.emit(ERR_BUSY)
                return False
            return True
        if not self._device:
            self.error_occurred.emit(ERR_NO_DEVICE)
            return False
        self._closing = False
        self._ready = False
        self._was_open = False
        self._cb_seen = False
        self._gen += 1
        self._stop.clear()
        with self._lock:
            self._pending.clear()
            self._queued = 0
        thread = threading.Thread(
            target=self._run, args=(self._gen,),
            name="CommToolRttLoop", daemon=True)
        if not _claim_worker(thread):
            self.error_occurred.emit(ERR_BUSY)
            return False
        self._thread = thread
        self._arm_watchdog(self._gen)
        try:
            thread.start()
        except Exception:
            self._disarm_watchdog()
            self._thread = None
            _release_worker(thread)
            raise
        return True

    def send(self, data, target=None):
        raw = bytes(data or b"")
        if not raw:
            return 0
        with self._lock:
            if not self._ready or self._closing:
                return 0
            if self._queued + len(raw) > MAX_QUEUED_BYTES:
                return 0
            self._pending.append(raw)
            self._queued += len(raw)
        return len(raw)

    def close(self):
        was_open = self._was_open
        self._was_open = False
        self._ready = False
        self._closing = True
        self._gen += 1
        self._stop.set()
        self._disarm_watchdog()
        with self._lock:
            self._pending.clear()
            self._queued = 0
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=JOIN_TIMEOUT_S)
        if thread is None or not thread.is_alive():
            # 线程真退出了才松手；还卡在 DLL 里就留着引用，让下一次 open()
            # 看得见并拒绝，而不是并发进同一个 JLinkARM。
            self._thread = None
        self._closing = False
        if was_open:
            self.state_changed.emit(False)

    # ---- watchdog ----

    def _arm_watchdog(self, gen):
        """打开阶段看门狗：CONNECT_TIMEOUT_S 内未就绪就报超时。

        DLL 卡死时无法中断当次调用，只能先把失败亮出来；worker 等卡住的
        调用返回后经 _cancelled(gen) 静默退出并自行清理。
        """
        self._disarm_watchdog()
        timer = threading.Timer(
            CONNECT_TIMEOUT_S, self._on_open_timeout, args=(gen,))
        timer.daemon = True
        timer.start()
        self._watchdog = timer

    def _disarm_watchdog(self):
        timer = self._watchdog
        self._watchdog = None
        if timer is not None:
            timer.cancel()

    def _on_open_timeout(self, gen):
        with self._lock:
            if gen != self._gen or self._ready or self._was_open or self._closing:
                return
            self._stop.set()
            self._ready = False
        self._disarm_watchdog()
        self.error_occurred.emit(ERR_TIMEOUT)
        self.state_changed.emit(False)

    # ---- worker thread ----

    def _cancelled(self, gen):
        return bool(gen != self._gen or self._closing or self._stop.is_set())

    def _run(self, gen):
        jlink = None
        ready = False
        dll_locked = False
        try:
            _JLINK_DLL_LOCK.acquire()
            dll_locked = True
            if self._cancelled(gen):
                return
            pylink_mod = self.pylink_module
            if pylink_mod is None:
                pylink_mod = _import_pylink()
            factory = self.jlink_factory
            jlink = factory() if factory is not None else make_jlink(pylink_mod)
            self._require_probe(jlink)
            self._open_probe(jlink, pylink_mod)
            self._silence_dll_dialogs(jlink)
            jlink.set_tif(resolve_interface(pylink_mod, self._interface))
            jlink.connect(self._device, speed=self._speed, verbose=False)
            self._maybe_reset(jlink)
            self._confirm_target(jlink)
            block = self._resolve_block(jlink, gen)
            self._flush_swo(jlink)
            jlink.rtt_start(block or None)
            _remember_successful_probe(jlink)
            # 到这里 J-Link 已经在跟目标说话了 —— 与 rtt_t2 / RTT Viewer 一致，
            # 链路立刻算通。控制块可能还要几秒、甚至要等固件跑到 RTT_Init，
            # 那是 _pump 里的等待状态，不是连接失败。
            ready = True
            # 与看门狗互斥：谁先拿到锁谁定胜负，避免「已连上又报超时」
            with self._lock:
                if self._stop.is_set() or self._closing or gen != self._gen:
                    return
                self._ready = True
            self._was_open = True
            self._disarm_watchdog()
            self.state_changed.emit(True)
            self._pump(jlink, gen)
        except Exception as exc:
            if self._cancelled(gen):
                return
            self._ready = False
            if ready:
                # 会话中断线：与 BLE 相同的 error → state(False) 次序，
                # 主窗口先按错误收尾，随后的 state(False) 因 conn 已空被忽略。
                self._was_open = False
                self.error_occurred.emit(ERR_GONE)
                self.state_changed.emit(False)
                return
            token = classify_error(exc)
            self.error_occurred.emit(token or str(exc))
        finally:
            self._ready = False
            with self._lock:
                self._pending.clear()
                self._queued = 0
            if jlink is not None:
                for fn in ("rtt_stop", "close"):
                    try:
                        getattr(jlink, fn)()
                    except Exception:
                        _log.debug("rtt %s cleanup failed", fn, exc_info=True)
            if dll_locked:
                _JLINK_DLL_LOCK.release()
            _release_worker(threading.current_thread())

    def _require_probe(self, jlink):
        """没插调试器就立刻失败，别进 open()。

        JLINKARM_Open 在找不到调试器时会重试 USB / 弹选择窗，一卡就是几十秒
        （用户看到的是「连接中」耗满看门狗）。枚举不需要 open，几毫秒就回。
        """
        counter = getattr(jlink, "num_connected_emulators", None)
        if not callable(counter):
            return          # 注入的假 jlink / 老 pylink：跳过这层预检
        try:
            count = int(counter() or 0)
        except Exception:
            return          # 数不出来就照常往下走，让 open() 自己报
        if count <= 0:
            raise RuntimeError(ERR_NO_PROBE)

    def _open_probe(self, jlink, pylink_mod):
        """打开探针，并在自动模式优先重试最近一次成功使用的序列号。

        显式指定序列号时严格只开指定探针，失败也不换；只有“自动”模式会在
        历史探针已拔出/占用时退回 ``open()``，交给 J-Link 选当前默认探针。
        这与参考 rtt_t2 的 ``last_successful_sn`` 行为一致。
        """
        if self._serial_no:
            jlink.open(serial_no=self._serial_no)
            return
        previous = _last_successful_probe()
        if previous:
            try:
                jlink.open(serial_no=previous)
                return
            except Exception as exc:
                errors = getattr(pylink_mod, "errors", None)
                retry_error = getattr(errors, "JLinkException", None)
                if retry_error is None or not isinstance(exc, retry_error):
                    raise
                _log.info("rtt previous probe %s unavailable; retry auto", previous)
        jlink.open()

    def _silence_dll_dialogs(self, jlink):
        """关掉 JLinkARM 自己的弹窗，免得后台 worker 卡在无人应答的对话框上。"""
        exec_command = getattr(jlink, "exec_command", None)
        if not callable(exec_command):
            return
        for cmd in SILENT_COMMANDS:
            try:
                exec_command(cmd)
            except Exception:
                _log.debug("rtt exec_command %s failed", cmd, exc_info=True)

    def _maybe_reset(self, jlink):
        """可选的连接时复位（rtt_t2 默认开）：目标停在 halt 时才需要。"""
        if not self._reset:
            return
        reset = getattr(jlink, "reset", None)
        if reset is None:
            return
        try:
            reset(ms=RESET_MS, halt=False)
        except Exception:
            _log.debug("rtt reset on open failed", exc_info=True)

    def _confirm_target(self, jlink):
        """rtt_start 前再确认目标在线（与 rtt_t2 的 connected() 兜底一致）。

        connect() 正常会在失败时抛异常，但目标在 connect 之后瞬间掉线
        （复位脚、供电抖动）时它可能已返回；这里主动核一次，早点报
        rtt:no-target 而不是让 rtt_start 抛一句难懂的原文。API 缺失或
        探测本身出错就跳过，交给 rtt_start 去暴露。
        """
        check = getattr(jlink, "target_connected", None)
        if not callable(check):
            check = getattr(jlink, "connected", None)
        if not callable(check):
            return
        try:
            online = bool(check())
        except Exception:
            return
        if not online:
            raise RuntimeError(ERR_NO_TARGET)

    def _flush_swo(self, jlink):
        """rtt_start 前刷一次 SWO 缓冲（与 rtt_t2 一致）：清掉混用 SWO 的
        固件残留在 DLL 缓冲里的脏字节。没有该 API 或失败都无所谓。"""
        flush = getattr(jlink, "swo_flush", None)
        if not callable(flush):
            return
        try:
            flush()
        except Exception:
            _log.debug("rtt swo_flush failed", exc_info=True)

    def _resolve_block(self, jlink, gen):
        """地址栏 -> 传给 rtt_start 的控制块地址（0 = 让 DLL 自动搜）。"""
        if self._search_size <= 0:
            return self._address
        found = search_control_block(
            jlink, self._address, self._search_size,
            cancelled=lambda: self._cancelled(gen))
        if found:
            _log.info("rtt control block found at %#x", found)
            return found
        # 搜不到不算失败：退回 DLL 自动搜索，与只填起点的工具行为一致。
        _log.info("rtt block search missed in [%#x, +%#x), fall back to auto",
                  self._address, self._search_size)
        return 0

    def _pump(self, jlink, gen):
        """读-发主循环：有数据连读排空，空闲按 POLL_IDLE_S 节流。

        读失败分三档：控制块还没出现 = 正常等待；FATAL_READ_TOKENS = 立刻
        断线；其余未知错误给 READ_FAIL_GRACE_S 的宽限（DLL 忙、目标复位的
        瞬间会抛，参考实现直接吞掉继续读）。
        """
        fail_since = None
        hint_at = time.monotonic() + RTT_HINT_S
        hinted = False
        while not self._cancelled(gen):
            got = False
            for _ in range(READ_BURST):
                try:
                    raw = bytes(jlink.rtt_read(self._channel, READ_CHUNK) or b"")
                except Exception as exc:
                    token = classify_error(exc)
                    if token in FATAL_READ_TOKENS:
                        raise
                    if token == ERR_NO_RTT:
                        fail_since = None       # 等控制块是正常状态
                    else:
                        now = time.monotonic()
                        if fail_since is None:
                            fail_since = now
                        elif now - fail_since >= READ_FAIL_GRACE_S:
                            raise
                        _log.debug("rtt transient read error: %s", exc)
                    break
                fail_since = None
                # rtt_read 没抛“控制块未找到”就说明 CB 已可访问；即使目标
                # 当前没有待收字节，也应立即结束“等待控制块”状态。
                if not self._cb_seen:
                    self._cb_seen = True
                    self.control_block_found.emit()
                if not raw:
                    break
                got = True
                self.data_received.emit(raw)
            self._drain_tx(jlink)
            if not got:
                if not (self._cb_seen or hinted) and time.monotonic() >= hint_at:
                    hinted = True
                    self.notice_occurred.emit(NOTICE_WAIT_CB)
                self._stop.wait(POLL_IDLE_S)

    def _drain_tx(self, jlink):
        while True:
            with self._lock:
                if not self._pending or not self._ready:
                    return
                pkt = self._pending[0]
            n = 0
            try:
                for chunk in split_write(pkt, WRITE_CHUNK):
                    w = int(jlink.rtt_write(self._channel, chunk) or 0)
                    n += w
                    if w < len(chunk):
                        break   # 下行缓冲满：剩余留到下一个节拍
            except Exception:
                raise    # 下行通道可单独失败，不能把失败伪装成发送成功
            with self._lock:
                if not self._pending:
                    return
                self._queued = max(0, self._queued - n)
                head = self._pending[0]
                if n >= len(head):
                    self._pending.pop(0)
                else:
                    if n > 0:
                        self._pending[0] = head[n:]
                    return
            if n < len(pkt):
                return
