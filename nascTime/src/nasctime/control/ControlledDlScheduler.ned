package nasctime.control;

import simu5g.stack.mac.scheduler.LteSchedulerEnbDl;

simple ControlledDlScheduler extends LteSchedulerEnbDl
{
    parameters:
        int initialBandBudget = default(0); // Zero uses all configured bands.
        @class(nasctime::control::ControlledDlScheduler);
}
