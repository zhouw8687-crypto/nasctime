#ifndef NASCTIME_FLOWPOLICER_H
#define NASCTIME_FLOWPOLICER_H

#include <cstdint>
#include <vector>

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
    int getCapacityBps() const { return capacityBps; }
    int getEnforcedRateBps() const { return enforcedRateBps; }
    void setRateBps(int newRateBps);
    ~FlowPolicer() override;

  protected:
    inet::PacketFilter packetFilter;
    inet::queueing::TokenBucket bucket;
    Counters counters;
    int rateBps = 0;

    void initialize() override;
    void finish() override;
    void handleMessage(omnetpp::cMessage *message) override;

  private:
    struct CapacityChange {
        omnetpp::simtime_t time;
        int bps;
    };

    int capacityBps = maxRateBps;
    int enforcedRateBps = 0;
    std::vector<CapacityChange> capacitySchedule;
    size_t nextChange = 0;
    omnetpp::cMessage *capacityTimer = nullptr;
    bool recordAdmissionVectors = false;
    omnetpp::cOutVector admittedBytes{"admissionAdmittedPacketBytes"};
    omnetpp::cOutVector droppedBytes{"admissionDroppedPacketBytes"};

    omnetpp::cOutVector configuredRate{"admissionConfiguredBps"};
    omnetpp::cOutVector capacityRate{"admissionCapacityBps"};
    omnetpp::cOutVector enforcedRate{"admissionEnforcedBps"};

    void recordRates();
    void updateEnforcedRate();
    void loadCapacitySchedule();
};

} // namespace nasctime::control

#endif