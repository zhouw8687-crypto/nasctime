#!/usr/bin/env python3
"""
gen_profile_ini.py — Generate per-endpoint app configuration for nascTime
                     heterogeneous traffic scenarios.

Reads a profile assignment (CLC/MV/BLK per endpoint) and emits an .ini
fragment that can be included from the main omnetpp.ini via:

    include profiles_N{N}.ini

The output covers:
  - tsnDeviceA.numApps and per-app traffic generators
  - tsnDeviceA streamIdentifier + streamCoder mappings
  - tsnDeviceB[*].numApps and sink/reverse-traffic apps
  - SDAP drbConfig for the gNB (per-UE) and the UEs

Profiles
--------
CLC = closed-loop control
    HP   100 B @ 1 ms CBR    PCP=7  QFI=7  DRB 2  deadline 2 ms

MV  = machine vision + monitoring
    HP   1500 B @ 5 ms CBR   PCP=6  QFI=6  DRB 1  deadline 10 ms
    BE   500 B @ exp(2 ms)   PCP=0  QFI=0  DRB 0  deadline 50 ms

BLK = bulk / asset tracking
    BE   1200 B @ exp(10 ms) PCP=0  QFI=0  DRB 0  deadline 100 ms

Reverse: every endpoint sends 100 B @ 10 ms CBR to TSN Device A.

Usage
-----
    # Generate for the standard N=5 mix:
    python3 gen_profile_ini.py 5 > profiles_N5.ini

    # Custom profile string:
    python3 gen_profile_ini.py --profiles "CLC,CLC,MV,BLK" > custom.ini

    # All standard sizes at once:
    python3 gen_profile_ini.py --all
"""

from __future__ import annotations
import argparse
import sys
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Profile definitions
# ---------------------------------------------------------------------------

@dataclass
class FlowSpec:
    """A single application flow within a profile."""
    name: str           # short name, used in port allocation and stream id
    msg_bytes: int
    interval: str       # OMNeT++ expression: "1ms" or "exponential(2ms)"
    pcp: int
    qfi: int
    drb: int
    deadline_ms: float


@dataclass
class ProfileDef:
    """A traffic profile = ordered list of flows."""
    name: str
    flows: list[FlowSpec] = field(default_factory=list)


CLC = ProfileDef(
    name="CLC",
    flows=[
        FlowSpec(name="clc_hp",  msg_bytes=100,  interval="1ms",
                 pcp=7, qfi=7, drb=2, deadline_ms=2.0),
    ],
)

MV = ProfileDef(
    name="MV",
    flows=[
        FlowSpec(name="mv_hp",   msg_bytes=1500, interval="5ms",
                 pcp=6, qfi=6, drb=1, deadline_ms=10.0),
        FlowSpec(name="mv_be",   msg_bytes=500,  interval="exponential(2ms)",
                 pcp=0, qfi=0, drb=0, deadline_ms=50.0),
    ],
)

BLK = ProfileDef(
    name="BLK",
    flows=[
        FlowSpec(name="blk_be",  msg_bytes=1200, interval="exponential(10ms)",
                 pcp=0, qfi=0, drb=0, deadline_ms=100.0),
    ],
)

PROFILES = {p.name: p for p in [CLC, MV, BLK]}


# Standard profile assignments per N (CLC,MV,BLK split as roughly 1/3 each
# with CLC and MV equal, BLK taking the remainder).
STANDARD_MIX = {
    1:  ["CLC"],
    5:  ["CLC", "CLC", "MV", "MV", "BLK"],
    10: ["CLC", "CLC", "CLC", "CLC", "MV", "MV", "MV", "MV", "BLK", "BLK"],
    15: ["CLC"] * 5 + ["MV"] * 5 + ["BLK"] * 5,
    20: ["CLC"] * 7 + ["MV"] * 7 + ["BLK"] * 6,
    30: ["CLC"] * 10 + ["MV"] * 10 + ["BLK"] * 10,
    40: ["CLC"] * 14 + ["MV"] * 14 + ["BLK"] * 12,
}


