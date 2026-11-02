# system_test —— 整体组装模型（承载为中心 + 多接入）

> 角色：把各域**装进一个网络**，验证"端到端连通"这条最底线的能力。
> 各域仍保留独立目录做单域验证；本目录只负责拼装。
>
> **架构修正**：早期版本把 5G 当成"在中间的桥"（3GPP logical TSN bridge 模型），
> 那对应的是 nascTime 的场景，不是本项目。本项目是 **承载域在中心，多种接入挂上去**。

## 拓扑

```
  TSN 有线接入（L2，链式）        边界           承载域（L3，三角环）          核心
 ┌───────────────────────┐   ┌──────────┐   ┌────────────────────┐   ┌──────────┐
 src ── pe1 ── pe2 ── pe3 ─── edgeRouter ── lsr1 ── lsr2 ── lsr3 ── upf ── server
                                              └──────╲ ╱─────┘
                                                     lsr2/3 三角环
```

| 段 | 节点 | 类型 |
|---|---|---|
| 有线接入 | `src`、`pe1`、`pe2`、`pe3` | `TsnDevice` + `TsnSwitch`（L2） |
| 边界 | `edgeRouter` | `Router`（L2 桥口 + L3 上行口） |
| 承载 | `lsr1`、`lsr2`、`lsr3` | `Router`（三角环） |
| 核心 | `upf`、`server` | `Router` + `StandardHost` |

## 实测（2026-11-02，3 s，200 B @ 10 ms）

| 指标 | 值 |
|---|---|
| src → server | 发 299，收 **299（100%）** |
| 端到端时延 mean | **81.83 µs** |
| p99 / max | 161.45 / 162.03 µs |
| stddev | 4.65 µs |

## 关键设计决定：**L2 段不能成环**

最初把有线接入写成三角环（`pe1-pe2-pe3-pe1`），结果是：

| 拓扑 | 送达 | 时延 p99 |
|---|---|---|
| L2 三角环 | 281/299（丢 18） | **981.9 ms** |
| L2 链式 | 299/299 | **161.45 µs** |

原因：**INET 的 `EthernetSwitch`/`TsnSwitch` 不跑 STP**，L2 环上的 ARP 广播会无限绕圈。
要保留环，必须三选一：

1. 断一条边（本文件的做法）；
2. 换 `MrpSwitch`（MRP 环保护）或自己加 STP；
3. 环上只跑**无 IP** 的静态 FDB 流量（这正是 `ring_test` 的做法：不配 IP、不配 ARP，用 FRER 的静态 FDB）。

**L3 段（lsr 三角环）不受影响**——路由天然处理环路。

## 已接入 / 未接入

| 项 | 状态 |
|---|---|
| TSN 有线接入（L2） | ✅ 已接入（链式） |
| L3 承载（三角环） | ✅ 已接入 |
| 核心（UPF 代理 + 数据网） | ✅ 已接入 |
| **无线接入（gNB/UE）** | ❌ 未接入——需要真 `Upf` 终结 GTP，而真 `Upf` 又需要 gNB 的 `GtpUser` 对端，两者必须一起加 |
| FRER（双路径冗余） | ❌ 未启用——见 `ring_test` |
| 802.1Qbv 门控 / 时间同步 | ❌ 未启用 |

## 跑法

```bash
cd nascTime/simulations/demos/system_test
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s --result-dir=results
```
