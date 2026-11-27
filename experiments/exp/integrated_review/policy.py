"""Transmit GCC input samples through a binary report channel within the TCP adapter."""
import argparse
import socket
import struct
from dataclasses import replace
from pathlib import Path

from control_reporting.reporting import HEADER, FRAME_VERSION, DOMAIN_IDS
from domain_coordination.adapter import LadderPolicy, STATE_LIFETIME_NS
from domain_coordination.baseline import Stamp
from ladder_controller import serve

RAN = struct.Struct("!BI")
CORE = struct.Struct("!II")
BRANCHES = ("direct", "detour")


def queue_code(depth, mode):
    if mode == "exact":
        return depth
    if mode == "round8":
        return (depth + 4) // 8
    # Preserve both congestion comparisons used by transport_candidates.
    return int(depth >= 5) + int(depth >= 24)


class ReportingPolicy(LadderPolicy):
    def __init__(self, mode, log):
        super().__init__("full", log)
        self.encoding = mode
        self.last = {}
        self.codec_id = {"exact": 11, "round8": 12, "boundary": 13, "boundary_periodic": 13}[mode]
        self.link = struct.Struct("!?III" if mode == "exact" else "!?BII")

    def exchange(self, domain, now, payload):
        previous = self.last.get(domain)
        send = (self.encoding != "boundary" or previous is None or
                now - previous[0] >= STATE_LIFETIME_NS or payload != previous[1])
        if send:
            wire = HEADER.pack(FRAME_VERSION, self.codec_id, 1, DOMAIN_IDS[domain], now) + payload
            _, _, _, _, source = HEADER.unpack_from(wire)
            self.last[domain] = source, wire[HEADER.size:]
            self.write({"type": "report", "domain": domain, "source_ns": source, "bits": len(wire) * 8})
        source, received = self.last[domain]
        return Stamp(source, source + STATE_LIFETIME_NS), received

    def states(self, obs):
        # Construct local observations before encoding. Only decoded dynamic fields
        # and the common static topology/traffic contract reach solve_full.
        ran, transport, core = super().states(obs)
        now = obs["sim_time_ns"]
        stamp, data = self.exchange("ran", now, RAN.pack(ran.max_bands, ran.mac_backlog_bytes))
        bands, backlog = RAN.unpack(data)
        ran = replace(ran, stamp=stamp, max_bands=bands, mac_backlog_bytes=backlog)
        stamp, data = self.exchange("core", now, CORE.pack(core.offered_video_bps, core.burst_bytes))
        offered, bucket = CORE.unpack(data)
        core = replace(core, stamp=stamp, offered_video_bps=offered, burst_bytes=bucket)
        payload = bytes([BRANCHES.index(transport.current_path)]) + b"".join(
            self.link.pack(path.available, queue_code(path.queued_packets, self.encoding),
                           path.control_queue_bits, path.bottleneck_bps) for path in transport.paths)
        stamp, data = self.exchange("transport", now, payload)
        paths = []
        for path, values in zip(transport.paths, self.link.iter_unpack(data[1:]), strict=True):
            available, code, bits, rate = values
            depth = code
            if self.encoding in ("boundary", "boundary_periodic"):
                depth = (0, 5, 24)[code]
            elif self.encoding == "round8":
                depth = 8 * code
            paths.append(replace(path, available=available, queued_packets=depth,
                                 control_queue_bits=bits, bottleneck_bps=rate))
        return ran, replace(transport, stamp=stamp, current_path=BRANCHES[data[0]], paths=tuple(paths)), core


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("encoding", choices=("exact", "round8", "boundary_periodic", "boundary"))
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    with (args.result / "policy.jsonl").open("x") as log, socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        (args.result / "port").write_text(str(listener.getsockname()[1]))
        serve(listener, ReportingPolicy(args.encoding, log))
