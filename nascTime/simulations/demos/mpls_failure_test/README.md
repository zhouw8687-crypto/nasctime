# mpls_failure_test —— L3 承载域（故障倒换）

> 来源：`inet/examples/mpls/testte_failure/`，只改了 `package` 与 `network`。
> 与 `../mpls_test/`（静态隧道）**同拓扑、不同用途**：这一份专门跑"节点故障 → 重收敛"。

## 故障脚本（`scenario.xml`）

```xml
<at t="2s"> <shutdown module="LSR4"/> </at>
<at t="4s"> <startup  module="LSR4"/> </at>
```

## 跑法

```bash
cd nascTime/simulations/demos/mpls_failure_test
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 \
  --sim-time-limit=6s --result-dir=results --**.vector-recording=true
python3 ../../../../experiments/exp/vec_gaps.py results 'host3.app[0]' packetBytes
```

必须开 `--**.vector-recording=true`，否则没有 `.vec`，算不出中断间隔。

## 实测（2026-11-02）

| 指标 | 值 |
|---|---|
| 采样数 | 513（6 s @ 10 ms，应有 600） |
| **最大中断** | **479.84 ms @ t=2.496 s**（LSR4 宕机） |
| 恢复期二次中断 | 320.16 ms @ t=4.576 s（LSR4 恢复） |

结论：节点级故障的重收敛时间是**数百毫秒级**，距电信级 50 ms 有量级差距。

## 注意

- 这是**节点故障**（shutdown 整个 LSR），不是链路故障。链路故障看 `testte_failure2`。
- 本域只验证"故障 → 恢复"的时间尺度，不含保护倒换配置（如 1+1/1:1 保护组）。
