//
//                  nascTime
//
// Authors: Mohamed Seliem (University College Cork)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

#include "nasctime/nodes/NwTt/NwTtTranslator.h"

#include <omnetpp/cvaluearray.h>
#include <omnetpp/cvaluemap.h>

#include "nasctime/nodes/NwTt/GptpResidenceHeader_m.h"
#include "inet/common/ModuleAccess.h"
#include "inet/common/ProtocolTag_m.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/linklayer/common/MacAddressTag_m.h"
#include "inet/linklayer/common/InterfaceTag_m.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/networklayer/common/L3AddressResolver.h"
#include "inet/networklayer/common/L3AddressTag_m.h"
#include "inet/networklayer/ipv4/Ipv4Header_m.h"
#include "simu5g/common/binder/Binder.h"
#include "inet/transportlayer/udp/UdpHeader_m.h"
#include "inet/networklayer/ipv4/Ipv4Header_m.h"
#include "inet/linklayer/ieee8021q/Ieee8021qTagHeader_m.h"
#include "inet/networklayer/contract/IInterfaceTable.h"
#include "inet/common/IProtocolRegistrationListener.h"

Define_Module(NwTtTranslator);

// ============================================================================
// Initialization
// ============================================================================

void NwTtTranslator::initialize(int stage)
{
    cSimpleModule::initialize(stage);

    if (stage == INITSTAGE_LOCAL) {
        ethInGateId        = gate("ethIn")->getId();
        ethOutGateId       = gate("ethOut")->getId();
        ipForwardOutGateId = gate("ipForwardOut")->getId();
        ipForwardInGateId  = gate("ipForwardIn")->getId();
        gptpOutGateId      = gate("gptpOut")->getId();

        tsnPortMac.setAddress(par("tsnPortMacAddress").stringValue());
        defaultDstMac.setAddress(par("defaultDstMacAddress").stringValue());
        encapUdpPort = par("encapUdpPort");
        useGtpuForGptp = (strcmp(par("gptpTransportMode").stringValue(), "gtpu") == 0);
        gptpEncapUdpPort = par("gptpEncapUdpPort");

        encapDelaySignal       = registerSignal("encapDelay");
        decapDelaySignal       = registerSignal("decapDelay");
        ethFrameReceivedSignal = registerSignal("ethFrameReceived");
        ipPacketReceivedSignal = registerSignal("ipPacketReceived");
        packetDroppedSignal    = registerSignal("packetDropped");
        gptpInterceptedSignal  = registerSignal("gptpIntercepted");
        registerProtocol(Protocol::ethernetMac, gate("ethOut"), gate("ethIn"));

        std::string mappedPcps = par("mappedPcpValues").stdstringValue();
        cStringTokenizer tokenizer(mappedPcps.c_str(), ",");
        while (tokenizer.hasMoreTokens())
            mappedPcpSet.insert(atoi(tokenizer.nextToken()));

        EV_INFO << "NwTtTranslator: initialised (stage LOCAL)" << endl;
    }
    else if (stage == INITSTAGE_NETWORK_LAYER) {
        // H1: Look up pppIf interface ID dynamically
        auto *ift = getModuleFromPar<IInterfaceTable>(par("interfaceTableModule"), this);
        auto *pppIe = ift->findInterfaceByName("pppIf");
        if (pppIe) {
            pppIfInterfaceId = pppIe->getInterfaceId();
            EV_INFO << "NwTtTranslator: pppIf interfaceId=" << pppIfInterfaceId << endl;
        } else {
            throw cRuntimeError("NwTtTranslator: pppIf interface not found");
        }
        // H5: Manually register ethernetmac service on nl so IPv4 routing
                // can find encap for the egress path (encap has registerProtocol=false
                // to avoid conflicts on ethLi)
                auto *encapMod = getParentModule()->getSubmodule("encap");
                if (encapMod) {
                    registerService(Protocol::ethernetMac,
                                   encapMod->gate("upperLayerIn"),
                                   encapMod->gate("upperLayerOut"));
                }
    }
    else if (stage == INITSTAGE_TRANSPORT_LAYER) {
        ueAddr    = L3AddressResolver().resolve(par("ueAddress"));
        localAddr = L3AddressResolver().resolve(par("localAddress"));

        // UDP socket for potential egress (5GS → TSN) path
        udpSocket.setOutputGate(gate("socketOut"));
        udpSocket.setCallback(this);
        udpSocket.bind(localAddr, encapUdpPort);

        EV_INFO << "NwTtTranslator: UDP socket bound on "
                << localAddr << ":" << encapUdpPort
                << ", forwarding toward " << ueAddr << endl;

        // Register downstream TSN device IPs with the binder.
        auto *binderModule = getSystemModule()->getSubmodule("binder");
        auto *binderMod = check_and_cast<simu5g::Binder *>(binderModule);

        // Build UE module → NR nodeId map from binder
        auto& nodeMap = binderMod->getNodeInfoMap();
        std::map<cModule*, simu5g::MacNodeId> ueNrNodeIds;
        for (auto& [nid, info] : nodeMap) {
            if (info.moduleRef && simu5g::isNrUe(nid))
                ueNrNodeIds[info.moduleRef.get()] = nid;
        }

        // Multi-endpoint registration
        const cValueArray *addrArr = check_and_cast_nullable<const cValueArray *>(
                par("tsnDeviceBAddresses").objectValue());

        if (addrArr && addrArr->size() > 0) {
            for (int i = 0; i < (int)addrArr->size(); i++) {
                const cValueMap *entry = check_and_cast<const cValueMap *>(
                        addrArr->get(i).objectValue());

                std::string tsnAddr = entry->get("address").stdstringValue();
                std::string ueModPath = entry->get("ue").stdstringValue();

                auto tsnIp = L3AddressResolver().resolve(tsnAddr.c_str());
                auto *ueModule = getModuleByPath(ueModPath.c_str());

                if (ueModule) {
                    auto it = ueNrNodeIds.find(ueModule);
                    if (it != ueNrNodeIds.end()) {
                        simu5g::MacNodeId nrNodeId = it->second;
                        binderMod->setMacNodeId(tsnIp.toIpv4(), nrNodeId);
                        tsnToUeMap[tsnIp] = L3AddressResolver().resolve(ueModPath.c_str());
                        EV_INFO << "NwTtTranslator: registered " << tsnIp
                                << " with binder as NR nodeId=" << nrNodeId
                                << " (ue=" << ueModPath << ")" << endl;
                    } else {
                        EV_WARN << "NwTtTranslator: no NR nodeId found for "
                                << ueModPath << endl;
                    }
                }
            }

            if (!tsnToUeMap.empty())
                tsnDeviceBAddr = tsnToUeMap.begin()->first;
        }
        else {
            // Single-endpoint fallback (backward compatible)
            std::string tsnBAddr = par("tsnDeviceBAddress").stdstringValue();
            if (!tsnBAddr.empty()) {
                tsnDeviceBAddr = L3AddressResolver().resolve(tsnBAddr.c_str());

                auto *ueModule = getModuleByPath("ue[0]");
                simu5g::MacNodeId nrNodeId = simu5g::NODEID_NONE;
                for (auto& [nid, info] : nodeMap) {
                    if (info.moduleRef.get() == ueModule && simu5g::isNrUe(nid)) {
                        nrNodeId = nid;
                        break;
                    }
                }

                if (nrNodeId != simu5g::NODEID_NONE) {
                    binderMod->setMacNodeId(tsnDeviceBAddr.toIpv4(), nrNodeId);
                    tsnToUeMap[tsnDeviceBAddr] = ueAddr;
                    EV_INFO << "NwTtTranslator: registered " << tsnDeviceBAddr
                            << " with binder as NR nodeId=" << nrNodeId << endl;
                }
            }
        }
    }
}
// ============================================================================
// Message dispatch
// ============================================================================

