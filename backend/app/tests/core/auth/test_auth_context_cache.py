import pytest

from flask import g

from app.core.auth.user.services import clinic_context_service
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.core.utils.decorators import _load_auth_context


def test_auth_context_does_not_cache_failed_clinic_resolution(
    app,
    clinic,
    make_user,
    auth_headers_for,
    monkeypatch,
):
    super_admin = make_user(
        role=Role.SUPER_ADMIN,
    )

    headers = auth_headers_for(
        super_admin,
        clinic_context_id=clinic.id,
    )

    calls = []

    def fake_resolve_effective_clinic_id(
        *,
        user_id,
        jwt_payload,
    ):
        calls.append(
            {
                "user_id": user_id,
                "jwt_payload": jwt_payload,
            }
        )

        if len(calls) == 1:
            raise ValidationError(
                "Synthetic clinic context failure"
            )

        return clinic.id

    monkeypatch.setattr(
        clinic_context_service,
        "resolve_effective_clinic_id",
        fake_resolve_effective_clinic_id,
    )

    with app.test_request_context(
        "/api/v1/patients",
        headers=headers,
    ):
        with pytest.raises(
            ValidationError,
            match="Synthetic clinic context failure",
        ):
            _load_auth_context()

        assert getattr(
            g,
            "_auth_context_request",
            None,
        ) is None

        _load_auth_context()

        assert g.current_user_id == super_admin.id
        assert g.current_user_role == Role.SUPER_ADMIN.value
        assert g.current_clinic_id == clinic.id
        assert len(calls) == 2


def test_auth_context_reloads_between_requests_in_shared_app_context(
    app,
    clinic,
    make_user,
    auth_headers_for,
):
    receptionist = make_user(
        clinic=clinic,
        role=Role.RECEPTIONIST,
        email="auth-context-receptionist@test.com",
    )

    doctor = make_user(
        clinic=clinic,
        role=Role.DOCTOR,
        email="auth-context-doctor@test.com",
    )

    receptionist_headers = auth_headers_for(
        receptionist,
        role=Role.RECEPTIONIST,
    )

    doctor_headers = auth_headers_for(
        doctor,
        role=Role.DOCTOR,
    )

    with app.test_request_context(
        "/api/v1/patients",
        headers=receptionist_headers,
    ):
        _load_auth_context()

        assert g.current_user_id == receptionist.id
        assert g.current_user_role == Role.RECEPTIONIST.value
        assert g.current_clinic_id == clinic.id

    with app.test_request_context(
        "/api/v1/consultations/",
        headers=doctor_headers,
    ):
        _load_auth_context()

        assert g.current_user_id == doctor.id
        assert g.current_user_role == Role.DOCTOR.value
        assert g.current_clinic_id == clinic.id
