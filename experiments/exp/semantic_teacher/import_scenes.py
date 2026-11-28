"""Normalize audited scene-team forks and recompute the causal GCC model at the fork."""

import argparse
from dataclasses import asdict
import io
import json
from pathlib import Path
import re

from counterfactual_teacher.dataset import BENEFITS, action_id, compare, frontier, reports_at
from counterfactual_teacher.measure import actuators, digest, read_jsonl
from counterfactual_teacher.simulate import ACTION_GRID
from domain_coordination.adapter import BUDGETS, LadderPolicy
from domain_coordination.baseline import Intent, MS


def time_ns(text):
    amount, unit = re.fullmatch(r"([\d.]+)(ns|us|ms|s)", text).groups()
    return round(float(amount) * {"ns": 1, "us": 1000, "ms": MS, "s": 1000 * MS}[unit])


def context_for(row):
    settings = row["ini_overrides"]

    def param(node, key, default):
        return settings.get(f"*.{node}.{key}", default)

    wired, radio = "NE1.app[0]", "gnb1.app[0]"
    return {
        "wired_bg_dscp": int(param(wired, "dscp", "34")),
        "wired_window_ns": [time_ns(param(wired, key, default)) for key, default in
                            (("startTime", "5s"), ("stopTime", "6s"))],
        "radio_window_ns": [time_ns(param(radio, key, default)) for key, default in
                            (("startTime", "5s"), ("stopTime", "6s"))],
        "wired_send_interval_ns": time_ns(param(wired, "sendInterval", "500us")),
        "radio_competitor_interval_ns": time_ns(param(radio, "sendInterval", "400us")),
        "control_send_interval_ns": time_ns(param("server.app[0]", "sendInterval", "5ms")),
        "control_payload_bytes": int(param("server.app[0]", "messageLength", "200B").removesuffix("B")),
    }


def normalize_flow(row, name):
    flow = row["flows"].get(name, {})
    sent = flow.get("sent", 0)
    delivered = flow.get("delivered", 0)
    p99 = flow.get("p99_delivered_ms")
    return {"sent_packets": sent, "delivered_packets": delivered, "undelivered_packets": sent - delivered,
            "on_time_20ms_packets": flow.get("on_time_20ms", 0),
            "delivered_payload_bits": int(flow.get("payload_bits", 0)),
            "p99_delivered_ns": p99 * MS if p99 is not None else None}


def outcome(row, ack, prefix, seed):
    flows = {name: normalize_flow(row, name) for name in ("control", "video", "radio_competitor")}
    control, video, competitor = flows.values()
    local = row["local_control_100ms"]
    local_pass = local["sent"] > 0 and local["on_time_20ms"] * 100 >= 99 * local["sent"]
    budget_pass = row["cell_rb_slots"] == row["ue0_rb_slots"] + row["ue1_rb_slots"]
    return {
        "replicate_id": f"seed-{seed}", "seed": seed, "prefix_state_sha256": prefix,
        "exogenous_trace_id": digest([seed, row["source_trace_sha256"]]),
        "applied_at_ns": ack["sim_time_ns"], "applied_action": actuators(ack), "apply_status": ack["status"],
        "control_sent_packets": local["sent"], "control_on_time_packets": local["on_time_20ms"],
        "control_burst_sent_packets": control["sent_packets"],
        "control_burst_on_time_packets": control["on_time_20ms_packets"],
        "video_delivered_payload_bits": video["delivered_payload_bits"],
        "video_on_time_20ms_packets": video["on_time_20ms_packets"],
        "competitor_delivered_payload_bits": competitor["delivered_payload_bits"],
        "competitor_on_time_20ms_packets": competitor["on_time_20ms_packets"],
        "ran_allocated_blocks": row["cell_rb_slots"], "transport_branch_bit_hops": row["n3_ip_bit_hops"],
        "resource_constraints_met": budget_pass,
        "local_sla_met": local_pass, "original_burst_sla_met": row["sla_feasible"],
        "feasible": row["sla_feasible"] and local_pass and budget_pass,
        "flows": flows, "admission": {"offered": row["n6_offered_video_packets"],
                                      "admitted": row["n6_admitted_video_packets"],
                                      "dropped": row["n6_dropped_video_packets"],
                                      "enforced_bps": ack["upf_video_enforced_bps"]},
    }


