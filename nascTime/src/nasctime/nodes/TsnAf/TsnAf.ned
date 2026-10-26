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
// TSN Application Function (TSN AF) — 3GPP TS 23.501 §5.28.2
//
// Exposes 5GS bridge capabilities to the TSN CNC and applies
// CNC scheduling configurations to the bridge components.
//
// This module acts as the control plane interface between the
// TSN Centralized Network Configuration (CNC) and the 5GS bridge.
// It reads bridge parameters, monitors residence time, and can
// apply TAS gate control lists and stream reservation configs.
//
simple TsnAf
{
    parameters:
        @display("i=block/control");
        @class(::TsnAf);

        // --- Bridge capability parameters (published to CNC) ---
        double portSpeedBps @unit(bps) = default(1Gbps);
        int numTrafficClasses = default(8);           // IEEE 802.1Q max
        string supportedFeatures = default("gPTP,QoS,FRER");

        // PCP-to-QFI mapping table (index = PCP, value = QFI)
        string pcpToQfiMap = default("0,1,2,3,4,5,6,7");

        // --- Bridge delay bounds (updated from G3 residence time) ---
        volatile double bridgeDelayMin @unit(s) @mutable= default(0s);
        volatile double bridgeDelayMax @unit(s) @mutable= default(0s);
        volatile double bridgeDelayAvg @unit(s) @mutable= default(0s);

        // --- References to bridge modules ---
        string nwTtModule = default("nwTt");
        string dsTtModule = default("dsTt");
        string gnbModule = default("gnb");

        // --- CNC configuration file ---
        xml cncConfig = default(xml("<cncConfig/>"));

        // --- Signals & statistics ---
        @signal[bridgeDelayUpdated](type=simtime_t);
        @signal[streamConfigured](type=long);
        @signal[qosViolation](type=long);

        @statistic[bridgeDelay](source=bridgeDelayUpdated; record=vector,histogram; unit=s);
        @statistic[streamConfigured](record=count);
        @statistic[qosViolation](record=count);
}