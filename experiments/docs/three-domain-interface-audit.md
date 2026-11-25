# 日字形三域仿真功能与接口审计

审计基线为 A100 项目提交 `c787fab`，对应已发布的实验线 `9b0cc01`。运行栈为 OMNeT++ 6.4.0、INET 4.6、项目内置 Simu5G 1.5.0 基线及其补丁。审计以主方案的 **三层选路与各域资源联合优化** 为边界。下文文件位置相对于项目根目录。

本项目的完整性按可验证的闭环判断。控制面需要 **接收业务需求 → 识别能力和约束 → 本地求解 → 接受或拒绝配置 → 回读实际生效状态**。数据面需要 **识别同一业务 → 执行队列、带宽、路径或承载动作 → 产生可定位到节点和流的结果**。无线 MAC 的发包与调度按本地时隙执行，承载和核心网控制器通过较慢周期更新配置。上层只消费带单位、时间戳和有效期的能力或候选，不需要读取每个 MAC 事件。

| 判定 | 含义 |
| --- | --- |
| 主场景已跑 | 实际在日字形场景开启，且有既有或本轮回放证据。 |
| 现有可复用 | 库源码、原生接口或历史场景具备，接入当前日字形仍需配置或验证。 |
| 首轮要补 | 拟验证的联合优化直接依赖这个能力，需要加实验配置、接口或算法。 |
| 按目标启用 | 只有换成相应研究条件或接真实设备才需要。 |

## 1. 参考体系与选择依据

| 参考 | 论文、标准或代码怎么做 | 本项目采用的边界 |
| --- | --- | --- |
| NR / Simu5G | TS 38.300 §4.4 区分 RRC/NAS 控制与用户面 SDAP/PDCP/RLC/MAC/PHY。Simu5G 系统级论文以用户面与可校准的 PHY 抽象为主。后续 SDAP 工作补上 QFI 分类、多 QFI 与 DRB 映射。 | 保留系统级 MAC/PHY 及真实队列，首轮固定接入和会话，验证业务分类、资源动作和归属。 |
| 5G-LENA | Patriciello 等的端到端仿真论文把 BWP、MAC/PHY、时延验证分别校准。官方 NR 模块公开了每 BWP 调度器及 QoS logical-channel 分配接口。 | 独立对照或在引入 BWP、每 UE PRB 保证时参考。当前实验继续使用已验证的 Simu5G fork。 |
| 有线承载 | IETF ACTN 把域能力抽象与多域协调分开。DetNet IP 定义流识别及逐跳 QoS，RFC 9320 给出时延和积压计算框架。UPC 的论文代码提供需求、拓扑、离线路径/排程和逐端口下发的示例。 | 承载域以有向图＋约束选路＋可验证的 IPv4 下一跳为主。Qbv 属于出口队列。UPC 可借鉴控制拆分，TSN 桥移植按需。 |
| 5GC | 3GPP TS 23.501 将 AMF、SMF、PCF 的策略控制与 UPF 用户面分开。N4 PFCP 用 PDR 描述包检测、FAR 描述转发、QER 描述 QoS 执行，URR 描述用量上报。Open5GS 与 free5GC 提供真实的控制面和用户面样例。 | 保留仿真 UPF 及 N3/N6，补必要的规则和反馈接口。首轮认证、会话建立信令及协议互通可用静态会话上下文代替。 |

