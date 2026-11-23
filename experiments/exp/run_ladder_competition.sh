#!/usr/bin/env bash
# A100. Keep the four result directories together for paired comparisons.
set -eo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
source "$repo/omnetpp-6.4.0/setenv"
export LD_LIBRARY_PATH="$repo/../conda-envs/nasctime/lib:$repo/omnetpp-6.4.0/lib"
export INET_ROOT="$repo/inet" SIMU5G_ROOT="$repo/Simu5G"
ulimit -c 0
results=$(mktemp -d "${TMPDIR:-/tmp}/ladder-competition.XXXXXX")
echo "Results: $results"
git -C "$repo" rev-parse HEAD >"$results/revision.txt"
git -C "$repo" status --porcelain >>"$results/revision.txt"
cd "$repo/nascTime/simulations/demos/e2e_ladder"
for mode in CompetitionNoBurst CompetitionFifo CompetitionPriority CompetitionTas; do
    output="$results/$mode"
    mkdir "$output"
    if ! ../../../bin/nasctime-run.sh -f omnetpp_competition.ini -u Cmdenv \
        -c "$mode" -r 0 --result-dir="$output" >"$output/run.log" 2>&1; then
        tail -40 "$output/run.log" >&2
        exit 1
    fi
    python3 -B "$repo/experiments/exp/competition_trace.py" "$output"
    printf '%s\n' "$mode"
    awk -F, 'NR==1 || $3=="phase_2"' "$output/flows.csv"
done
python3 "$repo/experiments/exp/ladder_kpis.py" "$results/CompetitionTas/"*.vec --gates \
    >"$results/CompetitionTas/gates.csv"
