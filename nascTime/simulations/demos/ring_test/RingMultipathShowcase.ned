//
// RingMultipathShowcase —— 三角环双路径最小拓扑
//
// 结构（照 INET 的 AutomaticMultipathConfigurationShowcase 改）：
//
//         pe1 ────────── pe3
//          │ ╲            │
//          │  ╲           │
//          │   ╲          │
//       source  pe2 ──────┘
//
//   实际连接：source-pe1, pe1-pe3, pe1-pe2, pe2-pe3, pe3-destination
//
// 两条边不相交路径（由 ini 里的 streamRedundancyConfigurator 显式给出）：
//   A: source → pe1 → pe3 → destination
//   B: source → pe1 → pe2 → pe3 → destination
//
// 只用于验证：FRER 在三角环上能否建立两条路径、报文是否送达、
// 端到端时延是否可观测。不含 5G、不含门控。
//
package nasctime.simulations.demos.ring_test;

import inet.networks.base.TsnNetworkBase;
import inet.node.ethernet.EthernetLink;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;

network RingMultipathShowcase extends TsnNetworkBase
{
    submodules:
        source: TsnDevice {
            @display("p=200,300");
        }
        pe1: TsnSwitch {
            @display("p=400,300");
        }
        pe2: TsnSwitch {
            @display("p=600,420");
        }
        pe3: TsnSwitch {
            @display("p=800,300");
        }
        destination: TsnDevice {
            @display("p=1000,300");
        }
    connections:
        source.ethg++ <--> EthernetLink <--> pe1.ethg++;
        pe1.ethg++ <--> EthernetLink <--> pe3.ethg++;
        pe1.ethg++ <--> EthernetLink <--> pe2.ethg++;
        pe2.ethg++ <--> EthernetLink <--> pe3.ethg++;
        pe3.ethg++ <--> EthernetLink <--> destination.ethg++;
}
