package nasctime.simulations.demos.e2e_ladder;

import simu5g.corenetwork.bearerConfigurator.BearerConfigurator;

network Qfi17Ladder extends ProjectBookLadder
{
    parameters:
        **.cellularNic.hasSdap = default(true);
    submodules:
        bearerConfigurator: BearerConfigurator;
}
