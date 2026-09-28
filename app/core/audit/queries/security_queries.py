from __future__ import annotations

from typing import Optional

from app.extensions import db

from app.core.audit.models.audit_model import AuditLog
from app.core.audit.queries.audit_queries import build_audit_query
from app.core.enums.audit_enums import AuditAction


SECURITY_ACTIONS = frozenset(
    {
        AuditAction.LOGIN,
        AuditAction.LOGOUT,
    }
)


def _validate_positive_id(
    value,
    field_name: str,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValueError(
            f"{field_name} must be a positive integer"
        )


def _build_security_query(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    target_clinic_id: Optional[int] = None,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    statement = build_audit_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    return statement.where(
        AuditLog.action.in_(SECURITY_ACTIONS)
    )


def get_security_events(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    target_clinic_id: Optional[int] = None,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    statement = _build_security_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    return db.session.execute(
        statement
    ).scalars().all()


def get_security_event_page(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    target_clinic_id: Optional[int] = None,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    page: int = 1,
    per_page: int = 20,
):
    statement = _build_security_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    return db.paginate(
        statement,
        page=page,
        per_page=per_page,
        error_out=False,
    )


def count_security_events(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    target_clinic_id: Optional[int] = None,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> int:
    statement = _build_security_query(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        user_id=user_id,
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


def get_user_security_events(
    *,
    actor_role,
    actor_clinic_id: Optional[int],
    target_user_id: int,
    target_clinic_id: Optional[int] = None,
):
    _validate_positive_id(
        target_user_id,
        "Target user ID",
    )

    return get_security_events(
        actor_role=actor_role,
        actor_clinic_id=actor_clinic_id,
        target_clinic_id=target_clinic_id,
        user_id=target_user_id,
    )