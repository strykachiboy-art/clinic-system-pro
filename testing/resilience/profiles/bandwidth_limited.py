from __future__ import annotations

from resilience.common.network import (
    BANDWIDTH_LIMITED,
    NetworkProfile,
)


PROFILE: NetworkProfile = BANDWIDTH_LIMITED


def get_profile() -> NetworkProfile:
    return PROFILE