# -*- coding: utf-8 -*-
"""新建工程协议模板到 CommTool 现有 QSettings 键的映射。"""


DEVICE_IDS = (
    "generic", "modbus", "at", "sensor", "network", "custom",
)

PROTOCOL_IDS = (
    "raw", "modbus_rtu", "modbus_tcp", "nmea", "at",
    "fixed_header", "delimiter", "custom",
)


_BASE = {
    "hexdump_view": False,
    "numview": False,
    "ansi_color": False,
    "proto_highlight": False,
    "packet_split": False,
    "packet_timeout": "20",
    "line_split": False,
    "line_nl_mode": 0,
    "tx_hex": False,
    "append_newline": False,
    "append_nl_mode": 0,
    "checksum_idx": 0,
    "encoding": "auto",
    "frame_rules": "",
    "plot_mode": 0,
    "plot_sep": 0,
    "plot_regex": "",
    "plot_hex_fields": "",
    "plot_hex_header": "",
    "dash_mode": 0,
    "dash_sep": 0,
    "dash_regex": "",
    "dash_fields": "",
    "dash_header": "",
}


def protocol_template_settings(template_id, connection_type=None):
    """Return template settings for main-window QSettings.

    Honor caller connection_type (wizard step 2). Fall back to protocol default.
    """
    template_id = str(template_id or "raw")
    cfg = dict(_BASE)
    if connection_type:
        cfg["net_proto"] = str(connection_type)
    else:
        cfg["net_proto"] = recommended_connection(template_id, "Serial")

    if template_id == "modbus_rtu":
        cfg.update({
            "rx_hex": True,
            "tx_hex": True,
            "packet_split": True,
            "checksum_idx": 5,  # ModbusCRC16
            "frame_rules": " | 从机=0:u8x, 功能码=1:u8x",
            "proto_highlight": True,
        })
    elif template_id == "modbus_tcp":
        cfg.update({
            "rx_hex": True,
            "tx_hex": True,
            "frame_rules": (
                " | 事务ID=0:u16bex, 协议ID=2:u16bex, 长度=4:u16be, "
                "单元ID=6:u8x, 功能码=7:u8x"
            ),
            "proto_highlight": True,
        })
    elif template_id == "at":
        cfg.update({
            "rx_hex": False,
            "line_split": True,
            "append_newline": True,
            "encoding": "ascii",
        })
    elif template_id == "nmea":
        cfg.update({
            "rx_hex": False,
            "line_split": True,
            "encoding": "ascii",
            "plot_mode": 0,
            "plot_sep": 0,
            "dash_mode": 0,
            "dash_sep": 0,
        })
    elif template_id == "fixed_header":
        cfg.update({
            "rx_hex": True,
            "tx_hex": True,
            "packet_split": True,
            "frame_rules": "AA 55 | 命令=2:u8x, 长度=3:u8, 数据=4:hex4",
            "proto_highlight": True,
            "plot_mode": 2,
            "plot_hex_header": "AA 55",
            "plot_hex_fields": "数值=4:u16be",
            "dash_mode": 2,
            "dash_header": "AA 55",
            "dash_fields": "数值=4:u16be",
        })
    elif template_id == "delimiter":
        cfg.update({
            "rx_hex": False,
            "line_split": True,
            "encoding": "utf-8",
            "plot_mode": 0,
            "plot_sep": 0,
            "dash_mode": 0,
            "dash_sep": 0,
        })
    else:
        cfg["rx_hex"] = False
    return cfg


def recommended_connection(template_id, current="Serial"):
    return {
        "modbus_rtu": "Serial",
        "modbus_tcp": "TCP Client",
        "nmea": "Serial",
        "at": "Serial",
    }.get(str(template_id or ""), current)


def recommended_protocol(device_id):
    return {
        "modbus": "modbus_rtu",
        "at": "at",
        "sensor": "delimiter",
        "network": "raw",
        "custom": "custom",
    }.get(str(device_id or ""), "raw")


def recommended_device_connection(device_id, current="Serial"):
    device_id = str(device_id or "")
    if device_id == "network":
        return "TCP Client"
    if device_id in ("generic", "modbus", "at", "sensor"):
        return "Serial"
    return current


def recommended_views(template_id):
    binary = template_id in ("modbus_rtu", "modbus_tcp", "fixed_header")
    return {
        "hex": binary,
        "timestamp": True,
        "plot": False,
        "dashboard": False,
    }
