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

package nasctime.nodes.DsTt;

import inet.linklayer.ethernet.basic.EthernetInterface;
import simu5g.nodes.NrUe;

module NRUeDsTt extends NrUe
{
    parameters:
        @display("i=device/pocketpc;bgb=858,750");
        numEthInterfaces = default(1);
        eth[*].typename = default("EthernetInterface");
        encap.typename = default("EthernetEncapsulation");

    gates:
        inout ethg @labels(EthernetSignal);

    connections:
        ethg <--> eth[0].phys;
}
