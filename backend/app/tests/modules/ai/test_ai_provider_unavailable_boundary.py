from __future__ import annotations

import pytest

from app.core.enums.ai_enums import AIFeature
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.extensions import db
from app.modules.ai.models.ai_model import AILog
from app.modules.ai.routes.ai_route import ai_bp
from app.modules.ai.services import ai_service
from app.modules.clinic.models.clinic_model import Clinic


def register_ai_blueprint(app):
    if "ai" not in app.blueprints:
        app.register_blueprint(ai_bp)


def test_missing_openai_configuration_rolls_back_ai_accounting(
    app,
    clinic,
):
    clinic_id = clinic.id

    before_credits = clinic.ai_credits
    before_requests = clinic.ai_requests_this_month

    db.session.commit()

    with app.app_context():
        app.config["AI_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = None

        with pytest.raises(
            ValidationError,
            match="OPENAI_API_KEY is not configured",
        ):
            ai_service._run_feature(
                feature=AIFeature.DRUG_INTERACTION_CHECK,
                clinic_id=clinic_id,
                payload={
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ],
                },
            )

    clinic_state = db.session.get(
        Clinic,
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


def test_unsupported_provider_rolls_back_ai_accounting(
    app,
    clinic,
):
    clinic_id = clinic.id

    before_credits = clinic.ai_credits
    before_requests = clinic.ai_requests_this_month

    db.session.commit()

    with app.app_context():
        app.config["AI_PROVIDER"] = "unsupported-provider"

        with pytest.raises(
            ValidationError,
            match="Unsupported AI provider",
        ):
            ai_service._run_feature(
                feature=AIFeature.DRUG_INTERACTION_CHECK,
                clinic_id=clinic_id,
                payload={
                    "drug_names": [
                        "Aspirin",
                        "Warfarin",
                    ],
                },
            )

    clinic_state = db.session.get(
        Clinic,
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


def test_route_missing_openai_configuration_fails_closed(
    app,
    clinic,
    make_user,
    auth_headers_for,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        before_credits = clinic.ai_credits
        before_requests = clinic.ai_requests_this_month

        db.session.commit()

        app.config["AI_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = None

        response = app.test_client().post(
            "/api/v1/ai/drug-interactions",
            headers=auth_headers_for(user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ],
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "OPENAI_API_KEY is not configured"
        )

        error_text = body["error"].lower()

        assert "secret" not in error_text
        assert "authorization" not in error_text
        assert "api_key_value" not in error_text

        clinic_state = db.session.get(
            Clinic,
            clinic.id,
        )

        assert clinic_state is not None
        assert clinic_state.ai_credits == before_credits
        assert clinic_state.ai_requests_this_month == (
            before_requests
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