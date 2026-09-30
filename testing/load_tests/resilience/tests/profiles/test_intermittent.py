from __future__ import annotations

import random

from load_tests.resilience.common.network import NetworkProfile
from load_tests.resilience.profiles import intermittent


def test_profile_is_network_profile():
    assert isinstance(
        intermittent.PROFILE,
        NetworkProfile,
    )


def test_profile_name():
    assert intermittent.PROFILE.name == "intermittent"


def test_profile_latency():
    assert intermittent.PROFILE.latency_ms == 300


def test_profile_has_no_jitter():
    assert intermittent.PROFILE.jitter_ms == 0


def test_profile_has_no_packet_loss():
    assert intermittent.PROFILE.packet_loss_rate == 0


def test_profile_has_no_bandwidth_limit():
    assert intermittent.PROFILE.bandwidth_kbps is None


def test_profile_interruption_rate():
    assert intermittent.PROFILE.interruption_rate == 0.20


def test_get_profile_returns_profile():
    profile = intermittent.get_profile()

    assert profile is intermittent.PROFILE


def test_profile_delay_is_expected():
    delay = intermittent.PROFILE.delay_seconds(
        random.Random(1),
    )

    assert delay == 0.3