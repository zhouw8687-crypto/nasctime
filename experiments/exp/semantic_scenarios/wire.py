"""Observe N3 IP bit-hops on the six instrumented directed links."""

from socket import inet_aton
from struct import unpack_from


DIRECT = ("ne1-egress.pcap", "ne3-to-ne5.pcap")
DETOUR = ("ne1-detour.pcap", "ne2-to-ne4.pcap", "ne4-to-ne6.pcap", "ne6-to-ne5.pcap")
UPF = inet_aton("10.0.0.2")
GNB = inet_aton("10.0.0.49")


def captures(path):
    data = path.read_bytes()
    if not data:
        return
    order, hz = {
        b"\xd4\xc3\xb2\xa1": ("<", 10**6), b"\xa1\xb2\xc3\xd4": (">", 10**6),
        b"\x4d\x3c\xb2\xa1": ("<", 10**9), b"\xa1\xb2\x3c\x4d": (">", 10**9),
    }[data[:4]]
    if unpack_from(order + "I", data, 20)[0] != 1:
        raise ValueError(f"{path}: expected Ethernet pcap")
    offset = 24
    while offset < len(data):
        second, frac, length, _ = unpack_from(order + "4I", data, offset)
        offset += 16
        frame = data[offset:offset + length]
        offset += length
        if len(frame) != length:
            raise ValueError(f"{path}: truncated packet")
        if (len(frame) >= 42 and frame[12:14] == b"\x08\x00" and frame[23] == 17
                and frame[26:34] == UPF + GNB):
            udp = 14 + (frame[14] & 15) * 4
            if unpack_from("!HH", frame, udp) == (31, 31):
                yield second + frac / hz, frame[15] >> 2, unpack_from("!H", frame, 16)[0]


def measure_wire(case, start, stop):
    total_bits = 0
    left_video = 0
    detour_video = 0
    for name in (*DIRECT, *DETOUR):
        packets = [(dscp, size) for time, dscp, size in captures(case / name) if start <= time < stop]
        total_bits += sum(size for _, size in packets) * 8
        if name == DIRECT[-1]:
            left_video = sum(dscp == 34 for dscp, _ in packets)
        if name == DETOUR[-1]:
            detour_video = sum(dscp == 34 for dscp, _ in packets)
    return dict(n3_ip_bit_hops=total_bits, left_tail_video=left_video, detour_tail_video=detour_video)
