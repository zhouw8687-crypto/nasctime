"""Regression checks for frame accounting, trigger state and causal replay."""

import json
from pathlib import Path
import unittest

from reporting import FIXED, FULL, HEADER, Periodic, Threshold, frame, unframe
from replay import DEFAULT_THRESHOLDS, evaluate, read_observations


def path_candidate(snapshot):
    transport = snapshot["transport"]
    return {"path_id": "detour" if transport["direct_queue_packets"] >= 24 else "direct"}


class ReportingTests(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).with_name("example.domains.jsonl")
        self.observations = read_observations(fixture.read_bytes(), "domains")
        self.reference = [path_candidate(row.domains) for row in self.observations]

    def test_wire_layout_and_fixed_rounding(self):
        state = self.observations[1].domains["transport"]
        full = frame(FULL, "transport", 220_000_000, state)
        fixed = frame(FIXED, "transport", 220_000_000, state)
        self.assertEqual(len(full), HEADER.size + 9)
        self.assertEqual(len(fixed), HEADER.size + 3)
        self.assertEqual(unframe(FULL, "transport", full), (220_000_000, state))
        self.assertEqual(unframe(FIXED, "transport", fixed)[1]["direct_queue_packets"], 24)
        with self.assertRaises(ValueError):
            unframe(FIXED, "ran", fixed)
        with self.assertRaises(ValueError):
            unframe(FIXED, "transport", fixed[:-1])

    def test_threshold_compares_to_last_raw_send_and_heartbeats(self):
        trigger = Threshold(100, DEFAULT_THRESHOLDS)
        initial = {"path_id": "direct", "direct_queue_packets": 0, "detour_queue_packets": 0}
        small = dict(initial, direct_queue_packets=7)
        limit = dict(initial, direct_queue_packets=8)
        self.assertEqual(trigger.reason("transport", 0, initial, None), "initial")
        self.assertIsNone(trigger.reason("transport", 20, small, (0, initial)))
        self.assertEqual(trigger.reason("transport", 40, limit, (0, initial)), "threshold")
        self.assertEqual(trigger.reason("transport", 100, small, (0, initial)), "max_silence")
        self.assertEqual(
            trigger.reason("transport", 20, dict(initial, path_id="detour"), (0, initial)),
            "threshold",
        )

    def test_replay_only_reads_arrived_frames(self):
        result, rows = evaluate(
            self.observations, 280_000_000, FULL, Periodic(),
            path_candidate, self.reference, delay_ns=20_000_000,
        )
        self.assertIsNone(rows[0]["received_view_action"])
        self.assertEqual(rows[2]["received_view_action"], {"path_id": "direct"})
        self.assertEqual(result["action"]["different"], 1)
        self.assertEqual(result["action"]["unavailable"], 1)
        self.assertEqual(result["domains"]["transport"]["age"]["mean_ms"], 20)
        bits = sum(
            len(bytes.fromhex(report["hex"])) * 8
            for row in rows for report in row["sent"].values()
        )
        self.assertEqual(result["uplink_application_wire_bits"], bits)

    def test_routes_skips_decision_wrappers_without_versions(self):
        snapshot = self.observations[0]
        state = {key: value for domain in snapshot.domains.values() for key, value in domain.items()}
        data = "\n".join(map(json.dumps, (
            {"type": "received_decision", "request_id": 1},
            dict(state, type="observation", version=1, sim_time_ns=snapshot.time_ns),
        )))
        self.assertEqual(read_observations(data.encode(), "routes"), [snapshot])


if __name__ == "__main__":
    unittest.main()
