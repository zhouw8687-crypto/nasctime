package nasctime.control;

import inet.applications.udpapp.UdpBasicApp;
import simu5g.stack.mac.NrMacGnb;

simple LocalQfiSource extends UdpBasicApp
{
    parameters:
        @class(nasctime::control::LocalQfiSource);
}

simple ObservedDlScheduler extends ControlledDlScheduler
{
    parameters:
        @class(nasctime::control::ObservedDlScheduler);
}

module ObservedNrMacGnb extends NrMacGnb
{
    parameters:
        @class(simu5g::NrMacGnb);
        dlSchedulerType @enum(LteSchedulerEnbDl,"nasctime.control.ObservedDlScheduler");
}
