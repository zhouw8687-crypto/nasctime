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

#include "nasctime/nodes/frer/FrerRecovery.h"

#include "nasctime/nodes/frer/FrerSequenceHeader_m.h"
#include "inet/common/ProtocolTag_m.h"
#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/ProtocolUtils.h"
#include "inet/linklayer/common/InterfaceTag_m.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/networklayer/ipv4/Ipv4Header_m.h"

Define_Module(FrerRecovery);

// ============================================================================
// Initialization
// ============================================================================

void FrerRecovery::initialize()
{
    inGateId  = gate("in")->getId();
    outGateId = gate("out")->getId();

    replicaDscp   = par("replicaDscp");
    streamMap.load(par("streamMap"), replicaDscp);
    windowSize    = par("windowSize");
    windowTimeout = par("windowTimeout");
    ethernetFramed = par("ethernetFramed");

    // Parse comma-separated primary-stream DSCPs
    const char *streams_str = par("frerStreams").stringValue();
    cStringTokenizer tokenizer(streams_str, ",");
    while (tokenizer.hasMoreTokens()) {
        frerStreamDscpSet.insert(atoi(tokenizer.nextToken()));
    }

    // Register signals
    recoveredFromPrimarySignal = registerSignal("recoveredFromPrimary");
    recoveredFromReplicaSignal = registerSignal("recoveredFromReplica");
    duplicatesDroppedSignal    = registerSignal("duplicatesDropped");
    windowOverrunsSignal       = registerSignal("windowOverruns");
    passedThroughSignal        = registerSignal("passedThrough");

    // Register ethernetMac protocol with the upstream ueLi dispatcher
    if (ethernetFramed && par("registerEthernetProtocol").boolValue()) {
        registerProtocol(Protocol::ethernetMac, gate("out"), gate("in"));
    }

    EV_INFO << "FrerRecovery: initialised — primary DSCPs={";
    for (int d : frerStreamDscpSet)
        EV_INFO << d << ",";
    EV_INFO << "} replicaDscp=" << replicaDscp
            << " windowSize=" << windowSize
            << " windowTimeout=" << windowTimeout << endl;
}

// ============================================================================
// Message handling
// ============================================================================

