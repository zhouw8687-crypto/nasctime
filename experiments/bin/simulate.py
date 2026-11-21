#!/usr/bin/env python3
"""Run an existing 6G simulation scenario on A100 and report per-flow KPIs."""

import argparse
import csv
import datetime
import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DEMOS = REPO / "nascTime/simulations/demos"
DEFAULT_RESULTS = REPO / "experiments/results"
QUEUE_CONFIGS = {
    "transport": {
        "baseline": {"fifo": "T2Fifo", "priority": "T2Priority", "tas": "T2Tas"},
        "stress": {"fifo": "T3OverloadFifo", "priority": "T3OverloadPriority", "tas": "T3OverloadTas"},
    },
    "e2e": {
        "baseline": {"priority": "E2ePriority", "tas": "E2eTas"},
        "stress": {"priority": "E2eMixedLoadPriority", "tas": "E2eMixedLoad"},
    },
}
MEASUREMENT_VECTORS = (
    "packetSent:vector*", "packetReceived:vector*", "endToEndDelay:vector", "rcvdPkSeqNo:vector",
)
START_ENV = """
set -e
ulimit -c 0
source "$1/omnetpp-6.4.0/setenv"
export INET_ROOT="$1/inet" SIMU5G_ROOT="$1/Simu5G"
export LD_LIBRARY_PATH="$1/../conda-envs/nasctime/lib:$1/omnetpp-6.4.0/lib"
shift
exec "$@"
"""


def select_case(scenario, load, policy):
    if scenario in QUEUE_CONFIGS:
        cases = QUEUE_CONFIGS[scenario][load]
        policy = policy or "priority"
        if policy not in cases:
            raise ValueError(f"{scenario} supports these policies: {', '.join(cases)}")
        ini = "omnetpp_transport.ini" if scenario == "transport" else "omnetpp_qos.ini"
        return "e2e_ladder", ini, cases[policy], policy, []
    if policy is not None:
        raise ValueError(f"{scenario} uses its native scheduler. Omit --policy for this scenario.")
    source = "server" if scenario == "ran" else "hostA"
    interval = "10ms" if load == "baseline" else "1ms"
    overrides = [
        f"--*.{source}.app[0].startTime=100ms",
        f"--*.{source}.app[0].stopTime=1700ms",
        f"--*.{source}.app[0].sendInterval={interval}",
    ]
    return f"{scenario}_test", "omnetpp.ini", "General", None, overrides


def write_manifest(path, metadata, status, error=None):
    metadata["status"] = status
    if error is not None:
        metadata["error"] = error
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summary_table(metadata, rows):
    flow_rows = [row for row in rows if row["window"] == "all"]
    if not flow_rows:
        raise ValueError("No measured flows in flows.csv")
    start, stop = metadata["cohort_seconds"]
    lines = [
        "# 仿真结果",
        "",
        f'场景 `{metadata["scenario"]}` · 负载 `{metadata["load"]}` · 调度 `{metadata["policy"] or "native"}`',
        f'配置 `{metadata["configuration"]}` · 随机种子 `{metadata["seed"]}`',
        "",
        f"按 {start:g}–{stop:g} s 的发送报文统计，排空期间到达的报文计入对应流。",
        "",
        "| 发送端 → 接收端 | 发送 / 送达 | 未送达 % | 平均时延 µs | P99 µs | 峰峰值 µs | 净荷 Mbps |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in flow_rows:
        cells = [
            f'`{row["source"]}` → `{row["sink"]}`',
            f'{row["sent"]} / {row["delivered"]}',
            *[
                f"{float(row[key]):.3f}" if row[key] else "—"
                for key in ("undelivered_pct", "mean_us", "p99_us", "p2p_us", "goodput_mbps")
            ],
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "数据与配置见 `flows.csv`、`run.json` 和 OMNeT++ 原始结果。", ""])
    return "\n".join(lines)


def run(options, folder, ini, configuration, policy, overrides):
    parent = options.output_dir.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    result = Path(tempfile.mkdtemp(prefix=f"{options.scenario}-{stamp}-", dir=parent))
    print(f"结果目录 {result}", flush=True)
    log_file = result / "run.log"
    manifest = result / "run.json"
    directory = DEMOS / folder
    runner = directory / "run.sh" if options.scenario == "ran" else REPO / "nascTime/bin/nasctime-run.sh"
    start, stop = (0.1 if options.scenario == "e2e" else 0.2), 1.7
    cuts = [0.6, 1.1] if options.scenario == "transport" and options.load == "stress" else []
    command = [
        "bash", "-c", START_ENV, "simulate", str(REPO), str(runner),
        "-f", ini, "-u", "Cmdenv", "-c", configuration, "-r", "0",
        "--sim-time-limit=2s", f"--seed-set={options.seed}", f"--result-dir={result}",
        *overrides,
        *(f"--**.app[*].{vector}.vector-recording=true" for vector in MEASUREMENT_VECTORS),
        "--**.vector-recording=false",
    ]
    metadata = {
        "scenario": options.scenario,
        "load": options.load,
        "policy": policy,
        "seed": options.seed,
        "configuration": configuration,
        "cohort_seconds": [start, stop],
        "phase_cuts_seconds": cuts,
        "created_utc": stamp,
        "working_directory": str(directory),
        "command": command,
    }
    stage = "启动环境"
    try:
        metadata["revision"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        metadata["dirty_worktree"] = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=REPO, text=True
        ).strip())
        write_manifest(manifest, metadata, "running")
        with log_file.open("w", encoding="utf-8") as log:
            stage = "运行仿真"
            subprocess.run(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT, check=True)
            stage = "提取逐流指标"
            vectors = list(result.glob("*.vec"))
            if len(vectors) != 1 or len(list(result.glob("*.sca"))) != 1:
                raise ValueError("Expected a single .vec and .sca pair")
            report = [
                sys.executable, str(REPO / "experiments/exp/ladder_kpis.py"),
                str(vectors[0]), "--start", str(start), "--stop", str(stop),
            ]
            for cut in cuts:
                report.extend(("--cut", str(cut)))
            with (result / "flows.csv").open("w", encoding="utf-8", newline="") as output:
                subprocess.run(report, stdout=output, stderr=log, check=True)
        with (result / "flows.csv").open(encoding="utf-8", newline="") as file:
            summary = summary_table(metadata, list(csv.DictReader(file)))
        (result / "summary.md").write_text(summary, encoding="utf-8")
        write_manifest(manifest, metadata, "completed")
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as error:
        detail = f"exit code {error.returncode}" if isinstance(error, subprocess.CalledProcessError) else str(error)
        write_manifest(manifest, metadata, "failed", f"{stage}: {detail}")
        raise RuntimeError(f"{stage}失败（{detail}）。结果和日志目录 {result}") from error
    print(summary, end="")
    print(f"报告 {result / 'summary.md'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("ran", "transport", "core", "e2e"))
    parser.add_argument("--load", choices=("baseline", "stress"), default="baseline")
    parser.add_argument("--policy", choices=("fifo", "priority", "tas"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS, help="parent for new run directories")
    options = parser.parse_args()
    if options.seed < 0:
        parser.error("--seed must be nonnegative")
    try:
        case = select_case(options.scenario, options.load, options.policy)
    except ValueError as error:
        parser.error(str(error))
    try:
        run(options, *case)
    except (RuntimeError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
