"""Read the teacher contract, verify the frozen split, and expose causal inputs."""

from hashlib import sha256
import json
from statistics import fmean

from domain_coordination.baseline import (
    Budgets, CoreState, DomainBudget, Intent, PathState, RanState, Stamp, TransportState, solve_full,
)
from integrated_review.uplink import BRANCHES, CoreReport, LinkReport, RanReport, TransportReport


def load_dataset(root, requested):
    files = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in files["files"].items():
        if sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Digest mismatch: {name}")
    split_data = json.loads((root / f"split-v{files['split_version']}.json").read_text(encoding="utf-8"))
    if files["split_version"] != split_data["version"]:
        raise ValueError("Split version does not match manifest")
    contract = json.loads((root / "contracts.json").read_text(encoding="utf-8"))
    assignments = split_data["assignments"]
    if split_data["version"] == "1":
        frozen = {}
        for split, seeds in assignments.items():
            for seed in seeds:
                key = split_data["group_key"].format(seed=seed)
                if key in frozen:
                    raise ValueError(f"Seed {seed} occurs in multiple splits")
                frozen[key] = split
    elif split_data["version"] == "2":
        frozen = assignments
    else:
        raise ValueError("Unsupported frozen trajectory split")
    selected = {name: [] for name in requested}
    identifiers = set()
    trajectories = {}
    actual_counts = {}
    with (root / "samples.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            record_id = row["record_id"]
            if record_id in identifiers:
                raise ValueError(f"Duplicate record {record_id}")
            identifiers.add(record_id)
            split = row["split"]
            trajectory = (row["scenario_id"], row["seed"])
            flows = {name: spec.copy() for name, spec in contract["flows"].items()}
            if "control_payload_bytes" in row.get("scenario_context", {}):
                flows["control"]["payload_bytes"] = row["scenario_context"]["control_payload_bytes"]
            if (split != frozen[row["split_group"]]
                    or trajectories.setdefault(trajectory, row["split_group"]) != row["split_group"]
                    or row["data_version"] != files["version"]
                    or row["unit_profile"] != contract["unit_profile"]
                    or row["flow_scope"] != flows
                    or row["label_status"] != "complete"):
                raise ValueError(f"Frozen dataset contract mismatch for {record_id}")
            actual_counts[split] = actual_counts.get(split, 0) + 1
            if split in selected:
                selected[split].append(row)
    for split, rows in selected.items():
        if not rows or len(rows) != files["counts"][f"{split}_groups"]:
            raise ValueError(f"Empty or incomplete requested split {split}")
    return selected, contract, {
        "teacher_version": files["version"], "split_version": files["split_version"],
        "teacher_sha256": files["files"]["samples.jsonl"], "group_counts": actual_counts,
    }


def report_inputs(row):
    ran, transport, core = (row["domains"][key] for key in ("ran", "transport", "core"))
    return {
        "ran": RanReport(ran["max_bands"], ran["mac_backlog_bytes"]),
        "transport": TransportReport(transport["current_path"], tuple(
            LinkReport(path["available"], path["queued_packets"],
                       path["control_queue_bits"], path["bottleneck_bps"])
            for path in sorted(transport["paths"], key=lambda p: BRANCHES.index(p["path_id"]))
        )),
        "core": CoreReport(core["offered_video_bps"], core["burst_bytes"], core["max_ip_rate_bps"]),
    }


def solve(row, reports):
    raw = row["domains"]
    now = row["sim_time_ns"]
    stamps = {name: Stamp(**raw[name]["stamp"]) for name in reports}
    if any(not stamp.is_live_at(now) for stamp in stamps.values()):
        raise ValueError("A labeled decision is missing a causal, valid input")
    ran, transport, core = (reports[key] for key in ("ran", "transport", "core"))
    ran_state = RanState(stamps["ran"], ran.max_bands, ran.mac_backlog_bytes,
                         raw["ran"]["service_bps_per_band"])
    common_paths = {path["path_id"]: path for path in raw["transport"]["paths"]}
    paths = []
    for name, dynamic in zip(BRANCHES, transport.paths, strict=True):
        common = common_paths[name]
        paths.append(PathState(
            name, dynamic.available, dynamic.queued_packets, dynamic.control_queue_bits,
            dynamic.bottleneck_bps, common["branch_links"], common["base_delay_ns"],
            common["congested_delivery_ppm"],
        ))
    transport_state = TransportState(stamps["transport"], transport.current_path, tuple(paths))
    core_state = CoreState(stamps["core"], core.offered_video_bps, core.max_ip_rate_bps,
                           raw["core"]["payload_bytes"], raw["core"]["packet_ip_bytes"], core.burst_bytes)
    budgets = Budgets(**{key: DomainBudget(**data) for key, data in row["domain_budgets"].items()})
    intent = Intent(**{key: row["intent"][key] for key in Intent.__dataclass_fields__})
    return solve_full(ran_state, transport_state, core_state, budgets, intent, now)


def action_key(action):
    return tuple(action[key] for key in ("path_id", "ran_bands", "upf_video_rate_bps"))


OBJECTIVES = {
    "video_bits": (1, "video_delivered_payload_bits"),
    "video_on_time": (1, "video_on_time_20ms_packets"),
    "competitor_bits": (1, "competitor_delivered_payload_bits"),
    "ran_blocks": (-1, "ran_allocated_blocks"),
    "branch_bit_hops": (-1, "transport_branch_bit_hops"),
}


def measured_outcomes(row, contract, preference):
    weights = contract["preferences"][preference]
    scales = contract["scales"]
    start, end = row["send_window_ns"]
    if not start < end:
        raise ValueError("Expected a nonempty measured outcome window")
    scale_to_100ms = 100_000_000 / (end - start)
    if preference not in row["preference_ids"]:
        raise ValueError("Decision has no matching business preference")
    result = {}
    for candidate in row["candidates"]:
        action = action_key(candidate["action"])
        branches = candidate["outcomes"]
        if action in result or not branches:
            raise ValueError("Missing or duplicate measured action")
        for branch in branches:
            if (branch["prefix_state_sha256"] != row["prefix_state_sha256"]
                    or branch["exogenous_trace_id"] != row["exogenous_trace_id"]
                    or branch["applied_at_ns"] != row["apply_at_ns"]
                    or action_key(branch["applied_action"]) != action
                    or branch["apply_status"] not in ("applied", "unchanged")
                    or (branch["apply_status"] == "unchanged" and action != action_key(row["active_action"]))):
                raise ValueError("Unpaired or unverified action outcome")
        utility = fmean(
            sum(sign * weights[name] * scale_to_100ms * branch[field] / scales[name]
                for name, (sign, field) in OBJECTIVES.items())
            for branch in branches
        )
        result[action] = (all(branch["feasible"] for branch in branches), utility)
    return result
