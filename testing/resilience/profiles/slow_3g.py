from __future__ import annotations

from resilience.common.network import (
    NetworkProfile,
    SLOW_3G,
)


PROFILE: NetworkProfile = SLOW_3G


def get_profile() -> NetworkProfile:
    return PROFILE