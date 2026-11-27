#!/usr/bin/env python3
"""Extract endpoint cohorts, per-slot MAC allocation, NE queue and pcap evidence."""

import argparse
import collections
import csv
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ladder_kpis import APP_SIGNALS, collect_flows, load_vectors, percentile


NETWORK = "Qfi17ControlledLadder"
WINDOWS = {"all": (0.1, 1.3), "pre": (0.1, 0.4), "burst": (0.4, 0.9), "post": (0.9, 1.3)}
DRAIN_END = 4.0
DEADLINE_MS = 20
FLOWS = {
    "control": ("server.app[0]", "ue[0].app[0]", 240),
    "video": ("server.app[1]", "ue[0].app[1]", 300),
    "radio_competitor": ("gnb1.app[0]", "ue[1].app[0]", 1250),
    "wired_background": ("NE1.app[0]", "NE3.app[0]", 1000),
}
MAC = {
    "cell": "controlledDlAllocatedBlocks",
    "ue0": "ue0DlAllocatedBlocks",
    "ue1": "ue1DlAllocatedBlocks",
}
QUEUES = {
    f"NE1.eth[{port}].queue.queue[{index}]": (branch, index)
    for port, branch in enumerate(("detour", "left"))
    for index in range(3)
}
LENGTH = "queueLength:vector"
DROP = "droppedPacketLengthsQueueOverflow:vector"
PCAPS = {
    "left": "ne1-egress.pcap",
    "detour": "ne1-detour.pcap",
    "detour_tail": "ne6-to-ne5.pcap",
}


def include(module, name):
    local = module.removeprefix(f"{NETWORK}.")
    return (name in APP_SIGNALS or name in MAC.values()
            or (local in QUEUES and name in {LENGTH, DROP}))


def extract_flows(meta, vectors):
    pairs = [(source, sink) for source, sink, _ in FLOWS.values()]
    observed = {
        source: (sent, delivered, duplicates)
        for source, _, sent, delivered, duplicates in collect_flows(vectors, NETWORK, pairs)
    }
    for name, (source, _, total) in FLOWS.items():
        sent, delivered, duplicates = observed.get(source, ([], {}, {}))
        if name == "radio_competitor" and meta["radio"] == "0":
            total = 0
        if name == "wired_background" and meta["wired"] == "0":
            total = 0
        if len(sent) != total:
            raise ValueError(f"{meta}: {name} sent {len(sent)} packets, expected {total}")
        for label, (start, stop) in WINDOWS.items():
            sequences = [i for i, (time, _, _) in enumerate(sent) if start <= time < stop]
            received = [delivered[i] for i in sequences if i in delivered]
            delays = [delay * 1000 for delay, _ in received]
            on_time = sum(delay <= DEADLINE_MS for delay in delays)
            yield dict(meta, flow=name, window=label, sent=len(sequences), delivered=len(received),
                       undelivered=len(sequences) - len(received), on_time_20ms=on_time,
                       on_time_pct=100 * on_time / len(sequences) if sequences else "",
                       p99_delivered_ms=percentile(delays, .99) if delays else "",
                       goodput_mbps=sum(size for _, size in received) * 8e-6 / (stop - start),
                       duplicates=sum(duplicates.get(i, 0) for i in sequences),
                       last_rx_ms=max((1000 * (sent[i][0] + delivered[i][0])
                                       for i in sequences if i in delivered), default=""))


def extract_mac(meta, vectors):
    module = f"{NETWORK}.gnb1.cellularNic.mac.schedulerDl"
    series = {key: vectors[(module, name)] for key, name in MAC.items()}
    if not series["cell"] or len({len(vec) for vec in series.values()}) != 1:
        raise ValueError(f"{meta}: missing MAC allocation samples")
    cap = int(meta["bands"])
    last_positive = {
        key: max((time * 1000 for time, _, value in vec if value > 0), default="")
        for key, vec in series.items()
    }
    for cell, ue0, ue1 in zip(series["cell"], series["ue0"], series["ue1"]):
        if cell[:2] != ue0[:2] or cell[:2] != ue1[:2] or cell[2] != ue0[2] + ue1[2] or cell[2] > cap:
            raise ValueError(f"{meta}: inconsistent allocation at {cell}")

    for label, (start, stop) in WINDOWS.items():
        for key, vec in series.items():
            blocks = [int(value) for time, _, value in vec if start <= time < stop]
            if not blocks:
                raise ValueError(f"{meta}: no MAC slots in {label}")
            yield dict(meta, scope=key, window=label, slots=len(blocks),
                       blocks=sum(blocks), peak=max(blocks),
                       positive_slots=sum(b > 0 for b in blocks),
                       full_budget_slots=sum(b == cap for b in blocks), last_positive_slot_ms=last_positive[key])


