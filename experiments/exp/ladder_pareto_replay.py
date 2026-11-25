#!/usr/bin/env python3
"""Replay compressed observations and execute the chosen policy in OMNeT++."""

import argparse
import concurrent.futures
import csv
import json
import socket
import subprocess
from pathlib import Path
from time import perf_counter_ns

import numpy as np

from ladder_pareto_codec import DOMAINS, LearnedCodec, features, reporter, scale
from ladder_pareto_probe import ACTIONS, MIN_CRITICAL_FRACTION, REPO, TICKS_NS, resource_cost, run_case


MODES = ("nominal", "full", "threshold", "manual", "learned")
MAX_RESOURCE_COST = 1.22
EPSILON = 1e-12
COSTS = np.array([resource_cost(action) for action in ACTIONS])
NOMINAL_INDEX = ACTIONS.index((20_000_000, 600, 4))


def metrics(outcomes):
    if [tuple(row["action"]) for row in outcomes] != list(ACTIONS):
        raise ValueError("Oracle action order does not match the replay catalog")
    return np.array([
        (row["scores"]["critical"]["on_time_fraction"], row["scores"]["background"]["on_time_mbps"])
        for row in outcomes
    ])


def pareto_indices(values):
    eligible = np.flatnonzero(values[:, 0] >= MIN_CRITICAL_FRACTION - EPSILON)
    return frozenset(
        int(index) for index in eligible
        if not any(
            values[other, 1] >= values[index, 1] - EPSILON and COSTS[other] <= COSTS[index] + EPSILON
            and (values[other, 1] > values[index, 1] + EPSILON or COSTS[other] < COSTS[index] - EPSILON)
            for other in eligible
        )
    )


def select(values, front):
    constrained = [index for index in front if COSTS[index] <= MAX_RESOURCE_COST + EPSILON]
    if constrained:
        return max(constrained, key=lambda index: (values[index, 1], -COSTS[index], -index))
    # A missing feasible prediction still results in a concrete, bounded action.
    return max(np.flatnonzero(COSTS <= MAX_RESOURCE_COST + EPSILON),
               key=lambda index: (values[index, 0], values[index, 1], -COSTS[index], -index))


def feature_history(case):
    observations = case["observations"]
    return [features(case, observations[:count]) for count in range(1, len(observations) + 1)]


class GlobalPredictor:
    def __init__(self, training_features, teacher_scores):
        self.samples = np.array([scale(vector) for vector in training_features])
        self.scores = teacher_scores

    def predict(self, observations):
        distance = np.mean((self.samples - scale(observations)) ** 2, axis=(1, 2))
        matching = np.argsort(distance, kind="stable")[:3]
        weights = 1 / (distance[matching] + .005)
        return np.average(self.scores[matching], axis=0, weights=weights)


