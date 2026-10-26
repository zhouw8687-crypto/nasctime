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

package nasctime.nodes.NwTt;

import inet.common.MessageDispatcher;
import inet.linklayer.ethernet.modular.LayeredEthernetInterface;
import inet.linklayer.ethernet.basic.EthernetEncapsulation;
import inet.linklayer.ppp.PppInterface;
import inet.node.base.NetworkLayerNodeBase;
import inet.transportlayer.udp.Udp;
import nasctime.nodes.frer.FrerReplicator;
import nasctime.nodes.frer.FrerRecovery;

module NwTt extends NetworkLayerNodeBase
{
    parameters:
        @display("bgb=1348,1103;i=abstract/switch");
        @figure[applicationLayer](type=rectangle; pos=250,6; size=1000,130; lineColor=#808080; cornerRadius=5; fillColor=#ffff00; fillOpacity=0.1);
        @figure[applicationLayer.title](type=text; pos=1245,11; anchor=ne; text="application layer");
        @figure[transportLayer](type=rectangle; pos=250,156; size=1000,130; fillColor=#ff0000; lineColor=#808080; cornerRadius=5; fillOpacity=0.1);
        @figure[transportLayer.title](type=text; pos=1245,161; anchor=ne; text="transport layer");
        @figure[submodules];

        string nodeType = default("NWTT");
        forwarding = default(true);
        multicastForwarding = default(false);
        //nl.interfaceMapping = {interface: "pppIf", towards: "pppIf"} ;

        string ueAddress;
        string localAddress;

		// --- FRER (IEEE 802.1CB) ---
        // DL FRER
        bool frerEnabled = default(false);
        // UL FRER
        bool frerUplinkEnabled = default(false);

        // --- Inter-session / NR-DC: second PPP interface for N3 path diversity ---
        bool frerInterSession = default(false);

    gates:
        inout tsnEthg @labels(EthernetSignal);
        inout filterGate @loose @labels(PppFrame-conn);
		// Second N3 link for inter-session / NR-DC FRER
        inout filterGate2 @loose @labels(PppFrame-conn);
        output gptpSidebandOut @loose;

    submodules:
        ethIf: LayeredEthernetInterface {
            parameters:
                bitrate = default(1Gbps);
                phyLayer.typename = "EthernetStreamingPhyLayer";
                processingDelayLayer.typename = "OmittedProcessingDelayLayer";
                trafficConditionerLayer.typename = "OmittedTrafficConditionerLayer";
                measurementLayer.typename = "OmittedMeasurementLayer";
                @display("p=500,1000");
        }

        pppIf: PppInterface {
            parameters:
                @display("p=1150,1000");
        }

        // Second PPP interface for replica N3 path (conditional)
        pppIf2: PppInterface if frerInterSession {
            parameters:
                @display("p=1250,1000");
        }

        udp: Udp {
            parameters:
                @display("p=375,200");
        }

        // H3/H5: EthernetEncapsulation for egress path (5GS → TSN)
        // registerProtocol=true so it registers ethernetmac service on nl → ipv4.lp
        // Connected to nl (upper) and ethLi (lower)
        encap: EthernetEncapsulation {
            parameters:
                @display("p=350,800");
                registerProtocol = false;
        }

        translator: NwTtTranslator {
            parameters:
                @display("p=675,80");
                ueAddress = parent.ueAddress;
                localAddress = parent.localAddress;
        }

        // DL FRER: replicator (translator → 5G)
        frerReplicator: FrerReplicator if frerEnabled {
            parameters:
                ethernetFramed = false;
                @display("p=900,80");
        }

        // UL FRER: recovery (5G → nl)
        frerRecoveryUl: FrerRecovery if frerUplinkEnabled {
            parameters:
                ethernetFramed = true;
                registerEthernetProtocol = false;  // encap already registered with ethLi
                @display("p=1150,80");
        }

        // H5: Dispatcher between LayeredEthernetInterface and translator/encap
        ethLi: MessageDispatcher {
            parameters:
                @display("p=500,900;b=500,5,,,,1");
                // Route ethernetmac SERVICE requests to ethIf (gate out[0])
                serviceMapping = {"ethernetmac": "ethIf"};
        }

        tn: MessageDispatcher {
            parameters:
                @display("p=750,300;b=1000,5,,,,1");
        }

        at: MessageDispatcher {
            parameters:
                @display("p=750,146;b=1000,5,,,,1");
        }

connections:
        // === TSN Ethernet port ===
        tsnEthg <--> ethIf.phys;

        // H5: ethIf ↔ ethLi (must be first connection so ethIf = gate[0])
        ethIf.upperLayerOut --> ethLi.in++;
        ethIf.upperLayerIn <-- ethLi.out++;

        // INGRESS: ethLi → translator (gate[1])
        ethLi.out++ --> translator.ethIn;
        ethLi.in++ <-- translator.ethOut;

        // EGRESS lower: encap → [FrerRecoveryUl] → ethLi
        // UL FRER recovery intercepts here — packets are Ethernet-framed
        encap.lowerLayerOut --> frerRecoveryUl.in if frerUplinkEnabled;
        frerRecoveryUl.out --> ethLi.in++ if frerUplinkEnabled;
        encap.lowerLayerOut --> ethLi.in++ if !frerUplinkEnabled;
        // Reverse direction stays unconditional
        encap.lowerLayerIn <-- ethLi.out++;

        // EGRESS upper: encap ↔ nl
        encap.upperLayerOut --> nl.in++;
        encap.upperLayerIn <-- nl.out++;

        // === Primary UPF PPP port (ALWAYS direct to nl — no interception) ===
        filterGate <--> pppIf.phys;
        pppIf.upperLayerOut --> nl.in++;
        pppIf.upperLayerIn <-- nl.out++;

        // === Second PPP port for replica N3 path (conditional) ===
        filterGate2 <--> pppIf2.phys if frerInterSession;
        pppIf2.upperLayerOut --> nl.in++ if frerInterSession;
        pppIf2.upperLayerIn <-- nl.out++ if frerInterSession;

        // === DL FRER: translator → [FrerReplicator] → nl ===
        translator.ipForwardOut --> frerReplicator.in if frerEnabled;
        frerReplicator.out --> nl.in++ if frerEnabled;
        translator.ipForwardOut --> nl.in++ if !frerEnabled;

        // Reverse path (ALWAYS direct — no interception)
        translator.ipForwardIn <-- nl.out++;

        // === Translator ↔ at dispatcher ===
        translator.socketOut --> at.in++;
        translator.socketIn <-- at.out++;

        // === at ↔ UDP ===
        at.out++ --> udp.appIn;
        at.in++ <-- udp.appOut;

        // === at ↔ tn ===
        at.out++ --> tn.in++;
        at.in++ <-- tn.out++;

        // === UDP ↔ tn ===
        udp.ipOut --> tn.in++;
        udp.ipIn <-- tn.out++;

        // === tn ↔ network layer ===
        tn.out++ --> nl.in++;
        tn.in++ <-- nl.out++;

        // === tn ↔ IPv4 transport ===
        tn.out++ --> ipv4.transportIn;
        tn.in++ <-- ipv4.transportOut;

        // gPTP sideband
        translator.gptpOut --> gptpSidebandOut;
}