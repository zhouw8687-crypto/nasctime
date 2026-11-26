#include <fstream>
#include <optional>
#include <string>

#include <nlohmann/json.hpp>

#include "inet/queueing/queue/PacketQueue.h"
#include "simu5g/stack/mac/LteMacBase.h"
#include "simu5g/stack/mac/buffer/LteMacBuffer.h"
#include "nasctime/control/ControlledDlScheduler.h"
#include "nasctime/control/ControllerConnection.h"
#include "nasctime/control/FlowPolicer.h"
#include "nasctime/control/QbvPort.h"

namespace nasctime::control {

using namespace omnetpp;

namespace {

constexpr int protocolVersion = 1;
bool hasInteger(const json& message, const char *key)
{
    return message.contains(key) && message.at(key).is_number_integer();
}

struct PolicyUpdate
{
    std::optional<int> rate;
    std::optional<int> window;
    std::optional<int> bands;
    const char *changedReason;
    const char *unchangedReason;
};

std::optional<int> boundedInteger(const json& message, const char *key, int limit, int upperLimit)
{
    if (!hasInteger(message, key))
        return std::nullopt;
    const auto value = message.at(key).get<double>();
    if (value < limit || value > upperLimit)
        return std::nullopt;
    return static_cast<int>(value);
}

class DeliveryCounter : public cListener
{
  public:
    std::int64_t packets = 0;
    std::int64_t bytes = 0;

    void receiveSignal(cComponent *, simsignal_t, cObject *value, cObject *) override
    {
        const auto *packet = check_and_cast<const inet::Packet *>(value);
        packets++;
        bytes += packet->getByteLength();
    }

    json snapshot() const { return {{"received_packets", packets}, {"received_payload_bytes", bytes}}; }
};

} // namespace

class ControllerBridge : public cSimpleModule
{
    FlowPolicer *policer = nullptr;
    simu5g::LteMacBase *mac = nullptr;
    inet::queueing::PacketQueue *priorityQueue = nullptr;
    inet::queueing::PacketQueue *backgroundQueue = nullptr;
    std::optional<QbvPort> qbvPort;
    ControlledDlScheduler *ranScheduler = nullptr;
    DeliveryCounter priorityDelivery;
    DeliveryCounter backgroundDelivery;
    Connection connection;
    std::ofstream trace;
    cMessage *tick = nullptr;
    simtime_t interval;
    simtime_t stopTime;
    bool requireController = false;
    int requestId = 0;
    int generation = 0;

    void initialize() override;
    void handleMessage(cMessage *) override;
    json observe() const;
    std::optional<PolicyUpdate> parseUpdate(const json& action) const;
    json execute(const json& decision);
    void log(const json& message);

