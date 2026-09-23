from __future__ import annotations

import random

from load_tests.resilience.common.network import NetworkProfile
from load_tests.resilience.profiles import high_latency


def test_profile_is_network_profile():
    assert isinstance(
        high_latency.PROFILE,
        NetworkProfile,
    )


def test_profile_name():
    assert high_latency.PROFILE.name == "high_latency"


def test_profile_latency():
    assert high_latency.PROFILE.latency_ms == 1200


def test_profile_has_no_jitter():
    assert high_latency.PROFILE.jitter_ms == 0


def test_profile_has_no_packet_loss():
    assert high_latency.PROFILE.packet_loss_rate == 0


def test_profile_has_no_bandwidth_limit():
    assert high_latency.PROFILE.bandwidth_kbps is None


def test_profile_has_no_interruption():
    assert high_latency.PROFILE.interruption_rate == 0


def test_get_profile_returns_profile():
    profile = high_latency.get_profile()

    assert profile is high_latency.PROFILE


def test_profile_delay_is_expected():
    delay = high_latency.PROFILE.delay_seconds(
        random.Random(1),
    )

    assert delay == 1.2