"""Replay a common live GCC prefix, branch once, then resume closed-loop GCC."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from itertools import product
import json
from pathlib import Path
import socket
import subprocess
from threading import Thread

from domain_coordination.adapter import ACTIONS as ACTUATORS, LadderPolicy
from domain_coordination.baseline import BANDS, MS, RATES_BPS
from ladder_controller import serve

FORKS = {280: "stable_before", 400: "burst_onset", 420: "approaching_switch", 440: "switch_to_detour",
         640: "stable_burst", 1020: "switch_to_direct", 1140: "stable_after"}
HOLD_MS = 100
DRAIN_MS = 4000
ACTION_GRID = {
    f"{route}-{bands}-{rate // 1_000_000}m": dict(
        type="apply_route_resources", path_id=route, ran_bands=bands, upf_video_rate_bps=rate
    )
    for route, bands, rate in product(("direct", "detour"), BANDS, RATES_BPS)
}


@dataclass(frozen=True)
class Run:
    seed: int
    fork_ms: int | None = None
    action_id: str | None = None

    @property
    def name(self):
        suffix = "reference" if self.fork_ms is None else f"{self.fork_ms}-{self.action_id}"
        return f"pf-{self.seed}-{suffix}"


class ForkPolicy(LadderPolicy):
    def __init__(self, run, log):
        super().__init__("full", log)
        self.run = run

    def __call__(self, obs):
        gcc_action = super().__call__(obs)
        if self.run.fork_ms is None:
            return gcc_action
        now = obs["sim_time_ns"]
        fork = self.run.fork_ms * MS
        if now == fork:
            return ACTION_GRID[self.run.action_id]
        if fork < now < fork + HOLD_MS * MS:
            return None
        return gcc_action


def run_simulator(sim, out, run, ini, config):
    case = out / run.name
    case.mkdir()
    with (case / "policy.jsonl").open("x", encoding="utf-8") as policy_log, \
            (case / "run.log").open("x", encoding="utf-8") as sim_log, \
            socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        errors = []

        def controller():
            try:
                serve(listener, ForkPolicy(run, policy_log), on_ack=lambda ack: None)
            except Exception as exc:
                errors.append(exc)

        port = listener.getsockname()[1]
        task = Thread(target=controller, daemon=True)
        task.start()
        cmd = [
            str(sim / "bin/simu5g"), "-n", str(out / "ned"), "-l", str(out / "build/dualue"),
            "-f", str(ini), "-u", "Cmdenv", "-c", config,
            "-r", "0", f"--seed-set={run.seed}", f"--result-dir={case}",
            f"--*.routeController.port={port}",
        ]
        proc = subprocess.run(cmd, stdout=sim_log, stderr=subprocess.STDOUT, timeout=90, check=False)
        task.join(timeout=15)
        if proc.returncode != 0 or errors or task.is_alive():
            raise RuntimeError(f"{case}: simulator exit {proc.returncode}, controller errors {errors!r}; "
                               "see run.log")
    return run.name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sim", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(5)))
    parser.add_argument("--forks", type=int, nargs="+", choices=sorted(FORKS), default=[point for point in FORKS if point != 400])
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--ini", type=Path, default=Path("counterfactual_teacher/scenario.ini"))
    parser.add_argument("--config", default="CounterfactualPf")
    parser.add_argument("--scenario-id", default="pf-dual-ue-both")
    parser.add_argument("--context", type=Path, help="JSON causal scenario configuration")
    args = parser.parse_args()
    if (args.config != "CounterfactualPf" or args.ini != Path("counterfactual_teacher/scenario.ini")) and (
        args.scenario_id == "pf-dual-ue-both" or args.context is None
    ):
        parser.error("custom configurations need a scenario ID and context JSON")
    context = json.loads(args.context.read_text()) if args.context else None
    if args.jobs < 1 or min(args.seeds) < 0 or len(set(args.seeds)) != len(args.seeds) or len(set(args.forks)) != len(args.forks):
        parser.error("specify distinct nonnegative seeds and fork points, and positive jobs")
    runs = [Run(seed) for seed in args.seeds]
    runs.extend(Run(seed, point, action) for seed, point, action in product(args.seeds, args.forks, ACTION_GRID))
    manifest = {"scenario_id": args.scenario_id, "config": args.config, "scenario_context": context,
                "seeds": args.seeds, "forks": args.forks,
                "hold_ms": HOLD_MS, "drain_ms": DRAIN_MS, "actions": ACTION_GRID,
                "runs": [asdict(run) for run in runs]}
    with (args.out / "matrix.json").open("x", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for index, name in enumerate(pool.map(lambda run: run_simulator(args.sim, args.out, run, args.ini, args.config), runs), 1):
            if index <= len(args.seeds) or index % 20 == 0 or index == len(runs):
                print(f"Finished {index}/{len(runs)} ({name})", flush=True)


if __name__ == "__main__":
    main()
