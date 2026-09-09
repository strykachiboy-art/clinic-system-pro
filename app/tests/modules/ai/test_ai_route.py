from __future__ import annotations

import pytest

from app.core.enums.role_enums import Role
from app.core.exceptions import NotFoundError, ValidationError
from app.extensions import db, limiter
from app.modules.ai.routes.ai_route import ai_bp


# ============================================================================
# HELPERS
# ============================================================================


AI_ALLOWED_ROLES = [
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
]


def auth_headers_for_user(app, user, role=None):
    from flask_jwt_extended import create_access_token

    with app.app_context():
        token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "role": (
                    role.value
                    if isinstance(role, Role)
                    else (
                        user.role.value
                        if hasattr(user.role, "value")
                        else user.role
                    )
                ),
            },
        )

    return {
        "Authorization": f"Bearer {token}",
    }


def register_ai_blueprint(app):
    if "ai" not in app.blueprints:
        app.register_blueprint(ai_bp)


def post_json(
    app,
    endpoint,
    headers,
    payload,
):
    return app.test_client().post(
        endpoint,
        headers=headers,
        json=payload,
    )


def valid_drug_payload():
    return {
        "drug_names": [
            "Aspirin",
            "Warfarin",
        ]
    }


def valid_triage_payload(patient_id):
    return {
        "patient_id": patient_id,
        "symptoms": "Fever and cough",
    }


def valid_lab_payload():
    return {
        "result_data": {
            "hemoglobin": 13.2,
            "wbc": 7.1,
        }
    }


# ============================================================================
# RATE-LIMITER ISOLATION
# ============================================================================


@pytest.fixture(autouse=True)
def isolate_ai_limiter(app):
    with app.app_context():
        if getattr(limiter, "_storage", None) is not None:
            try:
                limiter.reset()
            except Exception:
                pass

    yield

    with app.app_context():
        if getattr(limiter, "_storage", None) is not None:
            try:
                limiter.reset()
            except Exception:
                pass


# ============================================================================
# AUTHENTICATION / AUTHORIZATION
# ============================================================================


def test_drug_interactions_requires_authentication(app):
    with app.app_context():
        register_ai_blueprint(app)

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            json=valid_drug_payload(),
        )

        assert response.status_code == 401


def test_triage_requires_authentication(app):
    with app.app_context():
        register_ai_blueprint(app)

        response = app.test_client().post(
            "/api/ai/triage",
            json={
                "patient_id": 1,
                "symptoms": "Fever",
            },
        )

        assert response.status_code == 401


def test_lab_results_requires_authentication(app):
    with app.app_context():
        register_ai_blueprint(app)

        response = app.test_client().post(
            "/api/ai/lab-results/interpret",
            json=valid_lab_payload(),
        )

        assert response.status_code == 401


