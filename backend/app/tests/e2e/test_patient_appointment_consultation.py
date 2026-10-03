from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.modules.appointment.models.appointment_model import Appointment
from app.modules.consultation.models.consultation_model import Consultation
from app.modules.patient.models.patient_model import Patient


def test_patient_appointment_consultation_e2e(
    client,
    db,
    clinic,
    make_clinic,
    make_user,
    make_staff,
    e2e_login,
):
    receptionist = make_user(
        clinic=clinic,
        role=Role.RECEPTIONIST,
        email="e2e-receptionist@test.com",
    )

    doctor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-doctor@test.com",
        },
    )

    assert receptionist.id > 0
    assert doctor_staff.id > 0

    receptionist_login = e2e_login(
        "e2e-receptionist@test.com",
    )

    assert receptionist_login["user_id"] == receptionist.id
    assert receptionist_login["role"] == Role.RECEPTIONIST.value

    doctor_login = e2e_login(
        "e2e-doctor@test.com",
    )

    assert doctor_login["user_id"] == doctor_staff.user.id
    assert doctor_login["role"] == Role.DOCTOR.value

    patient_response = client.post(
        "/api/v1/patients",
        json={
            "first_name": "E2E",
            "last_name": "Patient",
        },
        headers={
            "Authorization": (
                f"Bearer {receptionist_login['access_token']}"
            ),
        },
    )

    assert patient_response.status_code == 201, (
        patient_response.get_json()
    )

    patient_body = patient_response.get_json()

    assert patient_body["success"] is True
    assert patient_body["data"]["clinic_id"] == clinic.id

    patient_id = patient_body["data"]["id"]

    persisted_patient = db.session.get(
        Patient,
        patient_id,
    )

    assert persisted_patient is not None
    assert persisted_patient.clinic_id == clinic.id
    assert persisted_patient.first_name == "E2E"
    assert persisted_patient.last_name == "Patient"

    scheduled_start = (
        datetime.now(timezone.utc)
        + timedelta(days=1)
    )

    scheduled_end = (
        scheduled_start
        + timedelta(minutes=30)
    )

    appointment_response = client.post(
        "/api/v1/appointments/",
        json={
            "patient_id": patient_id,
            "staff_id": doctor_staff.id,
            "scheduled_start": scheduled_start.isoformat(),
            "scheduled_end": scheduled_end.isoformat(),
            "appointment_type": "in_person",
            "reason": "Phase 8 E2E vertical slice",
        },
        headers={
            "Authorization": (
                f"Bearer {doctor_login['access_token']}"
            ),
        },
    )

    assert appointment_response.status_code == 201, (
        appointment_response.get_json()
    )

    appointment_body = appointment_response.get_json()

    assert appointment_body["success"] is True
    assert appointment_body["data"]["clinic_id"] == clinic.id
    assert appointment_body["data"]["patient_id"] == patient_id
    assert appointment_body["data"]["staff_id"] == doctor_staff.id
    assert appointment_body["data"]["status"] == "scheduled"

    appointment_id = appointment_body["data"]["id"]

    persisted_appointment = db.session.get(
        Appointment,
        appointment_id,
    )

    assert persisted_appointment is not None
    assert persisted_appointment.clinic_id == clinic.id
    assert persisted_appointment.patient_id == patient_id
    assert persisted_appointment.staff_id == doctor_staff.id

    consultation_response = client.post(
        "/api/v1/consultations/",
        json={
            "patient_id": patient_id,
            "staff_id": doctor_staff.id,
            "appointment_id": appointment_id,
            "consultation_type": "general",
            "chief_complaint": "Phase 8 E2E vertical slice",
            "symptoms": "Initial integration workflow",
        },
        headers={
            "Authorization": (
                f"Bearer {doctor_login['access_token']}"
            ),
        },
    )

    assert consultation_response.status_code == 201, (
        consultation_response.get_json()
    )

    consultation_body = consultation_response.get_json()

    assert consultation_body["success"] is True
    assert consultation_body["data"]["clinic_id"] == clinic.id
    assert consultation_body["data"]["patient_id"] == patient_id
    assert consultation_body["data"]["staff_id"] == doctor_staff.id
    assert consultation_body["data"]["appointment_id"] == appointment_id
    assert consultation_body["data"]["status"] == "in_progress"

    consultation_id = consultation_body["data"]["id"]

    persisted_consultation = db.session.get(
        Consultation,
        consultation_id,
    )

    assert persisted_consultation is not None
    assert persisted_consultation.clinic_id == clinic.id
    assert persisted_consultation.patient_id == patient_id
    assert persisted_consultation.staff_id == doctor_staff.id
    assert persisted_consultation.appointment_id == appointment_id

    audit_rows = list(
        db.session.execute(
            db.select(AuditLog)
            .where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_id.in_(
                    [
                        patient_id,
                        appointment_id,
                        consultation_id,
                    ]
                ),
            )
            .order_by(
                AuditLog.id.asc(),
            )
        ).scalars()
    )

    patient_audits = [
        row
        for row in audit_rows
        if row.entity_type == "patient"
        and row.entity_id == patient_id
    ]

    appointment_audits = [
        row
        for row in audit_rows
        if row.entity_type == "Appointment"
        and row.entity_id == appointment_id
    ]

    consultation_audits = [
        row
        for row in audit_rows
        if row.entity_type == "Consultation"
        and row.entity_id == consultation_id
    ]

    assert len(patient_audits) == 1
    assert patient_audits[0].action is AuditAction.CREATE
    assert patient_audits[0].clinic_id == clinic.id
    assert patient_audits[0].user_id == receptionist.id

    assert len(appointment_audits) == 1
    assert appointment_audits[0].action is AuditAction.CREATE
    assert appointment_audits[0].clinic_id == clinic.id
    assert appointment_audits[0].entity_id == appointment_id

    assert len(consultation_audits) == 1
    assert consultation_audits[0].action is AuditAction.CREATE
    assert consultation_audits[0].clinic_id == clinic.id
    assert consultation_audits[0].entity_id == consultation_id

    second_clinic = make_clinic()

    second_doctor = make_staff(
        clinic=second_clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": "e2e-doctor-clinic-2@test.com",
        },
    )

    second_doctor_login = e2e_login(
        "e2e-doctor-clinic-2@test.com",
    )

    assert (
        second_doctor_login["user_id"]
        == second_doctor.user.id
    )
    assert second_doctor_login["role"] == Role.DOCTOR.value

    cross_tenant_appointment_response = client.post(
        "/api/v1/appointments/",
        json={
            "patient_id": patient_id,
            "staff_id": doctor_staff.id,
            "scheduled_start": (
                datetime.now(timezone.utc)
                + timedelta(days=2)
            ).isoformat(),
            "scheduled_end": (
                datetime.now(timezone.utc)
                + timedelta(days=2, minutes=30)
            ).isoformat(),
            "appointment_type": "in_person",
        },
        headers={
            "Authorization": (
                f"Bearer {second_doctor_login['access_token']}"
            ),
        },
    )

    assert cross_tenant_appointment_response.status_code == 404
    assert (
        cross_tenant_appointment_response.get_json()["success"]
        is False
    )

    cross_tenant_consultation_response = client.post(
        "/api/v1/consultations/",
        json={
            "patient_id": patient_id,
            "staff_id": doctor_staff.id,
            "appointment_id": appointment_id,
            "consultation_type": "general",
            "chief_complaint": "Cross-tenant attempt",
            "symptoms": "Should be rejected",
        },
        headers={
            "Authorization": (
                f"Bearer {second_doctor_login['access_token']}"
            ),
        },
    )

    assert cross_tenant_consultation_response.status_code == 409
    assert (
        cross_tenant_consultation_response.get_json()["success"]
        is False
    )

    print("PHASE8_E2E_PATIENT_APPOINTMENT_CONSULTATION=PASS")
