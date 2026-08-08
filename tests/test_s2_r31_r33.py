# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R31-R33 (serial_params / loaders / workspace catalog)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import serial
import serial_params as sp
import project_templates as pt
import config_io as cio


def test_serial_params_maps_and_options():
    assert sp.PARITY_MAP["Even"] == serial.PARITY_EVEN
    assert sp.DATABITS_MAP["8"] == serial.EIGHTBITS
    assert sp.STOPBITS_MAP["1.5"] == serial.STOPBITS_ONE_POINT_FIVE
    assert sp.FLOW_MAP["RTS/CTS"] == "rtscts"
    assert "115200" in sp.BAUD_RATES
    assert sp.PARITY_OPTIONS[0] == "None"
    resolved = sp.resolve_pyserial("8", "Even", "1", "RTS/CTS")
    assert resolved["parity"] == serial.PARITY_EVEN
    assert resolved["flow"] == "rtscts"


def test_workspace_catalog():
    opts = pt.workspace_template_options()
    assert ("project_proto_raw", "raw") in opts
    proto = pt.workspace_tool_entries("protocol")
    assert proto[0][0] == "fb_title"
    assert proto[0][1] == "\u25c7+"
    assert pt.workspace_tool_entries("missing") == ()


def test_parse_json_list_still_ok_for_loaders():
    assert cio.parse_json_list("[]") == []
    assert cio.parse_json_list("") is None
    assert cio.parse_json_list('[{"a":1}]') == [{"a": 1}]
