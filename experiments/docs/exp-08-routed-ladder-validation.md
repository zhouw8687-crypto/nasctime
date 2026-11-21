# 日字形路由承载网仿真验证

2026-11-21 · A100 · OMNeT++ 6.4.0 / INET 4.6 / 项目内 Simu5G。用例组织借鉴 Spirent 集成测试流程。帧长、负载、测量点和判据按实际模型声明，以下数值来自仿真。

## 模型架构

~~~text
                     5GC / 双归测量端
                       /          \
                    NE1 ---------- NE2
                     |              |
                    NE3 ---------- NE4
                     |              |
                    NE5 ---------- NE6
                     |              |
                  gNB1/源1       gNB2/源2
~~~

- 两种场景继承同一个 LadderBackbone。六台 Router 之间保留三条横链路和四条竖链路。T0 对三条横链路各发五个限制为一跳的 ICMP 探针，均收到 5/5。T2 的两路业务分别走 NE5→NE3→NE1 和 NE6→NE4→NE2，每路三类在同一出口竞争。路由为 INET IPv4NetworkConfigurator 配置的静态路由。
- TransportLadder 在底部和顶部采用 INET StandardHost，按端口测量从接入点到核心侧的纯承载路径。ProjectBookLadder 在底部接两台 NR gNB，分别服务两个 NrUe，顶部是双归 UPF，UPF 的 N6 通向服务器。图中的 eNB 位置在 NR SA 模型中用 gNB 表示。
- 新测试配置的 NE 间链路为 100 Mbps、每跨 30 km，INET EthernetLink 给出约 150 µs 每跨的单向传播时延。每侧默认业务经过两跨。两端的 PPP 接入为 10 Gbps、10 µs，门控范围为 NE 的 Ethernet 出口。旧 General 配置保留原来的 10 m 默认跨距和流量。
- IPv4 负责每跳转发，因而可保留整个物理环。出口复用 EthernetInterface 的 egressTC 和 queue 两个配置点。DscpToPcpMarker 由两个 INET ContentBasedTagger 组成，从第一个 IPv4 头取 DSCP，忽略 ECN 位。DSCP 46、34 分别产生 PCP 5、4 的本机请求标签，默认类进队列 0。标准 PcpTrafficClassClassifier 将 PCP 5、4 分入队列 2、1。线上优先级随外层 DSCP 传递，每个 Router 重建本地 PCP 分类，仿真帧不插 VLAN。
- 每类 DropTailQueue 容量 128 包，FIFO 对照合计 384 包。TAS 给高、中、低类分别配置 500/1200/300 µs，周期 2 ms，隐式保护带把以太网前导码和 IFG 计入。T3 扩容通过 ScenarioManager 在周期边界切换两跳的 PeriodicGate，流量增量在两组一致。光层扰动采用同一现有链路的 PER 模型。

## 官方示例与研究依据

