from __future__ import annotations

import pytest

from app.core.audit.models.audit_model import AuditLog
from app.extensions import db
from app.modules.patient.models.patient_model import Patient
from app.modules.patient.services.patient_service import (
    create_patient,
)

from load_tests.resilience.common.faults import (
    FaultInjector,
    FaultType,
    InjectedConnectionError,
    InjectedTimeoutError,
)


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


def _patient_ids(
    clinic_id: int,
) -> list[int]:
    return db.session.execute(
        db.select(Patient.id)
        .where(
            Patient.clinic_id == clinic_id,
        )
        .order_by(
            Patient.id.asc(),
        )
    ).scalars().all()


def _patient_audit_ids() -> list[int]:
    return db.session.execute(
        db.select(AuditLog.id)
        .where(
            AuditLog.entity_type == "patient",
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()


def _patient_payload(
    suffix: str,
) -> dict:
    return {
        "first_name": "Resilience",
        "last_name": suffix,
        "email": f"resilience-{suffix.lower()}@test.com",
    }


def test_postgres_commit_timeout_rolls_back_patient_creation(
    app,
    db_session,
    clinic,
    monkeypatch,
):
    db_session.commit()

    injector = FaultInjector(
        seed=123,
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

    before_patient_ids = _patient_ids(
        clinic.id,
    )

    before_audit_ids = _patient_audit_ids()

    with pytest.raises(
        InjectedTimeoutError,
        match="Injected timeout",
    ):
        create_patient(
            clinic.id,
            _patient_payload("Timeout"),
        )

    after_patient_ids = _patient_ids(
        clinic.id,
    )

    after_audit_ids = _patient_audit_ids()

    assert after_patient_ids == (
        before_patient_ids
    )

    assert after_audit_ids == (
        before_audit_ids
    )

    injector.recover(
        "postgres",
    )

    patient = create_patient(
        clinic.id,
        _patient_payload("Recovered"),
    )

    assert patient.id is not None

    db_session.expire_all()

    persisted_patient = db_session.get(
        Patient,
        patient.id,
    )

    assert persisted_patient is not None

    recovered_patient_ids = _patient_ids(
        clinic.id,
    )

    assert recovered_patient_ids == (
        before_patient_ids
        + [patient.id]
    )


def test_postgres_connection_failure_rolls_back_and_recovers(
    app,
    db_session,
    clinic,
    monkeypatch,
):
    db_session.commit()

    injector = FaultInjector(
        seed=456,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.CONNECTION_FAILURE,
        operation="commit",
        max_occurrences=1,
    )

    _commit_with_fault(
        db_session,
        injector,
        monkeypatch,
    )

    before_patient_ids = _patient_ids(
        clinic.id,
    )

    with pytest.raises(
        InjectedConnectionError,
        match="Injected connection failure",
    ):
        create_patient(
            clinic.id,
            _patient_payload("ConnectionFailure"),
        )

    after_failure_patient_ids = _patient_ids(
        clinic.id,
    )

    assert after_failure_patient_ids == (
        before_patient_ids
    )

    injector.recover(
        "postgres",
    )

    recovered = create_patient(
        clinic.id,
        _patient_payload("ConnectionRecovered"),
    )

    assert recovered.id is not None

    db_session.expire_all()

    persisted = db_session.get(
        Patient,
        recovered.id,
    )

    assert persisted is not None
    assert persisted.first_name == "Resilience"
    assert persisted.last_name == (
        "ConnectionRecovered"
    )

    final_patient_ids = _patient_ids(
        clinic.id,
    )

    assert final_patient_ids == (
        before_patient_ids
        + [recovered.id]
    )