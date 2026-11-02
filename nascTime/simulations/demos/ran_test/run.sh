#!/usr/bin/env bash
# ============================================================
# ran_test 专用启动脚本
#
# 为什么要单独一个：nascTime 的通用包装 bin/nasctime-run.sh 的 NED 路径里
# 只有 $SIMU5G_ROOT/src，没有 $SIMU5G_ROOT/simulations，而本域要复用的
# SingleCell_Standalone.ned 在 simulations 下面。这里显式把两个都加上，
# 避免为了一个域去改通用脚本（域隔离）。
#
# 用法：./run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s --result-dir=results
# ============================================================
set -uo pipefail

BASE=/media/a100/data/zbw/nasctime

export PATH="$BASE/omnetpp-6.4.0/bin:$PATH"
export LD_LIBRARY_PATH="/media/a100/data/zbw/conda-envs/nasctime/lib:$BASE/omnetpp-6.4.0/lib"
export INET_ROOT="$BASE/inet"
export SIMU5G_ROOT="$BASE/Simu5G"
export NASCTIME_ROOT="$BASE/nascTime"

NED="$BASE/nascTime/src:$BASE/nascTime/tests:$BASE/nascTime/simulations:$BASE/Simu5G/src:$BASE/Simu5G/simulations:$BASE/inet/src"

exec opp_run -n "$NED" -l "$BASE/nascTime/src/nasctime" "$@"
