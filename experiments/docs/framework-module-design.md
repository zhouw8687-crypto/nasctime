# 端到端确定性网络验证框架（DNV）模块分解与接口设计

> 文档编号：DNV-DD-001 　版本：v0.1（草案） 　日期：2026-10-26 　状态：内部评审
> 位置：`experiments/docs/` 　关联文档：`AI交接文档_项目现状与后续方向.md`（nascTime 现状与实验流程规划）
> 配套文件：`schema/flow-contract.schema.json`、`schema/policy-set.schema.json`、`schema/experiment-spec.schema.json`、`schema/observation.schema.json`、`kpi-definitions.md`

> **上位文档**：项目书四层模型（图 2.3.35）、指标映射、MVP 功能与指标的对应关系、以及同类框架的实现程度调研，见 [`project-model-mapping.md`](project-model-mapping.md)。
> 本文只回答"框架怎么实现"。文中 nascTime 是**可替换的 5G 段仿真替身**，不是项目基线；项目 ≠ nascTime。

## 修订记录

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v0.1 | 2026-10-26 | 初稿：5 层 11 模块分解、4 个数据模型、控制面两级时标、开源底座选型 | — |

---

## 0. 摘要

本文把"端到端确定性网络验证框架"拆成 **5 层 11 个模块**，给出每个模块的职责、输入输出、时序保证、失败语义与首版验收断言；用 **FlowContract / PolicySet / Observation / ExperimentSpec** 四个数据模型作为全框架唯一事实源。第 7 章给出开源底座调研，核心结论：

1. **OMNeT++ 6.4 + INET 4.6 是目前唯一同时覆盖 802.1Qbv（TAS）、802.1Qav（CBS）、802.1Qcr（ATS）、802.1Qci（PSFP）、802.1CB（FRER）与 802.1AS（gPTP）、且自带确定性回归机制（fingerprint）的仿真底座**，可作为最小仿真单元的骨架；其缺项（CQF/802.1Qch、SDN 控制器、动态 BMCA、跨径时延对齐）正好是本框架要自研的部分。
2. **DETERMINISTIC6G 项目的 6GDetCom Simulator v3.0** 是同类框架里最接近的参考实现（OMNeT++/INET 之上、有控制面接口、有 Packet Delay Correction），建议**借鉴其 PDC 设计**用于 DP-4，但不直接作为底座（其 6G 侧偏时延轨迹模型，与"无线内生控制器需要真实信道反馈"的目标不一致）。
3. **最小仿真单元不需要任何"框架级"外部依赖**：单一底座（nascTime + Simu5G + INET，不设模块级适配层，见 ADR-001）+ 3 个自研控制面模块（Orchestrator / RanCtrl / WanCtrl）+ 离线规划器 + Verifier 即可闭环。

---

## 1. 范围与定位

### 1.1 目标

给定一组**业务流契约**（FlowContract）与网络配置，框架能自动完成：

```
spec.yaml（拓扑/流/控制器策略/信道/种子/指标）
  → gen       生成 NED 参数 + ini + manifest.json（唯一事实源）
  → validate  断言"期望参数 == .sca 中真正生效的参数"
  → run       并行、断点续跑、失败重试、逐 cell 状态入库
  → ingest    .sca/.vec → 单一结果库
  → kpi       唯一的指标实现（送达率/分位数/抖动/skew/驻留时间/隔离度）
  → oracle    契约满足判定 + 置信区间 + 回归对比
  → report    自动出表、出图、出结论
```

并支持**控制面闭环**：控制器观察运行中的网络状态，按两级时标调整数据面策略，其效果必须能被同一套指标判定。

**验收口径一句话**：换一台干净机器、只给一个 spec 文件，一条命令产出与历史一致的表和图；中间任何一步失败都必须是**显式失败**，不允许静默产出脏数据。

### 1.2 非目标（明确不做）

| 不做 | 原因 |
|---|---|
| 重新实现 TSN 协议栈 | INET 已完整覆盖 Qbv/Qav/Qcr/Qci/Qcb，重造没有收益 |
| 把 nascTime 改造成框架 | nascTime 是被测系统（SUT）本体，保持其可独立引用（论文 arXiv:2604.04616） |
| **做模块级 SUT 适配层**（统一抽象 INET 与 Simu5G 的节点/协议栈模型） | 见附录 D ADR-001：等价于重写半个 nascTime，且会随两侧版本升级持续腐化 |
| 追求"真实控制器软件"级保真 | 首版控制器在仿真内实现；真实 ONOS/Ryu 接入是独立工作项，不进入本框架排期 |
| 大规模硬件在环 | 首版纯仿真；半实物（Linux `tc-taprio`）列为可选后续，不承诺排期 |

### 1.3 与现有资产的关系

**决策（ADR-001）：唯一底座 = nascTime + Simu5G + INET，同一个 OMNeT++ 工程；不做模块级 SUT 适配层。**

理由：

- Simu5G 本身就是 INET 的扩展（其 README 要求 INET 4.5+），三者共处一个 NED 路径、一个进程、一个事件循环。"5G 段"与"有线 TSN 段"不是两棵树，而是同一棵树里实例化哪些模块的差别。
- 真正不能混的是 **6GDetCom 与 Simu5G**：两者各自绑定不同的 INET 版本与 5G 建模方式（轨迹驱动 vs 全 PHY）。把两者塞进同一个进程，才是"要重写半个项目"的事。
- 因此原方案里的 `wired-tsn` / `ran-only` 降级为**同底座下的场景配置变体**（不同 NED/ini + 关掉不需要的子系统），不是架构层；`trace-based` 降级为**未来可选的建模降级**，首版不做。

| 名称 | 层级 | 首版 | 用途 |
|---|---|---|---|
| `tsn5g`（nascTime 参数化拓扑） | 场景配置（默认） | 唯一首版场景 | 有线 TSN + 5G 桥，端到端 |
| `wired-tsn`（同工程，不实例化 gNB/UE） | 场景配置（对照） | 仅在需要隔离"无线贡献"时临时搭 | 消融对照：证明无线段贡献 |
| `ran-only`（同工程，去掉 TSN 域） | 场景配置（对照） | 同上 | 消融对照：证明 TSN 段贡献 |
| `trace-based`（替换 5G 段建模方式） | **建模降级** | 不做 | 仅当 p99.9 样本量成为硬约束时再评估 |

这条决策的代价是明确的：放弃"一份配置跑四种保真度"的理想，换来"不会在毕业前烂尾"。若将来要接 6GDetCom，那是**另开一个工程**，只共享 `dnv.verify` 的读结果部分，不共享模型。完整权衡见附录 D（ADR-001）。

### 1.4 代号

`DNV` = Deterministic Network Verification framework（暂定，可替换；代码命名空间建议 `dnv.*`）。模块编号 `S-*`（场景）、`DP-*`（数据面）、`CP-*`（控制面）、`V`（验证）。

### 1.5 术语

| 术语 | 含义 |
|---|---|
| SUT | System Under Test，被测系统（本框架中是网络本身，含有线 TSN 与 5G 段） |
| 契约（Contract） | 一条业务流的确定性承诺：带宽、时延、抖动、丢包、可用性、冗余等级、同步组 |
| 契约分解 | 把端到端契约拆成无线段/承载段/核心段/TSN 段的子契约，并留余量 |
| 快/中/慢环 | 0.125–1 ms / 1–100 ms / 0.1–10 s 三级控制时间尺度 |
| skew | 同一同步组内两条流在同一个周期上的到达时刻差 |
| GCL | Gate Control List，802.1Qbv 门控表 |
| PDC | Packet Delay Correction，把快径包延迟到与慢径对齐的机制（DETERMINISTIC6G 提出） |
| 消融实验 | Ablation：关掉某个模块后指标必须变差，否则该模块无贡献 |

---

## 2. 参考架构

### 2.1 分层

```
┌──────────────────── L4 场景层 ────────────────────┐
│ S-1 TrafficGen：XR / 工业控制 / BE 三类流的生成与契约标注 │
└──────────────────────────┬────────────────────────┘
┌──────────────────────────┴──── L3 验证层 ─────────┐
│ V Verifier：spec→manifest→run→ingest→KPI/oracle→report │
│            故障注入 · 负向测试 · 消融实验 · 回归基线      │
└──────────────────────────┬────────────────────────┘
┌──────────────────────────┴──── L2 控制面 ─────────┐
│ CP-3 Orchestrator：契约分解 · 资源账本 · 冲突仲裁 · 准入 │
│   ├─ CP-1 RanCtrl（ms 级，无线内生）                   │
│   ├─ CP-2 WanCtrl（s 级，有线/多径/GCL/时钟）           │
│   └─ CP-4 PolicyEngine（离线求解，产出 policy）         │
└──────────────────────────┬────────────────────────┘
              PolicySet（唯一控制指令载体）
┌──────────────────────────┴──── L1 数据面 ─────────┐
│ DP-1 分类 → DP-2 整形 → DP-3 周期调度 → DP-4 多径同步    │
│                    DP-5 PolicyExec（事务性执行/回滚）     │
└──────────────────────────┬────────────────────────┘
┌──────────────────────────┴──── L0 底座（SUT）─────┐
│ INET 4.6（TSN/队列/时钟） · Simu5G（gNB/UE/MAC）        │
│ · nascTime（5G-TSN 桥/FRER，可选）                      │
└───────────────────────────────────────────────────┘
```

