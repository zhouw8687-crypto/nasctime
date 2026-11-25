# INET 和 Simu5G 原生能力复用与回归

本轮在 A100 的日字形拓扑上用原生模块补了三类基线。INET 配置器安装指定 IPv4 路径，ScenarioManager 配合原生静态路由重算做断链恢复，Simu5G 的 SDAP、DRB 表和 QOS_PF 做下行流分类及调度。新增内容是 INI、XML 和 NED 场景配置，使用项目现有的 OMNeT++ 6.4、INET 4.6 和 Simu5G 1.5 基线。

## 可复用能力和适配边界

| 缺口 | 已找到的原生实现及使用方式 | 本轮验证结果 |
| --- | --- | --- |
| 同一 gNB 的显式 L3 路径 | INET `Ipv4NetworkConfigurator.config` 载入 `<route hosts=… destination=… gateway=… interface=…>`，用 `/32` 路由控制相同 N3 终点。 | `ReuseDirect` 和 `ReuseDetour` 的实际 GTP-U 包走了不同的有序路由，终点仍是 gNB1。 |
| 断链触发重路由 | INET `ScenarioManager` 做双向断链，`Ipv4NetworkConfigurator.updateRoutes=true` 根据接口状态重新计算路线。 | `ReuseLinkFailover` 在 700 ms 断开 NE3–NE5，后续流量改走 UPF→NE2→NE4→NE6→NE5→gNB1。 |
| QFI→DRB 以及优先级 | Simu5G 1.5 用 `hasSdap=true`、`sdap.drbConfig` 开启下行映射。用 `mac.schedulingDisciplineDl="QOS_PF"` 和 `mac.drbQosConfig` 激活原生加权调度。 | 两个小区下行都有 46→DRB 1、34→DRB 2、0→DRB 0。QOS_PF 记录的三类权重分别为 50、7.5、5。 |
| 上下行独立分类 | Simu5G 1.7 提供 `BearerConfigurator.dlQfiRules/ulQfiRules`，依据方向分别在 UPF/UE 按包规则分配 QFI。新版文档还有 `QosFlowClassifier`，供 UE 侧执行规则。 | 当前 A100 的 1.5 fork 中，上行在打开 `useDscpAsQfiFallback` 后仍进默认 DRB 0。该分支读取 `FlowControlInfo` 的 ToS，当前 IP→NIC 路径未写入该字段。候选是单独验证上游带规则的场景，之后择版本移植或适配。 |
| 外部 GCC 的按流/隧道路径动作 | INET 有 `Ipv4RoutingTable::addRoute/deleteRoute` 和查表接口，同时有已有 pcap/队列观测。 | 本轮采用原生静态配置和拓扑事件重路由，外部 GCC 尚未接入路径安装。未来接口可复用 INET 路由表；如果同一 N3 隧道、同外层类别的两条业务需要走不同路径，需先建立可区分的外层选择条件。 |

