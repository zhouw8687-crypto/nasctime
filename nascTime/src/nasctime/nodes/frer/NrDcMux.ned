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

package nasctime.nodes.frer;

simple NrDcMux
{
    parameters:
        @display("i=block/dispatch");
    gates:
        inout upper;       // to ip2nic.stackNic
        inout primary;     // to sdap  (NR stack 1 / primary cell group)
        inout secondary;   // to sdap2 (NR stack 2 / secondary cell group)
}
