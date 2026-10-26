#!/usr/bin/env python3
"""
parse_results.py — Extract per-profile metrics from a sweep results dir.

Produces a tidy CSV with one row per (N, scheduler, rep, endpoint, flow).
Uses the direct .vec parser from vec_parse.py — no scavetool required.

Usage:
    python3 parse_results.py results/sweep_primary > primary.csv
    python3 parse_results.py results/sweep_fading  > fading.csv
    python3 parse_results.py results/sweep_gptp    > gptp.csv
"""

from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

# Direct .vec file parser — no scavetool needed
from vec_parse import vec_stats

# ----------------------------------------------------------------------------
PROFILE_FLOWS = {
    "CLC": [{"name": "clc_hp",  "port": 0, "deadline_ms":   2.0, "qfi": 7}],
    "MV":  [
        {"name": "mv_hp",  "port": 0, "deadline_ms":  10.0, "qfi": 6},
        {"name": "mv_be",  "port": 1, "deadline_ms":  50.0, "qfi": 0},
    ],
    "BLK": [{"name": "blk_be", "port": 0, "deadline_ms": 100.0, "qfi": 0}],
}

STANDARD_MIX = {
    1:  ["CLC"],
    5:  ["CLC", "CLC", "MV", "MV", "BLK"],
    10: ["CLC", "CLC", "CLC", "CLC", "MV", "MV", "MV", "MV", "BLK", "BLK"],
    15: ["CLC"] * 5 + ["MV"] * 5 + ["BLK"] * 5,
    20: ["CLC"] * 7 + ["MV"] * 7 + ["BLK"] * 6,
    30: ["CLC"] * 10 + ["MV"] * 10 + ["BLK"] * 10,
    40: ["CLC"] * 14 + ["MV"] * 14 + ["BLK"] * 12,
}

FNAME_RE = re.compile(
    r"(?P<config>(?P<kind>Sweep|Fade|Gptp)_N(?P<N>\d+))_run(?P<runnum>\d+)\.sca$"
)

PRIMARY_SCHED = ["MAXCI", "PF", "DRR", "MAXCI_COMP", "QOS_PF"]

def primary_attrs(runnum: int) -> tuple[str, int]:
    return PRIMARY_SCHED[runnum // 3], runnum % 3

def fading_attrs(runnum: int) -> tuple[str, str, int]:
    sched = "MAXCI" if runnum < 6 else "QOS_PF"
    fade = "false" if (runnum // 3) % 2 == 0 else "true"
    return sched, fade, runnum % 3

NETWORK_PREFIX = "ExtendedMultiEndpointNetwork"


def sca_get(sca_path: Path, module: str, name: str) -> str | None:
    with sca_path.open() as f:
        for line in f:
            parts = line.split()
            if (len(parts) >= 4 and parts[0] == "scalar"
                and parts[1] == module and parts[2] == name):
                return parts[3]
    return None


def parse_sca_file(sca_path: Path) -> list[dict]:
    m = FNAME_RE.search(sca_path.name)
    if not m:
        return []

    N = int(m.group("N"))
    kind = m.group("kind")
    runnum = int(m.group("runnum"))

    if kind == "Fade":
        sched, fade, rep = fading_attrs(runnum)
    else:
        sched, rep = primary_attrs(runnum)
        fade = ""

    if N not in STANDARD_MIX:
        return []
    profiles = STANDARD_MIX[N]
    rows = []
    vec_path = sca_path.with_suffix(".vec")

    for ep_idx, profile in enumerate(profiles):
        for flow in PROFILE_FLOWS[profile]:
            module = f"{NETWORK_PREFIX}.tsnDeviceB[{ep_idx}].app[{flow['port']}]"
            count = sca_get(sca_path, module, "packetReceived:count")
            stats = vec_stats(vec_path, module, "endToEndDelay")

            # Convert delay seconds -> milliseconds; empty if no data
            def ms(k):
                v = stats.get(k)
                return v * 1000.0 if isinstance(v, (int, float)) else ""

            rows.append({
                "config": sca_path.parent.name,
                "N": N,
                "scheduler": sched,
                "fading": fade,
                "rep": rep,
                "endpoint": ep_idx,
                "profile": profile,
                "flow": flow["name"],
                "qfi": flow["qfi"],
                "deadline_ms": flow["deadline_ms"],
                "received": count or "",
                "delay_samples": stats.get("count", ""),
                "delay_mean_ms": ms("mean"),
                "delay_p99_ms":  ms("p99"),
                "delay_p999_ms": ms("p999"),
                "delay_max_ms":  ms("max"),
            })

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    rdir = Path(args.results_dir)
    if not rdir.is_dir():
        print(f"FAIL: {rdir} not a directory", file=sys.stderr)
        sys.exit(1)

    sca_files = sorted(rdir.glob("*_run*.sca"))
    print(f"Found {len(sca_files)} .sca files in {rdir}", file=sys.stderr)

    all_rows = []
    for i, sca in enumerate(sca_files, 1):
        rows = parse_sca_file(sca)
        all_rows.extend(rows)
        # Report progress every 10 files to reduce noise
        if i % 2 == 0 or i == len(sca_files):
            print(f"  [{i}/{len(sca_files)}] parsed",  file=sys.stderr)

    if not all_rows:
        print("FAIL: no rows extracted", file=sys.stderr)
        sys.exit(1)

    fieldnames = list(all_rows[0].keys())
    out = sys.stdout if args.output == "-" else open(args.output, "w")
    w = csv.DictWriter(out, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
