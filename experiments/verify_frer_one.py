#!/usr/bin/env python3
"""验证单文件处理逻辑: FrerAsym_N15_run0.sca（与已 grep 确认的值核对）"""
import sys
from pathlib import Path
sys.path.insert(0, "/media/a100/data/zbw/nasctime/nascTime/simulations/demos/ext_multiendpoint_test")
from vec_parse import parse_vec_file, percentile

RESULT_DIR = Path("/media/a100/data/zbw/nasctime/experiments/results/frer")
NET = "ExtendedMultiEndpointNetwork"

def parse_sca(path):
    data = {}
    with path.open() as f:
        for line in f:
            p = line.split()
            if len(p) >= 4 and p[0] == "scalar":
                data[(p[1], p[2])] = p[3]
    return data

sca = RESULT_DIR / "FrerAsym_N15_run0.sca"
data = parse_sca(sca)
vix = {}
for vid, v in parse_vec_file(sca.with_suffix(".vec")).items():
    vix[(v["module"], v["name"])] = v["values"]

print("=== 发送端 tsnDeviceA.app[0..4] packetSent:count ===")
sent = 0
for ai in range(5):
    v = data.get((f"{NET}.tsnDeviceA.app[{ai}]", "packetSent:count"))
    print(f"  app[{ai}]: {v}")
    if v: sent += int(v)
print(f"  CLC 总发送 sent = {sent}  (期望 40000 = primarySent)")

print("\n=== 接收端端点 0..4 明细 ===")
recv = rp = rr = dd = 0
delays = []
for ep in range(5):
    mod = f"{NET}.tsnDeviceB[{ep}].app[0]"
    r = data.get((mod, "packetReceived:count"))
    line = f"  端点{ep}: received={r}"
    vals = vix.get((mod, "endToEndDelay:vector"), [])
    if vals:
        vals.sort()
        mean = sum(vals)/len(vals)*1000
        p99 = percentile(vals, 0.99)*1000
        line += f"  delay mean={mean:.3f}ms p99={p99:.3f}ms n={len(vals)}"
        delays.extend(vals)
    frmod = f"{NET}.dsTt[{ep}].frerRecovery"
    rp_ = data.get((frmod, "recoveredFromPrimary:count"))
    rr_ = data.get((frmod, "recoveredFromReplica:count"))
    dd_ = data.get((frmod, "duplicatesDropped:count"))
    line += f"  FRER: recv_primary={rp_} recv_replica={rr_} dup={dd_}"
    print(line)
    if r: recv += int(r)
    rp += int(rp_ or 0); rr += int(rr_ or 0); dd += int(dd_ or 0)

print(f"\n=== 聚合 ===")
print(f"  received 总和 = {recv}")
print(f"  loss_rate = {round(1-recv/sent,5) if sent and recv else ''}  (期望 ~0.00025 = 0.025%)")
print(f"  delay 合并: n={len(delays)}")
if delays:
    delays.sort()
    print(f"    mean={sum(delays)/len(delays)*1000:.3f}ms p99={percentile(delays,0.99)*1000:.3f}ms max={delays[-1]*1000:.3f}ms")
print(f"  recovered_primary 和 = {rp}")
print(f"  recovered_replica 和 = {rr}")
print(f"  duplicates_dropped 和 = {dd}")
print("\n核对点: 端点0 recv_primary=3877 recv_replica=4121 dup=5194 | 端点1: 3726/4273/5215 (grep 确认值)")
