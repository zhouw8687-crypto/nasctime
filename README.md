# nascTime 实验仓库（源码 + 实验 + 验证框架设计）

本仓库把**源码、实验脚本、文档、指标契约**纳入版本控制；**仿真产物与第三方大包不入库**，靠 `experiments/env/env.lock.yaml` 与归档压缩包恢复。

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
