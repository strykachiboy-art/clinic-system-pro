from __future__ import annotations

import os
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app import create_app, extensions
from app.config import config_by_name
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.role_enums import Role
from app.core.auth.user.models.user_model import User
from app.core.idempotency.models.idempotency_model import (
    IdempotencyRecord,
)
from app.core.idempotency.services import idempotency_service
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic


def test_idempotency_reservation_is_created_once_under_concurrency(
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

    gate = Barrier(2)

    harness = None

    try:
        with app.app_context():
            from app import models_registry  # noqa: F401

            db.drop_all()
            db.create_all()

            clinic = Clinic(
                name="Gate 9 Idempotency Clinic",
                status=ClinicStatus.ACTIVE,
                ai_credits=5,
            )

            db.session.add(clinic)
            db.session.flush()

            user = User(
                clinic_id=clinic.id,
                role=Role.PHARMACIST,
                is_active=True,
                email="gate9-idempotency@test.com",
            )

            user.set_password("supersecret")

            db.session.add(user)
            db.session.commit()

            clinic_id = clinic.id
            user_id = user.id

        from app.tests.core.concurrency.concurrency_harness import (
            PostgresConcurrencyHarness,
        )

        harness = PostgresConcurrencyHarness(
            database_url
        )

        def reserve(worker_index):
            gate.wait(timeout=15)

            try:
                record, is_new = (
                    idempotency_service.reserve_idempotency_operation(
                        clinic_id=clinic_id,
                        user_id=user_id,
                        operation="gate9.concurrency.create",
                        idempotency_key="gate9-race-001",
                        request_payload={
                            "resource": "test",
                            "value": 1,
                        },
                    )
                )

                db.session.commit()

                return {
                    "worker_index": worker_index,
                    "record_id": record.id,
                    "is_new": is_new,
                    "request_hash": record.request_hash,
                }

            except Exception:
                db.session.rollback()
                raise

        results = harness.run_flask(
            app,
            reserve,
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

        assert sum(
            value["is_new"]
            for value in values
        ) == 1

        assert len({
            value["record_id"]
            for value in values
        }) == 1

        assert len({
            value["request_hash"]
            for value in values
        }) == 1

        with app.app_context():
            record_count = db.session.execute(
                select(
                    func.count(
                        IdempotencyRecord.id
                    )
                ).where(
                    IdempotencyRecord.clinic_id
                    == clinic_id,
                    IdempotencyRecord.user_id
                    == user_id,
                    IdempotencyRecord.operation
                    == "gate9.concurrency.create",
                    IdempotencyRecord.idempotency_key
                    == "gate9-race-001",
                )
            ).scalar_one()

            assert record_count == 1

            record = db.session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.clinic_id
                    == clinic_id,
                    IdempotencyRecord.user_id
                    == user_id,
                    IdempotencyRecord.operation
                    == "gate9.concurrency.create",
                    IdempotencyRecord.idempotency_key
                    == "gate9-race-001",
                )
            ).scalar_one()

            assert record.id in {
                value["record_id"]
                for value in values
            }

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