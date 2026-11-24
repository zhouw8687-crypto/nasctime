#include "nasctime/control/FlowPolicer.h"

namespace nasctime::control {

Define_Module(FlowPolicer);

void FlowPolicer::initialize()
{
    const auto initialRate = par("initialRate").intValue();
    const auto burstBytes = par("burstSize").intValue();
    if (initialRate < 1 || initialRate > maxRateBps || burstBytes <= 0)
        throw omnetpp::cRuntimeError("Invalid initial policing rate or burst size");
    rateBps = static_cast<int>(initialRate);
    const double burstBits = 8.0 * burstBytes;
    bucket = inet::queueing::TokenBucket(burstBits, burstBits, rateBps, nullptr);
    packetFilter.setExpression(par("packetFilter").objectValue());
}

void FlowPolicer::setRateBps(int newRateBps)
{
    Enter_Method("setRateBps");
    if (newRateBps < 1 || newRateBps > maxRateBps)
        throw omnetpp::cRuntimeError("Invalid policing rate %d bps", newRateBps);
    // Account for the elapsed time using the previous rate before changing it.
    bucket.getNumTokens();
    bucket.removeTokenProductionRate(rateBps);
    bucket.addTokenProductionRate(newRateBps);
    rateBps = newRateBps;
}

void FlowPolicer::handleMessage(omnetpp::cMessage *message)
{
    auto *packet = omnetpp::check_and_cast<inet::Packet *>(message);
    if (packetFilter.matches(packet)) {
        if (bucket.getNumTokens() < packet->getBitLength()) {
            counters.droppedPackets++;
            counters.droppedBytes += packet->getByteLength();
            delete packet;
            return;
        }
        bucket.removeTokens(packet->getBitLength());
        counters.admittedPackets++;
        counters.admittedBytes += packet->getByteLength();
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
}

} // namespace nasctime::control
