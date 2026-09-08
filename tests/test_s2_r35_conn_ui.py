# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R35 conn_ui visibility / open-button keys."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui import conn_ui as cu


def test_conn_types_match_historical_order():
    # Must stay aligned with net_io.PROTOCOLS + virtual_io.PROTO_VIRTUAL.
    assert cu.PROTO_SERIAL == "Serial"
    assert cu.PROTO_VIRTUAL == "Virtual"
    assert list(cu.PROTOCOLS) == [
        "UDP", "UDP Multicast", "TCP Server", "TCP Client",
    ]
    assert cu.CONN_TYPES == [
        "Serial", "UDP", "UDP Multicast", "TCP Server", "TCP Client", "Virtual",
        "BLE", "RTT",
    ]


def test_visible_conn_types_hides_ble_off_windows():
    assert cu.visible_conn_types("win32") == list(cu.CONN_TYPES)
    assert cu.PROTO_BLE not in cu.visible_conn_types("darwin")
    assert cu.PROTO_BLE not in cu.visible_conn_types("linux")
    assert cu.visible_conn_types("darwin") == [
        t for t in cu.CONN_TYPES if t != cu.PROTO_BLE
    ]


def test_open_btn_keys():
    assert cu.open_btn_key(cu.PROTO_SERIAL, False) == "btn_serial_open"
    assert cu.open_btn_key(cu.PROTO_SERIAL, True) == "btn_serial_close"
    assert cu.open_btn_key(cu.PROTO_VIRTUAL, False) == "btn_vconn_open"
    assert cu.open_btn_key(cu.PROTO_TCP_SERVER, False) == "btn_listen"
    assert cu.open_btn_key(cu.PROTO_TCP_SERVER, True) == "btn_listen_stop"
    assert cu.open_btn_key(cu.PROTO_TCP_CLIENT, False) == "btn_connect"
    assert cu.open_btn_key(cu.PROTO_TCP_CLIENT, True) == "btn_disconnect"
    assert cu.open_btn_key(cu.PROTO_UDP, False) == "btn_udp_open"
    assert cu.open_btn_key(cu.PROTO_UDP_MULTICAST, True) == "btn_udp_close"
    assert cu.open_btn_key("Unknown", False) == "btn_connect"


def test_serial_and_virtual_hide_net_rows():
    s = cu.field_visibility(cu.PROTO_SERIAL, True)
    assert s["serial_rows"] is True
    assert s["ctrl_box"] is True
    assert s["vconn_loop"] is False
    assert s["local_ip"] is False and s["target"] is False
    assert s["open_btn_key"] == "btn_serial_close"

    v = cu.field_visibility(cu.PROTO_VIRTUAL, False)
    assert v["vconn_loop"] is True
    assert v["serial_rows"] is False
    assert v["ctrl_box"] is False
    assert v["remote_enabled"] is False
    assert v["open_btn_key"] == "btn_vconn_open"


def test_tcp_server_target_and_udp_remote():
    idle = cu.field_visibility(cu.PROTO_TCP_SERVER, False, has_targets=True)
    assert idle["local_ip"] and idle["local_port"]
    assert idle["target"] is False  # need engaged
    assert idle["remote_enabled"] is False

    live = cu.field_visibility(cu.PROTO_TCP_SERVER, True, has_targets=True)
    assert live["target"] is True
    assert live["open_btn_key"] == "btn_listen_stop"

    no_cli = cu.field_visibility(cu.PROTO_TCP_SERVER, True, has_targets=False)
    assert no_cli["target"] is False

    udp_off = cu.field_visibility(cu.PROTO_UDP, False, udp_remote_on=False)
    assert udp_off["udp_remote"] is True
    assert udp_off["remote_ip"] is True
    assert udp_off["remote_enabled"] is False

    udp_on = cu.field_visibility(cu.PROTO_UDP, False, udp_remote_on=True)
    assert udp_on["remote_enabled"] is True

    udp_live = cu.field_visibility(cu.PROTO_UDP, True, udp_remote_on=True)
    assert udp_live["remote_enabled"] is False  # locked while engaged

    cli = cu.field_visibility(cu.PROTO_TCP_CLIENT, False)
    assert cli["remote_ip"] and cli["remote_port"] and cli["remote_enabled"]
    assert cli["local_ip"] is False
    assert cli.get("ble_rows") is False


def test_ble_rows_and_open_btn():
    idle = cu.field_visibility(cu.PROTO_BLE, False)
    assert idle["ble_rows"] is True
    assert idle["serial_rows"] is False
    assert idle["local_ip"] is False and idle["remote_ip"] is False
    assert idle["open_btn_key"] == "btn_connect"
    live = cu.field_visibility(cu.PROTO_BLE, True)
    assert live["open_btn_key"] == "btn_disconnect"
    assert cu.open_btn_key(cu.PROTO_BLE, False) == "btn_connect"
