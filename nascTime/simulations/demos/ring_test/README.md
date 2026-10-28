# ring_test —— 边缘有线接入段（L2 TSN）

> 角色：本场景是项目端到端链路里的**边缘有线接入段**，不是整条承载网。
> 上层还有 L3 承载域（MPLS/路由）和无线接入段（gNB/UE），目前都**未接入**。

## 拓扑

```
        pe1 ────────── pe3
         │ ╲            │
         │  ╲           │
         │   ╲          │
      source  pe2 ──────┘
```

5 个节点：`source`、`pe1`、`pe2`、`pe3`、`destination`，5 条 100 Mbps 链路。
`pe1/pe2/pe3` 是 `TsnSwitch`（纯 L2 桥，**没有 IP 层**）。

端口映射（由 NED 连接顺序决定，改拓扑必须重核）：

```
source.eth[0] ↔ pe1.eth[0]
pe1.eth[1]    ↔ pe3.eth[0]      # 路径 A：直连
pe1.eth[2]    ↔ pe2.eth[0]      # 路径 B：两跳
pe2.eth[1]    ↔ pe3.eth[1]
pe3.eth[2]    ↔ destination.eth[0]
```

## 文件

| 文件 | 用途 |
|---|---|
| `RingMultipathShowcase.ned` | 拓扑定义 |
| `omnetpp.ini` | 双路径 FRER（两条树） |
| `omnetpp_single.ini` | 单树对照 |
| `omnetpp_probe.ini` | 双路径 + 三组探针（e2e / pathA / pathB） |

跑法：

```bash
cd nascTime/simulations/demos/ring_test
../../../bin/nasctime-run.sh -f omnetpp_probe.ini -u Cmdenv -r 0 --sim-time-limit=0.05s
```

## 已验证（详见 `experiments/docs/exp-02-transport-minimal-principle.md`）

- 双路径 FRER 成立：复制在 `pe1`，去重在 `pe3`，用 VLAN 0/1 区分两棵树；
- 每跳 ≈ 101.17 µs；跨径差 = 跳数差 × 101.17 µs；
- 无拥塞时单路径方差为 **0**；
- 合并器交付**先到的快副本**（双路径结果与"仅快路径"一致）。

## 与后续域的衔接

- **有线侧向上**：`pe1` / `pe3` 是边界桥，未来接 `Router` 或 `RsvpMplsRouter`
  作为 L3 承载域入口。注意：**一旦插入路由器，L2 就断了，本段的 FRER 也到此为止**。
- **无线侧接入**：由 Simu5G 的 `gNodeB` + `NrUe` 提供，衔接点是 N3（GTP-U over IP），
  即 gNB 的 `ppp` 口。是否能把 `ppp` 直接接到 `TsnSwitch` 尚未验证——这是接 5G 前的第一个风险点。

## 尚未包含

- 802.1Qbv 门控（`hasEgressTrafficShaping` 仍为 false）
- 802.1AS 时间同步（`hasTimeSynchronization` 仍为 false）
- 5G 接入段、L3 承载域、控制平面
