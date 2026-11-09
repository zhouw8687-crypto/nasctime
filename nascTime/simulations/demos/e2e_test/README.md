# e2e_test —— 按项目书搭的端到端环境

> 完全按项目书的结构搭，**不引入 nascTime 的 5G-TSN 桥假设**（没有 NW-TT / DS-TT、没有 TSN 岛）。

## 拓扑（就是项目书那张图）

```
[无线接入]  ue ⇢ gNB ──N3──┐
                             ├── [承载: pe1 ══ pe2 ══ pe3，带 Qbv] ── [核心: upf ── server]
[有线终端]  host ── edge ───┘
```

| 节点 | 类型 | 角色 |
|---|---|---|
| `ue[0]` / `gnb` | `NrUe` / `gNodeB` | 无线接入（Simu5G） |
| `host` | `TsnDevice` | 有线终端 |
| `edge` | `TsnSwitch` | 有线边缘接入 |
| `n3Router` | `Router` | gNB 的 N3 接入点（PPP → Ethernet 转换） |
| `pe1/pe2/pe3` | `TsnSwitch` | **承载（PE）**，带 802.1Qbv 门控 |
| `coreRouter` | `Router` | 核心侧汇聚 |
| `upf` | `Upf`（Simu5G） | 真 UPF，终结 GTP |
| `server` | `StandardHost` | 数据网 |

## 实测（3 s，200 B @ 10 ms 两条流）

| 流 | 发送 | 接收 | 时延 mean | p99 | stddev |
|---|---|---|---|---|---|
| 无线 `ue[0] → server` | 298 | **295** | 20.56 ms | 32.25 ms | 6.08 ms |
| 有线 `host → server` | 299 | **299** | 112.23 µs | 169.61 µs | 3.36 µs |

两条接入都通，且无线流确实走了 GTP（UE ⇢ gNB → N3 路由 → PE 链 → UPF → 解封装 → server）。

## 20.58 ms 是怎么来的：上行调度，不是拓扑

上一版我判断"开 Qbv 不分类把无线流饿死了"，**这个判断是错的**。做了四组对照：

| 实验 | 无线流 mean | 结论 |
|---|---|---|
| 门控 20µs/980µs | 20.56 ms | 基准 |
| 门控 800µs/200µs | 20.58 ms | 窗口比例**无关** |
| **完全关掉门控** | **20.58 ms** | 门控**无关** |
| 业务延后到 1.5 s 再发 | 21.16 ms | attach 阶段**无关** |

同一场景里同时跑上行和下行：

| 流 | 样本 | mean | p50 | p99 | stddev |
|---|---|---|---|---|---|
| **下行** server→ue[0] | 299 | **4.54 ms** | 2.27 ms | 4.49 ms | 0.00 |
| **上行** ue[0]→server | 295 | **21.36 ms** | 21.46 ms | 32.27 ms | 6.62 ms |
| 有线 host→server | 299 | 112.91 µs | 240.44 µs | 368.26 µs | 15.16 µs |

再把上行发送间隔从 10 ms 改成 1 ms：上行时延涨到 **60.20 ms**（下行不变，4.54 ms）。

### 结论

- **承载网（PE 链 + 门控）对时延的贡献是微秒级**，不是 20 ms 的来源；
- **16 ms 的差值来自 Simu5G 的 NR 上行调度**（调度请求/授权 + 上行队列），且**随负载恶化**；
- `NrMacUe.ned` 只暴露 3 个参数（`harqProcesses`/`raResponseWindow`/`retxBsrTimer`），没有可调的 SR 周期。

### 对项目的直接影响

1. 若要验证"上行确定性"，Simu5G 的默认上行调度是瓶颈，需要改调度器或显式配置上行资源；
2. 若只做下行基线对照，4.5 ms 量级与 `ran_test` 一致（4.77 ms），说明拓扑拼接没有引入额外时延；
3. 报指标时必须写清方向（上行/下行），否则同一场景会差 4 倍以上。

## 跑法

```bash
cd nascTime/simulations/demos/e2e_test
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s --result-dir=results
```

## 与其它目录的关系

| 目录 | 关系 |
|---|---|
| `pe_test/` | 本网络的 PE 段单独验证（门控开/关对照） |
| `ran_test/` | 本网络的无线段单独验证（Simu5G 官方网络） |
| `core_test/` | 本网络的核心段单独验证 |
| `system_test/` | 早期组装（LSR 环做承载，与本模型不一致），保留作对照 |
| `ring_test/` `mpls_test/` | 机制验证台，不属于项目书模型 |

## 缺什么

- 流量分类（PCP 映射）——现在门控在饿死默认业务
- 多 UE / 切换
- 承载环与保护倒换（现在是链）
- 时间同步（802.1AS）
- 控制器


## 流分类被 ARP 阻塞（未解决）

想在 `n3Edge` 上按 GTP-U 端口（2152）打 PCP 4，配置为：

```
*.n3Edge.bridging.streamIdentifier.identifier.mapping = [
    {stream: "gtp", packetFilter: expr(udp.destPort == 2152)}]
```

运行时报错：

```
Error: Object nullptr has no member named 'destPort'
-- in module (inet::queueing::PacketMultiplexer) ...bridging.directionReverser.join
```

原因：ARP 包没有 UDP 头，表达式解引用空指针。

两条修法（都未实施）：
1. 配静态 ARP 表，让 ARP 根本不出现（INET 的 `Ipv4NetworkConfigurator` 不支持，需手写表）；
2. 换对空头安全的分类维度（如按 DSCP 或按接口），而不是按 UDP 端口。