- [INET 4.6 Time-Aware Shaping](https://inet.omnetpp.org/inet/docs/showcases/tsn/trafficshaping/timeawareshaper/doc/index.html) 将分类和门控放在出口队列。其周期流与发送窗口同步的示例启发本实验的相位锁定对照。
- [INET 4.6 独立使用流量整形模块](https://inet.omnetpp.org/inet/docs/showcases/tsn/trafficshaping/underthehood/doc/index.html) 说明整形模块可独立复用。项目接入点为 EthernetInterface，避免为添加整形而更换 Router 或裁剪日字形链路。
- [INET Gate Schedule Configuration](https://inet.omnetpp.org/docs/showcases/tsn/gatescheduling/) 与 [TSNsched 原始论文](https://theory.stanford.edu/~barrett/fmcad/papers/FMCAD2019_paper_24.pdf) 将门控相位视为沿路径调度的一部分。本轮对比同相、第二跳偏移和周期锁定。当前配置由手工窗口定义。
- [INET 官方社区讨论 #802](https://github.com/inet-framework/inet/discussions/802) 讨论了 TAS 与常开队列的对照。本轮将单 FIFO、三队列常开和三队列加门控分别运行。
- [Simu5G gNodeB 文档](https://simu5g.org/neddoc/simu5g.nodes.gNodeB.html) 给出 NR SA 与 UPF 组件关系。[INET 4.6 PCAP Recording](https://inet.omnetpp.org/docs/showcases/general/pcaprecording/doc/) 给出抓包及 FCS 配置。本轮在 NE1/2/5/6 抓以太网包，并用 fork 的 GTP-U UDP 端口 31 筛选外层 IPv4。
- [INET 4.6 Measuring Time Along Packet Flows](https://inet.omnetpp.org/docs/showcases/measurement/flow/doc/index.html) 与 [OMNeT++ 统计手册](https://docs.omnetpp.org/manual/index) 支持按流和按事件采样。本轮直接复用 UDP 应用的发送、序列号和时延向量，以及整形器的 gateState 和 queueingTime 向量。

## 测量口径

UDP 应用时延，时基为模拟器事件时间。纯承载的主统计区间为发送时刻 0.2–1.7 s，其中最初 100 ms 业务作为预热。记录保留序列号 0 起的所有样本，统计脚本按发送窗口配对，每次停止发送后继续运行约 300 ms 用于排空。另输出每秒窗口、扰动前/中/后、重复序列计数和按净荷计算的吞吐。时延取均值、线性插值 P99、最大值、极差和样本标准差。出队门状态取同一时间/事件下最后一次记录。P99 是单次对照的描述性分位数，样本量和重复数用于机制比较。

T1/T2 的帧长以 MAC 帧含 FCS 为口径。IPv4/UDP/无 VLAN 的 MAC/FCS 头合计 46 B，负载计算另计 20 B 前导码和 IFG。T2 每侧的 1024/1518/512 B 对应 20/50/10% 线上负载。512 B 流净荷吞吐约 8.76 Mbps。T2 的相位锁定对照只把高优流改为每 2 ms 一帧，即约 4.176% 线上负载，两组负载完全一致。

## A100 结果

| 用例 | 实测结果与结论 |
|---|---|
| T0 | 3 条横链路各 5/5，T2 两条竖边也各承载三类流。 |
| T1 | 64/128/512/1024/1518 B × 30%/80% 共 10 组。1024 B、80% 的左路稳态 14368/14368、均值 486.74 µs、极差 0 µs。把首批 ARP 瞬态计入时该组极差为 623.04 µs。 |
| T2 | 左路高优流三组均送达 3592/3592。FIFO / 三队列常开 / 固定门控的 P99 分别为 659.45 / 646.67 / 2563.37 µs，峰峰值为 200.08 / 162.64 / 1598.80 µs。第二跳后移 200 µs 将 P99 降至 2059.42 µs，极差为 1732.63 µs。 |
| T2 相位锁定 | 同一周期流和背景负载下，常开与 TAS 均送达 750/750。高优流峰峰值由 162.64 降到 0.89 µs，P99 由 646.74 降到 486.74 µs。说明收益依赖到达相位和窗口是否匹配。 |
| T3-1 | 0.6–1.1 s 高优流由 20% 升到 40%。左路高优流送达 1374/2394，当前固定窗口容量不足。 |
| T3-2 | 左路中优流由 50% 升到 60%。固定窗口送达 2376/2438，P99 29.20 ms。脚本扩容窗口后送达 2438/2438，P99 1.41 ms。高优流两组均送达 1197/1197，低优流 P99 由 2.23 升到 4.08 ms。 |
| T3-3 | 0.6–1.1 s 将 NE3–NE1 链路的模拟包错误率设为 2%。扰动窗口左路高优流送达 1172/1197，恢复后继续观察。模拟 PER 用于隔离网络模型影响，光衰、FEC 和链路保护倒换需另建测量。 |
| T3-4 | 低优流升至 100% 线上负载。左路高优在 FIFO 中送达 523/1197，在三队列常开及 TAS 中均送达 1197/1197。常开已能在这个配置下隔离低优过载。 |
| T4 | 30 s TAS 运行，分析区间内两侧六流共 519672/519672。左路高优流 29 个完整一秒窗口的均值范围为 1794.24–1796.18 µs。 |

静态 T2 的 56384 次全网出队与 E2E TAS 的 392 次全网出队全部位于各自开门窗口内。T2 高优混合负载的抖动结果说明，门控生效与达到 100 µs 抖动目标是两项独立验证。扩容结果只验证脚本触发和调度效果。预测控制、独立时钟漂移和仪表标定有各自的输入与对照。T4 为 30 s 稳态验证，项目中还有 2 h/24 h 测试口径。基础 Router MAC 的帧长上限使本轮 T1 选用 64–1518 B。9000 B 工况应在支持巨帧的接口模型上单独核对。

## 5G 集成的逐层证据

E2ePriority 与 E2eTas 以较轻的流量检查两台 gNB 的双向链路。12 条流在两组均为每流 16/16。四个观测 NE 的 PCAP 各出现 32 个 DSCP 46、32 个 DSCP 34 和 32 个 DSCP 0 的隧道包。在低侧两个 Router 的上行 Ethernet 口，队列 0/1/2 入包数为 17/16/16，队列 0 含一个 ARP。对照 E2eZeroOuterDscp 保持内层业务不变，通过现有 Simu5G QFI 映射把非零外层 DSCP 置零，同一出口入队变为 49/0/0，四个 PCAP 都只见 DSCP 0。由此确认分类取的是外层标记。

E2eMixedLoad 用更大的载荷和更短的周期加压。每侧上行三类的收发为 160/160、204/320、0/160，下行全部送达。NE5/NE6 首个以太网出口已经只观察到 160、204、0 个三类业务包，短缺发生在进入承载队列之前。后续应在 RLC/MAC/PPP 边界定位无线侧容量和优先级行为。当前模型中内层 DSCP 派生 QFI，结论限于该 Simu5G 配置。

## 复现

在 A100 项目根执行：

~~~bash
bash experiments/exp/run_ladder_validation.sh
~~~

脚本创建新的结果目录，输出 Git 版本、运行日志、原始 sca/vec、分流 CSV、门控 CSV 和集成 PCAP。主要验证批次保存在 A100 /tmp/ladder-validation.V8SY8a，相位锁定补测在 /tmp/ladder-phase-locked.yAfy0p。两批数据已归档到 A100 的 exports/ladder-validation-20261121.hu8ufR/raw-results.tar.gz，同目录有清单和 SHA-256 校验文件。按需定位外层 IPv4 字段：

~~~bash
tcpdump -nnvv -r '<PCAP 文件>' 'udp port 31'
~~~
