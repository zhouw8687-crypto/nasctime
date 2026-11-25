# EXP-14 · 同优先级多流的 FRER 标识与去重

## 原理与测试边界

同一优先级可以包含多条业务。FRER 在每个方向的实例内，用 UDP 目的端口选中受保护流，再按独立 streamId 维护序号和恢复窗口。两端填写同一组 `{udpDestPort, streamId, primaryDscp}`。副本 DSCP 用于已有的 DRB 路径选择，先收到副本时，恢复器从流表读出业务 DSCP。未列入流表的业务直接通过。起始缺省配置继续采用历史 DSCP 选择与 IPv4 ID 兜底。

在历史路径上确认了一个封装问题。接收 IPv4 按 Total Length 裁掉尾部填充，原做法的序号尾部会被去除，新模式初次修改时两份业务都透传。显式映射模式把 4 字节仿真尾部计入 IPv4 Total Length，恢复后还原长度和校验和。尾部依赖 INET 的 Packet/Chunk 表示。这一回归覆盖模拟栈内非 IPv4 分片 UDP，线速序列化、802.1CB 线格式和原生 Ethernet PDU Session 需要单独验证。

## 实验配置

复用 `FrerAsym_N15` 的历史 NW-TT/DS-TT 网络以及 `drb` transport binding。新配置把三条同 DSCP 流送到同一个 DS-TT 和终端，确保两条受保护流使用同一个恢复器实例。运行 0，种子集 0，MAXCI、24 RB、60 ms、无 warmup。受保护流的应用包为 100 B，每 1 ms 发包，继承 0–10 ms 随机起始时间。保留原场景背景业务。

| UDP 目的端口 | streamId | 主流 DSCP | 副本 DSCP | 发送 | 应用收到 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5000 | 101 | 7 | 8 | 52 | 50 |
| 5020 | 103 | 7 | 8 | 57 | 54 |
| 5040 | 未注册 | 7 | — | 56 | 53 |

NW-TT 复制 109 个原始包。DS-TT[0] 接受主副本各 55、49 个，丢弃重复包 103 个，并转发 53 个未注册流的包。事件记录显示 streamId 101 和 103 的序号 0 都到达同一个恢复器，各放行一份。103 的副本先到，DSCP 从 8 恢复为 7。发送与接收数量差包含 60 ms 窗口结束时的未交付包，不能用短样本差值估计可靠性增益。

```text
FrerReplicator: stream=103 seq=0 primary DSCP=7 replica DSCP=8 [trailer]
FrerRecovery: ACCEPT stream=103 seq=0 source=REPLICA (DSCP 8 -> 7) [trailer]
FrerRecovery: DUPLICATE stream=103 seq=0, dropping
FrerReplicator: stream=101 seq=0 primary DSCP=7 replica DSCP=8 [trailer]
FrerRecovery: ACCEPT stream=101 seq=0 source=PRIMARY [trailer]
FrerRecovery: DUPLICATE stream=101 seq=0, dropping
```

另外运行了旧 `FrerAsym_N15` 和日字形 `CompetitionTas` 冒烟测试。旧配置在同样的 60 ms 内复制 271 个包，第一终端应用收到 50 个。日字形 300 ms 运行正常结束。将 5000 与 5020 配成同一个 streamId 时，初始化返回重复 ID 错误。日字形应用三流、逐端口策略联动及同步对照在 [三流同步验收方案](three-domain-sync-plan.md) 中列出。

## A100 复现

环境为 OMNeT++ 6.4.0、INET 4.6、项目的 Simu5G fork。使用 `handoff/01-环境与登录.md` 初始化工具链并执行 `make -C nascTime -j4`。从仓库根运行以下命令。

```bash
cd nascTime/simulations/demos/frer_test
result=$(mktemp -d)
../../../bin/nasctime-run.sh -f frer_sweep.ini -u Cmdenv \
  -c FrerIndependentStreams_N15 -r 0 --result-dir="$result"
grep -E 'frerReplicator replicatedFrames:count|dsTt\[0\].frerRecovery .*:count |tsnDeviceB\[0\].app\[[023]\] packetReceived:count' "$result/"*.sca

set -o pipefail
../../../bin/nasctime-run.sh -f frer_sweep.ini -u Cmdenv \
  -c FrerIndependentStreams_N15 -r 0 --sim-time-limit=18ms \
  --cmdenv-express-mode=false --cmdenv-log-level=INFO --result-dir="$result/trace" 2>&1 \
  | LC_ALL=C grep -aE 'Frer(Replicator|Recovery):.*stream=(101|103) seq=0([^0-9]|$)'
```
