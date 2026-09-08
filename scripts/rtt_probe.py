# -*- coding: utf-8 -*-
"""J-Link RTT 连接诊断（CommTool「RTT」类型打不开时定位用）。

J-Link 调试器同一时刻只能被一个上位机使用：运行本脚本前请先完全退出
J-Link RTT Viewer / Keil / Ozone / J-Link Commander 等占用调试器的程序。

用法（工程根目录）:
    python scripts/rtt_probe.py <器件名> [SWD|JTAG] [速率kHz] [RTT地址] [调试器序列号]
示例:
    python scripts/rtt_probe.py STM32H743VI SWD 4000
    python scripts/rtt_probe.py nRF52840_xxAA SWD 4000 0x20000000
    python scripts/rtt_probe.py STM32H743VI SWD 4000 0x24000000+0x80000
    python scripts/rtt_probe.py --devices STM32H7        # 查器件名怎么拼

RTT 地址三种写法（与 CommTool 的「RTT 地址」栏一致）:
    留空 / auto              J-Link 自己在 RAM 里搜控制块
    0x20000000               控制块的精确地址
    0x20000000+0x40000       在这段 RAM 里搜 "SEGGER RTT" 标志

逐级执行 加载DLL → 打开调试器 → 连接目标 → 启动RTT → 等控制块，
任一步失败即打印原始报错 + 归类结论并退出（退出码 1）。
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from transport import rtt_io  # noqa: E402
from transport.rtt_io import classify_error  # noqa: E402

VERDICT = {
    rtt_io.ERR_NO_JLINK: "未安装 SEGGER J-Link 驱动包（缺 JLinkARM.dll）。"
                         "安装官方 J-Link Software 包后重试。",
    rtt_io.ERR_NO_PROBE: "调试器没插好、被其它程序占用（RTT Viewer/Keil/Ozone/"
                         "J-Link Commander 必须全关），或驱动器型号不匹配。",
    rtt_io.ERR_BAD_DEVICE: "J-Link 不认识该器件名。用 --devices <关键字> 查正确拼写。",
    rtt_io.ERR_NO_TARGET: "调试器在，但目标没应答：检查是否上电、SWD/JTAG 选择与接线、"
                          "复位脚是否被拉住、是否读保护。",
    rtt_io.ERR_BAD_SPEED: "速率越界：J-Link 只接受 5~50000 kHz。",
    rtt_io.ERR_NO_RTT: "连上了目标但找不到 RTT 控制块：确认固件含 SEGGER_RTT 输出，"
                       "或手填 _SEGGER_RTT 地址 / 搜索范围（第 4 个参数）。",
}

WAIT_CB_S = 15.0        # 等控制块的上限（仅诊断用；CommTool 里是一直等）


def _fail(step, exc):
    raw = str(exc).strip() or type(exc).__name__
    token = classify_error(raw)
    print("[失败] %s" % step)
    print("   原始报错: %s" % ascii(raw))
    if token:
        print("   归类: %s" % token)
        print("   结论: %s" % VERDICT.get(token, "把上面的原始报错发给维护者。"))
    else:
        print("   归类: 未知 —— 把上面的原始报错发给维护者。")
    return 1


def _list_devices(keyword):
    """按关键字列出 J-Link 支持的器件名（CommTool 器件选择窗的同一份数据）。"""
    print("驱动: %s" % (rtt_io.find_jlink_dll() or "（没找到）"))
    names = rtt_io.list_supported_devices(refresh=True)
    if names == list(rtt_io.COMMON_DEVICES):
        print("没能从 J-Link 驱动读出器件表（未装驱动？），下面是内置候选：")
    kw = (keyword or "").strip().lower()
    hits = [n for n in names if not kw or kw in n.lower()]
    print("匹配 %d 项（共 %d）：" % (len(hits), len(names)))
    for name in hits[:200]:
        print("   %s" % name)
    if len(hits) > 200:
        print("   … 还有 %d 项，换更具体的关键字。" % (len(hits) - 200))
    return 0


def main(argv):
    if len(argv) > 1 and argv[1] == "--devices":
        return _list_devices(argv[2] if len(argv) > 2 else "")

    device = argv[1] if len(argv) > 1 else ""
    tif = (argv[2] if len(argv) > 2 else "SWD").upper()
    sn = rtt_io.normalize_probe(argv[5] if len(argv) > 5 else "")
    try:
        speed = int(argv[3]) if len(argv) > 3 else 4000
    except ValueError:
        print("速率必须是整数 kHz（5~50000）。")
        return 2
    spec = rtt_io.parse_address_spec(argv[4] if len(argv) > 4 else "")
    if spec is None:
        print("地址写法不对。支持 留空 / 0x20000000 / 0x20000000+0x40000。")
        return 2
    start, search_size = spec
    if not device:
        print(__doc__)
        return 2
    if rtt_io.parse_speed(str(speed)) is None:
        print("速率越界：J-Link 只接受 %d~%d kHz。"
              % (rtt_io.MIN_SPEED_KHZ, rtt_io.MAX_SPEED_KHZ))
        return 2

    print("① 加载 pylink / J-Link DLL ...")
    dll = rtt_io.find_jlink_dll()
    print("   驱动: %s" % (dll or "（没找到，pylink 只会扫 C 盘；用 JLINK_PATH 指定）"))
    try:
        import pylink                                   # noqa: F401
        jl = rtt_io.make_jlink()
    except ImportError:
        print("[失败] 未安装 pylink 组件（pip install pylink-square）")
        return 1
    except Exception as exc:
        return _fail("加载 J-Link DLL", exc)

    probes = rtt_io.list_probes()
    print("   接入的调试器: %s" % (", ".join(probes) if probes else "（一个都没有）"))
    if not probes:
        return _fail("查找调试器", RuntimeError(rtt_io.ERR_NO_PROBE))

    print("② 打开调试器%s ..." % (" (SN=%s)" % sn if sn else ""))
    try:
        jl.open(serial_no=sn) if sn else jl.open()
        for cmd in rtt_io.SILENT_COMMANDS:
            try:
                jl.exec_command(cmd)
            except Exception:
                pass
    except Exception as exc:
        return _fail("打开调试器", exc)

    print("③ 设接口 %s、速率 %d kHz，连接目标 %s ..." % (tif, speed, device))
    try:
        table = getattr(getattr(pylink, "enums", None), "JLinkInterfaces")
        jl.set_tif(getattr(table, tif, table.SWD))
        jl.connect(device, speed=speed, verbose=False)
    except Exception as exc:
        return _fail("连接目标（%s / %s @ %d kHz）" % (device, tif, speed), exc)

    block = start
    if search_size:
        print("④ 在 [%#x, +%#x) 里搜 \"SEGGER RTT\" 标志 ..." % (start, search_size))
        found = rtt_io.search_control_block(jl, start, search_size)
        if found:
            print("   命中：控制块 %#x" % found)
            block = found
        else:
            print("   没搜到，退回 J-Link 自动搜索（和 CommTool 行为一致）。")
            block = 0

    print("⑤ 启动 RTT（控制块%s）..."
          % ("手填 " + hex(block) if block else "自动搜索"))
    try:
        jl.rtt_start(block or None)
    except Exception as exc:
        return _fail("启动 RTT", exc)

    print("⑥ 等 RTT 控制块（最多 %.0fs；RAM 大时自动搜索会慢些）..." % WAIT_CB_S)
    got = b""
    ok = False
    last = ""
    deadline = time.monotonic() + WAIT_CB_S
    while time.monotonic() < deadline:
        try:
            got = bytes(jl.rtt_read(0, 8192) or b"")
            ok = True
            break
        except Exception as exc:
            last = str(exc)
            time.sleep(0.05)
    if not ok:
        print("   注意：CommTool 到这一步不会判失败 —— 它已经算连上并继续等，"
              "固件跑到 SEGGER_RTT 初始化后数据就会出来。")
        return _fail("等待 RTT 控制块", RuntimeError(last or "rtt:no-rtt"))

    print("   RTT 通道 0 就绪，首批 %d 字节: %s" % (len(got), ascii(got[:64])))
    try:
        more = bytes(jl.rtt_read(0, 8192) or b"")
        time.sleep(1.0)
        more += bytes(jl.rtt_read(0, 8192) or b"")
        print("   1s 后再收 %d 字节: %s" % (len(more), ascii(more[:64])))
    except Exception:
        pass
    print("√ RTT 通路正常。请在 CommTool 里用同样参数连接；")
    print("  若 CommTool 仍失败，把本脚本完整输出发给维护者。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        sys.exit(130)
