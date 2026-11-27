"""Domain-only candidate generators and the full-information ladder baseline.

Rates are application payload bit/s, except the explicitly named IP policer rate.
Delays and timestamps are integer nanoseconds on the same simulation clock.
"""

from dataclasses import dataclass
from itertools import product

MS = 1_000_000
BANDS = (4, 10)
RATES_BPS = (1_000_000, 3_000_000)
PPM = 1_000_000


@dataclass(frozen=True)
class Stamp:
    observed_ns: int
    valid_until_ns: int

    def is_live_at(self, now_ns):
        return self.observed_ns <= now_ns < self.valid_until_ns


@dataclass(frozen=True)
class Intent:
    control_bps: int = 320_000
    video_target_bps: int = 2_000_000
    deadline_ns: int = 20 * MS
    fixed_delay_ns: int = 2 * MS


@dataclass(frozen=True)
class DomainBudget:
    max_control_delay_ns: int
    resource_limit: int  # RAN bands, transport branch links, or UPF IP bit/s.


@dataclass(frozen=True)
class Budgets:
    ran: DomainBudget = DomainBudget(8 * MS, 24)
    transport: DomainBudget = DomainBudget(9 * MS, 4)
    core: DomainBudget = DomainBudget(1 * MS, 3_000_000)


@dataclass(frozen=True)
class RanState:
    stamp: Stamp
    max_bands: int
    mac_backlog_bytes: int
    service_bps_per_band: int = 1_000_000


@dataclass(frozen=True)
class PathState:
    path_id: str
    available: bool
    queued_packets: int
    control_queue_bits: int
    bottleneck_bps: int
    branch_links: int
    base_delay_ns: int
    congested_delivery_ppm: int


@dataclass(frozen=True)
class TransportState:
    stamp: Stamp
    current_path: str
    paths: tuple[PathState, ...]


@dataclass(frozen=True)
class CoreState:
    stamp: Stamp
    offered_video_bps: int
    max_ip_rate_bps: int = 3_000_000
    payload_bytes: int = 1000
    packet_ip_bytes: int = 1028
    burst_bytes: int = 4120


@dataclass(frozen=True)
class Candidate:
    domain: str
    action: int | str
    stamp: Stamp
    video_bps: int
    control_service_bps: int | None
    control_delay_ns: int
    cost: int
    cost_unit: str
    violations: tuple[str, ...]
    video_delivery_ppm: int

    @property
    def feasible(self):
        return not self.violations


def serialization_ns(bits, rate_bps):
    return (bits * 1_000_000_000 + rate_bps - 1) // rate_bps


def candidate(domain, action, stamp, now_ns, video, control, delay, cost, unit,
              budget, intent, checks=(), video_delivery_ppm=PPM):
    violations = list(checks)
    if not stamp.is_live_at(now_ns):
        violations.append("stale_or_future_state")
    if cost > budget.resource_limit:
        violations.append("resource_budget")
    if control is not None and control < intent.control_bps:
        violations.append("control_service")
    if delay > budget.max_control_delay_ns:
        violations.append("control_delay_budget")
    return Candidate(domain, action, stamp, min(intent.video_target_bps, video),
                     control, delay, cost, unit, tuple(violations), video_delivery_ppm)


def ran_candidates(state: RanState, budget: DomainBudget, intent: Intent, now_ns: int):
    """Use only gNB state. The backlog model includes one control packet."""
    result = []
    for bands in BANDS:
        service = bands * state.service_bps_per_band
        delay = 2 * MS + serialization_ns((state.mac_backlog_bytes + 200) * 8, max(1, service))
        result.append(candidate(
            "ran", bands, state.stamp, now_ns, max(0, service - intent.control_bps),
            service, delay, bands, "bands", budget, intent,
            ("cell_band_limit",) if bands > state.max_bands else (),
        ))
    return tuple(result)


