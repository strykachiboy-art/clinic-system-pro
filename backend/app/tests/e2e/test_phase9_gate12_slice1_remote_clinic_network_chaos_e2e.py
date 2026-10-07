from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.appointment_enums import AppointmentStatus
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.idempotency.models.idempotency_model import (
    IdempotencyRecord,
)
from app.modules.appointment.models.appointment_model import (
    Appointment,
)
from app.modules.consultation.models.consultation_model import (
    Consultation,
)
from app.modules.consultation.routes import consultation_route
from app.modules.patient.models.patient_model import Patient


def _auth(login: dict) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {login['access_token']}"
        )
    }


def test_gate12_slice1_remote_clinic_unknown_outcome_reconciles_one_consultation(
    client,
    db,
    clinic,
    make_user,
    make_patient,
    make_staff,
    auth_headers_for,
    monkeypatch,
):
    admin = make_user(
        clinic=clinic,
        role=Role.ADMIN,
        email=(
            f"gate12-s1-admin-{uuid4().hex}"
            "@example.com"
        ),
    )

    doctor_staff = make_staff(
        clinic=clinic,
        role=Role.DOCTOR,
        user_overrides={
            "email": (
                f"gate12-s1-doctor-{uuid4().hex}"
                "@example.com"
            ),
        },
    )

    admin_headers = auth_headers_for(
        admin,
        role=Role.ADMIN,
    )

    doctor_headers = auth_headers_for(
        doctor_staff.user,
        role=Role.DOCTOR,
    )

    patient = make_patient(
        clinic,
        first_name="Gate12",
        last_name="RemoteClinic",
    )

    scheduled_start = (
        datetime.now(timezone.utc)
        + timedelta(days=1)
    )

    appointment_response = client.post(
        "/api/v1/appointments/",
        json={
            "patient_id": patient.id,
            "staff_id": doctor_staff.id,
            "scheduled_start": (
                scheduled_start.isoformat()
            ),
            "scheduled_end": (
                scheduled_start
                + timedelta(minutes=30)
            ).isoformat(),
            "appointment_type": "in_person",
            "reason": (
                "Gate 12 Slice 1 remote clinic "
                "network chaos"
            ),
        },
        headers=doctor_headers,
    )

    assert appointment_response.status_code == 201, (
        appointment_response.get_json()
    )

    appointment_id = (
        appointment_response.get_json()["data"]["id"]
    )

    operation_key = (
        f"gate12-s1-consultation-{uuid4().hex}"
    )

    payload = {
        "patient_id": patient.id,
        "staff_id": doctor_staff.id,
        "appointment_id": appointment_id,
        "consultation_type": "general",
        "chief_complaint": (
            "Remote clinic connection loss"
        ),
        "symptoms": (
            "Client cannot determine whether "
            "the consultation was committed"
        ),
    }

    headers = {
        **doctor_headers,
        "Idempotency-Key": operation_key,
    }

    original_jsonify = consultation_route.jsonify
    response_loss = {
        "injected": False,
    }

    def lose_client_response(
        *args,
        **kwargs,
    ):
        if not response_loss["injected"]:
            response_loss["injected"] = True
            raise ConnectionError(
                "Gate 12 Slice 1 simulated "
                "remote-clinic response loss"
            )

        return original_jsonify(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        consultation_route,
        "jsonify",
        lose_client_response,
    )

    first_response = client.post(
        "/api/v1/consultations/",
        json=payload,
        headers=headers,
    )

    assert response_loss["injected"] is True
    assert first_response.status_code == 500
    assert first_response.get_json() == {
        "success": False,
        "error": "Internal server error",
    }

    monkeypatch.setattr(
        consultation_route,
        "jsonify",
        original_jsonify,
    )

    db.session.expire_all()

    committed_consultations = list(
        db.session.scalars(
            db.select(Consultation).where(
                Consultation.clinic_id == clinic.id,
                Consultation.patient_id == patient.id,
                Consultation.appointment_id
                == appointment_id,
            )
        )
    )

    assert len(committed_consultations) == 1

    committed = committed_consultations[0]

    assert committed.clinic_id == clinic.id
    assert committed.patient_id == patient.id
    assert committed.staff_id == doctor_staff.id
    assert committed.appointment_id == appointment_id
    assert committed.status.value == "in_progress"

    idempotency_records = list(
        db.session.scalars(
            db.select(IdempotencyRecord).where(
                IdempotencyRecord.clinic_id == clinic.id,
                IdempotencyRecord.user_id
                == doctor_staff.user_id,
                IdempotencyRecord.operation
                == "consultation.start",
                IdempotencyRecord.idempotency_key
                == operation_key,
            )
        )
    )

    assert len(idempotency_records) == 1

    idempotency_record = idempotency_records[0]

    assert (
        idempotency_record.entity_type
        == "Consultation"
    )
    assert (
        idempotency_record.entity_id
        == committed.id
    )

    audits = list(
        db.session.scalars(
            db.select(AuditLog).where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type
                == "Consultation",
                AuditLog.entity_id == committed.id,
                AuditLog.action
                == AuditAction.CREATE,
            )
        )
    )

    assert len(audits) == 1

    persisted_appointment = db.session.get(
        Appointment,
        appointment_id,
    )

    persisted_patient = db.session.get(
        Patient,
        patient.id,
    )

    assert persisted_patient is not None
    assert persisted_appointment is not None
    assert (
        persisted_appointment.clinic_id
        == clinic.id
    )
    assert (
        persisted_appointment.patient_id
        == patient.id
    )
    assert persisted_appointment.status in (
        AppointmentStatus.SCHEDULED,
        AppointmentStatus.CONFIRMED,
    )

    baseline = {
        "patient_id": persisted_patient.id,
        "appointment_id": persisted_appointment.id,
        "appointment_status": (
            persisted_appointment.status
        ),
        "consultation_id": committed.id,
        "consultation_status": (
            committed.status
        ),
    }

    retry_response = client.post(
        "/api/v1/consultations/",
        json=payload,
        headers=headers,
    )

    assert retry_response.status_code == 201, (
        retry_response.get_json()
    )

    retry_body = retry_response.get_json()

    assert retry_body["success"] is True
    assert retry_body["data"]["id"] == committed.id
    assert (
        retry_body["data"]["clinic_id"]
        == clinic.id
    )
    assert (
        retry_body["data"]["patient_id"]
        == patient.id
    )
    assert (
        retry_body["data"]["appointment_id"]
        == appointment_id
    )
    assert (
        retry_body["data"]["status"]
        == "in_progress"
    )

    db.session.expire_all()

    final_consultations = list(
        db.session.scalars(
            db.select(Consultation).where(
                Consultation.clinic_id == clinic.id,
                Consultation.patient_id == patient.id,
                Consultation.appointment_id
                == appointment_id,
            )
        )
    )

    final_idempotency_records = list(
        db.session.scalars(
            db.select(IdempotencyRecord).where(
                IdempotencyRecord.clinic_id == clinic.id,
                IdempotencyRecord.user_id
                == doctor_staff.user_id,
                IdempotencyRecord.operation
                == "consultation.start",
                IdempotencyRecord.idempotency_key
                == operation_key,
            )
        )
    )

    final_audits = list(
        db.session.scalars(
            db.select(AuditLog).where(
                AuditLog.clinic_id == clinic.id,
                AuditLog.entity_type
                == "Consultation",
                AuditLog.entity_id == committed.id,
                AuditLog.action
                == AuditAction.CREATE,
            )
        )
    )

    final_appointment = db.session.get(
        Appointment,
        appointment_id,
    )

    assert len(final_consultations) == 1
    assert len(final_idempotency_records) == 1
    assert len(final_audits) == 1
    assert final_appointment is not None

    assert {
        "patient_id": patient.id,
        "appointment_id": final_appointment.id,
        "appointment_status": (
            final_appointment.status
        ),
        "consultation_id": final_consultations[0].id,
        "consultation_status": (
            final_consultations[0].status
        ),
    } == baseline
