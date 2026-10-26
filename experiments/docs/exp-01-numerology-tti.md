# EXP-01：numerologyIndex 是否真的改变 MAC 调度周期（TTI）

> 日期：2026-10-26 　状态：已完成 　影响指标：A3、K2b、K3b
> 复现脚本：`experiments/exp/tti_probe.sh`（`bash experiments/exp/tti_probe.sh 1 3`）

## 1. 要回答的问题

项目书要求"基站调度器在**微秒级**时间尺度下对 HRLLC 时频资源预留"（A3），并给出"局域场景时延抖动 ≤100 µs"（K2b/K3b）。
在此之前，我们不确定 Simu5G 能否把调度粒度做到亚毫秒，因为它代码里写着：

```c
#define TTI 0.001                    // Simu5G/src/simu5g/common/LteCommon.h:84
double ttiPeriod_ = TTI;             // LteMacBase.h:102（只是成员初值）
```

## 2. 为什么必须实测，不能看代码就下结论

`ttiPeriod_` 在 `INITSTAGE_SIMU5G_TTI_SETUP` 会被覆盖：

```c
// LteMacEnb.cc:173 / LteMacUe.cc:158
ttiPeriod_ = binder_->getSlotDurationFromNumerologyIndex(cellInfo_->getMaxNumerologyIndex());

// Binder.h:229  slot = 2^(-idx) / 1000 s
// idx0=1ms  idx1=0.5ms  idx2=0.25ms  idx3=0.125ms  idx4=62.5us
```

所以"能不能到微秒级"取决于两件事：①`numerologyIndex` 能不能配；②配了以后**运行时是否真的生效**、对哪些模块生效。

## 3. 方法

`.sca` 里没有 TTI 标量，但 MAC 每个 TTI 会发一个名为 `ttiTick_` 的自消息。开 eventlog 后，
每条 `BS` 记录的 `at` 字段就是该消息的到达时刻；取同一模块前两个 tick 的间隔，即为其 TTI 真值。

```bash
cd nascTime/simulations/demos/frer_test
../../../bin/nasctime-run.sh -f frer_sweep.ini -c FrerBaseline_N15 -u Cmdenv -r 0 \
  --sim-time-limit=0.02s --record-eventlog=true --result-dir=/tmp/tti_3 \
  '--*.carrierAggregation.componentCarrier[0].numerologyIndex=3'
# 然后统计 *.elog 里 ttiTick_ 的 at 间隔，并用 MC 表把 sm id 映射回模块类型
```

## 4. 结果

| numerologyIndex | 等价 slot | gNB `NrMacGnb` | UE `NrMacUe`（15 个） | UE `LteMacUeD2D`（15 个） |
|---|---|---|---|---|
| 1（基线，frer_sweep 当前值） | 0.5 ms | **0.0005 s** | **0.0005 s** | 0.001 s |
| 3 | 0.125 ms | **0.000125 s** | **0.000125 s** | 0.001 s |

原始证据（首 tick 到达时间）：idx=1 → `0.0005 0.001 0.0005 0.001`；idx=3 → `0.000125 0.001 0.000125 0.001`。
两次运行均正常结束（rc=0），未报错。

**事件活跃度**（同一 0.02 s 窗口，按发送模块统计事件数）：

| 模块 | 事件数 | 判读 |
|---|---|---|
| `NrMacGnb`（id 537） | 1243 | 数据面，活跃 |
| `NrMacUe`（id 616） | 373 | 数据面，活跃 |
| `LteMacUeD2D`（id 608） | 45 | 约等于 tick 数，**空转** |

## 5. 结论

1. **亚毫秒调度可用，且是纯配置项**：把 `componentCarrier[0].numerologyIndex` 改成 3，数据面 MAC（`NrMacGnb` + 15 个 `NrMacUe`）的 TTI 就从 0.5 ms 变成 0.125 ms，无需改源码。
2. **`LteMacUeD2D` 不跟随**：每 UE 还有一个遗留的 LTE MAC，保持 1 ms。从事件数看它基本只在空转（45 次事件 ≈ tick 数），**不在 NR 数据面路径上**。它的存在不影响指标，但会消耗仿真事件；后续可以在 NED 里禁用或忽略。
3. **当前所有 FRER 实验实际跑在 0.5 ms TTI**（`ex_multi_omnetpp.ini:50` 已设 `numerologyIndex = 1`），不是 1 ms。此前若按 1 ms 解读，时间尺度会差一倍。

## 6. 对项目指标的直接影响

| 指标 | 之前判断 | 现在结论 |
|---|---|---|
| A3（微秒级资源预留） | 存疑，疑似结构性不可达 | **可达**：idx=3 → 0.125 ms；idx=4 → 62.5 µs。报告里须写清是"slot 级"，不是"符号级" |
| K2b/K3b（抖动 ≤100 µs） | 结构性不可达 | **有条件可达**：TTI 降到 0.125 ms 后，抖动下限不再被 1 ms 支配；绝对值仍需实测 |
| 全部既有结果的可比性 | —— | 换 TTI 会改变 PHY slot 与 HARQ 时序，**必须重新基线**，不能与 0.5 ms 的结果混在一张表里 |

## 7. 踩到的坑（已固化进脚本）

1. **非交互 shell 不能 `source ~/nasctime-env.sh`**：其中 `nascTime/setenv` 检查 `$-` 是否含 `i`，非交互时打印 `not a login shell` 并 `exit 1`，会直接终止整个 shell。解决：手工 export 等价环境（脚本里已这么做），或 `source setenv -f`。
2. **`--sim-time-limit` 覆盖后，`.sca` 里会同时出现两条 `config sim-time-limit`**（0.02s 与 10s），后者是 ini 里的原值。以命令行为准，但读 `.sca` 时要小心。
3. **`.sca` 里没有 TTI**，只能靠 eventlog 或加探针。这也是"参数生效断言"必须存在的原因——配了不等于生效，生效了不等于全模块生效。

## 8. 下一步

- 用 idx=3 跑一组完整 FRER 对照（Baseline/Asym/Sym × 5 seeds），看 p99 与 PDV 是否真的降下来；
- 同时补一条 `ttiPeriod` 的标量探针（`recordScalar`），让后续所有 run 都能在 `.sca` 里直接断言 TTI，而不是每次靠 eventlog。
