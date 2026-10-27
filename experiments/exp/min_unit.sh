#!/usr/bin/env bash
# ============================================================
# 最小仿真单元：一条命令 → 一个端到端场景 → 一张 KPI 表
#
# 用法：
#   experiments/exp/min_unit.sh                          # 默认 FrerBaseline_N15, 3s
#   CONF=FrerBaseline_N15 DUR=10s experiments/exp/min_unit.sh
#
# 输出：控制台表格 + <结果目录>/kpi.csv
#
# 说明：
#   - 场景是 nascTime 的 TSN → NW-TT → UPF → gNB → UE → DS-TT → TSN 端到端链路
#   - 不含控制器、不含 FRER 对比、不含门控（这些是后续叠加项）
#   - DUR 小于 10s 时送达率会偏低：UE 附着与业务启动占掉了开头的时间
# ============================================================
set -uo pipefail

BASE=/media/a100/data/zbw/nasctime
SCEN="$BASE/nascTime/simulations/demos/frer_test"
CONF="${CONF:-FrerBaseline_N15}"
DUR="${DUR:-3s}"
OUT="${OUT:-/tmp/min_unit}"
PY="$BASE/conda-envs/nasctime/bin/python"

export PATH="$BASE/omnetpp-6.4.0/bin:$BASE/conda-envs/nasctime/bin:$PATH"
export LD_LIBRARY_PATH="$BASE/conda-envs/nasctime/lib:$BASE/omnetpp-6.4.0/lib"
export INET_ROOT="$BASE/inet"
export SIMU5G_ROOT="$BASE/Simu5G"
export NASCTIME_ROOT="$BASE/nascTime"

rm -rf "$OUT"; mkdir -p "$OUT"

echo ">>> 运行场景: $CONF  (sim-time-limit=$DUR)"
( cd "$SCEN" && ../../../bin/nasctime-run.sh \
    -f frer_sweep.ini -c "$CONF" -u Cmdenv -r 0 \
    --sim-time-limit="$DUR" --result-dir="$OUT" \
    > "$OUT/run.log" 2>&1 ) || { echo "运行失败，见 $OUT/run.log"; tail -5 "$OUT/run.log"; exit 1; }

echo ">>> 提取 KPI"
"$PY" "$BASE/experiments/exp/kpi_table.py" "$OUT"
