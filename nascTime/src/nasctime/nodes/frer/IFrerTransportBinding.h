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

#ifndef __SIMU5G_1_4_3_FRER_IFRERTRANSPORTBINDING_H_
#define __SIMU5G_1_4_3_FRER_IFRERTRANSPORTBINDING_H_

#include <omnetpp.h>
#include "inet/common/packet/Packet.h"
#include "inet/networklayer/ipv4/Ipv4Header_m.h"
#include "inet/linklayer/common/InterfaceTag_m.h"

using namespace omnetpp;
using namespace inet;

// ============================================================================
// Abstract interface
// ============================================================================

class IFrerTransportBinding
{
  public:
    virtual ~IFrerTransportBinding() = default;

    /**
     * Prepare primary and replica for their respective member-stream paths.
     * Called by FrerReplicator after the FrerSequenceHeader has been
     * inserted into both packets.  The implementation must NOT delete
     * either packet; it may only modify header fields or tags.
     */
    virtual void prepareMemberStreams(Packet *primary, Packet *replica) = 0;

    /** DSCP value assigned to replica packets by this binding. */
    virtual int getReplicaDscp() const = 0;

    /** True if @p dscp identifies a replica produced by this binding. */
    virtual bool isReplicaPacket(int dscp) const = 0;

    /** Map a replica DSCP back to the originating stream's primary DSCP. */
    virtual int mapToOriginalDscp(int replicaDscp) const = 0;
};

// ============================================================================
// Phase 1 — DRB transport binding (intra-PDU-session)
// ============================================================================

/**
 * Routes primary and replica to different DRBs within the same PDU session
 * by assigning a distinct DSCP to the replica.  The SDAP layer in the gNB
 * maps DSCP → QFI → DRB, so changing the DSCP is sufficient.
 *
 * Primary: keeps its original DSCP (e.g. 7 → QFI 7 → DRB 2)
 * Replica:  gets replicaDscp  (e.g. 34 → QFI 8 → DRB 4)
 */
class DrbTransportBinding : public IFrerTransportBinding
{
  protected:
    int primaryDscp_;
    int replicaDscp_;

  public:
    DrbTransportBinding(int primaryDscp, int replicaDscp)
        : primaryDscp_(primaryDscp), replicaDscp_(replicaDscp) {}

    void prepareMemberStreams(Packet *primary, Packet *replica) override
    {
        // Primary is left unchanged — its DSCP was already set by
        // NwTtTranslator's PCP→DSCP mapping.

        // Replica: overwrite DSCP so SDAP maps it to DRB 4.
        auto ipHdr = replica->removeAtFront<Ipv4Header>();
        ipHdr->setDscp(replicaDscp_);
        replica->insertAtFront(ipHdr);
    }

    int  getReplicaDscp()  const override { return replicaDscp_; }
    bool isReplicaPacket(int dscp) const override { return dscp == replicaDscp_; }
    int  mapToOriginalDscp(int dscp) const override
    {
        return (dscp == replicaDscp_) ? primaryDscp_ : dscp;
    }
};

// ============================================================================
// Path-diverse binding base — shared by PduSession and DualConn
//
// Extends DRB binding behaviour (DSCP change) with InterfaceReq change
// to route the replica through a different PPP interface → different
// GTP-U tunnel → different N3 path (and potentially different gNB).
// ============================================================================

class PathDiverseTransportBinding : public IFrerTransportBinding
{
  protected:
    int primaryDscp_;
    int replicaDscp_;
    int replicaInterfaceId_;   // interface ID of pppIf2

  public:
    PathDiverseTransportBinding(int primaryDscp, int replicaDscp,
                                int replicaInterfaceId)
        : primaryDscp_(primaryDscp), replicaDscp_(replicaDscp),
          replicaInterfaceId_(replicaInterfaceId) {}

    void prepareMemberStreams(Packet *primary, Packet *replica) override
    {
        // 1. Change DSCP (same as DRB binding — needed for recovery-side
        //    duplicate identification via DSCP-aware bitmap)
        auto ipHdr = replica->removeAtFront<Ipv4Header>();
        ipHdr->setDscp(replicaDscp_);
        replica->insertAtFront(ipHdr);

        // 2. Change InterfaceReq to route through a different PPP interface.
        //    The nl dispatcher uses this tag to select the outgoing interface,
        //    sending the replica to pppIf2 → upf2 (→ gnb or gnb2).
        replica->addTagIfAbsent<InterfaceReq>()->setInterfaceId(
            replicaInterfaceId_);
    }

    int  getReplicaDscp()  const override { return replicaDscp_; }
    bool isReplicaPacket(int dscp) const override { return dscp == replicaDscp_; }
    int  mapToOriginalDscp(int dscp) const override
    {
        return (dscp == replicaDscp_) ? primaryDscp_ : dscp;
    }
};

// ============================================================================
// Phase 2 — Inter-PDU-session binding (same gNB, different N3 paths)
//
// Routes replica through pppIf2 → upf2 → gnb.  Both copies arrive at
// the same gNB and same MAC scheduler, but via independent N3 tunnels.
// Diversity: independent N3 path + independent PDCP/RLC (from DRB split).
// ============================================================================

class PduSessionTransportBinding : public PathDiverseTransportBinding
{
  public:
    using PathDiverseTransportBinding::PathDiverseTransportBinding;
};

// ============================================================================
// Phase 3 — NR dual-connectivity binding (different gNBs)
//
// Routes replica through pppIf2 → upf2 → gnb2.  The two copies traverse
// independent gNBs with independent MAC schedulers and independent radio
// channels.  Maximum FRER diversity — uncorrelated radio drops.
// ============================================================================

class DualConnTransportBinding : public PathDiverseTransportBinding
{
  public:
    using PathDiverseTransportBinding::PathDiverseTransportBinding;
};

#endif
