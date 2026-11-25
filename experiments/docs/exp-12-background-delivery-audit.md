# EXP-12 背景流送达率审计与 HARQ 修复

## 审计方法

以 EXP-11 的日字形三域控制场景为基线。对同一随机种子 0、同一发送窗口 [0.60, 1.00) s 内发送的包，按应用序号检查 UPF N6、UPF N3、NE1 出口、NE5 入口、gNB 前和 UE 应用的记录。仿真持续到 3 s，晚到包仍归给发送时所在窗口。通过逐跳记录区分准入丢弃、承载队列溢出和基站到终端之间未送达。

## 两个根因

**UPF 的保护档限速将绝大多数突发背景包主动丢弃。** 突发阶段每约 700 µs 产生一个 1000 B UDP 负载，按 1028 B IPv4 包计约 11.75 Mbit/s，超过 2 Mbit/s 的保护档约 5.9 倍。2 Mbit/s 在 400 ms 内补充的令牌只够约 97 个包，桶中原有额度最多再放行约 4 个包。固定保护档观察到 464 个突发包消失在 UPF N6 到 N3 之间；动态档在一部分窗口内放开限速，所以这一计数较低。该模块是令牌桶 policing，额度不足立即丢包。INET 对该行为亦有独立示例。[INET 令牌桶监管示例](https://inet.omnetpp.org/docs/showcases/tsn/streamfiltering/tokenbucket/doc/index.html)

**Simu5G 下行调度存在 HARQ 满载时仍取包的缺陷。** gNB 的下行调度器遇到 firstAvailable() 返回 HARQ_NONE 时原来仍判定 UE 有资格调度。调度继续扣减虚拟缓存并请求 RLC 生成 PDU，MAC 组包后发现所有 HARQ 进程占用，删除已组装 PDU。修复前的动态组有 43 条这种发送前丢弃日志。一个实例发生在 631 ms，背景承载 RLC 发出 SN 143 后，gNB 在同一时刻出现无空闲进程日志，UE 接收序列出现缺口并记录分片重组失败。修改后在调度查询资格时检查空闲进程及空闲码字，未获准的业务留在队列等待下一时隙。

## 原参数复跑

| 配置 | 修复前背景流送达 | 修复后背景流送达 | 修复后 UPF 未通过 | 修复后承载段未通过 | 修复后 gNB 前到 UE 未通过 | 修复后控制流送达 / P99 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 固定常态 | 274/563 | 522/563 | 0 | 41 | 0 | 80/80 · 11.000 ms |
| 固定保护 | 98/563 | 99/563 | 464 | 0 | 0 | 80/80 · 6.210 ms |
| 动态门限 | 126/563 | 169/563 | 394 | 0 | 0 | 80/80 · 11.420 ms |
| 动态门限，突发后移 200 ms | 137/563 | 169/563 | 394 | 0 | 0 | 80/80 · 10.000 ms |

原动态组修复前的 437 个未送达包中，373 个丢在 UPF，64 个到达 gNB 前但没有到达 UE。修复让无线能继续处理排队的包，也改变了实时队列状态和下发时点，因此修复后动态限速多过滤了 21 个突发包。四组修复后的逐包轨迹在 gNB 前至 UE 间没有缺失，动态组的发送前 HARQ 丢弃日志和 RLC 分片重组失败日志复跑均为 0 条。固定常态的 41 个突发损失出现在 NE1 出队前，NE1 的背景队列全程溢出 42 次，其中 1 个属于突发后发送。固定常态虽然交付 522/563，送达背景包 P99 约 951.23 ms，仍存在长排队。

## 负载和限速验证

使用同一条数据路径、同一个算法与相同的其他参数。

- 将背景发送间隔恒定为 8 ms。在 0.60–1.00 s 的对照窗口，背景 50/50、控制 80/80，背景 P99 8 ms。控制器未进入保护档。
- 将动态策略保护档临时提升为 4 Mbit/s。突发背景交付 208/563（36.9%），其余 355 个在 UPF 被过滤。控制流 80/80、P99 11.000 ms，背景流 P99 37.693 ms。此配置在 620 ms 进保护、1020 ms 恢复，原 2 Mbit/s 基线有三次进入保护。仅对一条路径一个种子进行了该诊断，保留 2 Mbit/s 作为既有基线的复现参数。

## 复现

```bash
cd /media/a100/data/zbw/nasctime
source omnetpp-6.4.0/setenv
export LD_LIBRARY_PATH="$PWD/../conda-envs/nasctime/lib:$PWD/omnetpp-6.4.0/lib"
export INET_ROOT="$PWD/inet" SIMU5G_ROOT="$PWD/Simu5G"
make -C Simu5G/src -j6
make -C nascTime -j4
bash experiments/exp/run_ladder_controller.sh --cross-domain
```

汇总表的 background_burst_missing_* 列现在按发送窗口报告首个缺失点。保留全程计数 upf_drops_total 供与令牌桶统计核验。省略 --cross-domain 可运行 EXP-10 回归组。

以 EXP-10/11 的独立进程方式运行 CrossDomainExternal。无突发试验给仿真命令额外传入 '--*.server.app[1].sendInterval=8ms'。4 Mbit/s 试验在 PYTHONPATH 上放置如下 audit_policy.py 后，改用控制器 --policy audit_policy:decide。仿真配置和输入流量保持原样。

```python
from ladder_controller import CrossDomainBaseline

baseline = CrossDomainBaseline()


def decide(observation):
    core = observation["core"]
    if core["rate_bps"] == 4_000_000:
        observation = dict(observation, core=dict(core, rate_bps=2_000_000))
    action = baseline(observation)
    if action is not None and action["rate_bps"] == 2_000_000:
        action["rate_bps"] = 4_000_000
    return action
```

要复查 HARQ 日志，可在临时 INI 中从 CrossDomainExternal 继承并设置 cmdenv-express-mode=false、cmdenv-event-banners=false。先配置 gnb1.cellularNic.mac、gnb1.cellularNic.rlc-um-tx-* 及 ue[0].cellularNic.nrRlc-um-rx-* 的 cmdenv-log-level=trace，然后在 INI 配置末尾为其余模块设置 **.cmdenv-log-level=off。统计 no available process for this MAC PDU 和 SDU cannot be reassembled 条目。本地验收附件保留修复前后的日志计数和逐包结果。
