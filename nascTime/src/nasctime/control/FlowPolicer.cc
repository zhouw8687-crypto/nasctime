#include <algorithm>

#include "nasctime/control/FlowPolicer.h"

namespace nasctime::control {

using namespace omnetpp;

Define_Module(FlowPolicer);

FlowPolicer::~FlowPolicer()
{
    cancelAndDelete(capacityTimer);
}

void FlowPolicer::loadCapacitySchedule()
{
    const auto *schedule = check_and_cast<const cValueArray *>(par("capacitySchedule").objectValue());
    simtime_t previous = SIMTIME_ZERO;
    for (int i = 0; i < schedule->size(); ++i) {
        const auto *entry = check_and_cast<const cValueMap *>(schedule->get(i).objectValue());
        const auto atMs = entry->get("atMs").intValue();
        const auto bps = entry->get("bps").intValue();
        if (atMs <= 0 || bps < 0 || bps > maxRateBps)
            throw cRuntimeError("Invalid capacity schedule entry %d", i);
        const simtime_t time = SimTime(atMs, SIMTIME_MS);
        if (time <= previous)
            throw cRuntimeError("Capacity schedule times must be strictly increasing");
        capacitySchedule.push_back({time, static_cast<int>(bps)});
        previous = time;
    }
    if (!capacitySchedule.empty()) {
        capacityTimer = new cMessage("videoAdmissionCapacity");
        // Apply a scenario capacity change before packet arrivals and route-controller sampling.
        capacityTimer->setSchedulingPriority(-1);
        scheduleAt(capacitySchedule.front().time, capacityTimer);
    }
}

void FlowPolicer::initialize()
{
    const auto initialRate = par("initialRate").intValue();
    const auto initialCapacity = par("initialCapacity").intValue();
    const auto burstBytes = par("burstSize").intValue();
    if (initialRate < 1 || initialRate > maxRateBps || burstBytes <= 0)
        throw cRuntimeError("Invalid initial policing rate or burst size");
    if (initialCapacity < 0 || initialCapacity > maxRateBps)
        throw cRuntimeError("Invalid initial admission capacity");
    rateBps = static_cast<int>(initialRate);
    capacityBps = static_cast<int>(initialCapacity);
    enforcedRateBps = std::min(rateBps, capacityBps);
    const double burstBits = 8.0 * burstBytes;
    bucket = inet::queueing::TokenBucket(burstBits, burstBits, enforcedRateBps, nullptr);
    packetFilter.setExpression(par("packetFilter").objectValue());
    recordAdmissionVectors = par("recordAdmissionVectors").boolValue();
    if (recordAdmissionVectors) {
        admittedBytes.registerVector();
        droppedBytes.registerVector();
        configuredRate.registerVector();
        capacityRate.registerVector();
        enforcedRate.registerVector();
        recordRates();
    }
    loadCapacitySchedule();
}

void FlowPolicer::recordRates()
{
    if (recordAdmissionVectors) {
        configuredRate.record(rateBps);
        capacityRate.record(capacityBps);
        enforcedRate.record(enforcedRateBps);
    }
}

void FlowPolicer::updateEnforcedRate()
{
    const int newRate = std::min(rateBps, capacityBps);
    if (newRate == enforcedRateBps)
        return;
    // Accrue credit at the old rate up to this instant. Capacity changes do not refill the bucket.
    bucket.getNumTokens();
    bucket.removeTokenProductionRate(enforcedRateBps);
    bucket.addTokenProductionRate(newRate);
    enforcedRateBps = newRate;
}

void FlowPolicer::setRateBps(int newRateBps)
{
    Enter_Method("setRateBps");
    if (newRateBps < 1 || newRateBps > maxRateBps)
        throw cRuntimeError("Invalid policing rate %d bps", newRateBps);
    rateBps = newRateBps;
    updateEnforcedRate();
    recordRates();
}

void FlowPolicer::handleMessage(cMessage *message)
{
    if (message == capacityTimer) {
        capacityBps = capacitySchedule[nextChange++].bps;
        updateEnforcedRate();
        recordRates();
        if (nextChange < capacitySchedule.size())
            scheduleAt(capacitySchedule[nextChange].time, capacityTimer);
        return;
    }

    auto *packet = check_and_cast<inet::Packet *>(message);
    if (packetFilter.matches(packet)) {
        if (enforcedRateBps == 0 || bucket.getNumTokens() < packet->getBitLength()) {
            counters.droppedPackets++;
            counters.droppedBytes += packet->getByteLength();
            if (recordAdmissionVectors)
                droppedBytes.record(packet->getByteLength());
            delete packet;
            return;
        }
        bucket.removeTokens(packet->getBitLength());
        counters.admittedPackets++;
        counters.admittedBytes += packet->getByteLength();
        if (recordAdmissionVectors)
            admittedBytes.record(packet->getByteLength());
    }
    send(packet, "out");
}

void FlowPolicer::finish()
{
    recordScalar("managedAdmittedPackets", counters.admittedPackets);
    recordScalar("managedDroppedPackets", counters.droppedPackets);
    recordScalar("managedAdmittedBytes", counters.admittedBytes);
    recordScalar("managedDroppedBytes", counters.droppedBytes);
    recordScalar("lastRateBps", rateBps);
    if (recordAdmissionVectors) {
        recordScalar("lastCapacityBps", capacityBps);
        recordScalar("lastEnforcedRateBps", enforcedRateBps);
    }
}

} // namespace nasctime::control