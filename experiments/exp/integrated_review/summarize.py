"""Audit all live decisions and summarize endpoint outcomes by sending cohort."""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from dual_ue.extract import extract_flows, include, load_vectors


def summarize(case, scheduler, seed, codec):
    trace = [json.loads(line) for line in (case / "routes.jsonl").read_text().splitlines()]
    log = [json.loads(line) for line in (case / "policy.jsonl").read_text().splitlines()]
    obs = [r for r in trace if r["type"] == "observation"]
    decisions = [r for r in log if r["type"] == "policy"]
    acks = [r for r in trace if r["type"] == "ack"]
    commands = [r["decision"] for r in trace if r["type"] == "received_decision"]
    if len(obs) != 56:
        raise ValueError(f"{case}: expected 56 ticks")
    for o, d, cmd, ack in zip(obs, decisions, commands, acks, strict=True):
        action = d["action"]
        target = o if action is None else action
        if (len({r["request_id"] for r in (o, d, cmd, ack)}) != 1 or cmd["action"] != action
                or ack["status"] != ("noop" if action is None else "applied")
                or any(ack[k] != target[k] for k in ("path_id", "ran_bands", "upf_video_rate_bps"))):
            raise ValueError(f"{case}: unexpected control transaction")
    bits = Counter()
    for item in log:
        if item["type"] == "report":
            bits[item["domain"]] += item["bits"]
    vector, = case.glob("*.vec")
    flows = list(extract_flows({"radio": "1", "wired": "1"}, load_vectors(vector, include)))
    burst = {r["flow"]: r for r in flows if r["window"] == "burst"}
    switched = [a["sim_time_ns"] / 1e6 for a, o in zip(acks, obs) if a["path_id"] != o["path_id"]]
    return dict(scheduler=scheduler, seed=seed, codec=codec, control_on_time=burst["control"]["on_time_20ms"],
                video_mbps=round(burst["video"]["goodput_mbps"], 6), video_on_time=burst["video"]["on_time_20ms"],
                competitor_delivered=burst["radio_competitor"]["delivered"],
                no_candidate=sum(d["selected"] is None for d in decisions),
                path_changes_ms=" ".join(f"{t:g}" for t in switched),
                uplink_bits=sum(bits.values()), uplink_bps=round(sum(bits.values()) / 1.12, 2),
                **{k+"_bits": bits[k] for k in ("ran", "transport", "core")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    modes = ["exact", "round8", "boundary"]
    if any(args.results.glob("*-boundary_periodic")):
        modes.insert(2, "boundary_periodic")
    rows = [summarize(args.results / f"{scheduler}-{seed}-{mode}", scheduler, seed, mode)
            for scheduler in ("MAXCI", "PF") for seed in range(5)
            for mode in modes]
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
