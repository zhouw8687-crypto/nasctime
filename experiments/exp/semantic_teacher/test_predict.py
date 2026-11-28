import unittest

from .predict import feature_vector, rates
from .release import metric_values, queue_band, utility, PREFERENCES


class PredictorContract(unittest.TestCase):
    def test_features_do_not_require_labels(self):
        path = {"queue_band": 0, "control_queue_bits": 0, "available": True, "egress_bps": 10_000_000}
        action = {"path_id": "direct", "ran_bands": 4, "upf_video_rate_bps": 3_000_000}
        row = {
            "sim_time_ns": 420_000_000, "active_action": action,
            "send_window_ns": [420_000_000, 520_000_000], "intent": {"control_bps": 320000},
            "semantic": {
                "ran": {"source_ns": 420_000_000, "mac_backlog_bytes": 2, "max_bands": 24},
                "transport": {"source_ns": 420_000_000, "paths": {"direct": path, "detour": path}},
                "core": {"source_ns": 420_000_000, "offered_video_bps": 2_000_000, "burst_bytes": 4120},
            },
        }
        self.assertEqual(len(feature_vector(row, {"action": action})), 29)

    def test_utility_normalizes_windows_and_signed_cost(self):
        sample = {"video_delivered_payload_bits": 1_000_000, "video_on_time_20ms_packets": 125,
                  "competitor_delivered_payload_bits": 0, "ran_allocated_blocks": 500,
                  "transport_branch_bit_hops": 0}
        row = {"send_window_ns": [400_000_000, 900_000_000]}
        values = metric_values(sample, row)
        self.assertEqual(values["video_bits"], 200000)
        self.assertLess(utility(values, PREFERENCES["balanced"]),
                        utility({**values, "ran_blocks": 0}, PREFERENCES["balanced"]))

    def test_false_feasible_denominator_and_bands(self):
        matrix = rates([True, False, False, True], [True, True, False, False])
        self.assertEqual(matrix["false_positive_rate"], .5)
        self.assertEqual(matrix["false_feasible_among_predicted_feasible"], .5)
        self.assertEqual([queue_band(n) for n in (4, 5, 23, 24)], [0, 1, 1, 2])
