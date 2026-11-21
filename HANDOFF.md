# HANDOFF — 6G 确定性网络端到端验证框架（nascTime）

> 生成时间：2026-11-21 13:06 CST · 生成者：DSH 会话（deepseek-flash）
> 本地镜像：`C:\Users\a\.dsh\remote-workspaces\wmv4mdfl29ql5`
> 远端：`a100@222.20.99.7:/media/a100/data/zbw/nasctime`
> 分支：`main` · 最近提交：`efaeb91 feat: 打通 gNB→承载网切片映射——GtpUser 增加 QFI→DSCP 打标`

---

## 1. 总体目标

在国家重点研发计划课题五下，用 OMNeT++/INET/Simu5G 搭建**可运行的确定性网络验证仿真平台**，
覆盖 **无线接入 / 承载（PE+TSN）/ 核心** 三个域，按《6G确定性承载网集成测试方案》的用例
（T1 单流基准、T2 多流切片、T3 动态扰动、T4 长稳）产出可复现的 KPI 数据，支撑年度报告。

验收标准：
1. 每个用例都能用一条命令复现，结果落 `.sca`；
2. 关键指标（单向时延、峰峰值抖动、RMS、丢包率、有效带宽、切片隔离度）有对照数据；
3. 结论与实验证据一一对应，推测与实测分开标注。

---

## 2. 约束与红线

- **不要做统一 SUT 适配层**（用户明确否定过："这是最容易烂尾的设计"）。
- **三个域各自独立目录，互不 import**；仿真场景一个用例一个目录。
- **仿真结果不得当作设备验收依据**：仿真抖动为 0 只是理论下界，设备级指标必须硬件实测。
- 改动前先读文件；提交用 `bash experiments/bin/git-save.sh "<msg>"`（会自动排除本地脚本污染）。
- 服务器是共享算力机（512 核），单次仿真控制在 2 s 仿真时间、并发 ≤5。
- 不要覆盖仓库根目录的 `AI交接文档_项目现状与后续方向.md`（那是 FRER 线的历史交接）。

---

## 3. 已完成

- [x] **T1 帧长矩阵**（64/128/512/1024/1472/9000 B × 30%/80% 负载，12 组）— 证据：[`experiments/docs/exp-05-t1-frame-matrix.md`](experiments/docs/exp-05-t1-frame-matrix.md)，脚本 `experiments/exp/t1_matrix.sh`
- [x] **T2 三流三切片（链式）** — 证据：[`nascTime/simulations/demos/t2_slices/README.md`](nascTime/simulations/demos/t2_slices/README.md)，提交 `ba1d75d`
- [x] **T2 三流三切片（日字形，按参考拓扑）** — 证据：[`nascTime/simulations/demos/t2_ladder/README.md`](nascTime/simulations/demos/t2_ladder/README.md)，提交 `c5c2ace` `515cded`
- [x] **T3-4 切片隔离度** — 链式 100%；日字形下发现接入链路瓶颈并用实验定位 — 证据：[`experiments/docs/exp-06-t2-t3-t4.md`](experiments/docs/exp-06-t2-t3-t4.md)，提交 `1d083f2` `6612208`
- [x] **T3-1 高优先突发** — 超窗即崩溃、不影响其它切片 — 同上
- [x] **T4 长稳（30 s 缩比）** — 与 2 s 结果偏差 ≤0.19 µs — 同上
- [x] **gNB → 承载网 QFI→DSCP 映射**（改 Simu5G `GtpUser`）— 实测 QFI 46 → DSCP 46，294 次打标 — 证据：[`experiments/docs/exp-07-qfi-dscp-mapping.md`](experiments/docs/exp-07-qfi-dscp-mapping.md)，提交 `efaeb91`

---

## 4. 当前进度

**T1/T2/T3-4/T4 在链式拓扑上全部完成；T2/T3-4 在日字形拓扑上也已跑通。**

卡点：日字形的**承载网还没有 Qbv**（`e2e_ladder` 的 NE 是 `Router`，不是 `TsnSwitch`），
且 gNB 的外层 DSCP 虽然已经能打，但**承载网入口还没有 DSCP→PCP 映射**，
所以"5G 切片一路进到承载网队列"这条链路还差最后两环。

当前无后台任务在跑，工作区干净（`git status` 为空）。

---

## 5. 已改文件

### 5.1 本轮新增/修改（提交 `ba1d75d`..`efaeb91`）

