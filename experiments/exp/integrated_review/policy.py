"""Use only fresh decoded domain reports for the live ladder decision."""

import argparse
from dataclasses import replace
from importlib import import_module
from pathlib import Path
import socket

from domain_coordination.adapter import ACTIONS, BUDGETS, LadderPolicy, STATE_LIFETIME_NS
from domain_coordination.baseline import MS, Stamp, solve_full
from ladder_controller import serve

from .uplink import Codec, CoreReport, LinkReport, MODES, RanReport, ReportChannel, TransportReport
from .uplink import builtin_codec


class ReportingPolicy(LadderPolicy):
    def __init__(self, mode, log, *, delay_ns=0, ttl_ns=STATE_LIFETIME_NS,
                 refresh_ns=STATE_LIFETIME_NS, codec=None):
        super().__init__("full", log)
        codec = builtin_codec(mode) if codec is None else codec
        self.channel = ReportChannel(codec, delay_ns, ttl_ns, refresh_ns if mode == "boundary" else None)
        self.write(dict(type="report_settings", mode=mode, delay_ns=delay_ns, ttl_ns=ttl_ns,
                        refresh_ns=self.channel.refresh_ns, codec_id=codec.codec_id,
                        codec_version=codec.version))

    def decoded_states(self, local_states, fresh):
        ran, transport, core = local_states
        ran_rx, transport_rx, core_rx = (fresh[name] for name in ("ran", "transport", "core"))

        def stamp(received):
            return Stamp(received.source_ns, received.source_ns + self.channel.ttl_ns)

        # Keep the preconfigured service models; replace every dynamic field from the wire.
        ran = replace(ran, stamp=stamp(ran_rx), max_bands=ran_rx.report.max_bands,
                      mac_backlog_bytes=ran_rx.report.mac_backlog_bytes)
        core = replace(core, stamp=stamp(core_rx), offered_video_bps=core_rx.report.offered_video_bps,
                       burst_bytes=core_rx.report.burst_bytes,
                       max_ip_rate_bps=core_rx.report.max_ip_rate_bps)
        paths = tuple(
            replace(path, available=report.available, queued_packets=report.queued_packets,
                    control_queue_bits=report.control_queue_bits, bottleneck_bps=report.bottleneck_bps)
            for path, report in zip(transport.paths, transport_rx.report.paths, strict=True)
        )
        transport = replace(transport, stamp=stamp(transport_rx),
                            current_path=transport_rx.report.current_path, paths=paths)
        return ran, transport, core

    def __call__(self, obs):
        now_ns = obs["sim_time_ns"]
        local_states = self.states(obs)
        ran, transport, core = local_states
        reports = {
            "ran": RanReport(ran.max_bands, ran.mac_backlog_bytes),
            "transport": TransportReport(transport.current_path, tuple(
                LinkReport(path.available, path.queued_packets,
                           path.control_queue_bits, path.bottleneck_bps) for path in transport.paths
            )),
            "core": CoreReport(core.offered_video_bps, core.burst_bytes, core.max_ip_rate_bps),
        }
        for event in self.channel.tick(now_ns, reports):
            self.write(event)
        fresh, status = self.channel.view(now_ns)
        if len(fresh) == len(reports):
            action = self.choose_from_states(obs, self.decoded_states(local_states, fresh))
        else:
            action = None
            reason = ("report_missing" if any(s["status"] == "missing" for s in status.values())
                      else "report_expired")
            self.write(dict(type="policy", mode=self.mode, source="report_channel",
                            request_id=obs["request_id"], sim_time_ns=now_ns,
                            planned_effective_ns=None, base_generation=obs["generation"],
                            selected=None, evaluated=[], front=[], local_choices=None,
                            action=None, reason=reason))

        # Diagnostic only. This action never goes to the simulator.
        reference = solve_full(*local_states, BUDGETS, self.intent, now_ns).selected
        target = obs if action is None else action
        reference_target = obs if reference is None else reference.action()
        self.write(dict(type="report_view", request_id=obs["request_id"], sim_time_ns=now_ns,
                        domains=status,
                        reference_feasible=reference is not None,
                        reference_target={key: reference_target[key] for key in ACTIONS},
                        effective_target={key: target[key] for key in ACTIONS}))
        return action


def load_codec(spec):
    module, separator, name = spec.partition(":")
    if not separator or not module or not name:
        raise ValueError("Expected codec factory as module:function")
    codec = getattr(import_module(module), name)()
    if not isinstance(codec, Codec):
        raise ValueError("Codec factory must return an uplink.Codec")
    return codec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("encoding", choices=MODES)
    parser.add_argument("result", type=Path)
    parser.add_argument("--delay-ms", type=int, default=0)
    parser.add_argument("--ttl-ms", type=int, default=STATE_LIFETIME_NS // MS)
    parser.add_argument("--refresh-ms", type=int, default=STATE_LIFETIME_NS // MS)
    parser.add_argument("--codec-factory", help="Python module:function constructing both codec ends")
    args = parser.parse_args()
    if args.delay_ms < 0 or args.ttl_ms <= 0 or args.refresh_ms <= 0:
        parser.error("Require nonnegative delay and positive TTL/refresh")
    codec = load_codec(args.codec_factory) if args.codec_factory else None
    with (args.result / "policy.jsonl").open("x", encoding="utf-8") as log, socket.socket() as listener:
        policy = ReportingPolicy(args.encoding, log, delay_ns=args.delay_ms * MS,
                                 ttl_ns=args.ttl_ms * MS, refresh_ns=args.refresh_ms * MS, codec=codec)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        (args.result / "port").write_text(str(listener.getsockname()[1]), encoding="ascii")
        serve(listener, policy)


if __name__ == "__main__":
    main()
