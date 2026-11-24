#ifndef NASCTIME_QBVPORT_H
#define NASCTIME_QBVPORT_H

#include <array>
#include <omnetpp.h>

#include "inet/queueing/gate/PeriodicGate.h"

namespace nasctime::control {

// One INET TAS port with a priority window followed by a shared window.
class QbvPort
{
  public:
    static constexpr int cycleUs = 5000;
    static constexpr int minPriorityUs = 400;
    static constexpr int maxPriorityUs = 3000;

    void bind(omnetpp::cModule *shaper);
    bool canApplyNow() const;
    int getPriorityWindowUs() const;
    void setPriorityWindowUs(int priorityUs);

  private:
    std::array<inet::queueing::PeriodicGate *, 3> gates{};
};

} // namespace nasctime::control

#endif
