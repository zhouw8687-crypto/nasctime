#!/usr/bin/env bash
#
# nasctime-run — generic wrapper for running any nascTime scenario via
# opp_run, now that nascTime builds as a shared library (libnasctime.so)
# rather than a standalone executable.
#
# Unlike run_matrix.sh/smoke_test.sh (which are tied to one specific
# scenario's own logic -- profile generation, custom result parsing),
# this wrapper is scenario-agnostic: it just sets up the correct
# LD_LIBRARY_PATH and NED/library paths, then hands off every argument
# to opp_run untouched.
#
# Usage: run from inside any scenario directory (e.g. tests/bridge_test/,
# simulations/demos/frer_test/), same as the old per-scenario `run` script:
#   ../../bin/nasctime-run -f omnetpp.ini [any other opp_run args]
# or from anywhere, via an absolute/relative path to this script.
#
# Required environment (exported by sourcing each project's own setenv):
#   SIMU5G_ROOT=...   absolute path to Simu5G tree
#   INET_ROOT=...     absolute path to INET tree
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NASCTIME_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NASCTIME_SRC="$NASCTIME_ROOT/src"
NED_ROOTS="$NASCTIME_SRC:$NASCTIME_ROOT/tests:$NASCTIME_ROOT/simulations"

SIMU5G_ROOT="${SIMU5G_ROOT:-}"
if [ -z "$SIMU5G_ROOT" ] || [ ! -d "$SIMU5G_ROOT/src" ]; then
    echo "nasctime-run: SIMU5G_ROOT is not set or does not point to a Simu5G tree (source Simu5G's setenv, or pass SIMU5G_ROOT=...)" >&2
    exit 1
fi

INET_ROOT="${INET_ROOT:-}"
if [ -z "$INET_ROOT" ] || [ ! -d "$INET_ROOT/src" ]; then
    echo "nasctime-run: INET_ROOT is not set or does not point to an INET tree (source INET's setenv, or pass INET_ROOT=...)" >&2
    exit 1
fi

if [ ! -f "$NASCTIME_SRC/libnasctime.so" -a ! -f "$NASCTIME_SRC/libnasctime.dylib" ]; then
    echo "nasctime-run: libnasctime.[so|dylib] not found at $NASCTIME_SRC (build nascTime first: cd $NASCTIME_ROOT && make)" >&2
    exit 1
fi

exec opp_run -n "$NED_ROOTS:$SIMU5G_ROOT/src:$INET_ROOT/src" -l "$NASCTIME_SRC/nasctime" "$@"

