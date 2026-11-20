# e2e_ladder —— “日”字形端到端环境（顶部 5GC + 底部两台基站）

> 按 Spirent 参考拓扑改造：6 台 NE 组成日字形承载网，**5GC 在顶部**（双归 NE1/NE2），
> **两台基站在底部**（经边缘 I-UPF 汇聚后接入承载网）。参考图中的测试仪表不建模。

## 拓扑

```
                         server              ← 数据网（N6）
                           │
                          upf                ← 5GC 锚点 UPF
                       ╱        ╲
                     NE1 ══════ NE2          ← 5GC 顶部接入（双归）
                      ║            ║
                     NE3 ══════ NE4          ←  日 字 形 承 载 网
                      ║            ║
                     NE5 ══════ NE6
                      ╲            ╱
                        iUpf                 ← 边缘 I-UPF（N3 汇聚 / N9 上行）
                       ╱      ╲
                    gnb1      gnb2           ← 底部两台基站
                     ┆          ┆
                   ue[0]      ue[1]
```

| 参考图元素 | 本场景 | 说明 |
|---|---|---|
| NE1–NE6 | `NE1`–`NE6` | 三层路由节点，日字形三横两竖 |
| **5GC** | **`upf` + `server`**，接 NE1/NE2 | 双归接入，位于拓扑顶部 |
| eNB | `gnb1`、`gnb2` 接 `iUpf` | 两台基站，N3 直连边缘 I-UPF |
| 测试仪表 | 不建模 | 参考图仅示意，无对应仿真元器件 |

## 实测（6 s，业务从 2 s 开始，200 B @ 10 ms）

| 业务流 | 发送 | 接收 | 均值 | P99 | 标准差 |
|---|---|---|---|---|---|
| 上行 `ue[0]→server` | 401 | 399 | **20.31 ms** | 32.07 ms | 6.09 ms |
| 上行 `ue[1]→server` | 401 | 399 | **20.30 ms** | 32.07 ms | 6.10 ms |
| 下行 `server→ue[0]` | 401 | 400 | **5.00 ms** | 4.95 ms | 0.00 ms |
| 下行 `server→ue[1]` | 401 | 400 | **5.00 ms** | 4.95 ms | 0.00 ms |

四条流全部打通，上下行差异（20.3 ms vs 5.0 ms）与此前结论一致：上行受 NR 调度支配。

## 关键解决：I-UPF 汇聚解决了“双基站崩溃”

上一版把两台 gNB 分别直连 NE5、NE6，业务一开始即段错误：

```
Segmentation fault in simu5g::LteHarqBufferRx::insertPdu(unsigned short, inet::Packet*)
```

即使第二台 gNB 不挂 UE、甚至没有回程链路，崩溃依旧。改为**两台 gNB 先直连同一个
I-UPF**（这正是 Simu5G 官方多小区示例的结构），再由 I-UPF 双归接入 NE5/NE6，
崩溃消失，四条流全部跑通。

> 结论：Simu5G 的多 gNB 必须共用同一个 N3 汇聚点；gNB 直接挂到多跳路由网络上不受支持。

## 已知问题：两个 UE 目前都附着在 gnb1

`gnb2` 的 `rlcMux.sentPacketToLowerLayer:count` 为 0，说明业务全部由 gnb1 承载。
原因是两个 UE 都使用 `servingNodeId=0 / nrServingNodeId=1`（Simu5G 官方示例里所有 UE 也都是这组值）。
尝试 `(2,2)` 会让仿真段错误，`(1,1)` 会报 `NrMacUe` 对象所有权错误。

结论：Simu5G 中**每个 UE 指定不同服务基站的绑定方式尚未弄清**，官方多小区示例也没有示范。
后续需要阅读 `binder` 与 `NrMacUe` 的绑定逻辑，或改用动态关联（`dynamicAssociation`）让 UE 按位置自动选择基站。

## 其他已知问题

1. **二层环网不能直接跑 IP**：日字形在二层成环，会触发 ARP 广播风暴（P99 从 161 µs 恶化到 981.9 ms）。
   RSTP 方案因 BPDU 需要 LLC 协议栈、端节点无法承载而放弃，故 NE 采用三层路由节点。
2. **Qbv 门控未叠加**：能力验证见 `../pe_test/`，本场景聚焦拓扑与端到端指标。

## 跑法

```bash
cd nascTime/simulations/demos/e2e_ladder
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=6s --result-dir=results
```

## 后续

- 解决 UE 与基站的独立绑定，使两台基站各自承载一个 UE；
- 利用两条竖边（NE1-NE3-NE5 / NE2-NE4-NE6）做保护倒换实验；
- 若要把 Qbv 叠加回来，先解决 STP 域内端节点的 BPDU 处理。