| 绝对路径 | 变更内容 | 落盘状态 |
|---|---|---|
| `/media/a100/data/zbw/nasctime/nascTime/simulations/demos/t2_slices/omnetpp.ini` | 三切片配置：PCP 标记、显式 PCP→等级映射、GCL 三相窗口、`T34_Overload`/`T31_Burst` | 已落盘 |
| `/media/a100/data/zbw/nasctime/nascTime/simulations/demos/t2_slices/README.md` | 因果链、实验数据、踩坑记录 | 已落盘 |
| `/media/a100/data/zbw/nasctime/nascTime/simulations/demos/t2_ladder/T2LadderNetwork.ned` | 日字形六节点 + 5GC 双归 + 两个接入点 | 已落盘 |
| `/media/a100/data/zbw/nasctime/nascTime/simulations/demos/t2_ladder/omnetpp.ini` | 每接入点三切片（6 条流）、PCP 标记、DSCP/PCP 分类、GCL | 已落盘 |
| `/media/a100/data/zbw/nasctime/nascTime/simulations/demos/t2_ladder/README.md` | 拓扑、六流数据、接入链路瓶颈实验 | 已落盘 |
| `/media/a100/data/zbw/nasctime/Simu5G/src/simu5g/corenetwork/gtp/GtpUser.ned` | 新增参数 `qfiDscpMap` | 已落盘 |
| `/media/a100/data/zbw/nasctime/Simu5G/src/simu5g/corenetwork/gtp/GtpUser.h` | 新增 `std::map<int,int> qfiDscpMap_` | 已落盘 |
| `/media/a100/data/zbw/nasctime/Simu5G/src/simu5g/corenetwork/gtp/GtpUser.cc` | 解析映射表 + 封装后设 `DscpReq` | 已落盘 |
| `/media/a100/data/zbw/nasctime/experiments/docs/exp-05-t1-frame-matrix.md` | T1 数据与四条结论 | 已落盘 |
| `/media/a100/data/zbw/nasctime/experiments/docs/exp-06-t2-t3-t4.md` | T2/T3/T4 数据与隔离归因修正 | 已落盘 |
| `/media/a100/data/zbw/nasctime/experiments/docs/exp-07-qfi-dscp-mapping.md` | 四层映射链、业界做法、补丁与验证 | 已落盘 |
| `/media/a100/data/zbw/nasctime/experiments/exp/t1_matrix.sh` | T1 矩阵一键复现脚本 | 已落盘 |

### 5.2 本轮未改动但重要的既有文件

| 路径 | 作用 |
|---|---|
| `nascTime/simulations/demos/e2e_ladder/` | 日字形端到端（5GC 双归 + 两 gNB），**当前 NEs 是 Router** |
| `nascTime/simulations/demos/pe_test/` | 链式两跳门控场景，T1 用它跑 |
| `nascTime/simulations/demos/README.md` | 各域目录职责表 |
| `experiments/exp/kpi_v2.py` | KPI 提取工具（均值/峰峰值/RMS/丢包/带宽） |
| `experiments/bin/git-save.sh` | 统一提交脚本 |
| `AI交接文档_项目现状与后续方向.md` | **FRER 线的历史交接**，读它了解 5G-TSN 桥背景 |

---

## 6. 关键决策

| 决策 | 原因 | 放弃的备选 |
|---|---|---|
| 三域拆分（无线接入/承载/核心），不建统一适配层 | 统一层会掩盖各域特性，难以定位问题 | 用户明确否定的 SUT 适配层 |
| 切片用 **PCP** 分类而不是 DSCP | INET 队列分类器只认 PCP（`PcpTrafficClassClassifier`）；DSCP 分类器 `MultiFieldClassifier` 不是 `IPacketClassifier` | DSCP 直接分队列 |
| 三相窗口用 `GateControlList`，不用 `PeriodicGate` | `PeriodicGate.durations` 必须成对，无法表达"闭-开-闭"中间窗口 | `PeriodicGate`（只能两段） |
| 门控周期 1 ms、窗口 300/580/120 µs | 按"每周期发送时间 + 一帧保护带"公式算得 | 拍脑袋定窗口（会积压） |
| 隔离归因改为"按类分离队列"，不是"独立窗口" | A/B/C 三组对照：无窗口但分队列时 HP 仍 335 µs | 原本以为窗口提供隔离 |
| QFI→DSCP 打标放在 `GtpUser`，默认 DSCP=QFI | 对标 Juniper `fiveqi-map`；QFI 0–63 正好落在 DSCP 范围 | 用 INET `DscpMarker`（只能设固定值） |

