#!/usr/bin/env python3
"""Verify the built-in ladder experiment and print a cross-domain KPI table."""

import argparse
import csv
import json
import sys
from pathlib import Path


CONFIGS = ("ControllerBaseline", "ControllerStaticCap", "ControllerExternal", "ControllerExternalShifted")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def analyze(directory):
    with (directory / "control.jsonl").open(encoding="utf-8") as handle:
        events = [json.loads(line) for line in handle]
    observations = [event for event in events if event["type"] == "observation"]
    check(
        [obs["sim_time_ns"] for obs in observations] == list(range(200_000_000, 1_600_000_001, 20_000_000)),
        f"{directory.name}: incomplete sample series",
    )
    external = directory.name.startswith("ControllerExternal")
    actions = []
    if external:
        check(len(events) == len(observations) * 3, f"{directory.name}: missing control events")
        for index, obs in enumerate(observations):
            start = index * 3
            check(
                [event["type"] for event in events[start:start + 3]] == ["observation", "received_decision", "ack"],
                f"{directory.name}: events out of order",
            )
            received, ack = events[start + 1:start + 3]
            decision = received["decision"]
            check(
                obs["request_id"] == received["request_id"] == decision["request_id"] == ack["request_id"]
                and obs["sim_time_ns"] == received["sim_time_ns"] == ack["sim_time_ns"]
                and decision["base_generation"] == obs["generation"],
                f"{directory.name}: command/feedback identity mismatch",
            )
            action = decision["action"]
            if action is None:
                check(
                    ack["status"] == "noop" and ack["generation"] == obs["generation"]
                    and ack["rate_bps"] == obs["core"]["rate_bps"],
                    f"{directory.name}: rate changed without a command",
                )
            else:
                check(
                    ack["status"] == "applied" and ack["generation"] == obs["generation"] + 1
                    and ack["rate_bps"] == action["rate_bps"] and ack["flow_id"] == action["flow_id"]
                    and ack["rate_bps"] != obs["core"]["rate_bps"],
                    f"{directory.name}: incorrect execution readback",
                )
                actions.append(ack["sim_time_ns"])
            if index + 1 < len(observations):
                following = observations[index + 1]
                check(
                    following["generation"] == ack["generation"] and following["core"]["rate_bps"] == ack["rate_bps"],
                    f"{directory.name}: execution did not persist",
                )
        check(actions and observations[-1]["core"]["rate_bps"] == 20_000_000, f"{directory.name}: no throttle/recovery")
    else:
        check(len(events) == len(observations), f"{directory.name}: unexpected control events")

    dropped = observations[-1]["core"]["dropped_packets"]
    with (directory / "packet-trace.csv").open(encoding="utf-8", newline="") as handle:
        missing_n3 = [row for row in csv.DictReader(handle) if row["first_unobserved"] == "upf_n3_tx_ns"]
    check(
        len(missing_n3) == dropped and all(row["flow"] == "background" for row in missing_n3),
        f"{directory.name}: policer counters disagree with application sequences at N6/N3",
    )
    with (directory / "flows.csv").open(encoding="utf-8", newline="") as handle:
        flows = {(row["source"], row["window"]): row for row in csv.DictReader(handle)}
    return observations, actions, flows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    root = parser.parse_args().result_dir
    results = {name: analyze(root / name) for name in CONFIGS}
    first_action = {name: results[name][1][0] for name in CONFIGS if results[name][1]}
    check(
        first_action["ControllerExternalShifted"] - first_action["ControllerExternal"] == 200_000_000,
        "the first control action did not follow the 200 ms change in traffic",
    )
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow([
        "config", "sent_from_s", "sent_until_s", "priority_sent", "priority_delivered", "priority_p99_ms",
        "background_sent", "background_delivered", "upf_dropped_total", "peak_ran_sample_bytes",
        "peak_ne1_background_queue_packets", "applied_actions_sim_ms",
    ])
    for name, (observations, actions, flows) in results.items():
        priority = flows["server.app[0]", "phase_2"]
        background = flows["server.app[1]", "phase_2"]
        writer.writerow([
            name, priority["start_s"], priority["stop_s"], priority["sent"], priority["delivered"],
            f"{float(priority['p99_us']) / 1000:.3f}", background["sent"], background["delivered"],
            observations[-1]["core"]["dropped_packets"],
            max(obs["ran"]["dl_mac_virtual_buffer_bytes"] for obs in observations),
            max(obs["transport"]["background_queue_packets"] for obs in observations),
            " ".join(str(time // 1_000_000) for time in actions),
        ])


if __name__ == "__main__":
    main()
