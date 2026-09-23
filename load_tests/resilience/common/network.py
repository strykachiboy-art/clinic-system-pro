from __future__ import annotations

from dataclasses import dataclass
from random import Random
from time import sleep


class NetworkFault(RuntimeError):
    """Synthetic network fault injected by resilience tests."""


@dataclass(frozen=True, slots=True)
class NetworkProfile:
    name: str
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss_rate: float = 0.0
    bandwidth_kbps: float | None = None
    interruption_rate: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Network profile name cannot be empty")

        if self.latency_ms < 0:
            raise ValueError("Latency cannot be negative")

        if self.jitter_ms < 0:
            raise ValueError("Jitter cannot be negative")

        if not 0 <= self.packet_loss_rate <= 1:
            raise ValueError(
                "Packet loss rate must be between 0 and 1"
            )

        if self.bandwidth_kbps is not None:
            if self.bandwidth_kbps <= 0:
                raise ValueError(
                    "Bandwidth must be greater than zero"
                )

        if not 0 <= self.interruption_rate <= 1:
            raise ValueError(
                "Interruption rate must be between 0 and 1"
            )

    def delay_seconds(
        self,
        rng: Random,
        payload_bytes: int = 0,
    ) -> float:
        if (
            isinstance(payload_bytes, bool)
            or not isinstance(payload_bytes, int)
            or payload_bytes < 0
        ):
            raise ValueError(
                "payload_bytes must be a non-negative integer"
            )

        jitter_ms = 0.0

        if self.jitter_ms > 0:
            jitter_ms = rng.uniform(
                -self.jitter_ms,
                self.jitter_ms,
            )

        latency_ms = max(
            self.latency_ms + jitter_ms,
            0.0,
        )

        transfer_seconds = 0.0

        if self.bandwidth_kbps is not None:
            transfer_bits = payload_bytes * 8
            transfer_seconds = (
                transfer_bits
                / (self.bandwidth_kbps * 1000)
            )

        return (
            latency_ms / 1000
        ) + transfer_seconds


SLOW_2G = NetworkProfile(
    name="slow_2g",
    latency_ms=700,
    bandwidth_kbps=50,
)

SLOW_3G = NetworkProfile(
    name="slow_3g",
    latency_ms=250,
    bandwidth_kbps=400,
)

HIGH_LATENCY = NetworkProfile(
    name="high_latency",
    latency_ms=1200,
)

JITTER = NetworkProfile(
    name="jitter",
    latency_ms=500,
    jitter_ms=300,
)

PACKET_LOSS = NetworkProfile(
    name="packet_loss",
    latency_ms=250,
    packet_loss_rate=0.10,
)

BANDWIDTH_LIMITED = NetworkProfile(
    name="bandwidth_limited",
    latency_ms=200,
    bandwidth_kbps=128,
)

INTERMITTENT = NetworkProfile(
    name="intermittent",
    latency_ms=300,
    interruption_rate=0.20,
)


def create_rng(seed: int | None = None) -> Random:
    return Random(seed)


def should_drop(
    profile: NetworkProfile,
    rng: Random,
) -> bool:
    return rng.random() < profile.packet_loss_rate


def should_interrupt(
    profile: NetworkProfile,
    rng: Random,
) -> bool:
    return rng.random() < profile.interruption_rate


def inject_network_conditions(
    profile: NetworkProfile,
    *,
    payload_bytes: int = 0,
    seed: int | None = None,
) -> None:
    rng = create_rng(seed)

    sleep(
        profile.delay_seconds(
            rng,
            payload_bytes=payload_bytes,
        )
    )

    if should_drop(
        profile,
        rng,
    ):
        raise NetworkFault(
            f"Injected packet loss for profile "
            f"{profile.name}"
        )

    if should_interrupt(
        profile,
        rng,
    ):
        raise NetworkFault(
            f"Injected connection interruption for profile "
            f"{profile.name}"
        )