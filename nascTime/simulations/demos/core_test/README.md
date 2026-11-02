# core_test —— 核心网域（用户面）

> 角色：项目里的**核心网域**，负责用户面转发、流识别与策略、切片隔离。
> 与 `../ran_test/`（无线）、`../ring_test/`（L2 边缘）、`../mpls_test/`（L3 承载）域隔离。

## 结构

```
hostA ●──10G──● iUpf ●──10G──● upf ●──10G──● server
(接入侧代理)   (N3 汇聚)      (用户面锚点)    (外部数据网)
```

跑法：

```bash
cd nascTime/simulations/demos/core_test
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=3s --result-dir=results
```

## 实测（2026-11-02）

| 指标 | 值 |
|---|---|
| hostA → server | 发 299，收 **299（100%）** |
| 端到端时延 mean | **0.71 µs** |
| p99 / max | 0.71 / 0.71 µs |

## 为什么用 `Router` 代理 UPF（重要）

Simu5G 的 `Upf` **不能单独当 IP 路由器用**，实测会挂在 `upf.ipv4.lp`：

```
<!> Error: Connected network interfaces can register using registerInterface()
    or the interfaceMapping parameter can be used to specify the output gate
    -- in module CoreNetwork.upf.ipv4.lp
```

根因在 `Simu5G/src/simu5g/nodes/Upf.ned` 的 connections：

```ned
dnPpp.upperLayerOut --> trafficFlowFilter.internetFilterGateIn;
dnPpp.upperLayerIn  <-- gtp_user.pppGate;
dnPpp.phys <--> dnPppg;
```

`dnPpp` 只与 `gtp_user` 相连，**必须有一个 GTP 对端（gNB 的 `GtpUser`）** 才能完成封装/解封装并让接口注册。官方也只把它放在带 gNB 的网络里（`SingleCell_Standalone` / `MultiCell_Standalone`）。

Simu5G 文档自己写着 "act like IP routers in the current version"，所以在"只验证转发/时延/切片"的最小核心域里，用 `Router` 代理 UPF 是**功能等价**的。

**换回真 UPF 的条件**：接入真 gNB（存在 GTP）之后，把 `iUpf` / `upf` 换回 `Upf`，接法照抄 `MultiCell_Standalone`：

```ned
iUpf.pppg++ <--> Eth10G <--> gnb.ppp;
upf.pppg++  <--> Eth10G <--> iUpf.pppg++;
upf.dnPppg  <--> Eth10G <--> router.pppg++;
```

## 缺什么

| 缺 | 说明 |
|---|---|
| 策略点（PolicyPoint） | 流识别 + 切片规则 + 限速，需要自建 simple module |
| 切片隔离 | 目前无 per-slice 队列/限速；可用 INET `TokenBucket` + DSCP 分类实现 |
| GTP / N3 语义 | 当前是纯 IP，接 gNB 后才需要 |
| 控制面信令 | AMF/SMF/PCF 等**不建模**（Simu5G 也没有） |
| 与其它域的连接 | 接入侧应与 I-UPF 相连（`gnb.ppp → iUpf.pppg`），尚未做 |
