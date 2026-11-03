#!/usr/bin/env bash
# ============================================================
# 四个仿真域冒烟测试：逐个跑通，报告 rc 与产物
#
# 用法：experiments/exp/smoke_domains.sh [域...]
#       域可选：ring mpls mpls_failure ran    （默认全部）
#
# 注意：conda 环境在 /media/a100/data/zbw/conda-envs/nasctime
#       （zbw/ 下，不是 zbw/nasctime/ 下）。写错会报 Qt_6.11 not found。
# ============================================================
set -uo pipefail

B=/media/a100/data/zbw/nasctime
CONDA=/media/a100/data/zbw/conda-envs/nasctime
D="$B/nascTime/simulations/demos"

export PATH="$B/omnetpp-6.4.0/bin:$CONDA/bin:$PATH"
export LD_LIBRARY_PATH="$CONDA/lib:$B/omnetpp-6.4.0/lib"
export INET_ROOT="$B/inet"
export SIMU5G_ROOT="$B/Simu5G"
export NASCTIME_ROOT="$B/nascTime"

ALL=(ring mpls mpls_failure pe ran core system system_wireless)
DOMAINS=("$@")
if [ ${#DOMAINS[@]} -eq 0 ]; then DOMAINS=("${ALL[@]}"); fi

for name in "${DOMAINS[@]}"; do
    case "$name" in
        ring)
            dir="$D/ring_test"
            args=(-f omnetpp_probe.ini -u Cmdenv -r 0 --sim-time-limit=0.05s)
            runner="../../../bin/nasctime-run.sh"
            ;;
        mpls)
            dir="$D/mpls_test"
            args=(-f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=2s)
            runner="../../../bin/nasctime-run.sh"
            ;;
        mpls_failure)
            dir="$D/mpls_failure_test"
            args=(-f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=6s '--**.vector-recording=true')
            runner="../../../bin/nasctime-run.sh"
            ;;
        pe)
            dir="$D/pe_test"
            args=(-f omnetpp.ini -u Cmdenv -c Gating -r 0 --sim-time-limit=1s)
            runner="../../../bin/nasctime-run.sh"
            ;;
        ran)
            dir="$D/ran_test"
            args=(-f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s)
            runner="./run.sh"
            ;;
        core)
            dir="$D/core_test"
            args=(-f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s)
            runner="../../../bin/nasctime-run.sh"
            ;;
        system)
            dir="$D/system_test"
            args=(-f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s)
            runner="../../../bin/nasctime-run.sh"
            ;;
        system_wireless)
            dir="$D/system_test"
            args=(-f omnetpp_wireless.ini -u Cmdenv -r 0 --sim-time-limit=3s)
            runner="../../../bin/nasctime-run.sh"
            ;;
        system_wireless)
            dir="$D/system_test"
            args=(-f omnetpp_wireless.ini -u Cmdenv -r 0 --sim-time-limit=3s)
            runner="../../../bin/nasctime-run.sh"
            ;;
        *)
            echo "未知域：$name"; continue ;;
    esac

    echo "=== $name ($dir) ==="
    rm -rf "$dir/results_$name"
    ( cd "$dir" && $runner "${args[@]}" --result-dir="results_$name" > "/tmp/smoke_$name.log" 2>&1 )
    rc=$?
    if [ $rc -eq 0 ]; then
        printf '  ✅ rc=0  产物: '
        ls "$dir/results" 2>/dev/null | tr '\n' ' '
        echo
    else
        echo "  ❌ rc=$rc  日志尾部："
        tail -3 "/tmp/smoke_$name.log" | sed 's/^/     /'
    fi
done
