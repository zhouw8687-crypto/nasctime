//
// PeNetwork —— PE 承载域（L2 转发 + TSN 门控能力）
//
// 定位：项目书里的"承载网（PE 设备）"。它同时具备两项能力：
//   1) 转发（这里是 L2 桥接；L3/MPLS 能力后续叠加，见 mpls_test）
//   2) TSN 门控（802.1Qbv 固定传输窗口）—— 本文件的核心验证对象
//
// 拓扑（链式：避免 L2 环 + IP 的 ARP 广播风暴，环需要 MRP/STP）：
//
//   client1(BE) ─┐
//                ├─ pe1 ── pe2 ── server
//   client2(HP) ─┘
//
// 说明：真实 PE 通常是环/网，这里第一版用链式，环上保护倒换在后续增量。
//
package nasctime.simulations.demos.pe_test;

import inet.networks.base.TsnNetworkBase;
import inet.node.ethernet.EthernetLink;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;

network PeNetwork extends TsnNetworkBase
{
    submodules:
        client1: TsnDevice {
            @display("p=120,220");
        }
        client2: TsnDevice {
            @display("p=120,380");
        }
        pe1: TsnSwitch {
            @display("p=380,300");
        }
        pe2: TsnSwitch {
            @display("p=620,300");
        }
        server: TsnDevice {
            @display("p=860,300");
        }
    connections:
        client1.ethg++ <--> EthernetLink <--> pe1.ethg++;
        client2.ethg++ <--> EthernetLink <--> pe1.ethg++;
        pe1.ethg++ <--> EthernetLink <--> pe2.ethg++;
        pe2.ethg++ <--> EthernetLink <--> server.ethg++;
}
