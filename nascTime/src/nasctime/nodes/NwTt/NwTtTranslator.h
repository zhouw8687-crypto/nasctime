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

#ifndef __SIMU5G_1_4_3_NWTTTRANSLATOR_H_
#define __SIMU5G_1_4_3_NWTTTRANSLATOR_H_


#include <omnetpp.h>

#include "inet/common/packet/Packet.h"
//#include "inet/common/clock/ClockUserModuleMixin.h"
#include "inet/linklayer/common/MacAddress.h"
#include "inet/networklayer/common/L3Address.h"
#include "inet/transportlayer/contract/udp/UdpSocket.h"
#include "simu5g/common/LteCommon.h"

using namespace omnetpp;
using namespace inet;

/**
 * Translates between Ethernet frames (TSN domain) and UDP datagrams (5GC domain).
 *
 * Uses UdpSocket to communicate through the standard INET protocol stack
 * (UDP → IPv4 → PPP), connected via MessageDispatcher modules.
 *
 * The ethIn/ethOut gates connect directly to the LayeredEthernetInterface
 * (bypassing the MessageDispatcher for Ethernet — the NW-TT IS the bridge
 * port, it doesn't go through the node's normal L2 forwarding).
 */
class NwTtTranslator : public cSimpleModule,
                        public UdpSocket::ICallback
{
  protected:
    // --- Configuration ---
    MacAddress tsnPortMac;
    MacAddress defaultDstMac;
    L3Address  ueAddr;
    L3Address  localAddr;
    L3Address tsnDeviceBAddr;
    std::map<L3Address, L3Address> tsnToUeMap;  // tsnDeviceB IP → UE IP (for gPTP routing)
    int        encapUdpPort;
    bool useGtpuForGptp;
    int gptpEncapUdpPort;
    int pppIfInterfaceId;
    int ipForwardInGateId;
    std::set<int> mappedPcpSet;

    // --- UDP socket (uses socketIn/socketOut via MessageDispatcher) ---
    UdpSocket udpSocket;

    // --- Gate IDs ---
    int ethInGateId;
    int ethOutGateId;
    int ipForwardOutGateId;
    int gptpOutGateId;

    // --- Signals ---
    simsignal_t encapDelaySignal;
    simsignal_t decapDelaySignal;
    simsignal_t ethFrameReceivedSignal;
    simsignal_t ipPacketReceivedSignal;
    simsignal_t packetDroppedSignal;
    simsignal_t gptpInterceptedSignal;

    // --- Counters ---
    long numEthReceived = 0;
    long numIpReceived  = 0;
    long numDropped     = 0;
    long numGptpIntercepted = 0;

  protected:
    virtual void initialize(int stage) override;
    virtual int numInitStages() const override { return NUM_INIT_STAGES; }
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

    /** Ingress: Ethernet payload → UDP datagram toward UE */
    virtual void handleEthernetFrame(Packet *pkt);

    /** Egress: UDP datagram → Ethernet frame toward TSN switch */
    virtual void handleIpPacket(Packet *pkt);

    // --- UdpSocket::ICallback ---
    virtual void socketDataArrived(UdpSocket *socket, Packet *packet) override;
    virtual void socketErrorArrived(UdpSocket *socket, Indication *indication) override;
    virtual void socketClosed(UdpSocket *socket) override {}
};

#endif