def run_replay(case, root, mode, predictor, learned):
    folder = root / case["id"] / mode
    history = []
    decision_duration_us = []
    predicted_front = frozenset()
    selected = None
    reports = reporter(mode, learned) if mode != "nominal" else None

    sender, receiver = socket.socketpair()
    with sender, receiver:
        def decide(obs):
            nonlocal predicted_front, selected
            history.append(obs)
            start = perf_counter_ns()
            if reports is not None:
                reports.exchange(sender, receiver, obs["request_id"], features(case, history))
            if obs["sim_time_ns"] != TICKS_NS[-1]:
                decision_duration_us.append((perf_counter_ns() - start) / 1000)
                return None
            if mode == "nominal":
                selected = NOMINAL_INDEX
            else:
                prediction = predictor.predict(reports.state)
                predicted_front = pareto_indices(prediction)
                selected = select(prediction, predicted_front)
            decision_duration_us.append((perf_counter_ns() - start) / 1000)
            return ACTIONS[selected]

        measured = run_case(case, folder, decide)

    truth = metrics(case["outcomes"])
    true_front = pareto_indices(truth)
    oracle = select(truth, true_front)
    if measured["scores"] != case["outcomes"][selected]["scores"]:
        raise ValueError(f"{folder}: live execution did not reproduce the selected oracle-grid configuration")
    if measured["observations"] != case["observations"]:
        raise ValueError(f"{folder}: the live execution input changed from the reference")
    with (folder / "control.jsonl").open(encoding="utf-8") as stream:
        events = [json.loads(line) for line in stream]
    wall_us = [row["wait_wall_us"] for row in events if row["type"] == "received_decision"][-1]
    act_rate, act_window, act_bands = ACTIONS[selected]
    critical = measured["scores"]["critical"]
    bg = measured["scores"]["background"]
    budget_ok = COSTS[selected] <= MAX_RESOURCE_COST + EPSILON
    oracle_ok = truth[oracle, 0] >= MIN_CRITICAL_FRACTION - EPSILON
    sla_met = critical["on_time_fraction"] >= MIN_CRITICAL_FRACTION - EPSILON
    return {
        "workload": case["id"], "mode": mode, "seed": case["seed"], "burst_gap_us": case["burst_gap_us"],
        "ue_x_m": case["ue_x_m"], "link_mbps": case["link_mbps"],
        "core_bps": act_rate, "priority_window_us": act_window, "dl_bands": act_bands,
        "critical_sent": critical["sent"], "critical_on_time": critical["on_time"],
        "sla_met": sla_met, "background_sent": bg["sent"], "background_on_time": bg["on_time"],
        "background_on_time_mbps": bg["on_time_mbps"],
        "resource_cost": measured["resource_cost"], "resource_budget_met": bool(budget_ok),
        "oracle_action_index": int(oracle),
        "oracle_background_on_time_mbps": float(truth[oracle, 1]),
        "oracle_sla_feasible": bool(oracle_ok),
        "background_regret_mbps": float(truth[oracle, 1] - bg["on_time_mbps"]) if oracle_ok and sla_met and budget_ok else "",
        "chosen_on_front": selected in true_front,
        "true_front_size": len(true_front), "predicted_front_size": len(predicted_front),
        "front_recall": len(predicted_front & true_front) / len(true_front) if true_front and reports else "",
        "report_frames": reports.frames if reports else 0,
        "report_bits": reports.bits if reports else 0,
        "oldest_domain_report_ms": (int(max(history[-1]["request_id"] - reports.sample_ids)) * 20
                                    if reports else ""),
        "decision_local_us": decision_duration_us[-1],
        "bridge_wait_wall_us": wall_us,
    }


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def aggregate(results):
    def mean(rows, name):
        values = [row[name] for row in rows if row[name] != ""]
        return float(np.mean(values)) if values else ""

    for mode in MODES:
        rows = [row for row in results if row["mode"] == mode]
        yield {
            "mode": mode, "workloads": len(rows),
            "sla_met_cases": sum(row["sla_met"] for row in rows),
            "critical_on_time_fraction": sum(row["critical_on_time"] for row in rows) /
                                        sum(row["critical_sent"] for row in rows),
            "mean_background_on_time_mbps": mean(rows, "background_on_time_mbps"),
            "mean_resource_cost": mean(rows, "resource_cost"),
            "oracle_feasible_cases": sum(row["oracle_sla_feasible"] for row in rows),
            "mean_background_regret_mbps": mean(rows, "background_regret_mbps"),
            "actual_selected_on_front_cases": sum(row["chosen_on_front"] for row in rows),
            "mean_front_recall": mean(rows, "front_recall"),
            "mean_report_bits": mean(rows, "report_bits"),
            "mean_report_frames": mean(rows, "report_frames"),
            "p99_decision_local_us": float(np.percentile([row["decision_local_us"] for row in rows], 99)),
            "p99_bridge_wait_wall_us": float(np.percentile([row["bridge_wait_wall_us"] for row in rows], 99)),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    root = args.result_dir.resolve()
    root.mkdir()
    revision = subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"], text=True)
    status = subprocess.check_output(["git", "-C", REPO, "status", "--porcelain"], text=True)
    (root / "revision.txt").write_text(revision + status, encoding="utf-8")

    data = json.loads(args.oracle.read_text(encoding="utf-8"))
    if len(data["train"]) < 3 or not data["test"]:
        raise ValueError("Need at least three training workloads and a held-out workload")
    histories = np.array([feature_history(case) for case in data["train"]])
    scores = np.array([metrics(case["outcomes"]) for case in data["train"]])
    normalized_labels = scores.copy()
    normalized_labels[:, :, 1] /= max(1, float(scores[:, :, 1].max()))
    labels = normalized_labels.reshape(len(histories), -1)
    predictor = GlobalPredictor(histories[:, -1], scores)
    learned = [LearnedCodec(domain, histories, labels) for domain in range(len(DOMAINS))]
    with (root / "codec.json").open("w", encoding="utf-8") as handle:
        json.dump({name: {"weights": c.weights.tolist(), "centers": c.centers.tolist()}
                   for name, c in zip(DOMAINS, learned, strict=True)}, handle, indent=2)

    for case in data["test"]:
        (root / case["id"]).mkdir()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_replay, case, root, mode, predictor, learned)
                   for case in data["test"] for mode in MODES]
        results = [future.result() for future in futures]
    write_csv(root / "replay.csv", results)
    write_csv(root / "summary.csv", list(aggregate(results)))
    print((root / "summary.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
