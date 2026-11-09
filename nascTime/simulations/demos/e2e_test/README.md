# e2e_test —— 按项目书搭的端到端环境

> 完全按项目书的结构搭，**不引入 nascTime 的 5G-TSN 桥假设**（没有 NW-TT / DS-TT、没有 TSN 岛）。

## 拓扑（就是项目书那张图）

```
[无线接入]  ue ⇢ gNB ──N3──┐
                             ├── [承载: pe1 ══ pe2 ══ pe3，带 Qbv] ── [核心: upf ── server]
[有线终端]  host ── edge ───┘
```

| 节点 | 类型 | 角色 |
|---|---|---|
| `ue[0]` / `gnb` | `NrUe` / `gNodeB` | 无线接入（Simu5G） |
| `host` | `TsnDevice` | 有线终端 |
| `edge` | `TsnSwitch` | 有线边缘接入 |
| `n3Router` | `Router` | gNB 的 N3 接入点（PPP → Ethernet 转换） |
| `pe1/pe2/pe3` | `TsnSwitch` | **承载（PE）**，带 802.1Qbv 门控 |
| `coreRouter` | `Router` | 核心侧汇聚 |
| `upf` | `Upf`（Simu5G） | 真 UPF，终结 GTP |
| `server` | `StandardHost` | 数据网 |

## 实测（3 s，200 B @ 10 ms 两条流）

| 流 | 发送 | 接收 | 时延 mean | p99 | stddev |
|---|---|---|---|---|---|
| 无线 `ue[0] → server` | 298 | **295** | 20.56 ms | 32.25 ms | 6.08 ms |
| 有线 `host → server` | 299 | **299** | 112.23 µs | 169.61 µs | 3.36 µs |

两条接入都通，且无线流确实走了 GTP（UE ⇢ gNB → N3 路由 → PE 链 → UPF → 解封装 → server）。

## 一个重要的负面结果：开了 Qbv 但没做分类，会把默认业务饿死

当前 ini 给 PE 配了门控（class0 只占每 1 ms 里的 20 µs），但**没有给流量打 PCP 标记**。
结果：无线流（GTP，无标记）落进 class0，只能拿到 2% 的发送机会，
时延从 `ran_test` 里的 4.77 ms 恶化到 **20.56 ms**。

这说明：

> **Qbv 不是"打开就变好"的开关。** 不配合流分类（PCP/QFI 映射），
> 非高优先业务会被门控饿死。项目书里的"TSN 固定传输窗口"必须和"多流解析与流量整形"配套做。

下一步要么给流量打标记（`hasOutgoingStreams` + PCP 映射），要么先关掉门控做基线对照。

## 跑法

```bash
cd nascTime/simulations/demos/e2e_test
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s --result-dir=results
```

## 与其它目录的关系

| 目录 | 关系 |
|---|---|
| `pe_test/` | 本网络的 PE 段单独验证（门控开/关对照） |
| `ran_test/` | 本网络的无线段单独验证（Simu5G 官方网络） |
| `core_test/` | 本网络的核心段单独验证 |
| `system_test/` | 早期组装（LSR 环做承载，与本模型不一致），保留作对照 |
| `ring_test/` `mpls_test/` | 机制验证台，不属于项目书模型 |

## 缺什么

- 流量分类（PCP 映射）——现在门控在饿死默认业务
- 多 UE / 切换
- 承载环与保护倒换（现在是链）
- 时间同步（802.1AS）
- 控制器
