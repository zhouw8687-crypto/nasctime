"""Audit wire transactions and extract paired endpoint/resource measurements."""

from bisect import bisect_left
from dataclasses import dataclass
import hashlib
import json

from domain_coordination.adapter import ACTIONS
from domain_coordination.baseline import MS
from dual_ue.extract import FLOWS, MAC, NETWORK, PCAPS, include, udp_frames
from ladder_kpis import collect_flows, load_vectors, percentile

SECOND = 1_000 * MS
DEADLINE_NS = 20 * MS
BURST_NS = (400 * MS, 900 * MS)
BRANCH_PCAPS = {
    **PCAPS, "left_tail": "ne3-to-ne5.pcap", "detour_ne2": "ne2-to-ne4.pcap",
    "detour_ne4": "ne4-to-ne6.pcap",
}
ROUTE_READBACK = {"direct": ("eth1", "10.0.0.10"), "detour": ("eth0", "10.0.0.6")}


def digest(obj):
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def read_jsonl(path):
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def actuators(message):
    return {name: message[name] for name in ACTIONS}


@dataclass(frozen=True)
class Transaction:
    observation: dict
    wire: dict
    ack: dict
    prediction: dict

    @property
    def now(self):
        return self.observation["sim_time_ns"]

    @property
    def event_number(self):
        return self.observation["prefix_witness"]["event_number"]

    def validate(self, expected_action):
        obs, wire, ack = self.observation, self.wire, self.ack
        readback = actuators(obs if expected_action is None else expected_action)
        if (wire["action"] != expected_action or wire["base_generation"] != obs["generation"]
                or len({obs["request_id"], wire["request_id"], ack["request_id"],
                        self.prediction["request_id"]}) != 1
                or self.now != ack["sim_time_ns"] or self.now != self.prediction["sim_time_ns"]):
            raise ValueError(f"Invalid command envelope at {self.now}")
        changed = readback != actuators(obs)
        status = "noop" if expected_action is None else ("applied" if changed else "unchanged")
        same_tick = (actuators(ack) == readback and ack["status"] == status
                     and ack["generation"] == obs["generation"] + int(changed)
                     and (ack["interface"], ack["gateway"]) == ROUTE_READBACK[readback["path_id"]])
        if not same_tick:
            raise ValueError(f"Invalid execution readback at {self.now}: {ack}")


