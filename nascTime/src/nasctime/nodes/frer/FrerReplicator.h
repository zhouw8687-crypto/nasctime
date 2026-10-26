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

#ifndef __SIMU5G_1_4_3_FRER_FRERREPLICATOR_H_
#define __SIMU5G_1_4_3_FRER_FRERREPLICATOR_H_

#include <omnetpp.h>
#include <map>
#include <set>

#include "nasctime/nodes/frer/IFrerTransportBinding.h"
#include "inet/common/packet/Packet.h"
#include "inet/common/InitStages.h"

using namespace omnetpp;
using namespace inet;

class FrerReplicator : public cSimpleModule
{
  protected:
    // --- Configuration ---
    std::set<int> frerStreamDscpSet;   // DSCPs eligible for FRER
    int replicaDscp;
    std::string transportBindingType;
    bool ethernetFramed = false;

    // --- Transport binding (owned) ---
    IFrerTransportBinding *transportBinding = nullptr;

    // --- Per-stream 16-bit sequence counters ---
    // Key: DSCP value (used as stream identifier)
    std::map<int, uint16_t> sequenceCounters;

    // --- Gate IDs ---
    int inGateId;
    int outGateId;

    // --- Signals ---
    simsignal_t replicatedFramesSignal;
    simsignal_t primarySentSignal;
    simsignal_t replicaSentSignal;
    simsignal_t passedThroughSignal;

    // --- Counters ---
    long numReplicated    = 0;
    long numPrimarySent   = 0;
    long numReplicaSent   = 0;
    long numPassedThrough = 0;

  protected:
    virtual int numInitStages() const override { return inet::NUM_INIT_STAGES; }
    virtual void initialize(int stage) override;
    virtual void handleMessage(cMessage *msg) override;

    void initializeTransportBinding();
    virtual void finish() override;

    /** Stream identification (802.1CB §6): is this packet FRER-eligible? */
    virtual bool isFrerEligible(Packet *pkt, int &dscp);

    /** Sequence generation (802.1CB §7.4): get next seq# for this stream. */
    virtual uint16_t nextSequenceNumber(int streamId);

    /** Stream splitting (802.1CB §7.7): replicate and send both copies. */
    virtual void replicateAndSend(Packet *pkt, int dscp);
};

#endif
