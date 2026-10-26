#!/usr/bin/env python3
"""analyze_frer_agg.py — FRER run 级聚合（每 run 一行，仅 CLC/FRER 流口径）"""
import csv, re, sys
from pathlib import Path

sys.path.insert(0, "/media/a100/data/zbw/nasctime/nascTime/simulations/demos/ext_multiendpoint_test")
from vec_parse import parse_vec_file, percentile
from tqdm import tqdm

RESULT_DIR = Path("/media/a100/data/zbw/nasctime/experiments/results/frer")
NET = "ExtendedMultiEndpointNetwork"
FNAME_RE = re.compile(r"Frer(?P<cfg>\w+)_N(?P<N>\d+)_run(?P<rn>\d+)\.sca$")
SCHED = (["MAXCI"]*5 + ["PF"]*5 + ["DRR"]*5 + ["QOS_PF"]*5)
CLC_APPS, CLC_EPS = range(5), range(5)   # app[0..4]=CLC 发送流, 端点 0..4=CLC 接收

def parse_sca(path):
    data = {}
    with path.open() as f:
        for line in f:
            p = line.split()
            if len(p) >= 4 and p[0] == "scalar":
                data[(p[1], p[2])] = p[3]
    return data

def vec_index(path):
    idx = {}
    try:
        for vid, v in parse_vec_file(path).items():
            idx[(v["module"], v["name"])] = v["values"]
    except Exception as e:
        sys.stderr.write(f"vec fail {path.name}: {e}\n")
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
    out.writerow(["config","run","sched","rep","sent","received","loss_rate",
                  "delay_mean_ms","delay_p99_ms","delay_max_ms",
                  "replicated","primary","recovered_primary","recovered_replica","duplicates_dropped"])
    for sca in tqdm(sorted(RESULT_DIR.glob("*.sca")), desc="FRER聚合", unit="file"):
        m = FNAME_RE.search(sca.name)
        if not m: continue
        cfg, rn = m.group("cfg"), int(m.group("rn"))
        sched, rep = SCHED[rn], rn % 5
        data = parse_sca(sca)
        vix = vec_index(sca.with_suffix(".vec"))
        sent = 0
        for ai in CLC_APPS:
            v = data.get((f"{NET}.tsnDeviceA.app[{ai}]", "packetSent:count"))
            if v: sent += int(v)
        recv, rp, rr, dd, delays = 0, 0, 0, 0, []
        for ep in CLC_EPS:
            mod = f"{NET}.tsnDeviceB[{ep}].app[0]"
            r = data.get((mod, "packetReceived:count"))
            if r: recv += int(r)
            delays.extend(vix.get((mod, "endToEndDelay:vector"), []))
            frmod = f"{NET}.dsTt[{ep}].frerRecovery"
            rp += int(data.get((frmod, "recoveredFromPrimary:count"), 0) or 0)
            rr += int(data.get((frmod, "recoveredFromReplica:count"), 0) or 0)
            dd += int(data.get((frmod, "duplicatesDropped:count"), 0) or 0)
        loss = round(1 - recv/sent, 5) if sent and recv else ""
        d_mean, d_p99, d_max = stats_of(delays)
        repmod = f"{NET}.nwTt.frerReplicator"
        replicated = data.get((repmod, "replicatedFrames:count"), "")
        primary = data.get((repmod, "primarySent:count"), "")
        out.writerow([cfg, rn, sched, rep, sent, recv, loss, d_mean, d_p99, d_max,
                      replicated, primary, rp, rr, dd])

if __name__ == "__main__":
    main()
