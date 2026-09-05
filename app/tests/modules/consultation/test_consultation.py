from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.enums.consultation_enums import (
    ConsultationStatus,
    ConsultationType,
)
from app.core.enums.role_enums import Role
from app.modules.consultation.models.consultation_model import (
    Consultation,
    ConsultationTemplate,
)


# ============================================================================
# HELPERS
# ============================================================================


def auth_headers(auth_headers_for, user, role=None):
    return auth_headers_for(user, role=role)


def consultation_payload(clinic, patient, staff, **overrides):
    payload = {
        "clinic_id": clinic.id,
        "patient_id": patient.id,
        "staff_id": staff.id,
    }
    payload.update(overrides)
    return payload


# ============================================================================
# AUTHENTICATION
# ============================================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/consultations/1"),
        ("PATCH", "/api/consultations/1"),
        ("POST", "/api/consultations/1/complete"),
        ("POST", "/api/consultations/1/cancel"),
        ("GET", "/api/consultations/patient/1"),
        ("GET", "/api/consultations/staff/1"),
        ("POST", "/api/consultations/templates"),
        ("GET", "/api/consultations/templates"),
    ],
)
def test_consultation_routes_require_authentication(client, method, path):
    response = client.open(
        path,
        method=method,
        json={},
    )

    assert response.status_code in (401, 422)


def test_start_consultation_requires_authentication(client):
    response = client.post(
        "/api/consultations/",
        json={},
    )

    assert response.status_code in (401, 422)


# ============================================================================
# ROLE AUTHORIZATION
# ============================================================================


@pytest.mark.parametrize("role", list(Role))
def test_read_routes_allow_only_read_roles(
    client,
    clinic,
    patient,
    make_staff,
    make_user,
    auth_headers_for,
    role,
):
    staff = make_staff(clinic, role=Role.DOCTOR)

    actor = make_user(
        clinic,
        role=role,
    )

    headers = auth_headers_for(actor, role=role)

    response = client.get(
        f"/api/consultations/{1}",
        headers=headers,
    )

    if role in (
        Role.ADMIN,
        Role.DOCTOR,
        Role.NURSE,
    ):
        assert response.status_code != 403
    else:
        assert response.status_code == 403


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.DOCTOR,
        Role.NURSE,
    ],
)
def test_get_consultation_allows_read_roles(
    client,
    db,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
    role,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=role,
    )

    response = client.get(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=role),
    )

    assert response.status_code == 200
    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == consultation.id


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.DOCTOR,
        Role.NURSE,
    ],
)
def test_update_consultation_allows_write_roles(
    client,
    db,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
    role,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=role,
    )

    response = client.patch(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=role),
        json={
            "diagnosis": "Updated diagnosis",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True


@pytest.mark.parametrize(
    "role",
    [
        Role.ADMIN,
        Role.DOCTOR,
    ],
)
def test_create_template_allows_template_roles(
    client,
    clinic,
    make_user,
    auth_headers_for,
    role,
):
    actor = make_user(
        clinic,
        role=role,
    )

    response = client.post(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=role),
        json={
            "name": "General Consultation",
            "structure": {
                "sections": [
                    "chief_complaint",
                    "symptoms",
                    "diagnosis",
                ]
            },
        },
    )

    assert response.status_code == 201
    assert response.get_json()["success"] is True


@pytest.mark.parametrize(
    "role",
    [
        Role.NURSE,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
    ],
)
def test_create_template_rejects_non_template_roles(
    client,
    clinic,
    make_user,
    auth_headers_for,
    role,
):
    actor = make_user(
        clinic,
        role=role,
    )

    response = client.post(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=role),
        json={
            "name": "Forbidden Template",
            "structure": {
                "sections": ["diagnosis"],
            },
        },
    )

    assert response.status_code == 403


# ============================================================================
# START CONSULTATION
# ============================================================================


