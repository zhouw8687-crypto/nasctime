# e2e_ladder —— “日”字形端到端环境（顶部 5GC + 底部两台基站）

> 按 Spirent 参考拓扑改造：6 台 NE 组成日字形承载网，**5GC 在顶部**（双归 NE1/NE2），
> **两台基站在底部**，分别接 NE5、NE6。参考图中的测试仪表不建模。

## 拓扑（默认：基站直连承载网）

```
                         server              ← 数据网(N6)
                           │
                          upf                ← 5GC 锚点 UPF
                       ╱        ╲
                     NE1 ══════ NE2          ← 5GC 双归接入（顶部两角）
                      ║            ║
                     NE3 ══════ NE4          ←  日 字 形 承 载 网
                      ║            ║
                     NE5 ══════ NE6
                      ║            ║
                    gnb1        gnb2          ← 底部两台基站（N3 直连）
                     ┆            ┆
                   ue[0]        ue[1]
```

| 参考图元素 | 本场景 | 说明 |
|---|---|---|
| NE1–NE6 | `NE1`–`NE6` | 三层路由节点，日字形三横两竖 |
| **5GC** | `upf` + `server`，接 NE1/NE2 | 双归接入，位于拓扑顶部 |
| eNB | `gnb1`→NE5、`gnb2`→NE6 | 两台基站各承载一个 UE |
| 测试仪表 | 不建模 | 参考图仅示意，无对应仿真元器件 |

## 实测（6 s，业务从 2 s 开始，200 B @ 10 ms）

| 业务流 | 发送 | 接收 | 均值 | P99 | 标准差 |
|---|---|---|---|---|---|
| 上行 `ue[0]→server`（经 gnb1） | 401 | 399 | **20.29 ms** | 32.06 ms | 6.10 ms |
| 上行 `ue[1]→server`（经 gnb2） | 401 | 399 | **20.29 ms** | 32.06 ms | 6.10 ms |
| 下行 `server→ue[0]` | 401 | 400 | **5.00 ms** | 4.95 ms | 0.00 ms |
| 下行 `server→ue[1]` | 401 | 400 | **5.00 ms** | 4.95 ms | 0.00 ms |

承载网侧计数确认两台基站各自承载自己的 UE：
`gnb1.cellularNic.rlcMux.sentPacketToLowerLayer:count = 800`，`gnb2 = 800`。

## 更正：**不需要**共用 I-UPF

此前曾记录“两台 gNB 必须共用一个 N3 汇聚点（I-UPF），直连多跳路由网会崩溃”。
经复测，**该结论是错误的**。

真实原因是 **`nrServingNodeId` 配置错误**：当两个 UE 都指向同一台基站、
或指向不存在的 ID 时，Simu5G 会在业务开始时崩在 `LteHarqBufferRx::insertPdu`。
按正确 ID 配置后，两台 gNB 直连 NE5/NE6 完全正常。

两种接法都验证通过：

| 变体 | 文件 | 结构 | 结果 |
|---|---|---|---|
| **直连（默认）** | `omnetpp.ini` + `ProjectBookLadder.ned` | gnb1→NE5，gnb2→NE6 | ✅ 四条流全通 |
| I-UPF 汇聚（可选） | `omnetpp_iupf.ini` + `LadderWithIupf.ned` | gnb1/gnb2→iUpf→NE5/NE6 | ✅ 四条流全通 |

I-UPF 变体并非错误结构（3GPP 中 I-UPF 部署在边缘、N3 汇聚、N9 回传），
只是**本项目的参考拓扑并不要求它**，默认采用直连版本。

## Simu5G 的节点 ID 分配（源码依据）

| 项 | 定义 | 含义 |
|---|---|---|
| gNB 的 `macNodeId` | `eNodeB.ned: macNodeId = default(1 + simu5g_seq("eNodeB_macNodeId"))` | 第一台 = 1，第二台 = 2 |
| LTE UE 的 `macNodeId` | `LteUe.ned: 1025 + seq` | UE 段 |
| NR UE 的 `nrMacNodeId` | `NrUe.ned: 2049 + seq` | NR UE 段 |
| UE 的绑定 | `Registration.cc:80-81`：`nrServingNodeId = ue->par("nrServingNodeId")` 后 `binder->registerServingNode(nrServingNodeId, nrNodeId)` | **参数值直接作为服务基站的 macNodeId**，不做名称解析 |

因此配置规则很简单：

```
*.ue[0].nrServingNodeId = 1   # 对应 gnb1（macNodeId=1）
*.ue[1].nrServingNodeId = 2   # 对应 gnb2（macNodeId=2）
*.ue[*].servingNodeId   = 0   # 纯 NR 场景无 LTE 锚点，保持 0
```

`Binder::registerNode` 会校验 ID 区间（NODEB / UE / NR UE），
填错区间会直接抛 `Cannot register node ... Wrong macNodeId`。

## 跑法

```bash
cd nascTime/simulations/demos/e2e_ladder

# 默认：基站直连承载网
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=6s --result-dir=results

# 变体：经 I-UPF 汇聚
../../../bin/nasctime-run.sh -f omnetpp_iupf.ini -u Cmdenv -r 0 --sim-time-limit=6s --result-dir=results_iupf
```

## 其他已知问题

1. **二层环网不能直接跑 IP**：日字形在二层成环，会触发 ARP 广播风暴（P99 从 161 µs 恶化到 981.9 ms）。
   RSTP 方案因 BPDU 需要 LLC 协议栈、端节点无法承载而放弃，故 NE 采用三层路由节点。
2. **Qbv 门控未叠加**：能力验证见 `../pe_test/`，本场景聚焦拓扑与端到端指标。
3. **`servingNodeId` 不要乱填**：填成非 0 的值可能触发 `NrMacUe` 对象所有权错误或段错误。

## 后续

- 利用两条竖边（NE1-NE3-NE5 / NE2-NE4-NE6）做**保护倒换**实验；
- 若要把 Qbv 叠加回来，先解决 STP 域内端节点的 BPDU 处理；
- 双基站 + 移动性（切换）实验。
