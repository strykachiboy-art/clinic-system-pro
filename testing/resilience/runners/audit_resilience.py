from __future__ import annotations

import pytest

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.queries.patient_timeline import (
    get_patient_timeline,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
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


def test_audit_patient_timeline_round_trip(
    db_session,
    clinic,
    user,
):
    patient = create_patient(
        clinic.id,
        {
            "first_name": "Audit",
            "last_name": "RoundTrip",
            "email": "audit-roundtrip@test.com",
        },
        actor_id=user.id,
    )

    events = get_patient_timeline(
        actor_role=Role.ADMIN,
        actor_clinic_id=clinic.id,
        patient_id=patient.id,
    )

    assert len(events) == 1
    assert events[0].entity_id == patient.id
    assert events[0].entity_type == "patient"
    assert events[0].user_id == user.id
    assert events[0].clinic_id == clinic.id
    assert events[0].action == AuditAction.CREATE


def test_audit_and_patient_rollback_together(
    db_session,
    clinic,
    user,
    monkeypatch,
):
    db_session.commit()

    injector = FaultInjector(
        seed=900,
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
            AuditLog.clinic_id == clinic.id,
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
            AuditLog.entity_type == "patient",
            AuditLog.entity_id == recovered_patient.id,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert len(recovered_audits) == 1
    assert recovered_audits[0].user_id == user.id
    assert recovered_audits[0].clinic_id == clinic.id