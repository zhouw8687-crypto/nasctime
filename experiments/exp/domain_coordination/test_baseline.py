"""Controlled replay checks for decisions that the single-UE live run cannot isolate."""

from dataclasses import replace
import io
import json
import unittest

from .adapter import LadderPolicy

from .baseline import (
    MS, Budgets, CoreState, DomainBudget, Intent, PathState, RanState, Stamp,
    TransportState, ran_candidates, select_autonomous, solve_full, transport_candidates,
)


class CandidateReplay(unittest.TestCase):
    now = 200 * MS
    stamp = Stamp(now, now + 40 * MS)
    intent = Intent()
    budgets = Budgets()
    ran = RanState(stamp, 24, 0)
    direct = PathState("direct", True, 48, 0, 10_000_000, 2, 2 * MS, 224_000)
    detour = PathState("detour", True, 0, 0, 100_000_000, 4, 3 * MS, 0)
    transport = TransportState(stamp, "direct", (direct, detour))
    core = CoreState(stamp, 2_000_000)

    def solve(self, ran=None, transport=None, core=None, budgets=None, intent=None):
        return solve_full(ran or self.ran, transport or self.transport, core or self.core,
                          budgets or self.budgets, intent or self.intent, self.now)

    def test_transport_only_changes_path_and_front(self):
        calm = replace(self.transport, paths=(replace(self.direct, queued_packets=0), self.detour))
        self.assertEqual(self.solve(transport=calm).selected.transport.action, "direct")
        burst = self.solve()
        self.assertEqual(len(burst.evaluated), 8)
        self.assertEqual({combo.transport.action for combo in burst.front}, {"direct", "detour"})
        self.assertEqual(burst.selected.transport.action, "detour")

    def test_ran_change_with_fixed_transport_core_and_budget(self):
        high = replace(self.ran, mac_backlog_bytes=6_000)
        before = self.solve()
        after = self.solve(ran=high)
        self.assertEqual(before.selected.ran.action, 4)
        self.assertEqual(after.selected.ran.action, 10)
        self.assertEqual(before.selected.transport, after.selected.transport)
        report = ran_candidates(high, self.budgets.ran, self.intent, self.now)
        self.assertEqual(report[0].violations, ("control_delay_budget",))
        self.assertEqual(select_autonomous(report).action, 10)

    def test_core_change_with_fixed_transport_and_independent_choice(self):
        low = replace(self.core, offered_video_bps=320_000)
        self.assertEqual(self.solve().selected.core.action, 3_000_000)
        self.assertEqual(self.solve(core=low).selected.transport.action, "detour")
        narrow = replace(self.direct, queued_packets=0, bottleneck_bps=1_800_000)
        transport = replace(self.transport, paths=(narrow, self.detour))
        self.assertEqual(self.solve(transport=transport).selected.transport.action, "detour")
        joint = self.solve(core=low, transport=transport)
        self.assertEqual(joint.selected.core.action, 1_000_000)
        self.assertEqual(joint.selected.transport.action, "direct")
        self.assertEqual(joint.selected.video_bps, 320_000)
        local = transport_candidates(transport, self.budgets.transport, self.intent, self.now)
        self.assertEqual(select_autonomous(local).action, "detour")

    def test_empty_on_budget_freshness_and_joint_deadline(self):
        for kwargs, reason in (
            ({"budgets": replace(self.budgets, ran=DomainBudget(10 * MS, 3))},
             "ran.resource_budget"),
            ({"core": replace(self.core, stamp=Stamp(100 * MS, self.now))},
             "core.stale_or_future_state"),
            ({"core": replace(self.core, stamp=Stamp(201 * MS, 240 * MS))},
             "core.stale_or_future_state"),
            ({"intent": replace(self.intent, deadline_ns=1 * MS)}, "end_to_end_control_delay"),
        ):
            with self.subTest(reason=reason):
                result = self.solve(**kwargs)
                self.assertIsNone(result.selected)
                self.assertEqual(result.front, ())
                self.assertEqual(len(result.evaluated), 8)
                self.assertTrue(all(reason in combo.violations for combo in result.evaluated))

    def test_empty_policy_sends_no_actuator_command(self):
        obs = {"sim_time_ns": self.now, "generation": 1, "request_id": 2,
               "path_id": "direct", "direct_queue_packets": 0, "detour_queue_packets": 0,
               "ran_bands": 4, "upf_video_rate_bps": 3_000_000,
               "ran": {"max_bands": 24, "mac_backlog_bytes": 0},
               "transport": {path: {"available": False, "control_queue_bits": 0, "egress_bps": rate}
                             for path, rate in (("direct", 10_000_000), ("detour", 100_000_000))},
               "core": {"offered_video_packets": 25, "burst_bytes": 4120}}
        for mode, reason in (("full", "no_feasible_combination"),
                             ("autonomous", "no_feasible_local_candidate")):
            with self.subTest(mode=mode):
                log = io.StringIO()
                self.assertIsNone(LadderPolicy(mode, log)(obs))
                decision = json.loads(log.getvalue())
                self.assertEqual(decision["reason"], reason)
                self.assertIsNone(decision["planned_effective_ns"])

    def test_unavailable_route_is_filtered_before_pareto(self):
        impassable = replace(self.transport, paths=(self.direct, replace(self.detour, available=False)))
        decision = self.solve(transport=impassable)
        self.assertEqual(decision.selected.transport.action, "direct")
        rejected = [item for item in decision.evaluated if item.transport.action == "detour"]
        self.assertTrue(all("transport.path_unavailable" in item.violations for item in rejected))


if __name__ == "__main__":
    unittest.main()