### 2.2 模块清单

| 编号 | 模块 | 层 | 一句话职责 | 首版来源 |
|---|---|---|---|---|
| S-1 | TrafficGen 流量模型库 | 场景 | 生成三类流并标注契约 | 新建（复用 INET app） |
| DP-1 | FlowSense 流识别与契约分类 | 数据面 | 报文 → FlowDescriptor → FlowContract | 新建（复用 INET 分类器） |
| DP-2 | ShaperCtl 整形与契约执行 | 数据面 | 令牌桶/CBS/ATS/PSFP，参数可重配 | 新建（复用 INET shaper） |
| DP-3 | CycleSched 周期映射与队列调度 | 数据面 | GCL 生成→下发→执行；跨域周期对齐 | **扩展**（nascTime TsnAf 已解析 GCL、未下发） |
| DP-4 | MultiPathSync 多径与跨径同步 | 数据面 | 多径绑定 + 跨径时延对齐 + skew 度量 | **扩展**（nascTime FRER F1–F3） |
| DP-5 | PolicyExec 策略执行器 | 数据面 | PolicySet 事务性下发/回滚/回执 | 新建 |
| CP-1 | RanCtrl 无线内生控制器 | 控制面 | ms 级闭环：RB/MCS/DRB QoS/调度权重 | 新建（扩展点复用 Simu5G） |
| CP-2 | WanCtrl 有线网络控制器 | 控制面 | s 级闭环：多径/聚合/GCL/同步策略 | 新建（复用 INET configurator） |
| CP-3 | Orchestrator 全局协同 | 控制面 | 契约分解、准入、资源账本、冲突仲裁 | 新建 |
| CP-4 | PolicyEngine 智能决策 | 控制面 | MILP/启发式/RL 产出 policy | 新建（后置） |
| V | Verifier 验证基座 | 验证 | spec→manifest→run→ingest→KPI→report | 新建（由 `experiments/` 现有脚本演进） |

**与 nascTime 的边界**：nascTime 只贡献 DP-3 的"GCL 解析与桥接语义"和 DP-4 的"FRER 复制/去重"，其余 9 个模块全部新建或扩展自 INET/Simu5G。

### 2.3 部署位置与时间尺度

| 模块 | 运行位置 | 时间尺度 | 触发方式 |
|---|---|---|---|
| S-1 | 仿真内（应用层） | 每流周期 | 定时自消息 |
| DP-1 | 仿真内 | 每包 | 包到达 |
| DP-2 | 仿真内 | 每包 / 每周期 | 入队/出队事件 |
| DP-3 | 仿真内 | 每 slot（125 µs–1 ms） | 定时器 + 包事件 |
| DP-4 | 仿真内 | 每包 / 每窗口 | 包到达 + 对齐定时器 |
| DP-5 | 仿真内 | 每次下发 | 策略消息 |
| CP-1 | **仿真内**（事件驱动） | **1–100 ms（中环）** | 定时器 + 违约事件 |
| CP-2 | **仿真外**（离线/半在线） | **0.1–10 s（慢环）** | 触发（拓扑/违约/KPI 越界） |
| CP-3 | 仿真外（离线） | 事件驱动 | 新流 / 违约 / 周期 |
| CP-4 | 仿真外 | 分钟级 | 批处理 |
| V | 仿真外 | 全流程 | 编排 |

**硬性原则：仿真内只放确定性代码。** 任何求解器（MILP/RL/搜索）不得进入 OMNeT++ 事件循环——否则一次求解耗时会被计入网络时延，制造"仿真器抖动"，且同一 seed 不可复现。CP-2/3/4 通过 policy 文件 + 回放注入，注入时刻由 manifest 显式指定（确定性的"半在线"）。

### 2.4 控制时延预算

闭环的真实性取决于决策时延是否被显式建模：

```
T_decide = T_sample + T_compute + T_deliver + T_apply
```

| 环节 | 含义 | 首版目标 |
|---|---|---|
| T_sample | 观测采集与聚合窗口 | ≤ 10 ms（中环）/ ≤ 200 ms（慢环） |
| T_compute | 决策计算 | ≤ 5 ms（中环，查表/规则）/ 离线不计（慢环） |
| T_deliver | 策略下发传输 | ≤ 1 ms（同节点）/ 仿真外注入为 0（回放） |
| T_apply | 设备生效（需等周期边界） | ≤ 1 个周期 |

约束：`T_decide(fast) ≤ 10 ms`、`T_decide(mid) ≤ 100 ms`、`T_decide(slow) ≤ 2 s`。四个分量由 V 分别测量并写入结果库——**不得用"假设"填值**。

---

## 3. 数据模型（唯一事实源）

### 3.1 设计原则

1. **契约优先**：所有模块的输入输出都能追溯到某条 FlowContract 的某个字段；没有契约的流量不参与确定性判定。
2. **单位显式**：字段名自带单位后缀（`Ms` / `Us` / `Ns` / `Kbps` / `Bytes`），禁止裸数字。
3. **时基统一**：跨模块时间戳一律用**整数纳秒**（`*Ns`），禁止浮点秒；时基来自 gPTP 域（不是仿真器时钟）。
4. **版本化 + 乐观并发**：`PolicySet.generation` 单调递增，下发必须带 `precondition.generation`，不匹配即拒绝。
5. **YAML 进、JSON 中、Parquet 出**：人写 YAML，工具链内部 JSON，结果落 Parquet/CSV。

### 3.2 FlowContract（业务流契约）

一条流的完整描述，含**识别方式**、**流量特征**、**确定性承诺**、**冗余与同步要求**。

```yaml
apiVersion: dnv/v1alpha1
kind: FlowContract
metadata:
  name: icps-actuator-01
  labels: { scenario: factory-floor, tenant: line-a }
spec:
  flowId: "icps-act-01"
  app:
    class: INDUSTRIAL_CONTROL      # XR | INDUSTRIAL_CONTROL | BEST_EFFORT | BULK
    profile: "1ms-cyclic-small"    # 命名模板，便于批量生成
  endpoints:
    src: { node: tsnDeviceA, port: eth1 }
    dst: { node: tsnB[3],     port: eth1 }
  identification:                  # DP-1 的匹配规则
    l2:  { vlanId: 100, pcp: 6 }
    l3:  { dscp: 46, dstPrefix: "10.10.0.0/24" }
    l4:  { proto: udp, dstPort: 5000 }
    tsn: { streamHandle: "0x0102", streamRank: 1 }
    pattern:                       # 可选：在线识别/校验用
      kind: periodic
      periodUs: 1000
      burstFrames: 1
  traffic:                         # S-1 生成 + DP-2 整形共用
    model: periodic
    periodUs: 1000
    frameSizeBytes: { min: 64, max: 128 }
    framesPerPeriod: 1
    maxBurstBytes: 128
  guarantees:                      # 契约本体
    bandwidth: { committedKbps: 1024, peakKbps: 2048 }
    latency:   { maxMs: 2.0, p99Ms: 1.5 }
    jitter:    { maxUs: 100 }
    loss:      { maxRatio: 1.0e-6 }
    availability: { maxOutageMs: 50 }
  redundancy:
    class: R1                      # none | R1 | R2（R1=单路径冗余，R2=双路径冗余）
    pathDiversity: required        # required | preferred | none
    maxSkewUs: 200
  syncGroup: "g1"                  # 同组流要求输出时刻对齐
  priority: 1                      # 冲突仲裁用，0 最高
  admission:
    preemptible: true              # 资源不足时是否可被降级
    maxDegradeSteps: 1             # 最多降几档（降带宽/降冗余）
```

**约束（由 schema 校验，且在 gen 阶段二次断言）**

| 约束 | 说明 |
|---|---|
| `p99Ms ≤ maxMs` | 否则契约自相矛盾 |
| `committedKbps ≤ peakKbps` | 整形器上/下界 |
| `redundancy.class = R2 ⇒ pathDiversity = required` | 双路径冗余必须分径，否则退化为 DRB 级 FRER（已被实验证明无效） |
| `jitter.maxUs < periodUs × 1000` | 抖动不得超过周期，否则周期映射失去意义 |
| `class = INDUSTRIAL_CONTROL ⇒ latency.maxMs ≤ periodMs` | 控制流必须在下一个周期前到达 |

**为什么不用单个优先级数字**：nascTime 的现状是 PCP→DSCP→QFI→DRB 的**单个标量映射**（`frerStreams="7"` 硬编码 DSCP），它无法表达"周期 1ms、抖动 <100µs、双路径、与另一条流同步"。契约是把"业务语义"带进数据面的唯一载体；没有它，DP-2 的整形参数、DP-3 的 GCL、V 的判定只能各自拍脑袋，必然对不上。

### 3.3 契约分解（Orchestrator 核心算法）

端到端时延预算按段拆分，并留余量：

```
latency.maxMs  =  ranMs + xhaulMs + coreMs + tsnMs + marginMs
```