# ---------------------------------------------------------------------------
# Port and stream allocation
# ---------------------------------------------------------------------------

# Port plan: each endpoint i and each flow within its profile gets a unique
# (destPort, localPort) pair so apps and sinks can be matched cleanly.
#
# Forward port = 5000 + 100*endpoint_index + flow_index
# Reverse traffic uses port 7000 (sink on Device A is shared).
def forward_port(endpoint_idx: int, flow_idx: int) -> int:
    return 5000 + 20 * endpoint_idx + flow_idx


REVERSE_PORT = 7000


# VLAN allocation: 100 + 10*endpoint + flow_idx
def vlan_id(endpoint_idx: int, flow_idx: int) -> int:
    return 100 + 10 * endpoint_idx + flow_idx


# ---------------------------------------------------------------------------
# Profile parsing and validation
# ---------------------------------------------------------------------------

def parse_profile_string(s: str) -> list[str]:
    parts = [p.strip().upper() for p in s.split(",") if p.strip()]
    for p in parts:
        if p not in PROFILES:
            raise ValueError(f"Unknown profile '{p}'. Valid: {list(PROFILES)}")
    return parts


def assignment_for_n(n: int) -> list[str]:
    if n in STANDARD_MIX:
        return STANDARD_MIX[n]
    raise ValueError(f"No standard mix for N={n}. Use --profiles to specify.")


def expand_assignment(profile_names: Iterable[str]) -> list[tuple[int, str, ProfileDef]]:
    """Return list of (endpoint_idx, profile_name, ProfileDef)."""
    return [(i, name, PROFILES[name]) for i, name in enumerate(profile_names)]


# ---------------------------------------------------------------------------
# .ini emission
# ---------------------------------------------------------------------------

def emit_header(out, profile_names: list[str]) -> None:
    n = len(profile_names)
    print(f"# ============================================================", file=out)
    print(f"# Auto-generated by gen_profile_ini.py", file=out)
    print(f"# numEndpoints = {n}", file=out)
    print(f"# profiles = {','.join(profile_names)}", file=out)
    print(f"# Counts: {', '.join(f'{p}={profile_names.count(p)}' for p in sorted(set(profile_names)))}", file=out)
    print(f"# ============================================================", file=out)
    print(f"", file=out)
    print(f"*.numEndpoints = {n}", file=out)
    print(f'*.endpointProfiles = "{",".join(profile_names)}"', file=out)
    print(f"", file=out)


def emit_sdap(out, n: int) -> None:
    """Emit SDAP drbConfig for n UEs with four DRBs (DRB 0/1/2/3).

    DRB 3 is reserved for gPTP traffic (QFI=5, DSCP=46 EF). This prevents
    gPTP frames from being starved on DRB 0 when BE traffic saturates under
    high endpoint counts, which otherwise causes slave clock servo divergence.
    """
    print(f"# ----- SDAP / DRB config (4 DRBs: BE/MV-HP/CLC/gPTP) -----", file=out)
    print(f"", file=out)

    # gNB drbConfig: one entry per (UE, DRB)
    print(f"*.gnb.cellularNic.sdap.drbConfig = [ \\", file=out)
    entries = []
    for i in range(n):
        ue_id = 2049 + i
        entries.append(f"    {{drb: 0, ue: {ue_id}, qfiList: [0]}}")
        entries.append(f"    {{drb: 1, ue: {ue_id}, qfiList: [6]}}")
        entries.append(f"    {{drb: 2, ue: {ue_id}, qfiList: [7]}}")
        entries.append(f"    {{drb: 3, ue: {ue_id}, qfiList: [5]}}")  # gPTP
    print(", \\\n".join(entries) + "]", file=out)
    print(f"", file=out)

    # UE drbConfig (uniform across UEs)
    print(f"*.ue[*].cellularNic.sdap.drbConfig = [ \\", file=out)
    print(f"    {{drb: 0, qfiList: [0]}}, \\", file=out)
    print(f"    {{drb: 1, qfiList: [6]}}, \\", file=out)
    print(f"    {{drb: 2, qfiList: [7]}}, \\", file=out)
    print(f"    {{drb: 3, qfiList: [5]}}]", file=out)
    print(f"", file=out)


