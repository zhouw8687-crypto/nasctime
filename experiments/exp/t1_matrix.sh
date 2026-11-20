#!/usr/bin/env bash
# ============================================================
# T1 帧长矩阵：64/128/512/1024/1472/9000 B × 30%/80% 负载
#
# 用法：experiments/exp/t1_matrix.sh [负载百分比...]
#       缺省跑 30 和 80
# 依赖：pe_test 场景（单流、2 跳、100 Mbps、NoGating）
# ============================================================
set -uo pipefail

B=/media/a100/data/zbw/nasctime
CONDA=/media/a100/data/zbw/conda-envs/nasctime
PY="$CONDA/bin/python"
D="$B/nascTime/simulations/demos/pe_test"

export PATH="$B/omnetpp-6.4.0/bin:$CONDA/bin:$PATH"
export LD_LIBRARY_PATH="$CONDA/lib:$B/omnetpp-6.4.0/lib"
export INET_ROOT="$B/inet"
export SIMU5G_ROOT="$B/Simu5G"
export NASCTIME_ROOT="$B/nascTime"

LOADS=("$@")
if [ ${#LOADS[@]} -eq 0 ]; then LOADS=(30 80); fi
SIZES=(64 128 512 1024 1472 9000)

OUT=/tmp/t1_matrix.csv
echo "load,payload,sent,recv,mean_us,p2p_us,rms_us,loss_pct,bw_mbps" > "$OUT"

for L in "${LOADS[@]}"; do
    for P in "${SIZES[@]}"; do
        IV=$($PY -c "print(int(round(($P+46)*8/($L/100*1e8)*1e6)))")
        R="/tmp/t1_${L}_${P}"
        rm -rf "$R"
        ( cd "$D" && ../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c NoGating -r 0 \
            --sim-time-limit=1s --result-dir="$R" \
            "--*.client1.app[0].messageLength=${P}B" \
            "--*.client1.app[0].sendInterval=${IV}us" \
            '--*.client2.numApps=0' '--*.eth[*].mtu=9000B' > "/tmp/t1_${L}_${P}.log" 2>&1 )
        rc=$?
        if [ $rc -ne 0 ]; then echo "L=$L P=$P FAILED rc=$rc"; continue; fi

        $PY - "$R" "$L" "$P" >> "$OUT" <<'EOF'
import sys, re, glob, os
d, L, P = sys.argv[1], sys.argv[2], sys.argv[3]
f = glob.glob(os.path.join(d, "*.sca"))[0]
h, sc, cur = {}, {}, None
for line in open(f, encoding="utf-8", errors="replace"):
    line = line.rstrip()
    m = re.match(r"^statistic\s+(\S+)\s+(\S+):histogram", line)
    if m:
        cur = (m.group(1), m.group(2)); h.setdefault(cur, {}); continue
    m = re.match(r"^field\s+(\S+)\s+(\S+)", line)
    if m and cur:
        try: h[cur][m.group(1)] = float(m.group(2))
        except ValueError: pass
        continue
    m = re.match(r"^scalar\s+(\S+)\s+(\S+)\s+([-\d.eE+]+)", line)
    if m:
        try: sc[(m.group(1), m.group(2))] = float(m.group(3))
        except ValueError: pass
k = [x for x in h if "server.app[0]" in x[0] and "endToEndDelay" in x[1]]
s = h[k[0]] if k else {}
sent = sc.get(("PeNetwork.client1.app[0]", "packetSent:count"), 0)
recv = sc.get(("PeNetwork.server.app[0]", "packetReceived:count"), 0)
byts = sc.get(("PeNetwork.server.app[0]", "packetReceived:sum(packetBytes)"), 0)
loss = 100 * (sent - recv) / sent if sent else 0
print("%s,%s,%d,%d,%.1f,%.1f,%.1f,%.3f,%.1f" % (
    L, P, sent, recv, s.get("mean", 0) * 1e6,
    (s.get("max", 0) - s.get("min", 0)) * 1e6,
    s.get("stddev", 0) * 1e6, loss, byts * 8 / 1e6))
EOF
        echo "done L=$L P=$P"
    done
done

echo "---- 结果汇总 ----"
cat "$OUT"
