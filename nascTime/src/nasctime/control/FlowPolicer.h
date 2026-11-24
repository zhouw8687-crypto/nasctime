#ifndef NASCTIME_FLOWPOLICER_H
#define NASCTIME_FLOWPOLICER_H

#include <cstdint>

#include "inet/common/packet/PacketFilter.h"
#include <omnetpp.h>
#include "inet/queueing/common/TokenBucket.h"

namespace nasctime::control {

class FlowPolicer : public omnetpp::cSimpleModule
{
  public:
    struct Counters {
        std::int64_t admittedPackets = 0;
        std::int64_t droppedPackets = 0;
        std::int64_t admittedBytes = 0;
        std::int64_t droppedBytes = 0;
    };

    static constexpr int maxRateBps = 1'000'000'000;
    const Counters& getCounters() const { return counters; }
    const char *getFlowId() const { return par("flowId").stringValue(); }
    int getRateBps() const { return rateBps; }
    void setRateBps(int newRateBps);

  protected:
    inet::PacketFilter packetFilter;
    inet::queueing::TokenBucket bucket;
    Counters counters;
    int rateBps = 0;

    void initialize() override;
    void finish() override;
    void handleMessage(omnetpp::cMessage *message) override;
};

} // namespace nasctime::control

#endif
