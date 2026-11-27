"""Exercise an independent requested-rate change while the core capacity is down."""

REQUESTS = {460: 600_000, 600: 3_500_000, 940: 1_500_000}


def choose(observation):
    rate = REQUESTS.get(observation["sim_time_ns"] / 1_000_000)
    if rate is not None:
        return {"type": "apply_route_resources", "path_id": observation["path_id"],
                "ran_bands": observation["ran_bands"], "upf_video_rate_bps": rate}
    return None