#pragma once

#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstring>
#include <string>

#include <nlohmann/json.hpp>
#include <omnetpp.h>

namespace nasctime::control {

using nlohmann::json;
using WallClock = std::chrono::steady_clock;

constexpr std::size_t maxMessageBytes = 16384;

inline void socketError(const char *operation)
{
    throw omnetpp::cRuntimeError("Controller socket %s: %s", operation, std::strerror(errno));
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
                throw omnetpp::cRuntimeError("Controller message exceeds %zu bytes", maxMessageBytes);
            const auto remaining = std::chrono::ceil<std::chrono::milliseconds>(deadline - WallClock::now());
            if (remaining.count() <= 0)
                throw omnetpp::cRuntimeError("Controller decision timed out");
            pollfd ready{fd, POLLIN, 0};
            const auto result = poll(&ready, 1, remaining.count());
            if (result < 0 && errno == EINTR)
                continue;
            if (result < 0)
                socketError("poll");
            if (result == 0)
                throw omnetpp::cRuntimeError("Controller decision timed out");
            char buffer[4096];
            const auto count = recv(fd, buffer, sizeof(buffer), 0);
            if (count < 0 && errno == EINTR)
                continue;
            if (count < 0)
                socketError("read");
            if (count == 0)
                throw omnetpp::cRuntimeError("Controller disconnected before returning a decision");
            pending.append(buffer, count);
        }
    }
};

} // namespace nasctime::control
