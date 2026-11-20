//
// T2LadderNetwork —— 三流三切片 × 日字形承载网
//
// 目的：把 t2_slices（链式两跳）的三切片配置搬到日字形六节点环网上，
//       验证多跳、多路径、存在环路的 L2 承载网中，切片隔离与门控是否仍然成立。
//
// 拓扑：
//
//        client3 ── NE3 ── NE1 ── server
//                    ║        ║
//                   NE4 ════ NE2
//                    ║        ║
//        client1 ── NE5 ════ NE6 ── client2
//
//   NE1–NE2、NE3–NE4、NE5–NE6 为三横；NE1–NE3–NE5、NE2–NE4–NE6 为两竖。
//   三条流分别从 NE3、NE5、NE6 进入，汇聚到 NE1 的服务器，路径跳数不同：
//     切片1（client1→NE5→NE3→NE1）：2 跳
//     切片2（client2→NE6→NE4→NE2→NE1）：3 跳
//     切片3（client3→NE3→NE1）：1 跳
//
// 注意：六节点 L2 环网存在物理环路。本场景用 GlobalArp 消除 ARP 广播，
//       避免广播风暴；但 L2 未知单播仍可能泛洪，运行结果需检查是否有重复投递。
//
package nasctime.simulations.demos.t2_ladder;

import inet.networks.base.TsnNetworkBase;
import inet.node.ethernet.EthernetLink;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;

network T2LadderNetwork extends TsnNetworkBase
{
    submodules:
        client1: TsnDevice {
            @display("p=120,480");
        }
        client2: TsnDevice {
            @display("p=760,480");
        }
        client3: TsnDevice {
            @display("p=120,320");
        }

        NE1: TsnSwitch {
            @display("p=620,160");
        }
        NE2: TsnSwitch {
            @display("p=760,260");
        }
        NE3: TsnSwitch {
            @display("p=300,320");
        }
        NE4: TsnSwitch {
            @display("p=560,360");
        }
        NE5: TsnSwitch {
            @display("p=300,480");
        }
        NE6: TsnSwitch {
            @display("p=560,480");
        }

        server: TsnDevice {
            @display("p=620,60");
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

        // 接入
        client1.ethg++ <--> EthernetLink <--> NE5.ethg++;
        client2.ethg++ <--> EthernetLink <--> NE6.ethg++;
        client3.ethg++ <--> EthernetLink <--> NE3.ethg++;
        server.ethg++ <--> EthernetLink <--> NE1.ethg++;
}
