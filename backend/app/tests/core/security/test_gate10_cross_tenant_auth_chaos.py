from __future__ import annotations

from app.core.enums.role_enums import Role
from app.modules.patient.models.patient_model import Patient


def test_forged_foreign_clinic_context_cannot_expand_patient_list(
    client,
    clinic,
    make_clinic,
    make_user,
    make_patient,
    auth_headers_for,
):
    foreign_clinic = make_clinic(
        name="Gate 10 Foreign Clinic",
    )

    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    own_patient = make_patient(
        clinic,
        first_name="Own",
        last_name="Patient",
    )

    foreign_patient = make_patient(
        foreign_clinic,
        first_name="Foreign",
        last_name="Patient",
    )

    headers = auth_headers_for(
        user,
        clinic_context_id=foreign_clinic.id,
    )

    response = client.get(
        "/api/v1/patients?page=1&per_page=50",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == [
        own_patient.id
    ]
    assert foreign_patient.id not in {
        item["id"] for item in data["items"]
    }


def test_forged_foreign_clinic_context_cannot_read_foreign_patient(
    client,
    clinic,
    make_clinic,
    make_user,
    make_patient,
    auth_headers_for,
):
    foreign_clinic = make_clinic(
        name="Gate 10 Foreign Read Clinic",
    )

    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    foreign_patient = make_patient(
        foreign_clinic,
        first_name="Protected",
        last_name="Patient",
    )

    headers = auth_headers_for(
        user,
        clinic_context_id=foreign_clinic.id,
    )

    response = client.get(
        f"/api/v1/patients/{foreign_patient.id}",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Patient does not belong to the authenticated user's clinic"
    )


def test_forged_foreign_clinic_context_cannot_mutate_foreign_patient(
    db_session,
    client,
    clinic,
    make_clinic,
    make_user,
    make_patient,
    auth_headers_for,
):
    foreign_clinic = make_clinic(
        name="Gate 10 Foreign Mutation Clinic",
    )

    user = make_user(
        clinic=clinic,
        role=Role.ADMIN,
    )

    foreign_patient = make_patient(
        foreign_clinic,
        first_name="Protected",
        last_name="Patient",
    )

    db_session.commit()
    db_session.expire_all()

    persisted_before = db_session.get(
        Patient,
        foreign_patient.id,
    )

    assert persisted_before is not None

    before_active = persisted_before.is_active

    headers = auth_headers_for(
        user,
        clinic_context_id=foreign_clinic.id,
    )

    response = client.patch(
        f"/api/v1/patients/{foreign_patient.id}/status",
        json={
            "is_active": not before_active,
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Patient does not belong to the authenticated user's clinic"
    )

    db_session.expire_all()

    persisted_after = db_session.get(
        Patient,
        foreign_patient.id,
    )

    assert persisted_after is not None
    assert persisted_after.is_active == before_active