def queue_stats(lengths, start, stop):
    """Integrate sample-and-hold occupancy including the state entering the window."""
    old_value = 0
    old_time = start
    peak = 0
    area = 0.0
    for time, _, value in lengths:
        if time < start:
            old_value = value
        elif time < stop:
            if time > old_time:
                peak = max(peak, old_value)
            peak = max(peak, value)
            area += (time - old_time) * old_value
            old_time, old_value = time, value
        else:
            break
    if stop > old_time:
        peak = max(peak, old_value)
    area += (stop - old_time) * old_value
    return int(peak), area / (stop - start)


def extract_queues(meta, vectors):
    for module, (branch, index) in QUEUES.items():
        lengths = vectors[(f"{NETWORK}.{module}", LENGTH)]
        drops = vectors[(f"{NETWORK}.{module}", DROP)]
        for label, (start, stop) in WINDOWS.items():
            peak, mean = queue_stats(lengths, start, stop)
            yield dict(meta, branch=branch, queue=index, window=label, peak_packets=peak,
                       mean_packets=mean, overflow_packets=sum(start <= t < stop for t, _, _ in drops))


def udp_frames(data):
    """Read the untagged Ethernet/IPv4 UDP frames recorded by this INET scenario."""
    if not data:  # INET writes a zero-byte file if the interface had no events.
        return
    endian, resolution = {
        b"\xd4\xc3\xb2\xa1": ("<", 10**6), b"\xa1\xb2\xc3\xd4": (">", 10**6),
        b"\x4d\x3c\xb2\xa1": ("<", 10**9), b"\xa1\xb2\x3c\x4d": (">", 10**9),
    }[data[:4]]
    link_type, = struct.unpack_from(endian + "I", data, 20)
    if link_type != 1:
        raise ValueError(f"Expected Ethernet pcap, got link type {link_type}")
    offset = 24
    while offset < len(data):
        sec, frac, size, _ = struct.unpack_from(endian + "4I", data, offset)
        offset += 16
        frame = data[offset:offset + size]
        offset += size
        if len(frame) != size:
            raise ValueError("Truncated pcap frame")
        if frame[12:14] != b"\x08\x00" or frame[23] != 17:
            continue
        if int.from_bytes(frame[20:22], "big") & 0x3fff:
            raise ValueError("Unexpected IPv4 fragmentation")
        udp = 14 + (frame[14] & 15) * 4
        source, dest = struct.unpack_from("!HH", frame, udp)
        dscp = frame[15] >> 2
        yield sec + frac / resolution, source, dest, dscp


def extract_pcap(meta, case, results_hashes):
    windows = {"all": (0, DRAIN_END), "burst": WINDOWS["burst"]}
    for position, filename in PCAPS.items():
        data = (case / filename).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        results_hashes[meta["case"], meta["seed"], position] = digest
        counts = {name: collections.Counter() for name in windows}
        for time, source, dest, dscp in udp_frames(data):
            if source == dest == 31:
                kind = {46: "n3_control", 34: "n3_video"}.get(dscp, "other_n3")
            else:
                kind = {6300: "wired_background", 6400: "local_competitor"}.get(dest, "other_udp")
            for label, (start, stop) in windows.items():
                if start <= time < stop:
                    counts[label][kind] += 1
        for label, counter in counts.items():
            yield dict(meta, position=position, window=label, sha256=digest,
                       **{kind: counter[kind] for kind in
                          ("n3_control", "n3_video", "other_n3", "wired_background",
                           "local_competitor", "other_udp")})


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    with (args.results / "cases.tsv").open(newline="", encoding="utf-8") as file:
        cases = list(csv.DictReader(file, delimiter="\t"))
    if not cases:
        parser.error("cases.tsv contains no finished simulations")

    tables = {name: [] for name in ("flows", "mac", "queues", "pcap")}
    hashes = {}
    for meta in cases:
        case = args.results / f'{meta["case"]}-{meta["seed"]}'
        vector, = case.glob("*.vec")
        with (case / "routes.jsonl").open(encoding="utf-8") as trace:
            paths = {json.loads(line)["path_id"] for line in trace}
        if paths != {meta["path"]}:
            raise ValueError(f"{case}: route readback does not match {meta['path']}")
        vectors = load_vectors(vector, include)
        tables["flows"].extend(extract_flows(meta, vectors))
        tables["mac"].extend(extract_mac(meta, vectors))
        tables["queues"].extend(extract_queues(meta, vectors))
        tables["pcap"].extend(extract_pcap(meta, case, hashes))

    pairs = [("normal", "radio"), ("wired", "both"), ("radio", "radio_bands"),
             ("both", "both_bands"), ("wired_detour", "both_detour"), ("both_detour", "both_actions")]
    tables["paired_pcap"] = [
        dict(seed=seed, case_a=first, case_b=second, position=position,
             identical=int(hashes[first, seed, position] == hashes[second, seed, position]))
        for seed in sorted({case["seed"] for case in cases}, key=int)
        for first, second in pairs
        for position in PCAPS
        if (first, seed, position) in hashes and (second, seed, position) in hashes
    ]
    for name, rows in tables.items():
        if rows:
            write_csv(args.results / f"{name}.csv", rows)


if __name__ == "__main__":
    main()
