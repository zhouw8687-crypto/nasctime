//
// ProjectBookLadder —— 按 Spirent 参考拓扑改造的“日”字形端到端环境
//
// 结构（对照参考图）：
//
//                        server
//                          │
//                     coreRouter ── upf (N3/N6)
//                     ╱          ╲
//                  NE1 ════════ NE2          ← 5GC 双归接入（左上角连核心网）
//                   ║             ║
//                  NE3 ════════ NE4
//                   ║             ║
//                  NE5 ════════ NE6          ← gNB 侧双归接入（最下面一层连基站）
//                   ║             ║
//                 host        ranRouter ── gnb ⇢ ue[0]
//
// 与参考图的对应关系：
//   NE1..NE6      ↔ 参考图中的 6 台 NE（此处用带 Qbv 的 TsnSwitch）
//   5GC           ↔ coreRouter + upf + server（双归至 NE1、NE2）
//   eNB           ↔ gnb（经 ranRouter 双归至 NE5、NE6）
//   测试仪表      ↔ host（客户侧接入 NE1）
//
// 关键设计：
//   1) 日字形在二层会成环，而 L2 环 + IP 会触发 ARP 广播风暴（实测 P99 从 161µs 恶化到 981.9ms）。
//      先尝试 RSTP，但 BPDU 要求全链路具备 LLC 协议栈，端节点（终端/路由器）无法承载，故改用
//      **三层可路由的日字形**：六台 NE 用 Router，环路由路由自然处理，冗余路径用于后续保护倒换验证；
//   2) Qbv 门控能力已在 pe_test 中单独验证，本场景聚焦"日字形拓扑下的端到端指标"，
//      待 STP 方案打通后再把 NE 换回 TsnSwitch 以叠加门控。
//
package nasctime.simulations.demos.e2e_ladder;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.ethernet.EthernetLink;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.nodes.NrUe;
import simu5g.nodes.Upf;
import simu5g.nodes.gNodeB;
import simu5g.world.radio.LteChannelControl;

network ProjectBookLadder
{
    submodules:
        configurator: Ipv4NetworkConfigurator {
            @display("p=60,60");
        }
        binder: Binder {
            @display("p=60,120;is=s");
        }
        channelControl: LteChannelControl {
            @display("p=60,180;is=s");
        }
        carrierAggregation: CarrierAggregation {
            @display("p=60,240;is=s");
        }

        // ===== 承载网（日字形，6 台 NE）=====
        NE1: Router {
            @display("p=420,180");
        }
        NE2: Router {
            @display("p=620,180");
        }
        NE3: Router {
            @display("p=420,320");
        }
        NE4: Router {
            @display("p=620,320");
        }
        NE5: Router {
            @display("p=420,460");
        }
        NE6: Router {
            @display("p=620,460");
        }

        // ===== 核心网（5GC，双归 NE1/NE2）=====
        coreRouter: Router {
            @display("p=520,40");
        }
        upf: Upf {
            @display("p=380,40");
        }
        server: StandardHost {
            @display("p=680,40");
        }

        // ===== 无线接入（双归 NE5/NE6）=====
        ranRouter: Router {
            @display("p=800,460");
        }
        gnb: gNodeB {
            @display("p=800,600;is=vl");
        }
        ue[1]: NrUe {
            @display("p=930,600");
        }

        // ===== 有线终端 / 测试仪表 =====
        host: TsnDevice {
            @display("p=280,460");
        }

    connections:
        // ---- 日字：三横 ----
        NE1.ethg++ <--> EthernetLink <--> NE2.ethg++;
        NE3.ethg++ <--> EthernetLink <--> NE4.ethg++;
        NE5.ethg++ <--> EthernetLink <--> NE6.ethg++;

        // ---- 日字：两竖（左）----
        NE1.ethg++ <--> EthernetLink <--> NE3.ethg++;
        NE3.ethg++ <--> EthernetLink <--> NE5.ethg++;

        // ---- 日字：两竖（右）----
        NE2.ethg++ <--> EthernetLink <--> NE4.ethg++;
        NE4.ethg++ <--> EthernetLink <--> NE6.ethg++;

        // ---- 5GC 双归（左上角连核心网）----
        coreRouter.ethg++ <--> EthernetLink <--> NE1.ethg++;
        coreRouter.ethg++ <--> EthernetLink <--> NE2.ethg++;

        // ---- 核心网内部 ----
        coreRouter.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        upf.dnPppg <--> { datarate = 10Gbps; delay = 10us; } <--> coreRouter.pppg++;
        coreRouter.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> server.pppg++;

        // ---- 基站侧双归（最下面一层连基站）----
        ranRouter.ethg++ <--> EthernetLink <--> NE5.ethg++;
        ranRouter.ethg++ <--> EthernetLink <--> NE6.ethg++;
        ranRouter.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> gnb.ppp;

        // ---- 有线终端 ----
        host.ethg++ <--> EthernetLink <--> NE1.ethg++;
}
