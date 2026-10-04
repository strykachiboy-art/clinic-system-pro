from __future__ import annotations

import pytest

from resilience.common import faults


def test_fault_type_values():
    assert faults.FaultType.TIMEOUT.value == "timeout"
    assert (
        faults.FaultType.CONNECTION_FAILURE.value
        == "connection_failure"
    )
    assert (
        faults.FaultType.HTTP_5XX.value
        == "http_5xx"
    )
    assert (
        faults.FaultType.PARTIAL_FAILURE.value
        == "partial_failure"
    )
    assert (
        faults.FaultType.INTERMITTENT_FAILURE.value
        == "intermittent_failure"
    )
    assert faults.FaultType.RECOVERY.value == "recovery"


def test_fault_rule_rejects_empty_dependency():
    with pytest.raises(
        ValueError,
        match="Fault dependency cannot be empty",
    ):
        faults.FaultRule(
            dependency="   ",
            fault_type=faults.FaultType.TIMEOUT,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "probability": -0.01,
        },
        {
            "probability": 1.01,
        },
        {
            "max_occurrences": 0,
        },
        {
            "max_occurrences": -1,
        },
        {
            "max_occurrences": True,
        },
    ],
)
def test_fault_rule_rejects_invalid_values(
    kwargs,
):
    with pytest.raises(ValueError):
        faults.FaultRule(
            dependency="postgres",
            fault_type=faults.FaultType.TIMEOUT,
            **kwargs,
        )


def test_fault_rule_rejects_recovery_as_injectable_fault():
    with pytest.raises(
        ValueError,
        match="RECOVERY is an event type",
    ):
        faults.FaultRule(
            dependency="postgres",
            fault_type=faults.FaultType.RECOVERY,
        )


@pytest.mark.parametrize(
    "status_code",
    [
        400,
        499,
        600,
        700,
    ],
)
def test_http_5xx_rejects_non_5xx_status(
    status_code,
):
    with pytest.raises(
        ValueError,
        match="HTTP 5xx status code",
    ):
        faults.FaultRule(
            dependency="hie",
            fault_type=faults.FaultType.HTTP_5XX,
            status_code=status_code,
        )


def test_timeout_fault_is_injected():
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="postgres",
        fault_type=faults.FaultType.TIMEOUT,
    )

    with pytest.raises(
        faults.InjectedTimeoutError,
        match="Injected timeout for dependency postgres",
    ) as exc:
        injector.inject(
            "postgres",
            operation="execute",
        )

    assert isinstance(
        exc.value,
        TimeoutError,
    )

    assert exc.value.dependency == "postgres"
    assert exc.value.fault_type == (
        faults.FaultType.TIMEOUT
    )
    assert exc.value.operation == "execute"


def test_connection_failure_is_injected():
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
    )

    with pytest.raises(
        faults.InjectedConnectionError,
        match=(
            "Injected connection failure "
            "for dependency redis"
        ),
    ) as exc:
        injector.inject("redis")

    assert isinstance(
        exc.value,
        ConnectionError,
    )

    assert exc.value.dependency == "redis"
    assert exc.value.fault_type == (
        faults.FaultType.CONNECTION_FAILURE
    )


def test_http_5xx_fault_contains_status_code():
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="hie",
        fault_type=faults.FaultType.HTTP_5XX,
        status_code=503,
    )

    with pytest.raises(
        faults.InjectedHTTP5xxError,
        match="Injected HTTP 503 failure",
    ) as exc:
        injector.inject(
            "hie",
            operation="submit_document",
        )

    assert exc.value.status_code == 503
    assert exc.value.dependency == "hie"
    assert exc.value.operation == (
        "submit_document"
    )


@pytest.mark.parametrize(
    "fault_type",
    [
        faults.FaultType.PARTIAL_FAILURE,
        faults.FaultType.INTERMITTENT_FAILURE,
    ],
)
def test_generic_fault_types_are_injected(
    fault_type,
):
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="worker",
        fault_type=fault_type,
    )

    with pytest.raises(
        faults.InjectedFault,
    ) as exc:
        injector.inject(
            "worker",
            operation="process",
        )

    assert exc.value.dependency == "worker"
    assert exc.value.fault_type == fault_type
    assert exc.value.operation == "process"


