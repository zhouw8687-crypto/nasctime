"""Replay the same candidate policy with current and received domain reports."""

import argparse
from collections import deque
from dataclasses import dataclass
import hashlib
from importlib import import_module
import json
from pathlib import Path
import sys
from typing import Callable

from reporting import (
    Codec, FIXED, FRAME_VERSION, FULL, HEADER, Periodic, SCHEMA, State, Threshold,
    Trigger, frame, unframe, validate_state,
)


DEFAULT_THRESHOLDS = {
    "ran_bands": 1,
    "ran_last_allocated_blocks": 1,
    "direct_queue_packets": 8,
    "detour_queue_packets": 8,
    "upf_video_rate_bps": 100_000,
}
Snapshot = dict[str, State]
Candidate = dict[str, int | str]
Policy = Callable[[Snapshot], Candidate]


@dataclass(frozen=True)
class Observation:
    time_ns: int
    domains: Snapshot


def read_observations(data: bytes, source_format: str) -> list[Observation]:
    observations = []
    for number, line in enumerate(data.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if source_format == "routes" and record["type"] != "observation":
                continue
            if type(record["version"]) is not int or record["version"] != 1:
                raise ValueError("Expected record version 1")
            if source_format == "routes":
                domains = {
                    domain: {field.name: record[field.name] for field in fields}
                    for domain, fields in SCHEMA.items()
                }
            else:
                domains = record["domains"]
            time_ns = record["sim_time_ns"]
            if type(time_ns) is not int or not 0 <= time_ns < 2**64:
                raise ValueError("Expected a nonnegative uint64 timestamp")
            if observations and time_ns <= observations[-1].time_ns:
                raise ValueError("Observation timestamps must strictly increase")
            if set(domains) != set(SCHEMA):
                raise ValueError(f"Expected these domains: {list(SCHEMA)}")
            for domain, state in domains.items():
                validate_state(domain, state)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Line {number}: {error}") from error
        observations.append(Observation(time_ns, domains))
    if not observations:
        raise ValueError("No observations")
    return observations


def evaluation_end(observations: list[Observation], end_ns: int | None) -> int:
    times = [entry.time_ns for entry in observations]
    if end_ns is None:
        gaps = {right - left for left, right in zip(times, times[1:])}
        if len(gaps) != 1:
            raise ValueError("Provide --end-ns for irregular or single-observation traces")
        end_ns = times[-1] + gaps.pop()
    if end_ns <= times[-1]:
        raise ValueError("The exclusive end must be later than the last observation")
    return end_ns


def joint_policy(snapshot: Snapshot) -> Candidate:
    from ladder_route_policy import choose_joint_policy

    current = {key: value for state in snapshot.values() for key, value in state.items()}
    action = choose_joint_policy(current)
    selected = action if action is not None else current
    return {
        key: selected[key] for key in ("path_id", "ran_bands", "upf_video_rate_bps")
    }


def summary_age(ages_ns: list[int]) -> dict:
    if not ages_ns:
        return dict(samples=0, mean_ms=None, p50_ms=None, p95_ms=None, max_ms=None)
    ages = sorted(ages_ns)
    count = len(ages)
    return dict(
        samples=count,
        mean_ms=sum(ages) / count / 1e6,
        p50_ms=ages[(50 * count + 99) // 100 - 1] / 1e6,
        p95_ms=ages[(95 * count + 99) // 100 - 1] / 1e6,
        max_ms=ages[-1] / 1e6,
    )


def evaluate(
    observations: list[Observation], end_ns: int, codec: Codec, trigger: Trigger,
    policy: Policy, reference: list[Candidate], delay_ns: int = 0,
) -> tuple[dict, list[dict]]:
    if delay_ns < 0 or len(reference) != len(observations):
        raise ValueError("Provide nonnegative delay and one reference action per observation")
    duration_s = (evaluation_end(observations, end_ns) - observations[0].time_ns) / 1e9
    pending = deque()
    sent = {}
    received = {}
    send_times = {domain: [] for domain in SCHEMA}
    wire_bits = dict.fromkeys(SCHEMA, 0)
    age_history = {domain: [] for domain in SCHEMA}
    rows = []
    compared = 0
    different = 0
    field_differences = {}

    for observation, oracle in zip(observations, reference):
        now_ns = observation.time_ns
        transmissions = {}
        for domain, state in observation.domains.items():
            reason = trigger.reason(domain, now_ns, state, sent.get(domain))
            if reason is None:
                continue
            wire = frame(codec, domain, now_ns, state)
            sent[domain] = (now_ns, state.copy())
            arrival_ns = now_ns + delay_ns
            pending.append((arrival_ns, domain, wire))
            send_times[domain].append(now_ns)
            bits = 8 * len(wire)
            wire_bits[domain] += bits
            transmissions[domain] = {
                "reason": reason, "arrival_ns": arrival_ns, "wire_bits": bits, "hex": wire.hex(),
            }

        while pending and pending[0][0] <= now_ns:
            _, domain, wire = pending.popleft()
            received[domain] = unframe(codec, domain, wire)

        ages = dict.fromkeys(SCHEMA)
        for domain, (source_ns, _) in received.items():
            ages[domain] = now_ns - source_ns
            age_history[domain].append(ages[domain])

        candidate = None
        disagreements = None
        if received.keys() == SCHEMA.keys():
            candidate = policy({domain: state.copy() for domain, (_, state) in received.items()})
            if candidate.keys() != oracle.keys():
                raise ValueError("Policy must return the same action fields for every view")
            disagreements = [key for key, value in oracle.items() if value != candidate[key]]
            compared += 1
            different += bool(disagreements)
            for key in oracle:
                field_differences[key] = field_differences.get(key, 0) + (key in disagreements)
        rows.append({
            "sim_time_ns": now_ns, "sent": transmissions, "age_ns": ages,
            "full_information_action": oracle, "received_view_action": candidate,
            "different_fields": disagreements,
        })

    domains = {}
    for domain, times in send_times.items():
        count = len(times)
        gaps = [right - left for left, right in zip(times, times[1:])]
        domains[domain] = {
            "reports": count, "hz": count / duration_s, "wire_bits": wire_bits[domain],
            "wire_bps": wire_bits[domain] / duration_s,
            "mean_wire_bits_per_report": wire_bits[domain] / count if count else None,
            "payload_bits": wire_bits[domain] - 8 * HEADER.size * count,
            "max_inter_send_gap_ms": max(gaps) / 1e6 if gaps else None,
            "tail_since_last_send_ms": (end_ns - times[-1]) / 1e6 if times else None,
            "age": summary_age(age_history[domain]),
        }
    return {
        "codec": {"id": codec.codec_id, "version": codec.version},
        "trigger": type(trigger).__name__,
        "domains": domains,
        "uplink_application_wire_bits": sum(wire_bits.values()),
        "uplink_application_wire_bps": sum(wire_bits.values()) / duration_s,
        "action": {
            "reference_decisions": len(observations),
            "compared": compared,
            "unavailable": len(observations) - compared,
            "different": different,
            "different_fraction": different / compared if compared else None,
            "different_by_field": field_differences,
        },
    }, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--input-format", choices=("routes", "domains"), default="routes")
    parser.add_argument("--policy", default="joint",
                        help="joint or importable module:function returning absolute targets")
    parser.add_argument("--delay-ns", type=int, default=0)
    parser.add_argument("--end-ns", type=int, help="Exclusive evaluation end")
    parser.add_argument("--max-silence-ns", type=int, default=100_000_000)
    parser.add_argument("--thresholds", type=Path, help="JSON object overriding numeric thresholds")
    parser.add_argument("--details", type=Path, help="Write per-method decision and wire JSONL")
    args = parser.parse_args()

    exp_dir = str(Path(__file__).resolve().parent.parent)
    if exp_dir not in sys.path:
        sys.path.append(exp_dir)
    if args.policy == "joint":
        policy = joint_policy
    else:
        module, separator, name = args.policy.partition(":")
        if not (separator and module and name):
            parser.error("--policy expects joint or module:function")
        policy = getattr(import_module(module), name)

    try:
        data = args.trace.read_bytes()
        observations = read_observations(data, args.input_format)
        end_ns = evaluation_end(observations, args.end_ns)
        thresholds = DEFAULT_THRESHOLDS.copy()
        if args.thresholds:
            thresholds.update(json.loads(args.thresholds.read_text(encoding="utf-8")))
        threshold_trigger = Threshold(args.max_silence_ns, thresholds)
        reference = [
            policy({domain: state.copy() for domain, state in entry.domains.items()})
            for entry in observations
        ]
        methods = {}
        details = []
        for name, codec, trigger in (
            ("periodic_full", FULL, Periodic()),
            ("periodic_fixed", FIXED, Periodic()),
            ("threshold_fixed", FIXED, threshold_trigger),
        ):
            result, rows = evaluate(
                observations, end_ns, codec, trigger, policy, reference, args.delay_ns
            )
            methods[name] = result
            details.extend(dict(method=name, **row) for row in rows)
        if args.details:
            with args.details.open("w", encoding="utf-8", newline="\n") as stream:
                for row in details:
                    print(json.dumps(row, ensure_ascii=False), file=stream)
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps({
        "version": 1, "frame_version": FRAME_VERSION, "header_bytes": HEADER.size,
        "trace": str(args.trace), "trace_sha256": hashlib.sha256(data).hexdigest(),
        "input_format": args.input_format, "policy": args.policy,
        "start_ns": observations[0].time_ns, "end_ns_exclusive": end_ns,
        "delay_ns": args.delay_ns, "max_silence_ns": args.max_silence_ns,
        "thresholds": thresholds,
        "fixed_point_steps": {
            field.name: field.step for fields in SCHEMA.values() for field in fields
            if not field.categories
        },
        "methods": methods,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
