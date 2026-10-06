from __future__ import annotations

from enum import Enum
from typing import Optional

from app.core.exceptions import DomainError, ValidationError


class AIProviderFailureClass(str, Enum):
    RETRYABLE = "retryable"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    USER_INTERVENTION_REQUIRED = "user_intervention_required"
    FAIL_CLOSED = "fail_closed"


class AIProviderError(DomainError):
    status_code = 503
    failure_class = AIProviderFailureClass.FAIL_CLOSED

    def __init__(
        self,
        message: str,
        failure_class: AIProviderFailureClass | None = None,
    ) -> None:
        self.failure_class = (
            failure_class
            if failure_class is not None
            else type(self).failure_class
        )
        super().__init__(message)


class AIRetryableError(AIProviderError):
    failure_class = AIProviderFailureClass.RETRYABLE


class AIReconciliationRequiredError(AIProviderError):
    failure_class = AIProviderFailureClass.RECONCILIATION_REQUIRED


class AIUserInterventionRequiredError(AIProviderError):
    status_code = 422
    failure_class = (
        AIProviderFailureClass.USER_INTERVENTION_REQUIRED
    )


class AIFailClosedError(AIProviderError):
    failure_class = AIProviderFailureClass.FAIL_CLOSED


class AIProviderResponseError(
    AIFailClosedError,
    ValidationError,
):
    status_code = 422


class AIProviderUnavailableError(AIRetryableError):
    pass


class AIProviderHTTPError(AIProviderError):
    def __init__(
        self,
        status_code: int,
        message: Optional[str] = None,
    ) -> None:
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or status_code < 100
            or status_code > 599
        ):
            raise ValueError(
                "AI provider HTTP status code must be between 100 and 599"
            )

        self.status_code = status_code

        if status_code in {408, 425, 429} or status_code >= 500:
            self.failure_class = (
                AIProviderFailureClass.RETRYABLE
            )
        else:
            self.failure_class = (
                AIProviderFailureClass.USER_INTERVENTION_REQUIRED
            )

        super().__init__(
            message
            or f"AI provider returned HTTP {status_code}",
            failure_class=self.failure_class,
        )


def classify_ai_failure(
    error: Exception,
) -> AIProviderFailureClass:
    if isinstance(error, AIProviderError):
        return error.failure_class

    status_code = getattr(
        error,
        "status_code",
        None,
    )

    if (
        isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and 100 <= status_code <= 599
    ):
        if status_code in {408, 425, 429} or status_code >= 500:
            return AIProviderFailureClass.RETRYABLE

        return AIProviderFailureClass.USER_INTERVENTION_REQUIRED

    error_name = type(error).__name__.casefold()

    if (
        "timeout" in error_name
        or "connection" in error_name
        or (
            "rate" in error_name
            and "limit" in error_name
        )
        or "unavailable" in error_name
    ):
        return AIProviderFailureClass.RETRYABLE

    if "unknown" in error_name:
        return AIProviderFailureClass.RECONCILIATION_REQUIRED

    if isinstance(
        error,
        (
            TimeoutError,
            ConnectionError,
        ),
    ):
        return AIProviderFailureClass.RETRYABLE

    return AIProviderFailureClass.FAIL_CLOSED