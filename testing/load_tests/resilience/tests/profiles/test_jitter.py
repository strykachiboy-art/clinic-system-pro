from __future__ import annotations

import random

from load_tests.resilience.common.network import NetworkProfile
from load_tests.resilience.profiles import jitter


def test_profile_is_network_profile():
    assert isinstance(
        jitter.PROFILE,
        NetworkProfile,
    )


def test_profile_name():
    assert jitter.PROFILE.name == "jitter"


def test_profile_latency():
    assert jitter.PROFILE.latency_ms == 500


def test_profile_jitter():
    assert jitter.PROFILE.jitter_ms == 300


def test_profile_has_no_packet_loss():
    assert jitter.PROFILE.packet_loss_rate == 0


def test_profile_has_no_bandwidth_limit():
    assert jitter.PROFILE.bandwidth_kbps is None


def test_profile_has_no_interruption():
    assert jitter.PROFILE.interruption_rate == 0


def test_get_profile_returns_profile():
    profile = jitter.get_profile()

    assert profile is jitter.PROFILE


def test_profile_delay_stays_within_expected_range():
    rng = random.Random(1)

    delay = jitter.PROFILE.delay_seconds(
        rng,
    )

    assert 0.2 <= delay <= 0.8