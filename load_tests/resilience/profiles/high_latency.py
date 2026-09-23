from __future__ import annotations

from load_tests.resilience.common.network import (
    HIGH_LATENCY,
    NetworkProfile,
)


PROFILE: NetworkProfile = HIGH_LATENCY


def get_profile() -> NetworkProfile:
    return PROFILE