| 段 | 含义 | 取值来源 |
|---|---|---|
| `ranMs` | UE ↔ gNB 空口（含排队、调度、重传） | 信道/调度器标定表（离线扫参得到） |
| `xhaulMs` | gNB ↔ UPF | 拓扑配置 |
| `coreMs` | UPF ↔ NW-TT / 核心网 | 拓扑配置 |
| `tsnMs` | TSN 域内（含桥转发、门控等待） | GCL 计算 + 最坏排队 |
| `marginMs` | 余量，默认 10% 且 ≥ 0.2 ms | 策略 |

判定规则：

1. 每一段取**标定 p99**（不是均值），四段之和 + 余量 ≤ `latency.maxMs` 才准入；
2. 不可行 → 返回 `ADMISSION_REJECT`，附带"哪一段超了多少"，**不允许降级后静默通过**（除非 `admission.preemptible=true` 且降级步数未超限，此时必须记录 `degraded: true`）；
3. 分解结果写入 `SubContractSet`：`ranMs` 段下发给 CP-1，其余段下发给 CP-2；
4. 带宽同法分解：`committedKbps` 在 RAN 侧按 DRB 预留、在有线侧按流预留，两侧之和不得超过链路容量；
5. 可靠性分解：`redundancy.class=R2` 必须在拓扑上找到两条**边不相交**路径，找不到 → `ADMISSION_REJECT`（这正是当前 DRB 级 FRER 失效的根因，必须在准入阶段拦住）。

### 3.4 PolicySet（控制指令）

控制器对数据面的**唯一**指令载体。带 generation、前置条件、事务与回滚。

```yaml
apiVersion: dnv/v1alpha1
kind: PolicySet
metadata:
  name: gen-42-ran-adjust
  generation: 42
  issuedBy: cp1-ranctrl
  issuedAtNs: 1700000000000000000
  validUntilNs: 1700000010000000000
scope:
  domain: RAN                       # RAN | WIRELINE | GLOBAL
  targets: ["gnb1"]
precondition:
  generation: 41                    # 乐观并发：不匹配即拒绝
policies:
  - flowId: "icps-act-01"
    action:
      kind: qos                     # route|shape|schedule|qos|replicate|reserve
      params:
        drb: 2
        priority: 1
        delayBudgetMs: 1.0
  - flowId: "xr-cam-01"
    action:
      kind: reserve
      params: { rbCount: 12, durationMs: 100 }
conflictPolicy:
  mode: reject                      # reject | priority
  tieBreaker: priority              # priority | generation
transaction:
  onFailure: revert
  timeoutMs: 50
  ackRequired: true
```

**语义规定**

| 场景 | 行为 |
|---|---|
| `precondition.generation` 不匹配 | 拒绝，返回 `STALE_GENERATION`，不发半套策略 |
| 同一 target 上两条 policy 冲突且 `mode=reject` | 整包拒绝并回滚 |
| `mode=priority` | 按 `priority` 低者胜；同优先级按 `generation` 新者胜 |
| 任一条 action 执行失败 | 全部回滚到 `generation-1`，返回 `ROLLBACK_DONE` |
| `validUntilNs` 到期未刷新 | 策略失效，回落本地兜底配置（静态 GCL + 严格优先级） |

### 3.5 Observation（观测）

```yaml
apiVersion: dnv/v1alpha1
kind: Observation
metadata: { name: obs-000123, generation: 42 }
window: { startNs: 1700000000000000000, endNs: 1700000100000000000 }
source: { module: gnb1.mac, domain: RAN }
samples:
  - { metric: drb_queue_bytes,   labels: { drb: 2 }, value: 8192,  unit: Bytes }
  - { metric: cqi,               labels: { ue: 3 },  value: 12,    unit: index }
  - { metric: latency_budget_used_ratio, labels: { flow: "icps-act-01" }, value: 0.62, unit: ratio }
```

规定：**只允许上报可测量量**，禁止上报"控制器内部状态"当观测；每条观测必须带 `window` 与 `source`，否则不可归因。

### 3.6 ExperimentSpec（实验规格 = manifest 源头）

```yaml
apiVersion: dnv/v1alpha1
kind: ExperimentSpec
metadata: { name: frer-path-diversity-v1 }
topology:
  kind: tsn5g                      # wired-tsn | tsn5g | ran-only | trace-based
  params: { endpoints: 3, gnb: 1, upf: 2, channel: { fading: true, shadowing: true, thermalNoiseDbm: -95 } }
flows:                             # 引用 FlowContract 文件
  - ref: contracts/icps-act-01.yaml
  - ref: contracts/xr-cam-01.yaml
  - ref: contracts/be-bulk.yaml
controllers:
  ran:      { enabled: true, periodMs: 10,  policy: policies/ran-v1.yaml }
  wan:      { enabled: true, periodMs: 500, policy: policies/wan-v1.yaml }
  orchestrator: { enabled: true, admission: strict }
scenario:
  durationS: 10
  warmupS: 1
  seeds: [1, 2, 3, 4, 5]
  repetitions: 4
kpis:
  - { name: e2e_latency, quantiles: [0.5, 0.99, 0.999] }
  - { name: jitter_pdv,  metric: maxUs }
  - { name: skew,        group: "g1" }
  - { name: contract_violation_ratio }
```

### 3.7 单位与时基约定

| 类别 | 约定 | 反例 |
|---|---|---|
| 时间 | 字段后缀 `Ns`（整数纳秒）、`Us`、`Ms`；内部一律 `int64 Ns` | `delay: 1.5`（无单位） |
| 速率 | `Kbps`（千比特/秒） | `rate: 1e6`（歧义 bps/Bps） |
| 大小 | `Bytes` | `size: 1500` |
| 比例 | `ratio`，取值 [0,1] | `loss: 0.0001%`（字符串） |
| 时基 | gPTP 域时间（`syncGroup` → 域）；无同步时必须显式标 `timebase: simulator` | 混用仿真时钟与 gPTP 时钟 |

---

## 4. 模块接口契约

每个模块给出：**输入 / 输出 / 关键配置 / 时序保证 / 失败语义 / 首版验收断言**。接口以"消息 + 信号 + 配置参数"三种形式表达，避免模块间直接函数调用（保证可替换）。

### 4.1 S-1 TrafficGen（流量模型库）

- **输入**：`FlowContract[]`（`traffic` 段）；`ExperimentSpec.scenario`
- **输出**：应用层流（INET `UdpSourceApp` 等）；`FlowStarted{flowId, tNs}` / `FlowStopped`
- **配置**：三类模板（XR-4K-90fps / 1ms-cyclic-small / bulk-besteffort）、负载倍率、相位抖动
- **时序**：严格按 `periodUs` 发；相位可配（用于构造"同步组"与"错峰"两种场景）
- **失败**：契约参数不可实现（如 `frameSizeBytes.min > max`）→ 启动期失败，不进入仿真
- **验收**：给定 3 类流 × 负载倍率，实测发送速率与 `traffic` 描述偏差 <1%；周期流的实际间隔 p99 偏差 <1 个仿真时间步

### 4.2 DP-1 FlowSense（流识别与契约分类）

- **输入**：报文（含 VLAN/PCP、DSCP、5-tuple、802.1CB StreamID）；`FlowContract.identification`
- **输出**：`FlowDescriptor{flowId, class, contractRef}`（挂到包标签）；未识别流 → `UNCLASSIFIED`（按 BE 处理并计数）
- **配置**：分类规则表（由 manifest 生成）；是否启用在线周期估计
- **时序**：每包 O(1) 查表；在线周期估计仅采样不阻塞转发
- **失败**：同一报文命中多条规则 → 按 `priority` 取最高并记 `AMBIGUOUS_MATCH`；**禁止静默选第一条**
- **验收**：三类混合流分类准确率 100%；人为插入一条无契约流，必须出现在 `UNCLASSIFIED` 计数里；规则冲突用例必须报 `AMBIGUOUS_MATCH`

*复用*：INET `PcpClassifier` / `PacketClassifier` / `StreamIdentifier` / `StreamClassifier` / `ContentBasedClassifier`。

### 4.3 DP-2 ShaperCtl（整形与契约执行）

- **输入**：`FlowDescriptor`；`ShapePolicy`（PolicySet `action.kind=shape`）
- **输出**：整形后队列；`ShapingViolation{flowId, atNs, committedKbps, actualKbps}`；`ShapingApplied{generation}`
- **配置**：`shaperType ∈ {TB, LB, CBS, ATS}`、桶参数 `{rateKbps, burstBytes}`、队列深度、每流/每类粒度
- **时序**：入队/出队事件同步处理；**参数切换只在周期边界生效**（避免半个周期用新参数造成撕裂）
- **失败**：参数非法（`committed > peak`、`burst < MTU`）→ 拒绝下发并回滚到上一 generation；队列溢出 → 按契约优先级丢弃并计数，**不得静默丢弃**
- **验收**：注入超发 20% 的流，实际出队速率 ≤ `committedKbps × 1.05`；关闭整形器的对照场景中，同流 p99 恶化 ≥ 20%（否则整形器无贡献）

