from __future__ import annotations

import pytest

from app.core.enums.ai_enums import AIFeature
from app.core.enums.ai_enums import AIRiskLevel
from app.extensions import db
from app.modules.ai.ai_provider_exceptions import (
    AIFailClosedError,
    AIProviderFailureClass,
    AIProviderHTTPError,
    AIProviderUnavailableError,
    AIReconciliationRequiredError,
    AIRetryableError,
    AIUserInterventionRequiredError,
    classify_ai_failure,
)
from app.modules.ai.models.ai_model import AILog
from app.modules.ai.services import ai_service


def _valid_drug_result():
    return {
        "summary": (
            "No clinically significant interaction found."
        ),
        "interactions": [],
        "recommendations": [
            "Continue routine monitoring.",
        ],
    }


def test_failure_class_defaults_to_fail_closed():
    error = AIFailClosedError(
        "provider response cannot be trusted"
    )

    assert error.failure_class is (
        AIProviderFailureClass.FAIL_CLOSED
    )


@pytest.mark.parametrize(
    "error,expected",
    [
        (
            AIRetryableError("retry"),
            AIProviderFailureClass.RETRYABLE,
        ),
        (
            AIReconciliationRequiredError("unknown"),
            AIProviderFailureClass.RECONCILIATION_REQUIRED,
        ),
        (
            AIUserInterventionRequiredError("action"),
            AIProviderFailureClass.USER_INTERVENTION_REQUIRED,
        ),
        (
            AIFailClosedError("closed"),
            AIProviderFailureClass.FAIL_CLOSED,
        ),
        (
            AIProviderUnavailableError("unavailable"),
            AIProviderFailureClass.RETRYABLE,
        ),
    ],
)
def test_typed_provider_failures_preserve_classification(
    error,
    expected,
):
    assert classify_ai_failure(error) is expected


@pytest.mark.parametrize(
    "status_code,expected",
    [
        (
            408,
            AIProviderFailureClass.RETRYABLE,
        ),
        (
            425,
            AIProviderFailureClass.RETRYABLE,
        ),
        (
            429,
            AIProviderFailureClass.RETRYABLE,
        ),
        (
            500,
            AIProviderFailureClass.RETRYABLE,
        ),
        (
            502,
            AIProviderFailureClass.RETRYABLE,
        ),
        (
            503,
            AIProviderFailureClass.RETRYABLE,
        ),
        (
            504,
            AIProviderFailureClass.RETRYABLE,
        ),
    ],
)
def test_http_failure_maps_to_retryable(
    status_code,
    expected,
):
    error = AIProviderHTTPError(
        status_code
    )

    assert error.status_code == status_code
    assert error.failure_class is expected
    assert classify_ai_failure(error) is expected


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
def test_http_failure_maps_to_user_intervention(
    status_code,
):
    error = AIProviderHTTPError(
        status_code
    )

    assert error.status_code == status_code
    assert (
        error.failure_class
        is AIProviderFailureClass.USER_INTERVENTION_REQUIRED
    )


@pytest.mark.parametrize(
    "status_code",
    [
        99,
        600,
        -1,
    ],
)
def test_http_status_validation_rejects_invalid_values(
    status_code,
):
    with pytest.raises(
        ValueError,
        match="between 100 and 599",
    ):
        AIProviderHTTPError(
            status_code
        )


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timeout"),
        ConnectionError("connection"),
    ],
)
def test_builtin_timeout_and_connection_are_retryable(
    error,
):
    assert (
        classify_ai_failure(error)
        is AIProviderFailureClass.RETRYABLE
    )


def test_openai_style_timeout_name_is_retryable():
    error = type(
        "APITimeoutError",
        (Exception,),
        {},
    )(
        "timeout"
    )

    assert (
        classify_ai_failure(error)
        is AIProviderFailureClass.RETRYABLE
    )


