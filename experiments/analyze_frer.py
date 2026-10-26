#!/usr/bin/env python3
"""analyze_frer.py (v2 高效版) — 每个 .vec 只解析一次，索引后提取所有端点统计"""
import csv, re, sys, math
from pathlib import Path

sys.path.insert(0, "/media/a100/data/zbw/nasctime/nascTime/simulations/demos/ext_multiendpoint_test")
from vec_parse import parse_vec_file, percentile
from tqdm import tqdm

RESULT_DIR = Path("/media/a100/data/zbw/nasctime/experiments/results/frer")
NET = "ExtendedMultiEndpointNetwork"
FNAME_RE = re.compile(r"Frer(?P<cfg>\w+)_N(?P<N>\d+)_run(?P<rn>\d+)\.sca$")
SCHED = (["MAXCI"]*5 + ["PF"]*5 + ["DRR"]*5 + ["QOS_PF"]*5)

def parse_sca(path):
    data = {}
    with path.open() as f:
        for line in f:
            p = line.split()
            if len(p) >= 4 and p[0] == "scalar":
                data[(p[1], p[2])] = p[3]
    return data

def vec_index(vec_path):
    """解析 .vec 一次，返回 {(module, name): values}"""
    idx = {}
    try:
        vd = parse_vec_file(vec_path)
        for vid, v in vd.items():
            idx[(v["module"], v["name"])] = v["values"]
    except Exception as e:
        sys.stderr.write(f"vec parse fail {vec_path.name}: {e}\n")
    return idx

def stats_of(values):
    if not values:
        return "", "", ""
    values.sort()
    mean = sum(values) / len(values)
    return (round(mean*1000, 3), round(percentile(values, 0.99)*1000, 3),
            round(values[-1]*1000, 3))

def main():
    out = csv.writer(sys.stdout)
    out.writerow(["config","run","sched","rep","endpoint","sent","received","loss_rate",
                  "delay_mean_ms","delay_p99_ms","delay_max_ms",
                  "replicated","primary","recovered_primary","recovered_replica","duplicates_dropped"])
    for sca in tqdm(sorted(RESULT_DIR.glob("*.sca")), desc="FRER结果", unit="file"):
        m = FNAME_RE.search(sca.name)
        if not m: continue
        cfg, N, rn = m.group("cfg"), int(m.group("N")), int(m.group("rn"))
        sched, rep = SCHED[rn], rn % 5
        data = parse_sca(sca)
        vix = vec_index(sca.with_suffix(".vec"))
        repmod = f"{NET}.nwTt.frerReplicator"
        replicated = data.get((repmod, "replicatedFrames:count"), "")
        primary = data.get((repmod, "primarySent:count"), "")
        for ep in range(N):
            for ai in range(10):
                mod = f"{NET}.tsnDeviceB[{ep}].app[{ai}]"
                sent = data.get((mod, "packetSent:count"))
                recv = data.get((mod, "packetReceived:count"))
                if sent is None and recv is None: continue
                d_mean, d_p99, d_max = stats_of(vix.get((mod, "endToEndDelay:vector"), []))
                frmod = f"{NET}.dsTt[{ep}].frerRecovery"
                rp = data.get((frmod, "recoveredFromPrimary:count"), "")
                rr = data.get((frmod, "recoveredFromReplica:count"), "")
                dd = data.get((frmod, "duplicatesDropped:count"), "")
                loss = ""
                if sent and recv:
                    loss = round(1 - int(recv)/int(sent), 5)
                out.writerow([cfg, rn, sched, rep, ep, sent or "", recv or "", loss,
                              d_mean, d_p99, d_max, replicated, primary, rp, rr, dd])
        sys.stderr.write(f"done {sca.name}\n")

if __name__ == "__main__":
    main()
