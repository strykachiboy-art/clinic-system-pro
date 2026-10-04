from __future__ import annotations

from resilience.common.network import (
    JITTER,
    NetworkProfile,
)


PROFILE: NetworkProfile = JITTER


def get_profile() -> NetworkProfile:
    return PROFILE