"""Generate grouped simulation labels, full-information Pareto sets and paired effects."""

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path

from domain_coordination.adapter import BUDGETS
from domain_coordination.baseline import (
    CoreState, Intent, PathState, RanState, Stamp, TransportState,
    core_candidates, ran_candidates, transport_candidates,
)
from .measure import BURST_NS, DEADLINE_NS, MS, Measurements, actuators, digest
from .simulate import ACTION_GRID, DRAIN_MS, FORKS, HOLD_MS, Run

# Signed objectives are all maximized. Exact equivalence uses these discrete
# quantities; latency percentiles and other metrics are retained for new studies.
BENEFITS = (
    "control_on_time_packets", "control_burst_on_time_packets", "video_delivered_payload_bits",
    "video_on_time_20ms_packets", "competitor_delivered_payload_bits", "competitor_on_time_20ms_packets",
)
COSTS = ("ran_allocated_blocks", "transport_branch_bit_hops")
OBJECTIVES = BENEFITS + COSTS


def compare(challenger, baseline, fields=OBJECTIVES):
    """Classify effect after checking hard feasibility. No objective weights are assumed."""
    if challenger["feasible"] != baseline["feasible"]:
        return "gain" if challenger["feasible"] else "loss"
    if not challenger["feasible"]:
        return "both_infeasible"
    deltas = [(challenger[key] - baseline[key]) * (-1 if key in COSTS else 1) for key in fields]
    if not any(deltas):
        return "equivalent"
    if min(deltas) >= 0:
        return "gain"
    if max(deltas) <= 0:
        return "loss"
    return "tradeoff"


def frontier(outcomes, fields=OBJECTIVES):
    """Return all feasible nondominated actions, including exact ties."""
    return [
        name for name, outcome in outcomes.items()
        if outcome["feasible"] and not any(compare(other, outcome, fields) == "gain"
                                          for other in outcomes.values())
    ]


def weighted_regret(outcomes, chosen_id, weights, scales):
    """Regret for explicitly supplied maximization weights and physical scales.

    Returns None if no candidate is feasible, and +inf for an infeasible choice
    when at least one feasible candidate exists.
    """
    if chosen_id not in outcomes:
        raise KeyError(chosen_id)
    if (not weights or not set(weights) <= set(OBJECTIVES) or set(weights) != set(scales)
            or any(value < 0 or not value < float("inf") for value in weights.values())
            or not any(weights.values())
            or any(not 0 < value < float("inf") for value in scales.values())):
        raise ValueError("supply nonnegative finite weights and positive finite scales for known objectives")
    sign = lambda key: -1 if key in COSTS else 1
    scores = {key: sum(sign(metric) * weight * row[metric] / scales[metric]
                       for metric, weight in weights.items())
              for key, row in outcomes.items() if row["feasible"]}
    if not scores:
        return None
    return max(scores.values()) - scores.get(chosen_id, float("-inf"))


def reports_at(domains, intent, now):
    """Run the unmodified local solvers on exactly the teacher's causal inputs."""
    def with_stamp(domain):
        record = domains[domain]
        return {**record, "stamp": Stamp(**record["stamp"])}

    links = with_stamp("transport")
    links["paths"] = tuple(PathState(**item) for item in links["paths"])
    tables = {
        "ran": ran_candidates(RanState(**with_stamp("ran")), BUDGETS.ran, intent, now),
        "transport": transport_candidates(TransportState(**links), BUDGETS.transport, intent, now),
        "core": core_candidates(CoreState(**with_stamp("core")), BUDGETS.core, intent, now),
    }
    return {domain: [{**asdict(item), "feasible": item.feasible} for item in table]
            for domain, table in tables.items()}


def action_id(action):
    return next(key for key, known in ACTION_GRID.items() if actuators(action) == actuators(known))


def audit_and_measure(episode, reference, prefix, seed, now, stop, expected):
    for txn in episode.trace.values():
        command = expected if txn.now == now else (None if now < txn.now < stop else txn.prediction["action"])
        txn.validate(command)
        if now <= txn.now < stop and actuators(txn.ack) != actuators(expected):
            raise ValueError(f"{episode.path}: hold violated at {txn.now}")
    if episode.prefix_sha256(now) != prefix or episode.trace[now].prediction != reference.trace[now].prediction:
        raise ValueError(f"{episode.path}: replay prefix diverged at {now}")
    if episode.exogenous_traffic_sha256 != reference.exogenous_traffic_sha256:
        raise ValueError(f"{episode.path}: sender traffic differs from reference")
    ack = episode.trace[now].ack
    return {
        "replicate_id": f"seed-{seed}", "seed": seed, "case": episode.path.name,
        "prefix_state_sha256": prefix,
        "exogenous_trace_id": traffic_id(seed, episode.exogenous_traffic_sha256),
        "applied_at_ns": ack["sim_time_ns"], "applied_action": actuators(ack),
        "apply_status": ack["status"],
        **episode.outcomes(now, stop, DRAIN_MS * MS),
    }


def traffic_id(seed, trace):
    return digest({"seed_set": seed, "app_sends_sha256": trace})


