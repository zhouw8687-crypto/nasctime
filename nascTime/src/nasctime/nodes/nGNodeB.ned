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

package nasctime.nodes;

import simu5g.nodes.gNodeB;
import inet.linklayer.ppp.PppInterface;
import inet.common.MessageDispatcher;
import simu5g.corenetwork.gtp.GtpUser;
import simu5g.corenetwork.trafficFlowFilter.TrafficFlowFilter;

module NGNodeB extends gNodeB
{
    parameters:
        bool frerInterSession = default(false);

    gates:
        inout ppp2 @loose; // second N3 link for FRER inter-session / NR-DC

    submodules:
        pppIf2: PppInterface if frerInterSession {
            @display("p=824,600");
        }

    connections allowunconnected:
         pppIf2.phys <--> ppp2 if frerInterSession;
         pppIf2.upperLayerOut --> nl.in++ if frerInterSession;
         pppIf2.upperLayerIn <-- nl.out++ if frerInterSession;
}
