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

#include "nasctime/nodes/NwTt/GptpSideband.h"

Define_Module(GptpSideband);

void GptpSideband::initialize()
{
    sidebandDelay = par("sidebandDelay");
}

void GptpSideband::handleMessage(cMessage *msg)
{
    int gateId = msg->getArrivalGateId();

    if (gateId == gate("nwttIn")->getId()) {
        // NW-TT → DS-TT: add 5GS transit delay
        sendDelayed(msg, sidebandDelay, "dsttOut");
    }
    else if (gateId == gate("dsttIn")->getId()) {
        // DS-TT → NW-TT: add 5GS transit delay (reverse)
        sendDelayed(msg, sidebandDelay, "nwttOut");
    }
    else {
        delete msg;
    }
}
