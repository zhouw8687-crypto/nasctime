package nasctime.qos;

import inet.queueing.contract.ITrafficConditioner;
import inet.queueing.marker.ContentBasedTagger;

// Map the outer IPv4 DS field to local PCP requests before the egress queue.
// Other code points and non-IPv4 packets use the classifier's best-effort
// default. No VLAN header is inserted on the routed Ethernet segments.
module DscpToPcpMarker like ITrafficConditioner
{
    gates:
        input in;
        output out;
    submodules:
        ef: ContentBasedTagger {
            packetFilter = default(expr(has(ipv4) && ((ipv4[0].typeOfService >> 2) == 46)));
            pcp = default(5);
        }
        af41: ContentBasedTagger {
            packetFilter = default(expr(has(ipv4) && ((ipv4[0].typeOfService >> 2) == 34)));
            pcp = default(4);
        }
    connections:
        in --> ef.in;
        ef.out --> af41.in;
        af41.out --> out;
}
