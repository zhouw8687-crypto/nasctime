#include <array>
#include <string>

#include "inet/applications/base/ApplicationPacket_m.h"
#include "inet/applications/udpapp/UdpBasicApp.h"
#include "inet/common/Simsignals.h"
#include "inet/common/TimeTag_m.h"
#include "inet/networklayer/common/FragmentationTag_m.h"
#include "nasctime/control/ControlledDlScheduler.h"
#include "simu5g/common/QfiTag_m.h"
#include "simu5g/common/binder/Binder.h"
#include "simu5g/stack/mac/LteMacEnb.h"

namespace nasctime::control {

using namespace inet;
using namespace omnetpp;
using namespace simu5g;

// A native gNB UDP application injects only after N3. Supply the QFI tag
// normally restored by GTP-U decapsulation so the ordinary SDAP path runs.
class LocalQfiSource : public UdpBasicApp
{
    void sendPacket() override
    {
        auto *packet = new Packet((std::string(packetName) + "-" + std::to_string(numSent)).c_str());
        if (dontFragment)
            packet->addTag<FragmentationReq>()->setDontFragment(true);
        auto payload = makeShared<ApplicationPacket>();
        payload->setChunkLength(B(par("messageLength")));
        payload->setSequenceNumber(numSent);
        payload->addTag<CreationTimeTag>()->setCreationTime(simTime());
        packet->insertAtBack(payload);
        packet->addTag<QfiReq>()->setQfi(Qfi(5));
        const auto destAddr = chooseDestAddr();
        emit(packetSentSignal, packet);
        socket.sendTo(packet, destAddr, destPort);
        numSent++;
    }
};

Define_Module(LocalQfiSource);

class ObservedDlScheduler : public ControlledDlScheduler
{
    std::array<MacNodeId, 2> ueIds{};
    cOutVector ue0Blocks{"ue0DlAllocatedBlocks"};
    cOutVector ue1Blocks{"ue1DlAllocatedBlocks"};

    void initialize(int stage) override
    {
        ControlledDlScheduler::initialize(stage);
        if (stage != INITSTAGE_LAST)
            return;

        auto *network = getSimulation()->getSystemModule();
        for (unsigned i = 0; i < ueIds.size(); i++) {
            auto path = "ue[" + std::to_string(i) + "].cellularNic.nrMac";
            auto *ueMac = check_and_cast<LteMacBase *>(network->getModuleByPath(path.c_str()));
            ueIds[i] = ueMac->getMacNodeId();
            if (binder_->getServingNode(ueIds[i]) != mac_->getMacNodeId())
                throw cRuntimeError("%s is not served by the observed gNB", path.c_str());
        }
        if (ueIds[0] == ueIds[1])
            throw cRuntimeError("Expected two distinct NR MAC identities");
        ue0Blocks.registerVector();
        ue1Blocks.registerVector();
    }

    std::map<GHz, LteMacScheduleList> *schedule() override
    {
        auto *schedule = ControlledDlScheduler::schedule();
        std::array<unsigned, 2> blocks{};
        for (int band = 0; band < getMaxBands(); band++) {
            for (unsigned i = 0; i < ueIds.size(); i++)
                blocks[i] += readPerUeAllocatedBlocks(ueIds[i], MACRO, Band(band));
        }
        ue0Blocks.record(blocks[0]);
        ue1Blocks.record(blocks[1]);
        return schedule;
    }
};

Define_Module(ObservedDlScheduler);

} // namespace nasctime::control
