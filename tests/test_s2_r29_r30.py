# -*- coding: utf-8 -*-
"""Qt-free tests for S-2 R29/R30 (validate_open / parse_baud / max_lines)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import connection_presets as cp
import config_io as cio


def _ok_ip(ip):
    return bool(ip) and ip.count(".") == 3


def _ok_local(ip):
    return ip in ("0.0.0.0", "127.0.0.1")


def _ok_mcast(ip):
    try:
        a = int(str(ip).split(".")[0])
    except (ValueError, IndexError):
        return False
    return 224 <= a <= 239


def _v(proto, fields):
    return cp.validate_open(
        proto, fields,
        is_valid_ip=_ok_ip,
        is_local_ipv4=_ok_local,
        is_multicast_ipv4=_ok_mcast,
    )


def test_parse_baud_and_serial_open():
    assert cp.parse_baud("115200") == 115200
    assert cp.parse_baud("0") is None
    assert cp.parse_baud("x") is None
    assert _v("Serial", {"port": "", "baud": "9600"})["toast"] == "err_no_port"
    assert _v("Serial", {"port": "COM3", "baud": "bad"})["toast"] == "err_bad_baud"
    ok = _v("Serial", {"port": "COM3", "baud": "9600"})
    assert ok["ok"] and ok["port"] == "COM3" and ok["baud"] == 9600


def test_validate_open_network():
    assert _v("Virtual", {})["ok"] is True
    bad = _v("TCP Server", {"local_ip": "8.8.8.8", "local_port": "80"})
    assert bad["dialog"][0] == "err_not_local_ip_title"
    assert _v("TCP Client", {"remote_ip": "bad", "remote_port": "80"})["toast"] == "err_bad_ip"
    assert _v("TCP Client", {"remote_ip": "1.2.3.4", "remote_port": "0"})["toast"] == "err_bad_port"
    ok = _v("TCP Client", {"remote_ip": "1.2.3.4", "remote_port": "80"})
    assert ok["ok"] and ok["ip"] == "1.2.3.4" and ok["port"] == 80
    assert _v("UDP Multicast", {
        "local_ip": "0.0.0.0", "local_port": "5000", "group": "10.0.0.1",
    })["toast"] == "err_not_multicast"
    m = _v("UDP Multicast", {
        "local_ip": "0.0.0.0", "local_port": "5000", "group": "239.0.0.1",
    })
    assert m["ok"] and m["group"] == "239.0.0.1"
    u = _v("UDP", {
        "local_ip": "0.0.0.0", "local_port": "8080", "use_remote": False,
    })
    assert u["ok"] and u["rip"] == "" and u["rport"] == 0
    ur = _v("UDP", {
        "local_ip": "0.0.0.0", "local_port": "8080", "use_remote": True,
        "remote_ip": "1.2.3.4", "remote_port": "9",
    })
    assert ur["ok"] and ur["rip"] == "1.2.3.4" and ur["rport"] == 9


def test_clamp_max_lines():
    assert cio.clamp_max_lines(50) == 100
    assert cio.clamp_max_lines(2_000_000) == 1_000_000
    assert cio.clamp_max_lines("5000") == 5000
    assert cio.clamp_max_lines("x", default=10000) == 10000
