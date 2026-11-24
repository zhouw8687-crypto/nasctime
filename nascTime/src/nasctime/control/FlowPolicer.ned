package nasctime.control;

import inet.queueing.contract.ITrafficConditioner;

// Runtime-configurable policing at an IP ingress. Unmatched traffic passes through.
simple FlowPolicer like ITrafficConditioner
{
    parameters:
        string flowId;
        object packetFilter;
        int initialRate @unit(bps);
        int burstSize @unit(B) = default(4120B);
        @class(nasctime::control::FlowPolicer);
    gates:
        input in;
        output out;
}
