from __future__ import annotations

from typing import Optional

from app.extensions import db

from app.core.audit.queries.audit_queries import (
    build_audit_query,
)
from app.core.enums.audit_enums import AuditAction


PATIENT_ENTITY_TYPE = "Patient"


def get_patient_timeline(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    patient_id: int,
    target_clinic_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
):
    statement = build_audit_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        action=action,
        entity_type=PATIENT_ENTITY_TYPE,
        entity_id=patient_id,
    )

    return db.session.execute(
        statement
    ).scalars().all()


def get_patient_timeline_page(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    patient_id: int,
    target_clinic_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
    page: int = 1,
    per_page: int = 20,
):
    statement = build_audit_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        action=action,
        entity_type=PATIENT_ENTITY_TYPE,
        entity_id=patient_id,
    )

    return db.paginate(
        statement,
        page=page,
        per_page=per_page,
        error_out=False,
    )


def count_patient_timeline(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    patient_id: int,
    target_clinic_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
) -> int:
    statement = build_audit_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        action=action,
        entity_type=PATIENT_ENTITY_TYPE,
        entity_id=patient_id,
    ).order_by(None)

    count_statement = db.select(
        db.func.count()
    ).select_from(
        statement.subquery()
    )

    return int(
        db.session.execute(
            count_statement
        ).scalar_one()
    )