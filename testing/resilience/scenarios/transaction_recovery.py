from __future__ import annotations

import pytest

from app.core.audit.models.audit_model import AuditLog
from app.extensions import db
from app.modules.patient.models.patient_model import (
    Patient,
    PatientFamilyMember,
)
from app.modules.patient.services import (
    patient_service,
)

from resilience.common.faults import (
    FaultInjector,
    FaultType,
    InjectedFault,
)


def _raise_after_flush(
    injector: FaultInjector,
):
    def _audit_failure(**kwargs):
        injector.inject(
            "postgres",
            operation="audit_write",
        )

    return _audit_failure


def test_failed_patient_transaction_recovers_for_retry(
    db_session,
    clinic,
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

    injector = FaultInjector(
        seed=400,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.PARTIAL_FAILURE,
        operation="audit_write",
        max_occurrences=1,
    )

    original_audit = patient_service._audit

    monkeypatch.setattr(
        patient_service,
        "_audit",
        _raise_after_flush(
            injector,
        ),
    )

    with pytest.raises(
        InjectedFault,
        match="Injected partial_failure",
    ):
        patient_service.create_patient(
            clinic.id,
            {
                "first_name": "Recovery",
                "last_name": "Failure",
                "email": "recovery-failure@test.com",
            },
        )

    db_session.expire_all()

    after_failure_patients = db_session.execute(
        db.select(Patient.id)
        .where(
            Patient.clinic_id == clinic.id,
        )
        .order_by(
            Patient.id.asc(),
        )
    ).scalars().all()

    assert after_failure_patients == before_patients

    injector.recover(
        "postgres",
    )

    monkeypatch.setattr(
        patient_service,
        "_audit",
        original_audit,
    )

    recovered_patient = (
        patient_service.create_patient(
            clinic.id,
            {
                "first_name": "Recovered",
                "last_name": "Patient",
                "email": "recovered@test.com",
            },
        )
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
        "recovered@test.com"
    )

    persisted_audit = db_session.execute(
        db.select(AuditLog)
        .where(
            AuditLog.entity_type == "patient",
            AuditLog.entity_id == recovered_patient.id,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert len(persisted_audit) == 1


def test_failed_family_member_transaction_recovers_for_retry(
    db_session,
    clinic,
    make_patient,
    monkeypatch,
):
    patient = make_patient(
        clinic,
    )

    db_session.commit()

    before_members = db_session.execute(
        db.select(PatientFamilyMember.id)
        .where(
            PatientFamilyMember.patient_id
            == patient.id,
        )
        .order_by(
            PatientFamilyMember.id.asc(),
        )
    ).scalars().all()

    injector = FaultInjector(
        seed=500,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.PARTIAL_FAILURE,
        operation="audit_write",
        max_occurrences=1,
    )

    original_audit = patient_service._audit

    monkeypatch.setattr(
        patient_service,
        "_audit",
        _raise_after_flush(
            injector,
        ),
    )

    with pytest.raises(
        InjectedFault,
        match="Injected partial_failure",
    ):
        patient_service.add_family_member(
            patient.id,
            {
                "full_name": "Recovery Member",
                "relation": "sibling",
                "phone": "+2348111111111",
            },
        )

    db_session.expire_all()

    after_failure_members = db_session.execute(
        db.select(PatientFamilyMember.id)
        .where(
            PatientFamilyMember.patient_id
            == patient.id,
        )
        .order_by(
            PatientFamilyMember.id.asc(),
        )
    ).scalars().all()

    assert after_failure_members == before_members

    injector.recover(
        "postgres",
    )

    monkeypatch.setattr(
        patient_service,
        "_audit",
        original_audit,
    )

    recovered_member = (
        patient_service.add_family_member(
            patient.id,
            {
                "full_name": "Recovery Member",
                "relation": "sibling",
                "phone": "+2348111111111",
            },
        )
    )

    assert recovered_member.id is not None

    db_session.expire_all()

    persisted_members = db_session.execute(
        db.select(PatientFamilyMember)
        .where(
            PatientFamilyMember.patient_id
            == patient.id,
        )
        .order_by(
            PatientFamilyMember.id.asc(),
        )
    ).scalars().all()

    assert len(persisted_members) == (
        len(before_members) + 1
    )

    matching_members = [
        member
        for member in persisted_members
        if member.full_name == "Recovery Member"
    ]

    assert len(matching_members) == 1
    assert matching_members[0].id == recovered_member.id

    persisted_audits = db_session.execute(
        db.select(AuditLog)
        .where(
            AuditLog.entity_type
            == "patient_family_member",
            AuditLog.entity_id
            == recovered_member.id,
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert len(persisted_audits) == 1