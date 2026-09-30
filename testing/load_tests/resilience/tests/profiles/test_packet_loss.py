from __future__ import annotations

import random

from load_tests.resilience.common.network import NetworkProfile
from load_tests.resilience.profiles import packet_loss


def test_profile_is_network_profile():
    assert isinstance(
        packet_loss.PROFILE,
        NetworkProfile,
    )


def test_profile_name():
    assert packet_loss.PROFILE.name == "packet_loss"


def test_profile_latency():
    assert packet_loss.PROFILE.latency_ms == 250


def test_profile_has_no_jitter():
    assert packet_loss.PROFILE.jitter_ms == 0


def test_profile_packet_loss_rate():
    assert packet_loss.PROFILE.packet_loss_rate == 0.10


def test_profile_has_no_bandwidth_limit():
    assert packet_loss.PROFILE.bandwidth_kbps is None


def test_profile_has_no_interruption():
    assert packet_loss.PROFILE.interruption_rate == 0


def test_get_profile_returns_profile():
    profile = packet_loss.get_profile()

    assert profile is packet_loss.PROFILE


def test_profile_delay_is_expected():
    delay = packet_loss.PROFILE.delay_seconds(
        random.Random(1),
    )

    assert delay == 0.25