#!/usr/bin/env python3
"""从 .vec/.vci 计算某个模块某条向量的"到达间隔"，用来量中断时长。

用法：
    vec_gaps.py <结果目录或 .vec> <模块子串> [向量名子串]

例：
    vec_gaps.py mpls_failure_test/results host3.app appPkSeqNo
    vec_gaps.py mpls_failure_test/results host3.app packetBytes

输出：样本数、时间范围、最大间隔及其发生时刻、超过阈值(默认 1 个发送周期)的间隔列表。

原理：.vci 里 `vector <id> <模块路径> <向量名>:vector` 是声明；.vec 里每行
`<id> <事件号> <时间> <值>`。同一 id 的时间序列即到达时刻。
"""
import os
import sys
from collections import defaultdict


def load_vci(path):
    """返回 {vectorid: (module, vecname)}"""
    table = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 4 and parts[0] == "vector":
                try:
                    vid = int(parts[1])
                except ValueError:
                    continue
                table[vid] = (parts[2], parts[3])
    return table


def load_vec_times(path, wanted):
    """返回 {vid: [t,...]}，只保留 wanted 里的 id"""
    times = defaultdict(list)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 4 or parts[0] in ("version", "run", "attr"):
                continue
            try:
                vid = int(parts[0])
            except ValueError:
                continue
            if vid in wanted:
                try:
                    times[vid].append(float(parts[2]))
                except ValueError:
                    pass
    return times


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    target = sys.argv[1]
    mod_sub = sys.argv[2]
    name_sub = sys.argv[3] if len(sys.argv) > 3 else ""

    if os.path.isdir(target):
        vcis = [f for f in os.listdir(target) if f.endswith(".vci")]
        vecs = [f for f in os.listdir(target) if f.endswith(".vec")]
        if not vcis or not vecs:
            sys.exit("目录里没有 .vci/.vec")
        vci = os.path.join(target, vcis[0])
        vec = os.path.join(target, vecs[0])
    else:
        vec = target
        vci = target[:-4] + ".vci"

    table = load_vci(vci)
    wanted = {vid: (m, n) for vid, (m, n) in table.items()
              if mod_sub in m and name_sub in n}
    if not wanted:
        sys.exit(f"没找到匹配的向量：module~{mod_sub} name~{name_sub}")
    for vid, (m, n) in sorted(wanted.items()):
        print(f"向量 {vid}: {m} {n}")

    times = load_vec_times(vec, wanted)
    for vid, (m, n) in sorted(wanted.items()):
        ts = sorted(times.get(vid, []))
        if len(ts) < 2:
            print(f"  {m} {n}: 样本不足 ({len(ts)})")
            continue
        gaps = [(ts[i + 1] - ts[i], ts[i + 1]) for i in range(len(ts) - 1)]
        gaps.sort(reverse=True)
        biggest, when = gaps[0]
        print(f"\n{m} {n}")
        print(f"  样本 {len(ts)}，时间 {ts[0]:.6f} → {ts[-1]:.6f} s")
        print(f"  最大间隔 {biggest*1e3:.3f} ms，发生在 t={when:.6f} s")
        top = [g for g in gaps if g[0] > 2 * (sum(g[0] for g in gaps) / len(gaps))][:5]
        if top:
            print("  明显异常间隔（>2×平均）：")
            for d, t in top:
                print(f"    {d*1e3:.3f} ms @ t={t:.6f} s")


if __name__ == "__main__":
    main()
