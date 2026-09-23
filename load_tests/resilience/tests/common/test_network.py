from __future__ import annotations

from random import Random

import pytest

from load_tests.resilience.common import network


def test_network_profile_rejects_empty_name():
    with pytest.raises(
        ValueError,
        match="Network profile name cannot be empty",
    ):
        network.NetworkProfile(name="   ")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "test", "latency_ms": -1},
        {"name": "test", "jitter_ms": -1},
        {
            "name": "test",
            "packet_loss_rate": -0.01,
        },
        {
            "name": "test",
            "packet_loss_rate": 1.01,
        },
        {
            "name": "test",
            "bandwidth_kbps": 0,
        },
        {
            "name": "test",
            "bandwidth_kbps": -1,
        },
        {
            "name": "test",
            "interruption_rate": -0.01,
        },
        {
            "name": "test",
            "interruption_rate": 1.01,
        },
    ],
)
def test_network_profile_rejects_invalid_values(
    kwargs,
):
    with pytest.raises(ValueError):
        network.NetworkProfile(**kwargs)


def test_delay_seconds_with_latency_only():
    profile = network.NetworkProfile(
        name="latency",
        latency_ms=250,
    )

    delay = profile.delay_seconds(
        Random(1),
    )

    assert delay == pytest.approx(
        0.25,
    )


def test_delay_seconds_never_returns_negative():
    profile = network.NetworkProfile(
        name="jitter",
        latency_ms=10,
        jitter_ms=100,
    )

    delay = profile.delay_seconds(
        Random(1),
    )

    assert delay >= 0


def test_delay_seconds_includes_bandwidth_transfer_time():
    profile = network.NetworkProfile(
        name="bandwidth",
        latency_ms=100,
        bandwidth_kbps=100,
    )

    delay = profile.delay_seconds(
        Random(1),
        payload_bytes=12500,
    )

    expected_transfer_seconds = 1.0
    expected_total = 0.1 + expected_transfer_seconds

    assert delay == pytest.approx(
        expected_total,
    )


@pytest.mark.parametrize(
    "payload_bytes",
    [
        -1,
        -100,
    ],
)
def test_delay_seconds_rejects_negative_payload_size(
    payload_bytes,
):
    profile = network.NetworkProfile(
        name="payload",
    )

    with pytest.raises(
        ValueError,
        match="payload_bytes must be a non-negative integer",
    ):
        profile.delay_seconds(
            Random(1),
            payload_bytes=payload_bytes,
        )


def test_delay_seconds_rejects_boolean_payload_size():
    profile = network.NetworkProfile(
        name="payload",
    )

    with pytest.raises(
        ValueError,
        match="payload_bytes must be a non-negative integer",
    ):
        profile.delay_seconds(
            Random(1),
            payload_bytes=True,
        )


def test_create_rng_is_deterministic():
    first = network.create_rng(123)
    second = network.create_rng(123)

    assert first.random() == second.random()


def test_should_drop_returns_true_when_random_value_is_below_threshold(
    monkeypatch,
):
    profile = network.NetworkProfile(
        name="loss",
        packet_loss_rate=0.5,
    )

    class FakeRandom:
        def random(self):
            return 0.25

    assert network.should_drop(
        profile,
        FakeRandom(),
    ) is True


def test_should_drop_returns_false_when_random_value_is_above_threshold(
    monkeypatch,
):
    profile = network.NetworkProfile(
        name="loss",
        packet_loss_rate=0.5,
    )

    class FakeRandom:
        def random(self):
            return 0.75

    assert network.should_drop(
        profile,
        FakeRandom(),
    ) is False


def test_should_interrupt_returns_true_when_random_value_is_below_threshold():
    profile = network.NetworkProfile(
        name="intermittent",
        interruption_rate=0.5,
    )

    class FakeRandom:
        def random(self):
            return 0.25

    assert network.should_interrupt(
        profile,
        FakeRandom(),
    ) is True


def test_should_interrupt_returns_false_when_random_value_is_above_threshold():
    profile = network.NetworkProfile(
        name="intermittent",
        interruption_rate=0.5,
    )

    class FakeRandom:
        def random(self):
            return 0.75

    assert network.should_interrupt(
        profile,
        FakeRandom(),
    ) is False


def test_inject_network_conditions_applies_delay_without_sleeping(
    monkeypatch,
):
    profile = network.NetworkProfile(
        name="test",
        latency_ms=250,
    )

    sleeps = []

    monkeypatch.setattr(
        network,
        "sleep",
        sleeps.append,
    )

    monkeypatch.setattr(
        network,
        "should_drop",
        lambda profile, rng: False,
    )

    monkeypatch.setattr(
        network,
        "should_interrupt",
        lambda profile, rng: False,
    )

    network.inject_network_conditions(
        profile,
        payload_bytes=100,
        seed=123,
    )

    assert len(sleeps) == 1
    assert sleeps[0] > 0


def test_inject_network_conditions_raises_network_fault_on_packet_loss(
    monkeypatch,
):
    profile = network.NetworkProfile(
        name="loss",
        packet_loss_rate=0.5,
    )

    monkeypatch.setattr(
        network,
        "sleep",
        lambda seconds: None,
    )

    monkeypatch.setattr(
        network,
        "should_drop",
        lambda profile, rng: True,
    )

    with pytest.raises(
        network.NetworkFault,
        match="Injected packet loss for profile loss",
    ):
        network.inject_network_conditions(
            profile,
            seed=123,
        )


def test_inject_network_conditions_raises_network_fault_on_interruption(
    monkeypatch,
):
    profile = network.NetworkProfile(
        name="intermittent",
        interruption_rate=0.5,
    )

    monkeypatch.setattr(
        network,
        "sleep",
        lambda seconds: None,
    )

    monkeypatch.setattr(
        network,
        "should_drop",
        lambda profile, rng: False,
    )

    monkeypatch.setattr(
        network,
        "should_interrupt",
        lambda profile, rng: True,
    )

    with pytest.raises(
        network.NetworkFault,
        match="Injected connection interruption for profile intermittent",
    ):
        network.inject_network_conditions(
            profile,
            seed=123,
        )


def test_inject_network_conditions_does_not_raise_when_no_fault_is_selected(
    monkeypatch,
):
    profile = network.NetworkProfile(
        name="stable",
    )

    monkeypatch.setattr(
        network,
        "sleep",
        lambda seconds: None,
    )

    monkeypatch.setattr(
        network,
        "should_drop",
        lambda profile, rng: False,
    )

    monkeypatch.setattr(
        network,
        "should_interrupt",
        lambda profile, rng: False,
    )

    network.inject_network_conditions(
        profile,
        seed=123,
    )


@pytest.mark.parametrize(
    "profile",
    [
        network.SLOW_2G,
        network.SLOW_3G,
        network.HIGH_LATENCY,
        network.JITTER,
        network.PACKET_LOSS,
        network.BANDWIDTH_LIMITED,
        network.INTERMITTENT,
    ],
)
def test_builtin_network_profiles_are_valid(profile):
    assert profile.name
    assert profile.latency_ms >= 0
    assert profile.jitter_ms >= 0
    assert 0 <= profile.packet_loss_rate <= 1
    assert 0 <= profile.interruption_rate <= 1

    if profile.bandwidth_kbps is not None:
        assert profile.bandwidth_kbps > 0