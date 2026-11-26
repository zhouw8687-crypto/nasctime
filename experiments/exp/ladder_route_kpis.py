#!/usr/bin/env python3
"""Report routed downlink metrics by sending-time cohort."""

import argparse
import csv
import json
import sys
from pathlib import Path

from ladder_kpis import APP_SIGNALS, collect_flows, load_vectors, percentile


def summarize(case, deadline_ms):
    with (case / "routes.jsonl").open(encoding="utf-8") as trace:
        initial = json.loads(next(trace))
    vector_file, = case.glob("*.vec")
    vectors = load_vectors(vector_file, lambda _, name: name in APP_SIGNALS)
    pairs = [(f"server.app[{index}]", f"ue[0].app[{index}]") for index in range(2)]
    flows = list(collect_flows(vectors, "Qfi17ControlledLadder", pairs))
    if len(flows) != len(pairs):
        raise ValueError(f"{case}: missing a sender vector")
    burst = (0.6, 1.1) if case.name.endswith("Shifted") else (0.4, 0.9)

    for flow, (_, _, sent, delivery, _) in zip(("control", "video"), flows):
        windows = [("all", (0.1, 1.3)), ("preburst", (0.1, burst[0])), ("burst", burst)]
        for window, (start, end) in windows:
            cohort = [seq for seq, (time, _, _) in enumerate(sent) if start <= time < end]
            samples = [delivery[seq] for seq in cohort if seq in delivery]
            delays_ms = [delay * 1000 for delay, _ in samples]
            on_time = sum(delay <= deadline_ms for delay in delays_ms)
            goodput_mbps = sum(size for _, size in samples) * 8 / (end - start) / 1e6
            yield [
                case.name, initial["path_id"], initial.get("ran_bands", ""),
                initial.get("upf_video_rate_bps", ""), flow, window, len(cohort), len(samples),
                on_time, f"{100 * on_time / len(cohort):.3f}",
                f"{percentile(delays_ms, .99):.3f}" if delays_ms else "", f"{goodput_mbps:.6f}",
            ]


def calibrate(rows):
    """Enumerate feasible fixed profiles and keep the phase-specific Pareto fronts."""
    fields = (
        "case", "path_id", "ran_bands", "upf_video_rate_bps", "flow", "window",
        "sent", "delivered", "on_time", "on_time_pct", "p99_delivered_ms", "goodput_mbps",
    )
    grid = {}
    for row in rows:
        values = dict(zip(fields, row))
        if values["case"].startswith("grid-"):
            grid[values["case"], values["window"], values["flow"]] = values
    cases = sorted({case for case, _, _ in grid})
    if len(cases) != 8:
        raise ValueError("calibration requires all eight fixed candidates")
    profiles = {}
    for window in ("preburst", "burst"):
        feasible = []
        for case in cases:
            control = grid[case, window, "control"]
            video = grid[case, window, "video"]
            if control["on_time"] * 100 < 99 * control["sent"]:
                continue
            path = video["path_id"]
            feasible.append({
                "case": case, "path_id": path, "ran_bands": video["ran_bands"],
                "upf_video_rate_bps": video["upf_video_rate_bps"],
                "branch_links": {"direct": 2, "detour": 4}[path],
                "video_goodput_mbps": float(video["goodput_mbps"]),
            })

        def objectives(candidate):
            return (-candidate["video_goodput_mbps"], candidate["ran_bands"], candidate["branch_links"])

        def dominates(a, b):
            left, right = objectives(a), objectives(b)
            return left != right and all(x <= y for x, y in zip(left, right))

        front = [candidate for candidate in feasible if not any(dominates(other, candidate) for other in feasible)]
        if not front:
            raise ValueError(f"{window}: no candidate satisfies the control SLA")
        profiles[window] = {"front": front, "selected": min(front, key=objectives)}
    return profiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--deadline-ms", type=float, default=20)
    parser.add_argument("--write-policy", type=Path, help="write phase profiles from the complete fixed grid")
    args = parser.parse_args()
    if not 0 < args.deadline_ms < float("inf"):
        parser.error("deadline must be finite and positive")
    cases = sorted(path.parent for path in args.results.glob("*/routes.jsonl"))
    if not cases:
        parser.error("no route control traces found in results directory")
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow([
        "case", "initial_path", "initial_bands", "initial_video_cap_bps", "flow", "window",
        "sent", "delivered", "on_time", "on_time_pct", "p99_delivered_ms", "goodput_mbps",
    ])
    rows = [row for case in cases for row in summarize(case, args.deadline_ms)]
    writer.writerows(rows)
    if args.write_policy:
        profiles = calibrate(rows)
        args.write_policy.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
