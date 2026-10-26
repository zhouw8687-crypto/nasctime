//
//                  nascTime
//
// Authors: Mohamed Seliem (University College Cork)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

package nasctime.simulations.demos.multi_endpoint_test;

import nasctime.nodes.NwTt.NwTt;
import nasctime.nodes.NwTt.GptpSideband;
import nasctime.nodes.DsTt.DsTt;
import simu5g.nodes.gNodeB;
import nasctime.nodes.DsTt.NRUeDsTt;
import simu5g.nodes.Upf;
import simu5g.world.radio.LteChannelControl;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.networklayer.ipv4.RoutingTableRecorder;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;
import ned.DatarateChannel;

import nasctime.nodes.TsnAf.TsnAf;
import nasctime.nodes.TsnAf.StaticBmca;

network MultiEndpointNetwork
{
    parameters:
        int numEndpoints = default(3);
        @display("bgb=1600,700");

    types:
        channel Eth1G extends DatarateChannel
        {
            datarate = 1Gbps;
            delay = 0.1us;
        }
        channel Eth10G extends DatarateChannel
        {
            datarate = 10Gbps;
            delay = 0.1us;
        }

    submodules:
        channelControl: LteChannelControl {
            @display("p=50,25;is=s");
        }
        routingRecorder: RoutingTableRecorder {
            @display("p=50,75;is=s");
        }
        configurator: Ipv4NetworkConfigurator {
            @display("p=50,125;is=s");
            config = xmldoc("multi_ip_config.xml");
        }
        binder: Binder {
            @display("p=50,175;is=s");
        }
        carrierAggregation: CarrierAggregation {
            @display("p=50,225;is=s");
        }

        // Shared infrastructure
        tsnDeviceA: TsnDevice {
            @display("p=100,350");
        }
        tsnSwitch: TsnSwitch {
            @display("p=250,350");
        }
        nwTt: NwTt {
            @display("p=420,350");
            ueAddress = "ue[0]";
            localAddress = "nwTt";
        }
        upf: Upf {
            @display("p=600,350");
        }
        gnb: gNodeB {
            @display("p=780,350;is=vl");
        }

        // Per-endpoint: UE + DS-TT + TSN Device B
        ue[numEndpoints]: NRUeDsTt {
            @display("p=960,350");
        }
        dsTt[numEndpoints]: DsTt {
            @display("p=1120,250,c,150");
        }
        tsnDeviceB[numEndpoints]: TsnDevice {
            @display("p=1350,250,c,150");
        }
        tsnAf: TsnAf {
            @display("p=50,275;is=s");
            cncConfig = xmldoc("cnc_config.xml");
        }
        staticBmca: StaticBmca {
            @display("p=50,325;is=s");
        }

        // gPTP sideband (connects NW-TT to first DS-TT only for now)
        gptpSideband: GptpSideband {
            @display("p=770,150");
        }

    connections:
        // TSN domain A (shared)
        tsnDeviceA.ethg++ <--> Eth1G <--> tsnSwitch.ethg++;
        tsnSwitch.ethg++ <--> Eth1G <--> nwTt.tsnEthg;
        nwTt.filterGate <--> Eth10G <--> upf.dnPppg;
        upf.pppg++ <--> Eth10G <--> gnb.ppp;

        // Per-endpoint connections
        for i=0..numEndpoints-1 {
            ue[i].ethg <--> Eth1G <--> dsTt[i].ueEthg;
            dsTt[i].tsnEthg <--> Eth1G <--> tsnDeviceB[i].ethg++;
        }

        // gPTP sideband (to first DS-TT)
        nwTt.gptpSidebandOut --> gptpSideband.nwttIn;
        gptpSideband.dsttOut --> dsTt[0].gptpSidebandIn;
}
