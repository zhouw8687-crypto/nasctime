//
// NwTtTestNetwork — Test topology for the NW-TT module
//
// Based on Simu5G's simulations/NR/standalone topology.
// Replaces the external StandardHost + Router with TsnDevice + TsnSwitch + NwTt.
//
// Topology:
//   TsnDevice ──Eth1G──► TsnSwitch ──Eth1G──► NwTt ──Eth10G──► UPF ──Eth10G──► gNB ~~NR~~► UE
//

package nasctime.tests.nwtt_test;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.networklayer.ipv4.RoutingTableRecorder;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;
import ned.DatarateChannel;

import simu5g.world.radio.LteChannelControl;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.nodes.Upf;
import simu5g.nodes.gNodeB;
import simu5g.nodes.NrUe;
import nasctime.nodes.NwTt.NwTt;

network NwTtTestNetwork
{
    parameters:
        @display("bgb=1200,500");

    types:
        channel Eth1G extends DatarateChannel {
            datarate = 1Gbps;
            delay = 0.1us;
        }
        channel Eth10G extends DatarateChannel {
            datarate = 10Gbps;
            delay = 0.1us;
        }

    submodules:
        // --- Infrastructure (standard Simu5G) ---
        channelControl: LteChannelControl {
            @display("p=50,25;is=s");
        }
        routingRecorder: RoutingTableRecorder {
            @display("p=50,75;is=s");
        }
        configurator: Ipv4NetworkConfigurator {
            @display("p=50,125;is=s");
            config = xmldoc("nwtt_ip_config.xml");
        }
        binder: Binder {
            @display("p=50,175;is=s");
        }
        carrierAggregation: CarrierAggregation {
            @display("p=50,225;is=s");
        }

        // --- TSN domain ---
        tsnDevice: TsnDevice {
            @display("p=100,350");
        }
        tsnSwitch: TsnSwitch {
            @display("p=280,350");
        }

        // --- NW-TT (new module) ---
        nwTt: NwTt {
            @display("p=460,350");
            ueAddress = "ue[0]";
            localAddress = "nwTt";
        }

        // --- 5G Core & RAN ---
        upf: Upf {
            @display("p=640,350");
        }
        gnb: gNodeB {
            @display("p=780,350;is=vl");
        }
        ue[1]: NrUe {
            @display("p=900,350");
        }

    connections:
        // TSN device → TSN switch
        tsnDevice.ethg++ <--> Eth1G <--> tsnSwitch.ethg++;

        // TSN switch → NW-TT (Ethernet side)
        tsnSwitch.ethg++ <--> Eth1G <--> nwTt.tsnEthg;

        // NW-TT → UPF (replaces the usual router → upf.filterGate link)
        nwTt.filterGate <--> Eth10G <--> upf.dnPppg;

        // UPF → gNB (standard Simu5G wiring)
        upf.pppg++ <--> Eth10G <--> gnb.ppp;
}
