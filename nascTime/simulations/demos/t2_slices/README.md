# t2_slices —— 三流三切片（测试方案用例 T2）

> 对应《6G确定性承载网集成测试方案》4.6 节用例 T2：三条业务流分属三个切片，
> 验证多流并发时高优先级流的确定性、切片间是否串扰。

## 拓扑

```
client1（切片1 / 高优先控制流 1024 B） ┐
client2（切片2 / 中优先大带宽 1472 B） ┼─ pe1 ── pe2 ── server
client3（切片3 / 低优先背景流  512 B） ┘
```

| 切片 | PCP | 目标等级 | 负载 | 窗口（TAS） |
|---|---|---|---|---|
| 切片1 | 5 | 2（最高） | 18% | 0–250 µs |
| 切片2 | 4 | 1 | 45% | 250–1000 µs |
| 切片3 | 0 | 0（最低） | 8% | 900–1000 µs |

## 实测（2 s，NoGating 基线，可用）

| 切片 | 帧长 | 样本 | 均值 | 峰峰值 | RMS | 最小 | 最大 |
|---|---|---|---|---|---|---|---|
| 切片1（高优先） | 1024 B | 4212 | 313.1 µs | 199.9 µs | 54.4 µs | 258.9 | 458.8 |
| 切片2（中优先） | 1472 B | 7221 | 377.4 µs | 126.6 µs | 22.7 µs | 366.4 | 493.0 |
| 切片3（低优先） | 512 B | 3679 | 240.5 µs | 283.8 µs | 67.4 µs | 136.0 | 419.8 |

**读法**：静态优先级下高优先流的时延并不最低，因为当前负载（约 71%）下几乎没有排队，
三条流的时延主要由**帧长**决定。要体现优先级作用，负载需提到 80% 以上。

## 当前状态：TAS 组未跑通，原因待定位

### 先撤回一个错误结论

前期曾判断“INET 的 PCP 路线走不通、需要自研 DSCP 分类器”。复查后**该结论不成立**：

1. INET 4.6 官方文档写明“帧按 PCP 分类（默认机制）”，
   `showcases/tsn/trafficshaping/timeawareshaper` 用的正是 `streamIdentifier + streamCoder` 打 PCP，
   且标注“Verified with INET version 4.6”。
2. `PcpTrafficClassClassifier.ned` 的默认映射是 **IEEE 802.1Q 表 8-5 矩阵**，
   索引为 `mapping[pcp][等级数-1]`。**等级数为 3 时 PCP4 与 PCP5 都映射到等级 1**，
   等级 2 永远为空——本场景原配置在结构上就无法表达“三切片三等级”。

也就是说：这是配置问题，不是机制缺失。**不需要**改 C++ 写自定义分类器。

### 已定位的三个真实陷阱

| 陷阱 | 现象 | 处理 |
|---|---|---|
| 默认映射矩阵 | 3 个等级时 PCP4/PCP5 撞到同一类 | 显式设置 `classifier.mapping`（行=PCP，列=等级数-1） |
| 表达式分类器遇非 UDP 报文崩溃 | `Object nullptr has no member named 'destPort'` | ① `**.arp.typename = "GlobalArp"` 消除 ARP；② UDP 载荷 ≤1472 B 避免 IP 分片（非首片无 UDP 头） |
| `GateControlList` 驱动三相窗口 | 三条流几乎全被卡死 | 改用 `PeriodicGate` 直配；**仍未跑通** |

### 已做的对照实验

| 实验 | 结果 | 推论 |
|---|---|---|
| `hasGcl = false`（不设门控，门默认全开） | 三条流全部正常（2052 / 3517 / 1792） | 通路与打标流程无阻塞 |
| GCL 只开 0 号门 | 三条流全部通过 | 所有流量都进了等级 0 |
| GCL 只开 5 号门 | 一条不通 | 等级 5 队列为空 |
| 显式 `classifier.mapping`（PCP5→2、PCP4→1）+ 三相 `PeriodicGate` | 仍各只收到 0–1 个包 | 打标或分类未生效 |
| 保留 802.1Q 标签（取消 C-Tag 剥离） | 同上 | 标签剥离不是瓶颈 |

**当前判断**：报文没有携带 `PcpReq`/`PcpInd` 标签，分类器取不到 PCP，全部落入默认等级 0；
而等级 0 的窗口只有 100 µs，于是几乎所有报文被卡住。

### 下一步（一步即可定性）

在客户端 bridging 层或整形器分类器上加探针，直接观察**报文进入分类器时的 PCP 值**：

- PCP 有值但不符合预期 → 打标映射未命中（`streamCoder` 配置问题）；
- PCP 为空 → 标签未随报文传递，需检查 `Ieee8021qProtocol` 与交换机标签处理链路。

**在此之前不要改成自研 DSCP 分类器**——那是把配置问题当成机制缺陷来解。

## 跑法

```bash
cd nascTime/simulations/demos/t2_slices
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c NoGating -r 0 --sim-time-limit=2s --result-dir=results_NoGating
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c TAS      -r 0 --sim-time-limit=2s --result-dir=results_TAS
```

## 下一步计划

1. 加 PCP 探针，定位打标是否生效（见上）；
2. 修好后把总负载提到 80%，重跑 T2 对照；
3. 补充 T3-4（低优先级过载）用例，计算切片隔离度。
