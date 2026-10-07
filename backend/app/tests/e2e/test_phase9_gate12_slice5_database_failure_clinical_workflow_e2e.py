from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from flask import g
from flask_jwt_extended import create_access_token
from sqlalchemy import create_engine, delete, select

import app.core.utils.decorators as auth_decorators
from app import create_app, extensions
from app import models_registry  # noqa: F401
from app.core.audit.models.audit_model import AuditLog
from app.core.enums.appointment_enums import (
    AppointmentStatus,
    AppointmentType,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.consultation_enums import (
    ConsultationStatus,
)
from app.core.enums.patient_enums import BloodType
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.extensions import celery, db, socketio
from app.modules.appointment.models.appointment_model import (
    Appointment,
)
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.consultation.models.consultation_model import (
    Consultation,
)
from app.modules.consultation.routes import consultation_route
from app.modules.patient.models.patient_model import Patient
from app.modules.staff.models.staff_model import Staff
from app.core.auth.user.models.user_model import User
from app.core.idempotency.models.idempotency_model import (
    IdempotencyRecord,
)


DB_CONTAINER = "clinic-gate11-postgres"
DB_READY_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 0.5


def _docker(
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        capture_output=True,
    )


def _assert_disposable_database(
    database_url: str,
) -> None:
    expected_fragment = (
        "127.0.0.1:55433/clinic_gate11"
    )

    if expected_fragment not in database_url:
        raise AssertionError(
            "REFUSING_NON_DISPOSABLE_DATABASE="
            f"{database_url}"
        )

    inspect = _docker(
        "inspect",
        DB_CONTAINER,
        check=False,
    )

    if inspect.returncode != 0:
        raise AssertionError(
            "DISPOSABLE_DB_CONTAINER_MISSING="
            f"{DB_CONTAINER}"
        )


def _container_running() -> bool:
    result = _docker(
        "inspect",
        "-f",
        "{{.State.Running}}",
        DB_CONTAINER,
        check=False,
    )

    return (
        result.returncode == 0
        and result.stdout.strip().lower() == "true"
    )


def _ensure_postgres_running() -> None:
    if _container_running():
        return

    result = _docker(
        "start",
        DB_CONTAINER,
        check=False,
    )

    if result.returncode != 0:
        raise AssertionError(
            "POSTGRES_START_FAILED="
            f"{result.stderr.strip()}"
        )


def _wait_for_postgres() -> None:
    deadline = (
        time.monotonic()
        + DB_READY_TIMEOUT_SECONDS
    )

    last_output = ""

    while time.monotonic() < deadline:
        result = _docker(
            "exec",
            DB_CONTAINER,
            "pg_isready",
            "-U",
            "gate11",
            "-d",
            "clinic_gate11",
            check=False,
        )

        last_output = (
            result.stdout.strip()
            or result.stderr.strip()
        )

        if result.returncode == 0:
            return

        time.sleep(POLL_INTERVAL_SECONDS)

    raise AssertionError(
        "POSTGRES_READY_TIMEOUT="
        f"{last_output}"
    )


def _stop_postgres() -> None:
    result = _docker(
        "stop",
        DB_CONTAINER,
        check=False,
    )

    if result.returncode != 0:
        raise AssertionError(
            "POSTGRES_STOP_FAILED="
            f"{result.stderr.strip()}"
        )


def _dispose_db_engine() -> None:
    db.session.rollback()
    db.session.remove()
    db.engine.dispose()


def _auth_headers(
    app,
    user: User,
) -> dict[str, str]:
    with app.test_request_context():
        token = create_access_token(
            identity=str(user.id),
            additional_claims={
                "role": user.role.value,
                "token_version": user.token_version,
            },
        )

    return {
        "Authorization": f"Bearer {token}",
    }


def _cleanup_clinic(
    clinic_id: int,
) -> None:
    db.session.execute(
        delete(AuditLog).where(
            AuditLog.clinic_id == clinic_id,
        )
    )

    db.session.execute(
        delete(IdempotencyRecord).where(
            IdempotencyRecord.clinic_id == clinic_id,
        )
    )

    db.session.execute(
        delete(Consultation).where(
            Consultation.clinic_id == clinic_id,
        )
    )

    db.session.execute(
        delete(Appointment).where(
            Appointment.clinic_id == clinic_id,
        )
    )

    db.session.execute(
        delete(Patient).where(
            Patient.clinic_id == clinic_id,
        )
    )

    db.session.execute(
        delete(Staff).where(
            Staff.clinic_id == clinic_id,
        )
    )

    db.session.execute(
        delete(User).where(
            User.clinic_id == clinic_id,
        )
    )

    db.session.execute(
        delete(Clinic).where(
            Clinic.id == clinic_id,
        )
    )

    db.session.commit()


def _clinical_state(
    *,
    clinic_id: int,
    patient_id: int,
    appointment_id: int,
) -> dict:
    patient = db.session.get(
        Patient,
        patient_id,
    )

    appointment = db.session.get(
        Appointment,
        appointment_id,
    )

    consultations = list(
        db.session.scalars(
            select(Consultation).where(
                Consultation.clinic_id == clinic_id,
                Consultation.patient_id == patient_id,
                Consultation.appointment_id
                == appointment_id,
            )
        )
    )

    return {
        "patient_exists": patient is not None,
        "appointment_exists": appointment is not None,
        "appointment_status": (
            appointment.status
            if appointment is not None
            else None
        ),
        "consultation_count": len(
            consultations
        ),
        "consultation_statuses": [
            consultation.status
            for consultation in consultations
        ],
    }


def test_gate12_slice5_real_database_failure_recovers_one_clinical_consultation(monkeypatch):
    database_url = os.environ.get(
        "PHASE9_TEST_DATABASE_URL"
    )

    if not database_url:
        pytest.fail(
            "PHASE9_TEST_DATABASE_URL is required"
        )

    _assert_disposable_database(
        database_url
    )
    _ensure_postgres_running()
    _wait_for_postgres()

    os.environ["FLASK_ENV"] = "production"
    os.environ["DATABASE_URL"] = database_url
    os.environ["PGCONNECT_TIMEOUT"] = "3"
    os.environ["REDIS_URL"] = os.environ.get(
        "TEST_REDIS_URL",
        "redis://localhost:56379/15",
    )
    os.environ["CELERY_BROKER_URL"] = os.environ.get(
        "TEST_REDIS_URL",
        "redis://localhost:56379/15",
    )
    os.environ["CELERY_RESULT_BACKEND"] = (
        "cache+memory://"
    )
    os.environ["SECRET_KEY"] = (
        "gate12-slice5-disposable-secret"
    )
    os.environ["JWT_SECRET_KEY"] = (
        "gate12-slice5-disposable-jwt-secret"
    )
    os.environ["CORS_ALLOWED_ORIGINS"] = (
        "http://localhost"
    )
    os.environ["INTEGRATION_ENCRYPTION_KEY"] = (
        Fernet.generate_key().decode()
    )

    original_redis_client = extensions.redis_client
    original_socketio_server = socketio.server
    original_socketio_server_options = dict(
        getattr(socketio, "server_options", {})
    )
    original_celery_config = {
        "broker_url": celery.conf.get("broker_url"),
        "result_backend": celery.conf.get("result_backend"),
        "task_acks_late": celery.conf.get(
            "task_acks_late"
        ),
        "task_reject_on_worker_lost": celery.conf.get(
            "task_reject_on_worker_lost"
        ),
        "worker_prefetch_multiplier": celery.conf.get(
            "worker_prefetch_multiplier"
        ),
        "timezone": celery.conf.get("timezone"),
        "beat_schedule": celery.conf.get(
            "beat_schedule"
        ),
    }

    app = create_app("production")
    clinic_id = None
    seeded = None

    try:
        with app.app_context():
            unique = uuid4().hex

            clinic = Clinic(
                name=(
                    "Gate 12 Slice 5 "
                    f"Database Clinic {unique[:8]}"
                ),
                status=ClinicStatus.ACTIVE,
                ai_credits=5,
            )

            db.session.add(clinic)
            db.session.flush()

            doctor_user = User(
                clinic_id=clinic.id,
                email=(
                    f"gate12-s5-doctor-{unique}"
                    "@example.com"
                ),
                role=Role.DOCTOR,
                is_active=True,
                token_version=0,
            )

            db.session.add(doctor_user)
            db.session.flush()

            doctor_staff = Staff(
                clinic_id=clinic.id,
                user_id=doctor_user.id,
                first_name="Gate12",
                last_name="DatabaseDoctor",
                email=doctor_user.email,
                status=StaffStatus.ACTIVE,
            )

            db.session.add(doctor_staff)
            db.session.flush()

            patient = Patient(
                clinic_id=clinic.id,
                first_name="Gate12",
                last_name="DatabasePatient",
                blood_type=BloodType.UNKNOWN,
                patient_number=(
                    f"G12-S5-{unique[:12]}"
                ),
                is_active=True,
                email=(
                    f"gate12-s5-patient-{unique}"
                    "@example.com"
                ),
            )

            db.session.add(patient)
            db.session.flush()

            scheduled_start = (
                datetime.now(timezone.utc)
                + timedelta(minutes=30)
            )

            appointment = Appointment(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=doctor_staff.id,
                scheduled_start=scheduled_start,
                scheduled_end=(
                    scheduled_start
                    + timedelta(minutes=30)
                ),
                status=AppointmentStatus.SCHEDULED,
                appointment_type=AppointmentType.IN_PERSON,
                reason=(
                    "Gate 12 Slice 5 real "
                    "PostgreSQL clinical failure"
                ),
            )

            db.session.add(appointment)
            db.session.commit()

            clinic_id = clinic.id
            doctor_user_id = doctor_user.id
            doctor_staff_id = doctor_staff.id
            patient_id = patient.id
            appointment_id = appointment.id

            auth_principal = SimpleNamespace(
                id=doctor_user_id,
                clinic_id=clinic_id,
                is_active=True,
                role=Role.DOCTOR,
            )

            seeded = {
                "doctor_user_id": doctor_user_id,
                "doctor_staff_id": doctor_staff_id,
                "patient_id": patient_id,
                "appointment_id": appointment_id,
            }

            doctor_headers = _auth_headers(
                app,
                doctor_user,
            )

            def bypass_auth_context():
                g.current_user_id = doctor_user_id
                g.current_user_role = (
                    Role.DOCTOR.value
                )
                g.current_clinic_id = clinic_id
                g._auth_context_loaded = True

            monkeypatch.setattr(
                auth_decorators,
                "_load_auth_context",
                bypass_auth_context,
            )

            monkeypatch.setattr(
                consultation_route,
                "_get_current_user",
                lambda: auth_principal,
            )

            monkeypatch.setattr(
                consultation_route,
                "_get_authenticated_clinic_id",
                lambda: (clinic_id, None),
            )

            operation_key = (
                f"gate12-s5-consultation-{unique}"
            )

            consultation_payload = {
                "patient_id": patient.id,
                "staff_id": doctor_staff.id,
                "appointment_id": appointment.id,
                "consultation_type": "general",
                "chief_complaint": (
                    "Database outage during "
                    "clinical workflow"
                ),
                "symptoms": (
                    "Clinical workstation lost "
                    "database connectivity"
                ),
            }

            headers = {
                **doctor_headers,
                "Idempotency-Key": operation_key,
            }

            baseline = _clinical_state(
                clinic_id=clinic_id,
                patient_id=patient.id,
                appointment_id=appointment.id,
            )

            assert baseline == {
                "patient_exists": True,
                "appointment_exists": True,
                "appointment_status": (
                    AppointmentStatus.SCHEDULED
                ),
                "consultation_count": 0,
                "consultation_statuses": [],
            }

            client = app.test_client()

            _dispose_db_engine()
            _stop_postgres()

            failed_response = client.post(
                "/api/v1/consultations/",
                json=consultation_payload,
                headers=headers,
            )

            assert failed_response.status_code == 500, (
                failed_response.get_json()
            )

            assert failed_response.get_json() == {
                "success": False,
                "error": "Internal server error",
            }

            _dispose_db_engine()

            _ensure_postgres_running()
            _wait_for_postgres()
            _dispose_db_engine()

            recovered_state = _clinical_state(
                clinic_id=clinic_id,
                patient_id=patient_id,
                appointment_id=appointment_id,
            )

            assert recovered_state == baseline

            retry_response = client.post(
                "/api/v1/consultations/",
                json=consultation_payload,
                headers=headers,
            )

            assert retry_response.status_code == 201, (
                retry_response.get_json()
            )

            retry_body = retry_response.get_json()

            assert retry_body["success"] is True
            assert retry_body["data"]["clinic_id"] == (
                clinic_id
            )
            assert retry_body["data"]["patient_id"] == (
                patient_id
            )
            assert retry_body["data"]["staff_id"] == (
                doctor_staff_id
            )
            assert retry_body["data"]["appointment_id"] == (
                appointment_id
            )
            assert retry_body["data"]["status"] == (
                ConsultationStatus.IN_PROGRESS.value
            )

            consultation_id = retry_body["data"]["id"]

            db.session.expire_all()

            final_consultations = list(
                db.session.scalars(
                    select(Consultation).where(
                        Consultation.clinic_id == clinic_id,
                        Consultation.patient_id
                        == patient_id,
                        Consultation.appointment_id
                        == appointment_id,
                    )
                )
            )

            assert len(final_consultations) == 1
            assert final_consultations[0].id == (
                consultation_id
            )

            final_audits = list(
                db.session.scalars(
                    select(AuditLog).where(
                        AuditLog.clinic_id == clinic_id,
                        AuditLog.entity_type
                        == "Consultation",
                        AuditLog.entity_id
                        == consultation_id,
                        AuditLog.action
                        == AuditAction.CREATE,
                    )
                )
            )

            assert len(final_audits) == 1

            idempotency_records = list(
                db.session.scalars(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.clinic_id
                        == clinic_id,
                        IdempotencyRecord.user_id
                        == doctor_user_id,
                        IdempotencyRecord.operation
                        == "consultation.start",
                        IdempotencyRecord.idempotency_key
                        == operation_key,
                    )
                )
            )

            assert len(idempotency_records) == 1
            assert (
                idempotency_records[0].entity_type
                == "Consultation"
            )
            assert (
                idempotency_records[0].entity_id
                == consultation_id
            )

            final_state = _clinical_state(
                clinic_id=clinic_id,
                patient_id=patient_id,
                appointment_id=appointment_id,
            )

            assert final_state == {
                "patient_exists": True,
                "appointment_exists": True,
                "appointment_status": (
                    AppointmentStatus.SCHEDULED
                ),
                "consultation_count": 1,
                "consultation_statuses": [
                    ConsultationStatus.IN_PROGRESS
                ],
            }

    finally:
        try:
            with app.app_context():
                _ensure_postgres_running()
                _wait_for_postgres()
                _dispose_db_engine()

                if clinic_id is not None:
                    _cleanup_clinic(
                        clinic_id
                    )
        except Exception as cleanup_error:
            pytest.fail(
                "GATE12_S5_CLEANUP_FAILED="
                f"{cleanup_error!r}"
            )
        finally:
            extensions.redis_client = (
                original_redis_client
            )
            socketio.server = (
                original_socketio_server
            )
            socketio.server_options = (
                original_socketio_server_options
            )
            celery.conf.update(
                original_celery_config
            )