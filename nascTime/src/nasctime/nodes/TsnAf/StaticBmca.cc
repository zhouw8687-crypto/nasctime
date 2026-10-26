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

#include "nasctime/nodes/TsnAf/StaticBmca.h"

Define_Module(StaticBmca);

void StaticBmca::initialize(int stage)
{
    cSimpleModule::initialize(stage);

    if (stage == inet::INITSTAGE_LOCAL) {
        bmcaEstablishedSignal = registerSignal("bmcaEstablished");
        bmcaValidationErrorSignal = registerSignal("bmcaValidationError");

        // Load grandmaster config
        grandmaster.moduleName = par("grandmasterModule").stdstringValue();
        grandmaster.priority1 = par("grandmasterPriority1");
        grandmaster.priority2 = par("grandmasterPriority2");
        grandmaster.clockClass = par("clockClass");
        grandmaster.clockAccuracy = par("clockAccuracy");
        grandmaster.offsetScaledLogVariance = par("offsetScaledLogVariance");

        transparentClockEnabled = par("transparentClockEnabled");
        correctionFieldSupport = par("correctionFieldSupport");

        EV_INFO << "StaticBmca: initialized" << endl;
    }
    else if (stage == inet::INITSTAGE_APPLICATION_LAYER) {
        loadSpanningTree();
        validateTopology();

        if (validationErrors == 0) {
            emit(bmcaEstablishedSignal, (long)spanningTree.size());
            EV_INFO << "StaticBmca: topology established with "
                    << spanningTree.size() << " nodes" << endl;
        }
    }
}

void StaticBmca::handleMessage(cMessage *msg)
{
    delete msg;
}

void StaticBmca::loadSpanningTree()
{
    const cValueArray *arr = check_and_cast_nullable<const cValueArray *>(
        par("spanningTree").objectValue());

    if (!arr || arr->size() == 0) {
        EV_INFO << "StaticBmca: no spanning tree configured, "
                << "using module-level gPTP parameters" << endl;
        return;
    }

    for (int i = 0; i < (int)arr->size(); i++) {
        const cValueMap *entry = check_and_cast<const cValueMap *>(
            arr->get(i).objectValue());

        SpanningTreeEntry ste;
        ste.moduleName = entry->get("node").stdstringValue();
        ste.role = parseRole(entry->get("role").stdstringValue());

        if (entry->containsKey("slavePort"))
            ste.slavePort = entry->get("slavePort").stdstringValue();

        if (entry->containsKey("masterPorts")) {
            const cValueArray *ports = check_and_cast<const cValueArray *>(
                entry->get("masterPorts").objectValue());
            for (int j = 0; j < (int)ports->size(); j++)
                ste.masterPorts.push_back(ports->get(j).stdstringValue());
        }

        spanningTree.push_back(ste);

        EV_INFO << "StaticBmca: node " << ste.moduleName
                << " role=" << roleToString(ste.role)
                << " slavePort=" << ste.slavePort
                << " masterPorts=" << ste.masterPorts.size() << endl;
    }

    // Build lookup map
    for (auto& ste : spanningTree)
        nodeRoleMap[ste.moduleName] = &ste;

    // Add 5GS bridge as transparent clock
    if (transparentClockEnabled) {
        SpanningTreeEntry bridge;
        bridge.moduleName = "5gs_bridge";
        bridge.role = GptpRole::TRANSPARENT;
        spanningTree.push_back(bridge);
        nodeRoleMap["5gs_bridge"] = &spanningTree.back();

        EV_INFO << "StaticBmca: 5GS bridge registered as transparent clock"
                << " (correctionField=" << (correctionFieldSupport ? "yes" : "no")
                << ")" << endl;
    }
}

