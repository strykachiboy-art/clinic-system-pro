from __future__ import annotations

import pytest

from app.core.enums.ai_enums import AIFeature
from app.core.enums.role_enums import Role
from app.extensions import db
from app.modules.ai.ai_provider_exceptions import (
    AIProviderFailureClass,
    AIProviderHTTPError,
)
from app.modules.ai.models.ai_model import AILog
from app.modules.ai.routes.ai_route import ai_bp
from app.modules.ai.services import ai_service


def register_ai_blueprint(app):
    if "ai" not in app.blueprints:
        app.register_blueprint(ai_bp)


def valid_drug_payload():
    return {
        "drug_names": [
            "Aspirin",
            "Warfarin",
        ],
    }


@pytest.mark.parametrize(
    "status_code",
    [
        429,
        500,
        502,
        503,
        504,
    ],
)
def test_provider_http_failures_map_to_safe_api_status(
    app,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
    status_code,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        def failing_service(**kwargs):
            raise AIProviderHTTPError(
                status_code,
                "provider request failed",
            )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            failing_service,
        )

        response = app.test_client().post(
            "/api/v1/ai/drug-interactions",
            headers=auth_headers_for(user),
            json=valid_drug_payload(),
        )

        assert response.status_code == status_code

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "provider request failed"

        error_text = body["error"].lower()

        assert "api_key" not in error_text
        assert "authorization" not in error_text
        assert "secret" not in error_text


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
def test_provider_user_intervention_http_failures_preserve_provider_status(
    app,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
    status_code,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        def failing_service(**kwargs):
            raise AIProviderHTTPError(
                status_code,
                "provider requires intervention",
            )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            failing_service,
        )

        response = app.test_client().post(
            "/api/v1/ai/drug-interactions",
            headers=auth_headers_for(user),
            json=valid_drug_payload(),
        )

        assert response.status_code == status_code

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "provider requires intervention"
        )


def test_rate_limit_failure_rolls_back_ai_accounting(
    app,
    clinic,
):
    clinic_id = clinic.id

    before_credits = clinic.ai_credits
    before_requests = (
        clinic.ai_requests_this_month
    )

    db.session.commit()

    def rate_limited_provider(
        feature,
        payload,
    ):
        raise AIProviderHTTPError(
            429,
            "provider rate limit reached",
        )

    with app.app_context():
        with pytest.raises(
            AIProviderHTTPError
        ) as exc_info:
            ai_service._run_feature(
                feature=(
                    AIFeature.DRUG_INTERACTION_CHECK
                ),
                clinic_id=clinic_id,
                payload={
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ],
                },
                provider=rate_limited_provider,
            )

    assert exc_info.value.status_code == 429
    assert exc_info.value.failure_class is (
        AIProviderFailureClass.RETRYABLE
    )

    clinic_state = db.session.get(
        type(clinic),
        clinic_id,
    )

    assert clinic_state is not None
    assert clinic_state.ai_credits == before_credits
    assert clinic_state.ai_requests_this_month == (
        before_requests
    )

    logs = (
        db.session.execute(
            db.select(AILog).where(
                AILog.clinic_id == clinic_id,
            )
        )
        .scalars()
        .all()
    )

    assert logs == []


def test_rate_limit_recovery_succeeds_without_duplicate_local_state(
    app,
    clinic,
):
    clinic_id = clinic.id

    before_credits = clinic.ai_credits
    before_requests = (
        clinic.ai_requests_this_month
    )

    db.session.commit()

    calls = {
        "count": 0,
    }

    def rate_limited_provider(
        feature,
        payload,
    ):
        calls["count"] += 1

        raise AIProviderHTTPError(
            429,
            "provider rate limit reached",
        )

    with pytest.raises(
        AIProviderHTTPError
    ):
        ai_service._run_feature(
            feature=(
                AIFeature.DRUG_INTERACTION_CHECK
            ),
            clinic_id=clinic_id,
            payload={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ],
            },
            provider=rate_limited_provider,
        )

    assert calls["count"] == 1

    clinic_state = db.session.get(
        type(clinic),
        clinic_id,
    )

    assert clinic_state is not None
    assert clinic_state.ai_credits == before_credits
    assert clinic_state.ai_requests_this_month == (
        before_requests
    )

    result = ai_service._run_feature(
        feature=(
            AIFeature.DRUG_INTERACTION_CHECK
        ),
        clinic_id=clinic_id,
        payload={
            "drug_names": [
                "Aspirin",
                "Warfarin",
            ],
        },
        provider=lambda feature, payload: {
            "summary": (
                "No clinically significant "
                "interaction found."
            ),
            "interactions": [],
            "recommendations": [
                "Continue routine monitoring.",
            ],
        },
    )

    assert result["summary"] == (
        "No clinically significant interaction found."
    )

    clinic_state = db.session.get(
        type(clinic),
        clinic_id,
    )

    assert clinic_state is not None
    assert clinic_state.ai_credits == (
        before_credits - 1
    )
    assert clinic_state.ai_requests_this_month == (
        before_requests + 1
    )

    logs = (
        db.session.execute(
            db.select(AILog).where(
                AILog.clinic_id == clinic_id,
            )
        )
        .scalars()
        .all()
    )

    assert len(logs) == 1
    assert logs[0].credits_used == 1