# ---------------------------------------------------------------------------
# drbQosConfig emission (per-DRB QoS parameters for QoS-PF scheduler)
# ---------------------------------------------------------------------------
#
# Schema used by QoS-PF scheduler (src/stack/mac/scheduling_modules/
# QoSAwareScheduler.cc::computeQosWeight):
#   weight = (gbr ? 2 : 1) * (10 / (priority+1)) * delay_bonus
# where delay_bonus = 5.0 if delayBudget<=10ms, 3.0 if <=50ms, 1.5 if <=100ms
#
# Priority 0 (lowest numeric) gets the highest weight: weight *= 10
# DRB 3 at priority 0 with 1 ms budget and gbr=true gets weight = 2*10*5 = 100
# DRB 2 at priority 1 with 2 ms budget and gbr=true gets weight = 2*5*5 = 50
# DRB 1 at priority 2 with 10 ms budget and gbr=true gets weight = 2*3.3*5 = 33
# DRB 0 at priority 3 with 50 ms budget and gbr=false gets weight = 1*2.5*3 = 7.5

DRB_QOS_TEMPLATE = [
    # DRB 0: best effort (MV-BE, BLK)
    {"gbr": "false", "delayBudget": 50, "per": "1e-2", "priority": 3},
    # DRB 1: MV high-priority
    {"gbr": "true",  "delayBudget": 10, "per": "1e-3", "priority": 2},
    # DRB 2: CLC closed-loop control
    {"gbr": "true",  "delayBudget":  2, "per": "1e-4", "priority": 1},
    # DRB 3: gPTP time synchronization (highest priority)
    {"gbr": "true",  "delayBudget":  1, "per": "1e-5", "priority": 0},
]


def emit_drb_qos(out, n: int) -> None:
    """Emit drbQosConfig for n UEs x 4 DRBs = 4n entries."""
    print(f"# ----- drbQosConfig (per-UE x per-DRB QoS parameters) -----", file=out)
    print(f"*.gnb.cellularNic.mac.drbQosConfig = [ \\", file=out)

    entries = []
    for i in range(n):
        ue_id = 2049 + i
        for drb_idx, qos in enumerate(DRB_QOS_TEMPLATE):
            entries.append(
                f'    {{"drb": {drb_idx}, "ue": {ue_id}, '
                f'"gbr": {qos["gbr"]}, '
                f'"delayBudget": {qos["delayBudget"]}, '
                f'"per": {qos["per"]}, '
                f'"priority": {qos["priority"]}}}'
            )
    print(", \\\n".join(entries) + "]", file=out)
    print(f"", file=out)


