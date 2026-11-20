//
//                  Simu5G
//
// Copyright (C) 2012-2021 Giovanni Nardini, Giovanni Stea, Antonio Virdis et al. (University of Pisa)
// Copyright (C) 2022-2026 Giovanni Nardini, Giovanni Stea et al. (University of Pisa)
//
// This file is part of a software released under the license included in file
// "license.pdf". Please read LICENSE and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

package simu5g.corenetwork.gtp;

//
// Implements a simplified version of the user plane of the GPRS Tunneling
// Protocol (GTP). On one hand, this module encapsulates incoming IP datagrams into GTP
// packets and sends them to the tunnel destination endpoint (GTP operates on top of
// UDP). The destination endpoint is identified by utilizing information from the
// ~TrafficFlowFilter module. On the other hand, when this module receives GTP packets
// from a tunnel source endpoint, it decapsulates the included IP datagram and sends it
// to the intended destination according to normal IP forwarding.
// Used by all entities that need to communicate within the cellular core
// network, such as ~eNodeB, ~gNodeB, ~PgwStandard, ~Upf, and ~MecHost modules.
//
simple GtpUser
{
    parameters:
        string binderModule = default("binder");
        string interfaceTableModule;            // path to the InterfaceTable module
        string ipOutInterface = default("");    // optional: manual specification of outgoing interface for received IP
        int localPort = default(31);
        int tunnelPeerPort = default(31);
        // N3 外层 IP 的 DSCP 映射（对应 5QI/ QFI → DSCP 这一层，参考 Juniper fiveqi-map）
        // 格式 "qfi:dscp,qfi:dscp"，如 "1:46,5:34,9:0"；留空 = 直接用 QFI 作 DSCP
        string qfiDscpMap = default("");
        string gateway = default("");			// optional

        string forceTunnelPeer = default("");  // empty = normal routing, set = force all tunneling to this node
        @display("i=block/tunnel");

    gates:
        output socketOut;
        input socketIn;

        input trafficFlowFilterGate;
        output pppGate;
}