class Measurements:
    def __init__(self, path):
        self.path = path
        raw = read_jsonl(path / "routes.jsonl")
        if len(raw) != 56 * 3 or any(
            tuple(event["type"] for event in raw[i:i + 3]) != ("observation", "received_decision", "ack")
            for i in range(0, len(raw), 3)
        ):
            raise ValueError(f"{path}: unexpected route trace structure")
        decisions = read_jsonl(path / "policy.jsonl")
        self.trace = {
            txn.now: txn for txn in (
                Transaction(obs, cmd["decision"], ack, report)
                for obs, cmd, ack, report in zip(raw[::3], raw[1::3], raw[2::3], decisions, strict=True)
            )
        }
        if list(self.trace) != list(range(200 * MS, 1301 * MS, 20 * MS)):
            raise ValueError(f"{path}: unexpected control times")
        vector, = path.glob("*.vec")
        self.vectors = load_vectors(vector, include)
        pairs = [(source, sink) for source, sink, _ in FLOWS.values()]
        self.flows = {
            source: (sent, received, duplicates)
            for source, _, sent, received, duplicates in collect_flows(self.vectors, NETWORK, pairs)
        }
        for source, _, count in FLOWS.values():
            if len(self.flows[source][0]) != count:
                raise ValueError(f"{path}: wrong offered packet count for {source}")
        # Event numbers may differ after branching even when actual traffic is identical.
        self.exogenous_traffic_sha256 = digest({
            source: [(round(t * SECOND), int(size)) for t, _, size in sent]
            for source, (sent, _, _) in self.flows.items()
        })

    def prefix_sha256(self, now):
        point = self.trace[now]
        # Vectors contain RX, TX, per-UE allocation, and all NE1 queue lengths/drops.
        # Same-time events earlier than the decision are part of the prefix.
        vectors = [
            [key, [sample for sample in samples if sample[1] < point.event_number]]
            for key, samples in sorted(self.vectors.items())
            if samples and samples[0][1] < point.event_number
        ]
        prior = [
            [txn.observation, txn.wire, txn.ack] for t, txn in self.trace.items() if t < now
        ]
        return digest([prior, point.observation, vectors])

    def cohort(self, flow, start, stop, drain):
        source = FLOWS[flow][0]
        sent, received, duplicates = self.flows[source]
        sequence = [seq for seq, (time, _, _) in enumerate(sent)
                    if start <= round(time * SECOND) < stop]
        received_in_drain = [
            (seq, delay, int(size)) for seq in sequence if seq in received
            for delay, size in (received[seq],)
            if round((sent[seq][0] + delay) * SECOND) <= drain
        ]
        delays = [round(delay * SECOND) for _, delay, _ in received_in_drain]
        delivered = len(received_in_drain)
        return {
            "sent_packets": len(sequence), "delivered_packets": delivered,
            "undelivered_packets": len(sequence) - delivered,
            "on_time_20ms_packets": sum(delay <= DEADLINE_NS for delay in delays),
            "delivered_payload_bits": sum(size * 8 for _, _, size in received_in_drain),
            "p99_delivered_ns": percentile(delays, .99) if delays else None,
            "duplicates": sum(duplicates.get(seq, 0) for seq in sequence),
        }

    def allocation(self, start, stop):
        module = f"{NETWORK}.gnb1.cellularNic.mac.schedulerDl"
        cell, ue0, ue1 = (self.vectors[module, MAC[scope]] for scope in ("cell", "ue0", "ue1"))
        ticks = [txn.event_number for txn in self.trace.values()]
        acks = [txn.ack for txn in self.trace.values()]
        valid = True
        sums = [0, 0, 0]
        peak = 0
        slots = 0
        for slot, first, second in zip(cell, ue0, ue1, strict=True):
            dt, event, cell_blocks = slot
            if not start <= round(dt * SECOND) < stop:
                continue
            slots += 1
            prior = bisect_left(ticks, event) - 1
            cap = acks[prior]["ran_bands"] if prior >= 0 else self.trace[min(self.trace)].observation["ran_bands"]
            values = [int(item[2]) for item in (slot, first, second)]
            valid &= slot[:2] == first[:2] == second[:2] and values[0] == values[1] + values[2]
            valid &= 0 <= cell_blocks <= cap
            for i, value in enumerate(values):
                sums[i] += value
            peak = max(peak, values[0])
        if not slots:
            raise ValueError(f"{self.path}: no radio slots in the measurement window")
        return dict(cell=sums[0], ue0=sums[1], ue1=sums[2], cell_peak=peak, slots=slots, within_budget=valid)

    def transport(self, start, stop):
        # Timestamp by link observation, including in-flight packets from prior cohorts.
        return {name: sum(bits for time, source, dest, _, bits in
                          udp_frames((self.path / filename).read_bytes(), include_ip_bits=True)
                          if source == dest == 31 and start <= round(time * SECOND) < stop)
                for name, filename in BRANCH_PCAPS.items()}

    def outcomes(self, start, stop, drain):
        flow_data = {flow: self.cohort(flow, start, stop, drain)
                     for flow in ("control", "video", "radio_competitor")}
        burst = self.cohort("control", *BURST_NS, drain)
        control = flow_data["control"]
        video = flow_data["video"]
        competitor = flow_data["radio_competitor"]
        allocation = self.allocation(start, stop)
        links = self.transport(start, stop)
        local_sla = (control["sent_packets"] >= 20 and
                     control["on_time_20ms_packets"] * 100 >= 99 * control["sent_packets"])
        burst_sla = burst["sent_packets"] == 100 and burst["on_time_20ms_packets"] >= 99
        return {
            "control_sent_packets": control["sent_packets"],
            "control_on_time_packets": control["on_time_20ms_packets"],
            "control_burst_sent_packets": burst["sent_packets"],
            "control_burst_on_time_packets": burst["on_time_20ms_packets"],
            "video_delivered_payload_bits": video["delivered_payload_bits"],
            "video_on_time_20ms_packets": video["on_time_20ms_packets"],
            "competitor_delivered_payload_bits": competitor["delivered_payload_bits"],
            "competitor_on_time_20ms_packets": competitor["on_time_20ms_packets"],
            "ran_allocated_blocks": allocation["cell"], "transport_branch_bit_hops": sum(links.values()),
            "resource_constraints_met": allocation["within_budget"],
            "local_sla_met": local_sla, "original_burst_sla_met": burst_sla,
            "feasible": local_sla and burst_sla and allocation["within_budget"],
            "flows": flow_data, "ran": allocation, "transport_ip_bits_per_link": links,
            "rng_draws_at_window_close": self.trace[stop].observation["prefix_witness"]["rng_draws"],
        }
