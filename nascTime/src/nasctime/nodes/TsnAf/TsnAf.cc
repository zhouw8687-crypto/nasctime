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

#include "nasctime/nodes/TsnAf/TsnAf.h"

#include <inet/common/XMLUtils.h>

Define_Module(TsnAf);

void TsnAf::initialize(int stage)
{
    cSimpleModule::initialize(stage);

    if (stage == INITSTAGE_LOCAL) {
        portSpeedBps = par("portSpeedBps");
        numTrafficClasses = par("numTrafficClasses");

        // Parse PCP-to-QFI mapping
        std::string mapStr = par("pcpToQfiMap").stdstringValue();
        cStringTokenizer tokenizer(mapStr.c_str(), ",");
        while (tokenizer.hasMoreTokens())
            pcpToQfi.push_back(atoi(tokenizer.nextToken()));
        while (pcpToQfi.size() < 8)
            pcpToQfi.push_back(pcpToQfi.size());  // default: PCP = QFI

        bridgeDelayUpdatedSignal = registerSignal("bridgeDelayUpdated");
        streamConfiguredSignal = registerSignal("streamConfigured");
        qosViolationSignal = registerSignal("qosViolation");

        EV_INFO << "TsnAf: initialized with " << numTrafficClasses
                << " traffic classes, port speed " << portSpeedBps / 1e9 << " Gbps" << endl;
    }
    else if (stage == INITSTAGE_APPLICATION_LAYER) {
        // Find bridge modules
        nwTtModule = getModuleByPath(par("nwTtModule").stringValue());
        dsTtModule = getModuleByPath(par("dsTtModule").stringValue());
        gnbModule = getModuleByPath(par("gnbModule").stringValue());

        // Subscribe to DS-TT residence time signal
        if (dsTtModule) {
            auto *translator = dsTtModule->getSubmodule("translator");
            if (translator) {
                simsignal_t residenceSignal = registerSignal("residenceTime");
                translator->subscribe("residenceTime", this);
                EV_INFO << "TsnAf: subscribed to DS-TT residence time signal" << endl;
            }
        }

        // Load CNC configuration
        cXMLElement *xmlConfig = par("cncConfig").xmlValue();
        if (xmlConfig && xmlConfig->getFirstChild()) {
            loadCncConfig(xmlConfig);
        } else {
            EV_INFO << "TsnAf: no CNC config provided, using defaults" << endl;
        }
    }
}

void TsnAf::handleMessage(cMessage *msg)
{
    delete msg;  // no self-messages expected for now
}

void TsnAf::receiveSignal(cComponent *source, simsignal_t signalID,
                           const simtime_t& t, cObject *details)
{
    // Update bridge delay statistics from DS-TT residence time
    simtime_t delay = t;
    if (delay < delayMin) delayMin = delay;
    if (delay > delayMax) delayMax = delay;
    delaySum += delay;
    delaySamples++;

    emit(bridgeDelayUpdatedSignal, delay);

    // Update published parameters so other modules can read them
    par("bridgeDelayMin") = delayMin.dbl();
    par("bridgeDelayMax") = delayMax.dbl();
    par("bridgeDelayAvg") = (delaySum / delaySamples).dbl();

    // Check for QoS violations against stream reservations
    for (const auto& sr : streamReservations) {
        if (sr.maxLatencyMs > 0 && delay.dbl() * 1000 > sr.maxLatencyMs) {
            EV_WARN << "TsnAf: QoS VIOLATION — stream " << sr.streamId
                    << " delay " << delay.dbl() * 1000 << "ms exceeds max "
                    << sr.maxLatencyMs << "ms" << endl;
            emit(qosViolationSignal, (long)sr.streamId);
        }
    }
}

void TsnAf::loadCncConfig(cXMLElement *xmlConfig)
{
    EV_INFO << "TsnAf: loading CNC configuration" << endl;

    // Parse stream reservations
    cXMLElement *streamsElem = xmlConfig->getFirstChildWithTag("streams");
    if (streamsElem)
        parseStreamReservations(streamsElem);

    // Parse TAS gate control list
    cXMLElement *tasElem = xmlConfig->getFirstChildWithTag("gateControlList");
    if (tasElem)
        parseGateControlList(tasElem);

    // Apply configurations
    applyStreamReservations();
    applyGateControlList();
}

