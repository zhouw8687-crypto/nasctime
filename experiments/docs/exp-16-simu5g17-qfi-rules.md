# EXP-16 · Simu5G 1.7 按包规则分配 QFI

## 环境与目的

A100 独立目录为 `/media/a100/data/zbw/simu5g17-qfi.nJ2rCJ/Simu5G`，从官方 `v1.7.0` 拉取并编译，提交 `d7f7c4641952aec465f50d0df91d104dae6ce901`。用项目已有 OMNeT++ 6.4.0 和 INET 4.6.0 链接新库，原日字形继续使用自己的 Simu5G fork。新版官方 `VoIP-DL-MultiQfi` 和 `VoIP-UL-FilterRules` 在 run 0、250 ms 下正常结束。

本轮验证两件事。第一，在四条应用流都使用内层 DSCP 0 时，UPF 的下行规则和 UE 的上行规则能否按端口识别业务并选择不同 DRB。第二，在只交换上行 QFI 规则时，下行的分类是否仍然一致。用官方单小区 SA、`BearerConfigurator` 和 SDAP 实现，保留原生配置的 QFI 1→DRB 1 和 QFI 3→DRB 2。

[Simu5G 1.7 官方版本](https://github.com/Unipisa/Simu5G/releases/tag/v1.7.0) · [BearerConfigurator 分类接口](https://simu5g.org/neddoc/types/simu5g.corenetwork.bearerConfigurator.BearerConfigurator)

## 实验配置与结果

单 gNB、单 UE、两条下行和两条上行作为正交对照。UDP 应用负载 200 B，发送间隔 10 ms，发送窗为 [50, 180) ms，仿真 300 ms，run 0。四条应用流内层都设 DSCP 0。对照仅更换 UE 侧两个端口的 QFI，同时保留同一 DRB 表、包头、负载和 DL 规则。每个包用名称和序号关联入口分类、SDAP 选择及接收端计数。

| 业务 | 分类位置和目的端口 | 基准 QFI→DRB | 仅交换上行规则 | 两组各自交付 |
| --- | --- | --- | --- | --- |
| DL-control | UPF，6200 | 1→1 | 1→1 | 13/13 |
| DL-video | UPF，6204 | 3→2 | 3→2 | 13/13 |
| UL-control | UE，6000 | 1→1 | 3→2 | 13/13 |
| UL-video | UE，6004 | 3→2 | 1→1 | 13/13 |

两个配置均逐包核对了入口 QFI 与对应发送侧 SDAP 的 DRB。上行封装到 N3 前的 gNB 流分类日志也保留了 UE 分配的 QFI。靠 gNB 一侧的 N3 抓包在两组分别记录 52 个隧道包，外层 DSCP 全部为 0。因此，本轮证明了**应用 DSCP 相同仍能获得不同无线 QoS 承载**。承载队列分级需要单独配置 QFI 或 QoS profile 到可见服务类的映射。Simu5G 1.7 的 `GtpUserMsgSerializer` 未序列化 QFI，本轮的 QFI 证据取自仿真内部日志，PCAP 用于读取外层 DSCP。

[Simu5G 1.7 GTP 隧道处理](https://github.com/Unipisa/Simu5G/blob/v1.7.0/src/simu5g/corenetwork/gtp/GtpUser.cc) · [Simu5G 1.7 GTP 序列化](https://github.com/Unipisa/Simu5G/blob/v1.7.0/src/simu5g/corenetwork/gtp/GtpUserMsgSerializer.cc)

## 与三层跨域选路的关系

控制器层可以使用统一的业务合同，例如 `flowId + selector + SLA + direction`。无线域将流绑定到 QoS Flow 和 DRB。域边界用会话和 QoS profile 计算承载侧可见的 DSCP 或隧道类。承载域据此分类、候选选路和执行带宽或队列策略。QFI 的作用域是 PDU Session，相同的数值在不同会话可以指不同服务；运营策略决定它如何映到承载 class。

首批联合优化可固定映射，先只验证下行。在相同业务和负载下比较三组。固定路径加固定资源是基线，固定路径加按类队列隔离量化分类收益，最后让 GCC 联合选择三层路径与无线、承载资源配额。业务约束可先设关键流按期交付率及最低吞吐，再比较可行解的按期吞吐、链路占用及无线逻辑频带开销。标识让 GCC 能对业务分别处理，也让两类业务可在共享 UPF 和承载节点时得到不同队列或路径。标识本身没有产生容量预留，仍要以每个域执行和回读的动作确认。

如果任务只研究服务器到 UE 的下行路径，同方向保留关键流与竞争流即可。验证上行是对分类接口的检查。只有闭环业务的两段 SLA 或手机上下行资源竞争是研究变量时，才将反方向应用流纳入。届时业务层仍可保持一个合同，同时为各方向提供子流选择条件。

[3GPP TS 23.501 §5.7](https://www.etsi.org/deliver/etsi_ts/123500_123599/123501/18.10.00_60/ts_123501v181000p.pdf) · [IETF DetNet IP RFC 8939](https://www.rfc-editor.org/rfc/rfc8939.html)

## A100 复跑

从项目根目录按 `handoff/01-环境与登录.md` 加载现有环境。以下命令使用已经编译好的独立目录。若重新搭建，先在另一目录执行 `git clone --depth 1 --branch v1.7.0 https://github.com/Unipisa/Simu5G.git`，然后在相同环境下运行 `make -C "$SIMU5G_ROOT" -j12`。

~~~bash
repo="$PWD"
export SIMU5G_ROOT=/media/a100/data/zbw/simu5g17-qfi.nJ2rCJ/Simu5G
export INET_ROOT="$repo/inet"
cd "$SIMU5G_ROOT/simulations/nr/standalone_drb"
out=$(mktemp -d)

for cfg in VoIP-DL-MultiQfi VoIP-UL-FilterRules; do
  "$SIMU5G_ROOT/bin/simu5g" -f omnetpp.ini -u Cmdenv -c "$cfg" -r 0 \
    --sim-time-limit=250ms "--result-dir=$out/$cfg"
done

set -o pipefail
for cfg in QfiRulesByPort QfiRulesReverseUplink; do
  "$SIMU5G_ROOT/bin/simu5g" -f omnetpp.ini -f "$repo/experiments/exp/simu5g17_qfi.ini" \
    -u Cmdenv -c "$cfg" -r 0 --cmdenv-express-mode=false --cmdenv-log-level=INFO \
    "--result-dir=$out/$cfg" 2>&1 \
    | LC_ALL=C grep -aE 'Error|^\*\* Event.*(QosFlowClassifier|NrSdap|TrafficFlowFilter|GtpUser)|QosFlowClassifier - |Received datagram : |setting tft=|SDAP TX: Selected DRB|^End\.' \
      > "$out/$cfg.trace"
  tcpdump -nnv -r "$out/$cfg/n3.pcap" 'udp port 31' \
    | sed -n 's/.*tos \(0x[[:xdigit:]]*\),.*/\1/p' | sort | uniq -c
  awk '/^scalar .*app.* (packetSent|packetReceived):count /' "$out/$cfg/$cfg/0.sca"
done
~~~

本轮 A100 原始产物位于 `/media/a100/data/zbw/simu5g17-qfi.nJ2rCJ/port-test.RZtGk7`。独立验证了上游 QFI/DRB 分类，日字形尚未接入新版或 QFI 到承载 class 的新适配。
