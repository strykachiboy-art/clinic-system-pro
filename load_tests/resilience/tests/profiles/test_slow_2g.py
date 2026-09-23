from __future__ import annotations

from load_tests.resilience.common.network import NetworkProfile
from load_tests.resilience.profiles import slow_2g


def test_profile_is_network_profile():
    assert isinstance(
        slow_2g.PROFILE,
        NetworkProfile,
    )


def test_profile_name():
    assert slow_2g.PROFILE.name == "slow_2g"


def test_profile_latency():
    assert slow_2g.PROFILE.latency_ms == 700


def test_profile_has_no_jitter():
    assert slow_2g.PROFILE.jitter_ms == 0


def test_profile_has_no_packet_loss():
    assert slow_2g.PROFILE.packet_loss_rate == 0


def test_profile_has_no_interruption():
    assert slow_2g.PROFILE.interruption_rate == 0


def test_profile_bandwidth():
    assert slow_2g.PROFILE.bandwidth_kbps == 50


def test_get_profile_returns_profile():
    profile = slow_2g.get_profile()

    assert profile is slow_2g.PROFILE


def test_profile_delay_is_nonzero():
    delay = slow_2g.PROFILE.delay_seconds(
        __import__("random").Random(1),
    )

    assert delay == 0.7