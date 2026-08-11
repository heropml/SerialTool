# -*- coding: utf-8 -*-
"""Unit tests for CommTool._recorder_link_snapshot PCAP eligibility."""
from __future__ import print_function

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

_APP = QApplication.instance() or QApplication([])


def _quiet(monkeypatch):
    from main_window import CommTool, PortScannerThread
    monkeypatch.setattr(CommTool, "_setup_tray", lambda self: None)
    monkeypatch.setattr(PortScannerThread, "start", lambda self: None)
    monkeypatch.setattr(CommTool, "_info_dlg", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "toast", lambda *a, **k: None)
    monkeypatch.setattr(CommTool, "_confirm_dlg", lambda *a, **k: True)


def _window(monkeypatch, tmp_path, profile="link-snap"):
    _quiet(monkeypatch)
    from main_window import CommTool
    ini = tmp_path / ("%s.ini" % profile)
    monkeypatch.setattr(
        CommTool, "_settings_file",
        staticmethod(lambda profile="": str(ini)))
    w = CommTool(profile)
    w.settings = QSettings(str(ini), QSettings.IniFormat)
    return w


def test_recorder_link_tcp_server_single_client(monkeypatch, tmp_path):
    from main_window import PROTO_TCP_SERVER
    w = _window(monkeypatch, tmp_path, "srv-link")
    w._conn_proto = PROTO_TCP_SERVER
    w.cb_proto.setCurrentText(PROTO_TCP_SERVER)
    w.cb_local_ip.setCurrentText("0.0.0.0")
    w.ed_local_port.setText("9000")
    monkeypatch.setattr(w, "_send_target", lambda: "192.168.1.50:50123")
    monkeypatch.setattr(
        "main_window.resolve_export_local_ipv4",
        lambda configured, remote_ip=None, remote_port=None: "10.0.0.5")
    link = w._recorder_link_snapshot()
    assert link is not None
    assert link["proto"] == PROTO_TCP_SERVER
    assert link["remote_ip"] == "192.168.1.50"
    assert link["remote_port"] == 50123
    assert link["local_ip"] == "10.0.0.5"
    assert link["local_port"] == 9000
    w._close_all_sessions()


def test_recorder_link_tcp_server_wildcard_unresolved(monkeypatch, tmp_path):
    from main_window import PROTO_TCP_SERVER
    w = _window(monkeypatch, tmp_path, "srv-wild")
    w._conn_proto = PROTO_TCP_SERVER
    w.cb_proto.setCurrentText(PROTO_TCP_SERVER)
    w.cb_local_ip.setCurrentText("0.0.0.0")
    w.ed_local_port.setText("9000")
    monkeypatch.setattr(w, "_send_target", lambda: "192.168.1.50:50123")
    monkeypatch.setattr(
        "main_window.resolve_export_local_ipv4",
        lambda *a, **k: None)
    assert w._recorder_link_snapshot() is None
    w._close_all_sessions()


def test_recorder_link_udp_multicast_resolves_wildcard(monkeypatch, tmp_path):
    from main_window import PROTO_UDP_MULTICAST
    w = _window(monkeypatch, tmp_path, "mcast-wild")
    w._conn_proto = PROTO_UDP_MULTICAST
    w.cb_proto.setCurrentText(PROTO_UDP_MULTICAST)
    w.ed_group.setText("239.1.2.3")
    w.ed_local_port.setText("5000")
    w.cb_local_ip.setCurrentText("0.0.0.0")
    monkeypatch.setattr(
        "main_window.resolve_export_local_ipv4",
        lambda configured, remote_ip=None, remote_port=None: "192.168.0.20")
    link = w._recorder_link_snapshot()
    assert link is not None
    assert link["local_ip"] == "192.168.0.20"
    assert link["remote_ip"] == "239.1.2.3"
    w._close_all_sessions()


def test_recorder_link_tcp_server_all_clients_rejected(monkeypatch, tmp_path):
    from main_window import PROTO_TCP_SERVER
    w = _window(monkeypatch, tmp_path, "srv-all")
    w._conn_proto = PROTO_TCP_SERVER
    w.cb_proto.setCurrentText(PROTO_TCP_SERVER)
    monkeypatch.setattr(w, "_send_target", lambda: "__all__")
    assert w._recorder_link_snapshot() is None
    monkeypatch.setattr(w, "_send_target", lambda: None)
    assert w._recorder_link_snapshot() is None
    w._close_all_sessions()


def test_recorder_link_udp_multicast(monkeypatch, tmp_path):
    from main_window import PROTO_UDP_MULTICAST
    w = _window(monkeypatch, tmp_path, "mcast-link")
    w._conn_proto = PROTO_UDP_MULTICAST
    w.cb_proto.setCurrentText(PROTO_UDP_MULTICAST)
    w.ed_group.setText("239.1.2.3")
    w.ed_local_port.setText("5000")
    w.cb_local_ip.setCurrentText("10.0.0.8")
    link = w._recorder_link_snapshot()
    assert link is not None
    assert link["proto"] == PROTO_UDP_MULTICAST
    assert link["remote_ip"] == "239.1.2.3"
    assert link["remote_port"] == 5000
    assert link["local_ip"] == "10.0.0.8"
    assert link["local_port"] == 5000
    w._close_all_sessions()


def test_recorder_link_serial_rejected(monkeypatch, tmp_path):
    from main_window import PROTO_SERIAL
    w = _window(monkeypatch, tmp_path, "ser-link")
    w._conn_proto = PROTO_SERIAL
    w.cb_proto.setCurrentText(PROTO_SERIAL)
    assert w._recorder_link_snapshot() is None
    w._close_all_sessions()


def test_record_stream_tx_tracks_tcp_server_target(monkeypatch, tmp_path):
    from main_window import PROTO_TCP_SERVER
    w = _window(monkeypatch, tmp_path, "srv-tx-link")
    w._conn_proto = PROTO_TCP_SERVER
    w._recorder.start(link={
        "proto": PROTO_TCP_SERVER,
        "local_ip": "0.0.0.0", "local_port": 9000,
        "remote_ip": "192.168.1.50", "remote_port": 50123,
    })
    w._record_stream_tx(b"other", source="192.168.1.51:50124")
    assert w._recorder.link is None
    w._close_all_sessions()
