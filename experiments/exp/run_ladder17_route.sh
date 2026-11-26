#!/usr/bin/env bash
set -eo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: bash $0 /absolute/path/to/Simu5G-qos" >&2
    exit 2
fi
repo="$(cd "$(dirname "$0")/../.." && pwd)"
SIMU5G_ROOT="$(cd "$1" && pwd)"
source "$repo/omnetpp-6.4.0/setenv"
export LD_LIBRARY_PATH="$repo/../conda-envs/nasctime/lib:$repo/omnetpp-6.4.0/lib"
export INET_ROOT="$repo/inet" SIMU5G_ROOT
ulimit -c 0

out="$(mktemp -d)"
echo "Results: $out"
build="$out/build"
network="$out/ned/nasctime/simulations/demos/e2e_ladder"
marker="$out/ned/nasctime/qos"
control="$out/ned/nasctime/control"
mkdir -p "$build" "$network" "$marker" "$control"
cp "$repo/nascTime/simulations/demos/e2e_ladder/"{ProjectBookLadder,LadderBackbone}.ned "$network/"
cp "$repo/experiments/exp/"{Qfi17Ladder,Qfi17ControlledLadder}.ned "$network/"
cp "$repo/nascTime/src/nasctime/qos/DscpToPcpMarker.ned" "$marker/"
cp "$repo/nascTime/src/nasctime/control/"{ControlledDlScheduler,FlowPolicer}.ned "$control/"
cp "$repo/experiments/exp/RouteNrMacGnb.ned" "$control/"
cp "$repo/nascTime/src/nasctime/control/"{ControlledDlScheduler,FlowPolicer}.cc "$build/"
cp "$repo/experiments/exp/RouteController.cc" "$build/"
(
    cd "$build"
    opp_makemake --make-so -f -o routecontroller -I"$INET_ROOT/src" -I"$repo/nascTime/src" \
        -I"$SIMU5G_ROOT/src" -DINET_IMPORT -DSIMU5G_IMPORT \
        -L"$INET_ROOT/src" -L"$SIMU5G_ROOT/src" -lINET -lsimu5g
    make -j4
) > "$out/build.log" 2>&1 || { tail -40 "$out/build.log" >&2; exit 1; }

controller_pid=
stop_controller() {
    if [ -n "$controller_pid" ]; then
        kill "$controller_pid" 2>/dev/null || true
        wait "$controller_pid" 2>/dev/null || true
    fi
}
trap stop_controller EXIT

cd "$repo"
run_case() {
    local config="$1" policy="${2:-}"
    result="$out/$config"
    mkdir "$result"
    local -a override=()
    if [ "$policy" = choose_calibrated_policy ]; then
        override+=("${initial_profile[@]}")
    fi
    if [ -n "$policy" ]; then
        python3 -B experiments/exp/ladder_controller.py --policy "ladder_route_policy:$policy" \
            --port 0 --port-file "$result/port" > "$result/controller.log" 2>&1 &
        controller_pid=$!
        for ((attempt=0; attempt<100; attempt++)); do
            if [ -s "$result/port" ]; then
                break
            fi
            kill -0 "$controller_pid" 2>/dev/null || break
            sleep .05
        done
        if [ ! -s "$result/port" ]; then
            cat "$result/controller.log" >&2
            exit 1
        fi
        override+=("--*.routeController.port=$(cat "$result/port")")
    fi
    "$SIMU5G_ROOT/bin/simu5g" -n "$out/ned" -l "$build/routecontroller" \
        -f experiments/exp/simu5g17_ladder_route.ini -u Cmdenv -c "$config" -r 0 \
        "--result-dir=$result" "${override[@]}" > "$result/run.log" 2>&1 \
        || { tail -35 "$result/run.log" >&2; exit 1; }
    if [ -n "$controller_pid" ]; then
        wait "$controller_pid"
        controller_pid=
    fi
    echo "Finished $config"
}

for run in {0..7}; do
    result="$out/grid-$run"
    mkdir "$result"
    "$SIMU5G_ROOT/bin/simu5g" -n "$out/ned" -l "$build/routecontroller" \
        -f experiments/exp/simu5g17_ladder_route.ini -u Cmdenv -c LadderRouteGrid -r "$run" \
        "--result-dir=$result" > "$result/run.log" 2>&1 \
        || { tail -35 "$result/run.log" >&2; exit 1; }
done
echo "Finished 8 fixed path/resource combinations"

export LADDER_ROUTE_PROFILES="$out/profiles.json"
python3 -B experiments/exp/ladder_route_kpis.py "$out" --write-policy "$LADDER_ROUTE_PROFILES" > "$out/grid-kpis.csv"
initial_profile=()
while IFS= read -r arg; do
    initial_profile+=("$arg")
done < <(python3 - "$LADDER_ROUTE_PROFILES" <<'PROFILE'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as profile_file:
    profile = json.load(profile_file)["preburst"]["selected"]
print(f"--*.routeController.initialPath={json.dumps(profile['path_id'])}")
print(f"--*.gnb1.cellularNic.mac.schedulerDl.initialBandBudget={profile['ran_bands']}")
print(f"--*.upf.dnPpp.ingressTC.initialRate={profile['upf_video_rate_bps']}bps")
PROFILE
)
test "${#initial_profile[@]}" -eq 3
run_case LadderRouteFixedFifo
run_case LadderRouteFixed
run_case LadderRouteAdaptive choose_path
run_case LadderRouteAdaptiveShifted choose_path
run_case LadderRouteIndependent choose_path
run_case LadderRouteJoint choose_joint_policy
run_case LadderRouteJointShifted choose_joint_policy
run_case LadderRouteCalibrated choose_calibrated_policy
run_case LadderRouteCalibratedShifted choose_calibrated_policy
python3 -B experiments/exp/ladder_route_kpis.py "$out" > "$out/kpis.csv"