def test_operation_matching_limits_fault_to_target_operation():
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="postgres",
        fault_type=faults.FaultType.TIMEOUT,
        operation="execute",
    )

    injector.inject(
        "postgres",
        operation="connect",
    )

    with pytest.raises(
        faults.InjectedTimeoutError,
    ):
        injector.inject(
            "postgres",
            operation="execute",
        )


def test_fault_only_injects_for_matching_dependency():
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
    )

    injector.inject("postgres")

    with pytest.raises(
        faults.InjectedConnectionError,
    ):
        injector.inject("redis")


def test_max_occurrences_limits_fault_injection():
    injector = faults.FaultInjector()

    rule = injector.add_fault(
        dependency="postgres",
        fault_type=faults.FaultType.TIMEOUT,
        max_occurrences=1,
    )

    with pytest.raises(
        faults.InjectedTimeoutError,
    ):
        injector.inject("postgres")

    injector.inject("postgres")

    assert rule.occurrences == 1


def test_max_occurrences_none_allows_repeated_injection():
    injector = faults.FaultInjector()

    rule = injector.add_fault(
        dependency="postgres",
        fault_type=faults.FaultType.TIMEOUT,
        max_occurrences=None,
    )

    for _ in range(3):
        with pytest.raises(
            faults.InjectedTimeoutError,
        ):
            injector.inject("postgres")

    assert rule.occurrences == 3


def test_probability_zero_never_injects():
    injector = faults.FaultInjector(
        seed=123,
    )

    rule = injector.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
        probability=0.0,
        max_occurrences=None,
    )

    for _ in range(10):
        injector.inject("redis")

    assert rule.occurrences == 0


def test_probability_one_always_injects():
    injector = faults.FaultInjector(
        seed=123,
    )

    rule = injector.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
        probability=1.0,
        max_occurrences=None,
    )

    for _ in range(3):
        with pytest.raises(
            faults.InjectedConnectionError,
        ):
            injector.inject("redis")

    assert rule.occurrences == 3


def test_recover_disables_specific_dependency():
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="postgres",
        fault_type=faults.FaultType.TIMEOUT,
        max_occurrences=None,
    )

    injector.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
        max_occurrences=None,
    )

    injector.recover("postgres")

    injector.inject("postgres")

    with pytest.raises(
        faults.InjectedConnectionError,
    ):
        injector.inject("redis")


def test_recover_without_dependency_disables_all_rules():
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="postgres",
        fault_type=faults.FaultType.TIMEOUT,
        max_occurrences=None,
    )

    injector.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
        max_occurrences=None,
    )

    injector.recover()

    injector.inject("postgres")
    injector.inject("redis")

    assert all(
        rule.enabled is False
        for rule in injector.rules
    )


def test_clear_removes_all_rules():
    injector = faults.FaultInjector()

    injector.add_fault(
        dependency="postgres",
        fault_type=faults.FaultType.TIMEOUT,
    )

    injector.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
    )

    assert len(injector.rules) == 2

    injector.clear()

    assert injector.rules == ()


def test_seeded_probability_is_reproducible():
    first = faults.FaultInjector(seed=123)
    second = faults.FaultInjector(seed=123)

    first_rule = first.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
        probability=0.5,
        max_occurrences=None,
    )

    second_rule = second.add_fault(
        dependency="redis",
        fault_type=faults.FaultType.CONNECTION_FAILURE,
        probability=0.5,
        max_occurrences=None,
    )

    first_results = []
    second_results = []

    for _ in range(20):
        try:
            first.inject("redis")
            first_results.append(False)
        except faults.InjectedConnectionError:
            first_results.append(True)

        try:
            second.inject("redis")
            second_results.append(False)
        except faults.InjectedConnectionError:
            second_results.append(True)

    assert first_results == second_results
    assert first_rule.occurrences == (
        second_rule.occurrences
    )