#!/usr/bin/env bash
set -eo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: bash $0 /path/to/Simu5G-qos /path/to/original-nasctime [existing-output-parent]" >&2
    exit 2
fi
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../../.." && pwd)"
SIMU5G_ROOT="$(cd "$1" && pwd)"
deps="$(cd "$2" && pwd)"
parent="$(cd "${3:-${TMPDIR:-/tmp}}" && pwd)"
source "$deps/omnetpp-6.4.0/setenv"
export LD_LIBRARY_PATH="$deps/../conda-envs/nasctime/lib:$deps/omnetpp-6.4.0/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export INET_ROOT="$deps/inet" SIMU5G_ROOT
ulimit -c 0

out="$(mktemp -d "$parent/domain-coordination.XXXXXXXX")"
echo "Results: $out"
build="$out/build"
network="$out/ned/nasctime/simulations/demos/e2e_ladder"
marker="$out/ned/nasctime/qos"
control="$out/ned/nasctime/control"
mkdir -p "$build" "$network" "$marker" "$control"
cp "$repo/nascTime/simulations/demos/e2e_ladder/"{ProjectBookLadder,LadderBackbone}.ned "$network/"
cp "$here/../"{Qfi17Ladder,Qfi17ControlledLadder}.ned "$network/"
cp "$repo/nascTime/src/nasctime/qos/DscpToPcpMarker.ned" "$marker/"
cp "$repo/nascTime/src/nasctime/control/"{ControlledDlScheduler,FlowPolicer}.ned "$control/"
cp "$here/../RouteNrMacGnb.ned" "$control/"
cp "$repo/nascTime/src/nasctime/control/"{ControlledDlScheduler,FlowPolicer}.cc "$build/"
python3 -B "$here/augment_bridge.py" "$here/../RouteController.cc" "$build/RouteController.cc"
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

cd "$here/.."
for config in Nominal Shifted LowOffer LowOfferHighTarget; do
    video_target_bps=2000000
    if [ "$config" = LowOfferHighTarget ]; then
        video_target_bps=12000000
    fi
    for mode in full autonomous; do
        result="$out/$mode-$config"
        mkdir "$result"
        python3 -B -m domain_coordination.adapter --mode "$mode" --log "$result/policy.jsonl" \
            --port-file "$result/port" --video-target-bps "$video_target_bps" > "$result/controller.log" 2>&1 &
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
        "$SIMU5G_ROOT/bin/simu5g" -n "$out/ned" -l "$build/routecontroller" \
            -f domain_coordination/ladder.ini -u Cmdenv -c "DomainCoordination$config" -r 0 \
            "--result-dir=$result" "--*.routeController.port=$(cat "$result/port")" \
            > "$result/run.log" 2>&1 \
            || { tail -35 "$result/run.log" >&2; cat "$result/controller.log" >&2; exit 1; }
        wait "$controller_pid" || { cat "$result/controller.log" >&2; exit 1; }
        controller_pid=
        echo "Finished $mode-$config"
    done
done
python3 -B ladder_route_kpis.py "$out" > "$out/kpis.csv"
python3 -B -m domain_coordination.verify "$out" > "$out/verification.json"