[3GPP TS 38.300](https://www.etsi.org/deliver/etsi_ts/138300_138399/138300/18.08.00_60/ts_138300v180800p.pdf) · [Simu5G 系统级论文](https://doi.org/10.1109/ACCESS.2020.3028550) · [Simu5G SDAP 论文](https://doi.org/10.1109/CAMAD67323.2025.11229920) · [5G-LENA 论文](https://doi.org/10.1016/j.simpat.2019.101933) · [ACTN RFC 8453](https://www.rfc-editor.org/rfc/rfc8453.html) · [DetNet IP RFC 8939](https://www.rfc-editor.org/rfc/rfc8939.html) · [DetNet 时延 RFC 9320](https://www.rfc-editor.org/rfc/rfc9320.html) · [UPC 微服务控制平面](https://doi.org/10.3390/fi16040120) · [3GPP TS 23.501](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/18.10.00_60/ts_123501v181000p.pdf) · [3GPP TS 29.244](https://www.etsi.org/deliver/etsi_ts/129200_129299/129244/18.10.00_60/ts_129244v181000p.pdf)

## 2. 无线接入域

### 控制面

| 功能 | A100 模块与调用方式 | 本研究的处理 |
| --- | --- | --- |
| 小区、载波、频宽及 numerology | 主场景 `ProjectBookLadder.ned` 的 `CarrierAggregation`。通过 `*.carrierAggregation.componentCarrier[0].carrierFrequency / numBands / numerologyIndex` 初始化。历史 `ex_multi_omnetpp.ini` 有独立的载波配置。 | **首轮显式冻结**。本轮读回主场景默认是 2 GHz、6 个逻辑 band、μ=0。报告注明物理信道带宽假设及 PRB 对应关系，逻辑频带数按模型单位报告。在线调整用下方调度配额。 |
| UE 关联与可达性 | `*.ue[i].nrServingNodeId` 指定初始 gNB，`Binder` 保存标识与可达映射。`cellularNic.rrc` 有 `Registration`、`BearerManagement` 和可选 `nrHandoverController`。后者有 `dynamicCellAssociation`、`enableHandover`、`handoverLatency`。 | **主场景已跑固定关联**。首轮固化 `UE0/gNB1`，将 `ueId/cellId` 作路径兼容约束。若联合选择小区，要单独验证触发、服务小区变更、N3 更新及中断，再把 gNB2 列为同 UE 的可达候选。 |
| DRB 建立及分类策略 | 双端 `cellularNic.hasSdap = true`；`cellularNic.sdap.drbConfig` 提供 `{drb,ue,qfiList,rlcType,isDefault}`，gNB 按 UE 查表，UE 使用本端表。`rrc.bearerManagement` 管理 PDCP/RLC 实体。 | **历史场景已跑，主场景要适配**。本轮主场景 gNB/UE 的 `hasSdap=false`。从 `ext_multiendpoint_test/profiles/profiles_N1.ini` 取表格式，在同一个 IP 日字形用例配置并按本场景查询 UE 注册 ID。静态绑定足够验证首轮，动态 DRB 建立与 RRC 控制另设任务。 |
| 资源配额下发 | `omnetpp_cross_domain.ini` 通过 `*.gnb1.cellularNic.mac.dlSchedulerType` 注入 `ControlledDlScheduler`，用 `initialBandBudget` 设置初值；外部控制可用 `set_ran_dl_budget` 或 `apply_cross_domain` 调 `setBandBudget()`。 | **主场景已跑整小区 DL 限额**。当前固定单载波，限制可用的逻辑 band，覆盖前景、背景和 HARQ grant。适合整小区预算对照。若优化变量是每 UE/切片的最小/最大份额，需在 MAC 添加按 UE/DRB 或切片的预算与分配规则。 |
| RAN 域候选与读回 | `ControllerBridge::observe()` 读取 gNB1 MAC 活跃 CID 的虚拟缓冲合计、当前 band budget、上一个 slot 的分配块数。 | **首轮要补多对象观测**。上报小区级容量、UE→小区关联、按 UE/DRB 的队列/HOL、CQI 或平均速率、HARQ 成本。短期估计从已记录信号或窗口计数生成，避免上报每个 slot。 |
| 流准入与接入层信令 | 固定 UE 的注册/承载在仿真初始化建立。现有日字形控制桥没有为每流执行 RRC 建立和接入准入的外部动作。 | **首轮建轻量可行性检查**。对有效会话、可用 DL 预算及 QoS 映射查表，返回接受或明确拒绝。PRACH、完整 RRC/NGAP、行程移动和真实 CU/DU 拆分按对应研究目标启用。 |

### 数据面

| 功能 | A100 模块与调用方式 | 使用方式与验收证据 |
| --- | --- | --- |
| gNB 下行打标 | `GtpUser::handleFromUdp()` 在解封装后把模型 GTP-U header 中的 QFI 恢复成 `QfiReq`。启用 SDAP 后，`NrSdap::handleUpperPacket()` 查 QFI→DRB 并设置内部承载关联。必要时添加 SDAP header，单 QFI 的 DRB 可按配置省略。 | **历史 SDAP 复跑看到 7→DRB 2**。日字形需启用 SDAP，再做同一 UE 两流、不同 QFI/DRB 的回归。`QfiReq` 是模拟器内部 tag，跨 N3 的依据是封装头里的 QFI。 |
| UE 上行识别与 gNB 向承载标记 | UE 的 SDAP 可接收 `QfiReq`，也有 `useReflectiveQos` 和 `useDscpAsQfiFallback`；后者默认关闭，是实验兼容模式。已用主场景路径可通过 `TrafficFlowFilter` 与 `GtpUser.qfiDscpMap` 发出带外层 DSCP 的包。 | 若上、下行都要研究，应分别配置并验收 UE 的 UL 分类与 gNB N3 egress。统一记录 `(session, direction, inner flow, QFI, DRB, outer DSCP)`。DSCP 表达服务类别，资源块占用用调度统计记录。 |
| PDCP/RLC 队列与可靠性 | `NrNicEnb/NrNicUe` 连接 `pdcpMux` 与由 `BearerManagement` 管理的 RLC 实体；`drbConfig.rlcType` 决定所选模式。默认调度沿用原栈。 | 复用已有模块，明确实验使用 UM 或 AM。记录 RLC 队列/重传与丢包发生层。涉及 AM 重传边界或状态演化时单独验收所选 fork 版本。 |
| MAC、AMC、CQI 和 HARQ | `LteMacEnb.ned` 暴露 `schedulingDisciplineDl/Ul`。当前用 MAXCI，`QOS_PF` 可用 `mac.drbQosConfig`（`{drb,ue,gbr,delayBudget,per,priority}`）；`QoSAwareScheduler` 以配置的 GBR 标识、优先级和 PDB 档加权，再做按 CID/UE 的分配。`ControlledDlScheduler` 复用 grant 逻辑和重传。 | MAXCI 是信道感知基线。启用 `QOS_PF` 后用实际 grant/吞吐验证；表里的 GBR 布尔值和 PDB 权重还需要独立速率、期限约束才能用于硬保证。UL 配额需走另一执行路径，不能引用当前 DL 回读来证明。 |
| PHY/信道与资源遥测 | NR NIC 默认用 `NrChannelModel_3GPP38_901`。载波、信道场景、移动速度和干扰影响 CQI、调制编码与 HARQ。用 `controlledDlAllocatedBlocks`、MAC `avgServedBlocksDl/Ul`、应用时延与 UE/DRB 细分统计。 | 现有模型足够做系统级资源优化。按带宽/频段固定合理配置，对不同 CQI/负载分组，分别量化分配量和有效吞吐。真 RF 波形、波束控制实测及测量噪声接真实 RAN 阶段另验。 |

**现有开放实现。** 同 OMNeT++ 栈优先复用本项目的 RRC/SDAP/MAC。Simu5G 官方 1.7/1.8 文档为集中 `BearerConfigurator`、方向性 QFI 分类和会话控制提供了上游参考，应在独立版本兼容性检查之后选择移植。5G-LENA 的 BWP 与 5QI-aware 调度可用于独立模型对照。真实控制器可考察 srsRAN 的切片 PRB 比率及 Near-RT RIC 教程，具体 KPM/RC 动作及上报周期按选定版本重新核对。[Simu5G 上游变更](https://simu5g.org/neddoc/whatsnew.html) · [5G-LENA 功能](https://cttc-lena.gitlab.io/nr/html/features.html) · [srsRAN PRB 策略](https://docs.srsran.com/projects/project/en/latest/user_manuals/source/config_ref.html) · [srsRAN RIC 接口](https://docs.srsran.com/projects/project/en/latest/tutorials/source/near-rt-ric/source/)

**三种编号需要分开。** `flowId` 是业务稳定标识，QFI 标识某个 PDU Session 内的 QoS Flow，5QI 表示 QoS 特征配置索引，DRB/LCID 供接入层承载与调度。IP DSCP/本地 PCP 用于承载分类，PRB 或逻辑 band 则是分配记录。不能让 QFI、DSCP 或端口号单独承担所有域的流主键。[3GPP TS 23.501 §5.7](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/18.10.00_60/ts_123501v181000p.pdf) · [3GPP TS 37.324](https://www.etsi.org/deliver/etsi_ts/137300_137399/137324/18.00.00_60/ts_137324v180000p.pdf)

## 3. 确定性承载域

### 控制面

| 功能 | A100 模块与调用方式 | 本研究的处理 |
| --- | --- | --- |
| 地址、拓扑与路由发现 | `LadderBackbone.ned` 使用 6 个 INET `Router` 和 `Ipv4NetworkConfigurator`。现有配置以初始化路由为基线。用 `dumpTopology/dumpLinks/dumpRoutes` 核对节点、接口和初始化路由。 | **主场景已跑静态发现**。加一个针对控制器的有向快照，字段包括 `nodeId, interfaceId, peerId, bitrate, propagationDelay, up/down`。直接读取 INET 拓扑/接口即可，首轮无需部署 LLDP、BGP-LS 或独立拓扑服务。 |
| 约束选路与资源准入 | 当前 `ControllerBridge` 只有 NE1 单端口 Qbv 动态动作，没有可执行的路径动作。INET 有目的前缀路由表。 | **首轮要补**。当地承载控制器先按固定起止端点生成可行候选，筛掉断链、容量不够和超预算路径，再把有序出口、拥塞代价和剩余容量提交 GCC。小拓扑可枚举简单路径作真值，规模扩大后可用 Yen K 短路、约束最短路或多商品流。 |
| 路径下发及回读 | INET `Ipv4NetworkConfigurator.config` 支持 XML `<route>`。运行期可复用 `Ipv4RoutingTable::addRoute/deleteRoute` 与查表，必要时用 INET IPv4 netfilter 分类及下一跳路径能力做适配。 | **先静态、后在线**。第一个对照为同一 gNB 的两条明确下一跳。随后加小型执行器核对相邻、接口状态和每跳路由，回执显式列出实际下一跳与版本。目标匹配为外层 gNB IP 时，要按 N3 外层粒度报告。 |
| 逐流选路 | RFC 8939 允许按外层 IP 五元组加 DSCP 识别。当前承载的分类是从外层 DSCP 得到队列类别，IPv4 路由表按目的地址匹配。 | **同一 N3 外层目的独立分流时要补**。给选路规则匹配可见且稳定的标识，先做两个隧道或两个可区分的外层类。相同外层五元组、同 DSCP 时，需要在入口建立可区分标记或绑定到明确的封装/策略。单 gNB 选路用例可先按同一隧道整体转向，日志明确粒度。 |
| 队列与接口资源配置 | 现有 `set_ne_gate` 针对 `NE1.eth[1]`。`QbvPort` 调 `PeriodicGate.durations`，周期 5 ms，两窗口，限制整周期边界且使用全局仿真时钟。 | **主场景已跑单端口**。首轮选路冻结门表；若将逐端口队列配额加入优化，先扩展目标接口索引和候选可验证容量。独立本地时钟、多端口 GCL 与共享时刻提交按同步实验需要加。 |
| 故障、剩余容量和切换 | `Ipv4NetworkConfigurator.updateRoutes` 默认为 false。INET 可读取接口/链路状态和队列信号；实验用 pcap 和逐包延迟已具备。 | 为动态选路补链路状态上报、存活验证及同一版本下的读回。对断链和拥塞分别比较；记录生效前后走过的路径、瞬态丢包及恢复时间。保留 `routeId` 与 `generation`，避免把旧路由读回作新策略证据。 |

### 数据面

| 功能 | A100 模块与调用方式 | 使用方式与验收证据 |
| --- | --- | --- |
| IPv4 转发和链路模型 | Router 用 INET IPv4、路由表、以太网/PPP；`ProjectBookLadder` 的 N3 两侧是 PPP，域中间是以太网。 | **现成复用**。在每个有向出口采集实走流和接口序列。固定源终点和包序号，确认中间节点不同，同时核对返回方向路径。 |
| 分类、打标与排队 | `routed-queues.ini` 将 `eth[*].egressTC.typename` 配成项目 `DscpToPcpMarker`，将外层 46/34→本地 PCP 5/4，其他进入 BE。`eth[*].queue.typename` 设 `Ieee8021qTimeAwareShaper`，分类器按 PCP request 分到 2/1/0 三队列。 | **主场景已跑**。PCP request 属于仿真内部队列标记。抓包用于核对外层 DSCP，队列统计用于核对真正进入的队列；原生 VLAN tag 只在需要二层互联时启用。 |
| 调度、整形、监管和拥塞保护 | `RoutedPriority` 为既有队列常开，`RoutedTas` 加 GCL。INET 还有 token-bucket meter、分类/过滤及流量整形模块。 | **先复用现有队列**。明确整形是等候、监管可丢弃，区分带宽限制与预留。对于多流资源可行性，用实测速率和收发曲线核定容量；需要硬时延上界时额外配置流包络并用 DetNet 模型推导。 |
| 逐跳可测性 | `pcapRecorder`、`queueLength/queueingTime`、门状态和应用时间戳；`experiments/exp/competition_trace.py` 与现有 KPI 工具。 | 记录 `packet sequence → flowId → tunnel class → routeId → per-hop events`。至少保存 ingress、egress、drop、界限时延和方向。链路利用率与队列等待属于路径候选的重要依据。 |

**开放实现。** 仿真优先用 INET 的静态路由和运行期路由表；已有队列及 policing 可复用。GCC/承载控制器可用 [NetworkX 的 K 条简单路径](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.simple_paths.shortest_simple_paths.html) 生成候选，再做容量和时延筛选。真实路由端可以用 FRRouting PBR 或 SRv6 静态 segment list 验证执行。只有论文明确声称 SRv6 协议行为时，才需要验证 SID/SRH、流引流和真实设备回读。[INET IPv4 配置器](https://github.com/inet-framework/inet/blob/v4.6.0/src/inet/networklayer/configurator/ipv4/Ipv4NetworkConfigurator.ned) · [INET 队列和监管](https://inet.omnetpp.org/docs/showcases/tsn/streamfiltering/tokenbucket/doc/index.html) · [FRR PBR](https://docs.frrouting.org/en/latest/pbr.html) · [FRR SRv6 静态路由](https://github.com/FRRouting/frr/blob/master/doc/user/static.rst) · [SR Policy RFC 9256](https://www.rfc-editor.org/rfc/rfc9256.html)

## 4. 核心网域

### 控制面

| 功能 | A100 模块与调用方式 | 本研究的处理 |
| --- | --- | --- |
| AMF 注册、鉴权、安全及 NAS/NGAP | 主场景 NED 实例是 `Upf`，不实例化 AMF/SMF/PCF。现有 Binder/UE/RRC 初始状态可用来模拟预接入用户。 | **首轮用静态有效会话**。注册成功、固定 UE 及可达小区作为输入。若研究切换中断、会话生命周期、真实 UE 注册或控制接口互通，使用开源核心网的真实信令。 |
| SMF 会话、UPF 选择、N4 规则 | `TrafficFlowFilter::findTrafficFlow()` 按地址和 Binder 解析服务节点，`GtpUser` 用该目标送包。检查到项目 A100 的此实现将模型头的 TEID 设置为 0，依赖模拟的映射。主场景只有一个双网口 UPF。 | **首轮要补会话/出口的模型级表**，能从已知 UE、方向到可用 N3 出口并记录选中的出口。真正的多 UPF 选择、会话迁移、每会话 TEID、PFCP 请求/响应均属额外研究条件。现有单 UPF 的变动作应表述为“出口/限速”，与 UPF 选择分开。 |
| PCF/SMF 的 QoS 策略与 QFI 分配 | 当前 `TrafficFlowFilter.cc` 使用 `Qfi(ipv4Header->getDscp())`。`GtpUser.qfiDscpMap` 可配置外层打标，默认取 QFI 值。历史 profile 的 DRB QoS 是配置数据。 | 保留旧映射用于复现；**主实验增加业务类或五元组→会话内 QFI→QoS profile/外层类**显式表，供日字形接入 SDAP。首轮表可静态装载；需 GCC 变更业务优先级时再开放受控更新。 |
| 业务规则、配置事务及观测 | `ControllerBridge::parseUpdate/execute` 能解析外部 `set_upf_rate` 与联合动作，`FlowPolicer::setRateBps()` 改速后回读。`request_id/base_generation` 检查属于同一仿真进程的协议。 | **主场景已跑单流动作**。后续按 `session + flow + direction` 选择规则对象，返回接受/拒绝、实际生效版本及计数。保留可重复请求的幂等性。外部 SMF/PFCP 或多设备失配测试才需要跨设备事务和失败恢复。 |
| 跨域状态与计费 | 当前可读 token-bucket 的 admitted/dropped IP bytes/packets、配置速率和应用交付。 | **首轮够做速率与损失基线**。将 N6 入速率、各 N3 出口实际字节、队列/速率和承载约束分开。URR 级用量触发及计费不进入路径决策的首轮模型。 |

### 数据面

| 功能 | A100 模块与调用方式 | 使用方式与验收证据 |
| --- | --- | --- |
| N6 入站、流识别和 N3 封装 | `Simu5G/src/simu5g/nodes/Upf.ned` 接 `dnPpp.upperLayerOut → trafficFlowFilter → gtp_user`。`TrafficFlowFilter` 生成 `TftControlInfo`，`GtpUser::handleFromTrafficFlowFilter()` 封装并选择目的 gNB。 | **主场景已跑**。对比 N6 内层五元组、N3 外层、gNB 解封装及 UE 接收。A100 现有捕获的模型 GTP 使用 UDP 31，和设备实际 N3/GTP-U 抓包规则分开记录。 |
| N3 解封装、上行流与双向 | `GtpUser::handleFromUdp()` 还原 QFI 到包 tag，按 UPF 或 gNB 角色分发。两个 gNB 的双向轻载已有 EXP-08 证据。 | **现成复用**。对齐业务方向，验证核心动作是否只作用于设计的上下行。显式的 per-session PDR/FAR/QER 尚缺，方案内按规则语义抽象即可。 |
| 限速与队列 | `omnetpp_controller.ini` 通过 `*.upf.dnPpp.ingressTC.typename` 安装 `FlowPolicer`，用 `expr(has(ipv4) && has(udp) && udp.destPort == 6202)` 选背景流。令牌不足时丢弃，开放 `initialRate / burstSize` 与运行时速率。 | **主场景已跑**。若需要缓冲并平滑发送，可用 INET shaper 替代丢包型 policer。若要每流 GFBR/MFBR 的保证，需分开写速率、方向、队列与过载处置，不能从现有背景限速推得保证。 |
| 外层 DSCP 标注 | `**.gtpUser.qfiDscpMap`（gNB）与 `**.gtp_user.qfiDscpMap`（UPF）；`GtpUser` 加 `DscpReq`，INET IPv4 封装写 DS 字段。已有显式置零对照。 | **主场景已跑**。记录内层应用类、会话 QFI、外层 DSCP 和出口分类，验证 6202 以外的业务不被误限。多业务共享 QFI 或 DSCP 的边界依业务合同记录。 |

**开放实现。** Open5GS 的 SMF 源码可查看 QoS 决策、UPF 选择及 PDR/FAR/QER 规则建立。free5GC/gtp5g 是另一套 5GC 和 Linux GTP 用户面实现。要测试 N2/N4 互通可另建 Open5GS 或 free5GC 与 UERANSIM 的协议用例；UERANSIM 的部分空口由 UDP 模拟，验证 PRB/BWP 仍用系统级仿真或 srsRAN 真栈。在 A100 当前主实验中先复用现有仿真用户面，避免把真实协议栈启动、配置和实时性混进优化基线。[Open5GS](https://github.com/open5gs/open5gs) · [Open5GS SMF 的规则入口](https://github.com/open5gs/open5gs/blob/main/src/smf/npcf-handler.c) · [free5GC](https://github.com/free5gc/free5gc) · [gtp5g](https://github.com/free5gc/gtp5g) · [UERANSIM](https://github.com/aligungr/UERANSIM)

## 5. 三域共用的实验接口

### 可调用的现有接口

运行 `experiments/exp/ladder_controller.py`，通过 `--policy module:function` 替换算法。外部 Python 接收换行分隔的 JSON `observation`，回调返回已有动作或 `None`。包装器将其放入含 `version/request_id/base_generation` 的 `decision`，然后读取 `ack`。当前目标范围由 `ControlledCompetition.ned` 和 `omnetpp_cross_domain.ini` 固定。在 C++ 侧分别由 `FlowPolicer`、`QbvPort` 和 `ControlledDlScheduler` 执行，仿真结果写入 `control.jsonl`。现有代码在等待回复期间暂停仿真时间。真实的跨域状态老化、策略迟到和通信耗时，需要明确建模上报、下发及生效事件。

~~~json
{"type":"apply_cross_domain","rate_bps":2000000,"priority_window_us":1600,"bands":6}
~~~

上面是当前有效的 **回调返回值**。三项依次落到 UPF 背景流、NE1.eth[1]、gNB1。此接口没有 `routeId`，也没有选择另一 gNB 或另一个会话的动作。`experiments/docs/schema/{flow-contract,observation,policy-set}.schema.json` 可延续为设计参考；当前 TCP 协议使用自己的版本 1 消息。

### 后续域接口的数据合同

下表是后续实验的字段与语义，调用名称为拟定接口。先保留完整的未压缩消息并给每个域一套独立的配置生效和拒绝条件，再考虑分块编解码。

| 接口 | 无线域 | 承载域 | 核心网域 |
| --- | --- | --- | --- |
| 能力与观测 `snapshot` | `cellId, ueId, direction, carrierId`，band/PRB 总量与已用量、队列/HOL、CQI、HARQ、可达小区 | 有向链路状态、接口和出入边界，bps 容量/占用、队列、传播时延、已安装路径和版本 | `sessionId, ueId, direction, UPF`，绑定的 N3 区域/出口、可用 QoS profile、限速与收发计数 |
| 受约束生成候选 `propose` | 在调度预算内，返回可交付速率/时延与资源代价、服务小区 | 在给定边界、最小带宽和时延预算下返回路径 ID、有序下一跳、拥塞风险和成本 | 在待选会话/出口与带宽条件下，返回 QFI、外层类、可用出口、速率与成本 |
| 动作下发 `apply` | 对确定的 `cellId/carrierId/direction` 配置预算，细粒度实验另加 UE/DRB | 对确定的 `flow/tunnel selector` 安装/替换明确下一跳，核对接口与作用范围 | 对确定的 `session+flow+direction` 应用分类、标记、限速或出口策略 |
| 读回及验证 `ack + trace` | 实际档位、首个用新版本的 slot、按 UE/DRB 的 RB 与应用交付证据 | 实际 FIB/下一跳、首个走新路径的包、丢包与循环/黑洞检查 | 当前规则版本、实际 N3 出口与外层 DSCP、生效时间和 admitted/dropped |

所有观测携带 `observedAtNs, receivedAtNs, validUntilNs, generation` 及时间域。对 RAN 与核心网传回的不同量纲资源分别约束，在有正式定义时才换算为共同成本。候选应包括明确的不可行原因，例如无可达小区、承载链路失效、会话绑定不一致、预测带宽不足。GCC 组合时检查入口/出口、小区、PDU Session 的相容性及共享链路容量。应用侧用 `flowId + packet sequence` 关联跨域证据，对失踪包给出最后观察层。不同域的 P99 不能直接相加；端到端 P99 用应用逐包记录重算。

建议采用以下顺序固化实验基础。

1. **先做一流的完整闭环。** 固定 UE0/gNB1 和静态会话，先用两个明确 IP 下一跳复跑路径。在日字形添加有 SDAP 的场景配置，核查业务标识、QFI、DRB、外层 DSCP 与队列一致。无线整小区 DL 配额及 UPF 限速继续用已验证模块。
2. **再做两流可区分与三域候选。** 给两流设置明确业务选择器，在同一 UE 共享资源时核对分类、期限和竞争。承载控制器给候选路径与剩余容量，无线控制器给可行频带预算，核心控制器给合法出口与业务速率。GCC 用完全观测和有限枚举作参考。遇到实际要按流限制 PRB 份额或同隧道选不同路径时，才增加细粒度执行器。
3. **最后做变化与学习。** 先观察拥塞、断线、陈旧状态是否影响选路或 SLA；如果实验问题包括服务小区或会话迁移，再上移动性与真实会话状态。域接口和未压缩基线冻结后训练无线、承载、核心的分块编码与解码，再评估跨域对齐、决策差距和信令成本。

## 6. 本轮回放核验

| 运行 | 核查证据 | 能支持的结论 |
| --- | --- | --- |
| `Hetero_N1`，run 0，65 ms | `NrSdap` 日志实际出现 `QFI=7 → DRB=2`，接收端从 DRB 2 收到 IPv4 包。配置为双端启用 SDAP。 | 历史场景可复用 SDAP 绑定。主日字形需要接入配置并逐流对照。 |
| `E2ePriority / E2eZeroOuterDscp`，run 0，170 ms | NE1 以太网捕获的模型 UDP/31 包分别为 2 个 DSCP 46、2 个 34、1 个 0，以及置零组 5 个 DSCP 0。对应外层 ToS 为 0xb8、0x88、0x00。 | UPF/gNB 至承载外层标记和置零对照可复跑。抓包不足以单独证明无线 DRB 或任何预留。 |
| `run_ladder_controller.sh --cross-domain`，四组完整回放 | `CrossDomainExternal` 第一次联合生效在 620 ms，回执 UPF 2 Mbit/s、NE1 高优窗口 1600 μs、gNB1 预算 6。统计中 band 预算 4/6 档观察到最大分配块数分别为 4/6，所选窗口 80 个控制包均交付，P99 为 11.420 ms。 | 三域动作已走到真实仿真模块。该基线固定了业务路径，结果用于接口验证。 |

A100 读取环境以 `handoff/01-环境与登录.md` 为准，先完成 `make -C nascTime -j4`。以下命令从各场景目录运行，建议产物写入独立的临时目录。三个实验分别使用现有配置，未修改代码或原场景。

~~~bash
# nascTime/simulations/demos/ext_multiendpoint_test
out=$(mktemp -d)
set -o pipefail
../../../bin/nasctime-run.sh -f ex_multi_omnetpp.ini -u Cmdenv -c Hetero_N1 -r 0 \
  --sim-time-limit=65ms --warmup-period=0s --cmdenv-express-mode=false --cmdenv-log-level=INFO \
  '--**.vector-recording=false' "--result-dir=$out" 2>&1 \
  | LC_ALL=C grep -aE 'SDAP TX:|SDAP RX:|Error:|^End' > "$out/sdap.txt"

# nascTime/simulations/demos/e2e_ladder
out=$(mktemp -d)
for cfg in E2ePriority E2eZeroOuterDscp; do
  ../../../bin/nasctime-run.sh -f omnetpp_qos.ini -u Cmdenv -c "$cfg" -r 0 \
    --sim-time-limit=170ms "--result-dir=$out/$cfg"
  tcpdump -nn -v -r "$out/$cfg/"*NE1.pcap 'ip and udp port 31'
done

# 仓库根目录
bash experiments/exp/run_ladder_controller.sh --cross-domain
~~~

### 源码定位

| 要找的实现 | 路径 |
| --- | --- |
| 主场景、资源注入、包标记对照 | `nascTime/simulations/demos/e2e_ladder/{ProjectBookLadder.ned,LadderBackbone.ned,omnetpp_cross_domain.ini,omnetpp_controller.ini,omnetpp_qos.ini,routed-queues.ini}` |
| 三域控制和设备适配 | `nascTime/src/nasctime/control/{ControllerBridge.cc,ControlledDlScheduler.cc,QbvPort.cc,FlowPolicer.cc}` |
| 本地 SDAP、RRC、调度和 QoS 数据 | `Simu5G/src/simu5g/stack/rrc/Rrc.ned`、`stack/sdap/NrSdap.{ned,cc}`、`stack/mac/LteMacEnb.ned`、`stack/mac/scheduling_modules/QoSAwareScheduler.cc`（后一组路径从 `Simu5G/src/simu5g` 起） |
| UPF、分类、GTP 与外层 DSCP | `Simu5G/src/simu5g/nodes/Upf.ned`、`corenetwork/trafficFlowFilter/TrafficFlowFilter.cc`、`corenetwork/gtp/GtpUser.{ned,cc}`（后一组路径从 `Simu5G/src/simu5g` 起） |
| IPv4 路由与接口局部实现 | `inet/src/inet/networklayer/configurator/ipv4/Ipv4NetworkConfigurator.ned`、`inet/src/inet/networklayer/ipv4/{Ipv4.cc,Ipv4RoutingTable.h}` |
| 对照报告及实验入口 | `experiments/docs/exp-08-routed-ladder-validation.md`、`exp-09-e2e-downlink-competition.md`、`exp-11-cross-domain-execution.md`、`exp-12-background-delivery-audit.md`、`exp-13-pareto-reporting.md`（同目录）；`experiments/exp/{ladder_controller.py,competition_trace.py,run_ladder_controller.sh}` |

三层选路的研究假设与对照顺序另见 [三层路径规划与跨域联合优化方案](l3-cross-domain-optimization-plan.md)。本文为复用审计和接口设计，表中的新增功能仍需按各域实际可观察条件验证。
