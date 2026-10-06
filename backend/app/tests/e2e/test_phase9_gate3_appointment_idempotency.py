from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.modules.appointment.models.appointment_model import Appointment


def test_gate3_appointment_idempotency_same_key_same_payload(
    client,
    db,
    clinic,
    make_patient,
    make_staff,
    e2e_login,
):
    patient = make_patient(
        clinic,
        first_name="Gate3",
        last_name="Appointment",
    )

    doctor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "gate3-appointment@test.com",
        },
    )

    login = e2e_login(
        "gate3-appointment@test.com",
    )

    start = (
        datetime.now(timezone.utc)
        + timedelta(days=2)
    )
    end = start + timedelta(minutes=30)

    headers = {
        "Authorization": (
            f"Bearer {login['access_token']}"
        ),
        "Idempotency-Key": "gate3-appointment-001",
    }

    payload = {
        "patient_id": patient.id,
        "staff_id": doctor_staff.id,
        "scheduled_start": start.isoformat(),
        "scheduled_end": end.isoformat(),
        "appointment_type": "emergency",
        "reason": "Priority appointment",
        "notes": "Gate 3 replay",
    }

    first = client.post(
        "/api/v1/appointments/",
        json=payload,
        headers=headers,
    )

    assert first.status_code == 201, first.get_json()

    second = client.post(
        "/api/v1/appointments/",
        json=payload,
        headers=headers,
    )

    assert second.status_code == 201, second.get_json()

    first_id = first.get_json()["data"]["id"]
    second_id = second.get_json()["data"]["id"]

    assert first_id == second_id

    appointments = list(
        db.session.execute(
            db.select(Appointment).where(
                Appointment.clinic_id == clinic.id,
                Appointment.patient_id == patient.id,
                Appointment.staff_id == doctor_staff.id,
            )
        ).scalars()
    )

    assert len(appointments) == 1

    audits = list(
        db.session.execute(
            db.select(AuditLog).where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type == "Appointment",
                AuditLog.entity_id == first_id,
                AuditLog.action == AuditAction.CREATE,
            )
        ).scalars()
    )

    assert len(audits) == 1


def test_gate3_appointment_idempotency_same_key_different_payload(
    client,
    db,
    clinic,
    make_patient,
    make_staff,
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
            "email": "gate3-appointment-conflict@test.com",
        },
    )

    login = e2e_login(
        "gate3-appointment-conflict@test.com",
    )

    start = (
        datetime.now(timezone.utc)
        + timedelta(days=3)
    )
    end = start + timedelta(minutes=30)

    headers = {
        "Authorization": (
            f"Bearer {login['access_token']}"
        ),
        "Idempotency-Key": "gate3-appointment-002",
    }

    first_payload = {
        "patient_id": patient.id,
        "staff_id": doctor_staff.id,
        "scheduled_start": start.isoformat(),
        "scheduled_end": end.isoformat(),
        "appointment_type": "emergency",
        "reason": "Priority appointment",
    }

    conflicting_payload = {
        **first_payload,
        "reason": "Different priority appointment",
    }

    first = client.post(
        "/api/v1/appointments/",
        json=first_payload,
        headers=headers,
    )

    assert first.status_code == 201, first.get_json()

    second = client.post(
        "/api/v1/appointments/",
        json=conflicting_payload,
        headers=headers,
    )

    assert second.status_code == 409, second.get_json()

    body = second.get_json()

    assert body["success"] is False
    assert body["error"] == (
        "Idempotency-Key was already used "
        "with a different request payload"
    )

    first_id = first.get_json()["data"]["id"]

    appointments = list(
        db.session.execute(
            db.select(Appointment).where(
                Appointment.clinic_id == clinic.id,
                Appointment.patient_id == patient.id,
                Appointment.staff_id == doctor_staff.id,
            )
        ).scalars()
    )

    assert len(appointments) == 1

    audits = list(
        db.session.execute(
            db.select(AuditLog).where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type == "Appointment",
                AuditLog.entity_id == first_id,
                AuditLog.action == AuditAction.CREATE,
            )
        ).scalars()
    )

    assert len(audits) == 1
