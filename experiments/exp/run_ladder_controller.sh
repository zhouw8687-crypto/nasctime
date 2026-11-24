#!/usr/bin/env bash
# A100, with the existing OMNeT++/INET/Simu5G environment.
set -eo pipefail
case "${1:-}" in
    "")
        ini=omnetpp_controller.ini
        builtin=upf
        configs=(ControllerBaseline ControllerStaticCap ControllerExternal ControllerExternalShifted)
        summary=ladder_control_kpis.py
        ;;
    --cross-domain)
        ini=omnetpp_cross_domain.ini
        builtin=cross-domain
        configs=(CrossDomainFixedNominal CrossDomainFixedProtect CrossDomainExternal CrossDomainExternalShifted)
        summary=ladder_cross_domain_kpis.py
        ;;
    *)
        echo "Usage: $0 [--cross-domain]" >&2
        exit 2
        ;;
esac
repo="$(cd "$(dirname "$0")/../.." && pwd)"
source "$repo/omnetpp-6.4.0/setenv"
export LD_LIBRARY_PATH="$repo/../conda-envs/nasctime/lib:$repo/omnetpp-6.4.0/lib"
export INET_ROOT="$repo/inet" SIMU5G_ROOT="$repo/Simu5G"
ulimit -c 0
results=$(mktemp -d "${TMPDIR:-/tmp}/ladder-controller.XXXXXX")
echo "Results: $results"
git -C "$repo" rev-parse HEAD >"$results/revision.txt"
git -C "$repo" status --porcelain >>"$results/revision.txt"
cd "$repo/nascTime/simulations/demos/e2e_ladder"

controller_pid=
stop_controller() {
    if [[ -n "$controller_pid" ]]; then
        kill "$controller_pid" 2>/dev/null || true
        wait "$controller_pid" 2>/dev/null || true
    fi
}
trap stop_controller EXIT

for config in "${configs[@]}"; do
    output="$results/$config"
    mkdir "$output"
    launch=(../../../bin/nasctime-run.sh -f "$ini" -u Cmdenv
            -c "$config" -r 0 "--result-dir=$output")
    if [[ "$config" == *External* ]]; then
        python3 -B "$repo/experiments/exp/ladder_controller.py" \
            --builtin "$builtin" --port 0 --port-file "$output/controller.port" >"$output/controller.log" 2>&1 &
        controller_pid=$!
        port=
        for ((attempt=0; attempt<100; attempt++)); do
            if [[ -f "$output/controller.port" ]] && read -r port < "$output/controller.port"; then
                break
            fi
            if ! kill -0 "$controller_pid" 2>/dev/null; then
                break
            fi
            sleep .05
        done
        if [[ ! "$port" =~ ^[1-9][0-9]*$ ]]; then
            cat "$output/controller.log" >&2
            echo "The local controller did not open a port" >&2
            exit 1
        fi
        launch+=("--*.controller.port=$port")
    fi
    if ! "${launch[@]}" >"$output/run.log" 2>&1; then
        tail -40 "$output/run.log" >&2
        exit 1
    fi
    if [[ -n "$controller_pid" ]]; then
        if ! wait "$controller_pid"; then
            controller_pid=
            cat "$output/controller.log" >&2
            exit 1
        fi
        controller_pid=
    fi
    if [[ "$config" == *ExternalShifted ]]; then
        python3 -B "$repo/experiments/exp/competition_trace.py" "$output" --burst-start .8 --burst-stop 1.2
    else
        python3 -B "$repo/experiments/exp/competition_trace.py" "$output"
    fi
done
python3 -B "$repo/experiments/exp/$summary" "$results" >"$results/control-kpis.csv"
cat "$results/control-kpis.csv"