void FrerRecovery::handleMessage(cMessage *msg)
{
    // --- Self-message: stream idle timeout ---
    if (msg->isSelfMessage()) {
        uint16_t streamId = static_cast<uint16_t>(msg->getKind());
        EV_INFO << "FrerRecovery: timeout for stream " << streamId
                << ", resetting window" << endl;
        resetStream(streamId);
        return;
    }

    auto pkt = check_and_cast<Packet *>(msg);

    // --- Step 1: Strip Ethernet framing to access IPv4 header ---
    inet::Ptr<const EthernetMacHeader> ethHdr;
    inet::Ptr<const EthernetFcs> fcs;

    if (ethernetFramed) {
        ethHdr = pkt->popAtFront<EthernetMacHeader>();
        fcs    = pkt->popAtBack<EthernetFcs>(B(4));
    }

    const auto ipHdr = streamMap.empty() ? pkt->peekAtFront<Ipv4Header>() :
        (pkt->getDataLength() > b(0) ? dynamicPtrCast<const Ipv4Header>(pkt->peekAtFront<Chunk>()) : nullptr);
    const auto *entry = ipHdr && !streamMap.empty() ? streamMap.find(*pkt, *ipHdr) : nullptr;
    int dscp = ipHdr ? ipHdr->getDscp() : -1;
    bool isFragment = ipHdr && (ipHdr->getMoreFragments() || ipHdr->getFragmentOffset() > 0);
    const bool legacyEligible = streamMap.empty() &&
        (frerStreamDscpSet.count(dscp) > 0 || dscp == replicaDscp);
    Ptr<const simu5g::FrerSequenceHeader> frerHdr;
    if (legacyEligible && !isFragment && pkt->getDataLength() >= B(4))
        frerHdr = dynamicPtrCast<const simu5g::FrerSequenceHeader>(pkt->peekAtBack<Chunk>(B(4)));
    if (entry && ipHdr->getTotalLengthField() >= ipHdr->getChunkLength() + B(8) + B(4)) {
        frerHdr = dynamicPtrCast<const simu5g::FrerSequenceHeader>(
            pkt->peekDataAt<Chunk>(ipHdr->getTotalLengthField() - B(4), B(4)));
    }
    const bool isFrer = legacyEligible || frerHdr;

    if (!isFrer) {
        // Restore framing for packets outside this recovery instance.
        if (ethernetFramed) {
            pkt->insertAtFront(ethHdr);
            pkt->insertAtBack(fcs);
        }
        numPassedThrough++;
        emit(passedThroughSignal, numPassedThrough);
        send(pkt, outGateId);
        return;
    }

    uint16_t streamId;
    uint16_t seqNum;
    const bool isReplica = dscp == replicaDscp;
    if (frerHdr) {
        streamId = frerHdr->getStreamId();
        seqNum = frerHdr->getSequenceNumber();
        if (entry && (streamId != entry->streamId || (!isReplica && dscp != entry->primaryDscp)))
            throw cRuntimeError("FRER trailer (stream %d, DSCP %d) disagrees with streamMap (stream %d, primary DSCP %d)",
                                streamId, dscp, entry->streamId, entry->primaryDscp);
        if (entry)
            pkt->setBackOffset(pkt->getFrontOffset() + ipHdr->getTotalLengthField());
        pkt->popAtBack<simu5g::FrerSequenceHeader>(B(4));
    }
    else {
        // Fallback: use IPv4 Identification field
        seqNum = ipHdr->getIdentification();

        // The legacy replica mark identifies only one primary DSCP.
        if (isReplica) {
            streamId = frerStreamDscpSet.empty()
                           ? 0
                           : static_cast<uint16_t>(*frerStreamDscpSet.begin());
        } else {
            streamId = static_cast<uint16_t>(dscp);
        }

        EV_INFO << "FrerRecovery: fallback to IPv4 ID, stream="
                << streamId << " seq=" << seqNum
                << (isFragment ? " (fragment)" : " (no trailer)") << endl;
    }

    // --- Step 4: Vector Recovery Algorithm ---
    RecoveryResult result = recoverSequence(streamId, seqNum, dscp);

    switch (result) {

    case ACCEPT: {
        int primaryDscp = entry ? entry->primaryDscp : streamId;
        if (entry || isReplica) {
            auto ipHdrMut = pkt->removeAtFront<Ipv4Header>();
            if (entry)
                ipHdrMut->setTotalLengthField(ipHdrMut->getTotalLengthField() - B(4));
            ipHdrMut->setDscp(primaryDscp);
            if (entry)
                ipHdrMut->updateChecksum();
            pkt->insertAtFront(ipHdrMut);
        }
        if (isReplica) {
            numRecoveredReplica++;
            emit(recoveredFromReplicaSignal, numRecoveredReplica);

            EV_INFO << "FrerRecovery: ACCEPT stream=" << streamId
                    << " seq=" << seqNum << " source=REPLICA"
                    << " (DSCP " << dscp << " -> " << primaryDscp << ")"
                    << (frerHdr ? " [trailer]" : " [IPv4 ID]") << endl;
        }
        else {
            numRecoveredPrimary++;
            emit(recoveredFromPrimarySignal, numRecoveredPrimary);

            EV_INFO << "FrerRecovery: ACCEPT stream=" << streamId
                    << " seq=" << seqNum << " source=PRIMARY"
                    << (frerHdr ? " [trailer]" : " [IPv4 ID]") << endl;
        }

        // Restore Ethernet framing and forward to DsTtTranslator
        if (ethernetFramed) {
            pkt->insertAtFront(ethHdr);
            pkt->insertAtBack(fcs);
        }
        rescheduleTimeout(streamId);
        send(pkt, outGateId);
        break;
    }

    case DUPLICATE:
        numDuplicatesDropped++;
        emit(duplicatesDroppedSignal, numDuplicatesDropped);
        EV_INFO << "FrerRecovery: DUPLICATE stream=" << streamId
                << " seq=" << seqNum << ", dropping" << endl;
        delete pkt;
        break;

    case WINDOW_OVERRUN:
        numWindowOverruns++;
        emit(windowOverrunsSignal, numWindowOverruns);
        EV_INFO << "FrerRecovery: WINDOW_OVERRUN stream=" << streamId
                << " seq=" << seqNum << ", dropping" << endl;
        delete pkt;
        break;
    }
}

