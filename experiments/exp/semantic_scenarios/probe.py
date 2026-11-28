"""Run same-prefix PF forks and report measured control SLA and preferences."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
from itertools import product
import json
from pathlib import Path
import socket
import subprocess
from threading import Thread

from core_admission.extract import ADMITTED, DROPPED, N6
from dual_ue.extract import FLOWS, NETWORK, include
from ladder_controller import serve
from ladder_kpis import collect_flows, load_vectors, percentile
from semantic_scenarios.wire import measure_wire


HERE = Path(__file__).resolve().parent
MS = 1_000_000


def digest(items):
    return hashlib.sha256(json.dumps(items, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def actions(manifest):
    axes = manifest["candidate_axes"]
    return {
        f"{path}-{bands}-{rate // 1_000_000}m": {
            "path_id": path, "ran_bands": bands, "upf_video_rate_bps": rate,
        }
        for path, bands, rate in product(axes["path_id"], axes["ran_bands"], axes["upf_video_rate_bps"])
    }


def measure(case, scene, action, initial):
    vector, = case.glob("*.vec")
    vectors = load_vectors(vector, lambda mod, sig: mod == N6 or include(mod, sig))
    start, stop = [stamp / 1000 for stamp in scene["evaluation_window_ms"]]
    fork_ns = scene["source_time_ms"] * MS
    trace = [json.loads(line) for line in (case / "routes.jsonl").read_text().splitlines()]
    prefix = [r for r in trace if r["sim_time_ns"] < fork_ns
              or (r["sim_time_ns"] == fork_ns and r["type"] == "observation")]
    acks = [r for r in trace if r["sim_time_ns"] == fork_ns and r["type"] == "ack"]
    observations = [r for r in trace if r["sim_time_ns"] == fork_ns and r["type"] == "observation"]
    restore_ns = fork_ns + scene["action_hold_ms"] * MS
    restore = [r for r in trace if r["sim_time_ns"] == restore_ns and r["type"] == "ack"]
    if (len(restore) != 1 or restore[0]["status"] not in {"applied", "unchanged"}
            or any(restore[0][key] != value for key, value in initial.items())):
        raise ValueError(f"{case}: invalid post-hold readback")
    if (len(acks) != 1 or len(observations) != 1
            or any(observations[0][key] != value for key, value in initial.items()) or acks[0]["status"] not in {"applied", "unchanged"}
            or any(acks[0][key] != value for key, value in action.items())):
        raise ValueError(f"{case}: invalid fork acknowledgement")
    pairs = [(s, t) for s, t, _ in FLOWS.values()]
    reverse = {v[0]: k for k, v in FLOWS.items()}
    endpoints = {}
    local_start, local_stop = [stamp / 1000 for stamp in
                               scene.get("local_evaluation_window_ms", [start * 1000, start * 1000 + 100])]
    local_control = {}
    for source, _, sent, received, _ in collect_flows(vectors, NETWORK, pairs):
        sequences = [i for i, (t, _, _) in enumerate(sent) if start <= t < stop]
        rx = [received[i] for i in sequences if i in received]
        deadlines = [size for d, size in rx if d * 1000 <= 20]
        name = reverse[source]
        if name == "control":
            local = [i for i, (t, _, _) in enumerate(sent) if local_start <= t < local_stop]
            local_control = {
                "sent": len(local),
                "on_time_20ms": sum(i in received and received[i][0] * 1000 <= 20 for i in local),
            }
        endpoints[name] = {
            "sent": len(sequences), "delivered": len(rx), "on_time_20ms": len(deadlines),
            "payload_bits": sum(b for _, b in rx) * 8,
            "on_time_20ms_payload_bits": sum(deadlines) * 8,
            "p99_delivered_ms": percentile([d * 1000 for d, _ in rx], .99) if rx else None,
        }
    control = endpoints["control"]
    if control["sent"] == 0:
        raise ValueError(f"{case}: empty control cohort")

    def window(mod, signal):
        return [v for t, _, v in vectors[mod, signal] if start <= t < stop]

    radio = f"{NETWORK}.gnb1.cellularNic.mac.schedulerDl"
    queue = f"{NETWORK}.NE1.eth[1].queue.queue"
    core_admitted = window(N6, ADMITTED)
    core_dropped = window(N6, DROPPED)
    all_send = [(mod, [(t, value) for t, _, value in arr])
                for (mod, sig), arr in sorted(vectors.items()) if sig == "packetSent:vector(packetBytes)"]
    summary = {
        "prefix_state_sha256": digest([prefix,
            [(mod, sig, [event for event in arr if event[0] < start])
             for (mod, sig), arr in sorted(vectors.items()) if any(e[0] < start for e in arr)]]),
        "source_trace_sha256": digest(all_send),
        "fork_readback": {key: acks[0][key] for key in (*action, "upf_video_capacity_bps", "upf_video_enforced_bps")},
        "sla_feasible": control["on_time_20ms"] * 100 >= control["sent"] * 99,
        "flows": endpoints,
        "local_control_100ms": local_control,
        "video_on_time_20ms_payload_bits": endpoints["video"]["on_time_20ms_payload_bits"],
        "cell_rb_slots": int(sum(window(radio, "controlledDlAllocatedBlocks"))),
        "ue0_rb_slots": int(sum(window(radio, "ue0DlAllocatedBlocks"))),
        "ue1_rb_slots": int(sum(window(radio, "ue1DlAllocatedBlocks"))),
        "n6_offered_video_packets": len(core_admitted) + len(core_dropped),
        "n6_admitted_video_packets": len(core_admitted),
        "n6_dropped_video_packets": len(core_dropped),
        "left_queue1_peak_packets": max(window(f"{queue}[1]", "queueLength:vector"), default=0),
        "left_queue2_peak_packets": max(window(f"{queue}[2]", "queueLength:vector"), default=0),
        **measure_wire(case, start, stop),
    }
    return summary


def execute(sim, out, scene, action_id, action, initial):
    case = out / f'{scene["scenario_id"]}-{scene["seed"]}-{action_id}'
    case.mkdir()
    fork = scene["source_time_ms"] * MS
    restore = fork + scene["action_hold_ms"] * MS
    schedule = {fork: action, restore: initial}
    errors = []

    def decide(obs):
        choice = schedule.get(obs["sim_time_ns"])
        return {"type": "apply_route_resources", **choice} if choice is not None else None

    with socket.socket() as listener, (case / "run.log").open("x", encoding="utf-8") as log:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        def controller():
            try:
                serve(listener, decide, on_ack=lambda ack: None)
            except Exception as exc:
                errors.append(exc)

        thread = Thread(target=controller, daemon=True)
        thread.start()
        cmd = [str(sim / "bin/simu5g"), "-n", str(out / "ned"), "-l", str(out / "build/dualue"),
               "-f", str(HERE / "scenarios.ini"), "-u", "Cmdenv", "-c", scene["config"], "-r", "0",
               f'--seed-set={scene["seed"]}', f"--result-dir={case}",
               f"--*.routeController.port={listener.getsockname()[1]}"]
        cmd.extend(f"--{key}={value}" for key, value in scene["ini_overrides"].items())
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=90, check=False)
        thread.join(timeout=15)
        if proc.returncode or errors or thread.is_alive():
            raise RuntimeError(f"{case}: simulator exit {proc.returncode}, controller errors {errors!r}")
    return scene["split_group"], action_id, measure(case, scene, action, initial)


def preference_value(row, spec):
    directions = {"max": 1, "min": -1}
    return sum(directions[t["direction"]] * t["weight"] * row[t["metric"]] / t["scale"]
               for t in spec["terms"])


def write_results(out, manifest, scenes, by_group, selected):
    index_rows = []
    with (out / "paired.jsonl").open("x", encoding="utf-8") as jsonl:
        for scene in scenes:
            group = scene["split_group"]
            group_rows = by_group[group]
            if set(group_rows) != set(selected):
                raise ValueError(f"{group}: incomplete action family")
            ordered = {key: group_rows[key] for key in selected}
            for field in ("prefix_state_sha256", "source_trace_sha256"):
                if len({row[field] for row in ordered.values()}) != 1:
                    raise ValueError(f"{group}: action forks disagree on {field}")
            feasible = [key for key, row in ordered.items() if row["sla_feasible"]]
            winners = {}
            for pref in scene["preference_ids"]:
                spec = manifest["preferences"][pref]
                scores = {key: preference_value(ordered[key], spec) for key in feasible}
                winners[pref] = [key for key in scores if abs(scores[key] - max(scores.values())) < 1e-12]
            jsonl.write(json.dumps(dict(scene, units=manifest["units"], flow_contract=manifest["flows"],
                                        preference_specs={p: manifest["preferences"][p] for p in winners},
                                        feasible_action_ids=feasible, preference_winners=winners, outcomes=ordered),
                                   sort_keys=True) + "\n")
            for action_id, row in ordered.items():
                control, video = row["flows"]["control"], row["flows"]["video"]
                index_rows.append({
                    "scenario_id": scene["scenario_id"], "split": scene["split"], "split_group": group,
                    "seed": scene["seed"], "action_id": action_id,
                    "control_sent": control["sent"], "control_on_time_20ms": control["on_time_20ms"],
                    "control_p99_ms": control["p99_delivered_ms"], "sla_feasible": row["sla_feasible"],
                    "video_sent": video["sent"], "video_delivered": video["delivered"],
                    "video_on_time_20ms": video["on_time_20ms"],
                    "n6_dropped_video_packets": row["n6_dropped_video_packets"],
                    "left_queue2_peak_packets": row["left_queue2_peak_packets"],
                    "ue0_rb_slots": row["ue0_rb_slots"], "n3_ip_bit_hops": row["n3_ip_bit_hops"],
                })
    with (out / "paired.csv").open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(index_rows[0]))
        writer.writeheader()
        writer.writerows(index_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sim", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--manifest", type=Path, default=HERE / "scenario-manifest-v1.0.json")
    parser.add_argument("--split", choices=("discovery", "train", "validation", "test"), nargs="+", required=True)
    parser.add_argument("--actions", nargs="+")
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()
    if args.jobs < 1 or ("test" in args.split and len(args.split) != 1):
        parser.error("Use positive jobs and run the reserved test split alone")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    available = actions(manifest)
    selected = args.actions or list(available)
    if len(set(selected)) != len(selected) or any(key not in available for key in selected):
        parser.error("Unknown or duplicate action")
    scenes = [s for s in manifest["scenarios"] if s["split"] in args.split]
    if not scenes or len({s["split_group"] for s in scenes}) != len(scenes):
        parser.error("Selected scenario manifest is empty or has duplicate groups")
    args.out.joinpath("input-manifest.json").write_bytes(args.manifest.read_bytes())
    grouped = {scene["split_group"]: {} for scene in scenes}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(execute, args.sim, args.out, scene, key, available[key],
                               manifest["initial_action"]) for scene, key in product(scenes, selected)]
        for position, future in enumerate(as_completed(futures), 1):
            group, key, result = future.result()
            grouped[group][key] = result
            if position % 10 == 0 or position == len(futures):
                print(f"Finished {position}/{len(futures)}", flush=True)
    write_results(args.out, manifest, scenes, grouped, selected)


if __name__ == "__main__":
    main()
