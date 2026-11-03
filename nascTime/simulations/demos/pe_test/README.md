# pe_test —— 承载域（PE + TSN 能力）

> 角色：项目书里的**承载网（PE 设备）**。它同时具备两项能力：
> 1) 转发（本版是 L2 桥接；L3/MPLS 能力在 `mpls_test` 里验证，后续叠加）
> 2) **TSN 门控（802.1Qbv 固定传输窗口）**——本域的核心验证对象
>
> 这一版就是"无线接入 / 承载（PE+TSN）/ 核心"三域模型里的中间那个域。

## 拓扑

```
client1(BE) ─┐
             ├─ pe1 ── pe2 ── server
client2(HP) ─┘
```

链式（不是环）：L2 环 + IP 会触发 ARP 广播风暴（见 `system_test/README.md`）。
真实 PE 是环/网，环上保护倒换属后续增量（需 MRP/STP）。

## 两个配置

| 配置 | 说明 |
|---|---|
| `NoGating` | 不门控，BE 大包会阻塞 HP 小包 |
| `Gating` | 每 1 ms 周期给 HP 20 µs 独占窗口（照 INET `timeawareshaper` 示例） |

跑法：

```bash
cd nascTime/simulations/demos/pe_test
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c Gating   -r 0 --sim-time-limit=1s --result-dir=results_Gating
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c NoGating -r 0 --sim-time-limit=1s --result-dir=results_NoGating
```

## 实测（1 s，100 Mbps，HP 1 ms 周期 / 14B，BE ~60 Mbps / 1442B）

**HP 流（`server.app[1]`）端到端时延：**

| 配置 | 样本 | mean | stddev | min | max | max/min |
|---|---|---|---|---|---|---|
| NoGating | 1000 | **132.20 µs** | 82.66 µs | 17.43 µs | 271.95 µs | **15.6×** |
| Gating | 999 | **499.63 µs** | 60.02 µs | 432.97 µs | 553.61 µs | **1.28×** |

**BE 流（`server.app[0]`）：**

| 配置 | mean | p99 | max |
|---|---|---|---|
| NoGating | 441.06 µs | 834.10 µs | 1057.22 µs |
| Gating | 484.59 µs | 935.70 µs | 1161.64 µs |

### 怎么解读这组数

门控**没有降低平均时延，反而把 HP 从 132 µs 抬到 500 µs**。这是 Qbv 的正常代价：

- 不门控时，HP 包能"插空"走，均值小，但被 BE 大包挤得离散度极大（17 → 272 µs，15.6 倍）；
- 门控后，HP 包必须等自己的窗口，**均值 ≈ 半个周期（500 µs）**，但**离散度被压到 1.28 倍**（433 → 554 µs）。

均值 500 µs 恰好是周期的一半，而且 HP 的业务周期（1 ms）与门控周期（1 ms）相同，
相位关系固定 → 这就是项目书里"**周期映射**"要利用的性质：**周期对齐后时延锁定为常数**。

> 结论：门控是"**用确定的延迟上界换掉不确定的抖动**"，不是"降低时延"。
> 报指标时必须同时报 mean 和 max/min，只报 mean 会得出相反的结论。

## 踩过的坑（都写进 ini 注释了）

| 坑 | 现象 | 解决 |
|---|---|---|
| `UdpSinkApp` 全丢 | `packets:count` 有值但 `droppedPackets:count` 相同 | 改用 `UdpBasicApp` + `UdpSink`（自带 `endToEndDelay`） |
| 带 Q-Tag 的帧接收端不认识 | `Unknown protocol: ieee8021qctag` | `*.pe*.bridging.directionReverser.reverser.excludeEncapsulationProtocols = ["ieee8021qctag"]` |
| 门控配了但没效果 | 需要先 `hasOutgoingStreams` + PCP 映射，否则流量全进同一个队列 | 见 `[Config Gating]` 里的 `streamIdentifier` / `streamCoder` |

## 缺什么

- 802.1AS 时间同步（`hasTimeSynchronization`）——门控目前用仿真时间，没有真实时钟域
- 环网与保护倒换（MRP/STP）
- L3/MPLS 转发能力（PE 的另一半，见 `mpls_test`）
- 与无线接入、核心的拼接（见 `system_test`）
