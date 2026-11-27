#include <array>
#include <fstream>
#include <optional>

#include "inet/common/InitStages.h"
#include "inet/networklayer/common/InterfaceTable.h"
#include "inet/networklayer/common/L3AddressResolver.h"
#include "inet/networklayer/ipv4/Ipv4RoutingTable.h"
#include "inet/queueing/queue/PacketQueue.h"
#include "nasctime/control/ControllerConnection.h"
#include "nasctime/control/ControlledDlScheduler.h"
#include "nasctime/control/FlowPolicer.h"

namespace nasctime::control {

using namespace omnetpp;
using namespace inet;

class RouteController : public cSimpleModule
{
    struct NextHop {
        const char *id;
        NetworkInterface *interface;
        Ipv4Address address;
    };

    Ipv4RoutingTable *table = nullptr;
    Ipv4Address destination;
    std::array<NextHop, 2> paths{};
    std::array<cModule *, 2> queues{};
    ControlledDlScheduler *scheduler = nullptr;
    FlowPolicer *policer = nullptr;
    std::ofstream trace;
    Connection connection;
    cMessage *tick = nullptr;
    int request = 0;
    int generation = 0;
    bool online = false;
    simtime_t interval;
    simtime_t stopTime;

    int numInitStages() const override { return NUM_INIT_STAGES; }

    int readPath() const
    {
        const auto *route = table->findBestMatchingRoute(destination);
        if (route && route->getDestination() == destination && route->getNetmask() == Ipv4Address::ALLONES_ADDRESS) {
            for (int i = 0; i < static_cast<int>(paths.size()); ++i)
                if (route->getInterface() == paths[i].interface && route->getGateway() == paths[i].address)
                    return i;
        }
        throw cRuntimeError("NE1 has no expected /32 route to %s", destination.str().c_str());
    }

    void install(int which)
    {
        readPath();
        auto *route = table->findBestMatchingRoute(destination);
        route->setInterface(paths[which].interface);
        route->setGateway(paths[which].address);
        if (readPath() != which)
            throw cRuntimeError("Route readback disagrees with the requested path");
    }

    int backlog(int which) const
    {
        int count = 0;
        for (int index = 0; index < queues[which]->getSubmodule("queue", 0)->getVectorSize(); ++index)
            count += check_and_cast<queueing::PacketQueue *>(queues[which]->getSubmodule("queue", index))->getNumPackets();
        return count;
    }

    void writeTrace(const json& event)
    {
        trace << event.dump() << std::endl;
        if (!trace)
            throw cRuntimeError("Cannot write route control trace");
    }

    void initialize(int stage) override
    {
        if (stage != INITSTAGE_LAST)
            return;
        auto *root = getParentModule();
        table = check_and_cast<Ipv4RoutingTable *>(root->getModuleByPath("NE1.ipv4.routingTable"));
        auto *interfaces = check_and_cast<InterfaceTable *>(root->getModuleByPath("NE1.interfaceTable"));
        L3AddressResolver resolver;
        destination = resolver.resolve("gnb1%cellular").toIpv4();
        paths = {{{"direct", interfaces->findInterfaceByName("eth1"), resolver.resolve("NE3%eth1").toIpv4()},
                  {"detour", interfaces->findInterfaceByName("eth0"), resolver.resolve("NE2%eth0").toIpv4()}}};
        queues = {{root->getModuleByPath("NE1.eth[1].queue"), root->getModuleByPath("NE1.eth[0].queue")}};
        for (int i = 0; i < static_cast<int>(paths.size()); ++i)
            if (!paths[i].interface || !queues[i] || !queues[i]->getSubmodule("queue", 0))
                throw cRuntimeError("NE1 interface or egress queues are missing for %s", paths[i].id);
        // The XML preconfigures the detour's downstream hops. NE1 starts on the direct branch.
        const auto startPath = pathIndex(par("initialPath").stringValue());
        if (!startPath)
            throw cRuntimeError("Unknown initialPath");
        install(*startPath);
        if (par("manageResources").boolValue()) {
            scheduler = check_and_cast<ControlledDlScheduler *>(root->getModuleByPath("gnb1.cellularNic.mac.schedulerDl"));
            policer = check_and_cast<FlowPolicer *>(root->getModuleByPath("upf.dnPpp.ingressTC"));
        }
        const auto port = par("port").intValue();
        if (port < 0 || port > 65535)
            throw cRuntimeError("Route controller port must be in [0,65535]");
        online = par("requireController").boolValue();
        if (online && port == 0)
            throw cRuntimeError("The adaptive route case requires the external controller port");
        if (online)
            connection.connectTo(port, 3000);
        trace.open(par("traceFile").stringValue());
        if (!trace)
            throw cRuntimeError("Cannot open route control trace");
        const simtime_t startTime = par("startTime").doubleValue();
        interval = par("sampleInterval").doubleValue();
        stopTime = par("stopTime").doubleValue();
        if (startTime < simTime() || interval <= SIMTIME_ZERO || stopTime < startTime)
            throw cRuntimeError("Invalid route controller sampling times");
        tick = new cMessage("routeObservation");
        tick->setSchedulingPriority(10);
        scheduleAt(startTime, tick);
    }

