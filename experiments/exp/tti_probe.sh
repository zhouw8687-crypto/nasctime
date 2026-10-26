#!/usr/bin/env bash
# ============================================================
# 探针 EXP-01：numerologyIndex 是否真的改变 MAC 调度周期（TTI）
#
# 原理：Simu5G 的 MAC 每个 TTI 发一个名为 ttiTick_ 的自消息。
#       开 eventlog 后，该消息的 BS 记录里 `at` 字段就是到达时刻；
#       取同一模块前两个 tick 的间隔，即为其 TTI 真值。
#       再用 elog 的 MC 表把 sm id 映射回模块类型。
#
# 用法：experiments/exp/tti_probe.sh [idx1 idx2 ...]      默认 1 3
#       SIM_TIME_LIMIT=0.05s experiments/exp/tti_probe.sh 3
#
# 环境说明（踩过的坑，勿改回去）：
#   1) 不要 source ~/nasctime-env.sh：其中的 nascTime/setenv 要求交互式 shell
#      （$-$ 含 i），非交互执行会打印 not a login shell 并 exit 1。
#   2) 不要 source omnetpp-6.4.0/setenv 后再依赖 LD_LIBRARY_PATH：
#      实测在子进程里该变量会丢失，导致加载系统 Qt6 并报
#      "version `Qt_6.11' not found"。这里改为直接 export，且把
#      conda 的 lib 放在最前（liboppqtenv.so 的 RUNPATH 里没有它）。
# ============================================================
set -uo pipefail

NASCTIME_BASE=/media/a100/data/zbw/nasctime
OMNETPP="$NASCTIME_BASE/omnetpp-6.4.0"
CONDA_LIB="$NASCTIME_BASE/conda-envs/nasctime/lib"
SCEN="$NASCTIME_BASE/nascTime/simulations/demos/frer_test"
SIM_TIME_LIMIT="${SIM_TIME_LIMIT:-0.02s}"

export PATH="$OMNETPP/bin:$NASCTIME_BASE/conda-envs/nasctime/bin:$PATH"
export LD_LIBRARY_PATH="$CONDA_LIB:$OMNETPP/lib"
export INET_ROOT="$NASCTIME_BASE/inet"
export SIMU5G_ROOT="$NASCTIME_BASE/Simu5G"
export NASCTIME_ROOT="$NASCTIME_BASE/nascTime"

IDXS=("$@")
if [ ${#IDXS[@]} -eq 0 ]; then IDXS=(1 3); fi

for idx in "${IDXS[@]}"; do
    out="/tmp/tti_$idx"
    rm -rf "$out"; mkdir -p "$out"

    if ! ( cd "$SCEN" && env LD_LIBRARY_PATH="$LD_LIBRARY_PATH" ../../../bin/nasctime-run.sh \
            -f frer_sweep.ini -c FrerBaseline_N15 -u Cmdenv -r 0 \
            --sim-time-limit="$SIM_TIME_LIMIT" --record-eventlog=true \
            --result-dir="$out" \
            "--*.carrierAggregation.componentCarrier[0].numerologyIndex=$idx" \
            > "/tmp/tti_run_$idx.log" 2>&1 ); then
        echo "idx=$idx 运行失败，见 /tmp/tti_run_$idx.log"
        tail -2 "/tmp/tti_run_$idx.log" | sed 's/^/    /'
        if grep -q "Qt_6.11" "/tmp/tti_run_$idx.log" 2>/dev/null; then
            cat <<HINT
  → 动态库路径在子进程里丢失（DSH 非交互环境已复现）。
    请在**交互式终端**里直接运行下面这条，再重跑本脚本的分析部分：
      cd $SCEN && ../../../bin/nasctime-run.sh \
        -f frer_sweep.ini -c FrerBaseline_N15 -u Cmdenv -r 0 \
        --sim-time-limit=$SIM_TIME_LIMIT --record-eventlog=true \
        --result-dir=/tmp/tti_$idx '--*.carrierAggregation.componentCarrier[0].numerologyIndex=$idx'
HINT
        fi
        continue
    fi

    elog=$(ls "$out"/*.elog 2>/dev/null | head -1)
    if [ -z "$elog" ]; then echo "idx=$idx 未生成 elog"; continue; fi

    grep 'ttiTick_' "$elog" | grep '^BS' \
      | sed -n 's/.* sm \([0-9]*\).* at \([0-9.e-]*\).*/\1 \2/p' \
      | awk '{if(!($1 in f))f[$1]=$2; else if(!($1 in s))s[$1]=$2}
             END{for(m in f){d=(m in s)?s[m]-f[m]:-1; printf "%s\t%.7f\n", m, d}}' \
      > /tmp/tti_delta.txt || true

    grep '^MC id ' "$elog" \
      | awk '{id=$3; ty=""; for(i=1;i<=NF;i++) if($i=="t") ty=$(i+1); printf "%s\t%s\n", id, ty}' \
      > /tmp/tti_mods.txt || true

    echo "=== numerologyIndex=$idx  (sim-time-limit=$SIM_TIME_LIMIT) ==="
    awk -F'\t' 'NR==FNR{d[$1]=$2; next} ($1 in d){printf "%8.6f  %s\n", d[$1], $2}' \
        /tmp/tti_delta.txt /tmp/tti_mods.txt | sort -n | uniq -c
    echo
done
