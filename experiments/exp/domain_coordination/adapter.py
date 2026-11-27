"""Run either ladder policy on the existing TCP protocol or replay observations."""

import argparse
from collections import deque
from contextlib import ExitStack
from dataclasses import asdict
import json
from pathlib import Path
import socket
import sys

from .baseline import (
    MS, Budgets, CoreState, Intent, PathState, RanState, Stamp, TransportState,
    combine, core_candidates, ran_candidates, select_autonomous, solve_full,
    transport_candidates,
)

DEFAULT_INTENT = Intent()
BUDGETS = Budgets()
STATE_LIFETIME_NS = 40 * MS
LOAD_WINDOW_NS = 100 * MS
ACTIONS = ("path_id", "ran_bands", "upf_video_rate_bps")


def serialize(item):
    return None if item is None else {
        "action": item.action(),
        "video_bps": item.video_bps,
        "control_delay_ns": item.control_delay_ns,
        "feasible": item.feasible,
        "violations": item.violations,
    }


class LadderPolicy:
    def __init__(self, mode, log, legacy=False, intent=DEFAULT_INTENT):
        self.mode = mode
        self.intent = intent
        self.log = log
        self.legacy = legacy
        self.load_samples = deque()

    def offered_video(self, now_ns, packets):
        if self.load_samples:
            last_ns, last_count = self.load_samples[-1]
            if now_ns <= last_ns or packets < last_count:
                raise ValueError("Non-monotonic UPF observation stream")
        self.load_samples.append((now_ns, packets))
        while len(self.load_samples) > 1 and self.load_samples[1][0] <= now_ns - LOAD_WINDOW_NS:
            self.load_samples.popleft()
        before_ns, before_packets = self.load_samples[0]
        if before_ns == now_ns:
            return self.intent.video_target_bps
        return (packets - before_packets) * 8_000 * 1_000_000_000 // (now_ns - before_ns)

    def states(self, obs):
        now_ns = obs["sim_time_ns"]
        stamp = Stamp(now_ns, now_ns + STATE_LIFETIME_NS)
        if self.legacy:
            ran = RanState(stamp, 24, 0)
            core = CoreState(stamp, self.intent.video_target_bps)
            transport = {path: {"available": True, "control_queue_bits": 0, "egress_bps": rate}
                         for path, rate in (("direct", 10_000_000), ("detour", 100_000_000))}
        else:
            ran = RanState(stamp, obs["ran"]["max_bands"], obs["ran"]["mac_backlog_bytes"])
            core_obs = obs["core"]
            offered = self.offered_video(now_ns, core_obs["offered_video_packets"])
            core = CoreState(stamp, offered, burst_bytes=core_obs["burst_bytes"])
            transport = obs["transport"]

        paths = []
        for path, hops, delay, congested in (
            ("direct", 2, 2 * MS, 224_000),
            ("detour", 4, 3 * MS, 0),
        ):
            link = transport[path]
            paths.append(PathState(path, link["available"], obs[f"{path}_queue_packets"],
                                   link["control_queue_bits"], link["egress_bps"],
                                   hops, delay, congested))
        return ran, TransportState(stamp, obs["path_id"], tuple(paths)), core

    def __call__(self, obs):
        return self.choose_from_states(obs, self.states(obs))

    def choose_from_states(self, obs, states):
        now_ns = obs["sim_time_ns"]
        ran, transport, core = states
        if self.mode == "full":
            decision = solve_full(ran, transport, core, BUDGETS, self.intent, now_ns)
            item = decision.selected
            evaluated = [serialize(combo) for combo in decision.evaluated]
            front = [serialize(combo) for combo in decision.front]
            local = None
            reason = "no_feasible_combination"
        else:
            tables = (
                ran_candidates(ran, BUDGETS.ran, self.intent, now_ns),
                transport_candidates(transport, BUDGETS.transport, self.intent, now_ns),
                core_candidates(core, BUDGETS.core, self.intent, now_ns),
            )
            choices = [select_autonomous(table) for table in tables]
            local = [{**asdict(choice), "feasible": choice.feasible} if choice else None
                     for choice in choices]
            # Combine after the independent choices. This diagnostic does not re-rank them.
            item = combine(*choices, self.intent) if all(choices) else None
            evaluated, front = [], []
            reason = "no_feasible_local_candidate"

        action = None if item is None else item.action()
        if action is not None:
            if all(action[key] == obs[key] for key in ACTIONS):
                action, reason = None, "already_active"
            else:
                reason = "update"
        self.write({
            "type": "policy", "mode": self.mode, "request_id": obs["request_id"],
            "source": "legacy_assumptions" if self.legacy else "instrumented",
            "sim_time_ns": now_ns, "planned_effective_ns": now_ns if action else None,
            "base_generation": obs["generation"], "intent": asdict(self.intent),
            "ran": asdict(ran), "transport": asdict(transport), "core": asdict(core),
            "selected": serialize(item), "evaluated": evaluated, "front": front,
            "local_choices": local, "action": action, "reason": reason,
        })
        return action

    def write(self, row):
        print(json.dumps(row, allow_nan=False), file=self.log, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("full", "autonomous"), required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--video-target-bps", type=int, default=DEFAULT_INTENT.video_target_bps)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--port-file", type=Path)
    source.add_argument("--replay", type=Path)
    parser.add_argument("--legacy", action="store_true",
                        help="replay an old resource-enabled trace with explicit telemetry assumptions")
    args = parser.parse_args()
    if args.video_target_bps <= 0:
        parser.error("--video-target-bps must be positive")
    if args.legacy and not args.replay:
        parser.error("--legacy requires --replay")
    with ExitStack() as stack:
        policy = LadderPolicy(args.mode, stack.enter_context(args.log.open("w", encoding="utf-8")),
                              args.legacy, Intent(video_target_bps=args.video_target_bps))
        if args.replay:
            count = 0
            with args.replay.open(encoding="utf-8") as stream:
                for line in stream:
                    event = json.loads(line)
                    if event["type"] == "observation":
                        policy(event)
                        count += 1
            if not count:
                parser.error("no observations in replay trace")
            return

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from ladder_controller import serve

        listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        args.port_file.write_text(f"{listener.getsockname()[1]}\n", encoding="ascii")
        serve(listener, policy, on_ack=policy.write)


if __name__ == "__main__":
    main()
