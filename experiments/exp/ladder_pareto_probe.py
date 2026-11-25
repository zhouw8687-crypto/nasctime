#!/usr/bin/env python3
"""Measure every discrete cross-domain action from the same nominal prefix."""

import argparse
import concurrent.futures
import itertools
import json
import socket
import subprocess
from pathlib import Path

from competition_trace import PAIRS
from ladder_controller import serve
from ladder_kpis import APP_SIGNALS, collect_flows, load_vectors, percentile


REPO = Path(__file__).resolve().parents[2]
SCENARIO = REPO / "nascTime/simulations/demos/e2e_ladder"
TICKS_NS = tuple(range(580_000_000, 660_000_001, 20_000_000))
WINDOW = (0.66, 1.0)
CRITICAL_DEADLINE_S = .020
BACKGROUND_DEADLINE_S = .100
MIN_CRITICAL_FRACTION = .95
RATES = (2_000_000, 4_000_000, 20_000_000)
WINDOWS = (600, 1100, 1600)
BANDS = (4, 5, 6)
ACTIONS = tuple(itertools.product(RATES, WINDOWS, BANDS))


def workloads():
    train = [(gap, x, link, 0) for gap, x, link in itertools.product((500, 850, 1400, 2400), (120, 255, 400), (10, 100))]
    test = [(gap, x, link, seed) for gap, (x, link, seed) in itertools.product(
        (650, 1100, 1900, 2800), ((170, 10, 1), (345, 100, 2))
    )]
    return {
        group: [
            {"id": f"{group}-{index:02d}", "burst_gap_us": gap, "ue_x_m": x, "link_mbps": link, "seed": seed}
            for index, (gap, x, link, seed) in enumerate(rows)
        ]
        for group, rows in (("train", train), ("test", test))
    }


def resource_cost(action):
    _, window, bands = action
    # Sum of the fractional reservation of the radio and the gate cycle.
    return bands / max(BANDS) + window / 5000


def evaluate(folder):
    (vector,) = folder.glob("*.vec")
    vectors = load_vectors(vector, lambda _, name: name in APP_SIGNALS)
    scores = {}
    for (_, _, sent, delivery, _), (flow, deadline) in zip(
        collect_flows(vectors, "ControlledCompetition", PAIRS),
        (("critical", CRITICAL_DEADLINE_S), ("background", BACKGROUND_DEADLINE_S)), strict=True,
    ):
        cohort = [seq for seq, (time, _, _) in enumerate(sent) if WINDOW[0] <= time < WINDOW[1]]
        received = [delivery[seq] for seq in cohort if seq in delivery]
        on_time = [size for delay, size in received if delay <= deadline + 1e-12]
        scores[flow] = {
            "sent": len(cohort), "received": len(received), "on_time": len(on_time),
            "on_time_fraction": len(on_time) / len(cohort),
            "on_time_mbps": sum(on_time) * 8 / ((WINDOW[1] - WINDOW[0]) * 1e6),
            "p99_ms": percentile([delay for delay, _ in received], .99) * 1000 if received else None,
        }
    return scores


def run_case(case, folder, choose):
    folder.mkdir()
    observations = []
    acknowledgements = []
    actions = []

    def decide(observation):
        observations.append(observation)
        selected = choose(observation)
        if selected is None:
            return None
        if selected not in ACTIONS or observation["sim_time_ns"] != TICKS_NS[-1]:
            raise ValueError(f"Invalid policy action {selected} at {observation['sim_time_ns']}")
        actions.append(selected)
        rate, window, bands = selected
        return {"type": "apply_cross_domain", "rate_bps": rate, "priority_window_us": window, "bands": bands}

    gap = case["burst_gap_us"]
    link = case["link_mbps"]
    with socket.socket() as listener, (folder / "run.log").open("w", encoding="utf-8") as log:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        command = [
            "../../../bin/nasctime-run.sh", "-f", "omnetpp_pareto.ini", "-u", "Cmdenv",
            "-c", "ParetoProbe", "-r", "0",
            f"--result-dir={folder}", f"--seed-set={case['seed']}",
            f"--*.controller.port={listener.getsockname()[1]}",
            f"--*.ue[0].mobility.initialX={case['ue_x_m']}m",
            f"--*.server.app[1].sendInterval=simTime() >= 600ms && simTime() < 1s ? {gap}us : 8ms",
            *[f"--*.NE{ne}.eth[1].{parameter}={link}Mbps"
              for ne in (1, 3) for parameter in ("bitrate", "queue.bitrate")],
        ]
        with subprocess.Popen(command, cwd=SCENARIO, stdout=log, stderr=subprocess.STDOUT) as simulator:
            try:
                serve(listener, decide, acknowledgements.append)
                if simulator.wait(timeout=15) != 0:
                    raise RuntimeError(f"Simulation failed. See {folder / 'run.log'}")
            finally:
                if simulator.poll() is None:
                    simulator.terminate()
                    simulator.wait(timeout=5)

    if tuple(obs["sim_time_ns"] for obs in observations) != TICKS_NS or len(actions) != 1:
        raise ValueError(f"{folder}: simulation did not complete the common prefix and one decision")
    ack = acknowledgements[-1]
    action, = actions
    actual = ack["rate_bps"], ack["priority_window_us"], ack["dl_band_budget"]
    if ack["status"] not in ("applied", "unchanged") or actual != action:
        raise ValueError(f"{folder}: wrong execution readback {ack}")
    scores = evaluate(folder)
    result = {"action": action, "scores": scores, "resource_cost": resource_cost(action),
              "observations": observations, "ack": ack}
    with (folder / "result.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True)
    return result


def run_oracle(root, jobs, limit):
    candidates = workloads()
    if limit is not None:
        candidates = {group: rows[:limit] for group, rows in candidates.items()}
    folders = {case["id"]: root / case["id"] for rows in candidates.values() for case in rows}
    for folder in folders.values():
        folder.mkdir()

    def worker(case, index, action):
        folder = folders[case["id"]] / f"action-{index:02d}"
        return run_case(case, folder, lambda obs: action if obs["sim_time_ns"] == TICKS_NS[-1] else None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            case["id"]: [executor.submit(worker, case, index, action) for index, action in enumerate(ACTIONS)]
            for rows in candidates.values() for case in rows
        }
        for group, rows in candidates.items():
            for case in rows:
                results = [job.result() for job in futures[case["id"]]]
                common = results[0]["observations"]
                if any(result["observations"] != common for result in results):
                    raise ValueError(f"{case['id']}: choices do not share the same observations before applying")
                case["observations"] = common
                case["outcomes"] = [{key: result[key] for key in ("action", "scores", "resource_cost")}
                                    for result in results]
                print(f"{group} {case['id']}: {len(results)} actions validated", flush=True)
    with (root / "oracle.json").open("w", encoding="utf-8") as handle:
        json.dump(candidates, handle, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--limit", type=int, help="limit the workloads in each split for a smoke run")
    args = parser.parse_args()
    if args.jobs < 1 or (args.limit is not None and args.limit < 1):
        parser.error("--jobs and --limit must be positive")
    root = args.result_dir.resolve()
    root.mkdir()
    revision = subprocess.check_output(["git", "-C", REPO, "rev-parse", "HEAD"], text=True)
    status = subprocess.check_output(["git", "-C", REPO, "status", "--porcelain"], text=True)
    (root / "revision.txt").write_text(revision + status, encoding="utf-8")
    run_oracle(root, args.jobs, args.limit)


if __name__ == "__main__":
    main()
