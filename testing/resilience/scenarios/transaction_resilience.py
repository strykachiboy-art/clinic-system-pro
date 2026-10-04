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


def test_failure_after_patient_flush_rolls_back_patient_and_audit(
    db_session,
    clinic,
    monkeypatch,
):
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

    injector = FaultInjector(
        seed=100,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.PARTIAL_FAILURE,
        operation="audit_write",
        max_occurrences=1,
    )

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
                "first_name": "Partial",
                "last_name": "Failure",
                "email": "partial@test.com",
            },
        )

    db_session.expire_all()

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
            AuditLog.entity_type == "patient",
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()

    assert after_patients == before_patients
    assert after_audits == before_audits


def test_failure_after_family_member_flush_does_not_leave_orphan_record(
    db_session,
    clinic,
    make_patient,
    monkeypatch,
):
    patient = make_patient(
        clinic,
    )

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
        seed=200,
    )

    injector.add_fault(
        dependency="postgres",
        fault_type=FaultType.PARTIAL_FAILURE,
        operation="audit_write",
        max_occurrences=1,
    )

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
                "full_name": "Orphan Candidate",
                "relation": "Sibling",
                "phone": "+2348000000000",
            },
        )

    db_session.expire_all()

    after_members = db_session.execute(
        db.select(PatientFamilyMember.id)
        .where(
            PatientFamilyMember.patient_id
            == patient.id,
        )
        .order_by(
            PatientFamilyMember.id.asc(),
        )
    ).scalars().all()

    assert after_members == before_members

    orphan = db_session.execute(
        db.select(PatientFamilyMember)
        .where(
            PatientFamilyMember.full_name
            == "Orphan Candidate",
        )
    ).scalar_one_or_none()

    assert orphan is None
