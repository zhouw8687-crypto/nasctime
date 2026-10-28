#!/usr/bin/env python3
"""通用直方图摘要：从 .sca 里按关键字筛 statistic，输出 count/mean/p50/p99/min/max。

用法：hist_summary.py <sca 文件> [关键字正则，默认 '.']

用于读取 INET FlowMeasurement 产生的 <flow>:<stat>:histogram 统计。
分位数由分桶线性插值（OMNeT++ 直方图分桶，lower + count）。
"""
import re
import sys
from collections import defaultdict

RE_STAT = re.compile(r"^statistic\s+(\S+)\s+(\S+):histogram\s*$")
RE_FIELD = re.compile(r"^field\s+(\S+)\s+(\S+)\s*$")
RE_BIN = re.compile(r"^bin\s+(\S+)\s+(\S+)")


def percentile(h, p):
    bins = sorted([(lo, c) for lo, c in h["bins"] if c > 0], key=lambda x: x[0])
    total = h.get("count", 0.0)
    if not bins or total <= 0:
        return None
    rank = p * total
    cum = 0.0
    for i, (lo, c) in enumerate(bins):
        if cum + c >= rank:
            upper = bins[i + 1][0] if i + 1 < len(bins) else h.get("max", lo)
            if lo == float("-inf"):
                lo = h.get("min", upper)
                upper = bins[i + 1][0] if i + 1 < len(bins) else h.get("max", upper)
            frac = (rank - cum) / c
            return lo + frac * (upper - lo)
        cum += c
    return h.get("max")


def parse(path):
    hists = {}
    cur = None
    pending = None

    def flush():
        nonlocal pending
        if cur is not None and pending is not None:
            hists[cur]["bins"].append(pending)
        pending = None

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = RE_STAT.match(line)
            if m:
                flush()
                cur = f"{m.group(1)}|{m.group(2)}"
                hists.setdefault(cur, {"bins": []})
                continue
            m = RE_FIELD.match(line)
            if m and cur:
                try:
                    hists[cur][m.group(1)] = float(m.group(2))
                except ValueError:
                    pass
                continue
            m = RE_BIN.match(line)
            if m and cur:
                flush()
                try:
                    lo = float(m.group(1))
                except ValueError:
                    lo = float("-inf")
                try:
                    cnt = float(m.group(2))
                except ValueError:
                    cnt = 0.0
                pending = (lo, cnt)
                continue
            if line and not line[0].isspace() and line.split()[0] in (
                "par", "run", "config", "version"
            ):
                flush()
                cur = None
    flush()
    return hists


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sca = sys.argv[1]
    pat = re.compile(sys.argv[2] if len(sys.argv) > 2 else ".")

    rows = []
    for key, h in parse(sca).items():
        mod, name = key.split("|", 1)
        if not pat.search(name):
            continue
        if not h.get("count"):
            continue
        rows.append((name, mod, h))

    print(f"| 统计 | 样本 | mean | p50 | p99 | max | stddev |")
    print("|---|---|---|---|---|---|---|")
    for name, mod, h in sorted(rows, key=lambda r: r[0]):
        n = h.get("count", 0)
        mean = h.get("mean", h.get("sum", 0) / n if n else 0)
        sd = h.get("stddev", 0)
        short = mod.replace("RingMultipathShowcase.", "")
        print(
            f"| {name} @ {short} | {n:.0f} | {mean*1e6:.2f} µs | "
            f"{(percentile(h,0.50) or 0)*1e6:.2f} µs | {(percentile(h,0.99) or 0)*1e6:.2f} µs | "
            f"{h.get('max',0)*1e6:.2f} µs | {sd*1e6:.2f} µs |"
        )


if __name__ == "__main__":
    main()
