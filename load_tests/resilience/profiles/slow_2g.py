from __future__ import annotations

from load_tests.resilience.common.network import (
    NetworkProfile,
    SLOW_2G,
)


PROFILE: NetworkProfile = SLOW_2G


def get_profile() -> NetworkProfile:
    return PROFILE