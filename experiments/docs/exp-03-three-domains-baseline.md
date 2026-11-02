# EXP-03：三个承载/接入域的最小基线（L2 / L3 / 无线）

> 日期：2026-11-02
> 场景：`nascTime/simulations/demos/{ring_test, mpls_test, mpls_failure_test, ran_test}/`
> 目的：在不接线、不接控制器的前提下，给每个域单独跑出可引用的基线数字。

## 1. 域与产物

| 域 | 目录 | 网络来源 | 本实验产物 |
|---|---|---|---|
| 边缘有线接入（L2 TSN） | `ring_test/` | 自建三角环 | 跨径差 101.17 µs，方差 0（见 EXP-02） |
| L3 承载（MPLS） | `mpls_test/` | INET `testte_tunnel` | **LSP 生效证据** + 时延基线 |
| L3 承载（故障） | `mpls_failure_test/` | INET `testte_failure` | **中断时长 479.84 ms** |
| 无线接入（NR） | `ran_test/` | Simu5G `SingleCell_Standalone` | 送达 99.7%，DL 时延 4.77 ms |

## 2. L3：LSP 是否真的生效（A/B 对照）

`testte_tunnel` 的标签表把 host3 的流推向 `LSR1.ppp0`（15 ms 长链路），
而 IP 最短路是 `LSR1.ppp1`（5 ms）。用"清空 FEC 表"做对照：

| 配置 | host3 端到端 mean | stddev | 判定 |
|---|---|---|---|
| FEC 表正常（打标签） | **80.88 ms** | 1.79 ms | 走 LSP（长链路） |
| FEC 表清空（纯 IP 转发） | **55.90 ms** | 0.28 ms | 走 IGP 最短路 |

差值 **24.98 ms**，方向与配置一致（LSP 走 15 ms 而非 5 ms 链路），
且 LSP 路径的抖动明显更大（1.79 vs 0.28 ms）。**结论：LSP 确实生效，且 TE 会覆盖最短路。**

- 复现：`--**.LSR1.classifier.config=xmldoc("LSR1_fec_empty.xml")`
- 注意：`classifier.config` 是 XML 类型，不能赋 `""`（会报 `Cannot cast from type string to XML`），必须给空表文件。

## 3. L3：故障倒换中断时长

`testte_failure` 的 `scenario.xml`：t=2s 关闭 LSR4，t=4s 恢复。用接收向量的到达间隔量中断：

| 指标 | 值 |
|---|---|
| 采样数 | 513（6 s，发送间隔 10 ms → 应有 600，丢 87） |
| **最大中断** | **479.84 ms @ t=2.496 s** |
| 恢复期二次中断 | 320.16 ms @ t=4.576 s |

也就是说：**节点级故障 → 中断约 480 ms；恢复又断约 320 ms**。
这是"保护倒换"条款的基线，距离电信级 50 ms 差一个数量级，是后续要优化的点。

- 复现：`./run.sh`（或通用 wrapper）+ `--**.vector-recording=true`，再用 `experiments/exp/vec_gaps.py` 计算。

## 4. 无线接入（NR）最小单元

直接引用 Simu5G 官方网络定义 `simu5g.simulations.nr.networks.SingleCell_Standalone`，
本域只写 ini，不复制 NED。

| 指标 | 值 |
|---|---|
| server → ue[0] 下行 | 发 299，收 298（送达 99.7%） |
| 端到端时延 mean | **4.77 ms** |
| p50 / p99 / max | 2.38 / 4.72 / 4.77 ms |
| stddev | 0.00（直方图分桶过粗，呈双峰，见下） |

p50 约为均值一半、stddev 为 0，说明延迟集中在两个离散档位（TTI 量化），
不是连续分布——直方图分桶太粗，精确分布需开 vector。

**与项目指标的关系**：项目要求"局域场景单向时延 ≤4 ms"，当前 4.77 ms **略超**，
这是第一个需要优化的真实缺口（对照：论文基线 2 DRB/MAXCI/25 RB 下 high-priority mean 2.58 ms）。

## 5. 踩到的坑（已修，写进仓库）

| 坑 | 现象 | 根因 | 修复 |
|---|---|---|---|
| **conda 路径拼错** | `opp_run` 报 `Qt_6.11 not found`，误判为沙箱问题 | 脚本里写的是 `zbw/nasctime/conda-envs`，正确是 `zbw/conda-envs` | 已修正 `run.sh`、`tti_probe.sh`、`min_unit.sh` |
| `/tmp` 被清 | 上一轮结果全丢 | 机器重启/清理 | 结果改放各域 `results/`（已 gitignore） |
| Simu5G 场景不在 NED 路径 | `Network not found` | 通用 wrapper 的 `-n` 只含 `Simu5G/src` | `ran_test/run.sh` 显式补 `Simu5G/simulations` |
| XML 参数不能赋空串 | `Cannot cast from type string to XML` | 类型系统 | 用空表 XML 文件代替 |

## 6. 下一步

1. 给 L3 域加门控无关的**多径**（两条 LSP 同时承载），对齐 L2 的 FRER 做法；
2. 把 `ring_test`（L2）与 `mpls_test`（L3）在边界用一台路由器接起来，验证"跨域"；
3. 把 `ran_test` 的 gNB 接到 L3 域，形成"无线 → 承载 → 核心"的最短端到端链；
4. 三域都稳定后，再接控制平面（否则调参时会分不清是域错还是控制器错）。
