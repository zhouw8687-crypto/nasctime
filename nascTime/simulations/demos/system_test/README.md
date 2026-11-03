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


## 无线接入版（`SystemTestWireless.ned` + `omnetpp_wireless.ini`）

在原来的基础上加了 `gNB` + `NrUe` + 真 `Upf`，保留原版 `SystemTest` 不动。

### 一个必须记住的接法：TSN 要挂在 UPF 的 N6 侧

第一版把 TSN 接到 N3 承载环、再进 `upf.pppg`，结果运行时报：

```
Connected network interfaces can register using registerInterface()
-- in module SystemTestWireless.upf.ipv4.lp
```

原因：**UPF 是 GTP 隧道端点**
- `upf.pppg` = **N3 侧**，对端必须是 gNB（GTP 封装后的流量）
- `upf.dnPppg` = **N6 侧**，普通 IP，接数据网 / TSN 侧

所以 TSN 有线接入必须挂**核心侧（N6）**，不能挂 N3 传输环。

### 正确拓扑

```
[N3 承载]  gNB ── lsr2 ══ lsr1 ══ lsr3 ── upf.pppg
                                            │
[N6/核心]                            upf.dnPppg
                                            │
[TSN 接入] src ─ pe1 ─ pe2 ─ pe3 ─ edgeRouter ─ coreRouter ── server
```

### 实测（3 s）

| 流 | 发送 | 说明 |
|---|---|---|
| 有线 src → server | 299 | 经 TSN 接入 → N6 → server |
| 无线 ue[0] → server | 296 | 经 gNB → GTP → N3 环 → UPF → N6 → server |
| **server 合计收到** | **593** | = 299 + 294（2 个在途） |

合并时延：mean 10.24 ms / p99 32.2 ms / stddev 11.13 ms。
注意：这是**两条流混在一起**的统计（有线约 0.1 ms、无线约 5–30 ms），要看单流指标必须按端口分开采集。

### 这一版还缺

- `ue[0]` 的 `servingNodeId/nrServingNodeId` 是硬编码的 0/1，节点顺序一变就断——应当改成按名字绑定；
- 只有 1 个 UE、无切换；
- 没有 FRER / 门控 / 时间同步；
- 无线流的时延没有单独采集（混在 server 的 `endToEndDelay` 里）。