---

## 7. 已知问题

1. **日字形承载网无 Qbv** — `e2e_ladder` 的 NE 是 `Router`，换 `TsnSwitch` 才能加门控，但会引入 L2 环路（见 7.2）。
2. **L2 环路无生成树** — 日字形存在物理环路，靠 `GlobalArp` 只消除了 ARP 广播；未知单播仍可能泛洪。RSTP 尝试失败：BPDU 到端节点缺 LLC 导致 `Unknown protocol: protocolId = 34`。
3. **DSCP→PCP 映射缺失** — gNB 已能打外层 DSCP，但 L2 交换机分类器读 PCP，入口需要一层转换。
4. **帧抢占未验证** — 结论"巨帧必须上 802.1Qbu"目前是推算 + 间接证据（见 exp-05 §6.2）。
5. **Simu5G 无 5QI 概念** — 现用 DSCP 顶替 QFI，属简化。
6. **无仪表标定** — 所有结果只能算趋势级，不能作为设备验收依据。
7. **CQF（802.1Qch）INET 4.6 不支持** — 需移植 CyclicSim 或自研。

---

## 8. 未完成

- [ ] `e2e_ladder` 的 NE1–NE6 换成 `TsnSwitch` 并加 Qbv — 阻塞：L2 环路无生成树
- [ ] DSCP→PCP 映射模块（承载网入口） — 阻塞：无现成模块，需自写
- [ ] 帧抢占验证（大帧 + 抢占开关对比） — 阻塞：需按官方示例重配"门控+抢占"
- [ ] 接入侧 per-slice 令牌桶 — 阻塞：需自写整形模块
- [ ] T3-2 切片动态扩容 — 阻塞：需控制器（可用仿真时间触发代替）
- [ ] T3-3 链路扰动 — 阻塞：需光衰减器，纯硬件
- [ ] 2 h 长稳 — 阻塞：算力，目前只跑 30 s 缩比

---

## 9. 下一步

按优先级：

1. **先确认环境能跑通**（接手第一件事）：
   ```bash
   ssh a100@222.20.99.7
   cd /media/a100/data/zbw/nasctime/nascTime/simulations/demos/t2_ladder
   source /media/a100/data/zbw/nasctime/omnetpp-6.4.0/setenv
   export LD_LIBRARY_PATH=/media/a100/data/zbw/conda-envs/nasctime/lib:/media/a100/data/zbw/nasctime/omnetpp-6.4.0/lib
   export INET_ROOT=/media/a100/data/zbw/nasctime/inet
   export SIMU5G_ROOT=/media/a100/data/zbw/nasctime/Simu5G
   ../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -c TAS -r 0 --sim-time-limit=2s --result-dir=results_TAS
   ```
2. **给承载网加 Qbv**：把 `e2e_ladder/ProjectBookLadder.ned` 的 NE 改成 `TsnSwitch`，先断开 `NE1–NE2`、`NE3–NE4` 中的一条打破环路，验证 Qbv 生效后再补 RSTP。
3. **写 DSCP→PCP 映射模块**：参考 `GtpUser` 补丁的写法，做成 nascTime 库里的 `simple` 模块。
4. **帧抢占验证**：照 `inet/showcases/tsn/framepreemption` 配置。

---

## 10. 接手须知

- **服务器**：`a100@222.20.99.7`（DSH 里 profile 名 `A100`，密钥 `C:\Users\a\.ssh\id_ed25519`）。项目根 `/media/a100/data/zbw/nasctime`。
- **必须读**：本文件 → [`handoff/01-环境与登录.md`](handoff/01-环境与登录.md) → [`handoff/02-场景与拓扑.md`](handoff/02-场景与拓扑.md) → [`handoff/03-实验与结论.md`](handoff/03-实验与结论.md) → [`handoff/04-已知问题与后续.md`](handoff/04-已知问题与后续.md)。
- **不要重复跑**：T1 的 12 组、T2/T3/T4 的对照实验都已出数，直接看文档；要复现再跑。
- **不要覆盖**：`AI交接文档_项目现状与后续方向.md`（FRER 线历史）、各场景 `results*/` 目录里的既有 `.sca`。
- **提交规范**：`bash experiments/bin/git-save.sh "<中文说明>"`，脚本会自动 `git add` 并排除临时文件。
