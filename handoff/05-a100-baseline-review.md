# A100 接手核查记录

2026-11-21。核查基线为 b04a20e。已阅读 HANDOFF.md 及 handoff/01–04，结合本地《研究方案_任务五》和《2_项目年度重要进展及成果的详细介绍-日字形》核对 A100 相应场景。仿真使用现有编译产物，由命令行指定独立的 /tmp 结果目录。

## 项目目标与当前证据

课题五要在统一时基下验证无线接入、确定性承载、核心网和跨域协同。当前日字形集成场景包含六个承载网元、两台 gNB 与一个锚点 UPF，可以复测双基站双向业务。任务书中至少四套基站、至少两台核心网模拟服务器和跨距至少 30 km 是后续整体验证约束。报告中的空口和承载数据应注明场景、业务方向、测试条件与仿真时基。

| 场景 | 本轮结果 | 证据 |
|---|---|---|
| t2_ladder / TAS，run 0，2 s | 两侧各三流接收 2050 / 3610 / 1747 包，各发 2051 / 3612 / 1748 包。三类接收平均时延 798.29 / 769.86 / 1532.11 µs，与交接记录一致 | /tmp/nasctime-t2-baseline.5FDgof |
| e2e_ladder 默认直连，run 0，2 s | 通过命令行将四条流启动时间改为 50 ms。每流发送 196 包，每条上行收到 194 包，每条下行收到 195 包。接收均值约 20.276 / 5.000 ms | /tmp/nasctime-e2e-baseline.5nSAbU |
| e2e_ladder I-UPF 汇聚，同样的短跑参数 | 每流发送 196 包，上行各收 194 包，下行各收 195 包 | /tmp/nasctime-e2e-baseline.IONGwj |

用目的端口配对读取 t2_ladder 的应用层收发计数，三类每侧发送与接收的差分别为 1、2、1。kpi_v2.py 表 B 按同一个模块名减去收发计数，因此单向源端显示 100% 丢包。基线应使用配对后的统计，并在区分未交付与在途报文时设置排空窗口。

e2e_ladder 默认配置以 INI 的 network 参数和 NED 的实际连接为准。两台 gNB 经 PPP 分别接 NE5、NE6，锚点 UPF 经 PPP 双归 NE1、NE2，N6 连服务器。ProjectBookLadder.ned 和 omnetpp.ini 文件头仍有旧的 I-UPF 路径说明。单独的 LadderWithIupf.ned 和 omnetpp_iupf.ini 对应汇聚变体。

## 日字形报告的证据差异

- 原有 e2e_ladder/results 的 6 s 向量支持双侧上行均值约 20.29 ms、下行均值 5.00 ms，两条下行的 400 个样本均为 5.00 ms。按样本排序和线性插值复算，上行 P99 约 32.077 ms，下行 P99 为 5.000 ms。报告写的是 32.06 ms 和 4.95 ms。建议后续使用同一个样本序列计算均值、分位数与标准差。
- 报告表 2 下行均值为 4.54 ms、P50 为 2.27 ms、P99 为 4.49 ms，同时标准差为 0.00 ms。现有 ran_test/results 的 298 个下行样本均为 4.769631 ms，也与该表均值不同。需定位表 2 对应运行和统计口径。
- 报告表 3 的链式 PE 数据显示，门控使峰峰值从 254.52 降到 120.64 µs，最大观测时延从 271.95 升到 553.61 µs。均值约为周期一半只描述该配置的样本结果。报告后续宜保留这组对照的拓扑和相位条件。
- 历史端到端数据来自 Router 转发基线。报告 §2.6 的时延对比可用于说明该配置下双侧业务表现相近，尚需同一场景内的 Qbv 开关、队列归属和各段测量来支撑门控和多跳确定性结论。T2 记录的最大观测值从链式 1.485 ms 增至日字形 2.189 ms，也应与“上界与拓扑无关”的表述区分。

## 在现有 Router 以太网出口验证 Qbv

默认 e2e_ladder 的 Router 通过 EthernetInterface 的可配置 IPacketQueue 挂接 Ieee8021qTimeAwareShaper。用单队列先验证门控机制，保留原有三层转发、七条承载内部链路和 PPP 接口。六个网元的七条内部链路若全部改成同一个二层转发域，会有两个独立环。关闭任意一条横链路后仍有一个环。

按 01 文档加载环境，进入 e2e_ladder 后执行：

~~~bash
results=$(mktemp -d /tmp/nasctime-e2e-router-tas.XXXXXX)
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c General -r 0 \
  --sim-time-limit=2s --result-dir="$results" \
  '--*.ue[*].app[0].startTime=50ms' \
  '--*.server.app[2..3].startTime=50ms' \
  '--*.NE*.eth[*].queue.typename=Ieee8021qTimeAwareShaper' \
  '--*.NE*.eth[*].queue.bitrate=100Mbps' \
  '--*.NE*.eth[*].queue.numTrafficClasses=1' \
  '--*.NE*.eth[*].queue.classifier.defaultGateIndex=0' \
  '--*.NE*.eth[*].queue.transmissionGate[0].initiallyOpen=false' \
  '--*.NE*.eth[*].queue.transmissionGate[0].durations=[800us,200us]'
~~~

去掉最后两个门参数可得到常开对照。常开组在 /tmp/nasctime-e2e-router-tas.4lE9BX，周期门组在 /tmp/nasctime-e2e-router-tas.UTSoL6。两组四条业务流的收发数相同。周期门组 NE1.eth[1] 的 gateState 向量每 1 ms 在相位 800 µs 开门。该口 queue[0] 的 196 个排队时间样本对应的出队相位均在 800–811.62 µs，常开组平均等待 0 µs，周期门组平均等待 775.62 µs。默认直连中第一条上行平均时延从 20.276 ms 变为 21.066 ms，下行平均时延保持 5.000 ms。

尝试将 Router 一并切换为 LayeredEthernetInterface 和 EthernetLayer 时，首个业务报文在 NE3.ethernet.fcsChecker 触发 EthernetFcs 类型错误。基础以太网接口的队列配置已提供当前场景可复现的验证入口。门控证据覆盖单流量类及以太网出口，PPP 首末段、多个类、线上优先级标记与隔离仍待验证。

## 下一步验证边界

在默认直连场景保留原 General 基线，增加常开和三队列门控对照。先确认承载入口读取的是已封装 GTP-U 的外层 IPv4 DSCP，并按 46→5、34→4、0→0 进入不同队列，记录方向、出口和每类计数。对于 Router，检查每个转发出口能否读取外层 DSCP 并赋予本地分类标签。如果后续要求跨二层设备传递 PCP，再检查实际 VLAN 标记。PcpReq 是仿真报文的请求标签，线上 PCP 还依赖实际 802.1Q 封装。

已有 GtpUser 补丁在常规封装分支设置 DscpReq。FRER 使用的 UPF/PGW forcedPeer 分支提前发送并返回，当前默认场景未配置该分支。I-UPF 汇聚变体还需独立核对 N9 的外层标记。当前模型用内层 DSCP 派生 QFI，报告应保留这一模型假设。
