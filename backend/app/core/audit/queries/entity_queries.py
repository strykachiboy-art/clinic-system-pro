from __future__ import annotations

from typing import Optional

from app.extensions import db

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.queries.audit_queries import build_audit_query
from app.core.enums.audit_enums import AuditAction


def _validate_entity_type(
    entity_type: str,
) -> str:
    if not isinstance(entity_type, str):
        raise ValueError(
            "Entity type must be a string"
        )

    entity_type = entity_type.strip()

    if not entity_type:
        raise ValueError(
            "Entity type cannot be empty"
        )

    if len(entity_type) > 80:
        raise ValueError(
            "Entity type cannot exceed 80 characters"
        )

    return entity_type


def get_entity_audit_logs(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    entity_type: str,
    entity_id: int,
    target_clinic_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
):
    entity_type = _validate_entity_type(
        entity_type,
    )

    statement = build_audit_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    return db.session.execute(
        statement
    ).scalars().all()


def get_entity_audit_page(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    entity_type: str,
    entity_id: int,
    target_clinic_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
    page: int = 1,
    per_page: int = 20,
):
    entity_type = _validate_entity_type(
        entity_type,
    )

    statement = build_audit_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    return db.paginate(
        statement,
        page=page,
        per_page=per_page,
        error_out=False,
    )


def count_entity_audit_logs(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    entity_type: str,
    entity_id: int,
    target_clinic_id: Optional[int] = None,
    action: Optional[AuditAction] = None,
) -> int:
    entity_type = _validate_entity_type(
        entity_type,
    )

    statement = build_audit_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
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