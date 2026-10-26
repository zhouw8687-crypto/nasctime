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

package nasctime.nodes.TsnAf;

//
// Static Best Master Clock Algorithm (BMCA) Stub
//
// IEEE 802.1AS-2020 §10.3 — simplified static implementation.
// Reads the gPTP clock hierarchy from configuration and publishes
// it as queryable parameters. Validates the topology at init.
//
// In a real system, BMCA runs dynamically and elects the grandmaster.
// This stub provides the same result statically, which is sufficient
// for simulation where the topology is known at design time.
//
// The 5GS bridge is modelled as a transparent clock (IEEE 802.1AS
// §10.2.2.3) — it does not participate in BMCA election but must
// report its residence time in the correctionField.
//
simple StaticBmca
{
    parameters:
        @display("i=block/star");
        @class(::StaticBmca);

        // --- Grandmaster configuration ---
        string grandmasterModule = default("");       // e.g., "tsnDeviceA"
        int grandmasterPriority1 = default(246);      // IEEE 802.1AS default
        int grandmasterPriority2 = default(248);
        int clockClass = default(248);                // 248 = default, non-degraded
        int clockAccuracy = default(0xFE);            // 0xFE = unknown
        int offsetScaledLogVariance = default(0xFFFF);

        // --- Spanning tree (JSON array) ---
        // Each entry: {node: "moduleName", role: "MASTER"|"BRIDGE"|"SLAVE"|"TRANSPARENT",
        //              masterPorts: ["eth0"], slavePort: "eth1"}
        object spanningTree = default([]);

        // --- 5GS bridge configuration ---
        string nwTtModule = default("nwTt");
        string dsTtModule = default("dsTt");
        bool transparentClockEnabled = default(true);
        bool correctionFieldSupport = default(true);

        // --- Reference to TSN AF for bridge delay ---
        string tsnAfModule = default("tsnAf");

        // --- Signals ---
        @signal[bmcaEstablished](type=long);
        @signal[bmcaValidationError](type=long);

        @statistic[bmcaEstablished](record=count);
        @statistic[bmcaValidationError](record=count);
}