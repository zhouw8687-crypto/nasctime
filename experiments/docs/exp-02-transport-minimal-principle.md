# EXP-02：承载域最小原理（三角环 + FRER）

> 日期：2026-10-28 　场景：`nascTime/simulations/demos/ring_test/`（5 节点三角环）
> 复现：`omnetpp.ini`（双树）/ `omnetpp_probe.ini`（双树 + 探针）/ `omnetpp_single.ini`（单树对照）

## 1. 结论先行：一个有效的承载域最小单元需要 5 件事

| # | 要素 | 本实验的取值 | 少了它会怎样 |
|---|---|---|---|
| 1 | **两条边不相交路径** | 三角形：`pe1-pe3`（1 跳）与 `pe1-pe2-pe3`（2 跳） | 无法验证"跨径"，退化成单路径 |
| 2 | **路径区分标识** | FRER 配置器自动用 **VLAN 0/1** 区分两棵树 | 两份副本走同一条路 |
| 3 | **复制点** | `pe1` 出口（分流交换机） | 无冗余 |
| 4 | **合并点** | `pe3` 入口（汇合交换机） | 目的端收到双份 |
| 5 | **测量点** | `FlowMeasurement` 成对：starter 在出口、recorder 在入口 | 只有"通/不通"，没有时延数字 |

## 2. 实测数字（50 ms，50 个包，1200 B，100 Mbps）

| 场景 | 目的端 `packetLifeTime` 均值 | 说明 |
|---|---|---|
| 仅路径 A（直连，2 跳到 pe3） | **303.51 µs** | 端到端 3 跳 |
| 仅路径 B（两跳，3 跳到 pe3） | **404.68 µs** | 端到端 4 跳 |
| 双路径同时 | **303.51 µs** | **等于"仅 A"→ 交付的是先到的快副本** |

分点测量（创建→到达该点）：

| 测量点 | 路径 A | 路径 B |
|---|---|---|
| pe3 入口 | 202.34 µs | 303.51 µs |
| 目的端入口 | 303.51 µs | 404.68 µs |
| **stddev** | **0.00** | **0.00** |

## 3. 由此得到的三条硬结论

1. **每跳 ≈ 101.17 µs**：1200 B @ 100 Mbps 的传输时间 96 µs + IFG/处理 ≈ 5 µs。
2. **跨径差 = 1 跳 ≈ 101.17 µs**：两条路径的跳数差决定差值，与负载无关（无拥塞时）。
3. **FRER 交付的是先到的副本**：双路径结果与"仅快路径"完全一致，证明合并器按**流 + 序列号**去重，先到先放行（`StreamMerger::matchesSequenceNumber` = 未见过才转发）。方差为 0 也证明这一点——若交付慢副本，均值会变成 404.68 µs。

> 更正：本文件 v0.1 曾判断"目的端拿到慢副本"，那是漏算了最后一跳（pe3→destination）导致的误读。

## 4. 承载域的最小原理（可直接作为加域的模板）

```
[复制点] --路径A(VLAN0)--> [合并点] --单份--> [下游]
          \--路径B(VLAN1)-->/
```

- **域内必须 L2 连续**：FRER 是桥功能（`TsnSwitch` + `hasStreamRedundancy`），路由器会打断它。
- **路径用显式树表达**，不靠路由协议：
  ```ned
  trees: [[["source","pe1","pe3","destination"]],
          [["source","pe1","pe2","pe3","destination"]]]
  ```
- **复制/合并点由配置器自动计算**：`StreamRedundancyConfigurator` 会下发 FDB
  `{destination, eth_i, vlan_k}` 并配置 splitter/merger。
- **测量必须成对**：`measurementLayer.typename = "MeasurementLayer"`，起点配
  `measurementStarter.flowName`，终点配 `measurementRecorder.flowName`（同一名字），
  统计会以 `<flow>:packetLifeTime:histogram` 落到 `.sca`。
- **端口号由 NED 连接顺序决定**，改拓扑后必须重新核对（本文件里的映射是
  `source.eth[0]↔pe1.eth[0]`、`pe1.eth[1]↔pe3.eth[0]`、`pe1.eth[2]↔pe2.eth[0]`、
  `pe2.eth[1]↔pe3.eth[1]`、`pe3.eth[2]↔destination.eth[0]`）。

## 5. 加新域时的四条规则

| 情况 | 做法 | 注意 |
|---|---|---|
| 新域仍是 L2 桥接 | 把新交换机接进同一个 L2 域，树里加节点 | 环变大后树数增加，`StreamRedundancyConfigurator` 会重算 |
| 新域是 IP 路由域 | 路由器打断 L2 → **FRER 到此为止**，域内改用路由 | 跨域的多径要在域边界另做 |
| 跨域需要多径 | **每域各自分集**，域边界做两级复制/去重 | 两级序列号独立；流量翻 4 倍；去重窗口要分别配 |
| 需要与非 TSN 域（如 5G）互联 | 用翻译器（NW-TT 之类）而不是路由器 | 翻译器保持 L2 语义，路由器不保持 |

## 6. 待补

- 门控（802.1Qbv）尚未开启，`hasEgressTrafficShaping` 仍为 false；
- 时间同步未开，门控没有共同时间基准；
- 合并器的 `bufferSize=10`（序列号窗口）对高带宽/长时延场景是否够，未测；
- 分位数精度受直方图分桶限制（当前 100 µs 一档），需要更细的分桶或向量。
