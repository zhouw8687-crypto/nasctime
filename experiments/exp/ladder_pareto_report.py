#!/usr/bin/env python3
"""Plot the measured Pareto experiment and rescore a tighter critical deadline."""

import argparse
import csv
import json
from pathlib import Path

from matplotlib import pyplot as plt

from ladder_pareto_probe import ACTIONS, MIN_CRITICAL_FRACTION, evaluate, resource_cost
from ladder_pareto_replay import metrics, pareto_indices, write_csv


LABELS = {
    "nominal": ("Fixed nominal", "#666666", "x", (6, 7)),
    "full": ("Full report", "#3268a8", "o", (-69, 6)),
    "threshold": ("Threshold", "#5c886d", "s", (6, -14)),
    "manual": ("Hand quantized", "#aa7625", "^", (6, -13)),
    "learned": ("Learned", "#ad4e50", "D", (6, -12)),
}


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def deadline_sensitivity(replay, live_rows):
    for row in live_rows:
        folder = replay / row["workload"] / row["mode"]
        critical = evaluate(folder, critical_deadline_s=.010)["critical"]
        yield {
            "workload": row["workload"], "mode": row["mode"],
            "critical_sent": critical["sent"], "on_time_10ms": critical["on_time"],
            "fraction_10ms": critical["on_time_fraction"],
            "meets_95pct_at_10ms": critical["on_time_fraction"] >= MIN_CRITICAL_FRACTION,
        }


def plot(output, data, summary, live):
    fig, (traffic, frontier) = plt.subplots(1, 2, figsize=(11, 4.35), layout="constrained")
    for row in summary:
        label, color, marker, offset = LABELS[row["mode"]]
        x = float(row["mean_report_bits"])
        y = float(row["mean_background_on_time_mbps"])
        traffic.scatter(x, y, c=color, marker=marker, s=52, zorder=3)
        traffic.annotate(label, (x, y), xytext=offset, textcoords="offset points", fontsize=9, color=color)
    traffic.set(xlim=(-80, 1830), ylim=(.9, 3.4), xlabel="Domain-report bits per workload (five samples)",
                ylabel="Mean timely background goodput (Mbit/s)", title="Communication and live policy performance")
    traffic.grid(alpha=.22)

    # This held-out case illustrates how the codecs disagree at the same nominal history.
    case = next(case for case in data["test"] if case["id"] == "test-04")
    truth = metrics(case["outcomes"])
    cost = [resource_cost(action) for action in ACTIONS]
    guide = sorted({(cost[index], truth[index, 1]) for index in pareto_indices(truth)})
    feasible = [index for index, (critical, _) in enumerate(truth) if critical >= MIN_CRITICAL_FRACTION]
    frontier.scatter([cost[index] for index in feasible], [truth[index, 1] for index in feasible],
                     facecolors="none", edgecolors="#767f89", s=34, label="Feasible configurations")
    if guide:
        frontier.plot(*zip(*guide), c="#253239", lw=1.1, ls="--", label="Reference Pareto front")
    for mode in ("full", "learned"):
        selected = next(row for row in live if row["workload"] == case["id"] and row["mode"] == mode)
        label, color, marker, _ = LABELS[mode]
        frontier.scatter(float(selected["resource_cost"]), float(selected["background_on_time_mbps"]),
                         c=color, marker=marker, s=54, zorder=4, label=label)
    frontier.set(xlabel="Radio + gate reservation (normalized)", ylabel="Timely background goodput (Mbit/s)",
                 title="Held-out workload test-04")
    frontier.legend(loc="center right", fontsize=8, frameon=False)
    frontier.grid(alpha=.22)
    fig.savefig(output, dpi=200)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("replay_dir", type=Path)
    args = parser.parse_args()
    replay = args.replay_dir
    data = json.loads(args.oracle.read_text(encoding="utf-8"))
    live = read_csv(replay / "replay.csv")
    write_csv(replay / "deadline-sensitivity.csv", list(deadline_sensitivity(replay, live)))
    plot(replay / "pareto-results.png", data, read_csv(replay / "summary.csv"), live)


if __name__ == "__main__":
    main()
