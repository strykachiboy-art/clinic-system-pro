from __future__ import annotations

from load_tests.resilience.common.network import (
    INTERMITTENT,
    NetworkProfile,
)


PROFILE: NetworkProfile = INTERMITTENT


def get_profile() -> NetworkProfile:
    return PROFILE