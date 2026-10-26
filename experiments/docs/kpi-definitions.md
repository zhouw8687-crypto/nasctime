# DNV KPI 定义（唯一实现依据）

> 版本 v0.1 · 2026-10-26 · 配套 `framework-module-design.md`
> 规则：**所有报告、表格、论文图只能引用本文件的定义**；新增指标必须先改本文件，再改 `kpi.py`。

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 统计窗口 | `[warmupS, durationS]`，warmup 内数据丢弃；窗口必须在 manifest 中声明 |
| 时基 | gPTP 域整数纳秒；无同步时标 `timebase: simulator`，且该场景禁止计算 `skew` / `sync_error` |
| 样本单位 | 一条流的**一个报文**为一个样本；分位数按流分别计算，不跨流合并 |
| 缺失处理 | 缺样本的 cell 标 `INCOMPLETE`，**不参与聚合**，也不允许用 0 填充 |
| 舍入 | 内部全精度；报告保留 3 位有效数字 |

## 2. 指标定义

### 2.1 送达率 / 丢包率

```
delivery_ratio(f) = Σ_recv(f) / Σ_sent(f)
loss_ratio(f)     = 1 − delivery_ratio(f)
```

- 来源：应用层 `packetSent` / `packetReceived`（不是 MAC 层计数）
- 口径必须与历史 CSV 一致（`1 − ΣtsnDeviceB[*].app[0].packetReceived ÷ 40000` 这类硬编码口径，必须改为 manifest 声明的 `Σ_sent`）
- ⚠️ `recoveredFromReplica` 是"副本先到被接受"的次数，**不是"从副本恢复的丢包数"**，不得用于计算送达率

### 2.2 端到端时延

```
d_i = t_recv(i) − t_send(i)          # 必须同一时钟域
```

报告：`mean`、`p50`、`p99`、`p99.9`、`max`，单位 ms。分位数用**线性插值**，并在报告注明方法。

### 2.3 抖动（两种口径，必须分别报告）

| 口径 | 公式 | 适用 |
|---|---|---|
| PDV（RFC 3393） | `pdv_i = |d_i − d_{i−1}|`，报告 `mean` / `p99` / `max` | 与标准对齐，跨实现可比 |
| 时延标准差 | `std(d)` | 论文里"抖动"常用，需明确注明是标准差 |

**禁止**把两者混称"抖动"。

### 2.4 skew（多流同步误差）

```
skew(group, k) = max_{i,j ∈ group} | t_arrive(i, k) − t_arrive(j, k) |
```

- `k` 为周期序号（按 gPTP 时基对齐后的周期编号）
- 报告 `mean` / `p99` / `max`，单位 µs
- 要求：同组流必须同一 `periodUs`；否则该组不可计算，标 `INCOMPATIBLE_GROUP`

### 2.5 契约违反率

```
violated(window) = 1  iff  p99 > p99Ms  OR  max > maxMs  OR  loss > maxRatio  OR  skew > maxSkewUs
contract_violation_ratio = Σ violated / Σ windows
```

- 窗口长度默认 = 10 × `periodUs`（至少 10 ms）
- 违约必须能定位到"哪一项、超出多少"，写入 `violations.parquet`

### 2.6 QoS 隔离度

```
isolation_gap = p99(高优类) − p99(BE 类)
```

- 用于对标"高优与 BE 的时延差"这一论证方式（论文中曾用 1.16 ms gap）
- 必须同时报告两类各自的样本量与置信区间

### 2.7 5GS 驻留时间

- 来源：DS-TT 驻留时间信号（nascTime `residenceTime`）
- 报告 `mean` / `var` / `max`，单位 µs
- 方差用**样本方差**（n−1），并注明 n

### 2.8 同步误差

- `sync_error(t) = |clock_slave(t) − clock_master(t)|`
- 仿真中主钟真值已知，故报告的是**真实误差**，不是估计误差
- 报告 `mean` / `p99` / `max`，单位 ns；同时报告 `syncInterval` 参数

### 2.9 门控命中率（DP-3 直接证据）

```
gate_hit_ratio = #{ 包实际发送时刻 ∈ 其所属队列的开门窗口 } / #{ 总发送包 }
```

- 期望 100%；< 100% 说明 GCL 与流量相位不对齐或时基有问题

### 2.10 控制性能（控制器专属）

| 指标 | 定义 |
|---|---|
| 收敛时间 | 从扰动注入到 KPI 回到契约内的时长（ms） |
| 超调 | 收敛过程中 KPI 最差值与稳态值之差 |
| 振荡次数 | 一个观察窗内策略方向反转次数 |
| 决策时延 | `T_decide = T_sample + T_compute + T_deliver + T_apply`（四分量分别记录） |
| 策略变更率 | 单位时间内 PolicySet 生效次数（过高说明控制器抖动） |

### 2.11 资源效率

```
rb_utilization   = 已分配 RB / 可用 RB
link_utilization = 已用带宽 / 链路容量
```

用于"智能调度是否划算"的论证：任何以资源换时延的策略都必须同时报告这两项。

## 3. 样本量要求

| 目标分位数 | 单配置最少样本 | 说明 |
|---|---|---|
| p50 | ≥ 100 | 一般场景 |
| p99 | ≥ 10⁴ | 当前 5 seed × 8000 帧 ≈ 4×10⁴，勉强够 |
| p99.9 | ≥ 10⁶（或 ≥ 20 seeds × 长仿真） | 现有数据**不足以支撑 p99.9**，不得报告 |

- 置信区间：比例类用 Wilson 区间；分位数用 bootstrap（B ≥ 1000），报告 95% CI
- 任何"改善 X%"的结论必须给 CI，且 CI 不跨 0 才算显著

## 4. 与既有 CSV 的兼容性检查

| 检查项 | 要求 |
|---|---|
| `frer_fading_results.csv` 的 loss | 用新实现重算，必须逐行一致（容差 1e-9） |
| `delay_mean` / `delay_p99` | 必须逐行一致（容差 1e-6 ms） |
| 端点/流维度 | 新实现必须能下钻到 `(endpoint, flow, qfi)`，旧 CSV 只有聚合值 |

> 这是 P0 阶段的验收门槛：**新管线复算结果与历史 CSV 逐行一致**，否则不允许替换旧脚本。
