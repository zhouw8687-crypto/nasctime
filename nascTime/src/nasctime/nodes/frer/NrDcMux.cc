////
//                  nascTime
//
// Authors: Mohamed Seliem (University College Cork)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

#include "nasctime/nodes/frer/NrDcMux.h"

Define_Module(NrDcMux);

void NrDcMux::initialize()
{
    upperInId     = gate("upper$i")->getId();
    upperOutId    = gate("upper$o")->getId();
    primaryInId   = gate("primary$i")->getId();
    primaryOutId  = gate("primary$o")->getId();
    secondaryInId = gate("secondary$i")->getId();
    secondaryOutId= gate("secondary$o")->getId();
}

void NrDcMux::handleMessage(cMessage *msg)
{
    int gateId = msg->getArrivalGateId();

    if (gateId == primaryInId || gateId == secondaryInId) {
        // Downlink: forward from either NR stack to ip2nic
        send(msg, upperOutId);
    }
    else if (gateId == upperInId) {
        // Uplink: route to primary NR stack
        send(msg, primaryOutId);
    }
    else {
        EV_WARN << "NrDcMux: unexpected gate, dropping" << endl;
        delete msg;
    }
}