*复用*：INET `TokenBucket` / `LeakyBucket` / `CreditBasedShaper` / `AsynchronousShaper`、`queueing/meter`、`StreamFilter`（PSFP 令牌桶/统计 policer）。

### 4.4 DP-3 CycleSched（周期映射与队列调度）

- **输入**：`FlowContract[]` 的周期与时延要求；`SchedulePolicy`（GCL 或调度权重）
- **输出**：生效的 GCL；`GateStateChanged{port, tNs, gates}`；`ScheduleFeasibility{ok, slackNs}`
- **配置**：门控周期 `cycleNs`、每端口 GCL、队列→TC 映射、调度器类型（SP/WRR/DRR/CBS）
- **时序**：GCL 按 gPTP 时基对齐；**跨域对齐**要求无线侧 DRB 调度窗口与有线侧门控窗口同相位
- **失败**：GCL 不可行（某流在最坏排队下超出窗口）→ `ScheduleFeasibility.ok=false` 并给出最小 slack 缺口；**不得下发不可行 GCL 后继续跑**
- **验收**：①GCL 与实测发送窗口对齐（逐窗口比对，偏差 <1 µs）；②关键流 jitter 相比无门控下降 ≥ 50%；③故意把周期错配 1/2 相位，必须被可行性检查拦下

*复用*：INET `GateControlList` / `PeriodicGate` / `Ieee8021qTimeAwareShaper`、`PriorityScheduler` / `WrrScheduler`、`EagerGateScheduleConfigurator` / `Z3GateScheduleConfigurator` / `TSNschedGateScheduleConfigurator`；Simu5G `QoSAwareScheduler`（作为跨域对齐的落点）。
*缺口*：INET 4.6 **无 CQF（802.1Qch）**，周期映射若要做"双缓冲乒乓队列"，需用 `PeriodicGate` + 两个队列自研近似。

### 4.5 DP-4 MultiPathSync（多径与跨径同步）

- **输入**：`RedundancyPolicy`（路径集、对齐模式）；报文
- **输出**：对齐后的单份流；`PathRtt{pathId, rttNs}`；`SkewMeasured{group, skewNs}`；`PathHealth{pathId, lossRatio, state}`
- **配置**：`alignMode ∈ {none, slowest, targetDelay}`、`targetDelayNs`、重排序窗口、去重窗口、路径集
- **时序**：包级插入可调延迟（等价于"延迟线"）；对齐在**出口侧**做，不得在入口侧做（否则丢包率失真）
- **失败**：某路径 RTT 突增超出 `targetDelayNs` 的补偿能力 → 降级为"只用最快路径"并告警 `ALIGNMENT_DEGRADED`
- **验收**：两路径基线时延差 10 ms 时，输出 skew ≤ `maxSkewUs`，且丢包率不因对齐而上升；单路径中断后 50 ms 内恢复同步；**关闭对齐器时 skew 必须显著劣化**（消融对照）

*复用*：nascTime `FrerReplicator` / `FrerRecovery`（F1–F3）、INET `StreamSplitter` / `StreamMerger`。
*借鉴*：DETERMINISTIC6G 的 **Packet Delay Correction（PDC）**——把快径报文延迟到与慢径对齐，正是本模块 `alignMode=slowest` 的参考实现思路。

### 4.6 DP-5 PolicyExec（策略执行器）

- **输入**：`PolicySet`；当前配置版本
- **输出**：`PolicyAck{generation, result}` / `PolicyNack{code, detail}`；生效配置快照
- **配置**：事务超时、回滚策略、可在运行期开关的"空执行"（dry-run）
- **时序**：整包原子生效；**跨设备生效顺序**由 `scope.targets` 顺序决定，且必须全成或全回滚
- **失败**：任一 target 失败 → 回滚并 `PolicyNack`；`precondition` 不匹配 → `STALE_GENERATION`；超时 → `TIMEOUT`
- **验收**：①故意注入冲突策略，必须 `reject` 且现场配置不变；②注入"第 2 个 target 失败"的用例，第 1 个 target 必须回滚；③连续 1000 次下发无泄漏（内存/队列）

### 4.7 CP-1 RanCtrl（无线侧内生控制器）

- **输入**：`Observation`（DRB 队列、CQI、剩余时延预算、丢包率、RB 利用率）；`SubContractSet.ran` 段
- **输出**：`PolicySet{domain: RAN}`（RB 配额、MCS 偏置、调度权重、DRB QoS 参数、准入决策）
- **配置**：控制周期（默认 10 ms）、死区（避免抖动）、最大单步调整幅度、失效兜底策略
- **时序**：事件驱动 + 周期定时器；`T_decide ≤ 10 ms`；生效不晚于下一个 slot
- **失败**：观测缺失 → 保持上一策略并告警；连续 3 个周期不可用 → 切本地兜底（静态 GBR + 严格优先级）
- **验收**：信道恶化后 100 ms 内把高优流 p99 拉回契约内；断开控制器（固定参数）时同场景违约率显著上升——**这是"内生控制有效"的唯一证据**

*复用*：Simu5G `QoSAwareScheduler`（唯一消费 `drbQosConfig` 的调度器，MAXCI/PF/DRR 均不读——已有实验结论）。

### 4.8 CP-2 WanCtrl（有线侧网络控制器）

- **输入**：拓扑与链路状态；`SubContractSet.wireline`；`PathHealth`；`SkewMeasured`
- **输出**：`PolicySet{domain: WIRELINE or GLOBAL}`（路径集、聚合关系、GCL、同步策略）
- **配置**：规划周期（默认 500 ms）、触发条件（拓扑变化/违约/KPI 越界）、是否启用"过渡态规划"
- **时序**：`T_decide ≤ 2 s`；多设备重配必须**分阶段过渡**，任意中间态不得造成瞬时违约
- **失败**：找不到可行解 → 保持现状 + `ADMISSION_REJECT` 上报 CP-3；GCL 求解超时 → 用贪心解并标注 `heuristic: true`
- **验收**：拓扑删一条边后，重算并下发，端到端契约仍满足；重配过程中违约包数 ≤ 1 个周期量级；**关闭多径协同后 R2 流的送达率显著下降**

*复用*：INET `StreamRedundancyConfigurator`（算冗余树）、`GateScheduleConfigurator` 系列（算 GCL）、`FailureProtectionConfigurator`。
*借鉴*：OpenCNC 的"过渡配置规划"（避免重配过程掉性能）——这正是多设备批量下发最容易被忽略的部分。

### 4.9 CP-3 Orchestrator（全局协同）

- **输入**：`FlowContract` 请求、当前拓扑与资源账本、两控制器的能力上报
- **输出**：`SubContractSet`（分解结果）、`AdmissionDecision`、`ArbitrationResult`、`GlobalLedger` 快照
- **配置**：余量策略、降级策略、仲裁规则（优先级/租户/时序）
- **时序**：慢环（事件触发）；契约分解本身必须**确定性**（同一输入同一输出，禁止随机化）
- **失败**：分解不可行 → `REJECT` 并给出"超出的段与量"；两控制器目标冲突 → 按 `priority` 仲裁并记录仲裁原因
- **验收**：①构造一个端到端不可行的请求（如 1 ms 端到端跨 5G），必须 `REJECT` 而不是"跑起来看起来还行"；②构造无线侧与有线侧冲突的目标，仲裁结果可复现（跑 3 次一致）

### 4.10 CP-4 PolicyEngine（智能决策，后置）

- **输入**：`Observation` 历史、资源账本、目标函数（加权：违约率、资源效率、切换次数）
- **输出**：候选 `PolicySet`（带 `score` 与 `reason`）；**不直接下发**
- **配置**：求解器（MILP / 贪心 / 规则 / RL）、候选集规模、时限
- **时序**：离线批处理；结果带 `solver`、`timeMs`、`optimality` 元数据
- **失败**：超时/无解 → 回退到启发式基线，并标注 `fallback: true`
- **验收**：与启发式基线对比，至少 1 个 KPI 显著改善（如违约率 −30%）且**无新增违约**；`reason` 可解释到具体约束

### 4.11 V Verifier（验证基座）

- **输入**：`ExperimentSpec`；源码版本指纹；结果目录
- **输出**：`manifest.json`、`results.duckdb`、KPI 表、报告、`regression.json`
- **配置**：KPI 定义、容差、并发度、是否启用参数生效断言（**默认必须启用**）
- **时序**：每个 cell（config × seed × repetition）原子完成；失败重试 3 次后落 `.FAILED`
- **失败**：参数未生效 → cell 判 `FAILED` 且不入库；`.sca` 缺失/损坏 → 重跑；任何"部分成功"禁止入库
- **验收**：见 §8

---

## 5. 控制面闭环

### 5.1 两级时标与协同

```
t(ms)  0      1      2      5      10     50     100    500    1000
       |------|------|------|------|------|------|------|------|
DP门控  |<125µs>|<125µs>| ...                                        (每个 slot 一次)
CP-1   采样(1ms)→决策(≤5ms)→生效(下个 slot)
CP-2                       观测(100ms窗口) → 规划(≤1s) → 分批下发
CP-3   契约事件(新流/违约/拓扑变化) → 分解 → 仲裁 → 下发
V      全程记录：策略版本、决策时延、生效时刻、指标窗口
```

