"""Guard matched wire rates, policy boundaries, and based-on-window utility."""

import unittest

from integrated_review.uplink import CoreReport, LinkReport, RanReport, ReportChannel, TransportReport
from .data import measured_outcomes
from .formats import make_boundary, make_fixed


class SemanticUplinkTest(unittest.TestCase):
    def test_matched_rate_and_boundary(self):
        for factory in (make_fixed, make_boundary):
            for depth in (4, 5, 20, 23, 24, 128):
                codec = factory()
                snapshot = {
                    "ran": RanReport(24, 250),
                    "transport": TransportReport("direct", (
                        LinkReport(True, depth, 0, 10_000_000),
                        LinkReport(True, 0, 0, 100_000_000),
                    )),
                    "core": CoreReport(2_000_000, 4120, 1_000_000),
                }
                channel = ReportChannel(codec, 0, 40_000_000)
                wire = channel.tick(0, snapshot)
                self.assertEqual([frame["bits"] for frame in wire], [128] * 3)
                fresh, _ = channel.view(0)
                decoded = fresh["transport"].report.paths[0]
                self.assertEqual(decoded.bottleneck_bps, 10_000_000)
                self.assertEqual(fresh["core"].report.max_ip_rate_bps, 1_000_000)
                if factory is make_boundary:
                    self.assertEqual(decoded.queued_packets >= 5, depth >= 5)
                    self.assertEqual(decoded.queued_packets >= 24, depth >= 24)

    def test_outcome_window_scaling_and_verified_unchanged_action(self):
        action = dict(path_id="direct", ran_bands=4, upf_video_rate_bps=3_000_000)
        branch = dict(
            prefix_state_sha256="prefix", exogenous_trace_id="trace",
            applied_at_ns=10, applied_action=action, apply_status="unchanged",
            feasible=False, video_delivered_payload_bits=1_000_000, video_on_time_20ms_packets=100,
            competitor_delivered_payload_bits=0, ran_allocated_blocks=0, transport_branch_bit_hops=0,
        )
        row = dict(prefix_state_sha256="prefix", exogenous_trace_id="trace",
                   apply_at_ns=10, active_action=action, send_window_ns=[10, 500_000_010],
                   preference_ids=["balanced"], candidates=[dict(action=action, outcomes=[branch])])
        contract = {
            "preferences": {"balanced": dict(video_bits=1.0, video_on_time=0,
                                             competitor_bits=0, ran_blocks=0, branch_bit_hops=0)},
            "scales": dict(video_bits=200_000, video_on_time=25, competitor_bits=2_400_000,
                           ran_blocks=2_000, branch_bit_hops=2_000_000),
        }
        measured = measured_outcomes(row, contract, "balanced")
        self.assertEqual(measured[("direct", 4, 3_000_000)], (False, 1.0))
        branch["applied_at_ns"] += 1
        with self.assertRaisesRegex(ValueError, "Unpaired"):
            measured_outcomes(row, contract, "balanced")


if __name__ == "__main__":
    unittest.main()
