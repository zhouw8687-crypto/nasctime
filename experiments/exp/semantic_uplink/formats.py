"""Four-byte periodic reporting baselines and normalized learned-codec fields."""

from bisect import bisect_left
from math import expm1, log1p
import struct

from integrated_review.uplink import (
    Codec, CoreReport, LadderPayload, LinkReport, RanReport, TransportReport, builtin_codec,
)


NAMES = ("ran", "transport", "core")
WIDTH = 9
PAYLOAD_BYTES = 4
MAX_RATE = 200_000_000
RATES = tuple(range(0, 21_000_000, 1_000_000)) + tuple(range(25_000_000, 201_000_000, 5_000_000))
NACTIVE = (2, 9, 3)
MASK = tuple(tuple(float(i < count) for i in range(WIDTH)) for count in NACTIVE)
WEIGHT = ((2, 4), (4, 2, 8, 3, 3, 2, 8, 3, 3), (5, 2, 5))


def nearest(value, step, maximum):
    return max(0, min(maximum, (value + step // 2) // step))


def rate_index(value):
    index = bisect_left(RATES, value)
    if index == 0:
        return 0
    if index == len(RATES):
        return index - 1
    return index - 1 if value - RATES[index - 1] < RATES[index] - value else index


def queue_class(depth):
    return int(depth >= 5) + int(depth >= 24)


def split_fields(value, widths):
    result = []
    for width in reversed(widths):
        result.append(value & ((1 << width) - 1))
        value >>= width
    return result[::-1]


class Compact:
    def __init__(self, boundary):
        self.boundary = boundary

    def encode(self, domain, state):
        if domain == "ran":
            if not 0 <= state.max_bands < 256:
                raise ValueError("RAN band count exceeds uint8")
            value = (state.max_bands << 24) | min(0xFFFFFF, state.mac_backlog_bytes)
        elif domain == "core":
            value = (
                (nearest(state.offered_video_bps, 500, 65535) << 16)
                | (nearest(state.burst_bytes, 32, 255) << 8)
                | nearest(state.max_ip_rate_bps, 25_000, 255)
            )
        else:
            value = int(state.current_path == "detour")
            for path in state.paths:
                queue = queue_class(path.queued_packets) if self.boundary else nearest(path.queued_packets, 8, 15)
                for field, width in zip(
                    (int(path.available), queue, nearest(path.control_queue_bits, 1600, 15),
                     rate_index(path.bottleneck_bps)), (1, 4, 4, 6),
                ):
                    value = (value << width) | field
        return struct.pack("!I", value)

    def decode(self, domain, payload):
        value, = struct.unpack("!I", payload)
        if domain == "ran":
            return RanReport(*split_fields(value, (8, 24)))
        if domain == "core":
            rate, bucket, limit = split_fields(value, (16, 8, 8))
            return CoreReport(rate * 500, bucket * 32, limit * 25_000)
        fields = split_fields(value, (1, 1, 4, 4, 6, 1, 4, 4, 6))
        paths = []
        for available, queue, bits, rate in (fields[1:5], fields[5:9]):
            depth = (0, 5, 24)[queue] if self.boundary else 8 * queue
            paths.append(LinkReport(bool(available), depth, 1600 * bits, RATES[rate]))
        return TransportReport(("direct", "detour")[fields[0]], tuple(paths))


def make_fixed():
    payload = Compact(boundary=False)
    return Codec(21, 1, payload, payload)


def make_boundary():
    payload = Compact(boundary=True)
    return Codec(22, 1, payload, payload)


def normalized(domain, state):
    if domain == "ran":
        values = [state.max_bands / 32, log1p(state.mac_backlog_bytes) / log1p(65535)]
    elif domain == "core":
        values = [state.offered_video_bps / 4_000_000, state.burst_bytes / 8192,
                  (int(state.max_ip_rate_bps >= 1_000_000) + int(state.max_ip_rate_bps >= 3_000_000)) / 2]
    else:
        values = [float(state.current_path == "detour")]
        for path in state.paths:
            values.extend((
                float(path.available), queue_class(path.queued_packets) / 2,
                log1p(path.control_queue_bits) / log1p(65535),
                log1p(path.bottleneck_bps) / log1p(MAX_RATE),
            ))
    return [min(1.0, max(0.0, x)) for x in values] + [0.0] * (WIDTH - len(values))


def restored(domain, features):
    if domain == "ran":
        bands, backlog = features[:2]
        return RanReport(round(32 * bands), round(expm1(log1p(65535) * backlog)))
    if domain == "core":
        offered, bucket, maximum = features[:3]
        return CoreReport(round(4_000_000 * offered), round(8192 * bucket),
                          (0, 1_000_000, 3_000_000)[round(2 * maximum)])
    path = "detour" if features[0] >= 0.5 else "direct"
    links = []
    for available, queue, bits, rate in (features[1:5], features[5:9]):
        links.append(LinkReport(
            available >= 0.5, (0, 5, 24)[round(queue * 2)],
            round(expm1(bits * log1p(65535))), round(expm1(rate * log1p(MAX_RATE))),
        ))
    return TransportReport(path, tuple(links))


class ExactExtended:
    """Wide full-state reference for manifests with independently varying UPF caps."""
    def __init__(self):
        self.legacy = LadderPayload("exact")

    def encode(self, domain, state):
        if domain == "core":
            return struct.pack("!III", state.offered_video_bps, state.burst_bytes, state.max_ip_rate_bps)
        return self.legacy.encode(domain, state)

    def decode(self, domain, payload):
        if domain == "core":
            return CoreReport(*struct.unpack("!III", payload))
        return self.legacy.decode(domain, payload)


def make_full(rows):
    if all(row["domains"]["core"]["max_ip_rate_bps"] == 3_000_000 for row in rows):
        return builtin_codec("exact")
    payload = ExactExtended()
    return Codec(11, 2, payload, payload)
