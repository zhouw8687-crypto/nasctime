#!/usr/bin/env python3
"""从 OMNeT++ .sca 提取最小 KPI 表：送达率、端到端时延分位数、5GS 驻留时间。

用法：python3 experiments/exp/kpi_table.py <结果目录或 .sca 路径>

只读 .sca，不需要 .vec —— INET 的 endToEndDelay / residenceTime 以 histogram
形式写入 .sca（含 count/mean/stddev/min/max 与分桶），分位数由分桶插值得到。

注意：.sca 的文件格式是 "关键字 空格分隔"，但 scalar 的名字可能带引号和空格，
       所以不能用 split() 硬切，必须用正则。
"""
import csv
import os
import re
import sys
from collections import defaultdict

RE_SCALAR = re.compile(r"^scalar\s+(\S+)\s+(.+?)\s+(\S+)\s*$")
RE_STAT = re.compile(r"^statistic\s+(\S+)\s+(\S+)\s*$")
RE_FIELD = re.compile(r"^field\s+(\S+)\s+(\S+)\s*$")
RE_BIN = re.compile(r"^bin\s+(\S+)\s+(\S+)")


def parse_sca(path):
    scalars = defaultdict(dict)
    hist = defaultdict(dict)
    cur = None
    pending = None   # (lower, count) 待提交的 bin

    def flush():
        nonlocal pending
        if cur is not None and pending is not None:
            hist[cur[0]][cur[1]]["bins"].append(pending)
        pending = None

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue

            m = RE_SCALAR.match(line)
            if m:
                flush(); cur = None
                scalars[m.group(1)].setdefault(m.group(2), m.group(3))
                continue

            m = RE_STAT.match(line)
            if m:
                flush()
                name = m.group(2)
                if name.endswith(":histogram"):
                    key = name[: -len(":histogram")]
                    hist[m.group(1)].setdefault(key, {"bins": []})
                    cur = (m.group(1), key)
                else:
                    cur = None
                continue

            m = RE_FIELD.match(line)
            if m and cur is not None:
                try:
                    hist[cur[0]][cur[1]][m.group(1)] = float(m.group(2))
                except ValueError:
                    pass
                continue

            m = RE_BIN.match(line)
            if m and cur is not None:
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

            # 注意：histogram 块里 field 之后是 attr 行，attr 之后才是 bin 行。
            # 这里绝不能因为 attr 就把 cur 清掉，否则 bin 全部丢失。
            first = line.split()[0] if line.split() else ""
            if first in ("par", "run", "config", "version"):
                flush(); cur = None
    flush()
    return scalars, hist


def percentile(h, p):
    bins = sorted([(lo, c) for lo, c in h.get("bins", []) if c > 0], key=lambda x: x[0])
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
            frac = (rank - cum) / c if c else 0.0
            return lo + frac * (upper - lo)
        cum += c
    return h.get("max")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    target = sys.argv[1]
    if os.path.isdir(target):
        scas = [os.path.join(target, f) for f in os.listdir(target) if f.endswith(".sca")]
        if not scas:
            sys.exit("目录里没有 .sca")
        sca = scas[0]
    else:
        sca = target

    scalars, hist = parse_sca(sca)

    sent, sent_apps = 0.0, 0
    for mod, vals in scalars.items():
        if re.search(r"tsnDeviceA\.app\[\d+\]$", mod) and "packetSent:count" in vals:
            sent += float(vals["packetSent:count"]); sent_apps += 1

    recv_ep = {}
    for mod, vals in scalars.items():
        m = re.search(r"tsnDeviceB\[(\d+)\]\.app\[0\]$", mod)
        if m and "packetReceived:count" in vals:
            recv_ep[int(m.group(1))] = float(vals["packetReceived:count"])
    recv = sum(recv_ep.values())

    # 端到端时延：跨端点合并分桶
    cnt = ssum = 0.0
    vmin, vmax = float("inf"), 0.0
    merged_bins = defaultdict(float)
    for mod, by_name in hist.items():
        if not re.search(r"tsnDeviceB\[\d+\]\.app\[0\]$", mod):
            continue
        h = by_name.get("endToEndDelay")
        if not h or not h.get("count"):
            continue
        cnt += h.get("count", 0); ssum += h.get("sum", 0)
        vmin = min(vmin, h.get("min", float("inf"))); vmax = max(vmax, h.get("max", 0))
        for lo, c in h.get("bins", []):
            merged_bins[lo] += c
    merged = {"count": cnt, "sum": ssum, "min": vmin, "max": vmax,
              "bins": sorted(merged_bins.items())}

    # 5GS 驻留时间
    rcnt = rsum = 0.0
    rmax = 0.0
    for mod, by_name in hist.items():
        if ".dsTt[" not in mod or not mod.endswith(".translator"):
            continue
        h = by_name.get("residenceTime")
        if not h or not h.get("count"):
            continue
        rcnt += h.get("count", 0); rsum += h.get("sum", 0)
        rmax = max(rmax, h.get("max", 0))

    print(f"结果文件: {sca}\n")
    print("| 指标 | 值 |")
    print("|---|---|")
    print(f"| 发送包数（{sent_apps} 个发送端） | {sent:.0f} |")
    print(f"| 接收包数（{len(recv_ep)} 个端点） | {recv:.0f} |")
    if sent:
        print(f"| 送达率 | {recv / sent * 100:.4f}% |")
        print(f"| 丢包率 | {(1 - recv / sent) * 100:.4f}% |")
    if merged["count"]:
        print(f"| E2E 时延 mean | {merged['sum'] / merged['count'] * 1e3:.3f} ms |")
        print(f"| E2E 时延 p50 | {percentile(merged, 0.50) * 1e3:.3f} ms |")
        print(f"| E2E 时延 p99 | {percentile(merged, 0.99) * 1e3:.3f} ms |")
        print(f"| E2E 时延 max | {merged['max'] * 1e3:.3f} ms |")
        print(f"| E2E 样本数 | {merged['count']:.0f} |")
    if rcnt:
        print(f"| 5GS 驻留 mean | {rsum / rcnt * 1e6:.2f} us |")
        print(f"| 5GS 驻留 max | {rmax * 1e6:.2f} us |")

    out = os.path.join(os.path.dirname(os.path.abspath(sca)), "kpi.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["sent", f"{sent:.0f}"])
        w.writerow(["recv", f"{recv:.0f}"])
        if sent:
            w.writerow(["delivery_ratio", f"{recv / sent:.6f}"])
        if merged["count"]:
            w.writerow(["e2e_mean_ms", f"{merged['sum'] / merged['count'] * 1e3:.4f}"])
            w.writerow(["e2e_p50_ms", f"{percentile(merged, 0.50) * 1e3:.4f}"])
            w.writerow(["e2e_p99_ms", f"{percentile(merged, 0.99) * 1e3:.4f}"])
            w.writerow(["e2e_max_ms", f"{merged['max'] * 1e3:.4f}"])
        if rcnt:
            w.writerow(["residence_mean_us", f"{rsum / rcnt * 1e6:.2f}"])
    print(f"\n已写: {out}")


if __name__ == "__main__":
    main()
