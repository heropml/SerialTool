# -*- coding: utf-8 -*-
"""Generate shipped example .ctproj packs under examples/."""
from __future__ import print_function

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from connection_presets import make_preset  # noqa: E402
from project_model import make_project, save_project, collect_project_resources  # noqa: E402
from project_templates import protocol_template_settings  # noqa: E402
from version import __version__  # noqa: E402


def _snippets(*rows):
    """rows: (name, text, hex_mode)"""
    out = []
    for name, text, hex_mode in rows:
        out.append({
            "name": name,
            "text": text,
            "hex": bool(hex_mode),
        })
    return out


def _write(path, name, metadata, settings, resources=None):
    if resources is None:
        resources = collect_project_resources(settings)
    payload = make_project(
        name, metadata, settings, __version__, resources=resources)
    save_project(str(path), payload)
    print("wrote", path)


def build_modbus(out_dir):
    settings = protocol_template_settings("modbus_rtu", "Serial")
    settings.update({
        "ser_baud": "9600",
        "ser_databits": "8",
        "ser_parity": "Even",
        "ser_stopbits": "1",
        "show_timestamp": True,
        "device_registers": json.dumps([
            {"name": "Voltage", "address": 0, "type": "u16", "unit": "V",
             "scale": 0.1, "slave": 1, "function": 3},
            {"name": "Current", "address": 1, "type": "u16", "unit": "A",
             "scale": 0.01, "slave": 1, "function": 3},
        ], ensure_ascii=False),
        "snippets": json.dumps(_snippets(
            ("Read Holding 0..1", "01 03 00 00 00 02", True),
            ("Read Input 0", "01 04 00 00 00 01", True),
        ), ensure_ascii=False),
        "connection_presets": json.dumps([
            make_preset(
                "Modbus RTU COM",
                {"net_proto": "Serial", "ser_baud": "9600",
                 "ser_parity": "Even", "ser_databits": "8",
                 "ser_stopbits": "1"},
                note="Typical RS-485 Modbus RTU",
                preset_id="example-modbus-rtu-serial"),
            make_preset(
                "Modbus TCP",
                {"net_proto": "TCP Client",
                 "net_remote_ip": "192.168.1.10",
                 "net_remote_port": "502"},
                note="Optional TCP path",
                preset_id="example-modbus-tcp"),
        ], ensure_ascii=False),
    })
    _write(
        out_dir / "modbus_rtu_demo.ctproj",
        "Modbus RTU Demo",
        {
            "device_type": "modbus",
            "protocol_template": "modbus_rtu",
            "connection_type": "Serial",
            "description": "HEX + packet split + ModbusCRC; sample registers and snippets.",
        },
        settings,
    )


def build_at(out_dir):
    settings = protocol_template_settings("at", "Serial")
    settings.update({
        "ser_baud": "115200",
        "show_timestamp": True,
        "snippets": json.dumps(_snippets(
            ("AT", "AT", False),
            ("ATI", "ATI", False),
            ("AT+CSQ", "AT+CSQ", False),
        ), ensure_ascii=False),
        "connection_presets": json.dumps([
            make_preset(
                "AT Modem",
                {"net_proto": "Serial", "ser_baud": "115200"},
                note="ASCII line mode for AT commands",
                preset_id="example-at-modem"),
        ], ensure_ascii=False),
        "sequence_rules": json.dumps([
            {"on": True, "name": "AT", "send": "AT", "send_hex": False,
             "expect": "OK", "expect_hex": False, "timeout": 1000, "delay": 0},
            {"on": True, "name": "ATI", "send": "ATI", "send_hex": False,
             "expect": "", "expect_hex": False, "timeout": 1000, "delay": 100},
        ], ensure_ascii=False),
    })
    _write(
        out_dir / "at_modem_demo.ctproj",
        "AT Modem Demo",
        {
            "device_type": "at",
            "protocol_template": "at",
            "connection_type": "Serial",
            "description": "Line-split ASCII AT commands with sample snippets/sequence.",
        },
        settings,
    )


def build_dual_session(out_dir):
    """Dual-session via two connection presets (tabs are runtime-only)."""
    settings = protocol_template_settings("raw", "Virtual")
    settings.update({
        "net_proto": "Virtual",
        "vconn_loopback": True,
        "show_timestamp": True,
        "line_split": True,
        "snippets": json.dumps(_snippets(
            ("Ping A", "hello-A", False),
            ("Ping B", "hello-B", False),
        ), ensure_ascii=False),
        "connection_presets": json.dumps([
            make_preset(
                "Session A (Virtual)",
                {"net_proto": "Virtual", "vconn_loopback": True},
                note="Open as tab 1",
                preset_id="example-dual-session-a"),
            make_preset(
                "Session B (Virtual)",
                {"net_proto": "Virtual", "vconn_loopback": True},
                note="New Session, then apply this preset",
                preset_id="example-dual-session-b"),
            make_preset(
                "TCP Echo",
                {"net_proto": "TCP Client",
                 "net_remote_ip": "127.0.0.1",
                 "net_remote_port": "9000"},
                note="Optional second real link",
                preset_id="example-dual-tcp-echo"),
        ], ensure_ascii=False),
    })
    _write(
        out_dir / "dual_session_demo.ctproj",
        "Dual Session Demo",
        {
            "device_type": "generic",
            "protocol_template": "raw",
            "connection_type": "Virtual",
            "description": (
                "Two Virtual presets for multi-tab practice. "
                "Open project → New Session → apply Session B preset."
            ),
        },
        settings,
    )


def main():
    out = ROOT / "examples"
    out.mkdir(parents=True, exist_ok=True)
    build_modbus(out)
    build_at(out)
    build_dual_session(out)
    readme = out / "README.md"
    readme.write_text(
        "# CommTool example projects\n\n"
        "| File | Use |\n"
        "|---|---|\n"
        "| `modbus_rtu_demo.ctproj` | Modbus RTU HEX view, CRC, sample registers |\n"
        "| `at_modem_demo.ctproj` | AT line mode + snippets / smoke sequence |\n"
        "| `dual_session_demo.ctproj` | Two Virtual presets for multi-tab practice |\n\n"
        "Open via **Project → Open**. Dual-session tabs are runtime-only: "
        "after opening the project, use **New Session** and apply the "
        "**Session B** connection preset.\n"
        "Regenerate with `python scripts/build_example_projects.py`.\n",
        encoding="utf-8",
    )
    print("wrote", readme)


if __name__ == "__main__":
    main()
