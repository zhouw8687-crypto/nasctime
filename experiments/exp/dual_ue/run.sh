#!/usr/bin/env bash
set -eo pipefail

if [[ $# != 3 ]]; then
    echo "Usage: bash $0 SIMU5G_ROOT BASELINE_RUNTIME_REPO NEW_RESULTS_DIR" >&2
    exit 2
fi

scenario="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$scenario/../../.." && pwd)"
SIMU5G_ROOT="$(cd "$1" && pwd)"
runtime="$(cd "$2" && pwd)"
mkdir "$3"
out="$(cd "$3" && pwd)"
source "$runtime/omnetpp-6.4.0/setenv" -q
export LD_LIBRARY_PATH="$runtime/../conda-envs/nasctime/lib:$runtime/omnetpp-6.4.0/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export INET_ROOT="$runtime/inet" SIMU5G_ROOT
ulimit -c 0

discipline="${DL_DISCIPLINE:-MAXCI}"
case "$discipline" in MAXCI|PF) ;; *) echo "Expected MAXCI or PF" >&2; exit 2;; esac
seed_count="${SEED_COUNT:-5}"
[[ "$seed_count" =~ ^[1-9][0-9]*$ ]]

{
    printf 'experiment_commit='
    git -C "$repo" rev-parse HEAD
    printf 'simu5g_commit='
    git -C "$SIMU5G_ROOT" rev-parse HEAD
    printf 'simu5g_diff_sha256='
    git -C "$SIMU5G_ROOT" diff HEAD --binary | sha256sum
    printf 'runtime=%s\n' "$runtime"
    printf 'simu5g=%s\n' "$SIMU5G_ROOT"
    printf 'dl_discipline=%s\n' "$discipline"
    printf 'seed_count=%s\n' "$seed_count"
} > "$out/environment.txt"

build="$out/build"
network="$out/ned/nasctime/simulations/demos/e2e_ladder"
marker="$out/ned/nasctime/qos"
control="$out/ned/nasctime/control"
mkdir -p "$build" "$network" "$marker" "$control"
cp "$repo/nascTime/simulations/demos/e2e_ladder/"{ProjectBookLadder,LadderBackbone}.ned "$network/"
cp "$repo/experiments/exp/"{Qfi17Ladder,Qfi17ControlledLadder}.ned "$network/"
cp "$repo/nascTime/src/nasctime/qos/DscpToPcpMarker.ned" "$marker/"
cp "$repo/nascTime/src/nasctime/control/"{ControlledDlScheduler,FlowPolicer}.ned "$control/"
cp "$scenario/DualUeRadio.ned" "$control/"
cp "$repo/nascTime/src/nasctime/control/"{ControlledDlScheduler,FlowPolicer}.cc "$build/"
cp "$scenario/DualUeRadio.cc" "$build/"
if [[ "${BUILD_GCC_ONLY:-0}" == 1 ]]; then
    target=()
    if [[ -n "${TARGET_UE:-}" ]]; then target+=(--target-ue "$TARGET_UE"); fi
    if [[ "${PREFIX_WITNESS:-0}" == 1 ]]; then target+=(--prefix-witness); fi
    python3 -B "$repo/experiments/exp/domain_coordination/augment_bridge.py" "${target[@]}" \
        "$repo/experiments/exp/RouteController.cc" "$build/RouteController.cc"
else
    cp "$repo/experiments/exp/RouteController.cc" "$build/"
fi
(
    cd "$build"
    opp_makemake --make-so -f -o dualue -I"$INET_ROOT/src" -I"$repo/nascTime/src" \
        -I"$SIMU5G_ROOT/src" -DINET_IMPORT -DSIMU5G_IMPORT \
        -L"$INET_ROOT/src" -L"$SIMU5G_ROOT/src" -lINET -lsimu5g
    make -j4
) > "$out/build.log" 2>&1 || { tail -40 "$out/build.log" >&2; exit 1; }

if [[ "${BUILD_GCC_ONLY:-0}" == 1 ]]; then exit 0; fi
cd "$repo"
printf 'case\tseed\tradio\twired\tpath\tbands\n' > "$out/cases.tsv"
run_case() {
    local name="$1" seed="$2" radio="$3" wired="$4" path="$5" bands="$6"
    local result="$out/$name-$seed"
    local -a overrides=()
    if [[ "$radio" == 0 ]]; then
        overrides+=("--*.gnb1.app[0].startTime=5s" "--*.gnb1.app[0].stopTime=6s")
    fi
    if [[ "$wired" == 0 ]]; then
        overrides+=("--*.NE1.app[0].startTime=5s" "--*.NE1.app[0].stopTime=6s")
    fi
    mkdir "$result"
    "$SIMU5G_ROOT/bin/simu5g" -n "$out/ned" -l "$build/dualue" \
        -f "$scenario/dual_ue.ini" -u Cmdenv -c DualUe -r 0 \
        "--*.gnb1.cellularNic.mac.schedulingDisciplineDl=\"$discipline\"" \
        "--seed-set=$seed" "--result-dir=$result" "--*.routeController.initialPath=\"$path\"" \
        "--*.gnb1.cellularNic.mac.schedulerDl.initialBandBudget=$bands" \
        "${overrides[@]}" > "$result/run.log" 2>&1 || { tail -40 "$result/run.log" >&2; exit 1; }
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$seed" "$radio" "$wired" "$path" "$bands" >> "$out/cases.tsv"
    echo "Finished $name seed $seed"
}

for ((seed=0; seed<seed_count; seed++)); do
    run_case normal        "$seed" 0 0 direct 4
    run_case radio         "$seed" 1 0 direct 4
    run_case wired         "$seed" 0 1 direct 4
    run_case both          "$seed" 1 1 direct 4
    run_case radio_bands   "$seed" 1 0 direct 10
    run_case wired_detour  "$seed" 0 1 detour 4
    run_case both_bands    "$seed" 1 1 direct 10
    run_case both_detour   "$seed" 1 1 detour 4
    run_case both_actions  "$seed" 1 1 detour 10
done
python3 -B "$scenario/extract.py" "$out"
echo "Results: $out"