def emit_device_a_apps(out, assignment: list[tuple[int, str, ProfileDef]]) -> None:
    """Emit tsnDeviceA.numApps and per-app generators + 1 reverse sink."""
    # Build flat list of (app_idx, endpoint_idx, flow_idx, flow, profile_name)
    flat = []
    for ep_idx, prof_name, prof in assignment:
        for flow_idx, flow in enumerate(prof.flows):
            flat.append((ep_idx, prof_name, flow_idx, flow))

    num_gen_apps = len(flat)
    sink_app_idx = num_gen_apps  # one sink for all reverse traffic
    total_apps = num_gen_apps + 1

    print(f"# ----- TSN Device A: traffic generators -----", file=out)
    print(f"*.tsnDeviceA.hasOutgoingStreams = true", file=out)
    print(f"*.tsnDeviceA.numApps = {total_apps}", file=out)
    print(f"", file=out)

    for app_idx, (ep_idx, prof_name, flow_idx, flow) in enumerate(flat):
        port = forward_port(ep_idx, flow_idx)
        print(f"# app[{app_idx}]: endpoint {ep_idx} ({prof_name}) flow '{flow.name}'", file=out)
        print(f'*.tsnDeviceA.app[{app_idx}].typename = "UdpBasicApp"', file=out)
        print(f'*.tsnDeviceA.app[{app_idx}].destAddresses = "tsnDeviceB[{ep_idx}]"', file=out)
        print(f"*.tsnDeviceA.app[{app_idx}].destPort = {port}", file=out)
        print(f"*.tsnDeviceA.app[{app_idx}].localPort = {port}", file=out)
        print(f"*.tsnDeviceA.app[{app_idx}].messageLength = {flow.msg_bytes}B", file=out)
        print(f"*.tsnDeviceA.app[{app_idx}].sendInterval = {flow.interval}", file=out)
        print(f"*.tsnDeviceA.app[{app_idx}].startTime = uniform(0s, 0.01s)", file=out)
        print(f"*.tsnDeviceA.app[{app_idx}].dscp = {flow.qfi}", file=out)
        print(f"", file=out)

    # Reverse traffic sink
    print(f"# app[{sink_app_idx}]: reverse traffic sink", file=out)
    print(f'*.tsnDeviceA.app[{sink_app_idx}].typename = "UdpSink"', file=out)
    print(f"*.tsnDeviceA.app[{sink_app_idx}].localPort = {REVERSE_PORT}", file=out)
    print(f"", file=out)

    return flat


def emit_stream_mappings(out, flat: list[tuple]) -> None:
    """Emit streamIdentifier + streamCoder mappings."""
    print(f"# ----- TSN Device A: stream identification + VLAN encoding -----", file=out)

    id_entries = []
    coder_entries = []
    for app_idx, (ep_idx, prof_name, flow_idx, flow) in enumerate(flat):
        stream_name = f"ep{ep_idx}_{flow.name}"
        id_entries.append(f'    {{packetFilter: "*-{app_idx}", stream: "{stream_name}"}}')
        coder_entries.append(
            f'    {{stream: "{stream_name}", vlan: {vlan_id(ep_idx, flow_idx)}, pcp: {flow.pcp}}}'
        )

    print(f"*.tsnDeviceA.bridging.streamIdentifier.identifier.mapping = [ \\", file=out)
    print(", \\\n".join(id_entries) + "]", file=out)
    print(f"", file=out)

    print(f"*.tsnDeviceA.bridging.streamCoder.encoder.mapping = [ \\", file=out)
    print(", \\\n".join(coder_entries) + "]", file=out)
    print(f"", file=out)


def emit_device_b_apps(out, assignment: list[tuple[int, str, ProfileDef]]) -> None:
    """Emit per-Device-B sink apps + reverse-traffic source.

    Because each Device B has a different number of flows depending on its
    profile, we emit per-endpoint configuration rather than wildcards.
    """
    print(f"# ----- TSN Device B: per-endpoint sinks + reverse source -----", file=out)
    for ep_idx, prof_name, prof in assignment:
        n_sinks = len(prof.flows)
        n_apps = n_sinks + 1  # + reverse source

        print(f"# Device B[{ep_idx}] ({prof_name}): {n_sinks} sink(s) + 1 reverse source",
              file=out)
        print(f"*.tsnDeviceB[{ep_idx}].numApps = {n_apps}", file=out)

        for flow_idx, flow in enumerate(prof.flows):
            port = forward_port(ep_idx, flow_idx)
            print(f'*.tsnDeviceB[{ep_idx}].app[{flow_idx}].typename = "UdpSink"', file=out)
            print(f"*.tsnDeviceB[{ep_idx}].app[{flow_idx}].localPort = {port}", file=out)

        # Reverse source (always last app)
        rev = n_sinks
        print(f'*.tsnDeviceB[{ep_idx}].app[{rev}].typename = "UdpBasicApp"', file=out)
        print(f'*.tsnDeviceB[{ep_idx}].app[{rev}].destAddresses = "tsnDeviceA"', file=out)
        print(f"*.tsnDeviceB[{ep_idx}].app[{rev}].destPort = {REVERSE_PORT}", file=out)
        print(f"*.tsnDeviceB[{ep_idx}].app[{rev}].localPort = {REVERSE_PORT}", file=out)
        print(f"*.tsnDeviceB[{ep_idx}].app[{rev}].messageLength = 100B", file=out)
        print(f"*.tsnDeviceB[{ep_idx}].app[{rev}].sendInterval = 10ms", file=out)
        print(f"*.tsnDeviceB[{ep_idx}].app[{rev}].startTime = 1s", file=out)
        print(f"", file=out)