@pytest.mark.parametrize(
    "consultation_type",
    list(ConsultationType),
)
def test_start_consultation_success(
    client,
    db,
    clinic,
    patient,
    make_staff,
    make_user,
    auth_headers_for,
    consultation_type,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json=consultation_payload(
            clinic,
            patient,
            staff,
            consultation_type=consultation_type.value,
            chief_complaint="Headache",
            symptoms="Severe headache",
        ),
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["patient_id"] == patient.id
    assert body["data"]["staff_id"] == staff.id
    assert body["data"]["consultation_type"] == consultation_type.value
    assert body["data"]["status"] == ConsultationStatus.IN_PROGRESS.value


def test_start_consultation_defaults_to_general_type(
    client,
    clinic,
    patient,
    make_staff,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json=consultation_payload(
            clinic,
            patient,
            staff,
        ),
    )

    assert response.status_code == 201
    assert (
        response.get_json()["data"]["consultation_type"]
        == ConsultationType.GENERAL.value
    )


def test_start_consultation_with_optional_fields(
    client,
    clinic,
    patient,
    make_staff,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json=consultation_payload(
            clinic,
            patient,
            staff,
            chief_complaint="Chest pain",
            symptoms="Pain for two hours",
        ),
    )

    assert response.status_code == 201

    data = response.get_json()["data"]

    assert data["chief_complaint"] == "Chest pain"
    assert data["symptoms"] == "Pain for two hours"


def test_start_consultation_supports_template(
    client,
    clinic,
    patient,
    make_staff,
    make_template,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    template = make_template(
        clinic=clinic,
        name="General Template",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json=consultation_payload(
            clinic,
            patient,
            staff,
            template_id=template.id,
        ),
    )

    assert response.status_code == 201
    assert response.get_json()["data"]["template_id"] == template.id


def test_start_consultation_with_appointment(
    client,
    clinic,
    patient,
    make_staff,
    make_appointment,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    appointment = make_appointment(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json=consultation_payload(
            clinic,
            patient,
            staff,
            appointment_id=appointment.id,
        ),
    )

    assert response.status_code == 201
    assert (
        response.get_json()["data"]["appointment_id"]
        == appointment.id
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"clinic_id": 1},
        {"clinic_id": 1, "patient_id": 1},
        {"clinic_id": "bad", "patient_id": 1, "staff_id": 1},
        {"clinic_id": 1, "patient_id": "bad", "staff_id": 1},
        {"clinic_id": 1, "patient_id": 1, "staff_id": "bad"},
    ],
)
def test_start_consultation_rejects_invalid_payload(
    client,
    clinic,
    make_user,
    auth_headers_for,
    payload,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json=payload,
    )

    assert response.status_code == 422


def test_start_consultation_missing_patient_returns_error(
    client,
    clinic,
    make_staff,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "clinic_id": clinic.id,
            "patient_id": 999999,
            "staff_id": staff.id,
        },
    )

    assert response.status_code == 404


def test_start_consultation_missing_staff_returns_error(
    client,
    clinic,
    patient,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "clinic_id": clinic.id,
            "patient_id": patient.id,
            "staff_id": 999999,
        },
    )

    assert response.status_code == 404


# ============================================================================
# GET CONSULTATION
# ============================================================================


