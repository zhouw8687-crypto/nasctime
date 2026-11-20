//
// T2LadderNetwork —— 三流三切片 × 「日」字形承载网（按参考拓扑）
//
// 拓扑（与参考图一致：5GC 在顶、两台接入在底）：
//
//                          5GC (server)
//                          ╱          ╲
//                       NE1 ═════════ NE2
//                        ║              ║
//                       NE3 ═════════ NE4
//                        ║              ║
//                       NE5 ═════════ NE6
//                        ║              ║
//                   接入1(client1)   接入2(client2)
//
// 与参考图的对应：
//   5GC    ↔ server（双归 NE1、NE2）
//   eNB×2  ↔ 接入点 client1（NE5）、client2（NE6）
//   NE1–6  ↔ 承载网六节点（带 802.1Qbv 门控）
//
// 三条切片流分布在两个接入点上：
//   切片1（HP, PCP5）  client1 → NE5 → NE3 → NE1 → server   （2 跳）
//   切片3（LP, PCP0）  client1 → 同上                        （2 跳）
//   切片2（MP, PCP4）  client2 → NE6 → NE4 → NE2 → server   （2 跳）
//
// 说明：六节点 L2 有物理环路，本场景用 GlobalArp 消除 ARP 广播；
//       未知单播泛洪风险见 README“已知风险”。
//
package nasctime.simulations.demos.t2_ladder;

import inet.networks.base.TsnNetworkBase;
import inet.node.ethernet.EthernetLink;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;

network T2LadderNetwork extends TsnNetworkBase
{
    submodules:
        // ===== 5GC（顶部，双归）=====
        server: TsnDevice {
            @display("p=620,60");
        }

        // ===== 承载网（日字形）=====
        NE1: TsnSwitch {
            @display("p=520,180");
        }
        NE2: TsnSwitch {
            @display("p=760,180");
        }
        NE3: TsnSwitch {
            @display("p=520,320");
        }
        NE4: TsnSwitch {
            @display("p=760,320");
        }
        NE5: TsnSwitch {
            @display("p=520,460");
        }
        NE6: TsnSwitch {
            @display("p=760,460");
        }

        // ===== 两个接入点（底部）=====
        client1: TsnDevice {
            @display("p=520,600");
        }
        client2: TsnDevice {
            @display("p=760,600");
        }

    connections:
        // 三横
        NE1.ethg++ <--> EthernetLink <--> NE2.ethg++;
        NE3.ethg++ <--> EthernetLink <--> NE4.ethg++;
        NE5.ethg++ <--> EthernetLink <--> NE6.ethg++;

        // 左竖
        NE1.ethg++ <--> EthernetLink <--> NE3.ethg++;
        NE3.ethg++ <--> EthernetLink <--> NE5.ethg++;

        // 右竖
        NE2.ethg++ <--> EthernetLink <--> NE4.ethg++;
        NE4.ethg++ <--> EthernetLink <--> NE6.ethg++;

        // 5GC 双归
        server.ethg++ <--> EthernetLink <--> NE1.ethg++;
        server.ethg++ <--> EthernetLink <--> NE2.ethg++;

        // 底部两个接入点
        client1.ethg++ <--> EthernetLink <--> NE5.ethg++;
        client2.ethg++ <--> EthernetLink <--> NE6.ethg++;
}
