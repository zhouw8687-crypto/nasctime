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

#ifndef __SIMU5G_1_4_1_SDAP_STATICBMCA_H_
#define __SIMU5G_1_4_1_SDAP_STATICBMCA_H_

#include <omnetpp.h>
#include <inet/common/InitStages.h>
#include <map>
#include <vector>
#include <string>

using namespace omnetpp;

enum class GptpRole {
    MASTER,
    BRIDGE,
    SLAVE,
    TRANSPARENT  // 5GS bridge
};

struct SpanningTreeEntry {
    std::string moduleName;
    GptpRole role;
    std::vector<std::string> masterPorts;
    std::string slavePort;
};

struct GrandmasterInfo {
    std::string moduleName;
    int priority1;
    int priority2;
    int clockClass;
    int clockAccuracy;
    int offsetScaledLogVariance;
};

class StaticBmca : public cSimpleModule
{
  protected:
    GrandmasterInfo grandmaster;
    std::vector<SpanningTreeEntry> spanningTree;
    std::map<std::string, SpanningTreeEntry*> nodeRoleMap;

    bool transparentClockEnabled;
    bool correctionFieldSupport;

    simsignal_t bmcaEstablishedSignal;
    simsignal_t bmcaValidationErrorSignal;

    int validationErrors = 0;

  protected:
    virtual void initialize(int stage) override;
    virtual int numInitStages() const override { return inet::NUM_INIT_STAGES; }
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

    void loadSpanningTree();
    void validateTopology();
    GptpRole parseRole(const std::string& roleStr);
    std::string roleToString(GptpRole role);

  public:
    // API for other modules
    const GrandmasterInfo& getGrandmasterInfo() const { return grandmaster; }
    GptpRole getNodeRole(const std::string& moduleName) const;
    bool isTransparentClock(const std::string& moduleName) const;
    bool hasGrandmaster() const { return !grandmaster.moduleName.empty(); }
    const std::vector<SpanningTreeEntry>& getSpanningTree() const { return spanningTree; }
};

#endif