def test_get_consultation_success(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        chief_complaint="Headache",
        symptoms="Pain",
        diagnosis="Migraine",
        treatment_plan="Rest",
        notes="Follow up",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["id"] == consultation.id
    assert data["chief_complaint"] == "Headache"
    assert data["symptoms"] == "Pain"
    assert data["diagnosis"] == "Migraine"
    assert data["treatment_plan"] == "Rest"
    assert data["notes"] == "Follow up"


def test_get_consultation_serializes_nullable_fields(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["appointment_id"] is None
    assert data["icd10_code"] is None
    assert data["chief_complaint"] is None
    assert data["symptoms"] is None
    assert data["diagnosis"] is None
    assert data["treatment_plan"] is None
    assert data["notes"] is None
    assert data["voice_note_url"] is None
    assert data["transcribed_text"] is None
    assert data["template_id"] is None


def test_get_consultation_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/999999",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 404


# ============================================================================
# UPDATE CONSULTATION
# ============================================================================


def test_update_consultation_success(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.patch(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "icd10_code": "G43.909",
            "chief_complaint": "Headache",
            "symptoms": "Throbbing pain",
            "diagnosis": "Migraine",
            "treatment_plan": "Medication and rest",
            "notes": "Review in one week",
            "voice_note_url": "https://example.com/voice.mp3",
            "transcribed_text": "Patient reports headache",
        },
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["icd10_code"] == "G43.909"
    assert data["chief_complaint"] == "Headache"
    assert data["symptoms"] == "Throbbing pain"
    assert data["diagnosis"] == "Migraine"
    assert data["treatment_plan"] == "Medication and rest"
    assert data["notes"] == "Review in one week"
    assert data["voice_note_url"] == "https://example.com/voice.mp3"
    assert data["transcribed_text"] == "Patient reports headache"


def test_update_consultation_empty_body(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        diagnosis="Existing",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.patch(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["diagnosis"] == "Existing"


def test_update_consultation_none_fields_are_ignored(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        diagnosis="Existing diagnosis",
        notes="Existing notes",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.patch(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "diagnosis": None,
            "notes": None,
        },
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["diagnosis"] == "Existing diagnosis"
    assert data["notes"] == "Existing notes"


@pytest.mark.parametrize(
    "field",
    [
        "icd10_code",
        "chief_complaint",
        "symptoms",
        "diagnosis",
        "treatment_plan",
        "notes",
        "voice_note_url",
        "transcribed_text",
    ],
)
def test_update_consultation_supports_each_field(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
    field,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    value = (
        "G43.909"
        if field == "icd10_code"
        else "https://example.com/voice.mp3"
        if field == "voice_note_url"
        else f"Updated {field}"
    )

    response = client.patch(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={field: value},
    )

    assert response.status_code == 200
    assert response.get_json()["data"][field] == value


def test_update_consultation_unknown_field(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        notes="Original notes",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.patch(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "unknown_field": "value",
        },
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == consultation.id
    assert body["data"]["notes"] == "Original notes"


def test_update_consultation_icd10_max_length_validation(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.patch(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "icd10_code": "12345678901",
        },
    )

    assert response.status_code == 422


def test_update_consultation_voice_note_url_max_length_validation(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.patch(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "voice_note_url": "x" * 256,
        },
    )

    assert response.status_code == 422


def test_update_consultation_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.patch(
        "/api/consultations/999999",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "diagnosis": "Diagnosis",
        },
    )

    assert response.status_code == 404


# ============================================================================
# COMPLETE CONSULTATION
# ============================================================================


def test_complete_consultation_success(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/complete",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "diagnosis": "Migraine",
            "treatment_plan": "Rest and medication",
            "notes": "Follow-up required",
        },
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["status"] == ConsultationStatus.COMPLETED.value
    assert data["diagnosis"] == "Migraine"
    assert data["treatment_plan"] == "Rest and medication"
    assert data["notes"] == "Follow-up required"
    assert data["ended_at"] is not None


def test_complete_consultation_strips_diagnosis(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/complete",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "diagnosis": "   Migraine   ",
        },
    )

    assert response.status_code == 200
    assert (
        response.get_json()["data"]["diagnosis"]
        == "Migraine"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"diagnosis": ""},
        {"diagnosis": "   "},
    ],
)
def test_complete_consultation_requires_diagnosis(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
    payload,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/complete",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json=payload,
    )

    assert response.status_code == 422


def test_complete_consultation_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/999999/complete",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "diagnosis": "Migraine",
        },
    )

    assert response.status_code == 404


def test_complete_consultation_rejects_completed(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        status=ConsultationStatus.COMPLETED,
        diagnosis="Existing diagnosis",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/complete",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "diagnosis": "New diagnosis",
        },
    )

    assert response.status_code == 409


def test_complete_consultation_rejects_cancelled(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        status=ConsultationStatus.CANCELLED,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/complete",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "diagnosis": "New diagnosis",
        },
    )

    assert response.status_code == 409


# ============================================================================
# CANCEL CONSULTATION
# ============================================================================


def test_cancel_consultation_success(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        notes="Initial notes",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/cancel",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "reason": "Patient unavailable",
        },
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["status"] == ConsultationStatus.CANCELLED.value
    assert data["ended_at"] is not None
    assert "[Cancelled: Patient unavailable]" in data["notes"]
    assert "Initial notes" in data["notes"]


def test_cancel_consultation_without_reason(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/cancel",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={},
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert data["status"] == ConsultationStatus.CANCELLED.value
    assert data["ended_at"] is not None


def test_cancel_consultation_strips_reason(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/cancel",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "reason": "   Patient unavailable   ",
        },
    )

    assert response.status_code == 200

    assert (
        "[Cancelled: Patient unavailable]"
        in response.get_json()["data"]["notes"]
    )


def test_cancel_consultation_blank_reason_does_not_add_note(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        notes="Original notes",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/cancel",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "reason": "   ",
        },
    )

    assert response.status_code == 200
    assert (
        response.get_json()["data"]["notes"]
        == "Original notes"
    )


def test_cancel_consultation_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/999999/cancel",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={},
    )

    assert response.status_code == 404


