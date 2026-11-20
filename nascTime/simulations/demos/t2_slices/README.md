# t2_slices —— 三流三切片（测试方案用例 T2）

> 对应《6G确定性承载网集成测试方案》4.6 节用例 T2：三条业务流分属三个切片，
> 验证多流并发时高优先级流的确定性、切片间是否串扰。

## 拓扑与配置

```
client1（切片1 / 高优先 1024 B / PCP 5） ┐
client2（切片2 / 中优先 1472 B / PCP 4） ┼─ pe1 ── pe2 ── server
client3（切片3 / 低优先  512 B / PCP 0） ┘
```

门控周期 1 ms，三相窗口由 `GateControlList` 定义：

| 切片 | PCP | 等级 | 窗口 | 负载 |
|---|---|---|---|---|
| 切片1 | 5 | 2 | 0–300 µs | 18% |
| 切片2 | 4 | 1 | 300–880 µs | 45% |
| 切片3 | 0 | 0 | 880–1000 µs | 8% |

## 实测结果（2 s）

| 配置 | 切片 | 接收 | 均值 | 峰峰值 | RMS | 最小 | 最大 |
|---|---|---|---|---|---|---|---|
| NoGating | 切片1 | 4212 | 313.8 µs | 200.0 µs | 54.4 µs | 259.5 | 459.5 |
| NoGating | 切片2 | 7221 | 378.2 µs | 127.3 µs | 22.9 µs | 367.0 | 494.3 |
| NoGating | 切片3 | 3679 | 241.2 µs | 283.8 µs | 67.4 µs | 136.6 | 420.5 |
| **TAS** | 切片1 | 4210 | **665.1 µs** | 786.4 µs | 239.3 µs | 259.5 | 1045.9 |
| **TAS** | 切片2 | 7221 | **676.5 µs** | 605.5 µs | 164.1 µs | 367.0 | 972.6 |
| **TAS** | 切片3 | 3679 | **1014.8 µs** | 943.8 µs | 268.9 µs | 541.6 | 1485.3 |

**读法**：TAS 把三条流的时延上界锁定在 **1.5 ms 以内**（NoGating 下无上界保证）；
代价是平均时延上升（313→665 µs），这是“以确定上界换均值”的典型权衡，与承载域门控实验的结论一致。
三条流全部接近零丢包（4210/4212、7221/7221、3679/3679）。

## 探针与因果定位（排查过程记录）

### 探针方法

直接读 PE 出口各队列计数：

```
pe1.eth[3].macLayer.queue.queue[i].incomingPackets:count
```

### 三个配置错误（已修复）

| # | 真因 | 探针表现 | 修复 |
|---|---|---|---|
| 1 | 客户端未开流编码（`hasOutgoingStreams` 被删） | 7364 个包**全部**进 queue[0] | 补回流编码配置 |
| 2 | 默认映射表把 PCP4/PCP5 撞到同一类（IEEE 802.1Q 表8-5，3 等级时都→等级1） | 补回编码后 queue[2] 仍为 0 | 显式 `classifier.mapping` |
| 3 | 中间交换机剥掉 802.1Q 标签 | 分流正确、报文发出，但对端收不到 | 只在最后一跳 pe2 剥标签 |

修复后队列分流：queue[2]=4212（切片1）、queue[1]=7222（切片2）、queue[0]=3680（切片3）。

### 门控积压的因果实验

现象：TAS 下切片1/3 出现数十至数百毫秒积压。两个假设逐一验证：

| 实验 | HP 均值 | HP 最大 | 结论 |
|---|---|---|---|
| 基准（双交换机门控，250 µs 窗口） | 35.97 ms | 71.24 ms | — |
| 只开 pe1 门控 | 35.59 ms | 70.86 ms | 非级联 |
| 只开 pe2 门控 | 35.97 ms | 71.24 ms | 非级联 |
| 单流（仅 HP） | 35.97 ms | 71.24 ms | 非竞争 |
| 窗口放大到 400 µs | **0.574 ms** | 0.946 ms | 恢复 |
| 250 µs + 关闭保护带 | **0.631 ms** | 1.009 ms | 恢复 |

**结论：是窗口余量不足，不是级联相位。** 机理：`PeriodicGate` 的隐式保护带要求报文能在窗口关闭前发完，
有效窗口 = 窗口长度 − 一帧发送时间。切片1 窗口 250 µs、帧 84 µs → 有效 166 µs < 需求 186 µs，逐周期累积。

## 后续可用的优化方向：帧抢占（802.1Qbu）

如果后续要把窗口压得更紧、或要支持更大帧，业界有三种解法，按性价比排序：

| 解法 | 保护带开销 | 代价 | 与本场景的关系 |
|---|---|---|---|
| **显式预留保护带**（当前做法） | 一帧时间（切片1 约 84 µs） | 窗口必须放大 | 已按公式配置 |
| **相位对齐（`offset`）** | 接近 0 | 业务周期须与门控周期对齐 | 当前业务周期 463/270/530 µs 非 1 ms 整数倍，暂不适用；若后续把业务周期改成 1 ms 或 500 µs，可用 |
| **帧抢占（802.1Qbu + 802.3br）** | 降至最小分片（约 127 B，100 Mbps 下 ~10 µs） | 需 MAC 分片/重组 | **推荐后续尝试** |

### INET 对帧抢占的支持

```ned
// TsnSwitch.ned:43
bool hasFramePreemption = default(false);   // IEEE 802.1Qbu

// 开启后自动替换：
eth[*].macLayer.typename = "EthernetPreemptingMacLayer"
eth[*].phyLayer.typename = "EthernetPreemptingPhyLayer"
```

配套模块：`PreemptingServer`、`PreemptableStreamer`、`EthernetFragmentingMacLayer`；
官方示例：`inet/showcases/tsn/framepreemption`。

**注意**：源码中 `hasFramePreemption=true` 时会把 TAS 队列置空（`queue.typename = ""`），
因此“门控 + 抢占”的组合需要照官方示例单独配，不能简单叠加。

**触发条件（什么时候该上抢占）**：
- 窗口需求 + 一帧时间 > 周期可用时间（即当前配置余量不足）；
- 或要支持 1500 B 以上大帧而窗口又被压得很紧；
- 或需要把时延上界从“1.5 ms”进一步压到“亚毫秒”。

## 跑法

```bash
cd nascTime/simulations/demos/t2_slices
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c NoGating -r 0 --sim-time-limit=2s --result-dir=results_NoGating
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c TAS      -r 0 --sim-time-limit=2s --result-dir=results_TAS
```

## 排查踩坑记录

1. **表达式分类器遇非 UDP 报文崩溃**：`expr(udp.destPort == N)` 对 ARP 与 IP 分片都会抛
   `Object nullptr has no member named 'destPort'`。对策：`**.arp.typename="GlobalArp"` + UDP 载荷 ≤1472 B。
2. **`durations` 必须成对**：`PeriodicGate` 无法表达三段式窗口，三相窗口要用 `GateControlList`。
3. **探针优先**：看 `queue[i].incomingPackets:count` 比猜配置快得多，一轮就能区分“没打标 / 打错类 / 标签被剥”。
