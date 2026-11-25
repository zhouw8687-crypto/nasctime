# QoS 映射等级速查

**先记住四句。包是一次发送的数据单位。流是一组被同一条规则识别的包。QFI 标识 5G QoS 流，DRB 承载这批包走无线空口。承载网按看得到的标记分队列，路径和资源由各域控制器配置。**

## 1. 一个包、一条流分别是什么

**包（Packet）。** 假设服务器每 5 ms 给终端发一条 200 字节的控制消息。每次发送时，应用数据是 **Payload（有效载荷）**。UDP 在前面加 UDP 头，IPv4 再加 IP 头。这里的一条控制消息对应一个 UDP 数据报和一个 IP 包。IP 头写源和目的 IP，UDP 头写源和目的端口。收到包后，终端凭目的 UDP 端口把数据交给相应应用。本例假设包足够小，途中无需分片。

**流（Flow）。** 同一个服务器向同一个终端重复发送时，如果这些包共享同一个方向上的**源 IP、目的 IP、源端口、目的端口和传输协议**，就能按 **Five-tuple（五元组）**识别为一条流。比如服务器从 UDP 6201 发到终端 UDP 6200，每 5 ms 发一个包，发 100 个包仍可属于同一条流。视频也发给同一终端，但目的端口用 6204，可以作为另一条流。端口号可以由仿真配置指定，6200 和 6204 的业务含义来自本项目的约定。

**业务流和 5G QoS Flow（5G QoS 流）。** 项目的 `flowId` 用来关联业务参数、日志和端到端指标。五元组或端口规则用于识别包应归哪个 `flowId`。具有相同服务需求的多个业务流可以映到同一个 5G QoS Flow，多个 QoS Flow 也可以共享一个 DRB。要单独测某条业务的到达率，用 `flowId + packet sequence（包序号）`核对发送和接收。需要独立的资源待遇时，再检查业务是否确实进了不同的无线承载或承载队列。

