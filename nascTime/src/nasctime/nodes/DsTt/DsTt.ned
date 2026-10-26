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

package nasctime.nodes.DsTt;

import inet.common.MessageDispatcher;
import inet.linklayer.ethernet.modular.LayeredEthernetInterface;
import inet.networklayer.common.InterfaceTable;
import nasctime.nodes.frer.FrerRecovery;
import nasctime.nodes.frer.FrerReplicator;

module DsTt
{
    parameters:
        @display("i=abstract/switch;bgb=500,400");
        @networkNode();
        *.interfaceTableModule = default(absPath(".interfaceTable"));

        // --- FRER (IEEE 802.1CB) ---
        // DL FRER: recovery between ueLi and translator.ueIn
        bool frerEnabled = default(false);
        // UL FRER: replication between translator.ueOut and ueLi
        bool frerUplinkEnabled = default(false);

    gates:
        inout tsnEthg @labels(EthernetSignal);
        inout ueEthg @labels(EthernetSignal);
        input gptpSidebandIn @loose;

    submodules:
        interfaceTable: InterfaceTable {
            @display("p=80,50;is=s");
        }

        tsnEth: LayeredEthernetInterface {
            parameters:
                bitrate = default(1Gbps);
                phyLayer.typename = "EthernetStreamingPhyLayer";
                processingDelayLayer.typename = "OmittedProcessingDelayLayer";
                trafficConditionerLayer.typename = "OmittedTrafficConditionerLayer";
                measurementLayer.typename = "OmittedMeasurementLayer";
                @display("p=350,300");
        }

        ueEth: LayeredEthernetInterface {
            parameters:
                bitrate = default(1Gbps);
                phyLayer.typename = "EthernetPhyLayer";
                processingDelayLayer.typename = "OmittedProcessingDelayLayer";
                trafficConditionerLayer.typename = "OmittedTrafficConditionerLayer";
                measurementLayer.typename = "OmittedMeasurementLayer";
                @display("p=150,300");
        }

        translator: DsTtTranslator {
            parameters:
                @display("p=250,100");
        }

        // FRER: conditional recovery module (only when frerEnabled=true)
        // DL FRER: recovery (UE → translator path)
        frerRecovery: FrerRecovery if frerEnabled {
            parameters:
                ethernetFramed = true;
                @display("p=150,100");
        }

        // UL FRER: replicator (translator → UE path)
        frerReplicatorUl: FrerReplicator if frerUplinkEnabled {
            parameters:
                ethernetFramed = true;
                @display("p=350,100");
        }

        // H5: Dispatchers between LayeredEthernetInterface and translator
        tsnLi: MessageDispatcher {
            parameters:
                @display("p=350,200;b=200,5,,,,1");
                serviceMapping = {"ethernetmac": "tsnEth"};
        }

        ueLi: MessageDispatcher {
            parameters:
                @display("p=150,200;b=200,5,,,,1");
                serviceMapping = {"ethernetmac": "ueEth"};
        }

    connections:
        // External gates
        tsnEthg <--> tsnEth.phys;
        ueEthg <--> ueEth.phys;

        // TSN side: tsnEth ↔ tsnLi ↔ translator (unchanged)
        tsnEth.upperLayerOut --> tsnLi.in++;
        tsnEth.upperLayerIn <-- tsnLi.out++;
        tsnLi.out++ --> translator.tsnIn;
        tsnLi.in++ <-- translator.tsnOut;

        // UE side: ueEth ↔ ueLi ↔ [frerRecovery] ↔ translator
        ueEth.upperLayerOut --> ueLi.in++;
        ueEth.upperLayerIn <-- ueLi.out++;

        // === UE → translator path (with optional FRER recovery) ===
        //
        // When frerEnabled=true:
        //   ueLi → frerRecovery.in → frerRecovery.out → translator.ueIn
        //   (FrerRecovery drops duplicates, forwards first copy)
        //
        // When frerEnabled=false (DEFAULT):
        //   ueLi → translator.ueIn  (original wiring, unchanged)
        //
        // === DL path: UE → [FrerRecovery] → translator ===
        ueLi.out++ --> frerRecovery.in if frerEnabled;
        frerRecovery.out --> translator.ueIn if frerEnabled;
        ueLi.out++ --> translator.ueIn if !frerEnabled;

        // === UL path: translator → [FrerReplicatorUl] → ueLi ===
        translator.ueOut --> frerReplicatorUl.in if frerUplinkEnabled;
        frerReplicatorUl.out --> ueLi.in++ if frerUplinkEnabled;
        ueLi.in++ <-- translator.ueOut if !frerUplinkEnabled;

        // gPTP sideband
        gptpSidebandIn --> translator.gptpIn;
}
