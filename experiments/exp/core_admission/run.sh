#!/usr/bin/env bash
set -eo pipefail

if [[ $# != 3 ]]; then
    echo "Usage: bash $0 SIMU5G_ROOT BASELINE_RUNTIME_REPO NEW_RESULTS_DIR" >&2
    exit 2
fi
here="$(cd "$(dirname "$0")" && pwd)"
exp="$(cd "$here/.." && pwd)"
sim="$(realpath "$1")"
deps="$(realpath "$2")"
out="$(realpath -m "$3")"
seed_count="${SEED_COUNT:-5}"
[[ "$seed_count" =~ ^[1-9][0-9]*$ ]]

DL_DISCIPLINE=PF TARGET_UE=0 BUILD_GCC_ONLY=1 bash "$exp/dual_ue/run.sh" "$sim" "$deps" "$out"
source "$deps/omnetpp-6.4.0/setenv" -q
export LD_LIBRARY_PATH="$deps/../conda-envs/nasctime/lib:$deps/omnetpp-6.4.0/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export INET_ROOT="$deps/inet" SIMU5G_ROOT="$sim"
cd "$exp"

printf 'case\tseed\tradio\twired\tpath\tbands\tconfig\tvideo_packets\tonline\n' > "$out/cases.tsv"
pid=
trap 'if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi' EXIT
run_case() {
    local name="$1" seed="$2" radio="$3" wired="$4" path="$5" bands="$6" config="$7"
    local video_packets="${8:-300}" online="${9:-0}"
    local result="$out/$name-$seed"
    local -a overrides=()
    mkdir "$result"
    if [[ "$online" == 1 ]]; then
        python3 -B ladder_controller.py --policy core_admission.policy:choose \
            --port 0 --port-file "$result/port" > "$result/controller.log" 2>&1 &
        pid=$!
        for ((attempt=0; attempt<100; ++attempt)); do
            [[ -s "$result/port" ]] && break
            kill -0 "$pid" 2>/dev/null || break
            sleep .05
        done
        if [[ ! -s "$result/port" ]]; then
            cat "$result/controller.log" >&2
            return 1
        fi
        overrides+=("--*.routeController.requireController=true" "--*.routeController.port=$(cat "$result/port")")
    fi
    "$sim/bin/simu5g" -n "$out/ned" -l "$out/build/dualue" -f "$here/core_admission.ini" \
        -u Cmdenv -c "$config" -r 0 "--seed-set=$seed" "--result-dir=$result" \
        "${overrides[@]}" > "$result/run.log" 2>&1 || { tail -40 "$result/run.log" >&2; return 1; }
    if [[ -n "$pid" ]]; then
        wait "$pid"
        pid=
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$name" "$seed" "$radio" "$wired" "$path" "$bands" "$config" "$video_packets" "$online" >> "$out/cases.tsv"
    echo "Finished $name seed $seed"
}

for ((seed=0; seed<seed_count; ++seed)); do
    run_case normal          "$seed" 0 0 direct 4  AdmissionNormal
    run_case radio           "$seed" 1 0 direct 4  AdmissionRadio
    run_case wired           "$seed" 0 1 direct 4  AdmissionWired
    run_case radio_wired     "$seed" 1 1 direct 4  AdmissionReference
    run_case core            "$seed" 0 0 direct 4  AdmissionCore
    run_case radio_core      "$seed" 1 0 direct 4  AdmissionRadioCore
    run_case wired_core      "$seed" 0 1 direct 4  AdmissionWiredCore
    run_case all             "$seed" 1 1 direct 4  AdmissionAll
    run_case all_detour      "$seed" 1 1 detour 4  AdmissionAllDetour
    run_case all_detour_10   "$seed" 1 1 detour 10 AdmissionAllDetourBands
    run_case staggered       "$seed" 1 1 direct 4  AdmissionStaggered
    run_case low_offer       "$seed" 0 0 direct 4  AdmissionLowOffer 60
    run_case policy_limit    "$seed" 0 0 direct 4  AdmissionPolicyLimited
done
run_case core_cmd 0 0 0 direct 4 AdmissionCore 300 1
python3 -B "$here/extract.py" "$out"
echo "Results: $out"