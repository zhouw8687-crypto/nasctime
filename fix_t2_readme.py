import io

P = '/media/a100/data/zbw/nasctime/nascTime/simulations/demos/t2_slices/README.md'
t = io.open(P, encoding='utf-8').read()

start = t.find('## 已知阻塞')
end = t.find('## 跑法')
assert start != -1 and end != -1

new = '''## 当前状态：TAS 组未跑通，原因待定位（**此前“PCP 不可用”的结论已撤回**）

### 撤回的原因

前期曾判断“INET 的 PCP 路线走不通、需要自研 DSCP 分类器”。复查后该结论**不成立**：

1. INET 4.6 官方文档明确写着“帧按 PCP 分类（默认机制）”，
   `showcases/tsn/trafficshaping/timeawareshaper` 用的正是 `streamIdentifier + streamCoder` 打 PCP 这条路，
   且该示例标注“Verified with INET version 4.6”。
2. `PcpTrafficClassClassifier.ned` 的默认映射是 **IEEE 802.1Q 表 8-5 矩阵**，
   索引方式为 `mapping[pcp][等级数-1]`。**等级数为 3 时，PCP4 和 PCP5 都映射到等级 1**，
   等级 2 永远为空——本场景原配置在结构上就无法表达“三切片三等级”，这是配置错误，不是机制缺失。

因此**不需要**改 C++ 写自定义分类器，先用配置解决。

### 已定位的两个真实陷阱

| 陷阱 | 现象 | 处理 |
|---|---|---|
| 默认映射矩阵 | 3 个等级时 PCP4/PCP5 落在同一类 | 显式设置 `classifier.mapping`（行=PCP，列=等级数-1） |
| 表达式分类器遇到非 UDP 报文崩溃 | `Object nullptr has no member named 'destPort'` | ① 用 `**.arp.typename = "GlobalArp"` 消除 ARP；② UDP 载荷 ≤1472 B 避免 IP 分片（非首片无 UDP 头） |
| `GateControlList` 驱动三相窗口 | 三条流几乎全被卡死（各收到 0–1 个包） | 改用 `PeriodicGate` 直配；但**仍未跑通**，见下 |

### 已做的对照实验（用于定位）

| 实验 | 结果 | 推论 |
|---|---|---|
| `hasGcl = false`（不设门控，门默认全开） | 三条流全部正常（2052 / 3517 / 1792） | 通路、打标流程无阻塞 |
| 三相 GCL 只开 0 号门 | 三条流全部通过 | 所有流量都进了等级 0 |
| 三相 GCL 只开 5 号门 | 一条不通 | 等级 5 队列为空 |
| 显式 `classifier.mapping`（PCP5→2、PCP4→1）+ 三相 PeriodicGate | 仍各只收到 0–1 个包 | 打标或分类仍未生效 |
| 保留 802.1Q 标签（去掉 C-Tag 剥离） | 同上 | 标签并非瓶颈 |

**当前判断**：报文没有带上 `PcpReq`/`PcpInd` 标签，分类器取不到 PCP，全部落入默认等级 0；
而等级 0 的窗口只有 100 µs，于是几乎所有报文被卡住。

### 下一步（一步即可定性）

`Ieee8021qTimeAwareShaper` 的分类器有内置统计（`pkClass` 之类），或在客户端 bridging 层
加一个探针，直接观察**报文进入分类器时的 PCP 值**。据此可判定：

- 若 PCP 有值但不等于预期 → 打标配置问题（streamCoder 映射未命中）；
- 若 PCP 为空 → 标签未随报文传递，需要检查 `Ieee8021qProtocol` 与交换机标签处理链路。

在此之前**不要**改成自研 DSCP 分类器——那是把配置问题当成机制缺陷来解。

'''

t = t[:start] + new + t[end:]
io.open(P, 'w', encoding='utf-8').write(t)
print('README corrected')
