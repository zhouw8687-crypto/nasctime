#!/usr/bin/env python3
"""Join source and N6 packet outcomes and summarize fixed core admission cases."""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dual_ue.extract import (
    FLOWS, NETWORK, WINDOWS, extract_mac, extract_pcap, extract_queues, include, write_csv,
)
from ladder_kpis import collect_flows, load_vectors, percentile


N6 = f"{NETWORK}.upf.dnPpp.ingressTC"
ADMITTED = "admissionAdmittedPacketBytes"
DROPPED = "admissionDroppedPacketBytes"
RATE_VECTORS = ("admissionConfiguredBps", "admissionCapacityBps", "admissionEnforcedBps")
PHASES = dict(WINDOWS, early=(0.4, 0.55), overlap=(0.55, 0.8), late=(0.8, 0.9))


def extract_rates(meta, vectors, trace):
    tracks = [vectors[N6, signal] for signal in RATE_VECTORS]
    if not tracks[0] or len({len(track) for track in tracks}) != 1:
        raise ValueError("Missing rate or capacity vectors")
    states = []
    rows = []
    for configured, cap, enforced in zip(*tracks):
        time, event, req = configured
        if cap[:2] != (time, event) or enforced[:2] != (time, event):
            raise ValueError("Rate vectors disagree on time or event")
        capacity = cap[2]
        if enforced[2] != min(req, capacity):
            raise ValueError("Enforcement does not match request/capacity minimum")
        states.append((time, event, int(req), int(capacity), int(enforced[2])))
        rows.append(dict(meta, time_ms=time * 1000, configured_bps=int(req),
                         capacity_bps=int(capacity), enforced_bps=int(enforced[2])))

    acks = []
    for entry in trace:
        if entry["type"] not in ("observation", "ack"):
            continue
        req = entry["upf_video_rate_bps"]
        cap = entry["upf_video_capacity_bps"]
        enforced = entry["upf_video_enforced_bps"]
        if entry["path_id"] != meta["path"] or enforced != min(req, cap):
            raise ValueError(f"Unexpected actuator readback: {entry}")
        if entry["type"] == "observation":
            point = entry["core"]
            if point["offered_video_packets"] != point["admitted_video_packets"] + point["dropped_video_packets"]:
                raise ValueError("Inconsistent N6 observation counters")
        elif entry["status"] == "applied":
            acks.append((entry["sim_time_ns"], req, cap, enforced))
    expected_acks = [(460_000_000, 600_000, 800_000, 600_000),
                     (600_000_000, 3_500_000, 800_000, 800_000),
                     (940_000_000, 1_500_000, 3_000_000, 1_500_000)]
    if acks != (expected_acks if meta["online"] == "1" else []):
        raise ValueError(f"Unexpected TCP command acknowledgements: {acks}")
    return states, rows


def join_video(sent, vectors):
    classified = sorted(
        (time, event, accepted, int(size))
        for accepted, signal in ((True, ADMITTED), (False, DROPPED))
        for time, event, size in vectors[N6, signal]
    )
    if len(classified) != len(sent):
        raise ValueError("N6 classification count differs from source video count")
    for (n6_time, _, _, n6_bytes), (source_time, _, payload_bytes) in zip(classified, sent):
        if not 0 <= n6_time - source_time <= .001 or n6_bytes != payload_bytes + 28:
            raise ValueError("Source and N6 video packet do not match on time or size")
    return classified


def state_range(states, start, stop, column):
    active = next(state for state in reversed(states) if state[0] <= start)
    return [active[column], *(s[column] for s in states if start < s[0] < stop)]


