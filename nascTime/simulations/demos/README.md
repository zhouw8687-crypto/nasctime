# 仿真域目录约定

一个域一个目录，**互不 import、互不引用 ini**，只在 NED 里用一条链路连接。这样某个域出问题
（改参数、换模型、重跑），不会牵连其它域。

## 目录与角色

| 目录 | 域 | 层次 | 状态 | 关键机制 |
|---|---|---|---|---|
| `pe_test/` | **承载（PE+TSN）** | L2+TSN | ✅ 跑通 | Qbv 门控开/关对照：HP max/min 从 15.6× 降到 1.28× |
| `system_test/` | **整体组装** | L2+L3 | ✅ 跑通 | 有线接入 → 边界路由 → 承载环 → 核心；81.83 µs / 100% |
| `ring_test/` | **边缘有线接入** | L2 | ✅ 跑通 | TsnSwitch 三角环 + FRER 双路径 |
| `mpls_test/` | **L3 承载域** | L3 | ✅ 跑通 | 7 台 MPLS LSR + RSVP + 标签表；已验证 LSP 覆盖最短路（80.9 vs 55.9 ms） |
| `mpls_failure_test/` | **L3 承载域（故障）** | L3 | ✅ 跑通 | 节点宕机/恢复；中断 479.8 ms / 320.2 ms |
| `frer_test/` | 5G-TSN 桥接（nascTime 原场景） | L2+5G | ✅ 有 60 run 数据 | NW-TT/DS-TT + gPTP + FRER |
| `multi_endpoint_test/` | 3 端点参考场景 | L2+5G | ⚠️ 接收端未记录包 | 论文基线拓扑 |
| `ext_multiendpoint_test/` | N 端点参数化拓扑 | L2+5G | ✅ | frer_test 的底座 |
| `ran_test/` | **无线接入** | NR | ✅ 跑通 | 复用 Simu5G `SingleCell_Standalone`；DL 4.77 ms / 99.7% |
| `core_test/` | **核心网（用户面）** | IP | ✅ 跑通 | Router 代理 UPF（真 UPF 需 GTP 对端）；0.71 µs / 100% |

## 三条纪律

1. **改一个域只动它自己的目录**。跨域参数不要写进对方的 ini。
2. **域边界只在 NED 里连**。典型边界：
   - L2 ↔ L3：路由器（会打断广播域，FRER 到此为止）
   - 5G ↔ L2：NW-TT / DS-TT 翻译器（保持 L2 语义）
3. **每个域的 README 必须写清**：角色、端口映射、跑法、已验证结论、待补项、与相邻域的边界。

## 端口映射是个坑

NED 里 `ethg++` 的**连接顺序**决定端口号（`eth[0]`、`eth[1]`…），探针和 GCL 都依赖它。
改拓扑后必须重新核对，否则探针数据全错。`ring_test/README.md` 里有一份现成的映射表可参照。


## 架构模型（2026-11-02 修正）

**承载域在中心，各接入挂上去**；不是 3GPP 的"5G 当桥、TSN 岛在两端"。

```
TSN 有线接入 ─┐
无线接入   ───┼── 承载域（PE 环/网）── UPF ── 核心网
其它接入   ───┘
```

- 这个模型对应项目书里"承载网由 PE 构成、UPF 桥接无线接入与核心网"的描述；
- 3GPP 的桥模型（TSN—NW-TT—5G—DS-TT—TSN）是 `frer_test/` 那类场景的模型，两者不是一回事；
- 因此 `mpls_test`（承载）是中心域，`ring_test` / `ran_test` / `core_test` 都是挂在它上面的接入或边缘。


## 三域模型（2026-11-02 定稿）

项目书对应三个域，**不是四个**：

| 项目书 | 域 | 目录 |
|---|---|---|
| 无线接入（RU/基站/UE） | 无线接入 | `ran_test/` |
| **承载网（PE 设备，含 TSN 能力）** | 承载 | **`pe_test/`** |
| 核心网（UPF/策略/切片） | 核心 | `core_test/` |

**关键更正**：TSN 不是一段独立的"有线接入域"，而是**承载设备（PE）自身的能力**
（项目书原文："验证 TSN 机制为确定性流量预留固定传输窗口的保障能力"、
"评估承载设备对精密时钟协议的兼容性"）。所以：

- `ring_test/` 和 `mpls_test/` **降级为机制验证台**，不再是独立域：
  - `ring_test/`：纯 L2 下验证 FRER 双路径与跨径差（无 IP，所以环不会 ARP 风暴）；
  - `mpls_test/`：验证 L3/MPLS 的显式路径与故障重收敛；
  - 两者最终并入 `pe_test/` 的 PE 节点（PE 同时做转发 + 门控）。
- `system_test/` 是拼装验证：无线接入 → PE → 核心。

### 为什么 PE 不能简单等于 TsnSwitch

真实 PE 同时做两件事：**L3/MPLS 转发** 和 **Qbv 门控**。
INET 里 `TsnSwitch` 只做 L2，`Router`/`RsvpMplsRouter` 只做 L3，没有现成的"TSN-capable PE"。
所以：

- `pe_test/` 当前用 `TsnSwitch` 链（L2 + 门控能力），先证明门控有效；
- `mpls_test/` 用 `RsvpMplsRouter` 证明 L3 显式路径；
- 合成 TSN-capable PE 是后续工作项。
