#!/usr/bin/env bash
set -eo pipefail
here=$(cd "$(dirname "$0")" && pwd)
exp=$(cd "$here/.." && pwd)
sim=$(realpath "$1")
deps=$(realpath "$2")
out=$(realpath -m "$3")
scope="${4:-ue0}"
case "$scope" in
    ue0) export TARGET_UE=0 ;;
    cell) unset TARGET_UE ;;
    *) echo "Use ue0 or cell for backlog scope" >&2; exit 2 ;;
esac
BUILD_GCC_ONLY=1 bash "$exp/dual_ue/run.sh" "$sim" "$deps" "$out"
echo "$scope" > "$out/backlog_scope.txt"
source "$deps/omnetpp-6.4.0/setenv" -q
export LD_LIBRARY_PATH="$deps/../conda-envs/nasctime/lib:$deps/omnetpp-6.4.0/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export INET_ROOT="$deps/inet" SIMU5G_ROOT="$sim"
cd "$exp"
pid=
trap 'if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi' EXIT
for discipline in MAXCI PF; do
    for seed in 0 1 2 3 4; do
        for mode in exact round8 boundary_periodic boundary; do
            case_dir="$out/$discipline-$seed-$mode"
            mkdir "$case_dir"
            python3 -B -m integrated_review.policy "$mode" "$case_dir" > "$case_dir/controller.log" 2>&1 &
            pid=$!
            for ((i=0; i<100; ++i)); do
                [[ -s "$case_dir/port" ]] && break
                kill -0 "$pid" || break
                sleep .05
            done
            "$sim/bin/simu5g" -n "$out/ned" -l "$out/build/dualue" \
                -f dual_ue/dual_ue.ini -u Cmdenv -c DualUe -r 0 \
                "--seed-set=$seed" "--result-dir=$case_dir" \
                "--*.gnb1.cellularNic.mac.schedulingDisciplineDl=\"$discipline\"" \
                '--*.routeController.requireController=true' '--*.routeController.manageResources=true' \
                "--*.routeController.port=$(cat "$case_dir/port")" \
                '--*.upf.dnPpp.ingressTC.typename="nasctime.control.FlowPolicer"' \
                '--*.upf.dnPpp.ingressTC.packetFilter=expr(has(ipv4) && has(udp) && udp.destPort == 6204)' \
                '--*.upf.dnPpp.ingressTC.flowId="video"' '--*.upf.dnPpp.ingressTC.initialRate=3Mbps' \
                > "$case_dir/run.log" 2>&1 || { tail -20 "$case_dir/"{run,controller}.log; exit 1; }
            wait "$pid"
            pid=
            echo "Finished $discipline $seed $mode"
        done
    done
done
