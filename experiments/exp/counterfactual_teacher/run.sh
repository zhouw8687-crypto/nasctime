#!/usr/bin/env bash
set -eo pipefail
if [[ $# -lt 3 ]]; then
    echo "Usage: bash $0 SIMU5G_ROOT BASELINE_RUNTIME_REPO NEW_RESULTS_DIR [matrix options]" >&2
    exit 2
fi
here=$(cd "$(dirname "$0")" && pwd)
exp=$(cd "$here/.." && pwd)
sim=$(realpath "$1")
deps=$(realpath "$2")
out=$(realpath -m "$3")
shift 3
BUILD_GCC_ONLY=1 TARGET_UE=0 PREFIX_WITNESS=1 DL_DISCIPLINE=PF \
    bash "$exp/dual_ue/run.sh" "$sim" "$deps" "$out"
source "$deps/omnetpp-6.4.0/setenv" -q
export LD_LIBRARY_PATH="$deps/../conda-envs/nasctime/lib:$deps/omnetpp-6.4.0/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export INET_ROOT="$deps/inet" SIMU5G_ROOT="$sim"
ulimit -c 0
cd "$exp"
python3 -B -m counterfactual_teacher.simulate "$sim" "$out" "$@"
python3 -B -m counterfactual_teacher.dataset "$out"
echo "Results: $out"
