import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from protocol import binproto
from project.project_templates import (
    protocol_template_settings, recommended_connection,
    recommended_device_connection, recommended_protocol, recommended_views,
)


def test_modbus_rtu_template_sets_serial_hex_and_crc():
    cfg = protocol_template_settings("modbus_rtu", "UDP")

    # Caller-selected connection wins; recommendations stay in recommended_connection().
    assert cfg["net_proto"] == "UDP"
    assert cfg["rx_hex"] is True
    assert cfg["tx_hex"] is True
    assert cfg["checksum_idx"] == 5
    assert cfg["packet_split"] is True
    assert cfg["proto_highlight"] is True


def test_modbus_rtu_defaults_connection_when_omitted():
    cfg = protocol_template_settings("modbus_rtu")
    assert cfg["net_proto"] == "Serial"


def test_modbus_tcp_template_sets_tcp_and_valid_fields():
    cfg = protocol_template_settings("modbus_tcp", "Serial")
    _header, fields = cfg["frame_rules"].split("|", 1)

    assert cfg["net_proto"] == "Serial"
    parsed = binproto.parse_field_spec(fields)
    assert [item[0] for item in parsed] == [
        "事务ID", "协议ID", "长度", "单元ID", "功能码",
    ]


def test_at_template_sets_text_crlf_and_ascii():
    cfg = protocol_template_settings("at", "TCP Client")

    assert cfg["net_proto"] == "TCP Client"
    assert cfg["rx_hex"] is False
    assert cfg["append_newline"] is True
    assert cfg["append_nl_mode"] == 0
    assert cfg["line_split"] is True
    assert cfg["encoding"] == "ascii"


def test_fixed_header_template_fields_are_parseable():
    cfg = protocol_template_settings("fixed_header", "UDP")
    header, fields = cfg["frame_rules"].split("|", 1)

    assert binproto.parse_hex_header(header) == b"\xAA\x55"
    assert len(binproto.parse_field_spec(fields)) == 3
    assert cfg["plot_mode"] == 2
    assert cfg["dash_mode"] == 2


def test_text_templates_keep_selected_transport():
    assert protocol_template_settings("delimiter", "UDP")["net_proto"] == "UDP"
    assert protocol_template_settings("raw", "TCP Server")["net_proto"] == "TCP Server"


def test_recommendations_are_stable_ids():
    assert recommended_connection("modbus_tcp") == "TCP Client"
    assert recommended_connection("at", "UDP") == "Serial"
    assert recommended_protocol("modbus") == "modbus_rtu"
    assert recommended_protocol("sensor") == "delimiter"
    assert recommended_protocol("network") == "raw"
    assert recommended_device_connection("network") == "TCP Client"
    assert recommended_device_connection("sensor", "UDP") == "Serial"
    assert recommended_device_connection("custom", "UDP") == "UDP"
    assert recommended_views("fixed_header")["hex"] is True
    assert recommended_views("delimiter")["hex"] is False
