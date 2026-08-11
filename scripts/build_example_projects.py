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


def build_nmea(out_dir):
    settings = protocol_template_settings("nmea", "Serial")
    settings.update({
        "ser_baud": "9600",
        "show_timestamp": True,
        "snippets": json.dumps(_snippets(
            ("GPGGA sample",
             "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47",
             False),
            ("GPGSA sample",
             "$GPGSA,A,3,04,05,,09,12,,,24,,,,,2.5,1.3,2.1*39",
             False),
        ), ensure_ascii=False),
        "connection_presets": json.dumps([
            make_preset(
                "NMEA GPS 9600",
                {"net_proto": "Serial", "ser_baud": "9600",
                 "ser_databits": "8", "ser_parity": "None", "ser_stopbits": "1"},
                note="Typical GPS NMEA 0183 UART",
                preset_id="example-nmea-gps-serial"),
        ], ensure_ascii=False),
    })
    _write(
        out_dir / "nmea_gps_demo.ctproj",
        "NMEA GPS Demo",
        {
            "device_type": "sensor",
            "protocol_template": "nmea",
            "connection_type": "Serial",
            "description": "NMEA line mode @ 9600 with sample $GPGGA / $GPGSA snippets.",
        },
        settings,
    )


def build_fixed_header(out_dir):
    settings = protocol_template_settings("fixed_header", "Virtual")
    settings.update({
        "net_proto": "Virtual",
        "vconn_loopback": True,
        "show_timestamp": True,
        "snippets": json.dumps(_snippets(
            ("AA55 cmd", "AA 55 01 04 12 34 56 78", True),
            ("AA55 short", "AA 55 02 02 AB CD", True),
        ), ensure_ascii=False),
        "connection_presets": json.dumps([
            make_preset(
                "Fixed header loopback",
                {"net_proto": "Virtual", "vconn_loopback": True},
                note="Virtual loopback for AA 55 frame practice",
                preset_id="example-fixed-header-virtual"),
        ], ensure_ascii=False),
    })
    _write(
        out_dir / "fixed_header_demo.ctproj",
        "Fixed Header Demo",
        {
            "device_type": "generic",
            "protocol_template": "fixed_header",
            "connection_type": "Virtual",
            "description": "AA 55 fixed-header HEX frames on Virtual loopback with plot HEX fields.",
        },
        settings,
    )


def build_sensor_csv(out_dir):
    settings = protocol_template_settings("delimiter", "Virtual")
    settings.update({
        "net_proto": "Virtual",
        "vconn_loopback": True,
        "show_timestamp": True,
        "line_split": True,
        "append_newline": True,
        "append_nl_mode": 0,  # CRLF — plot delimiter parser needs a line end
        "plot_mode": 0,
        "plot_sep": 0,
        "snippets": json.dumps(_snippets(
            ("Sample CSV", "36.5,72,3.30", False),
            ("Sample CSV 2", "37.1,68,3.28", False),
        ), ensure_ascii=False),
        "multi_send_groups": json.dumps([{
            "name": "Sensor CSV",
            "items": [
                {"checked": True, "name": "row1", "data": "36.5,72,3.30",
                 "hex": False, "nl": 1, "delay": 200},
                {"checked": True, "name": "row2", "data": "37.1,68,3.28",
                 "hex": False, "nl": 1, "delay": 200},
            ],
        }], ensure_ascii=False),
        "connection_presets": json.dumps([
            make_preset(
                "Sensor CSV loopback",
                {"net_proto": "Virtual", "vconn_loopback": True},
                note="Delimiter plot: temp,humidity,voltage",
                preset_id="example-sensor-csv-virtual"),
        ], ensure_ascii=False),
    })
    _write(
        out_dir / "sensor_csv_demo.ctproj",
        "Sensor CSV Demo",
        {
            "device_type": "sensor",
            "protocol_template": "delimiter",
            "connection_type": "Virtual",
            "description": "Comma-separated sensor lines for delimiter plot (e.g. 36.5,72,3.30).",
        },
        settings,
    )


def build_tcp_client_debug(out_dir):
    settings = protocol_template_settings("raw", "TCP Client")
    settings.update({
        "net_proto": "TCP Client",
        "net_remote_ip": "127.0.0.1",
        "net_remote_port": "9000",
        "show_timestamp": True,
        "snippets": json.dumps(_snippets(
            ("Ping", "ping", False),
            ("Hex ping", "70 69 6E 67", True),
        ), ensure_ascii=False),
        "connection_presets": json.dumps([
            make_preset(
                "Local echo :9000",
                {"net_proto": "TCP Client",
                 "net_remote_ip": "127.0.0.1",
                 "net_remote_port": "9000"},
                note="TCP Client to localhost:9000",
                preset_id="example-tcp-client-9000"),
            make_preset(
                "Alt port :9001",
                {"net_proto": "TCP Client",
                 "net_remote_ip": "127.0.0.1",
                 "net_remote_port": "9001"},
                note="Optional alternate debug port",
                preset_id="example-tcp-client-9001"),
        ], ensure_ascii=False),
    })
    _write(
        out_dir / "tcp_client_debug.ctproj",
        "TCP Client Debug",
        {
            "device_type": "network",
            "protocol_template": "raw",
            "connection_type": "TCP Client",
            "description": "Raw TCP Client to 127.0.0.1:9000 with connection presets.",
        },
        settings,
    )


def main():
    out = ROOT / "examples"
    out.mkdir(parents=True, exist_ok=True)
    build_modbus(out)
    build_at(out)
    build_dual_session(out)
    build_nmea(out)
    build_fixed_header(out)
    build_sensor_csv(out)
    build_tcp_client_debug(out)
    readme = out / "README.md"
    readme.write_text(
        "# CommTool example projects\n\n"
        "| File | Use |\n"
        "|---|---|\n"
        "| `modbus_rtu_demo.ctproj` | Modbus RTU HEX view, CRC, sample registers |\n"
        "| `at_modem_demo.ctproj` | AT line mode + snippets / smoke sequence |\n"
        "| `dual_session_demo.ctproj` | Two Virtual presets for multi-tab practice |\n"
        "| `nmea_gps_demo.ctproj` | NMEA GPS @ 9600 with $GPGGA sample snippets |\n"
        "| `fixed_header_demo.ctproj` | AA 55 fixed-header HEX on Virtual loopback |\n"
        "| `sensor_csv_demo.ctproj` | Delimiter CSV sensor lines + multi-send / plot |\n"
        "| `tcp_client_debug.ctproj` | Raw TCP Client 127.0.0.1:9000 + presets |\n\n"
        "Open via **Project → Open**. Dual-session tabs are runtime-only: "
        "after opening the project, use **New Session** and apply the "
        "**Session B** connection preset.\n"
        "Regenerate with `python scripts/build_example_projects.py`.\n",
        encoding="utf-8",
    )
    print("wrote", readme)


if __name__ == "__main__":
    main()
