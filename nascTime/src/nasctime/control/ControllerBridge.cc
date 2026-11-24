#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstring>
#include <fstream>
#include <optional>
#include <string>

#include <nlohmann/json.hpp>

#include "inet/queueing/queue/PacketQueue.h"
#include "simu5g/stack/mac/LteMacBase.h"
#include "simu5g/stack/mac/buffer/LteMacBuffer.h"
#include "nasctime/control/FlowPolicer.h"
#include "nasctime/control/QbvPort.h"

namespace nasctime::control {

using namespace omnetpp;
using nlohmann::json;
using WallClock = std::chrono::steady_clock;

namespace {

constexpr int protocolVersion = 1;
constexpr std::size_t maxMessageBytes = 16384;

void socketError(const char *operation)
{
    throw cRuntimeError("Controller socket %s: %s", operation, std::strerror(errno));
}

class Connection
{
    int fd = -1;
    int timeoutMs = 0;
    std::string pending;

  public:
    ~Connection() { if (fd >= 0) close(fd); }

    void connectTo(int port, int timeout)
    {
        timeoutMs = timeout;
        fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
        if (fd < 0)
            socketError("create");
        const timeval wallTimeout{timeout / 1000, (timeout % 1000) * 1000};
        if (setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &wallTimeout, sizeof(wallTimeout)) < 0)
            socketError("set write timeout");
        const int noDelay = 1;
        if (setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &noDelay, sizeof(noDelay)) < 0)
            socketError("disable Nagle buffering");
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        address.sin_port = htons(port);
        if (connect(fd, reinterpret_cast<sockaddr *>(&address), sizeof(address)) < 0)
            socketError("connect to localhost");
    }

    void write(const json& message) const
    {
        const std::string line = message.dump() + '\n';
        for (std::size_t offset = 0; offset < line.size();) {
            const auto count = send(fd, line.data() + offset, line.size() - offset, MSG_NOSIGNAL);
            if (count < 0 && errno == EINTR)
                continue;
            if (count <= 0)
                socketError("write");
            offset += count;
        }
    }

    json read()
    {
        const auto deadline = WallClock::now() + std::chrono::milliseconds(timeoutMs);
        while (true) {
            const auto newline = pending.find('\n');
            if (newline != std::string::npos && newline <= maxMessageBytes) {
                auto message = json::parse(pending.begin(), pending.begin() + newline, nullptr, false);
                pending.erase(0, newline + 1);
                return message;
            }
            if (pending.size() > maxMessageBytes)
                throw cRuntimeError("Controller message exceeds %zu bytes", maxMessageBytes);
            const auto remaining = std::chrono::ceil<std::chrono::milliseconds>(deadline - WallClock::now());
            if (remaining.count() <= 0)
                throw cRuntimeError("Controller decision timed out");
            pollfd ready{fd, POLLIN, 0};
            const auto result = poll(&ready, 1, remaining.count());
            if (result < 0 && errno == EINTR)
                continue;
            if (result < 0)
                socketError("poll");
            if (result == 0)
                throw cRuntimeError("Controller decision timed out");
            char buffer[4096];
            const auto count = recv(fd, buffer, sizeof(buffer), 0);
            if (count < 0 && errno == EINTR)
                continue;
            if (count < 0)
                socketError("read");
            if (count == 0)
                throw cRuntimeError("Controller disconnected before returning a decision");
            pending.append(buffer, count);
        }
    }
};

bool hasInteger(const json& message, const char *key)
{
    return message.contains(key) && message.at(key).is_number_integer();
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
    return observation;
}

json ControllerBridge::execute(const json& decision)
{
    const char *status = "rejected";
    const char *reason = "invalid_decision";
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
        else if (action.is_object() && action.contains("type")) {
            reason = "invalid_action";
            const auto& type = action.at("type");
            if (type == "set_upf_rate" && action.contains("flow_id") &&
                    action.at("flow_id") == policer->getFlowId() && hasInteger(action, "rate_bps") &&
                    action.at("rate_bps").get<double>() >= 1 &&
                    action.at("rate_bps").get<double>() <= FlowPolicer::maxRateBps) {
                const int rate = action.at("rate_bps").get<int>();
                if (rate != policer->getRateBps()) {
                    policer->setRateBps(rate);
                    status = "applied";
                    reason = "rate_changed";
                }
                else {
                    status = "unchanged";
                    reason = "rate_already_active";
                }
            }
            else if (type == "set_ne_gate" && qbvPort && action.contains("port") &&
                    action.at("port") == "NE1.eth[1]" && hasInteger(action, "priority_window_us") &&
                    action.at("priority_window_us").get<double>() >= QbvPort::minPriorityUs &&
                    action.at("priority_window_us").get<double>() <= QbvPort::maxPriorityUs) {
                const int window = action.at("priority_window_us").get<int>();
                if (!qbvPort->canApplyNow())
                    reason = "outside_qbv_cycle_boundary";
                else if (window != qbvPort->getPriorityWindowUs()) {
                    qbvPort->setPriorityWindowUs(window);
                    status = "applied";
                    reason = "gate_window_changed";
                }
                else {
                    status = "unchanged";
                    reason = "window_already_active";
                }
            }
        }
        else
            reason = "invalid_action";
    }
    if (std::strcmp(status, "applied") == 0)
        generation++;
    json ack = {{"version", protocolVersion}, {"type", "ack"}, {"request_id", requestId},
                {"sim_time_ns", simTime().inUnit(SIMTIME_NS)}, {"generation", generation},
                {"status", status}, {"reason", reason}, {"flow_id", policer->getFlowId()},
                {"rate_bps", policer->getRateBps()}};
    if (qbvPort)
        ack["priority_window_us"] = qbvPort->getPriorityWindowUs();
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