def adapt(directory, row, release):
    if set(row["outcomes"]) != set(ACTION_GRID) or row["split"] not in {"train", "validation", "test"}:
        raise ValueError(f'Incomplete or discovery sample: {row["split_group"]}')
    seed, scene = row["seed"], row["scenario_id"]
    now = row["source_time_ms"] * MS
    context = context_for(row)
    control_bps = round(context["control_payload_bytes"] * 8e9 / context["control_send_interval_ns"])
    original = None
    outcomes = {}
    for name, branch in row["outcomes"].items():
        raw = read_jsonl(directory / f"{scene}-{seed}-{name}" / "routes.jsonl")
        prefix_trace = [item for item in raw if item["sim_time_ns"] < now or
                        (item["sim_time_ns"] == now and item["type"] == "observation")]
        if original is None:
            original = prefix_trace
        if prefix_trace != original:
            raise ValueError(f"{scene}/{seed}/{name}: inconsistent observed prefix")
        ack, = (item for item in raw if item["sim_time_ns"] == now and item["type"] == "ack")
        if actuators(ack) != actuators(ACTION_GRID[name]) or ack["status"] not in {"applied", "unchanged"}:
            raise ValueError(f"{scene}/{seed}/{name}: incorrect branch actuation")
        outcomes[name] = outcome(branch, ack, branch["prefix_state_sha256"], seed)

    if len({item["prefix_state_sha256"] for item in outcomes.values()}) != 1 or (
        len({item["exogenous_trace_id"] for item in outcomes.values()}) != 1
    ):
        raise ValueError(f"{scene}/{seed}: incompatible branch witnesses")
    intent = Intent(control_bps=control_bps)
    log = io.StringIO()
    policy = LadderPolicy("full", log, intent=intent)
    for item in original:
        if item["type"] == "observation":
            policy(item)
    decision = json.loads(log.getvalue().splitlines()[-1])
    obs = original[-1]
    domains = {key: decision[key] for key in ("ran", "transport", "core")}
    estimates = {action_id(item["action"]): item for item in decision["evaluated"]}
    chosen = action_id(decision["action"] or actuators(obs))
    candidates = [{"action_id": name, "action": action, "gcc_prediction": estimates[name],
                   "outcomes": [outcomes[name]], "effect_vs_gcc_held": compare(outcomes[name], outcomes[chosen]),
                   "service_effect_vs_gcc_held": compare(outcomes[name], outcomes[chosen], BENEFITS)}
                  for name, action in ACTION_GRID.items()]
    window = [time * MS for time in row["evaluation_window_ms"]]
    return {
        "version": 1, "source_family": "scene-manifest", "source_release": release, "scenario_id": scene,
        "scenario_context": context, "split_group": row["split_group"], "split": row["split"],
        "seed": seed, "decision_id": f"pf-{seed}-{row['source_time_ms']}", "phase": row["scenario_family"],
        "sim_time_ns": now, "apply_at_ns": now, "send_window_ns": window,
        "drain_until_ns": 4000 * MS, "original_burst_send_window_ns": window,
        "local_control_window_ns": [time * MS for time in row["local_evaluation_window_ms"]],
        "active_action": actuators(obs), "core_capacity_bps": obs["upf_video_capacity_bps"],
        "intent": {**asdict(intent), "control_deadline_ns": 20 * MS, "minimum_control_on_time_fraction": .99,
                   "minimum_control_packets": 1},
        "domains": domains, "domain_budgets": asdict(BUDGETS),
        "domain_candidates": reports_at(domains, intent, now),
        "environment": {"scheduler": "PF", "mac_backlog_scope": "ue[0]",
                        "prefix_policy": "no_control_change_before_source_time",
                        "radio_randomness_pairing": "same_seed_and_prefix"},
        "prefix_state_sha256": next(iter(outcomes.values()))["prefix_state_sha256"],
        "exogenous_trace_id": next(iter(outcomes.values()))["exogenous_trace_id"],
        "gcc_selected_action_id": chosen, "gcc_had_feasible_prediction": decision["selected"] is not None,
        "gcc_reference_kind": "online_model_recomputed_on_noop_prefix",
        "rolling_gcc_reference": None, "label_status": "complete", "candidates": candidates,
        "pareto_action_ids": frontier(outcomes), "service_pareto_action_ids": frontier(outcomes, BENEFITS),
        "shared_preference_specs": row["preference_specs"], "shared_preference_winners": row["preference_winners"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.directory / "input-manifest.json").read_text(encoding="utf-8"))
    if manifest["release"] != "v1.0":
        parser.error("use the frozen scene manifest v1.0")
    declared = {row["split_group"]: row for row in manifest["scenarios"]}
    with args.out.open("x", encoding="utf-8") as file:
        for row in read_jsonl(args.directory / "paired.jsonl"):
            entry = declared[row["split_group"]]
            if any(entry[key] != row[key] for key in ("split", "scenario_id", "seed", "source_time_ms")):
                raise ValueError(f'Pair does not match frozen scene assignment: {row["split_group"]}')
            file.write(json.dumps(adapt(args.directory, row, manifest["release"]), allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
