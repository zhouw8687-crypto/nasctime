#ifndef __NASCTIME_FRERSTREAMMAP_H
#define __NASCTIME_FRERSTREAMMAP_H

#include <cstdint>
#include <map>

#include "inet/common/packet/Packet.h"
#include "inet/networklayer/ipv4/Ipv4Header_m.h"

// One destination-port namespace per directional FRER instance.
class FrerStreamMap
{
  public:
    struct Entry {
        uint16_t streamId;
        int primaryDscp;
    };

  private:
    std::map<int, Entry> streamsByPort;

  public:
    void load(omnetpp::cPar& config, int replicaDscp);
    bool empty() const { return streamsByPort.empty(); }
    const Entry *find(const inet::Packet& packet, const inet::Ipv4Header& ip, inet::b ipOffset = inet::b(0)) const;
};

#endif
