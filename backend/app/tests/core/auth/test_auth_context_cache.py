from flask import g

from app.core.enums.role_enums import Role
from app.core.utils.decorators import _load_auth_context


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
