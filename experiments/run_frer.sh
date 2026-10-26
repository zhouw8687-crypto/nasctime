#!/bin/bash
# FRER 完整实验批次（自包含环境，避免 conda activate 后台挂起）
set -uo pipefail

export PATH=/media/a100/data/zbw/conda-envs/nasctime/bin:/media/a100/data/zbw/conda-envs/nasctime/lib/qt6:/media/a100/data/zbw/nasctime/omnetpp-6.4.0/bin:/media/a100/data/zbw/nasctime/nascTime/bin:$PATH
export LD_LIBRARY_PATH=/media/a100/data/zbw/conda-envs/nasctime/lib:$LD_LIBRARY_PATH
export INET_ROOT=/media/a100/data/zbw/nasctime/inet
export SIMU5G_ROOT=/media/a100/data/zbw/nasctime/Simu5G
export NASCTIME_ROOT=/media/a100/data/zbw/nasctime/nascTime

EXP=/media/a100/data/zbw/nasctime/experiments
RESULT_DIR=$EXP/results/frer
mkdir -p "$RESULT_DIR"

cd /media/a100/data/zbw/nasctime/nascTime/simulations/demos/frer_test

CONFIGS="FrerBaseline_N15 FrerAsym_N15 FrerSym_N15"
SYNC=('--*.tsnDeviceA.gptp.syncInterval=4s' '--*.tsnDeviceB[*].gptp.syncInterval=4s')

for cfg in $CONFIGS; do
  echo "===== $cfg (10s x 20 runs) ====="
  ../../../bin/nasctime-run.sh -f frer_sweep.ini -c "$cfg" -u Cmdenv \
    "${SYNC[@]}" --cmdenv-stop-batch-on-error=false --result-dir="$RESULT_DIR" \
    > "$EXP/log_${cfg}.log" 2>&1 || { echo "FAILED: $cfg (see $EXP/log_${cfg}.log)"; continue; }
  tail -2 "$EXP/log_${cfg}.log"
done
echo "ALL DONE"