def sample_at(out, ref, seed, fork_ms, manifest):
    now, stop = fork_ms * MS, (fork_ms + HOLD_MS) * MS
    prefix = ref.prefix_sha256(now)
    prediction = ref.trace[now].prediction
    domains = {domain: prediction[domain] for domain in ("ran", "transport", "core")}
    intent = Intent(**prediction["intent"])
    model = {action_id(row["action"]): row for row in prediction["evaluated"]}
    active = actuators(ref.trace[now].observation)
    chosen = action_id(prediction["action"] or active)
    candidates = []
    outcomes = {}
    nominal = manifest["scenario_id"] == "pf-dual-ue-both"
    for name, action in ACTION_GRID.items():
        episode = Measurements(out / Run(seed, fork_ms, name).name, validate_nominal_counts=nominal)
        outcome = audit_and_measure(episode, ref, prefix, seed, now, stop, action)
        outcomes[name] = outcome
        candidates.append({"action_id": name, "action": action,
                           "gcc_prediction": model[name], "outcomes": [outcome]})
    for row in candidates:
        name = row["action_id"]
        row["effect_vs_gcc_held"] = compare(outcomes[name], outcomes[chosen])
        row["service_effect_vs_gcc_held"] = compare(outcomes[name], outcomes[chosen], BENEFITS)
    split = {0: "train", 1: "train", 2: "train", 3: "validation", 4: "test"}.get(seed, "unassigned")
    return {
        "version": 1, "scenario_id": manifest["scenario_id"], "scenario_context": manifest.get("scenario_context"),
        "decision_id": f"pf-{seed}-{fork_ms}",
        "split_group": f"pf-dual-ue-both-seed-{seed}", "split": split, "seed": seed,
        "phase": FORKS[fork_ms], "sim_time_ns": now, "apply_at_ns": now,
        "send_window_ns": [now, stop], "drain_until_ns": DRAIN_MS * MS,
        "original_burst_send_window_ns": BURST_NS, "active_action": active,
        "intent": {**asdict(intent), "control_deadline_ns": DEADLINE_NS,
                   "minimum_control_on_time_fraction": 0.99, "minimum_control_packets": 20},
        "domains": domains, "domain_budgets": asdict(BUDGETS),
        "domain_candidates": reports_at(domains, intent, now),
        "environment": {"scheduler": "PF", "mac_backlog_scope": "ue[0]",
                        "radio_randomness_pairing": "same_seed_and_prefix"},
        "prefix_state_sha256": prefix, "app_sends_sha256": ref.exogenous_traffic_sha256,
        "exogenous_trace_id": traffic_id(seed, ref.exogenous_traffic_sha256),
        "gcc_selected_action_id": chosen, "gcc_had_feasible_prediction": prediction["selected"] is not None,
        "rolling_gcc_reference": ref.outcomes(now, stop, DRAIN_MS * MS),
        "pareto_action_ids": frontier(outcomes), "service_pareto_action_ids": frontier(outcomes, BENEFITS),
        "label_status": "complete", "candidates": candidates,
    }


def generate(out):
    manifest = json.loads((out / "matrix.json").read_text())
    if (manifest["hold_ms"] != HOLD_MS or manifest["drain_ms"] != DRAIN_MS
            or manifest["actions"] != ACTION_GRID):
        raise ValueError("matrix settings do not match the label contract")
    for seed in manifest["seeds"]:
        reference = Measurements(out / Run(seed).name,
                                 validate_nominal_counts=manifest["scenario_id"] == "pf-dual-ue-both")
        for txn in reference.trace.values():
            txn.validate(txn.prediction["action"])
        for point in manifest["forks"]:
            yield sample_at(out, reference, seed, point, manifest)


def summarize(rows):
    phases = defaultdict(Counter)
    total = Counter()
    for row in rows:
        counts = phases[row["phase"]]
        counts["groups"] += 1
        for cand in row["candidates"]:
            outcome, = cand["outcomes"]
            counts["branches"] += 1
            counts["feasible"] += outcome["feasible"]
            counts[f'effect_{cand["effect_vs_gcc_held"]}'] += 1
            counts[f'service_{cand["service_effect_vs_gcc_held"]}'] += 1
            counts["gcc_prediction_misses"] += cand["gcc_prediction"]["feasible"] != outcome["feasible"]
            counts["rng_count_diff_vs_rolling"] += (
                outcome["rng_draws_at_window_close"] != row["rolling_gcc_reference"]["rng_draws_at_window_close"]
            )
            if cand["action_id"] == row["gcc_selected_action_id"]:
                counts["gcc_held_pareto"] += cand["action_id"] in row["pareto_action_ids"]
    for counts in phases.values():
        total.update(counts)
    return {"total": dict(total), "by_phase": phases,
            "objectives_max": BENEFITS, "objectives_min": COSTS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    rows = list(generate(args.out))
    with (args.out / "counterfactuals.jsonl").open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, allow_nan=False) + "\n")
    with (args.out / "summary.json").open("w", encoding="utf-8") as file:
        json.dump(summarize(rows), file, allow_nan=False, indent=2)
        file.write("\n")
    print(f"Labeled {len(rows)} groups in {args.out}")


if __name__ == "__main__":
    main()
