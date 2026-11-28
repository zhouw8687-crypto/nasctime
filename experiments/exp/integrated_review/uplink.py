"""Versioned uplink codecs and simulation-time delivery of independent reports."""

from collections import deque
from dataclasses import dataclass
import struct
from typing import Protocol

from control_reporting.reporting import DOMAIN_IDS, FRAME_VERSION, HEADER


BRANCHES = ("direct", "detour")
MODES = ("exact", "round8", "boundary_periodic", "boundary")
RAN = struct.Struct("!BI")
CORE = struct.Struct("!II")


@dataclass(frozen=True)
class RanReport:
    max_bands: int
    mac_backlog_bytes: int


@dataclass(frozen=True)
class LinkReport:
    available: bool
    queued_packets: int
    control_queue_bits: int
    bottleneck_bps: int


@dataclass(frozen=True)
class TransportReport:
    current_path: str
    paths: tuple[LinkReport, ...]  # Direct, detour.


@dataclass(frozen=True)
class CoreReport:
    offered_video_bps: int
    burst_bytes: int
    max_ip_rate_bps: int = 3_000_000


Report = RanReport | TransportReport | CoreReport
REPORT_TYPES = {"ran": RanReport, "transport": TransportReport, "core": CoreReport}


class Encoder(Protocol):
    def encode(self, domain: str, report: Report) -> bytes: ...


class Decoder(Protocol):
    def decode(self, domain: str, payload: bytes) -> Report: ...


@dataclass(frozen=True)
class Codec:
    codec_id: int
    version: int
    encoder: Encoder
    decoder: Decoder

    def __post_init__(self):
        if any(type(value) is not int or not 1 <= value <= 255
               for value in (self.codec_id, self.version)):
            raise ValueError("Codec ID and version must be nonzero bytes")


@dataclass(frozen=True)
class LadderPayload:
    encoding: str

    @property
    def link(self):
        return struct.Struct("!?III" if self.encoding == "exact" else "!?BII")

    def queue_code(self, depth):
        if self.encoding == "exact":
            return depth
        if self.encoding == "round8":
            return (depth + 4) // 8
        # Preserve both congestion comparisons used by transport_candidates.
        return int(depth >= 5) + int(depth >= 24)

    def queue_depth(self, code):
        if self.encoding == "exact":
            return code
        if self.encoding == "round8":
            return 8 * code
        return (0, 5, 24)[code]

    def encode(self, domain, report):
        if domain == "ran":
            return RAN.pack(report.max_bands, report.mac_backlog_bytes)
        if domain == "core":
            if report.max_ip_rate_bps != 3_000_000:
                raise ValueError("Legacy uplink requires a preconfigured 3 Mbit/s UPF cap")
            return CORE.pack(report.offered_video_bps, report.burst_bytes)
        link = self.link
        return bytes([BRANCHES.index(report.current_path)]) + b"".join(
            link.pack(path.available, self.queue_code(path.queued_packets),
                      path.control_queue_bits, path.bottleneck_bps)
            for path in report.paths
        )

    def decode(self, domain, payload):
        if domain == "ran":
            return RanReport(*RAN.unpack(payload))
        if domain == "core":
            return CoreReport(*CORE.unpack(payload))
        link = self.link
        if len(payload) != 1 + len(BRANCHES) * link.size:
            raise ValueError("Unexpected transport payload length")
        paths = tuple(
            LinkReport(available, self.queue_depth(code), bits, rate)
            for available, code, bits, rate in link.iter_unpack(payload[1:])
        )
        return TransportReport(BRANCHES[payload[0]], paths)


def builtin_codec(mode):
    encoding = "boundary" if mode == "boundary_periodic" else mode
    codec_id = {"exact": 11, "round8": 12, "boundary": 13}[encoding]
    payload = LadderPayload(encoding)
    return Codec(codec_id, 1, payload, payload)


@dataclass(frozen=True)
class Received:
    source_ns: int
    arrival_ns: int
    report: Report


class ReportChannel:
    def __init__(self, codec, delay_ns, ttl_ns, refresh_ns=None):
        if delay_ns < 0 or ttl_ns <= 0 or (refresh_ns is not None and refresh_ns <= 0):
            raise ValueError("Require nonnegative delay and positive TTL/refresh")
        self.codec = codec
        self.delay_ns = delay_ns
        self.ttl_ns = ttl_ns
        self.refresh_ns = refresh_ns
        self.sent = {}
        self.pending = deque()
        self.received = {}
        self.last_tick_ns = -1

    def tick(self, now_ns, reports):
        if now_ns <= self.last_tick_ns:
            raise ValueError("Report ticks must be strictly increasing")
        if reports.keys() != DOMAIN_IDS.keys():
            raise ValueError("Each report tick must provide all three domains")
        self.last_tick_ns = now_ns
        events = []
        for domain, report in reports.items():
            payload = self.codec.encoder.encode(domain, report)
            if not isinstance(payload, bytes):
                raise ValueError("Encoder must return serialized bytes")
            previous = self.sent.get(domain)
            if self.refresh_ns is None:
                reason = "periodic"
            elif previous is None:
                reason = "initial"
            elif payload != previous[1]:
                reason = "changed"
            elif now_ns - previous[0] >= self.refresh_ns:
                reason = "refresh"
            else:
                continue
            header = HEADER.pack(FRAME_VERSION, self.codec.codec_id, self.codec.version,
                                 DOMAIN_IDS[domain], now_ns)
            wire = header + payload
            arrival_ns = now_ns + self.delay_ns
            self.sent[domain] = now_ns, payload
            self.pending.append((arrival_ns, domain, wire))
            events.append(dict(type="report", domain=domain, reason=reason, source_ns=now_ns,
                               arrival_ns=arrival_ns, bits=len(wire) * 8, wire_hex=wire.hex()))

        while self.pending and self.pending[0][0] <= now_ns:
            arrival_ns, domain, wire = self.pending.popleft()
            version, codec_id, codec_version, domain_id, source_ns = HEADER.unpack_from(wire)
            if (version, codec_id, codec_version, domain_id) != (
                FRAME_VERSION, self.codec.codec_id, self.codec.version, DOMAIN_IDS[domain]
            ):
                raise ValueError("Unrecognized report frame header")
            report = self.codec.decoder.decode(domain, wire[HEADER.size:])
            if not isinstance(report, REPORT_TYPES[domain]):
                raise ValueError(f"Decoder returned an incompatible {domain} report")
            if domain == "transport" and (report.current_path not in BRANCHES or
                    len(report.paths) != len(BRANCHES) or
                    any(not isinstance(path, LinkReport) for path in report.paths)):
                raise ValueError("Invalid decoded transport path set")
            self.received[domain] = Received(source_ns, arrival_ns, report)
        return events

    def view(self, now_ns):
        """Return fresh reports and audit status at the current decision tick."""
        if now_ns != self.last_tick_ns:
            raise ValueError("Read the report view at the current decision tick")
        fresh = {}
        status = {}
        for domain in DOMAIN_IDS:
            received = self.received.get(domain)
            if received is None:
                status[domain] = dict(status="missing", source_ns=None, arrival_ns=None, age_ns=None)
                continue
            age_ns = now_ns - received.source_ns
            live = age_ns < self.ttl_ns
            status[domain] = dict(status="fresh" if live else "expired",
                                  source_ns=received.source_ns, arrival_ns=received.arrival_ns,
                                  age_ns=age_ns)
            if live:
                fresh[domain] = received
        return fresh, status
