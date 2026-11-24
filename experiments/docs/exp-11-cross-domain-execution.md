# EXP-11 三域联合执行与传统基线

## 实验原理

在任务书的日字形拓扑中，沿用 EXP-10 的双流竞争路径 server → UPF → NE1 → NE3 → NE5 → gNB1 → UE0。控制器每 20 ms 读取三域和 UE 状态。预先设置两套固定资源档位，由队列高低水位和连续采样决定是否切换。一次联合请求包含三域目标值，校验版本、参数和周期边界后在同一仿真事件中写入并回读。故意发送非法参数、过期版本和错过门控周期边界的策略，确认拒绝后三个配置值和版本号保持原值。

| 执行位置 | 生效机制 | 常态 | 保护 |
| --- | --- | ---: | ---: |
| UPF N6 背景流 | 调整 UDP 6202 的令牌桶补充速率 | 20 Mbit/s | 2 Mbit/s |
| NE1.eth[1] 的 INET TAS/Qbv | 5 ms 周期前段开 PCP 高优先级门，余下时段开另两队列门，保留隐式保护带 | 前 600 µs | 前 1600 µs |
| gNB1 下行 | 在原生 MAXCI 的候选频带上设置上限，新传和重传沿用原调度和链路自适应 | 4 个逻辑频带 | 6 个逻辑频带 |

NE1 使用 INET 的原生 PeriodicGate，门控在本仿真共享时钟的周期边界更新。无线执行器限制本场景单载波 gNB1 能分配的逻辑频带，下一次下行调度读取新预算。每档固定保留前 N 个逻辑频带。这是小区级资源预算，按 UE 或切片分配频带需要额外的调度接口。实现参考 [INET Time-Aware Shaping](https://inet.omnetpp.org/inet/docs/showcases/tsn/trafficshaping/timeawareshaper/doc/index.html) 和 [Simu5G LteMacEnb](https://simu5g.org/neddoc/types/simu5g.stack.mac.LteMacEnb)。

传统门限基线进保护条件是 gNB1 下行 MAC 虚拟缓冲 ≥ 8000 B 或 NE1 背景队列 ≥ 8 包。两者连续 5 次同时低于或等于 2000 B、1 包时恢复常态。阈值沿用 EXP-10 的量级，基线按当前拥塞反馈工作。四组以相同 seed 0 运行 3 s，每段承载链路 30 km，NE1–NE3 速率 10 Mbit/s。控制流采用 200 B、间隔 5 ms、DSCP 46，背景流采用 1000 B、DSCP 0，常态间隔 8 ms，突发间隔 700 µs。

| 仿真配置 | 运行方式 | 实验目的 |
| --- | --- | --- |
| CrossDomainFixedNominal | 全程使用常态，0.60–1.00 s 突发 | 量化无资源增配的基线 |
| CrossDomainFixedProtect | 全程使用保护档，0.60–1.00 s 突发 | 量化持续保护对两类业务的影响 |
| CrossDomainExternal | 从常态启动，依据队列切换，0.60–1.00 s 突发 | 核对状态、联合下发、三域读回和业务结果 |
| CrossDomainExternalShifted | 同一算法，突发后移至 0.80–1.20 s | 观察策略是否随实际负载后移 |

## A100 结果

| 配置 | 突发发送队列的控制流送达 | 控制流送达包 P99 | 背景流送达 | 全程 UPF 丢背景包 | NE1 出队数 | 实测每次调度分配的块数峰值 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 固定常态 | 69/80 | 87.000 ms | 274/563 | 0 | 959 | 4 |
| 固定保护 | 79/80 | 76.100 ms | 98/563 | 465 | 536 | 6 |
| 动态门限基线 | 76/80 | 80.000 ms | 126/563 | 373 | 628 | 常态 4、保护 6 |
| 同一基线，突发后移 | 71/80 | 82.900 ms | 137/563 | 373 | 628 | 常态 4、保护 6 |

动态组在 640、820、840、980、1000、1120 ms 切换。后移组在 840、1020、1040、1180、1200、1320 ms 切换。两个动态组的 71 次采样均校验了请求 ID、执行时刻和版本，应用后下一次采样读回匹配。四组共检查 2751 次 NE1 出队，均同时符合实际门状态和下发窗口。逐次下行调度分配都在当时预算内，UPF 丢包计数与应用序号核对的 N6→N3 缺失数一致。

在原突发窗口内，动态基线比固定常态多交付 7 个控制包，比固定保护少交付 3 个控制包、多交付 28 个背景包。三项执行参数在联合组同步切换，单个执行器对 KPI 的贡献需要分别运行消融实验。当前只采用一个随机种子和一条活跃下行路径，结果适用于功能联调和基线对照。

## 复跑与接口

```bash
cd /media/a100/data/zbw/nasctime
source omnetpp-6.4.0/setenv
export LD_LIBRARY_PATH="$PWD/../conda-envs/nasctime/lib:$PWD/omnetpp-6.4.0/lib"
export INET_ROOT="$PWD/inet" SIMU5G_ROOT="$PWD/Simu5G"
make -C nascTime -j4
bash experiments/exp/run_ladder_controller.sh --cross-domain
```

结果目录保存 revision.txt、control-kpis.csv、流程分组 KPI、逐包轨迹、带门状态和下行分配的原始向量，以及五处 PCAP。原 EXP-10 使用同一脚本省略 --cross-domain 继续运行，四组逐包轨迹与改动前一致。

可从 EXP-10 的自定义算法接入方式启动控制器，用仿真配置 CrossDomainExternal。回调返回如下动作，或返回 None 维持当前配置。现有接口仍接受单域动作。三域场景的回执额外包含 priority_window_us、dl_band_budget、changed_domains。联合请求的三个目标固定指向本场景的 UPF 背景流、NE1.eth[1] 与 gNB1。

```json
{"type":"apply_cross_domain","rate_bps":2000000,"priority_window_us":1600,"bands":6}
```

本实验使用同一仿真时钟和同步请求回执。分层控制器独立周期、跨设备时钟误差、物理设备接口和异步定时生效属于下一阶段验证。当前的联合校验在单仿真进程内完成，跨设备下发需要单独定义失败后如何处理。
