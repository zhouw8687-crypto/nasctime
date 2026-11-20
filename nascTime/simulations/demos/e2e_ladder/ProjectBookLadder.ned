//
// ProjectBookLadder —— “日”字形端到端环境（底部两个基站）
//
// 结构（对照参考图，去掉测试仪表）：
//
//                        server
//                          │
//                       upf.dnPppg
//                    upf.pppg[0]  upf.pppg[1]
//                        │            │
//                  NE1 ══════════ NE2        ← 核心网双归（左上角连核心网）
//                   ║                ║
//                  NE3 ══════════ NE4
//                   ║                ║
//                  NE5 ══════════ NE6        ← 最下面一层接两个基站
//                   ║                ║
//                 gnb1             gnb2
//                   ┆                ┆
//                  ue[0]           ue[1]
//
// 与参考图的对应：
//   NE1..NE6 ↔ 6 台 NE（三层路由节点）
//   5GC      ↔ upf + server（双归至 NE1、NE2）
//   eNB      ↔ gnb1、gnb2（分别接在 NE5、NE6）
//   测试仪表 ↔ 不建模（参考图中仅为示意，且无对应的仿真元器件）
//
// 说明：
//   - 日字形在二层会成环，L2 环 + IP 会触发 ARP 广播风暴（实测 P99 从 161µs 恶化到 981.9ms）。
//     曾尝试用 RSTP 消除，但 BPDU 走 LLC，端节点（终端/路由器）二层无 LLC 协议栈会报错，
//     故 NE 采用三层可路由节点，环路由路由处理。
//   - 两条竖边（NE1-NE3-NE5 与 NE2-NE4-NE6）构成两条边不相交路径，可用于后续保护倒换验证。
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
        int numUe = default(1);

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

        // ===== 核心网（5GC）=====
        upf: Upf {
            @display("p=520,50");
        }
        server: StandardHost {
            @display("p=520,10");
        }

        // ===== 两个基站 =====
        gnb1: gNodeB {
            @display("p=420,620;is=vl");
        }
        // 第二台基站：当前启用会导致 Simu5G HARQ 段错误（见 README），暂不实例化
        // gnb2: gNodeB {
        //     @display("p=620,620;is=vl");
        // }
        ue[numUe]: NrUe {
            @display("p=420,720");
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

        // ---- 核心网双归（左上角连核心网）----
        NE1.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        NE2.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        upf.dnPppg <--> { datarate = 10Gbps; delay = 10us; } <--> server.pppg++;

        // ---- 底部两个基站 ----
        NE5.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> gnb1.ppp;
}
