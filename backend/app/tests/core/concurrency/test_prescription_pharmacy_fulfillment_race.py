from __future__ import annotations

import os
from datetime import date, timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app import create_app, extensions
from app.config import config_by_name
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.pharmacy_enums import DispenseStatus
from app.core.enums.prescription_enums import PrescriptionStatus
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError
from app.core.auth.user.models.user_model import User
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.patient.models.patient_model import Patient
from app.modules.pharmacy.models.pharmacy_model import (
    DispenseItem,
    DispenseRecord,
    Drug,
    DrugBatch,
)
from app.modules.pharmacy.services import pharmacy_service
from app.modules.prescription.models.prescription_model import (
    Prescription,
    PrescriptionItem,
)
from app.modules.staff.models.staff_model import Staff


def test_prescription_quantity_is_fulfilled_only_once_under_concurrency(
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

    original_redis_client = (
        extensions.redis_client
    )

    config_by_name["testing"].SQLALCHEMY_DATABASE_URI = (
        database_url
    )

    app = create_app("testing")

    extensions.redis_client = (
        original_redis_client
    )

    monkeypatch.setattr(
        pharmacy_service,
        "create_audit_log",
        lambda *args, **kwargs: None,
    )

    gate = Barrier(2)

    original_ensure_clinic_active = (
        pharmacy_service.ensure_clinic_active
    )

    def synchronized_ensure_clinic_active(
        clinic_id,
    ):
        gate.wait(
            timeout=15
        )

        return original_ensure_clinic_active(
            clinic_id
        )

    monkeypatch.setattr(
        pharmacy_service,
        "ensure_clinic_active",
        synchronized_ensure_clinic_active,
    )

    harness = None

    try:
        with app.app_context():
            from app import models_registry  # noqa: F401

            db.drop_all()
            db.create_all()

            clinic = Clinic(
                name="Gate 9 Prescription Clinic",
                status=ClinicStatus.ACTIVE,
                ai_credits=5,
            )

            db.session.add(clinic)
            db.session.flush()

            user = User(
                clinic_id=clinic.id,
                role=Role.PHARMACIST,
                is_active=True,
                email="gate9-prescription@test.com",
            )

            user.set_password("supersecret")

            db.session.add(user)
            db.session.flush()

            staff = Staff(
                clinic_id=clinic.id,
                user_id=user.id,
                first_name="Gate",
                last_name="Prescription",
                status=StaffStatus.ACTIVE,
            )

            patient = Patient(
                clinic_id=clinic.id,
                first_name="Race",
                last_name="Patient",
                patient_number="G9-PRESC-MRN-001",
            )

            drug = Drug(
                clinic_id=clinic.id,
                name="Gate 9 Fulfillment Drug",
                is_active=True,
            )

            db.session.add_all(
                [
                    staff,
                    patient,
                    drug,
                ]
            )
            db.session.flush()

            batch = DrugBatch(
                clinic_id=clinic.id,
                drug_id=drug.id,
                batch_number="G9-PRESC-BATCH-001",
                quantity_on_hand=2,
                reorder_level=0,
                expiry_date=(
                    date.today()
                    + timedelta(days=90)
                ),
            )

            prescription = Prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=staff.id,
                status=PrescriptionStatus.ACTIVE,
            )

            db.session.add_all(
                [
                    batch,
                    prescription,
                ]
            )
            db.session.flush()

            prescription_item = PrescriptionItem(
                prescription_id=prescription.id,
                drug_id=drug.id,
                quantity=1,
            )

            db.session.add(
                prescription_item
            )

            db.session.commit()

            clinic_id = clinic.id
            prescription_id = prescription.id
            staff_id = staff.id
            prescription_item_id = prescription_item.id
            batch_id = batch.id

        from app.tests.core.concurrency.concurrency_harness import (
            PostgresConcurrencyHarness,
        )

        harness = PostgresConcurrencyHarness(
            database_url
        )

        def dispense(worker_index):
            try:
                result = pharmacy_service.create_dispense_record(
                    clinic_id=clinic_id,
                    prescription_id=prescription_id,
                    dispensed_by_id=staff_id,
                    items=[
                        {
                            "prescription_item_id": (
                                prescription_item_id
                            ),
                            "batch_id": batch_id,
                            "quantity": 1,
                        }
                    ],
                )

                return {
                    "worker_index": worker_index,
                    "outcome": "accepted",
                    "dispense_record_id": result.id,
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
            dispense,
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
            DispenseStatus.DISPENSED.value
        )

        assert len(rejected) == 1

        assert rejected[0]["error_type"] == (
            ConflictError.__name__
        )

        with app.app_context():
            final_batch = db.session.execute(
                select(DrugBatch).where(
                    DrugBatch.id == batch_id
                )
            ).scalar_one()

            assert final_batch.quantity_on_hand == 1

            dispense_count = db.session.execute(
                select(
                    func.count(
                        DispenseRecord.id
                    )
                ).where(
                    DispenseRecord.prescription_id
                    == prescription_id
                )
            ).scalar_one()

            assert dispense_count == 1

            dispense_item_count = db.session.execute(
                select(
                    func.count(
                        DispenseItem.id
                    )
                )
                .join(
                    DispenseRecord,
                    DispenseItem.dispense_record_id
                    == DispenseRecord.id,
                )
                .where(
                    DispenseRecord.prescription_id
                    == prescription_id
                )
            ).scalar_one()

            assert dispense_item_count == 1

    finally:
        if harness is not None:
            harness.close()

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