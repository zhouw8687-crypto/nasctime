# t2_slices —— 三流三切片（测试方案用例 T2）

> 对应《6G确定性承载网集成测试方案》4.6 节用例 T2：三条业务流分属三个切片，
> 验证多流并发时高优先级流的确定性、切片间是否串扰。

## 拓扑

```
client1（切片1 / 高优先控制流 1024 B） ┐
client2（切片2 / 中优先大带宽 1472 B） ┼─ pe1 ── pe2 ── server
client3（切片3 / 低优先背景流  512 B） ┘
```

| 切片 | PCP | 流量等级 | 负载 | 窗口（TAS） |
|---|---|---|---|---|
| 切片1 | 5 | 2（最高） | 18% | 250 µs |
| 切片2 | 4 | 1 | 45% | 650 µs |
| 切片3 | 0 | 0（最低） | 8% | 100 µs |

门控周期 1 ms，三相由 `GateControlList` 定义（`PeriodicGate` 的 `durations`
必须成对出现，无法直接写出“闭-开-闭”的三相窗口）。

## 实测（2 s，NoGating 基线）

| 切片 | 帧长 | 样本 | 均值 | 峰峰值 | RMS | 最小值 | 最大值 |
|---|---|---|---|---|---|---|---|
| 切片1（高优先） | 1024 B | 4212 | 313.1 µs | 199.9 µs | 54.4 µs | 258.9 µs | 458.8 µs |
| 切片2（中优先） | 1472 B | 7221 | 377.4 µs | 126.6 µs | 22.7 µs | 366.4 µs | 493.0 µs |
| 切片3（低优先） | 512 B | 3679 | 240.5 µs | 283.8 µs | 67.4 µs | 136.0 µs | 419.8 µs |

**读法**：静态优先级下高优先流的时延并不最低，因为当前负载（约 71%）下几乎没有排队，
三条流的时延主要由**帧长**决定。要体现优先级作用，负载需提到 80% 以上。

## 已知阻塞：TAS 组的 PCP 标记未生效

TAS 组三条流几乎全部被卡死（切片1 只收到 1 个包）。诊断结论：**所有流量都落在等级 0**。

验证方法：把三相门状态改成只开 0 号门（`["10000000",...]`）→ 三条流全部通过；
只开 5 号门（`["00000100",...]`）→ 一条都不通。说明没有任何流量进入等级 5。

### 为什么放弃 PCP 路线（本文件的核心记录）

INET 的队列分类器只认 PCP，而 PCP 只能由 `StreamCoder` 写入 `PcpReq` 标签
（`PcpTrafficClassClassifier.cc` 直接读 `packet->findTag<PcpReq>()`，不读 802.1Q 头）。
实际尝试了四条路，均未打通：

| 尝试 | 结果 | 原因 |
|---|---|---|
| `MultiFieldClassifier` + DSCP 过滤 | 无法挂载 | 它实现的是 DiffServ 分类器接口，不是 `IPacketClassifier` |
| `Ieee8021qTagEpdHeaderInserter.defaultPcp` 按接口固定 PCP | 无效 | 所有流量仍在等级 0，标签未被识别 |
| `StreamCoder` + `expr(udp.destPort == N)` | 崩溃 | ① ARP 报文无 UDP 头；② **IP 分片**的非首片也无 UDP 头 |
| 上述 + `GlobalArp`（消除 ARP）+ 载荷降到 1472 B（消除分片） | 不崩了，但**标记仍不生效** | `StreamCoder` 未产生 `PcpReq` |

**结论**：在 INET 4.6 的这条路径上，靠配置无法得到可靠的 PCP 标记。
下一步应实现一个**按 DSCP 分队列的自定义分类器**（读 `Ipv4Header` 的 DSCP，非 IP 走默认门），
放在 nascTime 自己的库里编译，而不是继续在 ini 里绕。

### 顺带记录的两个坑

1. **ARP 会让表达式分类器崩溃**：`expr(udp.destPort == N)` 遇到无 UDP 头的报文会抛
   `Object nullptr has no member named 'destPort'`。用 `**.arp.typename = "GlobalArp"` 可消除 ARP。
2. **大载荷会分片**：1472 B 是 MTU 1500 下的 UDP 载荷上限，1500 B 会分片，
   非首片没有 UDP 头，同样触发上面的崩溃。

## 跑法

```bash
cd nascTime/simulations/demos/t2_slices
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c NoGating -r 0 --sim-time-limit=2s --result-dir=results_NoGating
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c TAS      -r 0 --sim-time-limit=2s --result-dir=results_TAS
```

## 下一步

1. 在 nascTime 库里实现 `DscpTrafficClassClassifier`（约 60 行），替换 shaper 的默认分类器；
2. 把总负载提到 80%，重跑 T2 对照；
3. 补充 T3-4（低优先级过载）用例，计算切片隔离度。