  public:
    ~ControllerBridge() override { cancelAndDelete(tick); }
};

Define_Module(ControllerBridge);

void ControllerBridge::initialize()
{
    const auto find = [this](const char *parameter) {
        return getParentModule()->getModuleByPath(par(parameter).stringValue());
    };
    policer = check_and_cast<FlowPolicer *>(find("policerModule"));
    mac = check_and_cast<simu5g::LteMacBase *>(find("ranMacModule"));
    priorityQueue = check_and_cast<inet::queueing::PacketQueue *>(find("priorityQueueModule"));
    backgroundQueue = check_and_cast<inet::queueing::PacketQueue *>(find("backgroundQueueModule"));
    if (!par("transportShaperModule").stdstringValue().empty())
        qbvPort.emplace().bind(find("transportShaperModule"));
    if (!par("ranSchedulerModule").stdstringValue().empty())
        ranScheduler = check_and_cast<ControlledDlScheduler *>(find("ranSchedulerModule"));
    find("prioritySinkModule")->subscribe("packetReceived", &priorityDelivery);
    find("backgroundSinkModule")->subscribe("packetReceived", &backgroundDelivery);

    const simtime_t startTime = par("startTime");
    interval = par("sampleInterval");
    stopTime = par("stopTime");
    if (startTime < SIMTIME_ZERO || interval <= SIMTIME_ZERO || stopTime < startTime)
        throw cRuntimeError("Invalid controller sampling times");

    trace.open(par("traceFile").stringValue());
    if (!trace)
        throw cRuntimeError("Cannot open controller trace '%s'", par("traceFile").stringValue());
    requireController = par("requireController").boolValue();
    if (requireController) {
        const auto port = par("port").intValue();
        const auto timeoutMs = par("ioTimeoutMs").intValue();
        if (port < 1 || port > 65535 || timeoutMs < 1 || timeoutMs > 60000)
            throw cRuntimeError("Invalid controller port or I/O timeout");
        connection.connectTo(port, timeoutMs);
    }

    tick = new cMessage("controllerSample");
    tick->setSchedulingPriority(10);
    scheduleAt(startTime, tick);
}

json ControllerBridge::observe() const
{
    std::int64_t macVirtualBufferBytes = 0;
    for (const auto cid : mac->getActiveMacBufferCids())
        macVirtualBufferBytes += mac->getMacBuffer(cid)->getQueueOccupancy();

    const auto& counts = policer->getCounters();
    json observation = {
        {"version", protocolVersion}, {"type", "observation"}, {"request_id", requestId},
        {"sim_time_ns", simTime().inUnit(SIMTIME_NS)}, {"generation", generation},
        {"ran", {{"node", "gnb1"}, {"dl_mac_virtual_buffer_bytes", macVirtualBufferBytes}}},
        {"transport", {{"port", "NE1.eth[1]"},
                       {"priority_queue_packets", priorityQueue->getNumPackets()},
                       {"background_queue_packets", backgroundQueue->getNumPackets()}}},
        {"core", {{"node", "upf"}, {"flow_id", policer->getFlowId()},
                  {"rate_bps", policer->getRateBps()}, {"admitted_packets", counts.admittedPackets},
                  {"dropped_packets", counts.droppedPackets}, {"admitted_ip_bytes", counts.admittedBytes},
                  {"dropped_ip_bytes", counts.droppedBytes}}},
        {"delivery", {{"node", "ue[0]"}, {"priority", priorityDelivery.snapshot()},
                      {"background", backgroundDelivery.snapshot()}}}
    };
    if (qbvPort) {
        observation["transport"]["cycle_us"] = QbvPort::cycleUs;
        observation["transport"]["priority_window_us"] = qbvPort->getPriorityWindowUs();
        observation["transport"]["qbv_update_allowed"] = qbvPort->canApplyNow();
    }
    if (ranScheduler) {
        observation["ran"]["dl_band_budget"] = ranScheduler->getBandBudget();
        observation["ran"]["dl_max_bands"] = ranScheduler->getMaxBands();
        observation["ran"]["dl_last_slot_allocated_blocks"] = ranScheduler->getLastSlotAllocatedBlocks();
    }
    return observation;
}

std::optional<PolicyUpdate> ControllerBridge::parseUpdate(const json& action) const
{
    if (!action.is_object() || !action.contains("type"))
        return std::nullopt;

    const auto& type = action.at("type");
    const auto rate = boundedInteger(action, "rate_bps", 1, FlowPolicer::maxRateBps);
    const auto window = boundedInteger(action, "priority_window_us", QbvPort::minPriorityUs, QbvPort::maxPriorityUs);
    const auto bands = ranScheduler ? boundedInteger(action, "bands", 1, ranScheduler->getMaxBands()) : std::nullopt;

    if (type == "set_upf_rate" && rate && action.contains("flow_id") && action.at("flow_id") == policer->getFlowId())
        return PolicyUpdate{rate, {}, {}, "rate_changed", "rate_already_active"};
    if (type == "set_ne_gate" && qbvPort && window && action.contains("port") && action.at("port") == "NE1.eth[1]")
        return PolicyUpdate{{}, window, {}, "gate_window_changed", "window_already_active"};
    if (type == "set_ran_dl_budget" && bands && action.contains("node") && action.at("node") == "gnb1")
        return PolicyUpdate{{}, {}, bands, "band_budget_changed", "budget_already_active"};
    if (type == "apply_cross_domain" && qbvPort && rate && window && bands)
        return PolicyUpdate{rate, window, bands, "policy_changed", "policy_already_active"};
    return std::nullopt;
}

json ControllerBridge::execute(const json& decision)
{
    const char *status = "rejected";
    const char *reason = "invalid_decision";
    json changed = json::array();
    const bool validEnvelope = decision.is_object() && hasInteger(decision, "version") &&
            decision.at("version") == protocolVersion && decision.contains("type") &&
            decision.at("type") == "decision" && hasInteger(decision, "request_id") &&
            hasInteger(decision, "base_generation") && decision.contains("action");
    if (validEnvelope) {
        const auto& action = decision.at("action");
        if (decision.at("request_id") != requestId)
            reason = "request_mismatch";
        else if (decision.at("base_generation") != generation)
            reason = "generation_mismatch";
        else if (action.is_null()) {
            status = "noop";
            reason = "no_action";
        }
        else if (const auto update = parseUpdate(action)) {
            if (update->window && !qbvPort->canApplyNow())
                reason = "outside_qbv_cycle_boundary";
            else {
                if (update->window && *update->window != qbvPort->getPriorityWindowUs()) {
                    qbvPort->setPriorityWindowUs(*update->window);
                    changed.push_back("transport");
                }
                if (update->bands && *update->bands != ranScheduler->getBandBudget()) {
                    ranScheduler->setBandBudget(*update->bands);
                    changed.push_back("ran");
                }
                if (update->rate && *update->rate != policer->getRateBps()) {
                    policer->setRateBps(*update->rate);
                    changed.push_back("core");
                }
                if (changed.empty()) {
                    status = "unchanged";
                    reason = update->unchangedReason;
                }
                else {
                    generation++;
                    status = "applied";
                    reason = update->changedReason;
                }
            }
        }
        else
            reason = "invalid_action";
    }
    json ack = {{"version", protocolVersion}, {"type", "ack"}, {"request_id", requestId},
                {"sim_time_ns", simTime().inUnit(SIMTIME_NS)}, {"generation", generation},
                {"status", status}, {"reason", reason}, {"flow_id", policer->getFlowId()},
                {"rate_bps", policer->getRateBps()}};
    if (qbvPort)
        ack["priority_window_us"] = qbvPort->getPriorityWindowUs();
    if (ranScheduler)
        ack["dl_band_budget"] = ranScheduler->getBandBudget();
    if (qbvPort && ranScheduler)
        ack["changed_domains"] = std::move(changed);
    return ack;
}

void ControllerBridge::log(const json& message)
{
    trace << message.dump() << std::endl;
    if (!trace)
        throw cRuntimeError("Cannot write controller trace");
}

void ControllerBridge::handleMessage(cMessage *)
{
    requestId++;
    const auto observation = observe();
    log(observation);
    if (requireController) {
        const auto startedAt = WallClock::now();
        connection.write(observation);
        const auto decision = connection.read();
        log({{"type", "received_decision"}, {"request_id", requestId},
             {"sim_time_ns", simTime().inUnit(SIMTIME_NS)},
             {"wait_wall_us", std::chrono::duration_cast<std::chrono::microseconds>(WallClock::now() - startedAt).count()},
             {"decision", decision.is_discarded() ? json(nullptr) : decision}});
        const auto ack = execute(decision);
        log(ack);
        connection.write(ack);
    }
    if (simTime() + interval <= stopTime)
        scheduleAt(simTime() + interval, tick);
}

} // namespace nasctime::control
