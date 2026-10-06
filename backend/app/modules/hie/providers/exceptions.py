from __future__ import annotations

from typing import Optional

from app.core.enums.hie_enums import HIEFailureClass


class HIEProviderError(Exception):
    failure_class = HIEFailureClass.FAIL_CLOSED

    def __init__(
        self,
        message: str,
    ) -> None:
        super().__init__(message)


class HIERetryableError(HIEProviderError):
    failure_class = HIEFailureClass.RETRYABLE


class HIEReconciliationRequiredError(HIEProviderError):
    failure_class = HIEFailureClass.RECONCILIATION_REQUIRED


class HIEUserActionRequiredError(HIEProviderError):
    failure_class = HIEFailureClass.USER_ACTION_REQUIRED


class HIEFailClosedError(HIEProviderError):
    failure_class = HIEFailureClass.FAIL_CLOSED


class HIEProviderHTTPError(HIEProviderError):
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
                "HIE provider HTTP status code must be between 100 and 599"
            )

        self.status_code = status_code

        if status_code in {408, 425, 429} or status_code >= 500:
            self.failure_class = HIEFailureClass.RETRYABLE
        else:
            self.failure_class = HIEFailureClass.USER_ACTION_REQUIRED

        super().__init__(
            message
            or f"HIE provider returned HTTP {status_code}"
        )


def classify_hie_failure(
    error: Exception,
) -> HIEFailureClass:
    if isinstance(error, HIEProviderError):
        return error.failure_class

    if isinstance(
        error,
        (
            TimeoutError,
            ConnectionError,
        ),
    ):
        return HIEFailureClass.RETRYABLE

    return HIEFailureClass.FAIL_CLOSED