[INET 手工路由官方教程](https://inet.omnetpp.org/docs/tutorials/configurator/doc/step5.html) · [INET 路由配置器源码](https://github.com/inet-framework/inet/blob/v4.6.0/src/inet/networklayer/configurator/ipv4/Ipv4NetworkConfigurator.cc) · [INET ScenarioManager 源码](https://github.com/inet-framework/inet/blob/v4.6.0/src/inet/common/scenario/ScenarioManager.cc) · [Simu5G 1.5.0](https://github.com/Unipisa/Simu5G/releases/tag/v1.5.0) · [Simu5G 1.7.0](https://github.com/Unipisa/Simu5G/releases/tag/v1.7.0) · [上游 BearerConfigurator](https://simu5g.org/neddoc/types/simu5g.corenetwork.bearerConfigurator.BearerConfigurator) · [Simu5G 1.8.0](https://github.com/Unipisa/Simu5G/releases/tag/v1.8.0)

## 实验原理与参数

四组均继承 `E2ePriority` 的小流量，两个 gNB、两个 UE、双向各三类，应用 UDP 负载 200 B、周期 100 ms、运行 2 s、run 0。保留轻载是为了控制队列竞争，只验证路径和分类模块是否工作。已有的运行时下行频带预算和 UPF 令牌桶保持在各自的基线用例；`ReuseQosPf` 组单独验证按 DRB 实际取调度权重。

- **指定直行与绕行。** 固定 UE、小区、应用和 N3 下行目的地址，在同一个拓扑上选择左纵路和右侧绕行。XML 用 `gnb1%cellular` 明确匹配 N3 外层目标，NE5 最后一跳的直连网关用 `gnb1%pppIf`。
- **有线断链。** 在使用原生自动路由的同一拓扑于 700 ms 断开 NE3–NE5，记录前后抓包和终端收包。断链组固定 IP 地址，设置 `assignDisjunctSubnetAddresses=false`，使断开的两端保留原 /30 地址。诊断中直接用自动分配会改变隧道端点，gNB1 侧目标由 10.0.0.49 变为 10.0.0.57，该组的一条 UE0 下行流仅收到断链前的 6/16。固定端点后恢复完整交付。
- **无线分类和调度。** 根据 SDAP 日志分区核对 gNB/UE 各自的 QFI 和 DRB，再从 MAC 日志确认载入并使用配置的权重。下行的 50/7.5/5 是本场景参数计算的权重，保留为执行证据。带宽保证、时延门槛与争用下收益还需要高负载对照。N3 外层 DSCP 仍可在上行出现 46/34，描述的是承载分类，无法用于证明 UE 的上行无线 DRB 已分离。

## 实测结果

| 配置 | gNB1 的下行承载路径 | 应用交付 |
| --- | --- | --- |
| `ReuseDirect` | UPF → NE1 → NE3 → NE5 → gNB1 | 12 条流各 16/16 |
| `ReuseDetour` | UPF → NE1 → NE2 → NE4 → NE6 → NE5 → gNB1 | 12 条流各 16/16 |
| `ReuseQosPf` | 直行，阅读 SDAP/调度日志校验分类与权重 | 12 条流各 16/16 |
| `ReuseLinkFailover` | 700 ms 前直行，随后由 UPF 经 NE2、NE4、NE6、NE5 到原 gNB1 | 12 条流各 16/16 |

gNB1 下行的三类流合计 48 包。断链前后 NE5 的以太网入口分别看到 18 和 30 包，NE3→NE5 使用量在断链后为 0。中间路由器在以太网两侧各抓一遍，抓包总数用来验证经过哪些节点，应用交付以 sink 的接收计数为准。当前模拟 GTP 使用 UDP 31，抓包以实际 N3 下行目的 10.0.0.49 过滤。

## 复现

从仓库根按 `handoff/01-环境与登录.md` 加载环境并编译项目。新增配置位于 `nascTime/simulations/demos/e2e_ladder/omnetpp_native_reuse.ini`、`native-reuse.xml` 和 `ReuseFailoverLadder.ned`。

~~~bash
cd nascTime/simulations/demos/e2e_ladder
out=$(mktemp -d)
for cfg in ReuseDirect ReuseDetour ReuseQosPf ReuseLinkFailover; do
  ../../../bin/nasctime-run.sh -f omnetpp_native_reuse.ini -u Cmdenv -c "$cfg" -r 0 \
    "--result-dir=$out/$cfg"
  awk '/^scalar .*app.* (packetSent|packetReceived):count /' "$out/$cfg/"*.sca
done
for cfg in ReuseDirect ReuseDetour ReuseLinkFailover; do
  for pcap in "$out/$cfg/"*.pcap; do
    echo "$pcap"
    tcpdump -nn -tt -r "$pcap" 'udp port 31 and dst host 10.0.0.49' 2>/dev/null \
      | awk '{if ($1 < .7) before++; else after++} END {print before+0, after+0}'
  done
done

set -o pipefail
../../../bin/nasctime-run.sh -f omnetpp_native_reuse.ini -u Cmdenv -c ReuseQosPf -r 0 \
  --sim-time-limit=170ms --cmdenv-express-mode=false --cmdenv-log-level=INFO \
  "--result-dir=$out/sdap" 2>&1 \
  | LC_ALL=C grep -aE 'DEBUG_SDAP_IDENTITY|SDAP TX: Selected DRB|QoSAwareScheduler.*QoS Weight|^End\.' > "$out/sdap.txt"
~~~

当前 fork 的 QFI 日志把数值按 8 位字节写出。读取 `sdap.txt` 时 QFI 46 可能显示为句点，34 可能显示为双引号，0 显示为 NUL。按字节数值解码或结合配置和 DRB ID 核对，新增稳定诊断接口时应使用整数输出。

上游规则和会话模型是已核实的复用来源，本轮复跑仍用 A100 现有 fork。外部路径动作、按业务流区分的 N3 路由，以及收集按域候选的接口还属于后续联调。
