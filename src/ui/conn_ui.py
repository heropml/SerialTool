# -*- coding: utf-8 -*-
"""Connection settings UI decision tables (Qt-free).

S-2 R35: open-button i18n keys and row visibility for CommTool
`_update_net_fields`. String constants mirror net_io / virtual_io
without importing Qt.
"""
import sys

PROTO_SERIAL = "Serial"
PROTO_VIRTUAL = "Virtual"
PROTO_TCP_SERVER = "TCP Server"
PROTO_TCP_CLIENT = "TCP Client"
PROTO_UDP = "UDP"
PROTO_UDP_MULTICAST = "UDP Multicast"
PROTO_BLE = "BLE"
PROTO_RTT = "RTT"

# Order: Serial + net_io.PROTOCOLS + Virtual + BLE + RTT (8th type).
PROTOCOLS = (
    PROTO_UDP, PROTO_UDP_MULTICAST, PROTO_TCP_SERVER, PROTO_TCP_CLIENT,
)
CONN_TYPES = [PROTO_SERIAL] + list(PROTOCOLS) + [PROTO_VIRTUAL, PROTO_BLE, PROTO_RTT]


def visible_conn_types(platform=None):
    """Types shown in the connection dropdown.

    BLE host UART is Windows-only. Hide it on macOS/Linux instead of
    offering a type that only toasts 'unsupported'. RTT runs wherever the
    SEGGER J-Link driver is installed (Win/macOS/Linux), so it is always
    listed; a missing driver toasts at open time.
    """
    plat = sys.platform if platform is None else platform
    if plat == "win32":
        return list(CONN_TYPES)
    return [t for t in CONN_TYPES if t != PROTO_BLE]

_OPEN_BTN_ENGAGED = {
    PROTO_SERIAL: "btn_serial_close",
    PROTO_VIRTUAL: "btn_vconn_close",
    PROTO_TCP_SERVER: "btn_listen_stop",
    PROTO_TCP_CLIENT: "btn_disconnect",
    PROTO_UDP: "btn_udp_close",
    PROTO_UDP_MULTICAST: "btn_udp_close",
    PROTO_BLE: "btn_disconnect",
    PROTO_RTT: "btn_disconnect",
}
_OPEN_BTN_IDLE = {
    PROTO_SERIAL: "btn_serial_open",
    PROTO_VIRTUAL: "btn_vconn_open",
    PROTO_TCP_SERVER: "btn_listen",
    PROTO_TCP_CLIENT: "btn_connect",
    PROTO_UDP: "btn_udp_open",
    PROTO_UDP_MULTICAST: "btn_udp_open",
    PROTO_BLE: "btn_connect",
    PROTO_RTT: "btn_connect",
}


def open_btn_key(proto, engaged):
    """i18n key for the primary open/close/listen button."""
    proto = proto or ""
    table = _OPEN_BTN_ENGAGED if engaged else _OPEN_BTN_IDLE
    return table.get(proto, "btn_connect")


def field_visibility(proto, engaged, *, has_targets=False, udp_remote_on=False):
    """Pure visibility / enable map for connection settings rows.

    Returns dict keys:
      ctrl_box, vconn_loop, serial_rows, ble_rows, rtt_rows,
      local_ip, group, local_port, udp_remote, remote_ip, remote_port, target,
      remote_enabled, open_btn_key
    """
    proto = proto or ""
    engaged = bool(engaged)
    is_serial = proto == PROTO_SERIAL
    is_virt = proto == PROTO_VIRTUAL
    is_ble = proto == PROTO_BLE
    is_rtt = proto == PROTO_RTT
    is_srv = proto == PROTO_TCP_SERVER
    is_cli = proto == PROTO_TCP_CLIENT
    is_udp = proto == PROTO_UDP
    is_grp = proto == PROTO_UDP_MULTICAST

    if is_virt or is_serial:
        return {
            "ctrl_box": is_serial and engaged,
            "vconn_loop": is_virt,
            "serial_rows": is_serial,
            "ble_rows": False,
            "rtt_rows": False,
            "local_ip": False,
            "group": False,
            "local_port": False,
            "udp_remote": False,
            "remote_ip": False,
            "remote_port": False,
            "target": False,
            "remote_enabled": False,
            "open_btn_key": open_btn_key(proto, engaged),
        }

    if is_ble:
        return {
            "ctrl_box": False,
            "vconn_loop": False,
            "serial_rows": False,
            "ble_rows": True,
            "rtt_rows": False,
            "local_ip": False,
            "group": False,
            "local_port": False,
            "udp_remote": False,
            "remote_ip": False,
            "remote_port": False,
            "target": False,
            "remote_enabled": False,
            "open_btn_key": open_btn_key(proto, engaged),
        }

    if is_rtt:
        return {
            "ctrl_box": False,
            "vconn_loop": False,
            "serial_rows": False,
            "ble_rows": False,
            "rtt_rows": True,
            "local_ip": False,
            "group": False,
            "local_port": False,
            "udp_remote": False,
            "remote_ip": False,
            "remote_port": False,
            "target": False,
            "remote_enabled": False,
            "open_btn_key": open_btn_key(proto, engaged),
        }

    return {
        "ctrl_box": False,
        "vconn_loop": False,
        "serial_rows": False,
        "ble_rows": False,
        "rtt_rows": False,
        "local_ip": is_srv or is_udp or is_grp,
        "group": is_grp,
        "local_port": is_srv or is_udp or is_grp,
        "udp_remote": is_udp,
        "remote_ip": is_cli or is_udp,
        "remote_port": is_cli or is_udp,
        "target": is_srv and engaged and bool(has_targets),
        "remote_enabled": (not engaged) and (is_cli or (is_udp and bool(udp_remote_on))),
        "open_btn_key": open_btn_key(proto, engaged),
    }
