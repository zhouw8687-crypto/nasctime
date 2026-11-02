# EXP-04：四个域的逐一验证与拓扑

> 日期：2026-11-02　脚本：`experiments/exp/smoke_domains.sh`（一键跑全部）
> 结论：四个域**全部 rc=0 且都有业务送达**，可作为后续拼接的基线。

## 0. 验证结果总表

| 域 | 发送 | 接收 | 送达率 | 时延 mean | 其它 |
|---|---|---|---|---|---|
| `ring_test`（L2 边缘） | 51 | 50 | 98.0%（1 个在途） | 303.51 µs | 双路径 FRER，跨径差 101.17 µs |
| `mpls_test`（L3 承载） | 200 | 191 | 95.5% | 80.88 ms | LSP 生效（关 FEC 后 55.90 ms） |
| `mpls_failure_test`（L3 故障） | — | 513 | — | 中断 479.84 ms | 恢复期再断 320.16 ms |
| `ran_test`（无线接入） | 299 | 298 | 99.7% | 4.77 ms | 1 gNB / 1 UE，下行 |
| `core_test`（核心网用户面） | 299 | 299 | **100%** | **0.71 µs** | Router 代理 UPF（真 UPF 需 GTP 对端） |

> 送达率不足 100% 都是"仿真结束时在途"或"启动期未收敛"，不是模型错误。

## 1. ring_test —— 边缘有线接入（L2 TSN）

```
                     pe1 ●────────────● pe3
                        ╱ ╲          ╱
                       ╱   ╲        ╱
              source ●╱     ╲● pe2 ╱● destination
```

| 节点 | 类型 | 说明 |
|---|---|---|
| source / destination | `TsnDevice` | 端点，`hasStreamRedundancy` |
| pe1 / pe2 / pe3 | `TsnSwitch` | 纯 L2 桥，无 IP 层 |

链路：5 条，均 100 Mbps。两条树：`source-pe1-pe3-dest`（202 µs）与 `source-pe1-pe2-pe3-dest`（303 µs）。

**缺什么**
- ❌ 802.1AS 时间同步（`hasTimeSynchronization=false`）
- ❌ 802.1Qbv 门控（`hasEgressTrafficShaping=false`）
- ❌ 与 L3 域、无线域的连接
- ❌ 控制器与契约

## 2. mpls_test —— L3 承载域（MPLS-TE，静态标签）

```
 host1 ─10─┐
 host2 ─10─┼─ LSR1 ──15── LSR2 ──5── LSR4 ──5── LSR5 ──10── host3
 host5 ─10─┘   │            │          │          │
               │5           │10        │10        │10
               │            │          │          │
             LSR3 ──────────┴──5───────┘        └──10── host4
               │
               └──10── LSR7 ──10── LSR5
```

精确边表（带宽均 600 kbps）：

| 边 | 时延 | 边 | 时延 |
|---|---|---|---|
| host1–LSR1 | 10 ms | LSR2–LSR4 | 5 ms |
| host2–LSR1 | 10 ms | LSR3–LSR4 | 5 ms |
| host5–LSR1 | 10 ms | LSR4–LSR5 | 5 ms |
| LSR1–LSR2 | **15 ms** | LSR5–host3 | 10 ms |
| LSR1–LSR3 | **5 ms** | LSR5–host4 | 10 ms |
| LSR2–LSR6 | 10 ms | LSR3–LSR7 | 10 ms |
| LSR6–LSR5 | 10 ms | LSR7–LSR5 | 10 ms |

**缺什么**
- ❌ 动态建隧道（当前是**静态标签表**，`LSR1_fec.xml` + `LSR*_lib.xml`；RSVP 模块在但未用于建路）
- ❌ 双 LSP 多径（对齐 L2 的 FRER 双路径）
- ❌ 与 L2 域、无线域的连接
- ❌ 时钟同步、门控

## 3. mpls_failure_test —— 同一拓扑的故障场景

拓扑同 `mpls_test`，`scenario.xml` 在 t=2s 关闭 LSR4、t=4s 恢复。

```
 t=0 ────── 正常 ────── t=2s ✖ LSR4 宕机 ── 重收敛 ── t=4s ✔ 恢复 ── 再收敛 ── t=6s
                          中断 479.84 ms              中断 320.16 ms
```

**缺什么**
- ❌ 保护倒换配置（1+1 / 1:1 保护组）——当前只是"故障后重收敛"，不是"预先建好备用路径"
- ❌ 链路故障（当前是节点故障；链路故障在 `testte_failure2`）
- ❌ 与其它域的连接

## 4. ran_test —— 无线接入域（NR）

```
 server ●─10G─● router ●─10G─● upf ●─10G─● iUpf ●─10G─● gnb
 (StandardHost) (Router)      (Upf)      (Upf)      (gNodeB)
                                                         ┆
                                                        NR
                                                         ┆
                                                     ue[0] (NrUe)
```

网络直接复用 `simu5g.simulations.nr.networks.SingleCell_Standalone`，本域只写 ini。

**缺什么**
- ❌ 多 gNB 与切换（当前 1 gNB / 1 UE；多小区在 `MultiCell_Standalone`）
- ❌ TSN 桥接（NW-TT / DS-TT）——当前是纯 5G，不是 5G-TSN 桥
- ❌ 上行业务（当前只有下行）
- ❌ 切片、DRB/QoS 分级
- ❌ 与 L3 域的连接（边界是 `iUpf` 的 N3）

## 5. 四个域共同的缺口（拼接前必须补）

| 缺口 | 影响 |
|---|---|
| **域间连接** | 现在四个域各跑各的，没有任何一条边把它们连起来 |
| **共同时钟** | 只有 `ring_test` 有 `hasTimeSynchronization` 字段（还没开），L3/RAN 都没有 |
| **控制平面** | 完全没有；所有参数都是写死的 |
| **统一业务** | 每个域自己造 `UdpBasicApp`，没有契约化流 |
| **统一指标采集** | 现在靠 `kpi_table.py`/`hist_summary.py`/`vec_gaps.py` 三个工具分别读，尚未合并 |


## 6. 补充：核心网域（2026-11-02）

`core_test/` 结构：`hostA ─10G─ iUpf ─10G─ upf ─10G─ server`，两个 `iUpf/upf` 是 INET `Router`（代理 UPF）。

**为什么不直接用 Simu5G 的 `Upf`**：`Upf.ned` 里 `dnPpp` 只与 `gtp_user` 相连，必须有 GTP 对端（gNB 的 `GtpUser`）才能完成封装/解封装并注册接口；独立核心域里会在 `upf.ipv4.lp` 报
`Connected network interfaces can register using registerInterface()`。
Simu5G 文档写 "act like IP routers in the current version"，因此用 `Router` 在"转发/时延/切片"维度等价。
换回真 UPF 的条件与接法见 `nascTime/simulations/demos/core_test/README.md`。

实测：hostA 发 299 / server 收 **299（100%）**，端到端 **0.71 µs**（两跳 10G）。