@pytest.mark.parametrize("role", AI_ALLOWED_ROLES)
def test_ai_roles_are_allowed(
    app,
    clinic,
    make_user,
    role,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=role,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            lambda **kwargs: {
                "summary": "No interaction found.",
                "interactions": [],
                "recommendations": [],
            },
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 200


def test_unauthorized_role_is_rejected(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.PATIENT,
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 403

        body = response.get_json()

        assert body["error"] == "Insufficient permissions"


def test_missing_role_claim_is_rejected(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        from flask_jwt_extended import create_access_token

        token = create_access_token(
            identity=str(user.id),
        )

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json=valid_drug_payload(),
        )

        assert response.status_code == 403


def test_invalid_jwt_identity_is_rejected(
    app,
):
    with app.app_context():
        register_ai_blueprint(app)

        from flask_jwt_extended import create_access_token

        token = create_access_token(
            identity="not-an-integer",
            additional_claims={
                "role": Role.DOCTOR.value,
            },
        )

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json=valid_drug_payload(),
        )

        assert response.status_code == 401


def test_non_positive_jwt_identity_is_rejected(
    app,
):
    with app.app_context():
        register_ai_blueprint(app)

        from flask_jwt_extended import create_access_token

        token = create_access_token(
            identity="-1",
            additional_claims={
                "role": Role.DOCTOR.value,
            },
        )

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json=valid_drug_payload(),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid authentication identity"


# ============================================================================
# CURRENT USER / CLINIC
# ============================================================================


def test_current_user_returns_authenticated_user(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        headers = auth_headers_for_user(app, user)

        from flask_jwt_extended import verify_jwt_in_request

        with app.test_request_context(
            "/api/ai/drug-interactions",
            headers=headers,
        ):
            verify_jwt_in_request()

            from app.modules.ai.routes.ai_route import _current_user

            result = _current_user()

            assert result.id == user.id


def test_current_user_rejects_nonexistent_user(
    app,
):
    with app.app_context():
        register_ai_blueprint(app)

        from flask_jwt_extended import create_access_token

        token = create_access_token(
            identity="999999",
            additional_claims={
                "role": Role.DOCTOR.value,
            },
        )

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json=valid_drug_payload(),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Authenticated user could not be resolved"
        )


def test_current_user_rejects_inactive_user(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        user.is_active = False
        db.session.flush()

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "User account is inactive"


def test_current_clinic_requires_user_clinic(
    app,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=None,
            role=Role.DOCTOR,
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Authenticated user is not associated with a clinic"
        )


def test_current_clinic_rejects_invalid_clinic_id(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        user.clinic_id = -1
        db.session.flush()

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Authenticated user has an invalid clinic"
        )


# ============================================================================
# REQUEST BODY VALIDATION
# ============================================================================


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/ai/drug-interactions",
        "/api/ai/triage",
        "/api/ai/lab-results/interpret",
    ],
)
def test_ai_routes_reject_empty_payload(
    app,
    clinic,
    make_user,
    endpoint,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = post_json(
            app,
            endpoint,
            auth_headers_for_user(app, user),
            {},
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid request payload"
        assert "details" in body


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/ai/drug-interactions",
        "/api/ai/triage",
        "/api/ai/lab-results/interpret",
    ],
)
@pytest.mark.parametrize(
    "payload",
    [
        [],
        "invalid",
        123,
        True,
        None,
    ],
)
def test_ai_routes_reject_non_object_json(
    app,
    clinic,
    make_user,
    endpoint,
    payload,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = post_json(
            app,
            endpoint,
            auth_headers_for_user(app, user),
            payload,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Request body must be a JSON object"
        )


def test_drug_interactions_rejects_unknown_fields(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        payload = valid_drug_payload()
        payload["provider"] = "openai"

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            payload,
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid request payload"


def test_triage_rejects_unknown_fields(
    app,
    clinic,
    patient,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        payload = valid_triage_payload(patient.id)
        payload["clinic_id"] = clinic.id

        response = post_json(
            app,
            "/api/ai/triage",
            auth_headers_for_user(app, user),
            payload,
        )

        assert response.status_code == 422


def test_lab_results_rejects_unknown_fields(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        payload = valid_lab_payload()
        payload["provider"] = "development"

        response = post_json(
            app,
            "/api/ai/lab-results/interpret",
            auth_headers_for_user(app, user),
            payload,
        )

        assert response.status_code == 422


# ============================================================================
# DRUG INTERACTION ROUTE
# ============================================================================


def test_drug_interactions_success(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            lambda **kwargs: {
                "summary": "No clinically significant interaction found.",
                "interactions": [],
                "recommendations": [
                    "Continue routine monitoring."
                ],
            },
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["summary"] == (
            "No clinically significant interaction found."
        )


def test_drug_interactions_passes_authenticated_context(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        captured = {}

        def fake_service(**kwargs):
            captured.update(kwargs)

            return {
                "summary": "No interaction found.",
                "interactions": [],
                "recommendations": [],
            }

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            fake_service,
        )

        payload = valid_drug_payload()
        payload["clinic_id"] = 999999

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            payload,
        )

        assert response.status_code == 422


def test_drug_interactions_uses_authenticated_clinic_and_user(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        captured = {}

        def fake_service(**kwargs):
            captured.update(kwargs)

            return {
                "summary": "No interaction found.",
                "interactions": [],
                "recommendations": [],
            }

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            fake_service,
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 200
        assert captured["clinic_id"] == clinic.id
        assert captured["user_id"] == user.id
        assert "ip_address" in captured


def test_drug_interactions_passes_client_ip(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        captured = {}

        def fake_service(**kwargs):
            captured.update(kwargs)

            return {
                "summary": "No interaction found.",
                "interactions": [],
                "recommendations": [],
            }

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            fake_service,
        )

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json=valid_drug_payload(),
            environ_base={
                "REMOTE_ADDR": "203.0.113.10",
            },
        )

        assert response.status_code == 200
        assert captured["ip_address"] == "203.0.113.10"


def test_drug_interactions_validation_error(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            {
                "drug_names": [
                    "Aspirin",
                ]
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid request payload"
        assert "details" in body


def test_drug_interactions_domain_error(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            lambda **kwargs: (_ for _ in ()).throw(
                ValidationError("AI service failed")
            ),
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "AI service failed"


def test_drug_interactions_invalid_service_response(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            lambda **kwargs: {
                "summary": "Invalid response",
                "interactions": [],
                "recommendations": [],
                "unexpected": "blocked",
            },
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False


# ============================================================================
# TRIAGE ROUTE
# ============================================================================


def test_triage_success(
    app,
    clinic,
    patient,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.assist_triage",
            lambda **kwargs: {
                "summary": "Patient requires assessment.",
                "risk_score": "medium",
                "recommendation": "Arrange clinical review.",
            },
        )

        response = post_json(
            app,
            "/api/ai/triage",
            auth_headers_for_user(app, user),
            valid_triage_payload(patient.id),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["risk_score"] == "medium"


def test_triage_validation_error(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = post_json(
            app,
            "/api/ai/triage",
            auth_headers_for_user(app, user),
            {
                "symptoms": "Fever",
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid request payload"
        assert "details" in body


def test_triage_passes_authenticated_context(
    app,
    clinic,
    patient,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        captured = {}

        def fake_service(**kwargs):
            captured.update(kwargs)

            return {
                "summary": "Assessment complete.",
                "risk_score": "low",
                "recommendation": "Routine follow-up.",
            }

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.assist_triage",
            fake_service,
        )

        response = post_json(
            app,
            "/api/ai/triage",
            auth_headers_for_user(app, user),
            valid_triage_payload(patient.id),
        )

        assert response.status_code == 200
        assert captured["clinic_id"] == clinic.id
        assert captured["user_id"] == user.id
        assert "ip_address" in captured


def test_triage_invalid_service_response(
    app,
    clinic,
    patient,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.assist_triage",
            lambda **kwargs: {
                "summary": "Assessment",
                "risk_score": "invalid-risk",
                "recommendation": "Review",
            },
        )

        response = post_json(
            app,
            "/api/ai/triage",
            auth_headers_for_user(app, user),
            valid_triage_payload(patient.id),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False


# ============================================================================
# LAB RESULT ROUTE
# ============================================================================


def test_lab_results_success(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.interpret_lab_results",
            lambda **kwargs: {
                "summary": "Laboratory results reviewed.",
                "interpretation": (
                    "Results require clinical correlation."
                ),
                "abnormal_findings": [],
                "recommendations": [],
            },
        )

        response = post_json(
            app,
            "/api/ai/lab-results/interpret",
            auth_headers_for_user(app, user),
            valid_lab_payload(),
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["summary"] == (
            "Laboratory results reviewed."
        )


def test_lab_results_validation_error(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        response = post_json(
            app,
            "/api/ai/lab-results/interpret",
            auth_headers_for_user(app, user),
            {
                "result_data": {},
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid request payload"
        assert "details" in body


def test_lab_results_passes_authenticated_context(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        captured = {}

        def fake_service(**kwargs):
            captured.update(kwargs)

            return {
                "summary": "Results reviewed.",
                "interpretation": "Clinical correlation required.",
                "abnormal_findings": [],
                "recommendations": [],
            }

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.interpret_lab_results",
            fake_service,
        )

        response = post_json(
            app,
            "/api/ai/lab-results/interpret",
            auth_headers_for_user(app, user),
            valid_lab_payload(),
        )

        assert response.status_code == 200
        assert captured["clinic_id"] == clinic.id
        assert captured["user_id"] == user.id
        assert "ip_address" in captured


def test_lab_results_domain_error(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.interpret_lab_results",
            lambda **kwargs: (_ for _ in ()).throw(
                NotFoundError("Lab order 99999 not found")
            ),
        )

        response = post_json(
            app,
            "/api/ai/lab-results/interpret",
            auth_headers_for_user(app, user),
            {
                "lab_order_id": 99999,
                "result_data": {
                    "hemoglobin": 13.2,
                },
            },
        )

        assert response.status_code == 404

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Lab order 99999 not found"


def test_lab_results_invalid_service_response(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.interpret_lab_results",
            lambda **kwargs: {
                "summary": "Results",
                "interpretation": "Review required.",
                "abnormal_findings": [],
                "recommendations": [],
                "unexpected": "blocked",
            },
        )

        response = post_json(
            app,
            "/api/ai/lab-results/interpret",
            auth_headers_for_user(app, user),
            valid_lab_payload(),
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False


# ============================================================================
# RESPONSE CONTRACT
# ============================================================================


def test_drug_interactions_response_contract(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.PHARMACIST,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            lambda **kwargs: {
                "summary": "No interaction detected.",
                "interactions": [],
                "recommendations": [],
            },
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            valid_drug_payload(),
        )

        body = response.get_json()

        assert set(body.keys()) == {
            "success",
            "data",
        }

        assert body["success"] is True
        assert isinstance(body["data"], dict)


def test_triage_response_contract(
    app,
    clinic,
    patient,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.assist_triage",
            lambda **kwargs: {
                "summary": "Assessment complete.",
                "risk_score": "low",
                "recommendation": "Routine monitoring.",
            },
        )

        response = post_json(
            app,
            "/api/ai/triage",
            auth_headers_for_user(app, user),
            valid_triage_payload(patient.id),
        )

        body = response.get_json()

        assert set(body.keys()) == {
            "success",
            "data",
        }

        assert body["success"] is True
        assert body["data"]["risk_score"] == "low"


def test_lab_results_response_contract(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.interpret_lab_results",
            lambda **kwargs: {
                "summary": "Results reviewed.",
                "interpretation": "Clinical correlation required.",
                "abnormal_findings": [],
                "recommendations": [],
            },
        )

        response = post_json(
            app,
            "/api/ai/lab-results/interpret",
            auth_headers_for_user(app, user),
            valid_lab_payload(),
        )

        body = response.get_json()

        assert set(body.keys()) == {
            "success",
            "data",
        }

        assert body["success"] is True
        assert isinstance(body["data"], dict)


# ============================================================================
# MALFORMED REQUESTS
# ============================================================================


def test_drug_interactions_rejects_invalid_drug_names(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = post_json(
            app,
            "/api/ai/drug-interactions",
            auth_headers_for_user(app, user),
            {
                "drug_names": [
                    "Aspirin",
                    "Aspirin",
                ],
            },
        )

        assert response.status_code == 422


def test_triage_rejects_blank_symptoms(
    app,
    clinic,
    patient,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = post_json(
            app,
            "/api/ai/triage",
            auth_headers_for_user(app, user),
            {
                "patient_id": patient.id,
                "symptoms": "   ",
            },
        )

        assert response.status_code == 422


def test_triage_rejects_invalid_patient_id(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        response = post_json(
            app,
            "/api/ai/triage",
            auth_headers_for_user(app, user),
            {
                "patient_id": 0,
                "symptoms": "Fever",
            },
        )

        assert response.status_code == 422


def test_lab_results_rejects_empty_result_data(
    app,
    clinic,
    make_user,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        response = post_json(
            app,
            "/api/ai/lab-results/interpret",
            auth_headers_for_user(app, user),
            {
                "result_data": {},
            },
        )

        assert response.status_code == 422


# ============================================================================
# RATE LIMITING
# ============================================================================


def test_ai_rate_limit_is_enforced(
    app,
    clinic,
    make_user,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        monkeypatch.setattr(
            "app.modules.ai.routes.ai_route.check_drug_interactions",
            lambda **kwargs: {
                "summary": "No interaction found.",
                "interactions": [],
                "recommendations": [],
            },
        )

        client = app.test_client()
        headers = auth_headers_for_user(app, user)

        responses = [
            client.post(
                "/api/ai/drug-interactions",
                headers=headers,
                json=valid_drug_payload(),
            )
            for _ in range(11)
        ]

        assert all(
            response.status_code == 200
            for response in responses[:10]
        )

        assert responses[10].status_code == 429