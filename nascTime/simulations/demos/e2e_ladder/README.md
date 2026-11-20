# e2e_ladder —— “日”字形端到端环境

> 按 Spirent 参考拓扑改造：6 台 NE 组成日字形承载网，核心网双归顶部两个角，基站挂在底部。

## 拓扑

```
                        server
                          │
                       upf.dnPppg
                    upf.pppg[0]  upf.pppg[1]
                        │            │
                  NE1 ══════════ NE2        ← 核心网双归（左上角连核心网）
                   ║                ║
                  NE3 ══════════ NE4
                   ║                ║
                  NE5 ══════════ NE6        ← 最下面一层接基站
                   ║                ║
                 gnb1            （gnb2 待启用）
                   ┆
                  ue[0]
```

| 参考图元素 | 本场景 | 说明 |
|---|---|---|
| NE1–NE6 | `NE1`–`NE6` | 三层路由节点，日字形三横两竖 |
| 5GC | `upf` + `server` | 双归至 NE1、NE2 |
| eNB | `gnb1` 接 NE5；`gnb2` 接 NE6（**暂未启用**） | 见“已知问题” |
| 测试仪表 | 不建模 | 参考图中仅为示意，且无对应仿真元器件 |

## 实测（6 s，业务从 2 s 开始，200 B @ 10 ms）

| 业务流 | 发送 | 接收 | 均值 | P99 | 标准差 |
|---|---|---|---|---|---|
| 无线上行 `ue[0]→server` | 401 | 399 | **20.29 ms** | 32.06 ms | 6.10 ms |
| 无线下行 `server→ue[0]` | 401 | 400 | **5.00 ms** | 4.95 ms | 0.00 ms |

## 已知问题

### 1. 两台基站同时存在会导致 Simu5G 段错误

在 NE6 上再挂一台 `gNodeB` 后，仿真在业务开始时崩溃：

```
Segmentation fault in simu5g::LteHarqBufferRx::insertPdu(unsigned short, inet::Packet*)
```

即使第二台基站没有挂 UE、甚至没有回程链路，崩溃依然出现；改为只保留一台基站后一切正常。
判断是 Simu5G 在“多 gNB + 路由化 N3”组合下的模型限制（其官方多小区示例中，
两台 gNB 是**直连**同一个 I-UPF 的，而非经多跳路由网）。后续可尝试：
把两台 gNB 改为直连同一个 I-UPF，再由 I-UPF 接入本日字形网络。

### 2. 一层环网不能直接跑 IP

日字形在二层会成环，L2 环 + IP 会触发 ARP 广播风暴（此前实测 P99 从 161 µs 恶化到 981.9 ms）。
曾尝试用 RSTP 消除，但 BPDU 走 IEEE 802.2 LLC，而端节点（终端/路由器）二层无 LLC 协议栈，
收到 BPDU 即报错。因此 6 台 NE 采用**三层可路由节点**。

### 3. 终端入网必须用 (0,1) 的 ID 组合

`ue[0].servingNodeId = 0`、`ue[0].nrServingNodeId = 1` 是可用的组合；
改成 `(1,1)` 会在业务开始时触发 `NrMacUe` 的对象所有权错误。该组合与 Simu5G 官方示例一致。

## 跑法

```bash
cd nascTime/simulations/demos/e2e_ladder
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=6s --result-dir=results
```

## 后续

- 解决双基站问题后，在 NE5、NE6 各挂一台基站，形成真正的双基站底部结构；
- 利用两条竖边（NE1-NE3-NE5 / NE2-NE4-NE6）做**保护倒换**实验；
- 若要把 Qbv 叠加回来，需要解决 STP 域内端节点的 BPDU 处理问题。
