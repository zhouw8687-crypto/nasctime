//
// ProjectBookNetwork —— 按项目书搭的端到端环境
//
// 结构（就是项目书描述的那张图）：
//
//   [无线接入]  ue ⇢ gNB ──N3──┐
//                                ├── [承载: pe1 ══ pe2 ══ pe3，带 Qbv] ── [核心: upf ── server]
//   [有线终端]  host ── 边缘 ───┘
//
// 说明：
//   - 承载用 `TsnSwitch`（L2 桥 + 802.1Qbv 门控能力），这是 PE 的"门控"那一半；
//   - gNB 的 N3 是 IP/PPP 接口，不能直接进 L2 桥，所以先进一台 `n3Router`（N3 接入点）；
//   - 核心侧：`upf` 是真 Simu5G UPF，`pppg` 收 gNB 的 GTP，`dnPppg` 接 `coreRouter`；
//   - 有线终端的流走纯 IP（不经过 GTP），所以直接经 PE 到 coreRouter → server；
//   - 本网络不包含任何 nascTime 的 5G-TSN 桥假设（没有 NW-TT/DS-TT）。
//
package nasctime.simulations.demos.e2e_test;

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

network ProjectBookNetwork
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

        // ===== 无线接入 =====
        gnb: gNodeB {
            @display("p=140,120;is=vl");
        }
        ue[1]: NrUe {
            @display("p=280,120");
        }

        // ===== 有线接入（终端 + 边缘）=====
        host: TsnDevice {
            @display("p=140,420");
        }
        edge: TsnSwitch {
            @display("p=280,420");
        }

        // ===== 承载（PE，带 Qbv）=====
        n3Router: Router {
            @display("p=420,120");
        }
        pe1: TsnSwitch {
            @display("p=560,300");
        }
        pe2: TsnSwitch {
            @display("p=720,300");
        }
        pe3: TsnSwitch {
            @display("p=880,300");
        }

        // ===== 核心 =====
        coreRouter: Router {
            @display("p=1040,300");
        }
        upf: Upf {
            @display("p=1040,160");
        }
        server: StandardHost {
            @display("p=1200,300");
        }

    connections:
        // 无线：UE ↔ gNB 是空口，不需要连线；gNB 的 N3 经 n3Router 进承载
        gnb.ppp <--> { datarate = 10Gbps; delay = 10us; } <--> n3Router.pppg++;
        n3Router.ethg++ <--> EthernetLink <--> pe1.ethg++;

        // 有线：终端 → 边缘 → 承载
        host.ethg++ <--> EthernetLink <--> edge.ethg++;
        edge.ethg++ <--> EthernetLink <--> pe1.ethg++;

        // 承载：PE 链
        pe1.ethg++ <--> EthernetLink <--> pe2.ethg++;
        pe2.ethg++ <--> EthernetLink <--> pe3.ethg++;

        // 承载 → 核心（L2 桥接域在这里结束）
        pe3.ethg++ <--> EthernetLink <--> coreRouter.ethg++;

        // 核心：UPF 的 N3/N6
        coreRouter.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        upf.dnPppg <--> { datarate = 10Gbps; delay = 10us; } <--> coreRouter.pppg++;
        coreRouter.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> server.pppg++;
}
