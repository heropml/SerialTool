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

    def test_rejects_serial_and_incomplete(self):
        self.assertFalse(pcap_export.can_export_link({"proto": "Serial"}))
        self.assertFalse(pcap_export.can_export_link({"proto": "TCP Server"}))
        self.assertTrue(pcap_export.can_export_link({
            "proto": "TCP Server",
            "local_ip": "10.0.0.1", "local_port": 9000,
        }))
        self.assertFalse(pcap_export.can_export_link({
            "proto": "UDP", "remote_ip": "", "remote_port": 502}))
        with self.assertRaises(pcap_export.PcapExportError):
            pcap_export.normalize_link({"proto": "UDP Multicast"})

    def test_tcp_server_and_multicast_normalize(self):
        srv = pcap_export.normalize_link({
            "proto": "TCP Server",
            "local_ip": "10.0.0.1",
            "local_port": 9000,
            "remote_ip": "192.168.1.50",
            "remote_port": 50123,
        })
        self.assertEqual(srv["transport"], "tcp")
        self.assertEqual(srv["remote_ip"], "192.168.1.50")
        self.assertEqual(srv["remote_port"], 50123)
        self.assertEqual(srv["local_ip"], "10.0.0.1")
        mcast = pcap_export.normalize_link({
            "proto": "UDP Multicast",
            "local_ip": "192.168.1.10",
            "local_port": 5000,
            "remote_ip": "239.0.0.1",
            "remote_port": 5000,
        })
        self.assertEqual(mcast["transport"], "udp")
        self.assertEqual(mcast["remote_ip"], "239.0.0.1")
        self.assertEqual(mcast["remote_port"], 5000)

    def test_wildcard_local_ip_rejected(self):
        with self.assertRaises(pcap_export.PcapExportError):
            pcap_export.normalize_link({
                "proto": "TCP Server",
                "local_ip": "0.0.0.0",
                "local_port": 9000,
                "remote_ip": "192.168.1.50",
                "remote_port": 50123,
            })
        self.assertFalse(pcap_export.can_export_link({
            "proto": "UDP Multicast",
            "local_ip": "0.0.0.0",
            "local_port": 5000,
            "remote_ip": "239.0.0.1",
            "remote_port": 5000,
        }))

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

    def test_pcapng_magic_and_blocks(self):
        link = {
            "proto": "TCP Client",
            "local_ip": "10.0.0.1", "local_port": 40000,
            "remote_ip": "10.0.0.2", "remote_port": 502,
        }
        events = [(0.0, "tx", b"ABC"), (0.1, "rx", b"XYZ")]
        data = pcap_export.events_to_pcapng(events, link, wall_t0=1_700_000_000.0)
        self.assertEqual(struct.unpack_from("<I", data, 0)[0], 0x0A0D0D0A)
        # Byte-order magic at offset 8 inside SHB
        self.assertEqual(struct.unpack_from("<I", data, 8)[0], 0x1A2B3C4D)
        # Walk blocks: SHB, IDB, then EPBs
        off = 0
        types = []
        while off + 8 <= len(data):
            btype, total = struct.unpack_from("<II", data, off)
            types.append(btype)
            if total < 12 or off + total > len(data):
                break
            off += total
        self.assertEqual(types[0], 0x0A0D0D0A)
        self.assertEqual(types[1], 0x00000001)  # IDB
        self.assertGreaterEqual(types.count(0x00000006), 2)  # EPB

    def test_export_pcap_file_format_from_extension(self):
        link = {
            "proto": "UDP Multicast",
            "local_ip": "10.0.0.1", "local_port": 5000,
            "remote_ip": "239.0.0.1", "remote_port": 5000,
        }
        events = [(0.0, "tx", b"hi")]
        with tempfile.TemporaryDirectory() as td:
            pcap_path = os.path.join(td, "a.pcap")
            ng_path = os.path.join(td, "a.pcapng")
            n1 = pcap_export.export_pcap_file(pcap_path, events, link)
            n2 = pcap_export.export_pcap_file(ng_path, events, link)
            self.assertEqual(n1, 1)
            self.assertEqual(n2, 1)
            with open(pcap_path, "rb") as f:
                self.assertEqual(struct.unpack("<I", f.read(4))[0], 0xA1B2C3D4)
            with open(ng_path, "rb") as f:
                self.assertEqual(struct.unpack("<I", f.read(4))[0], 0x0A0D0D0A)

    def test_tcp_server_frame_direction_and_ports(self):
        link = {
            "proto": "TCP Server",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "192.168.1.50", "remote_port": 50123,
        }
        frames = self._frames(pcap_export.events_to_pcap(
            [(0.0, "tx", b"SRV"), (0.1, "rx", b"CLI")], link))
        self.assertEqual(len(frames), 2)
        # TX from server local:40000-default-or-9000 → client
        sport_tx, dport_tx = struct.unpack_from("!HH", frames[0], 34)
        self.assertEqual((sport_tx, dport_tx), (9000, 50123))
        self.assertEqual(frames[0][54:], b"SRV")
        # RX from client → server
        sport_rx, dport_rx = struct.unpack_from("!HH", frames[1], 34)
        self.assertEqual((sport_rx, dport_rx), (50123, 9000))
        self.assertEqual(frames[1][54:], b"CLI")

    def test_udp_multicast_frame_direction_and_ports(self):
        link = {
            "proto": "UDP Multicast",
            "local_ip": "10.0.0.1", "local_port": 5000,
            "remote_ip": "239.0.0.1", "remote_port": 5000,
            "rx_peer_ip": "10.0.0.9", "rx_peer_port": 40000,
        }
        frames = self._frames(pcap_export.events_to_pcap(
            [(0.0, "tx", b"OUT"), (0.1, "rx", b"IN")], link))
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0][23], 17)  # UDP
        # TX: local → group
        sport_tx, dport_tx = struct.unpack_from("!HH", frames[0], 34)
        self.assertEqual((sport_tx, dport_tx), (5000, 5000))
        self.assertEqual(frames[0][42:], b"OUT")
        self.assertEqual(frames[0][26:30], bytes([10, 0, 0, 1]))
        self.assertEqual(frames[0][30:34], bytes([239, 0, 0, 1]))
        self.assertEqual(frames[0][:6], bytes([1, 0, 94, 0, 0, 1]))
        # RX: sender → group (not group → local)
        sport_rx, dport_rx = struct.unpack_from("!HH", frames[1], 34)
        self.assertEqual((sport_rx, dport_rx), (40000, 5000))
        self.assertEqual(frames[1][42:], b"IN")
        self.assertEqual(frames[1][26:30], bytes([10, 0, 0, 9]))
        self.assertEqual(frames[1][30:34], bytes([239, 0, 0, 1]))
        self.assertEqual(frames[1][:6], bytes([1, 0, 94, 0, 0, 1]))

    def test_udp_multicast_rejects_non_group_remote_ip(self):
        with self.assertRaises(pcap_export.PcapExportError):
            pcap_export.normalize_link({
                "proto": "UDP Multicast",
                "local_ip": "10.0.0.1", "local_port": 5000,
                "remote_ip": "10.0.0.2", "remote_port": 5000,
            })

    def test_tcp_server_recording_keeps_pcap_on_other_client(self):
        link = {
            "proto": "TCP Server",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "192.168.1.50", "remote_port": 50123,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"ok", t=1.0, source="192.168.1.50:50123")
        self.assertIsNotNone(rec.link)
        rec.on_rx(b"other", t=1.1, source="192.168.1.51:50124")
        self.assertIsNotNone(rec.link)
        self.assertNotIn("remote_ip", rec.link)
        self.assertEqual(rec.events.pcap_peers, [
            ("192.168.1.50", 50123), ("192.168.1.51", 50124)])

    def test_tcp_server_multi_client_export_tuples_and_broadcast(self):
        link = {
            "proto": "TCP Server",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "192.168.1.50", "remote_port": 50123,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"A", t=1.0, source="192.168.1.50:50123")
        rec.on_rx(b"B", t=1.1, source="192.168.1.51:50124")
        rec.on_tx(b"toB", t=1.2, source="192.168.1.51:50124")
        rec.on_tx(b"ALL", t=1.3, source="__all__")
        rec.stop()
        self.assertTrue(pcap_export.can_export_link(rec.link))
        self.assertEqual(
            pcap_export.list_export_peers(rec.events, rec.link),
            [("192.168.1.50", 50123), ("192.168.1.51", 50124)])
        frames = self._frames(pcap_export.events_to_pcap(rec.events, rec.link))
        # RX A, RX B, TX toB, broadcast TX → two frames
        self.assertEqual(len(frames), 5)
        ports = [struct.unpack_from("!HH", f, 34) for f in frames]
        payloads = [f[54:] for f in frames]
        src_ip = [tuple(f[26:30]) for f in frames]
        dst_ip = [tuple(f[30:34]) for f in frames]
        self.assertEqual(ports[0], (50123, 9000))
        self.assertEqual(payloads[0], b"A")
        self.assertEqual(src_ip[0], (192, 168, 1, 50))
        self.assertEqual(dst_ip[0], (10, 0, 0, 1))
        self.assertEqual(ports[1], (50124, 9000))
        self.assertEqual(payloads[1], b"B")
        self.assertEqual(src_ip[1], (192, 168, 1, 51))
        self.assertEqual(ports[2], (9000, 50124))
        self.assertEqual(payloads[2], b"toB")
        self.assertEqual(dst_ip[2], (192, 168, 1, 51))
        self.assertEqual(ports[3], (9000, 50123))
        self.assertEqual(payloads[3], b"ALL")
        self.assertEqual(dst_ip[3], (192, 168, 1, 50))
        self.assertEqual(ports[4], (9000, 50124))
        self.assertEqual(payloads[4], b"ALL")
        self.assertEqual(dst_ip[4], (192, 168, 1, 51))
        # Independent TCP seq per flow: both broadcast frames start at seq 1000
        # (client A has only RX so far; client B already sent TX toB).
        seq_a = struct.unpack_from("!I", frames[3], 38)[0]
        seq_b = struct.unpack_from("!I", frames[4], 38)[0]
        self.assertEqual(seq_a, 1000)
        self.assertEqual(seq_b, 1000 + len(b"toB"))

    def test_tcp_server_broadcast_does_not_include_later_clients(self):
        """A broadcast before client B exists must not invent a TX to B."""
        link = {
            "proto": "TCP Server",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "192.168.1.50", "remote_port": 50123,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"A", t=1.0, source="192.168.1.50:50123")
        rec.on_tx(b"ALL", t=1.1, source="__all__")
        rec.on_rx(b"B", t=1.2, source="192.168.1.51:50124")
        rec.stop()
        self.assertEqual(rec.events.pcap_peers[1], "__all__")
        frames = self._frames(pcap_export.events_to_pcap(rec.events, rec.link))
        self.assertEqual(len(frames), 3)
        self.assertEqual([f[54:] for f in frames], [b"A", b"ALL", b"B"])
        self.assertEqual(
            [struct.unpack_from("!HH", f, 34) for f in frames],
            [(50123, 9000), (9000, 50123), (50124, 9000)])

    def test_tcp_server_multi_client_roundtrip_ctrec(self):
        link = {
            "proto": "TCP Server",
            "local_ip": "10.0.0.1", "local_port": 9000,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"A", t=1.0, source="192.168.1.50:50123")
        rec.on_tx(b"ALL", t=1.1, source="__all__",
                  peers=["192.168.1.50:50123", "192.168.1.51:50124"])
        rec.on_rx(b"B", t=1.2, source="192.168.1.51:50124")
        rec.stop()
        with tempfile.TemporaryDirectory() as td:
            record_path = os.path.join(td, "srv.ctrec")
            pcap_path = os.path.join(td, "srv.pcap")
            rec.save(record_path)
            events, header = rec_replay.load(record_path)
            self.assertNotIn("remote_ip", header.get("link") or {})
            self.assertEqual(
                events.pcap_peers[1],
                [["192.168.1.50", 50123], ["192.168.1.51", 50124]])
            n = pcap_export.export_pcap_file(
                pcap_path, events, header["link"])
            # RX A, broadcast×2, RX B
            self.assertEqual(n, 4)
            with open(pcap_path, "rb") as f:
                frames = self._frames(f.read())
        self.assertEqual([f[54:] for f in frames], [b"A", b"ALL", b"ALL", b"B"])
        self.assertEqual(
            [struct.unpack_from("!HH", f, 34) for f in frames],
            [(50123, 9000), (9000, 50123), (9000, 50124), (50124, 9000)])

    def test_tcp_server_legacy_single_peer_without_sidecar(self):
        """Old .ctrec: header remote only, no per-event p — still exports."""
        link = {
            "proto": "TCP Server",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "192.168.1.50", "remote_port": 50123,
        }
        events = [(0.0, "tx", b"SRV"), (0.1, "rx", b"CLI")]
        frames = self._frames(pcap_export.events_to_pcap(events, link))
        self.assertEqual(len(frames), 2)
        self.assertEqual(struct.unpack_from("!HH", frames[0], 34), (9000, 50123))
        self.assertEqual(struct.unpack_from("!HH", frames[1], 34), (50123, 9000))

    def test_multicast_recording_notes_rx_peer(self):
        link = {
            "proto": "UDP Multicast",
            "local_ip": "10.0.0.1", "local_port": 5000,
            "remote_ip": "239.0.0.1", "remote_port": 5000,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"hi", t=1.0, source=("10.0.0.9", 40000))
        self.assertEqual(rec.link.get("rx_peer_ip"), "10.0.0.9")
        self.assertEqual(rec.link.get("rx_peer_port"), 40000)

    def test_multicast_recording_preserves_peer_per_event_after_save(self):
        link = {
            "proto": "UDP Multicast",
            "local_ip": "10.0.0.1", "local_port": 5000,
            "remote_ip": "239.0.0.1", "remote_port": 5000,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"A", t=1.0, source=("10.0.0.9", 40000))
        rec.on_rx(b"B", t=1.1, source=("10.0.0.10", 40001))
        rec.stop()
        with tempfile.TemporaryDirectory() as td:
            record_path = os.path.join(td, "group.ctrec")
            pcap_path = os.path.join(td, "group.pcap")
            rec.save(record_path)
            events, header = rec_replay.load(record_path)
            self.assertNotIn("rx_peer_ip", header["link"])
            self.assertEqual(pcap_export.export_pcap_file(
                pcap_path, events, header["link"]), 2)
            with open(pcap_path, "rb") as f:
                frames = self._frames(f.read())
        self.assertEqual([frame[26:30] for frame in frames], [
            bytes([10, 0, 0, 9]), bytes([10, 0, 0, 10])])

    def test_multicast_recording_loses_pcap_without_sender_metadata(self):
        link = {
            "proto": "UDP Multicast",
            "local_ip": "10.0.0.1", "local_port": 5000,
            "remote_ip": "239.0.0.1", "remote_port": 5000,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_rx(b"unknown", t=1.0, source=None)
        self.assertIsNone(rec.link)

    def test_tcp_server_recording_keeps_pcap_on_other_tx_target(self):
        link = {
            "proto": "TCP Server",
            "local_ip": "10.0.0.1", "local_port": 9000,
            "remote_ip": "192.168.1.50", "remote_port": 50123,
        }
        rec = rec_replay.StreamRecorder()
        rec.start(link=link)
        rec.on_tx(b"other", t=1.0, source="192.168.1.51:50124")
        self.assertIsNotNone(rec.link)
        self.assertEqual(rec.events.pcap_peers, [("192.168.1.51", 50124)])


if __name__ == "__main__":
    unittest.main()
