#ifndef NASCTIME_CONTROLLED_DLSCHEDULER_H
#define NASCTIME_CONTROLLED_DLSCHEDULER_H

#include "simu5g/stack/mac/scheduler/LteSchedulerEnbDl.h"

namespace nasctime::control {

using simu5g::BandLimitVector;
using simu5g::Codeword;
using simu5g::GHz;
using simu5g::MacCid;
using simu5g::MacNodeId;
using simu5g::Remote;

class ControlledDlScheduler : public simu5g::LteSchedulerEnbDl
{
  public:
    void setBandBudget(int bands);
    int getBandBudget() const { return bandBudget; }
    int getMaxBands() const { return maxBands; }
    int getLastSlotAllocatedBlocks() const { return lastSlotAllocatedBlocks; }

    std::map<GHz, simu5g::LteMacScheduleList> *schedule() override;
    unsigned int scheduleGrant(MacCid cid, unsigned int bytes, bool& terminate, bool& active, bool& eligible,
            GHz carrier, BandLimitVector *limits, Remote antenna, bool limitBlocks) override;
    unsigned int scheduleGrantBackground(MacCid cid, unsigned int bytes, bool& terminate, bool& active, bool& eligible,
            GHz carrier, BandLimitVector *limits, Remote antenna, bool limitBlocks) override;
    unsigned int schedulePerAcidRtx(MacNodeId ue, GHz carrier, Codeword codeword, unsigned char acid,
            BandLimitVector *limits, Remote antenna, bool limitBlocks) override;
    unsigned int scheduleBgRtx(MacNodeId ue, GHz carrier, Codeword codeword,
            BandLimitVector *limits, Remote antenna, bool limitBlocks) override;

  protected:
    void initialize(int stage) override;

  private:
    int bandBudget = 0;
    int maxBands = 0;
    int lastSlotAllocatedBlocks = 0;
    omnetpp::cOutVector allocatedBlocks{"controlledDlAllocatedBlocks"};

    BandLimitVector *restrictBands(GHz carrier, BandLimitVector *limits, BandLimitVector& fallback) const;
};

} // namespace nasctime::control

#endif
