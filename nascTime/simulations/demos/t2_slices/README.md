# t2_slices —— 三流三切片（测试方案用例 T2）

> 对应《6G确定性承载网集成测试方案》4.6 节用例 T2。

## 拓扑

```
client1（切片1 / 高优先 1024 B / PCP 5） ┐
client2（切片2 / 中优先 1472 B / PCP 4） ┼─ pe1 ── pe2 ── server
client3（切片3 / 低优先  512 B / PCP 0） ┘
```

门控周期 1 ms：等级2 独占 0–250 µs，等级1 独占 250–1000 µs，等级0 用剩余窗口。

## 探针诊断结果（本轮重点）

用「PE 出口各队列的 packet 计数」做探针（`pe1.eth[3].macLayer.queue.queue[i].incomingPackets:count`），
一路定位到三个真因，**与 PCP 机制本身无关**：

| # | 真因 | 发现方式 | 修复 |
|---|---|---|---|
| 1 | **客户端根本没开流编码**：ini 里 `hasOutgoingStreams` 被删掉，`client1.bridging` 模块都不存在 | 探针显示 7364 个包**全部**进 queue[0] | 补回 `hasOutgoingStreams` + streamIdentifier/streamCoder |
| 2 | **默认映射表把 PCP4/PCP5 撞到同一类**：`mapping[pcp][等级数-1]` 是 IEEE 802.1Q 表 8-5，3 个等级时 PCP4/5 都→等级1 | 补回编码后 queue[2] 仍为 0 | 显式设置 `classifier.mapping` |
| 3 | **中间交换机剥掉了 802.1Q 标签**：`excludeEncapsulationProtocols=["ieee8021qctag"]` 配在 `*.pe*` 上 | 队列分流正确、报文也发出，但对端收不到 | 只在最后一跳 pe2 剥标签，pe1 保留 |

修复后的队列分流（1 s，TAS）：

| 队列（等级） | 落入包数 | 对应切片 |
|---|---|---|
| queue[2] | 2052 | 切片1（PCP 5） |
| queue[1] | 3519 | 切片2（PCP 4） |
| queue[0] | 1793 | 切片3（PCP 0） |

**结论：PCP 这条件在 INET 4.6 里是可用的**，此前“需要自研 DSCP 分类器”的判断作废。

## 实测（2 s）

| 配置 | 切片 | 接收 | 均值 | 最小 | 最大 |
|---|---|---|---|---|---|
| NoGating | 切片1 | 4212 | 314 µs | 260 µs | 459 µs |
| NoGating | 切片2 | 7221 | 378 µs | 367 µs | 494 µs |
| NoGating | 切片3 | 3679 | 241 µs | 137 µs | 420 µs |
| TAS | 切片1 | 3898 | **72.97 ms** | 710 µs | 145.2 ms |
| TAS | 切片2 | 7221 | **497 µs** | 367 µs | 735 µs |
| TAS | 切片3 | 2886 | **211.6 ms** | 991 µs | 421.4 ms |

### 待解决：门控窗口仍需调优

- 切片2（窗口 750 µs）表现正常（497 µs）；
- 切片1（窗口 250 µs）与切片3（窗口 100 µs）出现数十至数百毫秒的积压。

初步判断：两个交换机各自独立门控、无相位对齐，且窗口余量偏小（含 64 B 前导/IFG 开销后，
实际可用带宽低于理论值）。下一步：
1. 只在一个交换机上启用门控，排除级联影响；
2. 按实测有效带宽重新核算窗口（切片1 提到 300 µs、切片3 提到 150 µs）；
3. 若仍积压，考虑给两个交换机配置相位偏移（`offset`）实现级联对齐。

## 跑法

```bash
cd nascTime/simulations/demos/t2_slices
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c NoGating -r 0 --sim-time-limit=2s --result-dir=results_NoGating
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c TAS      -r 0 --sim-time-limit=2s --result-dir=results_TAS
```

## 排查时踩过的坑（已修复，供后续参考）

1. **表达式分类器遇非 UDP 报文崩溃**：`expr(udp.destPort == N)` 对 ARP 和 IP 分片都会抛
   `Object nullptr has no member named 'destPort'`。对策：`**.arp.typename="GlobalArp"` + UDP 载荷 ≤1472 B。
2. **`GateControlList` 三相窗口不生效**：改用 `PeriodicGate` 直配。
3. **探针优先**：直接看 `queue[i].incomingPackets:count` 比猜配置快得多，一轮就能定位到“没打标 / 打错类 / 标签被剥”。