def test_cancel_consultation_rejects_completed(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        status=ConsultationStatus.COMPLETED,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/cancel",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "reason": "Too late",
        },
    )

    assert response.status_code == 409


def test_cancel_consultation_rejects_already_cancelled(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
        status=ConsultationStatus.CANCELLED,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        f"/api/consultations/{consultation.id}/cancel",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "reason": "Again",
        },
    )

    assert response.status_code == 409


# ============================================================================
# PATIENT CONSULTATIONS
# ============================================================================


def test_get_patient_consultations_success(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    older = make_consultation(
        clinic,
        patient,
        staff,
        started_at=(
            datetime.now(timezone.utc)
            - timedelta(days=2)
        ),
    )

    newer = make_consultation(
        clinic,
        patient,
        staff,
        started_at=(
            datetime.now(timezone.utc)
            - timedelta(days=1)
        ),
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/consultations/patient/{patient.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert len(data) == 2
    assert data[0]["id"] == newer.id
    assert data[1]["id"] == older.id


def test_get_patient_consultations_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/patient/999999",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 404


# ============================================================================
# STAFF CONSULTATIONS
# ============================================================================


def test_get_staff_consultations_success(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/consultations/staff/{staff.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert len(data) == 1
    assert data[0]["id"] == consultation.id


@pytest.mark.parametrize(
    "status",
    list(ConsultationStatus),
)
def test_get_staff_consultations_filters_by_status(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
    status,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    make_consultation(
        clinic,
        patient,
        staff,
        status=status,
    )

    other_status = next(
        item
        for item in ConsultationStatus
        if item != status
    )

    make_consultation(
        clinic,
        patient,
        staff,
        status=other_status,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/consultations/staff/{staff.id}",
        query_string={
            "status": status.value,
        },
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    assert len(data) == 1
    assert data[0]["status"] == status.value


def test_get_staff_consultations_without_status(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    for status in ConsultationStatus:
        make_consultation(
            clinic,
            patient,
            staff,
            status=status,
        )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/consultations/staff/{staff.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200
    assert len(response.get_json()["data"]) == 3


def test_get_staff_consultations_invalid_status(
    client,
    clinic,
    make_staff,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/consultations/staff/{staff.id}",
        query_string={
            "status": "not-a-status",
        },
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "Invalid consultation status" in body["error"]


def test_get_staff_consultations_not_found(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/staff/999999",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 404


# ============================================================================
# CONSULTATION TEMPLATES
# ============================================================================


def test_create_clinic_consultation_template(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.post(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
        json={
            "clinic_id": clinic.id,
            "name": "Cardiology Template",
            "specialty": "Cardiology",
            "structure": {
                "sections": [
                    "history",
                    "examination",
                    "diagnosis",
                    "plan",
                ]
            },
            "is_active": True,
        },
    )

    assert response.status_code == 201

    data = response.get_json()["data"]

    assert data["clinic_id"] == clinic.id
    assert data["name"] == "Cardiology Template"
    assert data["specialty"] == "Cardiology"
    assert data["is_active"] is True
    assert data["structure"]["sections"] == [
        "history",
        "examination",
        "diagnosis",
        "plan",
    ]


def test_create_global_consultation_template(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=Role.ADMIN),
        json={
            "name": "Global Template",
            "structure": {
                "sections": ["diagnosis"],
            },
        },
    )

    assert response.status_code == 201

    data = response.get_json()["data"]

    assert data["clinic_id"] is None
    assert data["name"] == "Global Template"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "Template"},
        {
            "name": "Template",
            "structure": None,
        },
        {
            "name": "Template",
            "structure": [],
        },
        {
            "name": "Template",
            "structure": "invalid",
        },
    ],
)
def test_create_consultation_template_validation(
    client,
    clinic,
    make_user,
    auth_headers_for,
    payload,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=Role.ADMIN),
        json=payload,
    )

    assert response.status_code == 422


def test_create_consultation_template_invalid_clinic(
    client,
    clinic,
    make_user,
    auth_headers_for,
):
    actor = make_user(
        clinic,
        role=Role.ADMIN,
    )

    response = client.post(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=Role.ADMIN),
        json={
            "clinic_id": 999999,
            "name": "Invalid Clinic Template",
            "structure": {
                "sections": ["diagnosis"],
            },
        },
    )

    assert response.status_code == 404


def test_get_active_templates_without_clinic_filter(
    client,
    clinic,
    make_template,
    make_user,
    auth_headers_for,
):
    global_template = make_template(
        name="Global Template",
        clinic=None,
    )

    clinic_template = make_template(
        clinic=clinic,
        name="Clinic Template",
    )

    inactive_template = make_template(
        clinic=clinic,
        name="Inactive Template",
        is_active=False,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    ids = {item["id"] for item in data}

    assert global_template.id in ids
    assert clinic_template.id in ids
    assert inactive_template.id not in ids


def test_get_active_templates_with_clinic_filter(
    client,
    clinic,
    make_clinic,
    make_template,
    make_user,
    auth_headers_for,
):
    other_clinic = make_clinic(
        name="Other Clinic",
    )

    global_template = make_template(
        clinic=None,
        name="Global Template",
    )

    clinic_template = make_template(
        clinic=clinic,
        name="Clinic Template",
    )

    other_template = make_template(
        clinic=other_clinic,
        name="Other Clinic Template",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/templates",
        query_string={
            "clinic_id": clinic.id,
        },
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    ids = {
        item["id"]
        for item in response.get_json()["data"]
    }

    assert global_template.id in ids
    assert clinic_template.id in ids
    assert other_template.id not in ids


def test_get_active_templates_with_valid_clinic_id(
    client,
    clinic,
    make_template,
    make_user,
    auth_headers_for,
):
    template = make_template(
        clinic=clinic,
        name="Clinic Template",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/templates",
        query_string={
            "clinic_id": str(clinic.id),
        },
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    ids = {
        item["id"]
        for item in response.get_json()["data"]
    }

    assert template.id in ids


@pytest.mark.parametrize(
    "clinic_id",
    [
        "abc",
        "1.5",
        "not-an-int",
    ],
)
def test_get_active_templates_rejects_invalid_clinic_id(
    client,
    clinic,
    make_user,
    auth_headers_for,
    clinic_id,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/templates",
        query_string={
            "clinic_id": clinic_id,
        },
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "clinic_id must be an integer"


@pytest.mark.parametrize(
    "clinic_id",
    [
        "0",
        "-1",
    ],
)
def test_get_active_templates_rejects_non_positive_clinic_id(
    client,
    clinic,
    make_user,
    auth_headers_for,
    clinic_id,
):
    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/templates",
        query_string={
            "clinic_id": clinic_id,
        },
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "clinic_id must be greater than 0"


def test_template_response_serializes_nullable_fields(
    client,
    clinic,
    make_template,
    make_user,
    auth_headers_for,
):
    template = make_template(
        clinic=None,
        name="Global Template",
        specialty=None,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    item = next(
        item
        for item in response.get_json()["data"]
        if item["id"] == template.id
    )

    assert item["clinic_id"] is None
    assert item["specialty"] is None
    assert item["name"] == "Global Template"
    assert item["is_active"] is True
    assert item["created_at"] is not None


# ============================================================================
# ROUTE / RESPONSE SERIALIZATION
# ============================================================================


def test_consultation_response_contains_expected_fields(
    client,
    clinic,
    patient,
    make_staff,
    make_consultation,
    make_user,
    auth_headers_for,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
    )

    consultation = make_consultation(
        clinic,
        patient,
        staff,
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        f"/api/consultations/{consultation.id}",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    data = response.get_json()["data"]

    expected_fields = {
        "id",
        "clinic_id",
        "patient_id",
        "staff_id",
        "appointment_id",
        "icd10_code",
        "consultation_type",
        "status",
        "chief_complaint",
        "symptoms",
        "diagnosis",
        "treatment_plan",
        "notes",
        "voice_note_url",
        "transcribed_text",
        "template_id",
        "started_at",
        "ended_at",
        "created_at",
        "updated_at",
    }

    assert expected_fields.issubset(data.keys())


def test_template_response_contains_expected_fields(
    client,
    clinic,
    make_template,
    make_user,
    auth_headers_for,
):
    template = make_template(
        clinic=clinic,
        name="Template",
    )

    actor = make_user(
        clinic,
        role=Role.DOCTOR,
    )

    response = client.get(
        "/api/consultations/templates",
        headers=auth_headers_for(actor, role=Role.DOCTOR),
    )

    assert response.status_code == 200

    item = next(
        item
        for item in response.get_json()["data"]
        if item["id"] == template.id
    )

    expected_fields = {
        "id",
        "clinic_id",
        "name",
        "specialty",
        "structure",
        "is_active",
        "created_at",
    }

    assert expected_fields.issubset(item.keys())