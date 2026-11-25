package nasctime.simulations.demos.e2e_ladder;

import inet.common.scenario.ScenarioManager;

network ReuseFailoverLadder extends ProjectBookLadder
{
    submodules:
        scenarioManager: ScenarioManager {
            @display("p=60,300");
        }
}
