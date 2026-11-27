"""Regression tests for hard SLA, ties, signed costs, and the hold transaction."""

import io
import unittest
from unittest.mock import patch

from domain_coordination.adapter import LadderPolicy
from domain_coordination.baseline import MS
from .dataset import BENEFITS, OBJECTIVES, compare, frontier, weighted_regret
from .simulate import ACTION_GRID, HOLD_MS, ForkPolicy, Run


def outcome(**fields):
    return {**dict.fromkeys(OBJECTIVES, 0), "feasible": True, **fields}


class Effects(unittest.TestCase):
    def test_feasibility_precedes_a_potential_video_gain(self):
        self.assertEqual(compare(outcome(feasible=False, video_delivered_payload_bits=100), outcome()), "loss")

    def test_distinguishes_ties_losses_and_service_tradeoff(self):
        base = outcome(video_delivered_payload_bits=80, competitor_delivered_payload_bits=100)
        self.assertEqual(compare({**base, "ran_allocated_blocks": 1}, base), "loss")
        self.assertEqual(compare({**base, "ran_allocated_blocks": 1}, base, BENEFITS), "equivalent")
        self.assertEqual(compare({**base, "video_delivered_payload_bits": 88,
                                  "competitor_delivered_payload_bits": 90}, base), "tradeoff")
        self.assertEqual(frontier({"base": base, "tie": dict(base), "invalid": outcome(feasible=False)}),
                         ["base", "tie"])

    def test_regret_uses_supplied_preferences_and_physical_scales(self):
        outcomes = {"baseline": outcome(), "better": outcome(video_delivered_payload_bits=100),
                    "invalid": outcome(feasible=False)}
        key = "video_delivered_payload_bits"
        self.assertEqual(weighted_regret(outcomes, "baseline", {key: 1}, {key: 100}), 1)
        self.assertEqual(weighted_regret(outcomes, "invalid", {key: 1}, {key: 100}), float("inf"))
        self.assertIsNone(weighted_regret({"invalid": outcomes["invalid"]},
                                        "invalid", {key: 1}, {key: 100}))


class BranchPolicy(unittest.TestCase):
    def test_only_overrides_the_fork_and_hold(self):
        fork = 420
        action = "direct-10-1m"
        runner = ForkPolicy(Run(0, fork, action), io.StringIO())
        default = ACTION_GRID["detour-4-3m"]
        with patch.object(LadderPolicy, "__call__", return_value=default) as live:
            self.assertEqual(runner({"sim_time_ns": (fork - 20) * MS}), default)
            self.assertEqual(runner({"sim_time_ns": fork * MS}), ACTION_GRID[action])
            self.assertIsNone(runner({"sim_time_ns": (fork + 20) * MS}))
            self.assertEqual(runner({"sim_time_ns": (fork + HOLD_MS) * MS}), default)
            self.assertEqual(live.call_count, 4)  # The local estimator keeps receiving live inputs.


if __name__ == "__main__":
    unittest.main()
