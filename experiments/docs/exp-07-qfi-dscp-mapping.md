# EXP-07：gNB → 承载网的切片映射（QFI → DSCP）

> 解决「5G 切片在承载网上塌缩成一个优先级」的问题。
> 对应 3GPP 的 QoS 映射链第 ④ 层（QFI/5QI → 外层 IP 的 DSCP）。
> 场景：`nascTime/simulations/demos/e2e_ladder/`（日字形 + 5GC + 两 eNB）

## 1. 问题

承载网按 DSCP/PCP 分类，而 Simu5G 的 `GtpUser` 在做 GTP-U 封装时**不设置外层 IP 的 DSCP**
（`GtpUser.cc` 中无任何 `DscpReq`/`setTos`），导致 N3 外层 DSCP 恒为 0：

> 所有切片到了承载网都会被识别成同一个优先级类，切片在承载网上塌缩。

## 2. 3GPP 的映射链（四层）

```
业务/应用
   │ ① 5QI 选择（0–255，PCF 策略 / S-NSSAI）
   ▼
QoS Flow（5QI）
   │ ② QFI 分配（6 bit，1–63，PDU Session 内唯一）
   ▼
QFI ────③ SDAP：QFI ↔ DRB────▶ DRB（无线承载）
   │
   └──④ QFI → 外层 DSCP（运营商策略，非标准强制映射）
          ▼
       N3 外层 IP 的 DSCP ──▶ 承载网 DiffServ
```

| 层 | Simu5G 实现 | 状态 |
|---|---|---|
| ① 5QI | 无 | ❌ 未建模 |
| ② DSCP→QFI | `TrafficFlowFilter.cc:139`（源码注释自认是简化） | ⚠️ 简化 |
| ③ QFI↔DRB | `NrSdap.drbConfig`（JSON 表） | ✅ 完整 |
| **④ QFI→DSCP** | `GtpUser` | ❌→**✅ 本次补齐** |

## 3. 业界的实现方式

| 方案 | 标识位置 | 代表 |
|---|---|---|
| **A. 外层 IP 的 DSCP**（本次采用） | GTP 外层 IP 头 | Juniper `services agf fiveqi-map`、专利 EP4096290B1 |
| B. GTP-U 头中的 QFI | GTP-U 扩展头 | IETF DMM 草案讨论 |
| C. 外层 UDP 源端口 | GTP 的 UDP 端口 | draft-ietf-dmm-tn-aware-mobility |

主流是方案 A：**按 5QI 设置外层 IP 头的 DSCP**（专利原文：set DSCP in an outer IP header
according to the 5QI）。

## 4. 本次改动

### 4.1 补丁内容

在 Simu5G 的 `GtpUser` 中增加 QFI→DSCP 映射：

| 文件 | 改动 |
|---|---|
| `GtpUser.ned` | 新增参数 `string qfiDscpMap = default("")`，格式 `"qfi:dscp,qfi:dscp"` |
| `GtpUser.h` | 新增 `std::map<int,int> qfiDscpMap_` |
| `GtpUser.cc` | 初始化时解析映射表；GTP 封装后按 QFI 查表设置 `DscpReq`（缺省 DSCP = QFI） |

核心逻辑：

```cpp
int dscp = (it != qfiDscpMap_.end()) ? it->second : static_cast<int>(qfi);
if (dscp >= 0 && dscp <= 63)
    gtpPacket->addTagIfAbsent<inet::DscpReq>()->setDifferentiatedServicesCodePoint(dscp);
```

INET 的 `Ipv4::encapsulate` 会读取该标签并写入 IP 头的 TOS 字段（`Ipv4.cc:1037`）。

### 4.2 配置示例

```ini
# 缺省：DSCP = QFI（QFI 0–63 正好落在 DSCP 范围内）
*.gnb*.gtpUser.qfiDscpMap = ""

# 显式映射（对标 Juniper fiveqi-map）
*.gnb*.gtpUser.qfiDscpMap = "1:46,5:34,9:0"
```

### 4.3 验证

场景：`e2e_ladder`，UE 应用设 `dscp=46`，仿真 2.5 s。在打标处临时打印：

```
QFI2DSCP-DEBUG qfi=46 dscp=46
QFI2DSCP-DEBUG qfi=0 dscp=0
```

共打标 **294 次**，QFI 46 正确映射为 DSCP 46，说明：

1. UE 应用的 DSCP 46 经过 `TrafficFlowFilter`（QFI = DSCP）传到 QFI；
2. `GtpUser` 把 QFI 写入 GTP-U 头；
3. 新增的第 ④ 层把 QFI 映射为外层 DSCP；
4. 外层 IP 头携带 DSCP 46 进入承载网。

## 5. 仍未完成的部分

| 项 | 状态 | 说明 |
|---|---|---|
| gNB → 承载网 DSCP 打通 | ✅ | 本次完成 |
| 承载网按 DSCP 分类 | ❌ | `e2e_ladder` 的 NE 是 `Router`（L3），没有 Qbv 队列；需改成 `TsnSwitch` |
| DSCP → PCP 映射 | ❌ | L2 交换机的分类器读 PCP，需要网关于入口把 DSCP 映射到 PCP |
| 5QI 建模 | ❌ | Simu5G 无 5QI 概念，当前用 DSCP 顶替 QFI |

## 6. 复现

```bash
cd nascTime/simulations/demos/e2e_ladder
../../../bin/nasctime-run.sh -f omnetpp.ini -u Cmdenv -r 0 --sim-time-limit=2.5s \
  --result-dir=results_dscp '--*.ue[*].app[0].dscp=46'
```

（验证时需在 `GtpUser.cc` 临时加打印；正式版本已移除。）
