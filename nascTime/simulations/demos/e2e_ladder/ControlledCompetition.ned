package nasctime.simulations.demos.e2e_ladder;

import nasctime.control.ControllerBridge;

network ControlledCompetition extends ProjectBookLadder
{
    submodules:
        controller: ControllerBridge {
            policerModule = "upf.dnPpp.ingressTC";
            ranMacModule = "gnb1.cellularNic.mac";
            priorityQueueModule = "NE1.eth[1].queue.queue[2]";
            backgroundQueueModule = "NE1.eth[1].queue.queue[0]";
            prioritySinkModule = "ue[0].app[0]";
            backgroundSinkModule = "ue[0].app[1]";
            @display("p=690,160");
        }
}
