#include <algorithm>

#include "nasctime/control/ControlledDlScheduler.h"

namespace nasctime::control {

using namespace omnetpp;
using namespace simu5g;

Define_Module(ControlledDlScheduler);

void ControlledDlScheduler::initialize(int stage)
{
    LteSchedulerEnbDl::initialize(stage);
    if (stage == INITSTAGE_SIMU5G_AMC_SETUP) {
        auto *cell = mac_->getCellInfo();
        if (cell->getCarrierInfoMap().size() != 1 || cell->getNumBands() == 0)
            throw cRuntimeError("Controlled downlink requires a single carrier with at least one band");
        maxBands = cell->getNumBands();
        const auto initial = par("initialBandBudget").intValue();
        if (initial < 0 || initial > maxBands)
            throw cRuntimeError("Initial downlink band budget is outside [0, %d]", maxBands);
        bandBudget = initial == 0 ? maxBands : initial;
        allocatedBlocks.registerVector();
    }
}

void ControlledDlScheduler::setBandBudget(int bands)
{
    Enter_Method("setBandBudget");
    if (bands < 1 || bands > maxBands)
        throw cRuntimeError("Requested downlink band budget is outside [1, %d]", maxBands);
    bandBudget = bands;
}

BandLimitVector *ControlledDlScheduler::restrictBands(GHz carrier, BandLimitVector *limits,
        BandLimitVector& fallback) const
{
    if (bandBudget == maxBands)
        return limits;
    if (limits == nullptr) {
        fallback = mac_->getCellInfo()->getCarrierBandLimit(carrier);
        limits = &fallback;
    }
    for (auto& band : *limits) {
        if (band.band_ >= bandBudget)
            std::fill(band.limit_.begin(), band.limit_.end(), -2);
    }
    return limits;
}

unsigned int ControlledDlScheduler::scheduleGrant(MacCid cid, unsigned int bytes, bool& terminate,
        bool& active, bool& eligible, GHz carrier, BandLimitVector *limits, Remote antenna, bool limitBlocks)
{
    BandLimitVector fallback;
    return LteSchedulerEnbDl::scheduleGrant(cid, bytes, terminate, active, eligible, carrier,
            restrictBands(carrier, limits, fallback), antenna, limitBlocks);
}

unsigned int ControlledDlScheduler::scheduleGrantBackground(MacCid cid, unsigned int bytes, bool& terminate,
        bool& active, bool& eligible, GHz carrier, BandLimitVector *limits, Remote antenna, bool limitBlocks)
{
    BandLimitVector fallback;
    return LteSchedulerEnbDl::scheduleGrantBackground(cid, bytes, terminate, active, eligible, carrier,
            restrictBands(carrier, limits, fallback), antenna, limitBlocks);
}

unsigned int ControlledDlScheduler::schedulePerAcidRtx(MacNodeId ue, GHz carrier, Codeword codeword,
        unsigned char acid, BandLimitVector *limits, Remote antenna, bool limitBlocks)
{
    BandLimitVector fallback;
    return LteSchedulerEnbDl::schedulePerAcidRtx(ue, carrier, codeword, acid,
            restrictBands(carrier, limits, fallback), antenna, limitBlocks);
}

unsigned int ControlledDlScheduler::scheduleBgRtx(MacNodeId ue, GHz carrier, Codeword codeword,
        BandLimitVector *limits, Remote antenna, bool limitBlocks)
{
    BandLimitVector fallback;
    return LteSchedulerEnbDl::scheduleBgRtx(ue, carrier, codeword,
            restrictBands(carrier, limits, fallback), antenna, limitBlocks);
}

std::map<GHz, LteMacScheduleList> *ControlledDlScheduler::schedule()
{
    auto *schedule = LteSchedulerEnbDl::schedule();
    lastSlotAllocatedBlocks = 0;
    for (int band = 0; band < maxBands; band++) {
        const auto blocks = readPerBandAllocatedBlocks(MAIN_PLANE, MACRO, Band(band));
        if (band >= bandBudget && blocks != 0)
            throw cRuntimeError("Downlink allocated excluded logical band %d", band);
        lastSlotAllocatedBlocks += blocks;
    }
    allocatedBlocks.record(lastSlotAllocatedBlocks);
    return schedule;
}

} // namespace nasctime::control
