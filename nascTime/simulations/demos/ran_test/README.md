# ran_test —— 无线接入域（NR）

> **不复制任何 NED**，直接引用 Simu5G 官方网络定义
> `simu5g.simulations.nr.networks.SingleCell_Standalone`。
> Simu5G 升级时本域自动跟随；与 `ring_test` / `mpls_test` 完全解耦。

## 结构

```
server ── router ── upf ── iUpf ── gnb ──NR── ue[0]
```

## 为什么要自己的 `run.sh`

nascTime 通用包装 `bin/nasctime-run.sh` 的 NED 路径只有 `$SIMU5G_ROOT/src`，
而 `SingleCell_Standalone.ned` 在 `$SIMU5G_ROOT/simulations` 下。
本域的 `run.sh` 显式补上该路径，避免为了一个域去改通用脚本。

## 跑法

```bash
cd nascTime/simulations/demos/ran_test
./run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s --result-dir=results
```

## 实测（2026-11-02，1 gNB / 1 UE，下行 200 B @ 10 ms）

| 指标 | 值 |
|---|---|
| server → ue[0] | 发 299，收 298（99.7%） |
| 端到端时延 mean | **4.77 ms** |
| p50 / p99 / max | 2.38 / 4.72 / 4.77 ms |

项目要求"局域单向 ≤4 ms"，当前 **4.77 ms 略超**——第一个需要优化的真实缺口。

## 与其它域的边界

- 下行边界是 `iUpf` 的 N3 口。接 L3 承载域时，把 `server`/`router` 换成 `mpls_test` 的 LSR。
- 无线侧不涉及 TSN 门控；门控在 `ring_test`（L2）里。

## 坑

- **conda 路径**：`/media/a100/data/zbw/conda-envs/nasctime`（`zbw/` 下，不是 `zbw/nasctime/` 下）。
  写错会导致 `opp_run` 报 `Qt_6.11 not found`，看起来像"找不到库"，其实是路径不存在。
