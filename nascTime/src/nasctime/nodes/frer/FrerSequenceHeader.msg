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

cplusplus {{
#include "inet/common/Units.h"
using namespace inet;
}}

import inet.common.INETDefs;
import inet.common.packet.chunk.Chunk;

namespace simu5g;

class FrerSequenceHeader extends inet::FieldsChunk
{
    chunkLength = B(4);
    uint16_t streamId = 0;         // identifies the compound stream (== primary DSCP)
    uint16_t sequenceNumber = 0;   // 16-bit wrapping counter per stream
}
