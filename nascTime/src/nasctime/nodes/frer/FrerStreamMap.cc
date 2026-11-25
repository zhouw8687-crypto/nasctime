#include "nasctime/nodes/frer/FrerStreamMap.h"

#include <set>

#include "inet/transportlayer/udp/UdpHeader_m.h"

using namespace inet;
using namespace omnetpp;

void FrerStreamMap::load(cPar& config, int replicaDscp)
{
    const auto *entries = check_and_cast<const cValueArray *>(config.objectValue());
    if (entries->size() == 0)
        return;
    if (replicaDscp < 0 || replicaDscp > 63)
        throw cRuntimeError("FRER replicaDscp must be in [0, 63]");

    std::set<intval_t> streamIds;
    for (int i = 0; i < static_cast<int>(entries->size()); ++i) {
        const auto *entry = check_and_cast<const cValueMap *>(entries->get(i).objectValue());
        auto port = entry->get("udpDestPort").intValue();
        auto id = entry->get("streamId").intValue();
        auto dscp = entry->get("primaryDscp").intValue();
        if (port < 1 || port > 65535 || id < 1 || id > 65535 ||
            dscp < 0 || dscp > 63 || dscp == replicaDscp)
            throw cRuntimeError("Invalid FRER streamMap entry %d: check UDP port, stream ID and DSCP", i);
        if (!streamIds.insert(id).second ||
            !streamsByPort.emplace(port, Entry{static_cast<uint16_t>(id), static_cast<int>(dscp)}).second)
            throw cRuntimeError("Duplicate UDP destination port or stream ID in FRER streamMap entry %d", i);
    }
}

const FrerStreamMap::Entry *FrerStreamMap::find(const Packet& packet, const Ipv4Header& ip, b ipOffset) const
{
    if (ip.getProtocolId() != IP_PROT_UDP || ip.getMoreFragments() || ip.getFragmentOffset() != 0)
        return nullptr;
    auto udpOffset = ipOffset + ip.getChunkLength();
    if (ip.getTotalLengthField() < ip.getChunkLength() + B(8) ||
            packet.getDataLength() < ipOffset + ip.getTotalLengthField())
        return nullptr;

    const auto udp = dynamicPtrCast<const UdpHeader>(packet.peekDataAt<Chunk>(udpOffset));
    if (!udp)
        return nullptr;
    auto it = streamsByPort.find(udp->getDestinationPort());
    return it == streamsByPort.end() ? nullptr : &it->second;
}
