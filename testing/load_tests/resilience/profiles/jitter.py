from __future__ import annotations

from load_tests.resilience.common.network import (
    JITTER,
    NetworkProfile,
)


PROFILE: NetworkProfile = JITTER


def get_profile() -> NetworkProfile:
    return PROFILE