def test_openai_style_connection_name_is_retryable():
    error = type(
        "APIConnectionError",
        (Exception,),
        {},
    )(
        "connection"
    )

    assert (
        classify_ai_failure(error)
        is AIProviderFailureClass.RETRYABLE
    )


def test_openai_style_rate_limit_name_is_retryable():
    error = type(
        "RateLimitError",
        (Exception,),
        {},
    )(
        "rate limited"
    )

    assert (
        classify_ai_failure(error)
        is AIProviderFailureClass.RETRYABLE
    )


def test_unknown_outcome_name_requires_reconciliation():
    error = type(
        "UnknownOutcomeError",
        (Exception,),
        {},
    )(
        "outcome unknown"
    )

    assert (
        classify_ai_failure(error)
        is AIProviderFailureClass.RECONCILIATION_REQUIRED
    )


def test_status_code_attribute_is_classified():
    error = type(
        "ProviderStatusError",
        (Exception,),
        {"status_code": 503},
    )(
        "server failure"
    )

    assert (
        classify_ai_failure(error)
        is AIProviderFailureClass.RETRYABLE
    )


def test_status_code_attribute_maps_user_intervention():
    error = type(
        "ProviderStatusError",
        (Exception,),
        {"status_code": 403},
    )(
        "forbidden"
    )

    assert (
        classify_ai_failure(error)
        is AIProviderFailureClass.USER_INTERVENTION_REQUIRED
    )


def test_unrecognized_provider_error_fails_closed():
    assert (
        classify_ai_failure(
            RuntimeError("unexpected provider failure")
        )
        is AIProviderFailureClass.FAIL_CLOSED
    )


@pytest.mark.parametrize(
    "provider_error",
    [
        AIRetryableError(
            "deterministic retryable failure"
        ),
        AIReconciliationRequiredError(
            "deterministic unknown outcome"
        ),
        AIUserInterventionRequiredError(
            "deterministic user intervention"
        ),
        AIFailClosedError(
            "deterministic fail closed"
        ),
    ],
)
def test_run_feature_propagates_typed_provider_failure(
    app,
    clinic,
    provider_error,
):
    with app.app_context():

        def provider(feature, payload):
            raise provider_error

        with pytest.raises(
            type(provider_error)
        ) as exc_info:
            ai_service._run_feature(
                feature=AIFeature.DRUG_INTERACTION_CHECK,
                clinic_id=clinic.id,
                payload={
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ],
                },
                provider=provider,
            )

        assert (
            exc_info.value.failure_class
            is provider_error.failure_class
        )

        logs = (
            db.session.execute(
                db.select(AILog).where(
                    AILog.clinic_id == clinic.id,
                )
            )
            .scalars()
            .all()
        )

        assert logs == []


def test_user_intervention_failure_has_client_safe_status():
    error = AIUserInterventionRequiredError(
        "provider requires intervention"
    )

    assert error.status_code == 422


def test_provider_failure_default_has_service_unavailable_status():
    error = AIRetryableError(
        "retryable provider failure"
    )

    assert error.status_code == 503


def test_http_error_message_is_safe():
    error = AIProviderHTTPError(
        503,
        "provider unavailable",
    )

    assert "provider unavailable" in str(error)
    assert "api_key" not in str(error).lower()
    assert "authorization" not in str(error).lower()


def test_valid_result_contract_remains_unchanged(
    app,
    clinic,
):
    with app.app_context():
        result = ai_service._run_feature(
            feature=AIFeature.DRUG_INTERACTION_CHECK,
            clinic_id=clinic.id,
            payload={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ],
            },
            provider=lambda feature, payload: (
                _valid_drug_result()
            ),
        )

        assert result == _valid_drug_result()

        logs = (
            db.session.execute(
                db.select(AILog).where(
                    AILog.clinic_id == clinic.id,
                )
            )
            .scalars()
            .all()
        )

        assert len(logs) == 1
        assert logs[0].risk_level is (
            AIRiskLevel.MEDIUM
        )