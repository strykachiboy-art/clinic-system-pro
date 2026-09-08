from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.enums.consultation_enums import (
    ConsultationStatus,
    ConsultationType,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import ValidationError
from app.modules.consultation.routes import consultation_route


# ============================================================================
# Helpers
# ============================================================================


def make_consultation(
    *,
    clinic_id=1,
    patient_id=1,
    staff_id=1,
    appointment_id=None,
    consultation_id=1,
    consultation_type=ConsultationType.GENERAL,
    status=ConsultationStatus.IN_PROGRESS,
    template_id=None,
    chief_complaint="Fever",
    symptoms="Fever and fatigue",
    diagnosis=None,
    treatment_plan=None,
    notes=None,
    voice_note_url=None,
    transcribed_text=None,
):
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=consultation_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        staff_id=staff_id,
        appointment_id=appointment_id,
        icd10_code=None,
        consultation_type=consultation_type,
        status=status,
        chief_complaint=chief_complaint,
        symptoms=symptoms,
        diagnosis=diagnosis,
        treatment_plan=treatment_plan,
        notes=notes,
        voice_note_url=voice_note_url,
        transcribed_text=transcribed_text,
        template_id=template_id,
        started_at=now,
        ended_at=None,
        created_at=now,
        updated_at=now,
    )


def make_template(
    *,
    template_id=1,
    clinic_id=1,
    name="General Consultation",
    specialty="General Medicine",
    structure=None,
    is_active=True,
):
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=template_id,
        clinic_id=clinic_id,
        name=name,
        specialty=specialty,
        structure=structure
        or {
            "sections": [
                "history",
                "examination",
                "assessment",
                "plan",
            ]
        },
        is_active=is_active,
        created_at=now,
    )


# ============================================================================
# START CONSULTATION
# ============================================================================


