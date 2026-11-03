//
// SystemTestWireless —— 整体模型 + 无线接入（正确接法）
//
// 关键：UPF 是 GTP 隧道端点
//   - upf.pppg   = N3 侧，对端必须是 gNB（GTP 封装）
//   - upf.dnPppg = N6 侧，普通 IP，接数据网/TSN 侧
// 因此 TSN 有线接入必须挂在**核心侧**，不能挂在 N3 传输环上。
// （第一版把 TSN 接到 lsr 环再进 upf.pppg，结果 upf.ipv4.lp 分发失败）
//
// 拓扑：
//
//   [N3 承载域]   gNB ── lsr2 ══ lsr1 ══ lsr3 ── upf.pppg
//                                                    │
//   [N6 / 核心]                               upf.dnPppg
//                                                    │
//   [TSN 有线接入] src ─ pe1 ─ pe2 ─ pe3 ─ edgeRouter ─ coreRouter ── server
//
package nasctime.simulations.demos.system_test;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
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

network SystemTestWireless
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

        // ===== TSN 有线接入（L2，链式）=====
        src: TsnDevice {
            @display("p=140,520");
        }
        pe1: TsnSwitch {
            @display("p=280,520");
        }
        pe2: TsnSwitch {
            @display("p=420,520");
        }
        pe3: TsnSwitch {
            @display("p=560,520");
        }
        edgeRouter: Router {
            @display("p=700,520");
        }

        // ===== N3 承载域（三角环）=====
        lsr1: Router {
            @display("p=820,300");
        }
        lsr2: Router {
            @display("p=960,220");
        }
        lsr3: Router {
            @display("p=960,400");
        }

        // ===== 无线接入 =====
        gnb: gNodeB {
            @display("p=1100,160;is=vl");
        }
        ue[1]: NrUe {
            @display("p=1240,160");
        }

        // ===== 核心 / N6 =====
        upf: Upf {
            @display("p=1100,300");
        }
        coreRouter: Router {
            @display("p=1180,420");
        }
        server: StandardHost {
            @display("p=1320,420");
        }

    connections:
        // TSN 接入：链式
        src.ethg++ <--> { datarate = 10Gbps; delay = 10us; } <--> pe1.ethg++;
        pe1.ethg++ <--> { datarate = 10Gbps; delay = 10us; } <--> pe2.ethg++;
        pe2.ethg++ <--> { datarate = 10Gbps; delay = 10us; } <--> pe3.ethg++;

        // TSN → 核心侧（N6）
        pe3.ethg++ <--> { datarate = 10Gbps; delay = 10us; } <--> edgeRouter.ethg++;
        edgeRouter.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> coreRouter.pppg++;

        // N3 承载域：三角环
        lsr1.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> lsr2.pppg++;
        lsr2.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> lsr3.pppg++;
        lsr3.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> lsr1.pppg++;

        // 无线接入：gNB 的 N3 挂到承载域
        lsr2.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> gnb.ppp;

        // 核心：UPF N3 挂承载域，N6 接核心路由
        lsr3.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        upf.dnPppg <--> { datarate = 10Gbps; delay = 10us; } <--> coreRouter.pppg++;

        // 核心路由 → 数据网
        coreRouter.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> server.pppg++;
}
