from __future__ import annotations

from sqlalchemy.orm import aliased

from app.core.audit.models.audit_model import AuditLog
from app.extensions import db
from app.modules.patient.models.patient_model import (
    Patient,
    PatientFamilyMember,
)


def find_orphan_family_member_ids(session) -> list[int]:
    return session.execute(
        db.select(PatientFamilyMember.id)
        .outerjoin(
            Patient,
            Patient.id == PatientFamilyMember.patient_id,
        )
        .where(
            PatientFamilyMember.patient_id.is_not(None),
            Patient.id.is_(None),
        )
        .order_by(
            PatientFamilyMember.id.asc(),
        )
    ).scalars().all()


def find_missing_related_patient_ids(session) -> list[int]:
    related_patient = aliased(Patient)

    return session.execute(
        db.select(PatientFamilyMember.id)
        .outerjoin(
            related_patient,
            related_patient.id
            == PatientFamilyMember.related_patient_id,
        )
        .where(
            PatientFamilyMember.related_patient_id.is_not(None),
            related_patient.id.is_(None),
        )
        .order_by(
            PatientFamilyMember.id.asc(),
        )
    ).scalars().all()


def find_cross_clinic_family_member_ids(session) -> list[int]:
    related_patient = aliased(Patient)

    return session.execute(
        db.select(PatientFamilyMember.id)
        .join(
            Patient,
            Patient.id == PatientFamilyMember.patient_id,
        )
        .join(
            related_patient,
            related_patient.id
            == PatientFamilyMember.related_patient_id,
        )
        .where(
            PatientFamilyMember.related_patient_id.is_not(None),
            Patient.clinic_id != related_patient.clinic_id,
        )
        .order_by(
            PatientFamilyMember.id.asc(),
        )
    ).scalars().all()


def find_orphan_family_member_audit_ids(session) -> list[int]:
    return session.execute(
        db.select(AuditLog.id)
        .outerjoin(
            PatientFamilyMember,
            (
                (AuditLog.entity_type == "patient_family_member")
                & (AuditLog.entity_id == PatientFamilyMember.id)
            ),
        )
        .where(
            AuditLog.entity_type == "patient_family_member",
            PatientFamilyMember.id.is_(None),
        )
        .order_by(
            AuditLog.id.asc(),
        )
    ).scalars().all()


def collect_patient_data_integrity_issues(
    session,
) -> dict[str, list[int]]:
    return {
        "orphan_family_members": (
            find_orphan_family_member_ids(session)
        ),
        "missing_related_patients": (
            find_missing_related_patient_ids(session)
        ),
        "cross_clinic_family_members": (
            find_cross_clinic_family_member_ids(session)
        ),
        "orphan_family_member_audits": (
            find_orphan_family_member_audit_ids(session)
        ),
    }


def assert_patient_data_integrity(session) -> None:
    issues = collect_patient_data_integrity_issues(session)

    assert not issues["orphan_family_members"], (
        "Orphan family members detected: "
        f"{issues['orphan_family_members']}"
    )

    assert not issues["missing_related_patients"], (
        "Family members reference missing related patients: "
        f"{issues['missing_related_patients']}"
    )

    assert not issues["cross_clinic_family_members"], (
        "Cross-clinic family relationships detected: "
        f"{issues['cross_clinic_family_members']}"
    )

    assert not issues["orphan_family_member_audits"], (
        "Audit logs reference missing family members: "
        f"{issues['orphan_family_member_audits']}"
    )