    std::optional<int> pathIndex(const json& name) const
    {
        for (int i = 0; i < static_cast<int>(paths.size()); ++i)
            if (name == paths[i].id)
                return i;
        return {};
    }

    std::optional<int> boundedInt(const json& action, const char *key, int maximum) const
    {
        if (!action.contains(key) || !action[key].is_number_integer())
            return {};
        const auto number = action[key].get<double>();
        if (number < 1 || number > maximum)
            return {};
        return static_cast<int>(number);
    }

    void recordResources(json& message) const
    {
        if (scheduler && policer) {
            message["ran_bands"] = scheduler->getBandBudget();
            message["upf_video_rate_bps"] = policer->getRateBps();
            message["upf_video_capacity_bps"] = policer->getCapacityBps();
            message["upf_video_enforced_bps"] = policer->getEnforcedRateBps();
            message["ran_last_allocated_blocks"] = scheduler->getLastSlotAllocatedBlocks();
        }
    }

    std::pair<const char *, const char *> apply(const json& action)
    {
        if (action.is_null())
            return {"noop", "no_action"};
        if (!action.is_object() || !action.contains("type") || !action.contains("path_id"))
            return {"rejected", "invalid_action"};
        const auto which = pathIndex(action["path_id"]);
        if (!which)
            return {"rejected", "unknown_path"};
        const bool changePath = *which != readPath();
        if (changePath && (!paths[*which].interface->isUp() || !paths[*which].interface->hasCarrier()))
            return {"rejected", "interface_unavailable"};

        bool changeBands = false;
        bool changeRate = false;
        std::optional<int> bands;
        std::optional<int> rate;
        if (action["type"] == "apply_route_resources") {
            if (!scheduler || !policer)
                return {"rejected", "no_resource_actuators"};
            bands = boundedInt(action, "ran_bands", scheduler->getMaxBands());
            rate = boundedInt(action, "upf_video_rate_bps", FlowPolicer::maxRateBps);
            if (!bands || !rate)
                return {"rejected", "invalid_resources"};
            changeBands = *bands != scheduler->getBandBudget();
            changeRate = *rate != policer->getRateBps();
        }
        else if (action["type"] != "set_route")
            return {"rejected", "invalid_action"};

        if (changePath)
            install(*which);
        if (changeBands)
            scheduler->setBandBudget(*bands);
        if (changeRate)
            policer->setRateBps(*rate);
        if (!changePath && !changeBands && !changeRate)
            return {"unchanged", "policy_already_active"};
        ++generation;
        return {"applied", "policy_updated"};
    }

    json execute(const json& decision)
    {
        std::pair<const char *, const char *> result{"rejected", "invalid_decision"};
        if (decision.is_object() && decision.contains("version") && decision["version"] == 1
                && decision.contains("type") && decision["type"] == "decision"
                && decision.contains("request_id") && decision["request_id"] == request
                && decision.contains("base_generation") && decision["base_generation"] == generation
                && decision.contains("action"))
            result = apply(decision["action"]);

        const auto& current = paths[readPath()];
        json ack = {{"version", 1}, {"type", "ack"}, {"request_id", request}, {"generation", generation},
                {"sim_time_ns", simTime().inUnit(SIMTIME_NS)}, {"status", result.first}, {"reason", result.second},
                {"path_id", current.id}, {"interface", current.interface->getInterfaceName()},
                {"gateway", current.address.str()}, {"destination", destination.str()}};
        recordResources(ack);
        return ack;
    }

    void handleMessage(cMessage *) override
    {
        json observation = {{"version", 1}, {"type", "observation"}, {"request_id", ++request},
                {"generation", generation}, {"sim_time_ns", simTime().inUnit(SIMTIME_NS)},
                {"path_id", paths[readPath()].id}, {"direct_queue_packets", backlog(0)},
                {"detour_queue_packets", backlog(1)}};
        recordResources(observation);
        writeTrace(observation);
        if (online) {
            connection.write(observation);
            auto decision = connection.read();
            writeTrace({{"type", "received_decision"}, {"request_id", request},
                        {"sim_time_ns", simTime().inUnit(SIMTIME_NS)},
                        {"decision", decision.is_discarded() ? json(nullptr) : decision}});
            const auto ack = execute(decision);
            writeTrace(ack);
            connection.write(ack);
        }
        const SimTime next = simTime() + interval;
        if (next <= stopTime)
            scheduleAt(next, tick);
    }

  public:
    ~RouteController() override { cancelAndDelete(tick); }
};

Define_Module(RouteController);

} // namespace nasctime::control
