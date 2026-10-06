from __future__ import annotations

from app.core.enums.role_enums import Role
from app.extensions import db
from app.modules.ai.models.ai_model import AILog
from app.modules.ai.routes.ai_route import ai_bp
from app.modules.ai.services import ai_service
from app.modules.clinic.models.clinic_model import Clinic


def register_ai_blueprint(app):
    if "ai" not in app.blueprints:
        app.register_blueprint(ai_bp)


def test_triage_cross_clinic_patient_fails_closed_before_provider(
    app,
    clinic,
    make_clinic,
    make_patient,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        other_clinic = make_clinic(
            name="AI Tenant Isolation Triage Clinic",
        )

        other_patient = make_patient(
            clinic=other_clinic,
        )

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        before_credits = clinic.ai_credits
        before_requests = clinic.ai_requests_this_month

        db.session.commit()

        provider_calls = {
            "count": 0,
        }

        def provider(feature, payload):
            provider_calls["count"] += 1
            raise AssertionError(
                "AI provider must not run for a cross-clinic patient"
            )

        monkeypatch.setattr(
            ai_service,
            "_get_configured_provider",
            lambda: provider,
        )

        response = app.test_client().post(
            "/api/v1/ai/triage",
            headers=auth_headers_for(user),
            json={
                "patient_id": other_patient.id,
                "symptoms": "Fever and cough",
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Patient does not belong to the authenticated clinic"
        )

        assert provider_calls["count"] == 0

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


def test_drug_interactions_cross_clinic_patient_fails_closed_before_provider(
    app,
    clinic,
    make_clinic,
    make_patient,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        other_clinic = make_clinic(
            name="AI Tenant Isolation Drug Clinic",
        )

        other_patient = make_patient(
            clinic=other_clinic,
        )

        user = make_user(
            clinic=clinic,
            role=Role.DOCTOR,
        )

        before_credits = clinic.ai_credits
        before_requests = clinic.ai_requests_this_month

        db.session.commit()

        provider_calls = {
            "count": 0,
        }

        def provider(feature, payload):
            provider_calls["count"] += 1
            raise AssertionError(
                "AI provider must not run for a cross-clinic patient"
            )

        monkeypatch.setattr(
            ai_service,
            "_get_configured_provider",
            lambda: provider,
        )

        response = app.test_client().post(
            "/api/v1/ai/drug-interactions",
            headers=auth_headers_for(user),
            json={
                "drug_names": [
                    "Aspirin",
                    "Warfarin",
                ],
                "patient_id": other_patient.id,
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Patient does not belong to the authenticated clinic"
        )

        assert provider_calls["count"] == 0

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


def test_lab_results_cross_clinic_order_fails_closed_before_provider(
    app,
    clinic,
    make_clinic,
    make_patient,
    make_staff,
    make_lab_test,
    make_lab_order,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    with app.app_context():
        register_ai_blueprint(app)

        other_clinic = make_clinic(
            name="AI Tenant Isolation Lab Clinic",
        )

        other_patient = make_patient(
            clinic=other_clinic,
        )

        other_staff = make_staff(
            other_clinic,
            role=Role.LAB_TECHNICIAN,
        )

        other_lab_test = make_lab_test(
            clinic=other_clinic,
        )

        other_lab_order = make_lab_order(
            other_clinic,
            other_patient,
            other_staff,
            [other_lab_test],
        )

        user = make_user(
            clinic=clinic,
            role=Role.LAB_TECHNICIAN,
        )

        before_credits = clinic.ai_credits
        before_requests = clinic.ai_requests_this_month

        db.session.commit()

        provider_calls = {
            "count": 0,
        }

        def provider(feature, payload):
            provider_calls["count"] += 1
            raise AssertionError(
                "AI provider must not run for a cross-clinic lab order"
            )

        monkeypatch.setattr(
            ai_service,
            "_get_configured_provider",
            lambda: provider,
        )

        response = app.test_client().post(
            "/api/v1/ai/lab-results/interpret",
            headers=auth_headers_for(user),
            json={
                "lab_order_id": other_lab_order.id,
                "result_data": {
                    "hemoglobin": 13.2,
                },
            },
        )

        assert response.status_code == 422

        body = response.get_json()

        assert body["success"] is False
        assert body["error"] == (
            "Lab order does not belong to the authenticated clinic"
        )

        assert provider_calls["count"] == 0

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