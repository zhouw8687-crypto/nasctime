# 仿真域目录约定

一个域一个目录，**互不 import、互不引用 ini**，只在 NED 里用一条链路连接。这样某个域出问题
（改参数、换模型、重跑），不会牵连其它域。

## 目录与角色

| 目录 | 域 | 层次 | 状态 | 关键机制 |
|---|---|---|---|---|
| `ring_test/` | **边缘有线接入** | L2 | ✅ 跑通 | TsnSwitch 三角环 + FRER 双路径 |
| `mpls_test/` | **L3 承载域** | L3 | ✅ 跑通 | 7 台 MPLS LSR + RSVP + 标签表 |
| `frer_test/` | 5G-TSN 桥接（nascTime 原场景） | L2+5G | ✅ 有 60 run 数据 | NW-TT/DS-TT + gPTP + FRER |
| `multi_endpoint_test/` | 3 端点参考场景 | L2+5G | ⚠️ 接收端未记录包 | 论文基线拓扑 |
| `ext_multiendpoint_test/` | N 端点参数化拓扑 | L2+5G | ✅ | frer_test 的底座 |
| （待建）`ran_test/` | 无线接入 | NR | ❌ | Simu5G gNodeB + NrUe |

## 三条纪律

1. **改一个域只动它自己的目录**。跨域参数不要写进对方的 ini。
2. **域边界只在 NED 里连**。典型边界：
   - L2 ↔ L3：路由器（会打断广播域，FRER 到此为止）
   - 5G ↔ L2：NW-TT / DS-TT 翻译器（保持 L2 语义）
3. **每个域的 README 必须写清**：角色、端口映射、跑法、已验证结论、待补项、与相邻域的边界。

## 端口映射是个坑

NED 里 `ethg++` 的**连接顺序**决定端口号（`eth[0]`、`eth[1]`…），探针和 GCL 都依赖它。
改拓扑后必须重新核对，否则探针数据全错。`ring_test/README.md` 里有一份现成的映射表可参照。
