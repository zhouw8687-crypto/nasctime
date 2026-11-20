//
// ProjectBookLadder —— “日”字形端到端环境（顶部 5GC，底部两台基站）
//
// 结构（对照参考图，去掉测试仪表）：
//
//                         server            ← 数据网（N6）
//                           │
//                          upf              ← 5GC 锚点 UPF
//                       ╱        ╲
//                     NE1 ══════ NE2        ← 5GC 顶部接入（双归 NE1/NE2）
//                      ║            ║
//                     NE3 ══════ NE4
//                      ║            ║
//                     NE5 ══════ NE6
//                      ╲            ╱
//                        iUpf               ← 边缘 I-UPF（N3 汇聚，N9 上行）
//                       ╱      ╲
//                    gnb1      gnb2         ← 底部两台基站
//                     ┆          ┆
//                   ue[0]      ue[1]
//
// 与参考图的对应：
//   NE1..NE6 ↔ 日字形承载网（三层路由节点）
//   5GC      ↔ upf（锚点）+ iUpf（边缘）+ server，接入点在顶部 NE1/NE2
//   eNB      ↔ gnb1、gnb2，分别经 N3 直连 iUpf（Simu5G 官方多小区接法）
//   测试仪表 ↔ 不建模（参考图仅示意）
//
// 为什么两台基站要先汇聚到 iUpf 再上网：
//   直接把两台 gNB 分别接到 NE5/NE6 会让 Simu5G 在业务开始时崩溃
//   （LteHarqBufferRx::insertPdu 段错误）。官方多小区示例中，多台 gNB 都是
//   **直连同一个 I-UPF** 的，因此这里沿用该结构：N3 在 iUpf 汇聚，N9 再经
//   日字形网络送到锚点 UPF，既保住了双基站，也保住了“承载网在中间”。
//
package nasctime.simulations.demos.e2e_ladder;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.ethernet.EthernetLink;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.nodes.NrUe;
import simu5g.nodes.Upf;
import simu5g.nodes.gNodeB;
import simu5g.world.radio.LteChannelControl;

network ProjectBookLadder
{
    parameters:
        int numUe = default(2);

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
            @display("p=420,220");
        }
        NE2: Router {
            @display("p=620,220");
        }
        NE3: Router {
            @display("p=420,360");
        }
        NE4: Router {
            @display("p=620,360");
        }
        NE5: Router {
            @display("p=420,500");
        }
        NE6: Router {
            @display("p=620,500");
        }

        // ===== 5GC（顶部）=====
        upf: Upf {
            @display("p=520,120");
        }
        server: StandardHost {
            @display("p=520,30");
        }

        // ===== 边缘 I-UPF（N3 汇聚）=====
        iUpf: Upf {
            @display("p=520,620");
        }

        // ===== 底部两台基站 =====
        gnb1: gNodeB {
            @display("p=400,740;is=vl");
        }
        gnb2: gNodeB {
            @display("p=640,740;is=vl");
        }
        ue[numUe]: NrUe {
            @display("p=520,840");
        }

    connections:
        // ---- 日字：三横 ----
        NE1.ethg++ <--> EthernetLink <--> NE2.ethg++;
        NE3.ethg++ <--> EthernetLink <--> NE4.ethg++;
        NE5.ethg++ <--> EthernetLink <--> NE6.ethg++;

        // ---- 日字：左竖 ----
        NE1.ethg++ <--> EthernetLink <--> NE3.ethg++;
        NE3.ethg++ <--> EthernetLink <--> NE5.ethg++;

        // ---- 日字：右竖 ----
        NE2.ethg++ <--> EthernetLink <--> NE4.ethg++;
        NE4.ethg++ <--> EthernetLink <--> NE6.ethg++;

        // ---- 5GC 顶部：锚点 UPF 双归 NE1/NE2 ----
        NE1.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        NE2.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        upf.dnPppg <--> { datarate = 10Gbps; delay = 10us; } <--> server.pppg++;

        // ---- 边缘 I-UPF 双归 NE5/NE6（N9 走日字形）----
        NE5.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> iUpf.pppg++;
        NE6.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> iUpf.pppg++;

        // ---- 底部两台基站：N3 直连 I-UPF（官方多小区接法）----
        iUpf.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> gnb1.ppp;
        iUpf.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> gnb2.ppp;
}
