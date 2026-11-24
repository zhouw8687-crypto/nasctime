#!/usr/bin/env python3
"""Pair application sequence numbers with captures from the competition scenario."""

import argparse
import csv
import struct
from contextlib import redirect_stdout
from pathlib import Path

from ladder_kpis import APP_SIGNALS, collect_flows, load_vectors, report_flows


PAIRS = [
    ("server.app[0]", "ue[0].app[0]"),
    ("server.app[1]", "ue[0].app[1]"),
]
CLASSES = {6200: ("control", 46), 6202: ("background", 0)}
CAPTURES = (
    ("upf_n6_rx_ns", "upf-n6.pcap", False),
    ("upf_n3_tx_ns", "upf-n3.pcap", True),
    ("ne1_egress_ns", "ne1-egress.pcap", True),
    ("ne5_ingress_ns", "ne5-ingress.pcap", True),
    ("ne5_to_gnb_ns", "ne5-to-gnb.pcap", True),
)


def ipv4_udp(packet, start):
    if len(packet) < start + 28 or packet[start] >> 4 != 4 or packet[start + 9] != 17:
        return None
    udp = start + (packet[start] & 15) * 4
    if len(packet) < udp + 8:
        raise ValueError("Truncated UDP header")
    port = struct.unpack_from("!H", packet, udp + 2)[0]
    return port, packet[start + 1] >> 2, packet[udp + 8:]


def packet_identity(frame, protocol, tunneled):
    if protocol == 1:
        if frame[12:14] != b"\x08\x00":
            return None  # ARP and other Ethernet control traffic
        start = 14
    elif protocol == 101:
        start = 0
    else:
        raise ValueError(f"Unsupported capture link type {protocol}")
    header = ipv4_udp(frame, start)
    if header is None:
        return None
    port, dscp, payload = header
    if tunneled:
        if port != 31:
            return None
        if len(payload) < 8 or struct.unpack_from("!I", payload)[0] != 8:
            raise ValueError("Unexpected Simu5G GtpUserMsg serialization")
        inner = ipv4_udp(payload, 8)
        if inner is None:
            raise ValueError("Expected an inner IPv4 UDP application packet")
        port, _, payload = inner
    if port not in CLASSES:
        return None
    if len(payload) < 8:
        raise ValueError("Missing ApplicationPacket length and sequence")
    return (port, struct.unpack_from("!I", payload, 4)[0]), dscp


def read_capture(path, tunneled):
    timestamps = {}
    with path.open("rb") as handle:
        header = handle.read(24)
        if len(header) != 24 or header[:4] != b"\x4d\x3c\xb2\xa1":
            raise ValueError(f"{path}: expected a nanosecond little-endian PCAP")
        protocol = struct.unpack_from("<I", header, 20)[0]
        while record := handle.read(16):
            seconds, nanos, size, original = struct.unpack("<IIII", record)
            frame = handle.read(size)
            if len(frame) != size or size != original:
                raise ValueError(f"{path}: truncated packet")
            value = packet_identity(frame, protocol, tunneled)
            if value is None:
                continue
            key, dscp = value
            if key in timestamps or dscp != CLASSES[key[0]][1]:
                raise ValueError(f"{path}: repeated sequence or unexpected DSCP for {key}")
            timestamps[key] = seconds * 1_000_000_000 + nanos
    if not timestamps:
        raise ValueError(f"{path}: no experiment packets captured")
    return timestamps


def write_trace(directory, vectors):
    networks = {
        module.split(".", 1)[0]
        for module, signal in vectors
        if signal == "packetSent:vector(packetBytes)"
    }
    if len(networks) != 1:
        raise ValueError("Expected one network with sender vectors")
    (network,) = networks
    captures = {
        field: read_capture(directory / filename, tunneled)
        for field, filename, tunneled in CAPTURES
    }
    with (directory / "packet-trace.csv").open("w", encoding="utf-8", newline="") as handle:
        table = csv.writer(handle)
        table.writerow([
            "flow", "udp_dst_port", "seq", "server_tx_ns",
            *captures, "ue_rx_ns", "first_unobserved",
        ])
        expected = set()
        for source, _, sent, delivery, duplicates in collect_flows(vectors, network, PAIRS):
            if duplicates:
                raise ValueError(f"{source}: unexpectedly received duplicate application packets")
            port = 6200 if source == PAIRS[0][0] else 6202
            for seq, (time, _, _) in enumerate(sent):
                key = (port, seq)
                expected.add(key)
                received_ns = round((time + delivery[seq][0]) * 1e9) if seq in delivery else None
                events = {field: samples.get(key) for field, samples in captures.items()}
                events["ue_rx_ns"] = received_ns
                missing = next((name for name, stamp in events.items() if stamp is None), "")
                stamps = list(events.values())
                first = next((i for i, value in enumerate(stamps) if value is None), len(stamps))
                if any(value is not None for value in stamps[first:]):
                    raise ValueError(f"{key}: later stage observed after a missing capture")
                sent_ns = round(time * 1e9)
                observed = [sent_ns, *stamps[:first]]
                if any(a > b for a, b in zip(observed, observed[1:])):
                    raise ValueError(f"{key}: nonmonotonic timestamps")
                table.writerow([CLASSES[port][0], port, seq, sent_ns, *stamps, missing])
        if any(samples.keys() - expected for samples in captures.values()):
            raise ValueError("Capture contains an unpaired application sequence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    directory = parser.parse_args().result_dir
    (vector,) = directory.glob("*.vec")
    vectors = load_vectors(vector, lambda _, name: name in APP_SIGNALS)
    write_trace(directory, vectors)
    with (directory / "flows.csv").open("w", encoding="utf-8", newline="") as handle:
        with redirect_stdout(handle):
            report_flows(vectors, 0.2, 1.6, [0.6, 1.0], PAIRS)


if __name__ == "__main__":
    main()