// ============================================================================
// IEEE 802.1CB Vector Recovery Algorithm (Annex C)
// Extended: tracks accepted DSCP per position for IP fragment support.
// ============================================================================

FrerRecovery::RecoveryResult
FrerRecovery::recoverSequence(uint16_t streamId, uint16_t seqNum, int dscp)
{
    if (streams.find(streamId) == streams.end()) {
        streams.emplace(streamId, StreamState(windowSize));
    }
    StreamState &s = streams[streamId];

    // --- First packet for this stream ---
    if (!s.active) {
        s.active = true;
        s.highestSeqSeen = seqNum;
        s.accepted.assign(windowSize, -1);
        s.accepted[seqNum % windowSize] = dscp;
        return ACCEPT;
    }

    // --- Wrapping 16-bit sequence difference ---
    int16_t diff = static_cast<int16_t>(seqNum - s.highestSeqSeen);

    if (diff > 0) {
        // Ahead of window — advance, clearing newly opened positions
        int advance = (diff <= windowSize) ? diff : windowSize;
        for (int i = 1; i <= advance; i++) {
            s.accepted[(s.highestSeqSeen + i) % windowSize] = -1;
        }
        if (diff > windowSize) {
            s.accepted.assign(windowSize, -1);
        }
        s.highestSeqSeen = seqNum;
        s.accepted[seqNum % windowSize] = dscp;
        return ACCEPT;
    }

    if (diff == 0) {
        // Same as highest — check who was accepted here
        int idx = seqNum % windowSize;
        if (s.accepted[idx] == dscp) {
            // Same copy (e.g. another fragment of the accepted datagram)
            return ACCEPT;
        }
        return DUPLICATE;
    }

    // diff < 0: behind highest
    int16_t behindBy = static_cast<int16_t>(-diff);

    if (behindBy >= windowSize) {
        return WINDOW_OVERRUN;
    }

    // Within window — check accepted array
    int idx = seqNum % windowSize;
    if (s.accepted[idx] < 0) {
        // Not yet seen — accept
        s.accepted[idx] = dscp;
        return ACCEPT;
    }
    if (s.accepted[idx] == dscp) {
        // Same copy (another fragment)
        return ACCEPT;
    }
    // Different copy — duplicate
    return DUPLICATE;
}

// ============================================================================
// Stream timeout management
// ============================================================================

void FrerRecovery::resetStream(uint16_t streamId)
{
    auto it = streams.find(streamId);
    if (it != streams.end()) {
        it->second.active = false;
        it->second.accepted.assign(windowSize, -1);
    }
}

void FrerRecovery::rescheduleTimeout(uint16_t streamId)
{
    StreamState &s = streams[streamId];

    if (!s.timeoutMsg) {
        s.timeoutMsg = new cMessage("frer-stream-timeout");
        s.timeoutMsg->setKind(static_cast<int>(streamId));
    }

    if (s.timeoutMsg->isScheduled())
        cancelEvent(s.timeoutMsg);

    scheduleAfter(windowTimeout, s.timeoutMsg);
}

// ============================================================================
// Cleanup
// ============================================================================

void FrerRecovery::finish()
{
    EV_INFO << "FrerRecovery stats:"
            << " recoveredPrimary=" << numRecoveredPrimary
            << " recoveredReplica=" << numRecoveredReplica
            << " duplicatesDropped=" << numDuplicatesDropped
            << " windowOverruns=" << numWindowOverruns
            << " passedThrough=" << numPassedThrough << endl;

    for (auto &pair : streams) {
        if (pair.second.timeoutMsg) {
            cancelAndDelete(pair.second.timeoutMsg);
            pair.second.timeoutMsg = nullptr;
        }
    }
}
