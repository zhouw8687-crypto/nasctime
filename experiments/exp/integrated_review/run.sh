#!/usr/bin/env bash
set -eo pipefail
if [[ $# -lt 3 || $# -gt 4 ]]; then
    echo "Usage: bash $0 SIMU5G_ROOT BASELINE_RUNTIME_REPO NEW_RESULTS_DIR [ue0|cell]" >&2
    exit 2
fi
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
seed_count=${SEED_COUNT:-5}
[[ "$seed_count" =~ ^[1-9][0-9]*$ ]]
read -r -a disciplines <<< "${DL_DISCIPLINES:-MAXCI PF}"
read -r -a modes <<< "${REPORT_MODES:-exact round8 boundary_periodic boundary}"
delay=${REPORT_DELAY_MS:-0}
ttl=${REPORT_TTL_MS:-40}
refresh=${REPORT_REFRESH_MS:-40}
controller_python=${REPORT_PYTHON:-python3}
startup_attempts=${REPORT_STARTUP_ATTEMPTS:-100}
[[ "$startup_attempts" =~ ^[1-9][0-9]*$ ]]
[[ "$delay" =~ ^[0-9]+$ && "$ttl" =~ ^[1-9][0-9]*$ && "$refresh" =~ ^[1-9][0-9]*$ ]]
for discipline in "${disciplines[@]}"; do
    case "$discipline" in MAXCI|PF) ;; *) echo "Unknown discipline: $discipline" >&2; exit 2;; esac
done
for mode in "${modes[@]}"; do
    case "$mode" in exact|round8|boundary_periodic|boundary) ;;
        *) echo "Unknown report mode: $mode" >&2; exit 2;;
    esac
done
codec_args=()
if [[ -n "${REPORT_CODEC_FACTORY:-}" ]]; then
    codec_args+=(--codec-factory "$REPORT_CODEC_FACTORY")
fi
DL_DISCIPLINE="${disciplines[0]}" BUILD_GCC_ONLY=1 bash "$exp/dual_ue/run.sh" "$sim" "$deps" "$out"
echo "$scope" > "$out/backlog_scope.txt"
source "$deps/omnetpp-6.4.0/setenv" -q
export LD_LIBRARY_PATH="$deps/../conda-envs/nasctime/lib:$deps/omnetpp-6.4.0/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export INET_ROOT="$deps/inet" SIMU5G_ROOT="$sim"
cd "$exp"
pid=
trap 'if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi' EXIT
for discipline in "${disciplines[@]}"; do
    for ((seed=0; seed<seed_count; ++seed)); do
        for mode in "${modes[@]}"; do
            case_dir="$out/$discipline-$seed-$mode"
            mkdir "$case_dir"
            "$controller_python" -B -m integrated_review.policy "$mode" "$case_dir" \
                --delay-ms "$delay" --ttl-ms "$ttl" --refresh-ms "$refresh" \
                "${codec_args[@]}" > "$case_dir/controller.log" 2>&1 &
            pid=$!
            for ((i=0; i<startup_attempts; ++i)); do
                [[ -s "$case_dir/port" ]] && break
                kill -0 "$pid" || break
                sleep .05
            done
            if [[ ! -s "$case_dir/port" ]]; then
                cat "$case_dir/controller.log" >&2
                exit 1
            fi
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
