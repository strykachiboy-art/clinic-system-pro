from __future__ import annotations

import random

from load_tests.resilience.common.network import NetworkProfile
from load_tests.resilience.profiles import bandwidth_limited


def test_profile_is_network_profile():
    assert isinstance(
        bandwidth_limited.PROFILE,
        NetworkProfile,
    )


def test_profile_name():
    assert (
        bandwidth_limited.PROFILE.name
        == "bandwidth_limited"
    )


def test_profile_latency():
    assert bandwidth_limited.PROFILE.latency_ms == 200


def test_profile_has_no_jitter():
    assert bandwidth_limited.PROFILE.jitter_ms == 0


def test_profile_has_no_packet_loss():
    assert (
        bandwidth_limited.PROFILE.packet_loss_rate
        == 0
    )


def test_profile_bandwidth():
    assert (
        bandwidth_limited.PROFILE.bandwidth_kbps
        == 128
    )


def test_profile_has_no_interruption():
    assert (
        bandwidth_limited.PROFILE.interruption_rate
        == 0
    )


def test_get_profile_returns_profile():
    profile = bandwidth_limited.get_profile()

    assert profile is bandwidth_limited.PROFILE


def test_profile_delay_includes_transfer_time():
    delay = bandwidth_limited.PROFILE.delay_seconds(
        random.Random(1),
        payload_bytes=16000,
    )

    expected = 0.2 + 1.0

    assert delay == expected