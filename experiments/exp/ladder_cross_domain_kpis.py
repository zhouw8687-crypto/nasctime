#!/usr/bin/env python3
"""Verify the coordinated baseline against command, gate, radio and packet traces."""

import argparse
import bisect
import csv
import json
import sys
from pathlib import Path

from ladder_control_kpis import check
from ladder_kpis import QUEUE, load_vectors


NOMINAL = (20_000_000, 600, 4)
PROTECTION = (2_000_000, 1600, 6)
CONFIGS = ("CrossDomainFixedNominal", "CrossDomainFixedProtect",
           "CrossDomainExternal", "CrossDomainExternalShifted")


def observation_profile(event):
    return event["core"]["rate_bps"], event["transport"]["priority_window_us"], event["ran"]["dl_band_budget"]


def check_policy_trace(directory, events):
    observations = [row for row in events if row["type"] == "observation"]
    check(
        [row["sim_time_ns"] for row in observations] == list(range(200_000_000, 1_600_000_001, 20_000_000)),
        f"{directory.name}: incomplete observation series",
    )
    fixed_protection = directory.name == "CrossDomainFixedProtect"
    profile = PROTECTION if fixed_protection else NOMINAL
    initial = profile
    generation = 0
    transitions = {}
    cursor = 0
    for obs in observations:
        when = obs["sim_time_ns"]
        check(
            events[cursor] == obs and observation_profile(obs) == profile and obs["generation"] == generation,
            f"{directory.name}: settings do not persist through {when}",
        )
        cursor += 1
        if "External" not in directory.name:
            continue
        received, ack = events[cursor:cursor + 2]
        cursor += 2
        command = received["decision"]
        action = command["action"]
        check(
            received["type"] == "received_decision" and ack["type"] == "ack"
            and obs["request_id"] == received["request_id"] == command["request_id"] == ack["request_id"]
            and when == received["sim_time_ns"] == ack["sim_time_ns"]
            and command["base_generation"] == generation,
            f"{directory.name}: command association mismatch at {when}",
        )
        if action is None:
            check(ack["status"] == "noop" and not ack["changed_domains"],
                  f"{directory.name}: write without a command at {when}")
        else:
            target = action["rate_bps"], action["priority_window_us"], action["bands"]
            check(
                action["type"] == "apply_cross_domain" and {target, profile} == {NOMINAL, PROTECTION}
                and ack["status"] == "applied" and set(ack["changed_domains"]) == {"core", "transport", "ran"}
                and when % (obs["transport"]["cycle_us"] * 1000) == 0,
                f"{directory.name}: incomplete or mistimed policy application at {when}",
            )
            profile = target
            generation += 1
            transitions[when] = profile
        readback = ack["rate_bps"], ack["priority_window_us"], ack["dl_band_budget"]
        check(readback == profile and ack["generation"] == generation,
              f"{directory.name}: execution readback differs at {when}")
    check(cursor == len(events), f"{directory.name}: unpaired controller events")
    if "External" in directory.name:
        check(initial == profile and len(transitions) >= 2, f"{directory.name}: missing protection or recovery")
    return initial, transitions, observations


def check_data_plane(directory, initial, transitions, observations):
    with (directory / "packet-trace.csv").open(encoding="utf-8", newline="") as handle:
        policer_losses = [row for row in csv.DictReader(handle) if row["first_unobserved"] == "upf_n3_tx_ns"]
    check(
        len(policer_losses) == observations[-1]["core"]["dropped_packets"]
        and all(row["flow"] == "background" for row in policer_losses),
        f"{directory.name}: UPF counters disagree with the packet traces",
    )
    (vector,) = directory.glob("*.vec")
    signals = {"controlledDlAllocatedBlocks", "queueingTime:vector", "gateState:vector"}
    vectors = load_vectors(vector, lambda _, name: name in signals)
    ((_, samples),) = [(mod, entries) for (mod, name), entries in vectors.items()
                       if name == "controlledDlAllocatedBlocks"]
    check(bool(samples), f"{directory.name}: missing downlink scheduler allocations")
    switch_times = list(transitions)
    profiles = [initial, *transitions.values()]
    peak_by_budget = {}
    for time, _, blocks in samples:
        # Scheduler runs before the bridge when events have the same simulation timestamp.
        budget = profiles[bisect.bisect_left(switch_times, round(time * 1e9))][2]
        check(0 <= blocks <= budget, f"{directory.name}: allocation exceeded {budget} at {time}s")
        peak_by_budget[budget] = max(peak_by_budget.get(budget, 0), int(blocks))
    if transitions:
        check(peak_by_budget.get(PROTECTION[2], 0) > NOMINAL[2],
              f"{directory.name}: larger radio budget did not increase measured allocations")

    departures = 0
    cycle_ns = observations[0]["transport"]["cycle_us"] * 1000
    for (queue, name), entries in vectors.items():
        if name != "queueingTime:vector" or not entries:
            continue
        match = QUEUE.fullmatch(queue)
        check(match is not None, f"{directory.name}: unexpected TAS queue path")
        shaper, index = match.groups()
        states = sorted(vectors[(f"{shaper}.transmissionGate[{index}]", "gateState:vector")])
        for time, event, _ in entries:
            gate_index = bisect.bisect_right(states, (time, event, float("inf"))) - 1
            stamp = round(time * 1e9)
            window = profiles[bisect.bisect_right(switch_times, stamp)][1]
            expected_open = (stamp % cycle_ns < window * 1000) == (index == "2")
            check(gate_index >= 0 and states[gate_index][2] == 1 and expected_open,
                  f"{directory.name}: {queue} departed outside the commanded gate window at {time}s")
        departures += len(entries)
    check(departures > 0, f"{directory.name}: no TAS departures")
    return len(policer_losses), departures, peak_by_budget


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    root = parser.parse_args().result_dir
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow([
        "config", "burst_start_s", "burst_end_s", "priority_sent", "priority_delivered", "priority_p99_ms",
        "background_sent", "background_delivered", "upf_drops_total", "ne1_gate_departures",
        "peak_dl_blocks_by_budget", "policy_switches_ms",
    ])
    first_switches = []
    for config in CONFIGS:
        directory = root / config
        with (directory / "control.jsonl").open(encoding="utf-8") as handle:
            initial, transitions, observations = check_policy_trace(directory, list(map(json.loads, handle)))
        drops, departures, peaks = check_data_plane(directory, initial, transitions, observations)
        with (directory / "flows.csv").open(encoding="utf-8", newline="") as handle:
            priority, background = [row for row in csv.DictReader(handle) if row["window"] == "phase_2"]
        if transitions:
            first_switches.append(next(iter(transitions)))
        writer.writerow([
            config, priority["start_s"], priority["stop_s"], priority["sent"], priority["delivered"],
            f"{float(priority['p99_us']) / 1000:.3f}", background["sent"], background["delivered"],
            drops, departures, " ".join(f"{budget}:{count}" for budget, count in sorted(peaks.items())),
            " ".join(str(time // 1_000_000) for time in transitions),
        ])
    check(first_switches[1] - first_switches[0] == 200_000_000,
          "the first joint policy did not follow the 200 ms change in traffic")


if __name__ == "__main__":
    main()