void StaticBmca::validateTopology()
{
    EV_INFO << "StaticBmca: validating topology..." << endl;

    // Check grandmaster exists
    if (grandmaster.moduleName.empty()) {
        EV_WARN << "StaticBmca: WARNING — no grandmaster configured" << endl;
        validationErrors++;
        emit(bmcaValidationErrorSignal, 1L);
    } else {
        // Verify grandmaster module exists in the network
        cModule *gmModule = getModuleByPath(grandmaster.moduleName.c_str());
        if (!gmModule) {
            EV_WARN << "StaticBmca: WARNING — grandmaster module '"
                    << grandmaster.moduleName << "' not found" << endl;
            validationErrors++;
            emit(bmcaValidationErrorSignal, 2L);
        } else {
            EV_INFO << "StaticBmca: grandmaster = " << grandmaster.moduleName
                    << " (priority1=" << grandmaster.priority1
                    << ", clockClass=" << grandmaster.clockClass << ")" << endl;
        }
    }

    // Check for exactly one master in spanning tree
    int masterCount = 0;
    int bridgeCount = 0;
    int slaveCount = 0;
    int transparentCount = 0;

    for (const auto& ste : spanningTree) {
        switch (ste.role) {
            case GptpRole::MASTER: masterCount++; break;
            case GptpRole::BRIDGE: bridgeCount++; break;
            case GptpRole::SLAVE: slaveCount++; break;
            case GptpRole::TRANSPARENT: transparentCount++; break;
        }
    }

    if (masterCount == 0 && !spanningTree.empty()) {
        EV_WARN << "StaticBmca: WARNING — no MASTER node in spanning tree" << endl;
        validationErrors++;
        emit(bmcaValidationErrorSignal, 3L);
    }
    if (masterCount > 1) {
        EV_WARN << "StaticBmca: WARNING — multiple MASTER nodes ("
                << masterCount << ") in spanning tree" << endl;
        validationErrors++;
        emit(bmcaValidationErrorSignal, 4L);
    }
    if (slaveCount == 0 && !spanningTree.empty()) {
        EV_WARN << "StaticBmca: WARNING — no SLAVE node in spanning tree" << endl;
        validationErrors++;
        emit(bmcaValidationErrorSignal, 5L);
    }

    // Check that 5GS bridge has correctionField support
    if (transparentCount > 0 && !correctionFieldSupport) {
        EV_WARN << "StaticBmca: WARNING — transparent clock without "
                << "correctionField support" << endl;
        validationErrors++;
        emit(bmcaValidationErrorSignal, 6L);
    }

    EV_INFO << "StaticBmca: topology validation complete — "
            << masterCount << " master, "
            << bridgeCount << " bridge, "
            << slaveCount << " slave, "
            << transparentCount << " transparent clock, "
            << validationErrors << " errors" << endl;
}

GptpRole StaticBmca::parseRole(const std::string& roleStr)
{
    if (roleStr == "MASTER") return GptpRole::MASTER;
    if (roleStr == "BRIDGE") return GptpRole::BRIDGE;
    if (roleStr == "SLAVE") return GptpRole::SLAVE;
    if (roleStr == "TRANSPARENT") return GptpRole::TRANSPARENT;
    throw cRuntimeError("StaticBmca: unknown role '%s'", roleStr.c_str());
}

std::string StaticBmca::roleToString(GptpRole role)
{
    switch (role) {
        case GptpRole::MASTER: return "MASTER";
        case GptpRole::BRIDGE: return "BRIDGE";
        case GptpRole::SLAVE: return "SLAVE";
        case GptpRole::TRANSPARENT: return "TRANSPARENT";
    }
    return "UNKNOWN";
}

GptpRole StaticBmca::getNodeRole(const std::string& moduleName) const
{
    auto it = nodeRoleMap.find(moduleName);
    if (it != nodeRoleMap.end())
        return it->second->role;
    return GptpRole::SLAVE;  // default
}

bool StaticBmca::isTransparentClock(const std::string& moduleName) const
{
    auto it = nodeRoleMap.find(moduleName);
    if (it != nodeRoleMap.end())
        return it->second->role == GptpRole::TRANSPARENT;
    return false;
}

void StaticBmca::finish()
{
    EV_INFO << "StaticBmca: clock hierarchy — grandmaster="
            << grandmaster.moduleName
            << " nodes=" << spanningTree.size()
            << " validationErrors=" << validationErrors << endl;
}
