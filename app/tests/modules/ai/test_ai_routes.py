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


def auth_headers_for_user(app, user):
    """
    Build JWT headers using the project's JWT configuration.
    """
    from flask_jwt_extended import create_access_token

    with app.app_context():
        token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "role": (
                    user.role.value
                    if hasattr(user.role, "value")
                    else user.role
                ),
            },
        )

    return {
        "Authorization": f"Bearer {token}",
    }


def register_ai_blueprint(app):
    """
    Register the AI blueprint if the application factory has not
    already registered it.
    """
    if "ai" not in app.blueprints:
        app.register_blueprint(ai_bp)


# ============================================================================
# RATE-LIMITER ISOLATION
# ============================================================================


@pytest.fixture(autouse=True)
def isolate_ai_limiter(app):
    """
    Isolate Flask-Limiter state between AI route tests.

    The production AI routes intentionally enforce:

        10 requests per minute

    The limiter remains enabled during tests. We only clear its
    in-memory counters before and after each test so one test cannot
    cause another unrelated test to receive HTTP 429.
    """
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


def test_drug_interactions_requires_authentication(
    app,
):
    with app.app_context():
        register_ai_blueprint(app)

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

        assert response.status_code == 401


def test_triage_requires_authentication(
    app,
):
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


def test_lab_results_requires_authentication(
    app,
):
    with app.app_context():
        register_ai_blueprint(app)

        response = app.test_client().post(
            "/api/ai/lab-results/interpret",
            json={
                "result_data": {
                    "hemoglobin": 13.2,
                }
            },
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

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
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

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

        assert response.status_code == 403


# ============================================================================
# CURRENT USER
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
    clinic,
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
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
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

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
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

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Authenticated user is not associated with a clinic"
        )


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

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

        assert response.status_code == 200

        body = response.get_json()

        assert body["success"] is True
        assert body["data"]["summary"] == (
            "No clinically significant interaction found."
        )


def test_drug_interactions_passes_authenticated_clinic(
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
            json={
                "clinic_id": 999999,
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ],
            },
        )

        assert response.status_code == 200

        assert captured["clinic_id"] == clinic.id
        assert captured["clinic_id"] != 999999
        assert captured["user_id"] == user.id


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

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json={
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

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "AI service failed"


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

        response = app.test_client().post(
            "/api/ai/triage",
            headers=auth_headers_for_user(app, user),
            json={
                "patient_id": patient.id,
                "symptoms": "Fever and cough",
                "vitals": {
                    "temperature": 38.5,
                },
            },
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

        response = app.test_client().post(
            "/api/ai/triage",
            headers=auth_headers_for_user(app, user),
            json={
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

        response = app.test_client().post(
            "/api/ai/triage",
            headers=auth_headers_for_user(app, user),
            json={
                "clinic_id": 999999,
                "patient_id": patient.id,
                "symptoms": "Mild headache",
            },
        )

        assert response.status_code == 200
        assert captured["clinic_id"] == clinic.id
        assert captured["user_id"] == user.id


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

        response = app.test_client().post(
            "/api/ai/lab-results/interpret",
            headers=auth_headers_for_user(app, user),
            json={
                "result_data": {
                    "hemoglobin": 13.2,
                    "wbc": 7.1,
                }
            },
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

        response = app.test_client().post(
            "/api/ai/lab-results/interpret",
            headers=auth_headers_for_user(app, user),
            json={
                "result_data": {},
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid request payload"
        assert "details" in body


def test_lab_results_passes_authenticated_clinic(
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

        response = app.test_client().post(
            "/api/ai/lab-results/interpret",
            headers=auth_headers_for_user(app, user),
            json={
                "clinic_id": 999999,
                "result_data": {
                    "hemoglobin": 13.2,
                },
            },
        )

        assert response.status_code == 200

        assert captured["clinic_id"] == clinic.id
        assert captured["clinic_id"] != 999999
        assert captured["user_id"] == user.id


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

        response = app.test_client().post(
            "/api/ai/lab-results/interpret",
            headers=auth_headers_for_user(app, user),
            json={
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

        response = app.test_client().post(
            "/api/ai/drug-interactions",
            headers=auth_headers_for_user(app, user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ]
            },
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

        response = app.test_client().post(
            "/api/ai/triage",
            headers=auth_headers_for_user(app, user),
            json={
                "patient_id": patient.id,
                "symptoms": "Mild headache",
            },
        )

        body = response.get_json()

        assert set(body.keys()) == {
            "success",
            "data",
        }

        assert body["success"] is True
        assert body["data"]["risk_score"] == "low"


# ============================================================================
# MALFORMED / EMPTY REQUESTS
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

        response = app.test_client().post(
            endpoint,
            headers=auth_headers_for_user(app, user),
            json={},
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == "Invalid request payload"
        assert "details" in body