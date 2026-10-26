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

simple DsTtTranslator
{
    parameters:
        @display("i=block/routing");
        @class(::DsTtTranslator);
		int gptpEncapUdpPort = default(30001);  // must match NW-TT's port
		
        // --- Signals & statistics ---
        @signal[tsnToUeForwarded](type=long);
        @signal[ueToTsnForwarded](type=long);
        @signal[packetDropped](type=long);

        @statistic[tsnToUeForwarded](title="Frames forwarded TSN→UE"; record=count);
        @statistic[ueToTsnForwarded](title="Frames forwarded UE→TSN"; record=count);
        @statistic[packetDropped](title="Packets dropped"; record=count);

        @signal[residenceTime](type=simtime_t);
        @statistic[residenceTime](title="5GS bridge residence time"; record=vector,histogram; unit=s);

    gates:
        // Facing TSN Device B
        input tsnIn;
        output tsnOut;

        // Facing UE's eth[0]
        input ueIn;
        output ueOut;

        // gPTP sideband input (from GptpSideband module)
        input gptpIn;
}
