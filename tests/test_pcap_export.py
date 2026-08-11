# -*- coding: utf-8 -*-
"""PCAP export unit tests (Qt-free)."""
import os
import struct
import tempfile
import unittest

import pcap_export
import rec_replay


class PcapExportTests(unittest.TestCase):
    @staticmethod
    def _frames(data):
        frames = []
        off = 24
        while off + 16 <= len(data):
            incl = struct.unpack_from("<I", data, off + 8)[0]
            off += 16
            frames.append(data[off:off + incl])
            off += incl
        return frames

    def test_rejects_serial_and_server(self):
        self.assertFalse(pcap_export.can_export_link({"proto": "Serial"}))
        self.assertFalse(pcap_export.can_export_link({"proto": "TCP Server"}))
        self.assertFalse(pcap_export.can_export_link({
            "proto": "UDP", "remote_ip": "", "remote_port": 502}))
        with self.assertRaises(pcap_export.PcapExportError):
            pcap_export.normalize_link({"proto": "UDP Multicast"})

    def test_tcp_client_roundtrip_payloads(self):
        link = {
            "proto": "TCP Client",
            "local_ip": "192.168.1.2",
            "local_port": 50000,
            "remote_ip": "192.168.1.10",
            "remote_port": 502,
        }
        events = [
            (0.0, "tx", b"\x00\x01\x00\x00\x00\x06\x01\x03\x00\x00\x00\x01"),
            (0.05, "rx", b"\x00\x01\x00\x00\x00\x05\x01\x03\x02\x00\x64"),
        ]
        data = pcap_export.events_to_pcap(events, link, wall_t0=1_700_000_000.0)
        self.assertEqual(struct.unpack_from("<I", data, 0)[0], 0xA1B2C3D4)
        self.assertEqual(struct.unpack_from("<I", data, 20)[0], 1)  # Ethernet
        # Two packets
        off = 24
        payloads = []
        for _ in range(2):
            ts_sec, ts_usec, incl, orig = struct.unpack_from("<IIII", data, off)
            off += 16
            frame = data[off:off + incl]
            off += incl
            self.assertEqual(incl, orig)
            self.assertGreater(ts_sec, 0)
            # Ethernet type IPv4
            self.assertEqual(frame[12:14], b"\x08\x00")
            # IPv4 proto TCP
            self.assertEqual(frame[23], 6)
            # payload after eth(14)+ipv4(20)+tcp(20)
            payloads.append(frame[54:])
        self.assertEqual(payloads[0], events[0][2])
        self.assertEqual(payloads[1], events[1][2])

    def test_udp_directions_swap_ports(self):
        link = {
            "proto": "UDP",
            "local_ip": "10.0.0.1",
            "local_port": 9000,
            "remote_ip": "10.0.0.2",
            "remote_port": 9001,
        }
        events = [(0.0, "tx", b"ping"), (0.1, "rx", b"pong")]
        data = pcap_export.events_to_pcap(events, link)
        off = 24
        ports = []
        for _ in range(2):
            incl = struct.unpack_from("<I", data, off + 8)[0]
            off += 16
            frame = data[off:off + incl]
            off += incl
            self.assertEqual(frame[23], 17)  # UDP
            sport, dport = struct.unpack_from("!HH", frame, 34)
            ports.append((sport, dport))
            payloads_off = 14 + 20 + 8
            # already checked via sport/dport
        self.assertEqual(ports[0], (9000, 9001))
        self.assertEqual(ports[1], (9001, 9000))

    def test_ctrec_header_keeps_link_for_offline_export(self):
        link = {
            "proto": "TCP Client",
            "local_ip": "127.0.0.1",
            "local_port": 40001,
            "remote_ip": "127.0.0.1",
            "remote_port": 1502,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_tx(b"ABC", t=1.0)
        rec.on_rx(b"XYZ", t=1.2)
        rec.stop()
        path = os.path.join(tempfile.mkdtemp(), "net.ctrec")
        rec.save(path)
        events, header = rec_replay.load(path)
        self.assertEqual(header.get("link", {}).get("proto"), "TCP Client")
        out = os.path.join(tempfile.mkdtemp(), "net.pcap")
        n = pcap_export.export_pcap_file(
            out, events, header["link"], wall_t0=header.get("wall_t0"))
        self.assertEqual(n, 2)
        self.assertGreater(os.path.getsize(out), 24)

    def test_empty_events_fail(self):
        link = {
            "proto": "TCP Client",
            "remote_ip": "1.2.3.4",
            "remote_port": 80,
        }
        with self.assertRaises(pcap_export.PcapExportError) as ctx:
            pcap_export.events_to_pcap([], link)
        self.assertIn("no events", str(ctx.exception))

    def test_all_empty_payloads_fail_distinctly(self):
        link = {
            "proto": "TCP Client",
            "remote_ip": "1.2.3.4",
            "remote_port": 80,
        }
        with self.assertRaises(pcap_export.PcapExportError) as ctx:
            pcap_export.events_to_pcap(
                [(0.0, "tx", b""), (0.1, "rx", b"")], link)
        self.assertIn("empty payload", str(ctx.exception))
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "empty.pcap")
            with self.assertRaises(pcap_export.PcapExportError) as ctx2:
                pcap_export.export_pcap_file(
                    out, [(0.0, "tx", b""), (0.1, "rx", b"")], link)
            self.assertIn("empty payload", str(ctx2.exception))

    def test_large_tcp_event_is_segmented_without_data_loss(self):
        link = {
            "proto": "TCP Client",
            "local_ip": "10.0.0.1", "local_port": 40000,
            "remote_ip": "10.0.0.2", "remote_port": 502,
        }
        payload = bytes(range(256)) * 256  # recorder's 65,536-byte chunk
        frames = self._frames(pcap_export.events_to_pcap(
            [(0.0, "tx", payload)], link))
        self.assertEqual(len(frames), 2)
        self.assertEqual(b"".join(frame[54:] for frame in frames), payload)

    def test_max_udp_datagram_is_preserved_and_oversize_rejected(self):
        link = {
            "proto": "UDP",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "10.0.0.2", "remote_port": 9001,
        }
        payload = b"U" * 65507
        frames = self._frames(pcap_export.events_to_pcap(
            [(0.0, "tx", payload)], link))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0][42:], payload)
        with self.assertRaises(pcap_export.PcapExportError):
            pcap_export.events_to_pcap(
                [(0.0, "tx", payload + b"X")], link)

    def test_udp_recording_loses_pcap_eligibility_on_other_peer(self):
        link = {
            "proto": "UDP",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "10.0.0.2", "remote_port": 9001,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"ok", t=1.0, source=("10.0.0.2", 9001))
        self.assertIsNotNone(rec.link)
        rec.on_rx(b"other", t=1.1, source=("10.0.0.3", 9001))
        self.assertIsNone(rec.link)

    def test_udp_recording_loses_pcap_eligibility_without_peer_metadata(self):
        link = {
            "proto": "UDP",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "10.0.0.2", "remote_port": 9001,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"unknown", t=1.0, source=None)
        self.assertIsNone(rec.link)


if __name__ == "__main__":
    unittest.main()
