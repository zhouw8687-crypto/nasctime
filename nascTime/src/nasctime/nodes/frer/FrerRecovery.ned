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

package nasctime.nodes.frer;

simple FrerRecovery
{
    parameters:
        @display("i=block/join");
        @class(::FrerRecovery);

        // Comma-separated DSCP values identifying primary FRER streams.
        // Must match the frerStreams parameter of FrerReplicator.
        string frerStreams = default("7");

        // DSCP used for replica packets (must match FrerReplicator).
        int replicaDscp = default(8);

        // Recovery window size (number of sequence numbers tracked).
        // IEEE 802.1CB Annex C recommends 64.
        int windowSize = default(64);

        // Timeout (seconds) after which a stream's recovery state is
        // reset if no packet arrives.  Prevents stale bitmaps from
        // blocking sequence-number reuse after idle periods.
        double windowTimeout @unit(s) = default(0.1s);

        // When true, packets arrive with Ethernet framing (DS-TT downlink — default).
        // When false, packets are bare IPv4 (NW-TT uplink recovery).
        bool ethernetFramed = default(true);
        bool registerEthernetProtocol = default(true);

        // --- Signals & statistics ---
        @signal[recoveredFromPrimary](type=long);
        @signal[recoveredFromReplica](type=long);
        @signal[duplicatesDropped](type=long);
        @signal[windowOverruns](type=long);
        @signal[passedThrough](type=long);

        @statistic[recoveredFromPrimary](title="Frames recovered from primary"; record=count,vector);
        @statistic[recoveredFromReplica](title="Frames recovered from replica"; record=count,vector);
        @statistic[duplicatesDropped](title="Duplicate frames dropped"; record=count,vector);
        @statistic[windowOverruns](title="Frames dropped (outside window)"; record=count);
        @statistic[passedThrough](title="Non-FRER frames passed through"; record=count);

    gates:
        input  in;
        output out;
}