### 5.2 冲突仲裁规则

| 冲突类型 | 判定 | 记录 |
|---|---|---|
| 同一流被 CP-1 与 CP-2 同时改（如 DRB 优先级 vs 路径） | 契约分解已划清域：CP-1 只管 `ran*` 字段，CP-2 只管路径/GCL；越界即 `OUT_OF_SCOPE` 拒绝 | 仲裁码 |
| 同域内两条 PolicySet 同 generation | 后到者 `reject`（防重放） | `DUPLICATE_GENERATION` |
| 资源不足，CP-1 想降级 vs CP-2 想保冗余 | 按契约 `priority`；同级按"先满足时延后满足冗余" | `TRADEOFF_APPLIED` |
| 契约过期（`validUntilNs`） | 回落本地兜底 | `FALLBACK_ACTIVE` |

### 5.3 失效降级（fail-safe）

| 失效 | 降级行为 | 必须可观测 |
|---|---|---|
| CP-1 失联 | 保持最后一版 RAN 策略；≥3 周期后切静态 GBR + 严格优先级 | `controller_state=STALE` |
| CP-2 失联 | GCL 保持；新流不再准入 | `ADMISSION_FROZEN` |
| DP-5 回滚失败 | 整端口切兜底配置（静态 GCL + SP），并置 `SAFE_MODE` | 告警 + 计数 |
| 时钟失步（gPTP 偏差超阈值） | 停用门控（避免错相位伤害），切 SP 调度 | `SYNC_LOST` |

> **原则**：任何控制器失效都必须让网络"降级但仍可预测"，且降级本身要出现在指标里——这是"验证框架"区别于"演示系统"的地方。

---

## 6. 底座映射：复用 vs 自研

以 INET 4.6 源码树（`/media/a100/data/zbw/nasctime/inet`）与官方 TSN showcase 为准：

| 框架需求 | 可直接复用的模块 | 判定 |
|---|---|---|
| 流分类（PCP/DSCP/StreamID） | `PcpClassifier`、`PacketClassifier`、`StreamIdentifier`、`StreamClassifier`、`ContentBasedClassifier` | **复用**，仅加"契约绑定"层 |
| 整形（令牌桶/漏桶/CBS/ATS） | `TokenBucket`、`LeakyBucket`、`CreditBasedShaper`、`AsynchronousShaper` | **复用**，加可重配 wrapper |
| 门控与周期映射 | `GateControlList`、`PeriodicGate`、`Ieee8021qTimeAwareShaper` | **复用**（Qbv 部分） |
| CQF / 802.1Qch 双缓冲 | —— | **自研**（INET 无此模块，用 `PeriodicGate` + 双队列近似） |
| 队列调度 | `PriorityScheduler`、`WrrScheduler`、`PacketScheduler` | **复用** |
| PSFP 流过滤/监管 | `StreamFilter`（令牌桶/统计 policer，见 showcase `streamfiltering`） | **复用** |
| GCL 自动计算 | `EagerGateScheduleConfigurator`、`Z3GateScheduleConfigurator`、`TSNschedGateScheduleConfigurator` | **复用**（且有 SAT/TSNsched 两种求解路线） |
| FRER 复制/消除/冗余树 | `StreamSplitter`、`StreamMerger`、`StreamRedundancyConfigurator`、`FailureProtectionConfigurator` | **复用** |
| 时间同步 | `Gptp`、`MultiDomainGptp`、`Oscillator`、servo | **复用**（多域 gPTP 已有） |
| 动态 BMCA | —— | **自研**（nascTime 只有静态校验；INET gPTP 无动态 BMCA） |
| 无线 MAC 调度 | Simu5G `QoSAwareScheduler`、`LteDrr`、`LteMaxCi`、`LtePf` | **复用 + 扩展**（新增策略参数通道） |
| 无线 QoS 参数化 | Simu5G `drbQosConfig`（仅 QOS_PF 消费） | **扩展**（让 CP-1 可运行时改） |
| SDN / 集中控制器 | —— | **自研**（INET 4.6 已无 OpenFlow/SDN 模块，全局 grep 为空） |
| 多径/ECMP 路由 | —— | **自研**（用 FRER 路径绑定或显式多路径配置，非 IP 层 ECMP） |
| 跨径时延对齐 | —— | **自研**（借鉴 DETERMINISTIC6G PDC） |
| 测量（时延/抖动/驻留） | `endToEndDelay`、`residenceTime`、`jitter`、`flow` 测量 showcase | **复用** |
| 确定性回归 | INET fingerprint 测试（`tests/fingerprint`） | **复用**（作为 V 的回归锚点） |

**结论**：数据面 80% 可复用，控制面 100% 自研，验证层 60% 可复用（测量 + 指纹 + 现有 `experiments/` 脚本演进）。

---

## 7. 开源底座选型调研

### 7.1 评估维度

| 维度 | 含义 | 为什么重要 |
|---|---|---|
| D 数据面覆盖 | Qbv/Qav/Qcr/Qci/Qcb/gPTP 是否齐备 | 缺一项就要自研成月的工作量 |
| W 无线段 | 是否有可用的 5G NR 模型（PHY/MAC/调度） | "无线侧内生控制器"必须有真实信道反馈 |
| C 控制面 | 是否提供控制器/配置接口/CNC | 决定自研量 |
| T 时间保真 | 时钟模型、门控精度、可复现性 | "确定性"结论的可信度 |
| S 规模 | 能否支撑多 seed / 多端点 / 大批量 | 决定论文样本量 |
| M 成熟度 | 文档、案例、维护活跃度 | 决定踩坑成本 |
| L 许可 | 许可证与商用限制 | 决定能否交付 |

### 7.2 候选清单

