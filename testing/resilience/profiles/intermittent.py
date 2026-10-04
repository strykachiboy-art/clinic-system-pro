from __future__ import annotations

from resilience.common.network import (
    INTERMITTENT,
    NetworkProfile,
)


PROFILE: NetworkProfile = INTERMITTENT


def get_profile() -> NetworkProfile:
    return PROFILE