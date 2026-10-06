from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import select

from app import create_app
from app.config import config_by_name
from app.core.enums.appointment_enums import (
    AppointmentStatus,
    AppointmentType,
)
from app.core.exceptions import ConflictError
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.extensions import db
from app.modules.appointment.models.appointment_model import Appointment
from app.modules.appointment.services import appointment_service


def test_confirm_appointment_is_single_winner_under_concurrency(
    monkeypatch,
):
    database_url = os.getenv(
        "CONCURRENCY_TEST_DATABASE_URL"
    )

    if not database_url:
        pytest.fail(
            "CONCURRENCY_TEST_DATABASE_URL is required"
        )

    original_database_url = (
        config_by_name["testing"].SQLALCHEMY_DATABASE_URI
    )
    from app import extensions

    original_redis_client = (
        extensions.redis_client
    )

    config_by_name["testing"].SQLALCHEMY_DATABASE_URI = (
        database_url
    )

    app = create_app("testing")
    extensions.redis_client = original_redis_client

    monkeypatch.setattr(
        appointment_service,
        "create_audit_log",
        lambda *args, **kwargs: None,
    )

    query_barrier = Barrier(2)

    original_get_appointment = (
        appointment_service._get_appointment
    )

    def synchronized_get_appointment(*args, **kwargs):
        query_barrier.wait(
            timeout=15
        )

        return original_get_appointment(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        appointment_service,
        "_get_appointment",
        synchronized_get_appointment,
    )

    try:
        with app.app_context():
            from app.core.auth.user.models.user_model import User
            from app.modules.clinic.models.clinic_model import Clinic
            from app.modules.patient.models.patient_model import Patient
            from app.modules.staff.models.staff_model import Staff
            from app import models_registry  # noqa: F401

            db.drop_all()
            db.create_all()

            clinic = Clinic(
                name="Gate 9 Appointment Clinic",
                status=ClinicStatus.ACTIVE,
                ai_credits=5,
            )

            db.session.add(clinic)
            db.session.flush()

            user = User(
                clinic_id=clinic.id,
                role=Role.ADMIN,
                is_active=True,
                email="gate9-appointment@test.com",
            )

            user.set_password(
                "supersecret"
            )

            db.session.add(user)
            db.session.flush()

            staff = Staff(
                clinic_id=clinic.id,
                user_id=user.id,
                first_name="Gate",
                last_name="Nine",
            )

            patient = Patient(
                clinic_id=clinic.id,
                first_name="Race",
                last_name="Patient",
                patient_number="G9-MRN-001",
            )

            db.session.add_all(
                [
                    staff,
                    patient,
                ]
            )

            db.session.flush()

            scheduled_start = (
                datetime.now(timezone.utc)
                + timedelta(days=1)
            )

            appointment = Appointment(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                scheduled_start=scheduled_start,
                scheduled_end=(
                    scheduled_start
                    + timedelta(hours=1)
                ),
                status=AppointmentStatus.SCHEDULED,
                appointment_type=AppointmentType.IN_PERSON,
            )

            db.session.add(
                appointment
            )

            db.session.commit()

            appointment_id = appointment.id
            clinic_id = clinic.id

        from app.tests.core.concurrency.concurrency_harness import (
            PostgresConcurrencyHarness,
        )

        harness = PostgresConcurrencyHarness(
            database_url
        )

        try:
            def confirm(worker_index):
                try:
                    result = (
                        appointment_service.confirm_appointment(
                            appointment_id,
                            clinic_id=clinic_id,
                        )
                    )

                    return {
                        "worker_index": worker_index,
                        "outcome": "accepted",
                        "status": result.status.value,
                    }

                except Exception as exc:
                    return {
                        "worker_index": worker_index,
                        "outcome": "rejected",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }

            results = harness.run_flask(
                app,
                confirm,
            )

            assert len(results) == 2

            assert all(
                result.error is None
                for result in results
            )

            backend_pids = {
                result.backend_pid
                for result in results
            }

            assert len(backend_pids) == 2

            values = [
                result.value
                for result in results
            ]

            accepted = [
                value
                for value in values
                if value["outcome"] == "accepted"
            ]

            rejected = [
                value
                for value in values
                if value["outcome"] == "rejected"
            ]

            assert len(accepted) == 1

            assert accepted[0]["status"] == (
                AppointmentStatus.CONFIRMED.value
            )

            assert len(rejected) == 1

            assert rejected[0]["error_type"] == (
                ConflictError.__name__
            )

            with app.app_context():
                final_appointment = (
                    db.session.execute(
                        select(
                            Appointment
                        ).where(
                            Appointment.id
                            == appointment_id
                        )
                    ).scalar_one()
                )

                assert final_appointment.status == (
                    AppointmentStatus.CONFIRMED
                )
        finally:
            harness.close()

    finally:

        with app.app_context():
            db.session.rollback()
            db.drop_all()
            db.session.remove()

            try:
                db.engine.dispose()
            except Exception:
                pass

        config_by_name["testing"].SQLALCHEMY_DATABASE_URI = (
            original_database_url
        )

        extensions.redis_client = (
            original_redis_client
        )
