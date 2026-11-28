"""Publish measured action outcomes with a frozen trajectory-level split."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

SPLITS = {"train": [0, 1, 2, 5, 6, 7], "validation": [3, 8], "test": [4, 9]}
SEED_SPLIT = {seed: split for split, seeds in SPLITS.items() for seed in seeds}
DOMAINS = ("ran", "transport", "core")
UNITS = {
    "source_ns": "ns", "valid_until_ns": "ns", "control_deadline_ns": "ns",
    "mac_backlog_bytes": "B", "queued_packets": "packets", "control_queue_bits": "bit",
    "egress_bps": "bit/s", "offered_video_bps": "UE0 video application bit/s",
    "burst_bytes": "IP B", "upf_video_rate_bps": "IP bit/s", "ran_bands": "logical bands",
    "control_on_time_packets": "packets", "control_burst_on_time_packets": "packets",
    "video_delivered_payload_bits": "application bit", "video_on_time_20ms_packets": "packets",
    "competitor_delivered_payload_bits": "application bit", "ran_allocated_blocks": "scheduled blocks",
    "transport_branch_bit_hops": "outer N3 IP bit-hop",
}
FLOWS = {"control": {"ue": "ue[0]", "udp_dst": 6200, "payload_bytes": 200},
         "video": {"ue": "ue[0]", "udp_dst": 6204, "payload_bytes": 1000},
         "radio_competitor": {"ue": "ue[1]", "udp_dst": 6400, "payload_bytes": 1200}}
# Objectives are maximized except resource costs; impose feasibility before scoring.
PREFERENCES = {
    "balanced": {"video_bits": .40, "video_on_time": .20, "competitor_bits": .20,
                 "ran_blocks": .10, "branch_bit_hops": .10},
    "video_first": {"video_bits": .45, "video_on_time": .35, "competitor_bits": .05,
                    "ran_blocks": .05, "branch_bit_hops": .10},
    "shared_radio": {"video_bits": .25, "video_on_time": .10, "competitor_bits": .45,
                     "ran_blocks": .15, "branch_bit_hops": .05},
}
SCALES = {"video_bits": 200_000, "video_on_time": 25, "competitor_bits": 2_400_000,
          "ran_blocks": 2_000, "branch_bit_hops": 2_000_000}


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as file:
        yield from (json.loads(line) for line in file if line.strip())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def queue_band(packets):
    return int(packets >= 5) + int(packets >= 24)


def semantic_view(domains):
    ran, transport, core = (domains[domain] for domain in DOMAINS)

    def stamped(state, **fields):
        return {"source_ns": state["stamp"]["observed_ns"],
                "valid_until_ns": state["stamp"]["valid_until_ns"], **fields}

    return {
        "ran": stamped(ran, ue="ue[0]", mac_backlog_bytes=ran["mac_backlog_bytes"],
                       max_bands=ran["max_bands"]),
        "transport": stamped(transport, current_path=transport["current_path"], paths={
            path["path_id"]: {"available": path["available"], "queued_packets": path["queued_packets"],
                              "queue_band": queue_band(path["queued_packets"]),
                              "control_queue_bits": path["control_queue_bits"],
                              "egress_bps": path["bottleneck_bps"]}
            for path in transport["paths"]}),
        "core": stamped(core, ue="ue[0]", flow="video", offered_video_bps=core["offered_video_bps"],
                        burst_bytes=core["burst_bytes"]),
    }


def metric_values(outcome):
    return {"video_bits": outcome["video_delivered_payload_bits"],
            "video_on_time": outcome["video_on_time_20ms_packets"],
            "competitor_bits": outcome["competitor_delivered_payload_bits"],
            "ran_blocks": outcome["ran_allocated_blocks"],
            "branch_bit_hops": outcome["transport_branch_bit_hops"]}


def utility(values, weights):
    return sum((-1 if name in ("ran_blocks", "branch_bit_hops") else 1)
               * weights[name] * values[name] / SCALES[name] for name in SCALES)


def publish(sources, out, version, source_revision):
    out.mkdir(parents=True, exist_ok=False)
    split = {"version": "1", "group_key": "pf-dual-ue-seed-{seed}", "assignments": SPLITS,
             "policy": "same seed across scenario variants and all forks stays together"}
    write_json(out / "split-v1.json", split)
    counts = Counter()
    scenarios = Counter()
    ids = set()
    with (out / "samples.jsonl").open("x", encoding="utf-8") as file:
        for source in sources:
            for row in read_jsonl(source):
                seed = row["seed"]
                split_name = SEED_SPLIT[seed]
                row["split_group"] = f"pf-dual-ue-seed-{seed}"
                row["split"] = split_name
                # Keep the original scenario-specific decision id for provenance.
                row["record_id"] = f'{row["scenario_id"]}/{row["decision_id"]}'
                if row["record_id"] in ids:
                    raise ValueError(f'Duplicate record: {row["record_id"]}')
                ids.add(row["record_id"])
                if row["label_status"] != "complete":
                    raise ValueError(f'Incomplete paired group: {row["record_id"]}')
                row["data_version"] = version
                row["semantic"] = semantic_view(row["domains"])
                row["flow_scope"] = FLOWS
                row["unit_profile"] = "pf-v1"
                row["preference_ids"] = list(PREFERENCES)
                for candidate in row["candidates"]:
                    replicate, = candidate["outcomes"]
                    metrics = metric_values(replicate)
                    candidate["utility_if_feasible"] = {
                        name: utility(metrics, weights) if replicate["feasible"] else None
                        for name, weights in PREFERENCES.items()
                    }
                    counts[f'{split_name}_branches'] += 1
                    counts[f'{split_name}_infeasible'] += not replicate["feasible"]
                counts[f'{split_name}_groups'] += 1
                scenarios[row["scenario_id"]] += 1
                file.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
    write_json(out / "contracts.json", {
        "unit_profile": "pf-v1", "units": UNITS, "flows": FLOWS,
        "preferences": PREFERENCES, "scales": SCALES,
        "feasibility": "apply/readback checked, local 100 ms control SLA, original burst SLA and resource constraints",
        "causal_inputs": ["scenario_context", "semantic", "intent", "domain_budgets", "active_action"],
        "supervision_only": ["candidates[].outcomes", "rolling_gcc_reference", "pareto_action_ids"],
    })
    write_json(out / "manifest.json", {
        "version": version, "source_revision": source_revision, "split_version": "1",
        "scenarios": dict(scenarios), "counts": dict(counts),
        "source_sha256": {str(source): sha(source) for source in sources},
        "files": {name: sha(out / name) for name in ("samples.jsonl", "split-v1.json", "contracts.json")},
        "teacher": "paired closed-loop Simu5G branches", "online_gcc": "causal analytical baseline",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("sources", type=Path, nargs="+")
    args = parser.parse_args()
    publish(args.sources, args.out, args.version, args.source_revision)


if __name__ == "__main__":
    main()
