# nascTime 项目 AI 交接文档（Handoff）

> 目的：让接手的 AI 在 10 分钟内掌握"我们已经做了什么、得出了什么、接下来往哪走"。
> 本文所有事实均来自真实实验日志、源码阅读和论文 fetch，无推测编造；标注【已验证】的均可在服务器 `.sca` / 本地 CSV / 论文原文中复核。
> 最后更新：2026-09-20（§1–§9）；2026-10-12 补写 §10 端到端仿真环境建设建议

---

## 0. 一句话项目定位

本项目是 **3GPP Release 16 5G-TSN 集成桥仿真**（nascTime：5G 系统当透明 IEEE 802.1AS TSN 桥用），我们在其上做的是 **IEEE 802.1CB FRER（帧复制消除冗余）在不同 5G 调度器与信道条件下的性能实验**，目标是为后续论文/报告提供"5G 作为确定性网络桥能否提供低时延高可靠"的仿真证据。

- 原始论文：arXiv:2604.04616v2《nascTime: A Full-Stack 5G-TSN Bridge Simulation Framework with SDAP-Based QoS Mapping and IEEE 802.1AS Transparent Clock》（Seliem 等，投稿 IEEE ETFA 2026）。
- 仿真栈：OMNeT++ 6.4.0 + INET 4.6.x + Simu5G v1.5.0；**FRER 必须用 Simu5G fork `nasctime-v1.0`**（vanilla 不支持 FRER 路径分集）。
- 本地产物根：`D:\aaaLab\6g确定性网络\nastTime\`（nascTime 源码 + experiments/）。

---

## 1. 环境与路径（接手前必须知道）

### 1.1 本地 Windows（用户工作机）
- 项目根：`D:\aaaLab\6g确定性网络\nastTime\`
- 源码：`nastTime\nascTime\src\...`、`nastTime\nascTime\simulations\demos\frer_test\`
- 实验目录：`nastTime\experiments\`（脚本 + CSV 聚合 + 日志 + 报告）
- 注意：**本地没有完整 .sca 原始结果**，完整结果在服务器上（见 1.2）。本地只有 CSV 聚合结果和日志。

### 1.2 服务器（A100 机器，真正跑仿真的地方）
- 根目录：`/media/a100/data/zbw/nasctime/`
  - `omnetpp-6.4.0/`、`inet/`、`Simu5G/`（fork）、`nascTime/`、`experiments/`
- conda 环境：`/media/a100/data/zbw/conda-envs/nasctime`（Python 3.12，pandas/numpy/tqdm）
- 环境激活：`source ~/nasctime-env.sh`
- 场景目录：`/media/a100/data/zbw/nasctime/nascTime/simulations/demos/frer_test/`
- **完整结果目录**：
  - 理想信道：`experiments/results/frer/`（.sca）
  - 差信道：`experiments/results/frer_fading/`（.sca，60/60 完整）
- 机器规格：512 核、~500GB 内存；实测开 5 路并行跑无压力（load ~2）。

### 1.3 跑仿真的最小命令模板
```bash
source ~/nasctime-env.sh
cd /media/a100/data/zbw/nasctime/nascTime/simulations/demos/frer_test
../../../bin/nasctime-run.sh -f frer_sweep.ini -c FrerBaseline_N15 -u Cmdenv -r 0 \
  '--*.tsnDeviceA.gptp.syncInterval=4s' '--*.tsnDeviceB[*].gptp.syncInterval=4s' \
  '--*.gnb.cellularNic.channelModel[0].fading=true' \
  '--*.gnb.cellularNic.channelModel[0].shadowing=true' \
  '--*.gnb.cellularNic.channelModel[0].thermalNoise=-95dBm' \
  --result-dir=/media/a100/data/zbw/nasctime/experiments/results/frer_fading
