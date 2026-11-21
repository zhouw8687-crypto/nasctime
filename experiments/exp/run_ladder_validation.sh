#!/usr/bin/env bash
# Reproduce the routed ladder validation on A100 with fresh result directories.
set -eo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
source "$repo/omnetpp-6.4.0/setenv"
export LD_LIBRARY_PATH="/media/a100/data/zbw/conda-envs/nasctime/lib:$repo/omnetpp-6.4.0/lib"
export INET_ROOT="$repo/inet" SIMU5G_ROOT="$repo/Simu5G"
set -u
ulimit -c 0

root=$(mktemp -d "${TMPDIR:-/tmp}/ladder-validation.XXXXXX")
echo "Results: $root"
cd "$repo/nascTime/simulations/demos/e2e_ladder"
git -C "$repo" rev-parse HEAD > "$root/revision.txt"
git -C "$repo" status --porcelain >> "$root/revision.txt"

run_case() {
    local ini=$1 configuration=$2 output=$3
    shift 3
    mkdir "$root/$output"
    if ! ../../../bin/nasctime-run.sh -f "$ini" -u Cmdenv -c "$configuration" -r 0 \
        --result-dir="$root/$output" "$@" > "$root/$output/run.log" 2>&1; then
        tail -40 "$root/$output/run.log"
        return 1
    fi
    echo "Finished $output"
}

report() {
    local name=$1
    shift
    python3 "$repo/experiments/exp/ladder_kpis.py" "$root/$name/"*.vec "$@" > "$root/$name/flows.csv"
}

report_gates() {
    local name=$1
    python3 "$repo/experiments/exp/ladder_kpis.py" "$root/$name/"*.vec --gates > "$root/$name/gates.csv"
}

run_case omnetpp_transport.ini T0CrossLinks T0CrossLinks
for frame in 64 128 512 1024 1518; do
    for load in 30 80; do
        name="T1_${frame}_${load}"
        interval=$(python3 -c 'import sys; frame, load = map(int, sys.argv[1:]); print((frame + 20) * 8 / load)' "$frame" "$load")
        run_case omnetpp_transport.ini T1Single "$name" \
            "--*.access*.app[0].messageLength=$((frame - 46))B" \
            "--*.access*.app[0].sendInterval=${interval}us"
        report "$name" --start .2
    done
done

for name in T2Fifo T2Priority T2Tas T2TasPhase T2TasStaggered T2PhaseLockedPriority T2PhaseLockedTas; do
    run_case omnetpp_transport.ini "$name" "$name"
    if [[ "$name" == T2TasPhase ]]; then
        report "$name" --start .2005 --stop 1.7005
    else
        report "$name" --start .2
    fi
done

for name in T3Burst T3OverloadFifo T3OverloadPriority T3OverloadTas T3ExpansionFixed T3Expansion T3LinkErrors; do
    run_case omnetpp_transport.ini "$name" "$name"
    report "$name" --start .2 --cut .6 --cut 1.1
done
run_case omnetpp_transport.ini T4Soak T4Soak
report T4Soak --start .2 --stop 29.7

for name in E2ePriority E2eTas E2eZeroOuterDscp E2eMixedLoad; do
    run_case omnetpp_qos.ini "$name" "$name"
    report "$name"
done
for name in T2Tas T2TasPhase T2TasStaggered T2PhaseLockedTas T3ExpansionFixed T3Expansion E2eTas; do
    report_gates "$name"
done
run_case omnetpp.ini General Legacy --sim-time-limit=2s \
    '--*.ue[*].app[0].startTime=50ms' '--*.server.app[2..3].startTime=50ms'
