#!/usr/bin/env python3
"""Summarize per-flow KPI vectors from the supported simulation scenarios.

Windows are sending-time cohorts. A packet sent in a cohort may arrive
during the drain interval, and is still credited to its sending cohort.
Input must retain all sender samples from sequence zero.
"""

import argparse
import bisect
import csv
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path


APP_SIGNALS = {
    "packetSent:vector(packetBytes)",
    "packetReceived:vector(packetBytes)",
    "rcvdPkSeqNo:vector",
    "endToEndDelay:vector",
}
QUEUE = re.compile(r"(.+\.queue)\.queue\[(\d+)\]$")


def load_vectors(path, include):
    names = {}
    vectors = defaultdict(list)
    for line in path.open(encoding="utf-8"):
        parts = line.split()
        if len(parts) == 5 and parts[0] == "vector":
            _, vector_id, module, name, columns = parts
            if include(module, name):
                if columns != "ETV":
                    raise ValueError(f"Unexpected columns {columns} for {module} {name}")
                names[vector_id] = (module, name)
                vectors[names[vector_id]]
        elif len(parts) == 4 and parts[0] in names:
            vector_id, event, time, value = parts
            vectors[names[vector_id]].append((float(time), int(event), float(value)))
    return vectors


def flow_pairs(network):
    if network == "SingleCell_Standalone":
        yield "server.app[0]", "ue[0].app[0]"
    elif network == "CoreNetwork":
        yield "hostA.app[0]", "server.app[0]"
    elif network == "TransportLadder":
        for side in range(2):
            for traffic_class in range(3):
                yield f"access{side + 1}.app[{traffic_class}]", f"core.app[{side * 3 + traffic_class}]"
    elif network == "ProjectBookLadder":
        for side in range(2):
            for traffic_class in range(3):
                flow = side * 3 + traffic_class
                yield f"ue[{side}].app[{traffic_class}]", f"server.app[{flow}]"
                yield f"server.app[{6 + flow}]", f"ue[{side}].app[{3 + traffic_class}]"
    else:
        raise ValueError(f"Unsupported network {network}")


def index_by_event(vector):
    return {(time, event): value for time, event, value in vector}


def collect_flows(vectors, network, pairs=None):
    if pairs is None:
        pairs = flow_pairs(network)
    for source, sink in pairs:
        sent = sorted(vectors.get((f"{network}.{source}", "packetSent:vector(packetBytes)"), []))
        if not sent:
            continue  # T1 intentionally has unused sink applications.
        receiver = f"{network}.{sink}"
        delays = index_by_event(vectors[(receiver, "endToEndDelay:vector")])
        received_bytes = index_by_event(vectors[(receiver, "packetReceived:vector(packetBytes)")])
        sequences = vectors[(receiver, "rcvdPkSeqNo:vector")]
        if not len(sequences) == len(delays) == len(received_bytes):
            raise ValueError(f"{receiver}: receive vectors disagree on the number of samples")
        delivery = {}
        duplicates = defaultdict(int)
        for time, event, number in sorted(sequences):
            seq = int(number)
            if not 0 <= seq < len(sent):
                raise ValueError(f"{receiver}: sequence {seq} outside the sender vector")
            delay = delays[time, event]
            if abs((time - sent[seq][0]) - delay) > 2e-9:
                raise ValueError(f"{source} -> {sink}: sequence {seq} fails timestamp pairing")
            if seq in delivery:
                duplicates[seq] += 1
            else:
                delivery[seq] = (delay, received_bytes[time, event])
        yield source, sink, sent, delivery, duplicates


def percentile(values, q):
    values = sorted(values)
    rank = (len(values) - 1) * q
    index = int(rank)
    other = min(index + 1, len(values) - 1)
    return values[index] + (rank - index) * (values[other] - values[index])


def report_flows(vectors, start, stop, cuts, pairs=None):
    networks = {mod.split(".", 1)[0] for (mod, prop) in vectors if prop.startswith("packetSent:")}
    if len(networks) != 1:
        raise ValueError("Expected one supported network with sender vectors")
    (network,) = networks
    writer = csv.writer(sys.stdout)
    writer.writerow([
        "source", "sink", "window", "start_s", "stop_s", "sent", "delivered", "duplicates",
        "undelivered_pct", "goodput_mbps", "mean_us", "p99_us", "max_us", "p2p_us", "stddev_us",
    ])
    windows = [("all", start, stop)]
    for index in range(math.ceil(stop - start)):
        left = start + index
        windows.append((f"second_{index + 1}", left, min(left + 1, stop)))
    boundaries = [start, *cuts, stop]
    if cuts:
        windows.extend(
            (f"phase_{index + 1}", left, right)
            for index, (left, right) in enumerate(zip(boundaries, boundaries[1:]))
        )

    for source, sink, sent, delivery, duplicates in collect_flows(vectors, network, pairs):
        times = [time for time, _, _ in sent]
        for window, left, right in windows:
            first = bisect.bisect_left(times, left)
            last = bisect.bisect_left(times, right)
            if first == last:
                continue
            sequences = range(first, last)
            samples = [delivery[seq] for seq in sequences if seq in delivery]
            delays = [delay * 1e6 for delay, _ in samples]
            goodput = sum(size for _, size in samples) * 8 / ((right - left) * 1e6)
            if delays:
                latency = [
                    statistics.mean(delays), percentile(delays, .99), max(delays), max(delays) - min(delays),
                    statistics.stdev(delays) if len(delays) > 1 else "",
                ]
            else:
                latency = [""] * 5
            writer.writerow([
                source, sink, window, left, right, last - first, len(samples),
                sum(duplicates[seq] for seq in sequences), (1 - len(samples) / (last - first)) * 100,
                goodput, *latency,
            ])


def report_gates(vectors):
    writer = csv.writer(sys.stdout)
    writer.writerow(["queue", "departures", "outside_open_window"])
    for (module, name), events in sorted(vectors.items()):
        if name != "queueingTime:vector" or not events:
            continue
        queue = QUEUE.fullmatch(module)
        if queue is None:
            raise ValueError(f"Unexpected subqueue path {module}")
        shaper, index = queue.groups()
        gate = sorted(vectors[(f"{shaper}.transmissionGate[{index}]", "gateState:vector")])
        if not gate:
            raise ValueError(f"{module}: no gate-state vector")
        states = [(time, event) for time, event, _ in gate]
        outside = 0
        for time, event, _ in events:
            prior = bisect.bisect_right(states, (time, event)) - 1
            outside += prior < 0 or gate[prior][2] == 0
        writer.writerow([module, len(events), outside])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vector", type=Path)
    parser.add_argument("--start", type=float, default=0.1, help="first sending cohort start in seconds")
    parser.add_argument("--stop", type=float, default=1.7, help="last sending cohort end in seconds")
    parser.add_argument("--cut", action="append", type=float, default=[], help="add a phase boundary in seconds")
    parser.add_argument("--gates", action="store_true", help="report queue departures against gate states instead")
    args = parser.parse_args()
    if args.gates:
        vectors = load_vectors(args.vector, lambda _, n: n in {"queueingTime:vector", "gateState:vector"})
        report_gates(vectors)
    else:
        boundaries = [args.start, *args.cut, args.stop]
        if not all(math.isfinite(x) for x in boundaries) or any(
            a >= b for a, b in zip(boundaries, boundaries[1:])
        ):
            parser.error("expected finite, strictly increasing start/cut/stop times")
        vectors = load_vectors(args.vector, lambda _, n: n in APP_SIGNALS)
        report_flows(vectors, args.start, args.stop, args.cut)


if __name__ == "__main__":
    main()
