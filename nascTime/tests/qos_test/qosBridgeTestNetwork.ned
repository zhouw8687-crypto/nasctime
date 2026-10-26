

package nasctime.tests.qos_test;

import nasctime.nodes.NwTt.NwTt;
import nasctime.nodes.NwTt.GptpSideband;
import nasctime.nodes.DsTt.DsTt;
import simu5g.nodes.gNodeB;
import nasctime.nodes.DsTt.NRUeDsTt;
import nasctime.nodes.TsnAf.TsnAf;
import nasctime.nodes.TsnAf.StaticBmca;
import simu5g.nodes.Upf;
import simu5g.world.radio.LteChannelControl;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.networklayer.ipv4.RoutingTableRecorder;
import inet.node.tsn.TsnDevice;
import inet.node.tsn.TsnSwitch;
import ned.DatarateChannel;

network qosBridgeTestNetwork
{
    parameters:
        @display("bgb=1500,600");

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
        channelControl: LteChannelControl { @display("p=50,25;is=s"); }
        routingRecorder: RoutingTableRecorder { @display("p=50,75;is=s"); }
        configurator: Ipv4NetworkConfigurator {
            @display("p=50,125;is=s");
            config = xmldoc("bridge_ip_config.xml");
        }
        binder: Binder { @display("p=50,175;is=s"); }
        carrierAggregation: CarrierAggregation { @display("p=50,225;is=s"); }

        tsnAf: TsnAf {
            @display("p=50,275;is=s");
            cncConfig = xmldoc("cnc_config.xml");
        }
        tsnDeviceA: TsnDevice { @display("p=100,350"); }
        tsnSwitch: TsnSwitch { @display("p=250,350"); }
        nwTt: NwTt {
            @display("p=420,350");
            ueAddress = "ue[0]";
            localAddress = "nwTt";
        }
        upf: Upf { @display("p=600,350"); }
        gnb: gNodeB { @display("p=780,350;is=vl"); }
        ue[1]: NRUeDsTt{ @display("p=920,350"); }
        dsTt: DsTt { @display("p=1120,350"); }
        tsnDeviceB: TsnDevice { @display("p=1300,350"); }

        // gPTP sideband — carries gPTP messages across the 5GS
        gptpSideband: GptpSideband {
            @display("p=770,150");
        }
        staticBmca: StaticBmca {
            @display("p=50,325;is=s");
        }

    connections:
        tsnDeviceA.ethg++ <--> Eth1G <--> tsnSwitch.ethg++;
        tsnSwitch.ethg++ <--> Eth1G <--> nwTt.tsnEthg;
        nwTt.filterGate <--> Eth10G <--> upf.dnPppg;
        upf.pppg++ <--> Eth10G <--> gnb.ppp;
        ue[0].ethg <--> Eth1G <--> dsTt.ueEthg;
        dsTt.tsnEthg <--> Eth1G <--> tsnDeviceB.ethg++;

        // gPTP sideband connections
        nwTt.gptpSidebandOut --> gptpSideband.nwttIn;
        gptpSideband.dsttOut --> dsTt.gptpSidebandIn;
}