# e2e_ladder —— “日”字形端到端环境

> 按 Spirent TestCenter 参考拓扑改造的端到端场景，与 `../e2e_test/`（链式）并列，用于对照。

## 拓扑与参考图的对应

参考图（`D:\aaaLab\fh\spirent\...` 中的日字形网络结构）：

```
                    5GC
                  ╱     ╲
              NE1 ═════ NE2
               ║         ║
              NE3 ═════ NE4
               ║         ║
              NE5 ═════ NE6
             ╱             ╲
        测试仪表            eNB
```

本场景的实现：

```
                        server
                          │
                     coreRouter ── upf (N3/N6)
                     ╱          ╲
                  NE1 ════════ NE2        ← 核心网双归（左上角连核心网）
                   ║             ║
                  NE3 ════════ NE4
                   ║             ║
                  NE5 ════════ NE6        ← 基站双归（最下面一层连基站）
                   ║             ║
                 host        ranRouter ── gnb ⇢ ue[0]
```

| 参考图 | 本场景 | 说明 |
|---|---|---|
| NE1–NE6 | `NE1`–`NE6` | 三层路由节点（见下方说明） |
| 5GC | `coreRouter` + `upf` + `server` | 双归至 NE1、NE2 |
| eNB | `gnb`（经 `ranRouter` 双归至 NE5、NE6） | 基站只有一条 N3，用站点路由器做双归 |
| 测试仪表 | `host` | 客户侧接入 NE1 |

## 为什么 NE 是三层节点而不是 TsnSwitch

第一版按“PE = TsnSwitch（带 Qbv）”实现，并打开 RSTP 消除日字形环网，但运行失败：

```
<!> Error: Unknown protocol: protocolId = 34, protocolName = ieee8022llc
    pathStartGate = ...host.ethernet.macHeaderChecker.out
    pathEndGate   = ...host.bl.in[2]
```

原因：RSTP 的 BPDU 走 IEEE 802.2 LLC，而 BPDU 会泛洪到**所有**二层端口；
终端（`TsnDevice`）与路由器的二层部分没有 LLC 协议栈，收到 BPDU 即报错。
即便全局打开 `**.llc.typename = "Ieee8022Llc"`，TsnDevice 的桥接层仍会先截获该帧。

因此本版改用**三层可路由的日字形**：

- 六台 NE 为 `Router`，环路由路由自然处理，不会产生广播风暴；
- 日字形的两条竖边（NE1-NE3-NE5 与 NE2-NE4-NE6）构成**两条边不相交路径**，
  为后续保护倒换/多径实验提供基础；
- Qbv 门控能力已在 `../pe_test/` 单独验证，本场景聚焦拓扑与端到端指标。

> 待办：若要把门控叠加回本拓扑，需要解决“STP 域内的端节点如何处理 BPDU”，
> 可行方向是给端节点接一台非 STP 的边缘交换机做隔离。

## 实测（6 s，业务从 2 s 开始，200 B @ 10 ms）

| 业务流 | 发送 | 接收 | 均值 | P99 | 标准差 |
|---|---|---|---|---|---|
| 有线 `host→server` | 401 | 399 | **50.96 µs** | 62.31 µs | 0.58 µs |
| 无线下行 `server→ue[0]` | 401 | 400 | **5.00 ms** | 4.95 ms | 0.00 ms |
| 无线上行 `ue[0]→server` | 401 | 399 | **20.35 ms** | 32.10 ms | 6.10 ms |

## 与链式拓扑（e2e_test）的对比

| 指标 | 链式 `e2e_test` | 日字形 `e2e_ladder` | 差异原因 |
|---|---|---|---|
| 有线端到端 | 112.91 µs | **50.96 µs** | 日字形中 host 直连 NE1，到核心仅 1 跳；链式需经边缘交换机与三级 PE |
| 无线下行 | 4.54 ms | 5.00 ms | 日字形多一跳站点路由 |
| 无线上行 | 21.36 ms | 20.35 ms | 均受 NR 上行调度支配，拓扑影响可忽略 |

**结论**：拓扑由链式改为日字形后，有线路径显著缩短（跳数减少），无线方向指标基本不变，
再次印证“端到端确定性瓶颈在无线段、尤其上行”的判断。

## 跑法

```bash
cd nascTime/simulations/demos/e2e_ladder
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=6s --result-dir=results
```

## 缺什么

- Qbv 门控（因 STP 问题暂未叠加，见上）
- 双归链路的**主备倒换**实验（当前由路由自行选路，未做故障注入）
- 多 UE、切换
- 时间同步
