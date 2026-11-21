# nascTime 实验仓库（源码 + 实验 + 验证框架设计）

本仓库把**源码、实验脚本、文档、指标契约**纳入版本控制；**仿真产物与第三方大包不入库**，靠 `experiments/env/env.lock.yaml` 与归档压缩包恢复。

## 在 A100 运行仿真

登录 A100，进入 `/media/a100/data/zbw/nasctime`，运行以下任一场景：

~~~bash
python3 experiments/bin/simulate.py ran
python3 experiments/bin/simulate.py transport --policy tas
python3 experiments/bin/simulate.py core
python3 experiments/bin/simulate.py e2e --policy priority
~~~

| 场景 | 默认负载 `baseline` | 加压负载 `--load stress` | 调度选项 |
|---|---|---|---|
| `ran` 无线接入 | 单小区，下行 200 B 每 10 ms | 下行 200 B 每 1 ms | 模型原生 |
| `transport` 日字形承载 | 双接入各三类流，单侧 80% 混合负载 | 低优流在 0.6–1.1 s 拉到线速 | `fifo` / `priority` / `tas` |
| `core` 核心网转发 | Router 代理用户面，200 B 每 10 ms | 200 B 每 1 ms | 模型原生 |
| `e2e` 端到端 | 两个基站，双向各三类轻载流 | 提高载荷和发包频率 | `priority` / `tas` |

承载和端到端默认使用 `priority`（三队列常开）。`tas` 使用相同分类和队列并启用周期门控。默认种子为 0，可用 `--seed` 修改。端到端场景使用 Simu5G UPF 和 GTP-U。核心网独立场景用于用户面转发基线。

每次运行在 `experiments/results/` 下新建目录，可用 `--output-dir` 选择结果的父目录。命令结束时会打印逐流摘要，目录内包含：

- `summary.md` 与 `flows.csv`。按流给出收发、未送达比例、时延、峰峰值抖动和净荷吞吐。CSV 另含标准差和分窗口统计。承载加压场景附带扰动前、中、后的统计。
- `run.json` 与 `run.log`。保存配置、种子、Git 版本、实际命令、运行状态和日志。
- 原始 `.sca` 和 `.vec`。端到端场景还会输出承载网 PCAP。

默认运行 2 秒仿真时间，1.7 秒停止发包，余下时间用于排空。统计以发送报文的序列号配对，口径是应用层单向时延。同一次运行的 `run.json` 记录了精确统计区间。首次搭建及编译见 [A100 环境说明](handoff/01-环境与登录.md)，完整机制实验见 [日字形验证记录](experiments/docs/exp-08-routed-ladder-validation.md)。

## 目录结构

| 路径 | 说明 | 入库 |
|---|---|---|
| `nascTime/` | 5G-TSN 桥仿真工程（NW-TT/DS-TT/gPTP/FRER/QoS 映射） | ✅（排除 `out/`、`results/`） |
| `Simu5G/` | Simu5G **fork**（`nasctime-v1.0`，基于 1.5.0，含 FRER 所需的路径分集） | ✅（排除 `out/`） |
| `experiments/` | 实验脚本、结果 CSV、文档、指标契约、环境锁定 | ✅（排除 `results/`，约 57G） |
| `experiments/docs/` | 设计文档：`project-model-mapping.md`（上位，项目书四层与指标）、`framework-module-design.md`（框架实现细节）、`kpi-definitions.md`（KPI 口径）、`schema/`（JSON Schema） | ✅ |
| `experiments/specs/` | `test-conditions.json`（23 个指标的测试条件，可自由改） | ✅ |
| `experiments/env/` | `env.lock.yaml`（版本锁定）、`Simu5G-fork.patch`（fork 差异存档） | ✅ |
| `inet/`、`omnetpp-6.4.0/`、`Simu5G-vanilla-1.5.0/` | 第三方与对照树 | ❌ 不入库 |
| `*.zip` / `*.tgz` / `*.pdf` | 归档与论文 | ❌ 不入库 |

## 恢复方式

```bash
# 1) 校验归档文件
sha256sum -c <(grep -A20 '^archives:' experiments/env/env.lock.yaml)   # 或手工对照

# 2) 恢复 Simu5G fork（若被误覆盖）
rm -rf Simu5G && cp -a Simu5G-vanilla-1.5.0 Simu5G
patch -p0 < experiments/env/Simu5G-fork.patch
```

## 提交约定

**每次改动后立即保存：**

```bash
experiments/bin/git-save.sh "feat: 一句话说明改了什么"
```

- 提交信息用 `feat:` / `fix:` / `docs:` / `exp:` / `chore:` 前缀；
- 改指标阈值或测试条件时，提交信息必须写明"改了哪个指标、从多少改到多少"；
- 不要 `git add` 任何 `results/`、`*.vec`、`*.sca`（已在 `.gitignore` 中）。

## 关键不变式（改代码前先看）

见 `experiments/env/env.lock.yaml` 的 `invariants` 段，以及 `experiments/docs/project-model-mapping.md` §2.2（底座选型）与 §3.4（指标张力）。
