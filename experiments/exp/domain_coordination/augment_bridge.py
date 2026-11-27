"""Add telemetry to a private build copy of the existing route control bridge."""

import argparse
from pathlib import Path

HEADERS = """#include "simu5g/stack/mac/LteMacBase.h"
#include "simu5g/stack/mac/buffer/LteMacBuffer.h"
"""

TELEMETRY = """        if (scheduler && policer) {
            auto *mac = check_and_cast<simu5g::LteMacBase *>(
                    scheduler->getParentModule());
            std::int64_t backlogBytes = 0;
            for (const auto cid : mac->getActiveMacBufferCids())
                backlogBytes += mac->getMacBuffer(cid)->getQueueOccupancy();
            observation["ran"] = {{"max_bands", scheduler->getMaxBands()},
                    {"mac_backlog_bytes", backlogBytes}};

            // In RoutedPriority, DSCP 46 maps to PCP 5 and queue index 2.
            json transport = json::object();
            for (int i = 0; i < static_cast<int>(paths.size()); ++i) {
                auto *priority = check_and_cast<queueing::PacketQueue *>(
                        queues[i]->getSubmodule("queue", 2));
                transport[paths[i].id] = {
                    {"available", paths[i].interface->isUp() && paths[i].interface->hasCarrier()},
                    {"control_queue_bits", priority->getTotalLength().get()},
                    {"egress_bps", static_cast<std::int64_t>(paths[i].interface->getDatarate())}};
            }
            observation["transport"] = transport;

            const auto& counts = policer->getCounters();
            observation["core"] = {{"offered_video_packets", counts.admittedPackets + counts.droppedPackets},
                    {"burst_bytes", policer->par("burstSize").intValue()}};
        }
"""


def insert_after(source, anchor, addition):
    if source.count(anchor) != 1:
        raise ValueError(f"Expected one route bridge anchor: {anchor.strip()}")
    return source.replace(anchor, anchor + addition, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("copy", type=Path)
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8")
    source = insert_after(source, '#include "inet/queueing/queue/PacketQueue.h"\n', HEADERS)
    source = insert_after(source, "        recordResources(observation);\n", TELEMETRY)
    args.copy.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
