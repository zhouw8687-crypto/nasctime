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

simple NwTtTranslator
{
    parameters:
        @display("i=block/routing");
        @class(::NwTtTranslator);

        // --- Ethernet-side configuration ---
        string tsnPortMacAddress = default("0A:00:00:00:00:01");
        string defaultDstMacAddress = default("FF:FF:FF:FF:FF:FF");

		string mappedPcpValues = default("0,1,2,3,4,5,6,7");  // default: map all

        // --- IP-side configuration ---
        string ueAddress;
        string localAddress;
        int encapUdpPort = default(30000);

		// IP address of the downstream TSN device (registered with binder for GTP routing)
        string tsnDeviceBAddress = default("");

		// Multi-endpoint: list of downstream TSN device → UE mappings
        // Each entry: {address: "tsnDeviceB[0]", ue: "ue[0]"}
        object tsnDeviceBAddresses = default([]);

		// gPTP transport mode: "sideband" (direct OMNeT++ connection) or "gtpu" (L2-in-GTP-U)
        string gptpTransportMode = default("gtpu");
        int gptpEncapUdpPort = default(30001);  // dedicated port for gPTP-in-UDP

		string interfaceTableModule = default("^.interfaceTable");


        // --- Signals & statistics ---
        @signal[encapDelay](type=simtime_t);
        @signal[decapDelay](type=simtime_t);
        @signal[ethFrameReceived](type=long);
        @signal[ipPacketReceived](type=long);
        @signal[packetDropped](type=long);

        @statistic[encapDelay](title="Eth→IP encapsulation delay"; record=vector,histogram);
        @statistic[decapDelay](title="IP→Eth decapsulation delay"; record=vector,histogram);
        @statistic[ethFrameReceived](title="Ethernet frames from TSN"; record=count);
        @statistic[ipPacketReceived](title="IP packets from UPF"; record=count);
        @statistic[packetDropped](title="Packets dropped"; record=count);

    gates:
        // Ethernet side (connects directly to LayeredEthernetInterface upperLayer)
        input ethIn;
        output ethOut;

        // Socket side (connects to MessageDispatcher 'at', like any INET app)
        input socketIn;
        output socketOut;


        // Direct IP forwarding (connects to tn dispatcher, bypasses UDP)
        output ipForwardOut;
        input ipForwardIn;

        // gPTP sideband output (to GptpSideband module)
        output gptpOut;
}