void TsnAf::parseStreamReservations(cXMLElement *streamsElem)
{
    cXMLElementList streamList = streamsElem->getChildrenByTagName("stream");
    for (auto *streamElem : streamList) {
        StreamReservation sr;
        sr.streamId = atoi(streamElem->getAttribute("id"));
        sr.pcp = atoi(streamElem->getAttribute("pcp"));
        sr.qfi = (sr.pcp < (int)pcpToQfi.size()) ? pcpToQfi[sr.pcp] : sr.pcp;
        sr.drbIndex = atoi(streamElem->getAttribute("drb"));
        sr.maxLatencyMs = atof(streamElem->getAttribute("maxLatencyMs"));
        sr.reservedBandwidthKbps = atof(streamElem->getAttribute("bandwidthKbps"));

        streamReservations.push_back(sr);
        emit(streamConfiguredSignal, (long)sr.streamId);

        EV_INFO << "TsnAf: stream " << sr.streamId
                << " PCP=" << sr.pcp << " QFI=" << sr.qfi
                << " DRB=" << sr.drbIndex
                << " maxLatency=" << sr.maxLatencyMs << "ms"
                << " bandwidth=" << sr.reservedBandwidthKbps << "kbps" << endl;
    }
}

void TsnAf::parseGateControlList(cXMLElement *tasElem)
{
    const char *cycleStr = tasElem->getAttribute("cycleTime");
    gateCycleTime = cycleStr ? SimTime::parse(cycleStr) : SimTime(1, SIMTIME_MS);

    cXMLElementList entries = tasElem->getChildrenByTagName("entry");
    for (auto *entryElem : entries) {
        GateControlEntry gce;
        gce.startTime = SimTime::parse(entryElem->getAttribute("start"));
        gce.duration = SimTime::parse(entryElem->getAttribute("duration"));
        gce.gateStates = (uint8_t)atoi(entryElem->getAttribute("gates"));

        gateControlList.push_back(gce);

        EV_INFO << "TsnAf: TAS entry start=" << gce.startTime
                << " duration=" << gce.duration
                << " gates=0x" << std::hex << (int)gce.gateStates << std::dec << endl;
    }

    EV_INFO << "TsnAf: loaded " << gateControlList.size()
            << " TAS entries, cycle=" << gateCycleTime << endl;
}

void TsnAf::applyStreamReservations()
{
    // Log the configuration that would be applied
    // In a full implementation, this would programmatically set
    // the gNB SDAP drbConfig and MAC scheduler parameters
    EV_INFO << "TsnAf: applying " << streamReservations.size()
            << " stream reservations" << endl;

    for (const auto& sr : streamReservations) {
        EV_INFO << "TsnAf: stream " << sr.streamId
                << " → DRB " << sr.drbIndex
                << " (QFI=" << sr.qfi << ")" << endl;
    }
}

void TsnAf::applyGateControlList()
{
    if (gateControlList.empty())
        return;

    // Log the TAS configuration
    // In a full implementation, this would configure the
    // TSN Device A's Ieee8021qTimeAwareShaper module
    EV_INFO << "TsnAf: applying TAS gate control list ("
            << gateControlList.size() << " entries, cycle="
            << gateCycleTime << ")" << endl;
}

int TsnAf::getQfiForPcp(int pcp) const
{
    if (pcp >= 0 && pcp < (int)pcpToQfi.size())
        return pcpToQfi[pcp];
    return pcp;
}

int TsnAf::getPcpForQfi(int qfi) const
{
    for (int i = 0; i < (int)pcpToQfi.size(); i++) {
        if (pcpToQfi[i] == qfi)
            return i;
    }
    return qfi;
}

simtime_t TsnAf::getBridgeDelayAvg() const
{
    if (delaySamples == 0)
        return SIMTIME_ZERO;
    return delaySum / delaySamples;
}

void TsnAf::finish()
{
    EV_INFO << "TsnAf: Bridge delay stats —"
            << " min=" << delayMin.inUnit(SIMTIME_MS) << "ms"
            << " max=" << delayMax.inUnit(SIMTIME_MS) << "ms"
            << " avg=" << getBridgeDelayAvg().inUnit(SIMTIME_MS) << "ms"
            << " samples=" << delaySamples << endl;

    EV_INFO << "TsnAf: " << streamReservations.size()
            << " stream reservations configured" << endl;
}