[IETF DetNet IP 的流识别](https://www.rfc-editor.org/rfc/rfc8939.html) · [3GPP TS 23.501 §5.7 的 QoS Flow](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/18.10.00_60/ts_123501v181000p.pdf)

## 2. 英文原名和记法

| 缩写 | 英文原名 | 在这里记什么 |
| --- | --- | --- |
| IP | Internet Protocol | IP 头携带源、目的地址，路由器据此转发。 |
| UDP | User Datagram Protocol | UDP 头携带源、目的端口，接收端用端口把数据交给应用。 |
| RAN | Radio Access Network | 无线接入网，包括基站及其接入侧控制和传输功能。 |
| QoS | Quality of Service | 服务质量。实验里具体写成时限、按期送达率、吞吐等要求。 |
| PDU Session | Protocol Data Unit Session | UE 通过 5G 系统接入数据网络的会话。一个会话可以有多个 QoS Flow。 |
| QFI | QoS Flow Identifier | **本会话里的 QoS 流编号**。不同会话里的 QFI 1 可以有不同的业务含义。 |
| 5QI | 5G QoS Identifier | **QoS 特征索引**。用来引用优先级、包时延预算等特征。QFI 回答“是哪条 QoS 流”，5QI 回答“采用哪类 QoS 特征”。 |
| SDAP | Service Data Adaptation Protocol | **在无线侧根据 QFI 选 DRB**，接收时恢复对应的 QoS 信息。 |
| DRB | Data Radio Bearer | **数据无线承载**。业务通过 DRB 进入后续的无线协议和调度流程。 |
| DSCP | Differentiated Services Code Point | **IP 包头里的服务标记**。承载网的分类器可以读外层 IP 的 DSCP 给包分队列。 |
| PCP | Priority Code Point | **以太网 VLAN 的优先级字段**。当前 INET 场景也用同样的数值作本地队列分类标记。 |
| UPF | User Plane Function | **核心网用户面转发模块**。下行在 UPF 侧识别业务并送进 N3 隧道。 |
| GTP-U | GPRS Tunnelling Protocol for the User Plane | **用户面隧道封装**。在 N3 上把原来的应用 IP 包装到外层 UDP/IP 里面。 |
| gNB | gNodeB | **5G NR 基站**。在这里接收 N3 隧道包，再把业务发往终端。 |
| UE | User Equipment | **用户终端**。比如手机、工业终端，或仿真里的 `ue[0]`。 |
| N3 | Reference point between the (R)AN and the UPF | **基站侧接入网与 UPF 之间的用户面接口**。本项目的日字形承载网运送这段 IP 隧道流量。 |
| SLA | Service Level Agreement | **服务等级协议**。实验用它表示应达到的时限、按期送达率或带宽目标。 |

[3GPP TS 23.501](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/18.10.00_60/ts_123501v181000p.pdf) · [SDAP 规范 TS 37.324](https://www.etsi.org/deliver/etsi_ts/137300_137399/137324/18.00.00_60/ts_137324v180000p.pdf) · [DSCP 定义 RFC 2474](https://www.rfc-editor.org/rfc/rfc2474.html)

## 3. 一条下行控制包怎么经过三域

下行方向是 **服务器 → 核心网 UPF → 日字形承载网 NE → 基站 gNB → 终端 UE**。以目的端口 6200 的控制包为例。

1. **服务器发原始 IP 包。** UDP 目的端口填 6200，内层 IP 的 DSCP 可以是 0。视频包也可以使用内层 DSCP 0，靠不同的目的端口来区分。
2. **UPF 按包分类并封装。** `dlQfiRules` 可以用 UDP 目的端口 6200 匹配控制流，给它分配 QFI 1。N3 封装相当于在原始 IP 包外再加上 GTP-U、UDP 和 IP 头。内层 IP 头的 DSCP 与外层 IP 头的 DSCP 是两个字段，可以分别设置。
3. **承载网按外层头转发并分队列。** 可以在隧道入口按业务策略给控制类写外层 DSCP 46，给视频类写外层 DSCP 34。路由器在本项目中按外层目的 IP 选择下一跳，在选中的出口按外层 DSCP 分到相应队列。队列是包等待发出的地方。该出口的容量和调度方式决定服务能力。
4. **gNB 解封装并发往 UE。** 基站恢复内部的 QFI。SDAP 用表把 QFI 1 映到 DRB 1。无线调度器再为在缓冲区等待的业务分时隙和频带。UE 收到原始应用数据，应用按包序号和时间戳统计交付。

~~~text
外层 IP（承载网读 DSCP） | 外层 UDP | GTP-U（仿真内部保存 QFI） |
    原始 IP（应用的内层 DSCP） | 应用 UDP（目的端口） | 应用数据
~~~

**可以分开记两条映射。** 无线侧是 `QFI → DRB → 无线调度`。承载侧是 `业务策略 → 外层 DSCP → 出口队列`。路径、门控、出口容量和无线分配还要各自配置。某个 DSCP 数值也不意味着那个包一定先发，实际结果取决于各节点执行的队列策略和当时负载。

粗略区分几个常见动作。**Classification（分类）**是按规则认出业务，**Marking（打标）**是把服务类别写入包头或模型内部标记，**Routing（路由）**是选择下一跳，**Scheduling（调度）**是决定什么时候让哪批数据使用资源。**TAS（Time-Aware Shaper，时间感知整形器）**用门表决定哪些出口队列在哪些时段可以发送，项目中也常简称 Qbv。[INET TAS 示例](https://inet.omnetpp.org/docs/showcases/tsn/trafficshaping/timeawareshaper/doc/index.html)

## 4. 基本等级例子与当前状态

| 例子 | 业务识别 | 无线侧的示例绑定 | 承载侧的项目配置 |
| --- | --- | --- | --- |
| 控制关键流 | 下行 UDP 目的端口 6200 | QFI 1 → DRB 1 | 外层 DSCP 46（EF，Expedited Forwarding）→ 本地 PCP 5 → 高优队列 2 |
| 视频竞争流 | 下行 UDP 目的端口 6204 | QFI 3 → DRB 2 | 外层 DSCP 34（AF41，Assured Forwarding Class 4、Drop Precedence 1）→ 本地 PCP 4 → 中优队列 1 |
| 普通背景流 | 按场景的背景流规则 | 按会话的默认 QoS Flow 配置 | 外层 DSCP 0 → 默认 Best Effort（尽力而为）队列 0 |

上表把两个已验证的模块接法放在一起方便记忆。**无线侧**来自 Simu5G 1.7 独立验证；**承载侧**来自日字形已有的 `DscpToPcpMarker` 和 `routed-queues.ini`。日字形的 PCP 值在这里是 INET 内部请求标记。表里的组合是项目拟沿用的策略，后续需要把独立验证的 QFI 分类接到日字形并逐跳核对。运营策略可以选别的 QFI、DSCP 和队列映射。

[EF 的 RFC 3246](https://www.rfc-editor.org/rfc/rfc3246.html) · [AF 的 RFC 2597](https://www.rfc-editor.org/rfc/rfc2597.html)

### 之前那段实验结果怎么读

- **应用包 DSCP 都是 0。** 在入网时，控制和视频在内层 IP 的服务标记相同。端口不同，所以两条规则还是能分别找到它们。
- **按端口分到了不同 QFI 和 DRB。** UPF 把控制、视频分别分给 QFI 1 和 3；SDAP 再把它们放入 DRB 1 和 2。说明当前规则能区分无线侧的两种业务。
- **只交换上行规则，只有上行映射交换。** 上行是 UE 向服务器发，`ulQfiRules` 在 UE 栈入口判断。下行是服务器向 UE 发，`dlQfiRules` 在 UPF 判断。两套规则作用位置和方向独立。
- **N3 抓包外层 DSCP 全是 0。** 独立验证的 Simu5G 1.7 已经在模型内部给包分配了 QFI，但这次 N3 封装后的 IP 包统一带 DSCP 0。拿日字形的接口策略来分类时，这些外层包会进入同一默认类。要让它们进不同承载队列，还要把 QFI 或 QoS profile 映射为不同的外层 DSCP，再验证出口队列。这个例子的 QFI/DRB 由仿真日志核对，PCAP 用于核对外层 DSCP。

[Simu5G 分类规则](https://simu5g.org/neddoc/types/simu5g.corenetwork.bearerConfigurator.BearerConfigurator) · [A100 实验报告](exp-16-simu5g17-qfi-rules.md)

## 5. 首轮实验只做下行

先固定同一个 UE、同一个 gNB、同一套业务到服务等级的映射。控制关键流和视频或背景竞争流都从服务器发往 UE。只要它们在某个出口或无线小区共享资源，就能测试竞争。核心网和无线协议所需的信令、反馈继续由仿真框架处理。后续做感知上报和控制下发的业务闭环时，再把上行业务与对应下行用同一个 `eventId` 关联。

| 对照 | 实际允许改变的动作 | 要回答的问题 |
| --- | --- | --- |
| 固定最短路 | 固定路径、初始资源和共享队列基线 | 当前业务竞争会带来多少超时和吞吐变化？ |
| 固定路径加队列隔离 | 路径保持一致，用同一份分类映射让关键流和竞争流进不同队列 | 队列隔离本身带来多少改善？ |
| 路径与资源联合优化 | 允许全局控制器 GCC 从可行路径中选路，并协调无线预算和承载侧资源 | 满足关键流按期送达率要求后，能交付多少竞争流数据、消耗多少资源？ |

每组用同一业务量、竞争条件和随机种子。**按期送达率 = 截止时间前收到的关键包数 ÷ 发送的关键包数。** 例如发 100 包，97 包按期、1 包晚到、2 包丢失，按期率是 97%，总送达率是 98%。同时记录竞争流的应用吞吐，以及链路容量占用、无线频带分配和队列情况。

日字形复用基础见[三层主实验方案](l3-cross-domain-optimization-plan.md)与[原生路由和 SDAP 回归](exp-15-native-ladder-reuse.md)。
