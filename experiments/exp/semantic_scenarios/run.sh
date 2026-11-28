#!/usr/bin/env bash
set -eo pipefail

if [[ $# -lt 3 ]]; then
    echo "Usage: bash $0 SIMU5G_ROOT RUNTIME NEW_RESULTS_DIR [probe options]" >&2
    exit 2
fi
here="$(cd "$(dirname "$0")" && pwd)"
exp="$(cd "$here/.." && pwd)"
sim="$(realpath "$1")"
deps="$(realpath "$2")"
out="$(realpath -m "$3")"
shift 3

DL_DISCIPLINE=PF TARGET_UE=0 BUILD_GCC_ONLY=1 bash "$exp/dual_ue/run.sh" "$sim" "$deps" "$out"
source "$deps/omnetpp-6.4.0/setenv" -q
export LD_LIBRARY_PATH="$deps/../conda-envs/nasctime/lib:$deps/omnetpp-6.4.0/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export INET_ROOT="$deps/inet" SIMU5G_ROOT="$sim"
cd "$exp"
python3 -B -m semantic_scenarios.probe "$sim" "$out" "$@"