def extract_flows(meta, vectors, states):
    specs = dict(FLOWS)
    specs["video"] = (*FLOWS["video"][:2], int(meta["video_packets"]))
    pairs = [(source, sink) for source, sink, _ in specs.values()]
    observed = {
        source: (sent, delivered, duplicates)
        for source, _, sent, delivered, duplicates in collect_flows(vectors, NETWORK, pairs)
    }
    flow_rows = []
    core_rows = []
    for name, (source, _, expected) in specs.items():
        if (name == "radio_competitor" and meta["radio"] == "0"
                or name == "wired_background" and meta["wired"] == "0"):
            expected = 0
        sent, delivered, duplicates = observed.get(source, ([], {}, {}))
        if len(sent) != expected or duplicates:
            raise ValueError(f"Unexpected source or duplicate count for {source}")
        outcomes = join_video(sent, vectors) if name == "video" else []
        if name == "video" and any(not outcomes[seq][2] for seq in delivered):
            raise ValueError("An N6-rejected video packet was received at the endpoint")

        for label, (start, stop) in PHASES.items():
            seqs = [i for i, (time, _, _) in enumerate(sent) if start <= time < stop]
            received = [delivered[i] for i in seqs if i in delivered]
            delays = [1000 * delay for delay, _ in received]
            on_time = sum(delay <= 20 for delay in delays)
            flow_rows.append(dict(meta, flow=name, window=label, sent=len(seqs), delivered=len(received),
                                  on_time_20ms=on_time, sla_99=on_time * 100 >= 99 * len(seqs)
                                  if name == "control" and seqs else "",
                                  p99_delivered_ms=percentile(delays, .99) if delays else "",
                                  goodput_mbps=sum(size for _, size in received) * 8e-6 / (stop - start)))
            if name == "video":
                n6 = [outcomes[i] for i in seqs]
                rates = {}
                for column, key in enumerate(("configured", "capacity", "enforced"), start=2):
                    values = state_range(states, start, stop, column)
                    rates[f"{key}_min_bps"] = min(values)
                    rates[f"{key}_max_bps"] = max(values)
                core_rows.append(dict(meta, window=label, offered_packets=len(seqs),
                                      source_payload_mbps=sum(sent[i][2] for i in seqs) * 8e-6 / (stop - start),
                                      offered_ip_bytes=sum(size for _, _, _, size in n6),
                                      admitted_packets=sum(accepted for _, _, accepted, _ in n6),
                                      dropped_packets=sum(not accepted for _, _, accepted, _ in n6),
                                      admitted_ip_bytes=sum(size for _, _, accepted, size in n6 if accepted),
                                      **rates))
    return flow_rows, core_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    with (args.results / "cases.tsv").open(newline="", encoding="utf-8") as file:
        cases = list(csv.DictReader(file, delimiter="\t"))
    if not cases:
        parser.error("cases.tsv lists no finished simulations")

    tables = {name: [] for name in ("rates", "flows", "core", "mac", "queues", "pcap")}
    for meta in cases:
        case = args.results / f'{meta["case"]}-{meta["seed"]}'
        vector, = case.glob("*.vec")
        with (case / "routes.jsonl").open(encoding="utf-8") as file:
            trace = [json.loads(line) for line in file]
        vectors = load_vectors(vector, lambda mod, signal: mod == N6 or include(mod, signal))
        try:
            states, rates = extract_rates(meta, vectors, trace)
            flow, core = extract_flows(meta, vectors, states)
            captures = list(extract_pcap(meta, case, {}))
            admitted = next(row["admitted_packets"] for row in core if row["window"] == "all")
            branch = "left" if meta["path"] == "direct" else "detour_tail"
            n3 = next(row for row in captures if row["position"] == branch and row["window"] == "all")
            if n3["n3_control"] != 240 or n3["local_competitor"] or n3["n3_video"] > admitted:
                raise ValueError("N3 capture is inconsistent with core accounting")
            if (meta["wired"] == "0" or branch == "detour_tail") and admitted != n3["n3_video"]:
                raise ValueError("Admitted video packets disappeared on an uncongested branch")
            tables["mac"].extend(extract_mac(meta, vectors))
            tables["queues"].extend(extract_queues(meta, vectors))
        except ValueError as exc:
            raise ValueError(f"{case.name}: {exc}") from exc
        for name, rows in (("rates", rates), ("flows", flow), ("core", core), ("pcap", captures)):
            tables[name].extend(rows)

    for name, rows in tables.items():
        write_csv(args.results / f"{name}.csv", rows)


if __name__ == "__main__":
    main()