package nasctime.simulations.demos.e2e_ladder;

import inet.node.inet.StandardHost;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.nodes.NrUe;
import simu5g.nodes.Upf;
import simu5g.nodes.gNodeB;
import simu5g.world.radio.LteChannelControl;

// NR standalone: two gNBs attach to NE5/NE6 via N3. The single 5GC
// anchor is dual-homed to NE1/NE2; its N6 interface faces the data server.
network ProjectBookLadder extends LadderBackbone
{
    parameters:
        int numUe = default(2);

    submodules:
        binder: Binder {
            @display("p=60,120;is=s");
        }
        channelControl: LteChannelControl {
            @display("p=60,180;is=s");
        }
        carrierAggregation: CarrierAggregation {
            @display("p=60,240;is=s");
        }
        upf: Upf {
            @display("p=520,120");
        }
        server: StandardHost {
            @display("p=520,30");
        }
        gnb1: gNodeB {
            @display("p=400,740;is=vl");
        }
        gnb2: gNodeB {
            @display("p=640,740;is=vl");
        }
        ue[numUe]: NrUe {
            @display("p=520,840");
        }

    connections:
        NE1.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        NE2.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> upf.pppg++;
        upf.dnPppg <--> { datarate = 10Gbps; delay = 10us; } <--> server.pppg++;
        NE5.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> gnb1.ppp;
        NE6.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> gnb2.ppp;
}
