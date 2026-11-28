"""Evaluate fixed-period, zero-delay uplink frames against measured teacher branches."""

import argparse
import json
from math import ceil
from pathlib import Path
from statistics import fmean
from time import perf_counter_ns

from domain_coordination.baseline import MS
from integrated_review.uplink import ReportChannel

from .data import action_key, load_dataset, measured_outcomes, report_inputs, solve
from .formats import NAMES, PAYLOAD_BYTES, make_boundary, make_fixed, make_full


PERIOD_NS = 20 * MS
DELAY_NS = 0


def verify_artifact(path, provenance, test_rows):
    meta = json.loads((path / "fit.json").read_text(encoding="utf-8"))
    if any(meta[key] != provenance[key] for key in ("teacher_sha256", "split_version", "teacher_version")):
        raise ValueError(f"{path} was not trained on the requested teacher version")
    used = set(meta["train_ids"]) | set(meta["validation_ids"])
    if used & {row["record_id"] for row in test_rows}:
        raise ValueError(f"Held-out record present in {path}/fit.json")


def latency(codec, validation, frames_per_domain):
    snapshots = [report_inputs(row) for row in validation]
    for snapshot in snapshots:
        for domain in NAMES:
            codec.decoder.decode(domain, codec.encoder.encode(domain, snapshot[domain]))
    samples = {domain: ([], []) for domain in NAMES}
    for index in range(frames_per_domain):
        reports = snapshots[index % len(snapshots)]
        for domain in NAMES:
            started = perf_counter_ns()
            payload = codec.encoder.encode(domain, reports[domain])
            encoded = perf_counter_ns()
            codec.decoder.decode(domain, payload)
            decoded = perf_counter_ns()
            encodes, decodes = samples[domain]
            encodes.append(encoded - started)
            decodes.append(decoded - encoded)

    def summarize(entries):
        return sorted(entries)[ceil(0.99 * len(entries)) - 1] / 1e6

    return {
        domain: dict(encode_p99_ms=summarize(enc), decode_p99_ms=summarize(dec),
                     codec_pair_p99_ms=summarize([a + b for a, b in zip(enc, dec, strict=True)]),
                     samples=len(enc))
        for domain, (enc, dec) in samples.items()
    }