```
关键环境变量（`run_frer_resume.sh` 顶部有完整导出）：`INET_ROOT`、`SIMU5G_ROOT`、`NASCTIME_ROOT`、`LD_LIBRARY_PATH`。

---

## 2. 已完成的工作（截至 2026-09-20）

### 2.1 实验矩阵全貌【已全部跑完】

| 批次 | 配置 | 信道 | 结果数 | 状态 |
|---|---|---|---|---|
| 理想信道 | FrerBaseline_N15 / FrerAsym_N15 / FrerSym_N15 | 无 fading/shadowing（默认） | 3 config × 20 runs = 60（56 有效 + 补跑） | ✅ 完成 |
| 差信道 | 同上 3 config | fading=true + shadowing=true + thermalNoise=-95dBm | 3 config × 20 runs = **60/60** | ✅ 完成（9 个失败 run 用 syncInterval=8s 补跑成功） |

**run → 调度器映射**（`analyze_frer_agg.py` 的 SCHED 表）：
- run0-4 = MAXCI，run5-9 = PF，run10-14 = DRR，run15-19 = QOS_PF
- rep = runN % 5；`seed-set = ${repetition}`（OMNeT++ 自动种子）

**三个 config 的唯一差异**（git diff 实证）：
- `FrerBaseline_N15`：无 FRER 模块（frerEnabled=false），4 DRB
- `FrerAsym_N15`：FRER 开启，副本走 DRB4/QFI8 = **non-GBR, priority=2**（副本比主流 CLC 低一档）
- `FrerSym_N15`：FRER 开启，副本走 DRB4/QFI8 = **GBR, priority=1**（副本与主流同档）
- 除 DRB4 的 `drbQosConfig` 外，三者其他行完全相同。

### 2.2 关键实验结果数字【已验证，来自 frer_fading_results.csv / frer_run_results.csv】

**理想信道（config 总平均）**：
| config | loss_rate | delay_mean | delay_p99 |
|---|---|---|---|
| Baseline | 0.0006% | 3.23 ms | 6.74 ms |
| Asym | 0.0106% | 9.44 ms | 18.60 ms |
| Sym | 0.0250% | 15.59 ms | 45.87 ms |

**差信道 -95dBm（config 总平均）**：
| config | loss_rate | delay_mean | delay_p99 |
|---|---|---|---|
| Baseline | 1.29% | 50.35 ms | 304.30 ms |
| Asym | 7.94% | 118.49 ms | 1400.82 ms |
| Sym | 7.43% | 137.03 ms | 1589.53 ms |

**差信道 config×sched 明细（节选关键）**：
- Baseline：DRR 0% / MAXCI 1.4% / PF 0.08% / QOS_PF 3.67%
- Asym：DRR 1.69% / MAXCI 16.7% / PF 2.93% / QOS_PF 10.43%
- Sym：DRR/MAXCI/PF = Asym 同值（逐行相同！），QOS_PF 8.39%
- MAXCI 在差信道下 p99 延迟高达 3458ms，是四个调度器里最差的。

### 2.3 信道标定（服务器实测，按 tsnDeviceB[3] 丢包）【已验证】
- thermalNoise=-98dBm → ep3 丢包 3.7%/7.6%
- -95dBm → 12%/13%（选定值，曲线陡峭段）
- -92dBm → 90.5%/56%
- 默认值是 -104.5dBm（不是 -94dBm，用户曾误判）。

### 2.4 已交付文档产物
- `experiments/nascTime完整解读报告.md`（约 38KB / 8 章：环境/拓扑/流量QoS/源码/脚本链/结果/速查）
- 同名 `.pdf` 版本
- 三份 CSV：`frer_run_results.csv`（理想 run 级）、`frer_fading_results.csv`（差信道 run 级）、`frer_results.csv`（理想逐端点 1961 行明细）

---

## 3. 关键技术知识（源码级，已确认）

### 3.1 FRER 数据流（本项目核心实验对象）
- **复制端**（`nwTt.frerReplicator`，NW-TT 内部）：
  - 只复制 DSCP ∈ `frerStreams="7"` 的流（即 CLC 工业控制流）；MTU 守卫 >1500B 跳过。
  - 每流独立 16bit 序列号；R-TAG（FrerSequenceHeader）插**包尾** + IPv4 Identification 兜底。
  - 副本深拷贝后把 DSCP 改为 `replicaDscp=8` → SDAP 按 QFI8 路由到 DRB4。主份 DSCP7 → QFI7 → DRB2。
- **恢复端**（`dsTt[*].frerRecovery`）：
  - IEEE 802.1CB Annex C Vector Recovery：每流窗口 `windowSize=64`、`windowTimeout=0.1s`。
  - 三态：ACCEPT（先到）/ DUPLICATE（后到，丢弃）/ WINDOW_OVERRUN（丢弃）。
  - `recoveredFromReplica` 的含义是"**副本先到**被接受的帧数"，**不是"从副本恢复了多少丢包"**。
- **传输绑定**（`transportBinding`，当前实验全用 "drb"）：
  - `drb`：同一条 N3 路径，仅靠 DSCP→不同 DRB 区分（**QoS 级分集，无路径分集**）
  - `pduSession`：独立 N3 路径、同 gNB（F3，已实现待集成测试）
  - `dualConnectivity`：独立 gNB、独立无线信道（F4，开发中）

### 3.2 QoS 映射链（端到端）
```
TSN Device A (VLAN PCP) → NW-TT 剥VLAN、PCP→DSCP → UPF TFF DSCP→QFI
→ gNB SDAP QFI→DRB → MAC 调度器按 DRB 排程 → UE SDAP → DS-TT DSCP→PCP → TSN Device B
```
DRB/QFI 表（N15，每 UE）：
- DRB0=QFI0（BE，gbr=false, p3, delay 50ms）
- DRB1=QFI6（MV视频，gbr=true, p2, delay 10ms）
- DRB2=QFI7（CLC 主流，gbr=true, p1, delay 2ms）
- DRB3=QFI5（gPTP，gbr=true, p0, delay 1ms）
- DRB4=QFI8（FRER 副本：Asym=nonGBR p2 / Sym=GBR p1）

### 3.3 四个调度器的算法本质（Simu5G 实现）
| 调度器 | 算法 | 是否读 drbQosConfig |
|---|---|---|
| MAXCI | 贪心：每 RB 给 C/I 最高 UE | ❌ |
| PF | 比例公平：R(t)/T(t) | ❌ |
| DRR | 赤字轮询：按权重 | ❌ |
| QOS_PF | PF × QoS 权重（priority/delay/per） | ✅ **唯一** |

---

## 4. 已确认的核心结论（实验得出，可直接引用）

1. **【关键发现】只有 QOS_PF 调度器真正区分 Asym 与 Sym**。DRR/MAXCI/PF 下 Asym 与 Sym 的结果**逐行完全相同**——这三个调度器不消费 `drbQosConfig`，FRER 副本的 QoS 差异形同虚设。
2. **DRB 级 FRER（当前实验配置）防不了物理信道丢包**：差信道下 FRER 丢包（Asym 7.94%）反而约为 Baseline（1.29%）的 6 倍。原因：主/副本走同一条无线链路，深衰落时双份一起丢；且双份发送使空口负载翻倍。**DRB 级 FRER 只防"队列/调度选择性丢包"，不防信道丢包**——这正是 F3/F4 路径分集存在的理由。
3. **QOS_PF 下结果反转**：Asym 10.43% > Sym 8.39%。机制：Sym 副本 GBR p1 与主流抢带宽 → 主份延迟超 `windowTimeout=0.1s` → 恢复窗口被重置 → 去重失效。
4. **"为什么每次只改第 3 个设备（ep3）"**：不是 ep3 特殊。`ue[*].mobility.initialX/Y` 是 50m 圆盘均匀随机坐标，由 seed 决定；某个 seed 下 ep3 恰好落在深衰落位置。换 seed 后最弱链路迁移（已实测 run1/run2 验证）。
5. **理想信道下 Asym（副本低优）优于 Sym（副本高优）**：副本占用资源越少，对主流干扰越小（0.0106% vs 0.0250%，p99 18.6ms vs 45.9ms）。

---

## 5. 原始论文（arXiv:2604.04616v2）验证口径（对比基准）

**论文验证的不是调度器比较**，而是框架能力。Section V 三支柱：

| 支柱 | 论文依据 | 论文结果 |
|---|---|---|
| QoS 分级 | Table III/IV，V-B/V-C | 高优 99.9% 送达、mean 2.58ms/p99 3.12/max 3.41；BE 3.74/5.89/7.23；**1.16ms gap = SDAP/DRB 隔离度** |
| 透明时钟 | Table VI，V-E/V-F | 驻留时间方差 <0.2µs（理想）→ 48.2µs（Rayleigh 衰落）；高优送达 99.7% |
| 多端点 | Table V，V-D | 1→3 端点高优时延 +<70µs、零丢包 |

**论文实验参数（与我们不同，引用时注意）**：
- 3 端点、2 DRB、**调度器只用 MAXCI**、25 RBs、gPTP sync interval=**125ms**、10s 仿真（1s warmup）
- 衰落信道 = INDOOR_HOTSPOT + Rayleigh，**无 shadowing**（我们加了 shadowing + 抬噪 -95dBm，更狠）
- FRER（802.1CB）**未出现在论文 v2**——是仓库 README 的 F1-F4 新功能，我们的 FRER 实验属于论文框架之上的扩展工作。

**"确定性网络"的正确度量**（论文口径，不是丢包率）：时延分布（mean/p99/max）、抖动、gPTP 驻留时间方差、QoS 隔离度（高优 vs BE 时延差）。

---

## 6. 已踩过的坑（接手时避免重蹈）

| 坑 | 现象 | 正解 |
|---|---|---|
| channelModel 路径写错 | `phy.channelModel[0].fading=true` 不生效（.sca 里仍是 false） | 正解是 `cellularNic.channelModel[0]`（它是 cellularNic 的直接子模块，不是 phy 的）。**改参数后必须查 .sca 的 config/par 段确认生效** |
| SIMU5G_ROOT 未 source | `nasctime-run: SIMU5G_ROOT is not set` exit=1 | 先 `source ~/nasctime-env.sh` |
| conda/系统 python 混用 | `ModuleNotFoundError: No module named 'tqdm'` | 用 `/media/a100/data/zbw/conda-envs/nasctime/bin/python` 显式调用 |
| gPTP 溢出 | `oscillatorCompensation = -999999 ppm`（t≈8.003s，随机一个 tsnDeviceB clock）差信道下必现 | syncInterval 从 4s 放宽到 **8s**（已补跑成功 9 个失败 run） |
| ini 参数静默忽略 | 路径写错不报错 | OMNeT++ 不报错，必须查 .sca |
| tail 命令 | `tail -2 file` 在某些环境报错 | 用 `tail -n 2` |
| 静默改参数 | fading 默认 false | 必须显式 `fading=true` 且验证 .sca |

---

## 7. 后续探索方向（按优先级建议）

### P0：用现有数据按论文"确定性指标"口径重分析（不重跑仿真）
现有 60-run 差信道 .sca 里已有 `endToEndDelay:vector` 和 gPTP 驻留时间，可直接提取：
- 每 config×sched 的 **时延 p99/p99.9/max、抖动（stddev）**
- **QoS 隔离度**：CLC 主流 vs BE 流的时延差（对标论文 1.16ms gap 的论证方式）
- **gPTP 驻留时间方差**（对标论文 Table VI）
- FRER 开销对比：Baseline vs Asym/Sym 的延迟/负载代价
> 这是性价比最高的下一步：零仿真时间，直接产出"确定性指标"叙事。

### P1：复现论文基线（可选，用于对标）
按论文参数（3 端点、2 DRB、MAXCI、理想 + Rayleigh 衰落无 shadowing、gPTP 125ms）跑一遍，验证能否复现 Table IV/VI 的数字（2.58ms、方差 0.2µs/48µs），确认我们环境与论文一致后再扩展。

### P2：FRER 路径分集实验（体现"可靠性"的关键）
当前 drb 绑定已被证明防不了信道丢包。仓库已实现 F3（`frer_intersession.ini`，独立 N3/UPF 同 gNB）和 F4（`frer_dualconn.ini`，独立 gNB，开发中）。建议：
- 用 P0 的差信道配置跑 `transportBinding=pduSession`（或 dualConnectivity 若可用），对比"同链路双挂 vs 路径分集"的丢包率/送达率。
- 预期结论：路径分集会让 FRER 在差信道下真正体现可靠性增益（主/副本走独立信道，不再双挂）。

### P3：gPTP syncInterval 参数敏感性
我们用 4s（补跑 8s），论文用 125ms。差信道下溢出风险与同步精度的权衡值得做一组扫描（125ms / 1s / 4s / 8s），看驻留时间方差变化。

### P4：信道标定细化
-95dBm 落在陡峭段（12%/13% 丢包），可补 -96/-97dBm 两点，把"丢包率 vs thermalNoise"曲线做光滑，支撑论文里的信道恶化叙事。

---

## 8. 关键文件索引

### 服务器（完整数据在这）
- 批次脚本：`experiments/run_frer.sh`（理想）、`run_frer_resume.sh`（差信道断点续跑，支持 RUN_START/RUN_END 并行分段）
- 分析脚本：`experiments/analyze_frer_agg.py`、`analyze_frer_fading.py`
- 结果：`experiments/results/frer/*.sca`、`experiments/results/frer_fading/*.sca`
- 日志：`experiments/log_resume_*.log`

### 本地 D:\aaaLab\6g确定性网络\nastTime\experiments\
- `nascTime完整解读报告.md` / `.pdf` —— 源码级完整解读（8 章），**先读这个再接手**
- `frer_run_results.csv`（理想 run 级）、`frer_fading_results.csv`（差信道 run 级）、`frer_results.csv`（理想逐端点明细）
- `analyze_frer*.py`、`run_frer*.sh`、`verify_frer_one.py`

### 源码关键位置（本地 + 服务器镜像）
- FRER：`nascTime/src/nasctime/nodes/frer/{FrerReplicator,FrerRecovery}.cc`、`IFrerTransportBinding.h`
- 桥：`nascTime/src/nasctime/nodes/NwTt/NwTtTranslator.cc`、`DsTt/DsTtTranslator.cc`
- 配置：`nascTime/simulations/demos/frer_test/frer_sweep.ini`、`profiles/profiles_N15.ini`、`gen_profile_ini.py`
- 信道模型：`Simu5G/src/simu5g/stack/phy/channelmodel/NrChannelModel_3GPP38_901.ned`

---

## 9. 交接注意事项（给下一个 AI）

1. **统计口径别搞错**：`loss_rate = 1 - ΣtsnDeviceB[*].app[0].packetReceived ÷ 40000`（sent = 5 CLC 流 × 8000 主帧，warmup 2s 后有效 8s）。`recovered_replica` 不是恢复的丢包，是副本先到数。
2. **不要把"调度器比较"当成论文主题**——论文验证的是桥框架能力（QoS 隔离 + 时钟精度 + 扩展性）。调度器扫描是仓库扩展矩阵，适合作为 FRER 新工作的实验维度。
3. **改任何 ini 参数后，必须查 .sca 的 config/par 段确认生效**（OMNeT++ 静默忽略未匹配参数，这是踩过的坑）。
4. **跑分析脚本时用 conda python 绝对路径**，别用系统 python3。
5. **完整原始 .sca 在服务器**，本地只有 CSV；要做新指标提取需 SSH 到 A100 或让用户把 .sca 拉下来。
6. 用户重视"可核验证据"——任何结论都要能回到 .sca / CSV / 源码 / 论文原文，不要给模糊推测。
7. 用户偏好：中文交流；实验文件放 `experiments/`（不动源码目录结构）；批次脚本要逐 run 进度显示。

---

# 10. 端到端仿真环境建设建议（2026-10-12 勘察补写）

> 补写说明：本节由接手 AI 在第 1–9 节基础上，通读 arXiv:2604.04616v2 全文 + 服务器源码树 + 结果目录 + 全部脚本后补写。
> 凡标【实测】的数字与路径，都可用 §10.9 给的命令在服务器当场复核。本节不改动第 1–9 节任何内容；原文档已备份为 `AI交接文档_项目现状与后续方向.md.bak-20261012`。

## 10.1 先定义清楚："端到端"是哪条端到端

本项目现在有两个"端"：

- **仿真的端**：TSN Device A → NW-TT → UPF → gNB → UE/DS-TT → TSN Device B（以及反向、gPTP 侧带）。这条链第 1–6 节已经打通并有可信数据。
- **实验流程的端**：一个科学问题 → 一页可引用、可复核的结论。这条链目前**仍然是人拉手推车**：手写 ini、手工分片、硬编码路径的解析脚本、手工贴表。

建议把"端到端仿真环境"的目标定为后者。目标形态：

```
spec.yaml（实验规格：拓扑/流量/QoS/信道/调度器/种子/指标）
  → gen        生成 ini + profiles + manifest.json（唯一事实源）
  → validate   断言"期望参数 == .sca 里真正生效的参数"
  → run        并行、断点续跑、自动重试、逐 cell 状态入库
  → ingest     .sca/.vec → 单一结果库（DuckDB/Parquet）
  → kpi        唯一的指标实现（送达率/分位数/抖动/驻留时间/隔离度）
  → report     自动出表、出图、出结论
  → regress    与基线比对，回答"这次改动是否改变了结论"
```

**验收口径一句话**：换一台干净机器、只给一个 spec 文件，一条命令产出与历史一致的表和图；中间任何一步失败都必须是**显式失败**，不允许静默产出脏数据。

## 10.2 现状盘点：链条上哪里是断的【实测】

| 环节 | 现有资产 | 状态 | 断点 |
|---|---|---|---|
| 环境封装 | `~/nasctime-env.sh`（唯一入口，含 conda/omnetpp/qt6 路径） | ✅ 可用 | 无版本锁定文件；`opp_run` 脱离该脚本直接跑会报 `Qt_6.11 not found` |
| 场景 NED | `ExtendedMultiEndpointNetwork.ned`（N≤40，含 `upf2 if frerInterSession` / `gnb2 if frerDualConn` 条件子模块） | ✅ 就绪 | 未见 N>3 的批量实测结果 |
| 信道/地址配置 | `multi_ip_config.xml` 已含 pppIf2/upf2/gnb2 网段（10.0.4/10.0.5）、`cnc_config.xml` | ✅ 就绪 | F3/F4 未端到端验证 |
| 配置生成 | `gen_profile_ini.py`（N1..N40 × base/asym/sym 三种 profiles 已生成） | 🔶 半自动 | `frer_sweep.ini` 仍手写约 250 行、每个 N 一段重复块；参数全靠命令行 `--*.xxx=` 覆盖 |
| 执行 | `bin/run_matrix.sh`（GNU parallel + resume）、`experiments/run_frer_resume.sh`（RUN_START/END 手工分片） | 🔶 可用但割裂 | 两套调度器互不知情；**服务器没装 GNU parallel**（`which parallel` 为空）→ run_matrix.sh 在当前机器上不可直接复用 |
| 结果存储 | `experiments/results/frer` 29GB + `frer_fading` 29GB | 🔴 体量失控 | `**.vector-recording = true` 导致单 run 526MB；`**.sca` 只有 6MB |
| 解析 | 三套并存：`vec_parse.py`（自写 .vec 解析）、`parse_results.py`、`analyze_frer_agg.py` / `analyze_frer_fading.py` | 🔴 重复且脆弱 | 路径硬编码 `RESULT_DIR`；`run → scheduler` 靠硬编码元组 `SCHED=(["MAXCI"]*5+...)` |
| 指标 | `frer_run_results.csv` / `frer_fading_results.csv` / `fading.csv` / `primary.csv` 口径 | 🔶 有雏形 | 两套口径（FRER 用 loss/delay，MSWiM 用 deadline miss/公平性）未合并 |
| 报告 | `nascTime完整解读报告.md/.pdf`、matplotlib 图 | 🔶 手工 | 无"spec → 报告"的自动通道 |
| 回归 | `tests/{nwtt,gptp,bridge,qos}_test` + `bin/smoke_test.sh` | ✅ 存在 | 不在任何流水线里；论文 Table IV/VI 数字没有作为断言锚点 |

**结论**：环境与场景这两层已经很扎实，缺的全部在"实验流程层"。所以下面的建议**不动源码、不动已有结果**，只加一层薄薄的编排与数据层。

## 10.3 六个必须补的能力（按性价比排序）

### P0 结果体量整形：先把 20 倍浪费砍掉（零仿真成本，最优先）

【实测】单 run 产物：`.sca` 6.1MB（8635 个 scalar）、`.vci` 13.6MB、`.vec` **524MB**（8436 条 vector 声明、1700 万行）。
两批 120 个 run 里，`.vec` 共约 28GB/批，`.sca` 仅 352MB/批。磁盘 7.3T 已用 3.9T，可用 3.1T。
按当前体量外推 MSWiM 矩阵（75+36+45=156 run）≈ 78GB；若把种子从 5 提到 20，直接 **500GB+**，还没算 N=40 时端点更多带来的放大。

做法（三选一或组合）：

1. **白名单录制**（推荐，改 ini 一行级）：
   ```ini
   **.vector-recording = false
   **.scalar-recording = true
   *.tsnDeviceB[*].app[*].endToEndDelay.vector-recording = true
   *.dsTt[*].translator.residenceTime.vector-recording = true
   ```
   其余全部走 `statistic-recording = true`（mean/histogram 落在 .sca，体积小 2–3 个数量级）。
2. **跑完即抽取**：`opp_scavetool x -f 'name(endToEndDelay:vector) OR name(residenceTime:vector)' -o needed.vec run.vec`，然后删原始 `.vec`；把这一步放进 runner 的收尾钩子。
3. **立即用现有 58GB 里的 .vec 做一次"确定性指标"全提取**，落成 CSV/Parquet 之后再删 `.vec`，可当场释放约 **56GB**，且直接产出交接文档 §7 P0 要的那批指标。

验收：单 run 产物体积 < 30MB（现 526MB，≈20×）；用新管线重算 `frer_fading_results.csv` 的 loss/p99，与现有 CSV **逐行一致**。

### P1 版本冻结：不锁版本，后面所有数字都不可信

【实测】`nascTime/`、`Simu5G/`、`inet/` **三棵树都不是 git 仓库**（无 `.git`）。
Simu5G fork 与 `Simu5G-vanilla-1.5.0` 的差异是 **35 个已有源文件的修改、零新增文件**（Binder、GtpUser、HandoverPacketHolder*、Ip2Nic、TechnologyDecision、LteAmc、LteMacEnb/Ue、QoSAwareScheduler、LteDlFeedbackGenerator、LtePhy*、NrPhyUe、BearerManagement、HandoverController、Rrc.ned、NrSdap、LteNicBase.ned 等）。
也就是说：**今天任何一次误覆盖都无法回滚，而"我改了什么"正是投稿审稿时最容易被追问的东西**。

做法：

1. 立刻 `git init` + 首次提交三棵树（`.gitignore` 掉 `out/`、`*.o`、`*.so`、`results/`、`*.vec/.vci/.sca`）；或至少 `diff -ruN Simu5G-vanilla-1.5.0 Simu5G > fork-nasctime-v1.0.patch` 存档（零新增文件，patch 会很干净）。
2. 写 `experiments/env/env.lock.yaml`：OMNeT++ 6.4.0、INET 4.6.0、Simu5G fork tag、`conda env export`、gcc 13.3.0、`opp_run -v`、以及 Qt6 路径来源。
3. 每个 run 在 `.sca` 旁写 `run_meta.json`：git 短哈希、ini 的 sha256、完整参数表、seed、wall time、退出码。
4. ⚠️ 顺手记下**版本漂移**：论文写的是 OMNeT++ 6.3 + Simu5G v1.4.1-sdap-2，我们用的是 6.4.0 + fork(nasctime-v1.0，基于 1.5.0)。做 §7-P1 论文基线复现时，这个漂移必须作为"差异来源"写进结论，否则复现不上会白查很久。

验收：空目录 → 按文档重建 → 跑通 `tests/` 全部 4 个场景 + 1 个 frer run，scalar 与基线一致。

### P2 配置生成 + "静默忽略"防护（本项目最大的隐形坑）

交接文档 §6 已经踩过：OMNeT++ 对写错的参数路径**不报错**，`phy.channelModel[0].fading=true` 写错就静默用默认值。

做法：

1. spec(YAML) → `gen_configs.py` → 生成 ini/profiles **+ manifest.json**（含每个 cell 的 config/run/sched/seed/信道/覆盖参数）。
2. **把 `run → scheduler` 的映射写进 manifest**，不要再用 `SCHED=(["MAXCI"]*5+...)` 这种元组推演——一旦 `repeat` 从 5 改成 20，这类硬编码会静默错位，出的表全错还不报错。
3. runner 每个 run 结束后自动解析 `.sca`，逐条断言 manifest 里的参数确实生效（对比 `.sca` 的 config/param 段），不一致 → 直接标 FAILED 并保留日志，禁止入库。

验收：故意把 `fading` 写到错误路径，流水线必须**拒绝**该 cell，而不是产出 60 个"看起来正常"的结果。

### P3 统一调度与并行：512 核现在只用了 4–16 路

【实测】机器 512 核 / 503GB 内存；当前并发是 `run_matrix.sh` 的 `JOBS=4` 或 `run_frer_resume.sh` 的 5 个手工分片。

做法：

1. manifest → 任务表 `(config, run)` → 进程池（Python `concurrent.futures`，或 `xargs -P`；服务器无 GNU parallel，别依赖它），跑 32–64 路。
2. 每个 cell 原子化：写临时目录 → 校验 `.sca` → 原子改名 + `DONE` 标记；失败重试 3 次后落 `.FAILED` + 日志摘要。
3. 进度与状态写 SQLite（`runs(state, config, run, seed, started, ended, exit_code, sca_sha, meta_path)`），支持 `--resume`、`--only-failed`。
4. ⚠️ 并发上限要先按"产物体积 × 并发"和内存算：现在一个 run 526MB `.vec`，64 路并发瞬间 33GB 落盘——**P0 不先做完就别放大并发**。

验收：一条命令跑完 N=1..40 × 5 sched × 20 seeds，无人工分片；`Ctrl-C` 后 `--resume` 无缝续跑；每个 cell 有独立日志。

### P4 指标库：把三套解析器合成一套口径

做法：单一 `ingest` 把 `.sca`/`.vec` 收进 DuckDB/Parquet，主键 `(exp, config, N, sched, seed, rep, endpoint, flow, qfi)`；`kpi.py` 只实现一次：

- 送达率 / 丢包率（口径固定为 §9.1 那条：`1 - ΣtsnDeviceB[*].app[0].packetReceived ÷ 40000`）
- mean / p50 / p99 / **p99.9** / max、抖动（stddev、IQR）
- gPTP 驻留时间 mean / **variance** / max（对标论文 Table VI）
- **QoS 隔离度**：CLC 高优 vs BE 的 Δmean / Δp99（对标论文"1.16ms gap"的论证方式）
- FRER 开销：`replicatedFrames`、`duplicatesDropped`、`recoveredFromPrimary/Replica`、空口负载增量
- 扩展性：N↑ 时 p99 的斜率与其置信区间

两个必须记住的坑：

- `recoveredFromReplica` 是"**副本先到**被接受"，不是"从副本恢复的丢包"（§3.1 已确认）；
- **p99.9 需要样本量**：单 run 8000 帧不够，建议 ≥20 seeds；现在只有 5 个 seed，p99 尚可、p99.9 不稳。

依赖：conda 环境已有 numpy 2.5.3 / pandas 2.3.3 / scipy 1.18.0 / matplotlib 3.11.1 / tqdm / psutil；**没有 pyarrow 与 duckdb**，要 Parquet/DuckDB 需 `pip install`（离线机器请先确认网络）。

验收：一条命令从结果库生成"论文级表格"（Table IV 风格三行数字），并带置信区间。

### P5 回归与论文基线锚定

做法：`ci.sh` = 构建 → 4 个 `tests/` 场景 → `smoke_test.sh` → 论文基线复现（3 端点 / 2 DRB / MAXCI / gPTP 125ms / 10s(1s warmup) / 理想 + Rayleigh 无 shadowing）。
对论文数字设容差断言：Table IV（高优 mean 2.58ms、p99 3.12、max 3.41 / BE 3.74、5.89、7.23）、Table VI（理想方差 <0.2µs、衰落 48.2µs、送达 99.9%/99.7%）。
容差建议先放宽到 ±20%（版本漂移见 P1），把偏差作为**已知差异**记录，而不是当失败。

验收：任何源码/参数改动后，一条命令给出"是否偏离基线"的报告。**这是判断"我新做的实验可信"的唯一办法。**

## 10.4 建议的目录结构（只加在 `experiments/`，不动三棵源码树）

```
experiments/
├── env/          env.lock.yaml, versions.sh, rebuild.sh（重建+自检）
├── specs/        frer_path_diversity.yaml, scalability.yaml, paper_baseline.yaml, fading_calib.yaml
├── gen/          gen_configs.py  → 产出 ini/profiles + manifest.json
├── runner/       run_experiment.py（manifest 驱动，并行/续跑/重试/校验）
├── ingest/       ingest.py（.sca/.vec → store，含 opp_scavetool 瘦身钩子）
├── analysis/     kpi.py（唯一指标实现）, figures.py, tables.py
├── report/       report.py（markdown + PDF，图表自动编号）
├── store/        results.duckdb, raw/<exp>/<config>_run<r>.{sca,meta.json}
├── logs/         每 cell 一个日志（替代现在的 log_resume_*.log 命名）
└── docs/         环境使用说明、指标定义、踩坑记录
```
原则：**配置即数据**——manifest 是唯一事实源；`.sca` 的文件名/目录名规则一旦改动，必须先改 manifest，因为现有解析脚本用正则 `Frer(?P<cfg>\w+)_N(?P<N>\d+)_run(?P<rn>\d+)\.sca$` 绑定了命名。

## 10.5 建议的实验主线（端到端环境要服务的问题，按价值排序）

| 线 | 内容 | 依据 | 成本 |
|---|---|---|---|
| **A ★路径分集** | `transportBinding ∈ {drb, pduSession, dualConnectivity}` × 信道 × 调度器，输出"送达率 vs 信道恶化"曲线 | 已证明 drb 级 FRER 防不住信道丢包（差信道 7.94% vs baseline 1.29%，反而 6 倍差）；F3 已实现、F4 开发中 | 中（F4 需源码收尾） |
| **B 确定性指标重分析** | 用已有 60 run 出 p99/p99.9/max、抖动、QoS 隔离度、驻留时间方差 | §7-P0，零仿真成本 | 低（0.5 天） |
| **C 扩展性** | N=1..40（profiles 已就绪）× 5 sched × ≥20 seeds | 论文 future work 明写"up to 20 endpoints"，我们有 N=40 脚手架 → **可超越论文** | 中（受 P0 存储制约） |
| **D TAS/802.1Qbv + 动态 BMCA** | 论文已知限制 1、2 | README Known Limitations 1/2 | 高（要动源码，是论文的空白区） |
| **E 参数敏感性** | gPTP syncInterval（125ms/1s/4s/8s）× 驻留时间方差；信道标定补 -96/-97dBm | §7-P3/P4；4s 在差信道会 gPTP 溢出，已用 8s 补跑 | 低–中 |

建议顺序：**B（立刻，零成本）→ P0/P1（基础设施）→ A（科学主线）→ C → E → D**。

## 10.6 不建议做的事（省下来的都是净赚）

1. 不要重跑已有 60 run 的相同配置去"确认"结论——直接对现有 `.vec` 做重分析。
2. 不要在 `frer_sweep.ini` 上继续堆手写配置块——先有 manifest 再扩矩阵，否则维度一多必然错配。
3. 不要在 P1（版本冻结）之前大改源码——F4 正在开发中，现在覆盖就永久失去可回滚点。
4. 不要用 `**.vector-recording = true` 跑 N=40 大规模矩阵——磁盘会先崩（见 P0 外推）。
5. 不要把"调度器比较"当论文主题——论文口径是桥能力（QoS 隔离 + 时钟精度 + 扩展性），调度器扫描只是我们 FRER 新工作的实验维度。
6. 不要在脚本里 `conda activate`（后台会挂起）——沿用现有"显式 export PATH"的写法；分析脚本一律用 `/media/a100/data/zbw/conda-envs/nasctime/bin/python` 绝对路径。

## 10.7 落地顺序与工作量估计

| 步骤 | 内容 | 依赖 | 估计 | 交付物 |
|---|---|---|---|---|
| 1 | 现有 `.vec` 全量指标提取 + 删 `.vec` 释放 ~56GB | 无 | 0.5 天 | 确定性指标 CSV/Parquet |
| 2 | `git init` + fork patch 存档 + env.lock | 无 | 0.5 天 | 可回滚的版本快照 |
| 3 | spec → gen → manifest 骨架（先覆盖现有 FRER 三配置） | 2 | 1–2 天 | `gen_configs.py` + manifest |
| 4 | runner（并行/续跑/重试/.sca 参数断言） | 3 | 1–2 天 | `run_experiment.py` |
| 5 | ingest + kpi（合并三套解析口径） | 1,4 | 1–2 天 | `results.duckdb` + `kpi.py` |
| 6 | report 自动出表出图 | 5 | 1 天 | 报告模板 |
| 7 | 论文基线复现 + 容差断言（ci.sh） | 2,4,5 | 1–2 天 | 基线锚点 |
| 8 | F3/F4 端到端跑通（先 N=1，再 N=15） | 4 | 2–5 天 | 路径分集数据 |

按 AI 代理执行估算，1–6 项大约 3–5 个工作日内可完工；7–8 项取决于源码层（F4 的 `gnb2.masterId` 等注释里已标"待验证"的点）。

## 10.8 第一周可执行清单（可直接照着做）

- [ ] `cp` 一份现有 60 run 的 `.sca` 到 `store/raw/`，写 `ingest` 的 v0（只读 `.sca`，不碰 `.vec`），先把 loss/mean/p99 复现出来与现有 CSV 对齐。
- [ ] 单开一个白名单录制的 ini，跑 1 个 run 验证体积 < 30MB，且指标与旧 run 一致。
- [ ] `git init` 三棵树 + `diff -ruN` 生成 fork patch + 记录 gcc/omnetpp/qt6/conda 版本。
- [ ] 写 `manifest.json` 生成器，先把 `FrerBaseline/Asym/Sym_N15 × 20 runs` 完整描述出来（含 `run→sched` 映射，取代硬编码元组）。
- [ ] runner 先做成"顺序 + resume"的 v0（并行留到 P0 瘦身之后），但**必须带 .sca 参数断言**。
- [ ] 定下 KPI 定义文件（一页 markdown），作为后续所有表格的唯一依据。

## 10.9 现场硬事实速查（复核命令）

| 事实 | 复核命令 | 实测值 |
|---|---|---|
| 结果体量 | `du -sh experiments/results/*` | `frer` 29G / `frer_fading` 29G |
| 单 run 组成 | `ls -la experiments/results/frer_fading/FrerAsym_N15_run0.*` | .sca 6.1M / .vci 13.6M / .vec 524M |
| 向量数量 | `grep -c '^vector ' <run>.vec` / `grep -c '^scalar ' <run>.sca` | 8436 / 8635 |
| 磁盘余量 | `df -h /media/a100/data` | 7.3T 总，3.9T 用，3.1T 可用 |
| 机器规格 | `nproc; free -g` | 512 核 / 503GB |
| fork 差异 | `diff -rq -x out -x '*.o' -x '*.so' Simu5G-vanilla-1.5.0 Simu5G` | 35 个文件，零新增 |
| 版本管理 | `ls -d nascTime/.git Simu5G/.git inet/.git` | 三者均不存在 |
| 缺什么工具 | `which parallel jq opp_scavetool` | parallel 缺失；jq、opp_scavetool 有 |
| 源码树污染 | `du -sh nascTime/simulations/demos/frer_test/results` | 377MB（120 个文件，建议移出源码树） |
| Python 依赖 | `conda-envs/nasctime/bin/pip list` | py3.12.14 / numpy 2.5.3 / pandas 2.3.3 / scipy 1.18 / matplotlib 3.11.1 / tqdm；**无 pyarrow、duckdb** |

---

> 一句话总结：**仿真这条端已经通了，缺的是实验流程这条端。** 先做 P0（瘦身 + 重分析，零仿真成本、立刻能出确定性指标）与 P1（版本冻结），再补 P2/P3（manifest + 调度），最后把资源投到主线 A（F3/F4 路径分集）——那是当前唯一能把"5G 当确定性桥"这个论证从"防不住"翻成"防得住"的方向。
