package nasctime.control;

import simu5g.stack.mac.NrMacGnb;

module RouteNrMacGnb extends NrMacGnb
{
    parameters:
        @class(simu5g::NrMacGnb);
        dlSchedulerType @enum(LteSchedulerEnbDl,"nasctime.control.ControlledDlScheduler");
}