def measure(codec, row, contract, preference, width):
    now_ns = row["sim_time_ns"]
    reports = report_inputs(row)
    stamps = [row["domains"][domain]["stamp"] for domain in NAMES]
    if any(stamp["observed_ns"] != now_ns for stamp in stamps):
        raise ValueError("This zero-delay replay requires aligned teacher reports")
    channel = ReportChannel(codec, DELAY_NS, min(s["valid_until_ns"] - now_ns for s in stamps))
    wire = channel.tick(now_ns, reports)
    received, _ = channel.view(now_ns)
    if len(received) != len(NAMES):
        raise ValueError("The evaluator needs a report from each domain at the labeled fork")
    if width is not None and any(len(bytes.fromhex(event["wire_hex"])) != 12 + width for event in wire):
        raise ValueError("Report length violates matched wire period")
    test = solve(row, {domain: item.report for domain, item in received.items()})
    reference = solve(row, reports)
    truth = measured_outcomes(row, contract, preference)
    all_candidates = {action_key(item.action()): item.feasible for item in test.evaluated}
    if all_candidates.keys() != truth.keys():
        raise ValueError("Solver and teacher enumerate different actions")
    target = action_key(test.selected.action() if test.selected else row["active_action"])
    full = action_key(reference.selected.action() if reference.selected else row["active_action"])
    actual_feasible, actual_utility = truth[target]
    full_utility = truth[full][1]
    feasible_values = [value for feasible, value in truth.values() if feasible]
    return {
        **{key: row[key] for key in (
            "record_id", "scenario_id", "split_group", "seed", "flow_scope", "unit_profile",
            "sim_time_ns", "send_window_ns", "apply_at_ns", "drain_until_ns",
        )},
        "preference": preference, "preference_weights": contract["preferences"][preference],
        "valid_until_ns": {name: row["domains"][name]["stamp"]["valid_until_ns"] for name in NAMES},
        "wire_bits": sum(frame["bits"] for frame in wire),
        "payload_hex": {frame["domain"]: bytes.fromhex(frame["wire_hex"])[12:].hex() for frame in wire},
        "prediction_feasible": sum(all_candidates.values()),
        "actual_infeasible_candidates": sum(not feasible for feasible, _ in truth.values()),
        "false_feasible": sum(estimate and not truth[key][0] for key, estimate in all_candidates.items()),
        "different": target != full, "target": target, "reference_target": full,
        "hold": test.selected is None, "selected_measured_feasible": actual_feasible,
        "selected_utility": actual_utility,
        "signed_loss_vs_full": full_utility - actual_utility,
        "loss_vs_measured_oracle": max(feasible_values) - actual_utility if actual_feasible and feasible_values else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mlp", type=Path, required=True)
    parser.add_argument("--lora", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--preference", default="balanced")
    parser.add_argument("--latency-frames", type=int, default=100)
    args = parser.parse_args()
    if args.latency_frames < 100:
        parser.error("Expected at least 100 measured frames per domain for P99")
    from .learned import load_learned
    import torch

    torch.set_num_threads(1)
    data, contract, provenance = load_dataset(args.dataset, ("validation", "test"))
    verify_artifact(args.mlp, provenance, data["test"])
    verify_artifact(args.lora, provenance, data["test"])
    args.output.mkdir(parents=True, exist_ok=False)
    summary = {
        **provenance, "period_ns": PERIOD_NS, "delay_ns": DELAY_NS, "preference": args.preference,
        "preference_weights": contract["preferences"][args.preference], "preference_scales": contract["scales"],
        "inference_device": torch.cuda.get_device_name(args.device) if args.device.startswith("cuda") else args.device,
        "modes": {},
    }
    with (args.output / "decisions.jsonl").open("w", encoding="utf-8") as stream:
        for name, codec in (
            ("full", make_full(data["validation"] + data["test"])), ("fixed", make_fixed()), ("boundary", make_boundary()),
            ("mlp", load_learned(args.mlp, args.device)), ("lora", load_learned(args.lora, args.device)),
        ):
            timing = latency(codec, data["validation"], args.latency_frames)
            rows = [measure(codec, row, contract, args.preference, None if name == "full" else PAYLOAD_BYTES)
                    for row in data["test"]]
            for row in rows:
                print(json.dumps(dict(mode=name, **row)), file=stream)
            negatives = sum(row["actual_infeasible_candidates"] for row in rows)
            predicted_positive = sum(row["prediction_feasible"] for row in rows)
            errors = sum(row["false_feasible"] for row in rows)
            oracle_losses = [row["loss_vs_measured_oracle"] for row in rows
                             if row["loss_vs_measured_oracle"] is not None]
            summary["modes"][name] = dict(
                decisions=len(rows), actual_infeasible_candidates=negatives,
                predicted_feasible_candidates=predicted_positive, false_feasible=errors,
                false_positive_rate=errors / negatives if negatives else None,
                false_feasible_fraction=errors / predicted_positive if predicted_positive else None,
                action_disagreements_vs_full=sum(row["different"] for row in rows),
                selected_infeasible=sum(not row["selected_measured_feasible"] for row in rows),
                hold_ticks=sum(row["hold"] for row in rows),
                max_signed_loss=max(row["signed_loss_vs_full"] for row in rows),
                mean_signed_loss=fmean(row["signed_loss_vs_full"] for row in rows),
                mean_loss_vs_measured_oracle=fmean(oracle_losses) if oracle_losses else None,
                scheduled_wire_bps=sum(row["wire_bits"] for row in rows) / (len(rows) * PERIOD_NS / 1e9),
                timing_ms=timing,
            )
    matched = {summary["modes"][mode]["scheduled_wire_bps"] for mode in ("fixed", "boundary", "mlp", "lora")}
    if len(matched) != 1:
        raise ValueError("Measured wire rates do not match")
    (args.output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
