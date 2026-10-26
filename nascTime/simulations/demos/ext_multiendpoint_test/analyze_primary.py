#!/usr/bin/env python3
"""
analyze_primary.py — Produces paper-ready tables from primary.csv.

Outputs:
  1. Delivery table: per (N, scheduler, flow) -> mean delivery count
  2. Delay table:    per (N, scheduler, flow) -> mean/p99/p999/max delay
  3. Deadline miss rate: per (N, scheduler, flow) -> % packets > deadline_ms
  4. Fairness metric: per (N, scheduler, flow) -> delivery std across endpoints

Usage:
  python3 analyze_primary.py primary.csv
  python3 analyze_primary.py primary.csv --out-dir tables/
"""

import argparse
import sys
from pathlib import Path

import pandas as pd


def load(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # Coerce numeric columns that may have empty strings
    for col in ["received", "delay_mean_ms", "delay_p99_ms",
                "delay_p999_ms", "delay_max_ms", "delay_samples"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def delivery_table(df: pd.DataFrame) -> pd.DataFrame:
    """Mean delivery count per (N, scheduler, flow), averaged over endpoints + reps."""
    return (df.groupby(["N", "flow", "scheduler"])["received"]
              .mean()
              .unstack("scheduler")
              .round(0))


def delay_table(df: pd.DataFrame, stat: str = "delay_mean_ms") -> pd.DataFrame:
    """Mean of a delay statistic per (N, scheduler, flow)."""
    d = df.dropna(subset=[stat])
    return (d.groupby(["N", "flow", "scheduler"])[stat]
              .mean()
              .unstack("scheduler")
              .round(2))


def deadline_miss_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Approximate P(delay > deadline) using mean delay / deadline comparison.

    This is a rough indicator — a true miss rate would need the raw samples.
    We mark a (scheduler, N, flow) cell as 'missing' if p99 > deadline:
    this means at least 1% of packets missed the deadline.
    """
    d = df.dropna(subset=["delay_p99_ms"])
    d = d.assign(p99_over_deadline=d["delay_p99_ms"] > d["deadline_ms"])
    return (d.groupby(["N", "flow", "scheduler"])["p99_over_deadline"]
              .mean()   # fraction of endpoint-reps where P99 missed
              .unstack("scheduler")
              .round(2))


def fairness_table(df: pd.DataFrame) -> pd.DataFrame:
    """Std of delivery count across endpoints within each (N, scheduler, flow, rep),
    then averaged over reps. Low std = fair delivery across endpoints."""
    # Std across endpoints within a (N, scheduler, flow, rep) cell
    by_cell = (df.groupby(["N", "scheduler", "flow", "rep"])["received"]
                 .std()
                 .reset_index())
    # Average over reps
    return (by_cell.groupby(["N", "flow", "scheduler"])["received"]
                   .mean()
                   .unstack("scheduler")
                   .round(1))


def print_section(title: str, df: pd.DataFrame) -> None:
    print()
    print("=" * len(title))
    print(title)
    print("=" * len(title))
    print(df.to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="Input primary.csv")
    ap.add_argument("--out-dir", default=None,
                    help="If set, also write each table to a .csv in this dir")
    args = ap.parse_args()

    df = load(Path(args.csv))

    # Report basic stats about the dataset
    print(f"Loaded {len(df)} rows from {args.csv}")
    print(f"  N values:        {sorted(df['N'].unique())}")
    print(f"  Schedulers:      {sorted(df['scheduler'].unique())}")
    print(f"  Flows:           {sorted(df['flow'].unique())}")
    print(f"  Rows with delay: {df['delay_mean_ms'].notna().sum()}")

    tables = {
        "delivery_mean": delivery_table(df),
        "delay_mean_ms": delay_table(df, "delay_mean_ms"),
        "delay_p99_ms":  delay_table(df, "delay_p99_ms"),
        "delay_p999_ms": delay_table(df, "delay_p999_ms"),
        "delay_max_ms":  delay_table(df, "delay_max_ms"),
        "deadline_miss_p99": deadline_miss_rate(df),
        "fairness_delivery_std": fairness_table(df),
    }

    for title, tbl in tables.items():
        print_section(title, tbl)

    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, tbl in tables.items():
            tbl.to_csv(out / f"{name}.csv")
        print(f"\nTables written to {out}/")


if __name__ == "__main__":
    main()