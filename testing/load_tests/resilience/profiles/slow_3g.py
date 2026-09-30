from __future__ import annotations

from load_tests.resilience.common.network import (
    NetworkProfile,
    SLOW_3G,
)


PROFILE: NetworkProfile = SLOW_3G


def get_profile() -> NetworkProfile:
    return PROFILE