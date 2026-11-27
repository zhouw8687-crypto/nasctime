"""Verify online command/readback alignment and replay the live policy decisions."""

import argparse
from collections import Counter
import io
import json
from pathlib import Path

from .adapter import ACTIONS, LadderPolicy
from .baseline import Intent


def rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def verify(case):
    events = rows(case / "routes.jsonl")
    live = rows(case / "policy.jsonl")
    observations = [row for row in events if row["type"] == "observation"]
    commands = [row["decision"] for row in events if row["type"] == "received_decision"]
    acknowledgements = [row for row in events if row["type"] == "ack"]
    decisions = [row for row in live if row["type"] == "policy"]
    mode = case.name.split("-", 1)[0]
    replay = io.StringIO()
    applied = []
    paths = Counter()
    state_values = {"ran_mac_backlog_bytes": set(), "core_offered_video_bps": set()}
    if not observations or not decisions:
        raise ValueError(f"{case}: missing online observations or decisions")
    policy = LadderPolicy(mode, replay, intent=Intent(**decisions[0]["intent"]))
    for obs, command, ack, decision in zip(observations, commands, acknowledgements, decisions, strict=True):
        request = obs["request_id"]
        if request != command["request_id"] or request != ack["request_id"] or request != decision["request_id"]:
            raise ValueError(f"{case}: mismatched request IDs")
        if command["base_generation"] != obs["generation"] or obs["sim_time_ns"] != ack["sim_time_ns"]:
            raise ValueError(f"{case}: invalid base generation or application time")
        action = policy(obs)
        if action != decision["action"] or action != command["action"]:
            raise ValueError(f"{case} request {request}: replay differs from wire action")
        paths[ack["path_id"]] += 1
        state_values["ran_mac_backlog_bytes"].add(decision["ran"]["mac_backlog_bytes"])
        state_values["core_offered_video_bps"].add(decision["core"]["offered_video_bps"])
        if action is None:
            if ack["status"] != "noop" or ack["generation"] != obs["generation"] or any(
                ack[key] != obs[key] for key in ACTIONS
            ):
                raise ValueError(f"{case} request {request}: no-op changed an actuator")
        else:
            if ack["status"] != "applied" or ack["generation"] != obs["generation"] + 1 or any(
                ack[key] != action[key] for key in ACTIONS
            ):
                raise ValueError(f"{case} request {request}: actuator readback differs from command")
            applied.append({"sim_time_ns": ack["sim_time_ns"], "generation": ack["generation"],
                            "interface": ack["interface"], "gateway": ack["gateway"],
                            **{key: ack[key] for key in ACTIONS}})

    if decisions != [json.loads(line) for line in replay.getvalue().splitlines()]:
        raise ValueError(f"{case}: replay differs from live candidate tables")
    if acknowledgements != [row for row in live if row["type"] == "ack"]:
        raise ValueError(f"{case}: TCP acknowledgements differ from simulator trace")
    return {"samples": len(observations), "applied": applied, "paths_by_sample": paths,
            "no_feasible": sum(row["reason"].startswith("no_feasible") for row in decisions),
            "distinct_observed_states": {field: sorted(values) for field, values in state_values.items()},
            "matching_replay": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    cases = sorted(path.parent for path in args.results.glob("*/policy.jsonl"))
    if not cases:
        parser.error("no online policy traces found")
    print(json.dumps({case.name: verify(case) for case in cases}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
