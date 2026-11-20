#!/usr/bin/env python3
"""按《6G确定性承载网集成测试方案》表1口径计算 KPI。

用法：
    kpi_v2.py <结果目录或 .sca> [--duration 秒] [--filter 子串]

输出两张表：
  表A 时延与抖动：每个 endToEndDelay 直方图一行
      单向时延均值、峰峰值抖动（max-min，主指标）、RMS 抖动（标准差）
  表B 收发与带宽：每个应用层 io 模块一行
      发送/接收帧数、丢包率、有效带宽（接收净荷×8/时长）

时长缺省取 3 s；仿真时长不同时用 --duration 指定，否则带宽数值不可信。
"""
import os
import re
import sys

RE_STAT = re.compile(r"^statistic\s+(\S+)\s+(\S+):histogram\s*$")
RE_FIELD = re.compile(r"^field\s+(\S+)\s+(\S+)\s*$")
RE_SCALAR = re.compile(r"^scalar\s+(\S+)\s+(\S+)\s+([-\d.eE+]+)\s*$")


def find_sca(target):
    if os.path.isdir(target):
        for f in sorted(os.listdir(target)):
            if f.endswith(".sca"):
                return os.path.join(target, f)
        raise SystemExit("目录里没有 .sca")
    return target


def parse(path):
    hists, scalars = {}, {}
    cur = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = RE_STAT.match(line)
            if m:
                cur = (m.group(1), m.group(2))
                hists.setdefault(cur, {})
                continue
            m = RE_FIELD.match(line)
            if m and cur:
                try:
                    hists[cur][m.group(1)] = float(m.group(2))
                except ValueError:
                    pass
                continue
            m = RE_SCALAR.match(line)
            if m:
                try:
                    scalars[(m.group(1), m.group(2))] = float(m.group(3))
                except ValueError:
                    pass
                continue
            if line and not line[0].isspace() and line.split()[0] in ("par", "run", "config", "version"):
                cur = None
    return hists, scalars


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        sys.exit(__doc__)
    duration = 3.0
    filt = ""
    target = None
    i = 0
    while i < len(args):
        if args[i] == "--duration":
            duration = float(args[i + 1]); i += 2
        elif args[i] == "--filter":
            filt = args[i + 1]; i += 2
        else:
            target = args[i]; i += 1
    sca = find_sca(target)
    hists, scalars = parse(sca)

    print("### 表A 时延与抖动（口径：峰峰值 = max-min，RMS = 标准差）\n")
    print("| 统计对象 | 样本 | 均值 | 峰峰值抖动 | RMS抖动 | 最小值 | 最大值 |")
    print("|---|---|---|---|---|---|---|")
    n = 0
    for (mod, name), h in sorted(hists.items()):
        if "endToEndDelay" not in name or not h.get("count"):
            continue
        if filt and filt not in mod:
            continue
        mn, mx = h.get("min", 0.0), h.get("max", 0.0)
        print("| %s | %d | %.2f µs | **%.2f µs** | %.2f µs | %.2f µs | %.2f µs |" % (
            mod, h["count"], h.get("mean", 0) * 1e6, (mx - mn) * 1e6,
            h.get("stddev", 0) * 1e6, mn * 1e6, mx * 1e6))
        n += 1
    if n == 0:
        print("| （无 endToEndDelay 统计，需在场景里开启该 statistic） | | | | | | |")

    print("\n### 表B 收发、丢包率与有效带宽（时长按 %.1f s 计）\n" % duration)
    print("| 模块 | 发送帧 | 接收帧 | 丢包率 | 有效带宽 |")
    print("|---|---|---|---|---|")
    sent, recv, nbytes = {}, {}, {}
    for (mod, name), val in scalars.items():
        if name == "packetSent:count":
            sent[mod] = val
        elif name == "packetReceived:count":
            recv[mod] = val
        elif name == "packetReceived:sum(packetBytes)":
            nbytes[mod] = val
    mods = sorted(set(list(sent) + list(recv)))
    for m in mods:
        if filt and filt not in m:
            continue
        s = sent.get(m, 0.0)
        r = recv.get(m, 0.0)
        b = nbytes.get(m, 0.0)
        loss = "%.3f%%" % (100.0 * (s - r) / s) if s else "-"
        bw = "%.3f Mbps" % (b * 8 / duration / 1e6) if b else "-"
        print("| %s | %d | %d | %s | %s |" % (m, int(s), int(r), loss, bw))


if __name__ == "__main__":
    main()
