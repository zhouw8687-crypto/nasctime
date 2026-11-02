//
// SystemTest —— 整体组装模型（承载为中心 + 多接入）
//
// 架构（修正版：承载域在中心，各接入挂上去）：
//
//   TSN 有线接入（L2）        边界         承载域（L3，PE 环）           核心
//   ┌────────────────────┐  ┌──────┐   ┌─────────────────────┐   ┌────────┐
//   src ── pe1 ── pe2 ── pe3 ─ edgeRouter ─ lsr1 ── lsr2 ── lsr3 ─ upf ── server
//                                             └──────╲  ╱──────┘
//                                                    lsr3（三角环）
//
// 关键设计决定（都有实测依据）：
//
// 1) **L2 段必须是链，不能是环**。
//    最初写成三角环（pe1-pe2-pe3-pe1），结果 ARP 广播在环里绕圈：
//    端到端 p99 从 161 µs 恶化到 981.9 ms、丢 18 包。
//    原因：INET 的 EthernetSwitch/TsnSwitch **不跑 STP**。
//    要保留环，必须三选一：
//      a. 断一条边（本文件的做法，L2 段为链）；
//      b. 换 MrpSwitch（MRP 环保护）或加 STP；
//      c. 环上只跑无 IP 的静态 FDB 流量（见 ring_test 的 FRER 做法）。
//
// 2) **L3 段可以是环**：路由协议/路由表天然处理三角环，没有广播风暴问题。
//
// 3) 边界用 `edgeRouter`（INET Router）把 L2 桥接域和 L3 承载域分开：
//    pe3.ethg ↔ edgeRouter.ethg（以太网），edgeRouter.pppg ↔ lsr1.pppg（PPP）。
//    注意：一旦插入这个路由器，L2 广播域就断了，FRER 也只能到 pe3 为止。
//
// 4) 无线接入（gNB/UE）本版未接入：它需要真 Upf 终结 GTP，属下一增量。
//
package nasctime.simulations.demos.system_test;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;

network SystemTest
{
    submodules:
        configurator: Ipv4NetworkConfigurator {
            @display("p=60,60");
        }

        // ===== TSN 有线接入（L2 域，链式）=====
        src: TsnDevice {
            @display("p=120,300");
        }
        pe1: TsnSwitch {
            @display("p=260,300");
        }
        pe2: TsnSwitch {
            @display("p=400,300");
        }
        pe3: TsnSwitch {
            @display("p=540,300");
        }

        // ===== L2 / L3 边界 =====
        edgeRouter: Router {
            @display("p=680,300");
        }

        // ===== 承载域（L3，三角环）=====
        lsr1: Router {
            @display("p=820,300");
        }
        lsr2: Router {
            @display("p=960,220");
        }
        lsr3: Router {
            @display("p=960,400");
        }

        // ===== 核心 =====
        upf: Router {
            @display("p=1100,300");
        }
        server: StandardHost {
            @display("p=1240,300");
        }

    connections:
        // TSN 接入：链式（不能成环，见文件头说明）
        src.ethg++ <--> { datarate = 10Gbps; delay = 10us; } <--> pe1.ethg++;
        pe1.ethg++ <--> { datarate = 10Gbps; delay = 10us; } <--> pe2.ethg++;
        pe2.ethg++ <--> { datarate = 10Gbps; delay = 10us; } <--> pe3.ethg++;

        // 边界：L2 桥接口 + L3 上行口
        pe3.ethg++ <--> { datarate = 10Gbps; delay = 10us; } <--> edgeRouter.ethg++;
        edgeRouter.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> lsr1.pppg++;

        // 承载域：三角环（L3 可以成环）
        lsr1.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> lsr2.pppg++;
        lsr2.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> lsr3.pppg++;
        lsr3.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> lsr1.pppg++;

        // 核心
        lsr3.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        upf.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> server.pppg++;
}
