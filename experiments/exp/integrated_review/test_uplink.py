"""Exercise causal delivery, expiration, and the endpoint codec contract."""

from io import StringIO
import json
import unittest

from control_reporting.reporting import HEADER
from domain_coordination.baseline import MS

from .policy import ReportingPolicy
from .uplink import (
    Codec, CoreReport, LinkReport, RanReport, ReportChannel, TransportReport, builtin_codec,
)


def snapshot(depth=0):
    return {
        "ran": RanReport(24, 0),
        "transport": TransportReport("direct", (
            LinkReport(True, depth, 0, 10_000_000), LinkReport(True, 0, 0, 100_000_000),
        )),
        "core": CoreReport(2_000_000, 4120),
    }


def observation(time_ns, request, depth=0):
    return dict(
        sim_time_ns=time_ns, request_id=request, generation=0,
        path_id="direct", ran_bands=4, upf_video_rate_bps=3_000_000,
        ran=dict(max_bands=24, mac_backlog_bytes=0),
        core=dict(offered_video_packets=time_ns // (4 * MS), burst_bytes=4120),
        transport={
            "direct": dict(available=True, control_queue_bits=0, egress_bps=10_000_000),
            "detour": dict(available=True, control_queue_bits=0, egress_bps=100_000_000),
        },
        direct_queue_packets=depth, detour_queue_packets=0,
    )


class PrefixEncoder:
    def encode(self, domain, report):
        return bytes([42]) + builtin_codec("exact").encoder.encode(domain, report)


class PrefixDecoder:
    def decode(self, domain, payload):
        if payload[0] != 42:
            raise ValueError("Expected the custom byte")
        return builtin_codec("exact").decoder.decode(domain, payload[1:])


class UplinkTests(unittest.TestCase):
    def test_delivery_then_expiry_at_the_exact_ttl(self):
        channel = ReportChannel(builtin_codec("exact"), 5 * MS, 40 * MS, 40 * MS)
        events = channel.tick(0, snapshot())
        self.assertEqual([event["arrival_ns"] for event in events], [5 * MS] * 3)
        self.assertFalse(channel.view(0)[0])
        self.assertFalse(channel.tick(20 * MS, snapshot()))
        fresh, _ = channel.view(20 * MS)
        self.assertEqual(fresh["ran"].source_ns, 0)
        channel.tick(40 * MS, snapshot())
        fresh, status = channel.view(40 * MS)
        self.assertFalse(fresh)
        self.assertEqual(status["ran"]["age_ns"], 40 * MS)
        self.assertEqual(status["ran"]["status"], "expired")
        channel.tick(60 * MS, snapshot())
        self.assertEqual(channel.view(60 * MS)[0]["ran"].source_ns, 40 * MS)

    def test_boundary_classes_preserve_both_solver_thresholds(self):
        codec = builtin_codec("boundary_periodic")
        for depth in (0, 4, 5, 23, 24, 128):
            with self.subTest(depth=depth):
                frame = codec.encoder.encode("transport", snapshot(depth)["transport"])
                decoded = codec.decoder.decode("transport", frame).paths[0].queued_packets
                self.assertEqual((decoded >= 5, decoded >= 24), (depth >= 5, depth >= 24))

    def test_encoder_and_decoder_can_be_supplied_separately(self):
        channel = ReportChannel(Codec(90, 2, PrefixEncoder(), PrefixDecoder()), 0, 10 * MS)
        reports = snapshot(24)
        events = channel.tick(0, reports)
        payload = bytes.fromhex(events[0]["wire_hex"])[HEADER.size:]
        self.assertEqual(payload, bytes([42]) + builtin_codec("exact").encoder.encode("ran", reports["ran"]))
        self.assertEqual(events[0]["bits"], (12 + 1 + 5) * 8)
        self.assertEqual(channel.view(0)[0]["transport"].report, reports["transport"])

    def test_policy_holds_on_missing_and_excludes_current_raw_state_from_solver(self):
        stream = StringIO()
        policy = ReportingPolicy("exact", stream, delay_ns=5 * MS, ttl_ns=40 * MS)
        self.assertIsNone(policy(observation(200 * MS, 1)))
        self.assertIsNone(policy(observation(220 * MS, 2, 128)))
        action = policy(observation(240 * MS, 3, 128))
        self.assertEqual(action["path_id"], "detour")
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        decisions = [row for row in rows if row["type"] == "policy"]
        views = [row for row in rows if row["type"] == "report_view"]
        self.assertEqual(decisions[0]["reason"], "report_missing")
        self.assertEqual(decisions[1]["transport"]["paths"][0]["queued_packets"], 0)
        self.assertEqual(views[1]["reference_target"]["path_id"], "detour")
        self.assertEqual(views[1]["effective_target"]["path_id"], "direct")

    def test_policy_holds_on_expired_reports_without_candidates(self):
        stream = StringIO()
        policy = ReportingPolicy("exact", stream, delay_ns=25 * MS, ttl_ns=40 * MS)
        for request in range(1, 5):
            self.assertIsNone(policy(observation((180 + 20 * request) * MS, request, 128)))
        decisions = [row for row in map(json.loads, stream.getvalue().splitlines())
                     if row["type"] == "policy"]
        self.assertEqual([row["reason"] for row in decisions],
                         ["report_missing", "report_missing", "report_expired", "report_expired"])
        self.assertTrue(all(not row["evaluated"] for row in decisions))


if __name__ == "__main__":
    unittest.main()
