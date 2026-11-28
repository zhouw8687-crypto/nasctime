"""Train a small multi-output ridge predictor on causal fields and candidate actions."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np

from counterfactual_teacher.dataset import compare
from .release import PREFERENCES, SCALES, read_jsonl, sha, utility, window_steps, write_json

UNSCALED = {"local_control_on_time_percentage_points": 100,
            "burst_control_on_time_percentage_points": 100, **SCALES}
KEYS = tuple(UNSCALED)
ALPHAS = (.05, .5, 5., 50.)
THRESHOLDS = (.35, .50, .65, .80, .90)


def feature_vector(row, candidate):
    ran, trans, core = (row["semantic"][name] for name in ("ran", "transport", "core"))
    action = candidate["action"]
    active = row["active_action"]
    chosen = trans["paths"][action["path_id"]]
    other = trans["paths"]["direct" if action["path_id"] == "detour" else "detour"]
    context = row.get("scenario_context") or {}
    now = row["sim_time_ns"]
    wired_start, wired_stop = context.get("wired_window_ns", (400_000_000, 900_000_000))
    radio_start, radio_stop = context.get("radio_window_ns", (400_000_000, 900_000_000))
    return (
        log_backlog(ran["mac_backlog_bytes"]), ran["max_bands"] / 24,
        (now - ran["source_ns"]) / 40e6, (now - trans["source_ns"]) / 40e6,
        (now - core["source_ns"]) / 40e6,
        chosen["queue_band"] / 2, chosen["control_queue_bits"] / 1e6,
        chosen["available"], chosen["egress_bps"] / 1e8,
        other["queue_band"] / 2, other["control_queue_bits"] / 1e6,
        core["offered_video_bps"] / 2e6, core["burst_bytes"] / 4120,
        (3_000_000 if core.get("capacity_bps") is None else core["capacity_bps"]) / 3e6, row["intent"]["control_bps"] / 3.4e6,
        window_steps(row) / 5,
        action["path_id"] == "detour", action["ran_bands"] / 10,
        action["upf_video_rate_bps"] / 3e6,
        active["path_id"] != action["path_id"], active["ran_bands"] / 10,
        active["upf_video_rate_bps"] / 3e6,
        context.get("wired_bg_dscp", 34) == 46,
        context.get("wired_send_interval_ns", 500_000) / 1e6,
        context.get("radio_competitor_interval_ns", 400_000) / 1e6,
        np.clip((now - wired_start) / 1e8, -1, 1),
        np.clip((wired_stop - now) / 1e8, -1, 1),
        np.clip((now - radio_start) / 1e8, -1, 1),
        np.clip((radio_stop - now) / 1e8, -1, 1),
    )


def log_backlog(value):
    return float(np.log1p(value) / 10)


def truth(candidate):
    outcome, = candidate["outcomes"]
    return outcome


def target(row, candidate):
    item = truth(candidate)
    window = window_steps(row)
    return (
        item["control_on_time_packets"] / item["control_sent_packets"],
        item["control_burst_on_time_packets"] / item["control_burst_sent_packets"],
        item["video_delivered_payload_bits"] / (window * SCALES["video_bits"]),
        item["video_on_time_20ms_packets"] / (window * SCALES["video_on_time"]),
        item["competitor_delivered_payload_bits"] / (window * SCALES["competitor_bits"]),
        item["ran_allocated_blocks"] / (window * SCALES["ran_blocks"]),
        item["transport_branch_bit_hops"] / (window * SCALES["branch_bit_hops"]),
        item["feasible"],
    )


def features(rows):
    return np.array([feature_vector(row, item) for row in rows for item in row["candidates"]], dtype=float)


def arrays(rows):
    return features(rows), np.array([target(row, item) for row in rows for item in row["candidates"]], dtype=float)


def design(values, mean, scale):
    z = np.clip((values - mean) / scale, -6, 6)
    i, j = np.triu_indices(z.shape[1])
    return np.column_stack((np.ones(len(z)), z, z[:, i] * z[:, j]))


def rates(actual, predicted):
    actual = np.asarray(actual, dtype=bool)
    predicted = np.asarray(predicted, dtype=bool)
    tp = int((actual & predicted).sum())
    fp = int((~actual & predicted).sum())
    tn = int((~actual & ~predicted).sum())
    fn = int((actual & ~predicted).sum())
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "false_feasible_among_predicted_feasible": fp / (tp + fp) if tp + fp else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None}


def validation_key(values, target_values, threshold):
    counts = rates(target_values[:, -1], values[:, -1] >= threshold)
    # Fix the relative cost before viewing validation or test outcomes.
    errors = 4 * counts["fp"] + counts["fn"]
    mae = float(np.abs(values[:, :-1] - target_values[:, :-1]).mean())
    return (errors, mae, -threshold)


def fit(train, validation):
    x, y = arrays(train)
    vx, vy = arrays(validation)
    mean = x.mean(axis=0)
    scale = np.maximum(x.std(axis=0), .08)
    train_x = design(x, mean, scale)
    valid_x = design(vx, mean, scale)
    gram = train_x.T @ train_x
    rhs = train_x.T @ y
    identity = np.eye(gram.shape[0])
    identity[0, 0] = 0
    options = []
    for alpha in ALPHAS:
        beta = np.linalg.solve(gram + alpha * identity, rhs)
        valid = clip_predictions(valid_x @ beta)
        for threshold in THRESHOLDS:
            options.append((validation_key(valid, vy, threshold), alpha, threshold, beta))
    _, alpha, threshold, beta = min(options, key=lambda item: item[:3])
    return {"mean": mean, "scale": scale, "beta": beta, "alpha": alpha, "threshold": threshold}


def clip_predictions(raw):
    # Resource and competing traffic may exceed their normalization scales.
    limited = np.maximum(raw, 0)
    limited[:, [0, 1, 2, 3, 7]] = np.minimum(limited[:, [0, 1, 2, 3, 7]], 1)
    return limited


def predict(model, rows):
    x = features(rows)
    return clip_predictions(design(x, model["mean"], model["scale"]) @ model["beta"])


def evaluate(rows, predicted, threshold):
    truth_array = arrays(rows)[1]
    report = {
        "groups": len(rows), "candidates": len(predicted),
        "physical_unit_mae_per_100ms_except_rate_points": {key: float(err * UNSCALED[key]) for key, err in zip(
            KEYS, np.abs(predicted[:, :-1] - truth_array[:, :-1]).mean(axis=0), strict=True)},
        "learned_feasibility": rates(truth_array[:, -1], predicted[:, -1] >= threshold),
        "online_gcc_feasibility": rates(truth_array[:, -1], [
            item["gcc_prediction"]["feasible"] for row in rows for item in row["candidates"]]),
    }
    choices = defaultdict(Counter)
    regrets = defaultdict(list)
    cursor = 0
    for row in rows:
        candidates = row["candidates"]
        estimates = predicted[cursor:cursor + len(candidates)]
        cursor += len(candidates)
        by_id = {item["action_id"]: item for item in candidates}
        active_gcc = row["gcc_selected_action_id"]
        for preference, weights in PREFERENCES.items():
            eligible = [index for index, estimate in enumerate(estimates) if estimate[-1] >= threshold]
            measurement = {name: item["utility_if_feasible"][preference] for name, item in by_id.items()
                           if item["utility_if_feasible"][preference] is not None}
            best = max(measurement, key=measurement.get) if measurement else None

            def predicted_utility(index):
                values = dict(zip(KEYS, estimates[index, :-1] * np.array(list(UNSCALED.values())), strict=True))
                return utility(values, weights)

            learned = candidates[max(eligible, key=predicted_utility)]["action_id"] if eligible else None
            for method, chosen in (("learned", learned), ("online_gcc", active_gcc)):
                key = f"{method}/{preference}"
                counts = choices[key]
                if best is None:
                    counts["no_feasible_teacher_action"] += 1
                    counts["unsafe_in_empty_group"] += chosen is not None
                elif chosen is None:
                    counts["abstained_with_feasible_action"] += 1
                elif chosen not in measurement:
                    counts["infeasible_selected"] += 1
                else:
                    regret = measurement[best] - measurement[chosen]
                    counts["valid_selection"] += 1
                    counts["zero_preference_loss"] += regret <= 1e-12
                    counts["positive_preference_loss"] += regret > 1e-12
                    relation = compare(truth(by_id[chosen]), truth(by_id[best]))
                    counts[f"objective_{relation}_vs_preferred"] += 1
                    regrets[key].append(regret)
    report["policy_comparison"] = {key: {
        **counts, "mean_regret_on_valid_selections": float(np.mean(regrets[key])) if regrets[key] else None,
    } for key, counts in choices.items()}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.release / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        if sha(args.release / name) != expected:
            raise ValueError(f"Integrity check failed: {name}")
    partitions = defaultdict(list)
    groups = {}
    for row in read_jsonl(args.release / "samples.jsonl"):
        if groups.setdefault(row["split_group"], row["split"]) != row["split"]:
            raise ValueError(f"Split leakage: {row['split_group']}")
        partitions[row["split"]].append(row)
    model = fit(partitions["train"], partitions["validation"])
    args.out.mkdir(parents=True, exist_ok=False)
    np.savez(args.out / "model.npz", **model)
    manifest_out = {"release": manifest["version"], "sample_sha256": manifest["files"]["samples.jsonl"],
                    "family": "quadratic multi-output ridge", "alpha": model["alpha"],
                    "feasibility_threshold": model["threshold"], "targets": KEYS,
                    "model_sha256": sha(args.out / "model.npz"),
                    "fit_split": "train", "selection_split": "validation", "final_evaluation_split": "test"}
    write_json(args.out / "model-manifest.json", manifest_out)
    rows = partitions["test"]
    by_scenario = defaultdict(list)
    for row in rows:
        by_scenario[row["scenario_id"]].append(row)
    write_json(args.out / "metrics.json", {
        "test": evaluate(rows, predict(model, rows), model["threshold"]),
        "test_by_scenario": {name: evaluate(subset, predict(model, subset), model["threshold"])
                             for name, subset in sorted(by_scenario.items())},
    })


if __name__ == "__main__":
    main()
