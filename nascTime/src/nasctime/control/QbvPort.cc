#include "nasctime/control/QbvPort.h"

namespace nasctime::control {

using namespace omnetpp;
using inet::queueing::PeriodicGate;

void QbvPort::bind(cModule *shaper)
{
    for (unsigned index = 0; index < gates.size(); index++)
        gates[index] = check_and_cast<PeriodicGate *>(shaper->getSubmodule("transmissionGate", index));
}

bool QbvPort::canApplyNow() const
{
    return simTime().raw() % SimTime(cycleUs, SIMTIME_US).raw() == 0;
}

int QbvPort::getPriorityWindowUs() const
{
    const auto& priorityDurations = gates[2]->getDurations();
    if (priorityDurations.size() != 2)
        throw cRuntimeError("Expected a two-window Qbv cycle");
    const auto firstDuration = priorityDurations[0];
    if (firstDuration < inet::ClockTime::from(SimTime(minPriorityUs, SIMTIME_US)) ||
            firstDuration > inet::ClockTime::from(SimTime(maxPriorityUs, SIMTIME_US)) ||
            firstDuration + priorityDurations[1] != inet::ClockTime::from(SimTime(cycleUs, SIMTIME_US)))
        throw cRuntimeError("Invalid Qbv priority window");
    for (unsigned index = 0; index < gates.size(); index++) {
        const auto *gate = gates[index];
        if (!gate->par("clockModule").stdstringValue().empty() ||
                gate->getInitiallyOpen() != (index == 2) ||
                gate->getInitialOffset() != inet::CLOCKTIME_ZERO ||
                gate->getDurations() != priorityDurations)
            throw cRuntimeError("Inconsistent Qbv gate cycle");
    }
    const int windowUs = CLOCKTIME_AS_SIMTIME(firstDuration).inUnit(SIMTIME_US);
    if (inet::ClockTime::from(SimTime(windowUs, SIMTIME_US)) != firstDuration)
        throw cRuntimeError("The Qbv priority window must be a whole number of microseconds");
    return windowUs;
}

void QbvPort::setPriorityWindowUs(int priorityUs)
{
    if (!canApplyNow() || priorityUs < minPriorityUs || priorityUs > maxPriorityUs)
        throw cRuntimeError("Invalid Qbv window update");
    for (auto *gate : gates) {
        auto *durations = new cValueArray();
        durations->add(cValue(priorityUs, "us"));
        durations->add(cValue(cycleUs - priorityUs, "us"));
        auto& parameter = gate->par("durations");
        parameter.copyIfShared();
        parameter.setObjectValue(durations);
    }
}

} // namespace nasctime::control
