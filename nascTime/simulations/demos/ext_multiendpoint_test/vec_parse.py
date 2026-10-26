#!/usr/bin/env python3
"""
vec_parse.py — Direct parser for OMNeT++ .vec files.

Replaces the scavetool-based vec_stats() in parse_results.py.
The .vec file format is text-based, so we can parse it directly
without needing the scavetool binary.

Format:
    version 2
    run <run_id>
    attr <key> <value>
    ...
    vector <id> <moduleFullPath> <vectorName> <type>
    attr <key> <value>       (per-vector attributes)
    <id> <eventNum> <simTime> <value>          (ETV format)
    <id> <simTime> <value>                     (TV format)

Example vector declaration line:
    vector 0 ExtendedMultiEndpointNetwork.tsnDeviceB[0].app[0] endToEndDelay:vector ETV

Example data line (ETV):
    0 12345 5.003421 0.003421
"""

from __future__ import annotations
import math
import signal
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
from pathlib import Path


def percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile for q in [0,1]."""
    if not sorted_vals:
        raise ValueError("empty input")
    if q <= 0:
        return sorted_vals[0]
    if q >= 1:
        return sorted_vals[-1]

    pos = (len(sorted_vals) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def parse_vec_file(vec_path: Path) -> dict:
    """
    Parse a .vec file and return a dict mapping vector_id -> dict with:
        'module': str
        'name': str
        'type': str ('TV' or 'ETV' etc)
        'values': list[float]

    The values list only includes the value column (not time).
    """
    vectors = {}  # id -> {module, name, type, values}

    with vec_path.open("r") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line[0] == "#":
                continue

            # Vector declaration: "vector <id> <module> <name> <type>"
            if line.startswith("vector "):
                parts = line.split(None, 4)
                # parts: ["vector", id, module, name, type]
                if len(parts) >= 5:
                    vec_id = parts[1]
                    vectors[vec_id] = {
                        "module": parts[2],
                        "name": parts[3],
                        "type": parts[4].strip(),
                        "values": [],
                    }
                continue

            # Data line: first token is a vector id (integer)
            # Format depends on the vector type declared earlier.
            # ETV: "<id> <eventNum> <simTime> <value>"
            # TV:  "<id> <simTime> <value>"
            first_char = line[0]
            if not (first_char.isdigit()):
                # attr lines, run lines, etc.
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            vec_id = parts[0]
            if vec_id not in vectors:
                continue

            vtype = vectors[vec_id]["type"]
            try:
                if vtype == "ETV" and len(parts) >= 4:
                    # id eventNum simTime value
                    value = float(parts[3])
                elif vtype == "TV" and len(parts) >= 3:
                    # id simTime value
                    value = float(parts[2])
                else:
                    # Unknown type — try last column
                    value = float(parts[-1])
            except (ValueError, IndexError):
                continue

            vectors[vec_id]["values"].append(value)

    return vectors


def vec_stats(vec_path: Path, module: str, name: str) -> dict:
    """
    Extract statistics for a single (module, name) vector from a .vec file.
    Returns dict with 'mean', 'p99', 'p999', 'max' keys.
    Returns {} if the vector is not found or has no values.
    """
    if not vec_path.exists():
        return {}

    vectors = parse_vec_file(vec_path)

    # Find the matching vector
    target_vec_name = name if ":vector" in name else f"{name}:vector"
    values = None
    for vec_id, vec in vectors.items():
        if vec["module"] == module and vec["name"] == target_vec_name:
            values = vec["values"]
            break

    if not values:
        return {}

    values.sort()
    return {
        "mean": sum(values) / len(values),
        "p99": percentile(values, 0.99),
        "p999": percentile(values, 0.999),
        "max": values[-1],
        "count": len(values),
    }


# ----------------------------------------------------------------------------
# Standalone test mode
# ----------------------------------------------------------------------------
def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: vec_parse.py <vec_file> [module] [name]", file=sys.stderr)
        sys.exit(1)

    vec_path = Path(sys.argv[1])

    if len(sys.argv) >= 4:
        # Extract stats for one specific vector
        module = sys.argv[2]
        name = sys.argv[3]
        stats = vec_stats(vec_path, module, name)
        print(f"Stats for {module} / {name}:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    else:
        # List all vectors in the file
        vectors = parse_vec_file(vec_path)
        print(f"Found {len(vectors)} vectors in {vec_path}")
        for vec_id, vec in sorted(vectors.items(), key=lambda x: int(x[0])):
            print(f"  id={vec_id} type={vec['type']} samples={len(vec['values'])}")
            print(f"    module: {vec['module']}")
            print(f"    name:   {vec['name']}")


if __name__ == "__main__":
    main()