def test_start_consultation_success(
    app,
    clinic,
    patient,
    staff,
    auth_headers_for,
    monkeypatch,
):
    headers = auth_headers_for(staff.user, role=Role.ADMIN)

    consultation = make_consultation(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
    )

    called = {}

    def fake_start_consultation(**kwargs):
        called.update(kwargs)
        return consultation

    monkeypatch.setattr(
        consultation_route,
        "start_consultation",
        fake_start_consultation,
    )

    response = app.test_client().post(
        "/api/consultations/",
        json={
            "patient_id": patient.id,
            "staff_id": staff.id,
            "consultation_type": ConsultationType.GENERAL.value,
            "chief_complaint": "Fever",
            "symptoms": "Fever and fatigue",
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == consultation.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["patient_id"] == patient.id
    assert body["data"]["staff_id"] == staff.id
    assert body["data"]["status"] == ConsultationStatus.IN_PROGRESS.value

    assert called["clinic_id"] == clinic.id
    assert called["patient_id"] == patient.id
    assert called["staff_id"] == staff.id


def test_start_consultation_ignores_client_clinic_id(
    app,
    clinic,
    patient,
    staff,
    auth_headers_for,
    monkeypatch,
):
    headers = auth_headers_for(staff.user, role=Role.ADMIN)

    consultation = make_consultation(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
    )

    called = {}

    def fake_start_consultation(**kwargs):
        called.update(kwargs)
        return consultation

    monkeypatch.setattr(
        consultation_route,
        "start_consultation",
        fake_start_consultation,
    )

    response = app.test_client().post(
        "/api/consultations/",
        json={
            "clinic_id": 999999,
            "patient_id": patient.id,
            "staff_id": staff.id,
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert called["clinic_id"] == clinic.id
    assert called["clinic_id"] != 999999


def test_start_consultation_invalid_payload_returns_422(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    response = app.test_client().post(
        "/api/consultations/",
        json={
            "patient_id": 0,
            "staff_id": 0,
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_start_consultation_rejects_blank_chief_complaint(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    response = app.test_client().post(
        "/api/consultations/",
        json={
            "patient_id": 1,
            "staff_id": 1,
            "chief_complaint": "   ",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_start_consultation_rejects_unknown_field(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    response = app.test_client().post(
        "/api/consultations/",
        json={
            "patient_id": 1,
            "staff_id": 1,
            "unknown_field": "bad",
        },
        headers=headers,
    )

    assert response.status_code == 422


# ============================================================================
# GET CONSULTATION
# ============================================================================


def test_get_consultation_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    consultation = make_consultation(
        clinic_id=clinic.id,
    )

    called = {}

    def fake_get_consultation(**kwargs):
        called.update(kwargs)
        return consultation

    monkeypatch.setattr(
        consultation_route,
        "get_consultation",
        fake_get_consultation,
    )

    response = app.test_client().get(
        f"/api/consultations/{consultation.id}",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == consultation.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["consultation_type"] == (
        ConsultationType.GENERAL.value
    )

    assert called["consultation_id"] == consultation.id
    assert called["clinic_id"] == clinic.id


def test_get_consultation_uses_authenticated_clinic(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    consultation = make_consultation(
        clinic_id=clinic.id,
        consultation_id=44,
    )

    called = {}

    def fake_get_consultation(**kwargs):
        called.update(kwargs)
        return consultation

    monkeypatch.setattr(
        consultation_route,
        "get_consultation",
        fake_get_consultation,
    )

    response = app.test_client().get(
        "/api/consultations/44",
        headers=headers,
    )

    assert response.status_code == 200
    assert called["consultation_id"] == 44
    assert called["clinic_id"] == clinic.id


# ============================================================================
# UPDATE CONSULTATION
# ============================================================================


def test_update_consultation_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    consultation = make_consultation(
        clinic_id=clinic.id,
        consultation_id=10,
        notes="Updated notes",
        diagnosis="Viral infection",
    )

    called = {}

    def fake_update_consultation_note(**kwargs):
        called.update(kwargs)
        return consultation

    monkeypatch.setattr(
        consultation_route,
        "update_consultation_note",
        fake_update_consultation_note,
    )

    response = app.test_client().patch(
        "/api/consultations/10",
        json={
            "diagnosis": "Viral infection",
            "notes": "Updated notes",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["diagnosis"] == "Viral infection"
    assert body["data"]["notes"] == "Updated notes"

    assert called["consultation_id"] == 10
    assert called["clinic_id"] == clinic.id
    assert called["diagnosis"] == "Viral infection"
    assert called["notes"] == "Updated notes"


def test_update_consultation_rejects_blank_notes(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    response = app.test_client().patch(
        "/api/consultations/1",
        json={
            "notes": "   ",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_update_consultation_rejects_unknown_field(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    response = app.test_client().patch(
        "/api/consultations/1",
        json={
            "clinic_id": 999,
        },
        headers=headers,
    )

    assert response.status_code == 422


# ============================================================================
# COMPLETE CONSULTATION
# ============================================================================


def test_complete_consultation_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    consultation = make_consultation(
        clinic_id=clinic.id,
        consultation_id=20,
        status=ConsultationStatus.COMPLETED,
        diagnosis="Malaria",
        treatment_plan="Oral treatment",
        notes="Follow up in 3 days",
    )

    called = {}

    def fake_complete_consultation(**kwargs):
        called.update(kwargs)
        return consultation

    monkeypatch.setattr(
        consultation_route,
        "complete_consultation",
        fake_complete_consultation,
    )

    response = app.test_client().post(
        "/api/consultations/20/complete",
        json={
            "diagnosis": "Malaria",
            "treatment_plan": "Oral treatment",
            "notes": "Follow up in 3 days",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == ConsultationStatus.COMPLETED.value
    assert body["data"]["diagnosis"] == "Malaria"

    assert called["consultation_id"] == 20
    assert called["clinic_id"] == clinic.id
    assert called["diagnosis"] == "Malaria"


def test_complete_consultation_requires_diagnosis(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    response = app.test_client().post(
        "/api/consultations/20/complete",
        json={},
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_complete_consultation_rejects_blank_diagnosis(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    response = app.test_client().post(
        "/api/consultations/20/complete",
        json={
            "diagnosis": "   ",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


# ============================================================================
# CANCEL CONSULTATION
# ============================================================================


def test_cancel_consultation_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.NURSE)

    consultation = make_consultation(
        clinic_id=clinic.id,
        consultation_id=30,
        status=ConsultationStatus.CANCELLED,
    )

    called = {}

    def fake_cancel_consultation(**kwargs):
        called.update(kwargs)
        return consultation

    monkeypatch.setattr(
        consultation_route,
        "cancel_consultation",
        fake_cancel_consultation,
    )

    response = app.test_client().post(
        "/api/consultations/30/cancel",
        json={
            "reason": "Patient unavailable",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["status"] == ConsultationStatus.CANCELLED.value

    assert called["consultation_id"] == 30
    assert called["clinic_id"] == clinic.id
    assert called["reason"] == "Patient unavailable"


def test_cancel_consultation_allows_missing_reason(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    consultation = make_consultation(
        clinic_id=clinic.id,
        consultation_id=31,
        status=ConsultationStatus.CANCELLED,
    )

    monkeypatch.setattr(
        consultation_route,
        "cancel_consultation",
        lambda **kwargs: consultation,
    )

    response = app.test_client().post(
        "/api/consultations/31/cancel",
        json={},
        headers=headers,
    )

    assert response.status_code == 200


def test_cancel_consultation_rejects_blank_reason(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    response = app.test_client().post(
        "/api/consultations/31/cancel",
        json={
            "reason": "   ",
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


# ============================================================================
# PATIENT CONSULTATION HISTORY
# ============================================================================


def test_patient_consultations_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    consultations = [
        make_consultation(
            clinic_id=clinic.id,
            patient_id=55,
            consultation_id=1,
        ),
        make_consultation(
            clinic_id=clinic.id,
            patient_id=55,
            consultation_id=2,
        ),
    ]

    called = {}

    def fake_get_consultations_for_patient(**kwargs):
        called.update(kwargs)
        return consultations

    monkeypatch.setattr(
        consultation_route,
        "get_consultations_for_patient",
        fake_get_consultations_for_patient,
    )

    response = app.test_client().get(
        "/api/consultations/patient/55",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 2
    assert body["data"][0]["id"] == 1
    assert body["data"][1]["id"] == 2

    assert called["patient_id"] == 55
    assert called["clinic_id"] == clinic.id


# ============================================================================
# STAFF CONSULTATION HISTORY
# ============================================================================


def test_staff_consultations_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    consultations = [
        make_consultation(
            clinic_id=clinic.id,
            staff_id=77,
            consultation_id=1,
        )
    ]

    called = {}

    def fake_get_consultations_for_staff(**kwargs):
        called.update(kwargs)
        return consultations

    monkeypatch.setattr(
        consultation_route,
        "get_consultations_for_staff",
        fake_get_consultations_for_staff,
    )

    response = app.test_client().get(
        "/api/consultations/staff/77?status=in_progress",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 1

    assert called["staff_id"] == 77
    assert called["clinic_id"] == clinic.id
    assert called["status"] == ConsultationStatus.IN_PROGRESS


def test_staff_consultations_without_status(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    called = {}

    def fake_get_consultations_for_staff(**kwargs):
        called.update(kwargs)
        return []

    monkeypatch.setattr(
        consultation_route,
        "get_consultations_for_staff",
        fake_get_consultations_for_staff,
    )

    response = app.test_client().get(
        "/api/consultations/staff/77",
        headers=headers,
    )

    assert response.status_code == 200
    assert called["status"] is None


def test_staff_consultations_rejects_invalid_status(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    response = app.test_client().get(
        "/api/consultations/staff/77?status=invalid",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "Invalid consultation status" in body["error"]


# ============================================================================
# TEMPLATES
# ============================================================================


def test_create_template_success(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    template = make_template(
        clinic_id=clinic.id,
    )

    called = {}

    def fake_create_consultation_template(**kwargs):
        called.update(kwargs)
        return template

    monkeypatch.setattr(
        consultation_route,
        "create_consultation_template",
        fake_create_consultation_template,
    )

    response = app.test_client().post(
        "/api/consultations/templates",
        json={
            "name": "General Consultation",
            "specialty": "General Medicine",
            "structure": {
                "sections": [
                    "history",
                    "examination",
                    "assessment",
                    "plan",
                ]
            },
        },
        headers=headers,
    )

    assert response.status_code == 201

    body = response.get_json()

    assert body["success"] is True
    assert body["data"]["id"] == template.id
    assert body["data"]["clinic_id"] == clinic.id
    assert body["data"]["name"] == "General Consultation"

    assert called["clinic_id"] == clinic.id
    assert called["name"] == "General Consultation"


def test_create_template_forbidden_for_nurse(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.NURSE)

    response = app.test_client().post(
        "/api/consultations/templates",
        json={
            "name": "Nursing Template",
            "structure": {
                "sections": ["notes"]
            },
        },
        headers=headers,
    )

    assert response.status_code == 403


def test_create_template_rejects_blank_name(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    response = app.test_client().post(
        "/api/consultations/templates",
        json={
            "name": "   ",
            "structure": {
                "sections": ["history"]
            },
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_create_template_rejects_empty_structure(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    response = app.test_client().post(
        "/api/consultations/templates",
        json={
            "name": "Empty Template",
            "structure": {},
        },
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert "error" in body


def test_active_templates_admin_without_clinic_filter(
    app,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    templates = [
        make_template(
            template_id=1,
            clinic_id=None,
            name="Global Template",
        ),
        make_template(
            template_id=2,
            clinic_id=1,
            name="Clinic Template",
        ),
    ]

    called = {}

    def fake_get_active_templates(**kwargs):
        called.update(kwargs)
        return templates

    monkeypatch.setattr(
        consultation_route,
        "get_active_templates",
        fake_get_active_templates,
    )

    response = app.test_client().get(
        "/api/consultations/templates",
        headers=headers,
    )

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert len(body["data"]) == 2
    assert called["clinic_id"] is None


def test_active_templates_non_admin_uses_authenticated_clinic(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    called = {}

    def fake_get_active_templates(**kwargs):
        called.update(kwargs)
        return []

    monkeypatch.setattr(
        consultation_route,
        "get_active_templates",
        fake_get_active_templates,
    )

    response = app.test_client().get(
        "/api/consultations/templates",
        headers=headers,
    )

    assert response.status_code == 200
    assert called["clinic_id"] == clinic.id


def test_active_templates_non_admin_rejects_other_clinic(
    app,
    clinic,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.DOCTOR)

    response = app.test_client().get(
        "/api/consultations/templates?clinic_id=999",
        headers=headers,
    )

    assert response.status_code == 403

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Access denied"


def test_active_templates_rejects_non_integer_clinic_id(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    response = app.test_client().get(
        "/api/consultations/templates?clinic_id=abc",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "clinic_id must be an integer"


def test_active_templates_rejects_non_positive_clinic_id(
    app,
    auth_headers_for,
    user,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    response = app.test_client().get(
        "/api/consultations/templates?clinic_id=0",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "clinic_id must be greater than 0"


# ============================================================================
# AUTHENTICATION / AUTHORIZATION
# ============================================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/consultations/1"),
        ("patch", "/api/consultations/1"),
        ("post", "/api/consultations/1/complete"),
        ("post", "/api/consultations/1/cancel"),
        ("get", "/api/consultations/patient/1"),
        ("get", "/api/consultations/staff/1"),
        ("get", "/api/consultations/templates"),
    ],
)
def test_consultation_routes_require_authentication(
    app,
    method,
    path,
):
    client = app.test_client()

    response = getattr(client, method)(path)

    assert response.status_code in (401, 422)


@pytest.mark.parametrize(
    "role",
    [
        Role.PATIENT,
        Role.PHARMACIST,
        Role.LAB_TECHNICIAN,
    ],
)
def test_read_routes_forbidden_for_unauthorized_roles(
    app,
    auth_headers_for,
    make_user,
    clinic,
    role,
):
    unauthorized_user = make_user(
        clinic,
        role=role,
    )

    headers = auth_headers_for(
        unauthorized_user,
        role=role,
    )

    response = app.test_client().get(
        "/api/consultations/1",
        headers=headers,
    )

    assert response.status_code == 403


def test_template_create_allowed_for_admin(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    template = make_template(
        clinic_id=clinic.id,
    )

    monkeypatch.setattr(
        consultation_route,
        "create_consultation_template",
        lambda **kwargs: template,
    )

    response = app.test_client().post(
        "/api/consultations/templates",
        json={
            "name": "Admin Template",
            "structure": {
                "sections": ["history"]
            },
        },
        headers=headers,
    )

    assert response.status_code == 201


# ============================================================================
# DOMAIN ERROR HANDLING
# ============================================================================


def test_route_returns_domain_error_status(
    app,
    clinic,
    auth_headers_for,
    user,
    monkeypatch,
):
    headers = auth_headers_for(user, role=Role.ADMIN)

    def fake_get_consultation(**kwargs):
        raise ValidationError("Consultation not found")

    monkeypatch.setattr(
        consultation_route,
        "get_consultation",
        fake_get_consultation,
    )

    response = app.test_client().get(
        "/api/consultations/999",
        headers=headers,
    )

    assert response.status_code == 422

    body = response.get_json()

    assert body["success"] is False
    assert body["error"] == "Consultation not found"