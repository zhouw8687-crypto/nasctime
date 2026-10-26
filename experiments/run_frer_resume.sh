#!/bin/bash
# run_frer_resume.sh — FRER fading 批次（断点续跑 + 逐 run 进度）
# 已有 .sca 的 run 自动跳过；失败 run 打 .FAILED 标记（下次跳过）
set -uo pipefail
export PATH=/media/a100/data/zbw/conda-envs/nasctime/bin:/media/a100/data/zbw/conda-envs/nasctime/lib/qt6:/media/a100/data/zbw/nasctime/omnetpp-6.4.0/bin:/media/a100/data/zbw/nasctime/nascTime/bin:$PATH
export LD_LIBRARY_PATH=/media/a100/data/zbw/conda-envs/nasctime/lib:$LD_LIBRARY_PATH
export INET_ROOT=/media/a100/data/zbw/nasctime/inet
export SIMU5G_ROOT=/media/a100/data/zbw/nasctime/Simu5G
export NASCTIME_ROOT=/media/a100/data/zbw/nasctime/nascTime
EXP=/media/a100/data/zbw/nasctime/experiments
RESULT_DIR=$EXP/results/frer_fading
mkdir -p "$RESULT_DIR"
cd /media/a100/data/zbw/nasctime/nascTime/simulations/demos/frer_test

CONFIGS="FrerBaseline_N15 FrerAsym_N15 FrerSym_N15"
RUN_START=${RUN_START:-0}
RUN_END=${RUN_END:-19}
SYNC=('--*.tsnDeviceA.gptp.syncInterval=4s' '--*.tsnDeviceB[*].gptp.syncInterval=4s')
FADE=('--*.gnb.cellularNic.channelModel[0].fading=true' '--*.gnb.cellularNic.channelModel[0].shadowing=true' '--*.gnb.cellularNic.channelModel[0].thermalNoise=-95dBm')
TOTAL=$(( (RUN_END - RUN_START + 1) * 3 ))
i=0; ok=0; fail=0; skip=0
for cfg in $CONFIGS; do
  for rn in $(seq "$RUN_START" "$RUN_END"); do
    i=$((i+1))
    sca="$RESULT_DIR/${cfg}_run${rn}.sca"
    flg="$RESULT_DIR/${cfg}_run${rn}.FAILED"
    if [ -f "$sca" ]; then skip=$((skip+1)); continue; fi
    if [ -f "$flg" ]; then fail=$((fail+1)); continue; fi
    echo "[$i/$TOTAL] $cfg run$rn 开始 $(date +%H:%M:%S)"
    if ../../../bin/nasctime-run.sh -f frer_sweep.ini -c "$cfg" -u Cmdenv -r "$rn" \
        "${SYNC[@]}" "${FADE[@]}" --result-dir="$RESULT_DIR" \
        >> "$EXP/log_resume_${cfg}_${RUN_START}_${RUN_END}.log" 2>&1; then
      ok=$((ok+1)); echo "[$i/$TOTAL] $cfg run$rn OK   $(date +%H:%M:%S)"
    else
      fail=$((fail+1)); touch "$flg"
      echo "[$i/$TOTAL] $cfg run$rn FAILED(已标记) $(date +%H:%M:%S)"
    fi
  done
done
echo "ALL DONE: 完成$ok 失败$fail 跳过$skip (共$TOTAL)"
