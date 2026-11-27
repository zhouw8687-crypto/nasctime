"""Audit live decisions, wire timing, and endpoint outcomes by sending cohort."""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from control_reporting.reporting import DOMAIN_IDS, FRAME_VERSION, HEADER
from domain_coordination.adapter import ACTIONS
from dual_ue.extract import extract_flows, include, load_vectors


def audit_reports(log, decisions, acks, duration_s):
    settings, = [record for record in log if record["type"] == "report_settings"]
    views = [record for record in log if record["type"] == "report_view"]
    delay_ns, ttl_ns = settings["delay_ns"], settings["ttl_ns"]
    frames = {domain: [] for domain in DOMAIN_IDS}
    for record in log:
        if record["type"] != "report":
            continue
        domain = record["domain"]
        wire = bytes.fromhex(record["wire_hex"])
        expected_header = (FRAME_VERSION, settings["codec_id"], settings["codec_version"],
                           DOMAIN_IDS[domain], record["source_ns"])
        if (len(wire) * 8 != record["bits"] or HEADER.unpack_from(wire) != expected_header
                or record["arrival_ns"] != record["source_ns"] + delay_ns):
            raise ValueError(f"Invalid wire record for {domain}: {record}")
        previous = frames[domain]
        if previous and previous[-1]["source_ns"] >= record["source_ns"]:
            raise ValueError(f"Nonmonotonic sources for {domain}")
        previous.append(record)

    outcomes = Counter()
    statuses = {domain: Counter() for domain in DOMAIN_IDS}
    ages = {domain: [] for domain in DOMAIN_IDS}
    cursors = dict.fromkeys(DOMAIN_IDS, 0)
    for view, decision, ack in zip(views, decisions, acks, strict=True):
        now_ns = decision["sim_time_ns"]
        if (view["request_id"] != decision["request_id"] or view["sim_time_ns"] != now_ns
                or view["effective_target"] != {key: ack[key] for key in ACTIONS}
                or view["domains"].keys() != DOMAIN_IDS.keys()):
            raise ValueError(f"Decision and report view differ at {now_ns} ns")

        blocked = set()
        for domain, rows in frames.items():
            index = cursors[domain]
            while index < len(rows) and rows[index]["arrival_ns"] <= now_ns:
                index += 1
            cursors[domain] = index
            received = rows[index - 1] if index else None
            if received is None:
                status = "missing"
                source_ns = arrival_ns = age_ns = None
            else:
                source_ns = received["source_ns"]
                arrival_ns = received["arrival_ns"]
                age_ns = now_ns - source_ns
                status = "fresh" if age_ns < ttl_ns else "expired"
                ages[domain].append(age_ns)
            expected = dict(status=status, source_ns=source_ns, arrival_ns=arrival_ns, age_ns=age_ns)
            if view["domains"][domain] != expected:
                raise ValueError(f"Invalid receiver state for {domain} at {now_ns} ns")
            statuses[domain][status] += 1
            if status != "fresh":
                blocked.add(status)

        difference = view["effective_target"] != view["reference_target"]
        outcomes["target_diff_ticks"] += difference
        if blocked:
            reason = "report_missing" if "missing" in blocked else "report_expired"
            if decision["reason"] != reason or decision["selected"] is not None or decision["evaluated"]:
                raise ValueError(f"Invalid hold with missing or expired state at {now_ns} ns")
            outcomes[reason + "_ticks"] += 1
            outcomes["target_diff_held_ticks"] += difference
        else:
            for domain, state in view["domains"].items():
                expected_stamp = dict(observed_ns=state["source_ns"],
                                      valid_until_ns=state["source_ns"] + ttl_ns)
                if decision[domain]["stamp"] != expected_stamp:
                    raise ValueError(f"Solver used the wrong source stamp for {domain}")
            outcomes["all_fresh_ticks"] += 1
            outcomes["target_diff_fresh_ticks"] += difference
            outcomes["no_candidate_fresh_ticks"] += decision["selected"] is None

    result = dict(report_delay_ms=delay_ns / 1e6, report_ttl_ms=ttl_ns / 1e6,
                  refresh_ms=None if settings["refresh_ns"] is None else settings["refresh_ns"] / 1e6)
    for key in ("all_fresh_ticks", "report_missing_ticks", "report_expired_ticks",
                "no_candidate_fresh_ticks", "target_diff_ticks", "target_diff_fresh_ticks",
                "target_diff_held_ticks"):
        result[key] = outcomes[key]
    for domain, rows in frames.items():
        samples = sorted(ages[domain])
        count = len(samples)
        result.update({
            f"{domain}_reports": len(rows),
            f"{domain}_hz": round(len(rows) / duration_s, 3),
            f"{domain}_missing_ticks": statuses[domain]["missing"],
            f"{domain}_expired_ticks": statuses[domain]["expired"],
            f"{domain}_mean_age_ms": round(sum(samples) / count / 1e6, 3) if count else None,
            f"{domain}_p95_age_ms": samples[(95 * count + 99) // 100 - 1] / 1e6 if count else None,
        })
    return result


def summarize(case, scheduler, seed, codec):
    trace = [json.loads(line) for line in (case / "routes.jsonl").read_text().splitlines()]
    log = [json.loads(line) for line in (case / "policy.jsonl").read_text().splitlines()]
    obs = [r for r in trace if r["type"] == "observation"]
    decisions = [r for r in log if r["type"] == "policy"]
    acks = [r for r in trace if r["type"] == "ack"]
    commands = [r["decision"] for r in trace if r["type"] == "received_decision"]
    if len(obs) != 56:
        raise ValueError(f"{case}: expected 56 ticks")
    times = [row["sim_time_ns"] for row in obs]
    steps = {b - a for a, b in zip(times, times[1:])}
    if steps != {20_000_000}:
        raise ValueError(f"{case}: expected 20 ms ticks")
    duration_s = (times[-1] - times[0] + steps.pop()) / 1e9
    changes = {key: [] for key in ACTIONS}
    for o, d, cmd, ack in zip(obs, decisions, commands, acks, strict=True):
        action = d["action"]
        target = o if action is None else action
        if (len({r["request_id"] for r in (o, d, cmd, ack)}) != 1 or cmd["action"] != action
                or d["sim_time_ns"] != o["sim_time_ns"] or ack["sim_time_ns"] != o["sim_time_ns"]
                or ack["status"] != ("noop" if action is None else "applied")
                or any(ack[key] != target[key] for key in ACTIONS)):
            raise ValueError(f"{case}: unexpected control transaction")
        for key in ACTIONS:
            if ack[key] != o[key]:
                changes[key].append(ack["sim_time_ns"] / 1e6)
    reporting = audit_reports(log, decisions, acks, duration_s) if any(
        r["type"] == "report_settings" for r in log
    ) else {}
    bits = Counter()
    for item in log:
        if item["type"] == "report":
            bits[item["domain"]] += item["bits"]
    vector, = case.glob("*.vec")
    flows = list(extract_flows({"radio": "1", "wired": "1"}, load_vectors(vector, include)))
    burst = {r["flow"]: r for r in flows if r["window"] == "burst"}
    control = burst["control"]
    video = burst["video"]
    change_times = {
        key: " ".join(f"{value:g}" for value in values) for key, values in changes.items()
    }
    return dict(scheduler=scheduler, seed=seed, codec=codec, control_on_time=control["on_time_20ms"],
                control_sent=control["sent"],
                control_sla=int(100 * control["on_time_20ms"] >= 99 * control["sent"]),
                video_mbps=round(video["goodput_mbps"], 6), video_on_time=video["on_time_20ms"],
                video_delivered=video["delivered"],
                competitor_delivered=burst["radio_competitor"]["delivered"],
                no_candidate=sum(d["selected"] is None for d in decisions),
                path_changes_ms=change_times["path_id"],
                ran_changes_ms=change_times["ran_bands"],
                core_changes_ms=change_times["upf_video_rate_bps"],
                uplink_bits=sum(bits.values()), uplink_bps=round(sum(bits.values()) / duration_s, 2),
                **{f"{k}_bits": bits[k] for k in DOMAIN_IDS}, **reporting)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    cases = sorted(entry.parent for entry in args.results.glob("*/controller.log"))
    if not cases:
        parser.error(f"No simulation cases in {args.results}")
    rows = [summarize(case, *case.name.split("-", 2)) for case in cases]
    fields = list(dict.fromkeys(key for row in rows for key in row))
    writer = csv.DictWriter(sys.stdout, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
