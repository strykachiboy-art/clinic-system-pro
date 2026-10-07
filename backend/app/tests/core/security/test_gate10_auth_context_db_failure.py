from __future__ import annotations

from sqlalchemy.exc import OperationalError

from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.auth.user.services import clinic_context_service
from app.modules.patient.routes import patient_route


def _raise_auth_database_failure(
    original_get,
):
    def _failing_get(model, identity, *args, **kwargs):
        if model is User:
            raise OperationalError(
                "auth context database unavailable",
                {},
                RuntimeError("simulated database outage"),
            )

        return original_get(
            model,
            identity,
            *args,
            **kwargs,
        )

    return _failing_get


def test_auth_context_db_failure_fails_closed_without_patient_fallback(
    client,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    headers = auth_headers_for(
        user,
        clinic_context_id=999999,
    )

    def _patient_service_must_not_run(*args, **kwargs):
        raise AssertionError(
            "patient service reached during auth context database failure"
        )

    monkeypatch.setattr(
        patient_route,
        "list_patients",
        _patient_service_must_not_run,
    )

    original_get = clinic_context_service.db.session.get

    monkeypatch.setattr(
        clinic_context_service.db.session,
        "get",
        _raise_auth_database_failure(original_get),
    )

    response = client.get(
        "/api/v1/patients?page=1&per_page=50",
        headers=headers,
    )

    assert response.status_code == 500

    body = response.get_json()

    assert body == {
        "success": False,
        "error": "Internal server error",
    }


def test_super_admin_context_db_failure_does_not_fall_back_to_system_scope(
    client,
    make_clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    selected_clinic = make_clinic(
        name="Gate 10 DB Failure Selected Clinic",
    )

    super_admin = make_user(
        role=Role.SUPER_ADMIN,
    )

    headers = auth_headers_for(
        super_admin,
        clinic_context_id=selected_clinic.id,
    )

    original_get = clinic_context_service.db.session.get

    monkeypatch.setattr(
        clinic_context_service.db.session,
        "get",
        _raise_auth_database_failure(original_get),
    )

    response = client.get(
        "/api/v1/auth/clinic-context",
        headers=headers,
    )

    assert response.status_code == 500

    body = response.get_json()

    assert body == {
        "success": False,
        "error": "Internal server error",
    }
