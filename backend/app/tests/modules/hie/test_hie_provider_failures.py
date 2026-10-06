from __future__ import annotations

import pytest

from app.core.enums.hie_enums import HIEFailureClass
from app.modules.hie.providers.exceptions import (
    HIEFailClosedError,
    HIEProviderHTTPError,
    HIEReconciliationRequiredError,
    HIERetryableError,
    HIEUserActionRequiredError,
    classify_hie_failure,
)


def test_failure_classes_are_stable():
    assert HIEFailureClass.RETRYABLE.value == "retryable"
    assert (
        HIEFailureClass.RECONCILIATION_REQUIRED.value
        == "reconciliation_required"
    )
    assert (
        HIEFailureClass.USER_ACTION_REQUIRED.value
        == "user_action_required"
    )
    assert HIEFailureClass.FAIL_CLOSED.value == "fail_closed"


@pytest.mark.parametrize(
    "error_type",
    [
        HIERetryableError,
        HIEReconciliationRequiredError,
        HIEUserActionRequiredError,
        HIEFailClosedError,
    ],
)
def test_typed_provider_failures_expose_classification(error_type):
    error = error_type("provider failure")

    assert classify_hie_failure(error) is error.failure_class


@pytest.mark.parametrize(
    "error_type",
    [
        TimeoutError,
        ConnectionError,
    ],
)
def test_transport_failures_are_retryable(error_type):
    assert (
        classify_hie_failure(
            error_type("transport failure")
        )
        is HIEFailureClass.RETRYABLE
    )


def test_untyped_provider_failure_fails_closed():
    assert (
        classify_hie_failure(
            RuntimeError("unexpected provider failure")
        )
        is HIEFailureClass.FAIL_CLOSED
    )


@pytest.mark.parametrize(
    "status_code",
    [
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    ],
)
def test_transient_http_failures_are_retryable(status_code):
    error = HIEProviderHTTPError(status_code)

    assert error.status_code == status_code
    assert (
        classify_hie_failure(error)
        is HIEFailureClass.RETRYABLE
    )


@pytest.mark.parametrize(
    "status_code",
    [
        400,
        401,
        403,
        404,
        409,
        422,
    ],
)
def test_non_transient_http_failures_require_user_action(status_code):
    error = HIEProviderHTTPError(status_code)

    assert error.status_code == status_code
    assert (
        classify_hie_failure(error)
        is HIEFailureClass.USER_ACTION_REQUIRED
    )


@pytest.mark.parametrize(
    "error_type",
    [
        HIEReconciliationRequiredError,
        HIEUserActionRequiredError,
        HIEFailClosedError,
    ],
)
def test_explicit_failure_classes_are_not_reclassified(error_type):
    error = error_type("explicit classification")

    assert classify_hie_failure(error) is error.failure_class


@pytest.mark.parametrize(
    "status_code",
    [
        99,
        600,
    ],
)
def test_invalid_http_status_codes_are_rejected(status_code):
    with pytest.raises(
        ValueError,
        match="between 100 and 599",
    ):
        HIEProviderHTTPError(status_code)