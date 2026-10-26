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

#ifndef __SIMU5G_1_4_1_SDAP_TSNAF_H_
#define __SIMU5G_1_4_1_SDAP_TSNAF_H_

#include <omnetpp.h>
#include <inet/common/InitStages.h>
#include <map>
#include <vector>

using namespace omnetpp;
using namespace inet;

struct StreamReservation {
    int streamId;
    int pcp;
    int qfi;
    int drbIndex;
    double maxLatencyMs;
    double reservedBandwidthKbps;
};

struct GateControlEntry {
    simtime_t startTime;
    simtime_t duration;
    uint8_t gateStates;  // bitmask: bit i = gate i open
};

class TsnAf : public cSimpleModule, public cListener
{
  protected:
    // Bridge capability cache
    double portSpeedBps;
    int numTrafficClasses;
    std::vector<int> pcpToQfi;

    // Bridge delay tracking (from G3 signals)
    simtime_t delayMin = SIMTIME_MAX;
    simtime_t delayMax = SIMTIME_ZERO;
    simtime_t delaySum = SIMTIME_ZERO;
    long delaySamples = 0;

    // Stream reservations (from CNC config)
    std::vector<StreamReservation> streamReservations;

    // TAS gate control list (from CNC config)
    std::vector<GateControlEntry> gateControlList;
    simtime_t gateCycleTime;

    // Signals
    simsignal_t bridgeDelayUpdatedSignal;
    simsignal_t streamConfiguredSignal;
    simsignal_t qosViolationSignal;

    // Module references
    cModule *nwTtModule = nullptr;
    cModule *dsTtModule = nullptr;
    cModule *gnbModule = nullptr;

  protected:
    virtual void initialize(int stage) override;
    virtual int numInitStages() const override { return NUM_INIT_STAGES; }
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

    // cListener — subscribes to DS-TT residence time signal
    virtual void receiveSignal(cComponent *source, simsignal_t signalID,
                               const simtime_t& t, cObject *details) override;

    // CNC config parsing
    void loadCncConfig(cXMLElement *xmlConfig);
    void parseStreamReservations(cXMLElement *streamsElem);
    void parseGateControlList(cXMLElement *tasElem);

    // Apply configurations
    void applyStreamReservations();
    void applyGateControlList();

  public:
    // API for other modules to query bridge capabilities
    double getPortSpeedBps() const { return portSpeedBps; }
    int getNumTrafficClasses() const { return numTrafficClasses; }
    int getQfiForPcp(int pcp) const;
    int getPcpForQfi(int qfi) const;
    simtime_t getBridgeDelayMin() const { return delayMin; }
    simtime_t getBridgeDelayMax() const { return delayMax; }
    simtime_t getBridgeDelayAvg() const;
    const std::vector<StreamReservation>& getStreamReservations() const { return streamReservations; }
};

#endif
