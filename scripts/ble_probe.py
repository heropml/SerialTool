#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dev-only BLE UART probe (not a user feature).

Scan, inspect GATT, and ping one Write + one Notify. Always stops notify
and disconnects (success, error, Ctrl+C).

Examples:
  python scripts/ble_probe.py scan --timeout 8
  python scripts/ble_probe.py inspect --address 69:1E:38:38:39:0D
  python scripts/ble_probe.py ping --address 69:1E:38:38:39:0D \\
      --service FFF0 --write FFF2 --notify FFF1 --hex AA
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import ble_uuid  # noqa: E402


def _ts():
    return time.strftime("%H:%M:%S")


def _need_bleak():
    try:
        import bleak  # noqa: F401
    except ImportError:
        sys.stderr.write("bleak is not installed. pip install bleak\n")
        sys.exit(2)


def _fmt_uuids(uuids):
    if not uuids:
        return "-"
    shorts = []
    for u in uuids:
        shorts.append(ble_uuid.short_uuid(u) or u)
    return ",".join(shorts)


async def cmd_scan(timeout):
    from bleak import BleakScanner

    print("[%s] scanning %.1fs..." % (_ts(), timeout))
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    rows = []
    for addr, pair in found.items():
        if isinstance(pair, tuple) and len(pair) == 2:
            dev, adv = pair
        else:
            dev, adv = None, pair
        name = ""
        if dev is not None:
            name = getattr(dev, "name", None) or ""
        if not name:
            name = getattr(adv, "local_name", None) or ""
        rssi = getattr(adv, "rssi", None)
        uuids = list(getattr(adv, "service_uuids", None) or [])
        address = getattr(dev, "address", None) or addr
        rows.append((address, name, rssi, uuids))
    rows.sort(key=lambda r: (r[2] is None, -(r[2] or -999), r[0]))
    print("%-18s  %-8s  %-28s  %s" % ("ADDRESS", "RSSI", "NAME", "ADV UUIDS"))
    for addr, name, rssi, uuids in rows:
        rssi_s = "" if rssi is None else str(rssi)
        print("%-18s  %-8s  %-28s  %s" % (
            addr, rssi_s, name or "(unnamed)", _fmt_uuids(uuids)))
    print("[%s] %d device(s)" % (_ts(), len(rows)))
    return 0


def _props(char):
    props = list(getattr(char, "properties", None) or [])
    return ",".join(props) if props else "-"


async def cmd_inspect(address):
    from bleak import BleakClient

    addr = ble_uuid.normalize_address(address)
    print("[%s] connect %s" % (_ts(), addr))
    client = BleakClient(addr)
    try:
        await client.connect(timeout=15.0)
        print("[%s] connected  mtu=%s" % (
            _ts(), getattr(client, "mtu_size", "?")))
        svcs = getattr(client, "services", None)
        if svcs is None:
            print("no services")
            return 1
        for svc in svcs:
            print("SERVICE  %s  %s" % (
                ble_uuid.short_uuid(svc.uuid), svc.uuid))
            for char in svc.characteristics:
                print("  CHAR   %s  %-36s  %s" % (
                    ble_uuid.short_uuid(char.uuid), char.uuid, _props(char)))
        return 0
    finally:
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception as exc:
            print("[%s] disconnect: %s" % (_ts(), exc), file=sys.stderr)
        print("[%s] disconnected" % _ts())


async def cmd_ping(address, service, write, notify, hex_payload, wait_s):
    from bleak import BleakClient

    addr = ble_uuid.normalize_address(address)
    wr = ble_uuid.normalize_uuid(write)
    ntf = ble_uuid.normalize_uuid(notify)
    svc = ble_uuid.normalize_uuid(service) if service else ""
    if not wr or not ntf:
        print("write/notify UUID invalid", file=sys.stderr)
        return 2
    try:
        payload = bytes.fromhex(hex_payload.replace(" ", ""))
    except ValueError:
        print("bad --hex", file=sys.stderr)
        return 2

    got = []

    def _on_notify(_sender, data):
        chunk = bytes(data)
        got.append((time.time(), chunk))
        print("[%s] RX %d bytes  %s" % (
            _ts(), len(chunk), chunk.hex(" ")))

    client = BleakClient(addr)
    started = False
    try:
        print("[%s] connect %s" % (_ts(), addr))
        await client.connect(timeout=15.0)
        print("[%s] connected" % _ts())
        if svc:
            found = False
            for s in client.services:
                if ble_uuid.uuids_equal(s.uuid, svc):
                    found = True
                    break
            if not found:
                print("service %s not found" % svc, file=sys.stderr)
                return 1
        await client.start_notify(ntf, _on_notify)
        started = True
        print("[%s] notify %s" % (_ts(), ntf))
        char = client.services.get_characteristic(wr)
        props = list(getattr(char, "properties", None) or []) if char else []
        use_resp = "write-without-response" not in props
        print("[%s] TX %d bytes via %s  response=%s  %s" % (
            _ts(), len(payload), wr, use_resp, payload.hex(" ")))
        await client.write_gatt_char(wr, payload, response=use_resp)
        deadline = time.monotonic() + max(0.2, float(wait_s))
        while time.monotonic() < deadline and not got:
            await asyncio.sleep(0.05)
        if not got:
            print("[%s] no RX within %.1fs" % (_ts(), wait_s))
            return 1
        return 0
    finally:
        if started:
            try:
                await client.stop_notify(ntf)
            except Exception as exc:
                print("[%s] stop_notify: %s" % (_ts(), exc), file=sys.stderr)
        try:
            if client.is_connected:
                await client.disconnect()
        except Exception as exc:
            print("[%s] disconnect: %s" % (_ts(), exc), file=sys.stderr)
        print("[%s] cleaned up" % _ts())


def main(argv=None):
    _need_bleak()
    p = argparse.ArgumentParser(description="CommTool BLE UART probe")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("scan", help="timed scan")
    ps.add_argument("--timeout", type=float, default=8.0)

    pi = sub.add_parser("inspect", help="connect and list GATT")
    pi.add_argument("--address", required=True)

    pp = sub.add_parser("ping", help="notify + one write")
    pp.add_argument("--address", required=True)
    pp.add_argument("--service", default="")
    pp.add_argument("--write", required=True, help="PC → device")
    pp.add_argument("--notify", required=True, help="device → PC")
    pp.add_argument("--hex", dest="hex_payload", default="AA")
    pp.add_argument("--wait", type=float, default=3.0)

    args = p.parse_args(argv)
    if args.cmd == "scan":
        return asyncio.run(cmd_scan(args.timeout))
    if args.cmd == "inspect":
        return asyncio.run(cmd_inspect(args.address))
    if args.cmd == "ping":
        return asyncio.run(cmd_ping(
            args.address, args.service, args.write, args.notify,
            args.hex_payload, args.wait))
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