def emit_bmca_spanning_tree(out, n: int) -> None:
    """Emit Static BMCA spanning tree for n endpoints."""
    print(f"# ----- Static BMCA spanning tree (auto-generated for N={n}) -----", file=out)
    entries = [
        '    {node: "tsnDeviceA", role: "MASTER", masterPorts: ["eth0"], slavePort: ""}',
        '    {node: "tsnSwitch", role: "BRIDGE", masterPorts: ["eth1"], slavePort: "eth0"}',
    ]
    for i in range(n):
        entries.append(
            f'    {{node: "tsnDeviceB[{i}]", role: "SLAVE", masterPorts: [], slavePort: "eth0"}}'
        )
    print("*.staticBmca.spanningTree = [ \\", file=out)
    print(", \\\n".join(entries) + "]", file=out)
    print(f"", file=out)


def emit_nwtt_registration(out, n: int) -> None:
    """Emit nwTt translator multi-endpoint registration."""
    print(f"# ----- NW-TT multi-endpoint registration -----", file=out)
    entries = [
        f'    {{address: "tsnDeviceB[{i}]", ue: "ue[{i}]"}}'
        for i in range(n)
    ]
    print("*.nwTt.translator.tsnDeviceBAddresses = [ \\", file=out)
    print(", \\\n".join(entries) + "]", file=out)
    print(f"", file=out)


def emit_full(out, profile_names: list[str]) -> None:
    """Emit a complete .ini fragment for the given profile assignment."""
    n = len(profile_names)
    assignment = expand_assignment(profile_names)

    emit_header(out, profile_names)
    emit_nwtt_registration(out, n)
    emit_sdap(out, n)
    emit_drb_qos(out, n)
    flat = emit_device_a_apps(out, assignment)
    emit_stream_mappings(out, flat)
    emit_device_b_apps(out, assignment)
    emit_bmca_spanning_tree(out, n)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Generate per-endpoint .ini fragment for nascTime heterogeneous traffic.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("n", type=int, nargs="?",
                   help="Endpoint count (uses standard mix). One of: 1, 5, 10, 15, 20.")
    g.add_argument("--profiles", type=str,
                   help="Custom profile string (comma-separated, e.g. 'CLC,MV,BLK').")
    g.add_argument("--all", action="store_true",
                   help="Emit profiles_N{N}.ini for all standard sizes.")
    ap.add_argument("-o", "--output-dir", default=".",
                    help="Output directory for --all (default: current dir).")
    args = ap.parse_args()

    if args.all:
        from pathlib import Path
        outdir = Path(args.output_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        for n in sorted(STANDARD_MIX.keys()):
            path = outdir / f"profiles_N{n}.ini"
            with path.open("w") as f:
                emit_full(f, STANDARD_MIX[n])
            print(f"Wrote {path}", file=sys.stderr)
        return

    if args.profiles is not None:
        names = parse_profile_string(args.profiles)
    else:
        names = assignment_for_n(args.n)

    emit_full(sys.stdout, names)


if __name__ == "__main__":
    main()