void NwTtTranslator::handleMessage(cMessage *msg)
{
    if (msg->isSelfMessage()) {
        delete msg;
        return;
    }

    int gateId = msg->getArrivalGateId();

    if (gateId == ethInGateId) {
        auto pkt = check_and_cast<Packet *>(msg);
        handleEthernetFrame(pkt);
    }
    else if (gateId == ipForwardInGateId) {
        // H3: Egress path — packet from 5GS destined for TSN
        auto pkt = check_and_cast<Packet *>(msg);
        //handleEgressPacket(pkt);
    }
    else {
        // From the IP side — may be Packet or Indication (ICMP error)
        udpSocket.processMessage(msg);
    }
}

// ============================================================================
// INGRESS: TSN → 5GS
//
// Receives Ethernet frame from EthernetInterface (MAC header + FCS attached).
// Strips Ethernet framing, leaving the original IPv4 datagram.
// Forwards it directly to pppIf via the nl dispatcher, bypassing the
// NwTt's own IPv4 stack to avoid double encapsulation.
// ============================================================================

void NwTtTranslator::handleEthernetFrame(Packet *pkt)
{
    simtime_t t0 = simTime();
    emit(ethFrameReceivedSignal, ++numEthReceived);

    EV_INFO << "NwTtTranslator INGRESS: " << pkt->getName()
            << " (" << pkt->getTotalLength() << ")" << endl;

    // Check for gPTP frames (ethertype 0x88F7) BEFORE stripping headers
    auto ethHeader = pkt->peekAtFront<EthernetMacHeader>();
    if (ethHeader->getTypeOrLength() == 0x88F7) {
        emit(gptpInterceptedSignal, ++numGptpIntercepted);
        if (!useGtpuForGptp) {
            // Sideband mode — send directly to DS-TT via OMNeT++ connection
            EV_INFO << "NwTtTranslator: gPTP frame → sideband" << endl;
            send(pkt, gptpOutGateId);
        } else {
            // L2-in-GTP-U mode — wrap entire Ethernet frame in UDP and send
            // through the 5GS data plane so gPTP experiences real 5G delay
            // — replicate to ALL registered downstream devices
            EV_INFO << "NwTtTranslator: gPTP frame → L2-in-GTP-U to "
                    << tsnToUeMap.size() << " endpoints" << endl;

            // Serialize the entire Ethernet frame (with MAC header + FCS) as raw bytes
            auto rawFrame = pkt->peekData();

            // G3: Prepend residence time header (models GTP-U PDU Session Container)
            auto residenceHdr = makeShared<simu5g::GptpResidenceHeader>();
            residenceHdr->setIngressTime(simTime());

            for (auto& [tsnIp, ueIp] : tsnToUeMap) {
                auto udpPkt = new Packet(pkt->getName());
                udpPkt->insertAtBack(residenceHdr->dupShared());
                udpPkt->insertAtBack(rawFrame);

                // Build UDP header
                auto udpHdr = makeShared<UdpHeader>();
                udpHdr->setSourcePort(gptpEncapUdpPort);
                udpHdr->setDestinationPort(gptpEncapUdpPort);
                udpHdr->setTotalLengthField(udpHdr->getChunkLength() + udpPkt->getTotalLength());
                udpHdr->setChecksumMode(FCS_DECLARED_CORRECT);
                udpHdr->setChecksum(0xC00D);
                udpPkt->insertAtFront(udpHdr);

                // Build IPv4 header — addressed to this specific tsnDeviceB
                auto ipHdr = makeShared<Ipv4Header>();
                ipHdr->setSrcAddress(localAddr.toIpv4());
                ipHdr->setDestAddress(tsnIp.toIpv4());
                ipHdr->setProtocolId(IP_PROT_UDP);
                ipHdr->setTimeToLive(64);
                ipHdr->setDscp(5);
                ipHdr->setTotalLengthField(ipHdr->getChunkLength() + udpPkt->getTotalLength());
                ipHdr->setChecksumMode(FCS_DECLARED_CORRECT);
                ipHdr->setChecksum(0xC00D);
                udpPkt->insertAtFront(ipHdr);

                // Tag and send directly to pppIf (same as data path)
                udpPkt->addTagIfAbsent<PacketProtocolTag>()->setProtocol(&Protocol::ipv4);
                udpPkt->addTagIfAbsent<InterfaceReq>()->setInterfaceId(pppIfInterfaceId);

                EV_INFO << "NwTtTranslator: gPTP replicated to " << tsnIp << endl;
                send(udpPkt, ipForwardOutGateId);
            }
            delete pkt;
        }
    return;
    }

    // Strip Ethernet framing
    pkt->popAtFront<EthernetMacHeader>();
    pkt->popAtBack<EthernetFcs>(B(4));

    // G4: Check for 802.1Q VLAN tag and strip it (reading PCP first)
    int pcp = 0;
    bool vlanStripped = false;
    auto firstChunk = pkt->peekAtFront<Chunk>();
    if (auto vlanTag = dynamicPtrCast<const Ieee8021qTagEpdHeader>(firstChunk)) {
        pcp = vlanTag->getPcp();
        if (mappedPcpSet.count(pcp) > 0) {
            // Mapped PCP — strip VLAN tag, will set DSCP instead
            pkt->popAtFront<Ieee8021qTagEpdHeader>();
            vlanStripped = true;
            EV_INFO << "NwTtTranslator: stripped VLAN tag, PCP=" << pcp << " (mapped)" << endl;
        } else {
            // Non-mapped PCP — preserve VLAN tag for passthrough
            EV_INFO << "NwTtTranslator: preserving VLAN tag, PCP=" << pcp << " (passthrough)" << endl;
        }
    }
    // G4: Map PCP → DSCP for 5G QoS
    if (vlanStripped) {
        auto ipHdr = pkt->removeAtFront<Ipv4Header>();
        ipHdr->setDscp(pcp);
        pkt->insertAtFront(ipHdr);
        EV_INFO << "NwTtTranslator: PCP=" << pcp << " → DSCP=" << pcp << endl;
    }

    // What remains is the original IPv4 datagram from the TSN device.
    // Send it directly to pppIf (toward UPF), bypassing the NwTt's own
    // IPv4 routing stack. The nl dispatcher routes by InterfaceReq tag.
    pkt->removeTagIfPresent<PacketProtocolTag>();
    pkt->removeTagIfPresent<DispatchProtocolReq>();
    pkt->removeTagIfPresent<L3AddressReq>();
    pkt->removeTagIfPresent<InterfaceInd>();
    pkt->removeTagIfPresent<MacAddressInd>();
    pkt->addTagIfAbsent<PacketProtocolTag>()->setProtocol(&Protocol::ipv4);
    pkt->addTagIfAbsent<InterfaceReq>()->setInterfaceId(pppIfInterfaceId);  // pppIf

    send(pkt, ipForwardOutGateId);

    emit(encapDelaySignal, simTime() - t0);
}