def transport_candidates(state: TransportState, budget: DomainBudget, intent: Intent, now_ns: int):
    """Use only path/link state. Use the prior route policy's 24/4-packet hysteresis."""
    result = []
    for path in state.paths:
        threshold = 24 if path.path_id == state.current_path else 5
        residual = max(0, path.bottleneck_bps - intent.control_bps)
        retention = path.congested_delivery_ppm if path.queued_packets >= threshold else PPM
        video = min(residual, intent.video_target_bps * retention // PPM)
        # Allow one in-flight 1500 B frame on the modeled bottleneck.
        delay = path.base_delay_ns
        violations = [] if path.available else ["path_unavailable"]
        if path.bottleneck_bps > 0:
            delay += serialization_ns(path.control_queue_bits + 12_000, path.bottleneck_bps)
        else:
            violations.append("no_link_capacity")
        result.append(candidate(
            "transport", path.path_id, state.stamp, now_ns, video,
            path.bottleneck_bps, delay, path.branch_links, "branch_links", budget, intent,
            violations, retention,
        ))
    return tuple(result)


def core_candidates(state: CoreState, budget: DomainBudget, intent: Intent, now_ns: int):
    """Use only UPF offered load and token-bucket configuration. Control bypasses policing."""
    result = []
    for rate in RATES_BPS:
        video = min(state.offered_video_bps, rate * state.payload_bytes // state.packet_ip_bytes)
        violations = []
        if rate > state.max_ip_rate_bps:
            violations.append("upf_rate_limit")
        if state.burst_bytes < state.packet_ip_bytes:
            violations.append("token_bucket_smaller_than_packet")
        result.append(candidate("core", rate, state.stamp, now_ns, video, None, 0,
                                rate, "ip_bps", budget, intent, violations))
    return tuple(result)


@dataclass(frozen=True)
class Combination:
    ran: Candidate
    transport: Candidate
    core: Candidate
    video_bps: int
    control_delay_ns: int
    violations: tuple[str, ...]

    @property
    def feasible(self):
        return not self.violations

    @property
    def objectives(self):
        return (-self.video_bps, self.ran.cost, self.transport.cost)

    def action(self):
        return {"type": "apply_route_resources", "path_id": self.transport.action,
                "ran_bands": self.ran.action, "upf_video_rate_bps": self.core.action}


def combine(ran, transport, core, intent):
    selected = (ran, transport, core)
    delay = intent.fixed_delay_ns + sum(item.control_delay_ns for item in selected)
    violations = [f"{item.domain}.{reason}" for item in selected for reason in item.violations]
    if delay > intent.deadline_ns:
        violations.append("end_to_end_control_delay")
    forwarded = core.video_bps * transport.video_delivery_ppm // PPM
    video = min(ran.video_bps, transport.video_bps, forwarded)
    return Combination(ran, transport, core, video, delay, tuple(violations))


def dominates(left, right):
    return left != right and all(a <= b for a, b in zip(left, right))


@dataclass(frozen=True)
class Decision:
    selected: Combination | None
    front: tuple[Combination, ...] = ()
    evaluated: tuple[Combination, ...] = ()


def select_autonomous(table):
    """Make one local choice from one candidate table. Ties prefer lower local cost."""
    return min((item for item in table if item.feasible),
               key=lambda item: (-item.video_bps, item.cost, item.action), default=None)


def solve_full(ran: RanState, transport: TransportState, core: CoreState,
               budgets: Budgets, intent: Intent, now_ns: int) -> Decision:
    """Enumerate the full product with current states and retain equal-objective ties."""
    tables = (
        ran_candidates(ran, budgets.ran, intent, now_ns),
        transport_candidates(transport, budgets.transport, intent, now_ns),
        core_candidates(core, budgets.core, intent, now_ns),
    )
    evaluated = tuple(combine(*items, intent) for items in product(*tables))
    feasible = tuple(item for item in evaluated if item.feasible)
    front = tuple(item for item in feasible if not any(
        dominates(other.objectives, item.objectives) for other in feasible
    ))
    selected = min(front, key=lambda item: (*item.objectives, item.core.cost,
                                            item.transport.action), default=None)
    return Decision(selected, front, evaluated)
