#!/usr/bin/env bash
# Integration smoke on an already-seen trajectory, independent of held-out label scoring.
set -euo pipefail
if [[ $# != 5 ]]; then
    echo "Usage: bash $0 SIMU5G_ROOT RUNTIME_REPO ARTIFACT_ROOT NEW_RESULTS_DIR CONTROLLER_PYTHON" >&2
    exit 2
fi
here=$(cd "$(dirname "$0")" && pwd)
exp=$(cd "$here/.." && pwd)
base=$(realpath "$3")
out=$(realpath -m "$4")
mkdir "$out"
export DL_DISCIPLINES=PF SEED_COUNT=1 REPORT_MODES=exact
export REPORT_DELAY_MS=0 REPORT_TTL_MS=40 REPORT_REFRESH_MS=40
export REPORT_PYTHON="$5" REPORT_STARTUP_ATTEMPTS=1200
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
for kind in full fixed boundary mlp lora; do
    export SEMANTIC_CODEC_DIR="$base/$kind-smoke"
    case "$kind" in
        full) unset REPORT_CODEC_FACTORY ;;
        fixed|boundary) export REPORT_CODEC_FACTORY="semantic_uplink.formats:make_$kind" ;;
        mlp|lora) export REPORT_CODEC_FACTORY=semantic_uplink.learned:make_learned ;;
    esac
    bash "$exp/integrated_review/run.sh" "$1" "$2" "$out/$kind" ue0 > "$out/$kind.log" 2>&1 ||
        { tail -30 "$out/$kind.log"; exit 1; }
    (cd "$exp" && python3 -B -m integrated_review.summarize "$out/$kind") > "$out/$kind.csv"
done
