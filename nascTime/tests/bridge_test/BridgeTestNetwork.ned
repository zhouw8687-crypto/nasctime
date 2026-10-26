//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Lesser General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Lesser General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public License
// along with this program.  If not, see http://www.gnu.org/licenses/.
//

package nasctime.tests.bridge_test;

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
import nasctime.nodes.DsTt.NRUeDsTt;
import nasctime.nodes.NwTt.NwTt;
import nasctime.nodes.DsTt.DsTt;

//
// BridgeTestNetwork — Full 5G-TSN bridge
//
// TSN Device A → TsnSwitch → NW-TT → UPF → gNB ~~NR~~ UE ←→ DS-TT ←→ TSN Device B
//
// The 5GS (NW-TT to DS-TT) acts as a single logical TSN bridge.
//
network BridgeTestNetwork
{
    parameters:
        @display("bgb=1400,500");

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
        channelControl: LteChannelControl {
            @display("p=50,25;is=s");
        }
        routingRecorder: RoutingTableRecorder {
            @display("p=50,75;is=s");
        }
        configurator: Ipv4NetworkConfigurator {
            @display("p=50,125;is=s");
            config = xmldoc("bridge_ip_config.xml");
        }
        binder: Binder {
            @display("p=50,175;is=s");
        }
        carrierAggregation: CarrierAggregation {
            @display("p=50,225;is=s");
        }

        // --- TSN domain A (ingress) ---
        tsnDeviceA: TsnDevice {
            @display("p=100,350");
        }
        tsnSwitch: TsnSwitch {
            @display("p=250,350");
        }

        // --- NW-TT (ingress bridge port) ---
        nwTt: NwTt {
            @display("p=420,350");
            ueAddress = "ue[0]";
            localAddress = "nwTt";
        }

        // --- 5G Core & RAN ---
        upf: Upf {
            @display("p=600,350");
        }
        gnb: gNodeB {
            @display("p=780,350;is=vl");
        }
        ue[1]: NRUeDsTt {
            @display("p=890,350");
        }

        // --- DS-TT (egress bridge port) ---
        dsTt: DsTt {
            @display("p=1120,350");
        }

        // --- TSN domain B (egress) ---
        tsnDeviceB: TsnDevice {
            @display("p=1280,350");
        }

    connections:
        // TSN domain A
        tsnDeviceA.ethg++ <--> Eth1G <--> tsnSwitch.ethg++;
        tsnSwitch.ethg++ <--> Eth1G <--> nwTt.tsnEthg;

        // NW-TT → UPF
        nwTt.filterGate <--> Eth10G <--> upf.dnPppg;

        // UPF → gNB
        upf.pppg++ <--> Eth10G <--> gnb.ppp;

        // UE ← Ethernet → DS-TT (UE's eth[0] connects to DS-TT)
        ue[0].ethg <--> Eth1G <--> dsTt.ueEthg;

        // DS-TT ← Ethernet → TSN Device B (direct, no switch)
        dsTt.tsnEthg <--> Eth1G <--> tsnDeviceB.ethg++;
}
