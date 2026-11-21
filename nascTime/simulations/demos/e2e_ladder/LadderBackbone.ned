package nasctime.simulations.demos.e2e_ladder;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.ethernet.EthernetLink;
import inet.node.inet.Router;

// Shared routed backbone of the reference ladder. Ethernet gate order is
// retained for compatibility with ProjectBookLadder's existing results.
network LadderBackbone
{
    parameters:
        double spanLength @unit(m) = default(10m);

    submodules:
        configurator: Ipv4NetworkConfigurator {
            @display("p=60,60");
        }
        NE1: Router {
            @display("p=420,220");
        }
        NE2: Router {
            @display("p=620,220");
        }
        NE3: Router {
            @display("p=420,360");
        }
        NE4: Router {
            @display("p=620,360");
        }
        NE5: Router {
            @display("p=420,500");
        }
        NE6: Router {
            @display("p=620,500");
        }

    connections:
        NE1.ethg++ <--> EthernetLink { length = parent.spanLength; } <--> NE2.ethg++;
        NE3.ethg++ <--> EthernetLink { length = parent.spanLength; } <--> NE4.ethg++;
        NE5.ethg++ <--> EthernetLink { length = parent.spanLength; } <--> NE6.ethg++;
        NE1.ethg++ <--> EthernetLink { length = parent.spanLength; } <--> NE3.ethg++;
        NE3.ethg++ <--> EthernetLink { length = parent.spanLength; } <--> NE5.ethg++;
        NE2.ethg++ <--> EthernetLink { length = parent.spanLength; } <--> NE4.ethg++;
        NE4.ethg++ <--> EthernetLink { length = parent.spanLength; } <--> NE6.ethg++;
}
