from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.modules.consultation.models.consultation_model import Consultation


def test_gate3_consultation_idempotency_same_key_same_payload(
    client,
    db,
    clinic,
    make_patient,
    make_staff,
    make_appointment,
    e2e_login,
):
    patient = make_patient(
        clinic,
        first_name="Gate3",
        last_name="Patient",
    )

    doctor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "gate3-idempotency-doctor@test.com",
        },
    )

    appointment = make_appointment(
        clinic,
        patient,
        doctor_staff,
        scheduled_start=(
            datetime.now(timezone.utc)
            + timedelta(days=1)
        ),
        scheduled_end=(
            datetime.now(timezone.utc)
            + timedelta(days=1, minutes=30)
        ),
    )

    login = e2e_login(
        "gate3-idempotency-doctor@test.com",
    )

    headers = {
        "Authorization": (
            f"Bearer {login['access_token']}"
        ),
        "Idempotency-Key": "gate3-consultation-001",
    }

    payload = {
        "patient_id": patient.id,
        "staff_id": doctor_staff.id,
        "appointment_id": appointment.id,
        "consultation_type": "general",
        "chief_complaint": "Gate 3 idempotency",
        "symptoms": "Same request",
    }

    first_response = client.post(
        "/api/v1/consultations/",
        json=payload,
        headers=headers,
    )

    assert first_response.status_code == 201, (
        first_response.get_json()
    )

    second_response = client.post(
        "/api/v1/consultations/",
        json=payload,
        headers=headers,
    )

    assert second_response.status_code == 201, (
        second_response.get_json()
    )

    first_body = first_response.get_json()
    second_body = second_response.get_json()

    first_id = first_body["data"]["id"]
    second_id = second_body["data"]["id"]

    assert first_id == second_id

    consultations = list(
        db.session.execute(
            db.select(Consultation)
            .where(
                Consultation.clinic_id == clinic.id,
                Consultation.patient_id == patient.id,
                Consultation.staff_id == doctor_staff.id,
            )
        ).scalars()
    )

    assert len(consultations) == 1

    audits = list(
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type == "Consultation",
                AuditLog.entity_id == first_id,
                AuditLog.action == AuditAction.CREATE,
            )
        ).scalars()
    )

    assert len(audits) == 1


def test_gate3_consultation_idempotency_same_key_different_payload(
    client,
    db,
    clinic,
    make_patient,
    make_staff,
    make_appointment,
    e2e_login,
):
    patient = make_patient(
        clinic,
        first_name="Gate3",
        last_name="Conflict",
    )

    doctor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "gate3-idempotency-conflict@test.com",
        },
    )

    appointment = make_appointment(
        clinic,
        patient,
        doctor_staff,
        scheduled_start=(
            datetime.now(timezone.utc)
            + timedelta(days=1)
        ),
        scheduled_end=(
            datetime.now(timezone.utc)
            + timedelta(days=1, minutes=30)
        ),
    )

    login = e2e_login(
        "gate3-idempotency-conflict@test.com",
    )

    headers = {
        "Authorization": (
            f"Bearer {login['access_token']}"
        ),
        "Idempotency-Key": "gate3-consultation-002",
    }

    first_payload = {
        "patient_id": patient.id,
        "staff_id": doctor_staff.id,
        "appointment_id": appointment.id,
        "consultation_type": "general",
        "chief_complaint": "Original request",
        "symptoms": "Original symptoms",
    }

    conflicting_payload = {
        **first_payload,
        "chief_complaint": "Different request",
    }

    first_response = client.post(
        "/api/v1/consultations/",
        json=first_payload,
        headers=headers,
    )

    assert first_response.status_code == 201, (
        first_response.get_json()
    )

    second_response = client.post(
        "/api/v1/consultations/",
        json=conflicting_payload,
        headers=headers,
    )

    assert second_response.status_code == 409, (
        second_response.get_json()
    )

    body = second_response.get_json()

    assert body["success"] is False

    consultations = list(
        db.session.execute(
            db.select(Consultation)
            .where(
                Consultation.clinic_id == clinic.id,
                Consultation.patient_id == patient.id,
                Consultation.staff_id == doctor_staff.id,
            )
        ).scalars()
    )

    assert len(consultations) == 1

    first_id = first_response.get_json()["data"]["id"]

    audits = list(
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type == "Consultation",
                AuditLog.entity_id == first_id,
                AuditLog.action == AuditAction.CREATE,
            )
        ).scalars()
    )

    assert len(audits) == 1