| # | 候选 | 类型 | 关键事实（来源） |
|---|---|---|---|
| 1 | [INET 4.6 + OMNeT++ 6.4](https://inet.omnetpp.org/) | 离散事件仿真 | TSN showcase 覆盖 TAS/CBS/ATS/PSFP/FRER/帧抢占/直通/gPTP，且有三套 GCL 求解器（[gate scheduling](https://inet.omnetpp.org/docs/showcases/tsn/gatescheduling/index.html)）；无 SDN、无 CQF |
| 2 | [6GDetCom Simulator v3.0](https://github.com/DETERMINISTIC6G/6GDetCom_Simulator)（DETERMINISTIC6G） | 仿真框架（OMNeT++/INET 之上） | [Zenodo 发布](https://zenodo.org/records/15305119)；特性：可替换时延轨迹、**Packet Delay Correction**、动态场景 + 调度器集成；[D4.4](https://zenodo.org/records/18223028) 明确"network control plane interfaces to configure the network data plane" |
| 3 | [6GDetCom Emulator v1.0](https://zenodo.org/records/15305265) | 半实物（Linux Qdisc） | 用 Linux Qdisc 模拟 TSN 特征时延，面向融合 6G/TSN |
| 4 | [ns-3 + TAS 模块](https://github.com/DenKrysos/Time-Aware-Shaper-TAS-in-ns-3) | 仿真 | ns-3 的 802.1Qbv 时间感知整形器实现（第三方） |
| 5 | [OpenTSN](https://github.com/flowseek/openTSN) | 真实 TSN 交换机 + 控制器 | 开源 TSN 系统（交换机/端系统/控制器），见 [CCF ToN 论文](https://link.springer.com/article/10.1007/s42045-020-00029-8) |
| 6 | [OpenCNC TSN service](https://git.cs.kau.se/hamzchah/opencnc_tsn-service) | 真实 CNC（Go + ONOS + K8s） | 含 PE 与 RAE：调度、QoS、流优先级、转发计算、**重配过渡规划** |
| 7 | ONOS / Ryu / ODL + Mininet/OVS | 真实控制面 + 软交换 | 控制面 API 成熟，但无时间感知转发 |
| 8 | P4 / BMv2 + ONOS | 可编程数据面 | 可编程性强，但无门控/时钟硬件语义 |
| 9 | Linux `tc-taprio`/`cbs`/`etf` + TSN 网卡 | 真实数据面 | 内核原生 Qbv/CBS/ETF，需硬件时间戳 |
| 10 | 开源 TSN 调度评估框架（RTSS 2025 WIP，[IEEE](https://www.computer.org/csdl/proceedings-article/rtss/2025/964200a628/2cTzHvdwQco)） | 评估框架 | 面向 TSN 调度研究的开源评估框架，可参考其指标口径 |

### 7.3 对比矩阵

| 候选 | D 数据面 | W 无线 | C 控制面 | T 时间保真 | S 规模 | 与本框架关系 |
|---|---|---|---|---|---|---|
| INET 4.6 + OMNeT++ | **全覆盖**（除 CQF） | 需 Simu5G | 无 | **高**（时钟模型 + 指纹） | 高（可 512 核并行） | **主选底座** |
| 6GDetCom Simulator | 高（依赖其 INET 版本） | 中（时延轨迹/PDC） | **有接口** | 中高 | 中 | **首选参考**（PDC 直接用于 DP-4） |
| ns-3 + TAS | 中（Qbv 有，Qci/CB/gPTP 散落） | 5G-LENA 强 | 无 | 中 | 高 | Plan B |
| OpenTSN | 真实 | 无 | 有集中控制器 | 高（硬件） | 低（受硬件数） | 硬件对照 / 功能验证 |
| OpenCNC | 无（只管控制） | 无 | **强**（含过渡规划） | n/a | n/a | **CP-2 架构参考** |
| ONOS/Ryu + Mininet | 低（无门控） | 无 | **强** | 低 | 中 | 控制面 API 原型 |
| P4/BMv2 | 可编程 | 无 | 有 | 低（无时钟语义） | 中 | 不适用 |
| Linux tc + TSN 网卡 | 真实 | 无 | 无 | 高（需硬件） | 低 | 半实物验收（第三阶段） |

### 7.4 结论

**最小仿真单元 = 单栈仿真，不引入外部框架级依赖：**

```
OMNeT++ 6.4 + INET 4.6 + Simu5G（数据面 / 时钟 / 无线）
  + 3 个自研控制面 simple module：Orchestrator / RanCtrl / WanCtrl
  + 1 个 TSN+5G 集成拓扑（nascTime 参数化 NED；不设适配层，见 ADR-001）
  + Python 离线规划器（产出 PolicySet 文件，按 manifest 指定时刻回放注入）
  + Verifier（spec→manifest→run→ingest→KPI→report）
```

四条理由：

1. **数据面保真度最高**：Qbv/Qci/CB/gPTP 全在，且官方 showcase 给的是可运行案例而不是"文档声称支持"；三套 GCL 求解器（贪心/SAT/TSNsched）可直接给 CP-2 当"求解后端"。
2. **确定性可回归**：INET 的 fingerprint 机制天然适配"验证框架"——任何改动都能回答"结论是否变了"。
3. **控制面本就要自研**：没有任何开源项目提供"无线 ms 级 + 有线 s 级 + 全局仲裁"这套东西；与其适配别人的控制器框架（ONOS 的南向是 OpenFlow/P4，与 TSN 门控语义不匹配），不如在仿真内实现，日后另做一个小桥接层接真实控制器。
4. **不选 6GDetCom 作底座的原因**：它把 6G 侧更多做成**时延轨迹模型**（发布说明明确有"option to replace delay traces"），适合研究"确定性传输的上层机制"，但你的"无线侧内生控制器"必须看到真实 CQI/队列/信道反馈才能闭环。**但它的 PDC 是 DP-4 的现成设计，应当直接借鉴而不是重造。**

**关于 trace-based（已移出首版）**：大批量 seed（p99.9 需要 ≥10⁴ 样本）用 Simu5G 全 PHY 会跑不动，但"时延轨迹注入"是替换 5G 段的建模方式，属独立工作项（见 ADR-001）。首版靠白名单录制 + 512 核并行把规模做上去；若仍不够再评估降级建模，而不是先造适配层。

### 7.5 许可证与复用边界

| 资产 | 许可（以仓库 LICENSE 为准） | 复用方式 |
|---|---|---|
| INET | LGPL-3.0（学术免费，需注册下载） | 直接链接，不改内核 |
| OMNeT++ | 学术免费（商用需授权） | 工具链 |
| Simu5G | 见仓库 LICENSE | 直接链接 |
| nascTime | LGPL-3.0 | 作为唯一底座（SUT 本体） |
| 6GDetCom | 见 GitHub/Zenodo 元数据 | **只借鉴设计，不复制代码**（避免版本耦合） |
| OpenTSN / OpenCNC | 见各自仓库 | 设计参考 |

> 交付注意：若框架要对外发布，**只发布自研的 `dnv.*` 模块 + 补丁**，不打包 INET/Simu5G 源码；依赖以版本锁定文件声明。

---

## 8. 验证基座设计

### 8.1 KPI 口径

完整定义见 [`kpi-definitions.md`](kpi-definitions.md)，此处只列清单与来源：

| KPI | 单位 | 来源 | 备注 |
|---|---|---|---|
| 送达率 / 丢包率 | ratio | 应用层收发计数 | 口径固定：`1 − Σrecv / Σsent`，分子分母都必须来自 manifest 声明的窗口 |
| 端到端时延 mean/p50/p99/p99.9/max | ms | 应用层时间戳 | 必须同一时基（gPTP 域） |
| 抖动 PDV | µs | 相邻包时延差（RFC 3393） | 与"时延标准差"分开报告，二者不可混用 |
| skew | µs | 同 `syncGroup` 内两流同周期到达时刻差 | 无同步组则不计 |
| 契约违反率 | ratio | 逐窗口判定 | 见 8.2 |
| QoS 隔离度 | ms | 高优类 p99 − BE 类 p99 | 对标论文"1.16ms gap"的论证方式 |
| 5GS 驻留时间 mean/var/max | µs | DS-TT 驻留时间信号 | 对标论文 Table VI |
| 同步误差 | ns | gPTP 从钟与主钟偏差 | 需真值（仿真器已知），不是估计值 |
| 控制性能 | — | 收敛时间、超调、振荡次数、决策时延 | 控制器专属 |
| 资源效率 | ratio | RB 利用率、链路利用率 | 用于"智能"的性价比论证 |
| 门控命中率 | ratio | 包实际发送时刻落在门控窗口内的比例 | DP-3 的直接证据 |

### 8.2 Oracle：四类断言

| 类型 | 断言 | 不通过的处置 |
|---|---|---|
| **契约满足** | 对每条流：`p99 ≤ p99Ms` ∧ `max ≤ maxMs` ∧ `loss ≤ maxRatio` ∧ `skew ≤ maxSkewUs`（若声明） | 记录违约窗口，标 `CONTRACT_VIOLATED`，**不阻断仿真**（违约本身是结果） |
| **配置生效** | manifest 中每个参数在 `.sca` 的 `config/par` 段存在且相等 | 立即 `FAILED`，不入库（防止"静默用默认值"这类历史坑） |
| **消融有效** | 关掉模块 M 后，M 声称改善的 KPI 必须显著劣化 | 否则标 `MODULE_NO_EFFECT`——**这是"智能"与"优化"类工作的唯一可信证据** |
| **负向必失败** | 注入错误配置/不可行契约，框架必须拒绝 | 若"通过"，说明验证器有漏洞，优先级高于任何性能结论 |

### 8.3 消融实验（Ablation）设计

每个模块上线时必须同时提交"开/关"两套结果。示例：

| 被消融对象 | 判据 | 期望方向 |
|---|---|---|
| DP-2 整形器 | 超发场景下 p99 与丢弃率 | 关闭后 p99 显著上升 |
| DP-3 门控 | 关键流 jitter | 关闭后 jitter 上升 ≥ 50% |
| DP-4 对齐器 | skew | 关闭后 skew ≈ 路径时延差 |
| CP-1 控制器 | 信道恶化后的违约率 | 关闭后违约率上升 |
| CP-2 多径协同 | R2 流送达率 | 关闭后送达率下降 |
| CP-4 智能调度 | 违约率/资源效率 | 关闭后至少一项变差 |

> 没有消融，就无法区分"框架跑通了"和"框架有价值"。这一节应写进论文的实验方法。

### 8.4 负向测试清单（必须全部为 FAIL）

1. 参数路径写错（如 `phy.channelModel[0].fading` 而非 `cellularNic.channelModel[0]`）→ gen/validate 阶段拒绝；
2. `committedKbps > peakKbps` 的契约 → schema 拒绝；
3. `redundancy.class=R2` 但拓扑无两条边不相交路径 → 准入拒绝；
4. 端到端预算不可行（1 ms 跨 5G）→ 准入拒绝；
5. 两条 PolicySet 同 generation → 后到者拒绝；
6. 控制器下发越界字段（CP-1 改路径）→ `OUT_OF_SCOPE` 拒绝；
7. GCL 不可行（窗口装不下最坏排队）→ 拒绝下发；
8. `.sca` 缺失/损坏 → 重跑，不产出空表。

### 8.5 故障注入清单

| 注入 | 目的 | 观测 |
|---|---|---|
| 信道恶化（fading/shadowing/噪声抬升） | 检验 CP-1 闭环 | 收敛时间、违约率 |
| 单路径中断 | 检验 DP-4 切换与 CP-2 重算 | 恢复时间、skew 尖峰 |
| 时钟漂移/失步 | 检验门控失效降级 | `SYNC_LOST`、jitter |
| 突发过载（BE 流量 ×N） | 检验整形与隔离 | 高优流 p99、隔离度 |
| 控制器冻结/失联 | 检验 fail-safe | 降级是否可预测 |
| 策略回滚失败 | 检验 `SAFE_MODE` | 是否落入兜底配置 |

### 8.6 可复现性

| 要求 | 实现 |
|---|---|
| 版本锁定 | `env.lock.yaml`：OMNeT++ / INET / Simu5G / gcc / conda / 内核版本 |
| 源码可追溯 | 三棵树 `git init`（当前均无 `.git`）+ fork patch 存档 |
| 运行可追溯 | 每 run 落 `run_meta.json`：git 短哈希、ini sha256、完整参数、seed、退出码、耗时 |
| 结果可复算 | 同一 manifest + 同一机器 → 指标逐行一致（除显式随机种子外） |
| 结论可回归 | `regression.json` 与基线对比，偏差超容差即报警 |
| 存储可控 | 白名单录制（只录 `endToEndDelay`/`residenceTime` 等必要 vector），单 run < 30 MB（现状 526 MB） |

---

## 9. 路线图与工作分解

**排期总原则：论文线优先，框架线只做服务论文线的最小集。** 控制面模块（CP-1/CP-2/CP-3/CP-4）在论文线稳定前不启动。

| 线 | 顺序 | 判据 |
|---|---|---|
| **论文线（主线）** | 现有 60 run 重分析 → F3 跨 PDU 会话路径分集 → PDC 式跨径对齐 → 投稿 | 每一阶段都有可引用的数字 |
| **框架线（支撑）** | P0 验证层（spec/manifest/KPI/参数生效断言）+ P1 的 GCL 生效验证 | 论文线每个结论可复算、可回归 |
| **控制面（后置）** | CP-1 → CP-2 → CP-3 → CP-4 | 仅在论文线完成后评估 |

> **PDC 的先后顺序很重要**：PDC（把快径延迟到与慢径对齐）只有在**存在两条真正不同的路径**时才有意义。当前 `FrerAsym_N15` / `FrerSym_N15` 是 DRB 级绑定，主份与副本共享同一条 N3 与同一条无线链路，两副本的时延差基本只剩排队与调度抖动，**没有"跨径时延差"可对齐**。因此 PDC 必须排在 F3（跨 PDU 会话）或 F4（双连接）之后。**对齐本身还有预算约束**：PDC 用"延迟快径"换同步，代价是给最坏时延增加 Δ。若端到端预算是 2 ms 而两径差 10 ms，对齐后必然违约——此时正确动作是 CP-2 换径（选时延相近的路径对），而不是硬对齐。所以"多径"与"对齐"是两个决策：**先选径，再对齐**。反过来，一旦有了跨径，PDC 恰好能治你们在 QOS_PF 下观察到的失效机制——主份时延超过 `windowTimeout=0.1s` 导致恢复窗口重置、去重失效（Asym 10.43% 那一组）。

| 阶段 | 内容 | 交付物 | 验收 | 估时 |
|---|---|---|---|---|
| **P0 地基** | 四个 schema + manifest 生成器 + KPI 定义 + 参数生效断言 + 版本锁 | `schema/*.json`、`gen_configs.py`、`kpi.py` v0 | 故意写错参数必须 FAIL；复算历史 CSV 逐行一致 | 1 周 |
| **P1 单域闭环** | S-1 → DP-1 → DP-2 → DP-3（在 nascTime 拓扑上先让 TSN 侧 GCL 生效，不依赖 5G 段）→ V | "GCL 生效"最小场景 + 报告 | 三类流按契约传输；关整形器/门控指标劣化 | 2–3 周 |
| **P2 无线纳入** | CP-1 快环 + DP-3 跨域周期对齐 + DP-5 执行器 | `tsn5g` 场景 + 闭环报告 | 信道恶化 100 ms 内恢复；控制器关闭则违约率上升 | 3–4 周 |
| **P3 多径同步** | DP-4 跨径对齐 + CP-2（复用 F3/F4） | 多径场景 + skew 报告 | 路径差 ≤ 时延预算余量时 skew ≤ 200 µs；路径差超出余量时必须换径而非硬对齐；断径 50 ms 恢复 | 3–4 周 |
| **P4 全局协同** | CP-3 仲裁/准入 + CP-4 求解器 | 端到端准入与仲裁实验 | 不可行请求必被拒；仲裁可复现 | 4 周+ |
| **P5 半实物（可选）** | `tc-taprio` 半实物对照（trace-based 已移出首版） | 保真度对比报告 | 同一契约在仿真与半实物下结论方向一致 | 2–3 周 |

**硬依赖**：P0 必须在 P1 之前（否则后续全部返工）；DP-1 先于 DP-2/DP-3（无契约无法配整形/门控）；DP-5 先于 CP-1/CP-2（无执行器，控制器无处下发）。

**里程碑判据（建议写进验收）**：

- M1（P1 结束）：一条命令从 spec 产出"三类流契约满足表"，且任意单模块关闭后指标劣化可量化；
- M2（P2 结束）：无线侧 QoS 自适应闭环可复现，决策时延四分量全部有测量值；
- M3（P3 结束）：跨径时延差被消除到契约内，skew 有上界并可解释；
- M4（P4 结束）：不可行请求拒绝率 100%，仲裁结果 3 次一致。

---

## 10. 风险与开放问题

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| 1 | INET 无 CQF（802.1Qch） | 周期映射只能做 Qbv 近似 | 用 `PeriodicGate` + 双缓冲近似，并在论文中明确"非标准 CQF" |
| 2 | INET 无动态 BMCA | 时钟控制环只能开环 | 第一版静态 BMCA + 时钟漂移注入；动态 BMCA 列为独立课题 |
| 3 | 仿真内控制器与"真实控制器"语义差异 | 结论可迁移性受质疑 | 控制面按"策略文件"接口设计，可在不改数据面的前提下替换为真实控制器（独立工作项，不承诺排期） |
| 4 | Simu5G 全 PHY 慢，p99.9 需 ≥10⁴ 样本 | 实验矩阵跑不完 | 白名单录制 + 512 核并行；trace-based 已移出首版（ADR-001） |
| 5 | 跨域时间基准不一致 | skew/时延数字不可解释 | 强制 `syncGroup → 802.1AS 域` 映射；无同步时标 `timebase: simulator` |
| 6 | 与已有 FRER 论文结论的口径冲突 | 论文叙事打架 | 明确分工：已有论文讲"5G 桥能力与 FRER 分集"，本框架讲"确定性验证方法学 + 控制闭环" |
| 7 | 6GDetCom/OpenTSN 版本耦合 | 引入不可控依赖 | 只借鉴设计不复制代码；以 URL + 版本号记录参考 |
| 8 | "智能调度"无法证明有效 | 沦为演示 | 强制消融实验 + 与启发式基线对比 + 可解释 reason |
| 9 | **过度抽象：统一 SUT 适配层** | 工作量等价于重写半个 nascTime，最易烂尾 | ADR-001 明确不做；若要第二底座则另开工程，只共享 `dnv.verify` |
| 10 | 框架线挤占论文线 | 毕业前没有可引用成果 | 排期总原则（§9）：控制面在论文线稳定前不启动 |

**开放问题（需要在设计评审上定）**

1. 控制面第一版是否全部在仿真内？（本文建议：CP-1 在内，CP-2/3/4 在外，理由是确定性与可复现）
2. `syncGroup` 的语义是"同周期到达"还是"同时刻到达"？前者可用门控实现，后者需要 PDC 级对齐。建议明确为"同周期 + 差值上界"。
3. 冗余等级 R1/R2 与 3GPP 的 PDCP 复制、802.1CB 的关系如何表述？（矩阵里必须能对应，否则评审会问）
4. 是否接受"非标准 CQF"的近似实现？若不接受，需把 802.1Qch 列为独立自研项（约 +2 周）。

---

## 附录 A：目录与文件清单

```
experiments/docs/
├── framework-module-design.md        # 本文件
├── kpi-definitions.md                # KPI 口径（唯一实现依据）
└── schema/
    ├── flow-contract.schema.json     # FlowContract JSON Schema
    ├── policy-set.schema.json        # PolicySet JSON Schema
    ├── experiment-spec.schema.json   # ExperimentSpec JSON Schema
    └── observation.schema.json       # Observation JSON Schema
```

后续代码目录建议（只加在 `experiments/`，不动三棵源码树）：

```
experiments/
├── env/          env.lock.yaml, versions.sh
├── specs/        *.yaml（ExperimentSpec）
├── contracts/    *.yaml（FlowContract）
├── policies/     *.yaml（PolicySet，含回放时间轴）
├── gen/          gen_configs.py → ini/NED 参数 + manifest.json
├── runner/       run_experiment.py（并行/续跑/重试/参数断言）
├── ingest/       ingest.py（.sca/.vec → store）
├── analysis/     kpi.py（唯一实现）, figures.py, tables.py
├── report/       report.py
├── store/        results.duckdb, raw/
└── logs/
```

## 附录 B：参考资料

- INET TSN showcase 总览：<https://inet.omnetpp.org/docs/showcases/tsn/index.html>
- INET 自动门控调度（Eager/SAT/TSNsched）：<https://inet.omnetpp.org/docs/showcases/tsn/gatescheduling/index.html>
- DETERMINISTIC6G D4.4（6GDetCom 仿真器与模拟器第二次发布说明）：<https://zenodo.org/records/18223028>
- 6GDetCom Simulator v3.0：<https://github.com/DETERMINISTIC6G/6GDetCom_Simulator>（发布包 <https://zenodo.org/records/15305119>）
- 6GDetCom Emulator v1.0：<https://zenodo.org/records/15305265>
- ns-3 时间感知整形器实现：<https://github.com/DenKrysos/Time-Aware-Shaper-TAS-in-ns-3>
- OpenTSN 项目：<https://github.com/flowseek/openTSN>；论文：<https://link.springer.com/article/10.1007/s42045-020-00029-8>
- OpenCNC TSN service（含重配过渡规划）：<https://git.cs.kau.se/hamzchah/opencnc_tsn-service>
- SDN 架构下的开源 TSN（DTPF 算法）：<https://ieeexplore.ieee.org/ielx7/6287639/10005208/10175538.pdf>
- 开源 TSN 调度评估框架（RTSS 2025 WIP）：<https://www.computer.org/csdl/proceedings-article/rtss/2025/964200a628/2cTzHvdwQco>
- nascTime 论文：arXiv:2604.04616v2

## 附录 C：本文件尚未覆盖、需要下一版补充

1. 每个模块的 NED 接口签名（门/信号名）与 C++ 类图；
2. CP-2 的 GCL 求解调用约定（参数如何映射到 `IGateScheduleConfigurator`）；
3. DP-4 对齐器的具体算法（延迟线长度估计、窗口选择、抖动抑制）；
4. 结果库表结构（DuckDB DDL）；
5. 与 3GPP TS 23.501 §5.28 的字段对应表（评审用）；
6. 6GDetCom PDC 的算法细节（需先精读 D4.4/D4.5 的 PDC 章节，再定 DP-4 实现）。

---

## 附录 D：ADR-001 单底座决策（含被否决方案）

- **状态**：已采纳（2026-10-26）
- **背景**：需要在"一个工程里同时有无线段与有线 TSN 段"的前提下做确定性验证；候选底座为 nascTime（Simu5G + INET）与 6GDetCom（INET + 时延轨迹）。
- **决策**：唯一底座 = nascTime + Simu5G + INET。**不设模块级 SUT 适配层**；场景差异通过 NED/ini 表达；6GDetCom 只作设计参考（PDC），不进入同一进程。

| 方案 | 内容 | 结论 | 理由 |
|---|---|---|---|
| A | 统一 SUT 适配层（把 Simu5G 与纯 INET 模型抽象成同一套节点接口） | 否决 | 两者节点层级/参数名/信号名不同，抽象层等价于重写半个 nascTime，且会随两侧版本升级持续腐化 |
| B | 以 6GDetCom/INET 为底座重做 | 否决（当前阶段） | 干净但从零开始，丢弃 60 run、Simu5G fork、gPTP 驻留时间等资产；6G 侧为轨迹模型，无法支撑"无线内生控制器"闭环 |
| C | 以 nascTime 为唯一底座 | **采纳** | 资产复用最大；论文线可立即产出；控制面与验证层可与底座解耦（只依赖 `.sca` 与 NED 参数） |

- **后果（Accept）**：
  - 放弃"一份配置跑四种保真度"的理想；
  - `wired-tsn` / `ran-only` 仅作临时对照，不是一等公民；
  - `trace-based` 不进首版；
  - 若未来接入 6GDetCom，须**另开工程**，只共享 `dnv.verify`（读 `.sca`）部分。
- **复审触发条件**：①论文线完成且框架线 P0/P1 稳定；②出现"必须用轨迹模型才能跑完样本量"的硬约束；③获得第二个独立底座的真实需求（如硬件在环）。

---

## 附录 E：MVP 功能清单（可执行版）

### E.1 先分两档，别一步到位

| 档位 | 目标 | 需要的东西 | 工期 |
|---|---|---|---|
| **MVP-0 能跑能判** | 一条命令：spec → 仿真 → 指标 → 契约判定 → 报告 | **不需要任何控制器**；只要 INET+Simu5G + 一个手写 PolicySet 注入模块 + 验证流水线 | 2 周 |
| **MVP-1 能闭环** | 控制器观察 → 决策 → 下发 → 效果可判定 | 加 PolicyStore + RanCtrl（仿真内）+ Orchestrator（离线） | 2 周 |

> "3 个控制面模块 + 多 SUT + 规划器 + Verifier"是**目标态**，不是最小态。按目标态开工，第一周就会卡在拓扑与参数改造上。

### E.2 MVP-0：7 项，全部不碰仿真模型

| # | 功能 | 交付文件 | 验收断言 | 复用 |
|---|---|---|---|---|
| 1 | 数据模型加载与校验（4 类 YAML + 跨字段约束） | `dnv/model/loader.py` | 非法契约（p99>max、R2 无分径）被拒 | `jsonschema` |
| 2 | spec → ini 覆盖 + manifest（每 cell 一行，含全部参数） | `gen/gen_configs.py` | 同 spec 两次生成逐字节一致 | 以 `frer_sweep.ini` 为模板 |
| 3 | 参数生效断言（manifest vs `.sca` config 段） | `gen/manifest.py::assert_effective` | 故意写错 `fading` 路径 → FAIL | 已有踩坑经验 |
| 4 | 执行器（串行 + resume + 重试 + 原子落盘） | `runner/run.py` | `Ctrl-C` 后 `--resume` 无缝 | `run_frer_resume.sh` 语义 |
| 5 | `.sca` 摄取（先只 scalar） | `ingest/ingest.py` | 复算 loss/p99 与旧 CSV 逐行一致 | `opp_scavetool` |
| 6 | KPI（loss/mean/p50/p99/PDV + 契约判定） | `analysis/kpi.py` | 5 个边界单测通过 | `kpi-definitions.md` |
| 7 | 报告（markdown 表 + 1 图） | `report/report.py` | 一条命令出全流程 | jinja2 / matplotlib |

**关键性质**：这 7 项只依赖 `.sca` 与 `ini`，**不被底座选型绑架**，因此可以与论文线并行推进。

### E.3 MVP-1：4 项

| # | 功能 | 交付文件 | 验收断言 |
|---|---|---|---|
| 8 | `PolicyStore`（不是直接改别人的 par） | `src/dnv/PolicyStore.{ned,cc}` | 下发/回读/回滚一致 |
| 9 | `Observation` 采集（队列、CQI、预算占用，按窗口聚合） | `src/dnv/ObservationSource.cc` | 窗口边界正确，缺样本标 `INCOMPLETE` |
| 10 | `RanCtrl`（定时器 + 规则表：队列>X → 降 BE 权重/保 GBR） | `src/dnv/RanCtrl.cc` | 信道恶化 100 ms 内恢复 |
| 11 | 闭环判定（`T_decide` 四分量 + 开/关消融） | `analysis/control.py` | 关控制器后违约率显著上升 |

### E.4 三个会卡住的技术点（提前规避）

| 卡点 | 现象 | 规避 |
|---|---|---|
| **运行期改参数** | OMNeT++ 的 `par` 不是随处可改；Simu5G 的 `drbQosConfig` 是 vector 参数，直接 `setPar` 别人的模块极易崩 | 用 `PolicyStore` + 数据面查表；先不改 Simu5G 源码 |
| **`.sca` 覆盖不到运行时状态** | 调度器内部权重、门控相位等不一定落 `.sca` | 断言分两层：config 层强断言 + 行为层信号探针 |
| **确定性被暗算** | 哈希表遍历序、时间戳、随机数破坏可复现 | 规则里禁 `unordered_map` 遍历；所有随机必须显式种子 |

### E.5 功能 → 现成参考对照

| 你要做的 | 可参考 | 可抄 | 不可抄 |
|---|---|---|---|
| TSN 数据面建模 | INET 4.6 showcases；NeSTiNg（IEEE 8854500） | NED 组合、门控/整形器用法 | 各自绑定的 INET 版本 |
| GCL 求解 | INET 的 Eager / SAT / TSNsched 三套 configurator；TSNsched 工具 | 求解器调用约定、约束写法 | 静态一次性求解（CP-2 要动态重算） |
| 5G-TSN 联合仿真 | nascTime（arXiv:2604.04616）；6GDetCom v3.0；DETERMINISTIC6G《A Data-driven Simulation Framework for Logical 5G-TSN Bridges》 | 桥接语义、PDC 设计 | 轨迹模型不适合内生控制闭环 |
| CNC / 控制面 | OpenCNC（KAU）；OpenTSN；集中式 TSN 控制器集群（IEEE 10704466） | 配置下发流程、**重配过渡规划** | 它们没有数据面，不能当仿真底座 |
| 验证方法学 | INET fingerprint；RTSS 2025 开源 TSN 调度评估框架；Network Digital Twin 综述 | 确定性回归、指标口径、定位论证 | —— |
| 标准口径 | IEEE 802.1Qbv/Qav/Qci/Qch、802.1CB、802.1AS；RFC 8655；3GPP TS 23.501 §5.28 | 字段与判据 | —— |

**结论：没有任何现成框架提供"全局协同 + 双控制器 + 数据面"的整套实现。** 最接近的两个：6GDetCom（有控制面接口，但 6G 侧是轨迹模型）、OpenCNC（有 CNC，但没有数据面）。所以"控制器自研"这个判断成立，但要限定为 **1 个仿真内（RanCtrl）+ 2 个离线（WanCtrl / Orchestrator）**，且第二批（MVP-1）才做。
