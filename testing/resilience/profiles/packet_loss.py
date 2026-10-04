from __future__ import annotations

from resilience.common.network import (
    NetworkProfile,
    PACKET_LOSS,
)


PROFILE: NetworkProfile = PACKET_LOSS


def get_profile() -> NetworkProfile:
    return PROFILE