// ============================================================================
// EGRESS: 5GS → TSN (via UdpSocket callback)
// ============================================================================

void NwTtTranslator::socketDataArrived(UdpSocket *socket, Packet *pkt)
{
    simtime_t t0 = simTime();
    emit(ipPacketReceivedSignal, ++numIpReceived);

    EV_INFO << "NwTtTranslator EGRESS: " << pkt->getName()
            << " (" << pkt->getTotalLength() << ")" << endl;

    handleIpPacket(pkt);
}

void NwTtTranslator::handleIpPacket(Packet *pkt)
{
    simtime_t t0 = simTime();

    // UdpSocket has stripped the UDP header.
    // Remaining payload is the raw TSN frame body.
    auto payload = pkt->peekData();

    // Create Ethernet frame for the TSN side
    auto ethPkt = new Packet(pkt->getName());
    ethPkt->insertAtBack(payload);

    // Set MAC addresses for EthernetInterface
    auto macReq = ethPkt->addTag<MacAddressReq>();
    macReq->setSrcAddress(tsnPortMac);
    macReq->setDestAddress(defaultDstMac);

    // Set protocol tag for EtherType
    ethPkt->addTagIfAbsent<PacketProtocolTag>()->setProtocol(&Protocol::ipv4);

    // Send toward TSN switch
    send(ethPkt, ethOutGateId);

    emit(decapDelaySignal, simTime() - t0);
    delete pkt;
}

void NwTtTranslator::socketErrorArrived(UdpSocket *socket, Indication *indication)
{
    EV_WARN << "NwTtTranslator: UDP error — " << indication->getName() << endl;
    delete indication;
}

// ============================================================================
// Finish
// ============================================================================

void NwTtTranslator::finish()
{
    EV_INFO << "NwTtTranslator stats:"
            << " ethRx=" << numEthReceived
            << " ipRx=" << numIpReceived
            << " dropped=" << numDropped << endl;
}
