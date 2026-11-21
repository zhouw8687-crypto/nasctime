package nasctime.simulations.demos.e2e_ladder;

import inet.common.scenario.ScenarioManager;
import inet.node.inet.StandardHost;

// Wired fixtures occupy the two gNB positions and the dual-homed 5GC
// position. Their UDP applications measure the routed transport in isolation.
network TransportLadder extends LadderBackbone
{
    submodules:
        scenarioManager: ScenarioManager {
            @display("p=60,120");
        }
        core: StandardHost {
            @display("p=520,120");
        }
        access1: StandardHost {
            @display("p=420,630");
        }
        access2: StandardHost {
            @display("p=620,630");
        }

    connections:
        NE1.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> core.pppg++;
        NE2.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> core.pppg++;
        NE5.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> access1.pppg++;
        NE6.pppg++ <--> { datarate = 10Gbps; delay = 10us; } <--> access2.pppg++;
}
