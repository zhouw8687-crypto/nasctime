# 下行仿真路线图与分级验证

主线是让控制器在下行负载变化时选择可执行的 IP 路径和资源配置，并验证终端的业务结果。首轮用同一个 UE、同一个 gNB，一条关键控制流和一条视频竞争流。两类业务分级固定，共用一个 N3 隧道，先允许整个隧道选择两条备选路径。业务上行留到端到端闭环实验。

## 我建议的推进顺序

| 阶段 | 具体工作 | 完成标准 |
| --- | --- | --- |
| 1. 分级接通 | Simu5G 1.7 的 UPF 按端口分 QFI，隧道入口写外层 DSCP，日字形 NE 按外层标记分类。 | **本轮完成。** 同一组业务只变化外层打标，抓包、出口队列和 UE 收包结果吻合。 |
| 2. 外部控制器主动换路 | 复用 INET 路由表、前两条已验证路径和现有 TCP 消息形式。把 N3 隧道标识、路径 ID 和实际下一跳读回接上。用单独的承载网背景负载只压一条路径，检查队列上涨后控制器能主动切换。 | 记录何时观察到拥塞、下发哪条路径、路由表生效时刻，以及第一个走新路径的包。固定 UE/gNB/会话，测切换期丢包和 SLA。 |
| 3. 各域生成候选，GCC 联合求解 | 承载域提供路径及每条的剩余容量，无线域提供下行预算与服务能力，核心域提供允许的速率策略。先用完整状态和传统枚举或贪心选可行组合，再与各域独立决策比较。 | 三组主对照为固定最短路、固定路径加队列隔离、路径与资源联合优化。关键流按期率须达预先设定的目标，在可行组合中比较竞争流吞吐、无线频带和链路开销。小候选集用全组合实跑作参考。 |
| 4. 验证状态上报与语义压缩 | 先冻结前述动作及 KPI。用完整上报对照阈值或量化，然后训练各域编解码器并验证跨域对齐。 | 分开记录真实上报比特、编码/解码和决策耗时、选路与参考前沿的差距及 SLA 违约。 |

第二阶段是下一项工程任务。现有 TCP 控制桥与无线预算模块出自项目的 Simu5G 1.5 fork，接到独立 1.7 环境时要逐个核对接口，包括控制器读回的目标和实时执行点。先打通路径动作，随后再让无线预算、UPF 限速和它一起参与求解。优先使用现有转发模块，避免为了第一轮同时引入切换小区、逐流隧道或新的门控协议。

三项当前设计假设可单独修正。第一，关键业务只看下行包是否按期到达。第二，路径选择单位暂时是 N3 隧道，同隧道控制和视频共享路径并分别排队。第三，先用显式标记建立可解释的分类，学习算法改善的是域间上报和决策质量。这样能区分分类、选路和压缩各自带来的变化。

## 本轮 A100 实验

临时工作树 `/media/a100/data/zbw/simu5g17-qfi.nJ2rCJ/Simu5G-qos` 基于上游提交 `d7f7c4641952aec465f50d0df91d104dae6ce901`。移植项目旧版的 `GtpUser.qfiDscpMap`，仅在指定 QFI 时设置新封装包的外层 IPv4 DSCP。使用日字形的拓扑、INET IPv4 和现有 `DscpToPcpMarker`，QFI 分类使用 1.7 版本的 `BearerConfigurator`。

固定首个 gNB 和附着 UE、链路 100 Mbit/s、种子 0、仿真 300 ms。两个应用从 50 ms 至 180 ms 每 10 ms 发 200 B，内层 DSCP 都为 0。控制端口 6200 分配 QFI 1、DRB 1，视频端口 6204 分配 QFI 3、DRB 2。两组的唯一区别是 UPF 是否写外层 DSCP。

| 组别 | NE1 下一跳抓到的 N3 包 | NE1.eth[1] 队列 0/1/2 入队计数 | UE 交付 |
| --- | --- | --- | --- |
| `LadderDownlinkUnmarked` | DSCP 0 共 26 包 | 27 / 0 / 0 | 控制 13/13，视频 13/13 |
| `LadderDownlinkMarked` | DSCP 46 与 34 各 13 包 | 1 / 13 / 13 | 控制 13/13，视频 13/13 |

队列 0 比 N3 数据包多一次出站 ARP。抓包验证外层 DSCP，队列计数验证包实际分类。此次是低负载的功能验收，拥塞下的时延、吞吐和资源收益由后续对照评估。

原生选路方法参考 [INET IPv4 路由教程](https://inet.omnetpp.org/docs/tutorials/configurator/doc/step5.html) 和 [IETF DetNet IP](https://www.rfc-editor.org/rfc/rfc8939.html)。

## A100 复跑

加载已有 OMNeT++/INET 环境，从项目根目录运行。已编译的实验用 Simu5G 位于 `$side/Simu5G-qos`。重新搭建时，从上游提交建立工作树，运行 `git -C "$SIMU5G_ROOT" apply --unidiff-zero "$repo/experiments/exp/simu5g17_qfi_dscp.patch"`，再以 `INET_ROOT="$repo/inet" make -j12` 编译。

~~~bash
repo="$PWD"
side=/media/a100/data/zbw/simu5g17-qfi.nJ2rCJ
export INET_ROOT="$repo/inet" SIMU5G_ROOT="$side/Simu5G-qos"
out=$(mktemp -d)
ned="$out/ned/nasctime"
ladder="$repo/nascTime/simulations/demos/e2e_ladder"
mkdir -p "$ned/simulations/demos/e2e_ladder" "$ned/qos"
cp "$ladder/"{ProjectBookLadder,LadderBackbone}.ned \
  "$repo/experiments/exp/Qfi17Ladder.ned" "$ned/simulations/demos/e2e_ladder/"
cp "$repo/nascTime/src/nasctime/qos/DscpToPcpMarker.ned" "$ned/qos/"
for cfg in LadderDownlinkUnmarked LadderDownlinkMarked; do
  "$SIMU5G_ROOT/bin/simu5g" -n "$out/ned" -f experiments/exp/simu5g17_ladder_downlink.ini \
    -u Cmdenv -c "$cfg" -r 0 "--result-dir=$out/$cfg"
  tcpdump -nnv -r "$out/$cfg/ne1-egress.pcap" 'udp port 31'
  grep -E 'NE1.eth\[1\].queue.queue\[[012]\] incomingPackets:count|ue\[0\].app\[[01]\] packetReceived:count' \
    "$out/$cfg/"*.sca
done
~~~
