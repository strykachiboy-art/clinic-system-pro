from __future__ import annotations

from load_tests.resilience.common.network import NetworkProfile
from load_tests.resilience.profiles import slow_3g


def test_profile_is_network_profile():
    assert isinstance(
        slow_3g.PROFILE,
        NetworkProfile,
    )


def test_profile_name():
    assert slow_3g.PROFILE.name == "slow_3g"


def test_profile_latency():
    assert slow_3g.PROFILE.latency_ms == 250


def test_profile_has_no_jitter():
    assert slow_3g.PROFILE.jitter_ms == 0


def test_profile_has_no_packet_loss():
    assert slow_3g.PROFILE.packet_loss_rate == 0


def test_profile_has_no_interruption():
    assert slow_3g.PROFILE.interruption_rate == 0


def test_profile_bandwidth():
    assert slow_3g.PROFILE.bandwidth_kbps == 400


def test_get_profile_returns_profile():
    profile = slow_3g.get_profile()

    assert profile is slow_3g.PROFILE


def test_profile_delay_is_expected():
    import random

    delay = slow_3g.PROFILE.delay_seconds(
        random.Random(1),
    )

    assert delay == 0.25