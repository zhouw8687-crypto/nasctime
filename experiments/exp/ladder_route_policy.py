"""Choose between the two installed N3 paths using NE1 egress backlog."""


import json
import os
from functools import lru_cache
from pathlib import Path


def choose_path(observation):
    current = observation["path_id"]
    direct = observation["direct_queue_packets"]
    detour = observation["detour_queue_packets"]
    if current == "direct" and direct >= 24 and detour <= 4:
        return {"type": "set_route", "path_id": "detour"}
    if current == "detour" and direct <= 4:
        return {"type": "set_route", "path_id": "direct"}
    return None


def choose_joint_policy(observation):
    route = choose_path(observation)
    path_id = route["path_id"] if route else observation["path_id"]
    bands, rate = (10, 3_000_000) if path_id == "detour" else (4, 1_000_000)
    if not route and (bands, rate) == (observation["ran_bands"], observation["upf_video_rate_bps"]):
        return None
    return {"type": "apply_route_resources", "path_id": path_id,
            "ran_bands": bands, "upf_video_rate_bps": rate}


@lru_cache(maxsize=1)
def load_profiles():
    return json.loads(Path(os.environ["LADDER_ROUTE_PROFILES"]).read_text(encoding="utf-8"))


def choose_calibrated_policy(observation):
    route = choose_path(observation)
    branch = route["path_id"] if route else observation["path_id"]
    phase = "burst" if branch == "detour" else "preburst"
    profile = load_profiles()[phase]["selected"]
    path_id, bands, rate = (profile[k] for k in ("path_id", "ran_bands", "upf_video_rate_bps"))
    current = (observation["path_id"], observation["ran_bands"], observation["upf_video_rate_bps"])
    if (path_id, bands, rate) == current:
        return None
    return {
        "type": "apply_route_resources", "path_id": path_id,
        "ran_bands": bands, "upf_video_rate_bps": rate,
    }
