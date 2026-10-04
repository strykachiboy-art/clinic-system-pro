from __future__ import annotations

import pytest

from app import extensions
from app.core.audit.models.audit_model import AuditLog
from app.extensions import db
from app.modules.patient.models.patient_model import Patient
from app.modules.patient.services.patient_service import (
    create_patient,
)
from resilience.common.faults import (
    FaultInjector,
    FaultType,
    InjectedTimeoutError,
)
from redis.exceptions import ConnectionError


PROFILE_ENDPOINT = "/api/v1/profile/me"


def _commit_with_fault(
    db_session,
    injector: FaultInjector,
    monkeypatch,
) -> None:
    original_commit = db_session.commit

    def commit_with_injection() -> None:
        injector.inject(
            "postgres",
            operation="commit",
        )
        original_commit()

    monkeypatch.setattr(
        db_session,
        "commit",
        commit_with_injection,
    )


def test_system_recovers_across_database_and_redis_failure(
    db_session,
    clinic,
    client,
    user,
    auth_headers_for,
    monkeypatch,
):
    db_session.commit()

    injector = FaultInjector(
        seed=700,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.TIMEOUT,
        operation="commit",
        max_occurrences=1,
    )

    _commit_with_fault(
        db_session,
        injector,
        monkeypatch,
    )

    before_patients = db_session.execute(
        db.select(Patient.id)
        .where(
            Patient.clinic_id == clinic.id,
        )
        .order_by(
            Patient.id.asc(),
        )
    ).scalars().all()

    before_audits = db_session.execute(
        db.select(AuditLog.id)
        .where(
            AuditLog.entity_type == "patient",
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    with pytest.raises(
        InjectedTimeoutError,
        match="Injected timeout",
    ):
        create_patient(
            clinic.id,
            {
                "first_name": "Recovery",
                "last_name": "DatabaseFailure",
                "email": "recovery-database-failure@test.com",
            },
        )

    after_failure_patients = db_session.execute(
        db.select(Patient.id)
        .where(
            Patient.clinic_id == clinic.id,
        )
        .order_by(
            Patient.id.asc(),
        )
    ).scalars().all()

    after_failure_audits = db_session.execute(
        db.select(AuditLog.id)
        .where(
            AuditLog.entity_type == "patient",
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert after_failure_patients == before_patients
    assert after_failure_audits == before_audits

    injector.recover(
        "postgres",
    )

    recovered_patient = create_patient(
        clinic.id,
        {
            "first_name": "Recovery",
            "last_name": "DatabaseRecovered",
            "email": "recovery-database-recovered@test.com",
        },
    )

    assert recovered_patient.id is not None

    db_session.expire_all()

    persisted_patient = db_session.get(
        Patient,
        recovered_patient.id,
    )

    assert persisted_patient is not None
    assert persisted_patient.clinic_id == clinic.id
    assert persisted_patient.email == (
        "recovery-database-recovered@test.com"
    )

    redis_client = extensions.redis_client

    calls = {
        "count": 0,
    }

    def fail_once_then_recover(_key):
        calls["count"] += 1

        if calls["count"] == 1:
            raise ConnectionError(
                "Synthetic transient Redis recovery failure"
            )

        return 0

    monkeypatch.setattr(
        redis_client,
        "exists",
        fail_once_then_recover,
    )

    first_response = client.get(
        PROFILE_ENDPOINT,
        headers=auth_headers_for(user),
    )

    assert first_response.status_code == 401

    second_response = client.get(
        PROFILE_ENDPOINT,
        headers=auth_headers_for(user),
    )

    assert second_response.status_code == 200
    assert calls["count"] == 2

    db_session.expire_all()

    persisted_again = db_session.get(
        Patient,
        recovered_patient.id,
    )

    assert persisted_again is not None
    assert persisted_again.email == (
        "recovery-database-recovered@test.com"
    )

    persisted_audits = db_session.execute(
        db.select(AuditLog)
        .where(
            AuditLog.entity_type == "patient",
            AuditLog.entity_id == recovered_patient.id,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert len(persisted_audits) == 1