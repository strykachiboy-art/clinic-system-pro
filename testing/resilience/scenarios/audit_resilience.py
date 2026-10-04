from __future__ import annotations

import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.enums.audit_enums import AuditAction
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


def _inject_commit_fault(
    db_session,
    injector: FaultInjector,
    monkeypatch,
) -> None:
    original_commit = db_session.commit

    def commit_with_fault():
        injector.inject(
            "postgres",
            operation="commit",
        )
        original_commit()

    monkeypatch.setattr(
        db_session,
        "commit",
        commit_with_fault,
    )


def test_audit_patient_write_and_read_round_trip(
    db_session,
    clinic,
    user,
):
    patient = create_patient(
        clinic.id,
        {
            "first_name": "Audit",
            "last_name": "Resilience",
            "email": "audit-resilience@test.com",
        },
        actor_id=user.id,
    )

    audit_logs = db_session.execute(
        db.select(AuditLog)
        .where(
            AuditLog.clinic_id == clinic.id,
            AuditLog.entity_type == "patient",
            AuditLog.entity_id == patient.id,
            AuditLog.user_id == user.id,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert len(audit_logs) == 1

    assert audit_logs[0].action == (
        AuditAction.CREATE
    )

    assert audit_logs[0].clinic_id == (
        clinic.id
    )


def test_patient_and_audit_rollback_together(
    db_session,
    clinic,
    user,
    monkeypatch,
):
    db_session.commit()

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
            AuditLog.clinic_id == clinic.id,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    injector = FaultInjector(
        seed=900,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.TIMEOUT,
        operation="commit",
        max_occurrences=1,
    )

    _inject_commit_fault(
        db_session,
        injector,
        monkeypatch,
    )

    with pytest.raises(
        InjectedTimeoutError,
        match="Injected timeout",
    ):
        create_patient(
            clinic.id,
            {
                "first_name": "Audit",
                "last_name": "Failure",
                "email": "audit-failure@test.com",
            },
            actor_id=user.id,
        )

    after_patients = db_session.execute(
        db.select(Patient.id)
        .where(
            Patient.clinic_id == clinic.id,
        )
        .order_by(
            Patient.id.asc(),
        )
    ).scalars().all()

    after_audits = db_session.execute(
        db.select(AuditLog.id)
        .where(
            AuditLog.clinic_id == clinic.id,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert after_patients == before_patients
    assert after_audits == before_audits

    injector.recover(
        "postgres",
    )

    recovered_patient = create_patient(
        clinic.id,
        {
            "first_name": "Audit",
            "last_name": "Recovered",
            "email": "audit-recovered@test.com",
        },
        actor_id=user.id,
    )

    assert recovered_patient.id is not None

    recovered_audits = db_session.execute(
        db.select(AuditLog)
        .where(
            AuditLog.clinic_id == clinic.id,
            AuditLog.entity_type == "patient",
            AuditLog.entity_id == recovered_patient.id,
            AuditLog.user_id == user.id,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert len(recovered_audits) == 1

    assert recovered_audits[0].action == (
        AuditAction.CREATE
    )