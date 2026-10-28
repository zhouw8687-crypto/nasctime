# mpls_test —— L3 承载域（MPLS-TE）

> 角色：项目里的**三层承载域**（N3 那一层）。与 `../ring_test/`（边缘有线接入，L2 TSN）**完全独立**，
> 两者目前没有连起来。以后要串，只在 NED 里加一条链路，不在 ini 里混配。

## 来源

从 INET 官方示例复制并改造：

```
inet/examples/mpls/testte_tunnel/  →  nascTime/simulations/demos/mpls_test/
```

改动只有两处：`RSVPTE4.ned` 的 `package`、`omnetpp.ini` 的 `network` 全名。其余（路由表 `.rt`、
标签表 `LSR*_lib.xml`、FEC 分类 `LSR1_fec.xml`）原样保留。

## 结构

```
host2 ─┐
host1 ─┼─ LSR1 ── LSR2 ── LSR4 ── LSR5 ─┬─ host3
host5 ─┘   │╲      │        │      │    └─ host4
           │ ╲     │        │      │
           │  LSR3─┘        │      LSR6
           │   │            │       │
           └───┴── LSR7 ────┴───────┘
```

7 台 LSR（`RsvpMplsRouter`）+ 5 台 host，链路带宽 600 kbps、时延 5/10/15 ms 各不相同。
每台 LSR 具备：`classifier`（FEC 分类）、`libTable`（标签表）、`rsvp`（信令）、`mpls`（转发）、`linkStateRouting`。

## 跑法

```bash
cd nascTime/simulations/demos/mpls_test
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=5s
```

## 已验证（2 s 跑通）

| 项 | 值 |
|---|---|
| host1 → host3 | 发 200，收 **191** |
| host2 → host4 | 发 200，收 **191** |
| LSR 子模块 | `classifier` / `libTable` / `rsvp` / `mpls` / `linkStateRouting` 全在 |
| 标签表配置 | 42 处 `libTable` 参数已下发 |

## 尚未验证 / 待补

1. **流量是否真的走 LSP**：当前只证明"能通"，没证明"走标签隧道而不是 IP 最短路径"。
   需要看 `LSR1.classifier` 的分流计数，或在 LSR 之间加探针。
2. **无时延/抖动统计**：示例本身不记录 `endToEndDelay`，要加 `FlowMeasurement`（做法同 `ring_test/omnetpp_probe.ini`）。
3. **动态路径与故障倒换**：本示例是**静态标签表**。动态建隧道、重路由、链路故障在兄弟目录：
   - `inet/examples/mpls/testte_routing/`（RSVP 建隧道）
   - `inet/examples/mpls/testte_reroute/`（运行时重路由，`scenario.xml`）
   - `inet/examples/mpls/testte_failure/`、`testte_failure2/`（故障）
4. **规模扩展**：`inet/examples/mpls/net37/`（37 节点）可作大拓扑模板。
5. **与 5G / TSN 的衔接**：完全没做。衔接点应是 `host` 换成一个边界节点（UPF 或 TSN 桥）。

## 与 ring_test 的边界

| | ring_test | mpls_test |
|---|---|---|
| 层次 | L2（桥） | L3（MPLS） |
| 确定性手段 | 802.1Qbv 门控、802.1CB FRER | 显式 LSP、带宽约束、重路由 |
| 路径表达 | `trees: [[节点序列...]]` | `<route><node>...</node></route>` |
| 能否跨域 | ❌（L2 无"域"概念） | ✅ |
| 冗余 | FRER 复制/去重 | LSP 保护倒换 |

**两者不能直接拼接**：中间必须有一台路由器，因为一旦插入 L3，L2 广播域就断了，`ring_test` 的 FRER 也到此为止。
