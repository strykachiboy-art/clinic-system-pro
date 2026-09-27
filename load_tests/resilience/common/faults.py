from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from random import Random


class FaultType(StrEnum):
    TIMEOUT = "timeout"
    CONNECTION_FAILURE = "connection_failure"
    HTTP_5XX = "http_5xx"
    PARTIAL_FAILURE = "partial_failure"
    INTERMITTENT_FAILURE = "intermittent_failure"
    RECOVERY = "recovery"


class InjectedFault(RuntimeError):
    """Base exception for synthetic resilience fault injection."""

    def __init__(
        self,
        *,
        dependency: str,
        fault_type: FaultType,
        operation: str | None = None,
        status_code: int | None = None,
        message: str | None = None,
    ) -> None:
        self.dependency = dependency
        self.fault_type = fault_type
        self.operation = operation
        self.status_code = status_code

        detail = message or (
            f"Injected {fault_type.value} for dependency "
            f"{dependency}"
        )

        if operation:
            detail = (
                f"{detail} during operation "
                f"{operation}"
            )

        super().__init__(detail)


class InjectedTimeoutError(TimeoutError):
    """Injected dependency timeout."""

    def __init__(
        self,
        *,
        dependency: str,
        operation: str | None = None,
    ) -> None:
        self.dependency = dependency
        self.fault_type = FaultType.TIMEOUT
        self.operation = operation
        self.status_code = None

        detail = (
            f"Injected timeout for dependency "
            f"{dependency}"
        )

        if operation:
            detail = (
                f"{detail} during operation "
                f"{operation}"
            )

        super().__init__(detail)


class InjectedConnectionError(ConnectionError):
    """Injected dependency connection failure."""

    def __init__(
        self,
        *,
        dependency: str,
        operation: str | None = None,
    ) -> None:
        self.dependency = dependency
        self.fault_type = FaultType.CONNECTION_FAILURE
        self.operation = operation
        self.status_code = None

        detail = (
            f"Injected connection failure for dependency "
            f"{dependency}"
        )

        if operation:
            detail = (
                f"{detail} during operation "
                f"{operation}"
            )

        super().__init__(detail)


class InjectedHTTP5xxError(InjectedFault):
    """Injected HTTP 5xx dependency failure."""

    def __init__(
        self,
        *,
        dependency: str,
        operation: str | None = None,
        status_code: int = 500,
    ) -> None:
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 500 <= status_code <= 599
        ):
            raise ValueError(
                "HTTP 5xx status code must be between 500 and 599"
            )

        super().__init__(
            dependency=dependency,
            fault_type=FaultType.HTTP_5XX,
            operation=operation,
            status_code=status_code,
            message=(
                f"Injected HTTP {status_code} failure for "
                f"dependency {dependency}"
            ),
        )


@dataclass(slots=True)
class FaultRule:
    dependency: str
    fault_type: FaultType
    operation: str | None = None
    probability: float = 1.0
    max_occurrences: int | None = 1
    status_code: int = 500
    enabled: bool = True
    occurrences: int = 0

    def __post_init__(self) -> None:
        self.dependency = self.dependency.strip()
        self.fault_type = FaultType(self.fault_type)

        if not self.dependency:
            raise ValueError(
                "Fault dependency cannot be empty"
            )

        if (
            self.operation is not None
            and not self.operation.strip()
        ):
            raise ValueError(
                "Fault operation cannot be empty"
            )

        if (
            isinstance(self.probability, bool)
            or not isinstance(
                self.probability,
                (int, float),
            )
            or not 0 <= self.probability <= 1
        ):
            raise ValueError(
                "Fault probability must be between 0 and 1"
            )

        if (
            self.max_occurrences is not None
            and (
                isinstance(self.max_occurrences, bool)
                or not isinstance(
                    self.max_occurrences,
                    int,
                )
                or self.max_occurrences <= 0
            )
        ):
            raise ValueError(
                "max_occurrences must be a positive integer or None"
            )

        if self.fault_type == FaultType.HTTP_5XX:
            if (
                isinstance(self.status_code, bool)
                or not isinstance(
                    self.status_code,
                    int,
                )
                or not 500 <= self.status_code <= 599
            ):
                raise ValueError(
                    "HTTP 5xx status code must be between 500 and 599"
                )

        if self.fault_type == FaultType.RECOVERY:
            raise ValueError(
                "RECOVERY is an event type, not an injectable fault"
            )

    def matches(
        self,
        dependency: str,
        operation: str | None,
    ) -> bool:
        if not self.enabled:
            return False

        if self.dependency != dependency:
            return False

        if (
            self.operation is not None
            and self.operation != operation
        ):
            return False

        if (
            self.max_occurrences is not None
            and self.occurrences >= self.max_occurrences
        ):
            return False

        return True


class FaultInjector:
    """Test-scoped deterministic fault injector."""

    def __init__(
        self,
        *,
        seed: int | None = None,
    ) -> None:
        self._rng = Random(seed)
        self._rules: list[FaultRule] = []

    @property
    def rules(self) -> tuple[FaultRule, ...]:
        return tuple(self._rules)

    def add_rule(
        self,
        rule: FaultRule,
    ) -> FaultRule:
        self._rules.append(rule)
        return rule

    def add_fault(
        self,
        *,
        dependency: str,
        fault_type: FaultType,
        operation: str | None = None,
        probability: float = 1.0,
        max_occurrences: int | None = 1,
        status_code: int = 500,
    ) -> FaultRule:
        return self.add_rule(
            FaultRule(
                dependency=dependency,
                fault_type=fault_type,
                operation=operation,
                probability=probability,
                max_occurrences=max_occurrences,
                status_code=status_code,
            )
        )

    def inject(
        self,
        dependency: str,
        *,
        operation: str | None = None,
    ) -> None:
        dependency = dependency.strip()

        if not dependency:
            raise ValueError(
                "Fault dependency cannot be empty"
            )

        if (
            operation is not None
            and not operation.strip()
        ):
            raise ValueError(
                "Fault operation cannot be empty"
            )

        for rule in self._rules:
            if not rule.matches(
                dependency,
                operation,
            ):
                continue

            if self._rng.random() > rule.probability:
                continue

            rule.occurrences += 1

            if rule.fault_type == FaultType.TIMEOUT:
                raise InjectedTimeoutError(
                    dependency=dependency,
                    operation=operation,
                )

            if (
                rule.fault_type
                == FaultType.CONNECTION_FAILURE
            ):
                raise InjectedConnectionError(
                    dependency=dependency,
                    operation=operation,
                )

            if rule.fault_type == FaultType.HTTP_5XX:
                raise InjectedHTTP5xxError(
                    dependency=dependency,
                    operation=operation,
                    status_code=rule.status_code,
                )

            if rule.fault_type in {
                FaultType.PARTIAL_FAILURE,
                FaultType.INTERMITTENT_FAILURE,
            }:
                raise InjectedFault(
                    dependency=dependency,
                    fault_type=rule.fault_type,
                    operation=operation,
                )

            raise ValueError(
                f"Unsupported fault type: "
                f"{rule.fault_type}"
            )

    def recover(
        self,
        dependency: str | None = None,
    ) -> None:
        if dependency is not None:
            dependency = dependency.strip()

            if not dependency:
                raise ValueError(
                    "Fault dependency cannot be empty"
                )

        for rule in self._rules:
            if (
                dependency is None
                or rule.dependency == dependency
            ):
                rule.enabled = False

    def clear(self) -> None:
        self._rules.clear()